"""
Tests for lib/indicators/ -- spread, volume profile, VWAP.
"""

import math
import pytest
from lib.indicators.spread import (
    parkinson_spread,
    rolling_parkinson_spread,
    corwin_schultz_spread,
)
from lib.indicators.volume_profile import typical_price, vwap, rolling_vwap


# =====================================================================
# Parkinson spread (per-bar)
# =====================================================================

class TestParkinsonSpread:
    def test_basic(self):
        """Non-zero range produces positive spread."""
        spreads = parkinson_spread([10, 11, 12], [9, 10, 11])
        assert len(spreads) == 3
        assert all(v > 0 for v in spreads)

    def test_zero_range(self):
        """Zero range (high==low) produces zero spread."""
        spreads = parkinson_spread([10, 10], [10, 10])
        assert spreads == [0.0, 0.0]

    def test_known_value(self):
        """Manual calculation for one bar."""
        # high=12, low=10 → diff=2
        # inv_4ln2 = 1/(4*ln(2)) ≈ 0.360674
        # sqrt(4 * 0.360674) = sqrt(1.442695) ≈ 1.20112
        spreads = parkinson_spread([12], [10])
        inv_4ln2 = 1.0 / (4.0 * math.log(2.0))
        expected = math.sqrt(4.0 * inv_4ln2)
        assert spreads[0] == pytest.approx(expected, rel=1e-9)

    def test_empty(self):
        """Empty input returns empty list."""
        assert parkinson_spread([], []) == []


# =====================================================================
# Rolling Parkinson spread
# =====================================================================

class TestRollingParkinsonSpread:
    def test_basic(self):
        """Rolling spread with period=3."""
        spreads = rolling_parkinson_spread(
            [10, 11, 12, 11, 13],
            [8, 9, 10, 9, 10],
            period=3,
        )
        assert len(spreads) == 5
        assert math.isnan(spreads[0])
        assert math.isnan(spreads[1])
        assert spreads[2] > 0

    def test_nan_prefix(self):
        """First period-1 values are NaN."""
        spreads = rolling_parkinson_spread(
            [10, 11, 12, 13, 14],
            [9, 10, 11, 12, 13],
            period=3,
        )
        assert math.isnan(spreads[0])
        assert math.isnan(spreads[1])
        assert not math.isnan(spreads[2])

    def test_constant_range(self):
        """Constant high-low ratio gives constant spread."""
        spreads = rolling_parkinson_spread(
            [10, 10, 10, 10],
            [8, 8, 8, 8],
            period=3,
        )
        assert math.isnan(spreads[0])
        assert math.isnan(spreads[1])
        assert spreads[2] > 0
        assert spreads[2] == spreads[3]

    def test_period_larger_than_data(self):
        """All NaN when period > len(data)."""
        spreads = rolling_parkinson_spread([10, 11], [9, 10], period=5)
        assert all(math.isnan(v) for v in spreads)


# =====================================================================
# Corwin-Schultz spread
# =====================================================================

class TestCorwinSchultzSpread:
    def test_basic(self):
        """Two-day spread with realistic data."""
        highs = [10, 11, 12, 11, 13, 12]
        lows = [8, 9, 10, 9, 10, 10]
        spreads = corwin_schultz_spread(highs, lows)
        assert len(spreads) == 6
        assert math.isnan(spreads[0])
        # Some pairs may produce NaN (negative alpha) which is valid behavior
        positive = [s for s in spreads[1:] if not math.isnan(s)]
        assert len(positive) > 0
        assert all(s > 0 for s in positive)

    def test_negative_alpha_returns_nan(self):
        """When alpha <= 0, spread is NaN."""
        # Large two-day range relative to one-day ranges → variance-dominated
        spreads = corwin_schultz_spread([10, 12], [9.9, 11.9])
        assert math.isnan(spreads[0])
        assert math.isnan(spreads[1])

    def test_first_value_always_nan(self):
        """First value is always NaN (needs 2 bars)."""
        spreads = corwin_schultz_spread([10, 12], [8, 10])
        assert math.isnan(spreads[0])

    def test_single_element(self):
        """Single element returns [NaN]."""
        spreads = corwin_schultz_spread([10], [8])
        assert len(spreads) == 1
        assert math.isnan(spreads[0])

    def test_empty(self):
        """Empty input returns empty list."""
        assert corwin_schultz_spread([], []) == []


# =====================================================================
# Volume profile
# =====================================================================

class TestTypicalPrice:
    def test_basic(self):
        tp = typical_price([10, 12], [8, 10], [9, 11])
        assert len(tp) == 2
        assert tp[0] == pytest.approx((10 + 8 + 9) / 3.0)
        assert tp[1] == pytest.approx((12 + 10 + 11) / 3.0)

    def test_empty(self):
        assert typical_price([], [], []) == []


class TestVWAP:
    def test_basic(self):
        v = vwap([10, 11, 12], [8, 9, 10], [9, 10, 11], [100, 200, 300])
        assert len(v) == 3
        # First VWAP = first typical price
        tp0 = (10 + 8 + 9) / 3.0
        assert v[0] == pytest.approx(tp0)
        # VWAP across all bars
        tp1 = (11 + 9 + 10) / 3.0
        tp2 = (12 + 10 + 11) / 3.0
        expected = (tp0 * 100 + tp1 * 200 + tp2 * 300) / (100 + 200 + 300)
        assert v[2] == pytest.approx(expected)

    def test_zero_volume(self):
        """When all volumes are 0, all VWAPs are NaN."""
        v = vwap([10, 11], [8, 9], [9, 10], [0, 0])
        assert all(math.isnan(x) for x in v)

    def test_empty(self):
        assert vwap([], [], [], []) == []


class TestRollingVWAP:
    def test_basic(self):
        rv = rolling_vwap(
            [10, 11, 12, 13],
            [8, 9, 10, 11],
            [9, 10, 11, 12],
            [100, 200, 300, 400],
            period=2,
        )
        assert len(rv) == 4
        assert math.isnan(rv[0])
        assert not math.isnan(rv[1])
        assert not math.isnan(rv[2])

    def test_nan_prefix(self):
        rv = rolling_vwap(
            [10, 11, 12],
            [8, 9, 10],
            [9, 10, 11],
            [100, 200, 300],
            period=3,
        )
        assert math.isnan(rv[0])
        assert math.isnan(rv[1])
        assert not math.isnan(rv[2])

    def test_zero_volume_returns_nan(self):
        """When cumulative volume over window is 0, entry is NaN."""
        rv = rolling_vwap(
            [10, 11, 12],
            [8, 9, 10],
            [9, 10, 11],
            [0, 0, 0],
            period=2,
        )
        assert math.isnan(rv[0])
        assert math.isnan(rv[1])
        assert math.isnan(rv[2])

    def test_period_larger_than_data(self):
        """All NaN when period > len(data)."""
        rv = rolling_vwap(
            [10, 11],
            [8, 9],
            [9, 10],
            [100, 200],
            period=5,
        )
        assert all(math.isnan(v) for v in rv)
