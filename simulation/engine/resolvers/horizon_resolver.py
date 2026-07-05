"""
Horizon resolver — computes stop/target price levels from ATR and profile multipliers.

Extracted from engine.py (Sim T4). Provides deterministic, stateless
calculation of price levels used by the exit simulator.
"""

from __future__ import annotations

from simulation.contracts.models import Candle
from simulation.engine.exits import ExitResult


def compute_stop_target_levels(
    entry_price: float,
    atr: float,
    stop_multiplier: float,
    target_multiplier: float,
) -> tuple[float, float, float, float]:
    """Compute stop-loss and take-profit price levels for both directions.

    Args:
        entry_price: Entry price
        atr: Average true range
        stop_multiplier: ATR multiplier for stop distance
        target_multiplier: ATR multiplier for target distance

    Returns:
        (long_stop, long_target, short_stop, short_target)
    """
    stop_distance = atr * stop_multiplier
    target_distance = atr * target_multiplier

    long_stop = entry_price - stop_distance
    long_target = entry_price + target_distance
    short_stop = entry_price + stop_distance
    short_target = entry_price - target_distance

    return long_stop, long_target, short_stop, short_target


def compute_resolution_status(
    candles: list[Candle],
    max_bars: int,
    exit_result: ExitResult,
) -> tuple[str, str]:
    """Determine resolution status based on candle availability and exit.

    Args:
        candles: Available future candles
        max_bars: Maximum holding bars per profile
        exit_result: Exit result from the long simulation (used for exit_reason)

    Returns:
        (resolution: str, invalidity_reason: str)
    """
    if not candles:
        return "UNRESOLVED", ""
    if len(candles) < max_bars and exit_result.exit_reason == "TIME_EXIT":
        return "COMPLETE", ""
    return "COMPLETE", ""
