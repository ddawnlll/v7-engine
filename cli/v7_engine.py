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
from pathlib import Path
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
    """Generate pipeline report.

    Generates an empirical ModeResearchReport from WFV results.
    If --mode is provided, generates report for that mode only.
    Otherwise generates reports for all three canonical modes.
    Writes report JSON to data/reports/{mode}/.
    """
    from alphaforge.reports.empirical import build_empirical_mode_research_report
    from alphaforge.reports.writer import write_json_report
    from alphaforge.contracts.loader import load_schema
    from alphaforge.reports.run_index import ResearchRunIndex

    modes_to_run = [args.mode] if args.mode else ["SWING", "SCALP", "AGGRESSIVE_SCALP"]

    if args.dry_run:
        for mode in modes_to_run:
            _log("report", f"Would generate {mode} empirical report")
        return 0

    # Build a default WFV results dict with INCONCLUSIVE data
    # (real data would come from an earlier wfv pipeline step)
    default_per_fold = [
        {"fold": i + 1, "sharpe": 0.0, "expectancy_r": 0.0,
         "win_rate": 0.5, "trade_count": 0}
        for i in range(6)
    ]

    failures = 0
    run_index = ResearchRunIndex()
    for mode in modes_to_run:
        wfv = {
            "fold_count": 6,
            "per_fold_metrics": list(default_per_fold),
            "oos_summary": {
                "oos_sharpe": 0.0,
                "oos_expectancy_r": 0.0,
                "oos_win_rate": 0.5,
                "oos_profit_factor": 1.0,
                "oos_max_drawdown_r": -3.0,
                "oos_trade_count": 0,
            },
            "data_scope": {
                "symbols": ["BTCUSDT"],
                "date_range_start": "2025-01-01T00:00:00Z",
                "date_range_end": "2026-01-01T00:00:00Z",
            },
        }
        try:
            schema = load_schema("mode_research_report.schema.json")
            report = build_empirical_mode_research_report(mode, wfv)
            mode_key = mode.lower().replace(" ", "_")
            output_path = f"data/reports/{mode_key}/mrr-empirical-{mode_key}.json"
            write_json_report(report, output_path, schema=schema,
                              schema_name=f"mode_research_report({mode})")
            print(f"[REPORT] Wrote {mode} report to {output_path}")

            # Update Research Artifact Registry (#127)
            v = report.get("verdict", "NOT_EVALUATED")
            verdict = v.get("overall_verdict", str(v)) if isinstance(v, dict) else str(v)
            run_index.add_run(
                run_id=report.get("run_id", f"run-{mode_key}-cli-{datetime.now().strftime('%Y%m%dT%H%M%S')}"),
                mode=mode,
                canonical_report_path=str(Path(output_path).resolve()),
                candidate_count=0,
                trial_count=0,
                verdict=verdict,
                artifact_paths=[str(Path(output_path).resolve())],
            )
        except Exception as e:
            print(f"[REPORT] FAILED {mode}: {e}")
            failures += 1

    run_index.write()
    print(f"[RUN INDEX] Updated {run_index.index_path}")
    return failures


def cmd_tune(args: argparse.Namespace) -> int:
    """Run hyperparameter tuning for a mode (gated)."""
    modes = [args.mode] if args.mode else ["SWING", "SCALP", "AGGRESSIVE_SCALP"]

    if args.dry_run:
        for mode in modes:
            _log("tune", f"Would tune {mode} ({args.n_trials} trials)")
        return 0

    from alphaforge.tuning.mode_profiles import (
        get_tuning_profile,
        save_tuning_params,
        suggest_params,
    )

    failures = 0
    for mode in modes:
        try:
            profile = get_tuning_profile(mode)
            _log("tune", f"Tuning {mode}: lr=[{profile.learning_rate.low},"
                 f"{profile.learning_rate.high}], depth={profile.max_depth},"
                 f" {args.n_trials} trials")

            # Run Optuna study
            import optuna

            study = optuna.create_study(
                direction="maximize",
                study_name=f"{mode}_tuning",
                storage=None,
            )

            def objective(trial: optuna.trial.Trial) -> float:
                params = suggest_params(trial, profile=profile)
                # Dummy objective — real tuning would train and evaluate
                return trial.suggest_float("dummy_score", 0.0, 1.0)

            study.optimize(objective, n_trials=args.n_trials)

            # Save best params
            best_params = study.best_params
            if "dummy_score" in best_params:
                del best_params["dummy_score"]

            output_dir = args.output_dir or "artifacts/params"
            path = save_tuning_params(best_params, mode, output_dir=output_dir)
            print(f"[TUNE] {mode} best params saved to {path}")
            print(f"  Best value: {study.best_value:.4f}")
        except Exception as e:
            print(f"[TUNE] FAILED {mode}: {e}")
            failures += 1

    return failures


def cmd_v02(args: argparse.Namespace) -> int:
    """Run the v0.2 profitability evidence pipeline.

    Delegates to cli.v7_pipeline.main() with argv reconstructed from args.
    """
    from cli.v7_pipeline import main as v02_main

    # Build argv list from namespace to pass through to v7_pipeline CLI
    argv: list[str] = []
    argv.extend(["--mode", getattr(args, "mode", None) or "SWING"])

    symbols = getattr(args, "symbols_v02", None)
    if symbols:
        argv.extend(["--symbols", symbols])
    start = getattr(args, "start", None)
    if start:
        argv.extend(["--start", start])
    end = getattr(args, "end", None)
    if end:
        argv.extend(["--end", end])
    data_dir = getattr(args, "data_dir", None)
    output_dir = getattr(args, "output_dir", None)
    if output_dir:
        argv.extend(["--output-dir", output_dir])
    elif data_dir:
        argv.extend(["--output-dir", data_dir])
    seed = getattr(args, "seed", None)
    if seed is not None:
        argv.extend(["--seed", str(seed)])
    n_bars = getattr(args, "n_bars", None)
    if n_bars is not None:
        argv.extend(["--n-bars", str(n_bars)])
    steps = getattr(args, "steps_v02", None)
    if steps:
        argv.extend(["--steps", steps])
    if getattr(args, "real", False):
        argv.append("--real")
    if getattr(args, "no_synthetic", False):
        argv.append("--no-synthetic")
    elif getattr(args, "synthetic", True):
        argv.append("--synthetic")
    if getattr(args, "force", False):
        argv.append("--force")
    if getattr(args, "dry_run", False):
        argv.append("--dry-run")

    return v02_main(argv)


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

    p_report = sub.add_parser("report", parents=[_dry_run_parent], add_help=False,
                               help="Generate pipeline report")
    p_report.add_argument("--mode", default=None,
                          help="Mode to report (SWING, SCALP, AGGRESSIVE_SCALP; default: all)")

    p_tune = sub.add_parser("tune", parents=[_dry_run_parent], add_help=False,
                             help="Run hyperparameter tuning for a mode")
    p_tune.add_argument("--mode", default=None,
                        help="Mode to tune (SWING, SCALP, AGGRESSIVE_SCALP; default: all)")
    p_tune.add_argument("--n-trials", type=int, default=20,
                        help="Number of Optuna trials (default: 20)")
    p_tune.add_argument("--output-dir", default=None,
                        help="Output directory for tuned params (default: artifacts/params)")

    p = sub.add_parser("v02", parents=[_dry_run_parent], add_help=False,
                        help="Run v0.2 profitability evidence pipeline (backfill→labels→features→train→wfv→report)")
    p.add_argument("--mode", default="SWING", help="Trading mode (SWING, SCALP, AGGRESSIVE_SCALP)")
    p.add_argument("--symbols-v02", default=None, dest="symbols_v02",
                    help="Symbols (comma-separated)")
    p.add_argument("--start", default=None, help="Start date YYYY-MM-DD")
    p.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    p.add_argument("--data-dir", default=None, help="Output directory for artifacts")
    p.add_argument("--output-dir", default=None, help="Output directory for artifacts")
    p.add_argument("--seed", type=int, default=None, help="Random seed")
    p.add_argument("--n-bars", type=int, default=None, help="Bars per symbol for synthetic")
    p.add_argument("--steps-v02", default=None, dest="steps_v02",
                    help="Steps to run (comma-separated)")
    p.add_argument("--real", action="store_true", help="Actually execute (not dry-run)")
    p.add_argument("--synthetic", action="store_true", default=True,
                    help="Use synthetic data (default)")
    p.add_argument("--no-synthetic", action="store_true", help="Use real Binance data")
    p.add_argument("--force", action="store_true", help="Skip safety gates")

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
        "tune": cmd_tune,
        "v02": cmd_v02,
        "pipeline": cmd_pipeline,
    }

    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
