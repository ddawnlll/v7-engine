"""
BatchSimulator — runs multiple SimulationInputs through the simulation engine.

Supports both sequential (single-process) and parallel (multi-process) modes
for maximum throughput.  Parallel mode uses ``concurrent.futures.ProcessPoolExecutor``
to distribute independent simulations across CPU cores.

Collects results and logs errors without stopping the batch, enabling
fault-tolerant processing of large datasets.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ProcessPoolExecutor
from typing import List, Sequence

from simulation.contracts.models import SimulationInput, SimulationOutput
from simulation.engine.engine import simulate

logger = logging.getLogger(__name__)


def _simulate_chunk(chunk: Sequence[SimulationInput]) -> List[SimulationOutput]:
    """Process a chunk of simulation inputs (module-level for pickle compat).

    ``ProcessPoolExecutor`` requires the worker function to be importable
    (pickle-able).  This module-level function wraps the per-input
    ``simulate()`` call and error handling so that each worker process
    executes its chunk independently.

    Args:
        chunk: A sequence of SimulationInput to simulate.

    Returns:
        List of SimulationOutput for successful simulations in the chunk.
        Failed simulations are logged and skipped.
    """
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
            # Continue processing remaining inputs in chunk
    return results


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
    ) -> List[SimulationOutput]:
        """Run batch simulation.

        Each input is simulated via ``simulation.engine.engine.simulate()``.
        Failed simulations produce a warning log entry and are excluded from
        results (unless ``fail_on_error`` is True).

        When parallel mode is active, inputs are split into chunks and
        distributed across worker processes.  Results are collected in the
        order they complete (which may differ from input order).

        Args:
            inputs: List of SimulationInput to simulate.

        Returns:
            List of SimulationOutput, one per successful simulation.
        """
        n_inputs = len(inputs)
        if n_inputs == 0:
            return []

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
