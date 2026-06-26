"""
Microstructure indicators: Amihud illiquidity ratio and Roll spread.

Pure math -- no state, no adapters.
"""

from typing import Sequence
import math


def amihud_illiquidity(
    returns: Sequence[float],
    volumes: Sequence[float],
    period: int = 20,
) -> list[float]:
    """Amihud (2002) illiquidity ratio.

    Measures price impact per unit of volume:

        ILLIQ_i = mean(|r_j| / V_j)  for j in window

    Higher values indicate lower liquidity (larger price impact).

    Args:
        returns: Return series (e.g. log or simple returns).
        volumes: Volume series (same length).
        period: Lookback window (default 20).

    Returns:
        List of illiquidity estimates, same length as inputs.
        First ``period - 1`` values are NaN.
        Entries with zero total-volume over the window are NaN.
    """
    n = len(returns)
    result: list[float] = [float("nan")] * n
    for i in range(period - 1, n):
        total = 0.0
        count = 0
        for j in range(i - period + 1, i + 1):
            r = returns[j]
            v = volumes[j]
            if v > 0 and not math.isnan(r):
                total += abs(r) / v
                count += 1
        if count > 0:
            result[i] = total / count
        # else remains NaN
    return result


def roll_spread_estimator(
    prices: Sequence[float],
    period: int = 20,
) -> list[float]:
    """Roll (1984) bid-ask spread estimator from serial covariance.

    S = 2 * sqrt(max(0, -cov(delta_p_t, delta_p_{t-1})))

    where the covariance is computed over a rolling window of price
    changes.  If the serial covariance is non-negative the spread is
    set to 0 (the estimator's domain requires negative covariance).

    Args:
        prices: Price series (length >= period + 1).
        period: Lookback window for the covariance (default 20).

    Returns:
        List of spread estimates, same length as inputs.
        First ``period`` values are NaN (need period+1 prices to
        compute ``period`` price changes).
    """
    n = len(prices)
    if n < period + 1:
        return [float("nan")] * n

    # Compute price changes (deltas)
    deltas: list[float] = [float("nan")] * n
    for i in range(1, n):
        if not math.isnan(prices[i]) and not math.isnan(prices[i - 1]):
            deltas[i] = prices[i] - prices[i - 1]

    result: list[float] = [float("nan")] * n

    # Need `period` deltas for the first estimate at index `period`
    for i in range(period, n):
        start = i - period + 1
        count = 0
        sum_d = 0.0
        sum_d_lag = 0.0

        # First pass: means (only where both delta[j] and delta[j-1] are valid)
        for j in range(start, i + 1):
            if not math.isnan(deltas[j]) and not math.isnan(deltas[j - 1]):
                sum_d += deltas[j]
                sum_d_lag += deltas[j - 1]
                count += 1

        if count < 2:
            continue

        mean_d = sum_d / count
        mean_d_lag = sum_d_lag / count

        # Second pass: covariance
        cov = 0.0
        valid = 0
        for j in range(start, i + 1):
            if not math.isnan(deltas[j]) and not math.isnan(deltas[j - 1]):
                cov += (deltas[j] - mean_d) * (deltas[j - 1] - mean_d_lag)
                valid += 1

        if valid >= 2:
            cov /= valid
            if cov < 0:
                result[i] = 2.0 * math.sqrt(-cov)
            else:
                result[i] = 0.0

    return result
