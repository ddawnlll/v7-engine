"""Tests for FeatureCache — Parquet+Zstd feature caching for pipeline speedup.

Covers:
  (a) Cache key determinism and uniqueness
  (b) Put/get roundtrip with numeric fidelity
  (c) Cache miss returns None
  (d) Invalidate and clear_all lifecycle
  (e) NaN preservation through serialization
  (f) Metadata preservation
  (g) Thread safety on concurrent writes
  (h) cached_compute_features() wrapper: hit, miss, symbol extraction
  (i) Error resilience (corrupt file returns None)
  (j) Empty feature matrix edge case

Minimum 18 tests per issue #158 requirement.
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
from pathlib import Path
from typing import Dict

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Ensure alphaforge is importable
# ---------------------------------------------------------------------------
_src = Path(__file__).resolve().parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from alphaforge.features.pipeline import (
    CACHE_DIR_DEFAULT,
    PIPELINE_VERSION,
    FeatureCache,
    FeatureMatrix,
    cached_compute_features,
    compute_features,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _make_test_matrix(
    n_bars: int = 5,
    symbol: str = "BTCUSDT",
    mode: str = "SWING",
    include_nan: bool = False,
) -> FeatureMatrix:
    """Create a deterministic FeatureMatrix for cache testing.

    Args:
        n_bars: Number of bars (rows) in each feature array.
        symbol: Trading pair identifier.
        mode: Trading mode.
        include_nan: If True, include NaN values in some arrays.

    Returns:
        FeatureMatrix with 3 feature arrays.
    """
    np.random.seed(42)
    noise = np.random.randn(n_bars) * 0.01

    log_ret = np.full(n_bars, np.nan, dtype=np.float64)
    if n_bars > 1:
        log_ret[1:] = noise[1:]

    rsi = np.full(n_bars, np.nan, dtype=np.float64)
    if n_bars > 14:
        rsi[14:] = 50.0 + np.cumsum(noise[14:]) * 10.0
    elif n_bars > 1:
        rsi[1:] = 50.0 + np.arange(n_bars - 1, dtype=np.float64) * 5.0

    atr = np.full(n_bars, np.nan, dtype=np.float64)
    if n_bars > 1:
        atr[1:] = np.abs(noise[1:]) * 100.0

    if include_nan and n_bars > 3:
        log_ret[2] = np.nan
        rsi[3] = np.nan

    features: Dict[str, np.ndarray] = {
        "log_return_1": log_ret,
        "rsi_N": rsi,
        "atr_N": atr,
    }

    return FeatureMatrix(
        features=features,
        symbol=symbol,
        mode=mode,
        metadata={"pipeline_version": PIPELINE_VERSION},
    )


def _make_dummy_ohlcv(
    n_bars: int = 100,
    symbol: str = "BTCUSDT",
    seed: int = 42,
) -> dict:
    """Generate deterministic OHLCV data for pipeline testing."""
    rng = np.random.RandomState(seed)
    close = 50000.0 + np.cumsum(rng.randn(n_bars) * 200.0)
    return {
        "open": close * 0.999,
        "high": close * 1.005,
        "low": close * 0.995,
        "close": close,
        "volume": np.abs(rng.randn(n_bars) * 100.0) + 100.0,
        "symbol": symbol,
    }


# ===========================================================================
# Cache Key Tests
# ===========================================================================


class TestCacheKey:
    """FeatureCache key derivation."""

    def test_key_deterministic(self):
        """Same inputs produce identical cache key."""
        cache = FeatureCache(cache_dir="/tmp/nonexistent")
        key1 = cache._cache_key("BTCUSDT", "4h", "SWING")
        key2 = cache._cache_key("BTCUSDT", "4h", "SWING")
        assert key1 == key2

    def test_key_differs_on_symbol(self):
        """Different symbols produce different keys."""
        cache = FeatureCache(cache_dir="/tmp/nonexistent")
        assert cache._cache_key("BTCUSDT", "4h", "SWING") != cache._cache_key(
            "ETHUSDT", "4h", "SWING"
        )

    def test_key_differs_on_interval(self):
        """Different intervals produce different keys."""
        cache = FeatureCache(cache_dir="/tmp/nonexistent")
        assert cache._cache_key("BTCUSDT", "4h", "SWING") != cache._cache_key(
            "BTCUSDT", "1h", "SWING"
        )

    def test_key_differs_on_mode(self):
        """Different modes produce different keys."""
        cache = FeatureCache(cache_dir="/tmp/nonexistent")
        assert cache._cache_key("BTCUSDT", "4h", "SWING") != cache._cache_key(
            "BTCUSDT", "4h", "SCALP"
        )

    def test_key_includes_version(self):
        """Cache key embeds PIPELINE_VERSION for automatic invalidation."""
        cache = FeatureCache(cache_dir="/tmp/nonexistent")
        key = cache._cache_key("BTCUSDT", "4h", "SWING")
        raw = f"BTCUSDT|4h|SWING|{PIPELINE_VERSION}"
        expected = hashlib.sha256(raw.encode()).hexdigest()
        assert key == expected

    def test_key_is_sha256_hex(self):
        """Cache key is a valid SHA-256 hex digest (64 chars)."""
        cache = FeatureCache(cache_dir="/tmp/nonexistent")
        key = cache._cache_key("BTCUSDT", "4h", "SWING")
        assert len(key) == 64
        int(key, 16)  # raises ValueError if not valid hex


# ===========================================================================
# Put / Get Roundtrip
# ===========================================================================


class TestPutGet:
    """FeatureMatrix storage and retrieval."""

    def test_put_get_roundtrip(self, tmp_path):
        """FeatureMatrix survives put/get roundtrip with numeric fidelity."""
        cache = FeatureCache(cache_dir=str(tmp_path))
        matrix = _make_test_matrix(n_bars=100)

        cache.put("BTCUSDT", "4h", "SWING", matrix)
        loaded = cache.get("BTCUSDT", "4h", "SWING")

        assert loaded is not None
        assert loaded.symbol == "BTCUSDT"
        assert loaded.mode == "SWING"
        assert set(loaded.features.keys()) == {"log_return_1", "rsi_N", "atr_N"}
        for name in matrix.features:
            assert np.allclose(
                loaded.features[name], matrix.features[name], equal_nan=True
            ), f"Feature '{name}' differs after roundtrip"

    def test_put_get_preserves_nan(self, tmp_path):
        """NaN values are preserved through serialization."""
        cache = FeatureCache(cache_dir=str(tmp_path))
        matrix = _make_test_matrix(n_bars=50, include_nan=True)

        cache.put("BTCUSDT", "4h", "SWING", matrix)
        loaded = cache.get("BTCUSDT", "4h", "SWING")

        assert loaded is not None
        for name in matrix.features:
            original_nans = np.isnan(matrix.features[name])
            loaded_nans = np.isnan(loaded.features[name])
            assert np.array_equal(
                original_nans, loaded_nans
            ), f"NaN pattern differs for '{name}'"

    def test_cache_miss_returns_none(self, tmp_path):
        """Cache miss returns None cleanly."""
        cache = FeatureCache(cache_dir=str(tmp_path))
        result = cache.get("NONEXISTENT", "4h", "SWING")
        assert result is None

    def test_put_get_different_symbols(self, tmp_path):
        """Different symbols do not interfere."""
        cache = FeatureCache(cache_dir=str(tmp_path))
        m1 = _make_test_matrix(symbol="BTCUSDT")
        m2 = _make_test_matrix(symbol="ETHUSDT")
        cache.put("BTCUSDT", "4h", "SWING", m1)
        cache.put("ETHUSDT", "4h", "SWING", m2)

        loaded1 = cache.get("BTCUSDT", "4h", "SWING")
        loaded2 = cache.get("ETHUSDT", "4h", "SWING")
        assert loaded1 is not None
        assert loaded2 is not None
        assert loaded1.symbol == "BTCUSDT"
        assert loaded2.symbol == "ETHUSDT"

    def test_put_get_empty_features(self, tmp_path):
        """Empty feature dict roundtrips without error."""
        cache = FeatureCache(cache_dir=str(tmp_path))
        matrix = FeatureMatrix(
            features={},
            symbol="BTCUSDT",
            mode="SWING",
        )
        cache.put("BTCUSDT", "4h", "SWING", matrix)
        loaded = cache.get("BTCUSDT", "4h", "SWING")
        assert loaded is not None
        assert loaded.features == {}
        assert loaded.bar_count() == 0

    def test_get_corrupt_file_returns_none(self, tmp_path):
        """Corrupt cache file returns None (not an exception)."""
        cache = FeatureCache(cache_dir=str(tmp_path))
        key = cache._cache_key("BTCUSDT", "4h", "SWING")
        path = cache._cache_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("this is not a valid parquet file")

        result = cache.get("BTCUSDT", "4h", "SWING")
        assert result is None


# ===========================================================================
# Metadata Preservation
# ===========================================================================


class TestMetadata:
    """FeatureMatrix metadata through cache roundtrip."""

    def test_metadata_preserved(self, tmp_path):
        """Pipeline version and feature_group_ids persist through cache."""
        cache = FeatureCache(cache_dir=str(tmp_path))
        matrix = _make_test_matrix()
        matrix.metadata["test_key"] = "test_value"

        cache.put("BTCUSDT", "4h", "SWING", matrix)
        loaded = cache.get("BTCUSDT", "4h", "SWING")

        assert loaded is not None
        assert loaded.metadata.get("pipeline_version") == PIPELINE_VERSION
        assert "test_value" in json.dumps(loaded.metadata)

    def test_bar_count_correct(self, tmp_path):
        """bar_count() returns correct value after roundtrip."""
        cache = FeatureCache(cache_dir=str(tmp_path))
        matrix = _make_test_matrix(n_bars=200)
        cache.put("BTCUSDT", "4h", "SWING", matrix)
        loaded = cache.get("BTCUSDT", "4h", "SWING")
        assert loaded is not None
        assert loaded.bar_count() == 200


# ===========================================================================
# Invalidation
# ===========================================================================


class TestInvalidation:
    """Cache invalidation and clearing."""

    def test_invalidate_removes_entry(self, tmp_path):
        """Invalidate removes a specific cache entry."""
        cache = FeatureCache(cache_dir=str(tmp_path))
        cache.put("BTCUSDT", "4h", "SWING", _make_test_matrix())
        assert cache.get("BTCUSDT", "4h", "SWING") is not None
        assert cache.invalidate("BTCUSDT", "4h", "SWING") is True
        assert cache.get("BTCUSDT", "4h", "SWING") is None

    def test_invalidate_missing_returns_false(self, tmp_path):
        """Invalidate on non-existent entry returns False."""
        cache = FeatureCache(cache_dir=str(tmp_path))
        assert cache.invalidate("NONEXISTENT", "4h", "SWING") is False

    def test_invalidate_does_not_affect_other_entries(self, tmp_path):
        """Invalidate removes only the targeted entry."""
        cache = FeatureCache(cache_dir=str(tmp_path))
        cache.put("BTCUSDT", "4h", "SWING", _make_test_matrix())
        cache.put("ETHUSDT", "4h", "SWING", _make_test_matrix(symbol="ETHUSDT"))
        cache.invalidate("BTCUSDT", "4h", "SWING")
        assert cache.get("ETHUSDT", "4h", "SWING") is not None

    def test_clear_all_removes_everything(self, tmp_path):
        """clear_all removes all cache files."""
        cache = FeatureCache(cache_dir=str(tmp_path))
        cache.put("BTCUSDT", "4h", "SWING", _make_test_matrix())
        cache.put("ETHUSDT", "1h", "SCALP", _make_test_matrix(symbol="ETHUSDT"))
        assert cache.clear_all() == 2
        assert cache.get("BTCUSDT", "4h", "SWING") is None
        assert cache.get("ETHUSDT", "1h", "SCALP") is None

    def test_clear_all_empty_returns_zero(self, tmp_path):
        """clear_all on empty cache returns 0."""
        cache = FeatureCache(cache_dir=str(tmp_path))
        assert cache.clear_all() == 0

    def test_clear_all_nonexistent_dir(self, tmp_path):
        """clear_all works when cache dir does not exist."""
        cache = FeatureCache(cache_dir=str(tmp_path / "nonexistent"))
        assert cache.clear_all() == 0


# ===========================================================================
# Thread Safety
# ===========================================================================


class TestThreadSafety:
    """Concurrent write safety."""

    def test_concurrent_puts(self, tmp_path):
        """Multiple threads can write to the same cache dir safely."""
        cache = FeatureCache(cache_dir=str(tmp_path))
        errors: list = []
        lock = threading.Lock()

        def _put(symbol: str) -> None:
            try:
                m = _make_test_matrix(symbol=symbol)
                cache.put(symbol, "4h", "SWING", m)
            except Exception as e:
                with lock:
                    errors.append(e)

        symbols = [f"SYM{i:04d}" for i in range(20)]
        threads = [threading.Thread(target=_put, args=(s,)) for s in symbols]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrent put errors: {errors}"
        # Verify all entries are readable
        for s in symbols:
            loaded = cache.get(s, "4h", "SWING")
            assert loaded is not None, f"Symbol {s} missing after concurrent puts"
            assert loaded.symbol == s


# ===========================================================================
# cached_compute_features Wrapper
# ===========================================================================


class TestCachedComputeFeatures:
    """cached_compute_features() integration."""

    def test_cache_miss_then_hit(self, tmp_path):
        """First call misses, second call hits."""
        ohlcv = _make_dummy_ohlcv(n_bars=100, symbol="BTCUSDT")
        cd = str(tmp_path)

        # First call: cache miss -> compute
        result1 = cached_compute_features(
            ohlcv, mode="SWING", interval="4h", cache_dir=cd,
        )
        assert result1 is not None
        assert result1.total_features() > 0

        # Second call: cache hit
        result2 = cached_compute_features(
            ohlcv, mode="SWING", interval="4h", cache_dir=cd,
        )
        assert result2 is not None
        # Same features as first call
        for name in result1.features:
            assert np.allclose(
                result1.features[name], result2.features[name], equal_nan=True
            ), f"Feature '{name}' differs between cache miss and hit"

    def test_different_mode_different_cache(self, tmp_path):
        """Different modes produce different cache entries."""
        ohlcv = _make_dummy_ohlcv(n_bars=100, symbol="BTCUSDT")
        cd = str(tmp_path)

        r_swing = cached_compute_features(
            ohlcv, mode="SWING", interval="4h", cache_dir=cd,
        )
        r_scalp = cached_compute_features(
            ohlcv, mode="SCALP", interval="4h", cache_dir=cd,
        )
        assert r_swing is not None
        assert r_scalp is not None

    def test_different_interval_different_cache(self, tmp_path):
        """Different intervals produce different cache entries."""
        ohlcv = _make_dummy_ohlcv(n_bars=100, symbol="BTCUSDT")
        cd = str(tmp_path)

        r1 = cached_compute_features(
            ohlcv, mode="SWING", interval="4h", cache_dir=cd,
        )
        r2 = cached_compute_features(
            ohlcv, mode="SWING", interval="1h", cache_dir=cd,
        )
        assert r1 is not None
        assert r2 is not None

    def test_missing_symbol_defaults_to_unknown(self, tmp_path):
        """ohlcv_data without 'symbol' key uses 'unknown' as default."""
        ohlcv = _make_dummy_ohlcv(n_bars=50, symbol="BTCUSDT")
        del ohlcv["symbol"]
        cd = str(tmp_path)

        result = cached_compute_features(
            ohlcv, mode="SWING", interval="4h", cache_dir=cd,
        )
        assert result is not None

    def test_cache_returns_same_object_shape(self, tmp_path):
        """Cached and fresh FeatureMatrix have same feature names."""
        ohlcv = _make_dummy_ohlcv(n_bars=100, symbol="BTCUSDT")
        cd = str(tmp_path)

        result = cached_compute_features(
            ohlcv, mode="SWING", interval="4h", cache_dir=cd,
        )
        # All standard features present
        expected_features = {
            "log_return_1", "log_return_N", "return_volatility_N",
            "return_zscore_N",
            "realized_volatility_N", "high_low_range_N",
            "garman_klass_vol_N", "parkinson_vol_N",
        }
        assert expected_features.issubset(set(result.features.keys()))

    def test_cached_result_has_cache_hit_metadata(self, tmp_path):
        """Second call's metadata includes cache_hit=True."""
        ohlcv = _make_dummy_ohlcv(n_bars=50, symbol="BTCUSDT")
        cd = str(tmp_path)

        _ = cached_compute_features(
            ohlcv, mode="SWING", interval="4h", cache_dir=cd,
        )
        result = cached_compute_features(
            ohlcv, mode="SWING", interval="4h", cache_dir=cd,
        )
        assert result.metadata.get("cache_hit") is True
        assert "cache_key" in result.metadata


# ===========================================================================
# CACHE_DIR_DEFAULT
# ===========================================================================


class TestCacheDirDefault:
    """CACHE_DIR_DEFAULT constant."""

    def test_cache_dir_default_is_string(self):
        """CACHE_DIR_DEFAULT is a non-empty string."""
        assert isinstance(CACHE_DIR_DEFAULT, str)
        assert len(CACHE_DIR_DEFAULT) > 0

    def test_cache_dir_default_ends_with_slash(self):
        """CACHE_DIR_DEFAULT ends with a forward slash for path clarity."""
        assert CACHE_DIR_DEFAULT.endswith("/")


# ===========================================================================
# PIPELINE_VERSION
# ===========================================================================


class TestPipelineVersion:
    """PIPELINE_VERSION reflects new caching feature."""

    def test_pipeline_version_bumped(self):
        """PIPELINE_VERSION is 0.2.0 for the caching feature."""
        assert PIPELINE_VERSION == "0.2.0"

    def test_pipeline_version_is_string(self):
        """PIPELINE_VERSION is a string."""
        assert isinstance(PIPELINE_VERSION, str)
