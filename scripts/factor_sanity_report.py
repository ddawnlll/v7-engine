#!/usr/bin/env python3
"""Sanity Report — validates factor sprint outputs and generates V7_ALPHA_CANDIDATES.md.

Reads the CSV outputs from factor_sprint.py and factor_r_sprint.py,
runs sanity checks, and produces human-readable reports.

Usage:
    PYTHONPATH=. .venv/bin/python3 scripts/factor_sanity_report.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# Ensure project root on path
PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_ROOT)

import numpy as np
import pandas as pd

from alphaforge.factors.leaderboard import (
    REPORTS_DIR,
    generate_v7_alpha_candidates,
)


def run_sanity_checks() -> str:
    """Run sanity checks on output CSVs and return markdown report."""
    lines = [
        "# Alpha Sanity Report — Factor Sprint 001",
        "",
        f"Generated: {datetime.now().isoformat()}",
        "",
    ]

    # ── Check ALPHA_LEADERBOARD.csv ────────────────────────────────
    ic_path = REPORTS_DIR / "ALPHA_LEADERBOARD.csv"
    lines.append("## ALPHA_LEADERBOARD.csv Sanity Checks")
    lines.append("")

    if not ic_path.exists():
        lines.append("❌ **FAIL**: ALPHA_LEADERBOARD.csv does not exist")
        ic_df = None
    else:
        ic_df = pd.read_csv(ic_path)
        lines.append(f"✅ File exists: {len(ic_df)} rows")

        # Check required columns
        required_cols = [
            "factor_name", "horizon", "direction", "mean_rank_ic",
            "ic_ir", "top_bottom_net_return", "n_timestamps",
            "n_symbols", "pass_fail",
        ]
        missing_cols = [c for c in required_cols if c not in ic_df.columns]
        if missing_cols:
            lines.append(f"❌ **FAIL**: Missing columns: {missing_cols}")
        else:
            lines.append("✅ All required columns present")

        # Check candidate count
        n_factors = ic_df["factor_name"].nunique()
        if n_factors >= 12:
            lines.append(f"✅ At least 12 candidates: {n_factors} unique factors")
        else:
            lines.append(f"⚠️ WARNING: Only {n_factors} unique factors (expected >= 12)")

        # Check horizon coverage
        horizons = sorted(ic_df["horizon"].unique())
        lines.append(f"- Horizons tested: {horizons}")
        expected = {1, 4, 12, 24}
        missing_h = expected - set(horizons)
        if missing_h:
            lines.append(f"⚠️ WARNING: Missing horizons: {missing_h}")

        # Check symbol count
        min_symbols = ic_df["n_symbols"].min()
        if min_symbols >= 10:
            lines.append(f"✅ Minimum symbol count: {min_symbols} (>= 10)")
        else:
            lines.append(f"⚠️ WARNING: Min symbol count: {min_symbols} (< 10)")

        # Check pass/fail distribution
        pf_counts = ic_df["pass_fail"].value_counts()
        lines.append(f"- PASS: {pf_counts.get('PASS', 0)}")
        lines.append(f"- WATCH: {pf_counts.get('WATCH', 0)}")
        lines.append(f"- FAIL: {pf_counts.get('FAIL', 0)}")

        # Check for critical NaN issues
        nan_rate = ic_df["mean_rank_ic"].isna().mean()
        if nan_rate > 0.5:
            lines.append(f"⚠️ WARNING: {nan_rate:.0%} of IC values are NaN")
        else:
            lines.append(f"✅ IC NaN rate: {nan_rate:.1%}")

        # Date range
        if "start_ts" in ic_df.columns and "end_ts" in ic_df.columns:
            starts = ic_df["start_ts"].dropna()
            ends = ic_df["end_ts"].dropna()
            if len(starts) > 0 and len(ends) > 0:
                lines.append(f"- Date range: {starts.min()} to {ends.max()}")

    lines.append("")

    # ── Check ALPHA_R_LEADERBOARD.csv ──────────────────────────────
    r_path = REPORTS_DIR / "ALPHA_R_LEADERBOARD.csv"
    lines.append("## ALPHA_R_LEADERBOARD.csv Sanity Checks")
    lines.append("")

    if not r_path.exists():
        lines.append("❌ **FAIL**: ALPHA_R_LEADERBOARD.csv does not exist")
        r_df = None
    else:
        r_df = pd.read_csv(r_path)
        lines.append(f"✅ File exists: {len(r_df)} rows")

        # Check required columns
        required_r_cols = [
            "alpha_name", "config_name", "trades", "total_R",
            "expectancy_R", "profit_factor", "max_drawdown_R",
            "pass_fail",
        ]
        missing_r_cols = [c for c in required_r_cols if c not in r_df.columns]
        if missing_r_cols:
            lines.append(f"❌ **FAIL**: Missing columns: {missing_r_cols}")
        else:
            lines.append("✅ All required columns present")

        # Check trade counts
        min_trades = r_df["trades"].min()
        if min_trades > 0:
            lines.append(f"✅ All configurations have trades (min: {min_trades})")
        else:
            zero_trades = (r_df["trades"] == 0).sum()
            lines.append(f"⚠️ WARNING: {zero_trades} configurations have 0 trades")

        # Check R results
        pf_counts_r = r_df["pass_fail"].value_counts()
        lines.append(f"- PROMOTE_TO_MINI_V7: {pf_counts_r.get('PROMOTE_TO_MINI_V7', 0)}")
        lines.append(f"- WATCH: {pf_counts_r.get('WATCH', 0)}")
        lines.append(f"- REJECT: {pf_counts_r.get('REJECT', 0)}")

        # Fee drag check
        if "fee_drag_R" in r_df.columns:
            avg_fee_drag = r_df["fee_drag_R"].mean()
            lines.append(f"- Average fee drag: {avg_fee_drag:.4f} R")

        # Dominant symbol check
        if "dominant_symbol_share" in r_df.columns:
            dominant = r_df["dominant_symbol_share"]
            over_50 = (dominant > 0.50).sum()
            if over_50 > 0:
                lines.append(f"⚠️ WARNING: {over_50} configurations dominated by single symbol")

    lines.append("")

    # ── Cross-check: top factors should appear in both ─────────────
    lines.append("## Cross-Check: IC × R Consistency")
    lines.append("")

    if ic_df is not None and r_df is not None:
        # Find top IC factors
        pass_factors = set(
            ic_df[ic_df["pass_fail"] == "PASS"]["factor_name"].unique()
        )
        promote_factors = set(
            r_df[r_df["pass_fail"] == "PROMOTE_TO_MINI_V7"]["alpha_name"].unique()
        )
        watch_factors_r = set(
            r_df[r_df["pass_fail"] == "WATCH"]["alpha_name"].unique()
        )

        ic_promote_overlap = pass_factors & promote_factors
        ic_watch_overlap = pass_factors & watch_factors_r

        if ic_promote_overlap:
            lines.append(f"✅ IC-PASS + R-PROMOTE overlap: {ic_promote_overlap}")
        else:
            lines.append("⚠️ No IC-PASS factor also achieves R-PROMOTE")

        if ic_watch_overlap:
            lines.append(f"- IC-PASS + R-WATCH: {ic_watch_overlap}")

        # Factors that are IC-FAIL but R-PROMOTE (suspicious)
        fail_factors = set(
            ic_df[ic_df["pass_fail"] == "FAIL"]["factor_name"].unique()
        )
        suspicious = fail_factors & promote_factors
        if suspicious:
            lines.append(f"⚠️ WARNING: IC-FAIL but R-PROMOTE: {suspicious}")
    else:
        lines.append("- Skipped (missing CSV)")

    lines.append("")

    # ── Overall verdict ────────────────────────────────────────────
    lines.append("## Overall Verdict")
    lines.append("")

    if ic_df is None or r_df is None:
        lines.append("❌ **INCOMPLETE** — Missing output files.")
    elif len(ic_df) < 12:
        lines.append("⚠️ **PARTIAL** — Fewer than 12 factor evaluations.")
    elif (r_df["pass_fail"] == "REJECT").all():
        lines.append("📊 **NEGATIVE EVIDENCE** — All candidates rejected. "
                      "This is valuable: the lab measured deterministic alphas honestly.")
    else:
        has_promote = (r_df["pass_fail"] == "PROMOTE_TO_MINI_V7").any()
        has_watch = (r_df["pass_fail"] == "WATCH").any()
        if has_promote:
            lines.append("✅ **CANDIDATES FOUND** — See V7_ALPHA_CANDIDATES.md")
        elif has_watch:
            lines.append("⚠️ **WATCH CANDIDATES** — Marginal signals, need further validation")
        else:
            lines.append("📊 **MIXED** — Some signals exist but none pass all gates")

    content = "\n".join(lines) + "\n"

    # Write report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "ALPHA_SANITY_REPORT.md"
    report_path.write_text(content)
    print(f"[sanity] Wrote {report_path}")

    return content


def generate_candidates() -> None:
    """Generate V7_ALPHA_CANDIDATES.md from the R leaderboard and IC leaderboard."""
    ic_path = REPORTS_DIR / "ALPHA_LEADERBOARD.csv"
    r_path = REPORTS_DIR / "ALPHA_R_LEADERBOARD.csv"

    if not ic_path.exists() or not r_path.exists():
        print("[sanity] Cannot generate candidates: missing CSV files")
        return

    ic_df = pd.read_csv(ic_path)
    r_df = pd.read_csv(r_path)

    ic_results = ic_df.to_dict("records")
    r_results = r_df.to_dict("records")

    output = generate_v7_alpha_candidates(r_results, ic_results)
    print(f"[sanity] Generated {output}")


def main() -> None:
    print("=" * 60)
    print("SANITY REPORT — Factor Sprint 001")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    # Run sanity checks
    report = run_sanity_checks()
    print(report)

    # Generate V7 candidates
    print("\n" + "=" * 60)
    print("GENERATING V7_ALPHA_CANDIDATES.md")
    print("=" * 60)
    generate_candidates()

    print(f"\nCompleted: {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
