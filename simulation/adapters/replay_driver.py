"""
ReplayDriver — side-effect-free simulation for historical replay.

Calls simulate() and guarantees adapter_kind=REPLAY in output lineage.
Implements the SimulationEngine interface (ABC).
No live exchange or broker — pure deterministic historical replay.
"""

from __future__ import annotations

from dataclasses import replace

from simulation.contracts.models import SimulationInput, SimulationOutput
from simulation.engine.engine import simulate
from simulation.engine.interface import SimulationEngine


class ReplayDriver(SimulationEngine):
    """Deterministic simulation adapter for historical replay.

    Wraps ``simulate()`` to ensure ``adapter_kind=REPLAY`` in output lineage.
    No order submission, no exchange connection. Pure deterministic replay.
    """

    ADAPTER_KIND = "REPLAY"

    def get_adapter_kind(self) -> str:
        return self.ADAPTER_KIND

    def run(self, input: SimulationInput) -> SimulationOutput:
        """Run simulation with REPLAY lineage.

        Args:
            input: SimulationInput with entry price, ATR, future path, profile.

        Returns:
            SimulationOutput with adapter_kind=REPLAY in lineage.

        Raises:
            ValueError: If input or output validation fails.
        """
        errors = self.validate_input(input)
        if errors:
            raise ValueError(
                f"ReplayDriver input validation failed: {'; '.join(errors)}"
            )
        output = simulate(input)
        lineage = replace(output.lineage, adapter_kind=self.ADAPTER_KIND)
        result = replace(output, lineage=lineage)
        out_errors = self.validate_output(result)
        if out_errors:
            raise ValueError(
                f"ReplayDriver output validation failed: {'; '.join(out_errors)}"
            )
        return result
