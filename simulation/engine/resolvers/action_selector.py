"""
Action selector — evaluates and selects the best trading action from
comparative simulation outcomes.

Extracted from engine.py (Sim T4). Contains all action-level decision logic:
- Building ActionOutcome from ExitResult + cost model
- Building NoTradeOutcome from directional outcomes
- Path quality scoring
- Best-action selection with ambiguity handling
"""

from __future__ import annotations

from simulation.contracts.models import (
    ActionOutcome,
    NoTradeOutcome,
    PathMetrics,
    SimulationProfile,
)
from simulation.engine.costs import total_cost_r
from simulation.engine.exits import ExitResult, compute_utility


def build_action_outcome(
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
        path_quality_score=path_quality(exit_result.mfe_r, exit_result.mae_r),
        path_quality_bucket=path_quality_bucket(exit_result.mfe_r, exit_result.mae_r),
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


def build_no_trade_outcome(
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


def path_quality(mfe_r: float, mae_r: float) -> float:
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


def path_quality_bucket(mfe_r: float, mae_r: float) -> str:
    score = path_quality(mfe_r, mae_r)
    if score >= 0.70:
        return "HIGH"
    elif score >= 0.40:
        return "MEDIUM"
    return "LOW"


def select_best_action(
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
