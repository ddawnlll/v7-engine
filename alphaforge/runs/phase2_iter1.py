#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════╗
# ║  DEPRECATED: Sentetik veri kullanir.                      ║
# ║  Gercek veri icin scripts/phase_reality_complete.py       ║
# ║  veya scripts/candidate_v031e_verified.py kullanin.       ║
# ╚══════════════════════════════════════════════════════════════╝

"""Phase 2 - Iteration 1: Confidence Threshold Optimization on Validation Set.

Tek degisken: CONFIDENCE_THRESHOLD.
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
    collect_metrics,
    MODE_CONFIG,
    CONFIDENCE_THRESHOLD,
    generate_synthetic_ohlcv,
)
from alphaforge.reports.metrics import compute_oos_metrics


def run_pipeline(mode="SCALP", folds=6):
    """Run pipeline and return wfv_results + raw predictions."""
    print(f"\n{'='*70}")
    print(f"PHASE 2 - ITERATION 1: Confidence Threshold Sweep")
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


def threshold_sweep(fold_preds, fold_y_class, fold_y_val, action_net_r_parts, results):
    """Post-hoc threshold sweep on validation fold data."""
    # Reconstruct per-fold action_net_r slices by re-deriving fold boundaries
    from alphaforge.train import _compute_stability, compute_overfit_gap, compute_inter_fold_consistency as _cifc

    thresholds = np.arange(0.30, 0.96, 0.025)
    baseline_threshold = 0.55

    print(f"\n{'='*70}")
    print(f"THRESHOLD SWEEP on VALIDATION folds (threshold candidate -> net R)")
    print(f"{'='*70}")
    print(f"  Sweep range: {thresholds[0]:.3f} to {thresholds[-1]:.3f}, step={thresholds[1]-thresholds[0]:.3f}")
    print(f"  Baseline: threshold = {baseline_threshold}")

    # We need val_action_net slices for each fold
    # Reconstruct from fold boundaries used in walk_forward_validate
    # Since we can't easily extract per-fold slices post-hoc from the aggregate,
    # we use the per-fold saved results and compute metrics for each threshold
    # by using the saved pred probabilities.

    # For each fold, val_action_net was action_net_r[effective_val_start:val_end]
    # We have the y_pred (before threshold) and the fold_y_val (true labels)
    # We need the action_net_r values. Let's get them from fold predictions:

    # Since walk_forward_validate saved preds before threshold and the
    # results already have the per-fold action_net slices in pred_gross_r,
    # let's do a simpler approach: for each threshold, re-evaluate all folds.

    n_folds = len(results)
    print(f"\n  Sweeping across {n_folds} validation folds...")

    results_by_threshold = {}
    for th in thresholds:
        fold_net_r_vals = []
        all_labels = []
        all_r = []
        for fi in range(n_folds):
            preds = fold_preds[fi]  # max softmax prob per sample (before threshold)
            y_pred_raw = fold_y_class[fi]  # argmax class (before threshold)
            y_val = fold_y_val[fi]

            # Apply threshold
            y_pred = y_pred_raw.copy()
            y_pred[preds < th] = 2  # NO_TRADE

            labels = np.array(["LONG_NOW" if p == 0 else "SHORT_NOW" if p == 1 else "NO_TRADE" for p in y_pred], dtype=object)
            action_vals = results[fi]["val_action_net"] if "val_action_net" in results[fi] else None

            if action_vals is None:
                continue

            trade_r = action_vals[np.arange(len(y_pred)), y_pred]
            metrics = compute_oos_metrics(labels.tolist(), trade_r.tolist(), fee_pct=0.0)
            fold_net_r_vals.append(metrics["avg_net_R_per_active_trade"])
            all_labels.extend(labels.tolist())
            all_r.extend(trade_r.tolist())

        if not fold_net_r_vals:
            continue

        avg_net_r = float(np.mean(fold_net_r_vals))
        total_net = float(np.sum(all_r))
        active = sum(1 for l in all_labels if l != "NO_TRADE")
        total_decisions = len(all_labels)

        results_by_threshold[round(float(th), 6)] = {
            "avg_net_R_per_active_trade": round(avg_net_r, 6),
            "total_net_R": round(total_net, 6),
            "active_trades": active,
            "total_decisions": total_decisions,
            "exposure_pct": round(active / total_decisions * 100, 2) if total_decisions > 0 else 0.0,
            "fold_net_r_vals": [round(v, 6) for v in fold_net_r_vals],
        }

    # Print sweep table
    print(f"\n  {'Threshold':>10} | {'NetR/trade':>11} | {'Tot NetR':>10} | {'NetR/dec':>10} | {'Active':>7} | {'Exposure':>9} | {'Fold net R vals'}")
    print(f"  {'-'*10}-+-{'-'*11}-+-{'-'*10}-+-{'-'*10}-+-{'-'*7}-+-{'-'*9}-+-{'fold_vals'}")
    for th, res in sorted(results_by_threshold.items()):
        marker = " <--" if abs(th - baseline_threshold) < 0.001 else ""
        fold_str = ", ".join(f"{v:.4f}" for v in res["fold_net_r_vals"])
        nr_per_dec = round(res["total_net_R"] / res["total_decisions"], 6) if res["total_decisions"] > 0 else 0.0
        print(f"  {th:>10.3f} | {res['avg_net_R_per_active_trade']:>11.6f} | {res['total_net_R']:>10.4f} | {nr_per_dec:>10.6f} | {res['active_trades']:>7d} | {res['exposure_pct']:>8.2f}% | {fold_str}{marker}")

    return results_by_threshold


def block_bootstrap_ci(trade_r, timestamps, block_size=48, n_resamples=10000, seed=42):
    """Compute block bootstrap CI for a single trade R series."""
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

    # Block bootstrap
    bm = np.zeros(n_resamples)
    for i in range(n_resamples):
        idx = rng.choice(n_non, size=n_non, replace=True)
        bm[i] = np.concatenate([bg_ne[j] for j in idx]).mean()
    bm.sort()
    cl, cu = float(bm[int(n_resamples * 0.025)]), float(bm[int(n_resamples * 0.975)])

    # Naive iid bootstrap
    nm = np.zeros(n_resamples)
    for i in range(n_resamples):
        nm[i] = rng.choice(trade_r_sorted, size=n, replace=True).mean()
    nm.sort()
    nl, nu = float(nm[int(n_resamples * 0.025)]), float(nm[int(n_resamples * 0.975)])

    return {
        "observed_mean_r": observed,
        "n_trades": n,
        "n_blocks": n_non,
        "ci_lower_block": cl,
        "ci_upper_block": cu,
        "ci_lower_naive": nl,
        "ci_upper_naive": nu,
    }


def compute_block_bootstrap_for_threshold(results_by_threshold, wfv_results):
    """Get best threshold and compute block bootstrap CI."""
    # Find best threshold
    best_th = max(results_by_threshold, key=lambda t: results_by_threshold[t]["avg_net_R_per_active_trade"])
    best_r = results_by_threshold[best_th]["avg_net_R_per_active_trade"]
    baseline = results_by_threshold.get(round(0.55, 6), {})
    baseline_r = baseline.get("avg_net_R_per_active_trade", 0.0)

    print(f"\n{'='*70}")
    print(f"BEST THRESHOLD: {best_th:.3f} (net R = {best_r:.6f})")
    print(f"BASELINE (0.55): net R = {baseline_r:.6f}")
    print(f"IMPROVEMENT: {((best_r - baseline_r) / abs(baseline_r) * 100) if abs(baseline_r) > 1e-12 else 0:.2f}%")

    return best_th, best_r


def main():
    print(f"AlphaForge Phase 2 - Iteration 1 @ {datetime.now(timezone.utc).isoformat()}")

    data = run_pipeline(mode="SCALP", folds=6)

    # Extract per-fold action_net_r for the threshold sweep
    wfv_results = data["wfv_results"]

    # Add val_action_net to each result for the sweep (reconstruct from fold slices)
    # Each fold's val_action_net was: action_net_r[effective_val_start:val_end]
    # We derive the indices from the saved results
    # The results contain n_train, n_val, purge_period, embargo_period
    # effective_train_end = train_end - purge_bars
    # effective_val_start = val_start + embargo_bars
    # train_end = (fold+1) * fold_size
    # val_start = train_end
    # val_end = val_start + fold_size // 2

    n = len(data["X_clean"])
    fold_size = n // (6 + 1)
    purge_bars = fold_size // 4
    embargo_bars = fold_size // 8
    all_an = data["action_net_r"]

    for fi in range(len(wfv_results)):
        train_end = (fi + 1) * fold_size
        val_start = train_end
        val_end = val_start + fold_size // 2
        effective_val_start = val_start + embargo_bars
        if effective_val_start >= val_end:
            wfv_results[fi]["val_action_net"] = np.empty((0, 3))
        else:
            wfv_results[fi]["val_action_net"] = all_an[effective_val_start:val_end]

    sweep_results = threshold_sweep(
        data["fold_preds"], data["fold_y_class"], data["fold_y_val"], all_an, wfv_results
    )

    best_th, best_r = compute_block_bootstrap_for_threshold(sweep_results, wfv_results)

    # Get timestamps for best threshold trades for block bootstrap
    # Re-run with best threshold to get the trade R series with timestamps
    print(f"\n{'='*70}")
    print(f"BLOCK BOOTSTRAP for BEST threshold = {best_th:.3f}")
    print(f"{'='*70}")

    all_labels_th = []
    all_r_th = []
    all_ts_th = []
    for fi in range(len(wfv_results)):
        preds = data["fold_preds"][fi]
        y_pred_raw = data["fold_y_class"][fi]
        y_pred = y_pred_raw.copy()
        y_pred[preds < best_th] = 2
        labels = np.array(["LONG_NOW" if p == 0 else "SHORT_NOW" if p == 1 else "NO_TRADE" for p in y_pred], dtype=object)
        action_vals = wfv_results[fi]["val_action_net"]
        trade_r = action_vals[np.arange(len(y_pred)), y_pred]

        # Timestamps for this fold's val slice
        train_end = (fi + 1) * fold_size
        val_start = train_end
        val_end = val_start + fold_size // 2
        effective_val_start = val_start + embargo_bars
        fold_ts = data["timestamps"][effective_val_start:val_end]

        for lbl, r_val, ts in zip(labels, trade_r, fold_ts):
            if lbl != "NO_TRADE":
                all_labels_th.append(lbl)
                all_r_th.append(r_val)
                all_ts_th.append(float(ts))

    tr = np.array(all_r_th)
    tt = np.array(all_ts_th)
    print(f"  Active trades: {len(tr)}, mean R = {tr.mean():.6f}, std = {tr.std():.6f}")

    bb = block_bootstrap_ci(tr, tt, block_size=48)
    print(f"\n  Block bootstrap ({10000} resamples):")
    print(f"    Observed mean:        {bb['observed_mean_r']:.6f}")
    print(f"    95% CI (block):       [{bb['ci_lower_block']:.6f}, {bb['ci_upper_block']:.6f}]")
    print(f"    95% CI (naive iid):   [{bb['ci_lower_naive']:.6f}, {bb['ci_upper_naive']:.6f}]")

    # Also compute for baseline for comparison
    print(f"\n{'='*70}")
    print(f"BLOCK BOOTSTRAP for BASELINE threshold = 0.55")
    print(f"{'='*70}")
    bl_labels, bl_r, bl_ts = [], [], []
    for fi in range(len(wfv_results)):
        preds = data["fold_preds"][fi]
        y_pred_raw = data["fold_y_class"][fi]
        y_pred = y_pred_raw.copy()
        y_pred[preds < 0.55] = 2
        labels = np.array(["LONG_NOW" if p == 0 else "SHORT_NOW" if p == 1 else "NO_TRADE" for p in y_pred], dtype=object)
        action_vals = wfv_results[fi]["val_action_net"]
        trade_r = action_vals[np.arange(len(y_pred)), y_pred]

        train_end = (fi + 1) * fold_size
        val_start = train_end
        val_end = val_start + fold_size // 2
        effective_val_start = val_start + embargo_bars
        fold_ts = data["timestamps"][effective_val_start:val_end]

        for lbl, r_val, ts in zip(labels, trade_r, fold_ts):
            if lbl != "NO_TRADE":
                bl_labels.append(lbl)
                bl_r.append(r_val)
                bl_ts.append(float(ts))

    bl_tr = np.array(bl_r)
    bl_tt = np.array(bl_ts)
    print(f"  Active trades: {len(bl_tr)}, mean R = {bl_tr.mean():.6f}, std = {bl_tr.std():.6f}")
    bl_bb = block_bootstrap_ci(bl_tr, bl_tt, block_size=48)
    print(f"\n  Block bootstrap ({10000} resamples):")
    print(f"    Observed mean:        {bl_bb['observed_mean_r']:.6f}")
    print(f"    95% CI (block):       [{bl_bb['ci_lower_block']:.6f}, {bl_bb['ci_upper_block']:.6f}]")
    print(f"    95% CI (naive iid):   [{bl_bb['ci_lower_naive']:.6f}, {bl_bb['ci_upper_naive']:.6f}]")

    # Compute total net R values
    bl_total_net = bl_bb['observed_mean_r'] * len(bl_tr)
    best_total_net = bb['observed_mean_r'] * len(tr)
    bl_total_decisions = sum(len(r.get("decision_labels", [])) for r in wfv_results)
    best_total_decisions = bl_total_decisions  # same total decisions, just different threshold

    print(f"\n{'='*70}")
    print(f"COMPARISON")
    print(f"{'='*70}")
    best_label = "Best ({:.3f})".format(best_th)
    print(f"  {'Metric':<30} {'Baseline (0.55)':>18} {best_label:>20}")
    print(f"  {'-'*30} {'-'*18} {'-'*20}")
    print(f"  {'Net R / active trade':<30} {bl_bb['observed_mean_r']:>18.6f} {bb['observed_mean_r']:>20.6f}")
    print(f"  {'Block bootstrap CI':<30} {'':>18} {bb['ci_lower_block']:>10.6f}-{bb['ci_upper_block']:>9.6f}")
    print(f"  {'Total Net R (sum)':<30} {bl_total_net:>18.4f} {best_total_net:>20.4f}")
    print(f"  {'Net R per decision':<30} {bl_total_net / bl_total_decisions:>18.6f} {best_total_net / best_total_decisions:>20.6f}")
    print(f"  {'Active trades':<30} {len(bl_tr):>18d} {len(tr):>20d}")
    print(f"  {'Exposure %':<30} {len(bl_tr) / bl_total_decisions * 100:>17.2f}% {len(tr) / best_total_decisions * 100:>18.2f}%")
    change_val = (bb['observed_mean_r'] - bl_bb['observed_mean_r']) / abs(bl_bb['observed_mean_r']) * 100
    print(f"  {'Change (%)':<30} {'':>18} {change_val:>18.2f}%")

    print(f"\n{'='*70}")
    print(f"VERDICT")
    print(f"{'='*70}")
    improvement = change_val
    hyp_passed = improvement >= 5.0
    if hyp_passed:
        print(f"  HYPOTHESIS: PASS (improvement {improvement:.2f}% >= 5.0%)")
    else:
        print(f"  HYPOTHESIS: FAIL (improvement {improvement:.2f}% < 5.0%)")

    print(f"\n  Open question for next iteration:")
    if hyp_passed:
        print(f"    Confidence threshold {best_th:.3f} improves net R by {improvement:.2f}%.")
        print(f"    Next: position sizing (confidence-based graduated sizing)")
    else:
        print(f"    Threshold optimization did not reach 5% improvement target.")
        print(f"    Next: position sizing as alternative lever")


if __name__ == "__main__":
    main()
