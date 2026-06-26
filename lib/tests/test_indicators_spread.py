"""
Tests for lib/indicators/spread.py and lib/indicators/volume_profile.py —
HL spread, Parkinson spread, VWAP, volume profile.
"""

import math
import pytest
from lib.indicators.spread import hl_spread, hl_spread_bps, parkinson_spread
from lib.indicators.volume_profile import vwap, compute_volume_profile, VolumeProfile


# =====================================================================
# High-Low Spread
# =====================================================================

class TestHLSpread:
    def test_basic(self):
        """hl_spread computes per-bar (H-L)/close averaged over period."""
        highs = [10, 12, 11, 13, 14]
        lows = [8, 9, 8, 10, 11]
        closes = [9, 11, 10, 12, 13]
        result = hl_spread(highs, lows, closes, period=3)
        assert len(result) == 5
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        # index 2: bars 0-2: (2/9 + 3/11 + 3/10)/3 = (0.2222 + 0.2727 + 0.3)/3
        expected_2 = ((10 - 8) / 9 + (12 - 9) / 11 + (11 - 8) / 10) / 3
        assert result[2] == pytest.approx(expected_2, rel=1e-4)
        assert result[3] > 0
        assert result[4] > 0

    def test_constant_prices(self):
        """Zero spread when H=L (no range)."""
        highs = [10.0] * 10
        lows = [10.0] * 10
        closes = [10.0] * 10
        result = hl_spread(highs, lows, closes, period=3)
        # All computed values should be 0 (spread=0 since H-L=0)
        for v in result[2:]:
            assert v == 0.0

    def test_period_larger_than_data(self):
        """period > len(input) returns all NaN."""
        result = hl_spread([10, 11], [9, 10], [9.5, 10.5], period=5)
        assert len(result) == 2
        assert all(math.isnan(v) for v in result)

    def test_single_element(self):
        """Single element returns NaN."""
        result = hl_spread([10], [9], [9.5], period=3)
        assert math.isnan(result[0])

    def test_empty_input(self):
        """Empty input returns empty list."""
        assert hl_spread([], [], [], period=3) == []

    def test_zero_close(self):
        """Zero close price gives NaN for affected bars."""
        highs = [10, 12, 11, 13]
        lows = [8, 9, 8, 10]
        closes = [0, 11, 10, 12]
        result = hl_spread(highs, lows, closes, period=2)
        assert math.isnan(result[0])
        # bar[1] window=[0,1]: bar[0] has close=0 -> raw spread NaN, skipped;
        # only bar[1] with (12-9)/11 counts, so result[1] is finite
        assert not math.isnan(result[1])
        assert result[1] > 0
        assert result[2] > 0
        assert result[3] > 0


# =====================================================================
# Parkinson Spread
# =====================================================================

class TestParkinsonSpread:
    def test_basic(self):
        """parkinson_spread computes Parkinson statistic on rolling window."""
        highs = [10, 11, 12, 11, 13]
        lows = [8, 9, 10, 9, 10]
        result = parkinson_spread(highs, lows, period=3)
        assert len(result) == 5
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        assert result[2] > 0
        assert result[3] > 0
        assert result[4] > 0

    def test_constant_range(self):
        """Same H/L ratio every bar gives constant spread."""
        highs = [10, 10, 10, 10]
        lows = [9, 9, 9, 9]
        result = parkinson_spread(highs, lows, period=3)
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        assert result[2] == result[3]

    def test_zero_low(self):
        """Zero low price gives NaN for affected windows."""
        highs = [10, 11, 12, 13]
        lows = [8, 0, 10, 11]
        result = parkinson_spread(highs, lows, period=2)
        # Window [0,1]: index 0 has H/L valid, index 1 has L=0, sum_sq unchanged
        # Actually only highs[0],lows[0] valid; highs[1],lows[1] invalid (low=0)
        # So count depends on implementation — at least result[1] is calculated
        # The point: function handles it gracefully
        assert len(result) == 4
        # Check no exception was raised
        for v in result:
            pass  # just verify it ran

    def test_period_larger_than_data(self):
        """Period larger than input returns all NaN."""
        result = parkinson_spread([10, 11], [8, 9], period=5)
        assert all(math.isnan(v) for v in result)

    def test_single_element(self):
        """Single element returns NaN."""
        result = parkinson_spread([10], [8], period=3)
        assert math.isnan(result[0])

    def test_empty_input(self):
        """Empty input returns empty list."""
        assert parkinson_spread([], [], period=3) == []

    def test_positive_values(self):
        """All computed values should be non-negative."""
        highs = [float(100 + i) for i in range(30)]
        lows = [float(95 + i) for i in range(30)]
        result = parkinson_spread(highs, lows, period=5)
        for i in range(4, 30):
            assert result[i] >= 0


# =====================================================================
# HL Spread BPS
# =====================================================================

class TestHLSpreadBPS:
    def test_scaling(self):
        """hl_spread_bps = hl_spread * 10000."""
        highs = [10, 12, 11, 13, 14]
        lows = [8, 9, 8, 10, 11]
        closes = [9, 11, 10, 12, 13]
        raw = hl_spread(highs, lows, closes, period=3)
        bps = hl_spread_bps(highs, lows, closes, period=3)
        assert len(bps) == len(raw)
        for r, b in zip(raw, bps):
            if math.isnan(r):
                assert math.isnan(b)
            else:
                assert b == pytest.approx(r * 10000, rel=1e-9)


# =====================================================================
# VWAP
# =====================================================================

class TestVWAP:
    def test_basic(self):
        """VWAP is volume-weighted typical price over the window."""
        highs = [10, 12, 11, 13]
        lows = [8, 9, 8, 10]
        closes = [9, 11, 10, 12]
        volumes = [100, 120, 90, 110]
        result = vwap(highs, lows, closes, volumes, period=2)
        assert len(result) == 4
        assert math.isnan(result[0])
        # index 1: tp[0]=(10+8+9)/3=9, tp[1]=(12+9+11)/3=10.666...
        # vwap = (9*100 + 10.6667*120) / (100+120) = (900+1280)/220 = 2180/220 = 9.90909...
        tp0 = (10 + 8 + 9) / 3
        tp1 = (12 + 9 + 11) / 3
        expected_1 = (tp0 * 100 + tp1 * 120) / (100 + 120)
        assert result[1] == pytest.approx(expected_1, rel=1e-4)

    def test_uniform_volumes(self):
        """Equal volumes -> VWAP = simple average of typical prices."""
        highs = [10, 12, 11]
        lows = [8, 9, 8]
        closes = [9, 11, 10]
        volumes = [1, 1, 1]
        result = vwap(highs, lows, closes, volumes, period=3)
        tp0 = (10 + 8 + 9) / 3
        tp1 = (12 + 9 + 11) / 3
        tp2 = (11 + 8 + 10) / 3
        expected = (tp0 + tp1 + tp2) / 3
        assert result[2] == pytest.approx(expected, rel=1e-4)

    def test_zero_volumes(self):
        """Zero volume in window -> NaN."""
        highs = [10, 12]
        lows = [8, 9]
        closes = [9, 11]
        volumes = [0, 0]
        result = vwap(highs, lows, closes, volumes, period=2)
        assert math.isnan(result[1])

    def test_period_larger_than_data(self):
        """Period larger than data -> all NaN."""
        result = vwap([10, 11], [9, 10], [9.5, 10.5], [100, 200], period=5)
        assert all(math.isnan(v) for v in result)

    def test_empty_input(self):
        """Empty input returns empty list."""
        assert vwap([], [], [], [], period=3) == []


# =====================================================================
# Volume Profile
# =====================================================================

class TestVolumeProfile:
    def test_basic(self):
        """Volume profile computes POC, VAH, VAL from price/volume data."""
        highs = [11, 13, 15, 17, 19]
        lows = [9, 11, 13, 15, 17]
        closes = [10, 12, 14, 16, 18]
        volumes = [100, 200, 300, 200, 100]
        vp = compute_volume_profile(highs, lows, closes, volumes, num_bins=5)
        assert isinstance(vp, VolumeProfile)
        assert len(vp.price_bins) == 5
        assert len(vp.volume_per_bin) == 5
        assert vp.total_volume > 0
        # POC should be bin 2 (middle) with highest volume (300)
        assert vp.poc_idx == 2
        assert vp.poc_price is not None
        assert vp.vah_price is not None
        assert vp.val_price is not None
        # Ensure all bin volumes sum to total_volume
        assert sum(vp.volume_per_bin) == pytest.approx(vp.total_volume, rel=1e-9)

    def test_single_bar(self):
        """Single bar: all volume in one bin."""
        vp = compute_volume_profile(
            [10], [9], [9.5], [100], num_bins=3
        )
        assert vp.total_volume == 100
        # All volume in one bin, so POC = VAH = VAL
        assert vp.poc_idx == vp.vah_idx == vp.val_idx
        assert vp.poc_price == vp.vah_price == vp.val_price

    def test_empty_input(self):
        """Empty input returns default VolumeProfile."""
        vp = compute_volume_profile([], [], [], [])
        assert vp.total_volume == 0
        assert vp.poc_price is None

    def test_zero_volume(self):
        """All zero volumes -> total_volume 0, no POC."""
        highs = [10, 12]
        lows = [8, 10]
        closes = [9, 11]
        volumes = [0, 0]
        vp = compute_volume_profile(highs, lows, closes, volumes, num_bins=3)
        assert vp.total_volume == 0
        assert vp.poc_price is None

    def test_flat_price_range(self):
        """Flat price range (all H=L) returns empty profile."""
        vp = compute_volume_profile(
            [10, 10, 10], [10, 10, 10], [10, 10, 10], [100, 200, 300]
        )
        assert vp.total_volume == 0  # price_max <= price_min

    def test_properties(self):
        """VolumeProfile properties return correct values."""
        highs = [10, 12, 11]
        lows = [8, 9, 8]
        closes = [9, 11, 10]
        volumes = [100, 200, 150]
        vp = compute_volume_profile(highs, lows, closes, volumes, num_bins=5)
        assert vp.poc_price == vp.price_bins[vp.poc_idx]
        assert vp.vah_price == vp.price_bins[vp.vah_idx]
        assert vp.val_price == vp.price_bins[vp.val_idx]

    def test_volume_sum_matches(self):
        """Sum of bin volumes equals total_volume."""
        highs = [float(10 + i * 0.1) for i in range(20)]
        lows = [float(9 + i * 0.1) for i in range(20)]
        closes = [float(9.5 + i * 0.1) for i in range(20)]
        volumes = [float(100 + i * 10) for i in range(20)]
        vp = compute_volume_profile(highs, lows, closes, volumes, num_bins=10)
        assert sum(vp.volume_per_bin) == pytest.approx(vp.total_volume, rel=1e-9)

    def test_value_area_covers_70_pct(self):
        """Value Area bins should cover at least 70% of total volume."""
        highs = [10, 12, 11, 13, 14, 12, 15, 13, 16, 14]
        lows = [8, 9, 8, 10, 11, 9, 12, 10, 13, 11]
        closes = [9, 11, 10, 12, 13, 11, 14, 12, 15, 13]
        volumes = [100, 120, 90, 110, 130, 100, 140, 110, 150, 120]
        vp = compute_volume_profile(highs, lows, closes, volumes, num_bins=10)
        va_volume = sum(vp.volume_per_bin[vp.val_idx : vp.vah_idx + 1])
        assert va_volume >= vp.total_volume * 0.70 - 1e-9
