#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════╗
# ║  DEPRECATED: Sentetik veri kullanir.                      ║
# ║  Gercek veri icin scripts/phase_reality_complete.py       ║
# ║  veya scripts/candidate_v031e_verified.py kullanin.       ║
# ╚══════════════════════════════════════════════════════════════╝

"""
Audit: bb_position-only model vs 32-feature model.
Train model on ONLY bb_position, evaluate on same test fold.
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
from alphaforge.train import generate_synthetic_ohlcv, build_aligned_training_frame, walk_forward_validate
from alphaforge.reports.metrics import compute_oos_metrics
from alphaforge.training.xgb_trainer import XGBoostTrainer

KEPT_INDICES_32 = [1, 2, 3, 4, 5, 8, 9, 11, 15, 17, 19, 24, 25, 27, 28, 29,
                   30, 32, 33, 36, 37, 39, 41, 42, 43, 44, 45, 47, 49, 50, 52, 53]
# bb_position is index 4 in the 54-feature set
BB_POSITION_IDX = 4

def compute_equity_curve(trade_r, timestamps):
    order = np.argsort(timestamps)
    sorted_r = np.array(trade_r)[order]
    equity = np.cumsum(sorted_r)
    peak = np.maximum.accumulate(equity)
    drawdown = peak - equity
    max_dd = float(drawdown.max()) if len(drawdown) > 0 else 0.0
    return equity, max_dd

def block_bootstrap_ci(trade_r, timestamps, block_size=24, n_resamples=10000, seed=42):
    rng = np.random.RandomState(seed)
    order = np.argsort(timestamps)
    trade_r_sorted = trade_r[order]
    n = len(trade_r_sorted)
    if n < 10:
        return {"ci_lower": None, "ci_upper": None, "n_trades": n}
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
    return {"ci_lower": float(bm[int(n_resamples*0.025)]), "ci_upper": float(bm[int(n_resamples*0.975)]),
            "n_trades": n, "observed_mean_r": float(trade_r_sorted.mean())}

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
    active_ts = val_timestamps[active_mask]
    _, max_dd = compute_equity_curve(active_r, active_ts)
    composite = metrics["total_net_R"] / max_dd if max_dd > 1e-12 else 999.0
    return {"total_net_R": metrics["total_net_R"], "active_trades": metrics["active_trade_count"],
            "max_dd": max_dd, "composite": composite, "labels": labels, "trade_r": trade_r, "active_r": active_r}

def main():
    mode = "SCALP"
    n_folds = 6
    print(f"{'='*70}")
    print(f"AUDIT: bb_position-only model vs 32-feature model")
    print(f"{'='*70}")

    # Fast CPU hyperparameters for audit (same total learning budget ≈ 10)
    from alphaforge.training.xgb_trainer import SWING_DEFAULT_HYPERPARAMS as _BASE_PARAMS
    FAST_CPU_PARAMS = {**_BASE_PARAMS,
        "n_estimators": 10,
        "learning_rate": 1.0,
        "max_bin": 64,
        "early_stopping_rounds": 5,
    }

    # ─── Load data ───────────────────────────────────────────────────────
    ohlcv = generate_synthetic_ohlcv(n_bars=3000, symbols=("BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","ADAUSDT"), random_seed=42)
    tf = build_aligned_training_frame(ohlcv, mode, feature_groups=None)
    X, y_int = tf["X"], tf["y_int"]
    an_raw = tf["action_net_r"]; timestamps = tf["timestamps"]
    feat_names = list(tf["feature_names"])
    
    nan_mask = np.isnan(X).any(axis=1)
    X_clean = X[~nan_mask]; y_clean = y_int[~nan_mask]
    an_clean = an_raw[~nan_mask]; ts_clean = timestamps[~nan_mask]
    
    # 32-feature matrix
    X_32 = X_clean[:, KEPT_INDICES_32]
    # bb_position-only matrix
    bb_idx_32 = KEPT_INDICES_32.index(BB_POSITION_IDX)
    X_bb = X_clean[:, [BB_POSITION_IDX]]

    n = len(X_clean); fold_size = n // (n_folds + 1)
    embargo = fold_size // 8; purge = fold_size // 4
    
    # Build fold data
    folds = []
    for fi in range(n_folds):
        train_end = (fi+1)*fold_size; vs = train_end; ve = vs + fold_size//2
        etr = train_end - purge; evs = vs + embargo
        if etr <= 0 or evs >= ve:
            folds.append(None)
            continue
        folds.append({"train_end": train_end, "vs": vs, "ve": ve, "etr": etr, "evs": evs})

    grid_folds = [0,1,2,3,4]
    test_fold = 5
    
    for label, X_data, n_feat in [("32-FEATURE", X_32, 32), ("BB_POSITION_ONLY", X_bb, 1)]:
        print(f"\n{'─'*70}")
        print(f"Model: {label} ({n_feat} feature)")
        print(f"{'─'*70}")

        # Pre-convert to float32 once for all folds
        X_data_f32 = X_data.astype(np.float32)

        # Train on folds 0-4, collect predictions for val
        fold_preds = []; fold_y_class = []; fold_y_val = []; fold_van = []; fold_vts = []
        
        for fi in grid_folds:
            fd = folds[fi]
            if fd is None: continue
            X_tr = X_data_f32[:fd["etr"]]; y_tr = y_clean[:fd["etr"]]
            X_v = X_data_f32[fd["evs"]:fd["ve"]]; y_v = y_clean[fd["evs"]:fd["ve"]]
            van = an_clean[fd["evs"]:fd["ve"]]; vts = ts_clean[fd["evs"]:fd["ve"]]
            
            trainer = XGBoostTrainer(mode=mode, hyperparameters=FAST_CPU_PARAMS)
            fr = trainer.train(X_tr, y_tr)
            dval = xgb.DMatrix(X_v)
            ypp = fr.model.predict(dval)
            yppm = np.max(ypp, axis=1)
            ypc = np.argmax(ypp, axis=1)
            
            fold_preds.append(yppm); fold_y_class.append(ypc)
            fold_y_val.append(y_v); fold_van.append(van); fold_vts.append(vts)
        
        # Grid on val folds
        center = 0.55
        grid = sorted(set([center, round(center*0.7,3), round(center*0.8,3), round(center*0.9,3),
                            round(center*1.1,3), round(center*1.2,3), round(center*1.3,3), 0.715]))
        
        print(f"  VAL GRID (folds 1-5):")
        grid_results = {}
        for th in grid:
            total_net = 0.0; all_r = []; all_ts = []; all_dec = 0
            for fi_idx, fi in enumerate(grid_folds):
                preds = fold_preds[fi_idx]; y_raw = fold_y_class[fi_idx]
                y_pred = y_raw.copy(); y_pred[preds < th] = 2
                labels = np.array(["LONG_NOW" if p==0 else "SHORT_NOW" if p==1 else "NO_TRADE" for p in y_pred], dtype=object)
                av = fold_van[fi_idx]
                trade_r = av[np.arange(len(y_pred)), y_pred]
                metrics = compute_oos_metrics(labels.tolist(), trade_r.tolist(), fee_pct=0.0)
                total_net += metrics["total_net_R"]; all_dec += len(labels)
                fts = fold_vts[fi_idx]
                for j, (lbl, rv, ts) in enumerate(zip(labels, trade_r, fts)):
                    if lbl != "NO_TRADE": all_r.append(float(rv)); all_ts.append(float(ts))
            tr_a = np.array(all_r); tt_a = np.array(all_ts)
            _, md = compute_equity_curve(tr_a, tt_a)
            comp = total_net / md if md > 1e-12 else 999.0
            grid_results[th] = {"comp": comp, "total_net_R": total_net, "max_dd": md, "n": len(tr_a)}
            print(f"    th={th:.3f} kompozit={comp:>8.2f} netR={total_net:>8.4f} maxDD={md:>8.4f} trades={len(tr_a):>5d}")
        
        best_th = max(grid_results, key=lambda t: grid_results[t]["comp"])
        print(f"  >>> VAL SECIMI: th={best_th:.3f} (kompozit={grid_results[best_th]['comp']:.2f})")
        
        # ─── TEST: Touch test fold ONLY ONCE with selected threshold ──────
        fd = folds[test_fold]; assert fd is not None
        # Train on fold 5 train (uses all data up to fold 5)
        X_tr_all = X_data_f32[:fd["etr"]]; y_tr_all = y_clean[:fd["etr"]]
        X_t = X_data_f32[fd["evs"]:fd["ve"]]; y_t = y_clean[fd["evs"]:fd["ve"]]
        tan = an_clean[fd["evs"]:fd["ve"]]; tts = ts_clean[fd["evs"]:fd["ve"]]
        
        trainer = XGBoostTrainer(mode=mode, hyperparameters=FAST_CPU_PARAMS)
        dval = xgb.DMatrix(X_t)
        ypp = fr.model.predict(dval)
        yppm = np.max(ypp, axis=1)
        ypc = np.argmax(ypp, axis=1)
        ypc[yppm < best_th] = 2
        
        labels = np.array(["LONG_NOW" if p==0 else "SHORT_NOW" if p==1 else "NO_TRADE" for p in ypc], dtype=object)
        trade_r = tan[np.arange(len(ypc)), ypc]
        metrics = compute_oos_metrics(labels.tolist(), trade_r.tolist(), fee_pct=0.0)
        active_mask = labels != "NO_TRADE"
        active_r = trade_r[active_mask]; active_ts = tts[active_mask]
        _, md = compute_equity_curve(active_r, active_ts)
        comp = metrics["total_net_R"] / md if md > 1e-12 else 999.0
        bb = block_bootstrap_ci(active_r, active_ts, n_resamples=2000)
        
        print(f"\n  TEST/OOS (fold {test_fold+1}) @ th={best_th:.3f}:")
        print(f"    total_net_R={metrics['total_net_R']:.4f} maxDD={md:.6f} kompozit={comp:.2f}")
        print(f"    trades={metrics['active_trade_count']} (L:{metrics['long_trade_count']} S:{metrics['short_trade_count']} NT:{metrics['no_trade_count']})")
        if bb["ci_lower"] is not None:
            print(f"    BB 95% CI=[{bb['ci_lower']:.6f}, {bb['ci_upper']:.6f}]")
            print(f"    CI fully positive: {'YES' if bb['ci_lower'] > 0 else 'NO'}")

if __name__ == "__main__":
    main()
