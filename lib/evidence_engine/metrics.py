from __future__ import annotations

import math
from statistics import mean, stdev


def compute_net_expectancy(net_r_values: list[float]) -> float:
    """Compute net expectancy (mean net R per trade).

    An empty list returns 0.0.
    """
    if not net_r_values:
        return 0.0
    return mean(net_r_values)


def compute_net_sharpe(net_r_expectancies: list[float]) -> float:
    """Compute net Sharpe ratio across per-fold expectancies.

    For a single value or zero-variance input returns 0.0.
    """
    if len(net_r_expectancies) < 2:
        return 0.0
    avg = mean(net_r_expectancies)
    sd = stdev(net_r_expectancies)
    if sd == 0.0:
        return 0.0
    # Annualised assuming each expectancy is one fold (not time-normalised here)
    return avg / sd


def compute_net_profit_factor(
    gross_r: list[float],
    costs: list[float],
) -> float:
    """Compute net profit factor: total_gains / total_losses (after costs).

    ``gross_r`` and ``costs`` are aligned per-trade (same length).
    Net R per trade = gross_r[i] - costs[i].

    Returns ``float('inf')`` when there are no net-loss trades.
    Returns ``0.0`` when there are no net-gain trades.
    """
    if not gross_r or not costs:
        return 0.0

    total_gain = 0.0
    total_loss = 0.0
    for gr, c in zip(gross_r, costs):
        net = gr - c
        if net > 0:
            total_gain += net
        else:
            total_loss += abs(net)

    if total_loss == 0.0:
        return float("inf") if total_gain > 0 else 0.0
    return total_gain / total_loss


def compute_cost_decomposition(
    gross_r: float,
    fee_pct: float,
    slippage_pct: float,
    funding_pct: float,
) -> dict:
    """Decompose a single trade's gross R into cost components.

    Returns
    -------
    dict with keys:
        gross_r, fee, slippage, funding, total_cost, net_r
    """
    fee = abs(gross_r) * fee_pct
    slippage = abs(gross_r) * slippage_pct
    funding = abs(gross_r) * funding_pct
    total_cost = fee + slippage + funding
    net_r = gross_r - total_cost
    return {
        "gross_r": round(gross_r, 8),
        "fee": round(fee, 8),
        "slippage": round(slippage, 8),
        "funding": round(funding, 8),
        "total_cost": round(total_cost, 8),
        "net_r": round(net_r, 8),
    }


def compute_max_drawdown_r(net_r_values: list[float]) -> float:
    """Compute maximum drawdown in R units from a sequence of net R values.

    Drawdown is measured from a running peak: the largest cumulative
    decline from a peak to a subsequent trough.

    Returns a positive float (the drawdown magnitude in R).
    Returns 0.0 for empty or always-positive series.
    """
    if not net_r_values:
        return 0.0

    peak = 0.0
    max_dd = 0.0
    running = 0.0

    for val in net_r_values:
        running += val
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd

    return max_dd
