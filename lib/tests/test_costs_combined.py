"""
Tests for lib/costs/combined.py — combined total_cost_r (fee + slippage + funding).
"""

import pytest
from lib.costs.combined import total_cost_r
from lib.costs.r_costs import fee_cost_r, slippage_cost_r
from lib.costs.funding_impact import funding_cost_r


class TestCombinedTotalCostR:
    def test_sum_of_parts_swing_long(self):
        """Combined total_cost_r = fee + slippage + funding for SWING LONG."""
        args = dict(
            notional=10_000, entry_price=50_000,
            atr=1000, stop_multiplier=2.0,
            tier="taker", avg_liquidity=100_000,
            mode="SWING", funding_rate=0.0001, direction="LONG",
        )
        combined = total_cost_r(**args)

        fee = fee_cost_r(10_000, 50_000, 1000, 2.0, tier="taker")
        slip = slippage_cost_r(10_000, 50_000, 1000, 2.0, avg_liquidity=100_000)
        fund = funding_cost_r(
            10_000, 50_000, 1000, 2.0,
            mode="SWING", funding_rate=0.0001, direction="LONG",
        )
        assert combined == pytest.approx(fee + slip + fund, rel=1e-9)

    def test_sum_of_parts_scalp(self):
        """Combined works for SCALP with smaller funding contribution."""
        combined = total_cost_r(
            5_000, 20_000, 500, 1.5,
            tier="maker", avg_liquidity=50_000,
            mode="SCALP", funding_rate=0.0001, direction="LONG",
        )
        fee = fee_cost_r(5_000, 20_000, 500, 1.5, tier="maker")
        slip = slippage_cost_r(5_000, 20_000, 500, 1.5, avg_liquidity=50_000)
        fund = funding_cost_r(
            5_000, 20_000, 500, 1.5,
            mode="SCALP", funding_rate=0.0001, direction="LONG",
        )
        assert combined == pytest.approx(fee + slip + fund, rel=1e-9)

    def test_swing_cost_higher_than_scalp(self):
        """SWING has higher total cost than SCALP due to more funding intervals."""
        swing = total_cost_r(
            10_000, 50_000, 1000, 2.0,
            mode="SWING", funding_rate=0.0001,
        )
        scalp = total_cost_r(
            10_000, 50_000, 1000, 2.0,
            mode="SCALP", funding_rate=0.0001,
        )
        assert swing > scalp

    def test_aggressive_scalp_no_funding_component(self):
        """AGGRESSIVE_SCALP combined cost equals fee + slippage (no funding)."""
        combined = total_cost_r(
            10_000, 50_000, 1000, 2.0,
            mode="AGGRESSIVE_SCALP", funding_rate=0.0001,
        )
        fee_slip = fee_cost_r(10_000, 50_000, 1000, 2.0) + \
            slippage_cost_r(10_000, 50_000, 1000, 2.0)
        assert combined == pytest.approx(fee_slip, rel=1e-9)

    def test_short_reduces_total_cost(self):
        """SHORT direction with positive funding reduces total cost vs LONG."""
        long_cost = total_cost_r(
            10_000, 50_000, 1000, 2.0,
            mode="SWING", funding_rate=0.0001, direction="LONG",
        )
        short_cost = total_cost_r(
            10_000, 50_000, 1000, 2.0,
            mode="SWING", funding_rate=0.0001, direction="SHORT",
        )
        assert short_cost < long_cost
        # SHORT receives funding credit, so total cost is lower

    def test_custom_holding_hours(self):
        """Explicit holding_hours produces a different combined cost."""
        default = total_cost_r(
            10_000, 50_000, 1000, 2.0,
            mode="SCALP", funding_rate=0.0001,
        )
        custom = total_cost_r(
            10_000, 50_000, 1000, 2.0,
            mode="SCALP", funding_rate=0.0001, holding_hours=1.0,
        )
        # 1h holding → 1/8 = 0.125 intervals vs SCALP default 2.0
        assert custom < default

    def test_no_funding_params_default(self):
        """Combined with default args (no funding params) works and matches fee+slippage."""
        combined = total_cost_r(10_000, 50_000, 1000, 2.0)
        fee_slip = fee_cost_r(10_000, 50_000, 1000, 2.0) + \
            slippage_cost_r(10_000, 50_000, 1000, 2.0)
        # Default mode is SWING, direction is LONG, so funding adds a small amount
        fund = funding_cost_r(10_000, 50_000, 1000, 2.0, mode="SWING")
        assert combined == pytest.approx(fee_slip + fund, rel=1e-9)

    def test_atr_zero_returns_zero(self):
        """atr <= 0 returns 0.0."""
        assert total_cost_r(10_000, 50_000, 0, 2.0) == 0.0
        assert total_cost_r(10_000, 50_000, -10, 2.0) == 0.0

    def test_stop_multiplier_zero_returns_zero(self):
        """stop_multiplier <= 0 returns 0.0."""
        assert total_cost_r(10_000, 50_000, 1000, 0) == 0.0
        assert total_cost_r(10_000, 50_000, 1000, -2.0) == 0.0

    def test_zero_notional(self):
        """Zero notional produces zero total cost."""
        cost = total_cost_r(0, 50_000, 1000, 2.0)
        assert cost == 0.0

    def test_maker_tier_lower_cost(self):
        """Maker tier produces lower total cost than taker."""
        maker_cost = total_cost_r(
            10_000, 50_000, 1000, 2.0,
            tier="maker",
        )
        taker_cost = total_cost_r(
            10_000, 50_000, 1000, 2.0,
            tier="taker",
        )
        assert maker_cost < taker_cost
