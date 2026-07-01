"""Candle Pattern Feature Group — multi-bar pattern detection from OHLCV.

Authority: AlphaForge owns feature discovery and specification.
This module computes multi-bar candlestick pattern features from OHLCV data.
Patterns are scaled into continuous scores for ML consumption.

Features (7 total):
  - doji_N:         Rolling fraction of doji candles (|open-close| <= threshold*range)
  - marubozu_N:     Rolling fraction of marubozu candles (body >> shadows)
  - engulfing_N:    Rolling fraction of bullish/bearish engulfing patterns
  - hammer_N:       Rolling fraction of hammer / shooting star patterns
  - gap_N:          Rolling fraction of gap openings (open vs prior close)
  - consecutive_up_N:  Consecutive up bars (close > open) count
  - consecutive_dn_N:  Consecutive down bars (close < open) count

Design constraints:
  - numpy only (no pandas, scipy, ta-lib)
  - all features are causal: pattern at bar[t] uses bars [t-lookback+1 .. t]
  - NaN fill for insufficient lookback at series start
  - deterministic: same input always produces identical output
"""

from __future__ import annotations

import logging
from typing import Dict

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Doji threshold: body / total range <= DOJI_BODY_THRESHOLD
DEFAULT_DOJI_THRESHOLD: float = 0.1
# Marubozu threshold: (high-low) / body <= MARUBOZU_SHADOW_THRESHOLD
DEFAULT_MARUBOZU_SHADOW_THRESHOLD: float = 0.2

DEFAULT_CANDLE_WINDOW: int = 10

# ---------------------------------------------------------------------------
# Per-bar pattern helpers
# ---------------------------------------------------------------------------

def _is_doji(
    open_arr: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    threshold: float = DEFAULT_DOJI_THRESHOLD,
) -> np.ndarray:
    """Detect doji candles: body / total range <= threshold.

    Returns boolean array (True for doji bars).
    """
    n = len(close)
    result = np.zeros(n, dtype=bool)
    body = np.abs(close - open_arr)
    total_range = high - low
    valid = total_range > 0
    result[valid] = (body[valid] / total_range[valid]) <= threshold
    return result


def _is_marubozu(
    open_arr: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    shadow_threshold: float = DEFAULT_MARUBOZU_SHADOW_THRESHOLD,
) -> np.ndarray:
    """Detect marubozu candles: shadows are small relative to total range.

    Marubozu = very small or no upper/lower shadows => body dominates.
    Returns boolean array.
    """
    n = len(close)
    result = np.zeros(n, dtype=bool)
    body = np.abs(close - open_arr)
    total_range = high - low
    valid = total_range > 0
    if not np.any(valid):
        return result
    upper_shadow = high - np.maximum(open_arr, close)
    lower_shadow = np.minimum(open_arr, close) - low
    shadow_ratio = (upper_shadow + lower_shadow) / total_range
    # Marubozu when shadows are small relative to body
    result[valid] = (shadow_ratio[valid] * 2.0) <= shadow_threshold
    return result


def _is_engulfing(
    open_arr: np.ndarray,
    close: np.ndarray,
) -> np.ndarray:
    """Detect bullish/bearish engulfing patterns (2-bar).

    Bullish engulfing: prior close < prior open (bearish) AND
                       current close > current open (bullish) AND
                       current open < prior close AND current close > prior open.
    Bearish engulfing: prior close > prior open (bullish) AND
                       current close < current open (bearish) AND
                       current open > prior close AND current close < prior open.

    Returns boolean array (True for the second bar of an engulfing pattern).
    Position 0 is always False (cannot detect 2-bar pattern with 1 bar).
    """
    n = len(close)
    result = np.zeros(n, dtype=bool)
    if n < 2:
        return result
    for i in range(1, n):
        prior_bearish = close[i - 1] < open_arr[i - 1]
        prior_bullish = close[i - 1] > open_arr[i - 1]
        curr_bullish = close[i] > open_arr[i]
        curr_bearish = close[i] < open_arr[i]

        # Bullish engulfing
        if prior_bearish and curr_bullish:
            if open_arr[i] < close[i - 1] and close[i] > open_arr[i - 1]:
                result[i] = True
        # Bearish engulfing
        if prior_bullish and curr_bearish:
            if open_arr[i] > close[i - 1] and close[i] < open_arr[i - 1]:
                result[i] = True
    return result


def _is_hammer(
    open_arr: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
) -> np.ndarray:
    """Detect hammer / shooting star patterns.

    Hammer: small body at top of range, long lower shadow (2-3x body).
    Shooting star: small body at bottom of range, long upper shadow.

    Returns boolean array.
    """
    n = len(close)
    result = np.zeros(n, dtype=bool)
    for i in range(n):
        body = abs(close[i] - open_arr[i])
        total_range = high[i] - low[i]
        if total_range <= 0 or body <= 0:
            continue
        upper_shadow = high[i] - max(open_arr[i], close[i])
        lower_shadow = min(open_arr[i], close[i]) - low[i]
        # Hammer: lower shadow >= 2 * body, upper shadow <= 0.3 * body
        if lower_shadow >= 2.0 * body and upper_shadow <= 0.3 * body:
            result[i] = True
        # Shooting star: upper shadow >= 2 * body, lower shadow <= 0.3 * body
        if upper_shadow >= 2.0 * body and lower_shadow <= 0.3 * body:
            result[i] = True
    return result


def _is_gap(
    open_arr: np.ndarray,
    close: np.ndarray,
) -> np.ndarray:
    """Detect gap openings: open[t] differs from close[t-1].

    Returns boolean array (True for bars that gapped). Position 0 is always False.
    """
    n = len(close)
    result = np.zeros(n, dtype=bool)
    if n < 2:
        return result
    # Gap up: open > prior close (with minimum threshold)
    # Gap down: open < prior close
    gap_up = open_arr[1:] > close[:-1] * 1.001  # 0.1% minimum gap
    gap_dn = open_arr[1:] < close[:-1] * 0.999
    result[1:] = gap_up | gap_dn
    return result


def _consecutive_up(close: np.ndarray, open_arr: np.ndarray) -> np.ndarray:
    """Compute consecutive up bars count (close > open)."""
    n = len(close)
    result = np.zeros(n, dtype=np.float64)
    for i in range(1, n):
        if close[i] > open_arr[i] and close[i - 1] > open_arr[i - 1]:
            result[i] = result[i - 1] + 1.0
        elif close[i] > open_arr[i]:
            result[i] = 1.0
        else:
            result[i] = 0.0
    return result


def _consecutive_down(close: np.ndarray, open_arr: np.ndarray) -> np.ndarray:
    """Compute consecutive down bars count (close < open)."""
    n = len(close)
    result = np.zeros(n, dtype=np.float64)
    for i in range(1, n):
        if close[i] < open_arr[i] and close[i - 1] < open_arr[i - 1]:
            result[i] = result[i - 1] + 1.0
        elif close[i] < open_arr[i]:
            result[i] = 1.0
        else:
            result[i] = 0.0
    return result


# ---------------------------------------------------------------------------
# Rolling helpers
# ---------------------------------------------------------------------------

def _rolling_fraction(mask: np.ndarray, window: int) -> np.ndarray:
    """Rolling fraction of True values in mask over window bars.

    NaN for t < window-1. Fraction = count(True) / window.
    """
    n = len(mask)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result
    for i in range(window - 1, n):
        seg = mask[i - window + 1 : i + 1]
        result[i] = float(np.sum(seg)) / float(window)
    return result


# ---------------------------------------------------------------------------
# Group compute function
# ---------------------------------------------------------------------------

def compute_candle_pattern_group(
    open_arr: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    window: int = DEFAULT_CANDLE_WINDOW,
) -> Dict[str, np.ndarray]:
    """Compute all Candle Pattern group features (7 total).

    Returns dict with keys:
      - doji_N:          Rolling fraction of doji candles
      - marubozu_N:      Rolling fraction of marubozu candles
      - engulfing_N:     Rolling fraction of engulfing patterns
      - hammer_N:        Rolling fraction of hammer/shooting star patterns
      - gap_N:           Rolling fraction of gap openings
      - consecutive_up_N:  Count of consecutive up bars
      - consecutive_dn_N:  Count of consecutive down bars

    All arrays same length as input. NaN at start for insufficient lookback
    where applicable. Consecutive counts start at 0.

    Causality: all patterns use only bars [t-window+1 .. t].

    Args:
        open_arr: Open prices.
        high: High prices.
        low: Low prices.
        close: Close prices.
        window: Rolling window for pattern fractions (default 10).

    Returns:
        Dict mapping feature name to numpy array of shape (n_bars,).
    """
    return {
        "doji_N": _rolling_fraction(
            _is_doji(open_arr, high, low, close), window,
        ),
        "marubozu_N": _rolling_fraction(
            _is_marubozu(open_arr, high, low, close), window,
        ),
        "engulfing_N": _rolling_fraction(
            _is_engulfing(open_arr, close), window,
        ),
        "hammer_N": _rolling_fraction(
            _is_hammer(open_arr, high, low, close), window,
        ),
        "gap_N": _rolling_fraction(
            _is_gap(open_arr, close), window,
        ),
        "consecutive_up_N": _consecutive_up(close, open_arr),
        "consecutive_dn_N": _consecutive_down(close, open_arr),
    }
