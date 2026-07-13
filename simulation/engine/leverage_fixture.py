"""
Deterministic leverage parity fixture — P0 Economic-R Parity.

Produces LeverageOutcome records for all 13 v2 actions (NO_TRADE +
LONG/SHORT at 1x/2x/3x/5x/7x/10x) under explicit cost scenarios.

Key guarantees:
  - base_net_R does NOT increase merely because leverage increases.
  - Leveraged equity_return_net is tracked separately.
  - Liquidation is deterministic.
  - Cost scenarios are immutable — no monkey-patching.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from simulation.contracts.models import (
    ActionOutcome,
    BinanceBracketSnapshot,
    Candle,
    CostScenario,
    FuturePath,
    LeverageOutcome,
    PositionMargin,
    SimulationInput,
    SimulationOutput,
    SimulationProfile,
    TradingMode,
)
from simulation.engine.engine import simulate
from simulation.engine.margin import (
    ACTION_ID_TO_DIRECTION_LEVERAGE,
    ACTION_ID_TO_LABEL,
    compute_isolated_margin,
)


# ── Canonical cost scenarios ───────────────────────────────────────────

COST_SCENARIOS: dict[str, CostScenario] = {
    "baseline_1.0x": CostScenario(
        scenario_id="baseline_1.0x",
        fee_multiplier=1.0,
        slippage_multiplier=1.0,
        funding_multiplier=1.0,
        description="Baseline costs — no stress",
    ),
    "fee_1.5x": CostScenario(
        scenario_id="fee_1.5x",
        fee_multiplier=1.5,
        slippage_multiplier=1.0,
        funding_multiplier=1.0,
        description="Fees stressed 1.5x",
    ),
    "fee_2.0x": CostScenario(
        scenario_id="fee_2.0x",
        fee_multiplier=2.0,
        slippage_multiplier=1.0,
        funding_multiplier=1.0,
        description="Fees stressed 2.0x",
    ),
    "fee_3.0x": CostScenario(
        scenario_id="fee_3.0x",
        fee_multiplier=3.0,
        slippage_multiplier=1.0,
        funding_multiplier=1.0,
        description="Fees stressed 3.0x",
    ),
    "slippage_1.5x": CostScenario(
        scenario_id="slippage_1.5x",
        fee_multiplier=1.0,
        slippage_multiplier=1.5,
        funding_multiplier=1.0,
        description="Slippage stressed 1.5x",
    ),
    "slippage_2.0x": CostScenario(
        scenario_id="slippage_2.0x",
        fee_multiplier=1.0,
        slippage_multiplier=2.0,
        funding_multiplier=1.0,
        description="Slippage stressed 2.0x",
    ),
    "combined_2.0x": CostScenario(
        scenario_id="combined_2.0x",
        fee_multiplier=2.0,
        slippage_multiplier=2.0,
        funding_multiplier=2.0,
        description="All costs stressed 2.0x jointly",
    ),
    "combined_3.0x": CostScenario(
        scenario_id="combined_3.0x",
        fee_multiplier=3.0,
        slippage_multiplier=3.0,
        funding_multiplier=3.0,
        description="All costs stressed 3.0x jointly",
    ),
}


# ── Deterministic fixture data ─────────────────────────────────────────
#
# One symbol (BTCUSDT), one decision point, 12-bar future path.
# All values are deterministic — no randomness, no live data.

FIXTURE_SYMBOL = "BTCUSDT"
FIXTURE_ENTRY_PRICE = 50000.0
FIXTURE_ATR = 1200.0
FIXTURE_NOTIONAL = FIXTURE_ENTRY_PRICE  # 1 unit of base (50K USD notional)
FIXTURE_BRACKETS = (
    BinanceBracketSnapshot(
        symbol=FIXTURE_SYMBOL, tier=1, leverage=10, notional_cap_usd=50_000,
        maintenance_margin_ratio=0.004, bracket_snapshot_version="fixture-bracket-v1",
    ),
    BinanceBracketSnapshot(
        symbol=FIXTURE_SYMBOL, tier=2, leverage=10, notional_cap_usd=250_000,
        maintenance_margin_ratio=0.005, bracket_snapshot_version="fixture-bracket-v1",
    ),
)


def _make_candle(open_p: float, high_p: float, low_p: float, close_p: float, close_time: str = "") -> Candle:
    return Candle(open=open_p, high=high_p, low=low_p, close=close_p, close_time_utc=close_time)


# A gently rising path so both LONG and SHORT have plausible outcomes.
# LONG can hit target, SHORT can hit stop, TIME_EXIT is possible for NO_TRADE.
FIXTURE_CANDLES: list[Candle] = [
    _make_candle(50100, 50350, 49900, 50200, "2025-07-01T01:00:00Z"),
    _make_candle(50200, 50500, 50100, 50300, "2025-07-01T02:00:00Z"),
    _make_candle(50300, 50600, 50200, 50400, "2025-07-01T03:00:00Z"),
    _make_candle(50400, 50800, 50300, 50700, "2025-07-01T04:00:00Z"),  # HIGH=50800 → could hit target
    _make_candle(50700, 51000, 50500, 50800, "2025-07-01T05:00:00Z"),  # HIGH=51000
    _make_candle(50800, 51200, 50600, 51100, "2025-07-01T06:00:00Z"),  # HIGH=51200 → LONG target hit here
    _make_candle(51100, 51400, 50900, 51300, "2025-07-01T07:00:00Z"),
    _make_candle(51300, 51500, 51000, 51400, "2025-07-01T08:00:00Z"),
    _make_candle(51400, 51700, 51200, 51600, "2025-07-01T09:00:00Z"),
    _make_candle(51600, 51900, 51400, 51800, "2025-07-01T10:00:00Z"),
    _make_candle(51800, 52000, 51600, 51900, "2025-07-01T11:00:00Z"),
    _make_candle(51900, 52100, 51700, 52000, "2025-07-01T12:00:00Z"),
]


def make_fixture_profile() -> SimulationProfile:
    """Return a SCALP profile tuned for the deterministic fixture."""
    return SimulationProfile(
        profile_version="fixture-1.0.0",
        mode=TradingMode.SCALP,
        primary_interval="1h",
        max_holding_bars=12,
        stop_multiplier=2.0,
        target_multiplier=2.0,
        ambiguity_margin_r=0.10,
        min_action_edge_r=0.15,
        no_trade_default=True,
        stop_method="atr_wide",
        target_method="atr_wide",
        mae_penalty_weight=2.0,
        cost_penalty_weight=2.0,
        time_penalty_weight=1.5,
        funding_rate=0.0,
        execution_mode="TAKER",
    )


def make_fixture_input(profile: SimulationProfile | None = None) -> SimulationInput:
    """Build the deterministic SimulationInput for the fixture."""
    if profile is None:
        profile = make_fixture_profile()

    future_path = FuturePath(
        candles=list(FIXTURE_CANDLES),
        completeness_status="COMPLETE",
        expected_bars=12,
    )

    return SimulationInput(
        symbol=FIXTURE_SYMBOL,
        decision_timestamp="2025-07-01T00:00:00Z",
        mode=profile.mode,
        primary_interval=profile.primary_interval,
        entry_price=FIXTURE_ENTRY_PRICE,
        atr=FIXTURE_ATR,
        future_path=future_path,
        profile=profile,
        simulation_family_version="simfam-1.0.0",
        cost_model_version="cost-1.1.0",
        bracket_snapshots=FIXTURE_BRACKETS,
        notional_quote=FIXTURE_NOTIONAL,
    )


# ── Core fixture generator ─────────────────────────────────────────────


def _apply_cost_scenario_to_fees(
    base_fee_r: float,
    base_slippage_r: float,
    base_funding_r: float,
    scenario: CostScenario,
) -> tuple[float, float, float]:
    """Apply cost scenario multipliers to base cost components."""
    return (
        base_fee_r * scenario.fee_multiplier,
        base_slippage_r * scenario.slippage_multiplier,
        base_funding_r * scenario.funding_multiplier,
    )


def generate_leverage_fixture(
    profile: SimulationProfile | None = None,
    scenarios: Sequence[CostScenario] | None = None,
) -> list[LeverageOutcome]:
    """Generate LeverageOutcome records for all 13 actions × cost scenarios.

    This is the canonical P0 parity fixture generator.

    Args:
        profile: SimulationProfile for the fixture. Defaults to make_fixture_profile().
        scenarios: Cost scenarios to run. Defaults to baseline only.

    Returns:
        List of LeverageOutcome records, one per (action_id, scenario).
    """
    if profile is None:
        profile = make_fixture_profile()
    if scenarios is None:
        scenarios = [COST_SCENARIOS["baseline_1.0x"]]

    outcomes: list[LeverageOutcome] = []

    for action_id in range(13):
        direction, leverage = ACTION_ID_TO_DIRECTION_LEVERAGE[action_id]
        action_label = ACTION_ID_TO_LABEL[action_id]

        if action_id == 0:  # NO_TRADE
            for scenario in scenarios:
                outcomes.append(LeverageOutcome(
                    action_label="NO_TRADE",
                    direction="NO_TRADE",
                    leverage=0,
                    base_net_R=0.0,
                    realized_r_gross=0.0,
                    equity_return_net=0.0,
                    fee_cost_r=0.0,
                    slippage_cost_r=0.0,
                    funding_cost_r=0.0,
                    total_cost_r=0.0,
                    initial_margin=0.0,
                    maintenance_margin=0.0,
                    margin_type="ISOLATED",
                    liquidation_price=None,
                    liquidation_distance_pct=0.0,
                    liquidation_event=False,
                    exit_reason="NO_TRADE",
                    exit_price=0.0,
                    exit_bar_index=0,
                    hold_duration_bars=0,
                    quantity=0.0,
                    notional=0.0,
                    cost_scenario_id=scenario.scenario_id,
                ))
            continue

        for scenario in scenarios:
            # Rerun canonical simulation for every cost scenario and leverage.
            # The only P0 fixture shortcut is a deterministic bracket snapshot.
            action_profile = replace(profile, leverage=leverage)
            action_input = replace(
                make_fixture_input(action_profile), cost_scenario=scenario,
            )
            sim_output = simulate(action_input)
            sim_outcome = sim_output.long_outcome if direction == "LONG" else sim_output.short_outcome
            margin = compute_isolated_margin(
                leverage=leverage, entry_price=FIXTURE_ENTRY_PRICE,
                notional=FIXTURE_NOTIONAL, direction=direction,
                bracket=(FIXTURE_BRACKETS[0] if leverage > 1 else None),
            )
            risk_quote = FIXTURE_ATR * profile.stop_multiplier * margin.quantity
            quote_pnl = sim_outcome.realized_r_net * risk_quote
            init_margin_val = margin.initial_margin_ratio * margin.notional
            margin_return = quote_pnl / init_margin_val if init_margin_val > 0 else 0.0

            outcomes.append(LeverageOutcome(
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
                initial_margin=margin.initial_margin_ratio * FIXTURE_NOTIONAL,
                maintenance_margin=margin.maintenance_margin_ratio * FIXTURE_NOTIONAL,
                margin_type="ISOLATED",
                liquidation_price=margin.liquidation_price,
                liquidation_distance_pct=margin.liquidation_distance_pct,
                liquidation_event=sim_outcome.exit_reason == "LIQUIDATED",
                exit_reason=sim_outcome.exit_reason,
                exit_price=sim_outcome.exit_price,
                exit_bar_index=sim_outcome.exit_bar_index,
                hold_duration_bars=sim_outcome.hold_duration_bars,
                quantity=margin.quantity,
                notional=FIXTURE_NOTIONAL,
                cost_scenario_id=scenario.scenario_id,
                mfe_r=sim_outcome.path_metrics.mfe_r,
                mae_r=sim_outcome.path_metrics.mae_r,
            ))

    return outcomes


def base_net_R_is_leverage_invariant(outcomes: list[LeverageOutcome]) -> bool:
    """Verify that base_net_R does not inflate with leverage.

    For each direction, all non-zero-leverage outcomes should have
    the same base_net_R as the 1x outcome.
    """
    # Extract 1x base_net_R for each direction
    long_1x = None
    short_1x = None
    for o in outcomes:
        if o.leverage == 1 and o.direction == "LONG" and o.cost_scenario_id == "baseline_1.0x":
            long_1x = o.base_net_R
        if o.leverage == 1 and o.direction == "SHORT" and o.cost_scenario_id == "baseline_1.0x":
            short_1x = o.base_net_R

    for o in outcomes:
        if o.direction == "NO_TRADE":
            continue
        if o.cost_scenario_id != "baseline_1.0x":
            continue
        if o.direction == "LONG" and long_1x is not None:
            if abs(o.base_net_R - long_1x) > 1e-12:
                return False
        if o.direction == "SHORT" and short_1x is not None:
            if abs(o.base_net_R - short_1x) > 1e-12:
                return False

    return True
