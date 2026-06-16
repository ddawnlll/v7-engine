"""
Tests for lib/indicators/momentum.py — momentum and rate of change.
"""

import math
import pytest
from lib.indicators.momentum import momentum, rate_of_change


class TestMomentum:
    def test_basic(self):
        """momentum = (P_t - P_{t-period}) / P_{t-period}."""
        prices = [100.0, 105.0, 110.0, 115.0]
        result = momentum(prices, period=2)
        assert len(result) == 4
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        assert result[2] == pytest.approx((110.0 - 100.0) / 100.0)
        assert result[3] == pytest.approx((115.0 - 105.0) / 105.0)

    def test_nan_prefix(self):
        """First `period` values are NaN."""
        result = momentum([100.0, 102.0, 104.0, 106.0], period=3)
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        assert math.isnan(result[2])

    def test_zero_base_price(self):
        """Zero base price returns NaN."""
        result = momentum([0.0, 100.0, 105.0, 110.0], period=2)
        assert math.isnan(result[2])  # base is prices[0] = 0.0

    def test_negative_base_price(self):
        """Negative base price returns NaN."""
        result = momentum([-100.0, 100.0, 105.0, 110.0], period=2)
        assert math.isnan(result[2])  # base is prices[0] = -100.0

    def test_empty_input(self):
        """Empty input returns empty list."""
        assert momentum([]) == []

    def test_period_larger_than_data(self):
        """period > len(prices) returns all NaN."""
        result = momentum([100.0, 102.0], period=10)
        assert all(math.isnan(v) for v in result)

    def test_negative_momentum(self):
        """Falling prices produce negative momentum."""
        result = momentum([100.0, 95.0, 90.0, 85.0], period=2)
        assert result[2] < 0
        assert result[3] < 0

    def test_zero_momentum(self):
        """Flat prices produce zero momentum."""
        result = momentum([100.0, 100.0, 100.0, 100.0], period=2)
        assert result[2] == 0.0
        assert result[3] == 0.0


class TestRateOfChange:
    def test_basic(self):
        """rate_of_change = momentum * 100."""
        prices = [100.0, 105.0, 110.0, 115.0]
        roc = rate_of_change(prices, period=2)
        mom = momentum(prices, period=2)
        assert len(roc) == 4
        assert math.isnan(roc[0])
        assert math.isnan(roc[1])
        assert roc[2] == pytest.approx(mom[2] * 100)
        assert roc[3] == pytest.approx(mom[3] * 100)

    def test_nan_prefix(self):
        """First `period` values are NaN."""
        result = rate_of_change([100.0, 102.0, 104.0], period=2)
        assert math.isnan(result[0])
        assert math.isnan(result[1])

    def test_zero_base_price(self):
        """Zero base price returns NaN."""
        result = rate_of_change([0.0, 100.0, 105.0], period=2)
        assert math.isnan(result[2])

    def test_empty_input(self):
        """Empty input returns empty list."""
        assert rate_of_change([]) == []
