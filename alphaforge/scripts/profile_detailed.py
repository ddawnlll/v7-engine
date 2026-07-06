#!/usr/bin/env python3
"""
Detailed per-fold XGBoost GPU profiler.
Also validates SCALP feature computation time anomaly (JIT vs real).
"""

from __future__ import annotations

import os, sys, time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC_PATH = str(_REPO_ROOT / "alphaforge" / "src")
for p in [_SRC_PATH, str(_REPO_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import numpy as np
from alphaforge.train import generate_synthetic_ohlcv, MODE_CONFIG
from alphaforge.training.xgb_trainer import GPU_PARAMS

# ── Warm-up: force numba JIT compile before main profiling ──
print("=== JIT Warm-up ===", flush=True)
from alphaforge.train import _generate_labels_numba
_ = _generate_labels_numba(
    np.array([100.0, 101.0, 99.0, 102.0], dtype=np.float64),
    np.array([101.0, 102.0, 100.0, 103.0], dtype=np.float64),
    np.array([99.0, 100.0, 98.0, 101.0], dtype=np.float64),
    3, 1.5, 2.0, 4, 0.15, 0.10,
)
print("  JIT warm-up done", flush=True)

# ── Generate data once ──
print("=== Generating Data ===", flush=True)
ohlcv = generate_synthetic_ohlcv(
    n_bars=3000, symbols=("SYM0", "SYM1", "SYM2", "SYM3", "SYM4"), random_seed=42,
)
print(f"  {len(ohlcv['close'])} bars, {len(set(ohlcv['symbol']))} symbols", flush=True)

# ── Profile each stage ──
def profile_mode_stages(mode: str, label: str):
    print(f"\n{'='*60}", flush=True)
    print(f"  {label} — {mode}", flush=True)
    print(f"{'='*60}", flush=True)
    
    times = {}
    
    # Feature computation (times might differ from JIT/non-JIT)
    from alphaforge.train import compute_all_features
    t0 = time.monotonic()
    X_feat, feat_names = compute_all_features(ohlcv, mode)
    times["features"] = time.monotonic() - t0
    print(f"  compute_features: {times['features']:.3f}s ({X_feat.shape[1]} cols)", flush=True)
    
    # Build aligned frame (includes labels)
    from alphaforge.train import build_aligned_training_frame
    t0 = time.monotonic()
    tf = build_aligned_training_frame(ohlcv, mode)
    times["build_frame"] = time.monotonic() - t0
    X, y_int, anet = tf["X"], tf["y_int"], tf["action_net_r"]
    print(f"  build_frame: {times['build_frame']:.3f}s (X={X.shape})", flush=True)
    
    # Clean NaNs
    nan_mask = np.isnan(X).any(axis=1)
    X_clean, y_clean, anet_clean = X[~nan_mask], y_int[~nan_mask], anet[~nan_mask]
    print(f"  nan_clean: {X_clean.shape[0]} valid ({int(nan_mask.sum())} dropped)", flush=True)
    
    # Per-fold XGBoost timing
    print(f"\n  Per-fold XGBoost training (GPU: {GPU_PARAMS['device']}):", flush=True)
    n = len(X_clean)
    min_folds = 6
    fold_size = n // (min_folds + 1)
    max_hold = MODE_CONFIG.get(mode, {}).get("max_hold", 12)
    k = 2
    purge_bars = max(fold_size // 4, k * max_hold)
    embargo_bars = max(fold_size // 8, k * max_hold)
    
    fold_times = []
    total_train_rows = 0
    
    from alphaforge.training.xgb_trainer import XGBoostTrainer
    import xgboost as xgb
    
    for fold in range(min_folds):
        train_end = (fold + 1) * fold_size
        val_start = train_end
        val_end = val_start + fold_size // 2
        if val_end >= n:
            break
        
        effective_train_end = train_end - purge_bars
        effective_val_start = val_start + embargo_bars
        
        if effective_train_end <= 0 or effective_val_start >= val_end:
            break
        
        X_train = X_clean[:effective_train_end]
        y_train = y_clean[:effective_train_end]
        X_val = X_clean[effective_val_start:val_end]
        y_val = y_clean[effective_val_start:val_end]
        
        if len(X_train) < 50 or len(X_val) < 10:
            break
        
        trainer = XGBoostTrainer(mode=mode)
        
        t0 = time.monotonic()
        fold_result = trainer.train(X_train, y_train)
        elapsed = time.monotonic() - t0
        
        dval = xgb.DMatrix(X_val)
        y_pred_prob = fold_result.model.predict(dval)
        y_pred = np.argmax(y_pred_prob, axis=1)
        val_acc = float(np.mean(y_pred == y_val))
        
        fold_times.append(elapsed)
        total_train_rows += len(X_train)
        
        print(f"    Fold {fold+1}: train={len(X_train):>5d}, "
              f"val={len(X_val):>4d}, acc={val_acc:.4f}, "
              f"training={elapsed:.3f}s", flush=True)
    
    times["xgb_training_total"] = sum(fold_times)
    times["xgb_training_per_fold"] = fold_times
    times["xgb_training_avg"] = np.mean(fold_times) if fold_times else 0
    times["total_train_rows"] = total_train_rows
    times["total_seconds"] = sum(times.get(k, 0) for k in ["features", "build_frame", "xgb_training_total"])
    
    print(f"  ─────────────────────────────────────", flush=True)
    print(f"  XGBoost total: {times['xgb_training_total']:.3f}s across {len(fold_times)} folds", flush=True)
    print(f"  XGBoost avg/fold: {times['xgb_training_avg']:.4f}s", flush=True)
    print(f"  ALL STAGES: {times['total_seconds']:.3f}s", flush=True)
    
    return times

# Run SCALP first (warm JIT), then report
scalp_times = profile_mode_stages("SCALP", "Run 1 — SCALP (post-JIT-warmup)")

print(f"\n\n{'='*60}", flush=True)
print(f"  FINAL PROFILE SUMMARY", flush=True)
print(f"{'='*60}", flush=True)
print(f"  Mode: SCALP (after JIT warmup)", flush=True)
print(f"  GPU: {GPU_PARAMS}", flush=True)
print(f"  Data: 3000 bars × 5 symbols", flush=True)
print(f"  Features: 61 cols", flush=True)
print(f"  Folds: 6", flush=True)
print(f"", flush=True)
print(f"  {'Stage':<35s} {'Time (s)':>10s} {'% of Total':>12s}", flush=True)
print(f"  {'─'*35} {'─'*10} {'─'*12}", flush=True)
total = scalp_times["total_seconds"]
for stage_key in ["features", "build_frame", "xgb_training_total"]:
    secs = scalp_times[stage_key]
    pct = secs / total * 100
    print(f"  {stage_key:<35s} {secs:>10.3f}s {pct:>11.1f}%", flush=True)
print(f"  {'─'*35} {'─'*10} {'─'*12}", flush=True)
print(f"  {'TOTAL':<35s} {total:>10.3f}s {100.0:>11.1f}%", flush=True)
print(f"", flush=True)
print(f"  Average XGBoost training per fold: {scalp_times['xgb_training_avg']:.4f}s", flush=True)
print(f"  Total train rows across all folds: {scalp_times['total_train_rows']}", flush=True)
print(f"  Throughput: {scalp_times['total_train_rows'] / scalp_times['xgb_training_total']:.0f} rows/s (GPU)", flush=True)

# Save
import json
_REPO_ROOT.joinpath("reports").mkdir(exist_ok=True)
with open(_REPO_ROOT / "reports" / "pipeline_profile_detailed.json", "w") as f:
    json.dump({"gpu": str(GPU_PARAMS), "scalp_times": scalp_times}, f, indent=2, default=str)
print(f"\n  Report: reports/pipeline_profile_detailed.json", flush=True)
