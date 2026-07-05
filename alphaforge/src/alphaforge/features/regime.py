"""Regime Detection — rule-based baseline classifier.

Phase 2 baseline: simple interpretable rules for regime classification.
Phase 3 (future): supervised classifier replacement (separate scope, issue #78).

Classification rules (per timestamp):
  TREND_UP:    close > SMA(50) AND slope > 0
  TREND_DOWN:  close < SMA(50) AND slope < 0
  RANGE:       ATR(14)/close < 0.02  (low volatility consolidation)
  TRANSITION:  none of the above (or insufficient data)

Design constraints:
  - numpy only (no pandas dependency in core computation)
  - deterministic: same input always produces identical output
  - pure function of price series
  - per-symbol classification at each timestamp

Authority: AlphaForge owns regime detection.
Cross-ref: v7/docs/v7_regime_aware_extensions.md for regime definitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Sequence
import math

import numpy as np

try:
    from numba import njit
except ImportError:
    njit = lambda x: x


# ===========================================================================
# Constants
# ===========================================================================

SMA_PERIOD: int = 50
ATR_PERIOD: int = 14
SLOPE_LOOKBACK: int = 10  # bars for linear regression slope
RANGE_ATR_PCT_THRESHOLD: float = 0.02  # ATR/close < 2% => RANGE

# ===========================================================================
# Constants for Online Regime Detector (#161)
# ===========================================================================

# CUSUM change point detection constants
DEFAULT_CUSUM_THRESHOLD: float = 5.0
DEFAULT_CUSUM_DRIFT: float = 0.0

# HMM streaming volatility classifier constants
DEFAULT_HMM_VOL_WINDOW: int = 20
DEFAULT_HMM_TRANS_PROB: float = 0.85
DEFAULT_HMM_VOL_FACTOR: float = 2.0

# Volatility regime constants
DEFAULT_VOL_REGIME_WINDOW: int = 20
DEFAULT_VOL_REGIME_LOW_PERCENTILE: float = 33.0
DEFAULT_VOL_REGIME_HIGH_PERCENTILE: float = 67.0

# Mode-specific SWING (4h primary)
SWING_CUSUM_THRESHOLD: float = 5.0
SWING_HMM_VOL_WINDOW: int = 20
SWING_VOL_REGIME_WINDOW: int = 20

# Mode-specific SCALP (1h primary)
SCALP_CUSUM_THRESHOLD: float = 3.0
SCALP_HMM_VOL_WINDOW: int = 15
SCALP_VOL_REGIME_WINDOW: int = 15

# Mode-specific AGGRESSIVE_SCALP (15m primary)
AGGRESSIVE_SCALP_CUSUM_THRESHOLD: float = 2.0
AGGRESSIVE_SCALP_HMM_VOL_WINDOW: int = 10
AGGRESSIVE_SCALP_VOL_REGIME_WINDOW: int = 10
# ===========================================================================
# Enums and dataclasses
# ===========================================================================


class Regime(Enum):
    """Market regime classification.

    Matches the canonical Regime enum from v7/docs/v7_regime_aware_extensions.md.
    """

    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    TRANSITION = "TRANSITION"


@dataclass(frozen=True)
class RegimeSignal:
    """Immutable output from regime detection at a single timestamp.

    Attributes:
        regime: Classified regime.
        confidence: Classification confidence 0.0 to 1.0.
            - TREND_UP/DOWN: proportional to |slope| strength
            - RANGE: 1.0 - atr_pct / threshold (capped)
            - TRANSITION: always 0.5 (no positive signal)
        sma_50: SMA(50) value at this timestamp (NaN if unavailable).
        atr_pct: ATR(14)/close ratio at this timestamp (NaN if unavailable).
        slope: Linear regression slope of closes over SLOPE_LOOKBACK bars.
    """

    regime: Regime
    confidence: float
    sma_50: float
    atr_pct: float
    slope: float


# ===========================================================================
# Indicator helpers (numpy-only, deterministic)
# ===========================================================================


def _sma(data: np.ndarray, period: int) -> np.ndarray:
    """Simple Moving Average over `period` bars.

    Returns array of same length as data, with NaN for indices < period-1.
    """
    n = len(data)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < period:
        return result
    kernel = np.ones(period, dtype=np.float64) / period
    result[period - 1 :] = np.convolve(data, kernel, mode="valid")
    return result


def _true_range(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray
) -> np.ndarray:
    """True Range series (n-1 elements for n input bars).

    TR[i] = max(high[i+1]-low[i+1], |high[i+1]-close[i]|, |low[i+1]-close[i]|)
    """
    n = len(highs)
    if n < 2:
        return np.array([], dtype=np.float64)
    tr1 = highs[1:] - lows[1:]
    tr2 = np.abs(highs[1:] - closes[:-1])
    tr3 = np.abs(lows[1:] - closes[:-1])
    return np.maximum(np.maximum(tr1, tr2), tr3)


def _atr(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int
) -> np.ndarray:
    """Average True Range over `period` bars.

    Returns array of same length as highs, with NaN for indices < period.
    Uses simple moving average of True Range.
    """
    n = len(highs)
    result = np.full(n, np.nan, dtype=np.float64)
    tr = _true_range(highs, lows, closes)
    if len(tr) < period:
        return result
    kernel = np.ones(period, dtype=np.float64) / period
    tr_ma = np.convolve(tr, kernel, mode="valid")
    # tr[0] corresponds to bar 1, so tr_ma maps to bars [period:]
    result[period:] = tr_ma
    return result


@njit
def _linreg_slope(y: np.ndarray) -> float:
    """Linear regression slope of y against bar index.

    Returns slope in units of y per bar.
    Returns 0.0 for length < 2 or zero variance.
    """
    n = len(y)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=np.float64)
    x_mean = np.mean(x)
    y_mean = np.mean(y)
    numerator = np.sum((x - x_mean) * (y - y_mean))
    denominator = np.sum((x - x_mean) ** 2)
    if denominator == 0:
        return 0.0
    return numerator / denominator


@njit
def _rolling_slope(data: np.ndarray, period: int) -> np.ndarray:
    """Rolling linear regression slope over `period` bars.

    Returns array of same length as data, with NaN for indices < period-1.
    """
    n = len(data)
    result = np.full(n, np.nan, dtype=np.float64)
    for i in range(period - 1, n):
        window = data[i - period + 1 : i + 1]
        result[i] = _linreg_slope(window)
    return result


# ===========================================================================
# Core classification
# ===========================================================================


def classify_regime(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
) -> List[RegimeSignal]:
    """Classify regime for each timestamp in a single-symbol price series.

    Args:
        closes: Close prices, oldest first.
        highs: High prices, same length.
        lows: Low prices, same length.

    Returns:
        List of RegimeSignal, one per timestamp, same length as closes.
        Early bars (before sufficient lookback) return Regime.TRANSITION
        with low confidence and NaN indicator values.

    Raises:
        ValueError: If arrays have different lengths or zero length.
    """
    n = len(closes)
    if n == 0:
        raise ValueError("Empty price arrays")
    if len(highs) != n or len(lows) != n:
        raise ValueError(
            f"Length mismatch: closes={n}, highs={len(highs)}, lows={len(lows)}"
        )

    # Compute indicators
    sma_50 = _sma(closes, SMA_PERIOD)
    atr_14 = _atr(highs, lows, closes, ATR_PERIOD)
    slope_arr = _rolling_slope(closes, SLOPE_LOOKBACK)

    results: List[RegimeSignal] = []

    for i in range(n):
        sma_val = sma_50[i]
        slope_val = slope_arr[i]

        # Compute ATR percentage for this bar
        atr_pct_val: float = float("nan")
        if not np.isnan(atr_14[i]) and closes[i] > 0:
            atr_pct_val = atr_14[i] / closes[i]

        # Insufficient lookback: can't classify
        if np.isnan(sma_val) or np.isnan(slope_val):
            results.append(
                RegimeSignal(
                    regime=Regime.TRANSITION,
                    confidence=0.0,
                    sma_50=sma_val,
                    atr_pct=atr_pct_val,
                    slope=slope_val,
                )
            )
            continue

        close_i = closes[i]

        # TREND_UP: close > SMA(50) AND slope > 0
        if close_i > sma_val and slope_val > 0.0:
            # Confidence proportional to slope strength, capped at 1.0
            raw_conf = abs(slope_val) * 1000.0 / close_i
            confidence = min(1.0, raw_conf)
            results.append(
                RegimeSignal(
                    regime=Regime.TREND_UP,
                    confidence=confidence,
                    sma_50=sma_val,
                    atr_pct=atr_pct_val,
                    slope=slope_val,
                )
            )
        # TREND_DOWN: close < SMA(50) AND slope < 0
        elif close_i < sma_val and slope_val < 0.0:
            raw_conf = abs(slope_val) * 1000.0 / close_i
            confidence = min(1.0, raw_conf)
            results.append(
                RegimeSignal(
                    regime=Regime.TREND_DOWN,
                    confidence=confidence,
                    sma_50=sma_val,
                    atr_pct=atr_pct_val,
                    slope=slope_val,
                )
            )
        # RANGE: ATR(14)/close < threshold (low volatility consolidation)
        elif not np.isnan(atr_pct_val) and atr_pct_val < RANGE_ATR_PCT_THRESHOLD:
            confidence = max(0.3, 1.0 - atr_pct_val / RANGE_ATR_PCT_THRESHOLD)
            results.append(
                RegimeSignal(
                    regime=Regime.RANGE,
                    confidence=confidence,
                    sma_50=sma_val,
                    atr_pct=atr_pct_val,
                    slope=slope_val,
                )
            )
        # TRANSITION: none of the above criteria matched
        else:
            results.append(
                RegimeSignal(
                    regime=Regime.TRANSITION,
                    confidence=0.5,
                    sma_50=sma_val,
                    atr_pct=atr_pct_val,
                    slope=slope_val,
                )
            )

    return results


# ===========================================================================
# Multi-symbol classification
# ===========================================================================


def classify_regime_multi_symbol(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    symbols: np.ndarray,
) -> Dict[str, List[RegimeSignal]]:
    """Classify regime for multiple symbols.

    Args:
        closes: Close prices of shape (n,), all symbols concatenated.
        highs: High prices of shape (n,).
        lows: Low prices of shape (n,).
        symbols: Symbol labels of shape (n,). Data must be sorted
            chronologically within each symbol group.

    Returns:
        Dict mapping symbol -> List[RegimeSignal], one per bar for that symbol.

    Raises:
        ValueError: If arrays have mismatched lengths.
    """
    n = len(closes)
    if len(highs) != n or len(lows) != n or len(symbols) != n:
        raise ValueError("All input arrays must have same length")

    results: Dict[str, List[RegimeSignal]] = {}

    unique_symbols = np.unique(symbols)
    for sym in unique_symbols:
        mask = symbols == sym
        sym_closes = closes[mask]
        sym_highs = highs[mask]
        sym_lows = lows[mask]
        results[str(sym)] = classify_regime(sym_closes, sym_highs, sym_lows)

    return results


# ===========================================================================
# Diagnostic helpers
# ===========================================================================


def regime_counts(signals: Sequence[RegimeSignal]) -> Dict[str, int]:
    """Count regime occurrences in a signal sequence.

    Returns:
        Dict with keys 'TREND_UP', 'TREND_DOWN', 'RANGE', 'TRANSITION'.
    """
    counts: Dict[str, int] = {
        "TREND_UP": 0,
        "TREND_DOWN": 0,
        "RANGE": 0,
        "TRANSITION": 0,
    }
    for s in signals:
        counts[s.regime.value] += 1
    return counts


def regime_transitions(signals: Sequence[RegimeSignal]) -> int:
    """Count number of regime changes in a signal sequence."""
    if len(signals) < 2:
        return 0
    transitions = 0
    for i in range(1, len(signals)):
        if signals[i].regime != signals[i - 1].regime:
            transitions += 1
    return transitions

# ===========================================================================
# Online Regime Detector (#161) — compute functions and streaming class
# ===========================================================================
def _compute_log_return(close: np.ndarray) -> np.ndarray:
    """Compute 1-bar log returns from close prices (internal helper).

    r[0] = NaN, r[t] = ln(close[t] / close[t-1]) for t >= 1.
    NaN at bar 0. NaN-safe division.

    Causality: uses close[t] and close[t-1] only.
    """
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < 2:
        return result
    with np.errstate(divide="ignore", invalid="ignore"):
        result[1:] = np.log(close[1:] / close[:-1])
    return result


@njit
def _gaussian_pdf(x: float, mu: float, sigma: float) -> float:
    """Unnormalized Gaussian PDF (no sqrt(2pi) factor).

    Returns density at x for N(mu, sigma^2), excluding the
    1/sqrt(2pi) constant since it cancels in likelihood ratios.
    """
    if sigma <= 1e-12:
        return 1.0 if abs(x - mu) <= 1e-12 else 0.0
    z = (x - mu) / sigma
    if abs(z) > 30.0:
        return 0.0
    return math.exp(-0.5 * z * z) / sigma


# ===========================================================================
# Feature: CUSUM change point detection
# ===========================================================================


@njit
def _njit_cusum_loop(log_ret: np.ndarray, threshold: float, drift: float) -> tuple:
    """Numba JIT helper: CUSUM loop body."""
    n = len(log_ret)
    cusum_pos = np.full(n, np.nan, dtype=np.float64)
    cusum_neg = np.full(n, np.nan, dtype=np.float64)
    cusum_sig = np.full(n, np.nan, dtype=np.float64)

    s_pos = 0.0
    s_neg = 0.0

    for i in range(1, n):
        ret = log_ret[i] if not np.isnan(log_ret[i]) else 0.0
        s_pos = max(0.0, s_pos + ret - drift)
        s_neg = min(0.0, s_neg + ret - drift)
        sig = 0.0
        if s_pos > threshold:
            sig = 1.0
            s_pos = 0.0
        elif s_neg < -threshold:
            sig = 1.0
            s_neg = 0.0
        cusum_pos[i] = s_pos
        cusum_neg[i] = abs(s_neg)
        cusum_sig[i] = sig

    return cusum_pos, cusum_neg, cusum_sig


def compute_cusum_detector(
    close: np.ndarray,
    threshold: float = DEFAULT_CUSUM_THRESHOLD,
    drift: float = DEFAULT_CUSUM_DRIFT,
) -> Dict[str, np.ndarray]:
    """CUSUM change point detection on log returns.

    CUSUM (Cumulative Sum) detects shifts in the mean of log returns.
    When the cumulative sum exceeds the threshold, a change point is
    signaled and the corresponding sum resets to zero.

    S_pos[t] = max(0, S_pos[t-1] + log_return[t] - drift)
    S_neg[t] = min(0, S_neg[t-1] + log_return[t] - drift)

    Args:
        close: Close prices.
        threshold: CUSUM decision interval. Higher = fewer alarms.
        drift: Allowable slack (small positive). Zero by default.

    Returns:
        Dict with keys:
          cusum_positive: Positive CUSUM accumulation (NaN at bar 0).
          cusum_negative: Absolute value of negative CUSUM (NaN at bar 0).
          cusum_signal:   1 when a change is detected, else 0 (NaN at bar 0).

    Causality: CUSUM at t uses returns up to t. Cumulative by construction.
    """
    n = len(close)
    nan_arr = np.full(n, np.nan, dtype=np.float64)
    if n < 2:
        return {
            "cusum_positive": nan_arr,
            "cusum_negative": nan_arr,
            "cusum_signal": nan_arr,
        }

    log_ret = _compute_log_return(close)

    cusum_pos, cusum_neg, cusum_sig = _njit_cusum_loop(log_ret, threshold, drift)

    return {
        "cusum_positive": cusum_pos,
        "cusum_negative": cusum_neg,
        "cusum_signal": cusum_sig,
    }


# ===========================================================================
# Feature: HMM streaming volatility state classification
# ===========================================================================


@njit
def _njit_hmm_loop(
    log_ret: np.ndarray,
    init_idx: int,
    low_vol: float,
    high_vol: float,
    trans_prob: float,
    vol_factor: float,
    prob_high: float,
) -> tuple:
    """Numba JIT helper: HMM streaming loop body."""
    n = len(log_ret)
    vol_state = np.full(n, np.nan, dtype=np.float64)
    vol_prob = np.full(n, np.nan, dtype=np.float64)
    alpha = 1.0 - trans_prob

    for i in range(init_idx, n):
        like_high = _gaussian_pdf(log_ret[i], 0.0, high_vol)
        like_low = _gaussian_pdf(log_ret[i], 0.0, low_vol)

        prior_high = (
            prob_high * trans_prob + (1.0 - prob_high) * (1.0 - trans_prob)
        )
        prior_low = (
            (1.0 - prob_high) * trans_prob + prob_high * (1.0 - trans_prob)
        )

        post_numer = like_high * prior_high
        post_low_numer = like_low * prior_low
        total = post_numer + post_low_numer
        prob_high = post_numer / total if total > 0 else 0.5

        vol_prob[i] = prob_high
        vol_state[i] = 1.0 if prob_high > 0.5 else 0.0

        if prob_high > 0.5:
            high_vol = math.sqrt(
                (1.0 - alpha) * high_vol ** 2 + alpha * log_ret[i] ** 2
            )
        else:
            low_vol = math.sqrt(
                (1.0 - alpha) * low_vol ** 2 + alpha * log_ret[i] ** 2
            )

        if high_vol <= low_vol:
            high_vol = low_vol * vol_factor

    return vol_state, vol_prob


def compute_hmm_vol_state(
    close: np.ndarray,
    window: int = DEFAULT_HMM_VOL_WINDOW,
    trans_prob: float = DEFAULT_HMM_TRANS_PROB,
    vol_factor: float = DEFAULT_HMM_VOL_FACTOR,
) -> Dict[str, np.ndarray]:
    """Streaming 2-state volatility classifier via HMM-like forward algorithm.

    Uses adaptive thresholding on absolute log returns with a forward-pass
    probability update that mimics the HMM forward algorithm:

      State 0: Low volatility (small absolute returns).
      State 1: High volatility (large absolute returns).

    State parameters are initialized from the first ``window`` bars, then
    updated adaptively via exponential smoothing weighted by state posterior.

    Args:
        close: Close prices.
        window: Initialization and adaptation window.
        trans_prob: HMM self-transition probability P(same | previous).
            Higher values produce more temporally coherent state sequences.
        vol_factor: Multiplicative separation between high and low vol.

    Returns:
        Dict with keys:
          hmm_vol_state:        Most likely state (0 = low vol, 1 = high vol).
          hmm_vol_probability:  Smoothed probability of high volatility state.

        First ``window`` bars are NaN (need window returns for initialization).

    Causality: state at t uses returns up to t. Forward-pass only.
    """
    n = len(close)
    nan_state = np.full(n, np.nan, dtype=np.float64)
    nan_prob = np.full(n, np.nan, dtype=np.float64)

    if n < window + 1:
        return {"hmm_vol_state": nan_state, "hmm_vol_probability": nan_prob}

    log_ret = _compute_log_return(close)

    vol_state = np.full(n, np.nan, dtype=np.float64)
    vol_prob = np.full(n, np.nan, dtype=np.float64)

    # --- Initialize from first ``window`` returns ---
    init_idx = window + 1  # log_ret[window] is the (window)th return
    init_abs = np.abs(log_ret[1:init_idx])

    low_vol = float(np.percentile(init_abs, 25.0))
    high_vol = max(
        float(np.percentile(init_abs, 75.0)) * 1.5,
        low_vol * vol_factor,
    )
    if high_vol <= low_vol:
        high_vol = low_vol * vol_factor

    prob_high = 0.5

    # Bars 0..window remain NaN (warmup). Classification starts at window+1.
    # Seed prob_high using the first non-init return's likelihood for temporal coherence.
    first_ret = log_ret[init_idx]
    like_high = _gaussian_pdf(first_ret, 0.0, high_vol)
    like_low = _gaussian_pdf(first_ret, 0.0, low_vol)
    total = like_high + like_low
    prob_high = like_high / total if total > 0 else 0.5

    vol_state, vol_prob = _njit_hmm_loop(
        log_ret, init_idx, low_vol, high_vol, trans_prob, vol_factor, prob_high,
    )

    return {
        "hmm_vol_state": vol_state,
        "hmm_vol_probability": vol_prob,
    }


# ===========================================================================
# Feature: Volatility regime classification (LOW/MEDIUM/HIGH)
# ===========================================================================


def _vectorized_vol_regime(
    log_ret: np.ndarray,
    window: int,
    low_percentile: float,
    high_percentile: float,
) -> np.ndarray:
    """Vectorized volatility regime using sliding_window_view + np.sort.

    Normalizes log_ret to fill NaN with 0, then uses sliding_window_view
    to get all windows at once. Sorts each window via np.sort along the
    last axis and picks the threshold at the appropriate percentile index.
    """
    from numpy.lib.stride_tricks import sliding_window_view

    n = len(log_ret)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result

    # log_ret[0] is always NaN (no prior bar for return), so we skip the first
    # window that contains it. Valid windows start at position 1.
    clean = np.abs(np.where(np.isnan(log_ret), 0.0, log_ret))

    # All windows as a view; skip the first window (contains position 0 = NaN return)
    abs_windows = sliding_window_view(clean, window)[1:]
    n_windows = n - window  # = len(abs_windows)

    if n_windows < 1:
        return result

    # Count valid (non-NaN) entries per window (first window had log_ret[0]=NaN)
    nan_mask = np.isnan(log_ret)
    nan_csum = np.cumsum(np.insert(nan_mask.astype(np.float64), 0, 0))
    n_valid = window - (nan_csum[window + 1:] - nan_csum[1:n_windows + 1])
    valid_mask = n_valid >= 5

    # Compute percentile thresholds via np.sort + index
    k_low = max(0, min(window - 1, int(np.ceil(low_percentile / 100.0 * window) - 1)))
    k_high = max(0, min(window - 1, int(np.ceil(high_percentile / 100.0 * window) - 1)))

    low_thresh = np.full(n_windows, np.nan, dtype=np.float64)
    high_thresh = np.full(n_windows, np.nan, dtype=np.float64)

    if valid_mask.any():
        sorted_windows = np.sort(abs_windows[valid_mask], axis=-1)
        low_thresh[valid_mask] = sorted_windows[:, k_low]
        high_thresh[valid_mask] = sorted_windows[:, k_high]

    current_abs = np.abs(log_ret[window:])

    # Classify at positions [window, ..., n-1]
    result[window:] = np.where(
        current_abs <= low_thresh, 0.0,
        np.where(current_abs >= high_thresh, 2.0, 1.0)
    )

    return result


def compute_volatility_regime(
    close: np.ndarray,
    window: int = DEFAULT_VOL_REGIME_WINDOW,
    low_percentile: float = DEFAULT_VOL_REGIME_LOW_PERCENTILE,
    high_percentile: float = DEFAULT_VOL_REGIME_HIGH_PERCENTILE,
) -> np.ndarray:
    """Classify per-bar volatility into LOW (0), MEDIUM (1), or HIGH (2).

    At each bar t, compares the current absolute log return to percentiles
    of absolute returns over the preceding ``window`` bars:

      |r[t]| <= P_low   -> LOW (0)
      |r[t]| >= P_high  -> HIGH (2)
      otherwise          -> MEDIUM (1)

    Args:
        close: Close prices.
        window: Rolling lookback for percentile estimation.
        low_percentile: Percentile for LOW boundary.
        high_percentile: Percentile for HIGH boundary.

    Returns:
        numpy array of dtype float64 with values 0.0, 1.0, 2.0 or NaN.
        First ``window`` bars are NaN (need window+1 for first return).

    Causality: at t uses returns [t-window+1 .. t] only.
    """
    n = len(close)
    if n < window + 1:
        return np.full(n, np.nan, dtype=np.float64)

    log_ret = _compute_log_return(close)
    return _vectorized_vol_regime(log_ret, window, low_percentile, high_percentile)


# ===========================================================================
# OnlineRegimeDetector class (stateful per-bar streaming)
# ===========================================================================


class OnlineRegimeDetector:
    """Stateful online regime detector for per-bar streaming use.

    Combines three detection methods in a single streaming pass:
      - CUSUM change point detection on log returns
      - HMM-like streaming 2-state volatility classification
      - Per-bar volatility regime estimation (LOW/MEDIUM/HIGH)

    Maintains internal state across update() calls. The first N bars
    (determined by max warmup window) produce NaN results during warmup.

    Usage:
        detector = OnlineRegimeDetector(cusum_threshold=5.0)
        for bar in bars:
            state = detector.update(close=bar.close)

    Attributes match the parameter names of the compute functions.
    """

    def __init__(
        self,
        cusum_threshold: float = DEFAULT_CUSUM_THRESHOLD,
        cusum_drift: float = DEFAULT_CUSUM_DRIFT,
        hmm_vol_window: int = DEFAULT_HMM_VOL_WINDOW,
        hmm_trans_prob: float = DEFAULT_HMM_TRANS_PROB,
        hmm_vol_factor: float = DEFAULT_HMM_VOL_FACTOR,
        vol_regime_window: int = DEFAULT_VOL_REGIME_WINDOW,
        vol_regime_low_pct: float = DEFAULT_VOL_REGIME_LOW_PERCENTILE,
        vol_regime_high_pct: float = DEFAULT_VOL_REGIME_HIGH_PERCENTILE,
    ):
        self.cusum_threshold = cusum_threshold
        self.cusum_drift = cusum_drift
        self.hmm_vol_window = hmm_vol_window
        self.hmm_trans_prob = hmm_trans_prob
        self.hmm_vol_factor = hmm_vol_factor
        self.vol_regime_window = vol_regime_window
        self.vol_regime_low_pct = vol_regime_low_pct
        self.vol_regime_high_pct = vol_regime_high_pct

        # Warmup: need max(window) + 1 bars for initial vol estimates
        self._warmup = max(hmm_vol_window, vol_regime_window) + 2

        # Rolling return buffer for vol regime
        self._prev_close: Optional[float] = None
        self._returns: List[float] = []
        self._abs_returns: List[float] = []
        self._n_processed = 0

        # CUSUM state
        self._s_pos = 0.0
        self._s_neg = 0.0

        # HMM state
        self._hmm_initialized = False
        self._prob_high = 0.5
        self._low_vol = 1.0
        self._high_vol = 2.0
        self._alpha = 1.0 - hmm_trans_prob

        # Vol regime state
        self._vol_regime_initialized = False
        self._vol_low_thresh = 0.0
        self._vol_high_thresh = 0.0

    def update(
        self, close: float, high: float = 0.0, low: float = 0.0
    ) -> Dict[str, float]:
        """Process one bar and return current regime state.

        Args:
            close: Close price of the current bar.
            high: High price (reserved, not currently used).
            low: Low price (reserved, not currently used).

        Returns:
            Dict with keys: cusum_positive, cusum_negative, cusum_signal,
            hmm_vol_state, hmm_vol_probability, volatility_regime.
            All values are NaN during the warmup period.
        """
        result: Dict[str, float] = {
            "cusum_positive": np.nan,
            "cusum_negative": np.nan,
            "cusum_signal": np.nan,
            "hmm_vol_state": np.nan,
            "hmm_vol_probability": np.nan,
            "volatility_regime": np.nan,
        }

        # Compute log return
        log_ret: Optional[float] = None
        if self._prev_close is not None and self._prev_close > 0:
            log_ret = math.log(close / self._prev_close)
            self._returns.append(log_ret)
            self._abs_returns.append(abs(log_ret))

        self._prev_close = close
        self._n_processed += 1

        if log_ret is None or self._n_processed < 2:
            return result

        # --- CUSUM (starts after first return) ---
        self._s_pos = max(0.0, self._s_pos + log_ret - self.cusum_drift)
        self._s_neg = min(0.0, self._s_neg + log_ret - self.cusum_drift)

        sig = 0.0
        if self._s_pos > self.cusum_threshold:
            sig = 1.0
            self._s_pos = 0.0
        elif self._s_neg < -self.cusum_threshold:
            sig = 1.0
            self._s_neg = 0.0

        result["cusum_positive"] = self._s_pos
        result["cusum_negative"] = abs(self._s_neg)
        result["cusum_signal"] = sig

        # --- HMM and volatility regime need warmup ---
        if self._n_processed < self._warmup:
            return result

        # --- Initialize HMM from warmup data ---
        if not self._hmm_initialized:
            init_abs = np.array(
                self._abs_returns[: self.hmm_vol_window], dtype=np.float64
            )
            self._low_vol = float(np.percentile(init_abs, 25.0))
            high_pct = float(np.percentile(init_abs, 75.0)) * 1.5
            self._high_vol = max(
                high_pct, self._low_vol * self.hmm_vol_factor
            )
            if self._high_vol <= self._low_vol:
                self._high_vol = self._low_vol * self.hmm_vol_factor
            self._hmm_initialized = True

        # --- HMM forward update ---
        like_high = _gaussian_pdf(log_ret, 0.0, self._high_vol)
        like_low = _gaussian_pdf(log_ret, 0.0, self._low_vol)

        prior_high = (
            self._prob_high * self.hmm_trans_prob
            + (1.0 - self._prob_high) * (1.0 - self.hmm_trans_prob)
        )
        prior_low = (
            (1.0 - self._prob_high) * self.hmm_trans_prob
            + self._prob_high * (1.0 - self.hmm_trans_prob)
        )

        post_numer = like_high * prior_high
        post_low_numer = like_low * prior_low
        total = post_numer + post_low_numer
        self._prob_high = post_numer / total if total > 0 else 0.5

        result["hmm_vol_state"] = 1.0 if self._prob_high > 0.5 else 0.0
        result["hmm_vol_probability"] = self._prob_high

        # Adapt volatility estimates
        if self._prob_high > 0.5:
            self._high_vol = math.sqrt(
                (1.0 - self._alpha) * self._high_vol ** 2
                + self._alpha * log_ret ** 2
            )
        else:
            self._low_vol = math.sqrt(
                (1.0 - self._alpha) * self._low_vol ** 2
                + self._alpha * log_ret ** 2
            )

        if self._high_vol <= self._low_vol:
            self._high_vol = self._low_vol * self.hmm_vol_factor

        # --- Volatility regime ---
        if not self._vol_regime_initialized:
            init_abs_arr = np.array(
                self._abs_returns[: self.vol_regime_window], dtype=np.float64
            )
            self._vol_low_thresh = float(
                np.percentile(init_abs_arr, self.vol_regime_low_pct)
            )
            self._vol_high_thresh = float(
                np.percentile(init_abs_arr, self.vol_regime_high_pct)
            )
            self._vol_regime_initialized = True
        else:
            recent = np.array(
                self._abs_returns[-self.vol_regime_window:], dtype=np.float64
            )
            if len(recent) >= 5:
                self._vol_low_thresh = float(
                    np.percentile(recent, self.vol_regime_low_pct)
                )
                self._vol_high_thresh = float(
                    np.percentile(recent, self.vol_regime_high_pct)
                )

        cur_abs = abs(log_ret)
        if cur_abs <= self._vol_low_thresh:
            result["volatility_regime"] = 0.0
        elif cur_abs >= self._vol_high_thresh:
            result["volatility_regime"] = 2.0
        else:
            result["volatility_regime"] = 1.0

        return result

    def reset(self) -> None:
        """Reset all internal state to initial values."""
        self._prev_close = None
        self._returns.clear()
        self._abs_returns.clear()
        self._n_processed = 0
        self._s_pos = 0.0
        self._s_neg = 0.0
        self._hmm_initialized = False
        self._prob_high = 0.5
        self._low_vol = 1.0
        self._high_vol = 2.0
        self._vol_regime_initialized = False


# ===========================================================================
# Regime Group compute function
# ===========================================================================


def compute_regime_group(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    cusum_threshold: float = SWING_CUSUM_THRESHOLD,
    cusum_drift: float = DEFAULT_CUSUM_DRIFT,
    hmm_vol_window: int = SWING_HMM_VOL_WINDOW,
    hmm_trans_prob: float = DEFAULT_HMM_TRANS_PROB,
    hmm_vol_factor: float = DEFAULT_HMM_VOL_FACTOR,
    vol_regime_window: int = SWING_VOL_REGIME_WINDOW,
    vol_regime_low_pct: float = DEFAULT_VOL_REGIME_LOW_PERCENTILE,
    vol_regime_high_pct: float = DEFAULT_VOL_REGIME_HIGH_PERCENTILE,
) -> Dict[str, np.ndarray]:
    """Compute all Online Regime Detector features (6 total).

    Returns dict with keys:
      - cusum_positive:      Positive CUSUM accumulation
      - cusum_negative:      Absolute negative CUSUM accumulation
      - cusum_signal:        CUSUM change point signal (0/1)
      - hmm_vol_state:       HMM volatility state (0=low, 1=high)
      - hmm_vol_probability: HMM high-vol state probability [0, 1]
      - volatility_regime:   Volatility regime (0=LOW, 1=MEDIUM, 2=HIGH)

    All arrays are same length as input. NaN at start for insufficient
    lookback windows.

    Args:
        close: Close prices.
        high: High prices (reserved).
        low: Low prices (reserved).
        cusum_threshold: CUSUM decision interval (mode-specific).
        cusum_drift: CUSUM drift allowance.
        hmm_vol_window: HMM vol state init and adaptation window.
        hmm_trans_prob: HMM self-transition probability.
        hmm_vol_factor: High/low vol separation factor.
        vol_regime_window: Volatility regime lookback window.
        vol_regime_low_pct: LOW volatility percentile boundary.
        vol_regime_high_pct: HIGH volatility percentile boundary.

    Returns:
        Dict mapping feature name to numpy array of shape (n_bars,).
    """
    cusum = compute_cusum_detector(close, cusum_threshold, cusum_drift)
    hmm = compute_hmm_vol_state(
        close, hmm_vol_window, hmm_trans_prob, hmm_vol_factor
    )
    vol = compute_volatility_regime(
        close, vol_regime_window, vol_regime_low_pct, vol_regime_high_pct
    )

    return {
        "cusum_positive": cusum["cusum_positive"],
        "cusum_negative": cusum["cusum_negative"],
        "cusum_signal": cusum["cusum_signal"],
        "hmm_vol_state": hmm["hmm_vol_state"],
        "hmm_vol_probability": hmm["hmm_vol_probability"],
        "volatility_regime": vol,
    }
