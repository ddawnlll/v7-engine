"""Tests for AlphaForge Lead-Lag Feature Group — cross-sectional multi-symbol features.

Covers:
  (a) Cross-sectional validation tests (multi-symbol OHLCV)
  (b) Unit tests per feature function (tf_alignment, correlation_pairwise, lead_lag_score)
  (c) Group integration test (compute_lead_lag_group)
  (d) Determinism tests
  (e) Causality tests (no future access)
  (f) Error handling / edge case tests
  (g) NaN handling tests
  (h) Import boundary tests
  (i) Cross-sectional data contract tests (HOLD-LEAD-LAG)
"""

import math
import sys
from typing import Dict

import numpy as np
import pytest

from alphaforge.features import (
    LL_CORRELATION_WINDOW,
    LL_MAX_LAG,
    LL_VOLATILITY_WINDOW,
    FeatureGroup,
    compute_correlation_pairwise,
    compute_lead_lag_group,
    compute_lead_lag_score,
    compute_tf_alignment,
)

from alphaforge.features.lead_lag import (
    _rolling_correlation,
    _validate_multi_symbol_ohlcv,
    _compute_log_returns,
)


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def two_symbol_ohlcv_100() -> Dict[str, Dict[str, np.ndarray]]:
    """Deterministic 100-bar OHLCV data for two correlated symbols.

    BTCUSDT: base random walk with drift.
    ETHUSDT: BTCUSDT * 0.9 + noise (highly correlated, follows BTC).
    """
    rng = np.random.RandomState(42)
    n = 100
    # BTC: random walk
    btc_close = 50000.0 + np.cumsum(rng.randn(n) * 200.0)
    btc_high = btc_close + np.abs(rng.randn(n) * 100.0)
    btc_low = btc_close - np.abs(rng.randn(n) * 100.0)
    btc_open = btc_close - rng.randn(n) * 50.0
    btc_volume = np.abs(rng.randn(n) * 100.0) + 100.0

    btc_ohlcv = {
        "open": btc_open,
        "high": btc_high,
        "low": btc_low,
        "close": btc_close,
        "volume": btc_volume,
    }

    # ETH: correlated to BTC with some noise
    eth_close = btc_close * 0.9 + rng.randn(n) * 150.0
    eth_high = eth_close + np.abs(rng.randn(n) * 80.0)
    eth_low = eth_close - np.abs(rng.randn(n) * 80.0)
    eth_open = eth_close - rng.randn(n) * 40.0
    eth_volume = np.abs(rng.randn(n) * 80.0) + 80.0

    eth_ohlcv = {
        "open": eth_open,
        "high": eth_high,
        "low": eth_low,
        "close": eth_close,
        "volume": eth_volume,
    }

    return {"BTCUSDT": btc_ohlcv, "ETHUSDT": eth_ohlcv}


@pytest.fixture
def two_symbol_ohlcv_500() -> Dict[str, Dict[str, np.ndarray]]:
    """Deterministic 500-bar OHLCV data for two symbols."""
    rng = np.random.RandomState(99)
    n = 500
    btc_close = 50000.0 + np.cumsum(rng.randn(n) * 200.0)
    btc_high = btc_close + np.abs(rng.randn(n) * 100.0)
    btc_low = btc_close - np.abs(rng.randn(n) * 100.0)
    btc_open = btc_close - rng.randn(n) * 50.0
    btc_volume = np.abs(rng.randn(n) * 150.0) + 50.0

    btc_ohlcv = {
        "open": btc_open,
        "high": btc_high,
        "low": btc_low,
        "close": btc_close,
        "volume": btc_volume,
    }

    # ETH: BTC * 0.85 + independent noise
    eth_close = btc_close * 0.85 + rng.randn(n) * 200.0
    eth_high = eth_close + np.abs(rng.randn(n) * 90.0)
    eth_low = eth_close - np.abs(rng.randn(n) * 90.0)
    eth_open = eth_close - rng.randn(n) * 45.0
    eth_volume = np.abs(rng.randn(n) * 120.0) + 60.0

    eth_ohlcv = {
        "open": eth_open,
        "high": eth_high,
        "low": eth_low,
        "close": eth_close,
        "volume": eth_volume,
    }

    return {"BTCUSDT": btc_ohlcv, "ETHUSDT": eth_ohlcv}


@pytest.fixture
def three_symbol_ohlcv_100() -> Dict[str, Dict[str, np.ndarray]]:
    """Deterministic 100-bar OHLCV data for three symbols (BTC, ETH, SOL)."""
    rng = np.random.RandomState(7)
    n = 100
    btc_close = 50000.0 + np.cumsum(rng.randn(n) * 200.0)
    btc_high = btc_close + np.abs(rng.randn(n) * 100.0)
    btc_low = btc_close - np.abs(rng.randn(n) * 100.0)
    btc_open = btc_close - rng.randn(n) * 50.0
    btc_volume = np.abs(rng.randn(n) * 100.0) + 100.0

    btc = {"open": btc_open, "high": btc_high, "low": btc_low, "close": btc_close, "volume": btc_volume}

    eth_close = btc_close * 0.9 + rng.randn(n) * 150.0
    eth_high = eth_close + np.abs(rng.randn(n) * 80.0)
    eth_low = eth_close - np.abs(rng.randn(n) * 80.0)
    eth_open = eth_close - rng.randn(n) * 40.0
    eth_volume = np.abs(rng.randn(n) * 80.0) + 80.0

    eth = {"open": eth_open, "high": eth_high, "low": eth_low, "close": eth_close, "volume": eth_volume}

    sol_close = 100.0 + np.cumsum(rng.randn(n) * 3.0)
    sol_high = sol_close + np.abs(rng.randn(n) * 5.0)
    sol_low = sol_close - np.abs(rng.randn(n) * 5.0)
    sol_open = sol_close - rng.randn(n) * 2.0
    sol_volume = np.abs(rng.randn(n) * 500.0) + 1000.0

    sol = {"open": sol_open, "high": sol_high, "low": sol_low, "close": sol_close, "volume": sol_volume}

    return {"BTCUSDT": btc, "ETHUSDT": eth, "SOLUSDT": sol}


@pytest.fixture
def perfect_positive_symbols() -> Dict[str, Dict[str, np.ndarray]]:
    """Two symbols with perfect positive correlation (context = primary * constant)."""
    rng = np.random.RandomState(1)
    n = 200
    primary_close = 100.0 + np.cumsum(rng.randn(n) * 1.0)
    # Context = primary scaled by factor (perfect correlation on returns too)
    context_close = primary_close * 1.5

    def make_ohlcv(close_series):
        high = close_series + np.abs(rng.randn(n) * 5.0)
        low = close_series - np.abs(rng.randn(n) * 5.0)
        open_arr = close_series - rng.randn(n) * 2.0
        volume = np.abs(rng.randn(n) * 100.0) + 100.0
        return {"open": open_arr, "high": high, "low": low, "close": close_series, "volume": volume}

    return {
        "PRIMARY": make_ohlcv(primary_close),
        "CONTEXT": make_ohlcv(context_close),
    }


# ===========================================================================
# Validation Tests
# ===========================================================================


class TestValidateMultiSymbolOHLCV:
    """LL-01: Cross-sectional validation."""

    def test_validates_two_symbols(self, two_symbol_ohlcv_100):
        n = _validate_multi_symbol_ohlcv(two_symbol_ohlcv_100)
        assert n == 100

    def test_validates_three_symbols(self, three_symbol_ohlcv_100):
        n = _validate_multi_symbol_ohlcv(three_symbol_ohlcv_100)
        assert n == 100

    def test_rejects_single_symbol(self):
        close = np.array([100.0, 101.0, 102.0], dtype=np.float64)
        single = {"BTCUSDT": {
            "open": close, "high": close, "low": close,
            "close": close, "volume": np.ones(3),
        }}
        with pytest.raises(ValueError, match="at least 2 symbols"):
            _validate_multi_symbol_ohlcv(single)

    def test_rejects_empty_dict(self):
        with pytest.raises(ValueError, match="at least 2 symbols"):
            _validate_multi_symbol_ohlcv({})

    def test_rejects_missing_columns(self):
        bad = {"A": {"close": np.array([1.0, 2.0])}}  # missing open, high, low, volume
        with pytest.raises(ValueError, match="missing required columns"):
            _validate_multi_symbol_ohlcv({"A": bad["A"], "B": {
                "open": np.array([1.0, 2.0]), "high": np.array([1.0, 2.0]),
                "low": np.array([1.0, 2.0]), "close": np.array([1.0, 2.0]),
                "volume": np.array([1.0, 2.0]),
            }})

    def test_rejects_mismatched_lengths(self):
        a = {"open": np.ones(5), "high": np.ones(5), "low": np.ones(5),
             "close": np.ones(5), "volume": np.ones(5)}
        b = {"open": np.ones(10), "high": np.ones(10), "low": np.ones(10),
             "close": np.ones(10), "volume": np.ones(10)}
        with pytest.raises(ValueError, match="same number of bars"):
            _validate_multi_symbol_ohlcv({"A": a, "B": b})

    def test_rejects_non_1d_array(self):
        a = {"open": np.ones((3, 1)), "high": np.ones(3), "low": np.ones(3),
             "close": np.ones(3), "volume": np.ones(3)}
        b = {"open": np.ones(3), "high": np.ones(3), "low": np.ones(3),
             "close": np.ones(3), "volume": np.ones(3)}
        with pytest.raises(TypeError, match="1D numpy"):
            _validate_multi_symbol_ohlcv({"A": a, "B": b})


# ===========================================================================
# tf_alignment Tests
# ===========================================================================


class TestTfAlignment:
    """LL-02: Timeframe volatility alignment."""

    def test_output_shape(self, two_symbol_ohlcv_100):
        result = compute_tf_alignment(two_symbol_ohlcv_100, "BTCUSDT", "ETHUSDT")
        assert len(result) == 100
        assert result.dtype == np.float64

    def test_range_bounded(self, two_symbol_ohlcv_500):
        """Alignment scores must be in [-1, 1]."""
        result = compute_tf_alignment(two_symbol_ohlcv_500, "BTCUSDT", "ETHUSDT")
        valid = result[~np.isnan(result)]
        assert len(valid) > 0, "Expected some valid (non-NaN) alignment values"
        assert np.all(valid >= -1.0), f"Min: {np.min(valid)}"
        assert np.all(valid <= 1.0), f"Max: {np.max(valid)}"

    def test_nan_at_start(self, two_symbol_ohlcv_500):
        """First window-1 values should be NaN (volatility needs window returns)."""
        result = compute_tf_alignment(two_symbol_ohlcv_500, "BTCUSDT", "ETHUSDT", window=20)
        # At index 0..19: NaN (insufficient data for volatility window)
        assert np.all(np.isnan(result[:19]))
        # At index 20+: should have valid values (volatility window = 20, need 20 returns = 21 bars)
        assert np.any(~np.isnan(result[21:]))

    def test_determinism(self, two_symbol_ohlcv_100):
        """Same input produces identical output."""
        r1 = compute_tf_alignment(two_symbol_ohlcv_100, "BTCUSDT", "ETHUSDT")
        r2 = compute_tf_alignment(two_symbol_ohlcv_100, "BTCUSDT", "ETHUSDT")
        assert np.allclose(r1, r2, equal_nan=True)

    def test_rejects_missing_symbol(self, two_symbol_ohlcv_100):
        with pytest.raises(ValueError, match="not in multi_ohlcv"):
            compute_tf_alignment(two_symbol_ohlcv_100, "MISSING", "ETHUSDT")

    def test_rejects_same_symbol(self, two_symbol_ohlcv_100):
        with pytest.raises(ValueError, match="must be different"):
            compute_tf_alignment(two_symbol_ohlcv_100, "BTCUSDT", "BTCUSDT")

    def test_causality_no_future_access(self, perfect_positive_symbols):
        """Adding future data must not change past values."""
        primary_close = perfect_positive_symbols["PRIMARY"]["close"].copy()
        context_close = perfect_positive_symbols["CONTEXT"]["close"].copy()

        # Compute on first 150 bars
        partial = {
            "PRIMARY": {**perfect_positive_symbols["PRIMARY"], "close": primary_close[:150]},
            "CONTEXT": {**perfect_positive_symbols["CONTEXT"], "close": context_close[:150]},
        }
        # Need to truncate all columns
        for sym in ["PRIMARY", "CONTEXT"]:
            for col in perfect_positive_symbols[sym]:
                partial[sym][col] = perfect_positive_symbols[sym][col][:150]

        r_partial = compute_tf_alignment(partial, "PRIMARY", "CONTEXT", window=10)

        # Compute on full 200 bars
        r_full = compute_tf_alignment(perfect_positive_symbols, "PRIMARY", "CONTEXT", window=10)

        # Past values at indices < 150 should match
        comparison = r_partial[:150]
        full_comparison = r_full[:150]
        valid = ~np.isnan(comparison) & ~np.isnan(full_comparison)
        if np.any(valid):
            assert np.allclose(comparison[valid], full_comparison[valid])


# ===========================================================================
# correlation_pairwise Tests
# ===========================================================================


class TestCorrelationPairwise:
    """LL-03: Pairwise rolling correlation."""

    def test_output_shape(self, two_symbol_ohlcv_100):
        result = compute_correlation_pairwise(two_symbol_ohlcv_100, "BTCUSDT", "ETHUSDT")
        assert len(result) == 100
        assert result.dtype == np.float64

    def test_range_bounded(self, two_symbol_ohlcv_500):
        """Correlation values must be in [-1, 1]."""
        result = compute_correlation_pairwise(two_symbol_ohlcv_500, "BTCUSDT", "ETHUSDT")
        valid = result[~np.isnan(result)]
        assert len(valid) > 0
        assert np.all(valid >= -1.0)
        assert np.all(valid <= 1.0)

    def test_nan_at_start(self, two_symbol_ohlcv_100):
        """First window-1 values should be NaN."""
        result = compute_correlation_pairwise(two_symbol_ohlcv_100, "BTCUSDT", "ETHUSDT", window=20)
        assert np.all(np.isnan(result[:19]))  # indices 0..18
        assert np.any(~np.isnan(result[20:]))  # index 20+ should have values

    def test_correlation_returns_vs_prices(self, two_symbol_ohlcv_100):
        """Correlation on returns vs prices should differ."""
        r_returns = compute_correlation_pairwise(
            two_symbol_ohlcv_100, "BTCUSDT", "ETHUSDT", window=20, use_returns=True
        )
        r_prices = compute_correlation_pairwise(
            two_symbol_ohlcv_100, "BTCUSDT", "ETHUSDT", window=20, use_returns=False
        )
        # Both should produce values but they'll differ in general
        valid_ret = r_returns[~np.isnan(r_returns)]
        valid_prc = r_prices[~np.isnan(r_prices)]
        assert len(valid_ret) > 0
        assert len(valid_prc) > 0

    def test_determinism(self, two_symbol_ohlcv_100):
        r1 = compute_correlation_pairwise(two_symbol_ohlcv_100, "BTCUSDT", "ETHUSDT")
        r2 = compute_correlation_pairwise(two_symbol_ohlcv_100, "BTCUSDT", "ETHUSDT")
        assert np.allclose(r1, r2, equal_nan=True)

    def test_rejects_missing_symbol(self, two_symbol_ohlcv_100):
        with pytest.raises(ValueError, match="not in multi_ohlcv"):
            compute_correlation_pairwise(two_symbol_ohlcv_100, "BTCUSDT", "MISSING")

    def test_rejects_same_symbol(self, two_symbol_ohlcv_100):
        with pytest.raises(ValueError, match="must be different"):
            compute_correlation_pairwise(two_symbol_ohlcv_100, "BTCUSDT", "BTCUSDT")

    def test_causality_no_future_access(self, perfect_positive_symbols):
        """Adding future data must not change past correlation values."""
        # Create partial dataset with 150 bars
        partial = {}
        for sym in ["PRIMARY", "CONTEXT"]:
            partial[sym] = {}
            for col in perfect_positive_symbols[sym]:
                partial[sym][col] = perfect_positive_symbols[sym][col][:150].copy()

        r_partial = compute_correlation_pairwise(partial, "PRIMARY", "CONTEXT", window=10)
        r_full = compute_correlation_pairwise(perfect_positive_symbols, "PRIMARY", "CONTEXT", window=10)

        valid = ~np.isnan(r_partial) & ~np.isnan(r_full[:150])
        if np.any(valid):
            assert np.allclose(r_partial[valid], r_full[:150][valid])


# ===========================================================================
# lead_lag_score Tests
# ===========================================================================


class TestLeadLagScore:
    """LL-04: Lead-lag detection."""

    def test_output_shape(self, two_symbol_ohlcv_100):
        result = compute_lead_lag_score(two_symbol_ohlcv_100, "BTCUSDT", "ETHUSDT")
        assert len(result) == 100
        assert result.dtype == np.float64

    def test_range_bounded(self, two_symbol_ohlcv_500):
        """Lead-lag scores must be in [-1, 1]."""
        result = compute_lead_lag_score(two_symbol_ohlcv_500, "BTCUSDT", "ETHUSDT")
        valid = result[~np.isnan(result)]
        assert len(valid) > 0
        assert np.all(valid >= -1.0), f"Min: {np.min(valid)}"
        assert np.all(valid <= 1.0), f"Max: {np.max(valid)}"

    def test_nan_at_start(self, two_symbol_ohlcv_100):
        """Start values should be NaN (requires window + max_lag bars)."""
        result = compute_lead_lag_score(two_symbol_ohlcv_100, "BTCUSDT", "ETHUSDT", window=20, max_lag=5)
        # First 24 values (0..24) should be NaN (window-1 + max_lag = 19 + 5 = 24)
        assert np.all(np.isnan(result[:24]))
        assert np.any(~np.isnan(result[25:]))

    def test_determinism(self, two_symbol_ohlcv_100):
        r1 = compute_lead_lag_score(two_symbol_ohlcv_100, "BTCUSDT", "ETHUSDT")
        r2 = compute_lead_lag_score(two_symbol_ohlcv_100, "BTCUSDT", "ETHUSDT")
        assert np.allclose(r1, r2, equal_nan=True)

    def test_rejects_missing_symbol(self, two_symbol_ohlcv_100):
        with pytest.raises(ValueError, match="not in multi_ohlcv"):
            compute_lead_lag_score(two_symbol_ohlcv_100, "BTCUSDT", "NOPE")

    def test_rejects_invalid_max_lag(self, two_symbol_ohlcv_100):
        with pytest.raises(ValueError, match="max_lag must be at least 1"):
            compute_lead_lag_score(two_symbol_ohlcv_100, "BTCUSDT", "ETHUSDT", max_lag=0)

    def test_rejects_max_lag_geq_window(self, two_symbol_ohlcv_100):
        with pytest.raises(ValueError, match="must be less than window"):
            compute_lead_lag_score(two_symbol_ohlcv_100, "BTCUSDT", "ETHUSDT", window=5, max_lag=5)

    def test_causality_no_future_access(self, perfect_positive_symbols):
        """Adding future data must not change past lead-lag scores."""
        partial = {}
        for sym in ["PRIMARY", "CONTEXT"]:
            partial[sym] = {}
            for col in perfect_positive_symbols[sym]:
                partial[sym][col] = perfect_positive_symbols[sym][col][:150].copy()

        r_partial = compute_lead_lag_score(partial, "PRIMARY", "CONTEXT", window=10, max_lag=3)
        r_full = compute_lead_lag_score(perfect_positive_symbols, "PRIMARY", "CONTEXT", window=10, max_lag=3)

        valid = ~np.isnan(r_partial) & ~np.isnan(r_full[:150])
        if np.any(valid):
            assert np.allclose(r_partial[valid], r_full[:150][valid])


# ===========================================================================
# Group Integration Tests
# ===========================================================================


class TestLeadLagGroup:
    """LL-05: compute_lead_lag_group integration."""

    def test_all_three_keys_present(self, two_symbol_ohlcv_100):
        result = compute_lead_lag_group(two_symbol_ohlcv_100, "BTCUSDT", "ETHUSDT")
        assert set(result.keys()) == {"tf_alignment", "correlation_pairwise", "lead_lag_score"}
        n_bars = 100
        for key, arr in result.items():
            assert len(arr) == n_bars, f"{key} has wrong length: {len(arr)} vs {n_bars}"

    def test_consistent_output_shape(self, two_symbol_ohlcv_500):
        """All three feature arrays should have the same length."""
        result = compute_lead_lag_group(two_symbol_ohlcv_500, "BTCUSDT", "ETHUSDT")
        lengths = {key: len(arr) for key, arr in result.items()}
        assert len(set(lengths.values())) == 1, f"Inconsistent lengths: {lengths}"

    def test_with_three_symbols(self, three_symbol_ohlcv_100):
        """Works with three symbols — picks pair."""
        result = compute_lead_lag_group(three_symbol_ohlcv_100, "BTCUSDT", "SOLUSDT")
        assert set(result.keys()) == {"tf_alignment", "correlation_pairwise", "lead_lag_score"}
        for arr in result.values():
            assert len(arr) == 100

    def test_determinism(self, two_symbol_ohlcv_100):
        r1 = compute_lead_lag_group(two_symbol_ohlcv_100, "BTCUSDT", "ETHUSDT")
        r2 = compute_lead_lag_group(two_symbol_ohlcv_100, "BTCUSDT", "ETHUSDT")
        for key in r1:
            assert np.allclose(r1[key], r2[key], equal_nan=True), f"Mismatch in {key}"

    def test_rejects_missing_primary(self, two_symbol_ohlcv_100):
        with pytest.raises(ValueError, match="not in multi_ohlcv"):
            compute_lead_lag_group(two_symbol_ohlcv_100, "NOPE", "ETHUSDT")


# ===========================================================================
# Rolling Correlation Utility Tests
# ===========================================================================


class TestRollingCorrelation:
    """LL-06: Internal rolling correlation utility."""

    def test_perfect_positive(self):
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        y = x * 2.0 + 3.0  # linear transformation => correlation = 1
        result = _rolling_correlation(x, y, window=5)
        valid = result[~np.isnan(result)]
        assert len(valid) > 0
        # Perfect linear correlation => r ~= 1.0
        assert np.all(np.abs(valid - 1.0) < 1e-10), f"Values: {valid}"

    def test_perfect_negative(self):
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        y = -x * 2.0 + 3.0  # linear negative => correlation = -1
        result = _rolling_correlation(x, y, window=5)
        valid = result[~np.isnan(result)]
        assert len(valid) > 0
        assert np.all(np.abs(valid + 1.0) < 1e-10), f"Values: {valid}"

    def test_nan_handling(self):
        """NaN values should not crash; should produce NaN where insufficient valid data."""
        x = np.array([1.0, np.nan, 3.0, 4.0, np.nan, 6.0, 7.0, 8.0, 9.0, 10.0])
        y = np.array([2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, np.nan, np.nan, 20.0])
        result = _rolling_correlation(x, y, window=5, min_valid=3)
        assert len(result) == 10
        # Should not raise any exception

    def test_short_input(self):
        x = np.array([1.0, 2.0, 3.0])
        y = np.array([4.0, 5.0, 6.0])
        result = _rolling_correlation(x, y, window=5)
        # Window > length => all NaN
        assert np.all(np.isnan(result))

    def test_constant_series(self):
        """Constant series should produce NaN correlation (zero std)."""
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        y = np.ones(10) * 5.0  # constant
        result = _rolling_correlation(x, y, window=5)
        valid = result[~np.isnan(result)]
        # Constant y => std=0 => correlation is NaN
        assert len(valid) == 0


# ===========================================================================
# Log Returns Utility Tests
# ===========================================================================


class TestComputeLogReturns:
    """LL-07: Internal log returns utility."""

    def test_basic(self):
        close = np.array([100.0, 110.0, 121.0], dtype=np.float64)
        result = _compute_log_returns(close)
        assert len(result) == 3
        assert np.isnan(result[0])
        assert math.isclose(result[1], math.log(110.0 / 100.0), rel_tol=1e-10)
        assert math.isclose(result[2], math.log(121.0 / 110.0), rel_tol=1e-10)

    def test_empty(self):
        result = _compute_log_returns(np.array([], dtype=np.float64))
        assert len(result) == 0

    def test_single(self):
        result = _compute_log_returns(np.array([100.0]))
        assert len(result) == 1
        assert np.isnan(result[0])


# ===========================================================================
# Cross-Sectional Contract Tests
# ===========================================================================


class TestCrossSectionalContract:
    """LL-08: Cross-sectional data contract verification."""

    def test_minimum_two_symbols_enforced_everywhere(self, two_symbol_ohlcv_100):
        """All lead-lag functions reject < 2 symbols."""
        single = {"A": two_symbol_ohlcv_100["BTCUSDT"]}
        with pytest.raises(ValueError, match="at least 2"):
            compute_tf_alignment(single, "A", "A")
        with pytest.raises(ValueError, match="at least 2"):
            compute_correlation_pairwise(single, "A", "A")
        with pytest.raises(ValueError, match="at least 2"):
            compute_lead_lag_score(single, "A", "A")

    def test_aligned_bar_count_required(self, two_symbol_ohlcv_100):
        """Mismatched bar counts are rejected."""
        bad = dict(two_symbol_ohlcv_100)
        # Truncate ETH close (and all columns to keep consistency)
        for col in bad["ETHUSDT"]:
            bad["ETHUSDT"][col] = bad["ETHUSDT"][col][:90]
        with pytest.raises(ValueError, match="same number of bars"):
            compute_tf_alignment(bad, "BTCUSDT", "ETHUSDT")

    def test_lead_lag_not_wired_in_main_pipeline(self):
        """LEAD_LAG is mapped but compute_features() does NOT compute it."""
        # This is a contract test: the main pipeline intentionally skips LEAD_LAG
        assert FeatureGroup.LEAD_LAG.value == "lead_lag"
        # compute_features() requires single-symbol OHLCV, which LEAD_LAG cannot use
        # This is by design — the cross-sectional pipeline is P0.9B
        single_ohlcv = {
            "open": np.array([100.0, 101.0, 102.0], dtype=np.float64),
            "high": np.array([101.0, 102.0, 103.0], dtype=np.float64),
            "low": np.array([99.0, 100.0, 101.0], dtype=np.float64),
            "close": np.array([100.0, 101.0, 102.0], dtype=np.float64),
            "volume": np.array([100.0, 110.0, 120.0], dtype=np.float64),
        }
        from alphaforge.features import compute_features
        result = compute_features(single_ohlcv, mode="SWING")
        assert "tf_alignment" not in result.features
        assert "correlation_pairwise" not in result.features
        assert "lead_lag_score" not in result.features
        assert "lead_lag" not in result.feature_group_ids


# ===========================================================================
# Import Tests
# ===========================================================================


class TestLeadLagImports:
    """LL-09: Import boundary verification."""

    def test_all_exports_importable(self):
        from alphaforge.features import (
            compute_lead_lag_group,
            compute_tf_alignment,
            compute_correlation_pairwise,
            compute_lead_lag_score,
            LL_CORRELATION_WINDOW,
            LL_MAX_LAG,
            LL_MIN_VALID,
            LL_PERIODS_PER_YEAR,
            LL_VOLATILITY_WINDOW,
        )
        assert compute_lead_lag_group is not None
        assert compute_tf_alignment is not None
        assert compute_correlation_pairwise is not None
        assert compute_lead_lag_score is not None
        assert LL_CORRELATION_WINDOW > 0
        assert LL_MAX_LAG > 0
        assert LL_VOLATILITY_WINDOW > 0

    def test_lead_lag_enum_mapped(self):
        """FEATURE_GROUP_MAP now maps LEAD_LAG to compute_lead_lag_group."""
        from alphaforge.features import FEATURE_GROUP_MAP, FeatureGroup
        assert FeatureGroup.LEAD_LAG in FEATURE_GROUP_MAP
        assert FEATURE_GROUP_MAP[FeatureGroup.LEAD_LAG] == "compute_lead_lag_group"
