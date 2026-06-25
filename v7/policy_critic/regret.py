"""
Regret computation for Policy Critic.

regret_r = best_possible_outcome_r - chosen_action_outcome_r

Where best_possible_outcome_r is max(LONG_r_net, SHORT_r_net, 0.0) and
0.0 represents NO_TRADE (the zero-cost baseline).

Uses simulation/engine/costs.py for authoritative cost computation.

Design (matches v7/docs/policy_critic/design.md section 5):
  - BASE:    r_base = realized_r_net          (NO_TRADE: r_base = 0)
  - SHAPED:  r_shaped = action_utility         (mode-weighted composite)
  - DRAWDOWN: r_drawdown = -lambda_dd * abs(mae_r)  (Sortino-style)
  - NO_TRADE: r_no_trade = saved_loss_r - 0.5 * missed_opportunity_r
  - FUNDING: NOT INCLUDED (DEFERRED — spot-only)

Action utility per mode (from design.md profile anchor):
  lambda_dd (drawdown penalty weight) varies by mode:
    SWING:              medium  -> 0.5
    SCALP:              high    -> 1.0
    AGGRESSIVE_SCALP:   very_high -> 2.0
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class RegretBasis(str, Enum):
    """What the regret is measured against."""
    R_NET = "R_NET"           # realized_r_net (post-cost)
    ACTION_UTILITY = "ACTION_UTILITY"  # utility composite from simulation
    SHAPED_REWARD = "SHAPED_REWARD"    # full reward with drawdown penalty


# Mode-specific drawdown penalty weights (design.md section 5)
_LAMBDA_DD: dict[str, float] = {
    "SWING": 0.5,
    "SCALP": 1.0,
    "AGGRESSIVE_SCALP": 2.0,
}

DEFAULT_LAMBDA_DD = 0.5


def get_lambda_dd(mode: str) -> float:
    """Return the drawdown penalty weight for a mode.

    Args:
        mode: Trading mode — SWING, SCALP, or AGGRESSIVE_SCALP.

    Returns:
        Drawdown penalty lambda (0.5 for SWING, 1.0 for SCALP, 2.0 for AGGRESSIVE_SCALP).
        Defaults to 0.5 for unrecognized modes.
    """
    return _LAMBDA_DD.get(mode.upper(), DEFAULT_LAMBDA_DD)


@dataclass(frozen=True)
class RegretResult:
    """Outcome of one regret computation at a single decision point.

    Attributes:
        regret_r:   Positive regret (best_r_net - chosen_r_net).
        best_action: Which of LONG, SHORT, NO_TRADE would have been best.
        best_r_net: Best achievable realized_r_net.
        best_action_utility: Best action utility composite.
        chosen_r_net: realized_r_net of the action that was actually taken.
        chosen_action_utility: Action utility of the chosen action.
        no_trade_saved_loss_r: saved_loss_r from simulation NoTradeOutcome.
        no_trade_missed_opp_r: missed_opportunity_r from NoTradeOutcome.
        is_regret_significant: True if regret_r > ambiguity_margin.
        ambiguity_margin_r: Threshold below which regret is considered noise.
        drawdown_penalty_long: -lambda_dd * abs(mae_r) for LONG.
        drawdown_penalty_short: -lambda_dd * abs(mae_r) for SHORT.
    """

    regret_r: float
    best_action: str
    best_r_net: float
    best_action_utility: float
    chosen_r_net: float
    chosen_action_utility: float
    no_trade_saved_loss_r: float = 0.0
    no_trade_missed_opp_r: float = 0.0
    is_regret_significant: bool = False
    ambiguity_margin_r: float = 0.20
    drawdown_penalty_long: float = 0.0
    drawdown_penalty_short: float = 0.0


def compute_regret_r(
    long_r_net: float,
    short_r_net: float,
    chosen_r_net: float,
    chosen_action: str = "LONG",
    *,
    long_mae_r: float = 0.0,
    short_mae_r: float = 0.0,
    saved_loss_r: float = 0.0,
    missed_opportunity_r: float = 0.0,
    mode: str = "SWING",
    ambiguity_margin_r: float = 0.20,
    basis: RegretBasis = RegretBasis.SHAPED_REWARD,
    long_action_utility: float = 0.0,
    short_action_utility: float = 0.0,
    chosen_action_utility: float = 0.0,
) -> RegretResult:
    """Compute regret_r for a single decision.

    Regret = best_possible_outcome - chosen_action_outcome.

    If basis is SHAPED_REWARD (default), the regret uses the full
    decomposable reward including drawdown penalty:
      shaped_r(action) = action_utility - lambda_dd * abs(mae_r)

    If basis is R_NET, regret is purely realized_r_net:
      r(action) = realized_r_net

    NO_TRADE baseline:
      r(NO_TRADE) = saved_loss_r - 0.5 * missed_opportunity_r
      (Matches simulation engine's _build_no_trade_outcome formula)

    Args:
        long_r_net:   Realized R-net for LONG action.
        short_r_net:  Realized R-net for SHORT action.
        chosen_r_net: Realized R-net of the action actually taken.
        chosen_action: The action taken (LONG, SHORT, NO_TRADE).
        long_mae_r:   MAE in R terms for LONG path.
        short_mae_r:  MAE in R terms for SHORT path.
        saved_loss_r: saved_loss_r from simulation (NO_TRADE quality).
        missed_opportunity_r: missed_opportunity_r from simulation.
        mode:         Trading mode for drawdown penalty weight.
        ambiguity_margin_r: Regret below this is considered noise.
        basis:        Which reward signal to use for regret.
        long_action_utility: Composite utility for LONG (if available).
        short_action_utility: Composite utility for SHORT.
        chosen_action_utility: Composite utility for the chosen action.

    Returns:
        RegretResult with full decomposition.
    """
    lambda_dd = get_lambda_dd(mode)

    # Drawdown penalties
    dd_penalty_long = -lambda_dd * abs(long_mae_r)
    dd_penalty_short = -lambda_dd * abs(short_mae_r)

    # NO_TRADE reward
    no_trade_r = saved_loss_r - 0.5 * missed_opportunity_r

    if basis == RegretBasis.R_NET:
        long_r = long_r_net
        short_r = short_r_net
        chosen_r = chosen_r_net
        best_r = max(long_r_net, short_r_net, 0.0)
    else:
        # SHAPED_REWARD (default): utility + drawdown penalty
        long_r = long_action_utility + dd_penalty_long if long_action_utility else long_r_net + dd_penalty_long
        short_r = short_action_utility + dd_penalty_short if short_action_utility else short_r_net + dd_penalty_short
        chosen_r = chosen_action_utility + (
            -lambda_dd * abs(long_mae_r) if chosen_action == "LONG"
            else -lambda_dd * abs(short_mae_r) if chosen_action == "SHORT"
            else 0.0
        ) if chosen_action_utility else chosen_r_net
        best_r = max(long_r, short_r, no_trade_r)

    # Determine best action
    if best_r == long_r:
        best_action = "LONG"
        best_action_utility = long_action_utility
    elif best_r == short_r:
        best_action = "SHORT"
        best_action_utility = short_action_utility
    else:
        best_action = "NO_TRADE"
        best_action_utility = 0.0

    # Regret: how much better the best action would have been
    regret_r = best_r - chosen_r

    # Beat-by: no regret if chose the best among all-losing options.
    # Regret is real when NO_TRADE (0.0) beats a losing chosen action.
    if best_r <= 0 and chosen_r <= 0:
        regret_r = max(0.0, best_r - chosen_r)  # still regret if chosen < best

    is_significant = regret_r > ambiguity_margin_r and regret_r > 0

    return RegretResult(
        regret_r=round(max(0.0, regret_r), 6),
        best_action=best_action,
        best_r_net=max(long_r_net, short_r_net, 0.0),
        best_action_utility=best_action_utility,
        chosen_r_net=chosen_r_net,
        chosen_action_utility=chosen_action_utility,
        no_trade_saved_loss_r=saved_loss_r,
        no_trade_missed_opp_r=missed_opportunity_r,
        is_regret_significant=is_significant,
        ambiguity_margin_r=ambiguity_margin_r,
        drawdown_penalty_long=dd_penalty_long,
        drawdown_penalty_short=dd_penalty_short,
    )


def compute_regret_from_simulation(
    simulation_output: dict[str, Any],
    chosen_action: str,
    *,
    mode: str = "SWING",
    ambiguity_margin_r: float = 0.20,
    basis: RegretBasis = RegretBasis.SHAPED_REWARD,
) -> RegretResult:
    """Compute regret_r from a SimulationOutput dict.

    Convenience wrapper that extracts all needed fields from a
    SimulationOutput-compatible dict.

    Args:
        simulation_output: Dict with long_outcome, short_outcome,
                           no_trade_outcome sub-dicts.
        chosen_action: The action that was actually taken.
        mode: Trading mode for drawdown penalty weight.
        ambiguity_margin_r: Regret noise floor.
        basis: Reward basis for regret computation.

    Returns:
        RegretResult.
    """
    lo = simulation_output.get("long_outcome", {})
    so = simulation_output.get("short_outcome", {})
    nt = simulation_output.get("no_trade_outcome", {})

    long_r_net = lo.get("realized_r_net", 0.0) if isinstance(lo, dict) else 0.0
    short_r_net = so.get("realized_r_net", 0.0) if isinstance(so, dict) else 0.0
    long_au = lo.get("action_utility", 0.0) if isinstance(lo, dict) else 0.0
    short_au = so.get("action_utility", 0.0) if isinstance(so, dict) else 0.0

    # MAE from PathMetrics
    long_pm = lo.get("path_metrics", {}) if isinstance(lo, dict) else {}
    short_pm = so.get("path_metrics", {}) if isinstance(so, dict) else {}
    long_mae_r = long_pm.get("mae_r", 0.0) if isinstance(long_pm, dict) else 0.0
    short_mae_r = short_pm.get("mae_r", 0.0) if isinstance(short_pm, dict) else 0.0

    saved_loss_r = nt.get("saved_loss_r", 0.0) if isinstance(nt, dict) else 0.0
    missed_opp_r = nt.get("missed_opportunity_r", 0.0) if isinstance(nt, dict) else 0.0

    # Determine chosen_r_net and chosen_au
    if chosen_action in ("LONG", "ENTER_LONG"):
        chosen_r_net = long_r_net
        chosen_au = long_au
    elif chosen_action in ("SHORT", "ENTER_SHORT"):
        chosen_r_net = short_r_net
        chosen_au = short_au
    else:
        chosen_r_net = 0.0
        chosen_au = 0.0

    return compute_regret_r(
        long_r_net=long_r_net,
        short_r_net=short_r_net,
        chosen_r_net=chosen_r_net,
        chosen_action=chosen_action,
        long_mae_r=long_mae_r,
        short_mae_r=short_mae_r,
        saved_loss_r=saved_loss_r,
        missed_opportunity_r=missed_opp_r,
        mode=mode,
        ambiguity_margin_r=ambiguity_margin_r,
        basis=basis,
        long_action_utility=long_au,
        short_action_utility=short_au,
        chosen_action_utility=chosen_au,
    )
