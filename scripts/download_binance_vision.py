#!/usr/bin/env python3
"""Direct downloader from Binance Vision public S3 → Parquet for _load_cached_data.

Downloads monthly kline CSVs, converts to Parquet, saves to data/raw/<symbol>/.
"""
import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd
import requests

RAW_DIR = Path("data/raw")
BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"

SYMBOLS: List[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
INTERVALS: List[str] = ["1h", "4h"]
START_YEAR = 2022
END_YEAR = 2026
END_MONTH = 6  # July 2026 = month 7, so we go up to 2026-06

# Kline CSV columns (Binance Vision format)
KLINE_COLS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_vol", "taker_buy_quote_vol", "ignore",
]


def download_month(symbol: str, interval: str, year: int, month: int) -> pd.DataFrame | None:
    """Download one month of klines from Binance Vision, return DataFrame."""
    url = f"{BASE_URL}/{symbol}/{interval}/{symbol}-{interval}-{year}-{month:02d}.zip"
    try:
        resp = requests.get(url, timeout=60)
        if resp.status_code != 200:
            return None
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            csv_name = f"{symbol}-{interval}-{year}-{month:02d}.csv"
            if csv_name not in zf.namelist():
                # try alternate name
                csv_name = f"{symbol}-{interval}-{year}-{month:02d}.CSV"
            with zf.open(csv_name) as f:
                df = pd.read_csv(f, header=None, names=KLINE_COLS)
        return df
    except Exception as e:
        print(f"  Error downloading {url}: {e}")
        return None


def download_symbol(symbol: str, interval: str) -> pd.DataFrame:
    """Download all months for one symbol/interval, concatenate."""
    chunks = []
    for year in range(START_YEAR, END_YEAR + 1):
        max_month = 12
        if year == END_YEAR:
            max_month = END_MONTH
        for month in range(1, max_month + 1):
            df = download_month(symbol, interval, year, month)
            if df is not None:
                chunks.append(df)
                print(f"  {symbol} {interval} {year}-{month:02d}: {len(df)} rows")
            else:
                print(f"  {symbol} {interval} {year}-{month:02d}: not found")
    if not chunks:
        return pd.DataFrame()
    full = pd.concat(chunks, ignore_index=True)
    # Deduplicate by open_time
    full = full.drop_duplicates(subset=["open_time"])
    full = full.sort_values("open_time")
    return full


def convert_to_parquet(symbol: str, interval: str, df: pd.DataFrame) -> None:
    """Convert DataFrame to the Parquet format expected by _load_cached_data.

    Saves to data/raw/<symbol>/<interval>.parquet
    """
    if df.empty:
        print(f"  No data for {symbol} {interval}, skipping")
        return

    # Parse numeric columns
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    out_dir = RAW_DIR / symbol
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{interval}.parquet"

    # Build the expected schema: timestamp, open, high, low, close, volume
    out_df = pd.DataFrame({
        "timestamp": pd.to_datetime(df["open_time"], unit="ms"),
        "open": df["open"].values,
        "high": df["high"].values,
        "low": df["low"].values,
        "close": df["close"].values,
        "volume": df["volume"].values,
    })
    out_df.to_parquet(out_path, index=False)
    print(f"  Saved {len(out_df)} rows → {out_path}")


def main():
    print(f"Downloading Binance Vision data: {SYMBOLS} {INTERVALS}")
    print(f"Period: {START_YEAR}-01 to {END_YEAR}-{END_MONTH:02d}")
    print()

    for symbol in SYMBOLS:
        for interval in INTERVALS:
            print(f"[{symbol} {interval}]")
            df = download_symbol(symbol, interval)
            convert_to_parquet(symbol, interval, df)
            print()


if __name__ == "__main__":
    main()
