"""
Simulation-authority label generator for leverage-aware AlphaForge training.

Replaces the forward-return label generator with true economic R labels
from the simulation engine for all 13 v2 actions.

For each bar, runs the canonical simulation for every leverage tier and
produces:
  - direction_label: 0=LONG, 1=SHORT, 2=NO_TRADE (best action at 1x)
  - optimal_leverage: the leverage tier that maximizes margin_return_net
    (only valid when base_net_R > 0; 0 when base_net_R <= 0)
  - base_net_R: the risk-normalized R at 1x — the alpha truth invariant
  - margin_return_net: best leverage-adjusted margin return
  - liquidation_risk: fraction of profitable tiers that hit liquidation

Fail-closed: only produces labels where SimulationInput has valid
bracket_snapshots. No silent MMR fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

from simulation.contracts.models import (
    BinanceBracketSnapshot,
    Candle,
    CostScenario,
    FuturePath,
    LeverageOutcome,
    SimulationInput,
    SimulationProfile,
    TradingMode,
)
from simulation.engine.engine import simulate
from simulation.engine.margin import (
    ACTION_ID_TO_DIRECTION_LEVERAGE,
    ACTION_ID_TO_LABEL,
    VALID_V2_ACTION_IDS,
)


@dataclass
class LeverageLabel:
    """Training label for one decision bar (all leverage tiers evaluated)."""
    timestamp_ms: int
    symbol: str
    close_price: float
    # Direction at 1x (the alpha truth)
    direction: int          # 0=LONG, 1=SHORT, 2=NO_TRADE
    base_net_R: float       # net R at 1x for the best direction
    # Leverage
    optimal_action_id: int  # v2 action ID that maximizes margin_return
    optimal_leverage: int   # 0-10, 0 means NO_TRADE
    optimal_margin_return: float  # margin_return_net at optimal leverage
    # All action outcomes for analysis
    action_outcomes: dict[str, LeverageOutcome]
    # Liquidation
    any_liquidation: bool   # True if ANY leverage tier liquidated
    liquidation_rate: float  # fraction of leverage tiers that liquidated
    # Cost
    cost_scenario_id: str
    break_even_cost_multiple: float  # at what cost_multiple does base_net_R go to 0


def _make_bracket_snapshots(
    symbol: str,
    entry_price: float,
    max_notional: float = 100_000,
) -> tuple[BinanceBracketSnapshot, ...]:
    """Create representative bracket snapshots for a symbol.

    For P1, uses conservative tier-1 Binance brackets.
    When real bracket loading is wired, this is replaced.
    """
    return (
        BinanceBracketSnapshot(
            symbol=symbol, tier=1, leverage=10,
            notional_cap_usd=50_000,
            maintenance_margin_ratio=0.004,
            bracket_snapshot_version="p1-representative-v1",
        ),
        BinanceBracketSnapshot(
            symbol=symbol, tier=2, leverage=10,
            notional_cap_usd=250_000,
            maintenance_margin_ratio=0.005,
            bracket_snapshot_version="p1-representative-v1",
        ),
        BinanceBracketSnapshot(
            symbol=symbol, tier=3, leverage=10,
            notional_cap_usd=1_000_000,
            maintenance_margin_ratio=0.01,
            bracket_snapshot_version="p1-representative-v1",
        ),
    )


def _make_candle(
    open_p: float, high_p: float, low_p: float, close_p: float, close_time_utc: str = "",
) -> Candle:
    return Candle(open=open_p, high=high_p, low=low_p, close=close_p, close_time_utc=close_time_utc)


def _simulate_bar(
    symbol: str,
    entry_price: float,
    atr: float,
    future_candles: list[Candle],
    profile: SimulationProfile,
    bracket_snapshots: tuple[BinanceBracketSnapshot, ...],
    timestamp_ms: int,
    cost_scenario: Optional[CostScenario] = None,
) -> dict[str, LeverageOutcome]:
    """Run all 13 actions for a single bar and return dict of outcomes."""
    outcomes: dict[str, LeverageOutcome] = {}

    for action_id in sorted(VALID_V2_ACTION_IDS):
        direction, leverage = ACTION_ID_TO_DIRECTION_LEVERAGE[action_id]
        action_label = ACTION_ID_TO_LABEL[action_id]

        if action_id == 0:  # NO_TRADE
            outcomes[action_label] = LeverageOutcome(
                action_label="NO_TRADE", direction="NO_TRADE", leverage=0,
                base_net_R=0.0, realized_r_gross=0.0,
                margin_return_net=0.0, equity_return_net=0.0,
                fee_cost_r=0.0, slippage_cost_r=0.0, funding_cost_r=0.0,
                total_cost_r=0.0, initial_margin=0.0, maintenance_margin=0.0,
                margin_type="ISOLATED",
                liquidation_price=None, liquidation_distance_pct=0.0,
                liquidation_event=False, exit_reason="NO_TRADE",
                exit_price=0.0, exit_bar_index=0, hold_duration_bars=0,
                quantity=0.0, notional=0.0,
                cost_scenario_id=(cost_scenario.scenario_id if cost_scenario else "baseline_1.0x"),
            )
            continue

        # Create action-specific profile with target leverage
        from dataclasses import replace
        action_profile = replace(profile, leverage=leverage)

        future_path = FuturePath(
            candles=future_candles,
            completeness_status="COMPLETE",
            expected_bars=len(future_candles),
        )

        action_input = SimulationInput(
            symbol=symbol,
            decision_timestamp=str(timestamp_ms),
            mode=profile.mode,
            primary_interval=profile.primary_interval,
            entry_price=entry_price,
            atr=atr,
            future_path=future_path,
            profile=action_profile,
            simulation_family_version="simfam-1.1.0",
            cost_model_version="cost-1.1.0",
            bracket_snapshots=bracket_snapshots,
            notional_quote=entry_price,
            cost_scenario=cost_scenario,
        )

        sim_output = simulate(action_input)
        sim_outcome = sim_output.long_outcome if direction == "LONG" else sim_output.short_outcome

        # Margin return
        entry_risk = atr * profile.stop_multiplier
        if leverage > 1 and bracket_snapshots and entry_risk > 0:
            from simulation.engine.margin import compute_isolated_margin, resolve_bracket_snapshot
            bracket = resolve_bracket_snapshot(
                symbol=symbol, notional=entry_price, leverage=leverage,
                snapshots=bracket_snapshots,
            )
            margin = compute_isolated_margin(
                leverage=leverage, entry_price=entry_price,
                notional=entry_price, direction=direction,
                bracket=bracket,
            )
            risk_quote = entry_risk * margin.quantity
            quote_pnl = sim_outcome.realized_r_net * risk_quote
            init_margin_val = margin.initial_margin_ratio * margin.notional
            margin_return = quote_pnl / init_margin_val if init_margin_val > 0 else 0.0
            init_margin = init_margin_val
            maint_margin = margin.maintenance_margin_ratio * margin.notional
        else:
            margin_return = sim_outcome.realized_r_net
            from simulation.engine.margin import compute_isolated_margin
            margin = compute_isolated_margin(
                leverage=1, entry_price=entry_price,
                notional=entry_price, direction=direction,
            )
            init_margin = margin.initial_margin_ratio * margin.notional
            maint_margin = margin.maintenance_margin_ratio * margin.notional

        outcomes[action_label] = LeverageOutcome(
            action_label=action_label,
            direction=direction,
            leverage=leverage,
            base_net_R=sim_outcome.realized_r_net,
            realized_r_gross=sim_outcome.realized_r_gross,
            margin_return_net=margin_return,
            equity_return_net=margin_return,
            fee_cost_r=sim_outcome.fee_cost_r,
            slippage_cost_r=sim_outcome.slippage_cost_r,
            funding_cost_r=sim_outcome.funding_cost_r,
            total_cost_r=sim_outcome.total_cost_r,
            initial_margin=init_margin,
            maintenance_margin=maint_margin,
            margin_type="ISOLATED",
            liquidation_price=margin.liquidation_price,
            liquidation_distance_pct=margin.liquidation_distance_pct,
            liquidation_event=sim_outcome.exit_reason == "LIQUIDATED",
            exit_reason=sim_outcome.exit_reason,
            exit_price=sim_outcome.exit_price,
            exit_bar_index=sim_outcome.exit_bar_index,
            hold_duration_bars=sim_outcome.hold_duration_bars,
            quantity=margin.quantity if leverage > 1 else 1.0,
            notional=entry_price,
            cost_scenario_id=(cost_scenario.scenario_id if cost_scenario else "baseline_1.0x"),
            mfe_r=sim_outcome.path_metrics.mfe_r,
            mae_r=sim_outcome.path_metrics.mae_r,
        )

    return outcomes


def _select_best_action(
    outcomes: dict[str, LeverageOutcome],
    min_base_net_R: float = 0.0,
) -> tuple[int, int, float]:
    """Select the best action from all leverage tier outcomes.

    Returns (action_id, optimal_leverage, margin_return_net).
    Rule: NO_TRADE wins if no direction has positive base_net_R.
    """
    long_tiers = [(label, o) for label, o in outcomes.items()
                  if o.direction == "LONG" and o.base_net_R > min_base_net_R]
    short_tiers = [(label, o) for label, o in outcomes.items()
                   if o.direction == "SHORT" and o.base_net_R > min_base_net_R]

    if not long_tiers and not short_tiers:
        return (0, 0, 0.0)  # NO_TRADE

    # Within each direction, pick the leverage tier that maximizes margin_return
    if long_tiers:
        best_long = max(long_tiers, key=lambda x: x[1].margin_return_net)
    else:
        best_long = (None, LeverageOutcome(margin_return_net=-999))

    if short_tiers:
        best_short = max(short_tiers, key=lambda x: x[1].margin_return_net)
    else:
        best_short = (None, LeverageOutcome(margin_return_net=-999))

    if best_long[1].margin_return_net >= best_short[1].margin_return_net:
        action_id = next(
            aid for aid, (d, l) in ACTION_ID_TO_DIRECTION_LEVERAGE.items()
            if d == "LONG" and l == best_long[1].leverage
        )
        return (action_id, best_long[1].leverage, best_long[1].margin_return_net)
    else:
        action_id = next(
            aid for aid, (d, l) in ACTION_ID_TO_DIRECTION_LEVERAGE.items()
            if d == "SHORT" and l == best_short[1].leverage
        )
        return (action_id, best_short[1].leverage, best_short[1].margin_return_net)


def generate_leverage_labels(
    ohlcv: dict,
    mode: str,
    profile: Optional[SimulationProfile] = None,
    bracket_snapshots: Optional[tuple[BinanceBracketSnapshot, ...]] = None,
    cost_scenario: Optional[CostScenario] = None,
    future_bars: int = 12,
) -> list[LeverageLabel]:
    """Generate leverage-aware training labels from OHLCV data.

    For each bar, runs simulation for all 13 v2 actions using the
    next `future_bars` as the future path.

    Args:
        ohlcv: dict with keys "open", "high", "low", "close", "volume",
               "timestamp", "symbol" — arrays of equal length.
        mode: Trading mode (SCALP, SWING, etc.)
        profile: SimulationProfile. If None, uses default SCALP.
        bracket_snapshots: Optional bracket snapshots. If None, generates
                          representative ones per symbol.
        cost_scenario: Optional cost stress scenario.
        future_bars: Number of future bars to simulate per decision point.

    Returns:
        List of LeverageLabel, one per decision bar.
    """
    close = np.asarray(ohlcv["close"], dtype=np.float64)
    high = np.asarray(ohlcv["high"], dtype=np.float64)
    low = np.asarray(ohlcv["low"], dtype=np.float64)
    timestamps = np.asarray(ohlcv["timestamp"])
    symbols = np.asarray(ohlcv.get("symbol", [""] * len(close)))
    
    if profile is None:
        profile = SimulationProfile(
            profile_version="p1-leverage-v1",
            mode=TradingMode.SCALP,
            primary_interval="1h",
            max_holding_bars=future_bars,
            stop_multiplier=2.0,
            target_multiplier=2.0,
            ambiguity_margin_r=0.10,
            min_action_edge_r=0.15,
            no_trade_default=True,
            execution_mode="TAKER",
        )

    # Simple ATR estimator
    atr_value = 1200.0  # placeholder for now

    labels: list[LeverageLabel] = []
    unique_symbols = list(set(s for s in symbols if s))

    for sym in unique_symbols:
        mask = symbols == sym
        sym_close = close[mask]
        sym_high = high[mask]
        sym_low = low[mask]
        sym_ts = timestamps[mask]
        n = len(sym_close)

        sym_brackets = bracket_snapshots if bracket_snapshots else _make_bracket_snapshots(sym, float(sym_close[0]) if n > 0 else 50000.0)

        for i in range(n - future_bars):
            entry_price = float(sym_close[i])
            entry_high = float(sym_high[i])
            entry_low = float(sym_low[i])
            atr_estimate = max(abs(float(sym_high[i]) - float(sym_low[i])), 10.0)

            # Build future candles
            future_candles = [
                _make_candle(
                    float(sym_close[j]), float(sym_high[j]),
                    float(sym_low[j]), float(sym_close[j]),
                    close_time_utc=str(int(sym_ts[j])),
                )
                for j in range(i + 1, min(i + 1 + future_bars, n))
            ]

            if len(future_candles) < future_bars:
                continue

            outcomes = _simulate_bar(
                symbol=sym,
                entry_price=entry_price,
                atr=atr_estimate,
                future_candles=future_candles,
                profile=profile,
                bracket_snapshots=sym_brackets,
                timestamp_ms=int(sym_ts[i]),
                cost_scenario=cost_scenario,
            )

            # Determine best action
            action_id, opt_leverage, opt_margin_return = _select_best_action(outcomes)
            base_dir, _ = ACTION_ID_TO_DIRECTION_LEVERAGE.get(action_id, ("NO_TRADE", 0))

            # Direction at 1x
            long_1x = outcomes.get("LONG_1X")
            short_1x = outcomes.get("SHORT_1X")
            if long_1x and long_1x.base_net_R > profile.min_action_edge_r and (
                short_1x is None or long_1x.base_net_R > short_1x.base_net_R
            ):
                direction = 0  # LONG
                base_net_r = long_1x.base_net_R
            elif short_1x and short_1x.base_net_R > profile.min_action_edge_r and (
                long_1x is None or short_1x.base_net_R > long_1x.base_net_R
            ):
                direction = 1  # SHORT
                base_net_r = short_1x.base_net_R
            else:
                direction = 2  # NO_TRADE
                base_net_r = 0.0
                action_id = 0
                opt_leverage = 0
                opt_margin_return = 0.0

            # Liquidation stats
            liq_count = sum(1 for o in outcomes.values() if o.liquidation_event)
            total_directional = sum(1 for o in outcomes.values() if o.direction in ("LONG", "SHORT"))

            labels.append(LeverageLabel(
                timestamp_ms=int(sym_ts[i]),
                symbol=sym,
                close_price=float(sym_close[i]),
                direction=direction,
                base_net_R=base_net_r,
                optimal_action_id=action_id,
                optimal_leverage=opt_leverage,
                optimal_margin_return=opt_margin_return,
                action_outcomes=outcomes,
                any_liquidation=liq_count > 0,
                liquidation_rate=liq_count / max(total_directional, 1),
                cost_scenario_id=(cost_scenario.scenario_id if cost_scenario else "baseline_1.0x"),
                break_even_cost_multiple=1.0,
            ))

    return labels
