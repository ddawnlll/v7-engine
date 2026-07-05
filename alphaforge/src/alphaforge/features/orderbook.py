"""OrderBook Feature Group — microstructure-aware features from OHLCV data.

Authority: AlphaForge owns feature discovery and specification.
This module computes microstructure proxy features from OHLCV data only.
No real order book data is used in v0.2 — all features are OHLCV proxies.

Primary target mode: AGGRESSIVE_SCALP (15m primary, 5m refinement).
Secondary applicability: SCALP and SWING with adjusted window parameters.

Features (21 total — 12 core + 9 expansion #119/#154/#165/#170):
  - spread_pct_N: rolling mean of (high-low)/close — spread proxy
  - volume_imbalance_N: rolling (up_volume - down_volume) / total_volume
  - trade_intensity_N: volume * (high-low)/close normalized by rolling mean
  - amihud_illiquidity_N: Amihud (2002) price impact measure
  - roll_spread_N: Roll (1984) effective bid-ask spread estimator
  - microstructure_noise_N: variance ratio based microstructure noise measure
  - serial_correlation_N: rolling autocorrelation of returns at lag 1
  - vpin_N: VPIN-inspired order flow toxicity proxy
  - price_impact_slope_N: Kyle's lambda proxy (return-on-signed-volume slope)
  - microprice_N: Estimate of true price from volume-weighted high/low (#119)
  - liquidity_vacuum_N: Combined low-volume + wide-spread regime detector (#119)
  - depth_ratio_N: Estimate of bid/ask depth ratio from volume classification (#119)
  - obi: Per-bar Level 1 order book imbalance (#154)
  - multi_level_obi_N: Multi-level OBI with depth decay (#165)
  - stoikov_micro_price_N: Stoikov contrarian micro-price (#170)
  - ofi_N: Equally-weighted order flow imbalance
  - vamp_N: Volume-adjusted mid price
  - quoted_spread_N: Effective quoted spread proxy
  - vwap_mid_deviation_N: Rolling VWAP deviation from midpoint
  - trade_count_N: Trade count proxy (volume z-score)
  - volume_concentration_hhi_N: Herfindahl-Hirschman Index of volume

Design constraints:
  - numpy only (no pandas, scipy, ta-lib) except lib/indicators bridge
  - no network calls, no exchange APIs, no real market data
  - all features are causal: feature at bar[t] uses bars [t-lookback+1 .. t]
  - NaN fill for insufficient lookback at series start
  - deterministic: same input always produces identical output
  - lib/indicators.microstructure.amihud_illiquidity bridged via list conversion
  - lib/indicators.microstructure.roll_spread_estimator bridged via list conversion

Causality contract:
  Every feature at index t accesses data only from indices [max(0, t - window + 1), t].
  No index > t is ever accessed.
"""

from __future__ import annotations

import logging
import math
from typing import Dict, List

import numpy as np

try:
    from numba import njit
except ImportError:
    njit = lambda x: x

from lib.indicators.microstructure import amihud_illiquidity, dollar_volume, roll_spread_estimator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fast rolling helpers (O(n) cumsum-based, replaces for+np.mean/std/sum)
# ---------------------------------------------------------------------------


@njit
def _njit_rolling_mean(
    csum: np.ndarray, nan_csum: np.ndarray, window: int, min_periods: int
) -> np.ndarray:
    """Numba-accelerated rolling mean from precomputed cumsum arrays."""
    n = len(csum) - 1
    result = np.full(n, np.nan, dtype=np.float64)
    for i in range(window - 1, n):
        count = window - (nan_csum[i + 1] - nan_csum[i - window + 1])
        if count >= min_periods:
            result[i] = (csum[i + 1] - csum[i - window + 1]) / count
    return result


@njit
def _njit_rolling_std(
    csum: np.ndarray, csum2: np.ndarray, nan_csum: np.ndarray,
    window: int, min_periods: int, ddof: int
) -> np.ndarray:
    """Numba-accelerated rolling std from precomputed cumsum arrays."""
    n = len(csum) - 1
    result = np.full(n, np.nan, dtype=np.float64)
    for i in range(window - 1, n):
        count = window - (nan_csum[i + 1] - nan_csum[i - window + 1])
        if count >= min_periods:
            s = csum[i + 1] - csum[i - window + 1]
            s2 = csum2[i + 1] - csum2[i - window + 1]
            var = s2 / count - (s / count) ** 2
            if var < 0:
                var = 0.0
            if ddof == 1 and count > 1:
                var = var * count / (count - 1)
            result[i] = np.sqrt(var)
    return result


@njit
def _njit_rolling_sum(csum: np.ndarray, window: int) -> np.ndarray:
    """Numba-accelerated rolling sum from precomputed cumsum."""
    n = len(csum) - 1
    result = np.full(n, np.nan, dtype=np.float64)
    for i in range(window - 1, n):
        result[i] = csum[i + 1] - csum[i - window + 1]
    return result


@njit
def _njit_rolling_var(
    csum: np.ndarray, csum2: np.ndarray, nan_csum: np.ndarray,
    window: int, min_periods: int, ddof: int
) -> np.ndarray:
    """Numba-accelerated rolling variance from precomputed cumsum."""
    n = len(csum) - 1
    result = np.full(n, np.nan, dtype=np.float64)
    for i in range(window - 1, n):
        count = window - (nan_csum[i + 1] - nan_csum[i - window + 1])
        if count >= min_periods:
            s = csum[i + 1] - csum[i - window + 1]
            s2 = csum2[i + 1] - csum2[i - window + 1]
            var = s2 / count - (s / count) ** 2
            if var < 0:
                var = 0.0
            if ddof == 1 and count > 1:
                var = var * count / (count - 1)
            result[i] = var
    return result


@njit
def _njit_rolling_cov(
    csum1: np.ndarray, csum2: np.ndarray, csum12: np.ndarray,
    nan_csum: np.ndarray, window: int, min_periods: int, ddof: int
) -> np.ndarray:
    """Numba-accelerated rolling covariance from precomputed cumsum."""
    n = len(csum1) - 1
    result = np.full(n, np.nan, dtype=np.float64)
    for i in range(window - 1, n):
        count = window - (nan_csum[i + 1] - nan_csum[i - window + 1])
        if count >= min_periods:
            s1 = csum1[i + 1] - csum1[i - window + 1]
            s2 = csum2[i + 1] - csum2[i - window + 1]
            s12 = csum12[i + 1] - csum12[i - window + 1]
            cov = (s12 - s1 * s2 / count) / (count - ddof) if count > ddof else 0.0
            result[i] = cov
    return result


def _rolling_mean(arr: np.ndarray, window: int, min_periods: int = 2) -> np.ndarray:
    """O(n) rolling mean via np.convolve (fast C implementation).

    NaN-safe: detects NaN and falls back to cumsum+numba if present.
    """
    n = len(arr)
    if n < min_periods or window < 1:
        return np.full(n, np.nan, dtype=np.float64)
    if np.isnan(arr).any():
        # NaN path: cumsum + numba loop
        nan_mask = np.isnan(arr)
        clean = np.where(nan_mask, 0.0, arr)
        csum = np.cumsum(np.insert(clean, 0, 0))
        nan_csum = np.cumsum(np.insert(nan_mask.astype(np.float64), 0, 0))
        return _njit_rolling_mean(csum, nan_csum, window, min_periods)
    # Fast path: no NaN, use np.convolve
    kernel = np.ones(window, dtype=np.float64) / window
    result = np.convolve(arr, kernel, mode='same')
    result[:window - 1] = np.nan
    return result


def _rolling_sum(arr: np.ndarray, window: int, min_periods: int = 1) -> np.ndarray:
    """O(n) rolling sum via np.convolve (fast C implementation).

    NaN-safe: detects NaN and falls back to cumsum+numba if present.
    """
    n = len(arr)
    if n < 1 or window < 1:
        return np.full(n, np.nan, dtype=np.float64)
    if np.isnan(arr).any():
        csum = np.cumsum(np.insert(np.where(np.isnan(arr), 0.0, arr), 0, 0))
        return _njit_rolling_sum(csum, window)
    kernel = np.ones(window, dtype=np.float64)
    result = np.convolve(arr, kernel, mode='same')
    result[:window - 1] = np.nan
    return result


def _rolling_std(arr: np.ndarray, window: int, min_periods: int = 2, ddof: int = 0) -> np.ndarray:
    """O(n) rolling std via cumsum + numba loop (needs variance)."""
    n = len(arr)
    if n < min_periods or window < 1:
        return np.full(n, np.nan, dtype=np.float64)
    nan_mask = np.isnan(arr)
    clean = np.where(nan_mask, 0.0, arr)
    csum = np.cumsum(np.insert(clean, 0, 0))
    csum2 = np.cumsum(np.insert(clean * clean, 0, 0))
    nan_csum = np.cumsum(np.insert(nan_mask.astype(np.float64), 0, 0))
    return _njit_rolling_std(csum, csum2, nan_csum, window, min_periods, ddof)


# Fast path for std when no NaN (avoids nan_mask overhead)
@njit
def _njit_rolling_std_nonan(clean: np.ndarray, window: int, ddof: int) -> np.ndarray:
    """Numba rolling std for arrays without NaN."""
    n = len(clean)
    csum = np.cumsum(clean)
    csum2 = np.cumsum(clean * clean)
    result = np.full(n, np.nan, dtype=np.float64)
    adj = 1 if ddof == 1 else 0
    for i in range(window - 1, n):
        count = window
        s = csum[i] - (csum[i - window] if i >= window else 0.0)
        s2 = csum2[i] - (csum2[i - window] if i >= window else 0.0)
        var = s2 / count - (s / count) ** 2
        if var < 0:
            var = 0.0
        if ddof == 1 and count > 1:
            var = var * count / (count - 1)
        result[i] = np.sqrt(var)
    return result


def _rolling_cov(
    arr1: np.ndarray, arr2: np.ndarray, window: int, min_periods: int = 2, ddof: int = 0
) -> np.ndarray:
    """O(n) rolling covariance via cumulative sums + numba loop."""
    n = len(arr1)
    if n < min_periods or window < 1:
        return np.full(n, np.nan, dtype=np.float64)
    nan_mask = np.isnan(arr1) | np.isnan(arr2)
    clean1 = np.where(nan_mask, 0.0, arr1)
    clean2 = np.where(nan_mask, 0.0, arr2)
    csum1 = np.cumsum(np.insert(clean1, 0, 0))
    csum2 = np.cumsum(np.insert(clean2, 0, 0))
    csum12 = np.cumsum(np.insert(clean1 * clean2, 0, 0))
    nan_csum = np.cumsum(np.insert(nan_mask.astype(np.float64), 0, 0))
    return _njit_rolling_cov(csum1, csum2, csum12, nan_csum, window, min_periods, ddof)


def _rolling_var(
    arr: np.ndarray, window: int, min_periods: int = 2, ddof: int = 0
) -> np.ndarray:
    """O(n) rolling variance via cumulative sum + numba loop."""
    n = len(arr)
    if n < min_periods or window < 1:
        return np.full(n, np.nan, dtype=np.float64)
    nan_mask = np.isnan(arr)
    clean = np.where(nan_mask, 0.0, arr)
    csum = np.cumsum(np.insert(clean, 0, 0))
    csum2 = np.cumsum(np.insert(clean * clean, 0, 0))
    nan_csum = np.cumsum(np.insert(nan_mask.astype(np.float64), 0, 0))
    return _njit_rolling_var(csum, csum2, nan_csum, window, min_periods, ddof)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# AGGRESSIVE_SCALP mode defaults (15m primary bars)
# Shorter windows than SWING to capture microstructure dynamics
AGGRESSIVE_SPREAD_WINDOW: int = 10
AGGRESSIVE_IMBALANCE_WINDOW: int = 10
AGGRESSIVE_INTENSITY_WINDOW: int = 10
AGGRESSIVE_AMIHUD_WINDOW: int = 15
AGGRESSIVE_ROLL_SPREAD_WINDOW: int = 10
AGGRESSIVE_NOISE_WINDOW: int = 20
AGGRESSIVE_SERIAL_CORR_WINDOW: int = 10
AGGRESSIVE_VPIN_WINDOW: int = 50
AGGRESSIVE_PRICE_IMPACT_WINDOW: int = 15
AGGRESSIVE_PERIODS_PER_YEAR: int = 35040  # 365 * 24 * 4 (15m bars)

# AGGRESSIVE_SCALP microprice window (very short, 5 bars at 15m = 75m)
AGGRESSIVE_MICROPRICE_WINDOW: int = 5
# AGGRESSIVE_SCALP liquidity vacuum window
AGGRESSIVE_LIQUIDITY_VACUUM_WINDOW: int = 10
# AGGRESSIVE_SCALP depth ratio window
AGGRESSIVE_DEPTH_RATIO_WINDOW: int = 5

# Generic defaults usable across modes
DEFAULT_ORDERBOOK_WINDOW: int = 10
DEFAULT_AMIHUD_WINDOW: int = 15
DEFAULT_ROLL_SPREAD_WINDOW: int = 20
DEFAULT_NOISE_WINDOW: int = 20
DEFAULT_SERIAL_CORR_WINDOW: int = 10
DEFAULT_VPIN_WINDOW: int = 50
DEFAULT_PRICE_IMPACT_WINDOW: int = 15
DEFAULT_MICROPRICE_WINDOW: int = 5
DEFAULT_LIQUIDITY_VACUUM_WINDOW: int = 10
DEFAULT_DEPTH_RATIO_WINDOW: int = 5

# Multi-level OBI constants (#154, #165)
DEFAULT_MULTI_LEVEL_OBI_N: int = 5
DEFAULT_MULTI_LEVEL_OBI_STEP: int = 3
DEFAULT_MULTI_LEVEL_OBI_DECAY: float = 0.8

# Stoikov micro-price constants (#170)
DEFAULT_STOIKOV_MICRO_PRICE_WINDOW: int = 5

# OFI (Order Flow Imbalance) constants
DEFAULT_OFI_WINDOW: int = 10

# VAMP (Volume-Adjusted Mid Price) constants
DEFAULT_VAMP_WINDOW: int = 5

# Quoted spread constants
DEFAULT_QUOTED_SPREAD_WINDOW: int = 10

# VWAP-to-mid deviation constants
DEFAULT_VWAP_MID_WINDOW: int = 10

# Trade count (volume z-score) constants
DEFAULT_TRADE_COUNT_WINDOW: int = 20

# Volume concentration (HHI) constants
DEFAULT_VOLUME_CONCENTRATION_WINDOW: int = 20


# ===========================================================================
# Per-bar helper: buy/sell volume classification from OHLCV
# ===========================================================================

def _classify_volume_direction(
    open_arr: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Classify per-bar volume into up (buy) and down (sell) components.

    Classification rule:
      - close > open  -> up_volume = volume, down_volume = 0
      - close < open  -> up_volume = 0, down_volume = volume
      - close == open -> up_volume = volume/2, down_volume = volume/2

    This is a standard OHLCV-based proxy for buy/sell volume when trade-level
    data is unavailable.

    Args:
        open_arr: Open prices.
        close: Close prices.
        volume: Volume (base asset).

    Returns:
        (up_volume, down_volume) as numpy arrays of same length.
    """
    n = len(volume)
    up_vol = np.zeros(n, dtype=np.float64)
    down_vol = np.zeros(n, dtype=np.float64)

    up_mask = close > open_arr
    down_mask = close < open_arr
    flat_mask = ~up_mask & ~down_mask  # close == open

    up_vol[up_mask] = volume[up_mask]
    down_vol[down_mask] = volume[down_mask]
    # Split flat bars evenly
    up_vol[flat_mask] = volume[flat_mask] * 0.5
    down_vol[flat_mask] = volume[flat_mask] * 0.5

    return up_vol, down_vol


# ===========================================================================
# Feature: spread_pct (OHLCV spread proxy)
# ===========================================================================

def compute_spread_pct(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    window: int = DEFAULT_ORDERBOOK_WINDOW,
) -> np.ndarray:
    """Compute rolling mean of (high - low) / close as a spread proxy.

    For each bar: raw_spread_i = (high_i - low_i) / close_i.
    Returns rolling mean of raw_spread over `window` bars.

    This captures the intra-bar price range relative to price level.
    Wider ranges suggest higher effective spreads or volatility-driven
    microstructure noise.

    Args:
        high: High prices.
        low: Low prices.
        close: Close prices (same length as high/low).
        window: Rolling window for smoothing (default 10 for AGGRESSIVE_SCALP).

    Returns:
        numpy array of spread estimates (same length as input).
        First `window-1` values are NaN.
        Values are in [0, +inf) as fractions (e.g., 0.001 = 0.1% spread).
    """
    n = len(high)
    if n < window:
        return np.full(n, np.nan, dtype=np.float64)

    # Per-bar raw spread (NaN-safe: skip bars where close <= 0)
    raw_spread = np.full(n, np.nan, dtype=np.float64)
    valid_close = close > 0
    with np.errstate(divide="ignore", invalid="ignore"):
        raw_spread[valid_close] = (high[valid_close] - low[valid_close]) / close[valid_close]

    # O(n) rolling mean over valid raw_spread values
    result = _rolling_mean(raw_spread, window, min_periods=2)

    return result


# ===========================================================================
# Feature: volume_imbalance (buy vs sell pressure proxy)
# ===========================================================================

def compute_volume_imbalance(
    open_arr: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    window: int = DEFAULT_ORDERBOOK_WINDOW,
    up_vol: np.ndarray = None,
    down_vol: np.ndarray = None,
) -> np.ndarray:
    """Compute rolling volume imbalance: (up_volume - down_volume) / total_volume.

    Uses OHLCV-based buy/sell classification:
      - close > open  -> buy volume
      - close < open  -> sell volume
      - close == open -> split evenly

    Positive values indicate buying pressure (more up-volume than down-volume).
    Negative values indicate selling pressure.
    Range: [-1, +1]. Values near 0 indicate balanced volume.

    Args:
        open_arr: Open prices.
        close: Close prices.
        volume: Volume (base asset).
        window: Rolling window (default 10).
        up_vol: Precomputed up volume (optional).
        down_vol: Precomputed down volume (optional).

    Returns:
        numpy array of volume imbalance values (same length as input).
        First `window-1` values are NaN.
    """
    n = len(volume)
    if n < window:
        return np.full(n, np.nan, dtype=np.float64)

    if up_vol is None or down_vol is None:
        up_vol, down_vol = _classify_volume_direction(open_arr, close, volume)

    # O(n) rolling imbalance via cumulative sum
    up_csum = np.cumsum(np.insert(up_vol, 0, 0))
    down_csum = np.cumsum(np.insert(down_vol, 0, 0))
    result = np.full(n, np.nan, dtype=np.float64)
    for i in range(window - 1, n):
        up_sum = up_csum[i + 1] - up_csum[i - window + 1]
        down_sum = down_csum[i + 1] - down_csum[i - window + 1]
        total = up_sum + down_sum
        if total > 0:
            result[i] = (up_sum - down_sum) / total
        else:
            result[i] = 0.0

    return result


# ===========================================================================
# Feature: trade_intensity (volume-price-range product normalized)
# ===========================================================================

def compute_trade_intensity(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    window: int = DEFAULT_ORDERBOOK_WINDOW,
) -> np.ndarray:
    """Compute normalized trade intensity.

    Intensity_i = volume_i * (high_i - low_i) / close_i
    This combines volume and price range into a single intensity metric.

    The raw intensity is then normalized against its rolling mean:
      trade_intensity[t] = intensity[t] / mean(intensity[t-window+1 .. t])

    Values > 1 indicate above-average trading intensity.
    Values < 1 indicate below-average trading intensity.

    Args:
        high: High prices.
        low: Low prices.
        close: Close prices.
        volume: Volume (base asset).
        window: Rolling window for normalization (default 10).

    Returns:
        numpy array of normalized intensity values (same length as input).
        First `window-1` values are NaN.
    """
    n = len(high)
    if n < window:
        return np.full(n, np.nan, dtype=np.float64)

    # Per-bar raw intensity: volume * (high-low) / close
    raw_intensity = np.full(n, np.nan, dtype=np.float64)
    valid_close = close > 0
    with np.errstate(divide="ignore", invalid="ignore"):
        raw_intensity[valid_close] = (
            volume[valid_close] * (high[valid_close] - low[valid_close]) / close[valid_close]
        )

    # O(n) normalization by rolling mean
    rolling_mu = _rolling_mean(raw_intensity, window, min_periods=2)
    mask = (rolling_mu > 0) & ~np.isnan(raw_intensity) & (raw_intensity >= 0)
    result = np.full(n, np.nan, dtype=np.float64)
    result[mask] = raw_intensity[mask] / rolling_mu[mask]

    return result


# ===========================================================================
# Feature: amihud_illiquidity (price impact)
# ===========================================================================

def compute_amihud_illiquidity_numpy(
    close: np.ndarray,
    volume: np.ndarray,
    window: int = DEFAULT_AMIHUD_WINDOW,
) -> np.ndarray:
    """Compute Amihud (2002) illiquidity measure bridged from lib/indicators.

        ILLIQ = rolling mean( |r_t| / dollar_volume_t )

    where r_t is the 1-bar log return and dollar_volume_t = close_t * volume_t.

    Higher values indicate lower liquidity (larger absolute return per unit
    of dollar volume traded).

    This bridges the list-based lib/indicators implementation to the
    numpy-based pipeline. The bridging conversion is O(n) and produces
    the same deterministic result.

    Args:
        close: Close prices.
        volume: Volume (base asset).
        window: Rolling window for Amihud computation (default 15).

    Returns:
        numpy array of Amihud ILLIQ values (same length as input).
        First `window-1` values are NaN.
    """
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)

    if n < window:
        return result

    # Compute log returns for the Amihud denominator
    log_ret = np.full(n, np.nan, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        log_ret[1:] = np.log(close[1:] / close[:-1])

    # Compute dollar volumes using lib/indicators bridge
    dv_list = dollar_volume(close.tolist(), volume.tolist())

    # Bridge: convert to lists for the lib function, then back to numpy
    ret_list: List[float] = log_ret.tolist()

    illiq_list = amihud_illiquidity(ret_list, dv_list, period=window)

    # Convert back to numpy array
    result = np.array(illiq_list, dtype=np.float64)

    return result


# ===========================================================================
# Feature: roll_spread (Roll 1984 effective bid-ask spread)
# ===========================================================================

def compute_roll_spread(
    close: np.ndarray,
    window: int = DEFAULT_ROLL_SPREAD_WINDOW,
) -> np.ndarray:
    """Compute Roll (1984) effective bid-ask spread estimator.

    S = 2 * sqrt(max(0, -covariance(delta_p_t, delta_p_{t-1})))

    O(n) vectorized via cumsum.

    Args:
        close: Close prices.
        window: Rolling window for covariance computation (default 20).

    Returns:
        numpy array of Roll spread estimates (same length as input).
    """
    n = len(close)
    if n < window + 1:
        return np.full(n, np.nan, dtype=np.float64)

    # Price changes (1-bar deltas)
    deltas = np.full(n, np.nan, dtype=np.float64)
    deltas[1:] = close[1:] - close[:-1]

    # Only use pairs where both delta[j] and delta[j-1] are valid
    valid = ~(np.isnan(deltas) | np.isnan(np.roll(deltas, 1)))
    valid[0] = False

    # Clean arrays: NaN → 0 for cumsum math
    clean_d = np.where(valid, deltas, 0.0)
    clean_d_lag = np.where(valid, np.roll(deltas, 1), 0.0)

    # Cumsum-based rolling covariance
    cs_d = np.cumsum(np.insert(clean_d, 0, 0))
    cs_dl = np.cumsum(np.insert(clean_d_lag, 0, 0))
    cs_ddl = np.cumsum(np.insert(clean_d * clean_d_lag, 0, 0))
    cs_valid = np.cumsum(np.insert(valid.astype(np.float64), 0, 0))

    result = np.full(n, np.nan, dtype=np.float64)
    w = window
    for i in range(w, n):
        start = i - w + 1
        nv = cs_valid[i + 1] - cs_valid[start]
        if nv < 3:
            continue

        sum_d = cs_d[i + 1] - cs_d[start]
        sum_dl = cs_dl[i + 1] - cs_dl[start]
        sum_ddl = cs_ddl[i + 1] - cs_ddl[start]

        # cov(delta, delta_lag) = (n*sum(d*dl) - sum(d)*sum(dl)) / (n*(n-1))
        cov = (nv * sum_ddl - sum_d * sum_dl) / (nv * (nv - 1))
        result[i] = 2.0 * math.sqrt(max(0.0, -cov))

    return result


# ===========================================================================
# Feature: microstructure_noise (variance ratio based noise measure)
# ===========================================================================

def _compute_log_return_1(close: np.ndarray) -> np.ndarray:
    """Compute 1-bar log returns (local helper, same contract as pipeline)."""
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < 2:
        return result
    with np.errstate(divide="ignore", invalid="ignore"):
        result[1:] = np.log(close[1:] / close[:-1])
    return result


def compute_microstructure_noise(
    close: np.ndarray,
    window: int = DEFAULT_NOISE_WINDOW,
) -> np.ndarray:
    """Compute microstructure noise via variance ratio.

    noise[t] = sqrt(window) * std(r_1[t-window+1 .. t])
               / std(r_window[t-window+1 .. t])

    where r_1 is 1-bar log return and r_window[t] = ln(close[t] / close[t-w]).

    For a pure random walk: noise ~ 1.0 (the std of windowed returns
    equals sqrt(window) * std of 1-bar returns).

    Values > 1.0 indicate microstructure noise (bid-ask bounce inflates
    the 1-bar return variance relative to the window return variance).
    Values < 1.0 indicate trending behaviour (windowed returns have
    higher variance than the random-walk baseline).

    The output is clamped to [0.01, 10.0] to prevent extreme outliers
    from degenerate windows.

    Causality: at t uses close and returns up to index t.

    Args:
        close: Close prices.
        window: Rolling window for variance ratio (default 20).
            Must be >= 4 for meaningful computation.

    Returns:
        numpy array of noise estimates (same length as input).
        First `window` values are NaN (need window+1 close prices).
        Values near 1 = random-walk-like. > 1 = noisy. < 1 = trending.
    """
    n = len(close)
    if n < window + 1:
        return np.full(n, np.nan, dtype=np.float64)

    log_ret_1 = _compute_log_return_1(close)

    # O(n) microstructure noise via variance ratio
    # noise[t] = sqrt(window) * std(r_1[..]) / std(r_window[..])
    #
    # r_window[j] = ln(close[j] / close[j-window]) = sum of window consecutive r_1
    # Precompute all r_window at once using cumsum of r_1
    cs = np.cumsum(np.insert(np.where(np.isnan(log_ret_1), 0.0, log_ret_1), 0, 0))
    r_window_vals = np.full(n, np.nan, dtype=np.float64)
    r_window_vals[window:] = cs[window + 1:] - cs[1: n - window + 1]

    # Rolling std of r_1 (1-bar returns) over window
    std_1 = _rolling_std(log_ret_1, window, min_periods=3, ddof=1)

    # Rolling std of window-bar returns over the same window
    std_window = _rolling_std(r_window_vals, window, min_periods=3, ddof=1)

    # Compute noise ratio
    result = np.full(n, np.nan, dtype=np.float64)
    mask = (std_1 > 1e-14) & (std_window > 1e-14)
    result[mask] = np.sqrt(float(window)) * std_1[mask] / std_window[mask]
    result = np.clip(result, 0.01, 10.0)

    return result


# ===========================================================================
# Feature: serial_correlation (rolling return autocorrelation at lag 1)
# ===========================================================================

def compute_serial_correlation(
    close: np.ndarray,
    window: int = DEFAULT_SERIAL_CORR_WINDOW,
) -> np.ndarray:
    """Compute rolling autocorrelation of 1-bar log returns at lag 1.

    For each bar t, computes the Pearson correlation between
    r[t-window+1 .. t] and r[t-window .. t-1].

    Interpretation:
      Positive -> trending behaviour (up follows up, down follows down).
      Negative -> mean-reversion / microstructure bounce (reversals).
      Near zero -> no serial dependence.

    For scalping: negative values indicate microstructure frictions
    (bid-ask bounce), which may present mean-reversion opportunities.

    Causality: at t uses returns up to index t. The lag-1 autocorrelation
    at t uses only bars [t-window .. t] (window+1 returns for window pairs).

    Args:
        close: Close prices.
        window: Rolling window for autocorrelation (default 10).
            Must be >= 4 for meaningful computation.

    Returns:
        numpy array of autocorrelation values in [-1, 1] (same length as input).
        First `window` values are NaN (need window+1 returns).
        NaN also when insufficient valid pairs exist.
    """
    n = len(close)
    if n < window + 2:  # need window+2 bars for window+1 returns
        return np.full(n, np.nan, dtype=np.float64)

    log_ret = _compute_log_return_1(close)

    # O(n) rolling serial correlation via cumulative sums
    clean = np.where(np.isnan(log_ret), 0.0, log_ret)
    nan_mask = np.isnan(log_ret)

    csum = np.cumsum(np.insert(nan_mask.astype(np.float64), 0, 0))
    # x: indices [i-window .. i-1], y: indices [i-window+1 .. i]
    # xy pairs: (j, j+1) for j in [i-window .. i-1]
    # cumsum over data
    cs_data = np.cumsum(np.insert(clean, 0, 0))
    cs_data2 = np.cumsum(np.insert(clean * clean, 0, 0))
    cs_xy = np.cumsum(np.insert(clean[1:] * clean[:-1], 0, 0))
    cs_y = cs_data  # y = x[1:] just like data shifted by 1
    cs_y2 = cs_data2  # y^2 = x[1:]^2

    result = np.full(n, np.nan, dtype=np.float64)
    w = window
    for i in range(w + 1, n):
        # x indices: [i-w .. i-1]
        x_start = i - w
        x_end = i  # exclusive

        # NaN count in x segment
        nan_x = csum[x_end] - csum[x_start]
        n_valid = w - nan_x
        if n_valid < 4:
            continue

        # x stats
        sum_x = cs_data[x_end] - cs_data[x_start]
        sum_x2 = cs_data2[x_end] - cs_data2[x_start]

        # y indices: [i-w+1 .. i]
        # y uses the same cumsum arrays but shifted by 1
        y_start = i - w + 1
        y_end = i + 1

        # y stats (using cumsum at y_start and y_end)
        sum_y = cs_data[y_end] - cs_data[y_start]
        sum_y2 = cs_data2[y_end] - cs_data2[y_start]

        # xy pairs: sum(x[j] * y[j]) for j in [i-w .. i-1]
        # = sum(log_ret[j] * log_ret[j+1]) for j in [i-w .. i-1]
        # cs_xy at idx k = sum_{j<k} log_ret[j] * log_ret[j+1]
        sum_xy = cs_xy[x_end] - cs_xy[x_start]

        # Pearson correlation (computational formula)
        cov = n_valid * sum_xy - sum_x * sum_y
        var_x = n_valid * sum_x2 - sum_x * sum_x
        var_y = n_valid * sum_y2 - sum_y * sum_y

        if var_x < 1e-14 or var_y < 1e-14:
            continue

        denom = np.sqrt(var_x * var_y)
        if denom < 1e-14:
            continue

        corr = cov / denom
        result[i] = float(np.clip(corr, -1.0, 1.0))

    return result


# ===========================================================================
# Feature: vpin (VPIN-inspired order flow toxicity proxy)
# ===========================================================================

def compute_vpin(
    open_arr: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    window: int = DEFAULT_VPIN_WINDOW,
    up_vol: np.ndarray = None,
    down_vol: np.ndarray = None,
) -> np.ndarray:
    """Compute VPIN-inspired order flow toxicity proxy.

    VPIN (Volume-synchronized Probability of Informed Trading) measures
    the cumulative absolute order imbalance relative to total volume over
    a rolling window.

      vpin[t] = sum(|up_volume - down_volume|, window) / sum(volume, window)

    Range: [0, 1].
    Values near 0 -> balanced order flow (low informed trading pressure).
    Values near 1 -> highly imbalanced order flow (potential informed trading).
    Values > 0.5 suggest directional pressure that may predict price moves.

    This is a simplified proxy: the original VPIN uses volume-synchronized
    buckets, while this uses a fixed-time rolling window.

    Uses OHLCV-based buy/sell volume classification consistent with
    compute_volume_imbalance.

    Causality: at t uses volume and classified flow up to index t.

    Args:
        open_arr: Open prices.
        close: Close prices.
        volume: Volume (base asset).
        window: Rolling window in bars (default 50). Larger windows
            provide more stable estimates.
        up_vol: Precomputed up volume (optional).
        down_vol: Precomputed down volume (optional).

    Returns:
        numpy array of VPIN values in [0, 1] (same length as input).
        First `window-1` values are NaN.
    """
    n = len(volume)
    if n < window:
        return np.full(n, np.nan, dtype=np.float64)

    if up_vol is None or down_vol is None:
        up_vol, down_vol = _classify_volume_direction(open_arr, close, volume)

    # O(n) rolling VPIN via cumulative sums
    vol_csum = np.cumsum(np.insert(up_vol + down_vol, 0, 0))
    abs_diff_csum = np.cumsum(np.insert(np.abs(up_vol - down_vol), 0, 0))
    result = np.full(n, np.nan, dtype=np.float64)
    for i in range(window - 1, n):
        total_vol = vol_csum[i + 1] - vol_csum[i - window + 1]
        if total_vol > 0:
            result[i] = (abs_diff_csum[i + 1] - abs_diff_csum[i - window + 1]) / total_vol
        else:
            result[i] = 0.0

    return result


# ===========================================================================
# Feature: price_impact_slope (Kyle's lambda proxy)
# ===========================================================================

def compute_price_impact_slope(
    open_arr: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    window: int = DEFAULT_PRICE_IMPACT_WINDOW,
    up_vol: np.ndarray = None,
    down_vol: np.ndarray = None,
) -> np.ndarray:
    """Compute Kyle's lambda proxy: regression of returns on signed order flow.

    For each rolling window [t-window+1 .. t]:
      1. Compute signed order flow: flow_i = up_vol_i - down_vol_i
      2. Compute log return: r_i = ln(close_i / close_{i-1})
      3. Price impact slope = covariance(r, flow) / variance(flow)

    Interpretation:
      Higher positive values -> order flow has large price impact (less liquid).
      Near zero -> order flow has little price impact (highly liquid).
      Negative values -> price moves against the order flow (perverse or
      strongly mean-reverting microstructure).

    Uses OHLCV-based buy/sell volume classification consistent with
    compute_volume_imbalance.

    Causality: at t uses open, high, low, close, volume up to index t.

    Args:
        open_arr: Open prices.
        high: High prices.
        low: Low prices.
        close: Close prices.
        volume: Volume (base asset).
        window: Rolling window for regression (default 15).
        up_vol: Precomputed up volume (optional).
        down_vol: Precomputed down volume (optional).

    Returns:
        numpy array of price impact slope values (same length as input).
        First `window` values are NaN (need window+1 bars for window
        returns).
        NaN also when variance of signed flow is too small.
    """
    log_ret = _compute_log_return_1(close)
    if up_vol is None or down_vol is None:
        up_vol, down_vol = _classify_volume_direction(open_arr, close, volume)
    signed_flow = up_vol - down_vol
    return _price_impact_slope_vectorized(log_ret, signed_flow, window)


def _price_impact_slope_vectorized(
    log_ret: np.ndarray,
    signed_flow: np.ndarray,
    window: int,
) -> np.ndarray:
    """Vectorized rolling regression for Kyle's lambda via cumsum (no for-loop per bar).

    slope = (n*sum(rf) - sum(r)*sum(f)) / (n*sum(f^2) - sum(f)^2)
    """
    n = len(log_ret)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window + 1:
        return result

    # Only use pairs where both r and f are valid
    valid = ~(np.isnan(log_ret) | np.isnan(signed_flow))
    clean_r = np.where(valid, log_ret, 0.0)
    clean_f = np.where(valid, signed_flow, 0.0)

    # Cumsum arrays for O(1) rolling window queries
    cs_r = np.cumsum(np.insert(clean_r, 0, 0))
    cs_f = np.cumsum(np.insert(clean_f, 0, 0))
    cs_rf = np.cumsum(np.insert(clean_r * clean_f, 0, 0))
    cs_f2 = np.cumsum(np.insert(clean_f * clean_f, 0, 0))
    cs_valid = np.cumsum(np.insert(valid.astype(np.float64), 0, 0))

    for i in range(window, n):
        start = i - window + 1
        n_valid = cs_valid[i + 1] - cs_valid[start]
        if n_valid < 3:
            continue

        sum_r = cs_r[i + 1] - cs_r[start]
        sum_f = cs_f[i + 1] - cs_f[start]
        sum_rf = cs_rf[i + 1] - cs_rf[start]
        sum_f2 = cs_f2[i + 1] - cs_f2[start]

        # slope = (n*sum(rf) - sum(r)*sum(f)) / (n*sum(f^2) - sum(f)^2)
        numer = n_valid * sum_rf - sum_r * sum_f
        denom = n_valid * sum_f2 - sum_f * sum_f
        if abs(denom) < 1e-14:
            continue

        result[i] = numer / denom

    return result


# ===========================================================================
# Feature: microprice (volume-weighted true price estimate) — #119
# ===========================================================================

def compute_microprice(
    high: np.ndarray,
    low: np.ndarray,
    open_arr: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    window: int = DEFAULT_MICROPRICE_WINDOW,
    up_vol: np.ndarray = None,
    down_vol: np.ndarray = None,
) -> np.ndarray:
    """Estimate microprice (true price between bid/ask) from OHLCV.

    The microprice in limit-order-book markets is:
      microprice = (bid_price * ask_qty + ask_price * bid_qty) / (bid_qty + ask_qty)

    From OHLCV data, we estimate it using volume-weighted high/low:
      weight_up = up_vol / max(up_vol + down_vol, 1)
      microprice_raw_i = low_i * (1 - weight_up) + high_i * weight_up

    When buying pressure dominates: microprice -> high (bid side active).
    When selling pressure dominates: microprice -> low (ask side active).
    When balanced: microprice -> midpoint.

    The per-bar microprice is then smoothed with a rolling mean.

    Suitable for AGGRESSIVE_SCALP at short windows (5 bars at 15m = 75m).

    Args:
        high: High prices.
        low: Low prices.
        open_arr: Open prices.
        close: Close prices.
        volume: Volume (base asset).
        window: Smoothing window in bars (default 5).

    Returns:
        numpy array of estimated microprice values, same length as input.
        First ``window - 1`` values are NaN. Values are in price units.
    """
    n = len(high)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result

    if up_vol is None or down_vol is None:
        up_vol, down_vol = _classify_volume_direction(open_arr, close, volume)
    total = up_vol + down_vol

    # Per-bar raw microprice: low * (1 - up_weight) + high * up_weight
    # Vectorized: avoid per-bar Python loop
    raw_mp = np.full(n, np.nan, dtype=np.float64)
    nonzero = total > 0
    if np.any(nonzero):
        weight_up = np.divide(up_vol[nonzero], total[nonzero], dtype=np.float64)
        raw_mp[nonzero] = low[nonzero] * (1.0 - weight_up) + high[nonzero] * weight_up
    zero_total = ~nonzero
    if np.any(zero_total):
        raw_mp[zero_total] = (high[zero_total] + low[zero_total]) * 0.5

    # O(n) rolling mean
    result = _rolling_mean(raw_mp, window, min_periods=2)
    return result


# ===========================================================================
# Feature: liquidity_vacuum (combined low-volume + wide-spread detector) — #119
# ===========================================================================

def _rolling_mean_nan_safe(arr: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling mean (causal, NaN-safe). Uses O(n) cumsum."""
    return _rolling_mean(arr, window, min_periods=2)


def compute_liquidity_vacuum(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    window: int = DEFAULT_LIQUIDITY_VACUUM_WINDOW,
) -> np.ndarray:
    """Detect low-liquidity episodes (liquidity vacuum) from OHLCV.

    A liquidity vacuum occurs when volume drops and spreads widen
    simultaneously — indicating thinning order books and higher
    execution risk.

    Algorithm per bar t:
      1. Compute rolling mean of volume over ``window`` bars.
      2. Compute volume ratio: vol[t] / mean_vol[t]. Low ratio = low volume.
      3. Compute per-bar spread: (high[t] - low[t]) / close[t].
      4. Compute rolling mean of spread, then spread ratio: spread[t] / mean_spread[t].
      5. vacuum[t] = (1 - min(vol_ratio[t], 1)) * max(spread_ratio[t], 1)

    Interpretation:
      0.0         -> normal liquidity (either volume normal or spread normal).
      > 0.0       -> liquidity vacuum intensifying.
      Higher values -> stronger vacuum (drier book).

    The signal is asymmetric: only combinations of low-volume AND wide-spread
    produce non-zero values. Normal conditions map to zero.

    Suitable for AGGRESSIVE_SCALP intraday microstructure monitoring.

    Args:
        high: High prices.
        low: Low prices.
        close: Close prices.
        volume: Volume (base asset).
        window: Rolling window for baselines (default 10).

    Returns:
        numpy array of liquidity vacuum scores >= 0, same length as input.
        First ``window - 1`` values are NaN.
    """
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result

    # 1. Volume ratio: vol / mean_vol
    vol_mean = _rolling_mean_nan_safe(volume, window)
    vol_ratio = np.full(n, np.nan, dtype=np.float64)
    valid_vol = vol_mean > 0
    vol_ratio[valid_vol] = volume[valid_vol] / vol_mean[valid_vol]

    # 2. Per-bar spread
    raw_spread = np.full(n, np.nan, dtype=np.float64)
    valid_close = close > 0
    with np.errstate(divide="ignore", invalid="ignore"):
        raw_spread[valid_close] = (high[valid_close] - low[valid_close]) / close[valid_close]

    spread_mean = _rolling_mean_nan_safe(raw_spread, window)
    spread_ratio = np.full(n, np.nan, dtype=np.float64)
    valid_spread = spread_mean > 0
    spread_ratio[valid_spread] = raw_spread[valid_spread] / spread_mean[valid_spread]

    # 3. Combine: low volume penalty * wide spread penalty
    # Only activates when both conditions are adverse
    for i in range(window - 1, n):
        vr = vol_ratio[i]
        sr = spread_ratio[i]
        if np.isnan(vr) or np.isnan(sr):
            continue
        vol_penalty = max(0.0, 1.0 - vr)      # 0 when volume >= normal
        spread_penalty = max(1.0, sr) - 1.0   # 0 when spread <= normal
        result[i] = vol_penalty * spread_penalty

    return result


# ===========================================================================
# Feature: depth_ratio (bid/ask depth proxy from volume classification) — #119
# ===========================================================================

def compute_depth_ratio(
    open_arr: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    window: int = DEFAULT_DEPTH_RATIO_WINDOW,
    up_vol: np.ndarray = None,
    down_vol: np.ndarray = None,
) -> np.ndarray:
    """Estimate bid/ask depth ratio from volume classification.

    Uses OHLCV-based buy/sell volume classification to estimate the
    ratio of buy depth to sell depth:

      per_bar_ratio[t] = up_vol[t] / max(down_vol[t], epsilon)
      depth_ratio[t] = mean(per_bar_ratio[t-window+1 .. t])

    Interpretation:
      > 1  -> more buy-side depth (bids dominate)
      < 1  -> more sell-side depth (asks dominate)
      ~ 1  -> balanced book

    This provides a complementary perspective to volume_imbalance:
    volume_imbalance measures net flow (up-down)/total, while depth_ratio
    measures the ratio of buy to sell volume directly.

    Suitable for AGGRESSIVE_SCALP at short windows (5 bars at 15m = 75m).

    Args:
        open_arr: Open prices.
        close: Close prices.
        volume: Volume (base asset).
        window: Smoothing window in bars (default 5).
        up_vol: Precomputed up volume (optional).
        down_vol: Precomputed down volume (optional).

    Returns:
        numpy array of depth ratio estimates >= 0, same length as input.
        First ``window - 1`` values are NaN.
    """
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result

    if up_vol is None or down_vol is None:
        up_vol, down_vol = _classify_volume_direction(open_arr, close, volume)

    # Per-bar depth ratio (vectorized: avoid per-bar Python loop)
    per_bar = np.full(n, np.nan, dtype=np.float64)
    short = np.maximum(down_vol, 1e-10)
    per_bar = np.divide(up_vol, short, dtype=np.float64)

    # O(n) rolling mean
    result = _rolling_mean(per_bar, window, min_periods=2)
    return result


# ===========================================================================
# Feature: compute_orderbook_imbalance (L1 Order Book Imbalance) — #154
# ===========================================================================

def compute_orderbook_imbalance(
    open_arr: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    up_vol: np.ndarray = None,
    down_vol: np.ndarray = None,
) -> np.ndarray:
    """Compute per-bar Level 1 Order Book Imbalance (L1 OBI) from OHLCV.

    OBI[t] = (up_volume[t] - down_volume[t]) / max(up_volume[t] + down_volume[t], eps)

    Uses OHLCV-based buy/sell volume classification consistent with
    compute_volume_imbalance and _classify_volume_direction:
      - close > open  -> buy volume
      - close < open  -> sell volume
      - close == open -> split evenly

    This is the instantaneous per-bar imbalance, UNLIKE compute_volume_imbalance
    which returns a rolling window mean. L1 OBI captures the raw order flow
    imbalance at each bar with no temporal smoothing.

    Interpretation:
      Positive -> buying pressure (more up-volume than down-volume).
      Negative -> selling pressure (more down-volume than up-volume).
      Zero     -> balanced flow or zero-volume bar.
    Range: [-1, +1].

    Causality: at bar t uses only open[t], close[t], volume[t].
    No NaN values (returns 0.0 for zero-volume bars).

    Args:
        open_arr: Open prices.
        close: Close prices.
        volume: Volume (base asset).
        up_vol: Precomputed up volume (optional).
        down_vol: Precomputed down volume (optional).

    Returns:
        numpy array of OBI values in [-1, +1], same length as input.
        No NaN values ever (zero-volume bars return 0.0).
    """
    n = len(volume)
    if up_vol is None or down_vol is None:
        up_vol, down_vol = _classify_volume_direction(open_arr, close, volume)
    total = up_vol + down_vol

    result = np.zeros(n, dtype=np.float64)
    non_zero = total > 0
    result[non_zero] = (up_vol[non_zero] - down_vol[non_zero]) / total[non_zero]

    return result


# ===========================================================================
# Feature: compute_multi_level_obi (Multi-level OBI with depth decay) — #165
# ===========================================================================

def compute_multi_level_obi(
    open_arr: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    n_levels: int = DEFAULT_MULTI_LEVEL_OBI_N,
    step: int = DEFAULT_MULTI_LEVEL_OBI_STEP,
    decay: float = DEFAULT_MULTI_LEVEL_OBI_DECAY,
    obi: np.ndarray = None,
    up_vol: np.ndarray = None,
    down_vol: np.ndarray = None,
) -> np.ndarray:
    """Compute multi-level Order Book Imbalance with depth-decaying weights.

    Simulates multi-level order book imbalance by computing OBI at
    progressively longer lookback horizons and combining with
    exponentially decaying level weights:

      For level k in [0, n_levels-1]:
        window_k = (k + 1) * step
        obi_k[t] = rolling_mean(raw_obi, window_k)[t]
        weight_k = exp(-k * decay)

      multi_obi[t] = sum(obi_k[t] * weight_k for k) / sum(weight_k for k)

    Each level k represents a different effective "depth" in the order book:
      - Level 0 (k=0): top of book, shortest window, highest weight
      - Level 1 (k=1): first hidden level, medium window
      - ...
      - Level N-1: deepest level, longest window, lowest weight

    The exponential decay assigns less importance to deeper levels,
    consistent with the diminishing information content of deeper
    order book levels.

    Range: [-1, +1]. Values track the same interpretation as L1 OBI
    but with multi-horizon smoothing.

    Causality: at bar t uses only bars [t - max_window + 1 .. t]
    where max_window = n_levels * step.

    Args:
        open_arr: Open prices.
        close: Close prices.
        volume: Volume (base asset).
        n_levels: Number of depth levels (default 5). Must be >= 1.
        step: Lookback step between levels in bars (default 3).
        decay: Exponential decay factor for level weights (default 0.8).
            Higher values discount deeper levels more aggressively.
        obi: Precomputed per-bar OBI (optional).
        up_vol: Precomputed up volume (optional).
        down_vol: Precomputed down volume (optional).

    Returns:
        numpy array of multi-level OBI values in [-1, +1], same length
        as input. First `n_levels * step - 1` values are NaN.
    """
    n = len(volume)
    max_window = n_levels * step
    result = np.full(n, np.nan, dtype=np.float64)

    if n < max_window or n_levels < 1 or step < 1:
        return result

    # Per-bar raw OBI
    if obi is None:
        obi = compute_orderbook_imbalance(open_arr, close, volume, up_vol=up_vol, down_vol=down_vol)

    # Pre-compute level weights: exponential decay with depth
    weights = np.array(
        [math.exp(-k * decay) for k in range(n_levels)],
        dtype=np.float64,
    )
    total_weight = np.sum(weights)

    # Single cumsum for obi (obi has no NaN — zero-volume bars return 0.0)
    # Use this for all window sizes instead of recomputing cumsum per level
    csum = np.cumsum(np.insert(obi, 0, 0))

    # For each level, compute rolling mean via vectorized cumsum slice:
    # mean_k[i] = (csum[i+1] - csum[i-w+1]) / w   for i >= w-1
    # Store partial sum per level, combine in second pass
    result = np.full(n, np.nan, dtype=np.float64)
    for i in range(max_window - 1, n):
        val_sum = 0.0
        for k in range(n_levels):
            w = (k + 1) * step
            start = i - w + 1
            mean = (csum[i + 1] - csum[start]) / w
            val_sum += mean * weights[k]
        result[i] = val_sum / total_weight

    return result


# ===========================================================================
# Feature: compute_micro_price (Stoikov contrarian micro-price) — #170
# ===========================================================================

def compute_micro_price(
    high: np.ndarray,
    low: np.ndarray,
    open_arr: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    window: int = DEFAULT_STOIKOV_MICRO_PRICE_WINDOW,
    up_vol: np.ndarray = None,
    down_vol: np.ndarray = None,
) -> np.ndarray:
    """Compute Stoikov micro-price estimate from OHLCV.

    The Stoikov micro-price is a cross-product of bid/ask prices and
    quantities from the limit order book:
      micro_price = (P_bid * V_ask + P_ask * V_bid) / (V_bid + V_ask)

    From OHLCV data, we proxy:
      P_bid ~ low, P_ask ~ high
      V_bid ~ down_volume, V_ask ~ up_volume

    This gives the per-bar Stoikov micro-price:
      raw_mp[t] = (low[t] * up_vol[t] + high[t] * down_vol[t]) / total[t]

    Which is equivalent to:
      raw_mp[t] = midprice[t] - half_spread[t] * OBI[t]

    Key difference from compute_microprice:
      Existing compute_microprice: low + (high-low) * up_vol/total
        -> pro-cyclical: buying -> toward high, selling -> toward low
      Stoikov compute_micro_price: low * up_vol/total + high * down_vol/total
        -> contrarian: buying -> toward low, selling -> toward high

    The per-bar estimate is smoothed with a rolling mean.

    Interpretation:
      Heavy buying (OBI > 0): micro_price pulled toward the bid (low).
      Heavy selling (OBI < 0): micro_price pulled toward the ask (high).
      Balanced flow (OBI ~ 0): micro_price at midpoint.

    Suitable for AGGRESSIVE_SCALP at short windows (5 bars).

    Causality: at bar t uses open[t], high[t], low[t], close[t],
    volume[t] plus up to `window - 1` prior bars for smoothing.

    Args:
        high: High prices.
        low: Low prices.
        open_arr: Open prices.
        close: Close prices.
        volume: Volume (base asset).
        window: Smoothing window in bars (default 5).
        up_vol: Precomputed up volume (optional).
        down_vol: Precomputed down volume (optional).

    Returns:
        numpy array of Stoikov micro-price estimates, same length as
        input. First `window - 1` values are NaN.
        Values are in price units, always between low and high.
    """
    n = len(high)
    result = np.full(n, np.nan, dtype=np.float64)

    if n < window:
        return result

    if up_vol is None or down_vol is None:
        up_vol, down_vol = _classify_volume_direction(open_arr, close, volume)
    total = up_vol + down_vol

    # Per-bar raw Stoikov micro-price (vectorized)
    # raw_mp = (low * up_vol + high * down_vol) / total
    raw_mp = np.full(n, np.nan, dtype=np.float64)
    nonzero = total > 0
    if np.any(nonzero):
        raw_mp[nonzero] = (low[nonzero] * up_vol[nonzero] + high[nonzero] * down_vol[nonzero]) / total[nonzero]
    zero_total = ~nonzero
    if np.any(zero_total):
        raw_mp[zero_total] = (high[zero_total] + low[zero_total]) * 0.5

    # O(n) rolling mean
    result = _rolling_mean(raw_mp, window, min_periods=2)
    return result


# ===========================================================================
# Feature: compute_ofi (Order Flow Imbalance, Cont-Kukanov-Stoikov style)
# ===========================================================================

def compute_ofi(
    open_arr: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    window: int = DEFAULT_OFI_WINDOW,
    up_vol: np.ndarray = None,
    down_vol: np.ndarray = None,
) -> np.ndarray:
    """Compute Order Flow Imbalance proxy from OHLCV (Cont-Kukanov-Stoikov style).

    Per-bar raw OFI is the signed volume imbalance:
      raw_ofi[i] = (up_vol[i] - down_vol[i]) / (up_vol[i] + down_vol[i])

    Range per bar: [-1, +1].
      +1 -> all volume classified as buy (close > open)
      -1 -> all volume classified as sell (close < open)
       0 -> balanced or zero-volume bar

    The windowed OFI is the rolling mean of per-bar imbalances:
      OFI[t] = mean(raw_ofi[t-window+1 .. t])

    This differs from volume_imbalance (which aggregates volume before computing
    the ratio over the window) by computing the ratio per-bar first and then
    averaging. Volume imbalance weights each bar by its volume; OFI weights
    each bar equally. When volume varies, these diverge materially.

    Uses OHLCV-based buy/sell volume classification consistent with
    _classify_volume_direction (used by volume_imbalance, vpin, etc.).

    Causality: at t uses open, close, volume up to index t.

    Args:
        open_arr: Open prices.
        close: Close prices.
        volume: Volume (base asset).
        window: Rolling window for smoothing (default 10).
        up_vol: Precomputed up volume (optional).
        down_vol: Precomputed down volume (optional).

    Returns:
        numpy array of OFI values in [-1, 1] (same length as input).
        First `window-1` values are NaN.
        NaN also when a window has no non-NaN raw imbalances.
    """
    n = len(volume)
    result = np.full(n, np.nan, dtype=np.float64)

    if n < window:
        return result

    if up_vol is None or down_vol is None:
        up_vol, down_vol = _classify_volume_direction(open_arr, close, volume)
    total_vol = up_vol + down_vol

    # Per-bar raw OFI (vectorized)
    raw_ofi = np.zeros(n, dtype=np.float64)
    nonzero = total_vol > 1e-12
    if np.any(nonzero):
        raw_ofi[nonzero] = (up_vol[nonzero] - down_vol[nonzero]) / total_vol[nonzero]
    # zero volume bars already 0.0

    # O(n) rolling mean
    result = _rolling_mean(raw_ofi, window, min_periods=2)
    return result


# ===========================================================================
# Feature: compute_vamp (Volume-Adjusted Mid Price)
# ===========================================================================

def compute_vamp(
    high: np.ndarray,
    low: np.ndarray,
    open_arr: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    window: int = DEFAULT_VAMP_WINDOW,
) -> np.ndarray:
    """Compute Volume-Adjusted Mid Price (VAMP).

    VAMP is the volume-weighted rolling mean of the bar midpoint:

      1. Per-bar midpoint: mid[i] = (high[i] + low[i]) / 2
      2. VAMP[t] = sum(mid[i] * volume[i] for i in [t-window+1 .. t])
                   / sum(volume[i] for i in [t-window+1 .. t])

    This differs from microprice in two ways:
      - VAMP uses the simple midpoint (high+low)/2, not the buy/sell weighted price.
      - VAMP weights by total volume, giving more influence to high-activity bars
        where the price estimate is more reliable.

    When volume is zero for all bars in the window, VAMP falls back to the
    simple mean of midpoints (equal weight).

    Interpretation:
      VAMP is an estimate of the "fair" price that accounts for trading activity.
      When VAMP > close, recent high-volume bars traded higher on average;
      the current price may be below its volume-weighted average.
      When VAMP < close, recent high-volume bars traded lower on average.

    Suitable for AGGRESSIVE_SCALP at short windows (5 bars at 15m = 75m).

    Causality: at t uses high, low, volume up to index t.

    Args:
        high: High prices.
        low: Low prices.
        open_arr: Open prices (unused but included for interface consistency).
        close: Close prices (unused but included for interface consistency).
        volume: Volume (base asset).
        window: Smoothing window in bars (default 5).

    Returns:
        numpy array of VAMP values in price units (same length as input).
        First `window-1` values are NaN.
    """
    n = len(high)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result

    # Per-bar midpoint
    mid = (high + low) * 0.5

    # O(n) volume-weighted rolling mean via cumsum
    # VAMP[t] = sum(mid * volume) / sum(volume) over rolling window
    mid_v = mid.astype(np.float64)
    vol_v = volume.astype(np.float64)
    # NaN-safe: set NaN mid/vol to 0 for cumsum, track valid counts
    mid_nan = np.isnan(mid_v)
    vol_nan = np.isnan(vol_v) | (vol_v < 0)
    invalid_mask = mid_nan | vol_nan
    clean_mid = np.where(invalid_mask, 0.0, mid_v)
    clean_vol = np.where(invalid_mask, 0.0, vol_v)
    csum_midvol = np.cumsum(np.insert(clean_mid * clean_vol, 0, 0))
    csum_vol = np.cumsum(np.insert(clean_vol, 0, 0))
    csum_invalid = np.cumsum(np.insert(invalid_mask.astype(np.float64), 0, 0))
    csum_mid = np.cumsum(np.insert(np.where(invalid_mask, 0.0, mid_v), 0, 0))
    for i in range(window - 1, n):
        count = window - (csum_invalid[i + 1] - csum_invalid[i - window + 1])
        if count < 2:
            continue
        vol_sum = csum_vol[i + 1] - csum_vol[i - window + 1]
        if vol_sum > 1e-12:
            pv_sum = csum_midvol[i + 1] - csum_midvol[i - window + 1]
            result[i] = pv_sum / vol_sum
        else:
            # Fall back to simple mean when all volume is zero
            mid_total = csum_mid[i + 1] - csum_mid[i - window + 1]
            result[i] = mid_total / count

    return result


# ===========================================================================
# Feature: compute_quoted_spread (effective quoted spread proxy)
# ===========================================================================

def compute_quoted_spread(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    window: int = DEFAULT_QUOTED_SPREAD_WINDOW,
) -> np.ndarray:
    """Compute effective quoted spread proxy from OHLCV.

    Uses the absolute deviation of close from the intraday midpoint to estimate
    the effective half-spread, then scales to a round-trip quoted spread:

      mid[t] = (high[t] + low[t]) / 2
      half_spread[t] = |close[t] - mid[t]| / mid[t]
      quoted_spread[t] = 2 * half_spread[t]

    The rolling mean over ``window`` bars smooths per-bar noise.

    Interpretation:
      Higher values -> wider effective spreads (higher transaction costs).
      Lower values -> tighter effective spreads (lower transaction costs).
      This is complementary to compute_spread_pct: that measures the full
      intraday range, while this measures the deviation from the midpoint
      at bar close (effective spread paid by a round-trip trade).

    Causality: at t uses high, low, close up to index t only.

    Args:
        high: High prices.
        low: Low prices.
        close: Close prices.
        window: Rolling window for smoothing (default 10).

    Returns:
        numpy array of quoted spread estimates (fraction, e.g. 0.001 = 0.1%).
        First ``window - 1`` values are NaN.
        Values are in [0, +inf).
    """
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)

    if n < window:
        return result

    # Per-bar effective quoted spread
    raw_spread = np.full(n, np.nan, dtype=np.float64)
    mid = (high + low) * 0.5
    valid = mid > 0
    with np.errstate(divide="ignore", invalid="ignore"):
        raw_spread[valid] = 2.0 * np.abs(close[valid] - mid[valid]) / mid[valid]

    # O(n) rolling mean
    result = _rolling_mean(raw_spread, window, min_periods=2)
    return result


# ===========================================================================
# Feature: compute_vwap_to_mid_deviation
# ===========================================================================

def compute_vwap_to_mid_deviation(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    window: int = DEFAULT_VWAP_MID_WINDOW,
) -> np.ndarray:
    """Compute the deviation of rolling VWAP from the midpoint price.

    For each bar t, computes:
      1. typical_price[t] = (high[t] + low[t] + close[t]) / 3
      2. Rolling VWAP over [t-window+1 .. t]:
         vwap[t] = sum(typical_price[i] * volume[i]) / sum(volume[i])
      3. mid[t] = (high[t] + low[t]) / 2
      4. deviation[t] = (mid[t] - vwap[t]) / vwap[t]

    Positive deviation -> mid > VWAP (closing price is above the volume-weighted
      average execution price -> buying pressure dominated during the window).
    Negative deviation -> mid < VWAP (selling pressure dominated).
    Near zero -> balanced order flow over the window.

    This captures directional order flow pressure: when aggressive buyers
    dominate, they push prices up through the VWAP, creating positive deviation.
    When sellers dominate, they push prices below VWAP.

    Causality: at t uses high, low, close, volume up to index t only.

    Args:
        high: High prices.
        low: Low prices.
        close: Close prices.
        volume: Volume (base asset).
        window: Rolling window for VWAP computation (default 10).

    Returns:
        numpy array of VWAP-to-mid deviations as fractions (same length as input).
        First ``window - 1`` values are NaN.
        Values are typically in [-0.01, 0.01] for liquid markets.
    """
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)

    if n < window:
        return result

    # Per-bar typical price for VWAP computation
    typical_price = (high + low + close) / 3.0

    # O(n) via cumsum
    tp_v = typical_price.astype(np.float64)
    vol_v = volume.astype(np.float64)
    mid = (high + low) * 0.5

    # NaN-safe: set NaN to 0 for cumsum
    tp_nan = np.isnan(tp_v)
    vol_nan = np.isnan(vol_v) | (vol_v < 0)
    invalid = tp_nan | vol_nan
    clean_tp = np.where(invalid, 0.0, tp_v)
    clean_vol = np.where(invalid, 0.0, vol_v)
    csum_pv = np.cumsum(np.insert(clean_tp * clean_vol, 0, 0))
    csum_vol = np.cumsum(np.insert(clean_vol, 0, 0))
    csum_invalid = np.cumsum(np.insert(invalid.astype(np.float64), 0, 0))

    for i in range(window - 1, n):
        count = window - (csum_invalid[i + 1] - csum_invalid[i - window + 1])
        if count < 2:
            continue
        total_vol = csum_vol[i + 1] - csum_vol[i - window + 1]
        if total_vol > 0:
            total_pv = csum_pv[i + 1] - csum_pv[i - window + 1]
            if not np.isnan(total_pv):
                vwap = total_pv / total_vol
                if vwap > 0:
                    result[i] = (mid[i] - vwap) / vwap

    return result


# ===========================================================================
# Feature: compute_trade_count (volume z-score proxy)
# ===========================================================================

def compute_trade_count(
    volume: np.ndarray,
    window: int = DEFAULT_TRADE_COUNT_WINDOW,
) -> np.ndarray:
    """Compute trade count proxy as rolling z-score of volume.

    Since actual trade count data is not available from OHLCV data alone,
    volume is used as a linear proxy for trade count (more volume implies
    more trading activity). The z-score standardisation measures how unusual
    the current trade activity is relative to its recent history:

      mean_vol[t] = mean(volume[t-window+1 .. t])
      std_vol[t] = std(volume[t-window+1 .. t], ddof=1)
      trade_count[t] = (volume[t] - mean_vol[t]) / std_vol[t]

    Interpretation:
      Positive -> more trades than usual (elevated activity, potential news/
        large participant entry).
      Near zero -> normal trade activity for this symbol/session.
      Negative -> fewer trades than usual (quiet market, reduced liquidity).

    This is distinct from volume_ratio_N (which is volume[t] / mean_vol[t]):
    volume_ratio captures only the proportion relative to mean, while the
    z-score also accounts for the variance. When volume is normally stable,
    a small deviation produces a high z-score (strong signal). When volume
    is normally volatile, the same deviation produces a lower z-score.

    Causality: at t uses volume up to index t only.

    Args:
        volume: Volume (base asset).
        window: Rolling window for mean/std computation (default 20).
            Must be >= 3 for meaningful z-score.

    Returns:
        numpy array of z-score values (same length as input).
        First ``window - 1`` values are NaN.
        NaN also when rolling standard deviation is zero (constant volume).
    """
    n = len(volume)
    result = np.full(n, np.nan, dtype=np.float64)

    if n < window:
        return result

    # O(n) rolling z-score via cumsum mean + std
    vol_mean = _rolling_mean(volume, window, min_periods=3)
    vol_var = _rolling_var(volume, window, min_periods=3, ddof=1)
    vol_std = np.sqrt(vol_var)
    mask = (vol_std > 1e-14) & ~np.isnan(volume) & ~np.isnan(vol_mean)
    result[mask] = (volume[mask] - vol_mean[mask]) / vol_std[mask]

    return result


# ===========================================================================
# Feature: compute_volume_concentration_hhi (Herfindahl-Hirschman Index)
# ===========================================================================

def compute_volume_concentration_hhi(
    volume: np.ndarray,
    window: int = DEFAULT_VOLUME_CONCENTRATION_WINDOW,
) -> np.ndarray:
    """Compute volume concentration using Herfindahl-Hirschman Index (HHI).

    For each rolling window [t-window+1 .. t]:
      total_vol = sum(volume[i] for i in window)
      share[i] = volume[i] / total_vol for each bar in window
      HHI[t] = sum(share[i]^2 for i in window)

    Range: [1/window, 1]
      1/window = perfect dispersion (all bars have equal volume).
      1 = perfect concentration (one bar has all the volume).
      0 = zero total volume in window.

    Interpretation:
      Low HHI -> volume evenly distributed across bars (steady, continuous
        trading -- typical of liquid markets during normal conditions).
      High HHI -> volume concentrated in a few bars (block trades, burst
        activity, scheduled news events, or flash crashes).

    This captures a different aspect of volume than trade_intensity or
    trade_count: it measures how evenly volume is distributed across bars,
    rather than the absolute level or per-bar deviation of volume.

    Causality: at t uses volume up to index t only.

    Args:
        volume: Volume (base asset).
        window: Rolling window for HHI computation (default 20).

    Returns:
        numpy array of HHI values in [0, 1] (same length as input).
        First ``window - 1`` values are NaN.
        0 when total volume in window is zero.
    """
    n = len(volume)
    result = np.full(n, np.nan, dtype=np.float64)

    if n < window:
        return result

    # O(n) rolling HHI via cumsum
    vol_v = volume.astype(np.float64)
    vol_nan = np.isnan(vol_v)
    clean = np.where(vol_nan, 0.0, vol_v)
    csum = np.cumsum(np.insert(clean, 0, 0))
    csum2 = np.cumsum(np.insert(clean * clean, 0, 0))
    csum_nan = np.cumsum(np.insert(vol_nan.astype(np.float64), 0, 0))

    for i in range(window - 1, n):
        count = window - (csum_nan[i + 1] - csum_nan[i - window + 1])
        if count < 2:
            continue
        total = csum[i + 1] - csum[i - window + 1]
        if total > 0:
            # HHI = sum((v_i / total)^2) = sum(v_i^2) / total^2
            sum_sq = csum2[i + 1] - csum2[i - window + 1]
            result[i] = sum_sq / (total * total)
        else:
            result[i] = 0.0

    return result


# ===========================================================================
# OrderBook Group
# ===========================================================================

def compute_orderbook_group(
    open_arr: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    window: int = DEFAULT_ORDERBOOK_WINDOW,
    amihud_window: int = DEFAULT_AMIHUD_WINDOW,
    roll_spread_window: int = DEFAULT_ROLL_SPREAD_WINDOW,
    noise_window: int = DEFAULT_NOISE_WINDOW,
    serial_corr_window: int = DEFAULT_SERIAL_CORR_WINDOW,
    vpin_window: int = DEFAULT_VPIN_WINDOW,
    price_impact_window: int = DEFAULT_PRICE_IMPACT_WINDOW,
    microprice_window: int = DEFAULT_MICROPRICE_WINDOW,
    liquidity_vacuum_window: int = DEFAULT_LIQUIDITY_VACUUM_WINDOW,
    depth_ratio_window: int = DEFAULT_DEPTH_RATIO_WINDOW,
    # New windows for extended feature set
    multi_level_obi_n: int = DEFAULT_MULTI_LEVEL_OBI_N,
    multi_level_obi_step: int = DEFAULT_MULTI_LEVEL_OBI_STEP,
    multi_level_obi_decay: float = DEFAULT_MULTI_LEVEL_OBI_DECAY,
    stoikov_micro_price_window: int = DEFAULT_STOIKOV_MICRO_PRICE_WINDOW,
    ofi_window: int = DEFAULT_OFI_WINDOW,
    vamp_window: int = DEFAULT_VAMP_WINDOW,
    quoted_spread_window: int = DEFAULT_QUOTED_SPREAD_WINDOW,
    vwap_mid_window: int = DEFAULT_VWAP_MID_WINDOW,
    trade_count_window: int = DEFAULT_TRADE_COUNT_WINDOW,
    volume_concentration_window: int = DEFAULT_VOLUME_CONCENTRATION_WINDOW,
) -> Dict[str, np.ndarray]:
    """Compute all OrderBook microstructure proxy features (19 total).

    Returns dict with keys:
      - spread_pct_N: rolling mean of (high-low)/close
      - volume_imbalance_N: (up_vol - down_vol) / total_vol
      - trade_intensity_N: volume*range/close normalized
      - amihud_illiquidity_N: Amihud price impact measure
      - roll_spread_N: Roll (1984) effective bid-ask spread
      - microstructure_noise_N: variance ratio noise measure
      - serial_correlation_N: return autocorrelation at lag 1
      - vpin_N: VPIN order flow toxicity proxy
      - price_impact_slope_N: Kyle's lambda proxy
      - microprice_N: volume-weighted true price estimate (#119)
      - liquidity_vacuum_N: low-volume + wide-spread detector (#119)
      - depth_ratio_N: buy/sell depth ratio from volume classification (#119)
      - obi: per-bar Level 1 order book imbalance (#154)
      - multi_level_obi_N: multi-level OBI with depth decay (#165)
      - ofi_N: per-bar equally-weighted order flow imbalance
      - quoted_spread_N: effective quoted spread proxy
      - vwap_mid_deviation_N: rolling VWAP deviation from midpoint
      - trade_count_N: trade count proxy (volume z-score)
      - volume_concentration_hhi_N: Herfindahl-Hirschman Index of volume

    stoikov_micro_price_N and vamp_N are removed because they produce
    identical values to microprice_N on OHLCV-only data (r=1.0).

    All arrays are same length as input. NaN at start for insufficient
    lookback windows.

    Args:
        open_arr: Open prices.
        high: High prices.
        low: Low prices.
        close: Close prices.
        volume: Volume (base asset).
        window: Window for spread, imbalance, and intensity (default 10).
        amihud_window: Window for Amihud illiquidity (default 15).
        roll_spread_window: Window for Roll spread (default 20).
        noise_window: Window for microstructure noise (default 20).
        serial_corr_window: Window for return autocorrelation (default 10).
        vpin_window: Window for VPIN (default 50).
        price_impact_window: Window for price impact slope (default 15).
        microprice_window: Window for microprice smoothing (default 5).
        liquidity_vacuum_window: Window for liquidity vacuum (default 10).
        depth_ratio_window: Window for depth ratio (default 5).
        multi_level_obi_n: Number of depth levels for multi-level OBI (default 5).
        multi_level_obi_step: Lookback step between OBI levels (default 3).
        multi_level_obi_decay: Exponential decay for level weights (default 0.8).
        ofi_window: Window for order flow imbalance (default 10).
        quoted_spread_window: Window for quoted spread (default 10).
        vwap_mid_window: Window for VWAP-mid deviation (default 10).
        trade_count_window: Window for trade count proxy (default 20).
        volume_concentration_window: Window for volume HHI (default 20).

    Returns:
        Dict mapping feature name to numpy array of shape (n_bars,).
    """
    # Precompute shared intermediates once (saves ~12 redundant calls)
    up_vol, down_vol = _classify_volume_direction(open_arr, close, volume)
    obi = compute_orderbook_imbalance(open_arr, close, volume, up_vol=up_vol, down_vol=down_vol)

    return {
        "spread_pct_N": compute_spread_pct(high, low, close, window),
        "volume_imbalance_N": compute_volume_imbalance(open_arr, close, volume, window, up_vol=up_vol, down_vol=down_vol),
        "trade_intensity_N": compute_trade_intensity(high, low, close, volume, window),
        "amihud_illiquidity_N": compute_amihud_illiquidity_numpy(close, volume, amihud_window),
        "roll_spread_N": compute_roll_spread(close, roll_spread_window),
        "microstructure_noise_N": compute_microstructure_noise(close, noise_window),
        "serial_correlation_N": compute_serial_correlation(close, serial_corr_window),
        "vpin_N": compute_vpin(open_arr, close, volume, vpin_window, up_vol=up_vol, down_vol=down_vol),
        "price_impact_slope_N": compute_price_impact_slope(
            open_arr, high, low, close, volume, price_impact_window,
            up_vol=up_vol, down_vol=down_vol,
        ),
        "microprice_N": compute_microprice(high, low, open_arr, close, volume, microprice_window, up_vol=up_vol, down_vol=down_vol),
        "liquidity_vacuum_N": compute_liquidity_vacuum(high, low, close, volume, liquidity_vacuum_window),
        "depth_ratio_N": compute_depth_ratio(open_arr, close, volume, depth_ratio_window, up_vol=up_vol, down_vol=down_vol),
        "obi": obi,
        "multi_level_obi_N": compute_multi_level_obi(
            open_arr, close, volume,
            n_levels=multi_level_obi_n,
            step=multi_level_obi_step,
            decay=multi_level_obi_decay,
            obi=obi, up_vol=up_vol, down_vol=down_vol,
        ),
        "ofi_N": compute_ofi(open_arr, close, volume, window=ofi_window, up_vol=up_vol, down_vol=down_vol),
        "quoted_spread_N": compute_quoted_spread(high, low, close, window=quoted_spread_window),
        "vwap_mid_deviation_N": compute_vwap_to_mid_deviation(
            high, low, close, volume, window=vwap_mid_window,
        ),
        "trade_count_N": compute_trade_count(volume, window=trade_count_window),
        "volume_concentration_hhi_N": compute_volume_concentration_hhi(
            volume, window=volume_concentration_window,
        ),
    }
