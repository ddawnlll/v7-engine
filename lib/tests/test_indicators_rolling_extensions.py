"""
Tests for lib/indicators/rolling.py — rolling_max, rolling_min, rolling_mean.
"""

import math
import pytest
from lib.indicators.rolling import rolling_max, rolling_min, rolling_mean


class TestRollingMax:
    def test_basic(self):
        """rolling_max([1,3,2,5,4], 3) → [NaN, NaN, 3, 5, 5]."""
        result = rolling_max([1, 3, 2, 5, 4], period=3)
        assert len(result) == 5
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        assert result[2] == 3
        assert result[3] == 5
        assert result[4] == 5

    def test_period_1(self):
        """period=1 returns values unchanged."""
        result = rolling_max([1, 3, 2], period=1)
        assert result == [1, 3, 2]

    def test_constant_series(self):
        """Constant series returns constant values after NaN prefix."""
        result = rolling_max([5] * 6, period=3)
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        assert all(v == 5 for v in result[2:])

    def test_empty_input(self):
        """Empty input returns empty list."""
        assert rolling_max([]) == []

    def test_period_larger_than_data(self):
        """period > len(prices) returns all NaN."""
        result = rolling_max([1, 2], period=10)
        assert all(math.isnan(v) for v in result)


class TestRollingMin:
    def test_basic(self):
        """rolling_min([5,3,4,1,2], 3) → [NaN, NaN, 3, 1, 1]."""
        result = rolling_min([5, 3, 4, 1, 2], period=3)
        assert len(result) == 5
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        assert result[2] == 3
        assert result[3] == 1
        assert result[4] == 1

    def test_period_1(self):
        """period=1 returns values unchanged."""
        result = rolling_min([5, 3, 4], period=1)
        assert result == [5, 3, 4]

    def test_constant_series(self):
        """Constant series returns constant values after NaN prefix."""
        result = rolling_min([5] * 6, period=3)
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        assert all(v == 5 for v in result[2:])

    def test_empty_input(self):
        """Empty input returns empty list."""
        assert rolling_min([]) == []

    def test_period_larger_than_data(self):
        """period > len(prices) returns all NaN."""
        result = rolling_min([1, 2], period=10)
        assert all(math.isnan(v) for v in result)


class TestRollingMean:
    def test_basic(self):
        """rolling_mean([1,2,3], 3) → [NaN, NaN, 2.0]."""
        result = rolling_mean([1, 2, 3], period=3)
        assert len(result) == 3
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        assert result[2] == 2.0

    def test_larger_window(self):
        """rolling_mean([1,2,3,4,5], 3) → [NaN, NaN, 2, 3, 4]."""
        result = rolling_mean([1, 2, 3, 4, 5], period=3)
        assert result[2] == 2.0
        assert result[3] == 3.0
        assert result[4] == 4.0

    def test_period_1(self):
        """period=1 returns values unchanged."""
        result = rolling_mean([1, 2, 3], period=1)
        assert result == [1, 2, 3]

    def test_constant_series(self):
        """Constant series returns constant values after NaN prefix."""
        result = rolling_mean([5] * 6, period=3)
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        assert all(v == 5 for v in result[2:])

    def test_empty_input(self):
        """Empty input returns empty list."""
        assert rolling_mean([]) == []

    def test_period_larger_than_data(self):
        """period > len(prices) returns all NaN."""
        result = rolling_mean([1, 2], period=10)
        assert all(math.isnan(v) for v in result)
