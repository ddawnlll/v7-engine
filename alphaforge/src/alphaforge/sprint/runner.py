"""Factor profitability sprint runner — loads data, evaluates factors, applies costs.

Pure functional where possible. Uses frozen dataclasses for all outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from alphaforge.factors.evaluation import (
    compute_forward_returns,
    evaluate_factor,
)
from alphaforge.factors.factors import FACTOR_REGISTRY
from alphaforge.sprint.config import SprintConfig
from simulation.authority import get_cost_constants
from simulation.engine.costs import (
    compute_entry_risk,
    fee_cost_r,
    slippage_cost_r,
)


@dataclass(frozen=True)
class FactorResult:
    """Immutable result for a single factor evaluation."""

    factor_name: str
    direction: str  # "long", "short", "agnostic"
    horizon: int  # bars (1, 4, 12, 24)
    mean_ic: float
    ic_ir: float
    gross_return: float
    net_return: float
    expectancy_r: float
    profit_factor: float
    max_drawdown: float
    win_rate: float
    turnover: float
    cost_drag: float
    trade_count: int
    pass_fail: str  # "PASS", "WATCH", "FAIL"
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SprintResult:
    """Aggregate result from a full sprint run."""

    factors: list[FactorResult]
    config: SprintConfig
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class FactorSprintRunner:
    """Runs a full profitability sprint across all registered factors.

    Loads OHLCV data, computes forward returns, evaluates each factor from
    FACTOR_REGISTRY, applies cost estimates, and produces a SprintResult.
    """

    def __init__(self, config: SprintConfig) -> None:
        self._config = config

    def run(self, ohlcv: dict[str, pd.DataFrame]) -> SprintResult:
        """Execute the sprint on provided OHLCV data.

        Parameters
        ----------
        ohlcv : dict[str, pd.DataFrame]
            Dict mapping column name -> DataFrame[timestamps x symbols].
            Must include 'close', 'high', 'low', 'open', 'volume'.

        Returns
        -------
        SprintResult
            Aggregate results for all factors.
        """
        results: list[FactorResult] = []

        for factor_name, (direction, factor_fn) in FACTOR_REGISTRY.items():
            factor_result = self._evaluate_single_factor(
                factor_name, direction, factor_fn, ohlcv
            )
            results.append(factor_result)

        return SprintResult(
            factors=results,
            config=self._config,
        )

    def _evaluate_single_factor(
        self,
        factor_name: str,
        direction: str,
        factor_fn,
        ohlcv: dict[str, pd.DataFrame],
    ) -> FactorResult:
        """Evaluate a single factor and map to FactorResult."""
        # Compute factor values
        try:
            factor_values = factor_fn(ohlcv)
        except Exception as exc:
            return FactorResult(
                factor_name=factor_name,
                direction=direction,
                horizon=0,
                mean_ic=0.0,
                ic_ir=0.0,
                gross_return=0.0,
                net_return=0.0,
                expectancy_r=0.0,
                profit_factor=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                turnover=0.0,
                cost_drag=0.0,
                trade_count=0,
                pass_fail="FAIL",
                notes=[f"Factor computation failed: {exc}"],
            )

        if factor_values is None or factor_values.empty:
            return FactorResult(
                factor_name=factor_name,
                direction=direction,
                horizon=0,
                mean_ic=0.0,
                ic_ir=0.0,
                gross_return=0.0,
                net_return=0.0,
                expectancy_r=0.0,
                profit_factor=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                turnover=0.0,
                cost_drag=0.0,
                trade_count=0,
                pass_fail="FAIL",
                notes=["Factor returned empty"],
            )

        # Compute forward returns for all horizons
        close = ohlcv.get("close")
        if close is None or close.empty:
            return FactorResult(
                factor_name=factor_name,
                direction=direction,
                horizon=0,
                mean_ic=0.0,
                ic_ir=0.0,
                gross_return=0.0,
                net_return=0.0,
                expectancy_r=0.0,
                profit_factor=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                turnover=0.0,
                cost_drag=0.0,
                trade_count=0,
                pass_fail="FAIL",
                notes=["No close price data"],
            )

        horizons = [1, 4, 12, 24]
        fwd_returns_dict = compute_forward_returns(close, horizons=horizons)

        # Evaluate across horizons, pick best by gross return
        best_result = None
        best_gross = -float("inf")
        best_horizon = 1

        for horizon, fwd_returns in fwd_returns_dict.items():
            eval_results = evaluate_factor(factor_name, factor_values, fwd_returns_dict, direction)
            for ev in eval_results:
                if ev.get("horizon") == horizon:
                    gross = ev.get("top_bottom_gross_return", 0.0)
                    if gross > best_gross:
                        best_gross = gross
                        best_result = ev
                        best_horizon = horizon

        if best_result is None:
            return FactorResult(
                factor_name=factor_name,
                direction=direction,
                horizon=1,
                mean_ic=0.0,
                ic_ir=0.0,
                gross_return=0.0,
                net_return=0.0,
                expectancy_r=0.0,
                profit_factor=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                turnover=0.0,
                cost_drag=0.0,
                trade_count=0,
                pass_fail="FAIL",
                notes=["No evaluation results"],
            )

        gross_return = best_result.get("top_bottom_gross_return", 0.0)
        turnover = best_result.get("turnover", 0.0)
        mean_ic = best_result.get("mean_rank_ic", 0.0)
        ic_ir = best_result.get("ic_ir", 0.0)
        n_timestamps = best_result.get("n_timestamps", 0)

        # Estimate cost per trade using ATR-based model
        atr = self._estimate_atr(close)
        atr_mean = atr.mean().mean() if not atr.empty else 0.0
        entry_price = close.mean().mean() if not close.empty else 1.0

        # Conservative: 2x ATR stop, 10k notional
        stop_multiplier = 2.0
        notional = 10_000.0
        entry_risk = compute_entry_risk(atr_mean, stop_multiplier)

        if entry_risk > 0:
            fee_per_trade = fee_cost_r(notional, entry_risk, self._config.fee_bps)
            slippage_per_trade = slippage_cost_r(
                notional, entry_price, entry_risk,
                self._config.slippage_bps, atr_mean,
            )
            cost_per_trade = fee_per_trade + slippage_per_trade
        else:
            cost_per_trade = 0.0

        # Apply costs to gross return
        n_trades = max(int(turnover * n_timestamps), 1) if turnover > 0 else 1
        total_cost = cost_per_trade * n_trades
        cost_drag = total_cost
        net_return = gross_return - cost_drag

        # Compute additional metrics
        expectancy_r = net_return / max(n_trades, 1)
        profit_factor = (
            gross_return / abs(cost_drag) if cost_drag > 0 else 0.0
        )
        max_drawdown = self._estimate_max_drawdown(gross_return)
        win_rate = self._estimate_win_rate(gross_return, n_trades)

        # Determine pass/fail
        pass_fail = "PASS"
        notes: list[str] = []

        if net_return < self._config.min_expectancy_r * n_trades:
            pass_fail = "FAIL"
            notes.append(f"net_return {net_return:.4f} below minimum expectancy")

        if profit_factor < self._config.min_profit_factor:
            pass_fail = "FAIL"
            notes.append(f"profit_factor {profit_factor:.2f} below minimum {self._config.min_profit_factor}")

        if n_trades < self._config.min_trades:
            pass_fail = "FAIL"
            notes.append(f"trade_count {n_trades} below minimum {self._config.min_trades}")

        if max_drawdown > self._config.max_drawdown_pct:
            pass_fail = "FAIL"
            notes.append(f"max_drawdown {max_drawdown:.2%} exceeds maximum {self._config.max_drawdown_pct}")

        if not notes:
            notes.append("All sanity checks passed")

        return FactorResult(
            factor_name=factor_name,
            direction=direction,
            horizon=best_horizon,
            mean_ic=mean_ic,
            ic_ir=ic_ir,
            gross_return=gross_return,
            net_return=net_return,
            expectancy_r=expectancy_r,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            turnover=turnover,
            cost_drag=cost_drag,
            trade_count=n_trades,
            pass_fail=pass_fail,
            notes=notes,
        )

    def _estimate_atr(self, close: pd.DataFrame) -> pd.DataFrame:
        """Estimate ATR from close prices using rolling volatility."""
        if close.empty or len(close) < 2:
            return close * 0.0  # Return zero DataFrame of same shape

        returns = close.pct_change()
        rolling_vol = returns.rolling(window=20, min_periods=10).std()
        atr = rolling_vol * close * (20 ** 0.5)
        return atr

    def _estimate_max_drawdown(self, gross_return: float) -> float:
        """Rough max drawdown estimate from total return."""
        if gross_return <= 0:
            return 0.3  # Assume high drawdown for negative returns
        return min(0.05, gross_return * 0.1)

    def _estimate_win_rate(self, gross_return: float, n_trades: int) -> float:
        """Rough win rate estimate."""
        if n_trades == 0:
            return 0.0
        avg_per_trade = gross_return / n_trades
        return 0.55 if avg_per_trade > 0 else 0.45
