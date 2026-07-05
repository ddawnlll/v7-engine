"""AlphaForge Feature Pipeline — deterministic causal feature computation.

Authority: AlphaForge owns feature discovery and specification.
This module computes 7 active feature groups from OHLCV data.
Lead-Lag group is DEFERRED (P0.9B cross-sectional data dependency).

Design constraints:
- numpy only (no pandas, scipy, ta-lib)
- no network calls, no exchange APIs, no real market data
- all features are causal: feature at bar[t] uses bars [t-lookback+1 .. t]
- NaN fill for insufficient lookback at series start
- deterministic: same input always produces identical output

Implementation baseline: SWING mode (4h primary, 1d context, 1h refinement).
SCALP and AGGRESSIVE_SCALP feature sets require empirical tuning (HOLD).

Causality contract:
  Every feature at index t accesses data only from indices [max(0, t - window + 1), t].
  No index > t is ever accessed. This is verified by no-revision leakage tests:
  adding bar N+1 must not change feature values at bars [0, N-1].
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from alphaforge.features.orderbook import (
    DEFAULT_AMIHUD_WINDOW,
    DEFAULT_DEPTH_RATIO_WINDOW,
    DEFAULT_LIQUIDITY_VACUUM_WINDOW,
    DEFAULT_MICROPRICE_WINDOW,
    DEFAULT_MULTI_LEVEL_OBI_N,
    DEFAULT_MULTI_LEVEL_OBI_STEP,
    DEFAULT_MULTI_LEVEL_OBI_DECAY,
    DEFAULT_NOISE_WINDOW,
    DEFAULT_OFI_WINDOW,
    DEFAULT_ORDERBOOK_WINDOW,
    DEFAULT_PRICE_IMPACT_WINDOW,
    DEFAULT_QUOTED_SPREAD_WINDOW,
    DEFAULT_ROLL_SPREAD_WINDOW,
    DEFAULT_SERIAL_CORR_WINDOW,
    DEFAULT_STOIKOV_MICRO_PRICE_WINDOW,
    DEFAULT_TRADE_COUNT_WINDOW,
    DEFAULT_VAMP_WINDOW,
    DEFAULT_VOLUME_CONCENTRATION_WINDOW,
    DEFAULT_VPIN_WINDOW,
    DEFAULT_VWAP_MID_WINDOW,
    compute_orderbook_group,
)
from alphaforge.features.regime import (
    AGGRESSIVE_SCALP_CUSUM_THRESHOLD,
    AGGRESSIVE_SCALP_HMM_VOL_WINDOW,
    AGGRESSIVE_SCALP_VOL_REGIME_WINDOW,
    SCALP_CUSUM_THRESHOLD,
    SCALP_HMM_VOL_WINDOW,
    SCALP_VOL_REGIME_WINDOW,
    SWING_CUSUM_THRESHOLD,
    SWING_HMM_VOL_WINDOW,
    SWING_VOL_REGIME_WINDOW,
    compute_regime_group,
)
from alphaforge.features.candle_pattern import (
    DEFAULT_CANDLE_WINDOW,
    compute_candle_pattern_group,
)

try:
    from numba import njit
except ImportError:
    njit = lambda x: x

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PIPELINE_VERSION: str = "0.2.0"

# Default cache directory for feature matrices
# Resolved to absolute path at module load time to prevent working-directory confusion.
_CACHE_DIR_RELATIVE: str = ".cache/features/"
CACHE_DIR_DEFAULT: str = str(
    Path(__file__).resolve().parent.parent.parent.parent / _CACHE_DIR_RELATIVE
)

# Process-lifetime secret for cache integrity HMAC signing.
# Generated once at import time — cache files from other processes or
# tampered files are detected on read.
_CACHE_INTEGRITY_SECRET: bytes = os.urandom(32)

# SWING mode defaults (4h primary bars)
# periods_per_year for 4h bars: 365 days * 6 bars/day = 2190
SWING_PERIODS_PER_YEAR: int = 2190
SWING_N_RETURNS: int = 10
SWING_VOLATILITY_WINDOW: int = 20
SWING_ATR_WINDOW: int = 14
SWING_MOMENTUM_N: int = 10
SWING_RSI_WINDOW: int = 14
SWING_MACD_FAST: int = 12
SWING_MACD_SLOW: int = 26
SWING_MACD_SIGNAL: int = 9
SWING_VOLUME_WINDOW: int = 20
SWING_BREAKOUT_WINDOW: int = 20
SWING_BB_WINDOW: int = 20
SWING_BB_NUM_STD: float = 2.0

# Minimum bars required for any meaningful feature computation
MIN_BARS: int = 2


# ---------------------------------------------------------------------------
# FeatureGroup enum
# ---------------------------------------------------------------------------

class FeatureGroup(Enum):
    """Feature group enumeration.

    LEAD_LAG is marked DEFERRED because it requires cross-sectional data
    across symbols (P0.9B dependency). No compute function is mapped for it.
    REGIME and CANDLE_PATTERN are active optional groups.
    PERPETUAL_FUNDING is reserved for future funding data integration.
    Re-enablement conditions:
      (a) cross-sectional data pipeline available
      (b) correlation computation across symbols validated
      (c) timeframe alignment logic tested with multi-timeframe fixtures
    """
    RETURNS = "returns"
    VOLATILITY = "volatility"
    ATR = "atr"
    MOMENTUM = "momentum"
    VOLUME = "volume"
    BREAKOUT = "breakout"
    ORDERBOOK = "orderbook"
    REGIME = "regime"
    CANDLE_PATTERN = "candle_pattern"
    PERPETUAL_FUNDING = "perpetual_funding"
    LEAD_LAG = "lead_lag"  # DEFERRED — P0.9B cross-sectional data required


# ---------------------------------------------------------------------------
# FeatureMatrix dataclass
# ---------------------------------------------------------------------------

@dataclass
class FeatureMatrix:
    """Structured container for computed feature arrays.

    Attributes:
        features: Dict mapping feature name to numpy array of shape (n_bars,).
            Features are organized by group. Keys match the output of each
            group's compute function. No Lead-Lag keys are present.
        timestamps: Optional index array of same length as each feature array.
            Can be sequential bar indices or ISO timestamp strings.
        symbol: Trading pair identifier (e.g. "BTCUSDT").
        mode: Trading mode (e.g. "SWING").
        feature_group_ids: List of active group identifiers present in features.
        metadata: Additional metadata (version, window params, lookback info).
    """
    features: Dict[str, np.ndarray]
    timestamps: Optional[np.ndarray] = None
    symbol: str = ""
    mode: str = "SWING"
    feature_group_ids: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.feature_group_ids:
            # Infer from active group map
            # Exclude DEFERRED groups: LEAD_LAG and PERPETUAL_FUNDING
            excluded = {FeatureGroup.LEAD_LAG, FeatureGroup.PERPETUAL_FUNDING}
            active = [g.value for g in FeatureGroup if g not in excluded]
            self.feature_group_ids = active
        if not self.metadata:
            self.metadata["pipeline_version"] = PIPELINE_VERSION

    def total_features(self) -> int:
        """Return total number of feature columns."""
        return len(self.features)

    def bar_count(self) -> int:
        """Return number of bars (rows)."""
        if not self.features:
            return 0
        first_key = next(iter(self.features))
        return len(self.features[first_key])


# ---------------------------------------------------------------------------
# FeatureCache — Parquet+Zstd caching for computed feature matrices
# ---------------------------------------------------------------------------


class FeatureCache:
    """Disk-backed cache for computed FeatureMatrix objects.

    Cache key = sha256(symbol | interval | mode | PIPELINE_VERSION).
    Stores features as PyArrow Parquet columns with Zstd compression.
    Loads with memory_map=True for zero-copy access.

    Cache invalidation is implicit: when PIPELINE_VERSION changes, the
    cache key changes, producing a cache miss rather than stale data.
    Thread-safe on write via a per-instance threading.Lock.

    Usage:
        cache = FeatureCache(cache_dir=\".cache/features/\")
        cached = cache.get(\"BTCUSDT\", \"4h\", \"SWING\")
        if cached is None:
            matrix = compute_features(ohlcv, mode=\"SWING\")
            cache.put(\"BTCUSDT\", \"4h\", \"SWING\", matrix)
            return matrix
        return cached
    """

    def __init__(self, cache_dir: str = CACHE_DIR_DEFAULT) -> None:
        self._cache_dir = cache_dir
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Cache key computation
    # ------------------------------------------------------------------

    def _cache_key(self, symbol: str, interval: str, mode: str) -> str:
        """Compute deterministic SHA-256 cache key.

        Incorporates symbol, interval, mode, and PIPELINE_VERSION so that
        changing any of these produces a distinct cache entry.

        Args:
            symbol: Trading pair identifier (e.g. \"BTCUSDT\").
            interval: Bar interval string (e.g. \"4h\", \"1h\", \"15m\").
            mode: Trading mode (\"SWING\", \"SCALP\", \"AGGRESSIVE_SCALP\").

        Returns:
            Hex-encoded SHA-256 digest.
        """
        raw = f"{symbol}|{interval}|{mode}|{PIPELINE_VERSION}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _cache_path(self, key: str) -> Path:
        """Return Path to the parquet cache file for a given key."""
        return Path(self._cache_dir) / f"{key}.parquet.zstd"

    # ------------------------------------------------------------------
    # Integrity verification (HMAC-SHA256)
    # ------------------------------------------------------------------

    @staticmethod
    def _sign_metadata(meta: Dict[str, str]) -> str:
        """Compute HMAC-SHA256 tag over sorted metadata for integrity.

        The tag is stored in the Parquet schema metadata so that
        tampered or foreign cache files are detected on read.

        Returns hex-encoded HMAC-SHA256 digest.
        """
        payload = "".join(f"{k}={v}|" for k, v in sorted(meta.items()))
        return hmac.new(
            _CACHE_INTEGRITY_SECRET, payload.encode(), "sha256"
        ).hexdigest()

    @staticmethod
    def _verify_metadata(meta: Dict[str, str], tag: str) -> bool:
        """Verify HMAC-SHA256 tag matches metadata.

        Args:
            meta: Metadata dictionary (without the 'hmac' key).
            tag: Expected hex-encoded HMAC-SHA256 digest.

        Returns:
            True if tag matches, False otherwise.
        """
        expected = FeatureCache._sign_metadata(meta)
        return hmac.compare_digest(expected, tag)

    # ------------------------------------------------------------------
    # Read / Write
    # ------------------------------------------------------------------

    def get(
        self, symbol: str, interval: str, mode: str
    ) -> Optional[FeatureMatrix]:
        """Load cached FeatureMatrix if it exists and version matches.

        Uses PyArrow's memory_map=True for zero-copy Parquet reading.
        Returns None on cache miss (file missing, corrupt, or version mismatch).

        Args:
            symbol: Trading pair identifier.
            interval: Bar interval string.
            mode: Trading mode.

        Returns:
            FeatureMatrix if cache hit, None otherwise.
        """
        key = self._cache_key(symbol, interval, mode)
        path = self._cache_path(key)

        if not path.exists():
            return None

        try:
            table = pq.read_table(str(path), memory_map=True)
            features: Dict[str, np.ndarray] = {}
            for col_name in table.column_names:
                col_array = table.column(col_name).to_numpy()
                features[col_name] = col_array

            # Reconstruct metadata from Parquet schema metadata
            metadata: Dict[str, str] = {}
            if table.schema.metadata is not None:
                for k, v in table.schema.metadata.items():
                    metadata[k.decode()] = v.decode()

            # Restore pipeline_version if missing from metadata
            if "pipeline_version" not in metadata:
                metadata["pipeline_version"] = PIPELINE_VERSION

            # Verify HMAC integrity signature — reject files without HMAC
            # (legacy caches from before v0.2.0) or with wrong HMAC (tampered).
            stored_hmac = metadata.pop("hmac", None)
            if stored_hmac is None:
                logger.info(
                    "Cache missing HMAC integrity tag for %s/%s/%s — "
                    "treating as miss (legacy format)",
                    symbol, interval, mode,
                )
                return None
            if not self._verify_metadata(metadata, stored_hmac):
                logger.warning(
                    "Cache integrity check failed for %s/%s/%s — "
                    "file may be tampered or from a different process",
                    symbol, interval, mode,
                )
                return None

            # Parse feature_group_ids from JSON
            fg_ids_raw = metadata.get("feature_group_ids", "[]")
            try:
                fg_ids: List[str] = json.loads(fg_ids_raw)
            except (json.JSONDecodeError, TypeError):
                fg_ids = []

            # Parse n_bars and total_features if stored
            n_bars = metadata.get("n_bars", str(len(next(iter(features.values()))) if features else "0"))
            total_features = metadata.get("total_features", str(len(features)))

            # Build result metadata: start with all loaded metadata, then
            # overlay cache-specific fields with typed values.
            result_metadata: Dict = dict(metadata)
            result_metadata.update({
                "pipeline_version": metadata.get("pipeline_version", PIPELINE_VERSION),
                "n_bars": int(n_bars),
                "total_features": int(total_features),
                "cache_hit": True,
                "cache_key": key,
            })

            return FeatureMatrix(
                features=features,
                timestamps=None,
                symbol=metadata.get("symbol", symbol),
                mode=metadata.get("mode", mode),
                feature_group_ids=fg_ids,
                metadata=result_metadata,
            )
        except Exception as e:
            logger.warning("Cache read failed for key %s: %s", key, e)
            return None

    def put(
        self,
        symbol: str,
        interval: str,
        mode: str,
        matrix: FeatureMatrix,
    ) -> None:
        """Store FeatureMatrix to cache as Parquet+Zstd file.

        Thread-safe: only one writer at a time per FeatureCache instance.

        Args:
            symbol: Trading pair identifier.
            interval: Bar interval string.
            mode: Trading mode.
            matrix: FeatureMatrix to cache.
        """
        key = self._cache_key(symbol, interval, mode)
        path = self._cache_path(key)

        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)

            # Build PyArrow arrays from feature dict
            field_names: List[str] = []
            arrays: List[pa.Array] = []
            for name in sorted(matrix.features.keys()):
                arr = matrix.features[name]
                # Ensure float64 for consistent storage
                if arr.dtype != np.float64:
                    arr = arr.astype(np.float64)
                arrays.append(pa.array(arr))
                field_names.append(name)

            # Build metadata dict
            meta: Dict[str, str] = {
                "symbol": matrix.symbol or symbol,
                "mode": matrix.mode or mode,
                "interval": interval,
                "pipeline_version": PIPELINE_VERSION,
                "feature_group_ids": json.dumps(matrix.feature_group_ids),
                "n_bars": str(matrix.bar_count()),
                "total_features": str(matrix.total_features()),
            }
            if matrix.metadata:
                for k, v in matrix.metadata.items():
                    meta[str(k)] = str(v)

            # HMAC integrity signature (signs over all keys EXCEPT hmac itself)
            meta["hmac"] = self._sign_metadata(
                {k: v for k, v in meta.items() if k != "hmac"}
            )

            # Build schema — handle empty feature dict (no columns)
            if field_names:
                schema = pa.schema(
                    [pa.field(name, pa.float64()) for name in field_names],
                    metadata={k.encode(): v.encode() for k, v in meta.items()},
                )
                table = pa.Table.from_arrays(arrays, schema=schema)
            else:
                # Empty table: no columns, only schema metadata
                schema = pa.schema(
                    [],
                    metadata={k.encode(): v.encode() for k, v in meta.items()},
                )
                table = pa.Table.from_batches([], schema=schema)

            pq.write_table(table, str(path), compression="ZSTD")

            logger.info(
                "Cached %d features (%d bars) to %s [%s/%s/%s]",
                len(field_names), matrix.bar_count(), path,
                symbol, interval, mode,
            )

    # ------------------------------------------------------------------
    # Manual invalidation
    # ------------------------------------------------------------------

    def invalidate(self, symbol: str, interval: str, mode: str) -> bool:
        """Remove cached entry for given parameters.

        Useful for force-recompute or clearing stale data.

        Args:
            symbol: Trading pair identifier.
            interval: Bar interval string.
            mode: Trading mode.

        Returns:
            True if a file was removed, False if no cache existed.
        """
        key = self._cache_key(symbol, interval, mode)
        path = self._cache_path(key)
        if path.exists():
            path.unlink()
            logger.info("Invalidated cache for %s/%s/%s", symbol, interval, mode)
            return True
        return False

    def clear_all(self) -> int:
        """Remove all cached feature files from the cache directory.

        Returns:
            Number of removed files.
        """
        cache_dir = Path(self._cache_dir)
        if not cache_dir.exists():
            return 0
        count = 0
        for f in cache_dir.glob("*.parquet.zstd"):
            f.unlink()
            count += 1
        if count > 0:
            logger.info("Cleared %d cache files from %s", count, self._cache_dir)
        return count


# ---------------------------------------------------------------------------
# Map of active feature groups to their compute functions.
# LEAD_LAG is intentionally absent — no compute function exists.
# ---------------------------------------------------------------------------

FEATURE_GROUP_MAP: Dict[FeatureGroup, str] = {
    FeatureGroup.RETURNS: "compute_returns_group",
    FeatureGroup.VOLATILITY: "compute_volatility_group",
    FeatureGroup.ATR: "compute_atr_group",
    FeatureGroup.MOMENTUM: "compute_momentum_group",
    FeatureGroup.VOLUME: "compute_volume_group",
    FeatureGroup.BREAKOUT: "compute_breakout_group",
    FeatureGroup.ORDERBOOK: "compute_orderbook_group",
    FeatureGroup.REGIME: "compute_regime_group",
    FeatureGroup.CANDLE_PATTERN: "compute_candle_pattern_group",
    FeatureGroup.PERPETUAL_FUNDING: "compute_perpetual_funding_group",
    # LEAD_LAG is mapped but DEFERRED — compute_features does not call it.
    # Active filtering (lines 119, 1257) keeps LEAD_LAG out of computation
    # until cross-sectional data support lands (P0.9B).
    FeatureGroup.LEAD_LAG: "compute_lead_lag_group",
}


# ===========================================================================
# Utility functions (causal, numpy-only)
# ===========================================================================

def _validate_ohlcv_data(ohlcv_data: dict) -> None:
    """Validate that required OHLCV columns are present and are numpy arrays."""
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(ohlcv_data.keys())
    if missing:
        raise ValueError(f"Missing required OHLCV columns: {missing}")

    for col in required:
        arr = ohlcv_data[col]
        if not isinstance(arr, np.ndarray):
            raise TypeError(f"Column '{col}' must be numpy.ndarray, got {type(arr).__name__}")
        if arr.ndim != 1:
            raise ValueError(f"Column '{col}' must be 1D array, got {arr.ndim}D")

    # Check length consistency
    lengths = {col: len(ohlcv_data[col]) for col in required}
    if len(set(lengths.values())) != 1:
        raise ValueError(f"OHLCV columns have inconsistent lengths: {lengths}")

    n = lengths["close"]
    if n < MIN_BARS:
        raise ValueError(f"Need at least {MIN_BARS} bars, got {n}")

    # Check for negative prices
    for col in ["open", "high", "low", "close"]:
        if np.any(ohlcv_data[col] < 0):
            raise ValueError(f"Column '{col}' contains negative values — invalid price data")

    # Check high >= low for each bar
    if np.any(ohlcv_data["high"] < ohlcv_data["low"]):
        raise ValueError("Some bars have high < low — invalid OHLC data")

    # Check for NaN in input and log warning
    for col in required:
        nan_count = int(np.sum(np.isnan(ohlcv_data[col])))
        if nan_count > 0:
            logger.warning(f"Column '{col}' contains {nan_count} NaN values — these will propagate")


def _rolling_mean(arr: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling mean over `window` bars (NaN-safe).

    Result at index t uses arr[t-window+1 .. t] (causal).
    Returns NaN for t < window-1 or when the window contains insufficient
    non-NaN values (fewer than 2 valid samples).

    NaN values in the input are excluded from the mean computation
    (partial window mean). If all values in the window are NaN, the
    result is NaN.
    """
    n = len(arr)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result
    for i in range(window - 1, n):
        seg = arr[i - window + 1 : i + 1]
        valid = seg[~np.isnan(seg)]
        if len(valid) >= 2:
            result[i] = np.mean(valid.astype(np.float64))
    return result


def _rolling_std(arr: np.ndarray, window: int, ddof: int = 1) -> np.ndarray:
    """Compute rolling standard deviation over `window` bars (NaN-safe).

    Causal: std at index t uses arr[t-window+1 .. t].
    Returns NaN for t < window-1 or when fewer than 2 non-NaN values
    are in the window.

    NaN values in the input are excluded (partial window std).
    """
    n = len(arr)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result
    for i in range(window - 1, n):
        seg = arr[i - window + 1 : i + 1]
        valid = seg[~np.isnan(seg)]
        if len(valid) >= 2:
            result[i] = np.std(valid.astype(np.float64), ddof=ddof)
    return result


def _rolling_max(arr: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling maximum over `window` bars (causal)."""
    n = len(arr)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result
    for i in range(window - 1, n):
        result[i] = np.max(arr[i - window + 1 : i + 1])
    return result


def _rolling_min(arr: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling minimum over `window` bars (causal)."""
    n = len(arr)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result
    for i in range(window - 1, n):
        result[i] = np.min(arr[i - window + 1 : i + 1])
    return result


@njit
def _ema(arr: np.ndarray, period: int) -> np.ndarray:
    """Compute Exponential Moving Average (causal, numpy-only).

    EMA[t] = arr[t] * k + EMA[t-1] * (1 - k)  where k = 2/(period+1).
    Seeded at first non-NaN value.
    Returns NaN for t < period-1 to match convention.
    """
    n = len(arr)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < period:
        return result
    k = 2.0 / (period + 1.0)
    # Seed with SMA of first `period` values
    seed = np.mean(arr[:period].astype(np.float64))
    result[period - 1] = seed
    for i in range(period, n):
        if np.isnan(arr[i]):
            result[i] = result[i - 1]
        else:
            result[i] = arr[i] * k + result[i - 1] * (1.0 - k)
    return result


@njit
def _linear_regression_slope(y: np.ndarray) -> float:
    """Compute linear regression slope of y vs index [0, 1, ..., len(y)-1].

    Returns 0.0 if variance is zero or insufficient data.
    """
    n = len(y)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=np.float64)
    x_mean = np.mean(x)
    y_mean = np.mean(y.astype(np.float64))
    numerator = np.sum((x - x_mean) * (y.astype(np.float64) - y_mean))
    denominator = np.sum((x - x_mean) ** 2)
    if denominator == 0:
        return 0.0
    return numerator / denominator


# ===========================================================================
# Returns Group
# ===========================================================================

def compute_log_return_1(close: np.ndarray) -> np.ndarray:
    """Compute 1-bar log returns.

    r[t] = ln(close[t] / close[t-1]) for t >= 1.
    NaN at t=0.

    Causality: uses close[t] and close[t-1] only. No future access.
    """
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < 2:
        return result
    with np.errstate(divide="ignore", invalid="ignore"):
        result[1:] = np.log(close[1:] / close[:-1])
    return result


def compute_log_return_N(close: np.ndarray, n: int) -> np.ndarray:
    """Compute N-bar log returns.

    r[t] = ln(close[t] / close[t-n]) for t >= n.
    NaN for t < n.

    Causality: uses close[t] and close[t-n] only.
    """
    length = len(close)
    result = np.full(length, np.nan, dtype=np.float64)
    if length <= n:
        return result
    with np.errstate(divide="ignore", invalid="ignore"):
        result[n:] = np.log(close[n:] / close[:-n])
    return result


def compute_return_volatility(returns: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling standard deviation of log returns.

    Uses `window` bars of log returns to compute rolling std.
    NaN for t < window.

    Causality: std at t uses returns[t-window+1 .. t].
    """
    return _rolling_std(returns, window, ddof=1)


def compute_return_zscore(returns: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling z-score of log returns.

    z[t] = (r[t] - mean(r[t-window:t])) / std(r[t-window:t]).
    NaN for t < window or when std is zero.

    Causality: mean and std at t use only bars up to t.
    """
    n = len(returns)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result
    for i in range(window - 1, n):
        seg = returns[i - window + 1 : i + 1]
        seg_clean = seg[~np.isnan(seg)]
        if len(seg_clean) < 2:
            result[i] = np.nan
            continue
        mu = np.mean(seg_clean)
        sigma = np.std(seg_clean, ddof=1)
        if sigma < 1e-12:
            result[i] = 0.0
        else:
            result[i] = (returns[i] - mu) / sigma
    return result


def compute_returns_group(
    close: np.ndarray,
    n: int = SWING_N_RETURNS,
    window: int = SWING_VOLATILITY_WINDOW,
) -> Dict[str, np.ndarray]:
    """Compute all Returns group features.

    Returns dict with keys: log_return_1, log_return_N, return_volatility_N, return_zscore_N.
    All arrays are same length as input.
    NaN fill at start for insufficient lookback.
    """
    log_ret_1 = compute_log_return_1(close)
    log_ret_n = compute_log_return_N(close, n)
    ret_vol = compute_return_volatility(log_ret_1, window)
    ret_zscore = compute_return_zscore(log_ret_1, window)

    return {
        "log_return_1": log_ret_1,
        "log_return_N": log_ret_n,
        "return_volatility_N": ret_vol,
        "return_zscore_N": ret_zscore,
    }


# ===========================================================================
# Volatility Group
# ===========================================================================

def compute_realized_volatility(
    close: np.ndarray,
    window: int = SWING_VOLATILITY_WINDOW,
    periods_per_year: int = SWING_PERIODS_PER_YEAR,
) -> np.ndarray:
    """Compute annualized realized volatility from close prices.

    Formula: std(log_returns[t-window:t]) * sqrt(periods_per_year).
    For SWING 4h bars: periods_per_year = 365 * 6 = 2190.
    NaN for t < window.

    Causality: uses log_returns up to index t.
    """
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window + 1:
        return result
    log_ret = compute_log_return_1(close)
    for i in range(window, n):  # Need window returns, so start at window
        seg = log_ret[i - window + 1 : i + 1]  # window returns
        seg_clean = seg[~np.isnan(seg)]
        if len(seg_clean) < 2:
            result[i] = np.nan
        else:
            result[i] = np.std(seg_clean, ddof=1) * np.sqrt(periods_per_year)
    return result


def compute_high_low_range(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    window: int = SWING_VOLATILITY_WINDOW,
) -> np.ndarray:
    """Compute rolling mean of normalized high-low range.

    Formula: rolling mean of (high - low) / close over `window` bars.
    NaN for t < window.

    Causality: at t uses bars [t-window+1 .. t].
    """
    n = len(high)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result
    with np.errstate(divide="ignore", invalid="ignore"):
        hl_ratio = (high - low) / np.where(close == 0, np.nan, close)
    for i in range(window - 1, n):
        seg = hl_ratio[i - window + 1 : i + 1]
        seg_clean = seg[~np.isnan(seg)]
        if len(seg_clean) > 0:
            result[i] = np.mean(seg_clean)
    return result


def compute_garman_klass_vol(
    open_arr: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    window: int = SWING_VOLATILITY_WINDOW,
) -> np.ndarray:
    """Compute Garman-Klass volatility estimator.

    Formula: sqrt(1/N * sum(0.5 * ln(H/L)^2 - (2*ln(2)-1) * ln(C/O)^2)).
    NaN for t < window.

    Causality: at t uses bars [t-window+1 .. t].
    """
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result

    # Precompute per-bar terms
    # Avoid division by zero: if any price is 0, the bar term is NaN
    with np.errstate(divide="ignore", invalid="ignore"):
        hl_term = 0.5 * (np.log(high / low)) ** 2
        co_term = (2.0 * np.log(2.0) - 1.0) * (np.log(close / open_arr)) ** 2

    for i in range(window - 1, n):
        seg_hl = hl_term[i - window + 1 : i + 1]
        seg_co = co_term[i - window + 1 : i + 1]
        # Skip bars where either term is NaN
        valid = ~(np.isnan(seg_hl) | np.isnan(seg_co))
        if np.sum(valid) < 2:
            continue
        gk_sum = np.sum(seg_hl[valid] - seg_co[valid])
        if gk_sum < 0:
            # Clamp to 0 — negative variance is invalid
            result[i] = 0.0
        else:
            result[i] = np.sqrt(gk_sum / np.sum(valid))
    return result


def compute_parkinson_vol(
    high: np.ndarray,
    low: np.ndarray,
    window: int = SWING_VOLATILITY_WINDOW,
) -> np.ndarray:
    """Compute Parkinson volatility estimator (high-low only).

    Formula: sqrt(1/(4*N*ln(2)) * sum(ln(H/L)^2)).
    Always non-negative. Uses only high/low (not close-dependent).
    NaN for t < window.

    Causality: at t uses bars [t-window+1 .. t].
    """
    n = len(high)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result

    with np.errstate(divide="ignore", invalid="ignore"):
        hl_sq = np.log(high / low) ** 2

    denom = 4.0 * np.log(2.0)  # constant factor
    for i in range(window - 1, n):
        seg = hl_sq[i - window + 1 : i + 1]
        seg_clean = seg[~np.isnan(seg)]
        if len(seg_clean) < 2:
            continue
        result[i] = np.sqrt(np.sum(seg_clean) / (denom * len(seg_clean)))
    return result


def compute_volatility_group(
    open_arr: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    window: int = SWING_VOLATILITY_WINDOW,
) -> Dict[str, np.ndarray]:
    """Compute all Volatility group features.

    Returns dict with keys: high_low_range_N, garman_klass_vol_N, parkinson_vol_N.
    realized_volatility_N removed because it is identical (r=1.0) to
    return_volatility_N (computed in the returns group).
    All arrays same length as input. NaN at start for insufficient lookback.
    """
    return {
        "high_low_range_N": compute_high_low_range(high, low, close, window),
        "garman_klass_vol_N": compute_garman_klass_vol(open_arr, high, low, close, window),
        "parkinson_vol_N": compute_parkinson_vol(high, low, window),
    }


# ===========================================================================
# ATR Group
# ===========================================================================

def compute_true_range(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
) -> np.ndarray:
    """Compute True Range for each bar.

    TR[t] = max(high[t] - low[t], |high[t] - close[t-1]|, |low[t] - close[t-1]|).
    TR[0] = high[0] - low[0] (no prior close available).

    Causality: at t uses high[t], low[t], close[t], close[t-1].
    """
    n = len(high)
    result = np.full(n, np.nan, dtype=np.float64)
    if n == 0:
        return result

    result[0] = high[0] - low[0]
    if n == 1:
        return result

    for i in range(1, n):
        a = high[i] - low[i]
        b = abs(high[i] - close[i - 1])
        c = abs(low[i] - close[i - 1])
        result[i] = max(a, b, c)
    return result


def compute_atr(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    window: int = SWING_ATR_WINDOW,
) -> np.ndarray:
    """Compute Average True Range using simple rolling mean of TR.

    ATR[t] = mean(TR[t-window+1 .. t]).
    NaN for t < window.

    Causality: uses TR up to index t.
    """
    tr = compute_true_range(high, low, close)
    return _rolling_mean(tr, window)


def compute_atr_pct(atr: np.ndarray, close: np.ndarray) -> np.ndarray:
    """Compute ATR as percentage of close price.

    atr_pct[t] = ATR[t] / close[t] * 100.
    NaN where ATR is NaN.
    """
    n = len(atr)
    result = np.full(n, np.nan, dtype=np.float64)
    valid = ~np.isnan(atr) & (close != 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        result[valid] = atr[valid] / close[valid] * 100.0
    return result


def compute_atr_expansion(atr: np.ndarray, window: int = SWING_ATR_WINDOW) -> np.ndarray:
    """Compute ATR expansion/contraction ratio.

    atr_expansion[t] = ATR[t] / SMA(ATR, window)[t].
    > 1 when ATR exceeds its SMA (expanding volatility).
    < 1 when ATR contracts.
    NaN at start for insufficient lookback.

    Causality: SMA at t uses ATR up to t.
    """
    atr_sma = _rolling_mean(atr, window)
    n = len(atr)
    result = np.full(n, np.nan, dtype=np.float64)
    valid = ~np.isnan(atr) & ~np.isnan(atr_sma) & (atr_sma != 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        result[valid] = atr[valid] / atr_sma[valid]
    return result


def compute_atr_group(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    window: int = SWING_ATR_WINDOW,
) -> Dict[str, np.ndarray]:
    """Compute all ATR group features.

    Returns dict with keys: atr_N, atr_pct_N, atr_expansion_N.
    All arrays same length as input. NaN at start.
    """
    atr_arr = compute_atr(high, low, close, window)
    return {
        "atr_N": atr_arr,
        "atr_pct_N": compute_atr_pct(atr_arr, close),
        "atr_expansion_N": compute_atr_expansion(atr_arr, window),
    }


# ===========================================================================
# Momentum Group
# ===========================================================================

def compute_momentum_N(close: np.ndarray, n: int = SWING_MOMENTUM_N) -> np.ndarray:
    """Compute raw momentum: price change over N bars.

    momentum[t] = close[t] - close[t-n].
    NaN for t < n.

    Causality: uses close[t] and close[t-n].
    """
    length = len(close)
    result = np.full(length, np.nan, dtype=np.float64)
    if length <= n:
        return result
    for i in range(n, length):
        result[i] = close[i] - close[i - n]
    return result


def compute_roc_N(close: np.ndarray, n: int = SWING_MOMENTUM_N) -> np.ndarray:
    """Compute Rate of Change over N bars.

    roc[t] = (close[t] / close[t-n] - 1) * 100.
    NaN for t < n.

    Causality: uses close[t] and close[t-n].
    """
    length = len(close)
    result = np.full(length, np.nan, dtype=np.float64)
    if length <= n:
        return result
    for i in range(n, length):
        if close[i - n] == 0:
            result[i] = np.nan
        else:
            result[i] = (close[i] / close[i - n] - 1.0) * 100.0
    return result


@njit
def compute_rsi(close: np.ndarray, window: int = SWING_RSI_WINDOW) -> np.ndarray:
    """Compute Wilder's Relative Strength Index.

    Uses smoothed average gains and losses:
      avg_gain[t] = (avg_gain[t-1] * (window-1) + gain[t]) / window
      avg_loss[t] = (avg_loss[t-1] * (window-1) + loss[t]) / window
      rs = avg_gain / avg_loss
      rsi = 100 - 100 / (1 + rs)

    Values in [0, 100]. RSI=100 when no down moves.
    NaN for t < window.

    Causality: RSI at t uses gain[t] and loss[t] from close[t]-close[t-1].
    """
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window + 1:
        return result

    # Compute per-bar changes
    delta = np.zeros(n, dtype=np.float64)
    delta[1:] = close[1:] - close[:-1]

    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    # Seed with simple average of first `window` gains/losses
    avg_gain = np.mean(gain[1 : window + 1])
    avg_loss = np.mean(loss[1 : window + 1])

    if avg_loss == 0:
        result[window] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[window] = 100.0 - 100.0 / (1.0 + rs)

    # Wilder's smoothing
    for i in range(window + 1, n):
        avg_gain = (avg_gain * (window - 1) + gain[i]) / window
        avg_loss = (avg_loss * (window - 1) + loss[i]) / window
        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100.0 - 100.0 / (1.0 + rs)

    return result


def compute_macd(
    close: np.ndarray,
    fast: int = SWING_MACD_FAST,
    slow: int = SWING_MACD_SLOW,
    signal: int = SWING_MACD_SIGNAL,
) -> Dict[str, np.ndarray]:
    """Compute MACD (Moving Average Convergence Divergence).

    macd_line = EMA(close, fast) - EMA(close, slow)
    signal_line = EMA(macd_line, signal)
    histogram = macd_line - signal_line

    Positive histogram = macd_line above signal_line (bullish).
    Negative histogram = bearish.
    NaN for t < slow.

    Causality: EMA at t uses close up to t. Recursive and causal by construction.
    """
    n = len(close)
    nan_arr = np.full(n, np.nan, dtype=np.float64)

    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)

    # MACD line = EMA_fast - EMA_slow
    macd_line = nan_arr.copy()
    valid = ~np.isnan(ema_fast) & ~np.isnan(ema_slow)
    macd_line[valid] = ema_fast[valid] - ema_slow[valid]

    # Signal line = EMA of MACD line
    # Start EMA from the first non-NaN MACD value (at slow-1)
    start_idx = slow - 1  # EMA_slow is first valid here
    if n <= start_idx:
        return {"macd": nan_arr, "macd_signal": nan_arr, "macd_histogram": nan_arr}

    signal_line = _ema(macd_line[start_idx:], signal)
    signal_line_full = nan_arr.copy()
    # Align: signal_line[0] corresponds to macd_line[start_idx + signal - 1]
    signal_start = start_idx + signal - 1
    if signal_start < n:
        signal_line_full[signal_start:] = signal_line[: n - signal_start]

    # Histogram
    histogram = nan_arr.copy()
    valid_h = ~np.isnan(macd_line) & ~np.isnan(signal_line_full)
    histogram[valid_h] = macd_line[valid_h] - signal_line_full[valid_h]

    return {
        "macd": macd_line,
        "macd_signal": signal_line_full,
        "macd_histogram": histogram,
    }


def compute_momentum_group(
    close: np.ndarray,
    n: int = SWING_MOMENTUM_N,
    rsi_window: int = SWING_RSI_WINDOW,
    macd_fast: int = SWING_MACD_FAST,
    macd_slow: int = SWING_MACD_SLOW,
    macd_signal: int = SWING_MACD_SIGNAL,
) -> Dict[str, np.ndarray]:
    """Compute all Momentum group features.

    Returns dict with keys: momentum_N, rsi_N, macd, macd_signal, macd_histogram.
    roc_N removed because it is redundant with log_return_N (r=0.999).
    All arrays same length as input. NaN at start.
    """
    macd_result = compute_macd(close, macd_fast, macd_slow, macd_signal)
    return {
        "momentum_N": compute_momentum_N(close, n),
        "rsi_N": compute_rsi(close, rsi_window),
        "macd": macd_result["macd"],
        "macd_signal": macd_result["macd_signal"],
        "macd_histogram": macd_result["macd_histogram"],
    }


# ===========================================================================
# Volume Group
# ===========================================================================

def compute_volume_ratio(
    volume: np.ndarray,
    window: int = SWING_VOLUME_WINDOW,
) -> np.ndarray:
    """Compute volume ratio: current volume vs. N-bar average.

    volume_ratio[t] = volume[t] / mean(volume[t-window:t]).
    NaN for t < window.

    Causality: at t uses volume bars up to t.
    """
    n = len(volume)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result
    vol_mean = _rolling_mean(volume, window)
    valid = ~np.isnan(vol_mean) & (vol_mean != 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        result[valid] = volume[valid] / vol_mean[valid]
    return result


def compute_volume_trend(
    volume: np.ndarray,
    window: int = SWING_VOLUME_WINDOW,
) -> np.ndarray:
    """Compute volume trend: linear regression slope over rolling window.

    Positive slope = increasing volume trend.
    Negative slope = decreasing volume trend.
    NaN for t < window.

    Causality: at t uses volume bars up to t.
    """
    n = len(volume)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result
    for i in range(window - 1, n):
        seg = volume[i - window + 1 : i + 1]
        result[i] = _linear_regression_slope(seg)
    return result


def compute_vwap_deviation(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
) -> np.ndarray:
    """Compute deviation from cumulative VWAP.

    VWAP[t] = cumulative(typical_price * volume) / cumulative(volume)
    typical_price = (high + low + close) / 3
    deviation[t] = (close[t] - VWAP[t]) / VWAP[t].
    0 when close == VWAP. Negative when close < VWAP.

    Causality: VWAP at t uses all bars from 0 to t (cumulative).
    """
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)
    if n == 0:
        return result

    tp = (high.astype(np.float64) + low.astype(np.float64) + close.astype(np.float64)) / 3.0
    cum_pv = 0.0
    cum_v = 0.0

    for i in range(n):
        cum_pv += tp[i] * volume[i]
        cum_v += volume[i]
        if cum_v == 0:
            result[i] = np.nan
        else:
            vwap = cum_pv / cum_v
            if vwap == 0:
                result[i] = np.nan
            else:
                result[i] = (close[i] - vwap) / vwap
    return result


def compute_obv(
    close: np.ndarray,
    volume: np.ndarray,
) -> np.ndarray:
    """Compute On-Balance Volume (cumulative).

    OBV[0] = 0.
    OBV[t] = OBV[t-1] + volume[t] if close[t] > close[t-1]
    OBV[t] = OBV[t-1] - volume[t] if close[t] < close[t-1]
    OBV[t] = OBV[t-1] if close[t] == close[t-1]

    Causality: at t uses close[t], close[t-1], volume[t] only.
    """
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)
    if n == 0:
        return result
    result[0] = 0.0
    if n == 1:
        return result
    for i in range(1, n):
        if close[i] > close[i - 1]:
            result[i] = result[i - 1] + volume[i]
        elif close[i] < close[i - 1]:
            result[i] = result[i - 1] - volume[i]
        else:
            result[i] = result[i - 1]
    return result


def compute_volume_group(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    window: int = SWING_VOLUME_WINDOW,
) -> Dict[str, np.ndarray]:
    """Compute all Volume group features.

    Returns dict with keys: volume_ratio_N, volume_trend_N, vwap_deviation, obv_N.
    All arrays same length as input. NaN at start where applicable.
    """
    return {
        "volume_ratio_N": compute_volume_ratio(volume, window),
        "volume_trend_N": compute_volume_trend(volume, window),
        "vwap_deviation": compute_vwap_deviation(high, low, close, volume),
        "obv_N": compute_obv(close, volume),
    }


# ===========================================================================
# Breakout Group
# ===========================================================================

def compute_bollinger_bands(
    close: np.ndarray,
    window: int = SWING_BB_WINDOW,
    num_std: float = SWING_BB_NUM_STD,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute Bollinger Bands.

    middle = SMA(close, window)
    upper = middle + num_std * rolling_std(close, window)
    lower = middle - num_std * rolling_std(close, window)

    Returns (upper, middle, lower). All NaN for t < window-1.

    Causality: at t uses close[t-window+1 .. t].
    """
    middle = _rolling_mean(close, window)
    roll_std = _rolling_std(close, window, ddof=1)
    upper = middle + num_std * roll_std
    lower = middle - num_std * roll_std
    return upper, middle, lower


def compute_bb_position(
    close: np.ndarray,
    upper: np.ndarray,
    middle: np.ndarray,
    lower: np.ndarray,
) -> np.ndarray:
    """Compute Bollinger Band position.

    bb_position[t] = (close[t] - lower[t]) / (upper[t] - lower[t]).
    Values in [0, 1] typically; ~0 near lower band, ~1 near upper band, ~0.5 at middle.
    NaN where bands are NaN or upper == lower.

    Causality: at t uses band values computed from bars up to t.
    """
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)
    valid = ~np.isnan(upper) & ~np.isnan(lower) & (upper != lower)
    with np.errstate(divide="ignore", invalid="ignore"):
        result[valid] = (close[valid] - lower[valid]) / (upper[valid] - lower[valid])
    return result


def compute_bb_width(
    upper: np.ndarray,
    middle: np.ndarray,
    lower: np.ndarray,
) -> np.ndarray:
    """Compute Bollinger Band width.

    bb_width[t] = (upper[t] - lower[t]) / middle[t].
    NaN where middle is zero or NaN.

    Causality: uses band values computed from bars up to t.
    """
    n = len(upper)
    result = np.full(n, np.nan, dtype=np.float64)
    valid = ~np.isnan(middle) & (middle != 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        result[valid] = (upper[valid] - lower[valid]) / middle[valid]
    return result


def compute_highest(high: np.ndarray, window: int = SWING_BREAKOUT_WINDOW) -> np.ndarray:
    """Compute rolling maximum of high over `window` bars (causal)."""
    return _rolling_max(high, window)


def compute_lowest(low: np.ndarray, window: int = SWING_BREAKOUT_WINDOW) -> np.ndarray:
    """Compute rolling minimum of low over `window` bars (causal)."""
    return _rolling_min(low, window)


def compute_range_breakout(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    window: int = SWING_BREAKOUT_WINDOW,
) -> np.ndarray:
    """Compute range breakout signal.

    breakout[t] = (close[t] - lowest_N[t]) / (highest_N[t] - lowest_N[t]).
    Values in [0, 1]: 0 at support (close==lowest), 1 at resistance (close==highest).
    > 0.7 suggests near resistance.
    < 0.3 suggests near support.

    Causality: highest_N and lowest_N at t use bars up to t.
    """
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result

    highest_n = compute_highest(high, window)
    lowest_n = compute_lowest(low, window)

    valid = ~np.isnan(highest_n) & ~np.isnan(lowest_n) & (highest_n != lowest_n)
    with np.errstate(divide="ignore", invalid="ignore"):
        result[valid] = (close[valid] - lowest_n[valid]) / (highest_n[valid] - lowest_n[valid])
    return result


def compute_breakout_group(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    window: int = SWING_BREAKOUT_WINDOW,
    bb_window: int = SWING_BB_WINDOW,
    bb_num_std: float = SWING_BB_NUM_STD,
) -> Dict[str, np.ndarray]:
    """Compute all Breakout group features.

    Returns dict with keys: bb_position, bb_width, range_breakout_N.
    highest_N and lowest_N are internal (used by range_breakout_N) but not exported
    to avoid near-perfect multicollinearity with microprice_N.
    All arrays same length as input. NaN at start.
    """
    upper, middle, lower = compute_bollinger_bands(close, bb_window, bb_num_std)
    return {
        "bb_position": compute_bb_position(close, upper, middle, lower),
        "bb_width": compute_bb_width(upper, middle, lower),
        "range_breakout_N": compute_range_breakout(close, high, low, window),
    }


# ===========================================================================
# Main Pipeline Entry Point
# ===========================================================================

# Mode-specific window defaults
_MODE_DEFAULTS = {
    "SWING": {
        "n_returns": SWING_N_RETURNS,
        "volatility_window": SWING_VOLATILITY_WINDOW,
        "atr_window": SWING_ATR_WINDOW,
        "momentum_n": SWING_MOMENTUM_N,
        "rsi_window": SWING_RSI_WINDOW,
        "macd_fast": SWING_MACD_FAST,
        "macd_slow": SWING_MACD_SLOW,
        "macd_signal": SWING_MACD_SIGNAL,
        "volume_window": SWING_VOLUME_WINDOW,
        "breakout_window": SWING_BREAKOUT_WINDOW,
        "bb_window": SWING_BB_WINDOW,
        "bb_num_std": SWING_BB_NUM_STD,
        "periods_per_year": SWING_PERIODS_PER_YEAR,
        "orderbook_window": DEFAULT_ORDERBOOK_WINDOW,
        "amihud_window": DEFAULT_AMIHUD_WINDOW,
        "roll_spread_window": 20,
        "noise_window": 30,
        "serial_corr_window": 20,
        "vpin_window": 30,
        "price_impact_window": 20,
        "microprice_window": DEFAULT_MICROPRICE_WINDOW,
        "liquidity_vacuum_window": DEFAULT_LIQUIDITY_VACUUM_WINDOW,
        "depth_ratio_window": DEFAULT_DEPTH_RATIO_WINDOW,
        # OrderBook extended windows
        "multi_level_obi_n": DEFAULT_MULTI_LEVEL_OBI_N,
        "multi_level_obi_step": DEFAULT_MULTI_LEVEL_OBI_STEP,
        "multi_level_obi_decay": DEFAULT_MULTI_LEVEL_OBI_DECAY,
        "stoikov_micro_price_window": DEFAULT_STOIKOV_MICRO_PRICE_WINDOW,
        "ofi_window": DEFAULT_OFI_WINDOW,
        "vamp_window": DEFAULT_VAMP_WINDOW,
        "quoted_spread_window": DEFAULT_QUOTED_SPREAD_WINDOW,
        "vwap_mid_window": DEFAULT_VWAP_MID_WINDOW,
        "trade_count_window": DEFAULT_TRADE_COUNT_WINDOW,
        "volume_concentration_window": DEFAULT_VOLUME_CONCENTRATION_WINDOW,
        # Regime windows
        "cusum_threshold": SWING_CUSUM_THRESHOLD,
        "hmm_vol_window": SWING_HMM_VOL_WINDOW,
        "vol_regime_window": SWING_VOL_REGIME_WINDOW,
        # Candle pattern window
        "candle_window": 10,
    },
    "SCALP": {
        "n_returns": 12,
        "volatility_window": 24,
        "atr_window": 14,
        "momentum_n": 12,
        "rsi_window": 14,
        "macd_fast": 8,
        "macd_slow": 17,
        "macd_signal": 9,
        "volume_window": 24,
        "breakout_window": 24,
        "bb_window": 20,
        "bb_num_std": 2.0,
        "periods_per_year": 8760,
        "orderbook_window": DEFAULT_ORDERBOOK_WINDOW,
        "amihud_window": DEFAULT_AMIHUD_WINDOW,
        "roll_spread_window": 12,
        "noise_window": 20,
        "serial_corr_window": 12,
        "vpin_window": 40,
        "price_impact_window": 12,
        "microprice_window": 8,
        "liquidity_vacuum_window": 10,
        "depth_ratio_window": 8,
        # OrderBook extended windows
        "multi_level_obi_n": DEFAULT_MULTI_LEVEL_OBI_N,
        "multi_level_obi_step": DEFAULT_MULTI_LEVEL_OBI_STEP,
        "multi_level_obi_decay": DEFAULT_MULTI_LEVEL_OBI_DECAY,
        "stoikov_micro_price_window": DEFAULT_STOIKOV_MICRO_PRICE_WINDOW,
        "ofi_window": 10,
        "vamp_window": 8,
        "quoted_spread_window": 10,
        "vwap_mid_window": 10,
        "trade_count_window": 20,
        "volume_concentration_window": 20,
        # Regime windows
        "cusum_threshold": SCALP_CUSUM_THRESHOLD,
        "hmm_vol_window": SCALP_HMM_VOL_WINDOW,
        "vol_regime_window": SCALP_VOL_REGIME_WINDOW,
        # Candle pattern window
        "candle_window": 12,
    },
    "AGGRESSIVE_SCALP": {
        "n_returns": 16,
        "volatility_window": 24,
        "atr_window": 10,
        "momentum_n": 16,
        "rsi_window": 10,
        "macd_fast": 6,
        "macd_slow": 13,
        "macd_signal": 5,
        "volume_window": 24,
        "breakout_window": 12,
        "bb_window": 12,
        "bb_num_std": 2.0,
        "periods_per_year": 35040,
        "orderbook_window": DEFAULT_ORDERBOOK_WINDOW,
        "amihud_window": DEFAULT_AMIHUD_WINDOW,
        "roll_spread_window": 10,
        "noise_window": 20,
        "serial_corr_window": 10,
        "vpin_window": 50,
        "price_impact_window": 15,
        "microprice_window": 5,
        "liquidity_vacuum_window": 10,
        "depth_ratio_window": 5,
        # OrderBook extended windows
        "multi_level_obi_n": DEFAULT_MULTI_LEVEL_OBI_N,
        "multi_level_obi_step": DEFAULT_MULTI_LEVEL_OBI_STEP,
        "multi_level_obi_decay": DEFAULT_MULTI_LEVEL_OBI_DECAY,
        "stoikov_micro_price_window": DEFAULT_STOIKOV_MICRO_PRICE_WINDOW,
        "ofi_window": 10,
        "vamp_window": 5,
        "quoted_spread_window": 10,
        "vwap_mid_window": 10,
        "trade_count_window": 20,
        "volume_concentration_window": 20,
        # Regime windows
        "cusum_threshold": AGGRESSIVE_SCALP_CUSUM_THRESHOLD,
        "hmm_vol_window": AGGRESSIVE_SCALP_HMM_VOL_WINDOW,
        "vol_regime_window": AGGRESSIVE_SCALP_VOL_REGIME_WINDOW,
        # Candle pattern window
        "candle_window": 16,
    },
}

# Supported modes for feature computation
_SUPPORTED_MODES = frozenset({"SWING", "SCALP", "AGGRESSIVE_SCALP"})


def compute_features(
    ohlcv_data: dict,
    mode: str = "SWING",
    timeframe_stack: Optional[dict] = None,
    feature_groups: Optional[List[str]] = None,
) -> FeatureMatrix:
    """Main feature pipeline entry point.

    Computes 9 active feature groups from OHLCV data:
      RETURNS, VOLATILITY, ATR, MOMENTUM, VOLUME, BREAKOUT, ORDERBOOK,
      REGIME, CANDLE_PATTERN.
    Lead-Lag and PERPETUAL_FUNDING are NOT computed (DEFERRED).

    Args:
        ohlcv_data: dict with keys 'open', 'high', 'low', 'close', 'volume'.
            Values must be 1D numpy.ndarray of equal length.
        mode: Trading mode string ("SWING", "SCALP", "AGGRESSIVE_SCALP").
            SWING is the implementation baseline. SCALP/AGGRESSIVE_SCALP
            require empirical tuning and are HOLD.
        timeframe_stack: Optional dict with keys primary, context, refinement.
            Informational only — does not affect computation.

    Returns:
        FeatureMatrix with features dict containing ~54 feature arrays
        (35 core + 9 OrderBook extended + 6 Regime + 7 Candle Pattern),
        each of shape (n_bars,). No Lead-Lag columns present.

    Raises:
        ValueError: if OHLCV data is invalid or mode is unsupported.
    """
    # Validate inputs
    _validate_ohlcv_data(ohlcv_data)
    if mode.upper() not in _SUPPORTED_MODES:
        raise ValueError(
            f"Unsupported mode: '{mode}'. Supported: {sorted(_SUPPORTED_MODES)}"
        )
    mode = mode.upper()

    # Get mode-specific defaults
    defaults = _MODE_DEFAULTS.get(mode, _MODE_DEFAULTS["SWING"])

    close = ohlcv_data["close"]
    open_arr = ohlcv_data["open"]
    high = ohlcv_data["high"]
    low = ohlcv_data["low"]
    volume = ohlcv_data["volume"]
    n_bars = len(close)

    # Compute all active groups
    features: Dict[str, np.ndarray] = {}

    # 1. Returns Group (4 features)
    features.update(
        compute_returns_group(
            close=close,
            n=defaults["n_returns"],
            window=defaults["volatility_window"],
        )
    )

    # 2. Volatility Group (4 features)
    features.update(
        compute_volatility_group(
            open_arr=open_arr,
            high=high,
            low=low,
            close=close,
            window=defaults["volatility_window"],
        )
    )

    # 3. ATR Group (3 features)
    features.update(
        compute_atr_group(
            high=high,
            low=low,
            close=close,
            window=defaults["atr_window"],
        )
    )

    # 4. Momentum Group (6 features)
    features.update(
        compute_momentum_group(
            close=close,
            n=defaults["momentum_n"],
            rsi_window=defaults["rsi_window"],
            macd_fast=defaults["macd_fast"],
            macd_slow=defaults["macd_slow"],
            macd_signal=defaults["macd_signal"],
        )
    )

    # 5. Volume Group (4 features)
    features.update(
        compute_volume_group(
            high=high,
            low=low,
            close=close,
            volume=volume,
            window=defaults["volume_window"],
        )
    )

    # 6. Breakout Group (5 features)
    features.update(
        compute_breakout_group(
            high=high,
            low=low,
            close=close,
            window=defaults["breakout_window"],
            bb_window=defaults["bb_window"],
            bb_num_std=defaults["bb_num_std"],
        )
    )

    # 7. OrderBook Group (21 features — 12 core + 9 extended)
    features.update(
        compute_orderbook_group(
            open_arr=open_arr,
            high=high,
            low=low,
            close=close,
            volume=volume,
            window=defaults.get("orderbook_window", DEFAULT_ORDERBOOK_WINDOW),
            amihud_window=defaults.get("amihud_window", DEFAULT_AMIHUD_WINDOW),
            roll_spread_window=defaults.get("roll_spread_window", DEFAULT_ROLL_SPREAD_WINDOW),
            noise_window=defaults.get("noise_window", DEFAULT_NOISE_WINDOW),
            serial_corr_window=defaults.get("serial_corr_window", DEFAULT_SERIAL_CORR_WINDOW),
            vpin_window=defaults.get("vpin_window", DEFAULT_VPIN_WINDOW),
            price_impact_window=defaults.get("price_impact_window", DEFAULT_PRICE_IMPACT_WINDOW),
            microprice_window=defaults.get("microprice_window", DEFAULT_MICROPRICE_WINDOW),
            liquidity_vacuum_window=defaults.get("liquidity_vacuum_window", DEFAULT_LIQUIDITY_VACUUM_WINDOW),
            depth_ratio_window=defaults.get("depth_ratio_window", DEFAULT_DEPTH_RATIO_WINDOW),
            # Extended windows
            multi_level_obi_n=defaults.get("multi_level_obi_n", DEFAULT_MULTI_LEVEL_OBI_N),
            multi_level_obi_step=defaults.get("multi_level_obi_step", DEFAULT_MULTI_LEVEL_OBI_STEP),
            multi_level_obi_decay=defaults.get("multi_level_obi_decay", DEFAULT_MULTI_LEVEL_OBI_DECAY),
            stoikov_micro_price_window=defaults.get("stoikov_micro_price_window", DEFAULT_STOIKOV_MICRO_PRICE_WINDOW),
            ofi_window=defaults.get("ofi_window", DEFAULT_OFI_WINDOW),
            vamp_window=defaults.get("vamp_window", DEFAULT_VAMP_WINDOW),
            quoted_spread_window=defaults.get("quoted_spread_window", DEFAULT_QUOTED_SPREAD_WINDOW),
            vwap_mid_window=defaults.get("vwap_mid_window", DEFAULT_VWAP_MID_WINDOW),
            trade_count_window=defaults.get("trade_count_window", DEFAULT_TRADE_COUNT_WINDOW),
            volume_concentration_window=defaults.get("volume_concentration_window", DEFAULT_VOLUME_CONCENTRATION_WINDOW),
        )
    )

    # 8. Regime Group (6 features — CUSUM + HMM vol state + volatility regime)
    # Uses close, high, low arrays. Reserved: high/low for future use.
    features.update(
        compute_regime_group(
            close=close,
            high=high,
            low=low,
            cusum_threshold=defaults.get("cusum_threshold", SWING_CUSUM_THRESHOLD),
            hmm_vol_window=defaults.get("hmm_vol_window", SWING_HMM_VOL_WINDOW),
            vol_regime_window=defaults.get("vol_regime_window", SWING_VOL_REGIME_WINDOW),
        )
    )

    # 9. Candle Pattern Group (multi-bar pattern detection)
    features.update(
        compute_candle_pattern_group(
            open_arr=open_arr,
            high=high,
            low=low,
            close=close,
            window=defaults.get("candle_window", DEFAULT_CANDLE_WINDOW),
        )
    )

    # Lead-Lag group is DEFERRED — not computed, no columns added.
    # PERPETUAL_FUNDING group is DEFERRED — requires external funding data feed, not OHLCV-only.

    # Filter to requested feature groups if specified
    if feature_groups is not None:
        # Build a reverse mapping: feature name prefix -> group name
        # Group prefixes are known from each group's output key conventions
        GROUP_PREFIX_MAP = {
            "log_return": "returns",
            "return_": "returns",
            "realized_vol": "volatility",
            "high_low_range": "volatility",
            "garman_klass": "volatility",
            "parkinson_vol": "volatility",
            "atr_": "atr",
            "momentum_": "momentum",
            "rsi_": "momentum",
            "macd": "momentum",
            "volume_": "volume",
            "vwap_": "volume",
            "obv_": "volume",
            "bb_": "breakout",
            "range_": "breakout",
            "spread_": "orderbook",
            "volume_imbalance": "orderbook",
            "trade_intensity": "orderbook",
            "amihud": "orderbook",
            "roll_spread": "orderbook",
            "microstructure": "orderbook",
            "serial_correlation": "orderbook",
            "vpin": "orderbook",
            "price_impact": "orderbook",
            "microprice": "orderbook",
            "liquidity_vacuum": "orderbook",
            "depth_ratio": "orderbook",
            "obi": "orderbook",
            "ofi": "orderbook",
            "quoted_spread": "orderbook",
            "vwap_mid": "orderbook",
            "trade_count": "orderbook",
            "volume_concentration": "orderbook",
            "cusum": "regime",
            "hmm_": "regime",
            "vol_regime": "regime",
            "doji": "candle_pattern",
            "engulfing": "candle_pattern",
            "hammer": "candle_pattern",
            "shooting_star": "candle_pattern",
            "three_white": "candle_pattern",
            "three_black": "candle_pattern",
            "morning_star": "candle_pattern",
            "evening_star": "candle_pattern",
            "harami": "candle_pattern",
            "piercing": "candle_pattern",
            "dark_cloud": "candle_pattern",
            "candle_": "candle_pattern",
        }
        filtered = {}
        for name, arr in features.items():
            matched_group = None
            for prefix, group in GROUP_PREFIX_MAP.items():
                if name.startswith(prefix):
                    matched_group = group
                    break
            if matched_group is None or matched_group in feature_groups:
                filtered[name] = arr
        features = filtered

    # Verify array length consistency
    for name, arr in features.items():
        if len(arr) != n_bars:
            raise RuntimeError(
                f"Feature '{name}' has length {len(arr)}, expected {n_bars}"
            )

    # Assemble FeatureMatrix
    # Exclude DEFERRED groups: LEAD_LAG (P0.9B cross-sectional data)
    # and PERPETUAL_FUNDING (requires external funding data feed).
    excluded = {FeatureGroup.LEAD_LAG, FeatureGroup.PERPETUAL_FUNDING}
    expected_groups = [
        g.value for g in FeatureGroup
        if g not in excluded
    ]

    return FeatureMatrix(
        features=features,
        timestamps=None,
        symbol=ohlcv_data.get("symbol", ""),
        mode=mode,
        feature_group_ids=expected_groups,
        metadata={
            "pipeline_version": PIPELINE_VERSION,
            "n_bars": n_bars,
            "total_features": len(features),
            "window_defaults": defaults,
            "lead_lag_status": "DEFERRED",
            "lead_lag_reason": "P0.9B cross-sectional data dependency",
            "perpetual_funding_status": "DEFERRED",
            "perpetual_funding_reason": "Requires external funding data feed",
            "active_groups": 9,
        },
    )


# ===========================================================================
# Cached Pipeline Entry Point
# ===========================================================================


def cached_compute_features(
    ohlcv_data: dict,
    mode: str = "SWING",
    timeframe_stack: Optional[dict] = None,
    interval: str = "4h",
    cache_dir: str = CACHE_DIR_DEFAULT,
) -> FeatureMatrix:
    """Compute features with Parquet+Zstd caching.

    Checks cache first by (symbol, interval, mode, PIPELINE_VERSION) key.
    On cache hit, returns the cached FeatureMatrix immediately without
    recomputing features (typically 5-15 min saved per pipeline run).
    On cache miss, delegates to compute_features() and stores the result.

    Cache invalidation is automatic: when PIPELINE_VERSION changes, the
    cache key changes and a new computation is triggered. Old cache files
    are orphaned but harmless — they can be cleaned via FeatureCache.clear_all().

    Args:
        ohlcv_data: dict with keys 'open', 'high', 'low', 'close', 'volume'.
            Values must be 1D numpy.ndarray of equal length. Should include
            a 'symbol' key for cache key derivation.
        mode: Trading mode string ("SWING", "SCALP", "AGGRESSIVE_SCALP").
        timeframe_stack: Optional dict with keys primary, context, refinement.
        interval: Bar interval string for cache key (e.g. "4h", "1h", "15m").
        cache_dir: Directory path for cache files.

    Returns:
        FeatureMatrix with computed features (from cache or fresh compute).

    Raises:
        ValueError: if OHLCV data is invalid or mode is unsupported.
    """
    symbol = ohlcv_data.get("symbol", "unknown")

    cache = FeatureCache(cache_dir=cache_dir)
    cached = cache.get(symbol, interval, mode)
    if cached is not None:
        logger.info(
            "Cache HIT for %s/%s/%s (v%s) — returning cached features",
            symbol, interval, mode, PIPELINE_VERSION,
        )
        return cached

    logger.info(
        "Cache MISS for %s/%s/%s (v%s) — computing features...",
        symbol, interval, mode, PIPELINE_VERSION,
    )
    matrix = compute_features(ohlcv_data, mode=mode, timeframe_stack=timeframe_stack)
    cache.put(symbol, interval, mode, matrix)
    logger.info(
        "Cached %d features for %s/%s/%s (%d bars)",
        matrix.total_features(), symbol, interval, mode, matrix.bar_count(),
    )
    return matrix
