#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════╗
# ║  DEPRECATED: Sentetik veri kullanir.                      ║
# ║  Gercek veri icin scripts/phase_reality_complete.py       ║
# ║  veya scripts/candidate_v031e_verified.py kullanin.       ║
# ╚══════════════════════════════════════════════════════════════╝

"""
Phase 3 — Final Feature Set: Threshold Re-optimization on Pruned 32-Feature Set

ADIM 1: Iteration 2v2 (threshold=0.715) was produced with 54 raw features,
         NOT the pruned 32-feature set. The ablation improved val composite
         from 530.41 → 544.92 at th=0.715, but the threshold was not
         re-optimized for the pruned set. This script fixes that.

Method:
  1. Build training frame with ALL 54 features (same pipeline as Iteration 2v2)
  2. Select only the 32 kept feature columns (from ablation results)
  3. Walk-forward validation on 6 folds
  4. Grid search thresholds on val folds 0-4 (composite = total_net_R / max_drawdown)
  5. Evaluate best threshold on test fold 5
  6. Block-bootstrap 95% CI on test
  7. Compare: 54-feat@0.715 vs 32-feat@0.715 vs 32-feat@new_threshold

TEST/OOS KURALI: Test set ONLY touched ONCE at the end.
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

from alphaforge.train import build_aligned_training_frame, generate_synthetic_ohlcv, walk_forward_validate
from alphaforge.reports.metrics import compute_oos_metrics

# ─── 32 kept feature indices from ablation results ──────────────────────
KEPT_INDICES = [1, 2, 3, 4, 5, 8, 9, 11, 15, 17, 19, 24, 25, 27, 28, 29,
                30, 32, 33, 36, 37, 39, 41, 42, 43, 44, 45, 47, 49, 50, 52, 53]


def compute_equity_curve(trade_r, timestamps):
    """Compute equity curve and max drawdown from chronologically sorted trades."""
    order = np.argsort(timestamps)
    sorted_r = np.array(trade_r)[order]
    equity = np.cumsum(sorted_r)
    peak = np.maximum.accumulate(equity)
    drawdown = peak - equity
    max_dd = float(drawdown.max()) if len(drawdown) > 0 else 0.0
    return equity, max_dd


def block_bootstrap_ci(trade_r, timestamps, block_size=48, n_resamples=10000, seed=42):
    """Block bootstrap CI for mean R."""
    rng = np.random.RandomState(seed)
    order = np.argsort(timestamps)
    trade_r_sorted = trade_r[order]
    n = len(trade_r_sorted)
    if n < 10:
        return {"observed_mean_r": float(trade_r.mean()) if n > 0 else 0.0,
                "n_trades": n, "n_blocks": 0, "total_net_r": float(trade_r.sum()) if n > 0 else 0.0,
                "ci_lower_block": None, "ci_upper_block": None}
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

    return {"observed_mean_r": observed, "n_trades": n, "n_blocks": n_non,
            "total_net_r": observed * n,
            "ci_lower_block": cl, "ci_upper_block": cu}


def main():
    print(f"AlphaForge Phase 3 — Final Feature Set @ {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*70}")
    print(f"Threshold re-optimization on 32-feature pruned set")
    print(f"{'='*70}")

    mode = "SCALP"
    n_folds = 6
    threshold_old = 0.715

    # ─── Load data (same as feature_ablation.py) ────────────────────────
    ohlcv = generate_synthetic_ohlcv(
        n_bars=3000,
        symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"),
        random_seed=42,
    )
    tf = build_aligned_training_frame(ohlcv, mode, feature_groups=None)
    X, y_int = tf["X"], tf["y_int"]
    an_raw = tf["action_net_r"]
    timestamps = tf["timestamps"]
    feat_names_full = list(tf["feature_names"])

    # Clean NaN
    nan_mask = np.isnan(X).any(axis=1)
    X_clean = X[~nan_mask]
    y_clean = y_int[~nan_mask]
    an_clean = an_raw[~nan_mask]
    ts_clean = timestamps[~nan_mask]

    # ─── Select 32 features ─────────────────────────────────────────────
    X_32 = X_clean[:, KEPT_INDICES]
    feat_names_32 = [feat_names_full[i] for i in KEPT_INDICES]
    print(f"\n  Full features: {X_clean.shape[1]}, Pruned features: {X_32.shape[1]}")
    print(f"  Valid samples: {X_32.shape[0]}")

    n = len(X_32)
    fold_size = n // (n_folds + 1)
    embargo = fold_size // 8

    # ─── Walk-forward validation with raw preds ─────────────────────────
    print(f"\n  Running {n_folds}-fold WFV on 32 features...")
    t0 = time.time()
    results, fold_preds, fold_y_class, fold_y_val = walk_forward_validate(
        X_32, y_clean, an_clean[:, 0], mode, min_folds=n_folds,
        action_net_r=an_clean, return_raw_preds=True,
    )
    print(f"  {len(results)} folds in {time.time() - t0:.1f}s")

    # Reconstruct per-fold val slices for action_net_r
    for fi in range(n_folds):
        train_end = (fi + 1) * fold_size
        vs = train_end
        ve = vs + fold_size // 2
        evs = vs + embargo
        results[fi]["val_action_net"] = an_clean[evs:ve] if evs < ve else np.empty((0, 3))
        results[fi]["val_timestamps"] = ts_clean[evs:ve] if evs < ve else np.empty(0)

    grid_folds = [0, 1, 2, 3, 4]
    test_fold = 5

    # ─── Grid thresholds (same grid as Iteration 2v2) ───────────────────
    center = 0.55
    grid = sorted(set([
        center,
        round(center * 0.7, 3), round(center * 0.8, 3), round(center * 0.9, 3),
        round(center * 1.1, 3), round(center * 1.2, 3), round(center * 1.3, 3),
    ]))
    grid = [max(0.0, min(1.0, t)) for t in grid]

    print(f"\n  Grid (val'de taranacak): {[f'{t:.3f}' for t in grid]}")

    # ─── Also evaluate the OLD threshold=0.715 on the 32-feat model ─────
    # This shows what the ablation result was (at old threshold)
    # ─── Grid evaluation on val folds ───────────────────────────────────
    print(f"\n{'='*70}")
    print(f"GRID — 32 FEATURE (validation folds 1-5)")
    print(f"{'='*70}")
    print(f"  {'Threshold':>10} | {'Tot NetR':>10} | {'Max DD':>10} | {'Kompozit':>10} | {'Trade#':>7} | {'Exposure':>9}")
    print(f"  {'-'*10}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}-+-{'-'*7}-+-{'-'*9}")

    # Also compute for old threshold separately (always include)
    old_th = 0.715
    if old_th not in grid:
        grid.append(old_th)
        grid.sort()

    grid_results = {}
    old_32_results = None

    for th in grid:
        total_net = 0.0
        all_trade_r = []
        all_trade_ts = []
        all_decisions = 0

        for fi in grid_folds:
            preds = fold_preds[fi]
            y_raw = fold_y_class[fi]
            y_pred = y_raw.copy()
            y_pred[preds < th] = 2

            labels = np.array(["LONG_NOW" if p == 0 else "SHORT_NOW" if p == 1 else "NO_TRADE" for p in y_pred], dtype=object)
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

        tr_arr = np.array(all_trade_r)
        tt_arr = np.array(all_trade_ts)
        _, max_dd = compute_equity_curve(tr_arr, tt_arr)
        composite = total_net / max_dd if max_dd > 1e-12 else 999.0
        n_trades = len(tr_arr)
        exposure = n_trades / all_decisions * 100 if all_decisions > 0 else 0.0

        grid_results[th] = {
            "total_net_R": total_net, "max_dd": max_dd, "composite": composite,
            "n_trades": n_trades, "exposure": exposure,
        }

        marker = ""
        if abs(th - old_th) < 1e-6:
            marker = " <-- OLD THRESHOLD (0.715)"
            old_32_results = grid_results[th]

        print(f"  {th:>10.3f} | {total_net:>10.4f} | {max_dd:>10.4f} | {composite:>10.2f} | {n_trades:>7d} | {exposure:>8.2f}%{marker}")

    # Select best threshold
    best_th = max(grid_results, key=lambda t: grid_results[t]["composite"])
    best_val = grid_results[best_th]
    print(f"\n  >>> SECILEN THRESHOLD (32-feat): {best_th:.3f} (kompozit={best_val['composite']:.2f})")
    print(f"  >>> OLD THRESHOLD @ 0.715 (32-feat): kompozit={old_32_results['composite']:.2f}")

    # ─── TEST: evaluate selected threshold on fold 5 (OOS) ──────────────
    print(f"\n{'='*70}")
    print(f"TEST/OOS: fold {test_fold + 1} — selected threshold vs old threshold")
    print(f"{'='*70}")

    def eval_test(fi, th_use, label):
        preds = fold_preds[fi]
        y_raw = fold_y_class[fi]
        y_pred = y_raw.copy()
        y_pred[preds < th_use] = 2

        labels = np.array(["LONG_NOW" if p == 0 else "SHORT_NOW" if p == 1 else "NO_TRADE" for p in y_pred], dtype=object)
        av = results[fi]["val_action_net"]
        trade_r = av[np.arange(len(y_pred)), y_pred]
        fold_ts = results[fi]["val_timestamps"]

        metrics = compute_oos_metrics(labels.tolist(), trade_r.tolist(), fee_pct=0.0)

        all_r = [float(rv) for lbl, rv in zip(labels, trade_r) if lbl != "NO_TRADE"]
        all_ts = [float(ts) for lbl, rv, ts in zip(labels, trade_r, fold_ts) if lbl != "NO_TRADE"]
        tr_arr = np.array(all_r)
        tt_arr = np.array(all_ts)
        _, max_dd = compute_equity_curve(tr_arr, tt_arr)
        composite = metrics["total_net_R"] / max_dd if max_dd > 1e-12 else 999.0

        bb = block_bootstrap_ci(tr_arr, tt_arr, block_size=24)

        print(f"\n  {label}:")
        print(f"  Threshold:       {th_use:.3f}")
        print(f"  Total Net R:     {metrics['total_net_R']:.6f}")
        print(f"  Max DD:          {max_dd:.6f}")
        print(f"  Kompozit:        {composite:.2f}")
        print(f"  Active trades:   {metrics['active_trade_count']} (L:{metrics['long_trade_count']}, S:{metrics['short_trade_count']}, NT:{metrics['no_trade_count']})")
        print(f"  Exposure:        {metrics['exposure_pct']:.2f}%")
        if bb['ci_lower_block'] is not None:
            print(f"  BB 95% CI:       [{bb['ci_lower_block']:.6f}, {bb['ci_upper_block']:.6f}]")

        return {
            "threshold": th_use,
            "total_net_R": metrics["total_net_R"],
            "max_dd": max_dd,
            "composite": composite,
            "active_trades": metrics["active_trade_count"],
            "long_count": metrics["long_trade_count"],
            "short_count": metrics["short_trade_count"],
            "no_trade_count": metrics["no_trade_count"],
            "exposure_pct": metrics["exposure_pct"],
            "ci_lower": bb["ci_lower_block"],
            "ci_upper": bb["ci_upper_block"],
            "n_trades": bb["n_trades"],
            "n_blocks": bb["n_blocks"],
            "observed_mean_r": bb["observed_mean_r"],
        }

    result_best = eval_test(test_fold, best_th, f"SECILEN ({best_th:.3f})")
    result_old = eval_test(test_fold, old_th, f"ESKI TH=0.715 (referans)")

    # ─── Comparison with 54-feature results ────────────────────────────
    # Values from feature_ablation_results.json / phase2_iter2_v2 output
    ab_54_result = {"composite": 216.51, "total_net_R": 10.6440, "max_dd": 0.0492}
    ab_32_result = {"composite": 223.02, "total_net_R": 10.9608, "max_dd": 0.0491}

    print(f"\n{'='*70}")
    print(f"KARSILASTIRMA TABLOSU")
    print(f"{'='*70}")
    print(f"  {'Konfigurasyon':<40} {'Kompozit':>10} {'NetR':>10} {'MaxDD':>8} {'Trade#':>7}")
    print(f"  {'-'*40} {'-'*10} {'-'*10} {'-'*8} {'-'*7}")
    print(f"  {'54-feat @ 0.715 (Iter2v2)':<40} {ab_54_result['composite']:>10.2f} {ab_54_result['total_net_R']:>10.4f} {ab_54_result['max_dd']:>8.4f} {'?':>7}")
    print(f"  {'32-feat @ 0.715 (ablation)':<40} {ab_32_result['composite']:>10.2f} {ab_32_result['total_net_R']:>10.4f} {ab_32_result['max_dd']:>8.4f} {'?':>7}")
    print(f"  {'32-feat @ 0.715 (this run)':<40} {result_old['composite']:>10.2f} {result_old['total_net_R']:>10.4f} {result_old['max_dd']:>8.4f} {result_old['active_trades']:>7d}")
    print(f"  {'32-feat @ BEST (this run)':<40} {result_best['composite']:>10.2f} {result_best['total_net_R']:>10.4f} {result_best['max_dd']:>8.4f} {result_best['active_trades']:>7d}")

    # ─── KARAR ──────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"KARAR")
    print(f"{'='*70}")

    ci_pos = result_best["ci_lower"] is not None and result_best["ci_lower"] > 0
    net_pos = result_best["total_net_R"] > 0
    pass_condition = ci_pos and net_pos

    print(f"  total_net_R > 0: {'YES' if net_pos else 'NO'} ({result_best['total_net_R']:.6f})")
    if result_best["ci_lower"] is not None:
        print(f"  CI fully positive: {'YES' if ci_pos else 'NO'} ([{result_best['ci_lower']:.6f}, {result_best['ci_upper']:.6f}])")
    else:
        print(f"  CI fully positive: N/A")

    impr_vs_54 = (result_best["composite"] - ab_54_result["composite"]) / ab_54_result["composite"] * 100
    impr_vs_32_old = (result_best["composite"] - result_old["composite"]) / result_old["composite"] * 100 if result_old["composite"] > 0 else 0

    print(f"  vs 54-feat@0.715: {impr_vs_54:+.2f}%")
    print(f"  vs 32-feat@0.715: {impr_vs_32_old:+.2f}%")

    if pass_condition:
        print(f"\n  >>> KARAR: PASS (total_net_R pozitif, CI tamamen pozitif)")
    else:
        print(f"\n  >>> KARAR: FAIL")

    # ─── OZET ───────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"OZET")
    print(f"{'='*70}")
    print(f"ITERASYON: Phase 3 — Final Feature Set")
    print(f"FEATURE SET: 32 (pruned from 54 via DoubleEnsemble shuffle ablation)")
    print(f"BEST THRESHOLD: {best_th:.3f}")
    print(f"  val kompozit={best_val['composite']:.2f}")
    print(f"TEST/OOS sonucu ({best_th:.3f}):")
    r = result_best
    print(f"  total_net_R={r['total_net_R']:.6f}, trade_count={r['active_trades']}")
    print(f"  max_dd={r['max_dd']:.6f}, kompozit={r['composite']:.2f}")
    if r['ci_lower'] is not None:
        print(f"  block-bootstrap 95% CI=[{r['ci_lower']:.6f}, {r['ci_upper']:.6f}]")
    print(f"KARAR: {'PASS' if pass_condition else 'FAIL'}")

    # ─── Save results ───────────────────────────────────────────────────
    out = {
        "phase": "Phase3_FinalFeatureSet",
        "mode": mode,
        "n_features_full": 54,
        "n_features_pruned": 32,
        "kept_indices": KEPT_INDICES,
        "grid": {
            "center": center,
            "values": grid,
            "results": grid_results,
        },
        "val_best": {
            "threshold": best_th,
            "composite": best_val["composite"],
            "total_net_R": best_val["total_net_R"],
            "max_dd": best_val["max_dd"],
            "n_trades": best_val["n_trades"],
        },
        "val_at_old_threshold_715": {
            "composite": old_32_results["composite"],
            "total_net_R": old_32_results["total_net_R"],
            "max_dd": old_32_results["max_dd"],
        },
        "test_best": result_best,
        "test_at_old_threshold": result_old,
        "comparison": {
            "54feat_0715_composite": ab_54_result["composite"],
            "32feat_0715_composite_ablation": ab_32_result["composite"],
            "32feat_0715_composite_this_run": result_old["composite"],
            "32feat_best_composite_this_run": result_best["composite"],
        },
        "decision": "PASS" if pass_condition else "FAIL",
    }

    out_path = _REPO_ROOT / "reports" / "phase3_feature_set_final.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nSonuclar: {out_path}")


if __name__ == "__main__":
    main()
