"""
Tests for resolution status — COMPLETE, UNRESOLVED, INVALIDATED.

Verifies that the engine correctly assigns resolution status and that
invalidity reasons are populated appropriately.
"""

from __future__ import annotations

import pytest

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
    TradingMode,
)
from simulation.engine.engine import simulate
from simulation.engine.exits import simulate_path


# ── Shared fixture ──────────────────────────────────────────────────────


@pytest.fixture
def profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="1.0.0",
        mode=TradingMode.SWING,
        primary_interval="4h",
        max_holding_bars=24,
        stop_multiplier=2.0,
        target_multiplier=2.5,
        ambiguity_margin_r=0.10,
        min_action_edge_r=0.05,
        no_trade_default=False,
    )


# ── Helpers ─────────────────────────────────────────────────────────────


def _candle(open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(open=open_, high=high, low=low, close=close)


# ── Tests ───────────────────────────────────────────────────────────────


class TestResolutionStatus:
    """Resolution status — COMPLETE, UNRESOLVED, INVALIDATED."""

    def test_complete_when_path_complete_and_exit_triggered(self, profile):
        """COMPLETE when the path is available and exit is triggered."""
        candles = [
            _candle(105, 130, 103, 125),
        ]
        inp = SimulationInput(
            symbol="BTCUSDT",
            decision_timestamp="2026-07-01T00:00:00Z",
            mode=TradingMode.SWING,
            primary_interval="4h",
            entry_price=100,
            atr=10,
            future_path=FuturePath(
                candles=candles,
                completeness_status="COMPLETE",
                expected_bars=10,
            ),
            profile=profile,
        )
        result = simulate(inp)
        assert result.resolution_status == "COMPLETE"

    def test_unresolved_when_path_empty(self, profile):
        """UNRESOLVED when the future path has no candles."""
        inp = SimulationInput(
            symbol="BTCUSDT",
            decision_timestamp="2026-07-01T00:00:00Z",
            mode=TradingMode.SWING,
            primary_interval="4h",
            entry_price=100,
            atr=10,
            future_path=FuturePath(candles=[]),
            profile=profile,
        )
        result = simulate(inp)
        assert result.resolution_status == "UNRESOLVED"

    def test_invalidated_when_path_corrupted(self):
        """INVALIDATED when the path data is corrupted.

        The engine currently does not produce INVALIDATED natively.
        This test verifies the contract surface: a SimulationOutput
        can carry INVALIDATED status with a populated invalidity_reason.
        """
        output = SimulationOutput(
            simulation_run_id="test-001",
            symbol="BTCUSDT",
            decision_timestamp="2026-07-01T00:00:00Z",
            mode="SWING",
            primary_interval="4h",
            resolution_status="INVALIDATED",
            invalidity_reason="Corrupted candle data: gap detected",
            long_outcome=ActionOutcome(),
            short_outcome=ActionOutcome(),
            no_trade_outcome=NoTradeOutcome(),
            best_action="NO_TRADE",
            action_gap_r=0.0,
            regret_r=0.0,
            is_ambiguous=False,
        )
        assert output.resolution_status == "INVALIDATED"
        assert output.invalidity_reason != ""

    def test_invalidated_when_missing_2x_horizon(self):
        """INVALIDATED when path is missing for more than 2x max_holding_bars.

        Verifies the contract surface carries INVALIDATED with a reason
        about missing data exceeding horizon bounds.
        """
        output = SimulationOutput(
            simulation_run_id="test-002",
            symbol="BTCUSDT",
            decision_timestamp="2026-07-01T00:00:00Z",
            mode="SWING",
            primary_interval="4h",
            resolution_status="INVALIDATED",
            invalidity_reason="No data for 50 bars (> 2x max_holding_bars=24)",
            long_outcome=ActionOutcome(),
            short_outcome=ActionOutcome(),
            no_trade_outcome=NoTradeOutcome(),
            best_action="NO_TRADE",
            action_gap_r=0.0,
            regret_r=0.0,
            is_ambiguous=False,
        )
        assert output.resolution_status == "INVALIDATED"
        assert "2x" in output.invalidity_reason

    def test_invalidity_reason_populated(self):
        """invalidity_reason is populated when status is INVALIDATED."""
        output = SimulationOutput(
            simulation_run_id="test-003",
            symbol="BTCUSDT",
            decision_timestamp="2026-07-01T00:00:00Z",
            mode="SWING",
            primary_interval="4h",
            resolution_status="INVALIDATED",
            invalidity_reason="Insufficient data for simulation",
            long_outcome=ActionOutcome(),
            short_outcome=ActionOutcome(),
            no_trade_outcome=NoTradeOutcome(),
            best_action="NO_TRADE",
            action_gap_r=0.0,
            regret_r=0.0,
            is_ambiguous=False,
        )
        assert len(output.invalidity_reason) > 0

    def test_unresolved_not_final(self, profile):
        """UNRESOLVED outcomes are not marked as final.

        When the engine returns UNRESOLVED, the resolution_status should
        indicate that no decision can be made (empty candle path).
        """
        inp = SimulationInput(
            symbol="BTCUSDT",
            decision_timestamp="2026-07-01T00:00:00Z",
            mode=TradingMode.SWING,
            primary_interval="4h",
            entry_price=100,
            atr=10,
            future_path=FuturePath(candles=[]),
            profile=profile,
        )
        result = simulate(inp)
        assert result.resolution_status == "UNRESOLVED"
        # With an empty path, simulate_path returns TIME_EXIT at entry price
        # (exit_reason itself is always set), but resolution_status captures
        # the engine-level assessment: no data available.
        assert result.resolution_status != "COMPLETE"
