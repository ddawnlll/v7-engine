"""AlphaForge Lead-Lag Feature Group — cross-sectional multi-symbol features.

Authority: AlphaForge owns feature discovery and specification.
Status: HOLD-LEAD-LAG — implemented, but cannot be wired into the main
pipeline until the cross-sectional data pipeline (P0.9B) exists.

This module computes 3 lead-lag features that require at least 2 symbols:
  tf_alignment          — timeframe volatility alignment between primary and context
  correlation_pairwise  — rolling pairwise correlation over a lookback window
  lead_lag_score        — does the primary symbol lead or lag the context?

Design constraints (consistent with pipeline.py):
- numpy only (no pandas, scipy, ta-lib)
- no network calls, no exchange APIs, no real market data
- all features are causal: feature at bar[t] uses bars [t-lookback+1 .. t]
- NaN fill for insufficient lookback at series start
- deterministic: same input always produces identical output

Cross-sectional contract:
  Every function in this module accepts multi-symbol OHLCV data as a Dict
  mapping symbol identifier to a Dict[str, np.ndarray] of OHLCV arrays
  (same structure as the single-symbol ohlcv_data in pipeline.py).
  All symbols must have the same number of bars.
  Missing symbols or mismatched lengths raise ValueError.

Re-enablement conditions (when P0.9B exists):
  (a) Cross-sectional data pipeline available — delivers aligned multi-symbol OHLCV
  (b) Correlation computation across symbols validated against known benchmarks
  (c) Timeframe alignment logic tested with multi-timeframe fixtures
  (d) lead_lag_score validated against academic lead-lag detection methods
  (e) FEATURE_GROUP_MAP[FeatureGroup.LEAD_LAG] wired into compute_features()
"""

from __future__ import annotations

import logging
from typing import Dict, List

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lead-Lag default window parameters (SWING baseline)
# ---------------------------------------------------------------------------

# Lookback window for rolling correlation and alignment
LL_CORRELATION_WINDOW: int = 20
# Maximum lag offset for lead-lag detection (bars)
LL_MAX_LAG: int = 5
# Volatility window for timeframe alignment
LL_VOLATILITY_WINDOW: int = 20
# Minimum valid observations required in a window
LL_MIN_VALID: int = 5
# Periods per year for annualization (consistent with SWING 4h bars)
LL_PERIODS_PER_YEAR: int = 2190


# ===========================================================================
# Utility: cross-sectional validation
# ===========================================================================


def _validate_multi_symbol_ohlcv(
    multi_ohlcv: Dict[str, Dict[str, np.ndarray]],
) -> int:
    """Validate multi-symbol OHLCV data and return uniform bar count.

    Args:
        multi_ohlcv: Dict mapping symbol -> OHLCV dict.
            Each OHLCV dict must have keys 'open', 'high', 'low', 'close', 'volume'.
            All arrays must be 1D numpy ndarrays of equal length.

    Returns:
        The common number of bars across all symbols.

    Raises:
        ValueError: if fewer than 2 symbols, missing required columns,
            mismatched lengths, or invalid data types.
    """
    if not isinstance(multi_ohlcv, dict) or len(multi_ohlcv) < 2:
        raise ValueError(
            f"Lead-Lag features require at least 2 symbols, got {len(multi_ohlcv) if isinstance(multi_ohlcv, dict) else 0}"
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

        length = len(ohlcv["close"])
        bar_counts.append(length)

        # Check internal consistency per symbol
        lengths = {col: len(ohlcv[col]) for col in required}
        if len(set(lengths.values())) != 1:
            raise ValueError(
                f"Symbol '{symbol}' has inconsistent OHLCV lengths: {lengths}"
            )

    if len(set(bar_counts)) != 1:
        raise ValueError(
            f"All symbols must have the same number of bars. Got lengths: "
            f"{dict(zip(multi_ohlcv.keys(), bar_counts))}"
        )

    n_bars = bar_counts[0]
    if n_bars < 2:
        raise ValueError(f"Need at least 2 bars for lead-lag computation, got {n_bars}")

    return n_bars


def _extract_close_prices(
    multi_ohlcv: Dict[str, Dict[str, np.ndarray]],
) -> Dict[str, np.ndarray]:
    """Extract close prices from multi-symbol OHLCV data.

    Returns dict mapping symbol to close price np.ndarray.
    """
    return {symbol: ohlcv["close"].astype(np.float64) for symbol, ohlcv in multi_ohlcv.items()}


def _compute_log_returns(prices: np.ndarray) -> np.ndarray:
    """Compute 1-bar log returns. NaN at t=0."""
    n = len(prices)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < 2:
        return result
    with np.errstate(divide="ignore", invalid="ignore"):
        result[1:] = np.log(prices[1:] / prices[:-1])
    return result


def _rolling_correlation(
    x: np.ndarray,
    y: np.ndarray,
    window: int,
    min_valid: int = LL_MIN_VALID,
) -> np.ndarray:
    """Compute rolling Pearson correlation between two arrays.

    At each index t, uses x[t-window+1 .. t] and y[t-window+1 .. t].
    Returns NaN for t < window-1 or when fewer than min_valid non-NaN
    pairs exist in the window.

    This is a pure numpy implementation — no pandas, no scipy.

    Args:
        x: First input array.
        y: Second input array, same length as x.
        window: Rolling window size.
        min_valid: Minimum number of non-NaN pairs required (default 5).

    Returns:
        np.ndarray of rolling correlation values, same length as inputs.
        NaN where computation is not possible.
    """
    n = len(x)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window or window < 2:
        return result

    # Use double precision throughout for numerical stability
    x_f = x.astype(np.float64)
    y_f = y.astype(np.float64)

    for i in range(window - 1, n):
        x_seg = x_f[i - window + 1 : i + 1]
        y_seg = y_f[i - window + 1 : i + 1]
        valid = ~np.isnan(x_seg) & ~np.isnan(y_seg)
        n_valid = int(np.sum(valid))
        if n_valid < min_valid:
            result[i] = np.nan
            continue
        x_valid = x_seg[valid]
        y_valid = y_seg[valid]
        # Correlation = covariance / (std_x * std_y)
        dx = x_valid - np.mean(x_valid)
        dy = y_valid - np.mean(y_valid)
        cov = np.sum(dx * dy) / n_valid
        std_x = np.std(x_valid, ddof=0)
        std_y = np.std(y_valid, ddof=0)
        if std_x < 1e-14 or std_y < 1e-14:
            result[i] = np.nan
        else:
            r = cov / (std_x * std_y)
            # Clamp to [-1, 1] to handle floating-point edge cases
            result[i] = float(np.clip(r, -1.0, 1.0))
    return result


def _rolling_mean(arr: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling mean (causal, NaN-safe)."""
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
    """Compute rolling std (causal, NaN-safe)."""
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
# Feature 1: tf_alignment — timeframe volatility alignment score
# ===========================================================================


def compute_tf_alignment(
    multi_ohlcv: Dict[str, Dict[str, np.ndarray]],
    primary_symbol: str,
    context_symbol: str,
    window: int = LL_VOLATILITY_WINDOW,
    periods_per_year: int = LL_PERIODS_PER_YEAR,
) -> np.ndarray:
    """Compute timeframe volatility alignment between primary and context symbols.

    Measures how closely the volatility structure of the primary symbol aligns
    with the context symbol. High values indicate the symbols are in the same
    volatility regime — useful for detecting contextual relevance.

    Algorithm:
      1. Compute log returns for both symbols.
      2. Compute rolling realized volatility (annualized) for both.
      3. Compute the ratio of volatilities: rv_primary / rv_context.
      4. Apply arctan normalization to map [0, +inf) -> [0, 1):
         alignment[t] = 2/pi * arctan(rv_primary[t] / rv_context[t])
         At 1:1 ratio, alignment = 0.5 (neutral).
         Above 1: primary more volatile. Below 1: context more volatile.
      5. Signed alignment: 2*(alignment - 0.5) maps to [-1, 1],
         where +1 means primary dominates volatility and -1 means context dominates.

    Args:
        multi_ohlcv: Dict mapping symbol to OHLCV dict. Must contain
            at least primary_symbol and context_symbol.
        primary_symbol: Symbol identifier for the primary instrument.
        context_symbol: Symbol identifier for the context instrument.
        window: Rolling window for volatility computation (default 20).
        periods_per_year: Annualization factor (default 2190 for SWING 4h).

    Returns:
        np.ndarray of shape (n_bars,) with alignment scores in [-1, 1].
        NaN for t < window.

    Raises:
        ValueError: if symbols are not in multi_ohlcv.
    """
    _validate_multi_symbol_ohlcv(multi_ohlcv)
    n_bars = len(next(iter(multi_ohlcv.values()))["close"])

    if primary_symbol not in multi_ohlcv:
        raise ValueError(f"Primary symbol '{primary_symbol}' not in multi_ohlcv")
    if context_symbol not in multi_ohlcv:
        raise ValueError(f"Context symbol '{context_symbol}' not in multi_ohlcv")
    if primary_symbol == context_symbol:
        raise ValueError("primary_symbol and context_symbol must be different")

    result = np.full(n_bars, np.nan, dtype=np.float64)
    if n_bars < window + 1:
        return result

    # Compute log returns and rolling volatility for both symbols
    primary_close = multi_ohlcv[primary_symbol]["close"].astype(np.float64)
    context_close = multi_ohlcv[context_symbol]["close"].astype(np.float64)

    primary_ret = _compute_log_returns(primary_close)
    context_ret = _compute_log_returns(context_close)

    primary_vol = _rolling_std(primary_ret, window) * np.sqrt(periods_per_year)
    context_vol = _rolling_std(context_ret, window) * np.sqrt(periods_per_year)

    for i in range(window, n_bars):
        pv = primary_vol[i]
        cv = context_vol[i]
        if np.isnan(pv) or np.isnan(cv) or cv < 1e-14:
            result[i] = np.nan
        else:
            ratio = pv / cv
            # atan maps [0, inf) -> [0, pi/2), normalized to [0, 1)
            alignment = (2.0 / np.pi) * np.arctan(ratio)
            # Signed: -1 (context dominates) to +1 (primary dominates)
            result[i] = 2.0 * alignment - 1.0

    return result


# ===========================================================================
# Feature 2: correlation_pairwise — pairwise correlation over lookback
# ===========================================================================


def compute_correlation_pairwise(
    multi_ohlcv: Dict[str, Dict[str, np.ndarray]],
    primary_symbol: str,
    context_symbol: str,
    window: int = LL_CORRELATION_WINDOW,
    use_returns: bool = True,
) -> np.ndarray:
    """Compute rolling pairwise correlation between primary and context symbols.

    Measures the linear relationship between two symbols' price movements
    over a rolling lookback window. This is the fundamental building block
    for lead-lag analysis and basket construction.

    Algorithm:
      1. Extract close prices for both symbols.
      2. If use_returns is True, compute log returns; otherwise use raw prices.
         Returns are preferred because prices are non-stationary.
      3. Compute rolling Pearson correlation over the specified window.

    Args:
        multi_ohlcv: Dict mapping symbol to OHLCV dict.
        primary_symbol: Symbol identifier for the primary instrument.
        context_symbol: Symbol identifier for the context instrument.
        window: Rolling window for correlation (default 20).
        use_returns: If True, correlate log returns (preferred).
            If False, correlate raw close prices.

    Returns:
        np.ndarray of shape (n_bars,) with correlation values in [-1, 1].
        NaN for t < window-1 or when insufficient valid pairs exist.

    Raises:
        ValueError: if symbols are not in multi_ohlcv.
    """
    _validate_multi_symbol_ohlcv(multi_ohlcv)

    if primary_symbol not in multi_ohlcv:
        raise ValueError(f"Primary symbol '{primary_symbol}' not in multi_ohlcv")
    if context_symbol not in multi_ohlcv:
        raise ValueError(f"Context symbol '{context_symbol}' not in multi_ohlcv")
    if primary_symbol == context_symbol:
        raise ValueError("primary_symbol and context_symbol must be different")

    primary_close = multi_ohlcv[primary_symbol]["close"].astype(np.float64)
    context_close = multi_ohlcv[context_symbol]["close"].astype(np.float64)

    if use_returns:
        x = _compute_log_returns(primary_close)
        y = _compute_log_returns(context_close)
    else:
        x = primary_close
        y = context_close

    return _rolling_correlation(x, y, window)


# ===========================================================================
# Feature 3: lead_lag_score — lead/lag detection via cross-correlation
# ===========================================================================


def compute_lead_lag_score(
    multi_ohlcv: Dict[str, Dict[str, np.ndarray]],
    primary_symbol: str,
    context_symbol: str,
    window: int = LL_CORRELATION_WINDOW,
    max_lag: int = LL_MAX_LAG,
) -> np.ndarray:
    """Determine whether the primary symbol leads or lags the context symbol.

    Uses cross-correlation analysis over a rolling window. For each bar t:
      1. Compute rolling window of log returns for both symbols.
      2. For each lag k in [-max_lag, max_lag]:
         corr(t, k) = corr(primary_ret[t-window:t], context_ret[t-window-k:t-k])
      3. Find the lag k* that maximizes |correlation|.
      4. lead_lag_score = sign(k*) * max_abs_corr.

    Interpretation:
      Positive score  → primary LEADS context (context follows primary).
      Negative score  → primary LAGS context (primary follows context).
      Near-zero       → no clear lead-lag relationship.
      |score| near 1  → strong lead-lag relationship.

    Args:
        multi_ohlcv: Dict mapping symbol to OHLCV dict.
        primary_symbol: Symbol identifier for the primary instrument.
        context_symbol: Symbol identifier for the context instrument.
        window: Rolling window for correlation computation (default 20).
        max_lag: Maximum lag offset in bars to test (default 5).

    Returns:
        np.ndarray of shape (n_bars,) with lead-lag scores in [-1, 1].
        NaN for t < window + max_lag - 1.

    Raises:
        ValueError: if symbols are not in multi_ohlcv or max_lag is invalid.
    """
    _validate_multi_symbol_ohlcv(multi_ohlcv)
    n_bars = len(next(iter(multi_ohlcv.values()))["close"])

    if primary_symbol not in multi_ohlcv:
        raise ValueError(f"Primary symbol '{primary_symbol}' not in multi_ohlcv")
    if context_symbol not in multi_ohlcv:
        raise ValueError(f"Context symbol '{context_symbol}' not in multi_ohlcv")
    if primary_symbol == context_symbol:
        raise ValueError("primary_symbol and context_symbol must be different")
    if max_lag < 1:
        raise ValueError(f"max_lag must be at least 1, got {max_lag}")
    if max_lag >= window:
        raise ValueError(
            f"max_lag ({max_lag}) must be less than window ({window}) "
            f"to have sufficient overlap"
        )

    result = np.full(n_bars, np.nan, dtype=np.float64)

    # Minimum bar index needed: window-1 for the reference window, plus max_lag
    # for the offset windows
    min_start = window + max_lag - 1
    if n_bars < min_start:
        return result

    primary_close = multi_ohlcv[primary_symbol]["close"].astype(np.float64)
    context_close = multi_ohlcv[context_symbol]["close"].astype(np.float64)
    primary_ret = _compute_log_returns(primary_close)
    context_ret = _compute_log_returns(context_close)

    for t in range(min_start, n_bars):
        # Reference: primary returns over [t-window+1 .. t]
        primary_seg = primary_ret[t - window + 1 : t + 1]

        best_abs_corr = -1.0
        best_k = 0

        for k in range(-max_lag, max_lag + 1):
            # Context returns shifted by k bars:
            # context_ret[t-k-window+1 .. t-k]
            ctx_start = t - k - window + 1
            ctx_end = t - k + 1

            if ctx_start < 0 or ctx_end > n_bars:
                continue

            context_seg = context_ret[ctx_start:ctx_end]

            if len(context_seg) != len(primary_seg):
                continue

            valid = ~np.isnan(primary_seg) & ~np.isnan(context_seg)
            n_valid = int(np.sum(valid))
            if n_valid < LL_MIN_VALID:
                continue

            p = primary_seg[valid]
            c = context_seg[valid]
            dp = p - np.mean(p)
            dc = c - np.mean(c)
            cov = np.sum(dp * dc) / n_valid
            std_p = np.std(p, ddof=0)
            std_c = np.std(c, ddof=0)
            if std_p < 1e-14 or std_c < 1e-14:
                continue

            corr_val = cov / (std_p * std_c)
            corr_val = float(np.clip(corr_val, -1.0, 1.0))

            if abs(corr_val) > best_abs_corr:
                best_abs_corr = abs(corr_val)
                best_k = k

        if best_abs_corr < 0:
            result[t] = np.nan
        else:
            # Score = sign(lag) * max_abs_correlation
            # Positive k means primary leads context (context follows at t-k)
            # We negate so positive = primary leads
            score = float(np.sign(best_k)) * best_abs_corr
            result[t] = float(np.clip(score, -1.0, 1.0))

    return result


# ===========================================================================
# Group compute function
# ===========================================================================


def compute_lead_lag_group(
    multi_ohlcv: Dict[str, Dict[str, np.ndarray]],
    primary_symbol: str,
    context_symbol: str,
    correlation_window: int = LL_CORRELATION_WINDOW,
    volatility_window: int = LL_VOLATILITY_WINDOW,
    max_lag: int = LL_MAX_LAG,
    periods_per_year: int = LL_PERIODS_PER_YEAR,
) -> Dict[str, np.ndarray]:
    """Compute all Lead-Lag group features for a pair of symbols.

    This is the group-level entry point. It computes:
      tf_alignment          — volatility alignment score [-1, 1]
      correlation_pairwise  — rolling return correlation [-1, 1]
      lead_lag_score        — lead/lag direction and strength [-1, 1]

    All three features are cross-sectional: they require at least 2 symbols.

    Args:
        multi_ohlcv: Dict mapping symbol -> OHLCV dict. Must contain
            at least primary_symbol and context_symbol.
        primary_symbol: Identifier for the primary symbol.
        context_symbol: Identifier for the context/basket symbol.
        correlation_window: Window for correlation and lead-lag (default 20).
        volatility_window: Window for volatility alignment (default 20).
        max_lag: Maximum lag offset for lead-lag detection (default 5).
        periods_per_year: Annualization factor (default 2190 for SWING 4h).

    Returns:
        Dict with keys 'tf_alignment', 'correlation_pairwise', 'lead_lag_score'.
        Each value is a numpy array of shape (n_bars,). NaN at start for
        insufficient lookback.

    Raises:
        ValueError: if symbols are missing, data is invalid, or lengths mismatch.
    """
    # Validate once (all individual functions also validate, but this gives
    # early failure with a clear message)
    _validate_multi_symbol_ohlcv(multi_ohlcv)

    if primary_symbol not in multi_ohlcv:
        raise ValueError(f"Primary symbol '{primary_symbol}' not in multi_ohlcv")
    if context_symbol not in multi_ohlcv:
        raise ValueError(f"Context symbol '{context_symbol}' not in multi_ohlcv")

    return {
        "tf_alignment": compute_tf_alignment(
            multi_ohlcv=multi_ohlcv,
            primary_symbol=primary_symbol,
            context_symbol=context_symbol,
            window=volatility_window,
            periods_per_year=periods_per_year,
        ),
        "correlation_pairwise": compute_correlation_pairwise(
            multi_ohlcv=multi_ohlcv,
            primary_symbol=primary_symbol,
            context_symbol=context_symbol,
            window=correlation_window,
            use_returns=True,
        ),
        "lead_lag_score": compute_lead_lag_score(
            multi_ohlcv=multi_ohlcv,
            primary_symbol=primary_symbol,
            context_symbol=context_symbol,
            window=correlation_window,
            max_lag=max_lag,
        ),
    }
