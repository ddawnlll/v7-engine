"""
Exit resolver for simulation engine.

Handles stop/target/time-exit logic for both LONG and SHORT paths.
Same-candle stop-before-target conservative rule applied.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ExitResult:
    """Outcome of exit resolution for one simulated path."""
    exit_reason: str           # ExitReason value
    exit_price: float
    exit_bar_index: int
    hold_duration_bars: int
    realized_r_gross: float
    stop_before_target: bool = False
    target_before_stop: bool = False
    same_candle_ambiguity: bool = False
    mfe: float = 0.0
    mae: float = 0.0
    mfe_r: float = 0.0
    mae_r: float = 0.0
    time_to_mfe: int = 0
    time_to_mae: int = 0


def simulate_path(
    direction: str,        # "LONG" or "SHORT"
    entry_price: float,
    stop_price: float,
    target_price: float,
    candles: list,         # list of Candle objects, index 0 = bar after entry
    max_holding_bars: int,
    entry_risk: float,     # 1R in price terms
) -> ExitResult:
    """Simulate a directional trade path through future candles.

    Conservative rule: if stop and target are both hit in the same candle,
    stop-before-target wins (assumes adverse move executes first).

    Args:
        direction: "LONG" or "SHORT"
        entry_price: Entry price
        stop_price: Stop-loss price
        target_price: Take-profit price
        candles: List of Candle objects representing future path
        max_holding_bars: Maximum bars before time-exit
        entry_risk: 1R value (atr * stop_multiplier) for R-multiple calc

    Returns:
        ExitResult with exit reason, prices, R-multiples, and path metrics
    """
    is_long = direction.upper() == "LONG"
    available_bars = min(len(candles), max_holding_bars)

    # Track path metrics
    mfe = 0.0   # best unrealized gain (price terms)
    mae = 0.0   # worst unrealized loss (price terms)
    time_to_mfe = 0
    time_to_mae = 0

    for i in range(available_bars):
        bar = candles[i]
        bar_high = bar.high
        bar_low = bar.low

        if is_long:
            # Check stop first (conservative: adverse move executes first)
            if bar_low <= stop_price:
                realized_r_gross = (stop_price - entry_price) / entry_risk if entry_risk > 0 else 0.0
                return ExitResult(
                    exit_reason="STOP_HIT",
                    exit_price=stop_price,
                    exit_bar_index=i,
                    hold_duration_bars=i + 1,
                    realized_r_gross=realized_r_gross,
                    stop_before_target=bar_high >= target_price if target_price > 0 else False,
                    same_candle_ambiguity=(bar_low <= stop_price and bar_high >= target_price) if target_price > 0 else False,
                    mfe=mfe, mae=mae,
                    mfe_r=mfe / entry_risk if entry_risk > 0 else 0.0,
                    mae_r=mae / entry_risk if entry_risk > 0 else 0.0,
                    time_to_mfe=time_to_mfe,
                    time_to_mae=time_to_mae,
                )

            # Check target
            if bar_high >= target_price:
                realized_r_gross = (target_price - entry_price) / entry_risk if entry_risk > 0 else 0.0
                return ExitResult(
                    exit_reason="TARGET_HIT",
                    exit_price=target_price,
                    exit_bar_index=i,
                    hold_duration_bars=i + 1,
                    realized_r_gross=realized_r_gross,
                    target_before_stop=bar_low <= stop_price if stop_price > 0 else False,
                    same_candle_ambiguity=(bar_low <= stop_price and bar_high >= target_price),
                    mfe=mfe, mae=mae,
                    mfe_r=mfe / entry_risk if entry_risk > 0 else 0.0,
                    mae_r=mae / entry_risk if entry_risk > 0 else 0.0,
                    time_to_mfe=time_to_mfe,
                    time_to_mae=time_to_mae,
                )

            # Track path metrics (unrealized during bar)
            high_dev = (bar_high - entry_price) / entry_risk if entry_risk > 0 else 0.0
            low_dev = (bar_low - entry_price) / entry_risk if entry_risk > 0 else 0.0
            bar_mfe = bar_high - entry_price
            bar_mae = bar_low - entry_price  # negative if below entry

        else:  # SHORT
            # Check stop first (conservative)
            if bar_high >= stop_price:
                realized_r_gross = (entry_price - stop_price) / entry_risk if entry_risk > 0 else 0.0
                return ExitResult(
                    exit_reason="STOP_HIT",
                    exit_price=stop_price,
                    exit_bar_index=i,
                    hold_duration_bars=i + 1,
                    realized_r_gross=realized_r_gross,
                    stop_before_target=bar_low <= target_price if target_price > 0 else False,
                    same_candle_ambiguity=(bar_high >= stop_price and bar_low <= target_price) if target_price > 0 else False,
                    mfe=mfe, mae=mae,
                    mfe_r=mfe / entry_risk if entry_risk > 0 else 0.0,
                    mae_r=mae / entry_risk if entry_risk > 0 else 0.0,
                    time_to_mfe=time_to_mfe,
                    time_to_mae=time_to_mae,
                )

            # Check target
            if bar_low <= target_price:
                realized_r_gross = (entry_price - target_price) / entry_risk if entry_risk > 0 else 0.0
                return ExitResult(
                    exit_reason="TARGET_HIT",
                    exit_price=target_price,
                    exit_bar_index=i,
                    hold_duration_bars=i + 1,
                    realized_r_gross=realized_r_gross,
                    target_before_stop=bar_high >= stop_price if stop_price > 0 else False,
                    same_candle_ambiguity=(bar_high >= stop_price and bar_low <= target_price),
                    mfe=mfe, mae=mae,
                    mfe_r=mfe / entry_risk if entry_risk > 0 else 0.0,
                    mae_r=mae / entry_risk if entry_risk > 0 else 0.0,
                    time_to_mfe=time_to_mfe,
                    time_to_mae=time_to_mae,
                )

            bar_mfe = entry_price - bar_low   # SHORT profit = price drop
            bar_mae = bar_high - entry_price  # SHORT loss = price rise
            high_dev = (entry_price - bar_low) / entry_risk if entry_risk > 0 else 0.0
            low_dev = (entry_price - bar_high) / entry_risk if entry_risk > 0 else 0.0

        # Update path metrics
        if bar_mfe > mfe:
            mfe = bar_mfe
            time_to_mfe = i
        if bar_mae < mae:
            mae = bar_mae
            time_to_mae = i

    # Time-exit / horizon-end: no stop or target hit
    if available_bars > 0:
        exit_price_bar = candles[available_bars - 1].close
        if is_long:
            realized_r_gross = (exit_price_bar - entry_price) / entry_risk if entry_risk > 0 else 0.0
        else:
            realized_r_gross = (entry_price - exit_price_bar) / entry_risk if entry_risk > 0 else 0.0
    else:
        exit_price_bar = entry_price
        realized_r_gross = 0.0

    return ExitResult(
        exit_reason="TIME_EXIT",
        exit_price=exit_price_bar,
        exit_bar_index=available_bars - 1 if available_bars > 0 else 0,
        hold_duration_bars=available_bars,
        realized_r_gross=realized_r_gross,
        mfe=mfe, mae=mae,
        mfe_r=mfe / entry_risk if entry_risk > 0 else 0.0,
        mae_r=mae / entry_risk if entry_risk > 0 else 0.0,
        time_to_mfe=time_to_mfe,
        time_to_mae=time_to_mae,
    )


def compute_utility(
    realized_r_net: float,
    mae_r: float,
    cost_r: float,
    time_to_mfe: int,
    profile,   # SimulationProfile
) -> float:
    """Mode-weighted composite utility score.

    utility = realized_r_net
              - mae_weight * abs(mae_r)
              - cost_weight * cost_r
              - time_weight * time_to_mfe * 0.1
    """
    w_mae = getattr(profile, 'mae_penalty_weight', 1.0)
    w_cost = getattr(profile, 'cost_penalty_weight', 1.0)
    w_time = getattr(profile, 'time_penalty_weight', 0.3)
    return (
        realized_r_net
        - w_mae * abs(mae_r)
        - w_cost * cost_r
        - w_time * time_to_mfe * 0.1
    )
