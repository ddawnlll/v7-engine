"""Comparative simulation engine.

Evaluates LONG_NOW, SHORT_NOW, and NO_TRADE under the same cost/exit
semantics. This is the core of the /simulation economic truth authority.

Input:  SimulationInput (entry price, ATR, future candles, profile)
Output: SimulationOutput (comparative outcomes, best action, regret)
"""

from __future__ import annotations

import uuid
from typing import Optional, Sequence

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
from simulation.engine.margin import compute_isolated_margin, resolve_bracket_snapshot
from simulation.engine.costs import total_cost_r
from simulation.engine.exits import (
    ExitResult,
    _extract_ohlc,
    compute_utility,
    simulate_path,
    simulate_path_from_arrays,
)
from simulation.engine.time import normalize_timestamp_ms


def _build_action_outcome(
    action: str,
    exit_result: ExitResult,
    notional: float,
    entry_price: float,
    atr: float,
    profile: SimulationProfile,
    decision_timestamp: int = 0,
    side: str = "LONG",
    future_candles: Sequence[Candle] | None = None,
    cost_scenario=None,
) -> ActionOutcome:
    """Build an ActionOutcome from an ExitResult + cost model.

    Parameters
    ----------
    future_candles : Sequence[Candle] | None
        The full future candle path, used to resolve the *real* exit timestamp
        from the candle at ``exit_result.exit_bar_index``.
    """
    # Resolve execution mode from profile
    exec_mode = getattr(profile, "execution_mode", "TAKER")
    maker_fill = getattr(profile, "maker_fill_probability", 0.7)
    from simulation.contracts.models import ExecutionMode
    try:
        execution_mode = ExecutionMode[exec_mode]
    except KeyError:
        execution_mode = ExecutionMode.TAKER

    # ── Real exit timestamp from candle close_time_utc ──────────────
    exit_timestamp_ms: int | None = None
    if future_candles and exit_result.exit_bar_index < len(future_candles):
        exit_candle = future_candles[exit_result.exit_bar_index]
        if exit_candle.close_time_utc:
            try:
                exit_timestamp_ms = normalize_timestamp_ms(exit_candle.close_time_utc)
            except ValueError:
                pass  # leave as None → will fall back to bar-based approx

    # ── Compute funding: prefer event-based over scalar rate ────────
    funding_events = getattr(profile, "funding_events", None)
    legacy_scalar_rate = getattr(profile, "funding_rate", 0.0)

    # Signed notional: positive for LONG, negative for SHORT
    signed_notional = notional if side == "LONG" else -notional

    # Determine entry timestamp for event matching
    entry_timestamp_ms = decision_timestamp

    from simulation.engine.funding import (
        FUNDING_MODEL_VERSION,
        funding_cost_r as scalar_funding_cost,
        funding_cost_r_from_events,
        resolve_funding_status,
    )
    from simulation.contracts.models import FundingDataStatus

    fund_r = 0.0
    matching_event_count = 0
    funding_source_str = ""
    funding_window_start = 0
    funding_window_end = 0

    if funding_events is not None and len(funding_events) > 0 and entry_timestamp_ms > 0:
        # Use real exit timestamp from candle if available
        effective_exit_ms = exit_timestamp_ms
        if effective_exit_ms is None:
            # Fallback: bar-based approximation (legacy behaviour)
            interval_ms = _interval_ms_for_profile(profile)
            effective_exit_ms = decision_timestamp + exit_result.hold_duration_bars * interval_ms

        funding_window_start = entry_timestamp_ms
        funding_window_end = effective_exit_ms

        # Count matching events
        for evt in funding_events:
            if entry_timestamp_ms < evt.timestamp <= effective_exit_ms:
                matching_event_count += 1

        # Compute event-based funding cost (signed notional already applied)
        fund_quote = funding_cost_r_from_events(
            signed_notional, funding_events, entry_timestamp_ms, effective_exit_ms,
        )
        risk = atr * profile.stop_multiplier
        fund_r = fund_quote / risk if risk > 0 else 0.0
        funding_source_str = "event"
    elif legacy_scalar_rate != 0.0 and entry_timestamp_ms > 0:
        # Scalar funding path — now side-aware
        fund_quote = scalar_funding_cost(
            notional, legacy_scalar_rate, exit_result.hold_duration_bars, side=side,
        )
        risk = atr * profile.stop_multiplier
        fund_r = fund_quote / risk if risk > 0 else 0.0
        funding_source_str = "legacy_scalar"

    # ── Fee & slippage (always with positive notional) ──────────────
    fcr, scr, _, tcr = total_cost_r(
        notional=notional,
        entry_price=entry_price,
        atr=atr,
        stop_multiplier=profile.stop_multiplier,
        funding_rate=0.0,  # funding already handled above
        holding_bars=exit_result.hold_duration_bars,
        execution_mode=execution_mode,
        maker_fill_probability=maker_fill,
    )
    # Stress belongs to simulation evaluation, never to a post-hoc fixture.
    # CostScenario is immutable and explicitly attached to SimulationInput.
    if cost_scenario is not None:
        fcr *= cost_scenario.fee_multiplier
        scr *= cost_scenario.slippage_multiplier
        fund_r *= cost_scenario.funding_multiplier
    tcr = fcr + scr + fund_r

    realized_r_net = exit_result.realized_r_gross - tcr

    # ── Determine truthful funding status for lineage ───────────────
    if funding_events is not None:
        has_legacy = (legacy_scalar_rate != 0.0)
    else:
        has_legacy = (legacy_scalar_rate != 0.0)

    funding_status = resolve_funding_status(
        events=funding_events if hasattr(profile, 'funding_events') else None,
        has_legacy_scalar=has_legacy,
        matching_count=matching_event_count,
    )

    # If we took the event path, re-check status with matching count
    if funding_events is not None:
        if matching_event_count > 0:
            funding_status = FundingDataStatus.APPLIED.value
        else:
            # Events list exists but no events in window
            funding_status = FundingDataStatus.AVAILABLE_EMPTY.value

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
        funding_status=funding_status,
        funding_event_count=matching_event_count,
        funding_source=funding_source_str,
    )


def _interval_ms_for_profile(profile: SimulationProfile) -> int:
    """Return interval in ms for the profile's primary_interval."""
    interval = getattr(profile, "primary_interval", "1h")
    # Simple mapping
    mapping = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}
    return mapping.get(interval, 3_600_000)


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
    if saved_loss_r == 0.0 and missed_opportunity_r == 0.0:
        quality = "CORRECT_NO_TRADE"
        was_correct = True
    elif saved_loss_r > 0.0 and missed_opportunity_r == 0.0:
        quality = "SAVED_LOSS"
        was_correct = True
    elif missed_opportunity_r > 0.0 and saved_loss_r == 0.0:
        quality = "MISSED_OPPORTUNITY"
        was_correct = False
    elif saved_loss_r > 0.0 and missed_opportunity_r > 0.0:
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
    """Select best action from comparative outcomes."""
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

    regret_r = 0.0

    is_ambiguous = action_gap < profile.ambiguity_margin_r
    if is_ambiguous and profile.no_trade_default:
        best_action_label = "NO_TRADE"
        action_gap = 0.0

    if is_ambiguous and not profile.no_trade_default:
        best_action_label = "AMBIGUOUS_STATE"

    return best_action_label, second_best_label, round(action_gap, 6), round(regret_r, 6), is_ambiguous


def simulate(input: SimulationInput) -> SimulationOutput:
    """Run comparative simulation for LONG_NOW, SHORT_NOW, and NO_TRADE."""
    profile = input.profile
    entry_risk = input.atr * profile.stop_multiplier
    notional = input.notional_quote if input.notional_quote is not None else input.entry_price

    # Stop/target levels
    stop_distance = input.atr * profile.stop_multiplier
    target_distance = input.atr * profile.target_multiplier

    # Isolated margin: bracket evidence is mandatory for leverage >1.
    _leverage = getattr(profile, "leverage", 1)
    if _leverage > 1:
        bracket = resolve_bracket_snapshot(
            symbol=input.symbol, notional=notional, leverage=_leverage,
            snapshots=input.bracket_snapshots,
        )
        long_margin = compute_isolated_margin(
            leverage=_leverage, entry_price=input.entry_price, notional=notional,
            direction="LONG", bracket=bracket,
        )
        short_margin = compute_isolated_margin(
            leverage=_leverage, entry_price=input.entry_price, notional=notional,
            direction="SHORT", bracket=bracket,
        )
        long_liquidation_price = long_margin.liquidation_price
        short_liquidation_price = short_margin.liquidation_price
    else:
        long_margin = short_margin = None
        long_liquidation_price = short_liquidation_price = None

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

    # Normalize decision timestamp
    try:
        decision_ms = normalize_timestamp_ms(input.decision_timestamp)
    except ValueError:
        decision_ms = 0

    # Simulate LONG_NOW
    long_exit = simulate_path_from_arrays(
        "LONG", input.entry_price, long_stop, long_target,
        highs, lows, max_bars, available_bars, entry_risk, close_price,
        liquidation_price=long_liquidation_price,
    )
    long_outcome = _build_action_outcome(
        "LONG_NOW", long_exit, notional, input.entry_price, input.atr, profile,
        decision_timestamp=decision_ms, side="LONG",
        future_candles=candles,
        cost_scenario=input.cost_scenario,
    )

    # Simulate SHORT_NOW
    short_exit = simulate_path_from_arrays(
        "SHORT", input.entry_price, short_stop, short_target,
        highs, lows, max_bars, available_bars, entry_risk, close_price,
        liquidation_price=short_liquidation_price,
    )
    short_outcome = _build_action_outcome(
        "SHORT_NOW", short_exit, notional, input.entry_price, input.atr, profile,
        decision_timestamp=decision_ms, side="SHORT",
        future_candles=candles,
        cost_scenario=input.cost_scenario,
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
        resolution = "COMPLETE"

    # Truthful funding lineage — derive from the LONG outcome (both sides use same funding data)
    funding_status = getattr(long_outcome, "funding_status", "")
    funding_event_count = getattr(long_outcome, "funding_event_count", 0)
    funding_source_str = getattr(long_outcome, "funding_source", "")
    funding_window_start = 0
    funding_window_end = 0

    # Lineage
    lineage = SimulationLineage(
        simulation_family_version=input.simulation_family_version,
        simulation_profile_version=profile.profile_version,
        cost_model_version=input.cost_model_version,
        fee_model_version="fee-1.0.0",
        slippage_model_version="slippage-1.0.0",
        funding_model_version="funding-2.0.0",
        horizon_family=f"{profile.mode.value.lower()}_horizon",
        stop_family=profile.stop_method,
        target_family=profile.target_method,
        time_exit_family="hold_then_exit",
        adapter_kind="TRAINING",
        funding_status=funding_status,
        funding_event_count=funding_event_count,
        funding_source=funding_source_str,
        funding_window_start_ms=funding_window_start,
        funding_window_end_ms=funding_window_end,
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
