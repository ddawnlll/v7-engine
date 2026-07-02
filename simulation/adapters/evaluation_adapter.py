"""
EvaluationAdapter — side-effect-free simulation for evaluation label generation.

Calls simulate() and guarantees adapter_kind=EVALUATION in output lineage.
No network I/O, no exchange APIs, no XGBoost. Pure deterministic transformation.
"""

from __future__ import annotations

from dataclasses import replace

from simulation.contracts.models import SimulationInput, SimulationOutput
from simulation.engine.engine import simulate


class EvaluationAdapter:
    """Deterministic simulation adapter for evaluation pipelines.

    Wraps ``simulate()`` to ensure ``adapter_kind=EVALUATION`` in output lineage.
    Identical input always produces identical output (modulo UUID run_id).
    """

    def run(self, input: SimulationInput) -> SimulationOutput:
        """Run simulation with EVALUATION lineage.

        Args:
            input: SimulationInput with entry price, ATR, future path, profile.

        Returns:
            SimulationOutput with adapter_kind=EVALUATION in lineage.
        """
        output = simulate(input)
        new_lineage = replace(output.lineage, adapter_kind="EVALUATION")
        return replace(output, lineage=new_lineage)
