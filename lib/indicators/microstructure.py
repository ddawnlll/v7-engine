"""
Microstructure-aware indicators.

Amihud (2002) illiquidity and Roll (1984) spread estimator.

Pure math — no state, no adapters, no business logic.
"""

import math
from typing import Sequence


def amihud_illiquidity(
    returns: Sequence[float],
    dollar_volumes: Sequence[float],
    period: int = 20,
) -> list[float]:
    """Amihud (2002) illiquidity measure.

    For each window of ``period`` bars, computes:

        ILLIQ = mean( |r_t| / dollar_volume_t )

    where r_t is the return and dollar_volume_t = price_t * volume_t.

    Higher values indicate lower liquidity (large price moves
    relative to traded volume).

    Args:
        returns: Per-bar return series (e.g. simple or log returns).
            First element may be NaN (price-change undefined).
        dollar_volumes: Per-bar dollar volume (= close * volume).
            Must be > 0 for valid estimates.
        period: Rolling window (default 20).

    Returns:
        List of Amihud ILLIQ values (same length). First ``period-1``
        values are NaN. Returns NaN for windows with no valid bars.
    """
    n = len(returns)
    result: list[float] = [float("nan")] * n

    if n < period:
        return result

    for i in range(period - 1, n):
        sum_ratio = 0.0
        count = 0
        for j in range(i - period + 1, i + 1):
            dv = dollar_volumes[j] if j < len(dollar_volumes) else 0.0
            if (
                not math.isnan(returns[j])
                and dv > 0
            ):
                sum_ratio += abs(returns[j]) / dv
                count += 1

        if count > 0:
            result[i] = sum_ratio / count
        else:
            result[i] = float("nan")

    return result


def roll_spread(
    closes: Sequence[float],
    period: int = 20,
) -> list[float]:
    """Roll (1984) effective bid-ask spread estimator.

    Derived from the autocovariance of price changes under the
    assumption that transaction prices bounce between bid and ask:

        spread = 2 * sqrt( -cov(Δp_t, Δp_{t-1}) )

    when the first-order return autocovariance is negative.
    If it is positive (no bounce signal), returns 0.

    Args:
        closes: Close price sequence.
        period: Rolling window (default 20).

    Returns:
        List of Roll spread estimates in the same units as closes
        (same length). First ``period`` values are NaN (needs
        at least period+2 bars for a 1st-order covariance).
        Returns 0 for windows where autocovariance is >= 0.
    """
    n = len(closes)
    result: list[float] = [float("nan")] * n

    # Need at least period+2 bars: period returns + 1 for lagged cov
    if n < period + 2:
        return result

    # Compute price changes (Δp_t)
    dp: list[float] = [float("nan")] * n
    for i in range(1, n):
        dp[i] = closes[i] - closes[i - 1]

    # For each valid window end
    for i in range(period + 1, n):
        # Window of `period` returns ending at i:
        # dp[i-period+1], ..., dp[i]
        # Their lagged counterparts: dp[i-period], ..., dp[i-1]
        sum_xy = 0.0
        sum_x = 0.0
        sum_y = 0.0
        count = 0

        for j in range(i - period + 1, i + 1):
            x = dp[j - 1]  # lagged return (t-1)
            y = dp[j]      # current return (t)
            if not (math.isnan(x) or math.isnan(y)):
                sum_xy += x * y
                sum_x += x
                sum_y += y
                count += 1

        if count < 2:
            result[i] = float("nan")
            continue

        # Sample covariance: cov(X,Y) = Σxy/n - (Σx/n)(Σy/n)
        cov = (sum_xy / count) - (sum_x / count) * (sum_y / count)

        if cov < 0:
            result[i] = 2.0 * math.sqrt(-cov)
        else:
            result[i] = 0.0

    return result


def dollar_volume(
    closes: Sequence[float],
    volumes: Sequence[float],
) -> list[float]:
    """Compute per-bar dollar (quote-currency) volume.

        dollar_vol_i = close_i * volume_i

    Args:
        closes: Close prices.
        volumes: Base-asset volumes.

    Returns:
        List of dollar volumes (same length). Returns NaN for bars
        where close <= 0.
    """
    n = len(closes)
    result: list[float] = [0.0] * n
    for i in range(n):
        c = closes[i] if i < len(closes) else 0.0
        v = volumes[i] if i < len(volumes) else 0.0
        if c > 0:
            result[i] = c * v
        else:
            result[i] = float("nan")
    return result
