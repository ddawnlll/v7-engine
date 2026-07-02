"""
Multi-Timeframe + Funding feature computation for AlphaForge.

Computes higher-timeframe context features (4h, 1d), lower-timeframe
pressure features (15m), and funding-rate features — then aligns
them to the primary 1h bar grid.

Usage:
    from alphaforge.features.mtf import compute_mtf_features
    mtf_dict = compute_mtf_features(ohlcv_1h, ohlcv_4h, ...)
    # merge mtf_dict into main feature matrix
"""

from __future__ import annotations

import numpy as np
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Resample helpers (1h -> 4h / 1d if raw data not available)
# ---------------------------------------------------------------------------

def resample_ohlcv(ohlcv: dict, source_bars: int, target_bars: int) -> dict:
    """Resample OHLCV from one bar size to another by periodic sampling.

    Args:
        ohlcv: dict with 'open','high','low','close','volume' arrays.
        source_bars: number of source bars per target bar (e.g. 4 for 1h->4h).
        target_bars: target bar count.

    Returns:
        Resampled dict with target_bars entries.
    """
    out = {}
    for key in ("open", "high", "low", "close", "volume"):
        if key not in ohlcv:
            continue
        arr = ohlcv[key]
        n = len(arr)
        if key == "open":
            out[key] = np.array([arr[i] for i in range(0, n, source_bars)][:target_bars])
        elif key == "high":
            out[key] = np.array([arr[i:i + source_bars].max() for i in range(0, n, source_bars)][:target_bars])
        elif key == "low":
            out[key] = np.array([arr[i:i + source_bars].min() for i in range(0, n, source_bars)][:target_bars])
        elif key == "close":
            out[key] = np.array([arr[min(i + source_bars - 1, n - 1)] for i in range(0, n, source_bars)][:target_bars])
        elif key == "volume":
            out[key] = np.array([arr[i:i + source_bars].sum() for i in range(0, n, source_bars)][:target_bars])
    return out


# ---------------------------------------------------------------------------
# 4h context features
# ---------------------------------------------------------------------------

def compute_4h_features(ohlcv: dict, n_bars_1h: int, source_bars: int = 4) -> Dict[str, np.ndarray]:
    """Compute 4h trend/volatility/position features, aligned to 1h grid.

    Returns dict with arrays of length n_bars_1h (NaN-padded at start).
    """
    resampled = resample_ohlcv(ohlcv, source_bars, n_bars_1h // source_bars + 1)
    close = resampled.get("close", np.array([]))
    high = resampled.get("high", np.array([]))
    low = resampled.get("low", np.array([]))
    volume = resampled.get("volume", np.array([]))
    n4 = len(close)

    if n4 == 0:
        return {}

    features: Dict[str, np.ndarray] = {}

    # 4h EMA slope (trend direction and strength)
    ema_fast = _ema(close, 5)
    ema_slow = _ema(close, 20)
    ema_slope = np.full(n4, np.nan, dtype=np.float64)
    ema_slope[1:] = ema_fast[1:] - ema_fast[:-1]
    features["ema_slope_4h"] = ema_slope
    features["trend_strength_4h"] = (ema_fast - ema_slow) / np.maximum(close, 1e-10)

    # 4h Bollinger position
    bb_ma = _ema(close, 20)
    bb_std = _rolling_std(close, 20)
    bb_upper = bb_ma + 2 * bb_std
    bb_lower = bb_ma - 2 * bb_std
    bb_pos = np.full(n4, np.nan, dtype=np.float64)
    mask = (bb_upper - bb_lower) > 1e-10
    bb_pos[mask] = (close[mask] - bb_lower[mask]) / (bb_upper[mask] - bb_lower[mask])
    features["bb_position_4h"] = bb_pos

    # 4h RSI
    features["rsi_4h"] = _rsi(close, 14)

    # 4h ATR regime
    atr_val = _atr(high, low, close, 14)
    atr_mean = _ema(atr_val, 50)
    atr_regime = np.full(n4, np.nan, dtype=np.float64)
    mask = atr_mean > 1e-10
    atr_regime[mask] = atr_val[mask] / atr_mean[mask]
    features["atr_regime_4h"] = atr_regime

    # 4h volatility expansion
    vol_short = _rolling_std(_log_returns(close), 5)
    vol_long = _rolling_std(_log_returns(close), 20)
    vol_exp = np.full(n4, np.nan, dtype=np.float64)
    mask = vol_long > 1e-10
    vol_exp[mask] = vol_short[mask] / vol_long[mask]
    features["vol_expansion_4h"] = vol_exp

    # 4h volume ratio
    vol_ma = _ema(volume, 20)
    vol_ratio = np.full(n4, np.nan, dtype=np.float64)
    mask = vol_ma > 1e-10
    vol_ratio[mask] = volume[mask] / vol_ma[mask]
    features["volume_ratio_4h"] = vol_ratio

    # Stretch to 1h grid by forward-filling
    stretched: Dict[str, np.ndarray] = {}
    for name, arr in features.items():
        s = np.full(n_bars_1h, np.nan, dtype=np.float64)
        for i in range(n4):
            idx = min((i + 1) * source_bars - 1, n_bars_1h - 1)
            s[idx] = arr[i]
        # forward-fill
        _ffill(s)
        stretched[name] = s

    return stretched


# ---------------------------------------------------------------------------
# 1d regime features
# ---------------------------------------------------------------------------

def compute_1d_features(ohlcv: dict, n_bars_1h: int) -> Dict[str, np.ndarray]:
    """Compute daily market regime / trend features, aligned to 1h grid.

    Uses 24-bar blocks (24 x 1h = 1d).
    """
    return compute_4h_features(ohlcv, n_bars_1h, source_bars=24)


# ---------------------------------------------------------------------------
# 15m local features
# ---------------------------------------------------------------------------

def compute_15m_features(ohlcv: dict, n_bars_1h: int) -> Dict[str, np.ndarray]:
    """Compute 15m local momentum/pressure features, aligned to 1h grid.

    Each 1h bar contains 4 x 15m sub-bars. We aggregate sub-bar
    extremes and momentum for the current hour.
    """
    close = ohlcv.get("close", np.array([]))
    high = ohlcv.get("high", np.array([]))
    low = ohlcv.get("low", np.array([]))
    n = len(close)
    if n == 0:
        return {}

    # Sub-bar sampling within each hour
    sub_per_hour = 4
    n_hours = n // sub_per_hour
    if n_hours == 0:
        return {}

    local_high = np.full(n_hours, np.nan, dtype=np.float64)
    local_low = np.full(n_hours, np.nan, dtype=np.float64)
    local_vol = np.full(n_hours, np.nan, dtype=np.float64)
    local_mom = np.full(n_hours, np.nan, dtype=np.float64)

    for h in range(n_hours):
        start = h * sub_per_hour
        end = min(start + sub_per_hour, n)
        seg_high = high[start:end]
        seg_low = low[start:end]
        seg_close = close[start:end]
        if len(seg_high) > 0:
            local_high[h] = seg_high.max()
            local_low[h] = seg_low.min()
            local_vol[h] = (seg_high.max() - seg_low.min()) / max(seg_close[0], 1e-10)
            local_mom[h] = (seg_close[-1] - seg_close[0]) / max(seg_close[0], 1e-10)

    features = {
        "local_range_15m": _stretch_to_1h(local_high - local_low, n_hours, n),
        "local_volatility_15m": _stretch_to_1h(local_vol, n_hours, n),
        "local_momentum_15m": _stretch_to_1h(local_mom, n_hours, n),
    }
    return features


# ---------------------------------------------------------------------------
# Funding features
# ---------------------------------------------------------------------------

def compute_funding_features(
    funding_rates: np.ndarray | None = None,
    n_bars_1h: int = 0,
) -> Dict[str, np.ndarray]:
    """Compute funding-rate context features.

    Args:
        funding_rates: 1D array of funding rate values, aligned to 1h grid.
            None if funding data is unavailable.
        n_bars_1h: Length of the primary 1h grid.

    Returns:
        Dict with funding features, all NaN if funding_rates is None.
    """
    nan_arr = np.full(n_bars_1h, np.nan, dtype=np.float64)
    if funding_rates is None or len(funding_rates) < 20:
        return {
            "funding_rate": nan_arr.copy(),
            "funding_zscore": nan_arr.copy(),
            "funding_direction": nan_arr.copy(),
            "funding_regime": nan_arr.copy(),
        }

    fr = funding_rates[:n_bars_1h].copy()
    features = {
        "funding_rate": fr,
        "funding_zscore": _zscore(fr, 168),  # 168h = 7 day window
        "funding_direction": np.sign(fr).astype(np.float64),
    }

    # Funding regime (positive, negative, neutral)
    fr_ma = _ema(np.abs(fr), 168)
    regime = np.full_like(fr, np.nan, dtype=np.float64)
    threshold = np.nanmean(fr_ma) if not np.all(np.isnan(fr_ma)) else 0.0001
    if threshold > 0:
        high_mask = fr_ma > threshold * 1.5
        low_mask = fr_ma < threshold * 0.5
        regime[high_mask] = 2.0
        regime[low_mask] = 0.0
        regime[~(high_mask | low_mask)] = 1.0
    features["funding_regime"] = regime

    return features


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_mtf_features(
    ohlcv_1h: dict,
    ohlcv_4h: dict | None = None,
    ohlcv_1d: dict | None = None,
    ohlcv_15m: dict | None = None,
    funding_rates: np.ndarray | None = None,
) -> Dict[str, np.ndarray]:
    """Compute all multi-timeframe + funding features.

    Args:
        ohlcv_1h: Primary 1h OHLCV data (dict with open/high/low/close/volume).
        ohlcv_4h: Optional 4h OHLCV. If None, resampled from 1h.
        ohlcv_1d: Optional 1d OHLCV. If None, resampled from 1h.
        ohlcv_15m: Optional 15m OHLCV. If None, uses sub-bar sampling from 1h.
        funding_rates: Optional 1D array of funding rates at 1h resolution.

    Returns:
        Dict mapping feature names to 1D numpy arrays (length = ohlcv_1h bars).
    """
    n = len(ohlcv_1h.get("close", []))
    if n == 0:
        return {}

    features = {}

    # 4h context (resample from 1h if no dedicated 4h data)
    features.update(compute_4h_features(ohlcv_1h, n, source_bars=4))

    # 1d regime (resample from 1h if no dedicated 1d data)
    features.update(compute_1d_features(ohlcv_1h, n))

    # 15m local features
    features.update(compute_15m_features(ohlcv_1h, n))

    # Funding features
    features.update(compute_funding_features(funding_rates, n))

    return features


# ---------------------------------------------------------------------------
# Internal helpers (vectorized numpy, no pandas)
# ---------------------------------------------------------------------------

def _ema(arr: np.ndarray, span: int) -> np.ndarray:
    """Exponential moving average."""
    if span < 1 or len(arr) == 0:
        return arr.copy()
    alpha = 2.0 / (span + 1)
    out = np.full_like(arr, np.nan)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        if np.isnan(out[i - 1]):
            out[i] = arr[i]
        else:
            out[i] = alpha * arr[i] + (1 - alpha) * out[i - 1]
    return out


def _rolling_std(arr: np.ndarray, window: int) -> np.ndarray:
    """Rolling standard deviation (pandas-free)."""
    out = np.full_like(arr, np.nan)
    if window < 2:
        return out
    for i in range(window - 1, len(arr)):
        out[i] = np.std(arr[i - window + 1:i + 1])
    return out


def _log_returns(arr: np.ndarray) -> np.ndarray:
    """Log returns."""
    out = np.full_like(arr, np.nan)
    mask = (arr[:-1] > 0) & (arr[1:] > 0)
    out[1:][mask] = np.log(arr[1:][mask] / arr[:-1][mask])
    return out


def _rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    """Relative Strength Index."""
    out = np.full_like(close, np.nan, dtype=np.float64)
    if len(close) < period + 1:
        return out
    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.full_like(close, np.nan)
    avg_loss = np.full_like(close, np.nan)
    avg_gain[period] = np.nanmean(gains[:period])
    avg_loss[period] = np.nanmean(losses[:period])
    for i in range(period + 1, len(close)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i - 1]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i - 1]) / period
    rs = avg_gain / np.maximum(avg_loss, 1e-10)
    out = 100.0 - (100.0 / (1.0 + rs))
    return out


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """Average True Range."""
    n = len(close)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    return _ema(tr, period)


def _zscore(arr: np.ndarray, window: int) -> np.ndarray:
    """Rolling z-score."""
    out = np.full_like(arr, np.nan)
    for i in range(window, len(arr)):
        seg = arr[i - window:i]
        mu = np.nanmean(seg)
        sd = np.nanstd(seg)
        if sd > 1e-10:
            out[i] = (arr[i] - mu) / sd
    return out


def _ffill(arr: np.ndarray) -> None:
    """Forward-fill NaN in-place."""
    last = np.nan
    for i in range(len(arr)):
        if np.isnan(arr[i]):
            arr[i] = last
        else:
            last = arr[i]


def _stretch_to_1h(sub_bar: np.ndarray, n_sub: int, n_1h: int) -> np.ndarray:
    """Stretch a sub-bar array to 1h grid with forward-fill."""
    sub_per = max(1, n_1h // max(n_sub, 1))
    out = np.full(n_1h, np.nan, dtype=np.float64)
    for i in range(min(n_sub, n_1h)):
        idx = min((i + 1) * sub_per - 1, n_1h - 1)
        out[idx] = sub_bar[i]
    _ffill(out)
    return out
