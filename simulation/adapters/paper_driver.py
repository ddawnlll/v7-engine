"""
PaperDriver — side-effect-free simulation for paper forward testing.

Calls simulate() and guarantees adapter_kind=PAPER in output lineage.
No order submission, no exchange connection. Pure deterministic forward test.
"""

from __future__ import annotations

from dataclasses import replace

from simulation.contracts.models import SimulationInput, SimulationOutput
from simulation.engine.engine import simulate


class PaperDriver:
    """Deterministic simulation adapter for paper forward testing.

    Wraps ``simulate()`` to ensure ``adapter_kind=PAPER`` in output lineage.
    No order submission, no exchange connection. Identical input produces
    identical output (modulo UUID run_id).
    """

    def run(self, input: SimulationInput) -> SimulationOutput:
        """Run simulation with PAPER lineage.

        Args:
            input: SimulationInput with entry price, ATR, future path, profile.

        Returns:
            SimulationOutput with adapter_kind=PAPER in lineage.
        """
        output = simulate(input)
        new_lineage = replace(output.lineage, adapter_kind="PAPER")
        return replace(output, lineage=new_lineage)
