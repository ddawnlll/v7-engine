"""Benchmark: build_indicator_snapshot vs precompute+extract.

Shows the speedup from computing all indicators in one vectorized pass
vs recomputing from scratch for each growing window.
"""

from __future__ import annotations

import time
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime.services.indicator_snapshot import build_indicator_snapshot


def make_frame(n_bars: int) -> pd.DataFrame:
    """Create a synthetic OHLCV frame."""
    rng = np.random.default_rng(42)
    closes = 100.0 + np.cumsum(rng.normal(0, 0.5, n_bars))
    highs = closes + np.abs(rng.normal(0, 0.3, n_bars))
    lows = closes - np.abs(rng.normal(0, 0.3, n_bars))
    opens = closes + rng.normal(0, 0.2, n_bars)
    volumes = np.abs(rng.normal(1000, 200, n_bars))
    ts = pd.date_range("2024-01-01", periods=n_bars, freq="1h", tz="UTC")

    return pd.DataFrame({
        "open_time": ts,
        "close_time": ts + pd.Timedelta(hours=1),
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
        "trades": np.random.randint(100, 1000, n_bars),
        "quote_volume": closes * volumes,
    })


def benchmark(n_bars: int = 500, step: int = 1, trials: int = 5):
    """Measure indicator computation in simulation-like loop."""
    frame = make_frame(n_bars)
    warmup = n_bars // 5

    # ── Baseline: recompute build_indicator_snapshot per window ──
    times = []
    for _ in range(trials):
        t0 = time.perf_counter()
        for idx in range(warmup, n_bars - 1, step):
            window = frame.iloc[:idx + 1].copy()
            _ = build_indicator_snapshot(window)
        times.append(time.perf_counter() - t0)
    baseline_avg = np.mean(times)
    baseline_ms = baseline_avg / ((n_bars - 1 - warmup) / step) * 1000

    # ── Optimized: precompute all indicators once, then extract ──
    from runtime.services.incremental_indicators import precompute_all_indicators, extract_snapshot
    t0 = time.perf_counter()
    indicator_frame = precompute_all_indicators(frame)
    precompute_time = time.perf_counter() - t0

    times2 = []
    for _ in range(trials):
        t0 = time.perf_counter()
        for idx in range(warmup, n_bars - 1, step):
            _ = extract_snapshot(indicator_frame, idx)
        times2.append(time.perf_counter() - t0)
    optimized_avg = np.mean(times2)
    optimized_ms = optimized_avg / ((n_bars - 1 - warmup) / step) * 1000

    n_steps = (n_bars - 1 - warmup) // step
    print(f"Frame: {n_bars} bars, {n_steps} steps (step={step}, warmup={warmup})")
    print(f"  Baseline (recompute per window):  {baseline_avg:.4f}s total, {baseline_ms:.3f}ms/step")
    print(f"  Precompute all indicators:         {precompute_time:.4f}s one-time")
    print(f"  Optimized (extract per step):     {optimized_avg:.4f}s total, {optimized_ms:.3f}ms/step")
    print(f"  Speedup on indicator path:         {baseline_avg / max(optimized_avg, 1e-12):.1f}x")
    total_opt = precompute_time + optimized_avg
    print(f"  With precompute amortized:         {total_opt:.4f}s total")
    print(f"  Effective speedup (amortized):     {baseline_avg / max(total_opt, 1e-12):.1f}x")

    # ── Verify output parity ──
    print(f"\n  Verifying output equality...")
    window = frame.iloc[:warmup + 1].copy()
    ref = build_indicator_snapshot(window)
    opt = extract_snapshot(indicator_frame, warmup)
    key_fields = ["rsi", "macd", "atr", "adx", "ema_9", "ema_21", "bb_upper", "bb_lower", "vwap"]
    mismatches = []
    for k in key_fields:
        if k in ref and k in opt:
            v_ref = ref[k] if ref[k] is not None else 0.0
            v_opt = opt[k] if opt[k] is not None else 0.0
            if abs(v_ref - v_opt) > 0.001:
                mismatches.append(f"  Mismatch {k}: ref={v_ref} opt={v_opt}")
    if mismatches:
        for m in mismatches:
            print(m)
    else:
        print(f"  All {len(key_fields)} key fields match within tolerance.")


if __name__ == "__main__":
    benchmark(n_bars=300, step=1, trials=3)
    print()
    benchmark(n_bars=1000, step=1, trials=3)
