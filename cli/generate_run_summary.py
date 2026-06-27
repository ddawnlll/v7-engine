#!/usr/bin/env python3
"""Generate a centralized research run summary from AlphaForge report JSON files.

Scans --report-dir for mode_research_report_*.json files, extracts key
diagnostic fields, and writes a consolidated research_run_summary.json.

Usage:
    PYTHONPATH=.:alphaforge/src python3 cli/generate_run_summary.py \\
        --report-dir data/reports --output data/reports/research_run_summary.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def extract_report_summary(report_path: Path) -> dict:
    """Extract key diagnostic fields from a single report JSON."""
    with open(report_path) as f:
        report = json.load(f)

    mode = report.get("mode", "UNKNOWN")
    verdict = report.get("verdict", "UNKNOWN")

    # Validation summary
    val = report.get("validation_summary", {})
    fold_count = val.get("fold_count", 0)
    overfit_risk = val.get("overfit_risk", None)

    # Metrics
    metrics = report.get("metrics", {})
    oos_trade_count = metrics.get("oos_trade_count", 0)
    oos_expectancy_r = metrics.get("oos_expectancy_r", {})
    oos_sharpe = metrics.get("oos_sharpe", {})
    active_trade_count = metrics.get("active_trade_count", None)

    # Cost stress
    cost_stress = report.get("cost_stress", {})
    edge_survives = cost_stress.get("combined_stress_edge_survives", None)

    # No-trade comparison
    no_trade = report.get("no_trade_comparison", {})
    active_beats_no_trade = no_trade.get("active_beats_no_trade", None)

    # MHT control
    mht = report.get("multiple_hypothesis_control", {})
    mht_status = mht.get("mht_status", "MISSING")
    correction_method = mht.get("correction_method", "MISSING")
    trial_count_disclosure = mht.get("trial_count_disclosure", 0)
    tested_hypothesis_count = mht.get("tested_hypothesis_count", 0)
    data_snooping_risk_flag = mht.get("data_snooping_risk_flag", "MISSING")
    corrected_significance = mht.get("corrected_significance", None)

    # Regime breakdown
    regime = report.get("regime_breakdown", {})
    edge_only_rare = regime.get("edge_only_in_rare_regime", None)
    regime_count = len(regime.get("regimes", []))

    # Data scope
    scope = report.get("data_scope", {})
    symbols = scope.get("symbols", [])
    primary_tfs = scope.get("primary_timeframes", [])

    # Per-fold metrics
    per_fold = metrics.get("per_fold_metrics", [])
    fold_sharpes = [f.get("sharpe") for f in per_fold if f.get("sharpe") is not None]
    fold_expectancies = [
        f.get("expectancy_r") for f in per_fold if f.get("expectancy_r") is not None
    ]

    return {
        "mode": mode,
        "verdict": verdict,
        "fold_count": fold_count,
        "oos_trade_count": oos_trade_count,
        "oos_expectancy_r_value": oos_expectancy_r.get("value"),
        "oos_expectancy_r_ci_lower": oos_expectancy_r.get("ci_lower"),
        "oos_expectancy_r_ci_upper": oos_expectancy_r.get("ci_upper"),
        "oos_sharpe_value": oos_sharpe.get("value"),
        "active_trade_count": active_trade_count,
        "edge_survives_combined_stress": edge_survives,
        "active_beats_no_trade": active_beats_no_trade,
        "mht_status": mht_status,
        "mht_correction_method": correction_method,
        "mht_trial_count_disclosure": trial_count_disclosure,
        "mht_tested_hypothesis_count": tested_hypothesis_count,
        "mht_corrected_significance": corrected_significance,
        "mht_data_snooping_risk_flag": data_snooping_risk_flag,
        "regime_edge_only_in_rare_regime": edge_only_rare,
        "regime_count": regime_count,
        "symbols": symbols,
        "primary_timeframes": primary_tfs,
        "fold_mean_sharpe": (
            sum(fold_sharpes) / len(fold_sharpes) if fold_sharpes else None
        ),
        "fold_mean_expectancy_r": (
            sum(fold_expectancies) / len(fold_expectancies)
            if fold_expectancies
            else None
        ),
        "report_path": str(report_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate research run summary")
    parser.add_argument(
        "--report-dir",
        required=True,
        help="Directory containing mode subdirectories with report JSONs",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output JSON path",
    )
    args = parser.parse_args()

    report_dir = Path(args.report_dir)
    if not report_dir.is_dir():
        print(f"ERROR: report-dir not found: {report_dir}", file=sys.stderr)
        sys.exit(1)

    # Collect all mode_research_report_*.json files
    report_files = sorted(report_dir.rglob("mode_research_report_*.json"))
    if not report_files:
        print(f"ERROR: no mode_research_report_*.json found in {report_dir}", file=sys.stderr)
        sys.exit(1)

    summaries = []
    for rf in report_files:
        try:
            summaries.append(extract_report_summary(rf))
        except Exception as e:
            print(f"WARNING: failed to parse {rf}: {e}", file=sys.stderr)

    if not summaries:
        print("ERROR: no reports could be parsed", file=sys.stderr)
        sys.exit(1)

    output = {
        "summary_version": "1.0.0",
        "report_count": len(summaries),
        "reports": summaries,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Summary written to {output_path} ({len(summaries)} reports)")


if __name__ == "__main__":
    main()
