"""
Combined cost function — fee + slippage + funding.

Sums all three cost components into a single R-normalized total.
Delegates to existing r_costs.total_cost_r (fee + slippage) and
funding_impact.funding_cost_r (funding).

Formula:
    combined_cost_r = total_cost_r + funding_cost_r

Where:
    total_cost_r = fee_cost_r + slippage_cost_r
    funding_cost_r is mode-sensitive per funding_impact.py
"""

from lib.costs.r_costs import total_cost_r as _total_cost_r_base
from lib.costs.funding_impact import funding_cost_r


def combined_cost_r(
    mode: str,
    notional: float,
    entry_price: float,
    atr: float,
    stop_multiplier: float,
    tier: str = "taker",
    avg_liquidity: float = 0.0,
    funding_rate: float = 0.0,
    position_direction: str = "LONG",
    holding_bars: int = 0,
    bar_duration_hours: float = 1.0,
) -> float:
    """Compute combined cost (fee + slippage + funding) in R-multiples.

    Args:
        mode: Trading mode — 'SWING', 'SCALP', or 'AGGRESSIVE_SCALP'.
        notional: Trade size in quote currency.
        entry_price: Entry price in quote per base unit.
        atr: Average True Range (price units).
        stop_multiplier: Stop-loss multiplier (1R = atr * stop_multiplier).
        tier: 'maker' or 'taker' (default 'taker').
        avg_liquidity: Average liquidity depth (default 0.0).
        funding_rate: Current funding rate (default 0.0, e.g. 0.0001 = 0.01%).
        position_direction: 'LONG' or 'SHORT' (default 'LONG').
        holding_bars: Number of bars the position is held (default 0).
        bar_duration_hours: Duration of each bar in hours (default 1.0).

    Returns:
        Combined cost expressed in R-multiples.
        May be negative if funding rebate exceeds fee+slippage costs.

    Examples:
        >>> # SWING with funding: fee+slippage cost + funding cost
        >>> combined_cost_r("SWING", 10000, 10000, 100, 2.0,
        ...     tier="taker", funding_rate=0.0001,
        ...     position_direction="LONG", holding_bars=30, bar_duration_hours=4)
        0.095  # 0.02 (fee) + ~0.001 (slippage w/0 liq) + 0.075 (funding)

        >>> # Zero funding case: same as total_cost_r
        >>> combined_cost_r("SWING", 10000, 10000, 100, 2.0)
        # equals total_cost_r(10000, 10000, 100, 2.0)
    """
    base = _total_cost_r_base(
        notional=notional,
        entry_price=entry_price,
        atr=atr,
        stop_multiplier=stop_multiplier,
        tier=tier,
        avg_liquidity=avg_liquidity,
    )
    funding = funding_cost_r(
        mode=mode,
        notional=notional,
        atr=atr,
        stop_multiplier=stop_multiplier,
        funding_rate=funding_rate,
        position_direction=position_direction,
        holding_bars=holding_bars,
        bar_duration_hours=bar_duration_hours,
    )
    return base + funding
