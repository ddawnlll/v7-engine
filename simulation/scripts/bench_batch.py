#!/usr/bin/env python3
"""
Benchmark: compare serial CPU vs GPU batch path simulation.

Measures wall-clock time for both paths at increasing signal counts,
records GPU utilization during the run, and reports speedup factor.

Usage:
    PYTHONPATH=/teamspace/studios/this_studio/v7-engine python3 simulation/scripts/bench_batch.py
"""

import logging
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[2]))
sys.path.insert(0, str(Path(__file__).parents[2] / "simulation"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("bench_batch")

from simulation.engine.cuda_kernels import (
    prepare_batch_arrays, run_batch_gpu, run_batch_cpu, is_cuda_available,
)


def generate_signals(n: int, seed: int = 42, max_bars: int = 12) -> list[dict]:
    """Generate n synthetic signals for benchmarking."""
    rng = np.random.RandomState(seed)
    signals = []
    for i in range(n):
        direction = "LONG" if i % 2 == 0 else "SHORT"
        entry = 100.0 + rng.randn() * 5
        atr = 1.0 + abs(rng.randn()) * 1.0
        stop_mult = 1.5
        target_mult = 2.0
        entry_risk = atr * stop_mult
        if direction == "LONG":
            stop = entry - stop_mult * atr
            target = entry + target_mult * atr
        else:
            stop = entry + stop_mult * atr
            target = entry - target_mult * atr

        n_bars = int(rng.randint(1, max_bars + 1))
        rw = np.cumsum(rng.randn(n_bars) * atr * 0.5) + entry
        highs = rw + np.abs(rng.randn(n_bars) * atr * 0.1)
        lows = rw - np.abs(rng.randn(n_bars) * atr * 0.1)

        signals.append({
            "direction": direction,
            "entry_price": float(entry),
            "stop_price": float(stop),
            "target_price": float(target),
            "entry_risk": float(entry_risk),
            "close_price": float(rw[-1]),
            "available_bars": n_bars,
            "highs": highs.tolist(),
            "lows": lows.tolist(),
        })
    return signals


def record_gpu_util(duration_s: float = 1.0) -> str:
    """Capture nvidia-smi output snapshot."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except Exception as e:
        return f"nvidia-smi failed: {e}"


def benchmark():
    cuda_ok = is_cuda_available()
    logger.info("=" * 60)
    logger.info("BACKTEST BENCHMARK — GPU vs CPU")
    logger.info("CUDA available: %s", cuda_ok)
    if cuda_ok:
        from numba import cuda
        logger.info("GPU: %s", cuda.current_context().device.name.decode() if hasattr(cuda.current_context().device.name, 'decode') else cuda.current_context().device.name)
    logger.info("=" * 60)

    # Check GPU before
    logger.info("GPU before benchmark: %s", record_gpu_util())

    sizes = [1000, 5000, 10000, 50000, 75996]
    results = []

    for n in sizes:
        n_paths = n * 2  # LONG + SHORT
        logger.info("\n--- N_signals=%d (paths=%d) ---", n, n_paths)

        signals = generate_signals(n, seed=42)
        t0 = time.time()
        arrays = prepare_batch_arrays(signals, max_bars=30)
        t_prep = time.time() - t0
        logger.info("  Prep: %.3fs", t_prep)

        # CPU path
        t0 = time.time()
        cpu_out = run_batch_cpu(arrays)
        t_cpu = time.time() - t0
        logger.info("  CPU (njit parallel): %.3fs (%.0f paths/s)",
                     t_cpu, n_paths / t_cpu if t_cpu > 0 else 0)

        # GPU path
        if cuda_ok:
            # Sync before timing
            cuda.synchronize()
            t0 = time.time()
            gpu_out = run_batch_gpu(arrays)
            cuda.synchronize()
            t_gpu = time.time() - t0
            logger.info("  GPU (CUDA): %.3fs (%.0f paths/s)",
                         t_gpu, n_paths / t_gpu if t_gpu > 0 else 0)

            # Parity check
            errors = 0
            for key in gpu_out:
                if not np.allclose(gpu_out[key], cpu_out[key], atol=1e-10):
                    errors += 1
                    if errors <= 3:
                        logger.warning("  Parity FAIL on %s", key)
            if errors == 0:
                logger.info("  Parity: PASS (all %d fields match)", len(gpu_out))
            else:
                logger.error("  Parity: %d/%d fields MISMATCH", errors, len(gpu_out))

            results.append({
                "n": n, "paths": n_paths,
                "t_cpu": round(t_cpu, 3), "t_gpu": round(t_gpu, 3),
                "speedup": round(t_cpu / t_gpu, 2) if t_gpu > 0 else float('inf'),
            })

    # Summary table
    logger.info("\n" + "=" * 70)
    logger.info("BENCHMARK SUMMARY")
    logger.info("%-12s %-10s %-10s %-10s %-10s",
                "Signals", "Paths", "CPU (s)", "GPU (s)", "Speedup")
    logger.info("-" * 52)
    for r in results:
        logger.info("%-12d %-10d %-10.3f %-10.3f %-10.2fx",
                    r["n"], r["paths"], r["t_cpu"], r["t_gpu"], r["speedup"])

    # GPU after
    logger.info("\nGPU during benchmark: %s", record_gpu_util(0.5))
    logger.info("=" * 70)


if __name__ == "__main__":
    benchmark()
