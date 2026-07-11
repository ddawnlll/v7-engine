#!/usr/bin/env python3
"""
Deterministic data sync script — Binance OHLCV for the 12-symbol bootstrap set.

Reuses the existing market_data authority (BackfillOrchestrator, KlinesService,
StorageWriter, DataCatalog, BackfillCheckpoint).

Idempotent (resume/checkpoint support), checksum-verified, with duplicate and
missing candle detection built in.

Usage:
    python3 scripts/sync_data.py                              # defaults: 12 symbols, 1h, last 3 months
    python3 scripts/sync_data.py --symbols BTCUSDT,ETHUSDT    # specific symbols
    python3 scripts/sync_data.py --intervals 1h,5m,15m        # multiple timeframes
    python3 scripts/sync_data.py --start-ts 1700000000000     # explicit range
    python3 scripts/sync_data.py --dry-run                    # show what would sync
    python3 scripts/sync_data.py --verbose                    # show gaps, duplicates
    python3 scripts/sync_data.py --output-dir data_lake       # custom data dir
    python3 scripts/sync_data.py --checkpoint /tmp/cp.json    # custom checkpoint path
    python3 scripts/sync_data.py --no-verify                  # skip checksum verification

Exit code:
    0   All data synced without errors
    1   Some errors or checksum failures
"""

import argparse
import logging
import sys

# Ensure the project root is on sys.path for lib imports
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "alphaforge" / "src"))

from lib.data_lake.sync import (
    BOOTSTRAP_SYMBOLS_12,
    DataSyncOrchestrator,
    print_sync_result,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deterministic OHLCV data sync from Binance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s\n"
            "  %(prog)s --symbols BTCUSDT,ETHUSDT --intervals 1h,4h\n"
            "  %(prog)s --start-ts 1700000000000 --end-ts 1730000000000\n"
            "  %(prog)s --dry-run --verbose\n"
        ),
    )

    parser.add_argument(
        "--symbols",
        default=",".join(BOOTSTRAP_SYMBOLS_12),
        help=(
            "Comma-separated symbols to sync "
            f"(default: all {len(BOOTSTRAP_SYMBOLS_12)} bootstrap symbols)"
        ),
    )
    parser.add_argument(
        "--intervals",
        default="1h",
        help="Comma-separated intervals (default: 1h)",
    )
    parser.add_argument(
        "--start-ts",
        type=int,
        default=None,
        help="Start timestamp in ms (default: 3 months ago UTC)",
    )
    parser.add_argument(
        "--end-ts",
        type=int,
        default=None,
        help="End timestamp in ms (default: now)",
    )
    parser.add_argument(
        "--output-dir",
        default="data_lake",
        help="Data directory for Parquet output (default: data_lake)",
    )
    parser.add_argument(
        "--checkpoint",
        default=None,
        help="Custom checkpoint file path",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip SHA-256 checksum verification after download",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be synced without downloading",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show gap and duplicate details",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: WARNING)",
    )

    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s [%(name)s] %(message)s",
    )

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    intervals = [s.strip() for s in args.intervals.split(",") if s.strip()]

    # Validate
    from lib.market_data.binance.klines_service import interval_to_minutes

    for interval in intervals:
        try:
            interval_to_minutes(interval)
        except ValueError:
            print(f"ERROR: Unsupported interval: {interval}", file=sys.stderr)
            return 1

    # Dry-run: just print what would happen
    if args.dry_run:
        print(f"  DRY RUN — DataSyncOrchestrator")
        print(f"  Symbols:        {len(symbols)}")
        print(f"    {', '.join(symbols)}")
        print(f"  Intervals:      {', '.join(intervals)}")
        print(f"  Output dir:     {args.output_dir}")
        print(f"  Checksum verify: {'OFF' if args.no_verify else 'ON'}")
        print(f"\n  Would sync up to {len(symbols) * len(intervals)} symbol×interval combinations")
        return 0

    # Real run
    sync = DataSyncOrchestrator(
        data_dir=args.output_dir,
        checkpoint_path=args.checkpoint,
        verify_checksums=not args.no_verify,
    )

    result = sync.run(
        symbols=symbols,
        intervals=intervals,
        start_time=args.start_ts,
        end_time=args.end_ts,
        skip_checksum_verify=args.no_verify,
    )

    print_sync_result(result, verbose=args.verbose)

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
