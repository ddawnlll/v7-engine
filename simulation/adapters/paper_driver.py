"""
PaperDriver — side-effect-free simulation for paper forward testing.

Calls simulate() and guarantees adapter_kind=PAPER in output lineage.
Implements the SimulationEngine interface (ABC).
No order submission, no exchange connection. Pure deterministic forward test.
"""

from __future__ import annotations

from dataclasses import replace

from simulation.contracts.models import SimulationInput, SimulationOutput
from simulation.engine.engine import simulate
from simulation.engine.interface import SimulationEngine


class PaperDriver(SimulationEngine):
    """Deterministic simulation adapter for paper forward testing.

    Wraps ``simulate()`` to ensure ``adapter_kind=PAPER`` in output lineage.
    No order submission, no exchange connection. Identical input produces
    identical output (modulo UUID run_id).
    """

    ADAPTER_KIND = "PAPER"

    def get_adapter_kind(self) -> str:
        return self.ADAPTER_KIND

    def run(self, input: SimulationInput) -> SimulationOutput:
        """Run simulation with PAPER lineage.

        Args:
            input: SimulationInput with entry price, ATR, future path, profile.

        Returns:
            SimulationOutput with adapter_kind=PAPER in lineage.

        Raises:
            ValueError: If input or output validation fails.
        """
        errors = self.validate_input(input)
        if errors:
            raise ValueError(
                f"PaperDriver input validation failed: {'; '.join(errors)}"
            )
        output = simulate(input)
        lineage = replace(output.lineage, adapter_kind=self.ADAPTER_KIND)
        result = replace(output, lineage=lineage)
        out_errors = self.validate_output(result)
        if out_errors:
            raise ValueError(
                f"PaperDriver output validation failed: {'; '.join(out_errors)}"
            )
        return result
