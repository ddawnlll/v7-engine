#!/usr/bin/env python3
"""
Comprehensive pipeline benchmark — measures each component individually.
Runs CPU vs GPU for all GPU-capable steps.
Usage:
    python3 scripts/bench_full_pipeline.py
    ALPHAFORGE_XGB_DEVICE=cpu python3 scripts/bench_full_pipeline.py  # force CPU
"""
import json, os, sys, time, warnings, textwrap
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, ROOT)
sys.path.insert(0, ROOT + "/simulation")
sys.path.insert(0, ROOT + "/alphaforge/src")
sys.path.insert(0, ROOT + "/lib")

# ── Config ──────────────────────────────────────────────────────────────
N_SYMBOLS = 10
N_BARS = 2160         # research run size
N_FEATURES = 14       # research run feature count
N_CLASSES = 3
BATCH_SIZES = [100, 1000, 10000, 50000, 100000, 500000]

results = {}

print("=" * 65)
print("V7 ENGINE — FULL PIPELINE BENCHMARK")
print("=" * 65)

# ── 1. Feature computation (CPU-bound pandas/numpy) ──
print("\n[1] Feature computation (10 sym × 2160 bars, 14 features)")
from alphaforge.training.xgb_trainer import GPU_PARAMS
print(f"    GPU_PARAMS detected: {GPU_PARAMS}")

times = []
for _ in range(5):
    data_chunks = []
    for sym in range(N_SYMBOLS):
        price = 100.0
        o = np.empty(N_BARS)
        h = np.empty(N_BARS)
        l = np.empty(N_BARS)
        c = np.empty(N_BARS)
        v = np.empty(N_BARS)
        for i in range(N_BARS):
            ret = np.random.randn() * 0.02
            price *= (1.0 + ret)
            o[i] = price * (1.0 + np.random.randn() * 0.005)
            h[i] = price * (1.0 + abs(np.random.randn()) * 0.01)
            l[i] = price * (1.0 - abs(np.random.randn()) * 0.01)
            c[i] = price
            v[i] = abs(np.random.randn()) * 1000
        data_chunks.append(pd.DataFrame({
            "open": o, "high": h, "low": l, "close": c, "volume": v,
            "symbol": f"SYM{sym}"
        }))
    data = pd.concat(data_chunks, ignore_index=True)

    t0 = time.perf_counter()
    # Compute features like research_run
    X_parts, y_parts = [], []
    for symbol in data["symbol"].unique():
        s = data[data["symbol"] == symbol].copy()
        o, h, l, c, v = (s["open"].values, s["high"].values, s["low"].values,
                         s["close"].values, s["volume"].values)
        n = len(c)
        ret = np.diff(c, prepend=c[0]) / c
        ma5 = np.convolve(c, np.ones(5)/5, mode="same")
        ma20 = np.convolve(c, np.ones(20)/20, mode="same")
        ma5[0:4] = np.nan; ma20[0:19] = np.nan
        ma5_ret = np.diff(ma5, prepend=ma5[0]) / ma5
        ma20_ret = np.diff(ma20, prepend=ma20[0]) / ma20
        vol20 = np.convolve(v, np.ones(20)/20, mode="same")
        vol20[0:19] = np.nan
        tr = np.maximum(h - l,
                        np.maximum(np.abs(h - np.roll(c, 1)),
                                   np.abs(l - np.roll(c, 1))))
        tr[0] = h[0] - l[0]
        atr14 = np.convolve(tr, np.ones(14)/14, mode="same")
        atr14[0:13] = np.nan
        pos_ratio_10 = np.convolve((ret > 0).astype(float), np.ones(10)/10, mode="same")
        pos_ratio_10[0:9] = np.nan

        feat = np.column_stack([
            ret, ma5_ret, ma20_ret, c / ma20 - 1, (h - l) / c,
            v / vol20, atr14 / c, np.maximum(0, ret), np.minimum(0, ret),
            pos_ratio_10, ma5_ret - ma20_ret,
            (c - ma20) / atr14,
            np.abs(np.diff(c, prepend=c[0])) / atr14,
            np.zeros(n),
        ])
        fwd_ret = np.full(n, np.nan)
        fwd_ret[:-5] = c[5:] / c[:-5] - 1
        label = np.full(n, "NO_TRADE", dtype="U20")
        label[fwd_ret > 0.002] = "LONG_NOW"
        label[fwd_ret < -0.002] = "SHORT_NOW"
        X_parts.append(feat)
        y_parts.append(label)

    X = np.vstack(X_parts).astype(np.float64)
    y = np.concatenate(y_parts)
    valid = ~(np.isnan(X).any(axis=1) | np.isinf(X).any(axis=1))
    warmup = 60
    cumul = 0
    for _s in data["symbol"].unique():
        cnt = int((data["symbol"] == _s).sum())
        valid[max(cumul, cumul + warmup):min(cnt, cumul + cnt)] = True
        cumul += cnt
    X, y = X[valid], y[valid]
    times.append(time.perf_counter() - t0)

feat_time = float(np.median(times))
results["feature_computation_s"] = feat_time
n_samples = len(X)
results["n_samples"] = int(n_samples)
results["n_features"] = X.shape[1]
print(f"    {n_samples} samples, {X.shape[1]} features")
print(f"    Median: {feat_time:.3f}s")

# ── 2. XGBoost Training (CPU vs GPU) ──
print("\n[2] XGBoost Training")

for device_mode, device_label in [("cpu", "CPU"), ("cuda", "GPU")]:
    old_env = os.environ.get("ALPHAFORGE_XGB_DEVICE", "")
    os.environ["ALPHAFORGE_XGB_DEVICE"] = device_mode
    import importlib
    from alphaforge.training import xgb_trainer as xt
    importlib.reload(xt)

    split = int(n_samples * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    times = []
    for fold in range(3):
        trainer = xt.XGBoostTrainer(mode="SCALP", random_seed=42 + fold)
        t0 = time.perf_counter()
        result = trainer.train(X_train, y_train)
        times.append(time.perf_counter() - t0)

    med_time = float(np.median(times))
    results[f"train_{device_mode}_s"] = med_time
    print(f"    {device_label}: median={med_time:.3f}s  (3 folds)")
    os.environ["ALPHAFORGE_XGB_DEVICE"] = old_env

# Speedup
if results.get("train_cpu_s", 0) > 0 and results.get("train_gpu_s", 0) > 0:
    results["train_gpu_speedup_x"] = round(results["train_cpu_s"] / results["train_gpu_s"], 2)
    print(f"    GPU speedup: {results['train_gpu_speedup_x']}x")

# ── 3. Batch simulation (CPU vs GPU) ──
print("\n[3] Batch path simulation")
from simulation.engine.cuda_kernels import (
    prepare_batch_arrays, run_batch_gpu, run_batch_cpu, is_cuda_available
)
print(f"    CUDA available: {is_cuda_available()}")

for n in BATCH_SIZES:
    # Generate signals
    rng = np.random.default_rng(42)
    sigs = []
    for _ in range(n):
        d = "LONG" if rng.random() > 0.5 else "SHORT"
        ep = rng.uniform(50, 200)
        rp = rng.uniform(0.01, 0.05)
        if d == "LONG":
            sp, tp = ep * (1 - rp), ep * (1 + rp * rng.uniform(1.5, 3.0))
        else:
            sp, tp = ep * (1 + rp), ep * (1 - rp * rng.uniform(1.5, 3.0))
        nb = int(rng.integers(5, 31))
        sigs.append({
            "direction": d, "entry_price": ep, "stop_price": sp,
            "target_price": tp, "entry_risk": sp - ep if d == "LONG" else ep - sp,
            "close_price": ep, "available_bars": nb,
            "highs": (ep + rng.uniform(0, 0.02 * ep, nb)).tolist(),
            "lows": (ep - rng.uniform(0, 0.02 * ep, nb)).tolist(),
        })

    arr = prepare_batch_arrays(sigs)
    for _ in range(2):
        run_batch_cpu(arr)
        run_batch_gpu(arr)

    cpu_t = float(np.median([time.perf_counter() - t0 for _ in range(5)
                             for t0 in [time.perf_counter()] + [run_batch_cpu(arr)] and []]))
    # Fix measurement
    cpu_ts = []
    for _ in range(5):
        t0 = time.perf_counter()
        run_batch_cpu(arr)
        cpu_ts.append(time.perf_counter() - t0)
    cpu_med = float(np.median(cpu_ts))

    gpu_ts = []
    for _ in range(5):
        t0 = time.perf_counter()
        run_batch_gpu(arr)
        gpu_ts.append(time.perf_counter() - t0)
    gpu_med = float(np.median(gpu_ts))

    results.setdefault("batch_cpu_s", {})[str(n)] = cpu_med
    results.setdefault("batch_gpu_s", {})[str(n)] = gpu_med
    results.setdefault("batch_speedup_x", {})[str(n)] = round(cpu_med / gpu_med, 2) if gpu_med > 0 else float('inf')
    print(f"    n={n:>7,}  CPU={cpu_med:.4f}s  GPU={gpu_med:.4f}s  speedup={cpu_med/gpu_med:.1f}x")

# ── 4. Results summary ──
print("\n" + "=" * 65)
print("BENCHMARK SUMMARY")
print("=" * 65)
for k, v in results.items():
    print(f"  {k}: {v}")

# Save
out_path = "reports/bench_full_pipeline.json"
os.makedirs("reports", exist_ok=True)
with open(out_path, "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\n✅ Saved: {out_path}")
