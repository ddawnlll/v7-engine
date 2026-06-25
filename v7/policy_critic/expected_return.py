"""
Per-direction expected return estimation for Policy Critic.

Computes expected_R_long and expected_R_short using V7's cost model and the
simulation engine's authoritative economic truth. The expected_R values are
used by the Policy Critic to assess whether a proposed action's expected
value exceeds the no-trade baseline.

expected_R = P(win) * avg_win_R - P(lose) * avg_lose_R - total_cost_r

For the initial baseline (v1 rule-based shadow), expected_R is derived from:
  - confidence score (proxy for P(win))
  - stop/target R multiples from mode profile
  - total_cost_r from simulation/engine/costs.py

Training target (v2+): per-direction realized_R from simulation replay.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from simulation.engine.costs import (
    compute_entry_risk,
    fee_cost_r,
    slippage_cost_r,
    total_cost_r,
)

from v7.policy_critic.replay_buffer import (
    CRITIC_ACTION_LONG,
    CRITIC_ACTION_SHORT,
    CRITIC_ACTION_NO_TRADE,
    map_decision_to_critic_action,
)


@dataclass(frozen=True)
class ExpectedReturn:
    """Per-direction expected return estimates.

    Attributes:
        expected_r_long: Expected R-multiple for going LONG (post-costs).
        expected_r_short: Expected R-multiple for going SHORT (post-costs).
        expected_r_no_trade: Expected R for NO_TRADE (always uses the
                             baseline formula: saved_loss_r - 0.5 * missed_opp_r).
        total_cost_r: Combined fee + slippage + funding cost in R terms.
        direction_bias: 1.0 if LONG > SHORT, -1.0 if SHORT > LONG,
                        0.0 if equal or neither has positive expectancy.
        confidence: Model confidence (0-1), used as P(win) proxy in v1.
        stop_r: Stop-loss distance in R terms (positive).
        target_r: Take-profit distance in R terms (positive).
        mode: Trading mode.
        source: How expected_R was computed — RULE_BASED (v1 shadow),
                SIMULATION_MEAN (v2 empirical mean realized R),
                or CRITIC_MODEL (v3+ critic value function output).
    """

    expected_r_long: float
    expected_r_short: float
    expected_r_no_trade: float
    total_cost_r: float
    direction_bias: float
    confidence: float
    stop_r: float
    target_r: float
    mode: str
    source: str = "RULE_BASED"


def compute_rule_based_expected_r(
    *,
    confidence: float,
    atr: float,
    entry_price: float,
    notional: float,
    mode: str = "SWING",
    stop_multiplier: float = 2.0,
    target_multiplier: float = 2.5,
    taker_fee_bps: float = 4.0,
    slippage_bps: float = 1.0,
    funding_rate: float = 0.0,
    holding_bars: int = 0,
    saved_loss_r: float = 0.0,
    missed_opportunity_r: float = 0.0,
) -> ExpectedReturn:
    """Compute per-direction expected_R using rule-based (v1 shadow) approach.

    This is the conservative baseline: expected_R = P(win) * win_R - P(lose) * loss_R - costs.

    Where:
      - P(win) = confidence (proxy — will be replaced by calibrated probability in v2+)
      - win_R = target_multiplier (R-multiple if target hits)
      - loss_R = stop_multiplier (R-multiple if stop hits)

    Both LONG and SHORT get the same symmetric treatment in this baseline;
    direction_bias is determined by realized evidence, not assumed.

    Args:
        confidence: Model confidence 0-1.
        atr: Current ATR value.
        entry_price: Recommended entry price.
        notional: Notional position size.
        mode: Trading mode.
        stop_multiplier: Stop distance in ATR multiples.
        target_multiplier: Target distance in ATR multiples.
        taker_fee_bps: Fee in basis points.
        slippage_bps: Slippage in basis points.
        funding_rate: Per-bar funding rate.
        holding_bars: Expected holding bars.
        saved_loss_r: saved_loss_r from simulation (for NO_TRADE expected R).
        missed_opportunity_r: missed_opportunity_r from simulation.

    Returns:
        ExpectedReturn with per-direction estimates.
    """
    entry_risk = compute_entry_risk(atr, stop_multiplier)
    if entry_risk <= 0:
        return ExpectedReturn(
            expected_r_long=0.0,
            expected_r_short=0.0,
            expected_r_no_trade=0.0,
            total_cost_r=0.0,
            direction_bias=0.0,
            confidence=confidence,
            stop_r=0.0,
            target_r=0.0,
            mode=mode,
            source="RULE_BASED",
        )

    fcr, scr, fund_r, tcr = total_cost_r(
        notional=notional,
        entry_price=entry_price,
        atr=atr,
        stop_multiplier=stop_multiplier,
        taker_fee_bps=taker_fee_bps,
        slippage_bps=slippage_bps,
        funding_rate=funding_rate,
        holding_bars=holding_bars,
    )

    # Expected value formula: E[R] = P(win) * win_R - (1-P(win)) * loss_R - costs
    # win_R = target_multiplier, loss_R = stop_multiplier
    p_win = max(0.0, min(1.0, confidence))
    p_lose = 1.0 - p_win

    expected_r_gross = p_win * target_multiplier - p_lose * stop_multiplier
    expected_r_net = expected_r_gross - tcr

    # Per-direction expected R (symmetric in v1 rule-based baseline)
    er_long = expected_r_net
    er_short = expected_r_net

    # NO_TRADE expected R: saved_loss - 0.5 * missed (same as simulation)
    er_no_trade = saved_loss_r - 0.5 * missed_opportunity_r

    # Direction bias
    if er_long > er_short:
        bias = 1.0
    elif er_short > er_long:
        bias = -1.0
    else:
        bias = 0.0

    return ExpectedReturn(
        expected_r_long=round(er_long, 6),
        expected_r_short=round(er_short, 6),
        expected_r_no_trade=round(er_no_trade, 6),
        total_cost_r=round(tcr, 6),
        direction_bias=bias,
        confidence=confidence,
        stop_r=stop_multiplier,
        target_r=target_multiplier,
        mode=mode,
        source="RULE_BASED",
    )


def compute_expected_r_from_simulation(
    *,
    simulation_output: dict[str, Any],
    confidence: float = 0.5,
    mode: str = "SWING",
) -> ExpectedReturn:
    """Compute expected_R from a SimulationOutput, using realized outcomes.

    Uses the simulation's actual realized_R values as per-direction expected_R
    estimates (empirical mean proxy for v2+).

    Args:
        simulation_output: SimulationOutput-compatible dict.
        confidence: Model confidence 0-1 (for metadata only in this mode).
        mode: Trading mode.

    Returns:
        ExpectedReturn using simulation-realized values.
    """
    lo = simulation_output.get("long_outcome", {})
    so = simulation_output.get("short_outcome", {})
    nt = simulation_output.get("no_trade_outcome", {})

    er_long = lo.get("realized_r_net", 0.0) if isinstance(lo, dict) else 0.0
    er_short = so.get("realized_r_net", 0.0) if isinstance(so, dict) else 0.0
    tcr = lo.get("total_cost_r", 0.0) if isinstance(lo, dict) else 0.0

    saved_loss_r = nt.get("saved_loss_r", 0.0) if isinstance(nt, dict) else 0.0
    missed_opp_r = nt.get("missed_opportunity_r", 0.0) if isinstance(nt, dict) else 0.0
    er_no_trade = saved_loss_r - 0.5 * missed_opp_r

    if er_long > er_short:
        bias = 1.0
    elif er_short > er_long:
        bias = -1.0
    else:
        bias = 0.0

    # Get stop/target R from simulation profile if available
    profile = simulation_output.get("profile", {})
    stop_r = profile.get("stop_multiplier", 2.0) if isinstance(profile, dict) else 2.0
    target_r = profile.get("target_multiplier", 2.5) if isinstance(profile, dict) else 2.5

    return ExpectedReturn(
        expected_r_long=round(er_long, 6),
        expected_r_short=round(er_short, 6),
        expected_r_no_trade=round(er_no_trade, 6),
        total_cost_r=round(tcr, 6),
        direction_bias=bias,
        confidence=confidence,
        stop_r=stop_r,
        target_r=target_r,
        mode=mode,
        source="SIMULATION_MEAN",
    )


def compare_directions(
    expected_long: float,
    expected_short: float,
    expected_no_trade: float = 0.0,
    *,
    min_action_edge_r: float = 0.35,
) -> dict[str, Any]:
    """Compare per-direction expected returns to determine the best action.

    Args:
        expected_long: Expected R for LONG.
        expected_short: Expected R for SHORT.
        expected_no_trade: Expected R for NO_TRADE.
        min_action_edge_r: Minimum edge required to favor a directional action
                          over NO_TRADE. Default 0.35 (SWING mode anchor).

    Returns:
        Dict with best_direction, best_expected_r, edge_over_no_trade,
        and ambiguity flag.
    """
    candidates = {
        "LONG": expected_long,
        "SHORT": expected_short,
        "NO_TRADE": expected_no_trade,
    }

    best_direction = max(candidates, key=lambda k: candidates[k])
    best_r = candidates[best_direction]
    second_r = sorted(candidates.values(), reverse=True)[1]
    gap = best_r - second_r

    edge = best_r - expected_no_trade

    # Ambiguity: best edge is below minimum, or gap between top two is small
    is_ambiguous = (
        (best_direction != "NO_TRADE" and edge < min_action_edge_r)
        or (best_direction == "NO_TRADE" and best_r < 0)
        or (gap < min_action_edge_r * 0.5)
    )

    return {
        "best_direction": best_direction,
        "best_expected_r": round(best_r, 6),
        "edge_over_no_trade": round(edge, 6),
        "gap_to_second": round(gap, 6),
        "is_ambiguous": is_ambiguous,
        "min_action_edge_r": min_action_edge_r,
    }
