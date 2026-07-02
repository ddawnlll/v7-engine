"""Cross-Sectional Rank Feature Group — cross-symbol rank and inter-symbol correlation features.

Authority: AlphaForge owns feature discovery and specification.
Status: HOLD (P0.9B) — requires cross-sectional data pipeline with multi-symbol
OHLCV. Module is wired into FEATURE_GROUP_MAP but not computed in the
single-symbol pipeline until multi-symbol data is available.

This module computes ~7 cross-sectional features that require >= 2 symbols:
  rank_momentum_1h          — rank of short-window momentum across the universe
  rank_momentum_4h          — rank of medium-window momentum across the universe
  rank_momentum_24h         — rank of long-window momentum across the universe
  rank_volatility           — rank of volatility across the universe
  rank_volume               — rank of volume across the universe
  correlation_with_median   — rolling pairwise correlation vs universe median return
  correlation_zscore        — z-score of correlation_with_median (extremes detected)

Design constraints (consistent with pipeline.py):
- numpy only (no pandas, scipy, ta-lib)
- no network calls, no exchange APIs, no real market data
- all features are causal: feature at bar[t] uses bars [t-lookback+1 .. t]
- NaN fill for insufficient lookback at series start
- deterministic: same input always produces identical output

Cross-sectional contract:
  Every function accepts multi-symbol OHLCV data as a Dict mapping symbol
  identifier to a Dict[str, np.ndarray] of OHLCV arrays.
  All symbols must have the same number of bars.
  Missing symbols or mismatched lengths raise ValueError.

Re-enablement conditions (when P0.9B exists):
  (a) Cross-sectional data pipeline available
  (b) Rank computation across symbols validated against known benchmarks
  (c) Correlation vs median logic tested with multi-timeframe fixtures
  (d) FEATURE_GROUP_MAP[FeatureGroup.CROSS_SECTIONAL_RANK] callable from pipeline
"""

from __future__ import annotations

import logging
import warnings
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Feature group identifier
FEATURE_GROUP_NAME: str = "cross_sectional_rank"

# Rank momentum windows (different lookback periods)
MOMENTUM_WINDOW_1H: int = 6       # Short-term momentum
MOMENTUM_WINDOW_4H: int = 24      # Medium-term momentum
MOMENTUM_WINDOW_24H: int = 144    # Long-term momentum

# Volatility rank window
RANK_VOLATILITY_WINDOW: int = 20

# Inter-symbol correlation windows
CORRELATION_WINDOW: int = 20
CORRELATION_ZSCORE_WINDOW: int = 20

# Minimum valid observations in a window
MIN_VALID: int = 5

# SCALP-specific windows (shorter lookbacks for 1h bars)
SCALP_MOMENTUM_WINDOW_1H: int = 4
SCALP_MOMENTUM_WINDOW_4H: int = 12
SCALP_MOMENTUM_WINDOW_24H: int = 48
SCALP_RANK_VOLATILITY_WINDOW: int = 12
SCALP_CORRELATION_WINDOW: int = 12
SCALP_CORRELATION_ZSCORE_WINDOW: int = 12

# AGGRESSIVE_SCALP windows (fastest lookbacks for 15m bars)
AGGRESSIVE_MOMENTUM_WINDOW_1H: int = 4
AGGRESSIVE_MOMENTUM_WINDOW_4H: int = 16
AGGRESSIVE_MOMENTUM_WINDOW_24H: int = 96
AGGRESSIVE_RANK_VOLATILITY_WINDOW: int = 10
AGGRESSIVE_CORRELATION_WINDOW: int = 10
AGGRESSIVE_CORRELATION_ZSCORE_WINDOW: int = 10


# ===========================================================================
# Helpers: multi-symbol validation and feature computation
# ===========================================================================


def _validate_multi_symbol_ohlcv(
    multi_ohlcv: Dict[str, Dict[str, np.ndarray]],
) -> int:
    """Validate multi-symbol OHLCV data and return uniform bar count.

    Args:
        multi_ohlcv: Dict mapping symbol -> OHLCV dict.
            Each OHLCV dict must have keys 'open', 'high', 'low', 'close',
            'volume'. All arrays must be 1D numpy ndarrays of equal length.

    Returns:
        The common number of bars across all symbols.

    Raises:
        ValueError: if fewer than 2 symbols, missing columns, mismatched
            lengths, or invalid data types.
    """
    if not isinstance(multi_ohlcv, dict) or len(multi_ohlcv) < 2:
        raise ValueError(
            f"Cross-sectional rank features require at least 2 symbols, "
            f"got {len(multi_ohlcv) if isinstance(multi_ohlcv, dict) else 0}"
        )

    required = {"open", "high", "low", "close", "volume"}
    bar_counts: List[int] = []

    for symbol, ohlcv in multi_ohlcv.items():
        missing = required - set(ohlcv.keys())
        if missing:
            raise ValueError(f"Symbol '{symbol}' missing required columns: {missing}")

        for col in required:
            arr = ohlcv[col]
            if not isinstance(arr, np.ndarray) or arr.ndim != 1:
                raise TypeError(
                    f"Symbol '{symbol}' column '{col}' must be 1D numpy.ndarray"
                )

        lengths = {col: len(ohlcv[col]) for col in required}
        if len(set(lengths.values())) != 1:
            raise ValueError(
                f"Symbol '{symbol}' has inconsistent OHLCV lengths: {lengths}"
            )
        bar_counts.append(lengths["close"])

    if len(set(bar_counts)) != 1:
        raise ValueError(
            f"All symbols must have the same number of bars. Got lengths: "
            f"{dict(zip(multi_ohlcv.keys(), bar_counts))}"
        )

    n_bars = bar_counts[0]
    if n_bars < 2:
        raise ValueError(
            f"Need at least 2 bars for cross-sectional rank computation, got {n_bars}"
        )

    return n_bars


def _compute_roc(close: np.ndarray, n: int) -> np.ndarray:
    """Compute Rate of Change over N bars (causal).

    roc[t] = (close[t] / close[t-n] - 1) * 100.
    NaN for t < n.

    Causality: uses close[t] and close[t-n] only.
    """
    length = len(close)
    result = np.full(length, np.nan, dtype=np.float64)
    if length <= n:
        return result
    with np.errstate(divide="ignore", invalid="ignore"):
        result[n:] = (close[n:] / close[:-n] - 1.0) * 100.0
    return result


def _compute_log_return_1(close: np.ndarray) -> np.ndarray:
    """Compute 1-bar log return (causal). NaN at t=0."""
    n = len(close)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < 2:
        return result
    with np.errstate(divide="ignore", invalid="ignore"):
        result[1:] = np.log(close[1:] / close[:-1])
    return result


# ===========================================================================
# Core: cross-sectional rank computation
# ===========================================================================


def _cross_sectional_rank(values: np.ndarray) -> np.ndarray:
    """Rank symbols column-wise at each bar (timestamp).

    For each column (bar), ranks the symbols by their values and
    normalizes to [0, 1]. NaN values in the input get NaN rank.

    Args:
        values: 2D array of shape (n_symbols, n_bars).

    Returns:
        2D array of same shape with ranks in [0, 1].
        0 = lowest, 1 = highest. NaN where input is NaN.
    """
    n_symbols, n_bars = values.shape
    result = np.full_like(values, np.nan, dtype=np.float64)

    for bar in range(n_bars):
        col = values[:, bar]
        valid = ~np.isnan(col)
        n_valid = int(np.sum(valid))
        if n_valid < 2:
            # Single valid symbol gets middle rank; all-NaN stays NaN
            if n_valid == 1:
                valid_idx = np.where(valid)[0][0]
                result[valid_idx, bar] = 0.5
            continue

        valid_indices = np.where(valid)[0]
        valid_vals = col[valid]

        # Double argsort: first sorts values, second converts to rank
        order = np.argsort(valid_vals)
        ranks_for_valid = np.empty(n_valid, dtype=np.float64)
        ranks_for_valid[order] = np.arange(n_valid, dtype=np.float64)

        # Normalize to [0, 1]
        ranks_for_valid /= max(n_valid - 1, 1)

        # Place back into result
        for idx, rank_val in zip(valid_indices, ranks_for_valid):
            result[idx, bar] = rank_val

    return result


def _rolling_correlation_vs_series(
    symbol_returns: np.ndarray,
    reference_returns: np.ndarray,
    window: int,
    min_valid: int = MIN_VALID,
) -> np.ndarray:
    """Compute rolling correlation between symbol returns and a reference series.

    Args:
        symbol_returns: 1D array of symbol log returns, length n_bars.
        reference_returns: 1D array of reference log returns, length n_bars.
        window: Rolling window in bars.
        min_valid: Minimum valid pairs required.

    Returns:
        1D array of rolling correlations in [-1, 1], NaN where insufficient data.
    """
    n = len(symbol_returns)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window or window < 2:
        return result

    x = symbol_returns.astype(np.float64)
    y = reference_returns.astype(np.float64)

    for i in range(window - 1, n):
        x_seg = x[i - window + 1 : i + 1]
        y_seg = y[i - window + 1 : i + 1]
        valid = ~np.isnan(x_seg) & ~np.isnan(y_seg)
        n_valid = int(np.sum(valid))
        if n_valid < min_valid:
            continue

        xv = x_seg[valid]
        yv = y_seg[valid]
        dx = xv - np.mean(xv)
        dy = yv - np.mean(yv)
        cov = np.sum(dx * dy) / n_valid
        std_x = np.std(xv, ddof=0)
        std_y = np.std(yv, ddof=0)
        if std_x < 1e-14 or std_y < 1e-14:
            continue
        r = cov / (std_x * std_y)
        result[i] = float(np.clip(r, -1.0, 1.0))

    return result


def _rolling_zscore(arr: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling z-score (causal, NaN-safe)."""
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


# ===========================================================================
# Main compute function
# ===========================================================================


def compute_cross_sectional_rank_group(
    multi_ohlcv: Dict[str, Dict[str, np.ndarray]],
    momentum_window_1h: int = MOMENTUM_WINDOW_1H,
    momentum_window_4h: int = MOMENTUM_WINDOW_4H,
    momentum_window_24h: int = MOMENTUM_WINDOW_24H,
    volatility_window: int = RANK_VOLATILITY_WINDOW,
    correlation_window: int = CORRELATION_WINDOW,
    zscore_window: int = CORRELATION_ZSCORE_WINDOW,
) -> Dict[str, np.ndarray]:
    """Compute all cross-sectional rank and inter-symbol correlation features.

    For each bar, ranks all symbols by their momentum (3 lookbacks),
    volatility, and volume. Also computes rolling correlation of each symbol
    vs the universe median return, and the z-score of that correlation.

    Args:
        multi_ohlcv: Dict mapping symbol -> OHLCV dict. Must contain at least
            2 symbols with 'close', 'high', 'low', 'volume' arrays of equal length.
        momentum_window_1h: Lookback for short-term momentum rank (default 6).
        momentum_window_4h: Lookback for medium-term momentum rank (default 24).
        momentum_window_24h: Lookback for long-term momentum rank (default 144).
        volatility_window: Window for volatility computation (default 20).
        correlation_window: Window for rolling correlation vs median (default 20).
        zscore_window: Window for correlation z-score (default 20).

    Returns:
        Dict mapping feature name to 2D numpy array of shape (n_symbols, n_bars).
        Rows are in the same order as multi_ohlcv.keys().
        Keys:
          rank_momentum_1h       — rank of short-term momentum [0, 1]
          rank_momentum_4h       — rank of medium-term momentum [0, 1]
          rank_momentum_24h      — rank of long-term momentum [0, 1]
          rank_volatility        — rank of realized volatility [0, 1]
          rank_volume            — rank of volume [0, 1]
          correlation_with_median — rolling correlation vs universe median [-1, 1]
          correlation_zscore     — z-score of correlation_with_median

    Raises:
        ValueError: if fewer than 2 symbols, missing columns, or mismatched lengths.
    """
    n_bars = _validate_multi_symbol_ohlcv(multi_ohlcv)
    symbols = list(multi_ohlcv.keys())
    n_symbols = len(symbols)

    # ------------------------------------------------------------------
    # Build per-symbol feature matrices (n_symbols, n_bars)
    # ------------------------------------------------------------------

    # Momentum at 3 lookbacks
    mom_1h_matrix = np.full((n_symbols, n_bars), np.nan, dtype=np.float64)
    mom_4h_matrix = np.full((n_symbols, n_bars), np.nan, dtype=np.float64)
    mom_24h_matrix = np.full((n_symbols, n_bars), np.nan, dtype=np.float64)

    # Realized volatility (annualized, using rolling std of log returns)
    vol_matrix = np.full((n_symbols, n_bars), np.nan, dtype=np.float64)

    # Volume (raw volume, used for cross-sectional rank)
    vol_raw_matrix = np.full((n_symbols, n_bars), np.nan, dtype=np.float64)

    # Log returns (for correlation features)
    ret_matrix = np.full((n_symbols, n_bars), np.nan, dtype=np.float64)

    for s_idx, sym in enumerate(symbols):
        ohlcv = multi_ohlcv[sym]
        close = ohlcv["close"].astype(np.float64)
        volume = ohlcv["volume"].astype(np.float64)

        # Momentum at each lookback using ROC
        mom_1h_matrix[s_idx, :] = _compute_roc(close, momentum_window_1h)
        mom_4h_matrix[s_idx, :] = _compute_roc(close, momentum_window_4h)
        mom_24h_matrix[s_idx, :] = _compute_roc(close, momentum_window_24h)

        # Log returns
        log_ret = _compute_log_return_1(close)
        ret_matrix[s_idx, :] = log_ret

        # Realized volatility: rolling std of log returns * sqrt(periods)
        if n_bars > volatility_window:
            for t in range(volatility_window - 1, n_bars):
                seg = log_ret[max(0, t - volatility_window + 1) : t + 1]
                seg_clean = seg[~np.isnan(seg)]
                if len(seg_clean) >= 2:
                    vol_matrix[s_idx, t] = np.std(seg_clean, ddof=1)

        # Raw volume (value for ranking)
        vol_raw_matrix[s_idx, :] = volume

    # ------------------------------------------------------------------
    # 1-5: Cross-sectional rank features
    # ------------------------------------------------------------------

    rank_mom_1h = _cross_sectional_rank(mom_1h_matrix)
    rank_mom_4h = _cross_sectional_rank(mom_4h_matrix)
    rank_mom_24h = _cross_sectional_rank(mom_24h_matrix)
    rank_vol = _cross_sectional_rank(vol_matrix)
    rank_volume = _cross_sectional_rank(vol_raw_matrix)

    result: Dict[str, np.ndarray] = {
        "rank_momentum_1h": rank_mom_1h,
        "rank_momentum_4h": rank_mom_4h,
        "rank_momentum_24h": rank_mom_24h,
        "rank_volatility": rank_vol,
        "rank_volume": rank_volume,
    }

    # ------------------------------------------------------------------
    # 6-7: Inter-symbol correlation features
    # ------------------------------------------------------------------

    # Compute universe median return at each bar
    # First-bar all-NaN columns are expected (log_returns[0] is always NaN).
    # np.nanmedian raises RuntimeWarning on all-NaN slices — suppress expected.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="All-NaN slice encountered")
        median_returns = np.nanmedian(ret_matrix, axis=0)  # shape (n_bars,)

    # Compute rolling correlation of each symbol vs median return
    corr_matrix = np.full((n_symbols, n_bars), np.nan, dtype=np.float64)
    for s_idx in range(n_symbols):
        corr_matrix[s_idx, :] = _rolling_correlation_vs_series(
            ret_matrix[s_idx, :], median_returns, correlation_window
        )

    result["correlation_with_median"] = corr_matrix

    # Z-score of the correlation values
    zscore_matrix = np.full((n_symbols, n_bars), np.nan, dtype=np.float64)
    for s_idx in range(n_symbols):
        zscore_matrix[s_idx, :] = _rolling_zscore(
            corr_matrix[s_idx, :], zscore_window
        )

    result["correlation_zscore"] = zscore_matrix

    return result
