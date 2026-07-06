"""SCALP-specific momentum enhancement features.

Designed to capture edge that generic returns/momentum features miss
at the 1h timeframe. All features are causal (trailing window only).

Feature list:
  mom_quality        — momentum quality: abs(return) / recent_volatility (high = strong trend)
  mom_acceleration   — change in momentum: current_return - prior_return
  mom_consistency    — fraction of positive returns in window (0..1)
  breakout_momentum  — return after a volatility contraction (bb_width < median)
  vol_adaptive_mom   — momentum lookback = max(3, min(24, 60/vol_percentile))
  range_expansion    — current range / median range (>1 = expanding)
  micro_trend        — short-window (3 bar) vs long-window (12 bar) momentum ratio
  volume_surge       — volume / median volume (>1.5 = surge)
  momentum_divergence — price high vs momentum high misalignment
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np


def _rolling_std(arr: np.ndarray, window: int, ddof: int = 1) -> np.ndarray:
    """Rolling standard deviation (causal, trailing window)."""
    n = len(arr)
    result = np.full(n, np.nan, dtype=np.float64)
    for i in range(window - 1, n):
        result[i] = np.std(arr[i - window + 1:i + 1], ddof=ddof)
    return result


def compute_scalp_momentum_group(
    ohlcv_data: Dict[str, np.ndarray],
    mode: str = "SCALP",
    **kwargs,
) -> Dict[str, np.ndarray]:
    """Compute SCALP momentum enhancement features.

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

    # Rolling volatility (annualized, 12-bar)
    vol_12 = _rolling_std(log_ret, N, ddof=1)
    vol_6 = _rolling_std(log_ret, W, ddof=1)

    # 1. Momentum quality: abs(return) / vol (signal-to-noise ratio for momentum)
    mom_quality = np.full(n, np.nan, dtype=np.float64)
    for i in range(N, n):
        ret = log_ret[i]
        v = vol_12[i]
        mom_quality[i] = abs(ret) / v if v > 1e-10 else 0.0
    results["mom_quality"] = mom_quality
    # 2. Momentum acceleration
    mom_acceleration = np.full(n, np.nan, dtype=np.float64)
    for i in range(2, n):
        mom_acceleration[i] = log_ret[i] - log_ret[i-1]
    results["mom_acceleration"] = mom_acceleration

    # 3. Momentum consistency
    mom_consistency = np.full(n, np.nan, dtype=np.float64)
    for i in range(N, n):
        window = log_ret[i-N+1:i+1]
        mom_consistency[i] = np.sum(window > 0) / N
    results["mom_consistency"] = mom_consistency

    # 4. Range expansion
    ranges = high_f - low_f
    range_median = np.full(n, np.nan, dtype=np.float64)
    for i in range(N, n):
        range_median[i] = np.median(ranges[i-N+1:i+1])
    mom_range_expansion = np.full(n, np.nan, dtype=np.float64)
    for i in range(N, n):
        mom_range_expansion[i] = ranges[i] / range_median[i] if range_median[i] > 1e-10 else 1.0
    results["mom_range_expansion"] = mom_range_expansion

    # 5. Micro-trend
    mom_micro_trend = np.full(n, np.nan, dtype=np.float64)
    for i in range(N, n):
        short_ret = np.mean(log_ret[i-W+1:i+1]) if W > 0 else 0.0
        long_ret = np.mean(log_ret[i-N+1:i+1])
        mom_micro_trend[i] = short_ret - long_ret
    results["mom_micro_trend"] = mom_micro_trend

    # 6. Volume surge
    vol_median = np.full(n, np.nan, dtype=np.float64)
    for i in range(N, n):
        vol_median[i] = np.median(vol_f[i-N+1:i+1])
    mom_volume_surge = np.full(n, np.nan, dtype=np.float64)
    for i in range(N, n):
        mom_volume_surge[i] = vol_f[i] / vol_median[i] if vol_median[i] > 1e-10 else 1.0
    results["mom_volume_surge"] = mom_volume_surge

    # 7. Momentum divergence
    mom_divergence = np.full(n, np.nan, dtype=np.float64)
    for i in range(N, n):
        peak = np.max(close_f[i-N+1:i+1])
        drawup = (close_f[i] / peak - 1.0)
        recent_ret = log_ret[i]
        mom_divergence[i] = abs(drawup) if recent_ret > 0 else -abs(drawup) if recent_ret < 0 else 0.0
    results["mom_divergence"] = mom_divergence

    return results
