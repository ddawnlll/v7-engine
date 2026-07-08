#!/usr/bin/env python3
"""
Before/After benchmark: original backtest_signals() vs batched GPU/CPU path.

Generates N random trade signals with forward OHLCV data, runs the full
AlphaForge backtest pipeline through both paths, measures wall-clock time,
reports speedup with nvidia-smi GPU utilization.

Usage:
    PYTHONPATH=... python3 simulation/scripts/bench_pipeline_before_after.py
"""

import logging
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[2]))
sys.path.insert(0, str(Path(__file__).parents[2] / "alphaforge" / "src"))
sys.path.insert(0, str(Path(__file__).parents[2] / "simulation"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("bench_pipeline")

from alphaforge.discovery import TradeSignal
from alphaforge.discovery.backtest import backtest_signals


def generate_benchmark_data(
    n_signals: int = 1000,
    seed: int = 42,
    max_hold: int = 12,
) -> tuple[list[TradeSignal], dict]:
    """Generate n TradeSignals with matching OHLCV data.

    Returns (signals, ohlcv_dict) suitable for backtest_signals().
    """
    rng = np.random.RandomState(seed)
    signals: list[TradeSignal] = []
    ohlcv_data: dict[str, list] = {
        "open": [], "high": [], "low": [], "close": [], "volume": [],
        "timestamp": [], "symbol": [],
    }

    # Generate 5 synthetic symbols
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    bars_per_symbol = max_hold + 10  # enough forward data

    ts_counter = 1672531200000  # Jan 2023 in ms
    for sym in symbols:
        price = 100.0 + rng.randn() * 20
        for b in range(bars_per_symbol * 5):  # ~60 bars per symbol
            ret = rng.randn() * 0.02
            price *= (1.0 + ret)
            atr = price * 0.015
            ohlcv_data["open"].append(float(price * (1.0 + rng.randn() * 0.005)))
            ohlcv_data["high"].append(float(price * (1.0 + abs(rng.randn()) * 0.01)))
            ohlcv_data["low"].append(float(price * (1.0 - abs(rng.randn()) * 0.01)))
            ohlcv_data["close"].append(float(price))
            ohlcv_data["volume"].append(float(abs(rng.randn()) * 1000))
            ohlcv_data["timestamp"].append(ts_counter + b * 3600000)
            ohlcv_data["symbol"].append(sym)

    # Generate random trade signals
    total_bars = len(ohlcv_data["close"])
    ts_arr = np.array(ohlcv_data["timestamp"], dtype=np.int64)
    sym_arr = np.array(ohlcv_data["symbol"], dtype=object)

    for i in range(n_signals):
        sym = symbols[i % len(symbols)]
        # Pick a random entry point
        sym_mask = sym_arr == sym
        sym_indices = np.where(sym_mask)[0]
        if len(sym_indices) < max_hold + 3:
            continue
        entry_idx = int(sym_indices[len(sym_indices) // 3])  # pick early bar
        entry_ts = ts_arr[entry_idx]
        entry_price = float(ohlcv_data["close"][entry_idx])
        atr = entry_price * 0.015
        side = "LONG" if i % 2 == 0 else "SHORT"

        signals.append(TradeSignal(
            bar_index=entry_idx,
            timestamp=entry_ts,
            symbol=sym,
            side=side,
            entry_price=entry_price,
            atr=atr,
            stop_price=entry_price - 1.5 * atr if side == "LONG" else entry_price + 1.5 * atr,
            target_price=entry_price + 2.0 * atr if side == "LONG" else entry_price - 2.0 * atr,
            confidence=0.6 + rng.random() * 0.3,
            model_score=0.6 + rng.random() * 0.3,
            initial_risk=1.5 * atr,
        ))

    # Convert lists to numpy arrays for OHLCV
    ohlcv = {k: np.array(v) for k, v in ohlcv_data.items()}

    logger.info("Generated %d signals, %d OHLCV bars (%d symbols)",
                len(signals), len(ohlcv["close"]), len(symbols))
    return signals, ohlcv


def benchmark():
    logger.info("=" * 60)
    logger.info("PIPELINE BENCHMARK — Before vs After")
    logger.info("=" * 60)

    # Check GPU before
    try:
        gpu_before = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        logger.info("GPU before: %s", gpu_before)
    except Exception:
        logger.info("GPU before: N/A")

    sizes = [100, 500, 1000, 2000, 5000]
    results = []

    for n in sizes:
        logger.info("\n--- N=%d signals ---", n)
        signals, ohlcv = generate_benchmark_data(n)

        # BEFORE: original per-signal path
        t0 = time.time()
        results_old = backtest_signals(signals, ohlcv, "SCALP", use_batch=False)
        t_old = time.time() - t0
        logger.info("  BEFORE (per-signal loop): %.3fs (%d results)",
                     t_old, len(results_old))

        # AFTER: GPU/CPU batch path
        t0 = time.time()
        results_new = backtest_signals(signals, ohlcv, "SCALP", use_batch=True)
        t_new = time.time() - t0
        logger.info("  AFTER (batch path):       %.3fs (%d results)",
                     t_new, len(results_new))

        if len(results_old) > 0 and len(results_new) > 0:
            speedup = t_old / t_new if t_new > 0 else 0
            logger.info("  SPEEDUP: %.2fx", speedup)

            # Parity check
            n_check = min(len(results_old), len(results_new))
            if n_check > 0:
                r_old = [r.realized_r_net for r in results_old[:n_check]]
                r_new = [r.realized_r_net for r in results_new[:n_check]]
                max_diff = max(abs(a - b) for a, b in zip(r_old, r_new))
                logger.info("  Max R-net diff: %.6f (1e-4 tol=%s)",
                            max_diff, "PASS" if max_diff < 1e-4 else "FAIL")
        elif len(results_old) != len(results_new):
            logger.warning("  Count mismatch! old=%d new=%d",
                           len(results_old), len(results_new))

        results.append({
            "n": n,
            "old_s": round(t_old, 3),
            "new_s": round(t_new, 3),
            "speedup": round(t_old / t_new, 2) if t_new > 0 and t_old > 0 else 0,
        })

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY — Before vs After")
    logger.info("%-12s %-14s %-14s %-10s",
                "Signals", "Before (s)", "After (s)", "Speedup")
    logger.info("-" * 50)
    for r in results:
        logger.info("%-12d %-14.3f %-14.3f %-10.2fx",
                    r["n"], r["old_s"], r["new_s"], r["speedup"])

    # Check GPU after
    try:
        gpu_after = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        logger.info("GPU after: %s", gpu_after)
    except Exception:
        logger.info("GPU after: N/A")

    logger.info("=" * 60)


if __name__ == "__main__":
    benchmark()
