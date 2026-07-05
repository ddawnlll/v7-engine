"""
Tests for lib/indicators/microstructure.py -- Amihud illiquidity and Roll spread.
"""

import math
import pytest
from lib.indicators.microstructure import amihud_illiquidity, roll_spread_estimator


# =====================================================================
# Amihud illiquidity
# =====================================================================

class TestAmihudIlliquidity:
    def test_basic(self):
        """Non-zero returns and volumes produce positive illiquidity."""
        returns = [0.01, -0.02, 0.015, -0.01, 0.005]
        volumes = [1000, 2000, 1500, 1800, 1200]
        illiq = amihud_illiquidity(returns, volumes, period=3)
        assert len(illiq) == 5
        assert math.isnan(illiq[0])
        assert math.isnan(illiq[1])
        assert illiq[2] > 0
        assert illiq[3] > 0
        assert illiq[4] > 0

    def test_nan_prefix(self):
        """First period-1 values are NaN."""
        returns = [0.01, -0.02, 0.015, 0.01]
        volumes = [100, 200, 150, 180]
        illiq = amihud_illiquidity(returns, volumes, period=3)
        assert math.isnan(illiq[0])
        assert math.isnan(illiq[1])
        assert not math.isnan(illiq[2])
        assert not math.isnan(illiq[3])

    def test_zero_volume_skipped(self):
        """Bars with zero volume are excluded from the average."""
        returns = [0.01, 0.02, 0.015]
        volumes = [100, 0, 150]
        illiq = amihud_illiquidity(returns, volumes, period=3)
        # The NaN return at index 1 isn't the issue; volume[1]=0 skips it
        assert not math.isnan(illiq[2])
        # Expected: (|0.01|/100 + |0.015|/150) / 2
        expected = (0.01 / 100 + 0.015 / 150) / 2.0
        assert illiq[2] == pytest.approx(expected, rel=1e-9)

    def test_all_zero_volume_returns_nan(self):
        """When all volumes in window are 0, result is NaN."""
        returns = [0.01, 0.02]
        volumes = [0, 0]
        illiq = amihud_illiquidity(returns, volumes, period=2)
        assert math.isnan(illiq[1])

    def test_nan_returns_skipped(self):
        """NaN returns are excluded from the average."""
        returns = [float("nan"), 0.02, float("nan"), 0.01]
        volumes = [100, 200, 300, 400]
        illiq = amihud_illiquidity(returns, volumes, period=3)
        # Window for index 2: [nan, 0.02, nan] → only one valid obs
        assert not math.isnan(illiq[2])
        assert illiq[2] == pytest.approx(0.02 / 200, rel=1e-9)

    def test_empty(self):
        """Empty input returns empty list."""
        assert amihud_illiquidity([], []) == []

    def test_small_data(self):
        """Fewer than period observations returns all NaN."""
        illiq = amihud_illiquidity([0.01], [100], period=5)
        assert all(math.isnan(v) for v in illiq)


# =====================================================================
# Roll spread estimator
# =====================================================================

class TestRollSpreadEstimator:
    def test_basic(self):
        """Alternating prices produce negative serial covariance → spread > 0."""
        # Bid-ask bounce: prices alternate between two levels
        prices = [100.0, 101.0, 100.0, 101.0, 100.0, 101.0]
        spread = roll_spread_estimator(prices, period=3)
        assert len(spread) == 6
        # First `period` values are NaN
        for i in range(3):
            assert math.isnan(spread[i])
        for i in range(3, 6):
            assert spread[i] > 0

    def test_nan_prefix(self):
        """First `period` values are NaN."""
        prices = [100.0, 101.0, 100.0, 101.0, 100.0, 101.0, 100.0]
        spread = roll_spread_estimator(prices, period=4)
        for i in range(4):
            assert math.isnan(spread[i])
        assert not math.isnan(spread[4])

    def test_positive_covariance_returns_zero(self):
        """Trending prices produce positive serial covariance → spread=0."""
        prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
        spread = roll_spread_estimator(prices, period=3)
        for i in range(3, 6):
            assert spread[i] == 0.0

    def test_small_data_all_nan(self):
        """Fewer than period+1 prices returns all NaN."""
        spread = roll_spread_estimator([100.0, 101.0, 102.0], period=5)
        assert all(math.isnan(v) for v in spread)

    def test_single_element(self):
        """Single price returns [NaN]."""
        spread = roll_spread_estimator([100.0], period=3)
        assert len(spread) == 1
        assert math.isnan(spread[0])

    def test_empty(self):
        """Empty input returns empty list."""
        assert roll_spread_estimator([], period=3) == []

    def test_default_period(self):
        """Default period=20 works with enough data."""
        # Create enough alternating prices
        prices = [100.0 + (i % 2) for i in range(30)]
        spread = roll_spread_estimator(prices)
        assert len(spread) == 30
        assert math.isnan(spread[19])
        # Alternating → negative covariance → spread > 0
        assert spread[20] > 0
