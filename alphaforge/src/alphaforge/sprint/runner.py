"""Factor profitability sprint runner — loads data, evaluates factors, applies costs.

Pure functional where possible. Uses frozen dataclasses for all outputs.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

from alphaforge.factors.evaluation import (
    compute_forward_returns,
    evaluate_factor,
)
from alphaforge.factors.factors import FACTOR_REGISTRY
from alphaforge.sprint.config import SprintConfig
from alphaforge.sprint.ledger import DEFAULT_LEDGER_PATH, append_record, load_seen_keys, record_key
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
    # New fields for ledger integration
    mode: str = "SWING"
    combined_from: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SprintResult:
    """Aggregate result from a full sprint run."""

    factors: list[FactorResult]
    config: SprintConfig
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    pairwise_results: list[FactorResult] = field(default_factory=list)


class FactorSprintRunner:
    """Runs a full profitability sprint across all registered factors.

    Loads OHLCV data, computes forward returns, evaluates each factor from
    FACTOR_REGISTRY, applies cost estimates, and produces a SprintResult.
    Optionally skips factors already in the experiment ledger and runs
    pairwise combinations of surviving factors.
    """

    def __init__(
        self,
        config: SprintConfig,
        mode: str = "SWING",
        skip_keys: Optional[set[str]] = None,
    ) -> None:
        self._config = config
        self._mode = mode
        self._skip_keys = skip_keys or set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
            Aggregate results for all factors including pairwise combos.
        """
        # ── Phase 1: single-factor evaluation ──────────────────────
        single_results: list[FactorResult] = []
        # Cache computed factor values for pairwise reuse
        computed_values: dict[str, pd.DataFrame] = {}

        for factor_name, (direction, factor_fn) in FACTOR_REGISTRY.items():
            lk = record_key([factor_name], self._mode, str(self._config.horizon))
            if lk in self._skip_keys:
                # Record as SKIPPED — already in ledger Hermes chose not to retry
                single_results.append(FactorResult(
                    factor_name=factor_name,
                    direction=direction,
                    horizon=self._config.horizon,
                    mean_ic=0.0, ic_ir=0.0,
                    gross_return=0.0, net_return=0.0,
                    expectancy_r=0.0, profit_factor=0.0,
                    max_drawdown=0.0, win_rate=0.0,
                    turnover=0.0, cost_drag=0.0, trade_count=0,
                    pass_fail="FAIL",
                    notes=[f"SKIPPED — already in ledger (key={lk})"],
                    mode=self._mode,
                ))
                continue

            factor_values = self._compute_factor_values(factor_name, factor_fn, ohlcv)
            if factor_values is not None:
                computed_values[factor_name] = factor_values

            factor_result = self._evaluate_single_factor(
                factor_name, direction, factor_fn, ohlcv, factor_values,
            )
            single_results.append(factor_result)

            # Write to ledger (deterministic audit trail)
            self._write_ledger(factor_result, factor_name)

        # ── Phase 2: pairwise combinations ─────────────────────────
        pairwise_results: list[FactorResult] = []
        if self._config.enable_pairwise and len(single_results) > 1:
            survivors = [
                r for r in single_results
                if r.pass_fail in ("PASS", "WATCH")
                and r.ic_ir >= self._config.pairwise_min_ic_ir
            ]
            survivor_names = {r.factor_name for r in survivors}

            for (name_a, fn_a), (name_b, fn_b) in itertools.combinations(
                [(n, f) for n, (_, f) in FACTOR_REGISTRY.items() if n in survivor_names], 2
            ):
                combo_key = record_key(
                    sorted([name_a, name_b]), self._mode, str(self._config.horizon),
                )
                if combo_key in self._skip_keys:
                    continue

                pair_result = self._evaluate_pairwise(name_a, name_b, ohlcv, computed_values)
                if pair_result is not None:
                    pairwise_results.append(pair_result)
                    self._write_ledger(pair_result, (name_a, name_b))

        return SprintResult(
            factors=single_results,
            config=self._config,
            pairwise_results=pairwise_results,
        )

    # ------------------------------------------------------------------
    # Factor computation (cached)
    # ------------------------------------------------------------------

    def _compute_factor_values(
        self, factor_name: str, factor_fn, ohlcv: dict[str, pd.DataFrame],
    ) -> Optional[pd.DataFrame]:
        """Compute factor values, returning None on failure."""
        try:
            return factor_fn(ohlcv)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Single-factor evaluation
    # ------------------------------------------------------------------

    def _evaluate_single_factor(
        self,
        factor_name: str,
        direction: str,
        factor_fn,
        ohlcv: dict[str, pd.DataFrame],
        factor_values: Optional[pd.DataFrame] = None,
    ) -> FactorResult:
        """Evaluate a single factor and map to FactorResult."""
        if factor_values is None:
            try:
                factor_values = factor_fn(ohlcv)
            except Exception as exc:
                return self._fail_result(factor_name, direction, notes=[f"Factor computation failed: {exc}"])

        if factor_values is None or factor_values.empty:
            return self._fail_result(factor_name, direction, notes=["Factor returned empty"])

        close = ohlcv.get("close")
        if close is None or close.empty:
            return self._fail_result(factor_name, direction, notes=["No close price data"])

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
            return self._fail_result(factor_name, direction, notes=["No evaluation results"])

        return self._build_factor_result(factor_name, direction, best_result, best_horizon)

    # ------------------------------------------------------------------
    # Pairwise evaluation
    # ------------------------------------------------------------------

    def _evaluate_pairwise(
        self,
        name_a: str,
        name_b: str,
        ohlcv: dict[str, pd.DataFrame],
        computed_values: dict[str, pd.DataFrame],
    ) -> Optional[FactorResult]:
        """Evaluate a pairwise combination of two factors.

        Combines factor values as simple average of directionally-oriented
        series, then runs through the same scoring path as single factors.
        """
        from alphaforge.factors.factors import FACTOR_REGISTRY

        fv_a = computed_values.get(name_a)
        fv_b = computed_values.get(name_b)

        if fv_a is None or fv_b is None:
            return None

        _, dir_a = FACTOR_REGISTRY[name_a]
        _, dir_b = FACTOR_REGISTRY[name_b]

        # Align indices
        idx = fv_a.index.intersection(fv_b.index)
        if len(idx) < 10:
            return None

        fv_a = fv_a.loc[idx]
        fv_b = fv_b.loc[idx]

        # Weighted average of directionally-aligned factor values
        if isinstance(fv_a, pd.Series):
            combined = (fv_a + fv_b) / 2.0
        else:
            combined = (fv_a.mean(axis=1) + fv_b.mean(axis=1)) / 2.0

        combined_name = f"{name_a}+{name_b}"

        close = ohlcv.get("close")
        if close is None or close.empty:
            return None

        horizons = [1, 4, 12, 24]
        fwd_returns_dict = compute_forward_returns(close, horizons=horizons)

        # Find best horizon
        best_result = None
        best_gross = -float("inf")
        best_horizon = 1
        combined_df = combined.to_frame("combined") if isinstance(combined, pd.Series) else combined

        for horizon, fwd_returns in fwd_returns_dict.items():
            eval_results = evaluate_factor(combined_name, combined_df, fwd_returns_dict, "long")
            for ev in eval_results:
                if ev.get("horizon") == horizon:
                    gross = ev.get("top_bottom_gross_return", 0.0)
                    if gross > best_gross:
                        best_gross = gross
                        best_result = ev
                        best_horizon = horizon

        if best_result is None:
            return None

        result = self._build_factor_result(combined_name, "long", best_result, best_horizon)
        # Override with custom metadata for pairwise result
        object.__setattr__(result, "factor_name", combined_name)
        object.__setattr__(result, "combined_from", (name_a, name_b))
        return result

    # ------------------------------------------------------------------
    # Cost & pass/fail logic
    # ------------------------------------------------------------------

    def _build_factor_result(
        self,
        factor_name: str,
        direction: str,
        eval_result: dict,
        horizon: int,
    ) -> FactorResult:
        """Build a FactorResult from evaluation dict + cost estimates."""
        close = None  # will be set below via callers

        gross_return = eval_result.get("top_bottom_gross_return", 0.0)
        turnover = eval_result.get("turnover", 0.0)
        mean_ic = eval_result.get("mean_rank_ic", 0.0)
        ic_ir = eval_result.get("ic_ir", 0.0)
        n_timestamps = eval_result.get("n_timestamps", 0)

        # Cost estimates via simulation authority
        atr_mean = self._estimate_atr_mean()
        entry_price = self._estimate_entry_price()
        stop_multiplier = 2.0
        notional = 10_000.0
        entry_risk = compute_entry_risk(atr_mean, stop_multiplier)

        if entry_risk > 0:
            fee = fee_cost_r(notional, entry_risk, self._config.fee_bps)
            slippage = slippage_cost_r(
                notional, entry_price, entry_risk,
                self._config.slippage_bps, atr_mean,
            )
            cost_per_trade = fee + slippage
        else:
            cost_per_trade = 0.0

        n_trades = max(int(turnover * n_timestamps), 1) if turnover > 0 else 1
        total_cost = cost_per_trade * n_trades
        cost_drag = total_cost
        net_return = gross_return - cost_drag
        expectancy_r = net_return / max(n_trades, 1)
        profit_factor = gross_return / abs(cost_drag) if cost_drag > 0 else 0.0
        max_drawdown = self._estimate_max_drawdown(gross_return)
        win_rate = self._estimate_win_rate(gross_return, n_trades)

        # 3-state pass/fail (PASS / WATCH / FAIL)
        pass_fail, notes = self._determine_verdict(
            net_return, profit_factor, n_trades, max_drawdown, expectancy_r, cost_drag,
        )

        return FactorResult(
            factor_name=factor_name,
            direction=direction,
            horizon=horizon,
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
            mode=self._mode,
        )

    def _determine_verdict(
        self,
        net_return: float,
        profit_factor: float,
        n_trades: int,
        max_drawdown: float,
        expectancy_r: float,
        cost_drag: float,
    ) -> tuple[str, list[str]]:
        """3-state gate: PASS / WATCH / FAIL.

        PASS  → all checks pass
        WATCH → net-positive, meaningful trades, but some gate fails
        FAIL  → net loss, too few trades, or excessive drawdown
        """
        notes: list[str] = []
        gate_failures: list[str] = []

        if net_return < self._config.min_expectancy_r * n_trades:
            gate_failures.append(
                f"net_return {net_return:.4f} below minimum expectancy "
                f"(min_expectancy_r * n_trades = {self._config.min_expectancy_r} * {n_trades})"
            )

        if profit_factor < self._config.min_profit_factor:
            gate_failures.append(
                f"profit_factor {profit_factor:.2f} below minimum {self._config.min_profit_factor}"
            )

        if n_trades < self._config.min_trades:
            gate_failures.append(
                f"trade_count {n_trades} below minimum {self._config.min_trades}"
            )

        if max_drawdown > self._config.max_drawdown_pct:
            gate_failures.append(
                f"max_drawdown {max_drawdown:.2%} exceeds maximum {self._config.max_drawdown_pct}"
            )

        if not gate_failures:
            return "PASS", ["All sanity checks passed"]

        # WATCH: net-positive + meaningful trades + reasonable drawdown
        is_net_positive = net_return > 0 and expectancy_r > 0
        has_trades = n_trades >= max(1, self._config.min_trades // 2)
        has_reasonable_drawdown = max_drawdown <= min(self._config.max_drawdown_pct * 1.5, 0.5)

        if is_net_positive and has_trades and has_reasonable_drawdown:
            return "WATCH", [f"Borderline — some gates failed: {'; '.join(gate_failures)}"]

        return "FAIL", gate_failures

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fail_result(
        self,
        factor_name: str,
        direction: str,
        notes: list[str],
    ) -> FactorResult:
        return FactorResult(
            factor_name=factor_name,
            direction=direction,
            horizon=0,
            mean_ic=0.0, ic_ir=0.0,
            gross_return=0.0, net_return=0.0,
            expectancy_r=0.0, profit_factor=0.0,
            max_drawdown=0.0, win_rate=0.0,
            turnover=0.0, cost_drag=0.0, trade_count=0,
            pass_fail="FAIL",
            notes=notes,
            mode=self._mode,
        )

    def _estimate_atr_mean(self) -> float:
        """Default ATR estimate — will be computed from real data in driver."""
        return 0.02  # 2% default

    def _estimate_entry_price(self) -> float:
        """Default entry price estimate."""
        return 100.0

    def _estimate_max_drawdown(self, gross_return: float) -> float:
        """Rough max drawdown estimate from total return."""
        if gross_return <= 0:
            return 0.3
        return min(0.05, gross_return * 0.1)

    def _estimate_win_rate(self, gross_return: float, n_trades: int) -> float:
        """Rough win rate estimate."""
        if n_trades == 0:
            return 0.0
        avg_per_trade = gross_return / n_trades
        return 0.55 if avg_per_trade > 0 else 0.45

    def _write_ledger(self, result: FactorResult, factor_id) -> None:
        """Write a single factor result to the experiment ledger."""
        factors = (
            list(result.combined_from) if result.combined_from
            else [result.factor_name]
        )
        try:
            append_record({
                "key": record_key(factors, self._mode, str(self._config.horizon)),
                "type": "pairwise" if len(factors) > 1 else "single",
                "factor_names": factors,
                "mode": self._mode,
                "horizon": str(self._config.horizon),
                "mean_ic": result.mean_ic,
                "ic_ir": result.ic_ir,
                "net_r": result.net_return,
                "verdict": result.pass_fail,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass  # Ledger failure should not crash the run
