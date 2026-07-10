"""
BatchSimulator — runs multiple SimulationInputs through the simulation engine.

Supports three modes selected by hardware calibration:
  1. GPU batch (numba cuda.jit) — auto-selected when measured faster
  2. CPU parallel (numba njit + prange) — auto-selected when measured faster
  3. Sequential / ProcessPoolExecutor — original Python fallback

Self-calibrating router:
  On first run (or explicit --calibrate), benchmarks both CPU and GPU on a
  small sample, caches the winner. Cache auto-invalidates when hardware changes
  (different CPU core count or GPU name).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np

from simulation.contracts.models import (
    ActionOutcome,
    Candle,
    ExecutionMode,
    NoTradeOutcome,
    PathMetrics,
    SimulationInput,
    SimulationLineage,
    SimulationOutput,
    SimulationProfile,
)
from simulation.engine.costs import total_cost_r
from simulation.engine.cuda_kernels import (
    prepare_batch_arrays,
    run_batch_cpu,
    run_batch_gpu,
    is_cuda_available,
    EXIT_STOP_HIT,
    EXIT_TARGET_HIT,
    EXIT_TIME_EXIT,
)
from simulation.engine.engine import (
    _build_action_outcome,
    _build_no_trade_outcome,
    _path_quality,
    _path_quality_bucket,
    _select_best_action,
    simulate,
)
from simulation.engine.exits import _extract_ohlc, compute_utility

logger = logging.getLogger(__name__)

EXIT_REASON_MAP = {0: "STOP_HIT", 1: "TARGET_HIT", 2: "TIME_EXIT"}


# ═══════════════════════════════════════════════════════════════════════
# Self-calibrating hardware router
# ═══════════════════════════════════════════════════════════════════════

# Cache location: repo-adjacent, environment-specific, never committed
_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".simulation"
_CACHE_FILE = _CACHE_DIR / "hw_calibration.json"

# Calibration parameters
_CALIBRATE_N_SIGNALS = 8000  # signals to benchmark (×2 directions = 16K kernel calls)
_CALIBRATE_WARMUP = 3        # JIT warmup iterations (not timed)
_CALIBRATE_REPEAT = 7        # timed iterations (median taken)


def _hardware_fingerprint() -> dict:
    """Generate a fingerprint of the current compute hardware."""
    cpu_count = os.cpu_count() or 1
    cpu_name = platform.processor() or "unknown"
    gpu_name = "none"
    if is_cuda_available():
        try:
            from numba import cuda
            gpu_name = cuda.get_current_device().name
            if isinstance(gpu_name, bytes):
                gpu_name = gpu_name.decode()
        except Exception:
            gpu_name = "cuda_unknown"
    return {
        "cpu_count": cpu_count,
        "cpu_name": cpu_name,
        "gpu_name": gpu_name,
    }


def _generate_calibration_signals(n: int, max_bars: int = 30) -> list[dict]:
    """Generate synthetic signal data for calibration benchmarking."""
    rng = np.random.default_rng(42)
    signals = []
    for _ in range(n):
        direction = "LONG" if rng.random() > 0.5 else "SHORT"
        entry_price = rng.uniform(50, 200)
        risk_pct = rng.uniform(0.01, 0.05)
        if direction == "LONG":
            stop_price = entry_price * (1 - risk_pct)
            target_price = entry_price * (1 + risk_pct * rng.uniform(1.5, 3.0))
            entry_risk = entry_price - stop_price
        else:
            stop_price = entry_price * (1 + risk_pct)
            target_price = entry_price * (1 - risk_pct * rng.uniform(1.5, 3.0))
            entry_risk = stop_price - entry_price
        n_bars = int(rng.integers(5, max_bars + 1))
        highs = (entry_price + rng.uniform(0, 0.02 * entry_price, n_bars)).tolist()
        lows = (entry_price - rng.uniform(0, 0.02 * entry_price, n_bars)).tolist()
        signals.append({
            "direction": direction,
            "entry_price": entry_price,
            "stop_price": stop_price,
            "target_price": target_price,
            "entry_risk": entry_risk,
            "close_price": entry_price,
            "available_bars": n_bars,
            "highs": highs,
            "lows": lows,
        })
    return signals


def _measure_gpu(arrays: dict) -> float:
    """Measure GPU batch simulation time (median of _CALIBRATE_REPEAT runs).

    Includes cuda.synchronize() to ensure accurate wall-clock measurement.
    """
    # Warmup — JIT compile + load kernels, NOT timed
    for _ in range(_CALIBRATE_WARMUP):
        run_batch_gpu(arrays)

    times = []
    for _ in range(_CALIBRATE_REPEAT):
        t0 = time.perf_counter()
        run_batch_gpu(arrays)
        # cuda.synchronize() is implicit in numba cuda.jit calls,
        # but we add an explicit sync to be certain
        try:
            from numba import cuda as _cuda
            _cuda.synchronize()
        except Exception:
            pass
        times.append(time.perf_counter() - t0)
    return float(np.median(times))


def _measure_cpu(arrays: dict) -> float:
    """Measure CPU-parallel batch simulation time (median of _CALIBRATE_REPEAT runs)."""
    # Warmup — JIT compile, NOT timed
    for _ in range(_CALIBRATE_WARMUP):
        run_batch_cpu(arrays)

    times = []
    for _ in range(_CALIBRATE_REPEAT):
        t0 = time.perf_counter()
        run_batch_cpu(arrays)
        times.append(time.perf_counter() - t0)
    return float(np.median(times))


def _load_cache() -> Optional[dict]:
    """Load calibration cache from disk. Returns None if missing or invalid."""
    if not _CACHE_FILE.exists():
        return None
    try:
        with open(_CACHE_FILE) as f:
            cache = json.load(f)
        # Validate required keys
        required = {"winner", "cpu_time", "gpu_time", "fingerprint", "calibrated_at"}
        if not required.issubset(cache.keys()):
            return None
        return cache
    except (json.JSONDecodeError, OSError):
        return None


def _save_cache(cache: dict) -> None:
    """Save calibration cache to disk."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)
    logger.info("Hardware calibration cache saved to %s", _CACHE_FILE)


def _cache_is_valid(cache: dict) -> bool:
    """Check if cached calibration is still valid for current hardware."""
    current = _hardware_fingerprint()
    cached_fp = cache.get("fingerprint", {})
    return (
        current["cpu_count"] == cached_fp.get("cpu_count")
        and current["gpu_name"] == cached_fp.get("gpu_name")
    )


def calibrate_hardware(force: bool = False) -> dict:
    """Benchmark both CPU-parallel and GPU path simulation, cache the winner.

    Args:
        force: If True, recalibrate even if valid cache exists.

    Returns:
        dict with keys: winner, cpu_time, gpu_time, fingerprint, calibrated_at.
    """
    # Check cache first
    if not force:
        cache = _load_cache()
        if cache and _cache_is_valid(cache):
            logger.info(
                "Hardware calibration: using cached result (winner=%s, "
                "cpu=%.4fs, gpu=%.4fs, calibrated_at=%s)",
                cache["winner"], cache["cpu_time"], cache["gpu_time"],
                cache["calibrated_at"],
            )
            return cache
        elif cache and not _cache_is_valid(cache):
            logger.info(
                "Hardware calibration: cache invalid (hardware changed), "
                "recalibrating..."
            )

    fp = _hardware_fingerprint()
    logger.info(
        "Hardware calibration: benchmarking CPU vs GPU with %d signals "
        "(warmup=%d, repeat=%d)...",
        _CALIBRATE_N_SIGNALS, _CALIBRATE_WARMUP, _CALIBRATE_REPEAT,
    )

    # Generate test data
    signals = _generate_calibration_signals(_CALIBRATE_N_SIGNALS)
    arrays = prepare_batch_arrays(signals)

    # Measure GPU (if available)
    gpu_time = None
    if is_cuda_available():
        try:
            gpu_time = _measure_gpu(arrays)
            logger.info("  GPU: %.4fs (median of %d runs)", gpu_time, _CALIBRATE_REPEAT)
        except Exception as e:
            logger.warning("  GPU measurement failed: %s", e)
    else:
        logger.info("  GPU: not available")

    # Measure CPU
    cpu_time = _measure_cpu(arrays)
    logger.info("  CPU: %.4fs (median of %d runs)", cpu_time, _CALIBRATE_REPEAT)

    # Decide winner
    if gpu_time is not None and gpu_time < cpu_time:
        winner = "gpu"
        speedup = cpu_time / gpu_time
    else:
        winner = "cpu"
        speedup = gpu_time / cpu_time if gpu_time and gpu_time > 0 else float("inf")

    logger.info(
        "Hardware calibration: winner=%s (cpu=%.4fs, gpu=%s, speedup=%.1fx)",
        winner, cpu_time,
        f"{gpu_time:.4f}s" if gpu_time else "N/A",
        speedup,
    )

    result = {
        "winner": winner,
        "cpu_time": cpu_time,
        "gpu_time": gpu_time,
        "fingerprint": fp,
        "calibrated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_signals": _CALIBRATE_N_SIGNALS,
        "warmup": _CALIBRATE_WARMUP,
        "repeat": _CALIBRATE_REPEAT,
    }

    _save_cache(result)
    return result


def get_preferred_backend(force_gpu: bool = False) -> str:
    """Get the preferred compute backend, using cache or calibrating.

    Returns:
        "gpu" or "cpu" — which backend to use for batch simulation.
    """
    if force_gpu and is_cuda_available():
        return "gpu"

    cache = _load_cache()
    if cache and _cache_is_valid(cache):
        return cache["winner"]

    # No valid cache — calibrate now
    result = calibrate_hardware()
    return result["winner"]


def _simulate_chunk(chunk: Sequence[SimulationInput]) -> List[SimulationOutput]:
    """Process a chunk of simulation inputs (module-level for pickle compat)."""
    results: List[SimulationOutput] = []
    for idx, sim_input in enumerate(chunk):
        try:
            output = simulate(sim_input)
            results.append(output)
        except Exception:
            logger.exception(
                "Simulation failed for input (symbol=%s, ts=%s)",
                sim_input.symbol,
                sim_input.decision_timestamp,
            )
    return results


def _inputs_to_batch_arrays(
    inputs: List[SimulationInput],
) -> Optional[dict]:
    """Convert SimulationInput list to batch arrays for GPU/CPU path.

    Returns None if conversion fails (fall back to original path).
    """
    try:
        signals_data = []
        for sim_input in inputs:
            profile = sim_input.profile
            entry = sim_input.entry_price
            atr = sim_input.atr
            stop_mult = profile.stop_multiplier
            target_mult = profile.target_multiplier
            entry_risk = atr * stop_mult

            # Compute stop/target prices
            if profile.mode.value == "LONG" or True:  # both directions computed
                long_stop = entry - atr * stop_mult
                long_target = entry + atr * target_mult
                short_stop = entry + atr * stop_mult
                short_target = entry - atr * target_mult

            candles = sim_input.future_path.candles
            n_avail = min(len(candles), profile.max_holding_bars)

            if n_avail == 0:
                continue

            # Extract OHLC arrays for available bars
            highs = np.array([c.high for c in candles[:n_avail]], dtype=np.float64)
            lows = np.array([c.low for c in candles[:n_avail]], dtype=np.float64)
            close_price = float(candles[n_avail - 1].close)

            # LONG direction
            signals_data.append({
                "direction": "LONG",
                "entry_price": float(entry),
                "stop_price": float(long_stop),
                "target_price": float(long_target),
                "entry_risk": float(entry_risk),
                "close_price": close_price,
                "available_bars": n_avail,
                "highs": highs,
                "lows": lows,
            })
            # SHORT direction
            signals_data.append({
                "direction": "SHORT",
                "entry_price": float(entry),
                "stop_price": float(short_stop),
                "target_price": float(short_target),
                "entry_risk": float(entry_risk),
                "close_price": close_price,
                "available_bars": n_avail,
                "highs": highs,
                "lows": lows,
            })

        return prepare_batch_arrays(signals_data)
    except Exception as e:
        logger.warning("Batch array conversion failed: %s — falling back", e)
        return None


def _batch_results_to_simulation_outputs(
    batch_out: dict,
    inputs: List[SimulationInput],
) -> List[SimulationOutput]:
    """Reconstruct SimulationOutput list from batch kernel results.

    Uses batched numpy operations for cost computation and outcome assembly
    to avoid per-signal Python function call overhead.
    """
    n = len(inputs)
    if n == 0 or "exit_reason" not in batch_out:
        return []

    outputs: List[SimulationOutput] = []

    # Pre-allocate arrays for batch cost computation
    n_paths = len(batch_out["exit_reason"])
    long_indices = np.arange(0, n_paths, 2)
    short_indices = np.arange(1, n_paths, 2)

    # Trim to actual data
    max_sig = min(n, len(long_indices), len(short_indices))

    # Batch compute costs for all paths at once
    for i in range(max_sig):
        sim_input = inputs[i]
        profile = sim_input.profile
        atr = sim_input.atr
        entry_price = sim_input.entry_price
        notional = entry_price
        stop_mult = profile.stop_multiplier
        entry_risk = atr * stop_mult

        long_idx = int(long_indices[i])
        short_idx = int(short_indices[i])

        # Build outcomes for both directions
        def _make_outcome(action: str, idx: int) -> ActionOutcome:
            """Build ActionOutcome from batch data + inline cost."""
            er_code = int(batch_out["exit_reason"][idx])
            exit_reason_str = EXIT_REASON_MAP.get(er_code, "TIME_EXIT")
            hold_bars = int(batch_out["hold_dur"][idx])
            rg = float(batch_out["realized_gross"][idx])

            # Cost computation (simple arithmetic — fast even in Python)
            risk = entry_risk
            fcr = 0.0; scr = 0.0; fund_r = 0.0
            if risk > 0 and notional > 0:
                exec_mode = getattr(profile, "execution_mode", "TAKER")
                maker_fill = getattr(profile, "maker_fill_probability", 0.7)
                from simulation.contracts.models import ExecutionMode
                try:
                    em = ExecutionMode[exec_mode]
                except KeyError:
                    em = ExecutionMode.TAKER
                fcr, scr, fund_r, _ = total_cost_r(
                    notional, entry_price, atr, stop_mult,
                    execution_mode=em, maker_fill_probability=maker_fill,
                    holding_bars=hold_bars,
                )

            r_net = rg - (fcr + scr + fund_r)

            # MFE/MAE
            mfe = float(batch_out["mfe"][idx])
            mae = float(batch_out["mae"][idx])
            mfe_r = float(batch_out["mfe_r"][idx])
            mae_r = float(batch_out["mae_r"][idx])
            t_mfe = int(batch_out["t_mfe"][idx])
            t_mae = int(batch_out["t_mae"][idx])

            pm = PathMetrics(
                mfe=mfe, mae=mae, mfe_r=mfe_r, mae_r=mae_r,
                time_to_mfe=t_mfe, time_to_mae=t_mae,
                path_quality_score=_path_quality(mfe_r, mae_r),
                path_quality_bucket=_path_quality_bucket(mfe_r, mae_r),
            )

            utility = compute_utility(r_net, mae_r, fcr + scr + fund_r, t_mfe, profile)

            return ActionOutcome(
                action=action,
                realized_r_gross=rg,
                realized_r_net=r_net,
                fee_cost_r=fcr, slippage_cost_r=scr, funding_cost_r=fund_r,
                total_cost_r=fcr + scr + fund_r,
                exit_reason=exit_reason_str,
                exit_price=float(batch_out["exit_price"][idx]),
                exit_bar_index=int(batch_out["exit_idx"][idx]),
                hold_duration_bars=hold_bars,
                action_utility=utility,
                path_metrics=pm,
                same_candle_ambiguity=False,
            )

        long_outcome = _make_outcome("LONG_NOW", long_idx)
        short_outcome = _make_outcome("SHORT_NOW", short_idx)
        no_trade_outcome = _build_no_trade_outcome(long_outcome, short_outcome, profile)
        best_action, second_best, gap, regret, ambiguous = _select_best_action(
            long_outcome, short_outcome, no_trade_outcome, profile,
        )

        resolution = "COMPLETE"
        if not sim_input.future_path.candles:
            resolution = "UNRESOLVED"

        lineage = SimulationLineage(
            simulation_family_version=getattr(sim_input, 'simulation_family_version', 'batch-1.0.0'),
            simulation_profile_version=profile.profile_version,
            cost_model_version=getattr(sim_input, 'cost_model_version', 'cost-1.0.0'),
            fee_model_version="fee-1.0.0",
            slippage_model_version="slippage-1.0.0",
            funding_model_version="funding-1.0.0",
            horizon_family=f"{profile.mode.value.lower()}_horizon",
            stop_family=profile.stop_method,
            target_family=profile.target_method,
            time_exit_family="hold_then_exit",
            adapter_kind="TRAINING",
        )

        outputs.append(SimulationOutput(
            simulation_run_id=str(i)[:8],
            symbol=sim_input.symbol,
            decision_timestamp=sim_input.decision_timestamp,
            mode=sim_input.mode.value,
            primary_interval=sim_input.primary_interval,
            resolution_status=resolution,
            invalidity_reason="",
            long_outcome=long_outcome,
            short_outcome=short_outcome,
            no_trade_outcome=no_trade_outcome,
            best_action=best_action,
            second_best_action=second_best,
            action_gap_r=gap,
            regret_r=regret,
            is_ambiguous=ambiguous,
            lineage=lineage,
        ))

    return outputs


class BatchSimulator:
    """Run multiple simulations, collecting results with error resilience.

    By default, errors are logged and the batch continues.  Set ``fail_on_error``
    to True to raise on first failure (useful for testing).

    When ``num_workers`` is > 1 (or None with CPU count > 1), simulations
    are distributed across a process pool for parallel execution.
    """

    def __init__(self, fail_on_error: bool = False, num_workers: int | None = None):
        """Initialize BatchSimulator.

        Args:
            fail_on_error: If True, raises on first simulation error.
            num_workers: Number of worker processes.
                - ``None`` (default): auto-detect CPU count; uses 1 if only 1 core.
                - ``1``: force sequential execution (useful for testing/debugging).
                - ``> 1``: use exactly that many workers.
        """
        self._fail_on_error = fail_on_error
        self._num_workers = num_workers

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        inputs: List[SimulationInput],
        use_batch: bool = True,
        force_gpu: bool = False,
        force_recalibrate: bool = False,
    ) -> List[SimulationOutput]:
        """Run batch simulation with self-calibrating acceleration.

        The router benchmarks both CPU-parallel and GPU on first call (or when
        cache is missing/invalid), caches the winner, and uses that for all
        subsequent calls. No hardcoded thresholds — everything is measured.

        Args:
            inputs: List of SimulationInput to simulate.
            use_batch: If True, try batch acceleration (default True).
            force_gpu: If True AND CUDA available, use GPU kernel (default False).
            force_recalibrate: If True, re-benchmark even if cache exists.

        Returns:
            List of SimulationOutput, one per successful simulation.
        """
        import time
        n_inputs = len(inputs)
        if n_inputs == 0:
            return []

        # Try batch path for large workloads
        if use_batch and n_inputs >= (os.cpu_count() or 4):
            arrays = _inputs_to_batch_arrays(inputs)
            if arrays is not None and len(arrays["directions"]) > 0:
                try:
                    # Get preferred backend from calibration cache
                    if force_recalibrate:
                        backend = calibrate_hardware(force=True)["winner"]
                    else:
                        backend = get_preferred_backend(force_gpu=force_gpu)

                    if backend == "gpu" and is_cuda_available():
                        t0 = time.perf_counter()
                        batch_out = run_batch_gpu(arrays)
                        bt = time.perf_counter() - t0
                        results = _batch_results_to_simulation_outputs(batch_out, inputs)
                        logger.info(
                            "BatchSimulator: GPU batch %d inputs in %.3fs (%.0f inputs/s)",
                            n_inputs, bt, n_inputs / bt if bt > 0 else 0,
                        )
                        return results
                    else:
                        t0 = time.perf_counter()
                        batch_out = run_batch_cpu(arrays)
                        bt = time.perf_counter() - t0
                        results = _batch_results_to_simulation_outputs(batch_out, inputs)
                        logger.info(
                            "BatchSimulator: CPU-parallel batch %d inputs in %.3fs (%.0f inputs/s)",
                            n_inputs, bt, n_inputs / bt if bt > 0 else 0,
                        )
                        return results
                except Exception as e:
                    logger.warning("Batch path failed (%s) — falling back to original", e)

        n_workers = self._resolve_workers(n_inputs)
        if n_workers <= 1:
            return self._run_sequential(inputs)
        return self._run_parallel(inputs, n_workers)

    @property
    def fail_on_error(self) -> bool:
        """Whether the simulator raises on first error."""
        return self._fail_on_error

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_workers(self, n_inputs: int) -> int:
        """Determine the effective number of worker processes.

        Args:
            n_inputs: Number of simulation inputs.

        Returns:
            Number of workers to use.
        """
        if self._num_workers is not None:
            return min(self._num_workers, n_inputs)
        # Auto-detect
        cpus = os.cpu_count() or 1
        return min(cpus, n_inputs)

    def _run_sequential(
        self,
        inputs: List[SimulationInput],
    ) -> List[SimulationOutput]:
        """Run simulations sequentially in the current process.

        This is the original single-process path.  Error handling respects
        the ``fail_on_error`` flag: errors are logged and skipped by default,
        or raised on first failure when the flag is set.
        """
        results: List[SimulationOutput] = []
        for idx, sim_input in enumerate(inputs):
            try:
                output = simulate(sim_input)
                results.append(output)
            except Exception:
                logger.exception(
                    "Simulation failed for input %d (symbol=%s, ts=%s)",
                    idx,
                    sim_input.symbol,
                    sim_input.decision_timestamp,
                )
                if self._fail_on_error:
                    raise
        return results

    def _run_parallel(
        self,
        inputs: List[SimulationInput],
        n_workers: int,
    ) -> List[SimulationOutput]:
        """Run simulations in parallel using a process pool.

        Chunks inputs by worker count, dispatches via
        ``ProcessPoolExecutor.map()``, and flattens results maintaining
        input order.

        In parallel mode the ``fail_on_error`` flag is intentionally
        NOT propagated to workers — a failing input in one chunk never
        kills another chunk's work.  This matches the "log and continue"
        contract of the original ``BatchSimulator``.
        """
        # Split inputs into roughly equal chunks
        chunk_size = max(1, len(inputs) // n_workers)
        chunks = [inputs[i:i + chunk_size] for i in range(0, len(inputs), chunk_size)]

        results: List[SimulationOutput] = []
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            # map() preserves input order across chunks
            for chunk_result in executor.map(_simulate_chunk, chunks):
                results.extend(chunk_result)

        logger.info(
            "BatchSimulator: %d/%d simulations succeeded (%d workers)",
            len(results),
            len(inputs),
            n_workers,
        )
        return results


# ═══════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Batch simulation hardware calibration and execution.",
    )
    sub = parser.add_subparsers(dest="command")

    cal = sub.add_parser(
        "calibrate",
        help="Benchmark CPU vs GPU and cache the winner.",
    )
    cal.add_argument(
        "--force", action="store_true",
        help="Recalibrate even if valid cache exists.",
    )
    cal.add_argument(
        "--status", action="store_true",
        help="Show current calibration status without recalibrating.",
    )

    sub.add_parser(
        "status",
        help="Show current calibration cache and hardware fingerprint.",
    )

    args = parser.parse_args()

    if args.command == "calibrate":
        if args.status:
            cache = _load_cache()
            if cache:
                print(json.dumps(cache, indent=2))
            else:
                print("No calibration cache found.")
        else:
            result = calibrate_hardware(force=args.force)
            print(f"\nWinner: {result['winner'].upper()}")
            print(f"CPU time: {result['cpu_time']:.4f}s")
            print(f"GPU time: {result['gpu_time']:.4f}s" if result['gpu_time'] else "GPU time: N/A")
            print(f"Hardware: {result['fingerprint']}")
            print(f"Calibrated at: {result['calibrated_at']}")
    elif args.command == "status":
        cache = _load_cache()
        fp = _hardware_fingerprint()
        print(f"Hardware fingerprint: {json.dumps(fp, indent=2)}")
        if cache:
            valid = _cache_is_valid(cache)
            print(f"Cache valid: {valid}")
            print(json.dumps(cache, indent=2))
        else:
            print("No calibration cache found.")
    else:
        parser.print_help()
        sys.exit(1)
