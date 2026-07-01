"""Funding Rate Feature Group — funding rate and OHLCV-derived funding proxies.

Authority: AlphaForge owns feature discovery and specification.
This module computes funding rate features from OHLCV data and optional
real funding rate arrays.

When real funding_rate data is available (passed as an additional column in
the OHLCV data dict), features are computed from the actual funding rates.
When funding_rate data is absent, features use an OHLCV-derived proxy that
estimates the funding rate direction from price action.

Features (7 — 5 core + 2 Funding-OI expansion #119):
  - funding_rate:              Raw funding rate (passthrough or OHLCV proxy).
  - funding_rate_ma_N:         Rolling mean of funding rate.
  - funding_rate_vol_N:        Rolling standard deviation of funding rate.
  - funding_rate_zscore_N:     Rolling z-score of funding rate — extremes detected.
  - funding_rate_change_N:     Period-over-period change in funding rate.
  - open_interest_proxy_N:     OI proxy from volume * |price change| (#119).
  - funding_oi_divergence_N:   Divergence between funding rate and OI proxy (#119).

OHLCV proxy formula (when no real funding_rate is available):
  funding_proxy[t] = -(close[t] / vwap[t] - 1.0) * 100.0

  This estimates the perpetual basis direction from price action:
    - close > VWAP (perpetual premium) -> negative proxy -> positive funding expected
    - close < VWAP (perpetual discount) -> positive proxy -> negative funding expected
  The factor of 100 scales the deviation to approximately the same magnitude
  as real funding rates (typically in basis points).

OI proxy formula:
  oi_proxy[t] = volume[t] * abs(close[t] / close[t-1] - 1)
  Then smoothed with rolling mean.

  This captures "open interest-like activity" — high volume combined with
  significant price movement suggests OI change (position entry/exit).

Funding-OI divergence:
  z-score(funding_rate) - z-score(oi_proxy)
  Positive divergence = funding is high but OI is low (premium without conviction).
  Negative divergence = funding is low but OI is high (discount with positioning).

Design constraints:
  - numpy only (no pandas, scipy, ta-lib)
  - no network calls, no exchange APIs, no real market data
  - all features are causal: feature at bar[t] uses bars [t-lookback+1 .. t]
  - NaN fill for insufficient lookback at series start
  - deterministic: same input always produces identical output
  - funding_rate column is OPTIONAL in ohlcv_data — absent defaults to proxy

Causality contract:
  Every feature at index t accesses data only from indices [max(0, t - window + 1), t].
  No index > t is ever accessed.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# SWING mode defaults (4h primary bars)
SWING_FUNDING_WINDOW: int = 10
SCALP_FUNDING_WINDOW: int = 12
AGGRESSIVE_SCALP_FUNDING_WINDOW: int = 16

# Generic default
DEFAULT_FUNDING_WINDOW: int = 10

# Funding rate change window
DEFAULT_FUNDING_CHANGE_N: int = 1

# OI proxy windows (#119)
DEFAULT_OI_PROXY_WINDOW: int = 10
SWING_OI_PROXY_WINDOW: int = 10
SCALP_OI_PROXY_WINDOW: int = 12
AGGRESSIVE_SCALP_OI_PROXY_WINDOW: int = 16


# ===========================================================================
# Helper: OHLCV funding proxy computation
# ===========================================================================


def _compute_funding_proxy(
    close: np.ndarray,
    vwap: Optional[np.ndarray] = None,
    high: Optional[np.ndarray] = None,
    low: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Compute OHLCV-derived funding rate proxy.

    Primary proxy:
      proxy[t] = -(close[t] / vwap[t] - 1.0) * 100.0

    where VWAP[t] is the cumulative VWAP up to bar t:
      VWAP[t] = sum(tp[i] * vol[i]) / sum(vol[i]) for i in [0..t]
      tp = (high + low + close) / 3

    When vwap is not provided, use a simpler price-position proxy:
      proxy[t] = -(close[t] / close_mean_window - 1.0) * 100.0

    Interpretation:
      Positive -> bears pay funding (short positioning premium)
      Negative -> bulls pay funding (long positioning premium)
      Near zero -> neutral funding conditions

    Args:
        close: Close prices.
        vwap: Optional pre-computed cumulative VWAP. If None, computed here.
        high: High prices (required when vwap is None).
        low: Low prices (required when vwap is None).

    Returns:
        numpy array of funding proxy values, same length as close.
    """
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)
    if n == 0:
        return result

    if vwap is not None:
        # Use provided VWAP
        valid = ~np.isnan(vwap) & (vwap != 0)
        with np.errstate(divide="ignore", invalid="ignore"):
            result[valid] = -(close[valid] / vwap[valid] - 1.0) * 100.0
    elif high is not None and low is not None:
        # Compute VWAP from high/low/close
        tp = (high.astype(np.float64) + low.astype(np.float64) + close.astype(np.float64)) / 3.0
        cum_pv = 0.0
        cum_v = 0.0
        # Use uniform volume weighting when no volume is available
        for i in range(n):
            cum_pv += tp[i]
            cum_v += 1.0
            vwap_i = cum_pv / cum_v
            if vwap_i != 0:
                result[i] = -(close[i] / vwap_i - 1.0) * 100.0
    else:
        # Fallback: use expanding mean of close as reference
        cum_sum = 0.0
        for i in range(n):
            cum_sum += close[i]
            ref = cum_sum / (i + 1)
            if ref != 0:
                result[i] = -(close[i] / ref - 1.0) * 100.0

    return result


# ===========================================================================
# Helper: rolling mean (copied pattern from orderbook module — causal, NaN-safe)
# ===========================================================================


def _rolling_mean(arr: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling mean over `window` bars (causal, NaN-safe).

    Result at index t uses arr[t-window+1 .. t].
    Returns NaN for t < window-1 or when fewer than 2 non-NaN values.
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
    """Compute rolling standard deviation over `window` bars (causal, NaN-safe).

    Returns NaN for t < window-1 or when fewer than 2 non-NaN values.
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


# ===========================================================================
# Feature 1: funding_rate
# ===========================================================================


def compute_funding_rate(
    ohlcv_data: dict,
    window: int = DEFAULT_FUNDING_WINDOW,
) -> np.ndarray:
    """Compute raw funding rate from OHLCV data.

    If ohlcv_data contains a 'funding_rate' key, use it directly.
    Otherwise, compute an OHLCV-derived proxy based on price position
    relative to cumulative VWAP.

    Args:
        ohlcv_data: dict with 'close' (required), 'high', 'low', 'volume'
            (optional), and optionally 'funding_rate'.
        window: Rolling window for proxy initialization.

    Returns:
        numpy array of funding rate values, same length as close.
    """
    close = ohlcv_data["close"]
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)

    if n < 2:
        return result

    # Check for real funding_rate data
    if "funding_rate" in ohlcv_data:
        fr = ohlcv_data["funding_rate"]
        if isinstance(fr, np.ndarray) and len(fr) == n:
            # Passthrough: copy directly (maintains dtype)
            result = fr.astype(np.float64, copy=True)
            return result
        else:
            logger.warning(
                f"funding_rate key present but invalid shape/type — "
                f"falling back to OHLCV proxy"
            )

    # Compute OHLCV proxy
    vwap = ohlcv_data.get("_vwap", None)
    result = _compute_funding_proxy(
        close=close,
        vwap=vwap,
        high=ohlcv_data.get("high"),
        low=ohlcv_data.get("low"),
    )

    return result


# ===========================================================================
# Feature 2: funding_rate_ma — rolling mean
# ===========================================================================


def compute_funding_rate_ma(
    funding_rate: np.ndarray,
    window: int = DEFAULT_FUNDING_WINDOW,
) -> np.ndarray:
    """Compute rolling mean of funding rate.

    Smoothed funding signal. Higher values indicate sustained positive
    funding (bullish positioning premium). Lower values indicate sustained
    negative funding (bearish positioning premium).

    Args:
        funding_rate: Funding rate array (from compute_funding_rate).
        window: Rolling window (default 10).

    Returns:
        numpy array of smoothed funding rates, same length as input.
        First `window-1` values are NaN.
    """
    return _rolling_mean(funding_rate, window)


# ===========================================================================
# Feature 3: funding_rate_volatility — rolling std
# ===========================================================================


def compute_funding_rate_volatility(
    funding_rate: np.ndarray,
    window: int = DEFAULT_FUNDING_WINDOW,
) -> np.ndarray:
    """Compute rolling standard deviation of funding rate.

    Captures uncertainty in funding costs. High values indicate unstable
    or rapidly changing funding conditions, which may signal market stress
    or positioning shifts.

    Args:
        funding_rate: Funding rate array (from compute_funding_rate).
        window: Rolling window (default 10).

    Returns:
        numpy array of funding rate volatility, same length as input.
        First `window-1` values are NaN.
    """
    return _rolling_std(funding_rate, window)


# ===========================================================================
# Feature 4: funding_rate_zscore — z-score of funding rate
# ===========================================================================


def compute_funding_rate_zscore(
    funding_rate: np.ndarray,
    window: int = DEFAULT_FUNDING_WINDOW,
) -> np.ndarray:
    """Compute rolling z-score of funding rate.

    Detects extreme funding conditions:
      z > 2  : funding unusually positive (extremely bullish positioning)
      z < -2 : funding unusually negative (extremely bearish positioning)

    These extremes may indicate crowded trades or regime shifts.

    Args:
        funding_rate: Funding rate array.
        window: Rolling window (default 10).

    Returns:
        numpy array of z-scores, same length as input.
        First `window-1` values are NaN.
    """
    n = len(funding_rate)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result

    fr_f = funding_rate.astype(np.float64)

    for i in range(window - 1, n):
        seg = fr_f[i - window + 1 : i + 1]
        valid = seg[~np.isnan(seg)]
        if len(valid) < 2:
            result[i] = np.nan
            continue
        mu = np.mean(valid)
        sigma = np.std(valid, ddof=1)
        if sigma < 1e-14:
            result[i] = 0.0
        else:
            result[i] = (fr_f[i] - mu) / sigma

    return result


# ===========================================================================
# Feature 4b: funding_rate_change — period-over-period change
# ===========================================================================


def compute_funding_rate_change(
    funding_rate: np.ndarray,
    n: int = DEFAULT_FUNDING_CHANGE_N,
) -> np.ndarray:
    """Compute period-over-period change in funding rate.

    change[t] = funding_rate[t] - funding_rate[t-n]

    Positive change -> funding rate increasing (bears pay more).
    Negative change -> funding rate decreasing (bulls pay more).

    This captures the momentum of funding costs, which can precede
    positioning shifts. Large positive changes may indicate rapidly
    increasing long positioning premium.

    Args:
        funding_rate: Funding rate array (from compute_funding_rate).
        n: Lookback periods for the change (default 1).

    Returns:
        numpy array of funding rate changes, same length as input.
        First ``n`` values are NaN.
    """
    length = len(funding_rate)
    result = np.full(length, np.nan, dtype=np.float64)
    if length <= n:
        return result
    result[n:] = funding_rate[n:] - funding_rate[:-n]
    return result


# ===========================================================================
# Feature 5: open_interest_proxy (OI proxy from volume * |price change|) — #119
# ===========================================================================


def compute_open_interest_proxy(
    close: np.ndarray,
    volume: np.ndarray,
    window: int = DEFAULT_OI_PROXY_WINDOW,
) -> np.ndarray:
    """Compute open interest proxy from OHLCV data.

    Algorithm per bar t:
      1. Raw OI proxy: price_activity[t] = volume[t] * |close[t] / close[t-1] - 1|
      2. Smooth with rolling mean over ``window`` bars.

    The intuition: when large volume enters or exits the market, it is
    accompanied by meaningful price movement. The product of volume and
    absolute return captures "open interest-like activity." Pure volume
    spikes without price movement are likely spread hedging or noise,
    while pure price moves without volume are likely order-book sweeps
    rather than OI changes.

    Higher values indicate greater OI activity (position entry/exit).
    Lower values indicate positional inactivity or consolidation.

    This is an OHLCV proxy — no real OI data is used.

    Args:
        close: Close prices.
        volume: Volume (base asset).
        window: Rolling mean window in bars (default 10).

    Returns:
        numpy array of OI proxy values >= 0, same length as input.
        First ``window`` values are NaN (need window+1 bars for first
        valid windowed value).
    """
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)
    lookback = window + 1  # Need window+1 for window of returns
    if n < lookback:
        return result

    # Per-bar raw OI proxy: volume * abs(close_change / close_prev - 1)
    raw_oi = np.full(n, np.nan, dtype=np.float64)
    for i in range(1, n):
        if close[i - 1] != 0:
            raw_oi[i] = volume[i] * abs(close[i] / close[i - 1] - 1.0)

    # Smooth with rolling mean
    for i in range(window, n):
        seg = raw_oi[i - window + 1 : i + 1]
        seg_clean = seg[~np.isnan(seg)]
        if len(seg_clean) >= 2:
            result[i] = np.mean(seg_clean)

    return result


# ===========================================================================
# Feature 6: funding_oi_divergence (funding vs OI proxy divergence) — #119
# ===========================================================================


def _rolling_zscore(arr: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling z-score of an array (causal, NaN-safe)."""
    n = len(arr)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result
    for i in range(window - 1, n):
        seg = arr[i - window + 1 : i + 1]
        valid = seg[~np.isnan(seg)]
        if len(valid) < 2:
            continue
        mu = np.mean(valid)
        sigma = np.std(valid, ddof=1)
        if sigma < 1e-14:
            result[i] = 0.0
        else:
            result[i] = (arr[i] - mu) / sigma
    return result


def compute_funding_oi_divergence(
    funding_rate: np.ndarray,
    oi_proxy: np.ndarray,
    window: int = DEFAULT_OI_PROXY_WINDOW,
) -> np.ndarray:
    """Compute divergence between funding rate and open interest proxy.

    divergence[t] = zscore(funding_rate, window)[t] - zscore(oi_proxy, window)[t]

    Interpretation:
      Positive divergence (> 1.0):
        Funding is expensive (bulls paying) but OI activity is low —
        suggests premium without conviction, potential reversal.
      Negative divergence (< -1.0):
        Funding is cheap or negative (bears paying) but OI activity is
        high — suggests positioning with cheap funding, potential
        continuation.
      Near zero:
        Funding and OI are in alignment.

    This signal helps distinguish between:
      - Conviction positioning (high funding + high OI = aligned)
      - Reluctant premium (high funding + low OI = divergent, fragile)
      - Quiet accumulation (low/negative funding + high OI = divergent, bullish)
      - Disinterest (low funding + low OI = aligned, neutral)

    Args:
        funding_rate: Funding rate array (proxy or real).
        oi_proxy: OI proxy array (from compute_open_interest_proxy).
        window: Rolling window for z-score computation (default 10).

    Returns:
        numpy array of divergence z-scores, same length as input.
        First ``window - 1`` values are NaN.
    """
    fr_z = _rolling_zscore(funding_rate, window)
    oi_z = _rolling_zscore(oi_proxy, window)

    n = len(funding_rate)
    result = np.full(n, np.nan, dtype=np.float64)
    for i in range(n):
        if not np.isnan(fr_z[i]) and not np.isnan(oi_z[i]):
            result[i] = fr_z[i] - oi_z[i]

    return result


# ===========================================================================
# Funding Group compute function
# ===========================================================================


def compute_funding_group(
    ohlcv_data: dict,
    window: int = DEFAULT_FUNDING_WINDOW,
    oi_window: int = DEFAULT_OI_PROXY_WINDOW,
) -> Dict[str, np.ndarray]:
    """Compute all Funding group features (6 total).

    Returns dict with keys:
      - funding_rate:              Raw funding rate (proxy or real)
      - funding_rate_ma_N:         Rolling mean of funding rate
      - funding_rate_vol_N:        Rolling std of funding rate
      - funding_rate_zscore_N:     Rolling z-score of funding rate
      - open_interest_proxy_N:     OI proxy from volume * |price change| (#119)
      - funding_oi_divergence_N:   Divergence between funding rate and OI proxy (#119)

    All arrays are same length as input. NaN at start for insufficient
    lookback windows.

    Args:
        ohlcv_data: dict with OHLCV data. May contain 'funding_rate' key
            for real funding rates.
        window: Rolling window for funding features (default 10).
        oi_window: Rolling window for OI proxy and divergence (default 10).

    Returns:
        Dict mapping feature name to numpy array of shape (n_bars,).
    """
    fr = compute_funding_rate(ohlcv_data, window=window)

    close = ohlcv_data["close"]
    volume = ohlcv_data.get("volume")
    if volume is not None:
        oi_proxy = compute_open_interest_proxy(close, volume, window=oi_window)
        fwd = compute_funding_oi_divergence(fr, oi_proxy, window=oi_window)
    else:
        oi_proxy = np.full(len(close), np.nan, dtype=np.float64)
        fwd = np.full(len(close), np.nan, dtype=np.float64)

    return {
        "funding_rate": fr,
        "funding_rate_ma_N": compute_funding_rate_ma(fr, window=window),
        "funding_rate_vol_N": compute_funding_rate_volatility(fr, window=window),
        "funding_rate_zscore_N": compute_funding_rate_zscore(fr, window=window),
        "funding_rate_change_N": compute_funding_rate_change(fr, n=1),
        "open_interest_proxy_N": oi_proxy,
        "funding_oi_divergence_N": fwd,
    }
