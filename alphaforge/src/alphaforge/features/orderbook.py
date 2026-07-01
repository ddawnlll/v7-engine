"""OrderBook Feature Group — microstructure-aware features from OHLCV data.

Authority: AlphaForge owns feature discovery and specification.
This module computes microstructure proxy features from OHLCV data only.
No real order book data is used in v0.2 — all features are OHLCV proxies.

Primary target mode: AGGRESSIVE_SCALP (15m primary, 5m refinement).
Secondary applicability: SCALP and SWING with adjusted window parameters.

Features (12 total — 9 core + 3 expansion #119):
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

from lib.indicators.microstructure import amihud_illiquidity, dollar_volume, roll_spread_estimator

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
            result[i] = 0.0  # zero volume window -> balanced

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
# Feature: roll_spread (Roll 1984 effective bid-ask spread)
# ===========================================================================

def compute_roll_spread(
    close: np.ndarray,
    window: int = DEFAULT_ROLL_SPREAD_WINDOW,
) -> np.ndarray:
    """Compute Roll (1984) effective bid-ask spread estimator.

    S = 2 * sqrt(max(0, -covariance(delta_p_t, delta_p_{t-1})))

    where the covariance of sequential price changes is computed over a
    rolling window. A negative serial covariance in price changes is
    interpreted as bid-ask bounce, from which the effective spread is inferred.

    Higher values indicate wider effective spreads (higher transaction costs).
    Zero when the serial covariance is non-negative (no detectable bounce).

    This bridges the list-based lib/indicators.microstructure.roll_spread_estimator
    to the numpy pipeline.

    Args:
        close: Close prices.
        window: Rolling window for covariance computation (default 20).

    Returns:
        numpy array of Roll spread estimates (same length as input).
        First `window` values are NaN (need window+1 prices for window
        price changes).
        Values are in price units (same as close prices).
    """
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)

    if n < window + 1:
        return result

    # Bridge: convert close to list for the lib function, then back to numpy
    close_list = close.tolist()
    spread_list = roll_spread_estimator(close_list, period=window)

    # Convert back to numpy array
    result = np.array(spread_list, dtype=np.float64)

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
    result = np.full(n, np.nan, dtype=np.float64)

    if n < window + 1:
        return result

    log_ret_1 = _compute_log_return_1(close)

    for i in range(window, n):
        # 1-bar returns over [i-window+1 .. i]
        seg_1 = log_ret_1[i - window + 1 : i + 1]
        seg_1_clean = seg_1[~np.isnan(seg_1)]

        # Window-bar return at i: ln(close[i] / close[i-window])
        r_window = math.log(close[i] / close[i - window])

        if len(seg_1_clean) < 3:
            continue

        std_1 = float(np.std(seg_1_clean, ddof=1))
        if std_1 > 1e-14:
            # Compute std of window-bar returns over the same window
            # We need a second moment: for overlapping windows we use
            # the window-bar return at each step
            r_w = np.full(window, np.nan, dtype=np.float64)
            for j in range(window):
                # r_window at index i-window+1+j
                idx = i - window + 1 + j
                if idx >= window:
                    r_w[j] = math.log(close[idx] / close[idx - window])
            r_w_clean = r_w[~np.isnan(r_w)]
            if len(r_w_clean) < 3:
                continue
            std_window = float(np.std(r_w_clean, ddof=1))
            if std_window > 1e-14:
                noise = math.sqrt(window) * std_1 / std_window
                result[i] = float(np.clip(noise, 0.01, 10.0))

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
    result = np.full(n, np.nan, dtype=np.float64)

    if n < window + 2:  # need window+2 bars for window+1 returns
        return result

    log_ret = _compute_log_return_1(close)

    for i in range(window + 1, n):
        # Returns at [i-window .. i] (window+1 values)
        seg = log_ret[i - window : i + 1]
        valid = seg[~np.isnan(seg)]
        if len(valid) < window + 1:
            # Too many NaN values — skip
            n_nan = int(np.sum(np.isnan(seg)))
            if n_nan > 0:
                seg = seg[~np.isnan(seg)]
            n_valid = len(seg)
        else:
            n_valid = len(seg)

        if n_valid < 4:
            continue

        x = seg[:-1]  # r[t-window .. t-1]
        y = seg[1:]   # r[t-window+1 .. t]

        # Pearson correlation
        dx = x - np.mean(x)
        dy = y - np.mean(y)
        cov = np.sum(dx * dy)
        std_x = np.sqrt(np.sum(dx ** 2))
        std_y = np.sqrt(np.sum(dy ** 2))

        if std_x < 1e-14 or std_y < 1e-14:
            continue

        corr = cov / (std_x * std_y)
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

    Returns:
        numpy array of VPIN values in [0, 1] (same length as input).
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
        total_vol = np.sum(seg_up) + np.sum(seg_down)

        if total_vol > 0:
            abs_imbalance = np.sum(np.abs(seg_up - seg_down))
            result[i] = abs_imbalance / total_vol
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

    Returns:
        numpy array of price impact slope values (same length as input).
        First `window` values are NaN (need window+1 bars for window
        returns).
        NaN also when variance of signed flow is too small.
    """
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)

    if n < window + 1:
        return result

    up_vol, down_vol = _classify_volume_direction(open_arr, close, volume)
    signed_flow = up_vol - down_vol
    log_ret = _compute_log_return_1(close)

    for i in range(window, n):
        # Returns at [i-window+1 .. i] (window values)
        r_seg = log_ret[i - window + 1 : i + 1]
        # Signed flow at [i-window+1 .. i]
        f_seg = signed_flow[i - window + 1 : i + 1]

        # Filter to non-NaN pairs
        valid = ~np.isnan(r_seg) & ~np.isnan(f_seg)
        n_valid = int(np.sum(valid))

        if n_valid < 3:
            continue

        r_v = r_seg[valid].astype(np.float64)
        f_v = f_seg[valid].astype(np.float64)

        # Covariance and variance of signed flow
        r_mean = np.mean(r_v)
        f_mean = np.mean(f_v)

        cov = np.sum((r_v - r_mean) * (f_v - f_mean))
        var_f = np.sum((f_v - f_mean) ** 2)

        if var_f < 1e-14:
            continue

        result[i] = cov / var_f

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

    up_vol, down_vol = _classify_volume_direction(open_arr, close, volume)
    total = up_vol + down_vol

    # Per-bar raw microprice: low * (1 - up_weight) + high * up_weight
    raw_mp = np.full(n, np.nan, dtype=np.float64)
    for i in range(n):
        if total[i] > 0:
            weight_up = up_vol[i] / total[i]
            raw_mp[i] = low[i] * (1.0 - weight_up) + high[i] * weight_up
        else:
            raw_mp[i] = (high[i] + low[i]) * 0.5

    # Smooth with rolling mean
    for i in range(window - 1, n):
        seg = raw_mp[i - window + 1 : i + 1]
        seg_clean = seg[~np.isnan(seg)]
        if len(seg_clean) >= 2:
            result[i] = np.mean(seg_clean)

    return result


# ===========================================================================
# Feature: liquidity_vacuum (combined low-volume + wide-spread detector) — #119
# ===========================================================================

def _rolling_mean_nan_safe(arr: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling mean (causal, NaN-safe). Same pattern as pipeline."""
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

    Returns:
        numpy array of depth ratio estimates >= 0, same length as input.
        First ``window - 1`` values are NaN.
    """
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result

    up_vol, down_vol = _classify_volume_direction(open_arr, close, volume)

    # Per-bar depth ratio (with epsilon to avoid division by zero)
    per_bar = np.full(n, np.nan, dtype=np.float64)
    for i in range(n):
        short = max(down_vol[i], 1e-10)
        per_bar[i] = up_vol[i] / short

    # Smooth with rolling mean
    for i in range(window - 1, n):
        seg = per_bar[i - window + 1 : i + 1]
        seg_clean = seg[~np.isnan(seg)]
        if len(seg_clean) >= 2:
            result[i] = np.mean(seg_clean)

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
) -> Dict[str, np.ndarray]:
    """Compute all OrderBook microstructure proxy features (12 total).

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

    Returns:
        Dict mapping feature name to numpy array of shape (n_bars,).
    """
    return {
        "spread_pct_N": compute_spread_pct(high, low, close, window),
        "volume_imbalance_N": compute_volume_imbalance(open_arr, close, volume, window),
        "trade_intensity_N": compute_trade_intensity(high, low, close, volume, window),
        "amihud_illiquidity_N": compute_amihud_illiquidity_numpy(close, volume, amihud_window),
        "roll_spread_N": compute_roll_spread(close, roll_spread_window),
        "microstructure_noise_N": compute_microstructure_noise(close, noise_window),
        "serial_correlation_N": compute_serial_correlation(close, serial_corr_window),
        "vpin_N": compute_vpin(open_arr, close, volume, vpin_window),
        "price_impact_slope_N": compute_price_impact_slope(
            open_arr, high, low, close, volume, price_impact_window,
        ),
        "microprice_N": compute_microprice(high, low, open_arr, close, volume, microprice_window),
        "liquidity_vacuum_N": compute_liquidity_vacuum(high, low, close, volume, liquidity_vacuum_window),
        "depth_ratio_N": compute_depth_ratio(open_arr, close, volume, depth_ratio_window),
    }
