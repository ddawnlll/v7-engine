"""
Multi-timeframe feature engine for AlphaForge.

Computes deterministic feature vectors from market data (OHLCV).
All features are derived from canonical state only — no future leakage.

Feature families:
- Primary interval: returns, volatility, technicals, volume, candle geometry
- Context interval: trend, regime, compression, breakout state
- Refinement interval: micro momentum, entry pressure, taker flow
"""

from __future__ import annotations

import math
from typing import Any


# ── Pure math helpers ──────────────────────────────────────────────

def _returns(prices: list[float], periods: list[int]) -> dict[str, float]:
    """Simple returns over specified periods."""
    result = {}
    for p in periods:
        if len(prices) > p:
            result[f"return_{p}"] = round((prices[-1] / prices[-1 - p]) - 1.0, 6)
        else:
            result[f"return_{p}"] = 0.0
    return result


def _log_returns(prices: list[float], period: int = 1) -> float:
    if len(prices) > period and prices[-1 - period] > 0:
        return round(math.log(prices[-1] / prices[-1 - period]), 6)
    return 0.0


def _volatility(prices: list[float], period: int) -> float:
    """Annualized-ish volatility from log returns over period."""
    if len(prices) < period + 1:
        return 0.0
    logs = [math.log(prices[i] / prices[i - 1]) for i in range(-period, 0) if prices[i - 1] > 0]
    if len(logs) < 2:
        return 0.0
    mean = sum(logs) / len(logs)
    variance = sum((x - mean) ** 2 for x in logs) / len(logs)
    return round(math.sqrt(variance), 6)


def _ema(values: list[float], length: int) -> float:
    """Exponential moving average of the last `length` values."""
    if not values:
        return 0.0
    k = 2.0 / (length + 1)
    result = values[0]
    for v in values[1:]:
        result = v * k + result * (1 - k)
    return result


def _sma(values: list[float], length: int) -> float:
    if len(values) < length:
        return values[-1] if values else 0.0
    return sum(values[-length:]) / length


def _rsi(prices: list[float], length: int = 14) -> float:
    if len(prices) < length + 1:
        return 50.0
    gains, losses = 0.0, 0.0
    for i in range(-length, 0):
        change = prices[i] - prices[i - 1]
        if change > 0:
            gains += change
        else:
            losses -= change
    if losses == 0:
        return 100.0 if gains > 0 else 50.0
    rs = gains / losses
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def _bollinger_position(price: float, sma_val: float, std_val: float) -> float:
    """Position within Bollinger Bands: 0=lower, 1=upper, 0.5=mid."""
    if std_val <= 0:
        return 0.5
    return round((price - (sma_val - 2 * std_val)) / (4 * std_val), 4)


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return math.sqrt(variance)


def _zscore(value: float, values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    std = _stddev(values)
    if std == 0:
        return 0.0
    return round((value - mean) / std, 4)


# ── Primary interval features ──────────────────────────────────────

def compute_primary_features(ohlcv: list[dict[str, Any]]) -> dict[str, float]:
    """Compute features from primary interval candles.

    Args:
        ohlcv: List of OHLCV dicts, most recent last.
               Each dict must have: open, high, low, close, volume.

    Returns:
        Dict of feature_name → float value.
    """
    if not ohlcv:
        return {}

    closes = [c["close"] for c in ohlcv]
    highs = [c["high"] for c in ohlcv]
    lows = [c["low"] for c in ohlcv]
    opens = [c["open"] for c in ohlcv]
    volumes = [c["volume"] for c in ohlcv]
    price = closes[-1]

    features = {}

    # Returns
    features.update(_returns(closes, [1, 2, 3, 6, 12, 24]))
    features["log_return_1"] = _log_returns(closes, 1)

    # Volatility
    for p in [6, 12, 24]:
        features[f"volatility_{p}"] = _volatility(closes, p)

    # ATR (simplified: mean true range over 14 bars)
    if len(ohlcv) >= 2:
        tr_values = []
        for i in range(max(1, len(ohlcv) - 14), len(ohlcv)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            tr_values.append(tr)
        features["atr_14"] = round(sum(tr_values) / len(tr_values), 4) if tr_values else 0.0
    else:
        features["atr_14"] = 0.0

    # Candle geometry
    candle_range = price - opens[-1]
    features["body_to_range_ratio"] = round(
        abs(candle_range) / max(highs[-1] - lows[-1], 0.001), 4
    )
    features["upper_wick_ratio"] = round(
        (highs[-1] - max(opens[-1], closes[-1])) / max(highs[-1] - lows[-1], 0.001), 4
    )
    features["lower_wick_ratio"] = round(
        (min(opens[-1], closes[-1]) - lows[-1]) / max(highs[-1] - lows[-1], 0.001), 4
    )

    # RSI
    features["rsi_14"] = _rsi(closes, 14)

    # MA distance (%)
    for ma_len in [20, 50]:
        ma = _sma(closes, ma_len)
        features[f"ma_distance_{ma_len}"] = round(
            (price - ma) / max(ma, 1e-9) * 100.0, 4
        )
    for ema_len in [20]:
        ema = _ema(closes, ema_len)
        features[f"ema_distance_{ema_len}"] = round(
            (price - ema) / max(ema, 1e-9) * 100.0, 4
        )

    # Bollinger (20,2)
    sma20 = _sma(closes, 20)
    if len(closes) >= 20:
        std20 = _stddev(closes[-20:])
    else:
        std20 = _stddev(closes)
    features["bollinger_position"] = _bollinger_position(price, sma20, std20)

    # Volume
    features["volume_zscore_20"] = _zscore(volumes[-1], volumes[-20:]) if len(volumes) >= 20 else 0.0

    return features


# ── Context interval features ──────────────────────────────────────

def compute_context_features(context_ohlcv: list[dict[str, Any]]) -> dict[str, float]:
    """Compute features from higher-timeframe context candles.

    Args:
        context_ohlcv: List of OHLCV dicts for the context interval.

    Returns:
        Dict of context feature_name → float value.
    """
    if not context_ohlcv:
        return {}

    closes = [c["close"] for c in context_ohlcv]
    price = closes[-1]

    features = {}
    features["context_return_3"] = _returns(closes, [3]).get("return_3", 0.0)
    features["context_return_6"] = _returns(closes, [6]).get("return_6", 0.0)

    # Trend strength: how directional the EMAs are
    ema9 = _ema(closes, 9)
    ema21 = _ema(closes, 21)
    ema50 = _ema(closes, 50) if len(closes) >= 50 else _sma(closes, len(closes))
    if ema9 > ema21 > ema50:
        features["context_trend_strength"] = round(
            min((ema9 - ema50) / max(ema50, 1e-9) * 100, 10.0), 4
        )
    elif ema9 < ema21 < ema50:
        features["context_trend_strength"] = round(
            max((ema9 - ema50) / max(ema50, 1e-9) * 100, -10.0), 4
        )
    else:
        features["context_trend_strength"] = 0.0

    features["context_rsi_14"] = _rsi(closes, 14)
    features["context_ma_distance_20"] = round(
        (price - _sma(closes, 20)) / max(_sma(closes, 20), 1e-9) * 100.0, 4
    )

    # Range compression: how tight vs recent range
    if len(closes) >= 20:
        recent_range = max(closes[-5:]) - min(closes[-5:])
        long_range = max(closes[-20:]) - min(closes[-20:])
        features["context_range_compression"] = round(
            recent_range / max(long_range, 1e-9), 4
        )
    else:
        features["context_range_compression"] = 1.0

    return features


# ── Refinement interval features ───────────────────────────────────

def compute_refinement_features(
    refinement_ohlcv: list[dict[str, Any]],
) -> dict[str, float]:
    """Compute features from refinement interval candles (entry-level).

    Args:
        refinement_ohlcv: List of OHLCV dicts for the refinement interval.

    Returns:
        Dict of refinement feature_name → float value.
    """
    if not refinement_ohlcv:
        return {}

    closes = [c["close"] for c in refinement_ohlcv]
    volumes = [c["volume"] for c in refinement_ohlcv]
    price = closes[-1]

    features = {}
    features["refinement_return_1"] = _returns(closes, [1]).get("return_1", 0.0)
    features["refinement_return_3"] = _returns(closes, [3]).get("return_3", 0.0)
    features["refinement_volume_zscore"] = _zscore(volumes[-1], volumes[-20:]) if len(volumes) >= 20 else 0.0
    features["refinement_range_zscore"] = _zscore(
        max(closes[-5:]) - min(closes[-5:]),
        [max(closes[i-5:i]) - min(closes[i-5:i]) for i in range(max(5, len(closes)-20), len(closes)) if i >= 5],
    ) if len(closes) >= 10 else 0.0

    # Micro momentum: last 3-bar price change
    if len(closes) >= 4:
        features["refinement_micro_momentum"] = round(
            (closes[-1] - closes[-4]) / max(closes[-4], 1e-9), 6
        )
    else:
        features["refinement_micro_momentum"] = 0.0

    return features


# ── Combined feature pipeline ──────────────────────────────────────

def compute_all_features(
    primary_ohlcv: list[dict[str, Any]],
    context_ohlcv: list[dict[str, Any]] | None = None,
    refinement_ohlcv: list[dict[str, Any]] | None = None,
    feature_schema_version: str = "feat-1.0.0",
) -> dict[str, Any]:
    """Compute all features across timeframes.

    Args:
        primary_ohlcv: Primary interval candles.
        context_ohlcv: Optional context interval candles.
        refinement_ohlcv: Optional refinement interval candles.
        feature_schema_version: Version string for lineage.

    Returns:
        Dict with 'features' (flat feature dict) and 'metadata'.
    """
    features = {}
    features.update(compute_primary_features(primary_ohlcv))
    if context_ohlcv is not None:
        features.update(compute_context_features(context_ohlcv))
    if refinement_ohlcv is not None:
        features.update(compute_refinement_features(refinement_ohlcv))

    return {
        "features": features,
        "metadata": {
            "feature_schema_version": feature_schema_version,
            "feature_count": len(features),
            "primary_candles": len(primary_ohlcv),
            "context_candles": len(context_ohlcv) if context_ohlcv is not None else 0,
            "refinement_candles": len(refinement_ohlcv) if refinement_ohlcv is not None else 0,
        },
    }
