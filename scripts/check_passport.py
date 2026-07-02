#!/usr/bin/env python3
"""DataPassport check — CLI entry point for Makefile.

Usage:
    python3 scripts/check_passport.py --symbols BTCUSDT,ETHUSDT

Exits with code 0.
"""
import argparse
import sys
from datetime import datetime, timezone

from lib.data_lake.passport import DataPassport
from lib.data_lake.spec import DatasetSpec
from lib.data_lake.catalog import DataCatalog


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT")
    parser.add_argument("--dataset-id", default="test-training")
    args = parser.parse_args()

    symbols = tuple(s.strip() for s in args.symbols.split(","))
    spec = DatasetSpec(
        dataset_id=args.dataset_id,
        source="binance",
        market="um_futures",
        symbols=symbols,
        intervals=("1h", "4h"),
        data_types=("klines",),
        start=datetime(2023, 1, 1, tzinfo=timezone.utc),
        end=datetime(2027, 1, 1, tzinfo=timezone.utc),
    )
    cat = DataCatalog()
    passport = DataPassport.from_spec(spec, cat)

    print(f"  Source:     {passport.source}")
    print(f"  Real data:  {passport.is_real_data}")
    print(f"  PIT safe:   {passport.point_in_time_safe}")
    print(f"  Coverage:   {passport.coverage_pct:.1f}%")
    print(f"  Backtest:   {passport.is_trustworthy_for_backtest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
