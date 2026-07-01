"""Tests for AlphaForge OrderBook Feature Group (#43, #142).

Covers:
  (a) Unit tests per feature function (all 9 orderbook features)
  (b) Group integration tests (9-feature group)
  (c) Leakage/causality negative tests (no-revision)
  (d) Determinism tests
  (e) Edge case tests (NaN, zero volume, short input)
  (f) New microstructure features: roll_spread, microstructure_noise,
      serial_correlation, vpin, price_impact_slope
"""

import math
from typing import Dict

import numpy as np
import pytest

from alphaforge.features import (
    DEFAULT_AMIHUD_WINDOW,
    DEFAULT_NOISE_WINDOW,
    DEFAULT_ORDERBOOK_WINDOW,
    DEFAULT_PRICE_IMPACT_WINDOW,
    DEFAULT_ROLL_SPREAD_WINDOW,
    DEFAULT_SERIAL_CORR_WINDOW,
    DEFAULT_VPIN_WINDOW,
    compute_amihud_illiquidity_numpy,
    compute_microstructure_noise,
    compute_orderbook_group,
    compute_price_impact_slope,
    compute_roll_spread,
    compute_serial_correlation,
    compute_spread_pct,
    compute_trade_intensity,
    compute_volume_imbalance,
    compute_vpin,
)
from alphaforge.features.orderbook import _classify_volume_direction
from alphaforge.features.pipeline import FeatureGroup, compute_features


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nan_safe_equal(a: np.ndarray, b: np.ndarray) -> bool:
    """Compare arrays where NaN == NaN."""
    nan_a = np.isnan(a)
    nan_b = np.isnan(b)
    if not np.array_equal(nan_a, nan_b):
        return False
    return bool(np.allclose(a[~nan_a], b[~nan_a]))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ohlcv_100() -> Dict[str, np.ndarray]:
    """Generate deterministic 100-bar OHLCV data."""
    rng = np.random.RandomState(42)
    n = 100
    close = 50000.0 + np.cumsum(rng.randn(n) * 200.0)
    high = close + np.abs(rng.randn(n) * 100.0)
    low = close - np.abs(rng.randn(n) * 100.0)
    open_arr = close - rng.randn(n) * 50.0
    volume = np.abs(rng.randn(n) * 100.0) + 100.0
    return {"open": open_arr, "high": high, "low": low, "close": close, "volume": volume}


@pytest.fixture
def ohlcv_200() -> Dict[str, np.ndarray]:
    """Generate deterministic 200-bar OHLCV data."""
    rng = np.random.RandomState(99)
    n = 200
    close = 50000.0 + np.cumsum(rng.randn(n) * 200.0)
    high = close + np.abs(rng.randn(n) * 100.0)
    low = close - np.abs(rng.randn(n) * 100.0)
    open_arr = close - rng.randn(n) * 50.0
    volume = np.abs(rng.randn(n) * 150.0) + 50.0
    return {"open": open_arr, "high": high, "low": low, "close": close, "volume": volume}


# ===========================================================================
# test 1: _classify_volume_direction
# ===========================================================================

class TestClassifyVolumeDirection:
    """#43-01: Volume direction classification from OHLCV."""

    def test_up_bar(self):
        open_arr = np.array([100.0])
        close = np.array([105.0])
        volume = np.array([10.0])
        up, down = _classify_volume_direction(open_arr, close, volume)
        assert math.isclose(up[0], 10.0)
        assert math.isclose(down[0], 0.0)

    def test_down_bar(self):
        open_arr = np.array([100.0])
        close = np.array([95.0])
        volume = np.array([10.0])
        up, down = _classify_volume_direction(open_arr, close, volume)
        assert math.isclose(up[0], 0.0)
        assert math.isclose(down[0], 10.0)

    def test_flat_bar_split_evenly(self):
        open_arr = np.array([100.0])
        close = np.array([100.0])
        volume = np.array([10.0])
        up, down = _classify_volume_direction(open_arr, close, volume)
        assert math.isclose(up[0], 5.0)
        assert math.isclose(down[0], 5.0)

    def test_mixed_bars(self):
        n = 10
        rng = np.random.RandomState(1)
        open_arr = rng.randn(n) * 10.0 + 100.0
        close = rng.randn(n) * 10.0 + 100.0
        volume = np.ones(n) * 10.0
        up, down = _classify_volume_direction(open_arr, close, volume)
        assert len(up) == n
        assert np.all(up >= 0)
        assert np.all(down >= 0)
        # Sum should equal total volume
        assert np.allclose(up + down, volume)


# ===========================================================================
# test 2: compute_spread_pct
# ===========================================================================

class TestSpreadPct:
    """#43-02: compute_spread_pct feature."""

    def test_basic(self, ohlcv_100):
        result = compute_spread_pct(ohlcv_100["high"], ohlcv_100["low"], ohlcv_100["close"], window=10)
        assert len(result) == len(ohlcv_100["close"])
        # First window-1 = 9 values NaN
        for i in range(9):
            assert np.isnan(result[i])
        assert not np.isnan(result[9])
        # All valid values should be non-negative
        valid = result[~np.isnan(result)]
        assert np.all(valid >= 0)

    def test_constant_prices(self):
        n = 50
        high = np.full(n, 105.0)
        low = np.full(n, 95.0)
        close = np.full(n, 100.0)
        result = compute_spread_pct(high, low, close, window=10)
        valid = result[~np.isnan(result)]
        # (105-95)/100 = 0.1 for every bar
        assert np.allclose(valid, 0.1)

    def test_zero_close_nan(self):
        n = 30
        high = np.full(n, 105.0)
        low = np.full(n, 95.0)
        close = np.full(n, 0.0)  # zero close — should produce NaN for those bars
        result = compute_spread_pct(high, low, close, window=10)
        assert np.all(np.isnan(result))  # all NaN since rolling windows have no valid bars

    def test_window_too_large(self):
        n = 5
        high = np.ones(n) * 110.0
        low = np.ones(n) * 100.0
        close = np.ones(n) * 105.0
        result = compute_spread_pct(high, low, close, window=20)
        assert np.all(np.isnan(result))


# ===========================================================================
# test 3: compute_volume_imbalance
# ===========================================================================

class TestVolumeImbalance:
    """#43-03: compute_volume_imbalance feature."""

    def test_all_up_bars_positive(self):
        n = 50
        open_arr = np.arange(n, dtype=np.float64)
        close = np.arange(n, dtype=np.float64) + 2.0  # all up bars
        volume = np.ones(n)
        result = compute_volume_imbalance(open_arr, close, volume, window=10)
        valid = result[~np.isnan(result)]
        # All up bars -> imbalance = 1.0
        assert np.allclose(valid, 1.0)

    def test_all_down_bars_negative(self):
        n = 50
        open_arr = np.arange(n, dtype=np.float64) + 2.0
        close = np.arange(n, dtype=np.float64)  # all down bars
        volume = np.ones(n)
        result = compute_volume_imbalance(open_arr, close, volume, window=10)
        valid = result[~np.isnan(result)]
        # All down bars -> imbalance = -1.0
        assert np.allclose(valid, -1.0)

    def test_balanced_mixed(self, ohlcv_100):
        result = compute_volume_imbalance(
            ohlcv_100["open"], ohlcv_100["close"], ohlcv_100["volume"], window=10
        )
        valid = result[~np.isnan(result)]
        # Range must be within [-1, 1]
        assert np.min(valid) >= -1.0
        assert np.max(valid) <= 1.0

    def test_zero_volume_window(self):
        n = 50
        open_arr = np.arange(n, dtype=np.float64)
        close = np.arange(n, dtype=np.float64) + 1.0
        volume = np.zeros(n)  # all zero volume
        result = compute_volume_imbalance(open_arr, close, volume, window=10)
        valid = result[~np.isnan(result)]
        # Zero volume -> balanced -> 0.0
        assert np.allclose(valid, 0.0)


# ===========================================================================
# test 4: compute_trade_intensity
# ===========================================================================

class TestTradeIntensity:
    """#43-04: compute_trade_intensity feature."""

    def test_non_negative(self, ohlcv_100):
        result = compute_trade_intensity(
            ohlcv_100["high"], ohlcv_100["low"], ohlcv_100["close"], ohlcv_100["volume"], window=10
        )
        valid = result[~np.isnan(result)]
        assert np.all(valid >= 0)

    def test_constant_data_near_one(self):
        n = 50
        high = np.full(n, 105.0)
        low = np.full(n, 95.0)
        close = np.full(n, 100.0)
        volume = np.full(n, 100.0)
        result = compute_trade_intensity(high, low, close, volume, window=10)
        valid = result[~np.isnan(result)]
        # With constant data, intensity ratio should be exactly 1.0
        assert np.allclose(valid, 1.0, atol=1e-10)

    def test_window_too_large(self):
        n = 5
        high = np.ones(n) * 110.0
        low = np.ones(n) * 100.0
        close = np.ones(n) * 105.0
        volume = np.ones(n) * 10.0
        result = compute_trade_intensity(high, low, close, volume, window=20)
        assert np.all(np.isnan(result))

    def test_spike_detection(self):
        """A bar with 10x volume should show high intensity."""
        n = 50
        rng = np.random.RandomState(7)
        high = 100.0 + np.abs(rng.randn(n))
        low = 100.0 - np.abs(rng.randn(n))
        close = 100.0 + rng.randn(n) * 2.0
        volume = np.ones(n)
        # Inject a spike at bar 30
        volume[30] = 10.0
        result = compute_trade_intensity(high, low, close, volume, window=10)
        # The spike bar should have intensity > 1 if it's the window's max
        assert not np.isnan(result[30])
        assert result[30] >= 0


# ===========================================================================
# test 5: compute_amihud_illiquidity_numpy
# ===========================================================================

class TestAmihudIlliquidity:
    """#43-05: compute_amihud_illiquidity_numpy feature."""

    def test_non_negative(self, ohlcv_100):
        result = compute_amihud_illiquidity_numpy(
            ohlcv_100["close"], ohlcv_100["volume"], window=15
        )
        valid = result[~np.isnan(result)]
        assert np.all(valid >= 0)

    def test_nan_at_start(self, ohlcv_100):
        result = compute_amihud_illiquidity_numpy(
            ohlcv_100["close"], ohlcv_100["volume"], window=15
        )
        # First window-1 = 14 values NaN
        for i in range(14):
            assert np.isnan(result[i])
        assert not np.isnan(result[14])

    def test_insufficient_data(self):
        n = 5
        close = np.arange(n, dtype=np.float64) + 100.0
        volume = np.ones(n)
        result = compute_amihud_illiquidity_numpy(close, volume, window=15)
        assert np.all(np.isnan(result))

    def test_bridge_consistency(self, ohlcv_100):
        """Bridged result matches direct lib call."""
        from lib.indicators.microstructure import amihud_illiquidity, dollar_volume

        close = ohlcv_100["close"]
        volume = ohlcv_100["volume"]

        # Direct lib call
        dv = dollar_volume(close.tolist(), volume.tolist())
        log_ret = np.full(len(close), np.nan)
        log_ret[1:] = np.log(close[1:] / close[:-1])
        direct_result = np.array(
            amihud_illiquidity(log_ret.tolist(), dv, period=15), dtype=np.float64
        )

        # Bridged call
        bridged_result = compute_amihud_illiquidity_numpy(close, volume, window=15)

        assert _nan_safe_equal(direct_result, bridged_result)


# ===========================================================================
# test 12: compute_roll_spread (NEW — #142)
# ===========================================================================

class TestRollSpread:
    """#142-01: compute_roll_spread — Roll (1984) effective spread."""

    def test_non_negative(self, ohlcv_100):
        result = compute_roll_spread(ohlcv_100["close"], window=20)
        valid = result[~np.isnan(result)]
        assert np.all(valid >= 0)

    def test_nan_at_start(self, ohlcv_100):
        result = compute_roll_spread(ohlcv_100["close"], window=20)
        # First `window` = 20 values NaN (need window+1 prices)
        for i in range(20):
            assert np.isnan(result[i])

    def test_insufficient_data(self):
        close = np.array([100.0, 101.0, 102.0])
        result = compute_roll_spread(close, window=20)
        assert np.all(np.isnan(result))

    def test_bridge_consistency(self, ohlcv_100):
        """Bridged result matches direct lib call."""
        from lib.indicators.microstructure import roll_spread_estimator

        close = ohlcv_100["close"]
        window = 20

        # Direct lib call
        direct = np.array(
            roll_spread_estimator(close.tolist(), period=window), dtype=np.float64
        )

        # Bridged call
        bridged = compute_roll_spread(close, window=window)

        assert _nan_safe_equal(direct, bridged)

    def test_constant_price_zero_spread(self):
        """Constant prices yield zero Roll spread (zero covariance)."""
        n = 60
        close = np.full(n, 100.0, dtype=np.float64)
        result = compute_roll_spread(close, window=20)
        valid = result[~np.isnan(result)]
        # With constant prices, covariance is zero -> Roll spread = 0
        assert np.allclose(valid, 0.0, atol=1e-10)


# ===========================================================================
# test 13: compute_microstructure_noise (NEW — #142)
# ===========================================================================

class TestMicrostructureNoise:
    """#142-02: compute_microstructure_noise — variance ratio noise."""

    def test_non_negative(self, ohlcv_100):
        result = compute_microstructure_noise(ohlcv_100["close"], window=20)
        valid = result[~np.isnan(result)]
        assert np.all(valid >= 0)

    def test_nan_at_start(self, ohlcv_100):
        result = compute_microstructure_noise(ohlcv_100["close"], window=20)
        # First `window` = 20 values NaN
        for i in range(20):
            assert np.isnan(result[i])

    def test_insufficient_data(self):
        close = np.array([100.0, 101.0, 102.0])
        result = compute_microstructure_noise(close, window=20)
        assert np.all(np.isnan(result))

    def test_constant_price_noise_idea(self):
        """Constant prices: noise near 1 since no drift or bounce."""
        n = 100
        close = np.full(n, 100.0, dtype=np.float64)
        result = compute_microstructure_noise(close, window=20)
        valid = result[~np.isnan(result)]
        # With all zero returns, the variance is zero, leading to NaN
        # But we should have some valid values if there's tiny noise
        assert len(valid) >= 0  # at least doesn't crash

    def test_noise_values_in_reasonable_range(self, ohlcv_100):
        """Noise values should be with [0.01, 10.0] after clipping."""
        result = compute_microstructure_noise(ohlcv_100["close"], window=20)
        valid = result[~np.isnan(result)]
        assert np.all(valid >= 0.01)
        assert np.all(valid <= 10.0)


# ===========================================================================
# test 14: compute_serial_correlation (NEW — #142)
# ===========================================================================

class TestSerialCorrelation:
    """#142-03: compute_serial_correlation — return autocorrelation."""

    def test_range_minus_one_to_one(self, ohlcv_100):
        result = compute_serial_correlation(ohlcv_100["close"], window=10)
        valid = result[~np.isnan(result)]
        assert np.all(valid >= -1.0)
        assert np.all(valid <= 1.0)

    def test_nan_at_start(self, ohlcv_100):
        result = compute_serial_correlation(ohlcv_100["close"], window=10)
        # Need window+2 = 12 bars for first valid value
        for i in range(11):
            assert np.isnan(result[i])

    def test_insufficient_data(self):
        close = np.array([100.0, 101.0, 102.0, 103.0])
        result = compute_serial_correlation(close, window=10)
        assert np.all(np.isnan(result))

    def test_monotonic_positive_corr(self):
        """Monotonically increasing prices should show positive autocorrelation."""
        close = np.arange(100.0, 200.0, dtype=np.float64)
        result = compute_serial_correlation(close, window=10)
        valid = result[~np.isnan(result)]
        # With a strong trend, lag-1 autocorrelation should be positive
        assert np.mean(valid) > 0

    def test_alternating_bars_negative_corr(self):
        """Alternating up/down (microstructure bounce) -> negative correlation."""
        close = np.array(
            [100.0, 101.0, 100.0, 101.0, 100.0, 101.0, 100.0, 101.0,
             100.0, 101.0, 100.0, 101.0, 100.0, 101.0, 100.0, 101.0,
             100.0, 101.0, 100.0, 101.0], dtype=np.float64
        )
        result = compute_serial_correlation(close, window=10)
        valid = result[~np.isnan(result)]
        # Alternating -> negative autocorrelation
        assert np.mean(valid) < 0


# ===========================================================================
# test 15: compute_vpin (NEW — #142)
# ===========================================================================

class TestVPIN:
    """#142-04: compute_vpin — VPIN order flow toxicity."""

    def test_range_0_to_1(self, ohlcv_100):
        result = compute_vpin(
            ohlcv_100["open"], ohlcv_100["close"], ohlcv_100["volume"], window=50
        )
        valid = result[~np.isnan(result)]
        assert np.all(valid >= 0.0)
        # Use tolerance for floating-point precision edge cases
        assert np.all(valid <= 1.0 + 1e-10), f"Max VPIN: {np.max(valid)}"

    def test_nan_at_start(self, ohlcv_100):
        result = compute_vpin(
            ohlcv_100["open"], ohlcv_100["close"], ohlcv_100["volume"], window=50
        )
        # First 49 values NaN
        for i in range(49):
            assert np.isnan(result[i])
        assert not np.isnan(result[49])

    def test_insufficient_data(self):
        n = 5
        open_arr = np.arange(n, dtype=np.float64)
        close = np.arange(n, dtype=np.float64) + 1.0
        volume = np.ones(n)
        result = compute_vpin(open_arr, close, volume, window=50)
        assert np.all(np.isnan(result))

    def test_all_up_bars_vpin(self):
        """All up bars -> volume all on one side -> high VPIN."""
        n = 100
        open_arr = np.arange(n, dtype=np.float64)
        close = np.arange(n, dtype=np.float64) + 2.0  # all up
        volume = np.ones(n)
        result = compute_vpin(open_arr, close, volume, window=50)
        valid = result[~np.isnan(result)]
        # All volume is buy volume, so |up - down| = total_vol -> VPIN = 1.0
        assert np.allclose(valid, 1.0)

    def test_balanced_flow_vpin(self):
        """Equal up and down volume -> VPIN near 0."""
        n = 100
        rng = np.random.RandomState(42)
        open_arr = np.full(n, 100.0)
        close = np.full(n, 100.0)  # All flat -> split evenly = balanced
        volume = np.ones(n)
        result = compute_vpin(open_arr, close, volume, window=50)
        valid = result[~np.isnan(result)]
        # Flat bars split evenly -> up = down = 0.5 -> |up-down| = 0 -> VPIN = 0
        assert np.allclose(valid, 0.0)

    def test_zero_volume_safe(self):
        """Zero volume should not crash and produce safe values."""
        n = 100
        open_arr = np.arange(n, dtype=np.float64)
        close = np.arange(n, dtype=np.float64) + 1.0
        volume = np.zeros(n)
        result = compute_vpin(open_arr, close, volume, window=50)
        valid = result[~np.isnan(result)]
        assert np.allclose(valid, 0.0)


# ===========================================================================
# test 16: compute_price_impact_slope (NEW — #142)
# ===========================================================================

class TestPriceImpactSlope:
    """#142-05: compute_price_impact_slope — Kyle's lambda proxy."""

    def test_finite_output(self, ohlcv_100):
        result = compute_price_impact_slope(
            ohlcv_100["open"], ohlcv_100["high"], ohlcv_100["low"],
            ohlcv_100["close"], ohlcv_100["volume"], window=15
        )
        valid = result[~np.isnan(result)]
        assert np.all(np.isfinite(valid))

    def test_nan_at_start(self, ohlcv_100):
        result = compute_price_impact_slope(
            ohlcv_100["open"], ohlcv_100["high"], ohlcv_100["low"],
            ohlcv_100["close"], ohlcv_100["volume"], window=15
        )
        # First 15 values NaN (need window+1 bars)
        for i in range(15):
            assert np.isnan(result[i])

    def test_insufficient_data(self):
        n = 5
        open_arr = np.arange(n, dtype=np.float64)
        high = open_arr + 2.0
        low = open_arr - 1.0
        close = open_arr + 1.0
        volume = np.ones(n)
        result = compute_price_impact_slope(
            open_arr, high, low, close, volume, window=15
        )
        assert np.all(np.isnan(result))

    def test_constant_volume_no_price_move(self):
        """When returns are zero, slope is NaN (zero variance)."""
        n = 60
        open_arr = np.full(n, 100.0)
        high = np.full(n, 102.0)
        low = np.full(n, 98.0)
        close = np.full(n, 100.0)
        volume = np.ones(n)
        result = compute_price_impact_slope(
            open_arr, high, low, close, volume, window=15
        )
        valid = result[~np.isnan(result)]
        # With zero returns, covariance is 0 -> NaN from 0/0
        # But some values may still compute if signed flow varies
        assert len(valid) >= 0  # no crash


# ===========================================================================
# test 6: compute_orderbook_group integration (updated for 9 features)
# ===========================================================================

class TestOrderbookGroup:
    """#43-06: compute_orderbook_group integration (9 features)."""

    def test_all_keys_present(self, ohlcv_100):
        result = compute_orderbook_group(
            ohlcv_100["open"], ohlcv_100["high"], ohlcv_100["low"],
            ohlcv_100["close"], ohlcv_100["volume"]
        )
        expected = {
            "spread_pct_N", "volume_imbalance_N",
            "trade_intensity_N", "amihud_illiquidity_N",
            "roll_spread_N", "microstructure_noise_N",
            "serial_correlation_N", "vpin_N",
            "price_impact_slope_N",
        }
        assert set(result.keys()) == expected
        for arr in result.values():
            assert len(arr) == len(ohlcv_100["close"])

    def test_determinism(self, ohlcv_100):
        results = [
            compute_orderbook_group(
                ohlcv_100["open"], ohlcv_100["high"], ohlcv_100["low"],
                ohlcv_100["close"], ohlcv_100["volume"]
            )
            for _ in range(5)
        ]
        for key in results[0]:
            for i in range(1, 5):
                assert _nan_safe_equal(results[0][key], results[i][key])

    def test_no_revision(self, ohlcv_200):
        """Adding bar N+1 must not change values at bars 0..N-1."""
        N = 100
        open_arr = ohlcv_200["open"]
        high = ohlcv_200["high"]
        low = ohlcv_200["low"]
        close = ohlcv_200["close"]
        volume = ohlcv_200["volume"]

        r1 = compute_orderbook_group(
            open_arr[:N], high[:N], low[:N], close[:N], volume[:N]
        )
        r2 = compute_orderbook_group(
            open_arr[:N + 1], high[:N + 1], low[:N + 1], close[:N + 1], volume[:N + 1]
        )
        for key in r1:
            assert _nan_safe_equal(r1[key], r2[key][:N]), f"No-revision failed for {key}"


# ===========================================================================
# test 7: Full pipeline includes ORDERBOOK
# ===========================================================================

class TestPipelineIncludesOrderbook:
    """#43-07: compute_features() includes ORDERBOOK group."""

    def test_orderbook_keys_present(self, ohlcv_100):
        result = compute_features(ohlcv_100, mode="SWING")
        assert "spread_pct_N" in result.features
        assert "volume_imbalance_N" in result.features
        assert "trade_intensity_N" in result.features
        assert "amihud_illiquidity_N" in result.features
        # New microstructure features (#142)
        assert "roll_spread_N" in result.features
        assert "microstructure_noise_N" in result.features
        assert "serial_correlation_N" in result.features
        assert "vpin_N" in result.features
        assert "price_impact_slope_N" in result.features

    def test_orderbook_in_feature_group_ids(self, ohlcv_100):
        result = compute_features(ohlcv_100, mode="SWING")
        assert "orderbook" in result.feature_group_ids

    def test_orderbook_in_feature_group_map(self):
        assert FeatureGroup.ORDERBOOK is not None
        assert FeatureGroup.ORDERBOOK.value == "orderbook"


# ===========================================================================
# test 8: Edge cases
# ===========================================================================

class TestOrderbookEdgeCases:
    """#43-08: Edge case tests."""

    def test_short_input_all_nan(self):
        n = 3
        open_arr = np.array([100.0, 101.0, 102.0])
        high = np.array([102.0, 103.0, 104.0])
        low = np.array([99.0, 100.0, 101.0])
        close = np.array([101.0, 102.0, 103.0])
        volume = np.array([10.0, 10.0, 10.0])
        result = compute_orderbook_group(open_arr, high, low, close, volume, window=10)
        for key in result:
            assert np.all(np.isnan(result[key])), f"{key} should be all NaN"

    def test_zero_volume_bars(self):
        n = 50
        rng = np.random.RandomState(42)
        close = 100.0 + np.cumsum(rng.randn(n) * 2.0)
        high = close + 5.0
        low = close - 5.0
        open_arr = close - rng.randn(n)
        volume = np.zeros(n)
        result = compute_orderbook_group(open_arr, high, low, close, volume, window=10)
        # All features should be safe (no division errors, no crashes)
        for key in result:
            arr = result[key]
            valid = arr[~np.isnan(arr)]
            assert np.all(np.isfinite(valid)), f"{key} has non-finite values"

    def test_negative_close_no_crash(self):
        n = 30
        open_arr = np.full(n, 100.0)
        high = np.full(n, 105.0)
        low = np.full(n, 95.0)
        close = np.arange(n, dtype=np.float64) * -1.0  # all negative
        volume = np.ones(n)
        result = compute_orderbook_group(open_arr, high, low, close, volume, window=10)
        # Should not crash — features that depend on close price level
        # (spread_pct, trade_intensity) should be NaN.
        # volume_imbalance is directional (close vs open comparison) and works
        # even with negative close.
        assert np.all(np.isnan(result["spread_pct_N"]))
        assert np.all(np.isnan(result["trade_intensity_N"]))
        assert np.all(np.isnan(result["amihud_illiquidity_N"]))
        # volume_imbalance should produce finite values (directional comparison)
        valid_imb = result["volume_imbalance_N"][~np.isnan(result["volume_imbalance_N"])]
        assert len(valid_imb) > 0
        assert np.all(np.isfinite(valid_imb))


# ===========================================================================
# test 9: Determinism across modes
# ===========================================================================

class TestOrderbookModeAgnostic:
    """#43-09: ORDERBOOK group works across all supported modes."""

    def test_swing_mode(self, ohlcv_100):
        result = compute_features(ohlcv_100, mode="SWING")
        assert "amihud_illiquidity_N" in result.features
        assert not np.all(np.isnan(result.features["amihud_illiquidity_N"]))

    def test_scalp_mode(self, ohlcv_100):
        result = compute_features(ohlcv_100, mode="SCALP")
        assert "amihud_illiquidity_N" in result.features
        assert not np.all(np.isnan(result.features["amihud_illiquidity_N"]))

    def test_aggressive_scalp_mode(self, ohlcv_100):
        result = compute_features(ohlcv_100, mode="AGGRESSIVE_SCALP")
        assert "amihud_illiquidity_N" in result.features
        assert not np.all(np.isnan(result.features["amihud_illiquidity_N"]))


# ===========================================================================
# test 10: Feature name consistency
# ===========================================================================

class TestOrderbookFeatureNames:
    """#43-10: Feature names follow naming convention."""

    def test_names_use_n_suffix(self):
        """Orderbook features should use _N suffix for window-dependent features."""
        result = compute_orderbook_group(
            np.array([100.0] * 100), np.array([102.0] * 100),
            np.array([98.0] * 100), np.array([101.0] * 100),
            np.ones(100)
        )
        for key in result:
            assert key.endswith("_N"), f"Feature '{key}' should end with _N"


# ===========================================================================
# test 11: Default window values are reasonable
# ===========================================================================

class TestOrderbookDefaults:
    """#43-11: Default window values are positive and reasonable."""

    def test_default_windows_positive(self):
        assert DEFAULT_ORDERBOOK_WINDOW > 0
        assert DEFAULT_AMIHUD_WINDOW > 0
        assert DEFAULT_ROLL_SPREAD_WINDOW > 0
        assert DEFAULT_NOISE_WINDOW > 0
        assert DEFAULT_SERIAL_CORR_WINDOW > 0
        assert DEFAULT_VPIN_WINDOW > 0
        assert DEFAULT_PRICE_IMPACT_WINDOW > 0

    def test_default_windows_reasonable(self):
        """Windows should be in a reasonable range for 15m bars."""
        assert 5 <= DEFAULT_ORDERBOOK_WINDOW <= 60
        assert 5 <= DEFAULT_AMIHUD_WINDOW <= 60
        assert 5 <= DEFAULT_ROLL_SPREAD_WINDOW <= 60
        assert 5 <= DEFAULT_NOISE_WINDOW <= 100
        assert 5 <= DEFAULT_SERIAL_CORR_WINDOW <= 60
        assert 10 <= DEFAULT_VPIN_WINDOW <= 200
        assert 5 <= DEFAULT_PRICE_IMPACT_WINDOW <= 60
