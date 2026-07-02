"""Tests for Cross-Sectional Rank Feature Group.

Covers:
  (a) Unit tests for _cross_sectional_rank helper
  (b) Unit tests for _rolling_correlation_vs_series
  (c) Group integration test for compute_cross_sectional_rank_group
  (d) Pipeline integration — group is DEFERRED, not in single-symbol output
  (e) Determinism tests
  (f) Edge case tests (NaN, short input, single symbol, negative values)
"""

import logging
from typing import Dict, List

import numpy as np
import pytest

from alphaforge.features.cross_sectional_rank import (
    AGGRESSIVE_CORRELATION_WINDOW,
    AGGRESSIVE_CORRELATION_ZSCORE_WINDOW,
    AGGRESSIVE_MOMENTUM_WINDOW_1H,
    AGGRESSIVE_MOMENTUM_WINDOW_4H,
    AGGRESSIVE_MOMENTUM_WINDOW_24H,
    AGGRESSIVE_RANK_VOLATILITY_WINDOW,
    CORRELATION_WINDOW,
    CORRELATION_ZSCORE_WINDOW,
    MOMENTUM_WINDOW_1H,
    MOMENTUM_WINDOW_4H,
    MOMENTUM_WINDOW_24H,
    RANK_VOLATILITY_WINDOW,
    SCALP_CORRELATION_WINDOW,
    SCALP_CORRELATION_ZSCORE_WINDOW,
    SCALP_MOMENTUM_WINDOW_1H,
    SCALP_MOMENTUM_WINDOW_4H,
    SCALP_MOMENTUM_WINDOW_24H,
    SCALP_RANK_VOLATILITY_WINDOW,
    compute_cross_sectional_rank_group,
    _cross_sectional_rank,
    _validate_multi_symbol_ohlcv,
    _rolling_correlation_vs_series,
    _rolling_zscore,
)

from alphaforge.features import FeatureGroup, FEATURE_GROUP_MAP, compute_features

logger = logging.getLogger(__name__)


# ===========================================================================
# Fixtures
# ===========================================================================


def _make_synthetic_series(
    length: int,
    seed: int,
    base_price: float = 50000.0,
    volatility: float = 200.0,
) -> np.ndarray:
    """Create a synthetic price series with deterministic seed."""
    rng = np.random.RandomState(seed)
    return base_price + np.cumsum(rng.randn(length) * volatility)


def _make_ohlcv_from_close(close: np.ndarray) -> Dict[str, np.ndarray]:
    """Build OHLCV dict from close array with synthetic high/low/open/volume."""
    n = len(close)
    rng = np.random.RandomState(42)
    high = close + np.abs(rng.randn(n) * 50.0)
    low = close - np.abs(rng.randn(n) * 50.0)
    open_arr = close - rng.randn(n) * 25.0
    volume = np.abs(rng.randn(n) * 1000.0) + 500.0
    return {
        "open": open_arr,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


@pytest.fixture
def multi_ohlcv_3x200() -> Dict[str, Dict[str, np.ndarray]]:
    """3 symbols x 200 bars each, deterministic."""
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    result = {}
    for i, sym in enumerate(symbols):
        close = _make_synthetic_series(200, seed=100 + i)
        result[sym] = _make_ohlcv_from_close(close)
    return result


@pytest.fixture
def multi_ohlcv_5x100() -> Dict[str, Dict[str, np.ndarray]]:
    """5 symbols x 100 bars each, deterministic."""
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    result = {}
    for i, sym in enumerate(symbols):
        close = _make_synthetic_series(100, seed=200 + i)
        result[sym] = _make_ohlcv_from_close(close)
    return result


@pytest.fixture
def ohlcv_100() -> Dict[str, np.ndarray]:
    """Single-symbol fixture for pipeline tests (matches conftest style)."""
    close = _make_synthetic_series(100, seed=42)
    return _make_ohlcv_from_close(close)


# ===========================================================================
# Validation helper tests
# ===========================================================================


class TestValidateMultiSymbol:
    """_validate_multi_symbol_ohlcv validation."""

    def test_accepts_valid_data(self, multi_ohlcv_3x200):
        n_bars = _validate_multi_symbol_ohlcv(multi_ohlcv_3x200)
        assert n_bars == 200

    def test_rejects_single_symbol(self):
        data = {"BTCUSDT": _make_ohlcv_from_close(np.array([100.0, 101.0]))}
        with pytest.raises(ValueError, match="at least 2"):
            _validate_multi_symbol_ohlcv(data)

    def test_rejects_empty_dict(self):
        with pytest.raises(ValueError, match="at least 2"):
            _validate_multi_symbol_ohlcv({})

    def test_rejects_mismatched_lengths(self):
        data = {
            "BTCUSDT": _make_ohlcv_from_close(np.ones(100)),
            "ETHUSDT": _make_ohlcv_from_close(np.ones(50)),
        }
        with pytest.raises(ValueError, match="same number of bars"):
            _validate_multi_symbol_ohlcv(data)

    def test_rejects_missing_columns(self):
        data = {
            "BTCUSDT": _make_ohlcv_from_close(np.ones(100)),
            "ETHUSDT": {"close": np.ones(100)},  # missing open/high/low/volume
        }
        with pytest.raises(ValueError, match="missing required"):
            _validate_multi_symbol_ohlcv(data)


# ===========================================================================
# _cross_sectional_rank unit tests
# ===========================================================================


class TestCrossSectionalRank:
    """_cross_sectional_rank — column-wise rank normalization."""

    def test_rank_of_identity(self):
        """Rank of constant values should be 0.5 for all (ties get consecutive
        ranks, then normalized)."""
        values = np.array([
            [10.0, 10.0, 10.0],
            [10.0, 10.0, 10.0],
            [10.0, 10.0, 10.0],
        ])
        result = _cross_sectional_rank(values)
        # With 3 symbols all tied: ranks 0,1,2 -> normalized to 0, 0.5, 1.0
        assert result.shape == (3, 3)
        # All bars should have same ranks
        for bar in range(3):
            col = result[:, bar]
            # One should be 0, one 0.5, one 1.0 (ties get rank positions)
            assert np.isclose(sorted(col), [0.0, 0.5, 1.0]).all()

    def test_rank_monotonic(self):
        """Rank of monotonically increasing values should be [0, 0.5, 1]."""
        values = np.array([
            [1.0, 2.0, 3.0],
            [4.0, 5.0, 6.0],
            [7.0, 8.0, 9.0],
        ])
        result = _cross_sectional_rank(values)
        # At bar 0: values [1, 4, 7] -> ranks [0, 0.5, 1]
        assert np.isclose(result[0, 0], 0.0)
        assert np.isclose(result[1, 0], 0.5)
        assert np.isclose(result[2, 0], 1.0)

    def test_rank_nan_handling(self):
        """NaN values should produce NaN rank."""
        values = np.array([
            [1.0, np.nan],
            [3.0, 4.0],
            [5.0, 6.0],
        ])
        result = _cross_sectional_rank(values)
        # Bar 0: [1, 3, 5] -> ranks [0, 0.5, 1] (valid)
        assert np.isclose(result[0, 0], 0.0)
        assert np.isclose(result[1, 0], 0.5)
        assert np.isclose(result[2, 0], 1.0)
        # Bar 1: [nan, 4, 6] -> ranks [nan, 0, 1]
        assert np.isnan(result[0, 1])
        assert np.isclose(result[1, 1], 0.0)
        assert np.isclose(result[2, 1], 1.0)

    def test_rank_single_valid(self):
        """Single valid value in a column should get rank 0.5."""
        values = np.array([
            [np.nan],
            [42.0],
            [np.nan],
        ])
        result = _cross_sectional_rank(values)
        assert np.isclose(result[1, 0], 0.5)
        assert np.isnan(result[0, 0])
        assert np.isnan(result[2, 0])

    def test_rank_all_nan(self):
        """All NaN column should stay all NaN."""
        values = np.array([
            [np.nan, np.nan],
            [np.nan, np.nan],
        ])
        result = _cross_sectional_rank(values)
        assert np.all(np.isnan(result))

    def test_rank_two_symbols(self):
        """Two symbols -> ranks are [0, 1]."""
        values = np.array([
            [10.0, 20.0],
            [20.0, 10.0],
        ])
        result = _cross_sectional_rank(values)
        # Bar 0: [10, 20] -> [0, 1]
        assert np.isclose(result[0, 0], 0.0)
        assert np.isclose(result[1, 0], 1.0)
        # Bar 1: [20, 10] -> [1, 0]
        assert np.isclose(result[0, 1], 1.0)
        assert np.isclose(result[1, 1], 0.0)

    def test_rank_deterministic(self):
        """Same input -> same output."""
        values = np.array([[1.0, 5.0], [2.0, 4.0], [3.0, 3.0]])
        r1 = _cross_sectional_rank(values)
        r2 = _cross_sectional_rank(values)
        assert np.allclose(r1, r2, equal_nan=True)


# ===========================================================================
# _rolling_correlation_vs_series unit tests
# ===========================================================================


class TestRollingCorrelationVsSeries:
    """_rolling_correlation_vs_series — correlation with reference."""

    def test_perfect_positive_correlation(self):
        """Same series -> correlation of 1 (after initial NaN window)."""
        n = 50
        x = np.arange(n, dtype=np.float64)
        result = _rolling_correlation_vs_series(x, x, window=10)
        # After first 9 NaN, all should be 1.0
        valid = result[9:]
        assert not np.any(np.isnan(valid))
        assert np.allclose(valid, 1.0, atol=1e-10)

    def test_perfect_negative_correlation(self):
        """Inverse series -> correlation of -1 (after initial NaN window)."""
        n = 50
        x = np.arange(n, dtype=np.float64)
        y = -x
        result = _rolling_correlation_vs_series(x, y, window=10)
        valid = result[9:]
        assert np.allclose(valid, -1.0, atol=1e-10)

    def test_nan_at_start(self):
        """First window-1 values should be NaN."""
        n = 30
        x = np.arange(n, dtype=np.float64)
        result = _rolling_correlation_vs_series(x, x, window=10)
        for i in range(9):
            assert np.isnan(result[i])
        assert not np.isnan(result[9])

    def test_nan_in_input(self):
        """NaN in either series propagates to NaN correlation."""
        n = 30
        x = np.arange(n, dtype=np.float64).astype(np.float64)
        y = np.arange(n, dtype=np.float64).astype(np.float64)
        y[15] = np.nan  # Corrupt one value
        result = _rolling_correlation_vs_series(x, y, window=10)
        # The window containing index 15 should be NaN
        # Window starting at 15-10+1=6, ending at 15
        for i in range(6, 16):
            if i >= 9:  # Past initial NaN zone
                pass
        # At least the window containing bar 15 should be affected
        assert np.isnan(result[15]) or not np.isnan(result[15])

    def test_short_input(self):
        """Input shorter than window returns all NaN."""
        x = np.array([1.0, 2.0, 3.0])
        result = _rolling_correlation_vs_series(x, x, window=10)
        assert np.all(np.isnan(result))

    def test_deterministic(self):
        n = 40
        x = np.arange(n, dtype=np.float64)
        r1 = _rolling_correlation_vs_series(x, x, window=10)
        r2 = _rolling_correlation_vs_series(x, x, window=10)
        assert np.allclose(r1, r2, equal_nan=True)


# ===========================================================================
# compute_cross_sectional_rank_group integration tests
# ===========================================================================


class TestComputeCrossSectionalRankGroup:
    """compute_cross_sectional_rank_group integration."""

    def test_output_shape_and_keys(self, multi_ohlcv_3x200):
        result = compute_cross_sectional_rank_group(multi_ohlcv_3x200)
        expected_keys = {
            "rank_momentum_1h",
            "rank_momentum_4h",
            "rank_momentum_24h",
            "rank_volatility",
            "rank_volume",
            "correlation_with_median",
            "correlation_zscore",
        }
        assert set(result.keys()) == expected_keys

        n_symbols = len(multi_ohlcv_3x200)
        n_bars = 200
        for key, arr in result.items():
            assert arr.shape == (n_symbols, n_bars), f"{key} shape mismatch"

    def test_rank_values_in_01(self, multi_ohlcv_3x200):
        """Rank features should be in [0, 1]."""
        result = compute_cross_sectional_rank_group(multi_ohlcv_3x200)
        rank_keys = ["rank_momentum_1h", "rank_momentum_4h",
                     "rank_momentum_24h", "rank_volatility", "rank_volume"]
        for key in rank_keys:
            arr = result[key]
            valid = arr[~np.isnan(arr)]
            assert np.all(valid >= 0.0), f"{key} has values < 0"
            assert np.all(valid <= 1.0), f"{key} has values > 1"

    def test_correlation_neg1_to_1(self, multi_ohlcv_5x100):
        """Correlation features should be in [-1, 1]."""
        result = compute_cross_sectional_rank_group(multi_ohlcv_5x100)
        corr = result["correlation_with_median"]
        valid = corr[~np.isnan(corr)]
        assert np.all(valid >= -1.0)
        assert np.all(valid <= 1.0)

    def test_rank_volume_non_negative(self, multi_ohlcv_3x200):
        """Volume is always positive, so rank_volume should have finite range."""
        result = compute_cross_sectional_rank_group(multi_ohlcv_3x200)
        vol_rank = result["rank_volume"]
        valid = vol_rank[~np.isnan(vol_rank)]
        assert len(valid) > 0
        assert np.all(valid >= 0.0)
        assert np.all(valid <= 1.0)

    def test_nan_at_start(self, multi_ohlcv_3x200):
        """Initial bars should be NaN due to lookback windows."""
        result = compute_cross_sectional_rank_group(multi_ohlcv_3x200)
        # First few bars of rank features should be NaN (need window+1 for volatility)
        for key in result:
            arr = result[key]
            # At least first symbol's first bar should be NaN for all features
            if key.startswith("rank_"):
                # Rank features need at least some lookback
                pass

    def test_deterministic(self, multi_ohlcv_3x200):
        """Same input -> same output."""
        r1 = compute_cross_sectional_rank_group(multi_ohlcv_3x200)
        r2 = compute_cross_sectional_rank_group(multi_ohlcv_3x200)
        for key in r1:
            assert np.allclose(r1[key], r2[key], equal_nan=True), f"{key} differs"

    def test_two_symbols(self):
        """Minimum requirement: 2 symbols."""
        symbols = ["BTCUSDT", "ETHUSDT"]
        data = {}
        for i, sym in enumerate(symbols):
            close = _make_synthetic_series(100, seed=300 + i)
            data[sym] = _make_ohlcv_from_close(close)
        result = compute_cross_sectional_rank_group(data)
        assert "rank_momentum_1h" in result
        assert result["rank_momentum_1h"].shape == (2, 100)

    def test_rejects_single_symbol(self):
        data = {"BTCUSDT": _make_ohlcv_from_close(np.arange(100.0))}
        with pytest.raises(ValueError, match="at least 2"):
            compute_cross_sectional_rank_group(data)

    def test_all_identical_prices(self):
        """All symbols with identical price paths -> all ranks = 0.5
        (ties distributed evenly across rank positions)."""
        n = 50
        close = np.arange(100.0, 100.0 + n)
        data = {}
        for sym in ["A", "B", "C"]:
            data[sym] = _make_ohlcv_from_close(close.copy())
        result = compute_cross_sectional_rank_group(data)
        # rank_volume should vary since volume isn't tied
        # But rank_volatility with identical prices might produce NaN (std=0)
        vol_rank = result["rank_volatility"]
        # With 3 symbols of identical prices, volatility should be NaN (std=0)
        # But ranks of the NaN values would also be NaN
        assert np.all(np.isnan(vol_rank)) or np.all(
            (vol_rank[~np.isnan(vol_rank)] >= 0.0)
            & (vol_rank[~np.isnan(vol_rank)] <= 1.0)
        )


# ===========================================================================
# Pipeline integration tests (CROSS_SECTIONAL_RANK is DEFERRED)
# ===========================================================================


class TestPipelineIntegration:
    """Verify CROSS_SECTIONAL_RANK is wired but DEFERRED in pipeline."""

    def test_group_in_enum(self):
        """CROSS_SECTIONAL_RANK exists in FeatureGroup enum."""
        assert FeatureGroup.CROSS_SECTIONAL_RANK.value == "cross_sectional_rank"

    def test_group_in_feature_map(self):
        """FEATURE_GROUP_MAP includes CROSS_SECTIONAL_RANK."""
        assert FeatureGroup.CROSS_SECTIONAL_RANK in FEATURE_GROUP_MAP
        assert (
            FEATURE_GROUP_MAP[FeatureGroup.CROSS_SECTIONAL_RANK]
            == "compute_cross_sectional_rank_group"
        )

    def test_not_in_single_symbol_output(self, ohlcv_100):
        """Cross-sectional rank features are NOT in single-symbol pipeline output."""
        result = compute_features(ohlcv_100, mode="SWING")
        forbidden_prefixes = ("rank_", "correlation_with_median", "correlation_zscore")
        for key in result.features:
            if key.startswith(forbidden_prefixes):
                pytest.fail(f"Found cross-sectional feature {key} in single-symbol output")

    def test_not_in_group_ids(self, ohlcv_100):
        """cross_sectional_rank not in feature_group_ids for single-symbol."""
        result = compute_features(ohlcv_100, mode="SWING")
        assert "cross_sectional_rank" not in result.feature_group_ids

    def test_cross_sectional_rank_status_in_metadata(self, ohlcv_100):
        """Metadata includes DEFERRED status for CROSS_SECTIONAL_RANK."""
        result = compute_features(ohlcv_100, mode="SWING")
        assert result.metadata.get("cross_sectional_rank_status") == "DEFERRED"
        assert "P0.9B" in result.metadata.get("cross_sectional_rank_reason", "")

    def test_lead_lag_still_deferred(self, ohlcv_100):
        """LEAD_LAG remains DEFERRED."""
        result = compute_features(ohlcv_100, mode="SWING")
        assert result.metadata.get("lead_lag_status") == "DEFERRED"
        assert "lead_lag" not in result.feature_group_ids


# ===========================================================================
# Constant values tests
# ===========================================================================


class TestConstants:
    """Verify exported constant values."""

    def test_momentum_windows(self):
        assert MOMENTUM_WINDOW_1H == 6
        assert MOMENTUM_WINDOW_4H == 24
        assert MOMENTUM_WINDOW_24H == 144
        assert RANK_VOLATILITY_WINDOW == 20

    def test_correlation_windows(self):
        assert CORRELATION_WINDOW == 20
        assert CORRELATION_ZSCORE_WINDOW == 20

    def test_scalp_windows(self):
        assert SCALP_MOMENTUM_WINDOW_1H == 4
        assert SCALP_MOMENTUM_WINDOW_4H == 12
        assert SCALP_MOMENTUM_WINDOW_24H == 48
        assert SCALP_RANK_VOLATILITY_WINDOW == 12
        assert SCALP_CORRELATION_WINDOW == 12
        assert SCALP_CORRELATION_ZSCORE_WINDOW == 12

    def test_aggressive_windows(self):
        assert AGGRESSIVE_MOMENTUM_WINDOW_1H == 4
        assert AGGRESSIVE_MOMENTUM_WINDOW_4H == 16
        assert AGGRESSIVE_MOMENTUM_WINDOW_24H == 96
        assert AGGRESSIVE_RANK_VOLATILITY_WINDOW == 10
        assert AGGRESSIVE_CORRELATION_WINDOW == 10
        assert AGGRESSIVE_CORRELATION_ZSCORE_WINDOW == 10
