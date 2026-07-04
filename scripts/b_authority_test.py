#!/usr/bin/env python3
"""B: breakdown_n_low x SCALP_1H_SLOW — tek kombinasyon, simulation.engine ile.

Aşama 2 — authority farkını ölçmek için dar test.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_ROOT)
ALPHAFORGE_SRC = str(Path(PROJECT_ROOT, "alphaforge", "src").resolve())
sys.path.insert(0, ALPHAFORGE_SRC)

import numpy as np
import pandas as pd

from alphaforge.factors.factors import FACTOR_REGISTRY, compute_all_factors
from alphaforge.factors.loader import (
    load_1h_ohlcv_gpu,
    load_or_build_aligned_panel_gpu,
)
from alphaforge.factors.r_simulator import CONFIGS
from alphaforge.factors.simulation_adapter import (
    simulate_trades_for_factor,
    aggregate_trades_fast,
    _compute_atr_from_panel,
)


def main() -> None:
    print("=" * 60)
    print("B TEST: breakdown_n_low × SCALP_1H_SLOW → simulation.engine")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    # ── 1. Load data ──
    print("\n[1/4] Loading 1h OHLCV...")
    data_1h = load_1h_ohlcv_gpu()
    loaded = {s: df for s, df in data_1h.items() if not df.empty}
    print(f"  Loaded {len(loaded)}/{len(data_1h)} symbols")

    # ── 2. Build panels ──
    print("\n[2/4] Building aligned panels...")
    panels_1h = load_or_build_aligned_panel_gpu(loaded)
    close = panels_1h["close"]
    high = panels_1h["high"]
    low = panels_1h["low"]
    print(f"  Symbols: {len(close.columns)}, Timestamps: {len(close)}")

    print("\n  Pre-computing ATR...")
    atr_panel = _compute_atr_from_panel(high, low, close, period=14)
    print(f"  ATR panel: {atr_panel.shape}")

    # ── 3. Compute breakdown_n_low ──
    print("\n[3/4] Computing factors...")
    factor_scores = compute_all_factors(panels_1h)
    scores = factor_scores.get("breakdown_n_low")
    if scores is None:
        print("  FATAL: breakdown_n_low not found")
        sys.exit(1)
    print(f"  breakdown_n_low: {scores.shape}")

    # ── 4. Simulate via simulation.engine ──
    print("\n[4/4] Simulating trades via simulation.engine (TrainingAdapter)...\n")
    config = CONFIGS["SCALP_1H_SLOW"]
    direction = "short"

    t0 = datetime.now()
    trades = simulate_trades_for_factor(
        factor_scores=scores,
        close=close,
        high=high,
        low=low,
        config=config,
        direction=direction,
        atr_panel=atr_panel,
    )
    elapsed = (datetime.now() - t0).total_seconds()
    print(f"  Simulated {len(trades)} trades in {elapsed:.1f}s")

    # ── 5. Aggregate ──
    trade_dicts = [
        {
            "symbol": t.symbol, "side": t.side,
            "entry_ts": str(t.entry_ts), "exit_ts": str(t.exit_ts),
            "entry_price": t.entry_price, "exit_price": t.exit_price,
            "stop_price": t.stop_price, "target_price": t.target_price,
            "initial_risk": t.initial_risk, "pnl": t.pnl, "R": t.R,
            "exit_reason": t.exit_reason, "hold_bars": t.hold_bars, "cost": t.cost,
        }
        for t in trades
    ]

    result = aggregate_trades_fast(trade_dicts, "breakdown_n_low", "SCALP_1H_SLOW", direction)

    # ── 6. Print results ──
    print("\n" + "=" * 60)
    print("SIMULATION.ENGINE SONUCU — breakdown_n_low × SCALP_1H_SLOW")
    print("=" * 60)
    for k, v in result.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}" if abs(v) < 1e6 else f"  {k}: {v}")
        else:
            print(f"  {k}: {v}")

    print(f"\nElapsed: {elapsed:.1f}s")
    print(f"Completed: {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
