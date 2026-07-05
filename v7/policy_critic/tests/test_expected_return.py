"""Tests for v7.policy_critic.expected_return — per-direction expected_R."""

import pytest

from v7.policy_critic.expected_return import (
    ExpectedReturn,
    compare_directions,
    compute_expected_r_from_simulation,
    compute_rule_based_expected_r,
)


class TestComputeRuleBasedExpectedR:
    """Test rule-based (v1 shadow) expected_R computation."""

    def test_positive_confidence_produces_positive_expected_r(self):
        er = compute_rule_based_expected_r(
            confidence=0.72,
            atr=1800.0,
            entry_price=64300.0,
            notional=10000.0,
        )
        assert er.expected_r_long > 0
        assert er.expected_r_short > 0
        assert er.expected_r_long == er.expected_r_short  # Symmetric in v1
        assert er.total_cost_r > 0

    def test_low_confidence_produces_negative_expected_r(self):
        er = compute_rule_based_expected_r(
            confidence=0.30,
            atr=1800.0,
            entry_price=64300.0,
            notional=10000.0,
        )
        assert er.expected_r_long < 0
        assert er.expected_r_short < 0

    def test_zero_atr_returns_zero(self):
        er = compute_rule_based_expected_r(
            confidence=0.80,
            atr=0.0,
            entry_price=64300.0,
            notional=10000.0,
        )
        assert er.expected_r_long == 0.0
        assert er.expected_r_short == 0.0
        assert er.total_cost_r == 0.0

    def test_expected_r_formula(self):
        """E[R] = P(win)*target - P(lose)*stop - costs."""
        er = compute_rule_based_expected_r(
            confidence=0.60,
            atr=1800.0,
            entry_price=64300.0,
            notional=10000.0,
            stop_multiplier=2.0,
            target_multiplier=2.5,
            funding_rate=0.0,
            holding_bars=0,
        )
        # P(win)=0.6, P(lose)=0.4
        # E[R]_gross = 0.6*2.5 - 0.4*2.0 = 1.5 - 0.8 = 0.70
        expected_gross = 0.70
        # Costs are deducted, so net is lower
        assert er.expected_r_long == pytest.approx(expected_gross - er.total_cost_r, rel=0.2)

    def test_direction_bias_long(self):
        """When LONG and SHORT have same expected R, bias should be 0."""
        er = compute_rule_based_expected_r(
            confidence=0.72,
            atr=1800.0,
            entry_price=64300.0,
            notional=10000.0,
        )
        # Symmetric in v1
        assert er.direction_bias == 0.0

    def test_with_funding_cost(self):
        er_no_fund = compute_rule_based_expected_r(
            confidence=0.72, atr=1800.0, entry_price=64300.0,
            notional=10000.0, funding_rate=0.0, holding_bars=0,
        )
        er_fund = compute_rule_based_expected_r(
            confidence=0.72, atr=1800.0, entry_price=64300.0,
            notional=10000.0, funding_rate=0.0001, holding_bars=20,
        )
        assert er_fund.total_cost_r > er_no_fund.total_cost_r
        assert er_fund.expected_r_long < er_no_fund.expected_r_long

    def test_no_trade_expected_r(self):
        er = compute_rule_based_expected_r(
            confidence=0.72,
            atr=1800.0,
            entry_price=64300.0,
            notional=10000.0,
            saved_loss_r=0.80,
            missed_opportunity_r=0.30,
        )
        # NO_TRADE E[R] = 0.80 - 0.5*0.30 = 0.65
        assert er.expected_r_no_trade == pytest.approx(0.65, rel=1e-5)

    def test_source_is_rule_based(self):
        er = compute_rule_based_expected_r(
            confidence=0.72, atr=1800.0, entry_price=64300.0, notional=10000.0,
        )
        assert er.source == "RULE_BASED"

    def test_immutable(self):
        er = compute_rule_based_expected_r(
            confidence=0.72, atr=1800.0, entry_price=64300.0, notional=10000.0,
        )
        with pytest.raises(Exception):
            er.expected_r_long = 1.0  # type: ignore


class TestComputeExpectedRFromSimulation:
    """Test expected_R computation from SimulationOutput."""

    def _sim_output(self, long_r=0.80, short_r=-0.20, long_tcr=0.15,
                    saved_loss=0.0, missed_opp=0.0):
        return {
            "long_outcome": {
                "realized_r_net": long_r,
                "total_cost_r": long_tcr,
            },
            "short_outcome": {
                "realized_r_net": short_r,
                "total_cost_r": 0.15,
            },
            "no_trade_outcome": {
                "saved_loss_r": saved_loss,
                "missed_opportunity_r": missed_opp,
            },
        }

    def test_extracts_realized_values(self):
        sim = self._sim_output()
        er = compute_expected_r_from_simulation(simulation_output=sim)
        assert er.expected_r_long == 0.80
        assert er.expected_r_short == -0.20
        assert er.total_cost_r == 0.15

    def test_source_is_simulation_mean(self):
        sim = self._sim_output()
        er = compute_expected_r_from_simulation(simulation_output=sim)
        assert er.source == "SIMULATION_MEAN"

    def test_direction_bias_long_dominant(self):
        sim = self._sim_output(long_r=1.20, short_r=-0.30)
        er = compute_expected_r_from_simulation(simulation_output=sim)
        assert er.direction_bias == 1.0

    def test_direction_bias_short_dominant(self):
        sim = self._sim_output(long_r=-0.50, short_r=0.80)
        er = compute_expected_r_from_simulation(simulation_output=sim)
        assert er.direction_bias == -1.0

    def test_direction_bias_neutral(self):
        sim = self._sim_output(long_r=0.50, short_r=0.50)
        er = compute_expected_r_from_simulation(simulation_output=sim)
        assert er.direction_bias == 0.0


class TestCompareDirections:
    """Test direction comparison logic."""

    def test_long_best_when_clear_edge(self):
        result = compare_directions(
            expected_long=0.85,
            expected_short=-0.10,
            expected_no_trade=0.0,
        )
        assert result["best_direction"] == "LONG"
        assert result["best_expected_r"] == 0.85
        assert result["edge_over_no_trade"] == 0.85
        assert result["is_ambiguous"] is False

    def test_short_best_when_clear_edge(self):
        result = compare_directions(
            expected_long=-0.20,
            expected_short=0.65,
            expected_no_trade=0.0,
        )
        assert result["best_direction"] == "SHORT"
        assert result["best_expected_r"] == 0.65

    def test_no_trade_wins_when_both_lose(self):
        result = compare_directions(
            expected_long=-0.50,
            expected_short=-0.30,
            expected_no_trade=0.0,
        )
        assert result["best_direction"] == "NO_TRADE"
        assert result["best_expected_r"] == 0.0

    def test_ambiguous_when_edge_below_minimum(self):
        result = compare_directions(
            expected_long=0.20,
            expected_short=-0.10,
            expected_no_trade=0.0,
            min_action_edge_r=0.35,
        )
        assert result["best_direction"] == "LONG"  # Still best, but ambiguous
        assert result["is_ambiguous"] is True
        assert result["edge_over_no_trade"] < 0.35

    def test_ambiguous_when_gap_small(self):
        result = compare_directions(
            expected_long=0.52,
            expected_short=0.50,
            expected_no_trade=0.0,
            min_action_edge_r=0.35,
        )
        # gap = 0.02; min_action_edge_r * 0.5 = 0.175 → gap < 0.175?
        # Actually gap 0.02 < 0.175 → ambiguous
        assert result["is_ambiguous"] is True

    def test_no_trade_negative_best_r_is_ambiguous(self):
        result = compare_directions(
            expected_long=-0.50,
            expected_short=-0.30,
            expected_no_trade=-0.05,
        )
        # NO_TRADE wins but its expected R is negative → ambiguous
        assert result["best_direction"] == "NO_TRADE"
        # best_r is negative AND direction is NO_TRADE → is_ambiguous True
        assert result["is_ambiguous"] is True
