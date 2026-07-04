"""Deterministic alpha factor functions.

Each function takes aligned panel data (dict of column → DataFrame[timestamps × symbols])
and returns a DataFrame of raw factor scores (timestamps × symbols).

All functions are CAUSAL: factor[t] uses data only up to and including t.
No lookahead. No future data.

Factor score direction conventions:
- MOMENTUM: high score = long bias (buy strength)
- REVERSAL: high score = long bias (buy weakness, sell strength)
- BREAKOUT: high score = long bias (new highs)
- BREAKDOWN: low/negative score = short bias (new lows)
- COMPRESSION: direction-agnostic, mark as such
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _safe_divide(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """Element-wise divide with safe zero handling."""
    return a.div(b.replace(0, np.nan))


def _rolling_return(close: pd.DataFrame, periods: int) -> pd.DataFrame:
    """Causal rolling return: close[t] / close[t-periods] - 1."""
    return close / close.shift(periods) - 1.0


def _zscore_cross_sectional(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional z-score: (x - mean) / std across symbols at each timestamp."""
    mu = df.mean(axis=1)
    sigma = df.std(axis=1)
    sigma = sigma.replace(0, np.nan)
    return df.sub(mu, axis=0).div(sigma, axis=0)


def _rank_cross_sectional(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional rank: percentile rank across symbols at each timestamp."""
    return df.rank(axis=1, pct=True)


# ── MOMENTUM FACTORS ──────────────────────────────────────────────

def ret_1h_rank(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """1-hour return rank — cross-sectional percentile rank of 1h return."""
    close = panels["close"]
    ret = _rolling_return(close, 1)
    return _rank_cross_sectional(ret)


def ret_4h_rank(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """4-hour return rank — cross-sectional percentile rank of 4h return (4 × 1h bars)."""
    close = panels["close"]
    ret = _rolling_return(close, 4)
    return _rank_cross_sectional(ret)


def ret_12h_rank(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """12-hour return rank — cross-sectional percentile rank of 12h return."""
    close = panels["close"]
    ret = _rolling_return(close, 12)
    return _rank_cross_sectional(ret)


def ret_24h_rank(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """24-hour return rank — cross-sectional percentile rank of 24h return."""
    close = panels["close"]
    ret = _rolling_return(close, 24)
    return _rank_cross_sectional(ret)


# ── REVERSAL FACTORS ──────────────────────────────────────────────

def reversal_1h_zscore(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """1-hour reversal z-score — INVERTED so high score = buy weakness."""
    close = panels["close"]
    ret = _rolling_return(close, 1)
    # Invert: buy when return is negative (reversal)
    return -_zscore_cross_sectional(ret)


def reversal_4h_zscore(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """4-hour reversal z-score — INVERTED so high score = buy weakness."""
    close = panels["close"]
    ret = _rolling_return(close, 4)
    return -_zscore_cross_sectional(ret)


# ── VOLUME / VOLATILITY FACTORS ───────────────────────────────────

def volume_zscore(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Volume z-score — high volume = high score (momentum/volatility signal)."""
    vol = panels.get("volume")
    if vol is None or vol.empty:
        return pd.DataFrame()
    # Rolling 24h average volume z-scored cross-sectionally
    vol_ma = vol.rolling(24, min_periods=12).mean()
    return _zscore_cross_sectional(vol_ma)


def range_zscore(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Range (high-low) z-score — high range = high volatility score."""
    high = panels["high"]
    low = panels["low"]
    rng = high - low
    rng_ma = rng.rolling(12, min_periods=6).mean()
    return _zscore_cross_sectional(rng_ma)


# ── BREAKOUT / BREAKDOWN FACTORS ──────────────────────────────────

def breakout_n_high(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """N-period high breakout — how close current price is to N-bar high.
    High score = near/above recent high = long bias.
    N = 24 (24h lookback on 1h bars).
    """
    close = panels["close"]
    high = panels["high"]
    # Rolling 24h high (using high series, not close)
    rolling_high = high.rolling(24, min_periods=12).max()
    # Score: distance from rolling high (0 = at high, negative = below)
    score = (close - rolling_high) / rolling_high.replace(0, np.nan)
    # Normalize: shift so higher = closer to high
    return _zscore_cross_sectional(score) * -1  # invert: being below high = low score


def breakdown_n_low(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """N-period low breakdown — how close current price is to N-low.
    Low/negative score = near/below recent low = short bias.
    N = 24 (24h lookback on 1h bars).
    """
    close = panels["close"]
    low = panels["low"]
    rolling_low = low.rolling(24, min_periods=12).min()
    # Score: distance from rolling low (0 = at low, positive = above)
    score = (close - rolling_low) / rolling_low.replace(0, np.nan)
    return _zscore_cross_sectional(score)


# ── TREND / COMPRESSION FACTORS ───────────────────────────────────

def trend_pullback_ema(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Trend pullback to EMA — buy pullbacks in uptrend.
    Score = (close - EMA_48) / ATR, normalized cross-sectionally.
    High score = price above EMA (trend strength).
    Pullback = price near EMA in uptrend (score near 0 but above).
    We use distance from EMA as the raw signal.
    """
    close = panels["close"]
    high = panels["high"]
    low = panels["low"]

    ema_48 = close.ewm(span=48, min_periods=24, adjust=False).mean()

    # Simple ATR proxy: rolling mean of (high - low)
    atr = (high - low).rolling(12, min_periods=6).mean()
    atr = atr.replace(0, np.nan)

    score = (close - ema_48) / atr
    return _zscore_cross_sectional(score)


def compression_expansion(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Compression/expansion — range contraction followed by expansion.
    Score = ratio of recent range to older range.
    High score = expanding range (volatility breakout).
    Direction-agnostic: measures regime, not direction.
    """
    high = panels["high"]
    low = panels["low"]

    rng = high - low
    # Recent 6h range average vs older 24h range average
    rng_short = rng.rolling(6, min_periods=3).mean()
    rng_long = rng.rolling(24, min_periods=12).mean()
    rng_long = rng_long.replace(0, np.nan)

    score = rng_short / rng_long
    return _zscore_cross_sectional(score)


# ── FACTOR REGISTRY ───────────────────────────────────────────────

FACTOR_REGISTRY: dict[str, tuple[str, callable]] = {
    # name: (direction, function)
    # direction: "long" = high score = long bias
    #            "short" = low score = short bias
    #            "agnostic" = direction unclear
    "ret_1h_rank": ("long", ret_1h_rank),
    "ret_4h_rank": ("long", ret_4h_rank),
    "ret_12h_rank": ("long", ret_12h_rank),
    "ret_24h_rank": ("long", ret_24h_rank),
    "reversal_1h_zscore": ("long", reversal_1h_zscore),
    "reversal_4h_zscore": ("long", reversal_4h_zscore),
    "volume_zscore": ("long", volume_zscore),
    "range_zscore": ("long", range_zscore),
    "breakout_n_high": ("long", breakout_n_high),
    "breakdown_n_low": ("short", breakdown_n_low),
    "trend_pullback_ema": ("long", trend_pullback_ema),
    "compression_expansion": ("agnostic", compression_expansion),
}


def compute_all_factors(
    panels: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """Compute all registered factors.

    Returns:
        Dict mapping factor_name → DataFrame of raw scores (timestamps × symbols).
    """
    results: dict[str, pd.DataFrame] = {}
    for name, (direction, func) in FACTOR_REGISTRY.items():
        try:
            scores = func(panels)
            if scores is not None and not scores.empty:
                results[name] = scores
            else:
                print(f"[factors] WARNING: {name} returned empty")
        except Exception as e:
            print(f"[factors] ERROR: {name} failed: {e}")
    return results
