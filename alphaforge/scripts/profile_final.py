#!/usr/bin/env python3
"""
AlphaForge Pipeline — definitive GPU profile with JIT warmup.
All times are post-JIT-compilation (production representative).
"""

from __future__ import annotations

import os, sys, time, json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC_PATH = str(_REPO_ROOT / "alphaforge" / "src")
for p in [_SRC_PATH, str(_REPO_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ["CUDA_VISIBLE_DEVICES"] = "0"
import numpy as np

# Generate data once
from alphaforge.train import generate_synthetic_ohlcv
ohlcv = generate_synthetic_ohlcv(n_bars=3000, symbols=("S0","S1","S2","S3","S4"), random_seed=42)

# ── JIT warmup: run ALL numba-heavy paths before timing ──
print("=== JIT warmup ===", flush=True)
from alphaforge.features.pipeline import compute_features
from alphaforge.train import compute_all_features, _generate_labels_numba
import numba

# Force @njit compilation by running on small data in each mode
for mode in ["SWING", "SCALP", "AGGRESSIVE_SCALP"]:
    t0 = time.monotonic()
    _ = compute_all_features(ohlcv, mode)
    print(f"  Warmup {mode}: {time.monotonic()-t0:.2f}s", flush=True)
print("  Warmup complete", flush=True)

# ── Timed runs (JIT already compiled) ──
results = {}
for mode in ["SCALP", "SWING", "AGGRESSIVE_SCALP"]:
    print(f"\n{'='*60}", flush=True)
    print(f"  PROFILING: {mode}", flush=True)
    print(f"{'='*60}", flush=True)

    t = {"mode": mode}

    t0 = time.monotonic()
    X_feat, feat_names = compute_all_features(ohlcv, mode)
    t["compute_features"] = round(time.monotonic() - t0, 3)

    from alphaforge.train import build_aligned_training_frame, walk_forward_validate, collect_metrics
    t0 = time.monotonic()
    tf = build_aligned_training_frame(ohlcv, mode)
    t["build_frame"] = round(time.monotonic() - t0, 3)

    X, y_int, anet = tf["X"], tf["y_int"], tf["action_net_r"]
    nan_mask = np.isnan(X).any(axis=1)
    X_clean = X[~nan_mask]
    y_clean = y_int[~nan_mask]
    anet_clean = anet[~nan_mask]

    # Per-fold breakdown
    from alphaforge.train import MODE_CONFIG
    from alphaforge.training.xgb_trainer import XGBoostTrainer
    import xgboost as xgb

    n = len(X_clean)
    min_folds = 6
    fold_size = n // (min_folds + 1)
    max_hold = MODE_CONFIG.get(mode, {}).get("max_hold", 12)
    k = 2
    purge_bars = max(fold_size // 4, k * max_hold)
    embargo_bars = max(fold_size // 8, k * max_hold)

    per_fold = []
    t["xgb_total"] = 0.0
    t0_all = time.monotonic()

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
        t1 = time.monotonic()
        fold_result = trainer.train(X_train, y_train)
        elapsed = time.monotonic() - t1

        dval = xgb.DMatrix(X_val)
        y_pred = np.argmax(fold_result.model.predict(dval), axis=1)
        val_acc = float(np.mean(y_pred == y_val))

        per_fold.append({
            "fold": fold + 1, "train_size": len(X_train), "val_size": len(X_val),
            "val_accuracy": round(val_acc, 4), "training_seconds": round(elapsed, 3),
        })
        t["xgb_total"] += elapsed

    t["xgb_per_fold"] = per_fold
    t["xgb_avg"] = round(t["xgb_total"] / len(per_fold), 4) if per_fold else 0
    t["total_seconds"] = round(sum(v for k, v in t.items() if isinstance(v, (int, float)) and k != "xgb_total"), 3)
    results[mode] = t

# ── Summary ──
print("\n\n" + "=" * 70)
print("  FINAL GPU PROFILE SUMMARY (JIT-warmed)")
print("=" * 70)
print(f"  GPU: Tesla T4, XGBoost device=cuda tree_method=hist")
print(f"  Data: 3000 bars × 5 symbols (synthetic)")
print(f"  Features: 61 per mode")
print(f"")
print(f"  {'Stage':<40s} {'SCALP':>8s} {'SWING':>8s} {'AGGRESSIVE':>10s}")
print(f"  {'─'*40} {'─'*8} {'─'*8} {'─'*10}")

for stage in ["compute_features", "build_frame"]:
    vals = " ".join(f"{results[m][stage]:>8.3f}s" for m in ["SCALP","SWING","AGGRESSIVE_SCALP"])
    print(f"  {stage:<40s} {vals}")

# XGBoost per-fold
print(f"  {'xgb_training (6 folds)':<40s}", end="")
for m in ["SCALP","SWING","AGGRESSIVE_SCALP"]:
    print(f" {results[m]['xgb_total']:>7.3f}s ", end="")
print()

print(f"  {'Avg per fold':<40s}", end="")
for m in ["SCALP","SWING","AGGRESSIVE_SCALP"]:
    print(f" {results[m]['xgb_avg']:>7.4f}s ", end="")
print()

# Totals
print(f"  {'─'*40} {'─'*8} {'─'*8} {'─'*10}")
totals = " ".join(f"{results[m]['total_seconds'] + results[m]['xgb_total']:>8.3f}s" for m in ["SCALP","SWING","AGGRESSIVE_SCALP"])
print(f"  {'TOTAL':<40s} {totals}")
print()

# Per-fold detail
print(f"  Per-fold XGBoost training:")
for m in ["SCALP", "SWING", "AGGRESSIVE_SCALP"]:
    print(f"    {m}: ", end="")
    for pf in results[m]["xgb_per_fold"]:
        print(f"F{pf['fold']}={pf['training_seconds']:.3f}s ({pf['train_size']} rows)  ", end="")
    print(f"  total={results[m]['xgb_total']:.3f}s")

# GPU utilization hint
print(f"\n  GPU throughput: ", end="")
for m in ["SCALP", "SWING", "AGGRESSIVE_SCALP"]:
    total_rows = sum(pf["train_size"] for pf in results[m]["xgb_per_fold"])
    throughput = total_rows / results[m]["xgb_total"]
    print(f"{m}: {throughput:.0f} rows/s  ", end="")
print()

# Save
_REPO_ROOT.joinpath("reports").mkdir(exist_ok=True)
with open(_REPO_ROOT / "reports" / "pipeline_profile_final.json", "w") as f:
    json.dump({"results": results}, f, indent=2, default=str)
print(f"\n  Report saved: reports/pipeline_profile_final.json")
