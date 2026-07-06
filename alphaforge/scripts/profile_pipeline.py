#!/usr/bin/env python3
"""
AlphaForge Pipeline Profiler.

Runs the full training pipeline with stage-level timing instrumentation.
Profiles all 3 modes (SWING, SCALP, AGGRESSIVE_SCALP) with synthetic data
and reports per-stage, per-fold, and total wall-clock seconds.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC_PATH = str(_REPO_ROOT / "alphaforge" / "src")
for p in [_SRC_PATH, str(_REPO_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np

# Force GPU detection before imports
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

from alphaforge.training.xgb_trainer import GPU_PARAMS
print(f"[GPU] XGBoost params: {GPU_PARAMS}", flush=True)


class Timer:
    """Simple hierarchical profiler."""
    def __init__(self):
        self.stages: OrderedDict[str, float] = OrderedDict()
        self._stack: list[tuple[str, float]] = []
    
    def start(self, name: str):
        self._stack.append((name, time.monotonic()))
    
    def stop(self, name: str | None = None):
        if not self._stack:
            return
        n, t0 = self._stack.pop()
        elapsed = time.monotonic() - t0
        key = f"{'  ' * len(self._stack)}{n}"
        self.stages[key] = elapsed
        return elapsed
    
    def report(self) -> str:
        lines = ["\n" + "=" * 60, "  PIPELINE TIMING PROFILE", "=" * 60]
        total = sum(self.stages.values())
        for stage, secs in self.stages.items():
            pct = secs / total * 100 if total > 0 else 0
            bar = "█" * int(pct / 2) + "░" * (50 - int(pct / 2))
            lines.append(f"  {stage:<55s} {secs:>8.2f}s {pct:>5.1f}%")
        lines.append(f"  {'─' * 55} {'─'*8} {'─'*6}")
        lines.append(f"  {'TOTAL':<55s} {total:>8.2f}s {100.0:>5.1f}%")
        lines.append("=" * 60)
        return "\n".join(lines)


def profile_mode(mode: str, n_bars: int = 3000, n_symbols: int = 5) -> dict:
    """Profile one mode's full pipeline and return per-stage timing."""
    t = Timer()
    
    print(f"\n{'#'*60}")
    print(f"  PROFILING MODE: {mode}")
    print(f"  Data: {n_bars} bars × {n_symbols} symbols (synthetic)")
    print(f"{'#'*60}")
    
    # ── Step 1: Data generation ──
    t.start("1. generate_synthetic_ohlcv")
    from alphaforge.train import generate_synthetic_ohlcv
    ohlcv = generate_synthetic_ohlcv(
        n_bars=n_bars,
        symbols=tuple(f"SYM{i}" for i in range(n_symbols)),
        random_seed=42,
    )
    t.stop()
    print(f"  Data: {len(ohlcv['close'])} bars, {len(set(ohlcv['symbol']))} symbols")
    
    # ── Step 2: Feature computation (per symbol) ──
    t.start("2. compute_all_features")
    from alphaforge.train import compute_all_features
    X_feat, feat_names = compute_all_features(ohlcv, mode)
    t.stop()
    print(f"  Features: {X_feat.shape[1]} cols, {X_feat.shape[0]} rows")
    
    # ── Step 3: Label generation (per symbol, numba) ──
    t.start("3. generate_labels")
    from alphaforge.train import generate_labels
    int_labels, net_r, label_metrics = generate_labels(ohlcv, mode)
    t.stop()
    print(f"  Labels: {len(int_labels)} samples, dist={label_metrics['label_distribution']}")
    
    # ── Step 4: Build aligned training frame ──
    t.start("4. build_aligned_training_frame")
    from alphaforge.train import build_aligned_training_frame
    tf = build_aligned_training_frame(ohlcv, mode, feature_groups=None)
    X = tf["X"]
    y_int = tf["y_int"]
    anet = tf["action_net_r"]
    feat_names = tf["feature_names"]
    t.stop()
    print(f"  Aligned: X={X.shape}, y={y_int.shape}")
    
    # ── Step 5: NaN cleaning ──
    t.start("5. nan_clean")
    nan_mask = np.isnan(X).any(axis=1)
    X_clean = X[~nan_mask]
    y_clean = y_int[~nan_mask]
    anet_clean = anet[~nan_mask]
    t.stop()
    print(f"  Clean: {X_clean.shape[0]} valid ({int(nan_mask.sum())} dropped)")
    
    # ── Step 6: Walk-forward validation (6 folds, each trains XGBoost) ──
    t.start("6. walk_forward_validate")
    from alphaforge.train import walk_forward_validate
    wfv_results = walk_forward_validate(
        X_clean, y_clean, np.zeros(len(y_clean), dtype=np.float64),
        mode, min_folds=6, action_net_r=anet_clean,
    )
    t.stop()
    print(f"  WFV: {len(wfv_results)} folds completed")
    
    # ── Step 7: Metrics collection ──
    t.start("7. collect_metrics")
    from alphaforge.train import collect_metrics
    metrics = collect_metrics(wfv_results, X_clean, feat_names, mode=mode)
    t.stop()
    
    # ── Step 8: Overfit detection ──
    t.start("8. overfit_detection")
    from alphaforge.train import compute_overfit_gap, compute_inter_fold_consistency
    overfit = compute_overfit_gap(wfv_results)
    consistency = compute_inter_fold_consistency(wfv_results)
    t.stop()
    
    print(t.report())
    
    return {
        "mode": mode,
        "n_bars": n_bars,
        "n_symbols": n_symbols,
        "n_features": X_clean.shape[1],
        "n_samples": X_clean.shape[0],
        "stages": dict(t.stages),
        "total_seconds": sum(t.stages.values()),
        "per_fold_training_seconds": [
            r.get("training_duration_seconds", 0.0) for r in wfv_results
        ],
        "metrics": {
            "accuracy": metrics.get("accuracy"),
            "net_expectancy_r": metrics.get("net_expectancy_r"),
            "total_net_R": metrics.get("total_net_R"),
            "pbo_risk": metrics.get("pbo_risk"),
        },
        "n_folds": len(wfv_results),
    }


def main():
    print(f"AlphaForge Pipeline Profiler @ {datetime.now(timezone.utc).isoformat()}")
    print(f"GPU: {GPU_PARAMS}")
    print(f"Python: {sys.version}")
    print()
    
    all_results = {}
    
    # Detailed per-stage profile on SCALP
    for mode in ["SCALP", "SWING", "AGGRESSIVE_SCALP"]:
        all_results[mode] = profile_mode(mode, n_bars=3000, n_symbols=5)
    
    # ── Summary ──
    print("\n\n" + "=" * 70)
    print("  CROSS-MODE PERFORMANCE SUMMARY")
    print("=" * 70)
    print(f"  {'Mode':<20} {'Total (s)':>10} {'Training (s)':>14} {'Folds':>6} {'Feat':>6} {'Samples':>8}")
    print(f"  {'-'*20} {'-'*10} {'-'*14} {'-'*6} {'-'*6} {'-'*8}")
    
    for mode, res in all_results.items():
        total = res["total_seconds"]
        fold_times = res.get("per_fold_training_seconds", [])
        train_total = sum(fold_times)
        n_folds = len(fold_times)
        print(f"  {mode:<20} {total:>10.2f}s {train_total:>14.2f}s {n_folds:>6d} "
              f"{res['n_features']:>6d} {res['n_samples']:>8d}")
    
    # Find the bottleneck stage across all modes
    print("\n  TOP BOTTLENECKS (all modes):")
    bottlenecks = []
    for mode, res in all_results.items():
        for stage, secs in res["stages"].items():
            bottlenecks.append((secs, mode, stage))
    bottlenecks.sort(reverse=True)
    for secs, mode, stage in bottlenecks[:10]:
        print(f"    {mode:<20s} {stage:<55s} {secs:>8.2f}s")
    
    # Save report
    report_path = _REPO_ROOT / "reports" / "pipeline_profile.json"
    _REPO_ROOT.joinpath("reports").mkdir(exist_ok=True)
    with open(report_path, "w") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gpu": str(GPU_PARAMS),
            "results": all_results,
        }, f, indent=2, default=str)
    
    print(f"\n  Profile report saved: {report_path}")


if __name__ == "__main__":
    main()
