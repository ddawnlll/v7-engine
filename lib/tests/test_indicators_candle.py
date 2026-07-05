"""
Tests for lib/indicators/candle.py — candle geometry ratios.
"""

import math
import pytest
from lib.indicators.candle import body_ratio, upper_wick_ratio, lower_wick_ratio


class TestCandleRatios:
    def test_body_ratio_basic(self):
        """body_ratio for a known candle."""
        # Bullish: open=10, close=15, high=18, low=8
        # body_ratio = |15-10| / (18-8) = 5/10 = 0.5
        result = body_ratio([10], [18], [8], [15])
        assert result[0] == pytest.approx(0.5)

    def test_body_ratio_bearish(self):
        """body_ratio for a bearish candle."""
        # Bearish: open=15, close=10, high=18, low=8
        # body_ratio = |10-15| / (18-8) = 5/10 = 0.5
        result = body_ratio([15], [18], [8], [10])
        assert result[0] == pytest.approx(0.5)

    def test_body_ratio_doji(self):
        """Doji (open==close) returns body_ratio=0.0, not NaN."""
        result = body_ratio([10], [15], [5], [10])
        assert result[0] == 0.0

    def test_upper_wick_basic(self):
        """upper_wick_ratio for a known candle."""
        # Bullish: open=10, close=15, high=18, low=8
        # upper_wick = (18 - max(10,15)) / (18-8) = (18-15)/10 = 0.3
        result = upper_wick_ratio([10], [18], [8], [15])
        assert result[0] == pytest.approx(0.3)

    def test_lower_wick_basic(self):
        """lower_wick_ratio for a known candle."""
        # Bullish: open=10, close=15, high=18, low=8
        # lower_wick = (min(10,15) - 8) / (18-8) = (10-8)/10 = 0.2
        result = lower_wick_ratio([10], [18], [8], [15])
        assert result[0] == pytest.approx(0.2)

    def test_flat_candle_nan(self):
        """Flat candle (high==low) returns NaN for all three ratios."""
        o = body_ratio([10], [10], [10], [10])
        u = upper_wick_ratio([10], [10], [10], [10])
        lw = lower_wick_ratio([10], [10], [10], [10])
        assert math.isnan(o[0])
        assert math.isnan(u[0])
        assert math.isnan(lw[0])

    def test_ratios_sum_to_one(self):
        """For a single candle, body + upper wick + lower wick = 1.0."""
        opens = [10]
        highs = [18]
        lows = [8]
        closes = [15]
        b = body_ratio(opens, highs, lows, closes)[0]
        u = upper_wick_ratio(opens, highs, lows, closes)[0]
        lw = lower_wick_ratio(opens, highs, lows, closes)[0]
        assert b + u + lw == pytest.approx(1.0)

    def test_ratios_in_0_1(self):
        """All ratios are in [0, 1] for valid non-flat candles."""
        opens = [10, 12, 11]
        highs = [18, 17, 16]
        lows = [8, 9, 10]
        closes = [15, 11, 14]
        for fn in [body_ratio, upper_wick_ratio, lower_wick_ratio]:
            result = fn(opens, highs, lows, closes)
            for v in result:
                assert 0 <= v <= 1

    def test_length_mismatch_raises(self):
        """Input length mismatch raises ValueError."""
        with pytest.raises(ValueError):
            body_ratio([10], [18, 19], [8], [15])
        with pytest.raises(ValueError):
            upper_wick_ratio([10], [18], [8, 9], [15])
        with pytest.raises(ValueError):
            lower_wick_ratio([10], [18], [8], [15, 16])

    def test_multi_candle(self):
        """Multiple candles return correct ratios for each."""
        opens = [10, 20, 30]
        highs = [18, 28, 38]
        lows = [8, 18, 28]
        closes = [15, 25, 35]
        b = body_ratio(opens, highs, lows, closes)
        assert len(b) == 3
        assert b[0] == pytest.approx(0.5)
        assert b[1] == pytest.approx(0.5)
        assert b[2] == pytest.approx(0.5)

    def test_empty_input(self):
        """Empty input returns empty list."""
        assert body_ratio([], [], [], []) == []
        assert upper_wick_ratio([], [], [], []) == []
        assert lower_wick_ratio([], [], [], []) == []
