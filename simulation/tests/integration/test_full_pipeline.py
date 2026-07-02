"""
Integration tests for the full SimulationInput -> SimulationOutput pipeline.

Exercises the entire flow: profile resolution, exit simulation, cost
calculation, NO_TRADE quality, action selection, and lineage tracking.
"""

from __future__ import annotations

import pytest

from simulation.contracts.models import (
    Action,
    ActionOutcome,
    Candle,
    FuturePath,
    NoTradeOutcome,
    SimulationInput,
    SimulationLineage,
    SimulationOutput,
    SimulationProfile,
    TradingMode,
)
from simulation.engine.engine import simulate


# ── Helpers ─────────────────────────────────────────────────────────────────


def _candle(open_: float, high: float, low: float, close: float, volume: float = 1000.0) -> Candle:
    return Candle(open=open_, high=high, low=low, close=close, volume=volume)


def _swing_profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="swing-1.0.0",
        mode=TradingMode.SWING,
        primary_interval="4h",
        max_holding_bars=24,
        stop_multiplier=2.0,
        target_multiplier=2.5,
        ambiguity_margin_r=0.10,
        min_action_edge_r=0.05,
        no_trade_default=False,
    )


def _scalp_profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="scalp-1.0.0",
        mode=TradingMode.SCALP,
        primary_interval="1h",
        max_holding_bars=12,
        stop_multiplier=1.5,
        target_multiplier=1.5,
        ambiguity_margin_r=0.10,
        min_action_edge_r=0.15,
        no_trade_default=True,
    )


def _make_input(
    symbol: str = "BTCUSDT",
    mode: TradingMode = TradingMode.SWING,
    profile: SimulationProfile | None = None,
    candles: list[Candle] | None = None,
    entry_price: float = 100,
    atr: float = 10,
    family_version: str = "simfam-1.0.0",
) -> SimulationInput:
    if profile is None:
        profile = _swing_profile()
    if candles is None:
        candles = [
            _candle(105, 130, 103, 125),
        ]
    return SimulationInput(
        symbol=symbol,
        decision_timestamp="2026-07-01T00:00:00Z",
        mode=mode,
        primary_interval=profile.primary_interval,
        entry_price=entry_price,
        atr=atr,
        future_path=FuturePath(candles=candles),
        profile=profile,
        simulation_family_version=family_version,
    )


# ── Tests ───────────────────────────────────────────────────────────────────


class TestFullPipeline:
    """Full SimulationInput -> SimulationOutput pipeline integration tests."""

    # ── Test 1: Full pipeline valid ─────────────────────────────────────

    def test_full_simulation_output_valid(self):
        """Full SimulationInput -> SimulationOutput produces a valid, complete output."""
        inp = _make_input()
        result = simulate(inp)

        assert isinstance(result, SimulationOutput)
        assert result.simulation_run_id != ""
        assert result.symbol == "BTCUSDT"
        assert result.decision_timestamp == "2026-07-01T00:00:00Z"
        assert result.mode == "SWING"
        assert result.primary_interval == "4h"
        assert result.resolution_status == "COMPLETE"

    # ── Test 2: All three actions present ───────────────────────────────

    def test_all_three_actions_present(self):
        """Output contains LONG_NOW, SHORT_NOW, and NO_TRADE outcomes."""
        inp = _make_input()
        result = simulate(inp)

        assert isinstance(result.long_outcome, ActionOutcome)
        assert result.long_outcome.action == "LONG_NOW"

        assert isinstance(result.short_outcome, ActionOutcome)
        assert result.short_outcome.action == "SHORT_NOW"

        assert isinstance(result.no_trade_outcome, NoTradeOutcome)
        assert result.no_trade_outcome.no_trade_quality != ""

        # Best action must be one of the three or AMBIGUOUS_STATE
        assert result.best_action in (
            "LONG_NOW", "SHORT_NOW", "NO_TRADE", "AMBIGUOUS_STATE",
        )

    # ── Test 3: All lineage fields populated ────────────────────────────

    def test_all_lineage_fields_populated(self):
        """Every lineage field is non-empty after a simulation run."""
        inp = _make_input()
        result = simulate(inp)

        lineage = result.lineage
        assert isinstance(lineage, SimulationLineage)
        assert lineage.simulation_family_version == "simfam-1.0.0"
        assert lineage.simulation_profile_version != ""
        assert lineage.cost_model_version != ""
        assert lineage.fee_model_version != ""
        assert lineage.slippage_model_version != ""
        assert lineage.funding_model_version != ""
        assert lineage.horizon_family != ""
        assert lineage.stop_family != ""
        assert lineage.target_family != ""
        assert lineage.time_exit_family != ""
        assert lineage.adapter_kind == "TRAINING"

    # ── Test 4: Long/short same cost semantics ─────────────────────────

    def test_long_short_same_cost_semantics(self):
        """Long and short actions have identical fee and slippage costs for the same profile."""
        inp = _make_input()
        result = simulate(inp)

        # Both directions should pay the same fee and slippage for identical input
        assert result.long_outcome.fee_cost_r == pytest.approx(
            result.short_outcome.fee_cost_r, abs=1e-10
        )
        assert result.long_outcome.slippage_cost_r == pytest.approx(
            result.short_outcome.slippage_cost_r, abs=1e-10
        )
        # Total costs may differ due to different hold durations (funding)
        assert result.long_outcome.fee_cost_r > 0
        assert result.long_outcome.slippage_cost_r > 0

    # ── Test 5: Profile switching ───────────────────────────────────────

    def test_profile_switching_swing_vs_scalp(self):
        """SWING and SCALP profiles produce different mode parameters in output."""
        swing_inp = _make_input(mode=TradingMode.SWING, profile=_swing_profile())
        scalp_inp = _make_input(
            symbol="BTCUSDT",
            mode=TradingMode.SCALP,
            profile=_scalp_profile(),
            candles=[
                _candle(101, 102, 99, 101),
                _candle(101, 103, 100, 102),
                _candle(102, 104, 101, 103),
            ],
        )

        swing_result = simulate(swing_inp)
        scalp_result = simulate(scalp_inp)

        # Mode and interval differ
        assert swing_result.mode == "SWING"
        assert scalp_result.mode == "SCALP"
        assert swing_result.primary_interval == "4h"
        assert scalp_result.primary_interval == "1h"

        # Profiles differ in max_holding_bars
        # SCALP has tighter stop_multiplier -> different risk profile
        assert swing_result.lineage.simulation_profile_version == "swing-1.0.0"
        assert scalp_result.lineage.simulation_profile_version == "scalp-1.0.0"

    # ── Test 6: Multiple symbols ────────────────────────────────────────

    def test_multiple_symbols_produce_correct_outputs(self):
        """Multiple symbols each produce correct, independent outputs."""
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        results = []
        for sym in symbols:
            inp = _make_input(symbol=sym)
            results.append(simulate(inp))

        assert len(results) == 3
        for i, sym in enumerate(symbols):
            assert results[i].symbol == sym
            assert results[i].simulation_run_id != ""
            for j in range(i + 1, len(symbols)):
                assert results[i].simulation_run_id != results[j].simulation_run_id

    # ── Test 7: Zero-volume bar resolves ────────────────────────────────

    def test_zero_volume_bar_resolves(self):
        """A future path with zero-volume bars still resolves correctly."""
        candles = [
            _candle(101, 102, 99, 101, volume=0.0),
            _candle(101, 103, 100, 102, volume=0.0),
            _candle(102, 104, 101, 103, volume=0.0),
        ]
        inp = _make_input(candles=candles)
        result = simulate(inp)

        # Volume is a metadata field — engine should process the path regardless
        assert result.resolution_status == "COMPLETE"
        assert result.long_outcome.exit_reason is not None
        assert result.short_outcome.exit_reason is not None

    # ── Test 8: Single-bar path -> TIME_EXIT ────────────────────────────

    def test_single_bar_path_time_exit(self):
        """A single candle that does not hit stop or target produces TIME_EXIT."""
        candles = [
            _candle(101, 102, 99, 101),
        ]
        inp = _make_input(
            candles=candles,
            profile=SimulationProfile(
                profile_version="wide-1.0.0",
                mode=TradingMode.SWING,
                primary_interval="4h",
                max_holding_bars=24,
                stop_multiplier=2.0,
                # Far targets so the single bar doesn't trigger exit
                target_multiplier=20.0,
                ambiguity_margin_r=0.10,
                min_action_edge_r=0.05,
                no_trade_default=False,
            ),
        )
        result = simulate(inp)

        # Both directions should TIME_EXIT (bar doesn't hit stop=80 or target=300)
        assert result.long_outcome.exit_reason == "TIME_EXIT"
        assert result.short_outcome.exit_reason == "TIME_EXIT"
        # Zero-volume path resolves as COMPLETE
        assert result.resolution_status == "COMPLETE"

    # ── Test 9: Empty future path -> UNRESOLVED ─────────────────────────

    def test_empty_future_path_unresolved(self):
        """An empty future path produces UNRESOLVED resolution status."""
        inp = _make_input(candles=[])
        result = simulate(inp)

        assert result.resolution_status == "UNRESOLVED"
        # With no candles, the engine still produces ActionOutcome but marks it UNRESOLVED
        assert isinstance(result.long_outcome, ActionOutcome)
        assert isinstance(result.short_outcome, ActionOutcome)
        assert isinstance(result.no_trade_outcome, NoTradeOutcome)
        # Exit reason for empty path should still be set (TIME_EXIT at entry)
        assert result.long_outcome.exit_reason is not None
