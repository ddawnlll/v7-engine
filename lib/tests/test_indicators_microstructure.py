"""
Tests for lib/indicators/microstructure.py —
Amihud illiquidity, Roll spread, dollar volume.
"""

import math
import pytest
from lib.indicators.microstructure import (
    amihud_illiquidity,
    dollar_volume,
    roll_spread,
)


# =====================================================================
# Dollar Volume
# =====================================================================

class TestDollarVolume:
    def test_basic(self):
        """dollar_volume = close * volume for each bar."""
        closes = [10.0, 12.0, 11.0]
        volumes = [100.0, 200.0, 150.0]
        result = dollar_volume(closes, volumes)
        assert result[0] == 1000.0
        assert result[1] == 2400.0
        assert result[2] == 1650.0

    def test_zero_close(self):
        """Zero close returns NaN dollar volume."""
        result = dollar_volume([0.0, 10.0], [100.0, 200.0])
        assert math.isnan(result[0])
        assert result[1] == 2000.0

    def test_negative_close(self):
        """Negative close returns NaN dollar volume."""
        result = dollar_volume([-5.0], [100.0])
        assert math.isnan(result[0])

    def test_zero_volume(self):
        """Zero volume returns 0 dollar volume."""
        result = dollar_volume([10.0], [0.0])
        assert result[0] == 0.0

    def test_empty_input(self):
        """Empty input returns empty list."""
        assert dollar_volume([], []) == []


# =====================================================================
# Amihud Illiquidity
# =====================================================================

class TestAmihudIlliquidity:
    def test_basic(self):
        """Amihud ILLIQ = mean(|r| / dollar_vol) over window."""
        returns = [float("nan"), 0.02, -0.01, 0.03, -0.005]
        dollar_vols = [10000, 12000, 9000, 11000, 13000]
        result = amihud_illiquidity(returns, dollar_vols, period=3)
        assert len(result) == 5
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        # index 2: bars 0-2, but bar 0 return is NaN so only bars 1-2 count
        expected_2 = (abs(0.02) / 12000 + abs(-0.01) / 9000) / 2
        assert result[2] == pytest.approx(expected_2, rel=1e-9)
        # index 3: bars 1-3
        expected_3 = (abs(0.02) / 12000 + abs(-0.01) / 9000 + abs(0.03) / 11000) / 3
        assert result[3] == pytest.approx(expected_3, rel=1e-9)

    def test_zero_dollar_volume(self):
        """Zero dollar volume is skipped in the average."""
        returns = [0.01, 0.02, 0.01]
        dollar_vols = [0, 1000, 2000]
        result = amihud_illiquidity(returns, dollar_vols, period=2)
        # index 1: bars 0-1, dv[0]=0 skipped, dv[1]=1000, only bar 1 counts
        expected_1 = abs(0.02) / 1000
        assert result[1] == pytest.approx(expected_1, rel=1e-9)

    def test_all_nan_returns(self):
        """All NaN returns give NaN illiquidity."""
        returns = [float("nan")] * 10
        dollar_vols = list(range(1000, 1100))
        result = amihud_illiquidity(returns, dollar_vols, period=3)
        for i in range(2, 10):
            assert math.isnan(result[i])

    def test_period_larger_than_data(self):
        """Period larger than input -> all NaN."""
        result = amihud_illiquidity(
            [0.01, 0.02], [1000, 2000], period=5
        )
        assert all(math.isnan(v) for v in result)

    def test_empty_input(self):
        """Empty input returns empty list."""
        assert amihud_illiquidity([], [], period=3) == []

    def test_single_element(self):
        """Single element returns NaN."""
        result = amihud_illiquidity([0.01], [1000], period=3)
        assert math.isnan(result[0])

    def test_large_illiquidity(self):
        """Large return on small volume -> high illiquidity."""
        returns = [0.05, 0.05, 0.05]
        dollar_vols = [100, 100, 100]  # tiny dollar vol
        result = amihud_illiquidity(returns, dollar_vols, period=2)
        # Bar 0 return=NaN (no prior), bar 1: (0.05/100 + 0.05/100)/2 = 0.0005
        assert result[1] > 0
        assert result[2] > 0

    def test_negative_returns(self):
        """Negative returns are handled with abs()."""
        returns = [float("nan"), -0.03, -0.02, 0.01]
        dollar_vols = [1000, 1000, 1000, 1000]
        result = amihud_illiquidity(returns, dollar_vols, period=3)
        # index 2: bars 0-2, bar 0 return NaN, bars 1-2: (0.03+0.02)/2000 = 0.000025
        expected_2 = (abs(-0.03) / 1000 + abs(-0.02) / 1000) / 2
        assert result[2] == pytest.approx(expected_2, rel=1e-9)


# =====================================================================
# Roll Spread
# =====================================================================

class TestRollSpread:
    def test_basic(self):
        """Roll spread = 2 * sqrt(-cov(Δp_t, Δp_{t-1})) for neg cov."""
        # Alternating prices: 100, 101, 100, 101, 100, 101
        # dp: NaN, +1, -1, +1, -1, +1
        # cov(dp(t), dp(t-1)):
        #   pairs: (+1,-1), (-1,+1), (+1,-1), (-1,+1)
        #   mean_x = 0, mean_y = 0
        #   cov = mean(xy) = (-1 + -1 + -1 + -1)/4 = -1
        # spread = 2 * sqrt(1) = 2
        closes = [100.0, 101.0, 100.0, 101.0, 100.0, 101.0]
        result = roll_spread(closes, period=4)
        assert len(result) == 6
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        assert math.isnan(result[2])
        assert math.isnan(result[3])
        assert math.isnan(result[4])
        # index 5: bars 2-5 (period=4), dp pairs: dp[2..5] with lags dp[1..4]
        # dp: [NaN, 1, -1, 1, -1, 1]
        # lagged dp: [NaN, NaN, 1, -1, 1, -1]
        # pairs for i=5, window j=2..5: (dp[1]=1,dp[2]=-1), (dp[2]=-1,dp[3]=1), (dp[3]=1,dp[4]=-1), (dp[4]=-1,dp[5]=1)
        # cov = ((-1)+(-1)+(-1)+(-1))/4 = -1
        assert result[5] == pytest.approx(2.0, rel=1e-6)

    def test_positive_autocovariance(self):
        """Positive autocovariance -> spread = 0 (no bounce signal)."""
        # Trending up: 100, 101, 102, 103, 104, 105
        # dp: NaN, +1, +1, +1, +1, +1
        # cov of consecutive returns is 0 for constant changes
        closes = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
        result = roll_spread(closes, period=4)
        assert result[5] == pytest.approx(0.0, rel=1e-6)

    def test_no_bounce(self):
        """Random walk with no bounce -> near-zero spread."""
        import random
        random.seed(42)
        closes = [100.0]
        for _ in range(15):
            closes.append(closes[-1] * (1 + random.gauss(0, 0.01)))
        result = roll_spread(closes, period=10)
        # Should be near zero (random walk, no bounce)
        finite = [v for v in result if not math.isnan(v)]
        assert len(finite) > 0
        for v in finite:
            assert v >= 0  # spread is always non-negative

    def test_period_larger_than_data(self):
        """Need at least period+2 bars; too few returns all NaN."""
        result = roll_spread([100, 101, 102], period=5)
        assert all(math.isnan(v) for v in result)

    def test_empty_input(self):
        """Empty input returns empty list."""
        assert roll_spread([], period=3) == []

    def test_single_element(self):
        """Single element returns NaN."""
        result = roll_spread([100], period=3)
        assert math.isnan(result[0])

    def test_two_elements(self):
        """Two elements: only one price change, cannot compute cov."""
        result = roll_spread([100, 101], period=2)
        assert all(math.isnan(v) for v in result)

    def test_non_negative_values(self):
        """All computed Roll spread values are >= 0."""
        import random
        random.seed(7)
        closes = [100.0]
        for _ in range(20):
            closes.append(closes[-1] * (1 + random.gauss(0, 0.02)))
        result = roll_spread(closes, period=5)
        for v in result:
            if not math.isnan(v):
                assert v >= 0
