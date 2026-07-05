#!/usr/bin/env python3
"""Download historical funding rate data from Binance Futures API.

Saves to data_lake/raw/binance/um/fundingRate/{SYMBOL}/YYYY/MM.parquet.

Usage:
    PYTHONPATH=. .venv/bin/python3 scripts/download_funding_rates.py [--symbols BTCUSDT,ETHUSDT] [--start 2023-01-01]
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests


BASE_URL = "https://fapi.binance.com"
FUNDING_RATE_ENDPOINT = "/fapi/v1/fundingRate"
MAX_LIMIT = 1000  # Binance max per request

DEFAULT_SYMBOLS = [
    "ADAUSDT", "APTUSDT", "ARBUSDT", "ATOMUSDT", "AVAXUSDT",
    "BNBUSDT", "BTCUSDT", "DOGEUSDT", "DOTUSDT", "ETHUSDT",
    "FILUSDT", "INJUSDT", "LINKUSDT", "MATICUSDT", "NEARUSDT",
    "OPUSDT", "RUNEUSDT", "SOLUSDT", "SUIUSDT", "XRPUSDT",
]


def download_funding_rates(
    symbol: str,
    start_ms: int,
    end_ms: int,
) -> pd.DataFrame:
    """Download all funding rates for a symbol in [start_ms, end_ms].

    Binance API returns max 1000 records per request. Funding rate is
    applied every 8 hours, so ~3 records/day = ~1095/year. For 3.5 years
    we need ~4000 records = ~4 requests per symbol.
    """
    all_records = []
    current_start = start_ms

    while current_start < end_ms:
        params = {
            "symbol": symbol,
            "startTime": current_start,
            "endTime": end_ms,
            "limit": MAX_LIMIT,
        }
        try:
            resp = requests.get(
                f"{BASE_URL}{FUNDING_RATE_ENDPOINT}",
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
        last_time = data[-1]["fundingTime"]
        current_start = last_time + 1

        # Rate limit: be gentle
        time.sleep(0.15)

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    df["funding_time"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
    df = df.set_index("funding_time")
    df = df[["symbol", "fundingRate", "markPrice"]]
    df.columns = ["symbol", "funding_rate", "mark_price"]
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

        # Ensure consistent columns and types
        save_df = group[["symbol", "funding_rate", "mark_price"]].copy()
        save_df.index.name = "funding_time"

        # Append if file exists
        if month_file.exists():
            existing = pd.read_parquet(month_file)
            # Normalize both to same columns
            combined = pd.concat([existing, save_df])
            combined = combined[~combined.index.duplicated(keep="last")]
            combined = combined.sort_index()
            combined.to_parquet(month_file)
        else:
            save_df.to_parquet(month_file)


def main():
    parser = argparse.ArgumentParser(description="Download Binance funding rate history")
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
    args = parser.parse_args()

    symbols = args.symbols.split(",") if args.symbols else DEFAULT_SYMBOLS
    start_dt = datetime.strptime(args.start, "%Y-%m-%d")
    end_dt = datetime.strptime(args.end, "%Y-%m-%d") if args.end else datetime.now()
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    base_dir = Path("data_lake/raw/binance/um/fundingRate")

    print(f"Downloading funding rates for {len(symbols)} symbols")
    print(f"  Period: {start_dt.date()} to {end_dt.date()}")
    print(f"  Output: {base_dir}/")
    print()

    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] {symbol}...", end=" ", flush=True)
        t0 = time.time()
        df = download_funding_rates(symbol, start_ms, end_ms)
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
