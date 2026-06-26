"""
Funding cost estimation for perpetual swap positions.

Pure math — no state, no adapters, no business logic.
Outputs R-normalized funding cost per trading mode, with
mode-specific sensitivity factors derived from holding duration.

Based on simulation/docs/cost_model.md section "Funding Cost Model".

Formula:
    funding_cost_quote = direction_sign * funding_rate * notional * intervals_crossed
    funding_cost_r = funding_cost_quote / (atr * stop_multiplier) * mode_sensitivity

Where:
    intervals_crossed = holding_bars * bar_duration_hours / funding_interval_hours
    direction_sign = +1 for LONG (pays when rate > 0), -1 for SHORT (receives when rate > 0)

Mode sensitivities:
    SWING:             1.0  (full — 120h holding, ~15 funding intervals)
    SCALP:             0.3  (moderate — ~12h holding, 1-2 intervals)
    AGGRESSIVE_SCALP:  0.0  (negligible — ~75min holding, unlikely to cross interval)
"""

from typing import Literal

TradingMode = Literal["SWING", "SCALP", "AGGRESSIVE_SCALP"]
PositionDirection = Literal["LONG", "SHORT"]

# Default funding interval in hours (Binance standard: 8 hours)
_DEFAULT_FUNDING_INTERVAL_HOURS = 8.0

# Mode-specific funding sensitivity multipliers.
# Derived from cost_model.md holding durations and interval counts.
_MODE_FUNDING_SENSITIVITY: dict[str, float] = {
    "SWING": 1.0,
    "SCALP": 0.3,
    "AGGRESSIVE_SCALP": 0.0,
}


def funding_cost_r(
    mode: TradingMode,
    notional: float,
    atr: float,
    stop_multiplier: float,
    funding_rate: float,
    position_direction: PositionDirection,
    holding_bars: int,
    bar_duration_hours: float,
    funding_interval_hours: float = _DEFAULT_FUNDING_INTERVAL_HOURS,
) -> float:
    """Compute funding cost in R-multiples for a perpetual position.

    Args:
        mode: Trading mode — 'SWING', 'SCALP', or 'AGGRESSIVE_SCALP'.
        notional: Position size in quote currency.
        atr: Average True Range (price units).
        stop_multiplier: Stop-loss multiplier (1R = atr * stop_multiplier).
        funding_rate: Current funding rate (e.g. 0.0001 = 0.01% per 8h).
        position_direction: 'LONG' or 'SHORT'.
            LONG pays funding when rate > 0 (positive cost).
            SHORT receives funding when rate > 0 (negative cost / rebate).
        holding_bars: Number of bars the position is held.
        bar_duration_hours: Duration of each bar in hours.
        funding_interval_hours: Funding settlement interval (default 8h).

    Returns:
        Funding cost expressed in R-multiples.
        Negative values represent funding rebate (position receives).
        Returns 0.0 if atr <= 0 or stop_multiplier <= 0.

    Examples:
        >>> funding_cost_r("SWING", 10000, 100, 2, 0.0001, "LONG", 30, 4)
        # 15 intervals crossed, long pays: +1 * 0.0001 * 10000 * 15 / 200 = 0.075
        0.075

        >>> funding_cost_r("SCALP", 10000, 100, 2, 0.0001, "SHORT", 12, 1)
        # 1.5 intervals, short receives, 0.3 sensitivity:
        # -1 * 0.0001 * 10000 * 1.5 / 200 * 0.3 = -0.00225
        -0.00225

        >>> funding_cost_r("AGGRESSIVE_SCALP", 10000, 100, 2, 0.0001, "LONG", 5, 0.25)
        # AGGRESSIVE_SCALP sensitivity is 0 → always 0
        0.0
    """
    if atr <= 0 or stop_multiplier <= 0:
        return 0.0

    sensitivity = _MODE_FUNDING_SENSITIVITY.get(mode, 0.0)
    if sensitivity == 0.0:
        return 0.0

    direction_sign = 1.0 if position_direction == "LONG" else -1.0

    # Number of funding intervals crossed during the holding period
    intervals_crossed = (holding_bars * bar_duration_hours) / funding_interval_hours

    funding_cost_quote = direction_sign * funding_rate * notional * intervals_crossed
    funding_cost_quote *= sensitivity

    r_value = atr * stop_multiplier
    return funding_cost_quote / r_value


def funding_sensitivity(mode: TradingMode) -> float:
    """Return the funding sensitivity multiplier for a given mode.

    Args:
        mode: Trading mode — 'SWING', 'SCALP', or 'AGGRESSIVE_SCALP'.

    Returns:
        Sensitivity multiplier (0.0 to 1.0).
        Returns 0.0 for unknown modes.
    """
    return _MODE_FUNDING_SENSITIVITY.get(mode, 0.0)
