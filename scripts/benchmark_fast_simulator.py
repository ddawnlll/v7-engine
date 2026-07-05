"""Benchmark: fast_simulator with numba JIT vs pure-Python fallback.

Usage:
    # With numba (via .venv):
    .venv/bin/python scripts/benchmark_fast_simulator.py

    # Without numba (system python, or set NUMBA_DISABLE_JIT=1):
    NUMBA_DISABLE_JIT=1 .venv/bin/python scripts/benchmark_fast_simulator.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure alphaforge is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── Force pure-Python mode for baseline (before importing fast_simulator) ──
# We'll re-import after changing the flag
_BASELINE_NUMBA = os.environ.pop("NUMBA_DISABLE_JIT", None)


def _benchmark(n_ts: int = 2000, n_sym: int = 50, trials: int = 3) -> dict:
    """Run fast_simulate_factor benchmark.

    Args:
        n_ts: Number of timestamps (bars).
        n_sym: Number of symbols.
        trials: Number of trials to average.
    """
    # Generate synthetic data
    rng = np.random.default_rng(42)
    scores = rng.normal(0, 1, (n_ts, n_sym)).astype(np.float64)
    close = 100.0 + np.cumsum(rng.normal(0, 0.5, (n_ts, n_sym)), axis=0).astype(np.float64)
    high = close + np.abs(rng.normal(0, 0.3, (n_ts, n_sym))).astype(np.float64)
    low = close - np.abs(rng.normal(0, 0.3, (n_ts, n_sym))).astype(np.float64)

    # ATR: simplified for benchmark
    atr = np.full((n_ts, n_sym), 1.5, dtype=np.float64)

    print(f"\n{'='*60}")
    print(f"Benchmark: {n_ts} bars × {n_sym} symbols ({n_ts * n_sym:,} cells)")
    print(f"{'='*60}")

    results = {}
    for mode_name, numba_disabled in [("WITH numba JIT", False), ("WITHOUT numba  ", True)]:
        # Reimport with the right flag
        os.environ["NUMBA_DISABLE_JIT"] = "1" if numba_disabled else "0"

        # Clear cached compiled functions
        import importlib
        for mod_name in list(sys.modules.keys()):
            if "fast_simulator" in mod_name:
                del sys.modules[mod_name]

        from alphaforge.factors.fast_simulator import fast_simulate_factor, fast_compute_atr

        is_jit = not numba_disabled

        # Warmup + verify numba status
        _ = fast_simulate_factor(
            scores, close, high, low, atr,
            config_stop_mult=2.0, config_target_mult=2.0,
            config_max_hold=20, direction_int=0,
            min_quantile=0.80, max_quantile=0.20, warmup=15,
        )
        if is_jit:
            # Check if truly compiled
            try:
                sig = fast_simulate_factor.signatures if hasattr(fast_simulate_factor, 'signatures') else None
                if sig:
                    print(f"  numba JIT compiled signatures: {sig}")
                else:
                    print(f"  numba is active but function has no compiled sig yet")
            except AttributeError:
                print(f"  numba not active (running pure Python)")

        timings = []
        for trial in range(trials):
            t0 = time.perf_counter()
            result = fast_simulate_factor(
                scores, close, high, low, atr,
                config_stop_mult=2.0, config_target_mult=2.0,
                config_max_hold=20, direction_int=0,
                min_quantile=0.80, max_quantile=0.20, warmup=15,
            )
            elapsed = time.perf_counter() - t0
            timings.append(elapsed)

        avg = np.mean(timings)
        trades = len(result[0]) if result and len(result) > 0 else 0
        results[mode_name] = {"avg_s": avg, "trades": trades}

        print(f"  {mode_name}: {avg:.4f}s avg ({trades} trades)")
        for i, t in enumerate(timings):
            print(f"    trial {i+1}: {t:.4f}s")

    ratio = results["WITHOUT numba  "]["avg_s"] / results["WITH numba JIT"]["avg_s"]
    print(f"\n  >>> Speedup: {ratio:.1f}x <<<")
    print(f"{'='*60}\n")

    return results


if __name__ == "__main__":
    _benchmark(n_ts=2000, n_sym=50, trials=3)
    _benchmark(n_ts=5000, n_sym=100, trials=3)
