"""
TrainingAdapter — side-effect-free simulation for training label generation.

Calls simulate() and guarantees adapter_kind=TRAINING in output lineage.
No network I/O, no exchange APIs, no XGBoost. Pure deterministic transformation.
"""

from __future__ import annotations

from dataclasses import replace

from simulation.contracts.models import SimulationInput, SimulationOutput
from simulation.engine.engine import simulate


class TrainingAdapter:
    """Deterministic simulation adapter for training pipelines.

    Wraps ``simulate()`` to ensure ``adapter_kind=TRAINING`` in output lineage.
    Identical input always produces identical output (modulo UUID run_id).
    """

    def run(self, input: SimulationInput) -> SimulationOutput:
        """Run simulation with TRAINING lineage.

        Args:
            input: SimulationInput with entry price, ATR, future path, profile.

        Returns:
            SimulationOutput with adapter_kind=TRAINING in lineage.
        """
        output = simulate(input)
        new_lineage = replace(output.lineage, adapter_kind="TRAINING")
        return replace(output, lineage=new_lineage)
