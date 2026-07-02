#!/usr/bin/env python3
"""Download Binance Vision data for test-training profile.

Downloads monthly klines ZIPs from data.binance.vision, converts to
Parquet+Zstd, and registers in the DataLake catalog.

Usage:
    python3 scripts/download_binance.py \\
        --symbols BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT \\
        --intervals 1h,4h \\
        --start-year 2023 \\
        --end-year 2026
"""
import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add alphaforge/src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "alphaforge" / "src"))

from alphaforge.data.backfill import (
    create_binance_vision_config,
    download_from_binance_vision,
    BackfillError,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Binance Vision data")
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT")
    parser.add_argument("--intervals", default="1h,4h")
    parser.add_argument("--start-year", type=int, default=2023)
    parser.add_argument("--start-month", type=int, default=1)
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument("--output-dir", default="data_lake/raw/binance/um/klines")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")]
    intervals = [s.strip() for s in args.intervals.split(",")]

    now = datetime.now(timezone.utc)
    end_year = args.end_year or now.year
    end_month = now.month

    print(f"=== Binance Vision Download ===")
    print(f"  Symbols:   {symbols}")
    print(f"  Intervals: {intervals}")
    print(f"  Period:    {args.start_year}-{args.start_month:02d} to {end_year}-{end_month:02d}")
    print(f"  Output:    {args.output_dir}")
    print()

    config = create_binance_vision_config(
        symbols=symbols,
        intervals=intervals,
        output_dir=args.output_dir,
        start_year=args.start_year,
        start_month=args.start_month,
        end_year=end_year,
        end_month=end_month,
    )

    t0 = time.time()
    try:
        result = download_from_binance_vision(config)
        elapsed = time.time() - t0
        print(f"\nDownload complete in {elapsed:.0f}s")
        print(f"  Files downloaded:  {result['total_files']}")
        print(f"  Total records:     {result['total_records']:,}")
        print(f"  Skipped (existed): {len(result['skipped'])}")
        if result['errors']:
            print(f"  Errors:            {len(result['errors'])}")
            for err in result['errors'][:5]:
                print(f"    - {err}")
        print(f"\nNow run: make data-health")
        return 0 if not result['errors'] else 1
    except BackfillError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
