#!/usr/bin/env python3
"""
Feature Ablation (DoubleEnsemble yontemi) — v2
===============================================
Her feature icin: val set'te shuffle => model yeniden predicts =>
kompozit skordaki dusus => feature onem siralamasi.

Feature CIKARMA: modeli retrain ederek yapilir (shuffle yetmez).
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
print(f"Cost constants: {json.dumps(COST, indent=2)}")

from alphaforge.train import generate_synthetic_ohlcv, build_aligned_training_frame
from alphaforge.reports.metrics import compute_oos_metrics
from alphaforge.training.xgb_trainer import XGBoostTrainer


def compute_equity_curve_metrics(trade_r, timestamps):
    if len(trade_r) < 5:
        return {"max_dd": 0.0, "composite": 0.0, "total_net_r": float(np.sum(trade_r)) if len(trade_r) > 0 else 0.0}
    order = np.argsort(timestamps)
    sorted_r = np.array(trade_r)[order]
    equity = np.cumsum(sorted_r)
    running_max = np.maximum.accumulate(equity)
    max_dd = float(running_max[-1] - np.minimum.accumulate(equity).min() if len(equity) > 0 else 0.0)
    # Correct max drawdown computation
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


def evaluate_fold(X_val, y_val, val_action_net, model, threshold=0.715, val_timestamps=None):
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
    if val_timestamps is not None:
        active_ts = val_timestamps[active_mask]
        eq = compute_equity_curve_metrics(active_r, active_ts)
    else:
        eq = compute_equity_curve_metrics(active_r, np.arange(len(active_r)))
    return {"total_net_R": metrics["total_net_R"], "active_trades": metrics["active_trade_count"],
            "max_dd": eq["max_dd"], "composite": eq["composite"], "labels": labels, "trade_r": trade_r,
            "active_r": active_r}


def train_and_evaluate(X_train_all, y_train_all, X_val, y_val, val_an, val_ts, feat_cols, mode="SCALP", threshold=0.715):
    """Train model on selected feature columns and evaluate on val."""
    Xtr = X_train_all[:, feat_cols] if feat_cols is not None else X_train_all
    Xv = X_val[:, feat_cols] if feat_cols is not None else X_val
    trainer = XGBoostTrainer(mode=mode)
    fold_result = trainer.train(Xtr, y_train_all)
    return fold_result.model, evaluate_fold(Xv, y_val, val_an, fold_result.model, threshold, val_ts)


def main():
    mode = "SCALP"; n_folds = 6; threshold = 0.715
    print(f"\n{'='*70}")
    print(f"FEATURE ABLATION (DoubleEnsemble yontemi) — v2")
    print(f"{'='*70}")
    print(f"Mode: {mode}, Fold: {n_folds}, Threshold: {threshold}\n")

    # --- Pipeline ---
    ohlcv = generate_synthetic_ohlcv(n_bars=3000, symbols=("BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","ADAUSDT"), random_seed=42)
    tf = build_aligned_training_frame(ohlcv, mode, feature_groups=None)
    X, y_int = tf["X"], tf["y_int"]
    an_raw = tf["action_net_r"]; timestamps = tf["timestamps"]
    feat_names = list(tf["feature_names"])

    nan_mask = np.isnan(X).any(axis=1)
    X_clean = X[~nan_mask]; y_clean = y_int[~nan_mask]
    an_clean = an_raw[~nan_mask]; ts_clean = timestamps[~nan_mask]
    n_features = X_clean.shape[1]
    print(f"  ADIM 1: {n_features} features, {X_clean.shape[0]} valid samples\n")

    # --- Fold structure ---
    n = len(X_clean); fold_size = n // (n_folds + 1)
    purge_bars = fold_size // 4; embargo_bars = fold_size // 8
    grid_folds = list(range(n_folds - 1))
    test_fold = n_folds - 1

    # Build fold data
    folds = []
    for fi in range(n_folds):
        train_end = (fi+1)*fold_size; vs = train_end; ve = vs + fold_size//2
        etr = train_end - purge_bars; evs = vs + embargo_bars
        if etr <= 0 or evs >= ve:
            folds.append(None); continue
        folds.append({
            "X_train": X_clean[:etr], "y_train": y_clean[:etr],
            "X_val": X_clean[evs:ve], "y_val": y_clean[evs:ve],
            "val_an": an_clean[evs:ve], "val_ts": ts_clean[evs:ve],
        })

    # ============ PHASE 1: TRAIN FULL MODEL + SHUFFLE ABLATION ============
    print(f"{'='*70}")
    print(f"FAZ 1: FULL MODEL + SHUFFLE ABLATION")
    print(f"{'='*70}")

    # Train full model on each grid fold for ablation
    all_cols = list(range(n_features))
    full_models = []
    full_scores = []
    rng = np.random.RandomState(42)

    for fi in grid_folds:
        fd = folds[fi]
        if fd is None: continue
        model, eval_res = train_and_evaluate(fd["X_train"], fd["y_train"], fd["X_val"], fd["y_val"],
                                              fd["val_an"], fd["val_ts"], all_cols, mode, threshold)
        full_models.append(model)
        full_scores.append(eval_res)
        print(f"  Fold {fi+1}: composite={eval_res['composite']:.2f}, totR={eval_res['total_net_R']:.4f}, "
              f"maxDD={eval_res['max_dd']:.4f}, active={eval_res['active_trades']}")

    # Aggregate baseline composite on val folds 0-4
    bl_all_r = []; bl_all_ts = []
    for fi, ev in zip(grid_folds, full_scores):
        fd = folds[fi]
        if fd is None: continue
        bl_all_r.extend(ev["active_r"].tolist())
        bl_all_ts.extend(fd["val_ts"][ev["labels"] != "NO_TRADE"].tolist())
    bl_eq = compute_equity_curve_metrics(np.array(bl_all_r), np.array(bl_all_ts))
    print(f"\n  BASELINE (val folds 1-{len(grid_folds)}): composite={bl_eq['composite']:.2f}, "
          f"totR={bl_eq['total_net_r']:.4f}, maxDD={bl_eq['max_dd']:.4f}")

    # Shuffle ablation: for each feature, shuffle in val set, re-predict
    print(f"\n  Shuffle ablation basliyor ({n_features} features)...")
    ablation_results = []
    for feat_idx in range(n_features):
        fold_drops = []
        for fi_idx, fi in enumerate(grid_folds):
            fd = folds[fi]; model = full_models[fi_idx]
            if fd is None: continue
            X_shuf = fd["X_val"].copy()
            col = X_shuf[:, feat_idx].copy(); rng.shuffle(col)
            X_shuf[:, feat_idx] = col
            eval_shuf = evaluate_fold(X_shuf, fd["y_val"], fd["val_an"], model, threshold, fd["val_ts"])
            bc = full_scores[fi_idx]["composite"]
            rel = (bc - eval_shuf["composite"]) / bc * 100 if bc > 1e-12 else 0.0
            fold_drops.append(rel)
        avg_drop = np.mean(fold_drops) if fold_drops else 0.0
        ablation_results.append({"idx": feat_idx, "name": feat_names[feat_idx],
                                 "avg_drop_pct": avg_drop, "fold_drops": fold_drops})

    ablation_results.sort(key=lambda r: r["avg_drop_pct"], reverse=True)

    print(f"\n  {'Rank':>4} | {'Feature':<32} | {'Avg Drop%':>10} | {'Fold drops'}")
    print(f"  {'-'*4}-+-{'-'*32}-+-{'-'*10}-+-{'------------'}")
    for rank, ar in enumerate(ablation_results, 1):
        fd_str = ", ".join(f"{d:+.1f}" for d in ar["fold_drops"])
        print(f"  {rank:>4d} | {ar['name']:<32} | {ar['avg_drop_pct']:>+9.2f}% | {fd_str}")

    # ============ PHASE 2: RETRAIN ON PRUNED SET ============
    print(f"\n{'='*70}")
    print(f"FAZ 2: RETRAIN ON PRUNED FEATURE SET")
    print(f"{'='*70}")

    # Features with <2% impact are candidates for removal
    kept_shuffle = [ar for ar in ablation_results if ar["avg_drop_pct"] >= 2.0]
    removed_shuffle = [ar for ar in ablation_results if ar["avg_drop_pct"] < 2.0]
    kept_indices_2pct = sorted([ar["idx"] for ar in kept_shuffle])

    print(f"\n  <%2 etki ile cikarilacak: {len(removed_shuffle)} feature")
    print(f"  Kalan: {len(kept_indices_2pct)} feature")
    for ar in removed_shuffle:
        print(f"    [{ar['idx']:2d}] {ar['name']:<32} drop={ar['avg_drop_pct']:+.2f}%")

    # Retrain grid folds on pruned set
    pruned_models = []; pruned_scores = []
    for fi in grid_folds:
        fd = folds[fi]
        if fd is None: continue
        model, eval_res = train_and_evaluate(fd["X_train"], fd["y_train"], fd["X_val"], fd["y_val"],
                                              fd["val_an"], fd["val_ts"], kept_indices_2pct, mode, threshold)
        pruned_models.append(model)
        pruned_scores.append(eval_res)
        print(f"  Fold {fi+1}: composite={eval_res['composite']:.2f}, totR={eval_res['total_net_R']:.4f}, "
              f"maxDD={eval_res['max_dd']:.4f}, active={eval_res['active_trades']}")

    # Aggregate pruned baseline
    pr_all_r = []; pr_all_ts = []
    for fi, ev in zip(grid_folds, pruned_scores):
        fd = folds[fi]
        if fd is None: continue
        pr_all_r.extend(ev["active_r"].tolist())
        pr_all_ts.extend(fd["val_ts"][ev["labels"] != "NO_TRADE"].tolist())
    pr_eq = compute_equity_curve_metrics(np.array(pr_all_r), np.array(pr_all_ts))

    composite_change = (pr_eq["composite"] - bl_eq["composite"]) / bl_eq["composite"] * 100 if bl_eq["composite"] > 1e-12 else 0
    print(f"\n  {'Metric':<25} {'Full (54 feat)':>20} {'Pruned':>20}")
    print(f"  {'-'*25} {'-'*20} {'-'*20}")
    print(f"  {'Composite':<25} {bl_eq['composite']:>20.2f} {pr_eq['composite']:>20.2f}")
    print(f"  {'Total Net R':<25} {bl_eq['total_net_r']:>20.4f} {pr_eq['total_net_r']:>20.4f}")
    print(f"  {'Max DD':<25} {bl_eq['max_dd']:>20.4f} {pr_eq['max_dd']:>20.4f}")
    print(f"  {'Change %':<25} {'':>20} {composite_change:>19.2f}%")

    if composite_change >= -2.0:
        print(f"\n  >>> KARAR: Pruned set KABUL (composite {composite_change:+.2f}%, <%2 dusus)")
        final_cols = kept_indices_2pct
    else:
        print(f"\n  >>> KARAR: Pruned set RED (composite {composite_change:+.2f}% dustu)")
        print(f"  >>> TUM feature'lar korunuyor.")
        final_cols = all_cols

    # ============ PHASE 3: TEST/OOS ============
    print(f"\n{'='*70}")
    print(f"FAZ 3: TEST/OOS DOGRULAMASI (fold {test_fold+1})")
    print(f"{'='*70}")

    fd_test = folds[test_fold]
    test_conducted = False
    test_full_eq = {"total_net_r": 0.0, "max_dd": 0.0, "composite": 0.0}
    test_pruned_eq = {"total_net_r": 0.0, "max_dd": 0.0, "composite": 0.0}
    test_bb = {"ci_lower_block": None, "ci_upper_block": None}

    if fd_test is not None:
        # Full model on test
        model_f, eval_f = train_and_evaluate(fd_test["X_train"], fd_test["y_train"], fd_test["X_val"], fd_test["y_val"],
                                              fd_test["val_an"], fd_test["val_ts"], all_cols, mode, threshold)
        test_full_eq = compute_equity_curve_metrics(eval_f["active_r"], fd_test["val_ts"][eval_f["labels"] != "NO_TRADE"])

        # Pruned model on test
        model_p, eval_p = train_and_evaluate(fd_test["X_train"], fd_test["y_train"], fd_test["X_val"], fd_test["y_val"],
                                              fd_test["val_an"], fd_test["val_ts"], final_cols, mode, threshold)
        test_pruned_eq = compute_equity_curve_metrics(eval_p["active_r"], fd_test["val_ts"][eval_p["labels"] != "NO_TRADE"])
        pruned_r = eval_p["active_r"]
        pruned_ts = fd_test["val_ts"][eval_p["labels"] != "NO_TRADE"]

        test_bb = block_bootstrap_ci(pruned_r, pruned_ts, block_size=24)
        test_conducted = True

        print(f"\n  {'Metric':<30} {'Full (54 feat)':>18} {'Pruned':>18}")
        print(f"  {'-'*30} {'-'*18} {'-'*18}")
        print(f"  {'Features':<30} {n_features:>18d} {len(final_cols):>18d}")
        print(f"  {'Total Net R':<30} {test_full_eq['total_net_r']:>18.4f} {test_pruned_eq['total_net_r']:>18.4f}")
        print(f"  {'Max DD':<30} {test_full_eq['max_dd']:>18.4f} {test_pruned_eq['max_dd']:>18.4f}")
        print(f"  {'Composite':<30} {test_full_eq['composite']:>18.2f} {test_pruned_eq['composite']:>18.2f}")
        print(f"  {'Active trades':<30} {eval_f['active_trades']:>18d} {eval_p['active_trades']:>18d}")
        if test_bb['ci_lower_block'] is not None:
            print(f"  {'BB CI 95%':<30} {'':>18} [{test_bb['ci_lower_block']:.4f}, {test_bb['ci_upper_block']:.4f}]")

        ci_pos = test_bb['ci_lower_block'] is not None and test_bb['ci_lower_block'] > 0
        net_pos = test_pruned_eq['total_net_r'] > 0
        print(f"\n  CI fully positive: {'YES' if ci_pos else 'NO'}")
        print(f"  total_net_R > 0: {'YES' if net_pos else 'NO'}")
        print(f"  >>> TEST KARAR: {'PASS' if (ci_pos and net_pos) else 'FAIL'}")
    else:
        print(f"  Test fold verisi yok.")
        ci_pos = False; net_pos = False

    # ============ SUMMARY ============
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"ADIM 1: Pipeline {n_features} feature ile calisiyor (feature_groups=None)")
    print(f"ADIM 2: Shuffle ablation tamamlandi")
    print(f"ADIM 3: Pruning karari: {'KABUL' if composite_change >= -2.0 else 'RED'} ({composite_change:+.2f}%)")
    print(f"        Kept={len(final_cols)}, Removed={n_features - len(final_cols)}")
    print(f"ADIM 4: Test {'PASS' if (ci_pos and net_pos) else 'FAIL'}")

    if len(final_cols) < n_features:
        print(f"\nKALAN FEATURE'LAR ({len(final_cols)}):")
        for i in sorted(final_cols):
            print(f"  [{i:2d}] {feat_names[i]}")
        print(f"\nCIKARILAN FEATURE'LAR ({n_features - len(final_cols)}):")
        kept_set = set(final_cols)
        for i in range(n_features):
            if i not in kept_set:
                print(f"  [{i:2d}] {feat_names[i]}")

    # Save
    out = {"n_full": n_features, "n_pruned": len(final_cols),
           "kept_indices": final_cols,
           "removed_indices": [i for i in range(n_features) if i not in set(final_cols)],
           "ablation_ranking": [(ar["idx"], ar["name"], round(ar["avg_drop_pct"], 4)) for ar in ablation_results],
           "test_total_net_r_full": float(test_full_eq['total_net_r']) if test_conducted else None,
           "test_total_net_r_pruned": float(test_pruned_eq['total_net_r']) if test_conducted else None,
           "test_composite_pruned": float(test_pruned_eq['composite']) if test_conducted else None,
           "test_ci_pruned": [float(test_bb['ci_lower_block']), float(test_bb['ci_upper_block'])] if test_conducted and test_bb['ci_lower_block'] is not None else None,
           "val_composite_full": float(bl_eq['composite']), "val_composite_pruned": float(pr_eq['composite']),
           "val_composite_change_pct": round(composite_change, 4)}
    out_path = _REPO_ROOT / "reports" / "feature_ablation_results.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSonuclar: {out_path}")


if __name__ == "__main__":
    main()
