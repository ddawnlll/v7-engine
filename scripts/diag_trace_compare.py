#!/usr/bin/env python3
"""Diagnostic: trace one symbol (FILUSDT), one month, compare trade-by-trade.

- fast_simulator → trades
- simulation_adapter (simulation.engine) → trades

Same factor, same config, same period. Show entry/exit details.
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

from alphaforge.factors.factors import compute_all_factors
from alphaforge.factors.loader import (
    load_1h_ohlcv_gpu,
    load_or_build_aligned_panel_gpu,
)
from alphaforge.factors.r_simulator import CONFIGS
from alphaforge.factors.simulation_adapter import (
    simulate_trades_for_factor,
    _compute_atr_from_panel,
)
from alphaforge.factors.fast_simulator import simulate_factor_fast


def main() -> None:
    TARGET_SYMBOL = "FILUSDT"
    START = "2024-01-01"
    END = "2024-01-31"

    print("=" * 60)
    print(f"DİAGNOSTİK: {TARGET_SYMBOL}, {START} → {END}")
    print("breakdown_n_low × SCALP_1H_SLOW")
    print("fast_simulator vs simulation_adapter trade-by-trade")
    print("=" * 60)

    # ── 1. Load & slice data ──
    print(f"\n[1] Loading 1h OHLCV...")
    data_1h = load_1h_ohlcv_gpu()
    loaded = {s: df for s, df in data_1h.items() if not df.empty}
    panels = load_or_build_aligned_panel_gpu(loaded)

    # Slice time range
    sliced = {}
    for k, df in panels.items():
        sliced[k] = df.loc[START:END]

    close = sliced["close"]
    high = sliced["high"]
    low = sliced["low"]

    # Keep only TARGET_SYMBOL (but factor computation needs multi-symbol)
    # Actually, keep all symbols for factor computation, slice to one for trade comparison
    print(f"  Full panel: {close.shape}, Range: {close.index[0]} → {close.index[-1]}")

    atr_panel = _compute_atr_from_panel(high, low, close, period=14)
    print(f"  ATR panel: {atr_panel.shape}")

    # ── 2. Compute breakdown_n_low ──
    print(f"\n[2] Computing factors...")
    factor_scores = compute_all_factors(sliced)
    scores = factor_scores["breakdown_n_low"]
    print(f"  breakdown_n_low: {scores.shape}")

    config = CONFIGS["SCALP_1H_SLOW"]
    direction = "short"

    # ── 3. Run fast_simulator ──
    print(f"\n[3] fast_simulator...")
    t0 = datetime.now()
    fs_trades = simulate_factor_fast(
        factor_scores=scores,
        close=close, high=high, low=low,
        atr_panel=atr_panel,
        config_stop_mult=config.stop_mult,
        config_target_mult=config.target_mult,
        config_max_hold=config.max_hold_bars,
        direction=direction,
    )
    fs_elapsed = (datetime.now() - t0).total_seconds()
    fs_trades_sym = [t for t in fs_trades if t["symbol"] == TARGET_SYMBOL]
    print(f"  fast_simulator: {len(fs_trades)} trades total, {len(fs_trades_sym)} for {TARGET_SYMBOL}, in {fs_elapsed:.1f}s")

    # ── 4. Run simulation_adapter ──
    print(f"\n[4] simulation_adapter (simulation.engine)...")
    t0 = datetime.now()
    sa_trades = simulate_trades_for_factor(
        factor_scores=scores,
        close=close, high=high, low=low,
        config=config, direction=direction,
        atr_panel=atr_panel,
    )
    sa_elapsed = (datetime.now() - t0).total_seconds()
    sa_trades_sym = [t for t in sa_trades if t.symbol == TARGET_SYMBOL]
    print(f"  simulation_adapter: {len(sa_trades)} trades total, {len(sa_trades_sym)} for {TARGET_SYMBOL}, in {sa_elapsed:.1f}s")

    # ── 5. Compare per-symbol ──
    print(f"\n{'='*60}")
    print(f"KARŞILAŞTIRMA: {TARGET_SYMBOL} — {START} → {END}")
    print(f"{'='*60}")

    # fast_simulator summary
    fs_R = np.array([t["R"] for t in fs_trades_sym])
    fs_hold = np.array([t["hold_bars"] for t in fs_trades_sym])
    fs_exit_types = {}
    for t in fs_trades_sym:
        fs_exit_types[t["exit_reason"]] = fs_exit_types.get(t["exit_reason"], 0) + 1

    print(f"\nfast_simulator ({len(fs_trades_sym)} trades):")
    print(f"  avg_R: {fs_R.mean():.4f}, total_R: {fs_R.sum():.2f}")
    print(f"  hold_bars: mean={fs_hold.mean():.1f}, median={np.median(fs_hold):.1f}")
    print(f"  exit types: {fs_exit_types}")

    # simulation_adapter summary
    sa_R = np.array([t.R for t in sa_trades_sym])
    sa_hold = np.array([t.hold_bars for t in sa_trades_sym])
    sa_exit_types = {}
    for t in sa_trades_sym:
        sa_exit_types[t.exit_reason] = sa_exit_types.get(t.exit_reason, 0) + 1

    print(f"\nsimulation_adapter ({len(sa_trades_sym)} trades):")
    print(f"  avg_R: {sa_R.mean():.4f}, total_R: {sa_R.sum():.2f}")
    print(f"  hold_bars: mean={sa_hold.mean():.1f}, median={np.median(sa_hold):.1f}")
    print(f"  exit types: {sa_exit_types}")

    # ── 6. Align by entry_ts ──
    print(f"\n{'='*60}")
    print("ENTRY KARŞILAŞTIRMASI (ilk 20 trade)")
    print(f"{'='*60}")

    fs_by_ts = {str(t["entry_ts"]): t for t in fs_trades_sym[:20]}
    sa_by_ts = {str(t.entry_ts): t for t in sa_trades_sym[:20]}

    all_ts = sorted(set(fs_by_ts.keys()) | set(sa_by_ts.keys()))
    print(f"{'Timestamp':<22} {'FS_R':>8} {'SA_R':>8} {'FS_hold':>7} {'SA_hold':>7} {'FS_exit':>10} {'SA_exit':>10}")
    print("-" * 72)
    for ts in all_ts[:20]:
        fs_t = fs_by_ts.get(ts)
        sa_t = sa_by_ts.get(ts)
        fs_r = f"{fs_t['R']:.3f}" if fs_t else "---"
        sa_r = f"{sa_t.R:.3f}" if sa_t else "---"
        fs_h = f"{fs_t['hold_bars']}" if fs_t else "---"
        sa_h = f"{sa_t.hold_bars}" if sa_t else "---"
        fs_ex = fs_t['exit_reason'] if fs_t else "---"
        sa_ex = sa_t.exit_reason if sa_t else "---"
        print(f"{ts[:19]:22} {fs_r:>8} {sa_r:>8} {fs_h:>7} {sa_h:>7} {fs_ex:>10} {sa_ex:>10}")

    # ── 7. Count consecutive same-bar entries ──
    print(f"\n{'='*60}")
    print("ART ARDA GİRİŞ ANALİZİ")
    print(f"{'='*60}")

    # fast_simulator: count how many trades have the same entry_ts as the previous one
    fs_ts_list = sorted([str(t["entry_ts"]) for t in fs_trades_sym])
    sa_ts_list = sorted([str(t.entry_ts) for t in sa_trades_sym])

    def count_consecutive(ts_list):
        if not ts_list:
            return 0, {}
        same = 0
        gaps = {}
        for i in range(1, len(ts_list)):
            gap = (pd.Timestamp(ts_list[i]) - pd.Timestamp(ts_list[i-1])).total_seconds() / 3600
            gaps[gap] = gaps.get(gap, 0) + 1
            if gap == 0:
                same += 1
        return same, gaps

    fs_same, fs_gaps = count_consecutive(fs_ts_list)
    sa_same, sa_gaps = count_consecutive(sa_ts_list)

    print(f"\nfast_simulator:")
    print(f"  same-bar entries: {fs_same}/{len(fs_ts_list)}")
    print(f"  0h gaps: {fs_gaps.get(0, 0)}, 1h gaps: {fs_gaps.get(1, 0)}, >1h gaps: {sum(v for k,v in fs_gaps.items() if k > 1)}")

    print(f"\nsimulation_adapter:")
    print(f"  same-bar entries: {sa_same}/{len(sa_ts_list)}")
    print(f"  0h gaps: {sa_gaps.get(0, 0)}, 1h gaps: {sa_gaps.get(1, 0)}, >1h gaps: {sum(v for k,v in sa_gaps.items() if k > 1)}")

    print(f"\nDone. fast_sim={fs_elapsed:.1f}s, sim_adapter={sa_elapsed:.1f}s")


if __name__ == "__main__":
    main()
