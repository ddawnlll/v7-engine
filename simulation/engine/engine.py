"""
Comparative simulation engine.

Evaluates LONG_NOW, SHORT_NOW, and NO_TRADE under the same cost/exit
semantics. This is the core of the /simulation economic truth authority.

Input:  SimulationInput (entry price, ATR, future candles, profile)
Output: SimulationOutput (comparative outcomes, best action, regret)

Extracted resolvers:
  - resolvers/action_selector.py — outcome building, path quality, action selection
  - resolvers/horizon_resolver.py — stop/target level computation, resolution status
  - resolvers/profile_resolver.py — profile lookup by mode
"""

from __future__ import annotations

import uuid

from simulation.contracts.models import (
    SimulationInput,
    SimulationOutput,
)
from simulation.engine.exits import simulate_path
from simulation.engine.resolvers import (
    build_action_outcome,
    build_no_trade_outcome,
    compute_resolution_status,
    compute_stop_target_levels,
    select_best_action,
)
from simulation.lineage import LineageBuilder


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
    long_stop, long_target, short_stop, short_target = compute_stop_target_levels(
        input.entry_price, input.atr, profile.stop_multiplier, profile.target_multiplier
    )

    candles = input.future_path.candles
    max_bars = profile.max_holding_bars

    # Simulate LONG_NOW
    long_exit = simulate_path(
        "LONG", input.entry_price, long_stop, long_target,
        candles, max_bars, entry_risk,
    )
    long_outcome = build_action_outcome(
        "LONG_NOW", long_exit, notional, input.entry_price, input.atr, profile,
    )

    # Simulate SHORT_NOW
    short_exit = simulate_path(
        "SHORT", input.entry_price, short_stop, short_target,
        candles, max_bars, entry_risk,
    )
    short_outcome = build_action_outcome(
        "SHORT_NOW", short_exit, notional, input.entry_price, input.atr, profile,
    )

    # NO_TRADE quality
    no_trade_outcome = build_no_trade_outcome(long_outcome, short_outcome, profile)

    # Action selection
    best_action, second_best, gap, regret, ambiguous = select_best_action(
        long_outcome, short_outcome, no_trade_outcome, profile,
    )

    # Resolution status
    resolution, invalidity_reason = compute_resolution_status(candles, max_bars, long_exit)

    # Lineage
    lineage = LineageBuilder(input=input, profile=profile).build()

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
