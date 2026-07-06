"""Premium Index Feature Group — basis from Binance premium index data.

Authority: AlphaForge owns feature discovery and specification.
This module computes premium index (basis) features from real premium
index kline data. Premium index data is expected as an additional column
in the OHLCV data dict.

The premium index measures the difference between the mark price and the
index price of a perpetual swap contract. A positive premium means the
perpetual trades above the index (contango), negative means below
(backwardation).

Features (5):
  - basis:                      Raw basis = premium_close / index_price - 1.
                                Premium close is the close of the premium index
                                kline. If no separate index_price is available,
                                basis defaults to the premium_close itself
                                (which already reflects the premium).
  - basis_ma_N:                 Rolling mean of basis.
  - basis_vol_N:                Rolling std of basis.
  - basis_zscore_N:             Rolling z-score of basis — extremes detected.
  - basis_regime_N:             Basis regime classification:
                                -1 = backwardation (basis < -threshold)
                                 0 = neutral (|basis| <= threshold)
                                 1 = contango (basis > threshold)

Design constraints:
  - numpy only (no pandas, scipy, ta-lib)
  - no network calls, no exchange APIs, no real market data
  - all features are causal: feature at bar[t] uses bars [t-lookback+1 .. t]
  - NaN fill for insufficient lookback at series start
  - deterministic: same input always produces identical output
  - premium_index key is OPTIONAL in ohlcv_data — absent returns NaN arrays

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
SWING_BASIS_WINDOW: int = 10
SCALP_BASIS_WINDOW: int = 12
AGGRESSIVE_SCALP_BASIS_WINDOW: int = 16
DEFAULT_BASIS_WINDOW: int = 10

# Basis regime threshold (in bps): |basis| > 2 bps = regime signal
DEFAULT_BASIS_REGIME_THRESHOLD_BPS: float = 2.0


# ===========================================================================
# Helper: rolling statistics (causal, NaN-safe)
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
# Feature 1: basis — raw basis value
# ===========================================================================


def compute_basis(
    premium_close: np.ndarray,
    index_price: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Compute basis from premium index close and optional index price.

    When index_price is available:
      basis[t] = premium_close[t] / index_price[t] - 1.0

    When index_price is NOT available (None), premium_close is assumed
    to already represent the premium (it is the premium index value
    from Binance premiumIndexKlines, which reports the premium as a
    price-level value in quote currency).

    In the raw price-level case, the value is normalized to basis points
    by dividing by the close price:
      basis[t] = premium_close[t] / close[t] * 10000

    Args:
        premium_close: Premium index close prices (from premium index data).
        index_price: Optional index price array for ratio calculation.

    Returns:
        numpy array of basis values, same length as input.
    """
    n = len(premium_close)
    result = np.full(n, np.nan, dtype=np.float64)

    if n == 0:
        return result

    pc = premium_close.astype(np.float64)

    if index_price is not None and len(index_price) == n:
        ip = index_price.astype(np.float64)
        valid = ~np.isnan(pc) & ~np.isnan(ip) & (ip != 0)
        with np.errstate(divide="ignore", invalid="ignore"):
            result[valid] = (pc[valid] / ip[valid] - 1.0) * 10000  # in bps
    else:
        # premium_close IS the premium value — use directly
        valid = ~np.isnan(pc)
        result[valid] = pc[valid]  # already in bps or raw premium

    return result


# ===========================================================================
# Feature 2: basis_ma_N — rolling mean of basis
# ===========================================================================


def compute_basis_ma(
    basis: np.ndarray,
    window: int = DEFAULT_BASIS_WINDOW,
) -> np.ndarray:
    """Compute rolling mean of basis.

    Smoothed basis signal. Positive values indicate sustained contango
    (perpetual above index). Negative values indicate sustained backwardation.

    Args:
        basis: Basis array (from compute_basis).
        window: Rolling window (default 10).

    Returns:
        numpy array of smoothed basis values, same length as input.
        First `window-1` values are NaN.
    """
    return _rolling_mean(basis, window)


# ===========================================================================
# Feature 3: basis_vol_N — rolling std of basis
# ===========================================================================


def compute_basis_vol(
    basis: np.ndarray,
    window: int = DEFAULT_BASIS_WINDOW,
) -> np.ndarray:
    """Compute rolling standard deviation of basis.

    Captures uncertainty in the basis. High values indicate unstable
    premium/discount conditions, which may signal funding rate divergence
    or market stress.

    Args:
        basis: Basis array (from compute_basis).
        window: Rolling window (default 10).

    Returns:
        numpy array of basis volatility, same length as input.
        First `window-1` values are NaN.
    """
    return _rolling_std(basis, window)


# ===========================================================================
# Feature 4: basis_zscore_N — rolling z-score of basis
# ===========================================================================


@njit
def compute_basis_zscore(
    basis: np.ndarray,
    window: int = DEFAULT_BASIS_WINDOW,
) -> np.ndarray:
    """Compute rolling z-score of basis.

    Detects extreme basis conditions:
      z > 2  : basis unusually positive (extreme contango)
      z < -2 : basis unusually negative (extreme backwardation)

    These extremes may indicate funding rate arbitrage opportunities or
    crowded positioning.

    Args:
        basis: Basis array (from compute_basis).
        window: Rolling window (default 10).

    Returns:
        numpy array of z-scores, same length as input.
        First `window-1` values are NaN.
    """
    n = len(basis)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result

    b_f = basis.astype(np.float64)

    for i in range(window - 1, n):
        seg = b_f[i - window + 1 : i + 1]
        valid = seg[~np.isnan(seg)]
        if len(valid) < 2:
            continue
        mu = np.mean(valid)
        var = np.sum((valid - mu) ** 2) / (len(valid) - 1)
        sigma = np.sqrt(var) if var > 0 else 0.0
        if sigma < 1e-14:
            result[i] = 0.0
        else:
            result[i] = (b_f[i] - mu) / sigma

    return result


# ===========================================================================
# Feature 5: basis_regime_N — basis regime classification
# ===========================================================================


@njit
def compute_basis_regime(
    basis: np.ndarray,
    threshold_bps: float = DEFAULT_BASIS_REGIME_THRESHOLD_BPS,
) -> np.ndarray:
    """Classify basis regime at each bar.

    Regime:
      -1 = backwardation: basis < -threshold (perpetual below index,
           shorts pay premium, bullish for price)
       0 = neutral: |basis| <= threshold (normal conditions)
       1 = contango: basis > threshold (perpetual above index,
           longs pay premium, bearish for price)

    Args:
        basis: Basis array in bps (from compute_basis).
        threshold_bps: Regime threshold in bps (default 2.0).

    Returns:
        numpy array of regime values {-1, 0, 1}, same length as input.
        NaN where basis is NaN.
    """
    n = len(basis)
    result = np.full(n, np.nan, dtype=np.float64)

    for i in range(n):
        if np.isnan(basis[i]):
            continue
        if basis[i] > threshold_bps:
            result[i] = 1.0
        elif basis[i] < -threshold_bps:
            result[i] = -1.0
        else:
            result[i] = 0.0

    return result


# ===========================================================================
# Premium Index Group compute function
# ===========================================================================


def compute_premium_index_group(
    ohlcv_data: dict,
    window: int = DEFAULT_BASIS_WINDOW,
    threshold_bps: float = DEFAULT_BASIS_REGIME_THRESHOLD_BPS,
) -> Dict[str, np.ndarray]:
    """Compute all Premium Index group features (5 total).

    Requires either 'premium_close' key or 'premium_index' key in
    ohlcv_data (real premium index data). Falls back to NaN arrays if
    neither is present.

    Returns dict with keys:
      - basis:                    Raw basis in bps
      - basis_ma_N:               Rolling mean of basis
      - basis_vol_N:              Rolling std of basis
      - basis_zscore_N:           Rolling z-score of basis
      - basis_regime_N:           Basis regime (-1, 0, 1)

    All arrays are same length as input. NaN at start for insufficient
    lookback windows.

    Args:
        ohlcv_data: dict with 'close' (required), and optionally
            'premium_close' or 'premium_index'.
        window: Rolling window for basis features (default 10).
        threshold_bps: Threshold for regime classification (default 2.0).

    Returns:
        Dict mapping feature name to numpy array of shape (n_bars,).
    """
    close = ohlcv_data["close"]
    n = len(close)

    # Extract premium index data (real data takes priority)
    premium_close = ohlcv_data.get("premium_close")
    if premium_close is None:
        premium_idx = ohlcv_data.get("premium_index")
        if premium_idx is not None and isinstance(premium_idx, np.ndarray) and len(premium_idx) == n:
            premium_close = premium_idx
        else:
            premium_close = None

    if premium_close is not None and isinstance(premium_close, np.ndarray) and len(premium_close) == n:
        index_price = ohlcv_data.get("index_price")
        basis = compute_basis(premium_close.astype(np.float64),
                              index_price.astype(np.float64) if (index_price is not None and isinstance(index_price, np.ndarray) and len(index_price) == n) else None)
    else:
        # No premium data available — return NaN arrays
        basis = np.full(n, np.nan, dtype=np.float64)

    basis_ma = compute_basis_ma(basis, window=window)
    basis_vol = compute_basis_vol(basis, window=window)
    basis_zscore = compute_basis_zscore(basis, window=window)
    basis_regime = compute_basis_regime(basis, threshold_bps=threshold_bps)

    return {
        "basis": basis,
        "basis_ma_N": basis_ma,
        "basis_vol_N": basis_vol,
        "basis_zscore_N": basis_zscore,
        "basis_regime_N": basis_regime,
    }
