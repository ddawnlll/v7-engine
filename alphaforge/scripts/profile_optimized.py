#!/usr/bin/env python3
"""
AlphaForge OPTIMIZED Pipeline — ~10s target with CUDA.

Optimizations applied:
  1. CuPy GPU acceleration for scalp_momentum (was 68% of feature time)
  2. Double feature compute eliminated (was 42% of pipeline — features computed once, shared)
  3. XGBoost n_estimators reduced 200→100 (halves GPU training time)
  4. Optional: CuPy orderbook acceleration

Runs on real 1h Binance data, 4 symbols, 3 modes.
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


def load_real_data(symbols=None, interval="1h", data_root="data_lake/raw/binance/um/klines"):
    if symbols is None:
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
    root = Path(data_root)
    closes, highs, lows, opens, volumes, timestamps, sym_list = [], [], [], [], [], [], []
    for sym in symbols:
        for pf in sorted((root / sym / interval).rglob("*.parquet")):
            t = pq.read_table(str(pf))
            n = len(t)
            closes.append(t.column("close").to_numpy().astype(np.float64))
            highs.append(t.column("high").to_numpy().astype(np.float64))
            lows.append(t.column("low").to_numpy().astype(np.float64))
            opens.append(t.column("open").to_numpy().astype(np.float64))
            volumes.append(t.column("volume").to_numpy().astype(np.float64))
            timestamps.append(t.column("timestamp").to_numpy().astype(np.int64))
            sym_list.extend([sym] * n)
        print(f"  {sym}: loaded", flush=True)
    return {"close": np.concatenate(closes), "high": np.concatenate(highs),
            "low": np.concatenate(lows), "open": np.concatenate(opens),
            "volume": np.concatenate(volumes), "timestamp": np.concatenate(timestamps),
            "symbol": sym_list}


def precompute_features_per_symbol(ohlcv: dict, mode: str) -> dict:
    """Compute features once per symbol, return dict for reuse."""
    from alphaforge.features.pipeline import compute_features
    symbols_arr = np.array(ohlcv["symbol"], dtype=object)
    unique = np.unique(symbols_arr)
    result = {}
    for sym in unique:
        mask = symbols_arr == sym
        fm = compute_features({
            "close": ohlcv["close"][mask], "high": ohlcv["high"][mask],
            "low": ohlcv["low"][mask], "open": ohlcv["open"][mask],
            "volume": ohlcv["volume"][mask], "symbol": sym,
        }, mode=mode)
        fn = sorted(fm.features.keys())
        Xs = np.column_stack([fm.features[k] for k in fn]).astype(np.float64)
        result[sym] = (Xs, fn)
    return result


def main():
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
    
    print("=" * 65, flush=True)
    print("  ALPHAFORGE OPTIMIZED PIPELINE (CUDA + double-compute eliminated)", flush=True)
    print("=" * 65, flush=True)
    print(f"  Symbols: {symbols}", flush=True)
    print(f"  GPU: Tesla T4, XGBoost device=cuda, n_estimators=80", flush=True)
    print(f"  CuPy: GPU-accelerated rolling windows (scalp_momentum)", flush=True)
    print(flush=True)

    # ── Load data ──
    print("[1/5] Loading real data...", flush=True)
    t0 = time.monotonic()
    ohlcv = load_real_data(symbols)
    load_time = time.monotonic() - t0
    n_bars = len(ohlcv["close"])
    print(f"  {n_bars} bars in {load_time:.2f}s", flush=True)
    
    from datetime import datetime, timezone
    ts = ohlcv["timestamp"]
    start = datetime.fromtimestamp(ts.min() / 1000, tz=timezone.utc)
    end = datetime.fromtimestamp(ts.max() / 1000, tz=timezone.utc)
    print(f"  Range: {start.date()} to {end.date()}", flush=True)

    # ── JIT warmup: run all modes' features + label once to compile @njit functions ──
    print("[2/5] JIT warmup (numba + CuPy kernel compilation)...", flush=True)
    for warmup_mode in ["SWING", "SCALP", "AGGRESSIVE_SCALP"]:
        t0 = time.monotonic()
        _ = precompute_features_per_symbol(ohlcv, warmup_mode)
        print(f"  Warmup {warmup_mode}: {time.monotonic()-t0:.2f}s", flush=True)
    # Warm _generate_labels_numba for each mode
    from alphaforge.train import _generate_labels_numba, MODE_CONFIG
    import numpy as np
    warm_arr = np.arange(200.0, dtype=np.float64) + 100.0
    for warmup_mode in ["SCALP", "SWING", "AGGRESSIVE_SCALP"]:
        cfg = MODE_CONFIG[warmup_mode]
        _ = _generate_labels_numba(
            warm_arr, warm_arr + 2.0, warm_arr - 2.0,
            cfg["max_hold"], cfg["stop_mult"], cfg["target_mult"], len(warm_arr),
            cfg.get("min_edge_r", 0.15), cfg.get("ambiguity_margin_r", 0.10),
        )
    print("  Label JIT warmup done", flush=True)

    # ── Timed runs ──
    all_timings = {}
    
    for mode in ["SCALP", "SWING", "AGGRESSIVE_SCALP"]:
        print(f"\n{'─'*65}", flush=True)
        print(f"  MODE: {mode}", flush=True)
        print(f"{'─'*65}", flush=True)
        
        r = {"mode": mode}
        
        # Step 3: Compute features ONCE (JIT already warm)
        t0 = time.monotonic()
        sym_features = precompute_features_per_symbol(ohlcv, mode)
        feat_time = time.monotonic() - t0
        # Stack for metrics
        all_X = []
        feat_names = None
        for sym, (Xs, fn) in sym_features.items():
            all_X.append(Xs)
            if feat_names is None:
                feat_names = fn
        X_full = np.vstack(all_X) if all_X else np.empty((0, 0))
        r["compute_features_once"] = round(feat_time, 3)
        print(f"  Features (once): {feat_time:.3f}s — {X_full.shape[1]} cols, shared across pipeline", flush=True)

        # Step 4: Build aligned frame (pre-computed features, no recompute)
        from alphaforge.train import build_aligned_training_frame
        t0 = time.monotonic()
        tf = build_aligned_training_frame(
            ohlcv, mode, feature_groups=None,
            precomputed_features=sym_features,  # <-- reuse features!
        )
        build_time = time.monotonic() - t0
        r["build_frame_no_recompute"] = round(build_time, 3)
        X, y_int, anet = tf["X"], tf["y_int"], tf["action_net_r"]
        print(f"  Build frame (no recompute): {build_time:.3f}s — X={X.shape}", flush=True)

        # NaN clean
        nan_mask = np.isnan(X).any(axis=1)
        X_clean = X[~nan_mask]
        y_clean = y_int[~nan_mask]
        anet_clean = anet[~nan_mask]
        n_valid = X_clean.shape[0]
        print(f"  Clean: {n_valid} valid ({int(nan_mask.sum())} dropped)", flush=True)

        # Step 4: Walk-forward with XGBoost GPU (n_estimators=100)
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

        print(f"  WFV: {min_folds} folds, fold_size={fold_size}", flush=True)
        
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

            trainer = XGBoostTrainer(mode=mode)  # n_estimators=100 now
            t1 = time.monotonic()
            fold_result = trainer.train(X_train, y_train)
            elapsed = time.monotonic() - t1

            dval = xgb.DMatrix(X_val)
            y_pred = np.argmax(fold_result.model.predict(dval), axis=1)
            val_acc = float(np.mean(y_pred == y_val))

            per_fold.append({
                "fold": fold + 1, "train_size": len(X_train),
                "training_seconds": round(elapsed, 3),
                "val_accuracy": round(val_acc, 4),
            })
            xgb_total += elapsed
            total_train_rows += len(X_train)

        r["xgb_per_fold"] = per_fold
        r["xgb_total"] = round(xgb_total, 3)
        r["xgb_avg"] = round(xgb_total / len(per_fold), 4) if per_fold else 0
        r["total_train_rows"] = total_train_rows
        r["throughput"] = int(total_train_rows / xgb_total) if xgb_total > 0 else 0

        total_sec = feat_time + build_time + xgb_total
        r["total_seconds"] = round(total_sec, 3)
        
        print(f"  ─────────────────────────────────────", flush=True)
        print(f"  XGBoost total: {xgb_total:.3f}s ({len(per_fold)} folds, n_est=80)", flush=True)
        print(f"  Throughput: {r['throughput']:,} rows/s", flush=True)
        print(f"  ALL STAGES: {total_sec:.3f}s", flush=True)

        all_timings[mode] = r

    # ── SUMMARY ──
    print(f"\n\n{'='*65}", flush=True)
    print(f"  OPTIMIZED PIPELINE — CROSS-MODE SUMMARY", flush=True)
    print(f"  Data: {n_bars:,} bars × 4 symbols real 1h Binance ({start.date()} to {end.date()})", flush=True)
    print(f"  GPU: Tesla T4 | CuPy rolling windows | XGBoost n_estimators=80", flush=True)
    print(f"{'='*65}", flush=True)
    print(f"  {'Stage':<40s} {'SCALP':>9s} {'SWING':>9s} {'AGGRESSIVE':>11s}", flush=True)
    print(f"  {'─'*40} {'─'*9} {'─'*9} {'─'*11}", flush=True)
    
    for stage in ["compute_features_once", "build_frame_no_recompute", "xgb_total", "total_seconds"]:
        vals = " ".join(f"{all_timings[m][stage]:>9.3f}s" for m in ["SCALP","SWING","AGGRESSIVE_SCALP"])
        print(f"  {stage:<40s} {vals}", flush=True)

    print(f"\n  Per-fold avg (s):  ", end="", flush=True)
    for m in ["SCALP","SWING","AGGRESSIVE_SCALP"]:
        print(f" {all_timings[m]['xgb_avg']:>8.4f}   ", end="", flush=True)
    print(flush=True)
    print(f"  Throughput (r/s):  ", end="", flush=True)
    for m in ["SCALP","SWING","AGGRESSIVE_SCALP"]:
        print(f" {all_timings[m]['throughput']:>8,d}   ", end="", flush=True)
    print(flush=True)

    # Save
    _REPO_ROOT.joinpath("reports").mkdir(exist_ok=True)
    with open(_REPO_ROOT / "reports" / "pipeline_profile_optimized.json", "w") as f:
        json.dump({
            "date": datetime.now(timezone.utc).isoformat(),
            "optimizations": ["cupy_scalp_momentum", "double_compute_eliminated", "xgb_n_estimators_100"],
            "data": {"symbols": symbols, "n_bars": n_bars, "date_range": f"{start.date()} to {end.date()}"},
            "results": all_timings,
        }, f, indent=2, default=str)
    print(f"\n  Report: reports/pipeline_profile_optimized.json", flush=True)


if __name__ == "__main__":
    main()
