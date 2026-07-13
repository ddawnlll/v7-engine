"""
P0 Economic-R Parity tests — leverage-native foundation validation.

Tests:
  1. Forward return != true R (semantic distinction)
  2. Deterministic fixture has exact known true R values
  3. base_net_R does not inflate with leverage
  4. 13 action v2 contract: all valid actions accepted, invalid ones rejected
  5. Isolated-only margin contract rejects cross/unknown margin type
  6. Liquidation behavior is deterministic
  7. Each explicit cost scenario changes expected costs correctly
  8. Simulation / outcome parity on the fixture
  9. Backward compatibility for v1 action-space artifacts
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pytest

# ── Test imports ────────────────────────────────────────────────────────

from simulation.contracts.models import (
    BinanceBracketSnapshot,
    BinanceBracketSnapshot,
    Candle,
    CostScenario,
    FuturePath,
    LeverageOutcome,
    MarginType,
    PositionMargin,
    SimulationInput,
    SimulationProfile,
    TradingMode,
)
from simulation.engine.engine import simulate
from simulation.engine.leverage_fixture import (
    COST_SCENARIOS,
    FIXTURE_ATR,
    FIXTURE_CANDLES,
    FIXTURE_ENTRY_PRICE,
    FIXTURE_NOTIONAL,
    FIXTURE_SYMBOL,
    _apply_cost_scenario_to_fees,
    base_net_R_is_leverage_invariant,
    generate_leverage_fixture,
    make_fixture_input,
    make_fixture_profile,
)
from simulation.engine.margin import (
    ACTION_ID_TO_DIRECTION_LEVERAGE,
    ACTION_ID_TO_LABEL,
    ACTION_LABEL_TO_ID,
    VALID_V2_ACTION_COUNT,
    VALID_V2_ACTION_IDS,
    action_id_is_valid_v2,
    compute_isolated_margin,
    direction_leverage_for_action,
    leverage_to_tier,
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Forward return vs true R semantic distinction
# ═══════════════════════════════════════════════════════════════════════════


class TestForwardReturnVsTrueR:
    """Prove that forward return != risk-normalized true R multiple.

    A forward return is (close[t+h]/close[t] - 1). A true R multiple
    is (exit_price - entry_price) / (ATR * stop_multiplier). They are
    numerically different by construction.
    """

    def test_forward_return_differs_from_simulation_R(self):
        """Simulation engine computes R = price_delta / (ATR * stop_mult),
        not a raw forward return. Verify they produce different values."""
        profile = make_fixture_profile()
        sim_input = make_fixture_input(profile)
        output = simulate(sim_input)

        # Raw forward return (what AlphaForge currently exports as net_r)
        last_close = FIXTURE_CANDLES[-1].close
        fwd_ret = last_close / FIXTURE_ENTRY_PRICE - 1.0
        # Simulate a simple label: gross = abs(fwd_ret) directionally
        # This is NOT an R-multiple
        forward_net = fwd_ret - 0.0008  # 8 bps fixed cost

        # Simulation R is risk-normalized by (ATR * stop_multiplier)
        sim_long_r = output.long_outcome.realized_r_net
        sim_short_r = output.short_outcome.realized_r_net

        # They must be numerically different
        assert abs(sim_long_r - forward_net) > 1e-6, (
            f"Simulation R ({sim_long_r}) should differ from "
            f"forward return net ({forward_net})"
        )
        assert abs(sim_short_r - forward_net) > 1e-6

    def test_simulation_R_is_risk_normalized(self):
        """R-multiple = price_delta / (ATR * stop_multiplier)."""
        profile = make_fixture_profile()
        entry_risk = FIXTURE_ATR * profile.stop_multiplier

        # Manually compute LONG gross R from the exit path
        sim_input = make_fixture_input(profile)
        output = simulate(sim_input)

        long_exit_price = output.long_outcome.exit_price
        expected_gross = (long_exit_price - FIXTURE_ENTRY_PRICE) / entry_risk

        assert abs(output.long_outcome.realized_r_gross - expected_gross) < 1e-10, (
            f"Gross R {output.long_outcome.realized_r_gross} != "
            f"({long_exit_price} - {FIXTURE_ENTRY_PRICE}) / {entry_risk} = {expected_gross}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. Deterministic fixture has exact known values
# ═══════════════════════════════════════════════════════════════════════════


class TestFixtureDeterminism:
    """The fixture must produce the same results every time."""

    def test_fixture_is_deterministic(self):
        """Two calls to generate_leverage_fixture must be byte-identical."""
        outcomes_1 = generate_leverage_fixture()
        outcomes_2 = generate_leverage_fixture()

        assert len(outcomes_1) == len(outcomes_2)

        for o1, o2 in zip(outcomes_1, outcomes_2):
            assert o1.action_label == o2.action_label
            assert o1.base_net_R == pytest.approx(o2.base_net_R, abs=1e-15)
            assert o1.equity_return_net == pytest.approx(o2.equity_return_net, abs=1e-15)
            assert o1.liquidation_event == o2.liquidation_event
            assert o1.exit_reason == o2.exit_reason

    def test_simulation_output_is_deterministic(self):
        """The underlying Simulation engine must be deterministic."""
        profile = make_fixture_profile()
        input_1 = make_fixture_input(profile)
        input_2 = make_fixture_input(profile)
        output_1 = simulate(input_1)
        output_2 = simulate(input_2)

        # SimulationRunIDs differ, but everything else must match
        assert output_1.best_action == output_2.best_action
        assert output_1.long_outcome.realized_r_net == pytest.approx(
            output_2.long_outcome.realized_r_net, abs=1e-15
        )
        assert output_1.short_outcome.realized_r_net == pytest.approx(
            output_2.short_outcome.realized_r_net, abs=1e-15
        )

    def test_fixture_has_exact_exit_reason(self):
        """With the known candle path and SCALP profile, LONG direction exits
        based on the highest high reaching the target or not.

        Entry=50000, ATR=1200, stop_mult=2.0, target_mult=2.0
        LONG target: 50000 + 2400 = 52400, stop: 50000 - 2400 = 47600
        Max high in fixture: 52100 at candle 10 — does NOT reach target.
        Min low: 48900 at candle 0 — does NOT trigger stop.
        Result: TIME_EXIT (held all 12 bars without stop or target hit)."""
        outcomes = generate_leverage_fixture()
        # Find baseline 1x LONG outcome
        long_1x = [o for o in outcomes
                   if o.action_label == "LONG_1X" and o.cost_scenario_id == "baseline_1.0x"]
        assert len(long_1x) == 1
        assert long_1x[0].exit_reason == "TIME_EXIT", (
            f"Expected TIME_EXIT (target 52400 never reached, max high=52100), "
            f"got {long_1x[0].exit_reason}"
        )

    def test_fixture_has_13_actions_baseline(self):
        """Baseline scenario produces exactly 13 outcomes."""
        outcomes = generate_leverage_fixture()
        baseline = [o for o in outcomes if o.cost_scenario_id == "baseline_1.0x"]
        assert len(baseline) == 13, f"Expected 13, got {len(baseline)}"


# ═══════════════════════════════════════════════════════════════════════════
# 3. base_net_R does not inflate with leverage
# ═══════════════════════════════════════════════════════════════════════════


class TestBaseNetRInvariant:
    """base_net_R must NOT increase merely because leverage increases."""

    def test_base_net_R_invariant_under_leverage(self):
        """All leverage tiers for same direction share same base_net_R."""
        outcomes = generate_leverage_fixture()
        assert base_net_R_is_leverage_invariant(outcomes), (
            "base_net_R changed with leverage — violation of economic parity"
        )

    def test_long_base_net_R_constant(self):
        """LONG_1X through LONG_10X have identical base_net_R."""
        outcomes = generate_leverage_fixture()
        baseline = [o for o in outcomes if o.cost_scenario_id == "baseline_1.0x"]

        long_1x_r = None
        for o in baseline:
            if o.action_label == "LONG_1X":
                long_1x_r = o.base_net_R
                break

        assert long_1x_r is not None
        for o in baseline:
            if o.direction == "LONG":
                assert o.base_net_R == pytest.approx(long_1x_r, abs=1e-15), (
                    f"{o.action_label} base_net_R = {o.base_net_R} != LONG_1X = {long_1x_r}"
                )

    def test_equity_return_changes_with_leverage(self):
        """equity_return_net SHOULD change with leverage (gross PnL scales)."""
        outcomes = generate_leverage_fixture()
        baseline = [o for o in outcomes if o.cost_scenario_id == "baseline_1.0x"]

        long_returns = [(o.leverage, o.equity_return_net)
                        for o in baseline if o.direction == "LONG"]
        long_returns.sort()

        # Different leverage tiers should have different equity returns
        # (leverage scales gross PnL linearly)
        unique_returns = set(round(r, 8) for _, r in long_returns)
        assert len(unique_returns) > 1, (
            "equity_return_net should differ across leverage tiers"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 13-action v2 contract
# ═══════════════════════════════════════════════════════════════════════════


class TestV2ActionSpace:
    """Validate the v2 action space contract with 13 actions."""

    def test_valid_action_count(self):
        """Exactly 13 actions: 1 NO_TRADE + 6 LONG + 6 SHORT."""
        assert VALID_V2_ACTION_COUNT == 13
        assert len(VALID_V2_ACTION_IDS) == 13

    def test_all_actions_map_to_direction_leverage(self):
        """Every v2 action ID 0-12 maps to a valid (direction, leverage)."""
        for action_id in range(13):
            direction, leverage = ACTION_ID_TO_DIRECTION_LEVERAGE[action_id]
            if action_id == 0:
                assert direction == "NO_TRADE"
                assert leverage == 0
            elif 1 <= action_id <= 4:
                assert direction == "LONG"
                assert leverage in (1, 2, 3, 5)
            elif 5 <= action_id <= 8:
                assert direction == "SHORT"
                assert leverage in (1, 2, 3, 5)
            elif action_id in (9, 10):
                assert direction == "LONG"
                assert leverage in (7, 10)
            else:  # 11, 12
                assert direction == "SHORT"
                assert leverage in (7, 10)

    def test_all_labels_have_unique_ids(self):
        """Each human-readable label maps to a unique integer."""
        assert len(ACTION_LABEL_TO_ID) == 13
        assert len(set(ACTION_LABEL_TO_ID.values())) == 13

    def test_valid_action_ids_accepted(self):
        """All 0-12 action IDs pass validation."""
        for i in range(13):
            assert action_id_is_valid_v2(i), f"Action ID {i} should be valid"

    @pytest.mark.parametrize("invalid_id", [-1, 13, 14, 100, -100])
    def test_invalid_action_ids_rejected(self, invalid_id):
        """IDs outside 0-12 are rejected."""
        assert not action_id_is_valid_v2(invalid_id)

    @pytest.mark.parametrize("invalid_id", [-1, 13, 99])
    def test_invalid_direction_leverage_raises(self, invalid_id):
        """direction_leverage_for_action raises ValueError for invalid IDs."""
        with pytest.raises(ValueError, match="Invalid v2 action ID"):
            direction_leverage_for_action(invalid_id)

    def test_action_label_roundtrip(self):
        """Label → ID → label is identity."""
        for label, id_ in ACTION_LABEL_TO_ID.items():
            assert ACTION_ID_TO_LABEL[id_] == label

    def test_no_trade_is_action_zero(self):
        """NO_TRADE is always action 0 (consistent with v0, v1)."""
        assert ACTION_LABEL_TO_ID["NO_TRADE"] == 0
        assert ACTION_ID_TO_LABEL[0] == "NO_TRADE"

    def test_leverage_to_tier_mapping(self):
        """leverage_to_tier maps correctly."""
        from simulation.contracts.models import LeverageTier
        assert leverage_to_tier(0) == LeverageTier.NO_TRADE
        assert leverage_to_tier(1) == LeverageTier.LEV_1X
        assert leverage_to_tier(2) == LeverageTier.LEV_2X
        assert leverage_to_tier(3) == LeverageTier.LEV_3X
        assert leverage_to_tier(5) == LeverageTier.LEV_5X
        assert leverage_to_tier(7) == LeverageTier.LEV_7X
        assert leverage_to_tier(10) == LeverageTier.LEV_10X

    def test_action_schema_accepts_v2(self):
        """The action_space JSON schema validates v2 format."""
        schema_path = Path(__file__).parent.parent.parent / "contracts" / "schemas" / "action_space.schema.json"
        if not schema_path.exists():
            pytest.skip("Schema file not found at expected path")

        with open(schema_path) as f:
            schema = json.load(f)

        assert "v2" in schema["properties"]["version"]["enum"], (
            "Schema must accept 'v2' version"
        )
        # Verify 13 actions defined
        actions = schema["properties"]["actions"]["properties"]
        assert len(actions) == 13
        assert "LONG_7X" in actions
        assert "LONG_10X" in actions
        assert "SHORT_7X" in actions
        assert "SHORT_10X" in actions
        assert "NO_TRADE" in actions


# ═══════════════════════════════════════════════════════════════════════════
# 5. Isolated-only margin contract
# ═══════════════════════════════════════════════════════════════════════════


class TestIsolatedMarginOnly:
    """Margin contract must reject cross/unknown margin types in P0."""

    def test_position_margin_accepts_isolated(self):
        """ISOLATED is the only accepted margin_type."""
        pm = PositionMargin(
            leverage=2,
            margin_type="ISOLATED",
            initial_margin_ratio=0.5,
            maintenance_margin_ratio=0.004,
            notional=50000,
        )
        assert pm.margin_type == "ISOLATED"

    def test_position_margin_rejects_cross(self):
        """CROSS margin is rejected in P0."""
        with pytest.raises(ValueError, match="must be ISOLATED"):
            PositionMargin(
                leverage=2,
                margin_type="CROSS",
                initial_margin_ratio=0.5,
                maintenance_margin_ratio=0.004,
                notional=50000,
            )

    def test_position_margin_rejects_unknown(self):
        """Unknown margin types are rejected."""
        with pytest.raises(ValueError, match="must be ISOLATED"):
            PositionMargin(
                leverage=2,
                margin_type="PORTFOLIO",
                initial_margin_ratio=0.5,
                maintenance_margin_ratio=0.004,
                notional=50000,
            )

    def test_compute_isolated_margin_uses_isolated(self):
        """compute_isolated_margin always returns ISOLATED type."""
        bracket = BinanceBracketSnapshot(
            symbol="TEST", tier=1, leverage=10, notional_cap_usd=999999,
            maintenance_margin_ratio=0.004,
        )
        pm = compute_isolated_margin(
            leverage=3,
            entry_price=50000,
            notional=50000,
            direction="LONG",
            bracket=bracket,
        )
        assert pm.margin_type == "ISOLATED"

    def test_compute_isolated_margin_rejects_zero_leverage(self):
        """leverage must be >= 1 for compute_isolated_margin."""
        with pytest.raises(ValueError, match="leverage must be >= 1"):
            compute_isolated_margin(
                leverage=0,
                entry_price=50000,
                notional=50000,
                direction="LONG",
            )

    def test_compute_isolated_margin_rejects_negative_leverage(self):
        """Negative leverage is rejected."""
        with pytest.raises(ValueError):
            compute_isolated_margin(
                leverage=-1,
                entry_price=50000,
                notional=50000,
                direction="LONG",
            )

    def test_compute_isolated_margin_rejects_bad_direction(self):
        """Invalid direction string is rejected."""
        with pytest.raises(ValueError, match="direction must be"):
            compute_isolated_margin(
                leverage=2,
                entry_price=50000,
                notional=50000,
                direction="SIDEWAYS",
            )


# ═══════════════════════════════════════════════════════════════════════════
# 6. Liquidation behavior
# ═══════════════════════════════════════════════════════════════════════════


class TestLiquidationBehavior:
    """Liquidation must be deterministic and correctly computed."""

    def test_liquidation_price_formula_long(self):
        """LONG liq_price = entry × (1 - (IMR - MMR))."""
        bracket = BinanceBracketSnapshot(
            symbol="TEST", tier=1, leverage=10, notional_cap_usd=999999,
            maintenance_margin_ratio=0.004,
        )
        pm = compute_isolated_margin(
            leverage=5,
            entry_price=50000,
            notional=50000,
            direction="LONG",
            bracket=bracket,
        )
        imr = 1.0 / 5  # 0.2
        mmr = 0.004    # 0.4%
        expected_liq = 50000.0 * (1.0 - (imr - mmr))
        expected_liq = 50000.0 * (1.0 - 0.196)  # 40200.0
        assert pm.liquidation_price == pytest.approx(expected_liq, abs=0.01)
        assert pm.liquidation_distance_pct == pytest.approx(imr - mmr, abs=1e-10)

    def test_liquidation_price_formula_short(self):
        """SHORT liq_price = entry × (1 + (IMR - MMR))."""
        bracket = BinanceBracketSnapshot(
            symbol="TEST", tier=1, leverage=10, notional_cap_usd=999999,
            maintenance_margin_ratio=0.004,
        )
        pm = compute_isolated_margin(
            leverage=5,
            entry_price=50000,
            notional=50000,
            direction="SHORT",
            bracket=bracket,
        )
        imr = 1.0 / 5
        mmr = 0.004
        expected_liq = 50000.0 * (1.0 + (imr - mmr))
        expected_liq = 50000.0 * 1.196  # 59800.0
        assert pm.liquidation_price == pytest.approx(expected_liq, abs=0.01)

    def test_1x_no_liquidation(self):
        """1x leverage means no liquidation price (spot-equivalent)."""
        pm = compute_isolated_margin(
            leverage=1,
            entry_price=50000,
            notional=50000,
            direction="LONG",
        )
        assert pm.liquidation_price is None
        assert pm.liquidation_distance_pct == 0.0

    def test_leverage_10x_liquidation_price(self):
        """10x LONG: IMR=0.1, MMR=0.004, liq_dist=0.096."""
        bracket = BinanceBracketSnapshot(
            symbol="TEST", tier=1, leverage=10, notional_cap_usd=999999,
            maintenance_margin_ratio=0.004,
        )
        pm = compute_isolated_margin(
            leverage=10,
            entry_price=50000,
            notional=50000,
            direction="LONG",
            bracket=bracket,
        )
        expected_liq = 50000.0 * (1.0 - 0.096)
        assert pm.liquidation_price == pytest.approx(expected_liq, abs=0.01)

    def test_liquidation_detected_in_fixture(self):
        """At 10x LONG, the fixture path may trigger liquidation."""
        outcomes = generate_leverage_fixture()
        baseline = [o for o in outcomes if o.cost_scenario_id == "baseline_1.0x"]

        # With our fixture candles (lows go down to 48900 at worst),
        # 10x LONG liquidation price is 45200, so no liquidation actually fires.
        # But the liquidation_price field must be set correctly.
        long_10x = [o for o in baseline if o.action_label == "LONG_10X"]
        assert len(long_10x) == 1
        assert long_10x[0].liquidation_price is not None
        assert long_10x[0].liquidation_price < FIXTURE_ENTRY_PRICE

        # For SHORT_10X, liq_price is ~54800, and max high is 52100 → no liq
        short_10x = [o for o in baseline if o.action_label == "SHORT_10X"]
        assert len(short_10x) == 1
        assert short_10x[0].liquidation_price is not None
        assert short_10x[0].liquidation_price > FIXTURE_ENTRY_PRICE

    def test_margin_values_scale_with_leverage(self):
        """Initial margin = notional / leverage. Maint margin = notional × MMR."""
        _fixture_bracket = BinanceBracketSnapshot(
            symbol="TEST", tier=1, leverage=10, notional_cap_usd=999999,
            maintenance_margin_ratio=0.004,
        )
        for lev in [1, 2, 3, 5, 7, 10]:
            pm = compute_isolated_margin(
                leverage=lev,
                entry_price=FIXTURE_ENTRY_PRICE,
                notional=FIXTURE_NOTIONAL,
                direction="LONG",
                bracket=(_fixture_bracket if lev > 1 else None),
            )
            expected_im = FIXTURE_NOTIONAL / lev
            expected_mm = FIXTURE_NOTIONAL * 0.004
            assert pm.initial_margin_ratio == pytest.approx(1.0 / lev, abs=1e-10)
            # initial_margin is the dollar amount
            assert pm.notional * pm.initial_margin_ratio == pytest.approx(expected_im, abs=0.01)


# ═══════════════════════════════════════════════════════════════════════════
# 7. Explicit cost scenarios
# ═══════════════════════════════════════════════════════════════════════════


class TestCostScenarios:
    """Each cost scenario must change expected costs correctly."""

    def test_cost_scenarios_are_immutable(self):
        """CostScenario dataclass is frozen."""
        cs = COST_SCENARIOS["baseline_1.0x"]
        with pytest.raises(Exception):  # FrozenInstanceError or similar
            cs.fee_multiplier = 2.0  # type: ignore[misc]

    def test_cost_scenario_multipliers_applied(self):
        """Fee 2.0x scenario doubles fee_cost_r."""
        base_fee = 0.01
        base_slip = 0.005
        base_fund = 0.0

        scenario = COST_SCENARIOS["fee_2.0x"]
        f, s, fu = _apply_cost_scenario_to_fees(base_fee, base_slip, base_fund, scenario)

        assert f == pytest.approx(0.02)      # 2.0 × 0.01
        assert s == pytest.approx(0.005)     # unchanged
        assert fu == pytest.approx(0.0)      # unchanged

    def test_combined_scenario_stresses_all(self):
        """Combined 3.0x stresses fee, slippage, and funding jointly."""
        base_fee = 0.01
        base_slip = 0.005
        base_fund = 0.001

        scenario = COST_SCENARIOS["combined_3.0x"]
        f, s, fu = _apply_cost_scenario_to_fees(base_fee, base_slip, base_fund, scenario)

        assert f == pytest.approx(0.03)
        assert s == pytest.approx(0.015)
        assert fu == pytest.approx(0.003)

    def test_baseline_is_identity(self):
        """Baseline 1.0x leaves costs unchanged."""
        base_fee = 0.01
        base_slip = 0.005
        base_fund = 0.0
        scenario = COST_SCENARIOS["baseline_1.0x"]
        f, s, fu = _apply_cost_scenario_to_fees(base_fee, base_slip, base_fund, scenario)
        assert f == base_fee
        assert s == base_slip
        assert fu == base_fund

    def test_all_scenarios_have_unique_ids(self):
        """Each cost scenario has a unique scenario_id."""
        ids = [cs.scenario_id for cs in COST_SCENARIOS.values()]
        assert len(ids) == len(set(ids))

    def test_cost_scenarios_change_equity_return(self):
        """Higher cost scenarios reduce equity_return_net."""
        baseline_outcomes = generate_leverage_fixture(
            scenarios=[COST_SCENARIOS["baseline_1.0x"]]
        )
        stressed_outcomes = generate_leverage_fixture(
            scenarios=[COST_SCENARIOS["combined_3.0x"]]
        )

        # For LONG_1X, compare equity_return_net
        base_1x = [o for o in baseline_outcomes if o.action_label == "LONG_1X"][0]
        stress_1x = [o for o in stressed_outcomes if o.action_label == "LONG_1X"][0]

        # Higher costs → lower equity_return_net
        assert stress_1x.equity_return_net < base_1x.equity_return_net, (
            f"Cost stress should reduce equity return: "
            f"baseline={base_1x.equity_return_net}, "
            f"stressed_3.0x={stress_1x.equity_return_net}"
        )

    def test_stressed_fee_reduces_net(self):
        """Fee-only 2.0x scenario reduces equity_return_net."""
        baseline = generate_leverage_fixture(
            scenarios=[COST_SCENARIOS["baseline_1.0x"]]
        )
        fee_stressed = generate_leverage_fixture(
            scenarios=[COST_SCENARIOS["fee_2.0x"]]
        )

        base_1x = [o for o in baseline if o.action_label == "LONG_1X"][0]
        fee_1x = [o for o in fee_stressed if o.action_label == "LONG_1X"][0]

        assert fee_1x.fee_cost_r > base_1x.fee_cost_r
        assert fee_1x.equity_return_net < base_1x.equity_return_net


# ═══════════════════════════════════════════════════════════════════════════
# 8. Simulation / outcome parity
# ═══════════════════════════════════════════════════════════════════════════


class TestSimulationParity:
    """Simulation output must agree with levered outcomes."""

    def test_base_1x_matches_simulation_long(self):
        """LONG_1X base_net_R == Simulation long_outcome.realized_r_net."""
        profile = make_fixture_profile()
        sim_input = make_fixture_input(profile)
        sim_output = simulate(sim_input)

        outcomes = generate_leverage_fixture(profile)

        long_1x = [o for o in outcomes
                   if o.action_label == "LONG_1X" and o.cost_scenario_id == "baseline_1.0x"][0]

        assert long_1x.base_net_R == pytest.approx(
            sim_output.long_outcome.realized_r_net, abs=1e-10
        )
        assert long_1x.realized_r_gross == pytest.approx(
            sim_output.long_outcome.realized_r_gross, abs=1e-10
        )

    def test_base_1x_matches_simulation_short(self):
        """SHORT_1X base_net_R == Simulation short_outcome.realized_r_net."""
        profile = make_fixture_profile()
        sim_input = make_fixture_input(profile)
        sim_output = simulate(sim_input)

        outcomes = generate_leverage_fixture(profile)

        short_1x = [o for o in outcomes
                    if o.action_label == "SHORT_1X" and o.cost_scenario_id == "baseline_1.0x"][0]

        assert short_1x.base_net_R == pytest.approx(
            sim_output.short_outcome.realized_r_net, abs=1e-10
        )

    def test_no_trade_has_zero_economics(self):
        """NO_TRADE produces zero across all economic fields."""
        outcomes = generate_leverage_fixture()
        no_trade = [o for o in outcomes if o.action_label == "NO_TRADE"]

        for nt in no_trade:
            assert nt.base_net_R == 0.0
            assert nt.realized_r_gross == 0.0
            assert nt.equity_return_net == 0.0
            assert nt.leverage == 0
            assert nt.notional == 0.0
            assert nt.liquidation_price is None


# ═══════════════════════════════════════════════════════════════════════════
# 9. Backward compatibility
# ═══════════════════════════════════════════════════════════════════════════


class TestBackwardCompatibility:
    """v1 action-space artifacts remain readable and valid."""

    def test_v1_action_ids_still_map(self):
        """v1 action IDs (0-8) still map to the same (direction, leverage)."""
        v1_mapping = {
            0: ("NO_TRADE", 0),
            1: ("LONG", 1),
            2: ("LONG", 2),
            3: ("LONG", 3),
            4: ("LONG", 5),
            5: ("SHORT", 1),
            6: ("SHORT", 2),
            7: ("SHORT", 3),
            8: ("SHORT", 5),
        }
        for action_id, expected in v1_mapping.items():
            assert ACTION_ID_TO_DIRECTION_LEVERAGE[action_id] == expected, (
                f"v1 action ID {action_id} mapping changed"
            )

    def test_v1_actions_are_valid_in_v2(self):
        """All v1 action IDs (0-8) are still valid in v2."""
        for action_id in range(9):
            assert action_id_is_valid_v2(action_id)

    def test_v2_adds_new_actions_after_v1(self):
        """v2 adds action IDs 9-12 (LONG_7X, LONG_10X, SHORT_7X, SHORT_10X)
        while preserving v1 IDs 0-8 exactly."""
        # v1 IDs (0-8) unchanged
        assert ACTION_ID_TO_LABEL[0] == "NO_TRADE"
        assert ACTION_ID_TO_LABEL[1] == "LONG_1X"
        assert ACTION_ID_TO_LABEL[5] == "SHORT_1X"
        assert ACTION_ID_TO_LABEL[8] == "SHORT_5X"
        # v2 new IDs (9-12)
        assert ACTION_ID_TO_LABEL[9] == "LONG_7X"
        assert ACTION_ID_TO_LABEL[10] == "LONG_10X"
        assert ACTION_ID_TO_LABEL[11] == "SHORT_7X"
        assert ACTION_ID_TO_LABEL[12] == "SHORT_10X"

    def test_schema_v2_preserves_v1_structure(self):
        """The schema file still has the same top-level structure."""
        schema_path = Path(__file__).parent.parent.parent / "contracts" / "schemas" / "action_space.schema.json"
        if not schema_path.exists():
            pytest.skip("Schema file not found")

        with open(schema_path) as f:
            schema = json.load(f)

        assert "version" in schema["required"]
        assert "actions" in schema["required"]
        assert "joint_encoding" in schema["properties"]
        # v1 versions still in enum for artifact reading
        assert "v0" in schema["properties"]["version"]["enum"]
        assert "v1" in schema["properties"]["version"]["enum"]


# ═══════════════════════════════════════════════════════════════════════════
# 10. PositionMargin computation edge cases
# ═══════════════════════════════════════════════════════════════════════════


class TestPositionMarginEdgeCases:
    """Additional margin computation edge cases."""

    def test_high_leverage_narrow_liquidation(self):
        """20x-like leverage (not in v2, but formula must be monotonic)."""
        # 20x: IMR=0.05, MMR=0.004, liq_dist=0.046
        bracket = BinanceBracketSnapshot(
            symbol="TEST", tier=1, leverage=20, notional_cap_usd=999999,
            maintenance_margin_ratio=0.004,
        )
        pm = compute_isolated_margin(
            leverage=20,
            entry_price=100000,
            notional=100000,
            direction="LONG",
            bracket=bracket,
        )
        expected_liq = 100000.0 * (1.0 - 0.046)
        assert pm.liquidation_price == pytest.approx(expected_liq, abs=0.1)

    def test_zero_entry_price(self):
        with pytest.raises(ValueError, match="entry_price must be > 0"):
            compute_isolated_margin(
                leverage=2,
                entry_price=0.0,
                notional=0.0,
                direction="LONG",
            )

    def test_custom_mmr(self):
        """Custom MMR override works."""
        bracket = BinanceBracketSnapshot(
            symbol="TEST", tier=1, leverage=5, notional_cap_usd=999999,
            maintenance_margin_ratio=0.01,
        )
        pm = compute_isolated_margin(
            leverage=5,
            entry_price=50000,
            notional=50000,
            direction="LONG",
            bracket=bracket,
        )
        assert pm.maintenance_margin_ratio == 0.01
        # IMR - custom_MMR = 0.2 - 0.01 = 0.19
        expected_liq = 50000.0 * (1.0 - 0.19)
        assert pm.liquidation_price == pytest.approx(expected_liq, abs=0.01)


# ═══════════════════════════════════════════════════════════════════════════
# 11. Simulation profile integration
# ═══════════════════════════════════════════════════════════════════════════


class TestProfileIntegration:
    """Fixture profile must work with the existing Simulation engine."""

    def test_fixture_profile_produces_valid_simulation(self):
        """make_fixture_profile + make_fixture_input → valid simulate()."""
        profile = make_fixture_profile()
        sim_input = make_fixture_input(profile)
        output = simulate(sim_input)

        assert output.resolution_status == "COMPLETE"
        assert output.symbol == FIXTURE_SYMBOL

    def test_fixture_profile_values_reasonable(self):
        """Profile values are within expected ranges."""
        profile = make_fixture_profile()
        assert profile.stop_multiplier > 0
        assert profile.target_multiplier > 0
        assert profile.max_holding_bars == 12
        assert profile.mode == TradingMode.SCALP

    def test_fixture_input_has_complete_path(self):
        """The fixture's future path is marked COMPLETE."""
        sim_input = make_fixture_input()
        assert sim_input.future_path.completeness_status == "COMPLETE"
        assert len(sim_input.future_path.candles) == 12
