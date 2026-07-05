"""
Business validation for Policy Critic — profitability, unit economics, and kill criteria.

This module provides tools for measuring whether the Policy Critic adds positive
net trading expectancy, quantifying its per-decision cost, and documenting
conditions under which the critic should be disabled.

Key functions:
  - ProfitabilityAnalyzer:     Measures critic impact on net trading expectancy
                               using shadow comparison methodology.
  - UnitEconomicsValidator:    Computes cost per critic decision and validates
                               against engineering/infrastructure budgets.
  - KillCriteriaDocumenter:    Documents conditions that trigger critic disablement,
                               with automatic detection rules.

Flow (Phase 6, per ai_summary §Staged Rollout):
  Shadow comparison data (with-critic vs without-critic trades)
    -> ProfitabilityAnalyzer.analyze()
    -> ProfitabilityReport

  Cost data + critic decision volume
    -> UnitEconomicsValidator.validate()
    -> UnitEconomicsVerdict

  Safety metrics + business thresholds
    -> KillCriteriaDocumenter.evaluate()
    -> KillCriteriaResult

Domain boundaries:
  - Does NOT make disablement decisions (reports to operator)
  - Does NOT alter critic behavior or runtime logic
  - Is NOT a live service — designed for periodic offline analysis
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Profitability analysis
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TradeRecord:
    """A single trade record for profitability comparison.

    Attributes:
        trade_id:         Unique trade identifier.
        symbol:           Trading symbol.
        mode:             Trading mode (SWING, SCALP, etc.).
        realized_r_net:   Realized R-net (post-cost).
        direction:        LONG or SHORT.
        with_critic:      True if the critic was active (influence or shadow).
        critic_verdict:   Critic's verdict for this trade (if available).
        timestamp:        ISO 8601 of trade entry.
        entry_price:      Entry price.
        exit_price:       Exit price.
        fee_cost_r:       Fee cost in R.
        slippage_cost_r:  Slippage cost in R.
    """
    trade_id: str
    symbol: str
    mode: str
    realized_r_net: float
    direction: str
    with_critic: bool
    critic_verdict: str = "NOT_EVALUATED"
    timestamp: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    fee_cost_r: float = 0.0
    slippage_cost_r: float = 0.0


@dataclass(frozen=True)
class ProfitabilityReport:
    """Profitability comparison between critic-on and critic-off groups.

    Attributes:
        n_critic_on:         Number of trades with critic active.
        n_critic_off:        Number of trades without critic (baseline).
        mean_r_critic_on:    Mean realized R-net with critic.
        mean_r_critic_off:   Mean realized R-net without critic.
        mean_r_delta:        Difference (critic_on - critic_off).
        win_rate_critic_on:  Win rate with critic.
        win_rate_critic_off: Win rate without critic.
        profit_factor_on:    Gross profit / gross loss (critic on).
        profit_factor_off:   Gross profit / gross loss (critic off).
        sharpe_delta:        Sharpe ratio difference (annualised).
        dsr_p_value:         Deflated Sharpe Ratio p-value (if computed).
        improvement_dir:     "POSITIVE", "NEGATIVE", or "NEUTRAL".
        per_mode_breakdown:  dict[mode, {delta, n_on, n_off}].
        drawdown_max_on:     Maximum drawdown with critic.
        drawdown_max_off:    Maximum drawdown without critic.
        avg_trade_cost_on:   Average cost per trade with critic.
        avg_trade_cost_off:  Average cost per trade without critic.
        is_significant:      True if improvement is statistically significant.
        analysis_timestamp:  ISO 8601 of this analysis.
    """
    n_critic_on: int = 0
    n_critic_off: int = 0
    mean_r_critic_on: float = 0.0
    mean_r_critic_off: float = 0.0
    mean_r_delta: float = 0.0
    win_rate_critic_on: float = 0.0
    win_rate_critic_off: float = 0.0
    profit_factor_on: float = 0.0
    profit_factor_off: float = 0.0
    sharpe_delta: float = 0.0
    dsr_p_value: float = 1.0
    improvement_dir: str = "NEUTRAL"
    per_mode_breakdown: dict[str, dict[str, float]] = field(default_factory=dict)
    drawdown_max_on: float = 0.0
    drawdown_max_off: float = 0.0
    avg_trade_cost_on: float = 0.0
    avg_trade_cost_off: float = 0.0
    is_significant: bool = False
    analysis_timestamp: str = ""


class ProfitabilityAnalyzer:
    """Analyse whether the Policy Critic adds positive net expectancy.

    Compares two groups of trades:
      - critic_on:  trades where the critic was active (shadow or influence)
      - critic_off: trades from the same period without critic (baseline)

    Key metrics:
      - Mean R-net difference (delta)
      - Win rate delta
      - Profit factor delta
      - Sharpe ratio delta (annualised)
      - Deflated Sharpe Ratio p-value
      - Per-mode breakdown
      - Drawdown comparison

    The analysis is designed to be run offline on accumulated shadow data
    (Phase 6, ≥90 days recommended per ai_summary).
    """

    def __init__(
        self,
        *,
        annualisation_factor: float = 252.0,
        significance_p_threshold: float = 0.05,
    ):
        """Initialise the profitability analyser.

        Args:
            annualisation_factor: Number of trading periods per year (default 252).
            significance_p_threshold: p-value below which improvement is
                                      considered statistically significant.
        """
        self.annualisation_factor = annualisation_factor
        self.significance_p_threshold = significance_p_threshold

    def analyze(self, trades: list[TradeRecord]) -> ProfitabilityReport:
        """Run profitability analysis on a list of trade records.

        Args:
            trades: List of TradeRecord instances with with_critic flag set.

        Returns:
            ProfitabilityReport with comparison metrics.
        """
        on_trades = [t for t in trades if t.with_critic]
        off_trades = [t for t in trades if not t.with_critic]

        if not on_trades or not off_trades:
            return self._empty_report("Need both critic_on and critic_off trades.")

        n_on, n_off = len(on_trades), len(off_trades)

        # Mean R-net
        r_on = [t.realized_r_net for t in on_trades]
        r_off = [t.realized_r_net for t in off_trades]
        mean_on = statistics.mean(r_on) if r_on else 0.0
        mean_off = statistics.mean(r_off) if r_off else 0.0
        delta = mean_on - mean_off

        # Win rate
        wr_on = sum(1 for t in on_trades if t.realized_r_net > 0) / n_on if n_on > 0 else 0.0
        wr_off = sum(1 for t in off_trades if t.realized_r_net > 0) / n_off if n_off > 0 else 0.0

        # Profit factor
        pf_on = self._profit_factor(r_on)
        pf_off = self._profit_factor(r_off)

        # Sharpe ratio (daily if applicable)
        sharpe_on = self._sharpe_ratio(r_on)
        sharpe_off = self._sharpe_ratio(r_off)
        sharpe_d = (sharpe_on - sharpe_off) if sharpe_on is not None and sharpe_off is not None else 0.0

        # Drawdown (simple maximum cumulative drawdown)
        dd_on = self._max_drawdown(r_on)
        dd_off = self._max_drawdown(r_off)

        # Average cost per trade
        avg_cost_on = statistics.mean(
            [t.fee_cost_r + t.slippage_cost_r for t in on_trades]
        ) if on_trades else 0.0
        avg_cost_off = statistics.mean(
            [t.fee_cost_r + t.slippage_cost_r for t in off_trades]
        ) if off_trades else 0.0

        # Per-mode breakdown
        per_mode: dict[str, dict[str, float]] = {}
        all_modes = {t.mode for t in trades if t.mode}
        for mode in sorted(all_modes):
            mo = [t for t in on_trades if t.mode == mode]
            mf = [t for t in off_trades if t.mode == mode]
            mo_mean = statistics.mean([t.realized_r_net for t in mo]) if mo else 0.0
            mf_mean = statistics.mean([t.realized_r_net for t in mf]) if mf else 0.0
            per_mode[mode] = {
                "delta": round(mo_mean - mf_mean, 6),
                "n_on": len(mo),
                "n_off": len(mf),
            }

        # Deflated Sharpe p-value (approximate: uses student t-test on means)
        dsr_p = self._approximate_dsr_p(r_on, r_off)

        # Significance
        improvement_dir = "POSITIVE" if delta > 0 else "NEGATIVE" if delta < 0 else "NEUTRAL"
        is_sig = dsr_p < self.significance_p_threshold and delta > 0

        return ProfitabilityReport(
            n_critic_on=n_on,
            n_critic_off=n_off,
            mean_r_critic_on=round(mean_on, 6),
            mean_r_critic_off=round(mean_off, 6),
            mean_r_delta=round(delta, 6),
            win_rate_critic_on=round(wr_on, 4),
            win_rate_critic_off=round(wr_off, 4),
            profit_factor_on=round(pf_on, 4),
            profit_factor_off=round(pf_off, 4),
            sharpe_delta=round(sharpe_d, 4),
            dsr_p_value=round(dsr_p, 6),
            improvement_dir=improvement_dir,
            per_mode_breakdown=per_mode,
            drawdown_max_on=round(dd_on, 6),
            drawdown_max_off=round(dd_off, 6),
            avg_trade_cost_on=round(avg_cost_on, 6),
            avg_trade_cost_off=round(avg_cost_off, 6),
            is_significant=is_sig,
            analysis_timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _profit_factor(returns: list[float]) -> float:
        """Compute profit factor: sum(gains) / sum(losses)."""
        gains = sum(r for r in returns if r > 0)
        losses = abs(sum(r for r in returns if r < 0))
        return gains / losses if losses > 0 else float("inf") if gains > 0 else 1.0

    @staticmethod
    def _sharpe_ratio(returns: list[float]) -> float | None:
        """Compute annualised Sharpe ratio from per-trade returns.

        Approximate: assumes each trade is one period.
        """
        if len(returns) < 2:
            return None
        mu = statistics.mean(returns)
        sigma = statistics.stdev(returns)
        if sigma == 0:
            return mu * math.sqrt(252) if mu != 0 else 0.0
        return mu / sigma * math.sqrt(252)

    @staticmethod
    def _max_drawdown(returns: list[float]) -> float:
        """Compute maximum cumulative drawdown from a sequence of returns."""
        if not returns:
            return 0.0
        cum = 0.0
        peak = 0.0
        max_dd = 0.0
        for r in returns:
            cum += r
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd
        return max_dd

    def _approximate_dsr_p(
        self,
        returns_on: list[float],
        returns_off: list[float],
    ) -> float:
        """Approximate Deflated Sharpe Ratio p-value via two-sample t-test.

        This is a rough approximation — the full DSR (Bailey & Lopez de Prado
        2014) accounts for multiple testing and non-normality. For the offline
        analysis phase, this provides directional signal; replace with the
        full DSR computation before making live decisions.
        """
        if len(returns_on) < 3 or len(returns_off) < 3:
            return 1.0
        try:
            mu_on = statistics.mean(returns_on)
            mu_off = statistics.mean(returns_off)
            var_on = statistics.variance(returns_on) if len(returns_on) > 1 else 0.0
            var_off = statistics.variance(returns_off) if len(returns_off) > 1 else 0.0
        except statistics.StatisticsError:
            return 1.0

        n_on, n_off = len(returns_on), len(returns_off)

        # Welch's t-test
        se = math.sqrt(var_on / n_on + var_off / n_off) if (var_on + var_off) > 0 else 0.0
        if se == 0:
            return 1.0

        t_stat = (mu_on - mu_off) / se

        # Approximate p-value from normal distribution (conservative)
        # Using the survival function of the normal: 1 - Phi(|t|)
        p = 2.0 * (1.0 - self._normal_cdf(abs(t_stat)))
        return max(0.0, min(1.0, p))

    @staticmethod
    def _normal_cdf(x: float) -> float:
        """Standard normal CDF using the Abramowitz and Stegun approximation."""
        if x < 0:
            return 1.0 - ProfitabilityAnalyzer._normal_cdf(-x)
        # Constants for approximation
        b0, b1, b2 = 0.2316419, 0.319381530, -0.356563782
        b3, b4, b5 = 1.781477937, -1.821255978, 1.330274429
        t = 1.0 / (1.0 + b0 * x)
        phi = math.exp(-x * x / 2.0) / math.sqrt(2.0 * math.pi)
        return 1.0 - phi * (b1 * t + b2 * t ** 2 + b3 * t ** 3 + b4 * t ** 4 + b5 * t ** 5)

    @staticmethod
    def _empty_report(reason: str) -> ProfitabilityReport:
        return ProfitabilityReport(
            analysis_timestamp=datetime.now(timezone.utc).isoformat(),
        )


# ---------------------------------------------------------------------------
# Unit economics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UnitEconomicsVerdict:
    """Per-decision cost analysis for the Policy Critic.

    Attributes:
        cost_per_decision:       Total critic cost divided by total decisions.
        n_decisions:             Total decisions reviewed.
        total_critic_cost:       Total cost of running the critic (compute + infra).
        total_eng_cost_amortised: Amortised engineering cost.
        cost_per_decision_vs_budget: cost_per_decision / budget_per_decision.
        budget_per_decision:     Maximum acceptable cost per decision.
        is_within_budget:        True if cost_per_decision <= budget_per_decision.
        break_even_improvement:  Minimum R-net improvement needed to justify cost.
        analysis_timestamp:      ISO 8601 analysis time.
    """
    cost_per_decision: float = 0.0
    n_decisions: int = 0
    total_critic_cost: float = 0.0
    total_eng_cost_amortised: float = 0.0
    cost_per_decision_vs_budget: float = 1.0
    budget_per_decision: float = 0.01
    is_within_budget: bool = True
    break_even_improvement: float = 0.0
    analysis_timestamp: str = ""


class UnitEconomicsValidator:
    """Validate per-decision unit economics of the Policy Critic.

    Computes:
      - Cost per critic decision (compute + infrastructure)
      - Amortised engineering cost per decision
      - Budget compliance check
      - Break-even improvement required to justify cost
    """

    def __init__(
        self,
        *,
        budget_per_decision: float = 0.01,
        compute_cost_per_review: float = 0.001,
        monthly_infra_fixed: float = 100.0,
        total_eng_cost: float = 150_000.0,
        eng_amortisation_months: int = 24,
    ):
        """Initialise the unit economics validator.

        Args:
            budget_per_decision:    Maximum acceptable cost per critic decision
                                    in R-units (default 0.01 R per decision).
            compute_cost_per_review: Per-review compute cost in R-units.
            monthly_infra_fixed:    Fixed monthly infrastructure cost in R-units.
            total_eng_cost:         Total engineering cost (salary, etc.) in
                                    R-units for the critic project.
            eng_amortisation_months: Period over which eng cost is amortised.
        """
        self.budget_per_decision = budget_per_decision
        self.compute_cost_per_review = compute_cost_per_review
        self.monthly_infra_fixed = monthly_infra_fixed
        self.total_eng_cost = total_eng_cost
        self.eng_amortisation_months = eng_amortisation_months

    def validate(
        self,
        n_decisions: int,
        *,
        months_elapsed: int = 1,
    ) -> UnitEconomicsVerdict:
        """Run unit economics validation.

        Args:
            n_decisions:    Total number of critic reviews in the period.
            months_elapsed: Number of months over which costs are measured.

        Returns:
            UnitEconomicsVerdict with cost analysis and budget compliance.
        """
        if n_decisions <= 0:
            return UnitEconomicsVerdict(
                n_decisions=0,
                analysis_timestamp=datetime.now(timezone.utc).isoformat(),
            )

        variable_cost = n_decisions * self.compute_cost_per_review
        infra_cost = self.monthly_infra_fixed * max(1, months_elapsed)
        eng_amortised = (
            self.total_eng_cost / max(1, self.eng_amortisation_months) * months_elapsed
        )
        total_cost = variable_cost + infra_cost + eng_amortised
        cpd = total_cost / n_decisions

        is_within = cpd <= self.budget_per_decision
        vs_budget = cpd / self.budget_per_decision if self.budget_per_decision > 0 else 1.0

        # Break-even: minimum improvement per trade
        # If the critic costs X and reviews N decisions, each decision must
        # contribute at least X/N improvement on average.
        # For the underlying strategy, the break-even improvement is the
        # per-decision cost expressed in R-multiples.
        break_even = total_cost / n_decisions

        return UnitEconomicsVerdict(
            cost_per_decision=round(cpd, 8),
            n_decisions=n_decisions,
            total_critic_cost=round(total_cost, 4),
            total_eng_cost_amortised=round(eng_amortised, 4),
            cost_per_decision_vs_budget=round(vs_budget, 4),
            budget_per_decision=self.budget_per_decision,
            is_within_budget=is_within,
            break_even_improvement=round(break_even, 8),
            analysis_timestamp=datetime.now(timezone.utc).isoformat(),
        )


# ---------------------------------------------------------------------------
# Kill criteria
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KillCriterion:
    """A single kill criterion — condition under which critic should be disabled.

    Attributes:
        name:              Human-readable name.
        description:       What this criterion detects.
        metric:            Which metric it monitors.
        threshold:         Trigger threshold.
        current_value:     Current value of the metric.
        is_triggered:      True if the criterion is currently met.
        severity:          "CRITICAL", "WARNING", or "INFO".
        recommendation:    What to do if triggered.
    """
    name: str
    description: str
    metric: str
    threshold: float
    current_value: float
    is_triggered: bool
    severity: str = "WARNING"
    recommendation: str = ""


@dataclass(frozen=True)
class KillCriteriaResult:
    """Result of evaluating all kill criteria.

    Attributes:
        all_ok:             True if NO kill criterion is triggered.
        triggered_criteria: List of triggered KillCriterion instances.
        n_triggered:        Number of triggered criteria.
        n_warnings:         Number of WARNING-level triggers.
        n_critical:         Number of CRITICAL-level triggers.
        recommendation:     Overall recommendation (CONTINUE, MONITOR, DISABLE).
        analysis_timestamp: ISO 8601.
    """
    all_ok: bool = True
    triggered_criteria: list[KillCriterion] = field(default_factory=list)
    n_triggered: int = 0
    n_warnings: int = 0
    n_critical: int = 0
    recommendation: str = "CONTINUE"
    analysis_timestamp: str = ""


class KillCriteriaDocumenter:
    """Document and evaluate conditions under which the critic should be disabled.

    Pre-defined criteria (per ai_summary §Invalidation and profitability doc):
      1. DSR p >= 0.05 after ≥ 90 days -> improvement not significant
      2. PBO >= 0.20 -> high overfitting probability
      3. Per-regime degradation (any regime significantly worse)
      4. Drawdown worsening (max drawdown, duration, or frequency)
      5. False veto rate > 30%
      6. Infrastructure cost exceeds value
      7. Live shadow OPE diverges from offline estimates

    This documenter evaluates the criteria and produces a recommendation,
    but does NOT disable the critic automatically — that requires operator action.
    """

    # Default kill criteria definitions
    DEFAULT_CRITERIA: list[dict[str, Any]] = [
        {
            "name": "dsr_not_significant",
            "description": "Improvement not statistically significant (DSR p >= 0.05 after ≥ 90 days)",
            "metric": "dsr_p_value",
            "threshold": 0.05,
            "operator": "above",  # triggered when metric > threshold
            "severity": "CRITICAL",
            "recommendation": "Disable critic influence; return to shadow-only mode",
        },
        {
            "name": "pbo_exceeded",
            "description": "High overfitting probability (PBO >= 0.20)",
            "metric": "pbo",
            "threshold": 0.20,
            "operator": "above",
            "severity": "CRITICAL",
            "recommendation": "Disable critic influence; retrain with different data split",
        },
        {
            "name": "false_veto_rate_exceeded",
            "description": "False veto rate > 30% — too many good trades blocked",
            "metric": "false_veto_rate",
            "threshold": 0.30,
            "operator": "above",
            "severity": "CRITICAL",
            "recommendation": "Disable critic VETO influence; investigate calibration",
        },
        {
            "name": "drawdown_worsened",
            "description": "Max drawdown with critic > 1.5x baseline without critic",
            "metric": "drawdown_ratio",
            "threshold": 1.5,
            "operator": "above",
            "severity": "WARNING",
            "recommendation": "Reduce critic influence; investigate drawdown source",
        },
        {
            "name": "ope_divergence",
            "description": "Live shadow OPE diverges from offline FQE estimates by > 50%",
            "metric": "ope_vs_fqe_error",
            "threshold": 0.50,
            "operator": "above",
            "severity": "WARNING",
            "recommendation": "Re-evaluate OPE protocol; check for regime shift",
        },
        {
            "name": "veto_rate_out_of_bounds",
            "description": "Veto rate near 0 or 1 — critic is either irrelevant or blocking everything",
            "metric": "veto_rate",
            "threshold_low": 0.01,
            "threshold_high": 0.95,
            "operator": "out_of_bounds",
            "severity": "WARNING",
            "recommendation": "Veto rate bounds violated; investigate critic behaviour",
        },
        {
            "name": "cost_exceeds_value",
            "description": "Infrastructure cost exceeds measured improvement",
            "metric": "cost_vs_improvement",
            "threshold": 1.0,
            "operator": "above",
            "severity": "WARNING",
            "recommendation": "Consider disabling critic if cost consistently exceeds value",
        },
        {
            "name": "regime_degradation",
            "description": "Any single regime shows significant degradation vs baseline",
            "metric": "min_regime_delta",
            "threshold": -0.1,
            "operator": "below",
            "severity": "WARNING",
            "recommendation": "Degrade critic confidence in affected regime",
        },
    ]

    def __init__(self, custom_criteria: list[dict[str, Any]] | None = None):
        """Initialise the kill criteria documenter.

        Args:
            custom_criteria: Optional list of criterion definitions to override
                             or extend DEFAULT_CRITERIA. Each dict should have:
                               name, description, metric, threshold, operator,
                               severity, recommendation.
        """
        self._criteria = list(custom_criteria) if custom_criteria else []
        self._criteria.extend(self.DEFAULT_CRITERIA)

    @property
    def criteria_definitions(self) -> list[dict[str, Any]]:
        """Return all criteria definitions (read-only)."""
        return [dict(c) for c in self._criteria]

    def evaluate(self, metrics: dict[str, float]) -> KillCriteriaResult:
        """Evaluate all kill criteria against current metric values.

        Args:
            metrics: Dict of metric_name -> current_value. Names should match
                     the 'metric' field in criterion definitions.

        Returns:
            KillCriteriaResult with triggered criteria and recommendation.
        """
        triggered: list[KillCriterion] = []
        n_warnings = 0
        n_critical = 0

        for crit_def in self._criteria:
            name = crit_def["name"]
            metric = crit_def["metric"]
            current = metrics.get(metric)
            if current is None:
                continue

            is_triggered = self._check_criterion(crit_def, current)
            if is_triggered:
                kc = KillCriterion(
                    name=name,
                    description=crit_def.get("description", ""),
                    metric=metric,
                    threshold=crit_def.get("threshold", 0.0),
                    current_value=current,
                    is_triggered=True,
                    severity=crit_def.get("severity", "WARNING"),
                    recommendation=crit_def.get("recommendation", ""),
                )
                triggered.append(kc)
                if kc.severity == "CRITICAL":
                    n_critical += 1
                elif kc.severity == "WARNING":
                    n_warnings += 1

        # Determine overall recommendation
        if n_critical > 0:
            recommendation = "DISABLE"
            all_ok = False
        elif n_warnings > 0:
            recommendation = "MONITOR"
            all_ok = False
        else:
            recommendation = "CONTINUE"
            all_ok = True

        return KillCriteriaResult(
            all_ok=all_ok,
            triggered_criteria=triggered,
            n_triggered=len(triggered),
            n_warnings=n_warnings,
            n_critical=n_critical,
            recommendation=recommendation,
            analysis_timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _check_criterion(crit_def: dict[str, Any], current_value: float) -> bool:
        """Check whether a single criterion is triggered."""
        operator = crit_def.get("operator", "above")

        if operator == "above":
            threshold = crit_def.get("threshold", 0.0)
            return current_value > threshold
        elif operator == "below":
            threshold = crit_def.get("threshold", 0.0)
            return current_value < threshold
        elif operator == "out_of_bounds":
            low = crit_def.get("threshold_low", 0.0)
            high = crit_def.get("threshold_high", 1.0)
            return current_value <= low or current_value >= high
        return False
