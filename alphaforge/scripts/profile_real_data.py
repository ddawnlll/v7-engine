#!/usr/bin/env python3
"""
AlphaForge Real-Data Pipeline Profiler.

Loads real 1h Binance data for 4 symbols from data_lake,
runs full pipeline (features, labels, 6-fold WFV XGBoost GPU),
and reports per-stage timing and GPU throughput.
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
import pyarrow.parquet as pq

# ── Step 1: Load real data from data_lake ──
def load_binance_vision_data(
    symbols: list[str],
    interval: str = "1h",
    data_root: str = "data_lake/raw/binance/um/klines",
) -> dict:
    """Load real 1h Binance Vision data from monthly parquet files."""
    root = Path(data_root)
    closes, highs, lows, opens, volumes = [], [], [], [], []
    timestamps, sym_list = [], []

    for sym in symbols:
        sym_dir = root / sym / interval
        if not sym_dir.exists():
            print(f"  WARNING: no data dir for {sym} at {sym_dir}")
            continue
        parquet_files = sorted(sym_dir.rglob("*.parquet"))
        if not parquet_files:
            print(f"  WARNING: no parquet files for {sym}")
            continue
        for pf in parquet_files:
            t = pq.read_table(str(pf))
            n = len(t)
            closes.append(t.column("close").to_numpy().astype(np.float64))
            highs.append(t.column("high").to_numpy().astype(np.float64))
            lows.append(t.column("low").to_numpy().astype(np.float64))
            opens.append(t.column("open").to_numpy().astype(np.float64))
            volumes.append(t.column("volume").to_numpy().astype(np.float64))
            timestamps.append(t.column("timestamp").to_numpy().astype(np.int64))
            sym_list.extend([sym] * n)
        print(f"  {sym}: loaded {len(parquet_files)} files")

    return {
        "close": np.concatenate(closes),
        "high": np.concatenate(highs),
        "low": np.concatenate(lows),
        "open": np.concatenate(opens),
        "volume": np.concatenate(volumes),
        "timestamp": np.concatenate(timestamps),
        "symbol": sym_list,
    }


# ── Step 2: Profile ──
def main():
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
    interval = "1h"
    
    print("=" * 60, flush=True)
    print("  AlphaForge REAL DATA Pipeline Profiler", flush=True)
    print("=" * 60, flush=True)
    print(f"  Symbols: {symbols}", flush=True)
    print(f"  Interval: {interval}", flush=True)
    print(f"  GPU: Tesla T4 (XGBoost device=cuda)", flush=True)
    print(flush=True)

    # Load data
    print("[1/5] Loading real Binance 1h data...", flush=True)
    t0 = time.monotonic()
    ohlcv = load_binance_vision_data(symbols, interval)
    load_time = time.monotonic() - t0
    n_bars = len(ohlcv["close"])
    n_syms = len(set(ohlcv["symbol"]))
    print(f"  {n_bars} bars across {n_syms} symbols in {load_time:.2f}s", flush=True)
    
    # Date range
    ts = ohlcv["timestamp"]
    from datetime import datetime, timezone
    start = datetime.fromtimestamp(ts.min() / 1000, tz=timezone.utc)
    end = datetime.fromtimestamp(ts.max() / 1000, tz=timezone.utc)
    print(f"  Date range: {start.date()} to {end.date()}", flush=True)

    # JIT warmup — run compute_features once on each mode
    print("\n[2/5] JIT warmup (numba compilation)...", flush=True)
    from alphaforge.train import compute_all_features
    for mode in ["SWING", "SCALP", "AGGRESSIVE_SCALP"]:
        t0 = time.monotonic()
        _ = compute_all_features(ohlcv, mode)
        print(f"  Warmup {mode}: {time.monotonic()-t0:.2f}s", flush=True)
    print("  JIT warmup complete", flush=True)

    # Profile each mode
    results = {}
    for mode in ["SCALP", "SWING", "AGGRESSIVE_SCALP"]:
        print(f"\n{'─'*60}", flush=True)
        print(f"  PROFILING: {mode} — {n_syms} symbols, {n_bars} bars real data", flush=True)
        print(f"{'─'*60}", flush=True)
        
        r = {"mode": mode, "symbols": n_syms, "bars": n_bars}

        # Features
        t0 = time.monotonic()
        X_feat, feat_names = compute_all_features(ohlcv, mode)
        r["compute_features"] = round(time.monotonic() - t0, 3)
        print(f"  compute_features: {r['compute_features']:.3f}s ({X_feat.shape[1]} cols)", flush=True)

        # Build aligned frame
        from alphaforge.train import build_aligned_training_frame
        t0 = time.monotonic()
        tf = build_aligned_training_frame(ohlcv, mode)
        r["build_frame"] = round(time.monotonic() - t0, 3)
        X, y_int, anet = tf["X"], tf["y_int"], tf["action_net_r"]
        print(f"  build_frame: {r['build_frame']:.3f}s (X={X.shape})", flush=True)

        # NaN clean
        nan_mask = np.isnan(X).any(axis=1)
        X_clean = X[~nan_mask]
        y_clean = y_int[~nan_mask]
        anet_clean = anet[~nan_mask]
        n_valid = X_clean.shape[0]
        n_dropped = int(nan_mask.sum())
        print(f"  nan_clean: {n_valid} valid ({n_dropped} dropped)", flush=True)

        # Walk-forward validation (6 folds, XGBoost on GPU)
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

        print(f"  WFV: {min_folds} folds, fold_size={fold_size}, purge={purge_bars}, embargo={embargo_bars}", flush=True)
        
        per_fold = []
        xgb_total = 0.0
        total_train_rows = 0

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
            xgb_total += elapsed
            total_train_rows += len(X_train)

            print(f"    Fold {fold+1}: train={len(X_train):>6d}, val={len(X_val):>6d}, "
                  f"acc={val_acc:.4f}, training={elapsed:.3f}s", flush=True)

        r["xgb_per_fold"] = per_fold
        r["xgb_total"] = round(xgb_total, 3)
        r["xgb_avg"] = round(xgb_total / len(per_fold), 4) if per_fold else 0
        r["total_train_rows"] = total_train_rows
        r["throughput_rows_per_sec"] = int(total_train_rows / xgb_total) if xgb_total > 0 else 0
        r["total_seconds"] = round(r["compute_features"] + r["build_frame"] + xgb_total, 3)

        print(f"  ─────────────────────────────────────", flush=True)
        print(f"  XGBoost total: {xgb_total:.3f}s across {len(per_fold)} folds", flush=True)
        print(f"  XGBoost avg: {r['xgb_avg']:.4f}s/fold", flush=True)
        print(f"  Throughput: {r['throughput_rows_per_sec']:,} rows/s", flush=True)
        print(f"  ALL STAGES: {r['total_seconds']:.3f}s", flush=True)

        results[mode] = r

    # ── Summary ──
    print(f"\n\n{'='*70}", flush=True)
    print(f"  REAL DATA — CROSS-MODE GPU PROFILE SUMMARY", flush=True)
    print(f"  Data: {n_bars:,} bars × {n_syms} symbols real 1h Binance", flush=True)
    print(f"  Range: {start.date()} to {end.date()}", flush=True)
    print(f"  GPU: Tesla T4, XGBoost device=cuda tree_method=hist", flush=True)
    print(f"{'='*70}", flush=True)
    print(f"  {'Stage':<40s} {'SCALP':>9s} {'SWING':>9s} {'AGGRESSIVE':>11s}", flush=True)
    print(f"  {'─'*40} {'─'*9} {'─'*9} {'─'*11}", flush=True)
    
    for stage in ["compute_features", "build_frame", "xgb_total", "total_seconds"]:
        vals = " ".join(f"{results[m][stage]:>9.3f}s" for m in ["SCALP","SWING","AGGRESSIVE_SCALP"])
        print(f"  {stage:<40s} {vals}", flush=True)

    print(f"\n  Per-fold avg (s):  ", end="", flush=True)
    for m in ["SCALP","SWING","AGGRESSIVE_SCALP"]:
        print(f" {results[m]['xgb_avg']:>8.4f}   ", end="", flush=True)
    print(flush=True)

    print(f"  Throughput (r/s):  ", end="", flush=True)
    for m in ["SCALP","SWING","AGGRESSIVE_SCALP"]:
        print(f" {results[m]['throughput_rows_per_sec']:>8,d}   ", end="", flush=True)
    print(flush=True)

    # Save
    _REPO_ROOT.joinpath("reports").mkdir(exist_ok=True)
    with open(_REPO_ROOT / "reports" / "pipeline_profile_real_data.json", "w") as f:
        json.dump({
            "date": datetime.now(timezone.utc).isoformat(),
            "data": {"symbols": symbols, "interval": interval, "n_bars": n_bars, "n_symbols": n_syms,
                     "date_range": f"{start.date()} to {end.date()}"},
            "results": results,
        }, f, indent=2, default=str)
    print(f"\n  Report: reports/pipeline_profile_real_data.json", flush=True)


if __name__ == "__main__":
    main()
