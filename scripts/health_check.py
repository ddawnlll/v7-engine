#!/usr/bin/env python3
"""Data health check — CLI entry point for Makefile.

Usage:
    python3 scripts/health_check.py [--symbols BTCUSDT,ETHUSDT] [--data-dir data_lake]

Exits with code 0 if healthy, 1 otherwise.
"""
import argparse
import sys
from datetime import datetime, timezone

from lib.data_lake.health import DataHealthChecker


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT")
    parser.add_argument("--intervals", default="1h,4h")
    parser.add_argument("--data-dir", default="data_lake")
    parser.add_argument("--start", default="2023-01-01T00:00:00+00:00")
    parser.add_argument("--end", default="2027-01-01T00:00:00+00:00")
    parser.add_argument("--auto-repair", action="store_true", default=True)
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")]
    intervals = [s.strip() for s in args.intervals.split(",")]
    start = datetime.fromisoformat(args.start)
    end = datetime.fromisoformat(args.end)

    checker = DataHealthChecker(data_dir=args.data_dir)
    report = checker.check(
        symbols=symbols,
        intervals=intervals,
        start=start,
        end=end,
        auto_repair=args.auto_repair,
    )

    print(f"  Healthy:        {report.healthy}")
    print(f"  Coverage:       {report.coverage_pct:.1f}%")
    print(f"  Gaps:           {len(report.gaps)}")
    print(f"  Checksum pass:  {report.checksum_pass}")
    print(f"  Auto-repaired:  {report.repaired}")
    print(f"  Repair action:  {report.repair_action or 'none'}")
    print(f"  Reason:         {report.reason}")

    return 0 if report.healthy else 1


if __name__ == "__main__":
    sys.exit(main())
