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

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np

from alphaforge.features.orderbook import (
    DEFAULT_AMIHUD_WINDOW,
    DEFAULT_ORDERBOOK_WINDOW,
    compute_orderbook_group,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PIPELINE_VERSION: str = "0.1.0"

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
# FeatureGroup enum
# ---------------------------------------------------------------------------

class FeatureGroup(Enum):
    """Feature group enumeration.

    LEAD_LAG is marked DEFERRED because it requires cross-sectional data
    across symbols (P0.9B dependency). No compute function is mapped for it.
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
    LEAD_LAG = "lead_lag"  # DEFERRED — P0.9B cross-sectional data required


# ---------------------------------------------------------------------------
# FeatureMatrix dataclass
# ---------------------------------------------------------------------------

@dataclass
class FeatureMatrix:
    """Structured container for computed feature arrays.

    Attributes:
        features: Dict mapping feature name to numpy array of shape (n_bars,).
            Features are organized by group. Keys match the output of each
            group's compute function. No Lead-Lag keys are present.
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
            # Infer from active group map
            active = [g.value for g in FeatureGroup if g != FeatureGroup.LEAD_LAG]
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
    # LEAD_LAG is mapped but DEFERRED — compute_features does not call it.
    # Active filtering (lines 119, 1257) keeps LEAD_LAG out of computation
    # until cross-sectional data support lands (P0.9B).
    FeatureGroup.LEAD_LAG: "compute_lead_lag_group",
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


def _rolling_mean(arr: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling mean over `window` bars (NaN-safe).

    Result at index t uses arr[t-window+1 .. t] (causal).
    Returns NaN for t < window-1 or when the window contains insufficient
    non-NaN values (fewer than 2 valid samples).

    NaN values in the input are excluded from the mean computation
    (partial window mean). If all values in the window are NaN, the
    result is NaN.
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
    """Compute rolling standard deviation over `window` bars (NaN-safe).

    Causal: std at index t uses arr[t-window+1 .. t].
    Returns NaN for t < window-1 or when fewer than 2 non-NaN values
    are in the window.

    NaN values in the input are excluded (partial window std).
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


def _rolling_max(arr: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling maximum over `window` bars (causal)."""
    n = len(arr)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result
    for i in range(window - 1, n):
        result[i] = np.max(arr[i - window + 1 : i + 1])
    return result


def _rolling_min(arr: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling minimum over `window` bars (causal)."""
    n = len(arr)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result
    for i in range(window - 1, n):
        result[i] = np.min(arr[i - window + 1 : i + 1])
    return result


def _ema(arr: np.ndarray, period: int) -> np.ndarray:
    """Compute Exponential Moving Average (causal, numpy-only).

    EMA[t] = arr[t] * k + EMA[t-1] * (1 - k)  where k = 2/(period+1).
    Seeded at first non-NaN value.
    Returns NaN for t < period-1 to match convention.
    """
    n = len(arr)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < period:
        return result
    k = 2.0 / (period + 1.0)
    # Seed with SMA of first `period` values
    seed = np.mean(arr[:period].astype(np.float64))
    result[period - 1] = seed
    for i in range(period, n):
        if np.isnan(arr[i]):
            result[i] = result[i - 1]
        else:
            result[i] = arr[i] * k + result[i - 1] * (1.0 - k)
    return result


def _linear_regression_slope(y: np.ndarray) -> float:
    """Compute linear regression slope of y vs index [0, 1, ..., len(y)-1].

    Returns 0.0 if variance is zero or insufficient data.
    """
    n = len(y)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=np.float64)
    x_mean = np.mean(x)
    y_mean = np.mean(y.astype(np.float64))
    numerator = np.sum((x - x_mean) * (y.astype(np.float64) - y_mean))
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
    result = np.full(n, np.nan, dtype=np.float64)
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
    result = np.full(length, np.nan, dtype=np.float64)
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
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result
    for i in range(window - 1, n):
        seg = returns[i - window + 1 : i + 1]
        seg_clean = seg[~np.isnan(seg)]
        if len(seg_clean) < 2:
            result[i] = np.nan
            continue
        mu = np.mean(seg_clean)
        sigma = np.std(seg_clean, ddof=1)
        if sigma < 1e-12:
            result[i] = 0.0
        else:
            result[i] = (returns[i] - mu) / sigma
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
    result = np.full(n, np.nan, dtype=np.float64)
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
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result
    with np.errstate(divide="ignore", invalid="ignore"):
        hl_ratio = (high - low) / np.where(close == 0, np.nan, close)
    for i in range(window - 1, n):
        seg = hl_ratio[i - window + 1 : i + 1]
        seg_clean = seg[~np.isnan(seg)]
        if len(seg_clean) > 0:
            result[i] = np.mean(seg_clean)
    return result


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
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result

    # Precompute per-bar terms
    # Avoid division by zero: if any price is 0, the bar term is NaN
    with np.errstate(divide="ignore", invalid="ignore"):
        hl_term = 0.5 * (np.log(high / low)) ** 2
        co_term = (2.0 * np.log(2.0) - 1.0) * (np.log(close / open_arr)) ** 2

    for i in range(window - 1, n):
        seg_hl = hl_term[i - window + 1 : i + 1]
        seg_co = co_term[i - window + 1 : i + 1]
        # Skip bars where either term is NaN
        valid = ~(np.isnan(seg_hl) | np.isnan(seg_co))
        if np.sum(valid) < 2:
            continue
        gk_sum = np.sum(seg_hl[valid] - seg_co[valid])
        if gk_sum < 0:
            # Clamp to 0 — negative variance is invalid
            result[i] = 0.0
        else:
            result[i] = np.sqrt(gk_sum / np.sum(valid))
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
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result

    with np.errstate(divide="ignore", invalid="ignore"):
        hl_sq = np.log(high / low) ** 2

    denom = 4.0 * np.log(2.0)  # constant factor
    for i in range(window - 1, n):
        seg = hl_sq[i - window + 1 : i + 1]
        seg_clean = seg[~np.isnan(seg)]
        if len(seg_clean) < 2:
            continue
        result[i] = np.sqrt(np.sum(seg_clean) / (denom * len(seg_clean)))
    return result


def compute_volatility_group(
    open_arr: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    window: int = SWING_VOLATILITY_WINDOW,
) -> Dict[str, np.ndarray]:
    """Compute all Volatility group features.

    Returns dict with keys: realized_volatility_N, high_low_range_N,
    garman_klass_vol_N, parkinson_vol_N.
    All arrays same length as input. NaN at start for insufficient lookback.
    """
    return {
        "realized_volatility_N": compute_realized_volatility(close, window),
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
    result = np.full(n, np.nan, dtype=np.float64)
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
    result = np.full(n, np.nan, dtype=np.float64)
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
    result = np.full(n, np.nan, dtype=np.float64)
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
    result = np.full(length, np.nan, dtype=np.float64)
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
    result = np.full(length, np.nan, dtype=np.float64)
    if length <= n:
        return result
    for i in range(n, length):
        if close[i - n] == 0:
            result[i] = np.nan
        else:
            result[i] = (close[i] / close[i - n] - 1.0) * 100.0
    return result


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
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window + 1:
        return result

    # Compute per-bar changes
    delta = np.zeros(n, dtype=np.float64)
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
    nan_arr = np.full(n, np.nan, dtype=np.float64)

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

    Returns dict with keys: momentum_N, roc_N, rsi_N, macd, macd_signal, macd_histogram.
    All arrays same length as input. NaN at start.
    """
    macd_result = compute_macd(close, macd_fast, macd_slow, macd_signal)
    return {
        "momentum_N": compute_momentum_N(close, n),
        "roc_N": compute_roc_N(close, n),
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
    result = np.full(n, np.nan, dtype=np.float64)
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
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result
    for i in range(window - 1, n):
        seg = volume[i - window + 1 : i + 1]
        result[i] = _linear_regression_slope(seg)
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
    result = np.full(n, np.nan, dtype=np.float64)
    if n == 0:
        return result

    tp = (high.astype(np.float64) + low.astype(np.float64) + close.astype(np.float64)) / 3.0
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
    result = np.full(n, np.nan, dtype=np.float64)
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
    result = np.full(n, np.nan, dtype=np.float64)
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
    result = np.full(n, np.nan, dtype=np.float64)
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
    result = np.full(n, np.nan, dtype=np.float64)
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

    Returns dict with keys: bb_position, bb_width, highest_N, lowest_N, range_breakout_N.
    All arrays same length as input. NaN at start.
    """
    upper, middle, lower = compute_bollinger_bands(close, bb_window, bb_num_std)
    return {
        "bb_position": compute_bb_position(close, upper, middle, lower),
        "bb_width": compute_bb_width(upper, middle, lower),
        "highest_N": compute_highest(high, window),
        "lowest_N": compute_lowest(low, window),
        "range_breakout_N": compute_range_breakout(close, high, low, window),
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
    },
}

# Supported modes for feature computation
_SUPPORTED_MODES = frozenset({"SWING", "SCALP", "AGGRESSIVE_SCALP"})


def compute_features(
    ohlcv_data: dict,
    mode: str = "SWING",
    timeframe_stack: Optional[dict] = None,
) -> FeatureMatrix:
    """Main feature pipeline entry point.

    Computes all 7 active feature groups from OHLCV data.
    Lead-Lag features are NOT computed (DEFERRED: P0.9B cross-sectional data).

    Args:
        ohlcv_data: dict with keys 'open', 'high', 'low', 'close', 'volume'.
            Values must be 1D numpy.ndarray of equal length.
        mode: Trading mode string ("SWING", "SCALP", "AGGRESSIVE_SCALP").
            SWING is the implementation baseline. SCALP/AGGRESSIVE_SCALP
            require empirical tuning and are HOLD.
        timeframe_stack: Optional dict with keys primary, context, refinement.
            Informational only — does not affect computation.

    Returns:
        FeatureMatrix with features dict containing ~30 feature arrays,
        each of shape (n_bars,). No Lead-Lag columns present.

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

    # 7. OrderBook Group (4 features)
    features.update(
        compute_orderbook_group(
            open_arr=open_arr,
            high=high,
            low=low,
            close=close,
            volume=volume,
            window=defaults.get("orderbook_window", DEFAULT_ORDERBOOK_WINDOW),
            amihud_window=defaults.get("amihud_window", DEFAULT_AMIHUD_WINDOW),
        )
    )

    # Lead-Lag group is DEFERRED — not computed, no columns added.

    # Verify array length consistency
    for name, arr in features.items():
        if len(arr) != n_bars:
            raise RuntimeError(
                f"Feature '{name}' has length {len(arr)}, expected {n_bars}"
            )

    # Assemble FeatureMatrix
    expected_groups = [
        g.value for g in FeatureGroup
        if g != FeatureGroup.LEAD_LAG
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
            "lead_lag_status": "DEFERRED",
            "lead_lag_reason": "P0.9B cross-sectional data dependency",
            "active_groups": 7,
        },
    )
