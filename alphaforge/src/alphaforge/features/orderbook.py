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

    # Vectorized rolling sums: total_vol and abs(up - down)
    total = up_vol + down_vol
    abs_diff = np.abs(up_vol - down_vol)

    # Use cumsum for O(n) rolling aggregation
    cum_total = np.cumsum(total)
    cum_abs = np.cumsum(abs_diff)

    total_window = cum_total[window - 1:] - np.concatenate([[0], cum_total[:-window]])
    abs_window = cum_abs[window - 1:] - np.concatenate([[0], cum_abs[:-window]])

    mask = total_window > 0
    result[window - 1:][mask] = abs_window[mask] / total_window[mask]
    result[window - 1:][~mask] = 0.0
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

    # Use sliding_window_view for O(n) rolling regression
    r_views = np.lib.stride_tricks.sliding_window_view(log_ret, window)
    f_views = np.lib.stride_tricks.sliding_window_view(signed_flow, window)

    # Both valid: not NaN in either
    both_valid = ~(np.isnan(r_views) | np.isnan(f_views))

    for i in range(len(r_views)):
        valid_mask = both_valid[i]
        n_valid = np.sum(valid_mask)
        if n_valid < 3:
            continue

        r_v = r_views[i][valid_mask].astype(np.float64)
        f_v = f_views[i][valid_mask].astype(np.float64)

        r_mean = np.mean(r_v)
        f_mean = np.mean(f_v)

        cov = np.sum((r_v - r_mean) * (f_v - f_mean))
        var_f = np.sum((f_v - f_mean) ** 2)

        if var_f < 1e-14:
            continue

        result[window + i] = cov / var_f

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

    # Per-bar raw microprice (vectorized): low * (1 - up_weight) + high * up_weight
    raw_mp = np.where(total > 0,
                      low * (1.0 - up_vol / total) + high * (up_vol / total),
                      (high + low) * 0.5)

    # Smooth with rolling mean (vectorized)
    valid = ~np.isnan(raw_mp)
    arr_clean = np.where(valid, raw_mp, 0.0)
    cumsum = np.cumsum(arr_clean, dtype=np.float64)
    cumcount = np.cumsum(valid)

    window_sum = cumsum[window - 1:] - np.concatenate([[0], cumsum[:-window]])
    window_count = cumcount[window - 1:] - np.concatenate([[0], cumcount[:-window]])

    mask = window_count >= 2
    result[window - 1:][mask] = window_sum[mask] / window_count[mask]

    return result


# ===========================================================================
# Feature: liquidity_vacuum (combined low-volume + wide-spread detector) — #119
# ===========================================================================

def _rolling_mean_nan_safe(arr: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling mean (causal, NaN-safe, vectorized). Uses cumsum."""
    n = len(arr)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result

    valid = ~np.isnan(arr)
    arr_clean = np.where(valid, arr, 0.0)

    cumsum = np.cumsum(arr_clean, dtype=np.float64)
    cumcount = np.cumsum(valid)

    window_sum = cumsum[window - 1:] - np.concatenate([[0], cumsum[:-window]])
    window_count = cumcount[window - 1:] - np.concatenate([[0], cumcount[:-window]])

    mask = window_count >= 2
    result[window - 1:][mask] = window_sum[mask] / window_count[mask]
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
    # Only activates when both conditions are adverse (vectorized)
    vol_penalty = np.maximum(0.0, 1.0 - vol_ratio)
    spread_penalty = np.maximum(0.0, spread_ratio - 1.0)
    result = np.where(np.isnan(vol_ratio) | np.isnan(spread_ratio), np.nan, vol_penalty * spread_penalty)
    # Apply nan for initial window
    result[:window - 1] = np.nan
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

    # Per-bar depth ratio (vectorized, with epsilon to avoid division by zero)
    down_safe = np.maximum(down_vol, 1e-10)
    per_bar = up_vol / down_safe

    # Smooth with rolling mean (vectorized)
    valid = ~np.isnan(per_bar)
    arr_clean = np.where(valid, per_bar, 0.0)
    cumsum = np.cumsum(arr_clean, dtype=np.float64)
    cumcount = np.cumsum(valid)

    window_sum = cumsum[window - 1:] - np.concatenate([[0], cumsum[:-window]])
    window_count = cumcount[window - 1:] - np.concatenate([[0], cumcount[:-window]])

    mask = window_count >= 2
    result[window - 1:][mask] = window_sum[mask] / window_count[mask]
    return result


# ===========================================================================
# Feature: compute_orderbook_imbalance (L1 Order Book Imbalance) — #154
# ===========================================================================

def compute_orderbook_imbalance(
    open_arr: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
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

    Returns:
        numpy array of OBI values in [-1, +1], same length as input.
        No NaN values ever (zero-volume bars return 0.0).
    """
    n = len(volume)
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
    obi = compute_orderbook_imbalance(open_arr, close, volume)

    # Pre-compute level weights: exponential decay with depth
    weights = np.array(
        [math.exp(-k * decay) for k in range(n_levels)],
        dtype=np.float64,
    )
    total_weight = np.sum(weights)

    # Pre-compute rolling means at each window size
    rolling_means: List[np.ndarray] = []
    for k in range(n_levels):
        w = (k + 1) * step
        rolling_means.append(_rolling_mean_nan_safe(obi, w))

    # Combine levels with weights
    for i in range(max_window - 1, n):
        val_sum = 0.0
        w_sum = 0.0
        for k in range(n_levels):
            rm_val = rolling_means[k][i]
            if not np.isnan(rm_val):
                val_sum += rm_val * weights[k]
                w_sum += weights[k]
        if w_sum > 0:
            result[i] = val_sum / w_sum

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

    Returns:
        numpy array of Stoikov micro-price estimates, same length as
        input. First `window - 1` values are NaN.
        Values are in price units, always between low and high.
    """
    n = len(high)
    result = np.full(n, np.nan, dtype=np.float64)

    if n < window:
        return result

    up_vol, down_vol = _classify_volume_direction(open_arr, close, volume)
    total = up_vol + down_vol

    # Per-bar raw Stoikov micro-price
    # raw_mp = (low * up_vol + high * down_vol) / total
    # When total == 0: use midpoint = (high + low) / 2
    raw_mp = np.full(n, np.nan, dtype=np.float64)
    for i in range(n):
        if total[i] > 0:
            raw_mp[i] = (low[i] * up_vol[i] + high[i] * down_vol[i]) / total[i]
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
# Feature: compute_ofi (Order Flow Imbalance, Cont-Kukanov-Stoikov style)
# ===========================================================================

def compute_ofi(
    open_arr: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    window: int = DEFAULT_OFI_WINDOW,
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

    Returns:
        numpy array of OFI values in [-1, 1] (same length as input).
        First `window-1` values are NaN.
        NaN also when a window has no non-NaN raw imbalances.
    """
    n = len(volume)
    result = np.full(n, np.nan, dtype=np.float64)

    if n < window:
        return result

    up_vol, down_vol = _classify_volume_direction(open_arr, close, volume)
    total_vol = up_vol + down_vol

    # Per-bar raw OFI
    raw_ofi = np.full(n, np.nan, dtype=np.float64)
    for i in range(n):
        if total_vol[i] > 1e-12:
            raw_ofi[i] = (up_vol[i] - down_vol[i]) / total_vol[i]
        else:
            raw_ofi[i] = 0.0  # zero volume -> balanced

    # Rolling mean of per-bar ratios
    for i in range(window - 1, n):
        seg = raw_ofi[i - window + 1 : i + 1]
        seg_clean = seg[~np.isnan(seg)]
        if len(seg_clean) >= 2:
            result[i] = float(np.mean(seg_clean))
        # else: result[i] stays NaN

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

    # Volume-weighted rolling mean
    for i in range(window - 1, n):
        seg_mid = mid[i - window + 1 : i + 1]
        seg_vol = volume[i - window + 1 : i + 1]

        valid = ~np.isnan(seg_mid) & ~np.isnan(seg_vol) & (seg_vol >= 0)
        n_valid = int(np.sum(valid))

        if n_valid < 2:
            continue

        s_mid = seg_mid[valid].astype(np.float64)
        s_vol = seg_vol[valid].astype(np.float64)
        vol_sum = float(np.sum(s_vol))

        if vol_sum > 1e-12:
            result[i] = float(np.sum(s_mid * s_vol)) / vol_sum
        else:
            # Fall back to simple mean when all volume is zero
            result[i] = float(np.mean(s_mid))

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

    # Rolling mean with NaN-safe handling
    for i in range(window - 1, n):
        seg = raw_spread[i - window + 1 : i + 1]
        seg_clean = seg[~np.isnan(seg)]
        if len(seg_clean) >= 2:
            result[i] = np.mean(seg_clean)

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

    for i in range(window - 1, n):
        seg_typical = typical_price[i - window + 1 : i + 1]
        seg_volume = volume[i - window + 1 : i + 1]

        total_pv = np.sum(seg_typical * seg_volume)
        total_vol = np.sum(seg_volume)

        if total_vol > 0 and not np.isnan(total_pv):
            vwap = total_pv / total_vol
            if vwap > 0:
                mid = (high[i] + low[i]) * 0.5
                result[i] = (mid - vwap) / vwap

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

    for i in range(window - 1, n):
        seg = volume[i - window + 1 : i + 1]
        seg_clean = seg[~np.isnan(seg)]
        if len(seg_clean) < 3:
            continue
        mu = float(np.mean(seg_clean))
        sigma = float(np.std(seg_clean, ddof=1))
        if sigma > 1e-14 and not np.isnan(volume[i]):
            result[i] = (volume[i] - mu) / sigma

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

    for i in range(window - 1, n):
        seg = volume[i - window + 1 : i + 1]
        seg_clean = seg[~np.isnan(seg)]
        if len(seg_clean) < 2:
            continue
        total = float(np.sum(seg_clean))
        if total > 0:
            shares = seg_clean / total
            result[i] = float(np.sum(shares ** 2))
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
    """Compute all OrderBook microstructure proxy features (21 total).

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
      - stoikov_micro_price_N: Stoikov contrarian micro-price (#170)
      - ofi_N: per-bar equally-weighted order flow imbalance
      - vamp_N: volume-adjusted mid price
      - quoted_spread_N: effective quoted spread proxy
      - vwap_mid_deviation_N: rolling VWAP deviation from midpoint
      - trade_count_N: trade count proxy (volume z-score)
      - volume_concentration_hhi_N: Herfindahl-Hirschman Index of volume

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
        stoikov_micro_price_window: Smoothing window for Stoikov micro-price (default 5).
        ofi_window: Window for order flow imbalance (default 10).
        vamp_window: Window for volume-adjusted mid price (default 5).
        quoted_spread_window: Window for quoted spread (default 10).
        vwap_mid_window: Window for VWAP-mid deviation (default 10).
        trade_count_window: Window for trade count proxy (default 20).
        volume_concentration_window: Window for volume HHI (default 20).

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
        # New features: L1 OBI, Multi-level OBI, Stoikov micro-price
        "obi": compute_orderbook_imbalance(open_arr, close, volume),
        "multi_level_obi_N": compute_multi_level_obi(
            open_arr, close, volume,
            n_levels=multi_level_obi_n,
            step=multi_level_obi_step,
            decay=multi_level_obi_decay,
        ),
        "stoikov_micro_price_N": compute_micro_price(
            high, low, open_arr, close, volume,
            window=stoikov_micro_price_window,
        ),
        # New features: OFI, VAMP, Quoted spread, VWAP-mid deviation
        "ofi_N": compute_ofi(open_arr, close, volume, window=ofi_window),
        "vamp_N": compute_vamp(high, low, open_arr, close, volume, window=vamp_window),
        "quoted_spread_N": compute_quoted_spread(high, low, close, window=quoted_spread_window),
        "vwap_mid_deviation_N": compute_vwap_to_mid_deviation(
            high, low, close, volume, window=vwap_mid_window,
        ),
        # New features: Trade count, Volume concentration HHI
        "trade_count_N": compute_trade_count(volume, window=trade_count_window),
        "volume_concentration_hhi_N": compute_volume_concentration_hhi(
            volume, window=volume_concentration_window,
        ),
    }
