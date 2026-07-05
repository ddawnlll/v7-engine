#!/usr/bin/env python3
"""Phase 2 - Iteration 1b: Confidence Threshold Optimization for TOTAL Net R.

Tek degisken: CONFIDENCE_THRESHOLD.
Hedef: avg_net_R_per_active_trade degil, TOTAL net R.
Pipeline, model, features, data: SABIT.
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
_EXTRA_PATHS = [
    str(_REPO_ROOT),
    str(_REPO_ROOT / "alphaforge" / "src"),
    str(_REPO_ROOT / "simulation"),
    str(_REPO_ROOT / "lib"),
]
for p in _EXTRA_PATHS:
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ["PYTHONPATH"] = os.pathsep.join(_EXTRA_PATHS + ([os.environ["PYTHONPATH"]] if "PYTHONPATH" in os.environ else []))

import numpy as np

from simulation.authority import get_cost_constants
_COST = get_cost_constants()
print(f"Cost constants: {json.dumps(_COST, indent=2)}")

from alphaforge.train import (
    build_aligned_training_frame,
    walk_forward_validate,
    MODE_CONFIG,
    CONFIDENCE_THRESHOLD,
    generate_synthetic_ohlcv,
)
from alphaforge.reports.metrics import compute_oos_metrics


def run_pipeline(mode="SCALP", folds=6):
    print(f"\n{'='*70}")
    print(f"PHASE 2 - ITERATION 1b: Threshold Sweep (TOTAL Net R)")
    print(f"{'='*70}\n")

    print("[1/4] Generating synthetic OHLCV...")
    ohlcv = generate_synthetic_ohlcv(
        n_bars=3000, symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"),
        random_seed=42
    )
    print(f"  {len(ohlcv['close'])} total bars, {len(set(ohlcv['symbol']))} symbols")

    print("\n[2/4] Building aligned training frame...")
    tf = build_aligned_training_frame(ohlcv, mode, feature_groups=None)
    X, y_int = tf["X"], tf["y_int"]
    feat_names = tf["feature_names"]
    an_clean_raw = tf["action_net_r"]
    timestamps = tf["timestamps"]
    print(f"  {X.shape[1]} features, {X.shape[0]} aligned rows")

    print("\n[3/4] Cleaning NaNs...")
    nan_mask = np.isnan(X).any(axis=1)
    X_clean = X[~nan_mask]
    y_clean = y_int[~nan_mask]
    an_clean = an_clean_raw[~nan_mask]
    ts_clean = timestamps[~nan_mask]
    print(f"  {len(X_clean)} valid samples ({int(nan_mask.sum())} dropped)")

    print(f"\n[4/4] Walk-forward validation ({folds} folds, return_raw_preds)...")
    t0 = time.time()
    results, fold_preds, fold_y_class, fold_y_val = walk_forward_validate(
        X_clean, y_clean, an_clean[:, 1] if an_clean.ndim == 2 and an_clean.shape[1] == 1 else an_clean[:, 0],
        mode, min_folds=folds, action_net_r=an_clean, return_raw_preds=True,
    )
    duration = time.time() - t0
    print(f"  {len(results)} folds in {duration:.1f}s")

    return {
        "wfv_results": results,
        "fold_preds": fold_preds,
        "fold_y_class": fold_y_class,
        "fold_y_val": fold_y_val,
        "X_clean": X_clean,
        "feat_names": feat_names,
        "timestamps": ts_clean,
        "action_net_r": an_clean,
    }


def block_bootstrap_ci(trade_r, timestamps, block_size=48, n_resamples=10000, seed=42):
    rng = np.random.RandomState(seed)
    order = np.argsort(timestamps)
    trade_r_sorted = trade_r[order]
    n = len(trade_r_sorted)
    block_ids = np.arange(n) // block_size
    u = np.unique(block_ids)
    bg = [trade_r_sorted[block_ids == b] for b in u]
    bs_arr = np.array([len(g) for g in bg])
    n_non = int((bs_arr > 0).sum())

    observed = float(trade_r_sorted.mean())
    bg_ne = [g for g, s in zip(bg, bs_arr) if s > 0]

    bm = np.zeros(n_resamples)
    for i in range(n_resamples):
        idx = rng.choice(n_non, size=n_non, replace=True)
        bm[i] = np.concatenate([bg_ne[j] for j in idx]).mean()
    bm.sort()
    cl, cu = float(bm[int(n_resamples * 0.025)]), float(bm[int(n_resamples * 0.975)])

    nm = np.zeros(n_resamples)
    for i in range(n_resamples):
        nm[i] = rng.choice(trade_r_sorted, size=n, replace=True).mean()
    nm.sort()
    nl, nu = float(nm[int(n_resamples * 0.025)]), float(nm[int(n_resamples * 0.975)])

    return {
        "observed_mean_r": observed,
        "n_trades": n,
        "n_blocks": n_non,
        "total_net_r": observed * n,
        "ci_lower_block": cl,
        "ci_upper_block": cu,
        "ci_lower_naive": nl,
        "ci_upper_naive": nu,
    }


def main():
    print(f"AlphaForge Phase 2 - Iteration 1b @ {datetime.now(timezone.utc).isoformat()}")

    data = run_pipeline(mode="SCALP", folds=6)
    wfv_results = data["wfv_results"]

    n = len(data["X_clean"])
    fold_size = n // (6 + 1)
    purge_bars = fold_size // 4
    embargo_bars = fold_size // 8
    all_an = data["action_net_r"]

    # Attach val_action_net to each fold result
    for fi in range(len(wfv_results)):
        train_end = (fi + 1) * fold_size
        val_start = train_end
        val_end = val_start + fold_size // 2
        effective_val_start = val_start + embargo_bars
        if effective_val_start >= val_end:
            wfv_results[fi]["val_action_net"] = np.empty((0, 3))
        else:
            wfv_results[fi]["val_action_net"] = all_an[effective_val_start:val_end]

    # Threshold sweep with TOTAL NET R as objective
    thresholds = np.arange(0.15, 0.96, 0.025)
    print(f"\n{'='*70}")
    print(f"THRESHOLD SWEEP (objective = TOTAL NET R, not per-trade avg)")
    print(f"{'='*70}")
    print(f"  Range: {thresholds[0]:.3f} to {thresholds[-1]:.3f}, step={thresholds[1]-thresholds[0]:.3f}")
    print(f"  Baseline threshold = 0.55")

    results_by_threshold = {}
    for th in thresholds:
        total_net_sum = 0.0
        total_active = 0
        total_all_decisions = 0
        fold_net_vals = []
        all_trade_r = []
        all_trade_ts = []

        for fi in range(len(wfv_results)):
            preds = data["fold_preds"][fi]
            y_pred_raw = data["fold_y_class"][fi]
            y_val = data["fold_y_val"][fi]

            y_pred = y_pred_raw.copy()
            y_pred[preds < th] = 2

            labels = np.array(["LONG_NOW" if p == 0 else "SHORT_NOW" if p == 1 else "NO_TRADE" for p in y_pred], dtype=object)
            action_vals = wfv_results[fi]["val_action_net"]
            trade_r = action_vals[np.arange(len(y_pred)), y_pred]

            metrics = compute_oos_metrics(labels.tolist(), trade_r.tolist(), fee_pct=0.0)
            fold_net_vals.append(metrics["avg_net_R_per_active_trade"] if metrics["active_trade_count"] > 0 else 0.0)
            total_net_sum += metrics["total_net_R"]
            total_active += metrics["active_trade_count"]
            total_all_decisions += len(labels)

            # Collect per-trade R + timestamps for block bootstrap
            train_end = (fi + 1) * fold_size
            val_start = train_end
            val_end = val_start + fold_size // 2
            effective_val_start = val_start + embargo_bars
            fold_ts = data["timestamps"][effective_val_start:val_end]

            for j, (lbl, r_val, ts) in enumerate(zip(labels, trade_r, fold_ts)):
                if lbl != "NO_TRADE":
                    all_trade_r.append(r_val)
                    all_trade_ts.append(float(ts))

        key = round(float(th), 6)
        results_by_threshold[key] = {
            "total_net_R": total_net_sum,
            "avg_net_R_per_active_trade": (total_net_sum / total_active) if total_active > 0 else 0.0,
            "avg_net_R_per_decision": (total_net_sum / total_all_decisions) if total_all_decisions > 0 else 0.0,
            "active_trades": total_active,
            "total_decisions": total_all_decisions,
            "exposure_pct": round(total_active / total_all_decisions * 100, 2) if total_all_decisions > 0 else 0.0,
            "fold_net_r_vals": [round(v, 6) for v in fold_net_vals],
            "all_trade_r": all_trade_r,
            "all_trade_ts": all_trade_ts,
        }

    # Print sweep table
    print(f"\n  {'Threshold':>10} | {'Tot NetR':>10} | {'NetR/trade':>11} | {'NetR/dec':>10} | {'Active':>7} | {'Exposure':>9}")
    print(f"  {'-'*10}-+-{'-'*10}-+-{'-'*11}-+-{'-'*10}-+-{'-'*7}-+-{'-'*9}")
    for th, res in sorted(results_by_threshold.items()):
        marker = " <--" if abs(th - 0.55) < 0.001 else ""
        print(f"  {th:>10.3f} | {res['total_net_R']:>10.4f} | {res['avg_net_R_per_active_trade']:>11.6f} | {res['avg_net_R_per_decision']:>10.6f} | {res['active_trades']:>7d} | {res['exposure_pct']:>8.2f}%{marker}")

    # Find best threshold by TOTAL NET R
    best_th = max(results_by_threshold, key=lambda t: results_by_threshold[t]["total_net_R"])
    best_res = results_by_threshold[best_th]
    baseline = results_by_threshold.get(round(0.55, 6), {})

    print(f"\n{'='*70}")
    print(f"BEST BY TOTAL NET R: threshold = {best_th:.3f}")
    print(f"  Total Net R:        {best_res['total_net_R']:.4f}")
    print(f"  Net R / active tr:  {best_res['avg_net_R_per_active_trade']:.6f}")
    print(f"  Net R / decision:   {best_res['avg_net_R_per_decision']:.6f}")
    print(f"  Active trades:      {best_res['active_trades']}")
    print(f"  Exposure:           {best_res['exposure_pct']:.2f}%")

    if baseline:
        print(f"\n  BASELINE (0.55):")
        print(f"  Total Net R:        {baseline['total_net_R']:.4f}")
        print(f"  Net R / active tr:  {baseline['avg_net_R_per_active_trade']:.6f}")
        print(f"  Active trades:      {baseline['active_trades']}")

        tot_improvement = (best_res['total_net_R'] - baseline['total_net_R']) / abs(baseline['total_net_R']) * 100
        print(f"\n  IMPROVEMENT in Total Net R: {tot_improvement:.2f}%")

    # Block bootstrap for best threshold vs baseline
    print(f"\n{'='*70}")
    print(f"BLOCK BOOTSTRAP: best threshold = {best_th:.3f}")
    print(f"{'='*70}")
    tr = np.array(best_res["all_trade_r"])
    tt = np.array(best_res["all_trade_ts"])
    print(f"  Active trades: {len(tr)}, mean R = {tr.mean():.6f}, std = {tr.std():.6f}")
    bb_best = block_bootstrap_ci(tr, tt, block_size=48)
    print(f"  Observed mean:        {bb_best['observed_mean_r']:.6f}")
    print(f"  95% CI (block):       [{bb_best['ci_lower_block']:.6f}, {bb_best['ci_upper_block']:.6f}]")

    print(f"\n{'='*70}")
    print(f"BLOCK BOOTSTRAP: baseline = 0.55")
    print(f"{'='*70}")
    bl_tr = np.array(baseline["all_trade_r"])
    bl_tt = np.array(baseline["all_trade_ts"])
    print(f"  Active trades: {len(bl_tr)}, mean R = {bl_tr.mean():.6f}, std = {bl_tr.std():.6f}")
    bb_bl = block_bootstrap_ci(bl_tr, bl_tt, block_size=48)
    print(f"  Observed mean:        {bb_bl['observed_mean_r']:.6f}")
    print(f"  95% CI (block):       [{bb_bl['ci_lower_block']:.6f}, {bb_bl['ci_upper_block']:.6f}]")

    # Comparison table
    print(f"\n{'='*70}")
    print(f"COMPARISON")
    print(f"{'='*70}")
    best_lbl = "Best ({:.3f})".format(best_th)
    base_lbl = "Baseline (0.55)"
    print(f"  {'Metric':<35} {base_lbl:>20} {best_lbl:>20}")
    print(f"  {'-'*35} {'-'*20} {'-'*20}")
    print(f"  {'Total Net R (sum)':<35} {bb_bl['total_net_r']:>20.4f} {bb_best['total_net_r']:>20.4f}")
    print(f"  {'Net R / active trade':<35} {bb_bl['observed_mean_r']:>20.6f} {bb_best['observed_mean_r']:>20.6f}")
    print(f"  {'Block bootstrap CI':<35} {'':>20} {bb_best['ci_lower_block']:>10.6f}-{bb_best['ci_upper_block']:>9.6f}")
    print(f"  {'Active trades':<35} {bb_bl['n_trades']:>20d} {bb_best['n_trades']:>20d}")
    print(f"  {'Exposure %':<35} {bb_bl['n_trades'] / baseline['total_decisions'] * 100:>19.2f}% {bb_best['n_trades'] / best_res['total_decisions'] * 100:>18.2f}%")

    impr = (bb_best['total_net_r'] - bb_bl['total_net_r']) / abs(bb_bl['total_net_r']) * 100
    print(f"  {'Improvement %':<35} {'':>20} {impr:>19.2f}%")

    print(f"\n{'='*70}")
    print(f"VERDICT")
    print(f"{'='*70}")
    hyp_passed = impr >= 1.0
    if hyp_passed:
        print(f"  HYPOTHESIS: PASS (total net R improved {impr:.2f}% >= 1.0%)")
    else:
        print(f"  HYPOTHESIS: FAIL (total net R improved {impr:.2f}% < 1.0%)")

    print(f"\n  Open question for next iteration:")
    if best_th < 0.55:
        print(f"    Optimal threshold {best_th:.3f} is LOWER than baseline 0.55.")
    else:
        print(f"    Optimal threshold {best_th:.3f} is HIGHER than baseline 0.55.")
    print(f"    Net effect on total net R: {impr:+.2f}%")
    print(f"    Next: position sizing (confidence-based graduated sizing) if total net R improvement < 5%,")
    print(f"    or commit threshold change if improvement >= 5% and acceptable exposure.")


if __name__ == "__main__":
    main()
