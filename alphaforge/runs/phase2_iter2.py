#!/usr/bin/env python3
"""Phase 2 - Iteration 2: Confidence-Based Graduated Position Sizing.

Tek degisken: Position sizing fonksiyonu (confidence -> weight multiplier).
Esik (0.55), model, pipeline, veri: SABIT.
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
    generate_synthetic_ohlcv,
)
from alphaforge.reports.metrics import compute_oos_metrics


def run_pipeline(mode="SCALP", folds=6, seed=42):
    print(f"\n{'='*70}")
    print(f"PHASE 2 - ITERATION 2: Position Sizing")
    print(f"{'='*70}\n")

    ohlcv = generate_synthetic_ohlcv(n_bars=3000, symbols=("BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","ADAUSDT"), random_seed=seed)
    print(f"  {len(ohlcv['close'])} total bars, {len(set(ohlcv['symbol']))} symbols")

    tf = build_aligned_training_frame(ohlcv, mode, feature_groups=None)
    X, y_int = tf["X"], tf["y_int"]
    an_clean_raw = tf["action_net_r"]
    timestamps = tf["timestamps"]
    print(f"  {X.shape[1]} features, {X.shape[0]} aligned rows")

    nan_mask = np.isnan(X).any(axis=1)
    X_clean = X[~nan_mask]
    y_clean = y_int[~nan_mask]
    an_clean = an_clean_raw[~nan_mask]
    ts_clean = timestamps[~nan_mask]
    print(f"  {len(X_clean)} valid samples ({int(nan_mask.sum())} dropped)")

    t0 = time.time()
    results, fold_preds, fold_y_class, fold_y_val = walk_forward_validate(
        X_clean, y_clean, an_clean[:, 1] if an_clean.ndim == 2 and an_clean.shape[1] == 1 else an_clean[:, 0],
        mode, min_folds=folds, action_net_r=an_clean, return_raw_preds=True,
    )
    print(f"  {len(results)} folds in {time.time()-t0:.1f}s")

    n = len(X_clean)
    fold_size = n // (folds + 1)
    purge_bars = fold_size // 4
    embargo_bars = fold_size // 8

    for fi in range(len(results)):
        train_end = (fi + 1) * fold_size
        val_start = train_end
        val_end = val_start + fold_size // 2
        effective_val_start = val_start + embargo_bars
        if effective_val_start >= val_end:
            results[fi]["val_action_net"] = np.empty((0, 3))
        else:
            results[fi]["val_action_net"] = an_clean[effective_val_start:val_end]

    return {
        "wfv_results": results,
        "fold_preds": fold_preds,
        "fold_y_class": fold_y_class,
        "fold_y_val": fold_y_val,
        "timestamps": ts_clean,
        "action_net_r": an_clean,
        "fold_size": fold_size,
        "embargo_bars": embargo_bars,
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
        "total_net_r": observed * n,
        "ci_lower_block": cl,
        "ci_upper_block": cu,
        "ci_lower_naive": nl,
        "ci_upper_naive": nu,
    }


def compute_position_sizing(all_labels_with_conf, all_net_r, all_ts, sizing_func):
    """Apply position sizing to trade R values.

    sizing_func: callable(confidence) -> weight multiplier [0, 1]
    Returns scaled R values (weighted), labels unchanged for count tracking.
    """
    weighted_r = []
    weighted_ts = []
    for (label, conf, ts), r_val in zip(all_labels_with_conf, all_net_r):
        if label != "NO_TRADE":
            weight = sizing_func(conf)
            weighted_r.append(r_val * weight)
            weighted_ts.append(float(ts))
    return np.array(weighted_r), np.array(weighted_ts)


def main():
    print(f"AlphaForge Phase 2 - Iteration 2 @ {datetime.now(timezone.utc).isoformat()}")
    data = run_pipeline(mode="SCALP", folds=6)
    wfv_results = data["wfv_results"]

    # Apply baseline (no sizing: threshold=0.55, weight=1.0 for all trades)
    # Collect per-trade data from baseline threshold
    threshold = 0.55
    all_labels_conf = []  # (label, confidence, timestamp)
    all_net_r = []

    for fi in range(len(wfv_results)):
        preds = data["fold_preds"][fi]
        y_pred_raw = data["fold_y_class"][fi]
        y_pred = y_pred_raw.copy()
        y_pred[preds < threshold] = 2
        labels = np.array(["LONG_NOW" if p == 0 else "SHORT_NOW" if p == 1 else "NO_TRADE" for p in y_pred], dtype=object)
        action_vals = wfv_results[fi]["val_action_net"]
        trade_r = action_vals[np.arange(len(y_pred)), y_pred]

        train_end = (fi + 1) * data["fold_size"]
        val_start = train_end
        val_end = val_start + data["fold_size"] // 2
        effective_val_start = val_start + data["embargo_bars"]
        fold_ts = data["timestamps"][effective_val_start:val_end]

        for j, (lbl, r_val, conf, ts) in enumerate(zip(labels, trade_r, preds, fold_ts)):
            all_labels_conf.append((lbl, float(conf), float(ts)))
            all_net_r.append(float(r_val))

    # Baseline: no sizing (weight=1.0 for all trades)
    base_r = [r for (l, c, t), r in zip(all_labels_conf, all_net_r) if l != "NO_TRADE"]
    base_ts = [t for (l, c, t), r in zip(all_labels_conf, all_net_r) if l != "NO_TRADE"]
    base_r_arr = np.array(base_r)
    base_ts_arr = np.array(base_ts)
    base_total = float(base_r_arr.sum())

    print(f"\n{'='*70}")
    print(f"POSITION SIZING CONFIGURATIONS")
    print(f"{'='*70}")
    print(f"  Threshold (fixed): {threshold}")
    print(f"  Baseline trades: {len(base_r_arr)}, total net R: {base_total:.4f}")
    print(f"  Baseline mean R/trade: {base_r_arr.mean():.6f}")

    # Define sizing functions to test
    # Each is callable(confidence) -> weight
    sizing_schemes = {
        "no_sizing": lambda c: 1.0,
        "linear_055_10": lambda c: 0.0 if c < 0.55 else (c - 0.55) / 0.45 * 1.0,  # 0.55->0, 1.0->1.0
        "linear_030_10": lambda c: max(0, (c - 0.30) / 0.70),  # 0.30->0, 1.0->1.0
        "linear_040_10": lambda c: max(0, (c - 0.40) / 0.60),  # 0.40->0, 1.0->1.0
        "linear_050_10": lambda c: max(0, (c - 0.50) / 0.50),  # 0.50->0, 1.0->1.0
        "capped_at_08": lambda c: min(1.0, (c - 0.30) / 0.60 * 0.8 + 0.2),  # 0.30->0.2, 1.0->0.8
        "sqrt": lambda c: max(0, ((c - 0.30) / 0.70) ** 0.5),  # sqrt scaling
        "square": lambda c: max(0, ((c - 0.30) / 0.70) ** 2),  # aggressive: only high conf gets weight
        "step_at_07": lambda c: 1.0 if c >= 0.70 else (0.5 if c >= 0.55 else 0.0),  # step function
        "step_at_08": lambda c: 1.0 if c >= 0.80 else (0.5 if c >= 0.55 else 0.0),  # stricter step
    }

    results = {}
    for name, sizing_fn in sizing_schemes.items():
        weighted_r, weighted_ts = compute_position_sizing(all_labels_conf, all_net_r, base_ts_arr, sizing_fn)
        total_weighted = float(weighted_r.sum()) if len(weighted_r) > 0 else 0.0
        avg_weighted = float(weighted_r.mean()) if len(weighted_r) > 0 else 0.0
        n_active = len(weighted_r)
        improvement = (total_weighted - base_total) / abs(base_total) * 100 if abs(base_total) > 1e-12 else 0.0

        results[name] = {
            "total_net_R": total_weighted,
            "avg_net_R_per_trade": avg_weighted,
            "active_trades": n_active,
            "improvement_pct": improvement,
        }

        # Block bootstrap if improvement > 0
        if improvement > 0 and n_active >= 20:
            bb = block_bootstrap_ci(weighted_r, weighted_ts, block_size=48)
            results[name]["bb_ci_lower"] = bb["ci_lower_block"]
            results[name]["bb_ci_upper"] = bb["ci_upper_block"]
        else:
            results[name]["bb_ci_lower"] = None
            results[name]["bb_ci_upper"] = None

    # Print results table sorted by total_net_R
    print(f"\n  {'Sizing Scheme':<20} | {'Tot NetR':>10} | {'Avg NetR':>10} | {'Active':>7} | {'Improv':>8} | {'BB CI 95%'}")
    print(f"  {'-'*20}-+-{'-'*10}-+-{'-'*10}-+-{'-'*7}-+-{'-'*8}-+-{'-----------'}")
    base_label = "no_sizing"
    for name in sorted(results, key=lambda n: results[n]["total_net_R"], reverse=True):
        r = results[name]
        marker = " <--" if name == base_label else ""
        ci_str = f"[{r['bb_ci_lower']:.4f}, {r['bb_ci_upper']:.4f}]" if r['bb_ci_lower'] is not None else "N/A"
        print(f"  {name:<20} | {r['total_net_R']:>10.4f} | {r['avg_net_R_per_trade']:>10.6f} | {r['active_trades']:>7d} | {r['improvement_pct']:>+7.2f}% | {ci_str}{marker}")

    # Find best
    best = max(results, key=lambda n: results[n]["total_net_R"])
    best_r = results[best]
    print(f"\n{'='*70}")
    print(f"BEST SIZING: {best}")
    print(f"  Total Net R:  {best_r['total_net_R']:.4f} (vs baseline {base_total:.4f})")
    print(f"  Improvement:  {best_r['improvement_pct']:+.2f}%")
    print(f"  Active trades:{best_r['active_trades']}")
    if best_r['bb_ci_lower'] is not None:
        print(f"  BB CI 95%:    [{best_r['bb_ci_lower']:.6f}, {best_r['bb_ci_upper']:.6f}]")

    print(f"\n{'='*70}")
    print(f"VERDICT")
    print(f"{'='*70}")
    hyp_passed = best_r['improvement_pct'] >= 5.0
    if hyp_passed:
        print(f"  HYPOTHESIS: PASS (best sizing improves total net R by {best_r['improvement_pct']:.2f}% >= 5.0%)")
    else:
        print(f"  HYPOTHESIS: FAIL (best sizing improves total net R by {best_r['improvement_pct']:.2f}% < 5.0%)")

    print(f"\n  Open question for next iteration:")
    if hyp_passed:
        print(f"    Sizing '{best}' is viable. Next: combine optimal threshold + sizing")
    else:
        print(f"    Position sizing alone cannot reach 5% improvement.")
        print(f"    Next: feature set fine-tuning (existing 10 features interaction analysis)")


if __name__ == "__main__":
    main()
