"""
V7 Engine CLI — Pipeline commands for the V7 Engine.

All commands are offline-safe by default.  Use --dry-run to see what would
happen without executing anything.  Training and WFV are gated behind
safety checks and require --force to bypass.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional


# ── Command handlers ──────────────────────────────────────────────

def cmd_help(args: argparse.Namespace) -> int:
    """Print help / usage information."""
    parser = _build_parser()
    parser.print_help()
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Run contract + boundary validation."""
    if args.dry_run:
        _log("validate", "Would run: contract checks + boundary checks + test suite")
        _log("validate", "  Step 1: check-contracts")
        _log("validate", "  Step 2: check-boundaries")
        _log("validate", "  Step 3: test suite (lib + integration)")
        return 0
    print("Not yet implemented — use --dry-run for now")
    return 0


def cmd_backfill(args: argparse.Namespace) -> int:
    """Download and backfill market data."""
    if args.dry_run:
        symbols = args.symbols or "default"
        intervals = args.intervals or "default"
        start = args.start or "default"
        end = args.end or "default"
        data_dir = args.data_dir or os.environ.get("V7_DATA_DIR") or "~/v7-data"
        _log(
            "backfill",
            f"--symbols {symbols} --intervals {intervals} "
            f"--start {start} --end {end} --data-dir {data_dir}",
        )
        return 0

    from alphaforge.data.backfill import (
        AlphaForgeBackfillPipeline,
        BackfillConfig,
    )

    symbols = _parse_comma_list(args.symbols)
    intervals = _parse_comma_list(args.intervals)
    start = _parse_date(args.start)
    end = _parse_date(args.end)
    data_dir = args.data_dir or os.environ.get("V7_DATA_DIR")

    config = AlphaForgeBackfillPipeline.default_config(
        start=start,
        end=end,
        symbols=symbols,
        intervals=intervals,
        data_dir=data_dir,
    )
    pipeline = AlphaForgeBackfillPipeline()
    result = pipeline.run(config)

    print(f"Backfill ok: {result.ok}")
    print(f"Records: {result.stats.get('total_records', 0)}")
    print(f"Errors: {len(result.stats.get('errors', []))}")
    print(f"Integrity reports: {len(result.integrity_reports)}")
    for report in result.integrity_reports:
        status = "PASS" if report.ok else "FAIL"
        print(f"  [{status}] {report.path}: {report.row_count} rows")
        for warning in report.warnings:
            print(f"      WARNING: {warning}")

    return 0 if result.ok else 1


def cmd_simulate(args: argparse.Namespace) -> int:
    """Run simulation."""
    if args.dry_run:
        mode = args.mode or "default"
        symbols = args.symbols or "default"
        _log("simulate", f"--mode {mode} --symbols {symbols}")
        return 0
    print("Not yet implemented — use --dry-run for now")
    return 0


def cmd_build_dataset(args: argparse.Namespace) -> int:
    """Build training dataset."""
    if args.dry_run:
        _log("build-dataset", "Would assemble feature + label dataset")
        return 0
    print("Not yet implemented — use --dry-run for now")
    return 0


def cmd_train(args: argparse.Namespace) -> int:
    """Train model (gated — requires --force to bypass)."""
    if args.dry_run:
        if args.force:
            _log("train", "--force bypasses gate; model training would proceed")
        else:
            print("[DRY RUN] GATE: Training not yet authorized — use --force to override")
        return 0
    if not args.force:
        print("GATE: Training not yet authorized — use --force to override")
        return 1
    print("Not yet implemented — use --dry-run for now")
    return 0


def cmd_wfv(args: argparse.Namespace) -> int:
    """Run walk-forward validation (gated — requires trained model)."""
    if args.dry_run:
        print("[DRY RUN] GATE: WFV requires trained model — run train first")
        return 0
    print("GATE: WFV requires trained model — run train first")
    return 1


def cmd_report(args: argparse.Namespace) -> int:
    """Generate pipeline report."""
    if args.dry_run:
        _log("report", "Would aggregate results into a report")
        return 0
    print("Not yet implemented — use --dry-run for now")
    return 0


def cmd_pipeline(args: argparse.Namespace) -> int:
    """Run end-to-end pipeline: validate → backfill → simulate → build-dataset → train → wfv → report."""
    steps: list[tuple[str, Any]] = [
        ("validate", cmd_validate),
        ("backfill", cmd_backfill),
        ("simulate", cmd_simulate),
        ("build-dataset", cmd_build_dataset),
        ("train", cmd_train),
        ("wfv", cmd_wfv),
        ("report", cmd_report),
    ]

    for name, handler in steps:
        print(f"\n=== Pipeline step: {name} ===")
        step_args = _step_namespace(args, name)
        ret = handler(step_args)
        if ret != 0:
            print(f"\n!!! Pipeline FAILED at step: {name}")
            return ret

    print("\n=== Pipeline complete ===")
    return 0


# ── Internals ─────────────────────────────────────────────────────

def _log(step: str, msg: str) -> None:
    print(f"[DRY RUN|{step}] {msg}")


def _parse_comma_list(value: Optional[str]) -> Optional[list[str]]:
    """Parse a comma-separated string into a list of stripped tokens."""
    if not value:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    """Parse a YYYY-MM-DD date into a UTC datetime."""
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _build_parser() -> argparse.ArgumentParser:
    # Shared parent with the global --dry-run flag so every subcommand
    # accepts it after the subcommand name.
    _dry_run_parent = argparse.ArgumentParser(add_help=False)
    _dry_run_parent.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without executing",
    )

    parser = argparse.ArgumentParser(
        prog="v7-engine",
        description="V7 Engine — Trading Pipeline CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Also accept --dry-run at the top level for consistency
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    sub = parser.add_subparsers(dest="command", help="Available commands")

    sub.add_parser("help", parents=[_dry_run_parent], add_help=False,
                    help="Print usage information")
    sub.add_parser("validate", parents=[_dry_run_parent], add_help=False,
                    help="Run contract + boundary validation")

    p = sub.add_parser("backfill", parents=[_dry_run_parent], add_help=False,
                        help="Download and backfill market data")
    p.add_argument("--symbols", default=None, help="Symbols to backfill (comma-separated)")
    p.add_argument("--intervals", default=None, help="Timeframe intervals (e.g. 4h, 1h)")
    p.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
    p.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    p.add_argument(
        "--data-dir",
        default=None,
        help="Output directory for market data (default: $V7_DATA_DIR or ~/v7-data)",
    )

    p = sub.add_parser("simulate", parents=[_dry_run_parent], add_help=False,
                        help="Run simulation with cost model")
    p.add_argument("--mode", default=None, help="Trading mode (e.g. SWING, SCALP)")
    p.add_argument("--symbols", default=None, help="Symbols to simulate")

    sub.add_parser("build-dataset", parents=[_dry_run_parent], add_help=False,
                    help="Build training dataset from features and labels")

    p = sub.add_parser("train", parents=[_dry_run_parent], add_help=False,
                        help="Train model (gated — see --force)")
    p.add_argument("--force", action="store_true", help="Override training gate")

    sub.add_parser("wfv", parents=[_dry_run_parent], add_help=False,
                    help="Run walk-forward validation (gated)")

    sub.add_parser("report", parents=[_dry_run_parent], add_help=False,
                    help="Generate pipeline report")

    sub.add_parser("pipeline", parents=[_dry_run_parent], add_help=False,
                    help="Run end-to-end pipeline")

    return parser


def _step_namespace(parent: argparse.Namespace, step: str) -> argparse.Namespace:
    """Build a minimal namespace for a pipeline sub-step from the parent args."""
    return argparse.Namespace(
        dry_run=parent.dry_run,
        force=getattr(parent, "force", False),
        symbols=getattr(parent, "symbols", None),
        intervals=getattr(parent, "intervals", None),
        start=getattr(parent, "start", None),
        end=getattr(parent, "end", None),
        data_dir=getattr(parent, "data_dir", None),
        mode=getattr(parent, "mode", None),
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    handlers: dict[str, Any] = {
        "help": cmd_help,
        "validate": cmd_validate,
        "backfill": cmd_backfill,
        "simulate": cmd_simulate,
        "build-dataset": cmd_build_dataset,
        "train": cmd_train,
        "wfv": cmd_wfv,
        "report": cmd_report,
        "pipeline": cmd_pipeline,
    }

    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
