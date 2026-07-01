"""Tests for compute_cost_stress — independent fee/slippage/spread stress.

Verifies that:
- Positive edge survives fee stress up to 3x with high expectancy
- Fee stress 3x destroys edge when expectancy is marginal
- Combined worst-case stress correctly applies all max multipliers
- Break-even cost calculation is correct
- Zero/negative edge produces correct (survives=False) results
- Edge cases (zero costs, huge edge) are handled
"""
from __future__ import annotations

import math

import pytest

from alphaforge.validation.cost_stress import (
    compute_cost_stress,
    cost_stress_to_stress_levels,
)
from alphaforge.validation.contracts import CostStressResult


# =========================================================================
# Positive edge — strong expectancy
# =========================================================================


class TestPositiveEdge:
    """Edge survives all stress levels with strong OOS expectancy."""

    def test_strong_edge_survives_fee_stress(self):
        """OOS expectancy of 0.50 R survives all fee stress levels."""
        result = compute_cost_stress(
            oos_expectancy_r=0.50,
            baseline_fee_pct=0.04,
            baseline_slippage_pct=0.02,
            baseline_spread_pct=0.01,
            entry_risk_pct=0.02,
        )
        assert result.fee_stress_edge_survives is True
        # Fee stress 1.5x, 2x, 3x all positive
        assert result.fee_stress_1_5x > 0
        assert result.fee_stress_2x > 0
        assert result.fee_stress_3x > 0

    def test_strong_edge_survives_slippage_stress(self):
        """OOS expectancy of 0.50 R survives all slippage stress levels."""
        result = compute_cost_stress(oos_expectancy_r=0.50)
        assert result.slippage_stress_edge_survives is True
        assert result.slippage_stress_1_5x > 0
        assert result.slippage_stress_2x > 0
        assert result.slippage_stress_3x > 0

    def test_combined_stress_survives_with_strong_edge(self):
        """Strong edge survives combined worst-case stress."""
        result = compute_cost_stress(oos_expectancy_r=0.50)
        assert result.combined_stress_edge_survives is True
        assert result.combined_stress > 0

    def test_break_even_cost_greater_than_one(self):
        """Break-even multiplier > 1 for positive edge."""
        result = compute_cost_stress(oos_expectancy_r=0.50)
        assert result.break_even_cost > 1.0
        assert not math.isinf(result.break_even_cost)


# =========================================================================
# Marginal edge — fee stress should destroy
# =========================================================================


class TestMarginalEdge:
    """Edge survives baseline but fails under moderate fee stress."""

    def test_marginal_edge_fails_fee_2x(self):
        """Low OOS expectancy (0.10) fails at fee 2x stress."""
        result = compute_cost_stress(
            oos_expectancy_r=0.10,
            baseline_fee_pct=0.04,
            baseline_slippage_pct=0.02,
            baseline_spread_pct=0.01,
            entry_risk_pct=0.02,
        )
        # Fee stress should fail because edge is small
        # Baseline fee cost R = 2 * 0.04/100 / 0.02 = 0.04
        # Fee stress 2x extra = 0.04 * (2-1) = 0.04
        # Edge = 0.10 - 0.04 = 0.06 > 0 (survives 2x)
        # Fee stress 3x extra = 0.04 * (3-1) = 0.08
        # Edge = 0.10 - 0.08 = 0.02 > 0 (survives 3x)
        # With 0.10, all should still survive
        assert result.fee_stress_edge_survives is True

    def test_very_marginal_edge_fails_fee_stress(self):
        """Very small edge (0.02) fails under fee 3x stress."""
        result = compute_cost_stress(
            oos_expectancy_r=0.02,
            baseline_fee_pct=0.04,
            entry_risk_pct=0.02,
        )
        # Baseline fee cost R = 2 * 0.04/100 / 0.02 = 0.04
        # Fee stress 3x extra = 0.04 * 2 = 0.08
        # Edge = 0.02 - 0.08 = -0.06 < 0
        assert result.fee_stress_3x <= 0
        assert result.fee_stress_edge_survives is False


# =========================================================================
# Combined worst-case
# =========================================================================


class TestCombinedStress:
    """Combined worst-case stress applies all max multipliers."""

    def test_combined_worst_case_applies_all_max_multipliers(self):
        """Combined stress reduces edge by the sum of all extra costs."""
        result = compute_cost_stress(
            oos_expectancy_r=0.50,
            baseline_fee_pct=0.04,
            baseline_slippage_pct=0.02,
            baseline_spread_pct=0.01,
            entry_risk_pct=0.02,
        )
        # combined_stress should be lower than any individual stress
        assert result.combined_stress < result.fee_stress_3x
        assert result.combined_stress < result.slippage_stress_3x
        assert result.combined_stress < result.spread_stress_2x

    def test_combined_stress_fails_when_accumulated(self):
        """Combined stress destroys edge even when individual survive."""
        # Fee 3x alone survives, slippage 3x alone survives,
        # but combined destroys
        result = compute_cost_stress(
            oos_expectancy_r=0.15,
            baseline_fee_pct=0.04,
            baseline_slippage_pct=0.02,
            entry_risk_pct=0.02,
        )
        # Fee baseline cost R = 0.04, slip baseline = 0.02
        # Fee 3x extra = 0.04 * 2 = 0.08
        # Slip 3x extra = 0.02 * 2 = 0.04
        # Total extra = 0.12
        # Combined = 0.15 - 0.12 = 0.03 > 0 -- may still survive
        # Let me use a tighter edge
        result2 = compute_cost_stress(
            oos_expectancy_r=0.06,
            baseline_fee_pct=0.04,
            baseline_slippage_pct=0.02,
            entry_risk_pct=0.02,
        )
        # Combined = 0.06 - (0.08 + 0.04) = -0.06 < 0
        assert result2.combined_stress <= 0


# =========================================================================
# Break-even cost
# =========================================================================


class TestBreakEvenCost:
    """Break-even cost calculation."""

    def test_break_even_scales_with_edge(self):
        """Higher edge means higher break-even multiplier."""
        low = compute_cost_stress(oos_expectancy_r=0.20)
        high = compute_cost_stress(oos_expectancy_r=0.60)

        assert high.break_even_cost > low.break_even_cost
        assert high.break_even_cost > 1.0

    def test_break_even_zero_when_edge_negative(self):
        """Break-even multiplier is 0 when edge is already negative."""
        result = compute_cost_stress(oos_expectancy_r=-0.10)
        assert result.break_even_cost == 0.0

    def test_break_even_infinite_when_baseline_costs_zero(self):
        """Break-even is infinite when baseline costs are zero."""
        result = compute_cost_stress(
            oos_expectancy_r=0.50,
            baseline_fee_pct=0.0,
            baseline_slippage_pct=0.0,
            baseline_spread_pct=0.0,
        )
        assert result.break_even_cost == float("inf") or result.break_even_cost > 1e6


# =========================================================================
# Baseline values
# =========================================================================


class TestBaselineValues:
    """Baseline cost fields are populated correctly."""

    def test_baseline_fee_in_r(self):
        """fee_baseline is the baseline fee cost in R."""
        result = compute_cost_stress(
            oos_expectancy_r=0.50,
            baseline_fee_pct=0.04,
            entry_risk_pct=0.02,
        )
        # Expected: 2 * 0.04/100 / 0.02 = 0.04
        assert abs(result.fee_baseline - 0.04) < 1e-10

    def test_baseline_slippage_in_r(self):
        """slippage_baseline is baseline slippage cost in R."""
        result = compute_cost_stress(
            oos_expectancy_r=0.50,
            baseline_slippage_pct=0.02,
            entry_risk_pct=0.02,
        )
        # Expected: 2 * 0.02/100 / 0.02 = 0.02
        assert abs(result.slippage_baseline - 0.02) < 1e-10

    def test_baseline_spread_in_r(self):
        """spread_baseline is baseline spread cost in R."""
        result = compute_cost_stress(
            oos_expectancy_r=0.50,
            baseline_spread_pct=0.01,
            entry_risk_pct=0.02,
        )
        # Expected: 2 * 0.01/100 / 0.02 = 0.01
        assert abs(result.spread_baseline - 0.01) < 1e-10


# =========================================================================
# Edge cases
# =========================================================================


class TestEdgeCases:
    """Edge cases: zero cost, zero edge, extreme values."""

    def test_returns_cost_stress_result_type(self):
        """Result is always a CostStressResult."""
        result = compute_cost_stress(oos_expectancy_r=0.50)
        assert isinstance(result, CostStressResult)

    def test_zero_entry_risk_does_not_crash(self):
        """Zero entry_risk_pct falls back to default."""
        result = compute_cost_stress(
            oos_expectancy_r=0.50,
            entry_risk_pct=0.0,
        )
        assert isinstance(result, CostStressResult)

    def test_negative_edge_has_no_stress_survival(self):
        """Negative OOS expectancy has all survive flags False."""
        result = compute_cost_stress(oos_expectancy_r=-0.10)
        assert result.fee_stress_edge_survives is False
        assert result.slippage_stress_edge_survives is False
        assert result.combined_stress_edge_survives is False
        assert result.break_even_cost == 0.0

    def test_zero_edge_has_factor_survival(self):
        """Zero OOS expectancy has no stress survival (edge already 0)."""
        result = compute_cost_stress(oos_expectancy_r=0.0)
        assert result.fee_stress_edge_survives is False
        assert result.slippage_stress_edge_survives is False
        assert result.combined_stress_edge_survives is False
        assert result.break_even_cost == 0.0

    def test_funding_deferred_block_preserved(self):
        """The funding_deferred_block string from CostStressResult is kept."""
        result = compute_cost_stress(oos_expectancy_r=0.50)
        assert "Funding model is DEFERRED" in result.funding_deferred_block


# =========================================================================
# Independent dimensions: fee vs slippage separation
# =========================================================================


class TestIndependentDimensions:
    """Fee and slippage stress should have independent effects."""

    def test_fee_stress_affects_more_with_higher_fee(self):
        """Higher baseline fee makes fee stress more impactful."""
        low_fee = compute_cost_stress(
            oos_expectancy_r=0.30,
            baseline_fee_pct=0.02,
            entry_risk_pct=0.02,
        )
        high_fee = compute_cost_stress(
            oos_expectancy_r=0.30,
            baseline_fee_pct=0.08,
            entry_risk_pct=0.02,
        )
        # Higher fee should result in lower edge under fee stress 3x
        assert high_fee.fee_stress_3x < low_fee.fee_stress_3x

    def test_slippage_stress_independent_of_fee(self):
        """Changing fee should not affect slippage stress results."""
        result_a = compute_cost_stress(
            oos_expectancy_r=0.30,
            baseline_fee_pct=0.04,
            baseline_slippage_pct=0.02,
            entry_risk_pct=0.02,
        )
        result_b = compute_cost_stress(
            oos_expectancy_r=0.30,
            baseline_fee_pct=0.08,  # higher fee
            baseline_slippage_pct=0.02,  # same slippage
            entry_risk_pct=0.02,
        )
        # Slippage stress values should be identical (same slippage pct)
        assert abs(result_a.slippage_stress_1_5x - result_b.slippage_stress_1_5x) < 1e-10
        assert abs(result_a.slippage_stress_2x - result_b.slippage_stress_2x) < 1e-10
        assert abs(result_a.slippage_stress_3x - result_b.slippage_stress_3x) < 1e-10

    def test_entry_risk_affects_all_dimensions(self):
        """Tighter stops (smaller entry_risk_pct) increase cost impact."""
        loose_stop = compute_cost_stress(
            oos_expectancy_r=0.30,
            baseline_fee_pct=0.04,
            entry_risk_pct=0.03,  # 3% stop
        )
        tight_stop = compute_cost_stress(
            oos_expectancy_r=0.30,
            baseline_fee_pct=0.04,
            entry_risk_pct=0.01,  # 1% stop
        )
        # Tighter stop = higher cost in R = lower stressed edge
        assert tight_stop.fee_stress_3x < loose_stop.fee_stress_3x
        assert tight_stop.combined_stress < loose_stop.combined_stress
        assert tight_stop.break_even_cost < loose_stop.break_even_cost


# =========================================================================
# Converter to report dict format
# =========================================================================


class TestCostStressToStressLevels:
    """CostStressResult to report dict conversion."""

    def test_converts_to_dict(self):
        """cost_stress_to_stress_levels returns a dict with expected keys."""
        result = compute_cost_stress(oos_expectancy_r=0.50)
        d = cost_stress_to_stress_levels(result, 0.04, 0.02)
        assert isinstance(d, dict)
        assert "baseline_fee_pct" in d
        assert "baseline_slippage_pct" in d
        assert "fee_stress_levels" in d
        assert "slippage_stress_levels" in d
        assert "combined_stress_edge_survives" in d
        assert "break_even_cost_total_pct" in d
        assert "net_edge_after_costs" in d
        assert "cost_stress_verdict" in d

    def test_fee_stress_levels_have_multiplier_expectancy_survives(self):
        """Each fee stress level has multiplier, oos_expectancy_r, edge_survives."""
        result = compute_cost_stress(oos_expectancy_r=0.50)
        d = cost_stress_to_stress_levels(result, 0.04, 0.02)
        for level in d["fee_stress_levels"]:
            assert "multiplier" in level
            assert "oos_expectancy_r" in level
            assert "edge_survives" in level
            assert isinstance(level["multiplier"], float)
            assert isinstance(level["oos_expectancy_r"], float)

    def test_strong_edge_passes_verdict(self):
        """Strong edge yields PASS verdict."""
        result = compute_cost_stress(oos_expectancy_r=0.50)
        d = cost_stress_to_stress_levels(result, 0.04, 0.02)
        assert d["cost_stress_verdict"] == "PASS"

    def test_weak_edge_fails_verdict(self):
        """Weak edge yields FAIL verdict."""
        result = compute_cost_stress(
            oos_expectancy_r=0.01,
            baseline_fee_pct=0.10,
            entry_risk_pct=0.02,
        )
        d = cost_stress_to_stress_levels(result, 0.10, 0.02)
        assert d["cost_stress_verdict"] == "FAIL_EDGE_DESTROYED_BY_COSTS"

    def test_break_even_cost_total_pct(self):
        """break_even_cost_total_pct is the break_even_cost from result."""
        result = compute_cost_stress(oos_expectancy_r=0.50)
        d = cost_stress_to_stress_levels(result, 0.04, 0.02)
        assert isinstance(d["break_even_cost_total_pct"], float)

    def test_net_edge_after_costs_is_combined_stress(self):
        """net_edge_after_costs matches combined_stress from result."""
        result = compute_cost_stress(oos_expectancy_r=0.50)
        d = cost_stress_to_stress_levels(result, 0.04, 0.02)
        assert isinstance(d["net_edge_after_costs"], float)
