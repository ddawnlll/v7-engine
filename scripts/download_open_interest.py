#!/usr/bin/env python3
"""Download historical open interest data from Binance Futures API.

Uses fapi.binance.com/fapi/v1/openInterest which returns current open
interest for a symbol (single snapshot). For historical OI, uses
fapi.binance.com/futures/data/openInterestHist which provides historical
OI per time interval.

Saves to data_lake/raw/binance/um/openInterest/{SYMBOL}/YYYY/MM.parquet.

Usage:
    PYTHONPATH=. python3 scripts/download_open_interest.py [--symbols BTCUSDT,ETHUSDT] [--start 2023-01-01]
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests


BASE_URL = "https://fapi.binance.com"
OPEN_INTEREST_ENDPOINT = "/futures/data/openInterestHist"
MAX_LIMIT = 500  # Binance max per request for this endpoint

DEFAULT_SYMBOLS = [
    "ADAUSDT", "APTUSDT", "ARBUSDT", "ATOMUSDT", "AVAXUSDT",
    "BNBUSDT", "BTCUSDT", "DOGEUSDT", "DOTUSDT", "ETHUSDT",
    "FILUSDT", "INJUSDT", "LINKUSDT", "MATICUSDT", "NEARUSDT",
    "OPUSDT", "RUNEUSDT", "SOLUSDT", "SUIUSDT", "XRPUSDT",
]

# Interval mapping: Binance stores OI hist data in specific intervals
# '5m','15m','30m','1h','2h','4h','6h','12h','1d'
OI_INTERVAL = "1h"


def download_open_interest_hist(
    symbol: str,
    start_ms: int,
    end_ms: int,
    period: str = OI_INTERVAL,
) -> pd.DataFrame:
    """Download historical open interest for a symbol in [start_ms, end_ms].

    Binance API returns max 500 records per request. For 1h intervals
    (~24 records/day), a 3.5 year range needs ~51 requests per symbol.

    Returns OHLCV-like OI data with: symbol, sumOpenInterest, sumOpenInterestValue,
    timestamp (opening time of the OI period).
    """
    all_records = []
    current_start = start_ms

    while current_start < end_ms:
        params = {
            "symbol": symbol,
            "period": period,
            "startTime": current_start,
            "endTime": end_ms,
            "limit": MAX_LIMIT,
        }
        try:
            resp = requests.get(
                f"{BASE_URL}{OPEN_INTEREST_ENDPOINT}",
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"  WARNING: {symbol} request failed at {current_start}: {e}")
            time.sleep(2)
            continue

        if not data:
            break

        all_records.extend(data)

        # Move start past the last record
        last_time = data[-1]["timestamp"]
        current_start = last_time + 1

        # Rate limit: be gentle
        time.sleep(0.15)

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp")
    # Keep relevant columns
    cols = ["symbol", "sumOpenInterest", "sumOpenInterestValue"]
    available = [c for c in cols if c in df.columns]
    df = df[available]
    # Rename to clean names
    rename = {
        "sumOpenInterest": "open_interest",
        "sumOpenInterestValue": "open_interest_value",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    df = df[~df.index.duplicated(keep="last")]
    df = df.sort_index()
    return df


def save_by_month(df: pd.DataFrame, symbol: str, base_dir: Path) -> None:
    """Save DataFrame split by year/month into parquet files."""
    if df.empty:
        return

    for (year, month), group in df.groupby([df.index.year, df.index.month]):
        month_dir = base_dir / symbol / str(year)
        month_dir.mkdir(parents=True, exist_ok=True)
        month_file = month_dir / f"{month:02d}.parquet"

        cols = [c for c in ["symbol", "open_interest", "open_interest_value"] if c in df.columns]
        save_df = group[cols].copy()
        save_df.index.name = "timestamp"

        # Append if file exists
        if month_file.exists():
            existing = pd.read_parquet(month_file)
            combined = pd.concat([existing, save_df])
            combined = combined[~combined.index.duplicated(keep="last")]
            combined = combined.sort_index()
            combined.to_parquet(month_file)
        else:
            save_df.to_parquet(month_file)


def main():
    parser = argparse.ArgumentParser(description="Download Binance open interest history")
    parser.add_argument(
        "--symbols", type=str, default=None,
        help="Comma-separated symbols (default: all 20)"
    )
    parser.add_argument(
        "--start", type=str, default="2023-01-01",
        help="Start date YYYY-MM-DD (default: 2023-01-01)"
    )
    parser.add_argument(
        "--end", type=str, default=None,
        help="End date YYYY-MM-DD (default: today)"
    )
    parser.add_argument(
        "--period", type=str, default=OI_INTERVAL,
        help="OI histogram interval: 5m,15m,30m,1h,2h,4h,6h,12h,1d (default: 1h)"
    )
    args = parser.parse_args()

    symbols = args.symbols.split(",") if args.symbols else DEFAULT_SYMBOLS
    start_dt = datetime.strptime(args.start, "%Y-%m-%d")
    end_dt = datetime.strptime(args.end, "%Y-%m-%d") if args.end else datetime.now()
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    base_dir = Path("data_lake/raw/binance/um/openInterest")

    print(f"Downloading open interest history for {len(symbols)} symbols")
    print(f"  Period: {start_dt.date()} to {end_dt.date()}")
    print(f"  Interval: {args.period}")
    print(f"  Output: {base_dir}/")
    print()

    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] {symbol}...", end=" ", flush=True)
        t0 = time.time()
        df = download_open_interest_hist(symbol, start_ms, end_ms, args.period)
        elapsed = time.time() - t0

        if df.empty:
            print(f"No data ({elapsed:.1f}s)")
            continue

        save_by_month(df, symbol, base_dir)
        n_months = len(df.groupby([df.index.year, df.index.month]))
        print(f"{len(df)} records, {n_months} months ({elapsed:.1f}s)")

    print("\nDone.")


if __name__ == "__main__":
    main()
