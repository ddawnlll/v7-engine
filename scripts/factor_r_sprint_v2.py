#!/usr/bin/env python3
"""Proxy R Leaderboard V2 — relabel standalone R simulation as proxy.

Reads existing ALPHA_R_LEADERBOARD.csv, adds proxy metadata fields,
and writes PROXY_R_LEADERBOARD_V2.csv.

Usage:
    PYTHONPATH=. .venv/bin/python3 scripts/factor_r_sprint_v2.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_ROOT)

import pandas as pd

REPORTS_DIR = Path("reports/alphaforge/factor_sprint")
INPUT_CSV = REPORTS_DIR / "ALPHA_R_LEADERBOARD.csv"
OUTPUT_CSV = REPORTS_DIR / "PROXY_R_LEADERBOARD_V2.csv"


def main() -> None:
    print("=" * 60)
    print("PROXY R LEADERBOARD V2 — Standalone R Relabeled as Proxy")
    print("=" * 60)

    if not INPUT_CSV.exists():
        print(f"  FATAL: {INPUT_CSV} not found. Run factor_r_sprint.py first.")
        sys.exit(1)

    df = pd.read_csv(INPUT_CSV)
    print(f"  Read {len(df)} rows from {INPUT_CSV}")

    # Add proxy metadata fields
    df["simulation_source"] = "standalone_proxy"
    df["official_v7_sim"] = False
    df["cost_model_source"] = "fast_simulator TOTAL_COST_RATE=0.0012"
    df["execution_model_source"] = "fast_simulator_numba"

    # Reorder columns: rank, metadata fields, then original columns
    meta_cols = ["simulation_source", "official_v7_sim", "cost_model_source", "execution_model_source"]
    orig_cols = [c for c in df.columns if c not in meta_cols]
    final_cols = orig_cols[:1] + meta_cols + orig_cols[1:]  # Insert after rank
    df = df[final_cols]

    # Write output
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"  Wrote {OUTPUT_CSV}: {len(df)} rows")

    # Summary
    print(f"\n  All rows marked as simulation_source=standalone_proxy")
    print(f"  All rows marked as official_v7_sim=False")
    print(f"  Cost model: fast_simulator TOTAL_COST_RATE=0.0012 (0.12% round trip)")
    print(f"  Execution model: fast_simulator_numba")

    best = df.loc[df["total_R"].idxmax()] if len(df) > 0 else None
    if best is not None:
        print(f"\n  Best result: {best['alpha_name']} ({best['config_name']})")
        print(f"    total_R={best['total_R']:.2f}, PF={best['profit_factor']:.2f}, "
              f"trades={best['trades']}")
        print(f"    official_v7_sim={best['official_v7_sim']}")

    print(f"\nDone.")


if __name__ == "__main__":
    main()
