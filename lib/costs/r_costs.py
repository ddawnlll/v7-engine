"""
R-normalized cost functions.

fee_cost_r, slippage_cost_r, total_cost_r normalize raw costs in quote
currency by 1R (atr * stop_multiplier) to express them as R-multiples.

Formula: cost_r = cost_quote / (atr * stop_multiplier)

Pure math — no state, no adapters, no business logic.
Calls existing lib.costs.fees and lib.costs.slippage primitives.
"""

from lib.costs.fees import FeeTier, estimate_fee
from lib.costs.slippage import get_slippage


def fee_cost_r(
    notional: float,
    entry_price: float,
    atr: float,
    stop_multiplier: float,
    tier: FeeTier = "taker",
) -> float:
    """Compute fee cost in R-multiples.

    fee_cost_r = estimate_fee(notional, tier) / (atr * stop_multiplier)
    1R = atr * stop_multiplier

    Args:
        notional: Trade size in quote currency.
        entry_price: Entry price in quote per base unit (unused, API consistency).
        atr: Average True Range (price units).
        stop_multiplier: Stop-loss multiplier (1R = atr * stop_multiplier).
        tier: 'maker' or 'taker' (default 'taker').

    Returns:
        Fee expressed in R-multiples.
        Returns 0.0 if atr <= 0 or stop_multiplier <= 0.
    """
    if atr <= 0 or stop_multiplier <= 0:
        return 0.0

    fee = estimate_fee(notional, tier)
    r_value = atr * stop_multiplier

    return fee / r_value


def slippage_cost_r(
    notional: float,
    entry_price: float,
    atr: float,
    stop_multiplier: float,
    avg_liquidity: float = 0.0,
) -> float:
    """Compute slippage cost in R-multiples.

    slippage_cost_r = get_slippage(notional, avg_liquidity) / (atr * stop_multiplier)

    Args:
        notional: Trade size in quote currency.
        entry_price: Entry price in quote per base unit (unused, API consistency).
        atr: Average True Range (price units).
        stop_multiplier: Stop-loss multiplier (1R = atr * stop_multiplier).
        avg_liquidity: Average liquidity depth (default 0.0).

    Returns:
        Slippage expressed in R-multiples.
        Returns 0.0 if atr <= 0 or stop_multiplier <= 0.
    """
    if atr <= 0 or stop_multiplier <= 0:
        return 0.0

    slippage = get_slippage(notional, avg_liquidity)
    r_value = atr * stop_multiplier

    return slippage / r_value


def total_cost_r(
    notional: float,
    entry_price: float,
    atr: float,
    stop_multiplier: float,
    tier: FeeTier = "taker",
    avg_liquidity: float = 0.0,
) -> float:
    """Compute total cost (fee + slippage) in R-multiples.

    total_cost_r = fee_cost_r + slippage_cost_r

    Args:
        notional: Trade size in quote currency.
        entry_price: Entry price in quote per base unit (unused, API consistency).
        atr: Average True Range (price units).
        stop_multiplier: Stop-loss multiplier (1R = atr * stop_multiplier).
        tier: 'maker' or 'taker' (default 'taker').
        avg_liquidity: Average liquidity depth (default 0.0).

    Returns:
        Total cost expressed in R-multiples.
    """
    return fee_cost_r(notional, entry_price, atr, stop_multiplier, tier) + \
        slippage_cost_r(notional, entry_price, atr, stop_multiplier, avg_liquidity)
