"""Minimal eval gate for the AlphaForge profitability sprint.

Defines pass/fail gates for factor candidates. Pure functional, frozen dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from alphaforge.sprint.config import SprintConfig
from alphaforge.sprint.runner import FactorResult


@dataclass(frozen=True)
class GateResult:
    """Result of a single gate evaluation."""

    gate_name: str
    passed: bool
    value: float
    threshold: float
    details: str


@dataclass(frozen=True)
class EvalGate:
    """Aggregate evaluation gate result for a factor."""

    gates: list[GateResult]
    overall_pass: bool
    summary: str


class EvalGateRunner:
    """Evaluates a FactorResult against a set of pass/fail gates."""

    def __init__(self, config: SprintConfig) -> None:
        self._config = config

    def evaluate(self, factor: FactorResult) -> EvalGate:
        """Run all gates on a factor result.

        Parameters
        ----------
        factor : FactorResult
            The factor evaluation result to gate.

        Returns
        -------
        EvalGate
            Gate results with overall pass/fail.
        """
        gates: list[GateResult] = []

        # Gate 1: MIN_TRADES
        gates.append(
            GateResult(
                gate_name="MIN_TRADES",
                passed=factor.trade_count >= self._config.min_trades,
                value=float(factor.trade_count),
                threshold=float(self._config.min_trades),
                details=f"trade_count={factor.trade_count}, min={self._config.min_trades}",
            )
        )

        # Gate 2: IC_SIGNAL — weak but non-zero signal
        ic_threshold = 0.01
        gates.append(
            GateResult(
                gate_name="IC_SIGNAL",
                passed=factor.mean_ic > ic_threshold,
                value=factor.mean_ic,
                threshold=ic_threshold,
                details=f"mean_ic={factor.mean_ic:.4f}, min={ic_threshold}",
            )
        )

        # Gate 3: IC_STABILITY — signal is stable
        ic_ir_threshold = 0.15
        gates.append(
            GateResult(
                gate_name="IC_STABILITY",
                passed=factor.ic_ir > ic_ir_threshold,
                value=factor.ic_ir,
                threshold=ic_ir_threshold,
                details=f"ic_ir={factor.ic_ir:.4f}, min={ic_ir_threshold}",
            )
        )

        # Gate 4: NET_POSITIVE — survives costs
        gates.append(
            GateResult(
                gate_name="NET_POSITIVE",
                passed=factor.net_return > 0,
                value=factor.net_return,
                threshold=0.0,
                details=f"net_return={factor.net_return:.4f}, must be > 0",
            )
        )

        # Gate 5: PROFIT_FACTOR
        gates.append(
            GateResult(
                gate_name="PROFIT_FACTOR",
                passed=factor.profit_factor > self._config.min_profit_factor,
                value=factor.profit_factor,
                threshold=self._config.min_profit_factor,
                details=f"profit_factor={factor.profit_factor:.2f}, min={self._config.min_profit_factor}",
            )
        )

        # Gate 6: DRAWDOWN
        gates.append(
            GateResult(
                gate_name="DRAWDOWN",
                passed=factor.max_drawdown <= self._config.max_drawdown_pct,
                value=factor.max_drawdown,
                threshold=self._config.max_drawdown_pct,
                details=f"max_drawdown={factor.max_drawdown:.2%}, max={self._config.max_drawdown_pct:.0%}",
            )
        )

        # Gate 7: COST_SURVIVAL — costs don't kill 50%+ of alpha
        cost_survival_threshold = abs(factor.gross_return) * 0.5 if factor.gross_return != 0 else 0.0
        cost_survived = factor.cost_drag < cost_survival_threshold if cost_survival_threshold > 0 else True
        gates.append(
            GateResult(
                gate_name="COST_SURVIVAL",
                passed=cost_survived,
                value=factor.cost_drag,
                threshold=cost_survival_threshold,
                details=f"cost_drag={factor.cost_drag:.4f}, max_allowed={cost_survival_threshold:.4f}",
            )
        )

        overall_pass = all(g.passed for g in gates)
        failed_gates = [g.gate_name for g in gates if not g.passed]

        if overall_pass:
            summary = f"ALL GATES PASSED — {factor.factor_name} is a candidate"
        else:
            summary = f"FAILED: {', '.join(failed_gates)} — {factor.factor_name} rejected"

        return EvalGate(
            gates=gates,
            overall_pass=overall_pass,
            summary=summary,
        )
