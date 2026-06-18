"""
Cost model for simulation engine.

Implements the documented net R formula:
  realized_r_net = realized_r_gross - fee_cost_r - slippage_cost_r

Uses lib.costs primitives for fee and slippage estimation.

Funding cost is DEFERRED — explicitly unsupported in this MVP.
"""

from lib.costs.fees import estimate_fee
from lib.costs.slippage import get_slippage


# Conservative defaults — taker fee both sides
DEFAULT_TAKER_FEE_BPS = 4.0   # 0.04%
DEFAULT_MAKER_FEE_BPS = 2.0   # 0.02%
DEFAULT_SLIPPAGE_BPS = 1.0    # 0.01% base slippage


def compute_entry_risk(atr: float, stop_multiplier: float) -> float:
    """1R = atr * stop_multiplier (entry risk in price terms).

    Returns 0.0 if either input is non-positive.
    """
    if atr <= 0 or stop_multiplier <= 0:
        return 0.0
    return atr * stop_multiplier


def fee_cost_r(
    notional: float,
    entry_risk: float,
    taker_fee_bps: float = DEFAULT_TAKER_FEE_BPS,
) -> float:
    """Fee cost in R-multiples for both entry and exit.

    Uses conservative taker assumption: fee applied on entry AND exit.
    """
    if entry_risk <= 0 or notional <= 0:
        return 0.0
    taker_rate = taker_fee_bps / 10000.0
    entry_fee = notional * taker_rate
    exit_fee = notional * taker_rate
    return (entry_fee + exit_fee) / entry_risk


def slippage_cost_r(
    notional: float,
    entry_price: float,
    entry_risk: float,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
    atr: float = 0.0,
    volatility_adjust: bool = True,
) -> float:
    """Slippage cost in R-multiples (entry + exit).

    Conservative: applies slippage on both sides.
    """
    if entry_risk <= 0 or entry_price <= 0:
        return 0.0
    base_rate = slippage_bps / 10000.0
    if volatility_adjust and atr > 0:
        vol_ratio = atr / entry_price
        adj_rate = base_rate * (1.0 + vol_ratio)
    else:
        adj_rate = base_rate
    entry_slippage = notional * adj_rate
    exit_slippage = notional * adj_rate
    return (entry_slippage + exit_slippage) / entry_risk


def total_cost_r(
    notional: float,
    entry_price: float,
    atr: float,
    stop_multiplier: float,
    taker_fee_bps: float = DEFAULT_TAKER_FEE_BPS,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
) -> tuple[float, float, float]:
    """Compute all costs in R terms.

    Returns:
        (fee_cost_r, slippage_cost_r, total_cost_r)
    """
    risk = compute_entry_risk(atr, stop_multiplier)
    fcr = fee_cost_r(notional, risk, taker_fee_bps)
    scr = slippage_cost_r(notional, entry_price, risk, slippage_bps, atr)
    return fcr, scr, fcr + scr
