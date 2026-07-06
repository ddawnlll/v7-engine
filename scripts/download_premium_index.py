#!/usr/bin/env python3
"""Download historical premium index data from Binance Futures API.

Uses fapi.binance.com/fapi/v1/premiumIndex which returns current state.
For historical data, uses fapi.binance.com/futures/data/premiumIndexKlines
or equivalently the markPriceKlines endpoint.

This script uses the premiumIndexKlines endpoint to get OHLCV-like
premium index candles per interval, which captures the basis between
mark price and index price over time.

Saves to data_lake/raw/binance/um/premiumIndex/{SYMBOL}/YYYY/MM.parquet.

Usage:
    PYTHONPATH=. python3 scripts/download_premium_index.py [--symbols BTCUSDT,ETHUSDT] [--start 2023-01-01]
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests


BASE_URL = "https://fapi.binance.com"
PREMIUM_INDEX_ENDPOINT = "/futures/data/premiumIndexKlines"
MAX_LIMIT = 1500  # Binance max per request for kline-like endpoints

DEFAULT_SYMBOLS = [
    "ADAUSDT", "APTUSDT", "ARBUSDT", "ATOMUSDT", "AVAXUSDT",
    "BNBUSDT", "BTCUSDT", "DOGEUSDT", "DOTUSDT", "ETHUSDT",
    "FILUSDT", "INJUSDT", "LINKUSDT", "MATICUSDT", "NEARUSDT",
    "OPUSDT", "RUNEUSDT", "SOLUSDT", "SUIUSDT", "XRPUSDT",
]

DEFAULT_INTERVAL = "1h"


def download_premium_index_klines(
    symbol: str,
    start_ms: int,
    end_ms: int,
    interval: str = DEFAULT_INTERVAL,
) -> pd.DataFrame:
    """Download premium index klines for a symbol in [start_ms, end_ms].

    Binance premiumIndexKlines returns OHLCV data for the premium index:
      [open_time, open, high, low, close, close_time]
    where open/close represent the premium index (basis) value.

    For ~24 records/day at 1h, a 3.5 year range needs ~21 requests.
    """
    all_records = []
    current_start = start_ms

    while current_start < end_ms:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": current_start,
            "endTime": end_ms,
            "limit": MAX_LIMIT,
        }
        try:
            resp = requests.get(
                f"{BASE_URL}{PREMIUM_INDEX_ENDPOINT}",
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
        last_time = data[-1][0]
        current_start = last_time + 1

        # Rate limit: be gentle
        time.sleep(0.15)

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    df.columns = ["timestamp", "open", "high", "low", "close", "close_time"]
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp")
    # Keep only useful columns
    df = df[["symbol" if "symbol" in df.columns else "open", "open", "high", "low", "close"]]
    # Add symbol column
    df["symbol"] = symbol
    df = df[["symbol", "open", "high", "low", "close"]]
    df.columns = ["symbol", "premium_open", "premium_high", "premium_low", "premium_close"]
    df = df[~df.index.duplicated(keep="last")]
    df = df.sort_index()
    return df


def save_by_month(df: pd.DataFrame, symbol: str, base_dir: Path) -> None:
    """Save DataFrame split by year/month into parquet files."""
    if df.empty:
        return

    cols = ["symbol", "premium_open", "premium_high", "premium_low", "premium_close"]

    for (year, month), group in df.groupby([df.index.year, df.index.month]):
        month_dir = base_dir / symbol / str(year)
        month_dir.mkdir(parents=True, exist_ok=True)
        month_file = month_dir / f"{month:02d}.parquet"

        save_df = group[cols].copy()
        save_df.index.name = "timestamp"

        if month_file.exists():
            existing = pd.read_parquet(month_file)
            combined = pd.concat([existing, save_df])
            combined = combined[~combined.index.duplicated(keep="last")]
            combined = combined.sort_index()
            combined.to_parquet(month_file)
        else:
            save_df.to_parquet(month_file)


def main():
    parser = argparse.ArgumentParser(description="Download Binance premium index history")
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
        "--interval", type=str, default=DEFAULT_INTERVAL,
        help="Kline interval: 1m,5m,15m,30m,1h,2h,4h,6h,12h,1d (default: 1h)"
    )
    args = parser.parse_args()

    symbols = args.symbols.split(",") if args.symbols else DEFAULT_SYMBOLS
    start_dt = datetime.strptime(args.start, "%Y-%m-%d")
    end_dt = datetime.strptime(args.end, "%Y-%m-%d") if args.end else datetime.now()
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    base_dir = Path("data_lake/raw/binance/um/premiumIndex")

    print(f"Downloading premium index klines for {len(symbols)} symbols")
    print(f"  Period: {start_dt.date()} to {end_dt.date()}")
    print(f"  Interval: {args.interval}")
    print(f"  Output: {base_dir}/")
    print()

    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] {symbol}...", end=" ", flush=True)
        t0 = time.time()
        df = download_premium_index_klines(symbol, start_ms, end_ms, args.interval)
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
