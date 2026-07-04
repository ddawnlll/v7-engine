#!/usr/bin/env python3
"""R Simulator Sprint — deterministic R-based trade simulation for factor candidates.

Loads real 1h OHLCV, computes factor signals, simulates R-based trades with
ATR stops/targets, writes ALPHA_R_LEADERBOARD.csv.

Uses the centralized simulation engine (simulation/) for proper cost models,
exit logic, and path metrics. Replaces the standalone R simulator.

Usage:
    PYTHONPATH=. .venv/bin/python3 scripts/factor_r_sprint.py
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

from alphaforge.factors.factors import FACTOR_REGISTRY, compute_all_factors
from alphaforge.factors.leaderboard import write_alpha_r_leaderboard
from alphaforge.factors.loader import (
    build_aligned_panel,
    load_1h_ohlcv,
)
from alphaforge.factors.r_simulator import (
    CONFIGS,
    TradeConfig,
)
from alphaforge.factors.fast_simulator import simulate_factor_fast, aggregate_trades_fast
from alphaforge.factors.simulation_adapter import _compute_atr_from_panel
from tqdm import tqdm


def main() -> None:
    print("=" * 60)
    print("R SIMULATOR SPRINT — Deterministic R-Based Trade Simulation")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    # ── STEP 1: Load data ──────────────────────────────────────────
    print("\n[1/4] Loading 1h OHLCV from data lake...")
    data_1h = load_1h_ohlcv()
    loaded = {s: df for s, df in data_1h.items() if not df.empty}
    print(f"  Loaded {len(loaded)}/{len(data_1h)} symbols")

    if len(loaded) < 5:
        print("  FATAL: Fewer than 5 symbols loaded. Aborting.")
        sys.exit(1)

    # ── STEP 2: Build aligned panels ───────────────────────────────
    print("\n[2/4] Building aligned panels...")
    panels_1h = build_aligned_panel(loaded)
    close = panels_1h.get("close")
    high = panels_1h.get("high")
    low = panels_1h.get("low")

    if close is None or close.empty:
        print("  FATAL: No close price panel. Aborting.")
        sys.exit(1)

    print(f"  Symbols: {len(close.columns)}")
    print(f"  Timestamps: {len(close)}")

    print("\n  Pre-computing ATR panel...")
    atr_panel = _compute_atr_from_panel(high, low, close, period=14)
    print(f"  ATR panel: {atr_panel.shape}")

    # ── STEP 3: Compute factors ────────────────────────────────────
    print("\n[3/4] Computing alpha factors...")
    factor_scores = compute_all_factors(panels_1h)
    print(f"  Computed {len(factor_scores)} factors")

    # ── STEP 4: Simulate R trades ──────────────────────────────────
    print("\n[4/4] Simulating R trades across factor-config combinations...")
    all_r_results = []

    # Filter out agnostic factors for R simulation (direction unclear)
    sim_factors = {
        name: scores for name, scores in factor_scores.items()
        if FACTOR_REGISTRY.get(name, ("agnostic", None))[0] != "agnostic"
    }

    total_combos = len(sim_factors) * len(CONFIGS)

    for factor_name, scores in tqdm(sim_factors.items(), desc="  Factors", total=len(sim_factors)):
        direction = FACTOR_REGISTRY.get(factor_name, ("long", None))[0]

        for config_name, config in CONFIGS.items():
            trades = simulate_factor_fast(
                factor_scores=scores,
                close=close,
                high=high,
                low=low,
                atr_panel=atr_panel,
                config_stop_mult=config.stop_mult,
                config_target_mult=config.target_mult,
                config_max_hold=config.max_hold_bars,
                direction=direction,
            )

            result = aggregate_trades_fast(trades, factor_name, config_name, direction)
            all_r_results.append(result)

            # Print summary
            n_trades = result["trades"]
            total_R = result["total_R"]
            pf = result["profit_factor"]
            pf_str = f"{pf:.2f}" if np.isfinite(pf) else "inf"
            print(f"  {factor_name} x {config_name}: trades={n_trades}, R={total_R:.2f}, PF={pf_str}, {result['pass_fail']}", flush=True)

    # ── WRITE OUTPUT ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("WRITING ALPHA_R_LEADERBOARD.csv")
    print("=" * 60)

    output_path = write_alpha_r_leaderboard(all_r_results)
    print(f"\nDone. Output: {output_path}")
    print(f"Total simulations: {len(all_r_results)}")

    # Print summary
    promote = [r for r in all_r_results if r["pass_fail"] == "PROMOTE_TO_MINI_V7"]
    watch = [r for r in all_r_results if r["pass_fail"] == "WATCH"]
    reject = [r for r in all_r_results if r["pass_fail"] == "REJECT"]

    print(f"\n  PROMOTE: {len(promote)}")
    print(f"  WATCH: {len(watch)}")
    print(f"  REJECT: {len(reject)}")

    if promote:
        print("\n--- PROMOTE candidates ---")
        for r in sorted(promote, key=lambda x: x["total_R"], reverse=True):
            print(f"  {r['alpha_name']} ({r['config_name']}): "
                  f"R={r['total_R']:.2f}, PF={r['profit_factor']:.2f}, "
                  f"trades={r['trades']}, E[R]={r['expectancy_R']:.4f}")

    if watch:
        print("\n--- WATCH candidates ---")
        for r in sorted(watch, key=lambda x: x["total_R"], reverse=True)[:5]:
            print(f"  {r['alpha_name']} ({r['config_name']}): "
                  f"R={r['total_R']:.2f}, PF={r['profit_factor']:.2f}, "
                  f"trades={r['trades']}")

    print(f"\nCompleted: {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
