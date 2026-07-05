"""
TrainingAdapter — side-effect-free simulation for training label generation.

Calls simulate() and guarantees adapter_kind=TRAINING in output lineage.
Implements the SimulationEngine interface (ABC).
No network I/O, no exchange APIs, no XGBoost. Pure deterministic transformation.
"""

from __future__ import annotations

from dataclasses import replace

from simulation.contracts.models import SimulationInput, SimulationOutput
from simulation.engine.engine import simulate
from simulation.engine.interface import SimulationEngine


class TrainingAdapter(SimulationEngine):
    """Deterministic simulation adapter for training pipelines.

    Wraps ``simulate()`` to ensure ``adapter_kind=TRAINING`` in output lineage.
    Identical input always produces identical output (modulo UUID run_id).
    """

    ADAPTER_KIND = "TRAINING"

    def get_adapter_kind(self) -> str:
        return self.ADAPTER_KIND

    def run(self, input: SimulationInput) -> SimulationOutput:
        """Run simulation with TRAINING lineage.

        Args:
            input: SimulationInput with entry price, ATR, future path, profile.

        Returns:
            SimulationOutput with adapter_kind=TRAINING in lineage.

        Raises:
            ValueError: If input or output validation fails.
        """
        errors = self.validate_input(input)
        if errors:
            raise ValueError(
                f"TrainingAdapter input validation failed: {'; '.join(errors)}"
            )
        output = simulate(input)
        lineage = replace(output.lineage, adapter_kind=self.ADAPTER_KIND)
        result = replace(output, lineage=lineage)
        out_errors = self.validate_output(result)
        if out_errors:
            raise ValueError(
                f"TrainingAdapter output validation failed: {'; '.join(out_errors)}"
            )
        return result
