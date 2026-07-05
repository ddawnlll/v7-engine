from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class CostSanityReport:
    """Immutable result of a cost sanity check."""

    gross_return: float
    net_return: float
    cost_drag: float
    cost_drag_pct: float
    sanity_pass: bool


class CostSanityChecker:
    """Pure-functional cost sanity checker.

    Evaluates whether a factor's gross return survives estimated trading costs.
    Uses a simplified per-period cost model: each period incurs entry + exit
    costs as a fraction of 1R (full position). Cost = 2 * (fee_bps + slippage_bps)
    / 10000.0 per period.
    """

    def check(
        self,
        gross_returns: pd.Series,
        fee_bps: float = 4.0,
        slippage_bps: float = 1.0,
        holding_period: float = 1.0,
    ) -> CostSanityReport:
        """Check cost sanity for a series of gross returns.

        Parameters
        ----------
        gross_returns : pd.Series
            Time series of gross returns per period (in R-multiples).
        fee_bps : float
            Fee cost in basis points per trade (applied entry + exit).
        slippage_bps : float
            Slippage cost in basis points per trade (applied entry + exit).
        holding_period : float
            Holding period in periods (default 1). Not used in the
            simplified cost model — reserved for future funding cost
            calculations.

        Returns
        -------
        CostSanityReport
            Immutable report with cost analysis.
        """
        if gross_returns.empty:
            return CostSanityReport(
                gross_return=0.0,
                net_return=0.0,
                cost_drag=0.0,
                cost_drag_pct=0.0,
                sanity_pass=False,
            )

        # Per-period cost drag estimate (entry + exit, both sides)
        # Assumes 1R represents a full position.
        fee_per_period = 2.0 * fee_bps / 10000.0
        slippage_per_period = 2.0 * slippage_bps / 10000.0
        total_cost_per_period = fee_per_period + slippage_per_period

        gross_return = float(gross_returns.sum())
        cost_drag = total_cost_per_period * len(gross_returns)
        net_return = gross_return - cost_drag
        cost_drag_pct = abs(cost_drag / gross_return) * 100.0 if gross_return != 0 else 0.0
        sanity_pass = net_return > 0.0

        return CostSanityReport(
            gross_return=gross_return,
            net_return=net_return,
            cost_drag=cost_drag,
            cost_drag_pct=cost_drag_pct,
            sanity_pass=sanity_pass,
        )
