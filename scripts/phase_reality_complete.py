#!/usr/bin/env python3
"""Phase 2-3: Feature ablation + threshold optimization on REAL Binance data.

Protocol:
  1. Load real data via load_cached_data()
  2. Full 54-feature pipeline (3-class, threshold=0.715)
  3. DoubleEnsemble shuffle ablation on val folds 0-4
  4. Remove features with <2% shuffle impact
  5. Retrain on pruned set, validate on val
  6. Threshold grid search on val folds 0-4 (composite = total_net_R/max_drawdown)
  7. Touch test fold EXACTLY ONCE with selected threshold
  8. Block-bootstrap 95% CI on test

RULES (never violated):
  - Test touched only ONCE
  - Selection on val only
  - No threshold comparison on test
"""

from __future__ import annotations
import json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(os.environ.get("V7_ENGINE_ROOT", "/home/daskomputer/src/v7-engine"))
os.chdir(str(_REPO_ROOT))
for p in [str(_REPO_ROOT), str(_REPO_ROOT/"alphaforge"/"src"), str(_REPO_ROOT/"simulation"), str(_REPO_ROOT/"lib")]:
    if p not in sys.path: sys.path.insert(0, p)

import numpy as np
import xgboost as xgb
from simulation.authority import get_cost_constants
COST = get_cost_constants()

from alphaforge.train import load_cached_data, build_aligned_training_frame
from alphaforge.reports.metrics import compute_oos_metrics
from alphaforge.training.xgb_trainer import XGBoostTrainer


# ─── Constants ───────────────────────────────────────────────────────
MODE = "SCALP"
N_FOLDS = 6
THRESHOLD_INIT = 0.715
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
INTERVAL = "1h"

KEPT_INDICES_32 = [1, 2, 3, 4, 5, 8, 9, 11, 15, 17, 19, 24, 25, 27, 28, 29,
                   30, 32, 33, 36, 37, 39, 41, 42, 43, 44, 45, 47, 49, 50, 52, 53]


def compute_equity_curve(trade_r, timestamps):
    if len(trade_r) < 5:
        return {"max_dd": 0.0, "composite": 0.0, "total_net_r": float(np.sum(trade_r)) if len(trade_r) > 0 else 0.0}
    order = np.argsort(timestamps)
    sorted_r = np.array(trade_r)[order]
    equity = np.cumsum(sorted_r)
    peak = np.maximum.accumulate(equity)
    drawdown = peak - equity
    max_dd = float(drawdown.max())
    total_net = float(equity[-1])
    composite = total_net / max_dd if max_dd > 1e-12 else 999.0
    return {"max_dd": max_dd, "composite": composite, "total_net_r": total_net}


def block_bootstrap_ci(trade_r, timestamps, block_size=24, n_resamples=10000, seed=42):
    rng = np.random.RandomState(seed)
    order = np.argsort(timestamps)
    trade_r_sorted = trade_r[order]
    n = len(trade_r_sorted)
    if n < 10:
        return {"observed_mean_r": float(trade_r.mean()) if n > 0 else 0.0, "n_trades": n, "n_blocks": 0,
                "ci_lower": None, "ci_upper": None}
    block_ids = np.arange(n) // block_size
    u = np.unique(block_ids)
    bg = [trade_r_sorted[block_ids == b] for b in u]
    n_non = int((np.array([len(g) for g in bg]) > 0).sum())
    bg_ne = [g for g in bg if len(g) > 0]
    bm = np.zeros(n_resamples)
    for i in range(n_resamples):
        idx = rng.choice(n_non, size=n_non, replace=True)
        bm[i] = np.concatenate([bg_ne[j] for j in idx]).mean()
    bm.sort()
    return {"observed_mean_r": float(trade_r_sorted.mean()), "n_trades": n, "n_blocks": n_non,
            "ci_lower": float(bm[int(n_resamples * 0.025)]), "ci_upper": float(bm[int(n_resamples * 0.975)])}


def evaluate_fold(X_val, y_val, val_action_net, model, threshold, val_timestamps):
    dval = xgb.DMatrix(X_val)
    y_pred_prob = model.predict(dval)
    y_pred_prob_max = np.max(y_pred_prob, axis=1)
    y_pred = np.argmax(y_pred_prob, axis=1)
    y_pred[y_pred_prob_max < threshold] = 2
    labels = np.array(["LONG_NOW" if p==0 else "SHORT_NOW" if p==1 else "NO_TRADE" for p in y_pred], dtype=object)
    trade_r = val_action_net[np.arange(len(y_pred)), y_pred]
    metrics = compute_oos_metrics(labels.tolist(), trade_r.tolist(), fee_pct=0.0)
    active_mask = labels != "NO_TRADE"
    active_r = trade_r[active_mask]
    active_ts = val_timestamps[active_mask] if val_timestamps is not None else np.arange(len(active_r))
    eq = compute_equity_curve(active_r, active_ts)
    return {"total_net_R": metrics["total_net_R"], "active_trades": metrics["active_trade_count"],
            "max_dd": eq["max_dd"], "composite": eq["composite"],
            "labels": labels, "trade_r": trade_r, "active_r": active_r}


def train_eval(X_train, y_train, X_val, y_val, val_an, val_ts, feat_cols, threshold=THRESHOLD_INIT):
    Xtr = X_train[:, feat_cols] if feat_cols is not None else X_train
    Xv = X_val[:, feat_cols] if feat_cols is not None else X_val
    trainer = XGBoostTrainer(mode=MODE)
    fr = trainer.train(Xtr, y_train)
    return fr.model, evaluate_fold(Xv, y_val, val_an, fr.model, threshold, val_ts)


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    print(f"{'='*70}")
    print(f"PHASE 2-3 ON REAL DATA @ {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*70}")
    print(f"Mode: {MODE}, Symbols: {SYMBOLS}, Interval: {INTERVAL}")
    print(f"Cost: {json.dumps(COST, indent=2)}")

    # ── 1. Load real data ──────────────────────────────────────────────
    print(f"\n{'─'*70}")
    print("STEP 1: Load real data")
    print(f"{'─'*70}")
    ohlcv = load_cached_data(SYMBOLS, INTERVAL)
    assert ohlcv is not None, "FAIL: No real data loaded"
    print(f"  {len(ohlcv['close'])} total bars, {len(set(ohlcv['symbol']))} symbols")

    # ── 2. Build training frame ────────────────────────────────────────
    print(f"\n{'─'*70}")
    print("STEP 2: Build training frame (54 features, 3-class)")
    print(f"{'─'*70}")
    tf = build_aligned_training_frame(ohlcv, MODE, feature_groups=None)
    X, y_int = tf["X"], tf["y_int"]
    an_raw = tf["action_net_r"]
    timestamps = tf["timestamps"]
    feat_names = list(tf["feature_names"])

    nan_mask = np.isnan(X).any(axis=1)
    X_clean = X[~nan_mask]; y_clean = y_int[~nan_mask]
    an_clean = an_raw[~nan_mask]; ts_clean = timestamps[~nan_mask]
    n_features = X_clean.shape[1]
    print(f"  {n_features} features, {X_clean.shape[0]} valid samples")

    # ── 3. Fold structure ──────────────────────────────────────────────
    print(f"\n{'─'*70}")
    print("STEP 3: Fold structure")
    print(f"{'─'*70}")
    n = len(X_clean)
    fold_size = n // (N_FOLDS + 1)
    purge_bars = fold_size // 4
    embargo_bars = fold_size // 8
    grid_folds = list(range(N_FOLDS - 1))  # 0-4 for val
    test_fold = N_FOLDS - 1               # 5 for test

    folds = []
    for fi in range(N_FOLDS):
        train_end = (fi + 1) * fold_size
        vs = train_end
        ve = vs + fold_size // 2
        etr = train_end - purge_bars
        evs = vs + embargo_bars
        if etr <= 0 or evs >= ve:
            folds.append(None)
            continue
        folds.append({
            "X_train": X_clean[:etr], "y_train": y_clean[:etr],
            "X_val": X_clean[evs:ve], "y_val": y_clean[evs:ve],
            "val_an": an_clean[evs:ve], "val_ts": ts_clean[evs:ve],
        })

    print(f"  {len(grid_folds)} val folds (1-{len(grid_folds)}), 1 test fold ({test_fold+1})")
    print(f"  fold_size={fold_size}, purge={purge_bars}, embargo={embargo_bars}")

    # ════════════════════════════════════════════════════════════════════
    # PHASE 2: FEATURE ABLATION
    # ════════════════════════════════════════════════════════════════════

    print(f"\n{'='*70}")
    print(f"PHASE 2: FEATURE ABLATION (DoubleEnsemble) on REAL DATA")
    print(f"{'='*70}")

    # Train full model on each val fold
    all_cols = list(range(n_features))
    full_models, full_scores = [], []
    rng = np.random.RandomState(42)

    for fi in grid_folds:
        fd = folds[fi]
        if fd is None: continue
        model, eval_res = train_eval(fd["X_train"], fd["y_train"], fd["X_val"], fd["y_val"],
                                     fd["val_an"], fd["val_ts"], all_cols)
        full_models.append(model)
        full_scores.append(eval_res)
        print(f"  Fold {fi+1}: composite={eval_res['composite']:.2f}, totR={eval_res['total_net_R']:.4f}, "
              f"maxDD={eval_res['max_dd']:.4f}, active={eval_res['active_trades']}")

    # Aggregate baseline
    bl_all_r, bl_all_ts = [], []
    for fi, ev in zip(grid_folds, full_scores):
        fd = folds[fi]
        if fd is None: continue
        bl_all_r.extend(ev["active_r"].tolist())
        bl_all_ts.extend(fd["val_ts"][ev["labels"] != "NO_TRADE"].tolist())
    bl_eq = compute_equity_curve(np.array(bl_all_r), np.array(bl_all_ts))
    print(f"\n  BASELINE (val folds 1-{len(grid_folds)}): composite={bl_eq['composite']:.2f}, "
          f"totR={bl_eq['total_net_r']:.4f}, maxDD={bl_eq['max_dd']:.4f}")

    # Shuffle ablation (same method as synthetic: shuffle per feature, measure composite drop)
    print(f"\n  Shuffle ablation ({n_features} features)...")
    ablation_results = []
    for feat_idx in range(n_features):
        fold_drops = []
        for fi_idx, fi in enumerate(grid_folds):
            fd = folds[fi]
            model = full_models[fi_idx]
            if fd is None: continue
            X_shuf = fd["X_val"].copy()
            col = X_shuf[:, feat_idx].copy()
            rng.shuffle(col)
            X_shuf[:, feat_idx] = col
            eval_shuf = evaluate_fold(X_shuf, fd["y_val"], fd["val_an"], model, THRESHOLD_INIT, fd["val_ts"])
            bc = full_scores[fi_idx]["composite"]
            rel = (bc - eval_shuf["composite"]) / bc * 100 if bc > 1e-12 else 0.0
            fold_drops.append(rel)
        avg_drop = np.mean(fold_drops) if fold_drops else 0.0
        ablation_results.append({"idx": feat_idx, "name": feat_names[feat_idx],
                                 "avg_drop_pct": round(avg_drop, 4), "fold_drops": fold_drops})

    ablation_results.sort(key=lambda r: r["avg_drop_pct"], reverse=True)

    print(f"\n  {'Rank':>4} | {'Feature':<32} | {'Avg Drop%':>10}")
    print(f"  {'-'*4}-+-{'='*32}-+-{'='*10}")
    for rank, ar in enumerate(ablation_results, 1):
        print(f"  {rank:>4d} | {ar['name']:<32} | {ar['avg_drop_pct']:>+9.2f}%")

    # ── Phase 2b: Pruning decision ────────────────────────────────────
    print(f"\n{'─'*70}")
    print("PHASE 2b: PRUNING DECISION (<2% removal threshold)")
    print(f"{'─'*70}")

    kept_shuffle = [ar for ar in ablation_results if ar["avg_drop_pct"] >= 2.0]
    removed_shuffle = [ar for ar in ablation_results if ar["avg_drop_pct"] < 2.0]
    kept_indices = sorted([ar["idx"] for ar in kept_shuffle])

    print(f"\n  Kept: {len(kept_indices)} features (>=2% impact)")
    print(f"  Removed: {len(removed_shuffle)} features (<2% impact)")
    for ar in removed_shuffle:
        print(f"    [{ar['idx']:2d}] {ar['name']:<32} drop={ar['avg_drop_pct']:+.2f}%")

    # Retrain on pruned set
    pruned_models, pruned_scores = [], []
    for fi in grid_folds:
        fd = folds[fi]
        if fd is None: continue
        model, eval_res = train_eval(fd["X_train"], fd["y_train"], fd["X_val"], fd["y_val"],
                                     fd["val_an"], fd["val_ts"], kept_indices)
        pruned_models.append(model)
        pruned_scores.append(eval_res)
        print(f"  Fold {fi+1}: composite={eval_res['composite']:.2f}, totR={eval_res['total_net_R']:.4f}, "
              f"maxDD={eval_res['max_dd']:.4f}, active={eval_res['active_trades']}")

    pr_all_r, pr_all_ts = [], []
    for fi, ev in zip(grid_folds, pruned_scores):
        fd = folds[fi]
        if fd is None: continue
        pr_all_r.extend(ev["active_r"].tolist())
        pr_all_ts.extend(fd["val_ts"][ev["labels"] != "NO_TRADE"].tolist())
    pr_eq = compute_equity_curve(np.array(pr_all_r), np.array(pr_all_ts))

    composite_change = (pr_eq["composite"] - bl_eq["composite"]) / bl_eq["composite"] * 100 if bl_eq["composite"] > 1e-12 else 0
    print(f"\n  {'Metric':<25} {'Full':>20} {'Pruned':>20}")
    print(f"  {'-'*25} {'-'*20} {'-'*20}")
    print(f"  {'Composite':<25} {bl_eq['composite']:>20.2f} {pr_eq['composite']:>20.2f}")
    print(f"  {'Total Net R':<25} {bl_eq['total_net_r']:>20.4f} {pr_eq['total_net_r']:>20.4f}")
    print(f"  {'Max DD':<25} {bl_eq['max_dd']:>20.4f} {pr_eq['max_dd']:>20.4f}")
    print(f"  {'Change %':<25} {'':>20} {composite_change:>19.2f}%")

    if composite_change >= -2.0:
        print(f"\n  >>> Pruned set KABUL (composite {composite_change:+.2f}%)")
        final_cols = kept_indices
    else:
        print(f"\n  >>> Pruned set RED (composite {composite_change:+.2f}%) — all features kept")
        final_cols = all_cols

    n_pruned = len(final_cols)

    # ════════════════════════════════════════════════════════════════════
    # PHASE 3: THRESHOLD OPTIMIZATION on pruned set
    # ════════════════════════════════════════════════════════════════════

    print(f"\n{'='*70}")
    print(f"PHASE 3: THRESHOLD OPTIMIZATION on {n_pruned}-feature set (REAL DATA)")
    print(f"{'='*70}")

    # Run WFV on pruned set to get fold predictions
    # Need to train new models and collect raw predictions
    X_pruned = X_clean[:, final_cols]

    from alphaforge.train import walk_forward_validate
    results_wfv, fold_preds, fold_y_class, fold_y_val = walk_forward_validate(
        X_pruned, y_clean, an_clean[:, 0], MODE, min_folds=N_FOLDS,
        action_net_r=an_clean, return_raw_preds=True,
    )
    print(f"  {len(results_wfv)} folds completed")

    # Reconstruct per-fold val data
    for fi in range(N_FOLDS):
        train_end = (fi + 1) * fold_size
        vs = train_end
        ve = vs + fold_size // 2
        evs = vs + embargo_bars
        results_wfv[fi]["val_action_net"] = an_clean[evs:ve] if evs < ve else np.empty((0, 3))
        results_wfv[fi]["val_timestamps"] = ts_clean[evs:ve] if evs < ve else np.empty(0)

    # Grid search on val folds 0-4 ONLY
    center = 0.55
    grid = sorted(set([
        center, round(center * 0.7, 3), round(center * 0.8, 3), round(center * 0.9, 3),
        round(center * 1.1, 3), round(center * 1.2, 3), round(center * 1.3, 3),
    ]))
    grid = [max(0.0, min(1.0, t)) for t in grid]

    print(f"\n  VAL GRID (folds 1-{len(grid_folds)}):")
    print(f"  {'Threshold':>10} | {'Tot NetR':>10} | {'Max DD':>10} | {'Kompozit':>10} | {'Trade#':>7}")
    print(f"  {'-'*10}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}-+-{'-'*7}")

    grid_results = {}
    for th in grid:
        total_net = 0.0
        all_trade_r, all_trade_ts = [], []
        all_decisions = 0

        for fi in grid_folds:
            preds = fold_preds[fi]
            y_raw = fold_y_class[fi]
            y_pred = y_raw.copy()
            y_pred[preds < th] = 2
            labels = np.array(["LONG_NOW" if p == 0 else "SHORT_NOW" if p == 1 else "NO_TRADE" for p in y_pred], dtype=object)
            av = results_wfv[fi]["val_action_net"]
            trade_r = av[np.arange(len(y_pred)), y_pred]
            metrics = compute_oos_metrics(labels.tolist(), trade_r.tolist(), fee_pct=0.0)
            total_net += metrics["total_net_R"]
            all_decisions += len(labels)
            fold_ts = results_wfv[fi]["val_timestamps"]
            for j, (lbl, rv, ts) in enumerate(zip(labels, trade_r, fold_ts)):
                if lbl != "NO_TRADE":
                    all_trade_r.append(float(rv))
                    all_trade_ts.append(float(ts))

        tr_arr = np.array(all_trade_r)
        tt_arr = np.array(all_trade_ts)
        eq = compute_equity_curve(tr_arr, tt_arr)
        max_dd = eq["max_dd"]
        composite = eq["composite"]
        n_trades = len(tr_arr)
        grid_results[th] = {"total_net_R": total_net, "max_dd": max_dd, "composite": composite, "n_trades": n_trades}
        print(f"  {th:>10.3f} | {total_net:>10.4f} | {max_dd:>10.4f} | {composite:>10.2f} | {n_trades:>7d}")

    # Select best threshold on VAL ONLY
    best_th = max(grid_results, key=lambda t: grid_results[t]["composite"])
    best_val_res = grid_results[best_th]
    print(f"\n  >>> SECILEN THRESHOLD: {best_th:.3f} (kompozit={best_val_res['composite']:.2f})")

    # ── TEST: Touch test fold EXACTLY ONCE ────────────────────────────
    print(f"\n{'='*70}")
    print(f"TEST/OOS (fold {test_fold+1}) — ONE touch with th={best_th:.3f}")
    print(f"{'='*70}")

    fi = test_fold
    preds = fold_preds[fi]
    y_raw = fold_y_class[fi]
    y_pred = y_raw.copy()
    y_pred[preds < best_th] = 2

    labels = np.array(["LONG_NOW" if p == 0 else "SHORT_NOW" if p == 1 else "NO_TRADE" for p in y_pred], dtype=object)
    av = results_wfv[fi]["val_action_net"]
    trade_r = av[np.arange(len(y_pred)), y_pred]
    fold_ts = results_wfv[fi]["val_timestamps"]

    metrics = compute_oos_metrics(labels.tolist(), trade_r.tolist(), fee_pct=0.0)
    test_total_net = metrics["total_net_R"]
    test_active = metrics["active_trade_count"]

    all_test_r = [float(rv) for lbl, rv in zip(labels, trade_r) if lbl != "NO_TRADE"]
    all_test_ts = [float(ts) for lbl, rv, ts in zip(labels, trade_r, fold_ts) if lbl != "NO_TRADE"]
    test_tr = np.array(all_test_r)
    test_tt = np.array(all_test_ts)
    test_eq = compute_equity_curve(test_tr, test_tt)
    test_max_dd = test_eq["max_dd"]
    test_composite = test_eq["composite"]

    bb = block_bootstrap_ci(test_tr, test_tt, block_size=24)

    print(f"\n  Threshold:          {best_th:.3f}")
    print(f"  Total Net R:        {test_total_net:.6f}")
    print(f"  Max DD:             {test_max_dd:.6f}")
    print(f"  Kompozit:           {test_composite:.2f}")
    print(f"  Active trades:      {test_active} (L:{metrics['long_trade_count']}, S:{metrics['short_trade_count']}, NT:{metrics['no_trade_count']})")
    print(f"  Exposure:           {metrics['exposure_pct']:.2f}%")
    if bb['ci_lower'] is not None:
        print(f"  Block bootstrap 95% CI: [{bb['ci_lower']:.6f}, {bb['ci_upper']:.6f}]")

    ci_pos = bb['ci_lower'] is not None and bb['ci_lower'] > 0
    net_pos = test_total_net > 0
    pass_condition = ci_pos and net_pos
    print(f"\n  total_net_R > 0: {'YES' if net_pos else 'NO'}")
    print(f"  CI fully positive: {'YES' if ci_pos else 'NO'}")
    print(f"  >>> TEST KARAR: {'PASS' if pass_condition else 'FAIL'}")

    # ════════════════════════════════════════════════════════════════════
    # SAVE RESULTS
    # ════════════════════════════════════════════════════════════════════

    out = {
        "phase": "Phase2_3_RealData",
        "mode": MODE,
        "symbols": SYMBOLS,
        "interval": INTERVAL,
        "n_features_full": n_features,
        "n_features_pruned": n_pruned,
        "data_source": "BINANCE_REAL",
        "data_bars": len(ohlcv["close"]),
        "ablation": {
            "baseline_val_composite": bl_eq["composite"],
            "pruned_val_composite": pr_eq["composite"],
            "val_composite_change_pct": composite_change,
            "kept_indices": final_cols,
            "removed_features": [ar["name"] for ar in removed_shuffle],
            "full_ranking": [(ar["idx"], ar["name"], ar["avg_drop_pct"]) for ar in ablation_results],
        },
        "threshold_optimization": {
            "grid": {str(k): v for k, v in grid_results.items()},
            "selected_threshold": best_th,
            "val_composite_at_selected": best_val_res["composite"],
        },
        "test": {
            "threshold_used": best_th,
            "total_net_R": test_total_net,
            "max_dd": test_max_dd,
            "composite": test_composite,
            "active_trades": test_active,
            "long_count": metrics["long_trade_count"],
            "short_count": metrics["short_trade_count"],
            "no_trade_count": metrics["no_trade_count"],
            "exposure_pct": metrics["exposure_pct"],
            "block_ci_95": [bb['ci_lower'], bb['ci_upper']],
            "decision": "PASS" if pass_condition else "FAIL",
        },
    }

    out_path = _REPO_ROOT / "reports" / "phase_reality_complete.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nResults: {out_path}")

    # ── OZET ──
    print(f"\n{'='*70}")
    print("OZET")
    print(f"{'='*70}")
    print(f"  Data source:  BINANCE REAL ({len(ohlcv['close'])} bars, {len(set(ohlcv['symbol']))} symbols)")
    print(f"  Full features: {n_features} -> Pruned: {n_pruned}")
    print(f"  Val composite: {bl_eq['composite']:.2f} -> {pr_eq['composite']:.2f} ({composite_change:+.2f}%)")
    print(f"  Selected threshold: {best_th:.3f}")
    print(f"  Test composite: {test_composite:.2f}")
    print(f"  Test BB CI 95%: [{bb['ci_lower']:.6f}, {bb['ci_upper']:.6f}]" if bb['ci_lower'] is not None else "")
    print(f"  TEST: {'PASS' if pass_condition else 'FAIL'}")


if __name__ == "__main__":
    main()
