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


# ══════════════════════════════════════════════════════════════════
# NEW FACTORS — Funding Rate, Volume Climax, BTC-Based
# ══════════════════════════════════════════════════════════════════

# ── FUNDING RATE FACTORS ──────────────────────────────────────────
# These require panels["funding_rate"] — a DataFrame of 8h funding rates
# resampled to 1h (forward-filled within each 8h window).

def funding_extreme_short(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Crowded long detector — high positive funding = crowded longs → SHORT.

    Score = cross-sectional z-score of funding rate.
    High positive funding = extreme long crowding = short signal.
    """
    fr = panels.get("funding_rate")
    if fr is None or fr.empty:
        return pd.DataFrame()
    # Z-score funding rate cross-sectionally (higher = more crowded long)
    return _zscore_cross_sectional(fr)


def funding_extreme_long(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Crowded short detector — extreme negative funding = crowded shorts → LONG.

    Score = INVERTED cross-sectional z-score of funding rate.
    High positive = crowded long (bad for long), so invert: high score = negative funding = long signal.
    """
    fr = panels.get("funding_rate")
    if fr is None or fr.empty:
        return pd.DataFrame()
    return -_zscore_cross_sectional(fr)


def funding_momentum_fade(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Funding momentum fade — funding rising + price up → fade the crowd.

    Score = funding_zscore × (-1) × price_return_sign.
    If funding is rising (crowded long) AND price went up, the crowd is
    overconfident → fade with SHORT (high score = short bias).
    We return the inverted signal so high score = long = buy the fade.
    """
    fr = panels.get("funding_rate")
    close = panels.get("close")
    if fr is None or fr.empty or close is None:
        return pd.DataFrame()

    # Funding momentum: change over last 6 bars (24h on 8h funding = ~3 bars, but
    # we resampled to 1h, so 6 bars ≈ 24h of funding changes)
    fr_delta = fr.diff(6)

    # Price return over same window
    price_ret = _rolling_return(close, 6)

    # Cross-sectional z-score of funding delta
    fr_delta_z = _zscore_cross_sectional(fr_delta)

    # Fade signal: if funding rising (positive delta) AND price up → fade
    # High fr_delta_z + positive price_ret = crowded long = SHORT
    # We invert so high score = long = buy the reversal
    score = -fr_delta_z * price_ret.apply(np.sign)
    return score


# ── VOLUME CLIMAX FACTORS ────────────────────────────────────────

def volume_climax_reversal_short(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Volume climax short — extreme volume + bullish candle → SHORT reversal.

    Detects: volume zscore > 2 AND close > open (bullish) AND long upper wick.
    Score = volume_zscore × candle_body_ratio × (1 if bullish else 0).
    High score = strong bullish climax = short reversal candidate.
    """
    vol = panels.get("volume")
    close = panels.get("close")
    open_ = panels.get("open")
    high = panels.get("high")
    low = panels.get("low")

    if vol is None or close is None or open_ is None:
        return pd.DataFrame()

    # Volume z-score (24h rolling)
    vol_ma = vol.rolling(24, min_periods=12).mean()
    vol_std = vol.rolling(24, min_periods=12).std()
    vol_zscore = (vol - vol_ma) / vol_std.replace(0, np.nan)

    # Candle body direction: bullish = close > open
    is_bullish = (close > open_).astype(float)

    # Body size relative to range
    body = (close - open_).abs()
    rng = (high - low).replace(0, np.nan)
    body_ratio = body / rng

    # Upper wick ratio (long upper wick = selling pressure)
    upper_wick = high - np.maximum(close, open_)
    upper_wick_ratio = upper_wick / rng

    # Climax score: extreme volume + bullish + long upper wick
    # High score = bullish climax = short reversal candidate
    score = vol_zscore * is_bullish * (1 + upper_wick_ratio) * body_ratio
    return _zscore_cross_sectional(score)


def volume_climax_reversal_long(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Volume climax long — extreme volume + bearish candle → LONG reversal.

    Mirror of short: detects capitulation selling.
    Score = volume_zscore × (1 if bearish) × (1 + lower_wick_ratio).
    High score = bearish climax = long reversal candidate.
    """
    vol = panels.get("volume")
    close = panels.get("close")
    open_ = panels.get("open")
    high = panels.get("high")
    low = panels.get("low")

    if vol is None or close is None or open_ is None:
        return pd.DataFrame()

    vol_ma = vol.rolling(24, min_periods=12).mean()
    vol_std = vol.rolling(24, min_periods=12).std()
    vol_zscore = (vol - vol_ma) / vol_std.replace(0, np.nan)

    is_bearish = (close < open_).astype(float)

    body = (close - open_).abs()
    rng = (high - low).replace(0, np.nan)
    body_ratio = body / rng

    lower_wick = np.minimum(close, open_) - low
    lower_wick_ratio = lower_wick / rng

    # Bearish climax: extreme volume + bearish + long lower wick
    score = vol_zscore * is_bearish * (1 + lower_wick_ratio) * body_ratio
    return _zscore_cross_sectional(score)


# ── BTC BENCHMARK FACTORS ────────────────────────────────────────
# These use BTC as the market benchmark and compute relative signals.
# panels["close"]["BTCUSDT"] is the BTC price series.

def _get_btc_regime(panels: dict[str, pd.DataFrame]) -> pd.Series:
    """Compute BTC regime: +1 = uptrend (above EMA_48), -1 = downtrend."""
    btc_close = panels["close"].get("BTCUSDT")
    if btc_close is None:
        return pd.Series(dtype=float)
    ema = btc_close.ewm(span=48, min_periods=24, adjust=False).mean()
    regime = (btc_close > ema).astype(float) * 2 - 1  # +1 or -1
    return regime


def btc_downtrend_breakdown_short(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """BTC downtrend + coin breakdown → SHORT continuation.

    Score = |breakdown_score| × btc_downtrend_regime.
    Only active when BTC is in downtrend. Coins breaking down in a BTC
    downtrend tend to continue lower.
    """
    btc_regime = _get_btc_regime(panels)
    if btc_regime.empty:
        return pd.DataFrame()

    close = panels["close"]
    low = panels["low"]
    rolling_low = low.rolling(24, min_periods=12).min()
    breakdown = (close - rolling_low) / rolling_low.replace(0, np.nan)

    # Multiply by BTC regime (only active in downtrend)
    # breakdown < 0 = below recent low, × regime (-1) = positive score
    score = breakdown.abs().mul(btc_regime.abs(), axis=0).mul(-breakdown.apply(np.sign), axis=0)
    return _zscore_cross_sectional(score)


def btc_uptrend_pullback_long(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """BTC uptrend + coin pullback → LONG.

    Score = pullback_depth × btc_uptrend_regime.
    Coins pulling back in a BTC uptrend tend to bounce.
    """
    btc_regime = _get_btc_regime(panels)
    if btc_regime.empty:
        return pd.DataFrame()

    close = panels["close"]
    ema_24 = close.ewm(span=24, min_periods=12, adjust=False).mean()

    # Pullback depth: how far below EMA (negative = pullback)
    pullback = (close - ema_24) / ema_24.replace(0, np.nan)

    # Only active in BTC uptrend; pullback < 0 = buy opportunity
    # We want: positive score when pullback is negative AND BTC uptrend
    btc_uptrend = btc_regime.clip(lower=0)  # regime ≥ 0
    score = -pullback.mul(btc_uptrend, axis=0)
    return _zscore_cross_sectional(score)


def btc_lead_lag_alt_long(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """BTC moved up, alt hasn't caught up → LONG alt catch-up.

    Score = (BTC return - alt return) × sign(BTC return).
    When BTC rallies and alt lags, alt tends to catch up.
    """
    close = panels["close"]
    btc_close = close.get("BTCUSDT")
    if btc_close is None:
        return pd.DataFrame()

    btc_ret_12h = _rolling_return(btc_close.to_frame("BTCUSDT"), 12)["BTCUSDT"]

    # Alt returns
    alt_ret_12h = _rolling_return(close, 12)

    # Lead-lag: BTC return minus alt return
    # Positive = BTC outperformed = alt lagging = long alt
    # Use alt_ret_12h.sub (DataFrame.sub broadcasts correctly)
    lag = alt_ret_12h.sub(btc_ret_12h, axis=0) * -1  # flip sign: BTC - alt

    # Only positive when BTC went up (otherwise it's a catch-down, not catch-up)
    btc_sign = btc_ret_12h.apply(np.sign).replace(0, np.nan)
    score = lag.mul(btc_sign, axis=0)
    return _zscore_cross_sectional(score)


def btc_lead_lag_alt_short(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """BTC moved down, alt hasn't dropped → SHORT alt catch-down.

    Score = (alt return - BTC return) × sign(-BTC return).
    When BTC drops and alt holds up, alt tends to catch down.
    """
    close = panels["close"]
    btc_close = close.get("BTCUSDT")
    if btc_close is None:
        return pd.DataFrame()

    btc_ret_12h = _rolling_return(btc_close.to_frame("BTCUSDT"), 12)["BTCUSDT"]
    alt_ret_12h = _rolling_return(close, 12)

    # Alt outperformed = alt lagging downside = short alt
    lag = alt_ret_12h.sub(btc_ret_12h, axis=0)

    # Only positive when BTC went down (otherwise it's catch-up, not catch-down)
    neg_btc_sign = (-btc_ret_12h).apply(np.sign).replace(0, np.nan)
    score = lag.mul(neg_btc_sign, axis=0)
    return _zscore_cross_sectional(score)


def compression_breakout_regime(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Compression → expansion with direction from BTC regime.

    Combines compression_expansion signal with BTC trend direction.
    High score = expanding range + BTC uptrend = LONG breakout.
    Low score = expanding range + BTC downtrend = SHORT breakdown.
    """
    btc_regime = _get_btc_regime(panels)
    if btc_regime.empty:
        return pd.DataFrame()

    high = panels["high"]
    low = panels["low"]

    rng = high - low
    rng_short = rng.rolling(6, min_periods=3).mean()
    rng_long = rng.rolling(24, min_periods=12).mean()
    rng_long = rng_long.replace(0, np.nan)

    expansion = rng_short / rng_long  # > 1 = expanding

    # Direction from BTC regime: expansion × regime = directional breakout score
    score = expansion.mul(btc_regime, axis=0)
    return _zscore_cross_sectional(score)


# ── MICROSTRUCTURE FACTORS (candle-derived) ──────────────────────
# Research: Corwin & Schultz (2012) spread proxy is the strongest
# microstructure predictor (0.79 selection probability in
# Microstructure Alpha study, Frontiers in Blockchain 2026).
# These work from candle data alone — no order book needed.

def corwin_schultz_spread_proxy(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Corwin-Schultz bid-ask spread proxy from candle data.

    Estimates the effective spread using only high/low prices across
    two consecutive periods. High spread = high transaction cost =
    market stress / illiquidity.

    Formula (simplified vectorized):
      beta = sum of squared H-L ratios over 2 periods
      gamma = (high_2 - low_2)^2 (single period squared range)
      alpha = sqrt(2*beta) - sqrt(beta)
      spread_proxy = 2*(exp(alpha) - 1) / (1 + exp(alpha))

    High spread proxy → market stressed → potential reversal opportunity.
    Low spread proxy → tight spreads → trend continuation more likely.
    """
    high = panels["high"]
    low = panels["low"]

    # 2-period beta: sum of squared ranges
    h_l_sq = ((high - low) / ((high + low) / 2).replace(0, np.nan)) ** 2
    beta = h_l_sq.rolling(2, min_periods=2).sum()

    # 1-period gamma: squared range of current bar
    gamma = ((high - low) / ((high + low) / 2).replace(0, np.nan)) ** 2

    # Alpha from Corwin-Schultz
    # Clamp to avoid overflow in exp
    alpha_raw = np.sqrt(2.0 * beta.replace(0, np.nan)) - np.sqrt(gamma.replace(0, np.nan))
    alpha = alpha_raw.clip(-5, 5)

    # Spread proxy (0 to 1 scale)
    exp_alpha = np.exp(alpha)
    spread_proxy = 2.0 * (exp_alpha - 1.0) / (1.0 + exp_alpha)

    return _zscore_cross_sectional(spread_proxy)


def spread_contraction_signal(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Spread contraction/expansion signal derived from Corwin-Schultz proxy.

    When spread contracts from high to low, it signals a potential breakout.
    High score = spread recently contracted = breakout imminent.

    Score = (long-term spread average) / (short-term spread average)
    High ratio = recent spread < historical = contraction.
    """
    high = panels["high"]
    low = panels["low"]

    h_l_ratio = (high - low) / ((high + low) / 2).replace(0, np.nan)
    h_l_sq = h_l_ratio ** 2

    beta = h_l_sq.rolling(2, min_periods=2).sum()
    gamma = h_l_sq

    alpha_raw = np.sqrt(2.0 * beta.replace(0, np.nan)) - np.sqrt(gamma.replace(0, np.nan))
    alpha = alpha_raw.clip(-5, 5)
    exp_alpha = np.exp(alpha)
    spread = 2.0 * (exp_alpha - 1.0) / (1.0 + exp_alpha)

    # Contraction ratio: long-term average / short-term average
    spread_ma_long = spread.rolling(48, min_periods=24).mean()  # 48h
    spread_ma_short = spread.rolling(6, min_periods=3).mean()    # 6h

    ratio = spread_ma_long / spread_ma_short.replace(0, np.nan)
    ratio = ratio.clip(0.1, 10)

    # High ratio = contraction (spread narrowing)
    return _zscore_cross_sectional(ratio)


def session_volatility_regime(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Session-based volatility regime detector.

    Uses BTC's ATR percentile to classify volatility:
    - LOW: ATR < 33rd percentile → avoid scalping
    - MEDIUM: 33rd-67th → best risk-adjusted returns
    - HIGH: > 67th percentile → momentum/breakout scalping

    Returns cross-sectional score: positive = favorable vol regime,
    negative = unfavorable (too quiet or too wild).
    """
    close = panels.get("close")
    high = panels.get("high")
    low = panels.get("low")
    if close is None or high is None or low is None:
        return pd.DataFrame()

    # ATR proxy (1-bar true range)
    tr = high - low
    # Rolling 24h average ATR
    atr_ma = tr.rolling(24, min_periods=12).mean()

    # Percentile rank over last 168h (1 week)
    atr_percentile = atr_ma.rolling(168, min_periods=48).rank(pct=True)

    # Score: MEDIUM is best (around 0.5), LOW and HIGH are bad
    # Use inverted parabola centered at 0.5
    score = -4.0 * (atr_percentile - 0.5) ** 2 + 1.0

    return _zscore_cross_sectional(score)


# ── FACTOR REGISTRY ───────────────────────────────────────────────

FACTOR_REGISTRY: dict[str, tuple[str, callable]] = {
    # name: (direction, function)
    # direction: "long" = high score = long bias
    #            "short" = low score = short bias
    #            "agnostic" = direction unclear

    # ── Original factors (price/volume only) ──
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

    # ── Funding rate factors (new) ──
    "funding_extreme_short": ("short", funding_extreme_short),
    "funding_extreme_long": ("long", funding_extreme_long),
    "funding_momentum_fade": ("long", funding_momentum_fade),

    # ── Volume climax factors (new) ──
    "volume_climax_reversal_short": ("short", volume_climax_reversal_short),
    "volume_climax_reversal_long": ("long", volume_climax_reversal_long),

    # ── BTC benchmark factors (new) ──
    "btc_downtrend_breakdown_short": ("short", btc_downtrend_breakdown_short),
    "btc_uptrend_pullback_long": ("long", btc_uptrend_pullback_long),
    "btc_lead_lag_alt_long": ("long", btc_lead_lag_alt_long),
    "btc_lead_lag_alt_short": ("short", btc_lead_lag_alt_short),
    "compression_breakout_regime": ("long", compression_breakout_regime),

    # ── Microstructure factors (candle-derived, research-backed) ──
    # Corwin-Schultz spread proxy: strongest predictor (0.79 selection prob)
    "corwin_schultz_spread_proxy": ("long", corwin_schultz_spread_proxy),
    # Spread contraction: breakout imminent when spread narrows
    "spread_contraction_signal": ("long", spread_contraction_signal),
    # Session volatility regime: MEDIUM vol = best risk-adjusted returns
    "session_volatility_regime": ("long", session_volatility_regime),
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
