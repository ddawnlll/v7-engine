"""
Tests for lib/costs/funding_impact.py — funding_cost_r and funding_sensitivity.
"""

import pytest
from lib.costs.funding_impact import funding_cost_r, funding_sensitivity


# =====================================================================
# funding_cost_r — mode-specific behavior
# =====================================================================

class TestFundingCostRByMode:
    def test_swing_long_known_example(self):
        """SWING LONG: 30 bars * 4h = 120h, 15 intervals crossed.
        funding_rate=0.0001, sensitivity=1.0, notional=10000, atr=100, stop_mult=2.0.
        Expected: +1 * 0.0001 * 10000 * 15 * 1.0 / 200 = 0.075"""
        result = funding_cost_r(
            mode="SWING",
            notional=10000,
            atr=100,
            stop_multiplier=2.0,
            funding_rate=0.0001,
            position_direction="LONG",
            holding_bars=30,
            bar_duration_hours=4.0,
        )
        assert result == pytest.approx(0.075, rel=1e-9)

    def test_swing_short_rebate(self):
        """SWING SHORT: same as above but direction=-1 → negative cost (rebate).
        Expected: -0.075"""
        result = funding_cost_r(
            mode="SWING",
            notional=10000,
            atr=100,
            stop_multiplier=2.0,
            funding_rate=0.0001,
            position_direction="SHORT",
            holding_bars=30,
            bar_duration_hours=4.0,
        )
        assert result == pytest.approx(-0.075, rel=1e-9)

    def test_scalp_long_moderate_impact(self):
        """SCALP LONG: 12 bars * 1h = 12h, 1.5 intervals, sensitivity=0.3.
        Expected: +1 * 0.0001 * 10000 * 1.5 * 0.3 / 200 = 0.00225"""
        result = funding_cost_r(
            mode="SCALP",
            notional=10000,
            atr=100,
            stop_multiplier=2.0,
            funding_rate=0.0001,
            position_direction="LONG",
            holding_bars=12,
            bar_duration_hours=1.0,
        )
        assert result == pytest.approx(0.00225, rel=1e-9)

    def test_scalp_short_moderate_impact(self):
        """SCALP SHORT: rebate scaled by 0.3.
        Expected: -0.00225"""
        result = funding_cost_r(
            mode="SCALP",
            notional=10000,
            atr=100,
            stop_multiplier=2.0,
            funding_rate=0.0001,
            position_direction="SHORT",
            holding_bars=12,
            bar_duration_hours=1.0,
        )
        assert result == pytest.approx(-0.00225, rel=1e-9)

    def test_aggressive_scalp_always_zero(self):
        """AGGRESSIVE_SCALP has sensitivity 0 → always returns 0.0."""
        result = funding_cost_r(
            mode="AGGRESSIVE_SCALP",
            notional=10000,
            atr=100,
            stop_multiplier=2.0,
            funding_rate=0.0001,
            position_direction="LONG",
            holding_bars=5,
            bar_duration_hours=0.25,
        )
        assert result == 0.0

    def test_aggressive_scalp_short_still_zero(self):
        """AGGRESSIVE_SCALP SHORT → still 0.0."""
        result = funding_cost_r(
            mode="AGGRESSIVE_SCALP",
            notional=10000,
            atr=100,
            stop_multiplier=2.0,
            funding_rate=0.0001,
            position_direction="SHORT",
            holding_bars=5,
            bar_duration_hours=0.25,
        )
        assert result == 0.0


# =====================================================================
# funding_cost_r — edge cases
# =====================================================================

class TestFundingCostREdgeCases:
    def test_atr_zero_returns_zero(self):
        assert funding_cost_r("SWING", 10000, 0, 2.0, 0.0001, "LONG", 30, 4.0) == 0.0

    def test_stop_multiplier_zero_returns_zero(self):
        assert funding_cost_r("SWING", 10000, 100, 0, 0.0001, "LONG", 30, 4.0) == 0.0

    def test_negative_atr_returns_zero(self):
        assert funding_cost_r("SWING", 10000, -10, 2.0, 0.0001, "LONG", 30, 4.0) == 0.0

    def test_zero_funding_rate_returns_zero(self):
        result = funding_cost_r("SWING", 10000, 100, 2.0, 0.0, "LONG", 30, 4.0)
        assert result == 0.0

    def test_zero_holding_bars_returns_zero(self):
        """Zero holding bars → zero intervals → zero cost."""
        result = funding_cost_r("SWING", 10000, 100, 2.0, 0.0001, "LONG", 0, 4.0)
        assert result == 0.0

    def test_zero_notional_returns_zero(self):
        result = funding_cost_r("SWING", 0, 100, 2.0, 0.0001, "LONG", 30, 4.0)
        assert result == 0.0

    def test_custom_funding_interval(self):
        """Explicit funding_interval_hours=4: intervals = 30*4/4 = 30."""
        result = funding_cost_r(
            mode="SWING",
            notional=10000,
            atr=100,
            stop_multiplier=2.0,
            funding_rate=0.0001,
            position_direction="LONG",
            holding_bars=30,
            bar_duration_hours=4.0,
            funding_interval_hours=4.0,
        )
        # +1 * 0.0001 * 10000 * 30 * 1.0 / 200 = 0.15
        assert result == pytest.approx(0.15, rel=1e-9)

    def test_negative_funding_rate_long_receives(self):
        """Negative funding rate + LONG = negative cost (receives)."""
        result = funding_cost_r(
            "SWING", 10000, 100, 2.0, -0.0002, "LONG", 30, 4.0,
        )
        # +1 * -0.0002 * 10000 * 15 / 200 = -0.15
        assert result == pytest.approx(-0.15, rel=1e-9)

    def test_negative_funding_rate_short_pays(self):
        """Negative funding rate + SHORT = positive cost (pays)."""
        result = funding_cost_r(
            "SWING", 10000, 100, 2.0, -0.0002, "SHORT", 30, 4.0,
        )
        # -1 * -0.0002 * 10000 * 15 / 200 = 0.15
        assert result == pytest.approx(0.15, rel=1e-9)


# =====================================================================
# funding_sensitivity
# =====================================================================

class TestFundingSensitivity:
    def test_swing_full(self):
        assert funding_sensitivity("SWING") == 1.0

    def test_scalp_moderate(self):
        assert funding_sensitivity("SCALP") == 0.3

    def test_aggressive_scalp_zero(self):
        assert funding_sensitivity("AGGRESSIVE_SCALP") == 0.0

    def test_unknown_mode_defaults_zero(self):
        assert funding_sensitivity("UNKNOWN") == 0.0
