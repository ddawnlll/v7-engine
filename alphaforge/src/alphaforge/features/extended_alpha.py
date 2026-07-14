"""Extended alpha features: volume profile proxy, momentum divergence, MTF alignment."""
import numpy as np
from typing import Dict


def compute_extended_alpha(ohlcv: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    close = ohlcv["close"].astype(np.float64)
    high = ohlcv["high"].astype(np.float64)
    low = ohlcv["low"].astype(np.float64)
    volume = ohlcv["volume"].astype(np.float64)
    n = len(close)
    out = {}

    # Feature 1: Volume Profile Proxy
    hl_range = high - low + 1e-10
    vol_price_ratio = volume / hl_range
    out["vol_price_ratio"] = vol_price_ratio

    # Range percentile (rolling 20-bar)
    range_20 = np.full(n, np.nan)
    for i in range(20, n):
        window = hl_range[i-20:i]
        valid = window[~np.isnan(window)]
        if len(valid) > 0:
            range_20[i] = float(np.sum(valid < hl_range[i])) / len(valid) * 100
    out["range_percentile"] = range_20

    # Volume percentile (rolling 20-bar)
    vol_20 = np.full(n, np.nan)
    for i in range(20, n):
        window = volume[i-20:i]
        valid = window[~np.isnan(window)]
        if len(valid) > 0:
            vol_20[i] = float(np.sum(valid < volume[i])) / len(valid) * 100
    out["volume_percentile"] = vol_20

    # Feature 2: Momentum Divergence
    price_mom_12h = np.zeros(n)
    vol_mom_12h = np.zeros(n)
    vol_median = np.full(n, np.nan)
    for i in range(12, n):
        price_mom_12h[i] = close[i] / close[i-12] - 1 if close[i-12] > 0 else 0
        window_vol = volume[max(0,i-12):i]
        valid_vol = window_vol[~np.isnan(window_vol) & (window_vol > 0)]
        vol_median[i] = np.median(valid_vol) if len(valid_vol) > 0 else 1.0
    vol_mom_12h = np.where(vol_median > 0, volume / vol_median - 1, 0.0)
    divergence = price_mom_12h - vol_mom_12h
    out["price_momentum_12h"] = price_mom_12h
    out["volume_momentum_12h"] = vol_mom_12h
    out["momentum_divergence"] = divergence

    # Feature 3: MTF Alignment
    sma_48 = np.full(n, np.nan)
    sma_192 = np.full(n, np.nan)
    for i in range(48, n):
        sma_48[i] = np.mean(close[i-48:i])
    for i in range(192, n):
        sma_192[i] = np.mean(close[i-192:i])

    trend_4h = np.where(sma_48 > 0, close / sma_48 - 1, 0.0)
    trend_1d = np.where(sma_192 > 0, close / sma_192 - 1, 0.0)
    trend_4h_sign = np.sign(trend_4h)
    trend_1d_sign = np.sign(trend_1d)
    trend_alignment = trend_4h_sign * trend_1d_sign
    out["trend_4h"] = trend_4h
    out["trend_1d"] = trend_1d
    out["trend_alignment"] = trend_alignment

    return out
