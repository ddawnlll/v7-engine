#!/usr/bin/env python3
"""Parallel Binance Vision downloader with max CPU utilization.

Downloads 1h klines from data.binance.vision (public S3 mirror, no API key).

NOTE: Binance Vision public archive only supports 1m, 5m, 15m, 1h intervals.
      4h/1d data must be resampled from 1h or downloaded via REST API.

Usage:
    # Default: 4 symbols, 1h, 2023-2026, 8 parallel workers
    python3 scripts/download_binance.py

    # Custom
    python3 scripts/download_binance.py \\
        --symbols BTCUSDT,ETHUSDT \\
        --intervals 1h \\
        --start-year 2023 \\
        --workers 12
"""
import argparse
import concurrent.futures
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add alphaforge/src and repo root to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "alphaforge" / "src"))
sys.path.insert(0, str(REPO_ROOT))  # for lib/ imports

from alphaforge.data.backfill import (
    create_binance_vision_config,
    download_from_binance_vision,
)


def download_single_config(config) -> dict:
    """Download one (symbol, interval) combination.

    This is the unit of parallelism — each call handles all months
    for one symbol+interval pair.
    """
    result = download_from_binance_vision(config)
    return result


def chunk_intervals(symbols: list[str], intervals: list[str]) -> list[tuple[str, str]]:
    """Create (symbol, interval) pairs for parallel dispatch."""
    pairs = []
    for sym in symbols:
        for interval in intervals:
            pairs.append((sym, interval))
    return pairs


def resample_1h_to_4h(data_dir: str, symbols: list[str]) -> None:
    """Resample 1h klines to 4h using pandas.

    4h data is NOT available from Binance Vision. We derive it from 1h.
    """
    try:
        import pandas as pd
        import pyarrow.parquet as pq
        import pyarrow as pa
    except ImportError:
        print("  [WARN] pandas/pyarrow not available, skipping 4h resample")
        return

    base = Path(data_dir)
    for symbol in symbols:
        src_dir = base / symbol / "1h"
        dst_dir = base / symbol / "4h"
        if not src_dir.exists():
            continue

        for year_dir in sorted(src_dir.iterdir()):
            if not year_dir.is_dir():
                continue
            for month_file in sorted(year_dir.iterdir()):
                if not month_file.suffix == ".parquet":
                    continue

                try:
                    df = pq.read_table(str(month_file)).to_pandas()
                    if len(df) < 4:
                        continue

                    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                    df = df.sort_values("timestamp").set_index("timestamp")

                    # Resample 1h → 4h
                    ohlc_4h = df.resample("4h").agg({
                        "open": "first",
                        "high": "max",
                        "low": "min",
                        "close": "last",
                        "volume": "sum",
                        "quote_volume": "sum",
                        "trade_count": "sum",
                        "taker_buy_base_volume": "sum",
                        "taker_buy_quote_volume": "sum",
                    }).dropna()

                    if len(ohlc_4h) == 0:
                        continue

                    ohlc_4h = ohlc_4h.reset_index()
                    ohlc_4h["timestamp"] = ohlc_4h["timestamp"].astype("int64") // 10**6

                    out_path = dst_dir / year_dir.name / month_file.name
                    out_path.parent.mkdir(parents=True, exist_ok=True)

                    table = pa.Table.from_pandas(ohlc_4h)
                    pq.write_table(table, out_path, compression="zstd")
                    print(f"  [4h] {symbol} {year_dir.name}/{month_file.name}: {len(ohlc_4h)} bars")

                except Exception as e:
                    print(f"  [4h ERR] {symbol} {year_dir.name}/{month_file.name}: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Parallel Binance Vision download")
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT")
    parser.add_argument("--intervals", default="1h")
    parser.add_argument("--start-year", type=int, default=2023)
    parser.add_argument("--start-month", type=int, default=1)
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument("--end-month", type=int, default=None)
    parser.add_argument("--output-dir", default="data_lake/raw/binance/um/klines")
    parser.add_argument("--workers", type=int, default=8,
                        help="Max parallel workers (default 8)")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")]
    intervals = [s.strip() for s in args.intervals.split(",")]

    # Validate intervals
    valid = {"1m", "5m", "15m", "1h"}
    unsupported = [i for i in intervals if i not in valid]
    if unsupported:
        print(f"NOTE: Intervals {unsupported} NOT available from Binance Vision.")
        print(f"  Valid: {valid}")
        print(f"  {unsupported} will be RESAMPLED from 1h after download.")
        intervals = [i for i in intervals if i in valid]

    now = datetime.now(timezone.utc)
    end_year = args.end_year or now.year
    end_month_val = args.end_month or now.month

    print(f"=== Binance Vision Parallel Download ===")
    print(f"  Symbols:   {symbols}")
    print(f"  Intervals: {intervals}")
    print(f"  Period:    {args.start_year}-{args.start_month:02d} to {end_year}-{end_month_val:02d}")
    print(f"  Workers:   {args.workers}")
    print(f"  Output:    {args.output_dir}")
    print()

    # Create per-(symbol,interval) configs
    pairs = chunk_intervals(symbols, intervals)
    configs = []
    for sym, interval in pairs:
        cfg = create_binance_vision_config(
            symbols=[sym],
            intervals=[interval],
            output_dir=args.output_dir,
            start_year=args.start_year,
            start_month=args.start_month,
            end_year=end_year,
            end_month=end_month_val,
        )
        configs.append(cfg)

    total_expected = len(symbols) * len(intervals) * (
        (end_year - args.start_year) * 12 + (end_month_val - args.start_month + 1)
    )
    print(f"  Expected files: ~{total_expected}")
    print()

    # Parallel download
    t0 = time.time()
    total_files = 0
    total_records = 0
    all_errors = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        fut_to_label = {
            executor.submit(download_single_config, cfg): f"{cfg.symbols[0]} {cfg.intervals[0]}"
            for cfg in configs
        }

        for fut in concurrent.futures.as_completed(fut_to_label):
            label = fut_to_label[fut]
            try:
                result = fut.result()
                n_files = result.get("total_files", 0)
                n_records = result.get("total_records", 0)
                n_skipped = len(result.get("skipped", []))
                n_errors = len(result.get("errors", []))
                total_files += n_files
                total_records += n_records
                if n_errors:
                    all_errors.extend(result["errors"])
                status = f"{n_files} files, {n_records:,} records"
                if n_skipped:
                    status += f", {n_skipped} skipped"
                if n_errors:
                    status += f", {n_errors} errors"
                print(f"  [{label}] {status}")
            except Exception as e:
                print(f"  [{label}] FAILED: {e}")
                all_errors.append(str(e))

    elapsed = time.time() - t0
    print(f"\nDownload complete in {elapsed:.0f}s ({elapsed / max(1, total_files):.1f}s/file avg)")
    print(f"  Files:     {total_files}")
    print(f"  Records:   {total_records:,}")
    if all_errors:
        print(f"  Errors:    {len(all_errors)}")
        for err in all_errors[:5]:
            print(f"    - {err}")

    # Resample 1h → 4h if needed
    if unsupported:
        print(f"\n=== Resampling 1h → {unsupported} ===")
        resample_1h_to_4h(args.output_dir, symbols)

    print(f"\nNow run: make data-health")
    return 0 if not all_errors else 1


if __name__ == "__main__":
    sys.exit(main())
