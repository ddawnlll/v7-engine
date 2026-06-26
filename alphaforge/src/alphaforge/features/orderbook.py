"""OrderBook Feature Group — microstructure-aware features from OHLCV data.

Authority: AlphaForge owns feature discovery and specification.
This module computes microstructure proxy features from OHLCV data only.
No real order book data is used in v0.2 — all features are OHLCV proxies.

Primary target mode: AGGRESSIVE_SCALP (15m primary, 5m refinement).
Secondary applicability: SCALP and SWING with adjusted window parameters.

Features:
  - spread_pct_N: rolling mean of (high-low)/close — spread proxy
  - volume_imbalance_N: rolling (up_volume - down_volume) / total_volume
  - trade_intensity_N: volume * (high-low)/close normalized by rolling mean
  - amihud_illiquidity_N: Amihud (2002) price impact measure

Design constraints:
  - numpy only (no pandas, scipy, ta-lib) except lib/indicators bridge
  - no network calls, no exchange APIs, no real market data
  - all features are causal: feature at bar[t] uses bars [t-lookback+1 .. t]
  - NaN fill for insufficient lookback at series start
  - deterministic: same input always produces identical output
  - lib/indicators.microstructure.amihud_illiquidity bridged via list conversion

Causality contract:
  Every feature at index t accesses data only from indices [max(0, t - window + 1), t].
  No index > t is ever accessed.
"""

from __future__ import annotations

import logging
from typing import Dict, List

import numpy as np

from lib.indicators.microstructure import amihud_illiquidity, dollar_volume

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# AGGRESSIVE_SCALP mode defaults (15m primary bars)
# Shorter windows than SWING to capture microstructure dynamics
AGGRESSIVE_SPREAD_WINDOW: int = 10
AGGRESSIVE_IMBALANCE_WINDOW: int = 10
AGGRESSIVE_INTENSITY_WINDOW: int = 10
AGGRESSIVE_AMIHUD_WINDOW: int = 15
AGGRESSIVE_PERIODS_PER_YEAR: int = 35040  # 365 * 24 * 4 (15m bars)

# Generic defaults usable across modes
DEFAULT_ORDERBOOK_WINDOW: int = 10
DEFAULT_AMIHUD_WINDOW: int = 15


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
      - close > open  → up_volume = volume, down_volume = 0
      - close < open  → up_volume = 0, down_volume = volume
      - close == open → up_volume = volume/2, down_volume = volume/2

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
    result = np.full(n, np.nan, dtype=np.float64)

    if n < window:
        return result

    # Per-bar raw spread (NaN-safe: skip bars where close <= 0)
    raw_spread = np.full(n, np.nan, dtype=np.float64)
    valid_close = close > 0
    with np.errstate(divide="ignore", invalid="ignore"):
        raw_spread[valid_close] = (high[valid_close] - low[valid_close]) / close[valid_close]

    # Rolling mean over valid raw_spread values
    for i in range(window - 1, n):
        seg = raw_spread[i - window + 1 : i + 1]
        seg_clean = seg[~np.isnan(seg)]
        if len(seg_clean) >= 2:
            result[i] = np.mean(seg_clean)
        # else: result[i] stays NaN

    return result


# ===========================================================================
# Feature: volume_imbalance (buy vs sell pressure proxy)
# ===========================================================================

def compute_volume_imbalance(
    open_arr: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    window: int = DEFAULT_ORDERBOOK_WINDOW,
) -> np.ndarray:
    """Compute rolling volume imbalance: (up_volume - down_volume) / total_volume.

    Uses OHLCV-based buy/sell classification:
      - close > open  → buy volume
      - close < open  → sell volume
      - close == open → split evenly

    Positive values indicate buying pressure (more up-volume than down-volume).
    Negative values indicate selling pressure.
    Range: [-1, +1]. Values near 0 indicate balanced volume.

    Args:
        open_arr: Open prices.
        close: Close prices.
        volume: Volume (base asset).
        window: Rolling window (default 10).

    Returns:
        numpy array of volume imbalance values (same length as input).
        First `window-1` values are NaN.
    """
    n = len(volume)
    result = np.full(n, np.nan, dtype=np.float64)

    if n < window:
        return result

    up_vol, down_vol = _classify_volume_direction(open_arr, close, volume)

    for i in range(window - 1, n):
        seg_up = up_vol[i - window + 1 : i + 1]
        seg_down = down_vol[i - window + 1 : i + 1]
        total = np.sum(seg_up) + np.sum(seg_down)
        if total > 0:
            result[i] = (np.sum(seg_up) - np.sum(seg_down)) / total
        else:
            result[i] = 0.0  # zero volume window → balanced

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
    result = np.full(n, np.nan, dtype=np.float64)

    if n < window:
        return result

    # Per-bar raw intensity: volume * (high-low) / close
    raw_intensity = np.full(n, np.nan, dtype=np.float64)
    valid_close = close > 0
    with np.errstate(divide="ignore", invalid="ignore"):
        raw_intensity[valid_close] = (
            volume[valid_close] * (high[valid_close] - low[valid_close]) / close[valid_close]
        )

    # Normalize by rolling mean
    for i in range(window - 1, n):
        seg = raw_intensity[i - window + 1 : i + 1]
        seg_clean = seg[~np.isnan(seg)]
        if len(seg_clean) >= 2 and np.mean(seg_clean) > 0:
            current = raw_intensity[i]
            if not np.isnan(current) and current >= 0:
                mu = np.mean(seg_clean)
                result[i] = current / mu if mu > 0 else np.nan
        # else: result[i] stays NaN

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
) -> Dict[str, np.ndarray]:
    """Compute all OrderBook microstructure proxy features.

    Returns dict with keys:
      - spread_pct_N: rolling mean of (high-low)/close
      - volume_imbalance_N: (up_vol - down_vol) / total_vol
      - trade_intensity_N: volume*range/close normalized
      - amihud_illiquidity_N: Amihud price impact measure

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

    Returns:
        Dict mapping feature name to numpy array of shape (n_bars,).
    """
    return {
        "spread_pct_N": compute_spread_pct(high, low, close, window),
        "volume_imbalance_N": compute_volume_imbalance(open_arr, close, volume, window),
        "trade_intensity_N": compute_trade_intensity(high, low, close, volume, window),
        "amihud_illiquidity_N": compute_amihud_illiquidity_numpy(close, volume, amihud_window),
    }
