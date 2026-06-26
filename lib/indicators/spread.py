"""
Bid-ask spread estimators from OHLCV data.

Pure math — no state, no adapters, no business logic.
"""

import math
from typing import Sequence


def hl_spread(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 20,
) -> list[float]:
    """High-low spread proxy as a percentage of close price.

    For each bar: spread_i = (high_i - low_i) / close_i
    Returns the rolling mean of per-bar spread estimates.

    This is a simple microstructure spread proxy that captures
    the intra-bar price range as a fraction of price level.

    Args:
        highs: High prices.
        lows: Low prices.
        closes: Close prices (same length as highs/lows).
        period: Rolling window for smoothing (default 20).

    Returns:
        List of spread estimates (same length). First ``period-1``
        values are NaN. Each value is in [0, +inf) as a fraction.
    """
    n = len(highs)
    result: list[float] = [float("nan")] * n

    if n < period:
        return result

    raw_spreads: list[float] = [0.0] * n
    for i in range(n):
        if closes[i] > 0:
            raw_spreads[i] = (highs[i] - lows[i]) / closes[i]
        else:
            raw_spreads[i] = float("nan")

    for i in range(period - 1, n):
        window = raw_spreads[i - period + 1 : i + 1]
        valid = [v for v in window if not math.isnan(v)]
        if valid:
            result[i] = sum(valid) / len(valid)
        else:
            result[i] = float("nan")

    return result


def parkinson_spread(
    highs: Sequence[float],
    lows: Sequence[float],
    period: int = 20,
) -> list[float]:
    """Parkinson (1980) extreme-value spread proxy.

    Uses the Parkinson range statistic to estimate the effective
    bid-ask spread component embedded in the high-low range:

        spread = sqrt( mean(ln(H/L)^2) / (4 * ln(2)) )

    This is structurally identical to parkinson_vol but interpreted
    as a spread proxy rather than annualised volatility.

    Args:
        highs: High prices.
        lows: Low prices (same length).
        period: Rolling window (default 20).

    Returns:
        List of spread estimates (same length). First ``period-1``
        values are NaN.
    """
    n = len(highs)
    result: list[float] = [float("nan")] * n

    if n < period:
        return result

    c = 1.0 / (4.0 * math.log(2.0))

    for i in range(period - 1, n):
        sum_sq = 0.0
        for j in range(i - period + 1, i + 1):
            if highs[j] > 0 and lows[j] > 0:
                hl_ratio = highs[j] / lows[j]
                sum_sq += math.log(hl_ratio) ** 2
        result[i] = math.sqrt(c * sum_sq / period)

    return result


def hl_spread_bps(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 20,
) -> list[float]:
    """High-low spread proxy in basis points (1 bp = 0.01%).

    Identical to ``hl_spread`` but scaled to basis points:

        spread_bps = hl_spread * 10000

    Args:
        highs: High prices.
        lows: Low prices.
        closes: Close prices (same length).
        period: Rolling window for smoothing (default 20).

    Returns:
        List of spread estimates in basis points (same length).
    """
    raw = hl_spread(highs, lows, closes, period)
    return [
        float("nan") if math.isnan(v) else v * 10000.0
        for v in raw
    ]
