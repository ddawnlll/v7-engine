"""
ReplayDriver — side-effect-free simulation for historical replay.

Calls simulate() and guarantees adapter_kind=REPLAY in output lineage.
No live exchange or broker — pure deterministic historical replay.
"""

from __future__ import annotations

from dataclasses import replace

from simulation.contracts.models import SimulationInput, SimulationOutput
from simulation.engine.engine import simulate


class ReplayDriver:
    """Deterministic simulation adapter for historical replay.

    Wraps ``simulate()`` to ensure ``adapter_kind=REPLAY`` in output lineage.
    No order submission, no exchange connection. Pure deterministic replay.
    """

    def run(self, input: SimulationInput) -> SimulationOutput:
        """Run simulation with REPLAY lineage.

        Args:
            input: SimulationInput with entry price, ATR, future path, profile.

        Returns:
            SimulationOutput with adapter_kind=REPLAY in lineage.
        """
        output = simulate(input)
        new_lineage = replace(output.lineage, adapter_kind="REPLAY")
        return replace(output, lineage=new_lineage)
