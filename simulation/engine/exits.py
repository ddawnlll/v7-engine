"""
Exit resolver for simulation engine.

Handles stop/target/time-exit logic for both LONG and SHORT paths.
Same-candle stop-before-target conservative rule applied.

Vectorized with NumPy for 10-50x speedup on the candle scan loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


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


def _extract_ohlc(candles: list, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Extract high/low arrays from candle list for vectorized processing.

    Args:
        candles: List of Candle objects.
        n: Number of candles to extract (typically ``min(len(candles), max_holding_bars)``).

    Returns:
        (highs, lows) arrays of shape (n,).
    """
    highs = np.empty(n, dtype=float)
    lows = np.empty(n, dtype=float)
    for i in range(n):
        c = candles[i]
        highs[i] = c.high
        lows[i] = c.low
    return highs, lows


def simulate_path_from_arrays(
    direction: str,
    entry_price: float,
    stop_price: float,
    target_price: float,
    highs: np.ndarray,
    lows: np.ndarray,
    max_holding_bars: int,
    available_bars: int,
    entry_risk: float,
    close_price: float,
    liquidation_price: Optional[float] = None,
    # NOTE(#313): liquidation_price is wired as optional API surface for #302.
    # Currently always None — LIQUIDATED cannot fire in production until
    # Futures Position & Margin Model delivers a liquidation price.
    # When #302 lands, pass the computed liquidation_price here.
) -> ExitResult:
    """Vectorized path simulation from pre-extracted numpy arrays.

    Same logic as ``simulate_path()`` but accepts pre-extracted high/low
    arrays to avoid redundant candle-list iteration when simulating both
    directions for the same input.

    Args:
        direction: "LONG" or "SHORT"
        entry_price: Entry price
        stop_price: Stop-loss price
        target_price: Take-profit price
        highs: High prices array (length ``available_bars``).
        lows: Low prices array (length ``available_bars``).
        max_holding_bars: Maximum bars before time-exit (for R calc).
        available_bars: Number of bars actually available (>= 0).
        entry_risk: 1R value for R-multiple calc.
        close_price: Close price of last candle (for TIME_EXIT).

    Returns:
        ExitResult with exit reason, prices, R-multiples, and path metrics.
    """
    is_long = direction.upper() == "LONG"

    if available_bars == 0:
        return ExitResult(
            exit_reason="TIME_EXIT", exit_price=entry_price,
            exit_bar_index=0, hold_duration_bars=0, realized_r_gross=0.0,
            mfe=0.0, mae=0.0, mfe_r=0.0, mae_r=0.0,
            time_to_mfe=0, time_to_mae=0,
        )

    # --- Vectorized stop/target detection ---
    if is_long:
        stop_bars = np.where(lows <= stop_price)[0]
        target_bars = np.where(highs >= target_price)[0]
        liq_bars = np.where(lows <= liquidation_price)[0] if liquidation_price is not None else np.array([], dtype=int)
    else:
        stop_bars = np.where(highs >= stop_price)[0]
        target_bars = np.where(lows <= target_price)[0]
        liq_bars = np.where(highs >= liquidation_price)[0] if liquidation_price is not None else np.array([], dtype=int)

    first_stop = int(stop_bars[0]) if len(stop_bars) > 0 else available_bars
    first_target = int(target_bars[0]) if len(target_bars) > 0 else available_bars
    first_liq = int(liq_bars[0]) if len(liq_bars) > 0 else available_bars

    # Liquidation takes priority over stop/target on same bar (Issue #313)
    if first_liq < available_bars and first_liq <= first_stop:
        exit_idx = first_liq
        if is_long:
            realized_gross = (liquidation_price - entry_price) / entry_risk if entry_risk > 0 else 0.0
        else:
            realized_gross = (entry_price - liquidation_price) / entry_risk if entry_risk > 0 else 0.0
        mfe, mae, mfe_r, mae_r, t_mfe, t_mae = _compute_path_metrics(
            highs[:exit_idx], lows[:exit_idx], entry_price, entry_risk, is_long,
        )
        return ExitResult(
            exit_reason="LIQUIDATED", exit_price=liquidation_price,
            exit_bar_index=exit_idx, hold_duration_bars=exit_idx + 1,
            realized_r_gross=realized_gross,
            mfe=mfe, mae=mae, mfe_r=mfe_r, mae_r=mae_r,
            time_to_mfe=t_mfe, time_to_mae=t_mae,
        )

    # Conservative: stop checked first → wins on same bar
    if first_stop <= first_target and first_stop < available_bars:
        exit_idx = first_stop
        if is_long:
            realized_gross = (stop_price - entry_price) / entry_risk if entry_risk > 0 else 0.0
        else:
            realized_gross = (entry_price - stop_price) / entry_risk if entry_risk > 0 else 0.0

        same_candle = (first_stop == first_target)
        mfe, mae, mfe_r, mae_r, t_mfe, t_mae = _compute_path_metrics(
            highs[:exit_idx], lows[:exit_idx], entry_price, entry_risk, is_long,
        )

        return ExitResult(
            exit_reason="STOP_HIT", exit_price=stop_price,
            exit_bar_index=exit_idx, hold_duration_bars=exit_idx + 1,
            realized_r_gross=realized_gross,
            stop_before_target=(same_candle and target_price > 0),
            same_candle_ambiguity=same_candle,
            mfe=mfe, mae=mae, mfe_r=mfe_r, mae_r=mae_r,
            time_to_mfe=t_mfe, time_to_mae=t_mae,
        )

    if first_target < available_bars:
        exit_idx = first_target
        if is_long:
            realized_gross = (target_price - entry_price) / entry_risk if entry_risk > 0 else 0.0
        else:
            realized_gross = (entry_price - target_price) / entry_risk if entry_risk > 0 else 0.0

        same_candle = (first_target == first_stop)
        mfe, mae, mfe_r, mae_r, t_mfe, t_mae = _compute_path_metrics(
            highs[:exit_idx], lows[:exit_idx], entry_price, entry_risk, is_long,
        )

        return ExitResult(
            exit_reason="TARGET_HIT", exit_price=target_price,
            exit_bar_index=exit_idx, hold_duration_bars=exit_idx + 1,
            realized_r_gross=realized_gross,
            target_before_stop=(same_candle and stop_price > 0),
            same_candle_ambiguity=same_candle,
            mfe=mfe, mae=mae, mfe_r=mfe_r, mae_r=mae_r,
            time_to_mfe=t_mfe, time_to_mae=t_mae,
        )

    # TIME_EXIT
    if is_long:
        realized_gross = (close_price - entry_price) / entry_risk if entry_risk > 0 else 0.0
    else:
        realized_gross = (entry_price - close_price) / entry_risk if entry_risk > 0 else 0.0

    mfe, mae, mfe_r, mae_r, t_mfe, t_mae = _compute_path_metrics(
        highs[:available_bars], lows[:available_bars], entry_price, entry_risk, is_long,
    )

    return ExitResult(
        exit_reason="TIME_EXIT", exit_price=close_price,
        exit_bar_index=available_bars - 1,
        hold_duration_bars=available_bars,
        realized_r_gross=realized_gross,
        mfe=mfe, mae=mae, mfe_r=mfe_r, mae_r=mae_r,
        time_to_mfe=t_mfe, time_to_mae=t_mae,
    )


def _compute_path_metrics(
    highs: np.ndarray,
    lows: np.ndarray,
    entry_price: float,
    entry_risk: float,
    is_long: bool,
) -> tuple[float, float, float, float, int, int]:
    """Compute MFE/MAE from pre-extracted numpy arrays.

    Matches the original bar-by-bar semantics: metrics are computed over
    the bars *before* the exit bar (the exit bar itself does not contribute).

    Args:
        highs: High prices array (pre-exit segment).
        lows: Low prices array (pre-exit segment).
        entry_price: Entry price.
        entry_risk: 1R value (atr * stop_multiplier).
        is_long: True for LONG, False for SHORT.

    Returns:
        (mfe, mae, mfe_r, mae_r, time_to_mfe, time_to_mae)
    """
    n = len(highs)
    if n == 0:
        return 0.0, 0.0, 0.0, 0.0, 0, 0

    if is_long:
        # LONG MFE: best price rise from entry (max of high - entry)
        gains = highs - entry_price
        mfe = float(np.max(gains))
        time_to_mfe = int(np.argmax(gains))

        # LONG MAE: min(low - entry); only < 0 counts (original semantics)
        losses = lows - entry_price
        min_loss = float(np.min(losses))
        if min_loss < 0:
            mae = min_loss
            time_to_mae = int(np.argmin(losses))
        else:
            mae = 0.0
            time_to_mae = 0
    else:
        # SHORT MFE: best price drop from entry (max of entry - low)
        gains = entry_price - lows
        mfe = float(np.max(gains))
        time_to_mfe = int(np.argmax(gains))

        # SHORT MAE: min(high - entry); only < 0 counts (original semantics)
        # When price rises (high > entry), bar_mae > 0, which does NOT
        # update mae (starts at 0). Only price drops below entry give
        # negative bar_mae, which updates mae.
        losses = highs - entry_price
        min_loss = float(np.min(losses))
        if min_loss < 0:
            mae = min_loss
            time_to_mae = int(np.argmin(losses))
        else:
            mae = 0.0
            time_to_mae = 0

    if entry_risk > 0:
        mfe_r = mfe / entry_risk
        mae_r = mae / entry_risk
    else:
        mfe_r = 0.0
        mae_r = 0.0

    return mfe, mae, mfe_r, mae_r, time_to_mfe, time_to_mae


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

    Vectorized implementation using NumPy for ~10-50x speedup over the
    original bar-by-bar Python loop.

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
    available_bars = max(0, min(len(candles), max_holding_bars))

    # --- Edge case: no bars available ---
    if available_bars == 0:
        return ExitResult(
            exit_reason="TIME_EXIT",
            exit_price=entry_price,
            exit_bar_index=0,
            hold_duration_bars=0,
            realized_r_gross=0.0,
            mfe=0.0, mae=0.0,
            mfe_r=0.0, mae_r=0.0,
            time_to_mfe=0, time_to_mae=0,
        )

    # --- Extract OHLC arrays and delegate ---
    highs, lows = _extract_ohlc(candles, available_bars)
    close_price = candles[available_bars - 1].close

    return simulate_path_from_arrays(
        direction, entry_price, stop_price, target_price,
        highs, lows, max_holding_bars, available_bars, entry_risk, close_price,
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
