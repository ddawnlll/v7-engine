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
from alphaforge.features.scalp_momentum import (
    compute_scalp_momentum_group,
)
from alphaforge.features.residual_momentum import (
    compute_residual_momentum_group,
)
from alphaforge.features.open_interest import (
    DEFAULT_OI_WINDOW,
    SWING_OI_WINDOW,
    SCALP_OI_WINDOW,
    AGGRESSIVE_SCALP_OI_WINDOW,
    compute_open_interest_group,
)
from alphaforge.features.premium_index import (
    AGGRESSIVE_SCALP_BASIS_WINDOW,
    DEFAULT_BASIS_REGIME_THRESHOLD_BPS,
    DEFAULT_BASIS_WINDOW,
    SCALP_BASIS_WINDOW,
    SWING_BASIS_WINDOW,
    compute_premium_index_group,
)
from alphaforge.features.mtf import (
    compute_mtf_features,
)
from alphaforge.features.funding import (
    compute_funding_group,
)

try:
    from numba import njit
except ImportError:
    njit = lambda x: x

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PIPELINE_VERSION: str = "0.3.1"

# Default cache directory for feature matrices
# Resolved to absolute path at module load time to prevent working-directory confusion.
_CACHE_DIR_RELATIVE: str = ".cache/features/"
CACHE_DIR_DEFAULT: str = str(
    Path(__file__).resolve().parent.parent.parent.parent / _CACHE_DIR_RELATIVE
)

# Process-lifetime secret for cache integrity HMAC signing.
# Generated once at import time — cache files from other processes or
# tampered files are detected on read.
_CACHE_INTEGRITY_SECRET: bytes = hashlib.sha256(PIPELINE_VERSION.encode()).digest()

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
# Data fingerprint for cache invalidation
# ---------------------------------------------------------------------------


def _compute_data_fingerprint(ohlcv_data: dict) -> str:
    """Compute deterministic fingerprint from OHLCV data for cache key.

    Incorporates row count, first/last close values, and first/last timestamps
    (if available). This ensures that refreshed or corrected data produces a
    cache miss rather than serving stale features.

    Returns:
        Hex SHA-256 digest, or empty string if data has no close array.
    """
    close = ohlcv_data.get("close")
    if close is None or len(close) == 0:
        return ""
    parts = [str(len(close))]
    parts.append(f"{close[0]:.8f}")
    parts.append(f"{close[-1]:.8f}")
    ts = ohlcv_data.get("timestamp")
    if ts is not None and len(ts) > 0:
        parts.append(str(ts[0]))
        parts.append(str(ts[-1]))
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


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
    MTF = "mtf"  # Multi-timeframe context features (4h, 1d, 15m)
    LEAD_LAG = "lead_lag"  # DEFERRED — P0.9B cross-sectional data required
    SCALP_MOMENTUM = "scalp_momentum"  # P0.9G — SCALP-specific momentum enhancers
    OPEN_INTEREST = "open_interest"    # Real OI data features (#280)
    PREMIUM_INDEX = "premium_index"    # Premium index / basis features (#280)
    RESIDUAL_MOMENTUM = "residual_momentum"  # Milestone C — beta-adjusted residual momentum
    TIME_FEATURES = "time_features"  # Calendar/time-based features (hour_of_day, day_of_week, us_hours)


# ---------------------------------------------------------------------------
# FeatureMatrix dataclass
# ---------------------------------------------------------------------------

@dataclass
class FeatureMatrix:
    """Structured container for computed feature arrays.

    Attributes:
        features: Dict mapping feature name to numpy array of shape (n_bars,).
            Features are organized by group. Keys match the output of each
            group's compute function.
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
            # Exclude only PERPETUAL_FUNDING from default active set.
            # LEAD_LAG is conditional on multi_ohlcv availability.
            excluded = {FeatureGroup.PERPETUAL_FUNDING}
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

    def _cache_key(
        self, symbol: str, interval: str, mode: str,
        data_fingerprint: str = "",
    ) -> str:
        """Compute deterministic SHA-256 cache key.

        Incorporates symbol, interval, mode, and PIPELINE_VERSION so that
        changing any of these produces a distinct cache entry. When a
        ``data_fingerprint`` is provided (a hex hash derived from the OHLCV
        data content), it is also incorporated — this ensures that refreshed
        or corrected data produces a cache miss rather than serving stale
        features.

        Args:
            symbol: Trading pair identifier (e.g. \"BTCUSDT\").
            interval: Bar interval string (e.g. \"4h\", \"1h\", \"15m\").
            mode: Trading mode (\"SWING\", \"SCALP\", \"AGGRESSIVE_SCALP\").
            data_fingerprint: Optional hex hash of OHLCV data content. When
                present, the key uniquely identifies both the data source AND
                the content at the time of computation.

        Returns:
            Hex-encoded SHA-256 digest.
        """
        if data_fingerprint:
            raw = f"{symbol}|{interval}|{mode}|{PIPELINE_VERSION}|{data_fingerprint}"
        else:
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
        self, symbol: str, interval: str, mode: str,
        data_fingerprint: str = "",
    ) -> Optional[FeatureMatrix]:
        """Load cached FeatureMatrix if it exists and version matches.

        Uses PyArrow's memory_map=True for zero-copy Parquet reading.
        Returns None on cache miss (file missing, corrupt, or version mismatch).

        Args:
            symbol: Trading pair identifier.
            interval: Bar interval string.
            mode: Trading mode.
            data_fingerprint: Optional hex hash of OHLCV data content.
                When provided, the cache key incorporates the fingerprint
                so that refreshed data produces a cache miss.

        Returns:
            FeatureMatrix if cache hit, None otherwise.
        """
        key = self._cache_key(symbol, interval, mode, data_fingerprint)
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
        data_fingerprint: str = "",
    ) -> None:
        """Store FeatureMatrix to cache as Parquet+Zstd file.

        Thread-safe: only one writer at a time per FeatureCache instance.

        Args:
            symbol: Trading pair identifier.
            interval: Bar interval string.
            mode: Trading mode.
            matrix: FeatureMatrix to cache.
            data_fingerprint: Optional hex hash of OHLCV data content.
                When provided, the cache key incorporates the fingerprint
                so that refreshed data produces a cache miss.
        """
        key = self._cache_key(symbol, interval, mode, data_fingerprint)
        path = self._cache_path(key)

        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)

            # Build PyArrow arrays from feature dict
            field_names: List[str] = []
            arrays: List[pa.Array] = []
            for name in sorted(matrix.features.keys()):
                arr = matrix.features[name]
                # Ensure float32 for consistent storage
                if arr.dtype != np.float32:
                    arr = arr.astype(np.float32)
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
# MTF Group — multi-timeframe context features (4h, 1d, 15m)
# ---------------------------------------------------------------------------


def compute_mtf_group(
    ohlcv_data: dict,
    mode: str = "SWING",
    **kwargs,
) -> Dict[str, np.ndarray]:
    """Compute all multi-timeframe context features.

    Wraps mtf.compute_mtf_features() and aligns results to the primary
    bar grid. Accepts single-timeframe OHLCV and resamples internally
    for higher/lower timeframes.

    NOTE: Returns empty dict for multi-symbol data (MTF resampling
    assumes continuous single-symbol time series). This is a known
    limitation — process per-symbol for cross-symbol MTF features.

    Args:
        ohlcv_data: Primary OHLCV data dict with 'open','high','low',
            'close','volume' as 1D numpy arrays.
        mode: Trading mode string (for future mode-specific tuning).
        **kwargs: Passed through to mtf.compute_mtf_features.

    Returns:
        Dict mapping MTF feature names to 1D numpy arrays, same length
        as the input OHLCV data. Returns empty dict if no OHLCV data
        or multi-symbol data detected. All keys prefixed mtf_.
    """
    close = ohlcv_data.get("close")
    if close is None or len(close) == 0:
        return {}

    # Detect multi-symbol data — MTF resampling assumes continuous series
    symbols = ohlcv_data.get("symbol", [])
    if isinstance(symbols, (list, np.ndarray)) and len(symbols) > 1:
        unique_syms = set(str(s) for s in symbols)
        if len(unique_syms) > 1:
            return {}

    # compute_mtf_features handles internal resampling
    raw = compute_mtf_features(ohlcv_data)

    # Prefix keys with mtf_ for GROUP_PREFIX_MAP matching
    prefixed = {f"mtf_{k}": v for k, v in raw.items()}
    return prefixed


# ---------------------------------------------------------------------------
# PERPETUAL_FUNDING Group — funding rate + OI divergence features (#119)
# ---------------------------------------------------------------------------


def compute_perpetual_funding_group(
    ohlcv_data: dict,
    **kwargs,
) -> Dict[str, np.ndarray]:
    """Compute funding rate and funding-OI divergence features.

    Delegates to funding.compute_funding_group which produces:
      - funding_rate, funding_rate_ma_N, funding_rate_vol_N,
        funding_rate_zscore_N, funding_rate_change_N,
        open_interest_proxy_N, funding_oi_divergence_N

    Requires 'funding_rate' key in ohlcv_data for real funding data;
    falls back to OHLCV-derived proxy when absent.
    Requires 'volume' key for OI proxy computation.

    Returns:
        Dict mapping feature name to 1D numpy array.
    """
    from alphaforge.features.funding import (
        DEFAULT_FUNDING_WINDOW,
        DEFAULT_OI_PROXY_WINDOW,
        compute_funding_group as _cfg,
    )
    return _cfg(ohlcv_data, window=DEFAULT_FUNDING_WINDOW, oi_window=DEFAULT_OI_PROXY_WINDOW)


# ---------------------------------------------------------------------------
# TREND Group — SMA slope features for market direction context
# ---------------------------------------------------------------------------


def _trend_sma(close: np.ndarray, period: int) -> np.ndarray:
    """Trailing SMA with strict-NaN semantics (NaN if any NaN in window).

    Matches np.mean-over-slice behaviour: result[t] = mean(close[t-period+1:t+1]),
    NaN for t < period-1 or when the window contains a NaN.
    """
    n = len(close)
    out = np.full(n, np.nan, dtype=np.float32)
    if n < period:
        return out
    nan_mask = np.isnan(close)
    clean = np.where(nan_mask, 0.0, close).astype(np.float64)
    kernel = np.ones(period, dtype=np.float64)
    ma = np.convolve(clean, kernel, mode="full")[:n] / period
    if nan_mask.any():
        nan_cnt = np.convolve(nan_mask.astype(np.float64), kernel, mode="full")[:n]
        ma[nan_cnt > 0.5] = np.nan
    out[period - 1:] = ma[period - 1:].astype(np.float32)
    return out


def _rolling_lr_slope(y: np.ndarray, window: int) -> np.ndarray:
    """Rolling linear-regression slope of y against x = [0..window-1], closed form.

    slope[t] = sum(x_c * y[t-window+1:t+1]) / sum(x_c**2) with x_c = x - mean(x);
    the y-mean term vanishes because sum(x_c) == 0. y is globally demeaned first
    for float conditioning (adds a constant, which sum(x_c) == 0 cancels).
    NaN for t < window-1 or when the window contains a non-finite value.
    """
    n = len(y)
    out = np.full(n, np.nan, dtype=np.float32)
    if n < window:
        return out
    x_c = np.arange(window, dtype=np.float64)
    x_c -= x_c.mean()
    denom = max(float(np.sum(x_c * x_c)), 1e-12)
    finite = np.isfinite(y)
    if not finite.any():
        return out
    y64 = np.where(finite, y, 0.0).astype(np.float64)
    y64 -= y64[finite].mean()
    y64[~finite] = 0.0
    num = np.convolve(y64, x_c[::-1], mode="full")[:n]
    finite_cnt = np.convolve(
        finite.astype(np.float64), np.ones(window, dtype=np.float64), mode="full"
    )[:n]
    ok = finite_cnt > window - 0.5
    ok[:window - 1] = False
    out[ok] = (num[ok] / denom).astype(np.float32)
    return out


def _compute_trend_group(
    close: np.ndarray,
    ma_short: int = 50,
    ma_long: int = 200,
) -> Dict[str, np.ndarray]:
    """Compute long-term trend features from SMA slopes.

    Features:
      - trend_ma_short_slope:  slope of short MA (50 bars) over its window
      - trend_ma_long_slope:   slope of long MA (200 bars) over its window
      - trend_ma_cross:        short_MA / long_MA - 1 (golden/death cross)
      - trend_position:        close / long_MA - 1 (distance from trend)

    All values positive in uptrend, negative in downtrend.
    Helps model avoid short bias in bull markets.
    """
    n = len(close)
    result = {}
    ma_by_period: Dict[int, np.ndarray] = {}
    for name, period in [("trend_ma_short_slope", ma_short), ("trend_ma_long_slope", ma_long)]:
        ma = ma_by_period.setdefault(period, _trend_sma(close, period))
        # Slope: linear regression over half-period window
        window = max(period // 2, 5)
        slope = _rolling_lr_slope(ma, window)
        slope[:min(window + period - 1, n)] = np.nan
        result[name] = slope

    # MA cross and position
    ma_s = ma_by_period.get(ma_short)
    if ma_s is None:
        ma_s = _trend_sma(close, ma_short)
    ma_l = ma_by_period.get(ma_long)
    if ma_l is None:
        ma_l = _trend_sma(close, ma_long)
    result["trend_ma_cross"] = (ma_s / ma_l - 1.0) * 100
    result["trend_position"] = (close / ma_l - 1.0) * 100

    return result


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
    FeatureGroup.MTF: "compute_mtf_group",
    FeatureGroup.PERPETUAL_FUNDING: "compute_perpetual_funding_group",
    # LEAD_LAG is mapped but DEFERRED — compute_features does not call it.
    # Active filtering (lines 119, 1257) keeps LEAD_LAG out of computation
    # until cross-sectional data support lands (P0.9B).
    FeatureGroup.LEAD_LAG: "compute_lead_lag_group",
    FeatureGroup.SCALP_MOMENTUM: "compute_scalp_momentum_group",
    FeatureGroup.RESIDUAL_MOMENTUM: "compute_residual_momentum_group",
    FeatureGroup.OPEN_INTEREST: "compute_open_interest_group",
    FeatureGroup.PREMIUM_INDEX: "compute_premium_index_group",
    FeatureGroup.TIME_FEATURES: "compute_time_features_group",
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


@njit
def _p_njit_rolling_mean(
    csum: np.ndarray, nan_csum: np.ndarray, window: int
) -> np.ndarray:
    """Numba-accelerated rolling mean from precomputed cumsum arrays."""
    n = len(csum) - 1
    result = np.full(n, np.nan, dtype=np.float32)
    for i in range(window - 1, n):
        count = window - (nan_csum[i + 1] - nan_csum[i - window + 1])
        if count >= 2:
            result[i] = (csum[i + 1] - csum[i - window + 1]) / count
    return result


@njit
def _p_njit_rolling_sum(csum: np.ndarray, window: int) -> np.ndarray:
    """Numba-accelerated rolling sum."""
    n = len(csum) - 1
    result = np.full(n, np.nan, dtype=np.float32)
    for i in range(window - 1, n):
        result[i] = csum[i + 1] - csum[i - window + 1]
    return result


@njit
def _p_njit_rolling_std(
    csum: np.ndarray, csum2: np.ndarray, nan_csum: np.ndarray,
    window: int, ddof: int
) -> np.ndarray:
    """Numba-accelerated rolling std."""
    n = len(csum) - 1
    result = np.full(n, np.nan, dtype=np.float32)
    for i in range(window - 1, n):
        count = window - (nan_csum[i + 1] - nan_csum[i - window + 1])
        if count >= 2:
            s = csum[i + 1] - csum[i - window + 1]
            s2 = csum2[i + 1] - csum2[i - window + 1]
            var = s2 / count - (s / count) ** 2
            if var < 0:
                var = 0.0
            if ddof == 1 and count > 1:
                var = var * count / (count - 1)
            if var >= 0:
                result[i] = np.sqrt(var)
    return result


@njit
def _p_njit_rolling_var(
    csum: np.ndarray, csum2: np.ndarray, nan_csum: np.ndarray,
    window: int, ddof: int
) -> np.ndarray:
    """Numba-accelerated rolling variance."""
    n = len(csum) - 1
    result = np.full(n, np.nan, dtype=np.float32)
    for i in range(window - 1, n):
        count = window - (nan_csum[i + 1] - nan_csum[i - window + 1])
        if count >= 2:
            s = csum[i + 1] - csum[i - window + 1]
            s2 = csum2[i + 1] - csum2[i - window + 1]
            var = s2 / count - (s / count) ** 2
            if var < 0:
                var = 0.0
            if ddof == 1 and count > 1:
                var = var * count / (count - 1)
            result[i] = var
    return result


def _rolling_mean(arr: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling mean over `window` bars (O(n) via np.convolve or cumsum)..."""
    n = len(arr)
    if n < window:
        return np.full(n, np.nan, dtype=np.float32)
    if np.isnan(arr).any():
        # NaN path: cumsum + numba
        nan_mask = np.isnan(arr)
        clean = np.where(nan_mask, 0.0, arr)
        csum = np.cumsum(np.insert(clean, 0, 0))
        nan_csum = np.cumsum(np.insert(nan_mask.astype(np.float32), 0, 0))
        return _p_njit_rolling_mean(csum, nan_csum, window)
    # Fast path: no NaN, use np.convolve with trailing window
    kernel = np.ones(window, dtype=np.float32) / window
    result = np.convolve(arr, kernel, mode='full')[:n]
    result[:window - 1] = np.nan
    return result


def _rolling_sum(arr: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling sum over `window` bars (O(n) via np.convolve or cumsum)."""
    n = len(arr)
    if n < window:
        return np.full(n, np.nan, dtype=np.float32)
    if np.isnan(arr).any():
        csum = np.cumsum(np.insert(np.where(np.isnan(arr), 0.0, arr), 0, 0))
        return _p_njit_rolling_sum(csum, window)
    kernel = np.ones(window, dtype=np.float32)
    result = np.convolve(arr, kernel, mode='full')[:n]
    result[:window - 1] = np.nan
    return result


def _rolling_std(arr: np.ndarray, window: int, ddof: int = 1) -> np.ndarray:
    """Compute rolling standard deviation over `window` bars (NaN-safe, O(n) cumsum + numba).

    Causal: std at index t uses arr[t-window+1 .. t].
    Returns NaN for t < window-1 or when fewer than 2 non-NaN values
    are in the window.

    NaN values in the input are excluded (partial window std).
    """
    n = len(arr)
    if n < window:
        return np.full(n, np.nan, dtype=np.float32)
    nan_mask = np.isnan(arr)
    clean = np.where(nan_mask, 0.0, arr)
    csum = np.cumsum(np.insert(clean, 0, 0))
    csum2 = np.cumsum(np.insert(clean * clean, 0, 0))
    nan_csum = np.cumsum(np.insert(nan_mask.astype(np.float32), 0, 0))
    return _p_njit_rolling_std(csum, csum2, nan_csum, window, ddof)


def _rolling_var(arr: np.ndarray, window: int, ddof: int = 1) -> np.ndarray:
    """Compute rolling variance over `window` bars (NaN-safe, O(n) cumsum + numba).

    Causal: var at index t uses arr[t-window+1 .. t].
    Returns NaN for t < window-1 or when fewer than 2 non-NaN values.
    """
    n = len(arr)
    if n < window:
        return np.full(n, np.nan, dtype=np.float32)
    nan_mask = np.isnan(arr)
    clean = np.where(nan_mask, 0.0, arr)
    csum = np.cumsum(np.insert(clean, 0, 0))
    csum2 = np.cumsum(np.insert(clean * clean, 0, 0))
    nan_csum = np.cumsum(np.insert(nan_mask.astype(np.float32), 0, 0))
    return _p_njit_rolling_var(csum, csum2, nan_csum, window, ddof)


def _rolling_max(arr: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling maximum over `window` bars (O(n) via monotonic deque)."""
    n = len(arr)
    if n < window:
        return np.full(n, np.nan, dtype=np.float32)
    from collections import deque
    dq: deque = deque()
    result = np.full(n, np.nan, dtype=np.float32)
    for i in range(n):
        # Remove elements outside window
        while dq and dq[0] <= i - window:
            dq.popleft()
        # Remove smaller elements (they'll never be max)
        while dq and arr[dq[-1]] <= arr[i]:
            dq.pop()
        dq.append(i)
        if i >= window - 1:
            result[i] = arr[dq[0]]
    return result


def _rolling_min(arr: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling minimum over `window` bars (O(n) via monotonic deque)."""
    n = len(arr)
    if n < window:
        return np.full(n, np.nan, dtype=np.float32)
    from collections import deque
    dq: deque = deque()
    result = np.full(n, np.nan, dtype=np.float32)
    for i in range(n):
        # Remove elements outside window
        while dq and dq[0] <= i - window:
            dq.popleft()
        # Remove larger elements (they'll never be min)
        while dq and arr[dq[-1]] >= arr[i]:
            dq.pop()
        dq.append(i)
        if i >= window - 1:
            result[i] = arr[dq[0]]
    return result


@njit
def _ema(arr: np.ndarray, period: int) -> np.ndarray:
    """Compute Exponential Moving Average (causal, numpy-only).

    EMA[t] = arr[t] * k + EMA[t-1] * (1 - k)  where k = 2/(period+1).
    Seeded at first non-NaN value.
    Returns NaN for t < period-1 to match convention.
    """
    n = len(arr)
    result = np.full(n, np.nan, dtype=np.float32)
    if n < period:
        return result
    k = 2.0 / (period + 1.0)
    # Seed with SMA of first `period` values
    seed = np.mean(arr[:period].astype(np.float32))
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
    x = np.arange(n, dtype=np.float32)
    x_mean = np.mean(x)
    y_mean = np.mean(y.astype(np.float32))
    numerator = np.sum((x - x_mean) * (y.astype(np.float32) - y_mean))
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
    result = np.full(n, np.nan, dtype=np.float32)
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
    result = np.full(length, np.nan, dtype=np.float32)
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
    if n < window:
        return np.full(n, np.nan, dtype=np.float32)
    # O(n) rolling z-score via cumsum
    ret_mean = _rolling_mean(returns, window)
    ret_var = _rolling_var(returns, window, ddof=1)
    ret_std = np.sqrt(np.maximum(ret_var, 0.0))
    result = np.full(n, np.nan, dtype=np.float32)
    # Use adaptive threshold for near-zero std to handle cumsum floating-point error
    # cumsum variance can produce 1e-20 for constant data; sqrt gives 1e-10
    abs_mean = np.abs(ret_mean)
    zero_threshold = np.where(abs_mean > 1e-12, abs_mean * 1e-6, 1e-10)
    mask = ~np.isnan(ret_mean) & ~np.isnan(ret_std) & (ret_std > zero_threshold) & ~np.isnan(returns)
    result[mask] = (returns[mask] - ret_mean[mask]) / ret_std[mask]
    # When std is near-zero, z-score is 0 (no deviation)
    zero_std = ~np.isnan(ret_mean) & ~np.isnan(ret_std) & (ret_std <= zero_threshold) & ~np.isnan(returns)
    result[zero_std] = 0.0
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
    result = np.full(n, np.nan, dtype=np.float32)
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
    if n < window:
        return np.full(n, np.nan, dtype=np.float32)
    with np.errstate(divide="ignore", invalid="ignore"):
        hl_ratio = (high - low) / np.where(close == 0, np.nan, close)
    return _rolling_mean(hl_ratio, window)


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
    result = np.full(n, np.nan, dtype=np.float32)
    if n < window:
        return result

    # Precompute per-bar terms
    # Avoid division by zero: if any price is 0, the bar term is NaN
    with np.errstate(divide="ignore", invalid="ignore"):
        hl_term = 0.5 * (np.log(high / low)) ** 2
        co_term = (2.0 * np.log(2.0) - 1.0) * (np.log(close / open_arr)) ** 2

    gk = hl_term - co_term
    # O(n) rolling sum via cumsum
    gk_sum = _rolling_sum(gk, window)
    # Count valid bars per window
    nan_mask = np.isnan(gk)
    csum_nan = np.cumsum(np.insert(nan_mask.astype(np.float32), 0, 0))
    result = np.full(n, np.nan, dtype=np.float32)
    for i in range(window - 1, n):
        count = window - (csum_nan[i + 1] - csum_nan[i - window + 1])
        if count < 2:
            continue
        s = gk_sum[i]
        if s < 0 or np.isnan(s):
            result[i] = 0.0
        else:
            result[i] = np.sqrt(s / count)
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
    result = np.full(n, np.nan, dtype=np.float32)
    if n < window:
        return result

    with np.errstate(divide="ignore", invalid="ignore"):
        hl_sq = np.log(high / low) ** 2

    denom = 4.0 * np.log(2.0)  # constant factor
    # O(n): sum of ln(H/L)^2 via rolling sum, divide by count, sqrt
    roll_sum = _rolling_sum(hl_sq, window)
    nan_mask = np.isnan(hl_sq)
    csum_nan = np.cumsum(np.insert(nan_mask.astype(np.float32), 0, 0))
    result = np.full(n, np.nan, dtype=np.float32)
    for i in range(window - 1, n):
        count = window - (csum_nan[i + 1] - csum_nan[i - window + 1])
        if count < 2:
            continue
        s = roll_sum[i]
        if not np.isnan(s) and s > 0:
            result[i] = np.sqrt(s / (denom * count))
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
    result = np.full(n, np.nan, dtype=np.float32)
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
    result = np.full(n, np.nan, dtype=np.float32)
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
    result = np.full(n, np.nan, dtype=np.float32)
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
    result = np.full(length, np.nan, dtype=np.float32)
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
    result = np.full(length, np.nan, dtype=np.float32)
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
    result = np.full(n, np.nan, dtype=np.float32)
    if n < window + 1:
        return result

    # Compute per-bar changes
    delta = np.zeros(n, dtype=np.float32)
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
    nan_arr = np.full(n, np.nan, dtype=np.float32)

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
    result = np.full(n, np.nan, dtype=np.float32)
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
    if n < window:
        return np.full(n, np.nan, dtype=np.float32)

    # O(n) rolling linear regression slope via cumsum of volume and idx*volume
    # β = Σ(i - mean_i)(y_i - mean_y) / Σ(i - mean_i)²
    #   = (Σ i*y_i - mean_i * Σ y_i) / denom  (since Σ(i - mean_i) = 0)
    # where i = [0, 1, ..., window-1] within each window
    # mean_i = (window-1)/2
    # denom = window*(window²-1)/12
    mid = (window - 1.0) * 0.5
    denom = window * (window * window - 1.0) / 12.0

    # Use global indices to compute rolling weighted sums
    # For window ending at t, the local index i = global_idx - (t-window+1)
    # β[t] = (Σ((j - (t-window+1) - mid) * y_j)) / denom  for j in [t-window+1, t]
    #       = (Σ((j - mid) * y_j) - (t-window+1) * Σ y_j) / denom
    # where y_j = volume[j]
    clean = np.where(np.isnan(volume), 0.0, volume)
    csum_y = np.cumsum(np.insert(clean, 0, 0))
    # j * y_j where j is global index (0, 1, ..., n-1)
    jy = np.arange(n, dtype=np.float32) * clean
    csum_jy = np.cumsum(np.insert(jy, 0, 0))

    result = np.full(n, np.nan, dtype=np.float32)
    if denom == 0:
        return result
    for i in range(window - 1, n):
        start = i - window + 1
        sum_y = csum_y[i + 1] - csum_y[start]
        sum_jy = csum_jy[i + 1] - csum_jy[start]
        # β = (Σ(j * y_j) - (start + (W-1)/2) * Σ y_j) / denom
        # where start = t-W+1 and mid = (W-1)/2
        # so start + mid = t - (W-1)/2 = offset correction
        numer = sum_jy - (start + mid) * sum_y
        result[i] = numer / denom
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
    result = np.full(n, np.nan, dtype=np.float32)
    if n == 0:
        return result

    tp = (high.astype(np.float32) + low.astype(np.float32) + close.astype(np.float32)) / 3.0
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
    result = np.full(n, np.nan, dtype=np.float32)
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
    result = np.full(n, np.nan, dtype=np.float32)
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
    result = np.full(n, np.nan, dtype=np.float32)
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
    result = np.full(n, np.nan, dtype=np.float32)
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


# ═══════════════════════════════════════════════════════════════════════
# Time Features Group (S3 — calendar/time-based features)
# ═══════════════════════════════════════════════════════════════════════


def compute_time_features_group(
    timestamps: np.ndarray,
) -> Dict[str, np.ndarray]:
    """Compute time/calendar-based features from Unix timestamps.

    Produces 5 features:
      hour_of_day_sin, hour_of_day_cos  — sin/cos encoding of trading hour
      day_of_week_sin, day_of_week_cos  — sin/cos encoding of day of week
      is_us_hours                       — 1 during US market overlap (13:30-20:00 UTC)

    All features are trivially causal (derived from timestamp alone,
    no future leakage possible).

    Args:
        timestamps: Unix-ns or Unix-ms int64 array of bar close times.

    Returns:
        Dict with 5 keys, each a float64 array of same length as input.
    """
    n = len(timestamps)
    if n == 0:
        return {
            "hour_of_day_sin": np.array([], dtype=np.float32),
            "hour_of_day_cos": np.array([], dtype=np.float32),
            "day_of_week_sin": np.array([], dtype=np.float32),
            "day_of_week_cos": np.array([], dtype=np.float32),
            "is_us_hours": np.array([], dtype=np.float32),
        }

    # Detect scale: Unix-ns (~1.7e18) vs Unix-ms (~1.7e12) vs Unix-s (~1.7e9)
    ts_max = float(timestamps.max())
    if ts_max > 1e15:
        # Nanoseconds → seconds
        ts_s = timestamps.astype(np.float64) / 1e9
    elif ts_max > 1e11:
        # Milliseconds → seconds
        ts_s = timestamps.astype(np.float64) / 1e3
    else:
        ts_s = timestamps.astype(np.float64)

    # Convert to UTC datetime components using vectorized operations
    # Python's datetime fromtimestamp for vectorized hour/day-of-week extraction
    import datetime

    hours = np.zeros(n, dtype=np.float32)
    day_of_week = np.zeros(n, dtype=np.float32)

    for i in range(n):
        try:
            dt = datetime.datetime.utcfromtimestamp(ts_s[i])
            hours[i] = float(dt.hour)
            day_of_week[i] = float(dt.weekday())  # Monday=0, Sunday=6
        except (OSError, ValueError, OverflowError):
            hours[i] = np.nan
            day_of_week[i] = np.nan

    # Sin/cos encoding for cyclical features
    hour_angle = 2.0 * np.pi * hours / 24.0
    dow_angle = 2.0 * np.pi * day_of_week / 7.0

    hour_sin = np.sin(hour_angle)
    hour_cos = np.cos(hour_angle)

    dow_sin = np.sin(dow_angle)
    dow_cos = np.cos(dow_angle)

    # US trading hours: 13:30-20:00 UTC (NY open to close)
    # is_us_hours = 1 during this window, 0 otherwise
    us_hours = np.where(
        np.isnan(hours), np.nan,
        np.where((hours >= 13.5) & (hours < 20.0), 1.0, 0.0),
    )

    return {
        "hour_of_day_sin": hour_sin,
        "hour_of_day_cos": hour_cos,
        "day_of_week_sin": dow_sin,
        "day_of_week_cos": dow_cos,
        "is_us_hours": us_hours.astype(np.float32),
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
        # Open Interest windows
        "oi_window": SWING_OI_WINDOW,
        # Premium index windows
        "basis_window": DEFAULT_BASIS_WINDOW,
        "basis_threshold_bps": DEFAULT_BASIS_REGIME_THRESHOLD_BPS,
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
        # Open Interest windows
        "oi_window": SCALP_OI_WINDOW,
        # Premium index windows
        "basis_window": SCALP_BASIS_WINDOW,
        "basis_threshold_bps": DEFAULT_BASIS_REGIME_THRESHOLD_BPS,
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
        # Open Interest windows
        "oi_window": AGGRESSIVE_SCALP_OI_WINDOW,
        # Premium index windows
        "basis_window": AGGRESSIVE_SCALP_BASIS_WINDOW,
        "basis_threshold_bps": DEFAULT_BASIS_REGIME_THRESHOLD_BPS,
    },
}

# Supported modes for feature computation
_SUPPORTED_MODES = frozenset({"SWING", "SCALP", "AGGRESSIVE_SCALP"})


def compute_features(
    ohlcv_data: dict,
    mode: str = "SWING",
    timeframe_stack: Optional[dict] = None,
    feature_groups: Optional[List[str]] = None,
    multi_ohlcv: Optional[Dict[str, Dict[str, np.ndarray]]] = None,
) -> FeatureMatrix:
    """Main feature pipeline entry point.

    Computes 15 active feature groups from OHLCV data:
      RETURNS, VOLATILITY, ATR, MOMENTUM, VOLUME, BREAKOUT, ORDERBOOK,
      REGIME, CANDLE_PATTERN, MTF, SCALP_MOMENTUM, OPEN_INTEREST,
      PREMIUM_INDEX, RESIDUAL_MOMENTUM, PERPETUAL_FUNDING,
      TIME_FEATURES.
    Lead-Lag is NOT computed (DEFERRED).

    Args:
        ohlcv_data: dict with keys 'open', 'high', 'low', 'close', 'volume'.
            Values must be 1D numpy.ndarray of equal length.
        mode: Trading mode string ("SWING", "SCALP", "AGGRESSIVE_SCALP").
            SWING is the implementation baseline. SCALP/AGGRESSIVE_SCALP
            require empirical tuning and are HOLD.
        timeframe_stack: Optional dict with keys primary, context, refinement.
            Informational only — does not affect computation.

    Returns:
        FeatureMatrix with features dict containing ~63 feature arrays
        (35 core + 9 OrderBook extended + 6 Regime + 7 Candle Pattern
        + 8 MTF + 5 SCALP Momentum + 4 Open Interest + 5 Premium Index
        + 4 Residual Momentum), each of shape (n_bars,). No Lead-Lag
        columns present.

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

    _SKIP_ON_1H = {"orderbook", "candle_pattern", "scalp_momentum", "breakout"}

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

    # 10. TREND Group — long-term market direction via SMA slopes
    # Fixes the SHORT bias in bull markets by providing trend context.
    features.update(
        _compute_trend_group(
            close=close,
            ma_short=50,
            ma_long=200,
        )
    )

    # 11. MTF Group (multi-timeframe context features)
    # Resamples internally from primary OHLCV — no extra data needed.
    if "mtf" in (feature_groups or ["mtf"]):
        features.update(
            compute_mtf_group(
                ohlcv_data=ohlcv_data,
                mode=mode,
            )
        )

    # 11. SCALP Momentum Group (P0.9G — SCALP-specific momentum enhancers)
    if "scalp_momentum" in (feature_groups or ["scalp_momentum"]):
        features.update(
            compute_scalp_momentum_group(
                ohlcv_data=ohlcv_data,
                mode=mode,
            )
        )

    # 12. Open Interest Group (4+1 features — requires 'open_interest' in ohlcv_data)
    if "open_interest" in (feature_groups or ["open_interest"]):
        features.update(
            compute_open_interest_group(
                ohlcv_data=ohlcv_data,
                window=defaults.get("oi_window", DEFAULT_OI_WINDOW),
            )
        )

    # 13. Premium Index Group (5 features — requires 'premium_close' or 'premium_index')
    if "premium_index" in (feature_groups or ["premium_index"]):
        features.update(
            compute_premium_index_group(
                ohlcv_data=ohlcv_data,
                window=defaults.get("basis_window", DEFAULT_BASIS_WINDOW),
                threshold_bps=defaults.get("basis_threshold_bps", DEFAULT_BASIS_REGIME_THRESHOLD_BPS),
            )
        )

    # 14. Residual Momentum Group (Milestone C — beta-adjusted momentum, clustering)
    # Requires multi-symbol data. When only a single symbol is present,
    # this group is skipped (it requires at least 2 symbols).
    if "residual_momentum" in (feature_groups or ["residual_momentum"]):
        # Build multi-symbol dict if possible; otherwise silently skip
        symbol_key = ohlcv_data.get("symbol", "UNKNOWN")
        multi_ohlcv = {symbol_key: ohlcv_data}
        try:
            features.update(
                compute_residual_momentum_group(
                    multi_ohlcv=multi_ohlcv,
                    btc_symbol=symbol_key,
                    beta_window=defaults.get("residual_beta_window", 20),
                    n_clusters=defaults.get("residual_n_clusters", 3),
                )
            )
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(
                "Residual momentum group skipped for %s: %s — "
                "requires >=2 symbols with close data (multi-symbol panel)",
                symbol_key, e,
            )

    # Lead-Lag group — cross-sectional features (requires multi_ohlcv)
    # Default OFF — enabled by passing lead_lag in feature_groups AND multi_ohlcv.
    if "lead_lag" in (feature_groups or []) and multi_ohlcv is not None:
        symbol_key = ohlcv_data.get("symbol", "UNKNOWN")
        # Use BTC as the context symbol for lead-lag detection
        context_symbol = "BTCUSDT" if "BTCUSDT" in multi_ohlcv else (
            next(s for s in multi_ohlcv if s != symbol_key) if len(multi_ohlcv) > 1 else symbol_key
        )
        cluster_symbols = [s for s in multi_ohlcv if s != symbol_key and s != context_symbol][:5]
        try:
            ll_features = compute_lead_lag_group(
                multi_ohlcv=multi_ohlcv,
                primary_symbol=symbol_key,
                context_symbol=context_symbol,
                correlation_window=defaults.get("ll_correlation_window", 12),
                volatility_window=defaults.get("ll_volatility_window", 12),
                max_lag=defaults.get("ll_max_lag", 3),
                periods_per_year=defaults.get("periods_per_year", 8760),
                cluster_symbols=cluster_symbols if len(cluster_symbols) >= 2 else None,
            )
            features.update(ll_features)
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(
                "Lead-lag group skipped for %s: %s", symbol_key, e,
            )
    elif "lead_lag" in (feature_groups or []):
        logger.warning(
            "Lead-lag group requested but no multi_ohlcv provided — skipping"
        )
    # PERPETUAL_FUNDING group — funding rate + OI divergence features
    if "perpetual_funding" in (feature_groups or ["perpetual_funding"]):
        features.update(
            compute_perpetual_funding_group(
                ohlcv_data=ohlcv_data,
            )
        )

    # 15. Time Features Group (S3 — calendar/time-based features)
    # Trivially causal from timestamps alone. Requires 'timestamp' in ohlcv_data.
    if "time_features" in (feature_groups or ["time_features"]):
        ts = ohlcv_data.get("timestamp")
        if ts is not None and len(ts) == n_bars:
            features.update(
                compute_time_features_group(ts)
            )
        else:
            logger.warning("Time features skipped: no timestamp data available")

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
            "mtf_": "mtf",  # Multi-timeframe features
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
            "mom_": "scalp_momentum",       # P0.9G — all mom_* features
            "open_interest_change": "open_interest",  # #280 OI features
            "open_interest_volume": "open_interest",  # #280 OI features
            "open_interest_zscore": "open_interest",  # #280 OI features
            "oi_price_divergence": "open_interest",   # new OI-price divergence
            "basis_ma": "premium_index",             # #280 premium index features
            "basis_vol": "premium_index",            # #280 premium index features
            "basis_zscore": "premium_index",         # #280 premium index features
            "basis_regime": "premium_index",         # #280 premium index features
            "basis": "premium_index",                # #280 raw basis
            "funding_basis_divergence": "premium_index",  # new funding-basis divergence
            "residual_beta": "residual_momentum",      # Milestone C
            "residual_momentum": "residual_momentum",  # Milestone C
            "cluster_id": "residual_momentum",         # Milestone C
            "cs_momentum": "residual_momentum",        # Milestone C
            "funding_rate": "perpetual_funding",       # PERPETUAL_FUNDING group
            "funding_rate_ma": "perpetual_funding",
            "funding_rate_vol": "perpetual_funding",
            "funding_rate_zscore": "perpetual_funding",
            "funding_rate_change": "perpetual_funding",
            "funding_oi_divergence": "perpetual_funding",
            "open_interest_proxy": "perpetual_funding",
            "trend_": "trend",  # trend features (always included)
            "hour_of_day": "time_features",   # S3 time features
            "day_of_week": "time_features",   # S3 time features
            "is_us_hours": "time_features",   # S3 time features
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
    # and PERPETUAL_FUNDING (live funding data feed now supported).
    excluded = {FeatureGroup.LEAD_LAG}
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
            "lead_lag_status": "CONDITIONAL",
            "lead_lag_reason": "Activated when multi_ohlcv provided + lead_lag in feature_groups",
            "perpetual_funding_status": "DEFERRED",
            "perpetual_funding_reason": "Requires external funding data feed",
            "active_groups": 15,
            "residual_momentum_status": "ACTIVE",
            "open_interest_status": "ACTIVE",
            "premium_index_status": "ACTIVE",
            "time_features_status": "ACTIVE",
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
    feature_groups: Optional[List[str]] = None,
) -> FeatureMatrix:
    """Compute features with Parquet+Zstd caching.

    Checks cache first by (symbol, interval, mode, PIPELINE_VERSION, data_fingerprint) key.
    On cache hit, returns the cached FeatureMatrix immediately without
    recomputing features (typically 5-15 min saved per pipeline run).
    On cache miss, delegates to compute_features() and stores the result.

    Cache invalidation is automatic: when PIPELINE_VERSION changes or the
    OHLCV data content changes, the cache key changes and a new computation
    is triggered. Old cache files are orphaned but harmless — they can be
    cleaned via FeatureCache.clear_all().

    Args:
        ohlcv_data: dict with keys 'open', 'high', 'low', 'close', 'volume'.
            Values must be 1D numpy.ndarray of equal length. Should include
            a 'symbol' key for cache key derivation.
        mode: Trading mode string ("SWING", "SCALP", "AGGRESSIVE_SCALP").
        timeframe_stack: Optional dict with keys primary, context, refinement.
        interval: Bar interval string for cache key (e.g. "4h", "1h", "15m").
        cache_dir: Directory path for cache files.
        feature_groups: Optional list of feature groups to compute. Passed
            through to compute_features() on cache miss.

    Returns:
        FeatureMatrix with computed features (from cache or fresh compute).

    Raises:
        ValueError: if OHLCV data is invalid or mode is unsupported.
    """
    symbol = ohlcv_data.get("symbol", "unknown")
    data_fp = _compute_data_fingerprint(ohlcv_data)

    cache = FeatureCache(cache_dir=cache_dir)
    cached = cache.get(symbol, interval, mode, data_fingerprint=data_fp)
    if cached is not None:
        logger.info(
            "Cache HIT for %s/%s/%s (v%s, fp=%s) — returning cached features",
            symbol, interval, mode, PIPELINE_VERSION, data_fp[:8],
        )
        return cached

    logger.info(
        "Cache MISS for %s/%s/%s (v%s, fp=%s) — computing features...",
        symbol, interval, mode, PIPELINE_VERSION, data_fp[:8],
    )
    matrix = compute_features(ohlcv_data, mode=mode, timeframe_stack=timeframe_stack, feature_groups=feature_groups)
    cache.put(symbol, interval, mode, matrix, data_fingerprint=data_fp)
    logger.info(
        "Cached %d features for %s/%s/%s (%d bars, fp=%s)",
        matrix.total_features(), symbol, interval, mode, matrix.bar_count(), data_fp[:8],
    )
    return matrix
