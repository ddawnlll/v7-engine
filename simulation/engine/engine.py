"""
Comparative simulation engine.

Evaluates LONG_NOW, SHORT_NOW, and NO_TRADE under the same cost/exit
semantics. This is the core of the /simulation economic truth authority.

Input:  SimulationInput (entry price, ATR, future candles, profile)
Output: SimulationOutput (comparative outcomes, best action, regret)
"""

from __future__ import annotations

import uuid
from typing import Optional

import numpy as np

from simulation.contracts.models import (
    ActionOutcome,
    Candle,
    FuturePath,
    NoTradeOutcome,
    PathMetrics,
    SimulationInput,
    SimulationLineage,
    SimulationOutput,
    SimulationProfile,
)
from simulation.engine.costs import total_cost_r
from simulation.engine.exits import (
    ExitResult,
    _extract_ohlc,
    compute_utility,
    simulate_path,
    simulate_path_from_arrays,
)


def _build_action_outcome(
    action: str,
    exit_result: ExitResult,
    notional: float,
    entry_price: float,
    atr: float,
    profile: SimulationProfile,
) -> ActionOutcome:
    """Build an ActionOutcome from an ExitResult + cost model."""
    fcr, scr, fund_r, tcr = total_cost_r(
        notional=notional,
        entry_price=entry_price,
        atr=atr,
        stop_multiplier=profile.stop_multiplier,
        funding_rate=getattr(profile, "funding_rate", 0.0),
        holding_bars=exit_result.hold_duration_bars,
    )
    realized_r_net = exit_result.realized_r_gross - tcr

    # Path metrics
    pm = PathMetrics(
        mfe=exit_result.mfe,
        mae=exit_result.mae,
        mfe_r=exit_result.mfe_r,
        mae_r=exit_result.mae_r,
        time_to_mfe=exit_result.time_to_mfe,
        time_to_mae=exit_result.time_to_mae,
        path_quality_score=_path_quality(exit_result.mfe_r, exit_result.mae_r),
        path_quality_bucket=_path_quality_bucket(exit_result.mfe_r, exit_result.mae_r),
    )

    utility = compute_utility(realized_r_net, exit_result.mae_r, tcr, exit_result.time_to_mfe, profile)

    return ActionOutcome(
        action=action,
        realized_r_gross=exit_result.realized_r_gross,
        realized_r_net=realized_r_net,
        fee_cost_r=fcr,
        slippage_cost_r=scr,
        funding_cost_r=fund_r,
        total_cost_r=tcr,
        exit_reason=exit_result.exit_reason,
        exit_price=exit_result.exit_price,
        exit_bar_index=exit_result.exit_bar_index,
        hold_duration_bars=exit_result.hold_duration_bars,
        action_utility=utility,
        path_metrics=pm,
        same_candle_ambiguity=exit_result.same_candle_ambiguity,
    )


def _build_no_trade_outcome(
    long_outcome: ActionOutcome,
    short_outcome: ActionOutcome,
    profile: SimulationProfile,
) -> NoTradeOutcome:
    """Derive no-trade quality from directional outcomes."""
    worst_r = min(long_outcome.realized_r_net, short_outcome.realized_r_net)
    best_r = max(long_outcome.realized_r_net, short_outcome.realized_r_net)

    saved_loss_r = max(0.0, -worst_r)
    saved_loss_score = min(1.0, saved_loss_r / max(profile.stop_multiplier, 0.01))

    missed_opportunity_r = best_r if best_r > profile.min_action_edge_r else 0.0
    missed_opportunity_score = min(
        1.0, missed_opportunity_r / max(profile.target_multiplier, 0.01)
    )

    # Classify no-trade quality per no_trade_quality.md:84-101
    # Uses saved_loss_r and missed_opportunity_r (not best_r) for
    # classification, matching the authoritative doc.
    if saved_loss_r == 0.0 and missed_opportunity_r == 0.0:
        # Neither direction lost money, neither produced a clear edge
        quality = "CORRECT_NO_TRADE"
        was_correct = True
    elif saved_loss_r > 0.0 and missed_opportunity_r == 0.0:
        quality = "SAVED_LOSS"
        was_correct = True
    elif missed_opportunity_r > 0.0 and saved_loss_r == 0.0:
        quality = "MISSED_OPPORTUNITY"
        was_correct = False
    elif saved_loss_r > 0.0 and missed_opportunity_r > 0.0:
        # Contradictory: one direction lost, the other won.
        # Use ambiguity margin to decide — close scores → AMBIGUOUS.
        if abs(saved_loss_r - missed_opportunity_r) < profile.ambiguity_margin_r:
            quality = "AMBIGUOUS_NO_TRADE"
            was_correct = False
        elif saved_loss_r >= missed_opportunity_r:
            quality = "SAVED_LOSS"
            was_correct = True
        else:
            quality = "MISSED_OPPORTUNITY"
            was_correct = False
    else:
        quality = "CORRECT_NO_TRADE"
        was_correct = True

    return NoTradeOutcome(
        saved_loss_r=saved_loss_r,
        saved_loss_score=round(saved_loss_score, 4),
        missed_opportunity_r=missed_opportunity_r,
        missed_opportunity_score=round(missed_opportunity_score, 4),
        no_trade_quality=quality,
        was_correct_skip=was_correct,
    )


def _path_quality(mfe_r: float, mae_r: float) -> float:
    """Composite path quality score (0-1)."""
    if mfe_r <= 0:
        return 0.0
    ratio = mfe_r / max(abs(mae_r), 0.001)
    if ratio >= 2.0:
        return 0.85
    elif ratio >= 1.0:
        return 0.60
    elif ratio >= 0.5:
        return 0.40
    else:
        return 0.20


def _path_quality_bucket(mfe_r: float, mae_r: float) -> str:
    score = _path_quality(mfe_r, mae_r)
    if score >= 0.70:
        return "HIGH"
    elif score >= 0.40:
        return "MEDIUM"
    return "LOW"


def _select_best_action(
    long_outcome: ActionOutcome,
    short_outcome: ActionOutcome,
    no_trade_outcome: NoTradeOutcome,
    profile: SimulationProfile,
) -> tuple[str, str, float, float, bool]:
    """Select best action from comparative outcomes.

    NO_TRADE utility = saved_loss_score (normalized 0-1 scale, mapped to R-scale via profile).

    Returns:
        (best_action, second_best_action, action_gap_r, regret_r, is_ambiguous)
    """
    # NO_TRADE utility: saved-loss quality in R-comparable terms
    nt_utility = no_trade_outcome.saved_loss_r - no_trade_outcome.missed_opportunity_r * 0.5

    utilities = {
        "LONG_NOW": long_outcome.action_utility,
        "SHORT_NOW": short_outcome.action_utility,
        "NO_TRADE": nt_utility,
    }

    ranked = sorted(utilities.items(), key=lambda x: x[1], reverse=True)
    best_action_label, best_utility = ranked[0]
    second_best_label, second_utility = ranked[1]
    action_gap = best_utility - second_utility

    # Regret: difference between chosen best and theoretical best
    regret_r = 0.0  # best action is the one recommended

    is_ambiguous = action_gap < profile.ambiguity_margin_r
    if is_ambiguous and profile.no_trade_default:
        best_action_label = "NO_TRADE"
        action_gap = 0.0

    if is_ambiguous and not profile.no_trade_default:
        best_action_label = "AMBIGUOUS_STATE"

    return best_action_label, second_best_label, round(action_gap, 6), round(regret_r, 6), is_ambiguous


def simulate(input: SimulationInput) -> SimulationOutput:
    """Run comparative simulation for LONG_NOW, SHORT_NOW, and NO_TRADE.

    Args:
        input: SimulationInput with entry price, ATR, future candles, profile.

    Returns:
        SimulationOutput with all three action outcomes compared.
    """
    profile = input.profile
    entry_risk = input.atr * profile.stop_multiplier
    notional = input.entry_price  # 1 unit of base currency

    # Stop/target levels
    stop_distance = input.atr * profile.stop_multiplier
    target_distance = input.atr * profile.target_multiplier

    long_stop = input.entry_price - stop_distance
    long_target = input.entry_price + target_distance
    short_stop = input.entry_price + stop_distance
    short_target = input.entry_price - target_distance

    candles = input.future_path.candles
    max_bars = profile.max_holding_bars
    available_bars = max(0, min(len(candles), max_bars))

    # Pre-extract OHLC arrays once — shared by both directions
    if available_bars > 0:
        highs, lows = _extract_ohlc(candles, available_bars)
        close_price = candles[available_bars - 1].close
    else:
        highs = np.array([], dtype=float)
        lows = np.array([], dtype=float)
        close_price = input.entry_price

    # Simulate LONG_NOW
    long_exit = simulate_path_from_arrays(
        "LONG", input.entry_price, long_stop, long_target,
        highs, lows, max_bars, available_bars, entry_risk, close_price,
    )
    long_outcome = _build_action_outcome(
        "LONG_NOW", long_exit, notional, input.entry_price, input.atr, profile,
    )

    # Simulate SHORT_NOW
    short_exit = simulate_path_from_arrays(
        "SHORT", input.entry_price, short_stop, short_target,
        highs, lows, max_bars, available_bars, entry_risk, close_price,
    )
    short_outcome = _build_action_outcome(
        "SHORT_NOW", short_exit, notional, input.entry_price, input.atr, profile,
    )

    # NO_TRADE quality
    no_trade_outcome = _build_no_trade_outcome(long_outcome, short_outcome, profile)

    # Action selection
    best_action, second_best, gap, regret, ambiguous = _select_best_action(
        long_outcome, short_outcome, no_trade_outcome, profile,
    )

    # Resolution status
    resolution = "COMPLETE"
    invalidity_reason = ""
    if not candles:
        resolution = "UNRESOLVED"
    elif len(candles) < max_bars and long_exit.exit_reason == "TIME_EXIT":
        resolution = "COMPLETE"  # partial path but exit resolved

    # Lineage
    lineage = SimulationLineage(
        simulation_family_version=input.simulation_family_version,
        simulation_profile_version=profile.profile_version,
        cost_model_version=input.cost_model_version,
        fee_model_version="fee-1.0.0",
        slippage_model_version="slippage-1.0.0",
        funding_model_version="funding-1.0.0",
        horizon_family=f"{profile.mode.value.lower()}_horizon",
        stop_family=profile.stop_method,
        target_family=profile.target_method,
        time_exit_family="hold_then_exit",
        adapter_kind="TRAINING",
    )

    return SimulationOutput(
        simulation_run_id=str(uuid.uuid4())[:8],
        symbol=input.symbol,
        decision_timestamp=input.decision_timestamp,
        mode=input.mode.value,
        primary_interval=input.primary_interval,
        resolution_status=resolution,
        invalidity_reason=invalidity_reason,
        long_outcome=long_outcome,
        short_outcome=short_outcome,
        no_trade_outcome=no_trade_outcome,
        best_action=best_action,
        second_best_action=second_best,
        action_gap_r=gap,
        regret_r=regret,
        is_ambiguous=ambiguous,
        lineage=lineage,
    )
