"""
Tests for lib/indicators/rsi.py — RSI using Wilder's smoothed EMA.
"""

import math
import pytest
from lib.indicators.rsi import rsi


class TestRSI:
    def test_basic(self):
        prices = [100.0, 102.0, 101.0, 103.0, 105.0, 104.0]
        result = rsi(prices, period=3)
        assert len(result) == 6
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        assert math.isnan(result[2])
        for i in range(3, 6):
            assert 0 <= result[i] <= 100

    def test_all_gains(self):
        """Strictly rising prices → avg_loss=0 → RSI=100."""
        result = rsi([100.0, 101.0, 102.0, 103.0, 104.0], period=3)
        assert result[3] == 100.0
        assert result[4] == 100.0

    def test_all_losses(self):
        """Strictly falling prices → avg_gain=0 → RSI=0."""
        result = rsi([100.0, 99.0, 98.0, 97.0, 96.0], period=3)
        assert result[3] == 0.0
        assert result[4] == 0.0

    def test_nan_prefix(self):
        """First `period` values must be NaN."""
        result = rsi([100.0, 101.0, 102.0, 103.0, 104.0], period=3)
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        assert math.isnan(result[2])
        assert not math.isnan(result[3])

    def test_period_1_returns_all_nan(self):
        """period=1 returns all NaN."""
        result = rsi([100.0, 101.0, 102.0], period=1)
        assert all(math.isnan(v) for v in result)

    def test_empty_input(self):
        """Empty input returns empty list."""
        assert rsi([]) == []

    def test_zero_price_returns_nan_at_affected_index(self):
        """Zero price at an index produces NaN at that index."""
        result = rsi([100.0, 0.0, 102.0, 103.0], period=2)
        assert math.isnan(result[1])  # period=2, index 1 is first NaN prefix
        # prices[2] > 0 so it computes; zero at [1] just means no gain/loss for that bar
        assert not math.isnan(result[2])

    def test_negative_price_returns_nan(self):
        """Negative price at an index produces NaN at that index."""
        result = rsi([100.0, -50.0, 102.0, 103.0], period=2)
        assert math.isnan(result[1])
        assert not math.isnan(result[2])

    def test_default_period(self):
        """Default period=14 works with enough data."""
        prices = [float(100 + i) for i in range(30)]
        result = rsi(prices)
        assert len(result) == 30
        assert math.isnan(result[13])
        assert not math.isnan(result[14])
        # Rising prices → RSI above 50
        assert result[14] > 50

    def test_period_larger_than_data(self):
        """When period > len(prices), all NaN."""
        result = rsi([100.0, 101.0, 102.0], period=10)
        assert all(math.isnan(v) for v in result)

    def test_rsi_range(self):
        """RSI values are in [0, 100] for valid inputs."""
        import random
        random.seed(42)
        prices = [100.0 + random.uniform(-5, 5) for _ in range(50)]
        result = rsi(prices, period=14)
        for v in result:
            if not math.isnan(v):
                assert 0 <= v <= 100, f"RSI {v} outside [0, 100]"
