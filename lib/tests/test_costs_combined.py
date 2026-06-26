"""
Tests for lib/costs/combined.py — combined_cost_r (fee + slippage + funding).
"""

import pytest
from lib.costs.r_costs import total_cost_r
from lib.costs.funding_impact import funding_cost_r
from lib.costs.combined import combined_cost_r


# =====================================================================
# combined_cost_r — component sum semantics
# =====================================================================

class TestCombinedCostR:
    def test_swing_long_with_funding(self):
        """SWING LONG: fee+slippage cost (0.02) + funding cost (0.075) = 0.095.
        total_cost_r: taker fee=0.02, slippage=0 (no liquidity) → 0.02
        funding_cost_r: +1*0.0001*10000*15*1.0 / 200 = 0.075
        """
        result = combined_cost_r(
            mode="SWING",
            notional=10000,
            entry_price=10000,
            atr=100,
            stop_multiplier=2.0,
            tier="taker",
            funding_rate=0.0001,
            position_direction="LONG",
            holding_bars=30,
            bar_duration_hours=4.0,
        )
        assert result == pytest.approx(0.095, rel=1e-9)

    def test_swing_short_rebate(self):
        """SWING SHORT: fee+slippage (0.02) + funding rebate (-0.075) = -0.055."""
        result = combined_cost_r(
            mode="SWING",
            notional=10000,
            entry_price=10000,
            atr=100,
            stop_multiplier=2.0,
            tier="taker",
            funding_rate=0.0001,
            position_direction="SHORT",
            holding_bars=30,
            bar_duration_hours=4.0,
        )
        assert result == pytest.approx(-0.055, rel=1e-9)

    def test_scalp_long_moderate(self):
        """SCALP LONG: 0.02 base + 0.00225 funding = 0.02225."""
        result = combined_cost_r(
            mode="SCALP",
            notional=10000,
            entry_price=10000,
            atr=100,
            stop_multiplier=2.0,
            tier="taker",
            funding_rate=0.0001,
            position_direction="LONG",
            holding_bars=12,
            bar_duration_hours=1.0,
        )
        assert result == pytest.approx(0.02225, rel=1e-9)

    def test_aggressive_scalp_funding_zero(self):
        """AGGRESSIVE_SCALP: funding=0 → same as total_cost_r alone."""
        result = combined_cost_r(
            mode="AGGRESSIVE_SCALP",
            notional=10000,
            entry_price=10000,
            atr=100,
            stop_multiplier=2.0,
            tier="taker",
            funding_rate=0.0001,
            position_direction="LONG",
            holding_bars=5,
            bar_duration_hours=0.25,
        )
        expected = total_cost_r(10000, 10000, 100, 2.0, tier="taker")
        assert result == pytest.approx(expected, rel=1e-9)

    def test_equals_total_cost_r_when_funding_zero(self):
        """No funding params → equal to total_cost_r."""
        result = combined_cost_r("SWING", 10000, 10000, 100, 2.0)
        expected = total_cost_r(10000, 10000, 100, 2.0)
        assert result == pytest.approx(expected, rel=1e-9)

    def test_sum_of_parts(self):
        """combined_cost_r = total_cost_r + funding_cost_r (validated via decomposition)."""
        mode = "SWING"
        notional = 10000
        entry_price = 10000
        atr = 100
        stop_mult = 2.0
        tier = "taker"
        avg_liquidity = 100000
        funding_rate_val = 0.0001

        base = total_cost_r(
            notional, entry_price, atr, stop_mult, tier, avg_liquidity,
        )
        funding = funding_cost_r(
            mode, notional, atr, stop_mult, funding_rate_val, "LONG", 30, 4.0,
        )
        combined = combined_cost_r(
            mode, notional, entry_price, atr, stop_mult,
            tier=tier, avg_liquidity=avg_liquidity,
            funding_rate=funding_rate_val,
            position_direction="LONG", holding_bars=30, bar_duration_hours=4.0,
        )
        assert combined == pytest.approx(base + funding, rel=1e-9)

    def test_atr_zero_returns_zero(self):
        assert combined_cost_r("SWING", 10000, 10000, 0, 2.0) == 0.0

    def test_stop_multiplier_zero_returns_zero(self):
        assert combined_cost_r("SWING", 10000, 10000, 100, 0) == 0.0

    def test_default_tier_is_taker(self):
        """Default tier='taker' produces taker fee in the combined cost."""
        taker = combined_cost_r("SWING", 10000, 10000, 100, 2.0)
        maker = combined_cost_r("SWING", 10000, 10000, 100, 2.0, tier="maker")
        assert maker < taker

    def test_larger_position_more_cost(self):
        """Larger notional → proportionally larger combined cost."""
        small = combined_cost_r("SWING", 1000, 10000, 100, 2.0)
        large = combined_cost_r("SWING", 10000, 10000, 100, 2.0)
        assert large > small
