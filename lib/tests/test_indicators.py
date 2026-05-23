"""
Tests for lib/indicators/ — ATR, returns, volatility, rolling.
"""

import math
import pytest
from lib.indicators.atr import compute_atr
from lib.indicators.returns import log_returns, simple_returns
from lib.indicators.volatility import rolling_std, parkinson_vol
from lib.indicators.rolling import rolling_apply


# =====================================================================
# ATR
# =====================================================================

class TestComputeATR:
    def test_basic(self):
        highs = [10, 12, 11, 13, 14, 12, 15]
        lows = [8, 9, 8, 10, 11, 9, 12]
        closes = [9, 11, 10, 12, 13, 11, 14]
        atr = compute_atr(highs, lows, closes, period=3)
        assert len(atr) == 7
        # First 3 values should be NaN
        assert math.isnan(atr[0])
        assert math.isnan(atr[1])
        assert math.isnan(atr[2])
        # From index 3 onward should be finite positive (first ATR at index=period)
        for i in range(3, 7):
            assert atr[i] > 0

    def test_period_1(self):
        highs = [10, 12, 11]
        lows = [8, 9, 9]
        closes = [9, 11, 10]
        atr = compute_atr(highs, lows, closes, period=1)
        assert len(atr) == 3
        assert math.isnan(atr[0])
        assert atr[1] == pytest.approx(max(12 - 9, abs(12 - 9), abs(9 - 9)), rel=1e-9)
        assert atr[2] > 0

    def test_constant_prices(self):
        highs = [10] * 10
        lows = [10] * 10
        closes = [10] * 10
        atr = compute_atr(highs, lows, closes, period=5)
        assert len(atr) == 10
        # First 5 values should be NaN (first ATR at index 5)
        for i in range(5):
            assert math.isnan(atr[i])
        # From index 5 onward ATR should be 0 (true range is always 0)
        for i in range(5, 10):
            assert atr[i] == 0.0

    def test_single_element(self):
        atr = compute_atr([10], [8], [9], period=14)
        assert len(atr) == 1
        assert math.isnan(atr[0])

    def test_empty(self):
        atr = compute_atr([], [], [])
        assert atr == []

    def test_period_larger_than_data(self):
        atr = compute_atr([10, 11, 12], [8, 9, 10], [9, 10, 11], period=14)
        assert len(atr) == 3
        assert all(math.isnan(v) for v in atr)

    def test_default_period(self):
        # Ensure default period=14 works with enough data
        highs = [float(100 + i) for i in range(30)]
        lows = [float(90 + i) for i in range(30)]
        closes = [float(95 + i) for i in range(30)]
        atr = compute_atr(highs, lows, closes)
        assert len(atr) == 30
        assert math.isnan(atr[13])
        assert atr[14] > 0


# =====================================================================
# Returns
# =====================================================================

class TestLogReturns:
    def test_basic(self):
        rets = log_returns([100.0, 105.0, 102.0])
        assert len(rets) == 3
        assert math.isnan(rets[0])
        assert rets[1] == pytest.approx(math.log(105.0 / 100.0), rel=1e-9)
        assert rets[2] == pytest.approx(math.log(102.0 / 105.0), rel=1e-9)

    def test_negative_return(self):
        rets = log_returns([100.0, 90.0])
        assert rets[1] < 0

    def test_zero_return(self):
        rets = log_returns([100.0, 100.0])
        assert rets[1] == 0.0

    def test_single_element(self):
        assert all(math.isnan(v) for v in log_returns([100.0]))

    def test_empty(self):
        assert log_returns([]) == []

    def test_zero_price(self):
        rets = log_returns([100.0, 0.0])
        assert math.isnan(rets[1])

    def test_negative_price(self):
        rets = log_returns([100.0, -50.0])
        assert math.isnan(rets[1])


class TestSimpleReturns:
    def test_basic(self):
        rets = simple_returns([100.0, 105.0, 102.0])
        assert len(rets) == 3
        assert math.isnan(rets[0])
        assert rets[1] == 0.05
        assert rets[2] == pytest.approx(-0.0285714, rel=1e-5)

    def test_single_element(self):
        assert all(math.isnan(v) for v in simple_returns([100.0]))

    def test_empty(self):
        assert simple_returns([]) == []

    def test_zero_price(self):
        rets = simple_returns([100.0, 0.0])
        assert rets[1] == -1.0

    def test_negative_price(self):
        rets = simple_returns([100.0, -50.0])
        assert rets[1] == -1.5


# =====================================================================
# Rolling std
# =====================================================================

class TestRollingStd:
    def test_basic(self):
        stds = rolling_std([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], period=3)
        assert len(stds) == 10
        assert math.isnan(stds[0])
        assert math.isnan(stds[1])
        assert stds[2] == pytest.approx(0.81649658, rel=1e-5)
        assert stds[9] == pytest.approx(0.81649658, rel=1e-5)

    def test_period_1(self):
        stds = rolling_std([1, 2, 3], period=1)
        assert stds[0] == 0.0
        assert stds[1] == 0.0
        assert stds[2] == 0.0

    def test_period_larger_than_data(self):
        stds = rolling_std([1, 2], period=5)
        assert all(math.isnan(v) for v in stds)

    def test_constant_values(self):
        stds = rolling_std([5] * 10, period=4)
        assert all(v == 0.0 for v in stds[3:])

    def test_single_element(self):
        stds = rolling_std([1], period=3)
        assert math.isnan(stds[0])


# =====================================================================
# Parkinson vol
# =====================================================================

class TestParkinsonVol:
    def test_basic(self):
        vols = parkinson_vol([10, 11, 12, 11, 13], [8, 9, 10, 9, 10], period=3)
        assert len(vols) == 5
        assert math.isnan(vols[0])
        assert math.isnan(vols[1])
        assert vols[2] > 0

    def test_constant_range(self):
        # H/L same every day → log(H/L) same every day, vol is constant > 0
        vols = parkinson_vol([10, 10, 10, 10], [9, 9, 9, 9], period=3)
        assert math.isnan(vols[0])
        assert math.isnan(vols[1])
        # Constant H/L gives constant non-zero vol
        assert vols[2] > 0
        assert vols[2] == vols[3]  # same because same values

    def test_period_larger_than_data(self):
        vols = parkinson_vol([10, 11], [8, 9], period=5)
        assert all(math.isnan(v) for v in vols)

    def test_single_element(self):
        vols = parkinson_vol([10], [8], period=3)
        assert math.isnan(vols[0])


# =====================================================================
# Rolling apply
# =====================================================================

class TestRollingApply:
    def test_sum(self):
        result = rolling_apply([1, 2, 3, 4, 5], 3, lambda w: sum(w))
        assert result == [None, None, 6, 9, 12]

    def test_custom_function(self):
        result = rolling_apply([1, 2, 3, 4], 2, lambda w: max(w))
        assert result == [None, 2, 3, 4]

    def test_min_periods(self):
        result = rolling_apply([1, 2, 3, 4], 3, lambda w: sum(w), min_periods=2)
        assert result == [None, 3, 6, 9]

    def test_min_periods_1(self):
        result = rolling_apply([1, 2, 3], 3, lambda w: sum(w), min_periods=1)
        assert result == [1, 3, 6]

    def test_window_larger_than_data(self):
        result = rolling_apply([1, 2], 5, lambda w: sum(w))
        assert result == [None, None]

    def test_empty(self):
        assert rolling_apply([], 3, lambda w: sum(w)) == []
