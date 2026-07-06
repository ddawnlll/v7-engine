#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════╗
# ║  DEPRECATED: Sentetik veri kullanir.                      ║
# ║  Gercek veri icin scripts/phase_reality_complete.py       ║
# ║  veya scripts/candidate_v031e_verified.py kullanin.       ║
# ╚══════════════════════════════════════════════════════════════╝

"""
Faz 2 - İterasyon 2 (Threshold Trade-off Taraması)

Amaç: total_net_R / max_drawdown kompozit metriğiyle dengeli threshold bulmak.
Val/Test ayrımı: folds 0-4 grid için val, fold 5 test/OOS.
Block-bootstrap CI ile doğrulama.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(os.environ.get("V7_ENGINE_ROOT", "/home/daskomputer/src/v7-engine"))
os.chdir(str(_REPO_ROOT))
_EXTRA_PATHS = [str(_REPO_ROOT), str(_REPO_ROOT / "alphaforge" / "src"), str(_REPO_ROOT / "simulation"), str(_REPO_ROOT / "lib")]
for p in _EXTRA_PATHS:
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np
from simulation.authority import get_cost_constants
COST = get_cost_constants()
print(f"Cost constants: {json.dumps(COST, indent=2)}")

from alphaforge.train import build_aligned_training_frame, walk_forward_validate, generate_synthetic_ohlcv
from alphaforge.reports.metrics import compute_oos_metrics


def compute_equity_curve(trade_r, timestamps):
    """Compute equity curve and max drawdown from chronologically sorted trades."""
    order = np.argsort(timestamps)
    sorted_r = np.array(trade_r)[order]
    equity = np.cumsum(sorted_r)
    running_max = np.maximum.accumulate(equity)
    drawdowns = running_max - equity
    max_dd = float(drawdowns.max()) if len(drawdowns) > 0 else 0.0
    return equity, max_dd


def block_bootstrap_ci(trade_r, timestamps, block_size=48, n_resamples=10000, seed=42):
    """Block bootstrap CI for mean R."""
    rng = np.random.RandomState(seed)
    order = np.argsort(timestamps)
    trade_r_sorted = trade_r[order]
    n = len(trade_r_sorted)
    if n < 10:
        return {"observed_mean_r": float(trade_r.mean()) if n > 0 else 0.0, "n_trades": n, "n_blocks": 0, "total_net_r": float(trade_r.sum()) if n > 0 else 0.0, "ci_lower_block": None, "ci_upper_block": None}
    block_ids = np.arange(n) // block_size
    u = np.unique(block_ids)
    bg = [trade_r_sorted[block_ids == b] for b in u]
    n_non = int((np.array([len(g) for g in bg]) > 0).sum())

    observed = float(trade_r_sorted.mean())
    bg_ne = [g for g in bg if len(g) > 0]

    bm = np.zeros(n_resamples)
    for i in range(n_resamples):
        idx = rng.choice(n_non, size=n_non, replace=True)
        bm[i] = np.concatenate([bg_ne[j] for j in idx]).mean()
    bm.sort()
    cl, cu = float(bm[int(n_resamples * 0.025)]), float(bm[int(n_resamples * 0.975)])

    return {"observed_mean_r": observed, "n_trades": n, "n_blocks": n_non, "total_net_r": observed * n, "ci_lower_block": cl, "ci_upper_block": cu}


def main():
    print(f"AlphaForge Faz2 - Iterasyon 2 @ {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*70}")
    print(f"THRESHOLD TRADE-OFF: total_net_R / max_drawdown")
    print(f"{'='*70}")

    # --- Pipeline ---
    ohlcv = generate_synthetic_ohlcv(n_bars=3000, symbols=("BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","ADAUSDT"), random_seed=42)
    tf = build_aligned_training_frame(ohlcv, "SCALP", feature_groups=None)
    X, y_int = tf["X"], tf["y_int"]
    an_raw = tf["action_net_r"]
    timestamps = tf["timestamps"]

    nan_mask = np.isnan(X).any(axis=1)
    X_clean = X[~nan_mask]; y_clean = y_int[~nan_mask]
    an_clean = an_raw[~nan_mask]; ts_clean = timestamps[~nan_mask]
    print(f"  {X_clean.shape[0]} valid samples, {X_clean.shape[1]} features")

    t0 = time.time()
    results, fold_preds, fold_y_class, fold_y_val = walk_forward_validate(
        X_clean, y_clean, an_clean[:,0], "SCALP", min_folds=6,
        action_net_r=an_clean, return_raw_preds=True,
    )
    print(f"  {len(results)} folds in {time.time()-t0:.1f}s")

    n = len(X_clean); fold_size = n // 7; embargo = fold_size // 8

    # Reconstruct per-fold val slices for action_net_r
    for fi in range(6):
        train_end = (fi+1)*fold_size
        vs = train_end; ve = vs + fold_size//2
        evs = vs + embargo
        results[fi]["val_action_net"] = an_clean[evs:ve] if evs < ve else np.empty((0,3))
        results[fi]["val_timestamps"] = ts_clean[evs:ve] if evs < ve else np.empty(0)

    # --- GRID: folds 0-4 (VAL), fold 5 (TEST) ---
    grid_folds = [0,1,2,3,4]; test_fold = 5

    # Grid: center at 0.55, ±10%, ±20%, ±30%
    center = 0.55
    grid = sorted(set([
        center,
        round(center * 0.7, 3), round(center * 0.8, 3), round(center * 0.9, 3),
        round(center * 1.1, 3), round(center * 1.2, 3), round(center * 1.3, 3),
    ]))
    # Clip to [0, 1]
    grid = [max(0.0, min(1.0, t)) for t in grid]
    print(f"\n  Grid (val'de taranacak): {[f'{t:.3f}' for t in grid]}")
    print(f"  Grid folds: 1-5 (indices 0-4), Test fold: 6 (index {test_fold})")

    comp_key = lambda th: (th - center) / center * 100

    # --- Grid evaluation on val folds ---
    print(f"\n{'='*70}")
    print(f"GRID SONUCLARI (validation folds 1-5)")
    print(f"{'='*70}")
    print(f"  {'Threshold':>10} | {'Tot NetR':>10} | {'Max DD':>10} | {'Kompozit':>10} | {'Trade#':>7} | {'Exposure':>9}")
    print(f"  {'-'*10}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}-+-{'-'*7}-+-{'-'*9}")

    grid_results = {}
    for th in grid:
        total_net = 0.0; all_trade_r = []; all_trade_ts = []; all_decisions = 0

        for fi in grid_folds:
            preds = fold_preds[fi]
            y_raw = fold_y_class[fi]
            y_pred = y_raw.copy()
            y_pred[preds < th] = 2

            labels = np.array(["LONG_NOW" if p==0 else "SHORT_NOW" if p==1 else "NO_TRADE" for p in y_pred], dtype=object)
            av = results[fi]["val_action_net"]
            trade_r = av[np.arange(len(y_pred)), y_pred]

            metrics = compute_oos_metrics(labels.tolist(), trade_r.tolist(), fee_pct=0.0)
            total_net += metrics["total_net_R"]
            all_decisions += len(labels)

            fold_ts = results[fi]["val_timestamps"]
            for j, (lbl, rv, ts) in enumerate(zip(labels, trade_r, fold_ts)):
                if lbl != "NO_TRADE":
                    all_trade_r.append(float(rv))
                    all_trade_ts.append(float(ts))

        tr_arr = np.array(all_trade_r); tt_arr = np.array(all_trade_ts)
        _, max_dd = compute_equity_curve(tr_arr, tt_arr)
        composite = total_net / max_dd if max_dd > 1e-12 else 999.0
        n_trades = len(tr_arr)
        exposure = n_trades / all_decisions * 100 if all_decisions > 0 else 0.0

        grid_results[th] = {"total_net_R": total_net, "max_dd": max_dd, "composite": composite, "n_trades": n_trades, "exposure": exposure}
        marker = " <-- BASELINE" if abs(th - center) < 1e-6 else ""
        print(f"  {th:>10.3f} | {total_net:>10.4f} | {max_dd:>10.4f} | {composite:>10.2f} | {n_trades:>7d} | {exposure:>8.2f}%{marker}")

    # Select best threshold by composite score
    best_th = max(grid_results, key=lambda t: grid_results[t]["composite"])
    best_val = grid_results[best_th]
    print(f"\n  >>> SECILEN THRESHOLD: {best_th:.3f} (kompozit={best_val['composite']:.2f}, totNetR={best_val['total_net_R']:.4f}, maxDD={best_val['max_dd']:.4f})")

    # --- TEST: evaluate selected threshold on fold 5 (test/OOS) ---
    print(f"\n{'='*70}")
    print(f"TEST/ OOS: fold {test_fold+1} ile dogrulama")
    print(f"{'='*70}")

    fi = test_fold
    preds = fold_preds[fi]
    y_raw = fold_y_class[fi]
    y_pred = y_raw.copy()
    y_pred[preds < best_th] = 2

    labels = np.array(["LONG_NOW" if p==0 else "SHORT_NOW" if p==1 else "NO_TRADE" for p in y_pred], dtype=object)
    av = results[fi]["val_action_net"]
    trade_r = av[np.arange(len(y_pred)), y_pred]
    fold_ts = results[fi]["val_timestamps"]

    metrics = compute_oos_metrics(labels.tolist(), trade_r.tolist(), fee_pct=0.0)
    test_total_net = metrics["total_net_R"]
    test_active = metrics["active_trade_count"]
    test_long = metrics["long_trade_count"]
    test_short = metrics["short_trade_count"]
    test_no_trade = metrics["no_trade_count"]
    test_exposure = metrics["exposure_pct"]

    all_test_r = []; all_test_ts = []
    for lbl, rv, ts in zip(labels, trade_r, fold_ts):
        if lbl != "NO_TRADE":
            all_test_r.append(float(rv))
            all_test_ts.append(float(ts))

    test_tr = np.array(all_test_r); test_tt = np.array(all_test_ts)
    _, test_max_dd = compute_equity_curve(test_tr, test_tt)
    test_composite = test_total_net / test_max_dd if test_max_dd > 1e-12 else 999.0

    # Block bootstrap on test
    bb = block_bootstrap_ci(test_tr, test_tt, block_size=24)
    bb_net_r = bb["observed_mean_r"] if bb["n_trades"] > 0 else 0.0

    print(f"\n  Threshold: {best_th:.3f}")
    print(f"  Total Net R: {test_total_net:.6f}")
    print(f"  Max DD:      {test_max_dd:.6f}")
    print(f"  Kompozit:    {test_composite:.2f}")
    print(f"  Active trades: {test_active} (L:{test_long}, S:{test_short}, NT:{test_no_trade})")
    print(f"  Exposure:    {test_exposure:.2f}%")
    print(f"  Block bootstrap 95% CI: [{bb['ci_lower_block']:.6f}, {bb['ci_upper_block']:.6f}]" if bb['ci_lower_block'] is not None else "  Block bootstrap: N/A (< 10 trades)")
    if bb['ci_lower_block'] is not None:
        print(f"  Observed mean R: {bb['observed_mean_r']:.6f}")

    # Also compute baseline (center threshold) on test for comparison
    y_pred_bl = fold_y_class[fi].copy()
    y_pred_bl[fold_preds[fi] < center] = 2
    labels_bl = np.array(["LONG_NOW" if p==0 else "SHORT_NOW" if p==1 else "NO_TRADE" for p in y_pred_bl], dtype=object)
    trade_r_bl = av[np.arange(len(y_pred_bl)), y_pred_bl]
    metrics_bl = compute_oos_metrics(labels_bl.tolist(), trade_r_bl.tolist(), fee_pct=0.0)
    test_bl_total = metrics_bl["total_net_R"]
    test_bl_active = metrics_bl["active_trade_count"]

    all_bl_r = [float(rv) for lbl, rv in zip(labels_bl, trade_r_bl) if lbl != "NO_TRADE"]
    all_bl_ts = [float(ts) for lbl, rv, ts in zip(labels_bl, trade_r_bl, fold_ts) if lbl != "NO_TRADE"]
    bl_tr = np.array(all_bl_r); bl_tt = np.array(all_bl_ts)
    _, bl_max_dd = compute_equity_curve(bl_tr, bl_tt)
    bl_composite = test_bl_total / bl_max_dd if bl_max_dd > 1e-12 else 999.0
    bb_bl = block_bootstrap_ci(bl_tr, bl_tt, block_size=24)

    print(f"\n  BASELINE ({center}) test sonucu:")
    print(f"  Total Net R: {test_bl_total:.6f}")
    print(f"  Max DD:      {bl_max_dd:.6f}")
    print(f"  Kompozit:    {bl_composite:.2f}")
    print(f"  Active trades: {test_bl_active}")
    if bb_bl['ci_lower_block'] is not None:
        print(f"  Block bootstrap 95% CI: [{bb_bl['ci_lower_block']:.6f}, {bb_bl['ci_upper_block']:.6f}]")

    print(f"\n{'='*70}")
    print(f"KARSILASTIRMA")
    print(f"{'='*70}")
    print(f"  {'Metric':<25} {'Baseline':>15} {'Secilen':>15}")
    print(f"  {'-'*25} {'-'*15} {'-'*15}")
    impr = (test_total_net - test_bl_total) / abs(test_bl_total) * 100 if abs(test_bl_total) > 1e-12 else 0.0
    print(f"  {'Threshold':<25} {center:>15.3f} {best_th:>15.3f}")
    print(f"  {'Total Net R':<25} {test_bl_total:>15.4f} {test_total_net:>15.4f}")
    print(f"  {'Max DD':<25} {bl_max_dd:>15.4f} {test_max_dd:>15.4f}")
    print(f"  {'Kompozit':<25} {bl_composite:>15.2f} {test_composite:>15.2f}")
    print(f"  {'Improvement %':<25} {'':>15} {impr:>14.2f}%")

    # --- KARAR ---
    print(f"\n{'='*70}")
    print(f"KARAR")
    print(f"{'='*70}")

    ci_pos = bb['ci_lower_block'] is not None and bb['ci_lower_block'] > 0
    net_pos = test_total_net > 0
    pass_condition = ci_pos and net_pos

    print(f"  total_net_R > 0: {'YES' if net_pos else 'NO'} ({test_total_net:.6f})")
    if bb['ci_lower_block'] is not None:
        print(f"  CI fully positive: {'YES' if ci_pos else 'NO'} ([{bb['ci_lower_block']:.6f}, {bb['ci_upper_block']:.6f}])")
    else:
        print(f"  CI fully positive: N/A (< 10 trades)")
    print(f"  Kompozit iyilesme: {impr:+.2f}%")

    if pass_condition:
        print(f"\n  >>> KARAR: PASS (total_net_R pozitif, CI tamamen pozitif)")
    else:
        print(f"\n  >>> KARAR: FAIL {'(CI sifiri kapsiyor veya total_net_R negatif)' if not ci_pos else '(yetersiz trade sayisi)'}")
        print(f"  >>> DUR — insan onayi bekleniyor.")

    print(f"\n{'='*70}")
    print(f"OZET")
    print(f"{'='*70}")
    print(f"ITERASYON: Faz 2 - Iterasyon 2 (threshold trade-off)")
    print(f"ITERASYON: Faz 2 - Iterasyon 2 (threshold trade-off)")
    print("ESIK (onceden yazilmisti): CI tamamen pozitif VE total_net_R > 0")
    grid_str = ", ".join(f"{t:.3f}" for t in grid)
    print(f"DEGISEN TEK SEY: confidence threshold (grid: [{grid_str}])")
    print(f"SECILEN THRESHOLD: {best_th:.3f}")
    print(f"TEST/OOS sonucu:")
    print(f"  total_net_R={test_total_net:.6f}, trade_count={test_active}")
    print(f"  max_dd={test_max_dd:.6f}, kompozit={test_composite:.2f}")
    print(f"  block-bootstrap 95% CI=[{bb['ci_lower_block']:.6f}, {bb['ci_upper_block']:.6f}]")
    print(f"KARAR: {'PASS' if pass_condition else 'FAIL'}")

if __name__ == "__main__":
    main()
