"""Local trend helpers for market and scan routes."""

from __future__ import annotations

from dataclasses import dataclass


def _pct(a: float, b: float) -> float:
    if not b:
        return 0.0
    return (a - b) / abs(b) * 100.0


@dataclass
class TrendFactor:
    name: str
    role: str
    signal: str
    score: float
    reason: str
    used: bool = True
    weight: float = 1.0


def determine_trend(snapshot: dict) -> tuple[str, float, list[TrendFactor]]:
    price = snapshot.get("price")
    ema_9 = snapshot.get("ema_9")
    ema_21 = snapshot.get("ema_21")
    ema_50 = snapshot.get("ema_50")
    ema_200 = snapshot.get("ema_200")

    factors: list[TrendFactor] = []
    bullish_score = 0.0
    total_score = 0.0

    if all(value is not None for value in (ema_9, ema_21, ema_50)):
        total_score += 2.0
        if ema_9 > ema_21 > ema_50:
            bullish_score += 2.0
            factors.append(TrendFactor("EMA Stack", "TREND", "BUY", 1.0, "EMA9 > EMA21 > EMA50", weight=2.0))
        elif ema_9 < ema_21 < ema_50:
            factors.append(TrendFactor("EMA Stack", "TREND", "SELL", -1.0, "EMA9 < EMA21 < EMA50", weight=2.0))
        else:
            total_score -= 1.0
            factors.append(TrendFactor("EMA Stack", "TREND", "NEUTRAL", 0.0, "EMAs mixed"))

    if price is not None and ema_50 is not None:
        total_score += 1.0
        diff = _pct(float(price), float(ema_50))
        if diff > 0.2:
            bullish_score += 1.0
            factors.append(TrendFactor("Price/EMA50", "TREND", "BUY", min(diff / 3.0, 1.0), f"Price {diff:.1f}% above EMA50"))
        elif diff < -0.2:
            factors.append(TrendFactor("Price/EMA50", "TREND", "SELL", max(diff / 3.0, -1.0), f"Price {abs(diff):.1f}% below EMA50"))
        else:
            total_score -= 1.0

    if price is not None and ema_200 is not None:
        total_score += 0.5
        if price > ema_200:
            bullish_score += 0.5
            factors.append(TrendFactor("Price/EMA200", "TREND", "BUY", 0.5, "Above EMA200", weight=0.5))
        else:
            factors.append(TrendFactor("Price/EMA200", "TREND", "SELL", -0.4, "Below EMA200", weight=0.5))

    if total_score <= 0:
        return "MIXED", 50.0, factors

    ratio = bullish_score / total_score
    strength = round(ratio * 100.0, 1)
    if ratio >= 0.67:
        return "BULLISH", strength, factors
    if ratio <= 0.33:
        return "BEARISH", strength, factors
    return "MIXED", strength, factors
