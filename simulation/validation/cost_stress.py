"""
Cost stress testing framework.

Runs simulation at multiple cost multipliers to detect cost-dependent edge.
Industry best practice for evaluating strategy robustness to trading costs.

Usage:
    runner = CostStressRunner()
    results = runner.stress(my_input)
    if runner.is_cost_sensitive(results):
        # Strategy edge is sensitive to costs
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from simulation.contracts.models import SimulationInput, SimulationOutput
from simulation.engine.engine import simulate


@dataclass
class CostStressResult:
    """Result of a single cost stress run.

    Attributes:
        multiplier: Cost multiplier applied (e.g., 1.5 = 50% higher costs).
        outputs: SimulationOutput produced at this cost level.
    """

    multiplier: float
    outputs: SimulationOutput


class CostStressRunner:
    """Runs simulation at multiple cost multipliers.

    Scales fee and slippage costs proportionally to detect how sensitive
    a strategy's edge is to trading costs.  Uses monkey-patching of
    total_cost_r defaults to avoid engine or contract changes.

    Industry context: cost stress is standard practice in systematic
    trading to verify that a strategy's edge survives realistic and
    stressed cost assumptions.
    """

    # Default multipliers to run
    MULTIPLIERS: List[float] = [1.0, 1.5, 2.0, 3.0]

    def stress(self, input_data: SimulationInput) -> List[CostStressResult]:
        """Run simulation at each cost multiplier.

        For each multiplier, the fee and slippage defaults in
        total_cost_r are scaled proportionally before calling simulate(),
        then restored.

        Args:
            input_data: Baseline simulation input.

        Returns:
            List of CostStressResult, one per multiplier in ascending order.
        """
        import simulation.engine.costs as cost_mod

        results: List[CostStressResult] = []
        # Snapshot original defaults before any modification
        orig_defaults = cost_mod.total_cost_r.__defaults__

        for m in self.MULTIPLIERS:
            try:
                self._apply_cost_multiplier(cost_mod, m)
                output = simulate(input_data)
            finally:
                cost_mod.total_cost_r.__defaults__ = orig_defaults

            results.append(CostStressResult(multiplier=m, outputs=output))

        return results

    @staticmethod
    def _apply_cost_multiplier(
        cost_mod: object,
        multiplier: float,
    ) -> None:
        """Patch total_cost_r defaults to scale fee and slippage.

        total_cost_r signature:
          def total_cost_r(notional, entry_price, atr, stop_multiplier,
                           taker_fee_bps=4.0, slippage_bps=1.0,
                           funding_rate=0.0, holding_bars=0) -> ...

        __defaults__ order: (fee_bps, slippage_bps, funding_rate, holding_bars)
        """
        orig = cost_mod.total_cost_r.__defaults__
        cost_mod.total_cost_r.__defaults__ = (
            orig[0] * multiplier,  # scale taker_fee_bps
            orig[1] * multiplier,  # scale slippage_bps
            orig[2],               # keep funding_rate unchanged
            orig[3],               # keep holding_bars unchanged
        )

    @staticmethod
    def is_cost_sensitive(results: List[CostStressResult]) -> bool:
        """Check if best directional net R declines with higher cost multipliers.

        A strategy is cost-sensitive if the best available directional net R
        (max of long and short realized_r_net) decreases monotonically as
        the cost multiplier increases.

        Args:
            results: CostStressResult list sorted by ascending multiplier.

        Returns:
            True if best directional realized_r_net decreases strictly
            monotonically as cost multiplier increases.
        """
        if len(results) < 2:
            return False

        prev_best_net: float = float("inf")
        for r in results:
            best_directional_net = max(
                r.outputs.long_outcome.realized_r_net,
                r.outputs.short_outcome.realized_r_net,
            )
            # Strictly decreasing check (allow 1e-9 float tolerance)
            if best_directional_net >= prev_best_net - 1e-9:
                return False
            prev_best_net = best_directional_net

        return True
