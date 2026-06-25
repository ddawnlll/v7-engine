"""
BatchSimulator — runs multiple SimulationInputs through the simulation engine.

Collects results and logs errors without stopping the batch, enabling
fault-tolerant processing of large datasets.
"""

from __future__ import annotations

import logging
from typing import List

from simulation.contracts.models import SimulationInput, SimulationOutput
from simulation.engine.engine import simulate

logger = logging.getLogger(__name__)


class BatchSimulator:
    """Run multiple simulations, collecting results with error resilience.

    By default, errors are logged and the batch continues. Set ``fail_on_error``
    to True to raise on first failure (useful for testing).
    """

    def __init__(self, fail_on_error: bool = False):
        """Initialize BatchSimulator.

        Args:
            fail_on_error: If True, raises on first simulation error.
        """
        self._fail_on_error = fail_on_error

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

        Args:
            inputs: List of SimulationInput to simulate.

        Returns:
            List of SimulationOutput, one per successful simulation.
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

    @property
    def fail_on_error(self) -> bool:
        """Whether the simulator raises on first error."""
        return self._fail_on_error
