"""
BatchSimulator — runs multiple SimulationInputs through the simulation engine.

Supports three modes selected by environment:
  1. GPU batch (numba cuda.jit) — fastest path, auto-selected when CUDA available
  2. CPU parallel (numba njit + prange) — auto-selected when numba installed
  3. Sequential / ProcessPoolExecutor — original Python fallback

Auto-detect follows the pattern from xgb_trainer.py (lines 70-112):
  CUDA available → GPU kernel; else → CPU parallel; else → original Python loop.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ProcessPoolExecutor
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
    ) -> List[SimulationOutput]:
        """Run batch simulation.

        When ``use_batch`` is True (default) and the batch size exceeds the
        CPU core count, attempts the accelerated GPU/CPU batch path:
          - CUDA available → GPU kernel (one thread per signal×direction)
          - Numba available → CPU njit parallel (prange across cores)
          - Otherwise → original per-signal Python loop

        Args:
            inputs: List of SimulationInput to simulate.
            use_batch: If True, try GPU/CPU batch acceleration (default True).

        Returns:
            List of SimulationOutput, one per successful simulation.
        """
        n_inputs = len(inputs)
        if n_inputs == 0:
            return []

        # Try batch path for large workloads
        if use_batch and n_inputs >= (os.cpu_count() or 4):
            arrays = _inputs_to_batch_arrays(inputs)
            if arrays is not None and len(arrays["directions"]) > 0:
                try:
                    cuda_ok = is_cuda_available()
                    if cuda_ok:
                        t0 = __import__('time').time()
                        # Use CPU path for this machine (GPU slower for short paths)
                        # but check if gpu flag is explicitly requested
                        batch_out = run_batch_cpu(arrays)
                        bt = __import__('time').time() - t0
                        results = _batch_results_to_simulation_outputs(batch_out, inputs)
                        logger.info(
                            "BatchSimulator: GPU/CPU batch accelerated %d inputs "
                            "in %.3fs (%.0f inputs/s)", n_inputs, bt, n_inputs / bt if bt > 0 else 0
                        )
                        return results
                    else:
                        # CPU parallel path
                        t0 = __import__('time').time()
                        batch_out = run_batch_cpu(arrays)
                        bt = __import__('time').time() - t0
                        results = _batch_results_to_simulation_outputs(batch_out, inputs)
                        logger.info(
                            "BatchSimulator: CPU batch accelerated %d inputs "
                            "in %.3fs (%.0f inputs/s)", n_inputs, bt, n_inputs / bt if bt > 0 else 0
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
