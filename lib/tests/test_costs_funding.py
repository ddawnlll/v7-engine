"""
Tests for lib/costs/funding_impact.py — funding_cost_r and max_funding_intervals.
"""

import pytest
from lib.costs.funding_impact import (
    funding_cost_r,
    max_funding_intervals,
    FUNDING_INTERVAL_HOURS,
    _MODE_MAX_FUNDING_INTERVALS,
)


class TestMaxFundingIntervals:
    def test_swing_default(self):
        """SWING returns the expected default (15 intervals)."""
        assert max_funding_intervals("SWING") == 15.0

    def test_scalp_default(self):
        """SCALP returns the expected default (2 intervals)."""
        assert max_funding_intervals("SCALP") == 2.0

    def test_aggressive_scalp_default(self):
        """AGGRESSIVE_SCALP returns 0 (negligible by spec)."""
        assert max_funding_intervals("AGGRESSIVE_SCALP") == 0.0

    def test_with_explicit_holding(self):
        """Explicit holding_hours produces a pro-rata interval count."""
        # 24h holding / 8h interval = 3.0
        assert max_funding_intervals("SWING", holding_hours=24.0) == 3.0

    def test_partial_interval(self):
        """Partial overlap returns fractional intervals."""
        # 2h holding / 8h interval = 0.25
        intervals = max_funding_intervals("SCALP", holding_hours=2.0)
        assert intervals == pytest.approx(0.25, rel=1e-9)

    def test_zero_holding_returns_zero(self):
        """Zero or negative holding_hours returns 0.0."""
        assert max_funding_intervals("SWING", holding_hours=0.0) == 0.0
        assert max_funding_intervals("SWING", holding_hours=-5.0) == 0.0

    def test_custom_funding_interval(self):
        """Non-standard funding interval is respected."""
        # 12h holding / 4h interval = 3.0
        assert max_funding_intervals("SWING", holding_hours=12.0, funding_interval_hours=4.0) == 3.0

    def test_negative_funding_interval_returns_zero(self):
        """Non-positive funding_interval_hours returns 0.0."""
        assert max_funding_intervals("SWING", funding_interval_hours=0.0) == 0.0
        assert max_funding_intervals("SWING", funding_interval_hours=-8.0) == 0.0


class TestFundingCostR:
    def test_swing_long_pays_funding(self):
        """SWING LONG with positive funding rate produces positive cost."""
        cost = funding_cost_r(
            notional=10_000,
            entry_price=50_000,
            atr=1000,
            stop_multiplier=2.0,
            mode="SWING",
            funding_rate=0.0001,
            direction="LONG",
        )
        # 15 intervals * 0.0001 * 10000 / (1000 * 2.0) = 15 * 1.0 / 2000 = 0.0075
        assert cost == pytest.approx(0.0075, rel=1e-9)
        assert cost > 0  # LONG pays funding → positive cost

    def test_swing_short_receives_funding(self):
        """SHORT with positive funding rate receives credit (negative cost)."""
        cost = funding_cost_r(
            notional=10_000,
            entry_price=50_000,
            atr=1000,
            stop_multiplier=2.0,
            mode="SWING",
            funding_rate=0.0001,
            direction="SHORT",
        )
        # -15 intervals * 0.0001 * 10000 / (1000 * 2.0) = -15 * 1.0 / 2000 = -0.0075
        assert cost == pytest.approx(-0.0075, rel=1e-9)
        assert cost < 0  # SHORT receives funding → negative cost (credit)

    def test_scalp_funding_smaller_than_swing(self):
        """SCALP's smaller interval count yields smaller absolute funding impact."""
        swing = funding_cost_r(10_000, 50_000, 1000, 2.0, mode="SWING")
        scalp = funding_cost_r(10_000, 50_000, 1000, 2.0, mode="SCALP")
        assert abs(scalp) < abs(swing)

    def test_aggressive_scalp_zero_by_default(self):
        """AGGRESSIVE_SCALP returns 0.0 when no explicit holding_hours."""
        cost = funding_cost_r(
            notional=10_000, entry_price=50_000,
            atr=1000, stop_multiplier=2.0,
            mode="AGGRESSIVE_SCALP",
        )
        assert cost == 0.0

    def test_aggressive_scalp_nonzero_with_explicit_holding(self):
        """AGGRESSIVE_SCALP can have non-zero funding if holding_hours is provided."""
        cost = funding_cost_r(
            notional=10_000, entry_price=50_000,
            atr=1000, stop_multiplier=2.0,
            mode="AGGRESSIVE_SCALP",
            holding_hours=12.0,
            funding_rate=0.0001,
        )
        # 12/8 = 1.5 intervals * 0.0001 * 10000 / 2000 = 1.5 * 1.0 / 2000 = 0.00075
        assert cost == pytest.approx(0.00075, rel=1e-9)

    def test_direction_sign_opposite(self):
        """LONG and SHORT with same inputs produce opposite signs."""
        long_cost = funding_cost_r(
            10_000, 50_000, 1000, 2.0,
            mode="SWING", funding_rate=0.0001, direction="LONG",
        )
        short_cost = funding_cost_r(
            10_000, 50_000, 1000, 2.0,
            mode="SWING", funding_rate=0.0001, direction="SHORT",
        )
        assert long_cost == pytest.approx(-short_cost, rel=1e-9)

    def test_atr_zero_returns_zero(self):
        """atr <= 0 returns 0.0."""
        assert funding_cost_r(10_000, 50_000, 0, 2.0, mode="SWING") == 0.0
        assert funding_cost_r(10_000, 50_000, -10, 2.0, mode="SWING") == 0.0

    def test_stop_multiplier_zero_returns_zero(self):
        """stop_multiplier <= 0 returns 0.0."""
        assert funding_cost_r(10_000, 50_000, 1000, 0, mode="SWING") == 0.0
        assert funding_cost_r(10_000, 50_000, 1000, -2.0, mode="SWING") == 0.0

    def test_higher_funding_rate_greater_magnitude(self):
        """Higher funding rate yields proportionally larger absolute cost."""
        low = funding_cost_r(
            10_000, 50_000, 1000, 2.0,
            mode="SWING", funding_rate=0.0001,
        )
        high = funding_cost_r(
            10_000, 50_000, 1000, 2.0,
            mode="SWING", funding_rate=0.0005,
        )
        assert abs(high) == pytest.approx(5.0 * abs(low), rel=1e-9)

    def test_custom_holding_hours(self):
        """Explicit holding_hours overrides mode default."""
        default = funding_cost_r(
            10_000, 50_000, 1000, 2.0,
            mode="SCALP",
        )
        custom = funding_cost_r(
            10_000, 50_000, 1000, 2.0,
            mode="SCALP", holding_hours=4.0,
        )
        # SCALP default = 2 intervals, custom = 4/8 = 0.5 intervals
        assert custom < default

    def test_zero_notional_returns_zero(self):
        """Zero notional produces zero funding cost."""
        cost = funding_cost_r(0, 50_000, 1000, 2.0, mode="SWING", funding_rate=0.0001)
        assert cost == 0.0

    def test_negative_funding_rate_short(self):
        """SHORT with negative funding rate pays (positive cost)."""
        cost = funding_cost_r(
            10_000, 50_000, 1000, 2.0,
            mode="SWING", funding_rate=-0.0001, direction="SHORT",
        )
        # (-1) * (-0.0001) * 10000 * 15 / 2000 = 15 * 1.0 / 2000 = 0.0075
        assert cost == pytest.approx(0.0075, rel=1e-9)
        assert cost > 0
