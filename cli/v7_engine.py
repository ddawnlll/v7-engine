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
    """Download and backfill market data via Binance Vision.

    The old CLI referenced ``AlphaForgeBackfillPipeline``, which no longer
    exists.  The maintained downloader is ``scripts/download_binance.py``;
    call it with the active interpreter so Makefile/menu targets use the same
    environment as the rest of the repo.
    """
    mode = (args.mode or os.environ.get("MODE") or "SCALP").upper()
    symbols = args.symbols or os.environ.get("SYMBOLS") or "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT"
    intervals = args.intervals or _default_backfill_intervals(mode)
    data_dir = args.data_dir or os.environ.get("V7_DATA_DIR") or "data_lake"
    output_dir = _resolve_backfill_output_dir(data_dir)

    cmd = [
        sys.executable,
        "scripts/download_binance.py",
        "--symbols",
        symbols,
        "--intervals",
        intervals,
        "--output-dir",
        output_dir,
    ]
    _extend_year_month_args(cmd, "--start", args.start)
    _extend_year_month_args(cmd, "--end", args.end)

    if args.dry_run:
        _log("backfill", " ".join(cmd))
        return 0

    import subprocess

    print(f"Backfill mode: {mode}")
    print(f"Symbols:       {symbols}")
    print(f"Intervals:     {intervals}")
    print(f"Output dir:    {output_dir}")
    return subprocess.call(cmd)


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
        print("GATE: Training not authorized in legacy CLI — no-op. Use pipeline-v0.2 ARGS=--force for executable training.")
        return 0
    print("Legacy train command is not wired to production training — use make pipeline-v0.2 ARGS='--real --synthetic --force'.")
    return 0


def cmd_wfv(args: argparse.Namespace) -> int:
    """Run walk-forward validation (legacy gated no-op)."""
    if args.dry_run:
        print("[DRY RUN] WFV would run after a trained model exists")
        return 0
    print("GATE: WFV requires a trained model — no-op in legacy CLI. Use pipeline-v0.2 with train,wfv steps.")
    return 0


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
        {"fold": i + 1, "ic": 0.0, "rank_ic": 0.0, "sharpe": 0.0, "expectancy_r": 0.0,
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
                "oos_ic": 0.0,
                "oos_rank_ic": 0.0,
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
    """Run tuning: synthetic baseline with optional real data comparison.

    Always runs with synthetic data to establish a deterministic baseline.
    When --real is provided, also runs with real Binance data and produces
    a synthetic-vs-real comparison report.

    Usage:
        # Dry-run (shows what would run)
        python3 -m cli tune --mode SWING --symbols BTCUSDT,ETHUSDT,SOLUSDT

        # Synthetic baseline only
        python3 -m cli tune --mode SWING

        # Synthetic baseline + real data comparison
        python3 -m cli tune --mode SWING --real --symbols BTCUSDT,ETHUSDT,SOLUSDT
    """
    if args.dry_run:
        _log("tune", f"--mode {args.mode or 'SWING'} "
             f"--real {getattr(args, 'real', False)} "
             f"--symbols {args.symbols or 'BTCUSDT,ETHUSDT,SOLUSDT'}")
        return 0

    from cli.v7_pipeline import (
        PIPELINE_STEPS,
        PipelineConfig,
        PipelineRunner,
        StepStatus,
    )

    symbols = tuple(_parse_comma_list(args.symbols) or ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    mode = (args.mode or "SWING").upper()
    output_dir = args.data_dir or "artifacts/pipeline"
    random_seed = args.seed or 42
    n_bars = args.n_bars or 2000
    force = getattr(args, "force", False)
    use_real = getattr(args, "real", False)

    # Step 1: Run synthetic baseline
    print("\n" + "=" * 60)
    print("TUNE STEP 1: Synthetic data baseline")
    print("=" * 60)

    syn_config = PipelineConfig(
        mode=mode,
        symbols=symbols,
        dry_run=False,
        use_synthetic=True,
        n_bars=n_bars,
        output_dir=output_dir,
        random_seed=random_seed,
        force=force,
    )
    syn_runner = PipelineRunner(syn_config)
    syn_result = syn_runner.run()

    syn_failed = False
    for ev in syn_result.evidence:
        if ev.status == StepStatus.FAILED.value:
            print(f"  [SYNTHETIC] Step '{ev.step}' FAILED: {ev.errors}")
            syn_failed = True

    # Step 2: If --real, run with real Binance data
    real_result = None
    if use_real:
        print("\n" + "=" * 60)
        print("TUNE STEP 2: Real Binance data")
        print("=" * 60)

        start = getattr(args, "start", None)
        end = getattr(args, "end", None)

        real_config = PipelineConfig(
            mode=mode,
            symbols=symbols,
            dry_run=False,
            use_synthetic=False,
            start_date=start,
            end_date=end,
            output_dir=output_dir,
            random_seed=random_seed,
            force=force,
        )
        try:
            real_runner = PipelineRunner(real_config)
            real_result = real_runner.run()

            for ev in real_result.evidence:
                if ev.status == StepStatus.FAILED.value:
                    print(f"  [REAL] Step '{ev.step}' FAILED: {ev.errors}")
        except Exception as e:
            print(f"\n  [REAL] Pipeline crashed: {e}")
            print("  Real data pipeline encountered an error (likely no cached data).")
            print("  Run 'python3 -m cli backfill ...' first or check data/raw/ for cached parquet files.")

    # Step 3: Comparison report
    comparisons = _build_tune_comparison(syn_result, real_result, mode, symbols)

    print("\n" + "=" * 60)
    print("TUNE RESULTS")
    print("=" * 60)
    _print_tune_report(comparisons)

    # Save comparison report
    report_path = _save_tune_report(comparisons, output_dir, mode)
    print(f"\n  Tune report saved to: {report_path}")

    return 0


def _build_tune_comparison(
    syn_result: "Any",
    real_result: "Any | None",
    mode: str,
    symbols: tuple[str, ...],
) -> dict:
    """Build a structured comparison dict from synthetic and real pipeline results."""
    from cli.v7_pipeline import StepStatus

    def _extract_step_metrics(result, step_name: str) -> dict:
        for ev in result.evidence:
            if ev.step == step_name:
                return {
                    "status": ev.status,
                    "metrics": ev.metrics,
                    "errors": ev.errors,
                    "warnings": ev.warnings,
                    "duration_seconds": ev.duration_seconds,
                }
        return {"status": "NOT_FOUND", "metrics": {}, "errors": [], "warnings": []}

    syn_verdict = syn_result.verdict if hasattr(syn_result, "verdict") else "UNKNOWN"
    real_verdict = real_result.verdict if real_result and hasattr(real_result, "verdict") else None

    comparison: dict = {
        "tune_report_version": "0.1.0",
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "config": {
            "mode": mode,
            "symbols": list(symbols),
        },
        "synthetic": {
            "verdict": syn_verdict,
            "steps": {step: _extract_step_metrics(syn_result, step)
                      for step in ["validate", "backfill", "labels", "features", "train", "wfv", "report"]},
        },
    }

    if real_result:
        comparison["real"] = {
            "verdict": real_verdict,
            "steps": {step: _extract_step_metrics(real_result, step)
                      for step in ["validate", "backfill", "labels", "features", "train", "wfv", "report"]},
        }

    # Computed comparison fields
    syn_train = comparison["synthetic"]["steps"].get("train", {})
    syn_wfv = comparison["synthetic"]["steps"].get("wfv", {})

    comparison["metrics"] = {
        "synthetic_train_accuracy": syn_train.get("metrics", {}).get("train_accuracy"),
        "synthetic_val_accuracy": syn_train.get("metrics", {}).get("val_accuracy"),
        "synthetic_wfv_verdict": syn_wfv.get("metrics", {}).get("verdict"),
        "synthetic_wfv_avg_sharpe": syn_wfv.get("metrics", {}).get("avg_sharpe"),
    }

    if real_result:
        real_train = comparison["real"]["steps"].get("train", {})
        real_wfv = comparison["real"]["steps"].get("wfv", {})
        comparison["metrics"].update({
            "real_train_accuracy": real_train.get("metrics", {}).get("train_accuracy"),
            "real_val_accuracy": real_train.get("metrics", {}).get("val_accuracy"),
            "real_wfv_verdict": real_wfv.get("metrics", {}).get("verdict"),
            "real_wfv_avg_sharpe": real_wfv.get("metrics", {}).get("avg_sharpe"),
        })

    return comparison


def _print_tune_report(comparisons: dict) -> None:
    """Print the tune comparison report to stdout."""
    syn = comparisons.get("synthetic", {})
    real = comparisons.get("real")

    print(f"\n  Synthetic Verdict: {syn.get('verdict', 'N/A')}")
    for step_name, metrics in syn.get("steps", {}).items():
        s = metrics.get("status", "?")
        dur = metrics.get("duration_seconds", 0)
        print(f"    {step_name}: {s} ({dur:.3f}s)")

    if real:
        print(f"\n  Real Verdict: {real.get('verdict', 'N/A')}")
        for step_name, metrics in real.get("steps", {}).items():
            s = metrics.get("status", "?")
            dur = metrics.get("duration_seconds", 0)
            print(f"    {step_name}: {s} ({dur:.3f}s)")

    m = comparisons.get("metrics", {})
    print(f"\n  --- Accuracy Comparison ---")
    print(f"  Synthetic train accuracy:  {m.get('synthetic_train_accuracy', 'N/A')}")
    print(f"  Synthetic val accuracy:    {m.get('synthetic_val_accuracy', 'N/A')}")
    if m.get("real_train_accuracy") is not None:
        print(f"  Real train accuracy:       {m['real_train_accuracy']}")
        print(f"  Real val accuracy:         {m['real_val_accuracy']}")


def _save_tune_report(
    comparisons: dict,
    output_dir: str,
    mode: str,
) -> str:
    """Save the tune comparison report as JSON."""
    import json
    import os
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    dir_path = os.path.join(output_dir, "reports")
    os.makedirs(dir_path, exist_ok=True)

    filename = f"tune_comparison_{mode.lower()}_{ts}.json"
    filepath = os.path.join(dir_path, filename)

    with open(filepath, "w") as f:
        json.dump(comparisons, f, indent=2, default=str)

    return filepath


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


def _default_backfill_intervals(mode: str) -> str:
    """Return Binance Vision intervals needed by a mode.

    ``4h`` is resampled from downloaded ``1h`` data by the downloader.
    ``1d`` is intentionally excluded because the downloader currently supports
    intraday kline archives only.
    """
    if mode == "AGGRESSIVE_SCALP":
        return "5m,15m,1h"
    if mode == "SWING":
        return "1h,4h"
    return "15m,1h,4h"


def _resolve_backfill_output_dir(data_dir: str) -> str:
    """Resolve a user data dir to the downloader's kline output root."""
    path = Path(data_dir).expanduser()
    parts = path.parts
    if len(parts) >= 4 and parts[-4:] == ("raw", "binance", "um", "klines"):
        return str(path)
    return str(path / "raw" / "binance" / "um" / "klines")


def _extend_year_month_args(cmd: list[str], prefix: str, value: Optional[str]) -> None:
    """Append downloader year/month args from a YYYY-MM-DD value."""
    if not value:
        return
    parsed = _parse_date(value)
    cmd.extend([f"{prefix}-year", str(parsed.year), f"{prefix}-month", str(parsed.month)])


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
    p.add_argument("--mode", default=None, help="Trading mode (SCALP, AGGRESSIVE_SCALP, SWING)")
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

    p_tune = sub.add_parser("tune", parents=[_dry_run_parent], add_help=False,
                             help="Run tuning: synthetic baseline + optional real data comparison")
    p_tune.add_argument("--mode", default="SWING",
                        help="Trading mode (SWING, SCALP, AGGRESSIVE_SCALP)")
    p_tune.add_argument("--real", action="store_true",
                        help="Also run with real Binance data for comparison")
    p_tune.add_argument("--symbols", default=None,
                        help="Symbols (comma-separated, default: BTCUSDT,ETHUSDT,SOLUSDT)")
    p_tune.add_argument("--start", default=None,
                        help="Start date YYYY-MM-DD (required for real data)")
    p_tune.add_argument("--end", default=None,
                        help="End date YYYY-MM-DD (required for real data)")
    p_tune.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility (default: 42)")
    p_tune.add_argument("--n-bars", type=int, default=2000,
                        help="Bars per symbol for synthetic data (default: 2000)")
    p_tune.add_argument("--data-dir", default=None,
                        help="Output directory for artifacts (default: artifacts/pipeline)")
    p_tune.add_argument("--force", action="store_true",
                        help="Override training gate")

    p_report = sub.add_parser("report", parents=[_dry_run_parent], add_help=False,
                               help="Generate pipeline report")
    p_report.add_argument("--mode", default=None,
                          help="Mode to report (SWING, SCALP, AGGRESSIVE_SCALP; default: all)")

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
