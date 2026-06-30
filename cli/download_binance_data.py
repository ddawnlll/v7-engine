#!/usr/bin/env python3
"""Download Binance klines and save as Parquet for training pipeline.

Usage:
    /tmp/v7-venv/bin/python cli/download_binance_data.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 4h
"""
import argparse
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.market_data.binance.client import BinanceClient
from lib.market_data.storage import StorageWriter
from lib.market_data.contracts import KlineRecord


def download_klines(client, symbol, interval, start_time, end_time=None):
    """Download all klines in the given time range (pagination)."""
    all_klines = []
    current_start = start_time
    while True:
        raw = client.get_klines(symbol, interval, start_time=current_start, end_time=end_time, limit=1000)
        if not raw:
            break
        all_klines.extend(raw)
        if len(raw) < 1000:
            break
        # Move start to the open time of the last kline + interval
        current_start = raw[-1][0] + 1
        print(f"  Downloaded {len(all_klines)} klines so far for {symbol}...")
    return all_klines


def raw_to_kline_records(raw_list, symbol, interval):
    """Convert raw Binance klines to KlineRecord list."""
    records = []
    for r in raw_list:
        records.append(KlineRecord(
            symbol=symbol,
            timestamp=r[0],  # open time in ms
            open=float(r[1]),
            high=float(r[2]),
            low=float(r[3]),
            close=float(r[4]),
            volume=float(r[5]),
            quote_volume=float(r[7]),
            trade_count=int(r[8]),
            taker_buy_volume=float(r[9]),
            taker_buy_quote_volume=float(r[10]),
            interval=interval,
            source="binance",
            is_closed=True,
        ))
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    parser.add_argument("--interval", default="4h")
    parser.add_argument("--days", type=int, default=365,
                        help="Days of history to download (default: 365)")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")]
    interval = args.interval

    interval_ms = {"1h": 3600000, "4h": 14400000, "15m": 900000, "1d": 86400000}.get(interval, 14400000)
    now = int(__import__("time").time() * 1000)
    start_ms = now - args.days * 86400000

    client = BinanceClient()
    writer = StorageWriter()

    for symbol in symbols:
        print(f"\nDownloading {symbol} {interval}...")
        raw = download_klines(client, symbol, interval, start_ms, now)
        print(f"  Total: {len(raw)} klines for {symbol}")

        if not raw:
            print(f"  WARNING: No data for {symbol}")
            continue

        # Use start/end from actual data
        actual_start = raw[0][0]
        actual_end = raw[-1][0]

        records = raw_to_kline_records(raw, symbol, interval)
        file_path = writer.write_raw_klines(records, symbol, interval, actual_start, actual_end)
        print(f"  Saved: {file_path}")

    print("\nDone!")


if __name__ == "__main__":
    main()
