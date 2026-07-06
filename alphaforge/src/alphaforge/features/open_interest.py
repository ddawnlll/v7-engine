"""Open Interest Feature Group — real OI data from Binance Futures.

Authority: AlphaForge owns feature discovery and specification.
This module computes open interest features from real OI data arrays.
OI data is expected as an additional column in the OHLCV data dict.

Features (4):
  - open_interest_change_N:      Period-over-period change in OI.
  - open_interest_volume_ratio:  OI / volume ratio — measures OI relative
                                 to trading activity.
  - open_interest_zscore_N:      Rolling z-score of OI — detects extreme
                                 positioning changes.
  - open_interest_change_pct_N:  Percentage change in OI over N bars.

Design constraints:
  - numpy only (no pandas, scipy, ta-lib)
  - no network calls, no exchange APIs, no real market data
  - all features are causal: feature at bar[t] uses bars [t-lookback+1 .. t]
  - NaN fill for insufficient lookback at series start
  - deterministic: same input always produces identical output
  - open_interest column is REQUIRED in ohlcv_data

Causality contract:
  Every feature at index t accesses data only from indices [max(0, t - window + 1), t].
  No index > t is ever accessed.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np

try:
    from numba import njit
except ImportError:
    njit = lambda x: x


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default windows for SWING mode (4h primary bars)
SWING_OI_WINDOW: int = 10
SCALP_OI_WINDOW: int = 12
AGGRESSIVE_SCALP_OI_WINDOW: int = 16
DEFAULT_OI_WINDOW: int = 10
DEFAULT_OI_CHANGE_N: int = 1


# ===========================================================================
# Helper: rolling mean (pipeline pattern — causal, NaN-safe)
# ===========================================================================


@njit
def _rolling_mean(arr: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling mean over `window` bars (causal, NaN-safe)."""
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


@njit
def _rolling_std(arr: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling standard deviation over `window` bars (causal, NaN-safe)."""
    n = len(arr)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result
    for i in range(window - 1, n):
        seg = arr[i - window + 1 : i + 1]
        valid = seg[~np.isnan(seg)]
        if len(valid) >= 2:
            v = valid.astype(np.float64)
            mu = np.mean(v)
            var = np.sum((v - mu) ** 2) / (len(v) - 1)
            result[i] = np.sqrt(var) if var > 0 else 0.0
    return result


# ===========================================================================
# Feature 1: open_interest_change_N — period-over-period change
# ===========================================================================


def compute_open_interest_change(
    open_interest: np.ndarray,
    n: int = DEFAULT_OI_CHANGE_N,
) -> np.ndarray:
    """Compute period-over-period change in open interest.

    change[t] = open_interest[t] - open_interest[t-n]

    Positive change -> OI increasing (positions being opened).
    Negative change -> OI decreasing (positions being closed).

    Args:
        open_interest: Open Interest array (from ohlcv_data).
        n: Lookback periods for the change (default 1).

    Returns:
        numpy array of OI changes, same length as input.
        First ``n`` values are NaN.
    """
    length = len(open_interest)
    result = np.full(length, np.nan, dtype=np.float64)
    if length <= n:
        return result
    result[n:] = open_interest[n:] - open_interest[:-n]
    return result


# ===========================================================================
# Feature 2: open_interest_volume_ratio — OI relative to volume
# ===========================================================================


@njit
def compute_open_interest_volume_ratio(
    open_interest: np.ndarray,
    volume: np.ndarray,
    window: int = DEFAULT_OI_WINDOW,
) -> np.ndarray:
    """Compute OI-to-volume ratio, smoothed over window.

    ratio[t] = mean(OI[t-window+1:t+1]) / mean(volume[t-window+1:t+1])

    High ratio: OI is large relative to volume — suggests established
    positions with low turnover (positional holding).
    Low ratio: Volume dominates OI — suggests high turnover, day-trading,
    or scalping activity.

    Smoothed with rolling means to avoid single-bar noise.

    Args:
        open_interest: Open Interest array.
        volume: Volume (base asset) array.
        window: Rolling mean window in bars (default 10).

    Returns:
        numpy array of OI-volume ratios, same length as input.
        First `window-1` values are NaN.
    """
    n = len(open_interest)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result

    for i in range(window - 1, n):
        oi_seg = open_interest[i - window + 1 : i + 1]
        vol_seg = volume[i - window + 1 : i + 1]
        oi_valid = oi_seg[~np.isnan(oi_seg)]
        vol_valid = vol_seg[~np.isnan(vol_seg)]
        if len(oi_valid) >= 2 and len(vol_valid) >= 2:
            oi_mean = np.mean(oi_valid.astype(np.float64))
            vol_mean = np.mean(vol_valid.astype(np.float64))
            if vol_mean > 0:
                result[i] = oi_mean / vol_mean
    return result


# ===========================================================================
# Feature 3: open_interest_zscore_N — rolling z-score of OI
# ===========================================================================


@njit
def compute_open_interest_zscore(
    open_interest: np.ndarray,
    window: int = DEFAULT_OI_WINDOW,
) -> np.ndarray:
    """Compute rolling z-score of open interest.

    Detects extreme OI conditions:
      z > 2  : OI unusually high (extreme positioning)
      z < -2 : OI unusually low (position liquidation/unwinding)

    z = (current OI - mean(window)) / std(window)

    Args:
        open_interest: Open Interest array.
        window: Rolling window (default 10).

    Returns:
        numpy array of z-scores, same length as input.
        First `window-1` values are NaN.
    """
    n = len(open_interest)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result

    oi_f = open_interest.astype(np.float64)

    for i in range(window - 1, n):
        seg = oi_f[i - window + 1 : i + 1]
        valid = seg[~np.isnan(seg)]
        if len(valid) < 2:
            continue
        mu = np.mean(valid)
        var = np.sum((valid - mu) ** 2) / (len(valid) - 1)
        sigma = np.sqrt(var) if var > 0 else 0.0
        if sigma < 1e-14:
            result[i] = 0.0
        else:
            result[i] = (oi_f[i] - mu) / sigma

    return result


# ===========================================================================
# Feature 4: open_interest_change_pct_N — percentage change
# ===========================================================================


@njit
def compute_open_interest_change_pct(
    open_interest: np.ndarray,
    n: int = DEFAULT_OI_CHANGE_N,
) -> np.ndarray:
    """Compute percentage change in open interest over N bars.

    change_pct[t] = (OI[t] / OI[t-n] - 1) * 100

    Positive -> OI growing as percentage of prior.
    Negative -> OI shrinking.

    Args:
        open_interest: Open Interest array.
        n: Lookback periods (default 1).

    Returns:
        numpy array of percentage changes, same length as input.
        First ``n`` values are NaN.
    """
    length = len(open_interest)
    result = np.full(length, np.nan, dtype=np.float64)
    if length <= n:
        return result
    for i in range(n, length):
        prev = open_interest[i - n]
        if prev != 0 and not np.isnan(prev):
            result[i] = (open_interest[i] / prev - 1.0) * 100.0
    return result


# ===========================================================================
# Open Interest Group compute function
# ===========================================================================


def compute_open_interest_group(
    ohlcv_data: dict,
    window: int = DEFAULT_OI_WINDOW,
    change_n: int = DEFAULT_OI_CHANGE_N,
) -> Dict[str, np.ndarray]:
    """Compute all Open Interest group features (4 total).

    Requires 'open_interest' key in ohlcv_data (real OI data).
    Requires 'volume' for OI-volume ratio.

    Returns dict with keys:
      - open_interest_change_N:       Period-over-period OI change
      - open_interest_volume_ratio:   OI / volume ratio
      - open_interest_zscore_N:       Rolling z-score of OI
      - open_interest_change_pct_N:   Percentage OI change

    All arrays are same length as input. NaN at start for insufficient
    lookback windows.

    Args:
        ohlcv_data: dict with 'open', 'high', 'low', 'close', 'volume',
            and 'open_interest' keys.
        window: Rolling window for features (default 10).
        change_n: Lookback for OI change (default 1).

    Returns:
        Dict mapping feature name to numpy array of shape (n_bars,).
    """
    close = ohlcv_data["close"]
    volume = ohlcv_data.get("volume")
    n = len(close)

    # Check for real open_interest data
    open_interest = ohlcv_data.get("open_interest")
    if open_interest is None:
        oi_proxy = ohlcv_data.get("oi_proxy")
        if oi_proxy is not None:
            open_interest = oi_proxy
        else:
            # No OI data at all — return NaN arrays
            nan_arr = np.full(n, np.nan, dtype=np.float64)
            return {
                "open_interest_change_N": nan_arr.copy(),
                "open_interest_volume_ratio": nan_arr.copy(),
                "open_interest_zscore_N": nan_arr.copy(),
                "open_interest_change_pct_N": nan_arr.copy(),
            }

    if isinstance(open_interest, np.ndarray) and len(open_interest) == n:
        oi = open_interest.astype(np.float64)
    else:
        oi = np.full(n, np.nan, dtype=np.float64)

    oi_change = compute_open_interest_change(oi, n=change_n)

    vol_for_ratio = volume if (volume is not None and isinstance(volume, np.ndarray) and len(volume) == n) else np.full(n, np.nan, dtype=np.float64)
    oi_vol_ratio = compute_open_interest_volume_ratio(oi, vol_for_ratio, window=window)

    oi_zscore = compute_open_interest_zscore(oi, window=window)
    oi_change_pct = compute_open_interest_change_pct(oi, n=change_n)

    return {
        "open_interest_change_N": oi_change,
        "open_interest_volume_ratio": oi_vol_ratio,
        "open_interest_zscore_N": oi_zscore,
        "open_interest_change_pct_N": oi_change_pct,
    }
