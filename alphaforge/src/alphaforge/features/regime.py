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
from typing import Dict, List, Sequence

import numpy as np


# ===========================================================================
# Constants
# ===========================================================================

SMA_PERIOD: int = 50
ATR_PERIOD: int = 14
SLOPE_LOOKBACK: int = 10  # bars for linear regression slope
RANGE_ATR_PCT_THRESHOLD: float = 0.02  # ATR/close < 2% => RANGE


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
    return float(numerator / denominator)


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
