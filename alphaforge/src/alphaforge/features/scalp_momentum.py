"""SCALP-specific momentum enhancement features (CUDA-accelerated).

Designed to capture edge that generic returns/momentum features miss
at the 1h timeframe. All features are causal (trailing window only).

Feature list:
  mom_quality         — momentum quality: abs(return) / recent_volatility
  mom_acceleration    — change in momentum: current_return - prior_return
  mom_consistency     — fraction of positive returns in window (0..1)
  mom_range_expansion — current range / median range
  mom_micro_trend     — short-window vs long-window momentum ratio
  mom_volume_surge    — volume / median volume
  mom_divergence      — price vs momentum divergence
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np

# CuPy GPU acceleration (optional — auto-falls back to numpy)
try:
    import cupy as cp

    _HAS_CUPY = True
    def _asnumpy(arr):
        """Convert cupy array to numpy; passthrough for numpy arrays."""
        if _HAS_CUPY:
            return cp.asnumpy(arr)
        return np.asarray(arr)
except ImportError:
    cp = np
    _HAS_CUPY = False
    def _asnumpy(arr):
        return np.asarray(arr)


def _rolling_std_cupy(arr: np.ndarray, window: int, ddof: int = 1) -> np.ndarray:
    """Rolling standard deviation via CuPy sliding_window_view (GPU)."""
    n = len(arr)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result
    # sliding_window_view on full array: shape (n - window + 1, window)
    arr_g = cp.asarray(arr)
    windows = cp.lib.stride_tricks.sliding_window_view(arr_g, window)
    std_g = cp.std(windows, axis=1, ddof=ddof)
    result[window - 1:] = _asnumpy(std_g)
    return result


def _rolling_median_cupy(arr: np.ndarray, window: int) -> np.ndarray:
    """Rolling median via CuPy sliding_window_view (GPU)."""
    n = len(arr)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result
    arr_g = cp.asarray(arr)
    windows = cp.lib.stride_tricks.sliding_window_view(arr_g, window)
    med_g = cp.median(windows, axis=1)
    result[window - 1:] = _asnumpy(med_g)
    return result


def _rolling_mean_cupy(arr: np.ndarray, window: int) -> np.ndarray:
    """Rolling mean (GPU)."""
    n = len(arr)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result
    arr_g = cp.asarray(arr)
    windows = cp.lib.stride_tricks.sliding_window_view(arr_g, window)
    mean_g = cp.mean(windows, axis=1)
    result[window - 1:] = _asnumpy(mean_g)
    return result


def _count_positive_cupy(arr: np.ndarray, window: int) -> np.ndarray:
    """Rolling count of positive values (GPU)."""
    n = len(arr)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return result
    arr_g = cp.asarray(arr)
    windows = cp.lib.stride_tricks.sliding_window_view(arr_g, window)
    count_g = cp.sum(windows > 0, axis=1).astype(cp.float64)
    result[window - 1:] = _asnumpy(count_g)
    return result


def compute_scalp_momentum_group(
    ohlcv_data: Dict[str, np.ndarray],
    mode: str = "SCALP",
    **kwargs,
) -> Dict[str, np.ndarray]:
    """Compute SCALP momentum enhancement features (CUDA-accelerated).

    Args:
        ohlcv_data: Dict with 'close', 'high', 'low', 'volume' arrays.
        mode: Trading mode (uses SCALP-specific window defaults).

    Returns:
        Dict mapping feature name -> np.ndarray (float64).
    """
    close = ohlcv_data.get("close", np.array([]))
    high = ohlcv_data.get("high", np.array([]))
    low = ohlcv_data.get("low", np.array([]))
    volume = ohlcv_data.get("volume", np.array([]))
    n = len(close)

    if n == 0:
        return {}

    close_f = np.asarray(close, dtype=np.float64)
    high_f = np.asarray(high, dtype=np.float64)
    low_f = np.asarray(low, dtype=np.float64)
    vol_f = np.asarray(volume, dtype=np.float64)

    results: Dict[str, np.ndarray] = {}
    N = 12  # SCALP-specific window (max_hold = 12)
    W = 6   # short window

    # Log returns
    log_ret = np.full(n, np.nan, dtype=np.float64)
    log_ret[1:] = np.log(close_f[1:] / close_f[:-1])

    # Rolling volatility (annualized, 12-bar) — GPU accelerated
    vol_12 = _rolling_std_cupy(log_ret, N, ddof=1)

    # 1. Momentum quality: abs(return) / vol
    mom_quality = np.full(n, np.nan, dtype=np.float64)
    mask = slice(N, n)
    v12 = vol_12[mask]
    mom_quality[mask] = np.where(
        np.abs(v12) > 1e-10,
        np.abs(log_ret[mask]) / v12,
        0.0,
    )
    results["mom_quality"] = mom_quality

    # 2. Momentum acceleration (simple diff)
    mom_acceleration = np.full(n, np.nan, dtype=np.float64)
    mom_acceleration[2:] = log_ret[2:] - log_ret[1:-1]
    results["mom_acceleration"] = mom_acceleration

    # 3. Momentum consistency — GPU accelerated
    mom_consistency = _count_positive_cupy(log_ret, N) / N
    results["mom_consistency"] = mom_consistency

    # 4. Range expansion — GPU accelerated
    ranges = high_f - low_f
    range_median_arr = _rolling_median_cupy(ranges, N)
    mom_range_expansion = np.full(n, np.nan, dtype=np.float64)
    rmed = range_median_arr[mask]
    mom_range_expansion[mask] = np.where(
        rmed > 1e-10,
        ranges[mask] / rmed,
        1.0,
    )
    results["mom_range_expansion"] = mom_range_expansion

    # 5. Micro-trend — GPU accelerated (rolling means)
    short_mean = _rolling_mean_cupy(log_ret, W)
    long_mean = _rolling_mean_cupy(log_ret, N)
    results["mom_micro_trend"] = short_mean - long_mean

    # 6. Volume surge — GPU accelerated
    vol_median_arr = _rolling_median_cupy(vol_f, N)
    mom_volume_surge = np.full(n, np.nan, dtype=np.float64)
    vmed = vol_median_arr[mask]
    mom_volume_surge[mask] = np.where(
        vmed > 1e-10,
        vol_f[mask] / vmed,
        1.0,
    )
    results["mom_volume_surge"] = mom_volume_surge

    # 7. Momentum divergence — vectorized with CuPy
    if _HAS_CUPY and n > N:
        close_g = cp.asarray(close_f)
        log_ret_g = cp.asarray(log_ret)
        windows_g = cp.lib.stride_tricks.sliding_window_view(close_g, N)
        peak_g = cp.max(windows_g, axis=1)  # shape (n - N + 1,)
        drawup_g = close_g[N - 1:] / peak_g - 1.0
        recent_log_ret_g = log_ret_g[N - 1:]
        div = cp.where(
            recent_log_ret_g > 0, cp.abs(drawup_g),
            cp.where(recent_log_ret_g < 0, -cp.abs(drawup_g), 0.0),
        )
        mom_div = np.full(n, np.nan, dtype=np.float64)
        mom_div[N - 1:] = _asnumpy(div)
    else:
        # CPU fallback: vectorized rolling maximum + divergence computation
        from numpy.lib.stride_tricks import sliding_window_view
        peaks = np.max(sliding_window_view(close_f, N), axis=1)
        mom_div = np.full(n, np.nan, dtype=np.float64)
        recent_ret = log_ret[N - 1:]
        drawup = close_f[N - 1:] / peaks - 1.0
        mom_div[N - 1:] = np.where(
            recent_ret > 0, np.abs(drawup),
            np.where(recent_ret < 0, -np.abs(drawup), 0.0),
        )
    results["mom_divergence"] = mom_div

    return results
