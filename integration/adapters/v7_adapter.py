"""
V7Adapter — Adapter for consuming simulation outputs into V7 lifecycle.

This stub defines the interface for transforming simulation outputs into
V7 TradeOutcome records and integrating with the decision lifecycle.

Real implementation: v7/docs/implementation/phase_2_simulation_truth_layer.md
Dependency: simulation/ must be implemented first.

Rules:
- Must NOT import simulation, alphaforge, or v7.
- Must not duplicate simulation semantics.
- Must preserve simulation lineage in TradeOutcome.
"""

from typing import Any, Dict, Optional


class V7Adapter:
    """Stub adapter for V7 runtime simulation hosting and outcome normalization.

    In the real implementation, this adapter hosts the simulation engine
    and normalizes SimulationOutput into TradeOutcome lifecycle records.
    """

    def build_trade_outcome(
        self,
        simulation_output: Dict[str, Any],
        decision_event: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build a TradeOutcome from a simulation output.

        Args:
            simulation_output: Dict matching SimulationOutput contract.
            decision_event: Optional dict matching DecisionEvent contract for
                lineage linking.

        Returns:
            Dict matching TradeOutcome contract.

        Raises:
            NotImplementedError: Real implementation belongs to v7 phase 2.
        """
        raise NotImplementedError(
            "V7Adapter.build_trade_outcome: real implementation belongs to v7 phase 2. "
            "See v7/docs/implementation/phase_2_simulation_truth_layer.md"
        )

    def normalize_outcome(
        self,
        execution_result: Dict[str, Any],
        simulation_output: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Normalize a live/paper execution result with simulation evidence.

        Args:
            execution_result: Execution data from broker/paper engine.
            simulation_output: Simulated comparative evidence.

        Returns:
            Dict matching TradeOutcome contract with resolved outcome.

        Raises:
            NotImplementedError: Real implementation belongs to v7 phase 2.
        """
        raise NotImplementedError(
            "V7Adapter.normalize_outcome: real implementation belongs to v7 phase 2."
        )


class RuntimeSimulationHost(V7Adapter):
    """Stub for runtime-hosted simulation engine.

    Hosts simulation execution for paper forward, historical replay,
    and live outcome normalization contexts.
    """
    pass
