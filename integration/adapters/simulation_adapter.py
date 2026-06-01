"""
SimulationAdapter — Side-effect-free adapter between simulation engine and consumers.

This stub defines the interface for adapters that wrap the simulation engine
for training, evaluation, replay, paper, and live-outcome contexts.

Real implementation: simulation/docs/phases/S3__side-effect-free_adapters.md
Dependency: simulation/ must be implemented first.

Rules:
- Must NOT import simulation, alphaforge, or v7.
- Must NOT have live execution side effects.
- Must be deterministic: same input → same output.
"""

from typing import Any, Dict


class SimulationAdapter:
    """Stub adapter for simulation engine consumption.

    In the real implementation, this adapter wraps SimulationInput → SimulationOutput
    for a specific adapter_kind (TRAINING, EVALUATION, REPLAY, PAPER, LIVE_OUTCOME).
    """

    adapter_kind: str = "TRAINING"

    def run(self, simulation_input: Dict[str, Any]) -> Dict[str, Any]:
        """Run simulation and return SimulationOutput.

        Args:
            simulation_input: Dict matching SimulationInput contract.

        Returns:
            Dict matching SimulationOutput contract.

        Raises:
            NotImplementedError: Real implementation belongs to simulation phase S3.
        """
        raise NotImplementedError(
            "SimulationAdapter.run: real implementation belongs to simulation phase S3. "
            "See simulation/docs/phases/S3__side-effect-free_adapters_and_runtime_hosting.md"
        )


class TrainingAdapter(SimulationAdapter):
    """Side-effect-free adapter for training/label generation contexts."""
    adapter_kind: str = "TRAINING"


class EvaluationAdapter(SimulationAdapter):
    """Side-effect-free adapter for walk-forward evaluation contexts."""
    adapter_kind: str = "EVALUATION"


class ReplayAdapter(SimulationAdapter):
    """Adapter for historical replay contexts."""
    adapter_kind: str = "REPLAY"


class PaperAdapter(SimulationAdapter):
    """Adapter for paper forward simulation contexts."""
    adapter_kind: str = "PAPER"


class LiveOutcomeAdapter(SimulationAdapter):
    """Adapter for live trading outcome normalization."""
    adapter_kind: str = "LIVE_OUTCOME"
