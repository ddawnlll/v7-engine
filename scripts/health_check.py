#!/usr/bin/env python3
"""Data health check — CLI entry point for Makefile.

Checks whether required Binance Vision data is downloaded and healthy.
Only checks intervals that actually exist on disk (4h is resampled from 1h).

Usage:
    python3 scripts/health_check.py [--symbols BTCUSDT,ETHUSDT]
    python3 scripts/health_check.py --intervals 1h,4h

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
    parser.add_argument("--end", default=None)  # None = now
    parser.add_argument("--auto-repair", action="store_true", default=True)
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")]
    intervals_arg = [s.strip() for s in args.intervals.split(",")]
    start = datetime.fromisoformat(args.start)
    end = datetime.fromisoformat(args.end) if args.end else datetime.now(timezone.utc)

    # Only check intervals that exist on disk (4h doesn't from Vision)
    from lib.data_lake.storage import DataLakePaths

    intervals = []
    for interval in intervals_arg:
        found = False
        for sym in symbols:
            p = DataLakePaths.klines_path(sym, interval, start.year, 1)
            if p.parent.parent.exists():  # symbol/interval dir exists
                found = True
                break
        if found:
            intervals.append(interval)
        else:
            print(f"  [SKIP] {interval} — no data yet (resampled from 1h)")

    if not intervals:
        print("  No data found for any interval")
        return 1

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
