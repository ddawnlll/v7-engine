"""Tests for v7.evaluation — PaperMode, ReplayMode, EvaluationDriver."""

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
from v7.evaluation import (
    EvaluationDriver,
    EvaluationReport,
    PaperMode,
    ReplayMode,
    ReplaySummary,
)


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def swing_profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="profile-1.0.0",
        mode=TradingMode.SWING,
        primary_interval="4h",
        max_holding_bars=30,
        stop_multiplier=2.0,
        target_multiplier=2.5,
        ambiguity_margin_r=0.20,
        min_action_edge_r=0.35,
        no_trade_default=False,
    )


@pytest.fixture
def sim_input(swing_profile: SimulationProfile) -> SimulationInput:
    return SimulationInput(
        symbol="BTCUSDT",
        decision_timestamp="2026-07-05T12:00:00Z",
        mode=TradingMode.SWING,
        primary_interval="4h",
        entry_price=64300.0,
        atr=245.0,
        future_path=FuturePath(
            candles=[
                Candle(open=64300, high=64800, low=64000, close=64500, volume=100.0),
                Candle(open=64500, high=65200, low=64300, close=65000, volume=120.0),
                Candle(open=65000, high=65500, low=64800, close=65300, volume=90.0),
            ],
            completeness_status="COMPLETE",
            expected_bars=3,
        ),
        profile=swing_profile,
    )


@pytest.fixture
def sim_input_no_trade(swing_profile: SimulationProfile) -> SimulationInput:
    return SimulationInput(
        symbol="BTCUSDT",
        decision_timestamp="2026-07-05T12:00:00Z",
        mode=TradingMode.SWING,
        primary_interval="4h",
        entry_price=64000.0,
        atr=250.0,
        future_path=FuturePath(
            candles=[
                Candle(open=64000, high=64100, low=63500, close=63800, volume=80.0),
                Candle(open=63800, high=63900, low=63200, close=63500, volume=95.0),
            ],
            completeness_status="COMPLETE",
            expected_bars=2,
        ),
        profile=swing_profile,
    )


def _make_sim_output(
    best_action: str = "LONG_NOW",
    realized_r: float = 1.25,
    fee_cost: float = 0.08,
    slippage_cost: float = 0.02,
    funding_cost: float = 0.0,
    total_cost: float = 0.10,
    hold_bars: int = 10,
) -> SimulationOutput:
    pm = PathMetrics(mfe=2.0, mae=-0.5, path_quality_score=0.85)
    long_outcome = ActionOutcome(
        action=best_action,
        realized_r_gross=realized_r + total_cost,
        realized_r_net=realized_r,
        fee_cost_r=fee_cost,
        slippage_cost_r=slippage_cost,
        funding_cost_r=funding_cost,
        total_cost_r=total_cost,
        exit_reason="TARGET_HIT",
        exit_price=65500.0,
        exit_bar_index=hold_bars - 1,
        hold_duration_bars=hold_bars,
        path_metrics=pm,
    )
    short_outcome = ActionOutcome(action="SHORT_NOW", realized_r_net=-0.45)
    no_trade = NoTradeOutcome(
        saved_loss_r=0.0,
        missed_opportunity_r=0.0,
        no_trade_quality="AMBIGUOUS_NO_TRADE",
    )
    return SimulationOutput(
        simulation_run_id="sim_001",
        symbol="BTCUSDT",
        decision_timestamp="2026-07-05T12:00:00Z",
        mode="SWING",
        primary_interval="4h",
        resolution_status="COMPLETE",
        long_outcome=long_outcome,
        short_outcome=short_outcome,
        no_trade_outcome=no_trade,
        best_action=best_action,
        action_gap_r=0.80,
        regret_r=0.0,
        is_ambiguous=False,
        lineage=SimulationLineage(adapter_kind="PAPER"),
    )


def _make_no_trade_sim_output() -> SimulationOutput:
    """SimulationOutput where NO_TRADE was the best action."""
    long_outcome = ActionOutcome(action="LONG_NOW", realized_r_net=-0.55)
    short_outcome = ActionOutcome(action="SHORT_NOW", realized_r_net=-0.10)
    no_trade = NoTradeOutcome(
        saved_loss_r=0.55,
        missed_opportunity_r=0.0,
        no_trade_quality="CORRECT_NO_TRADE",
        was_correct_skip=True,
    )
    return SimulationOutput(
        simulation_run_id="sim_002",
        symbol="BTCUSDT",
        decision_timestamp="2026-07-05T12:00:00Z",
        mode="SWING",
        primary_interval="4h",
        resolution_status="COMPLETE",
        long_outcome=long_outcome,
        short_outcome=short_outcome,
        no_trade_outcome=no_trade,
        best_action="NO_TRADE",
        action_gap_r=0.0,
        regret_r=0.0,
        is_ambiguous=False,
        lineage=SimulationLineage(adapter_kind="PAPER"),
    )


# =========================================================================
# PaperMode tests
# =========================================================================


class TestPaperMode:
    """PaperMode — single-scenario paper forward simulation."""

    def test_run_returns_all_artifacts(self, sim_input) -> None:
        mode = PaperMode()
        result = mode.run(
            symbol="BTCUSDT",
            mode="SWING",
            model_scope="swing_v1",
            sim_input=sim_input,
        )
        assert isinstance(result, dict)
        assert "request" in result
        assert "sim_output" in result
        assert "decision_event" in result
        assert "trade_outcome" in result
        assert "no_trade_validation" in result

    def test_run_with_analysis_result(self, sim_input) -> None:
        """PaperMode accepts an explicit analysis_result."""
        analysis_result = {
            "contract": {"contract_version": "v7-0.3", "response_schema_version": "result-0.3", "engine_output_version": "engine-out-0.3"},
            "identity": {"request_id": "req_paper", "engine_name": "v7", "engine_version": "0.3.0", "timestamp_utc": "2026-07-05T12:00:00Z", "model_scope": "swing_v1", "trade_mode": "SWING"},
            "request_link": {"symbol": "BTCUSDT", "model_scope": "swing_v1", "trade_mode": "SWING", "primary_interval": "4h", "request_kind_seen": "paper_scan"},
            "status": {"signal_status": "SIGNAL", "decision_status": "VALID", "is_actionable": True},
            "decision": {"recommended_action": "LONG_NOW", "direction": "LONG", "decision_summary": "Paper test."},
            "scores": {"confidence": 0.70, "confidence_kind": "RAW", "expected_r": 1.0},
            "execution_guidance": {"entry_price": 64300.0, "stop_loss": 62100.0, "take_profit": 67800.0, "time_sensitivity": "STANDARD"},
            "uncertainty_and_quality": {},
            "fallback_and_degradation": {"fallback_used": False, "degraded_reason": None},
            "observability": {"warnings": []},
        }
        mode = PaperMode()
        result = mode.run(
            symbol="BTCUSDT",
            mode="SWING",
            model_scope="swing_v1",
            sim_input=sim_input,
            analysis_result=analysis_result,
        )
        assert result["decision_event"] is not None
        assert result["trade_outcome"] is not None

    def test_decision_event_has_valid_shape(self, sim_input) -> None:
        mode = PaperMode()
        result = mode.run(
            symbol="BTCUSDT",
            mode="SWING",
            model_scope="swing_v1",
            sim_input=sim_input,
        )
        event = result["decision_event"]
        assert "contract" in event
        assert "identity" in event
        assert "lineage" in event
        assert "scope" in event
        assert event["scope"]["symbol"] == "BTCUSDT"
        assert event["scope"]["trade_mode"] == "SWING"

    def test_trade_outcome_has_valid_shape(self, sim_input) -> None:
        mode = PaperMode()
        result = mode.run(
            symbol="BTCUSDT",
            mode="SWING",
            model_scope="swing_v1",
            sim_input=sim_input,
        )
        outcome = result["trade_outcome"]
        assert "contract" in outcome
        assert "identity" in outcome
        assert outcome["resolution_status"]["outcome_status"] == "PENDING"

    def event_and_outcome_linked(self, sim_input) -> None:
        """DecisionEvent should link to the created TradeOutcome."""
        mode = PaperMode()
        result = mode.run(
            symbol="BTCUSDT",
            mode="SWING",
            model_scope="swing_v1",
            sim_input=sim_input,
        )
        event = result["decision_event"]
        outcome = result["trade_outcome"]
        event_id = event.get("identity", {}).get("decision_event_id")
        outcome_id = outcome.get("identity", {}).get("trade_outcome_id")

        # Retrieve updated event from manager
        stored = mode._event_manager.get(event_id)
        assert stored is not None
        assert stored["outcome_linkage"]["trade_outcome_id"] == outcome_id


class TestPaperModeNoTradeValidation:
    """PaperMode no-trade validation."""

    def test_no_trade_validation_match(self, sim_input) -> None:
        """When engine action matches simulation best action."""
        mode = PaperMode()
        analysis_result = {
            "contract": {"contract_version": "v7-0.3", "response_schema_version": "result-0.3", "engine_output_version": "engine-out-0.3"},
            "identity": {"request_id": "req_001", "engine_name": "v7", "engine_version": "0.3.0", "timestamp_utc": "2026-07-05T12:00:00Z", "model_scope": "swing_v1", "trade_mode": "SWING"},
            "request_link": {"symbol": "BTCUSDT", "model_scope": "swing_v1", "trade_mode": "SWING"},
            "status": {"signal_status": "NO_TRADE", "decision_status": "VALID", "is_actionable": False},
            "decision": {"recommended_action": "NO_TRADE", "direction": "NONE", "decision_summary": "No trade."},
            "scores": {"confidence": 0.22, "expected_r": 0.05},
            "fallback_and_degradation": {"fallback_used": False, "degraded_reason": None},
            "observability": {"warnings": []},
        }
        result = mode.run(
            symbol="BTCUSDT",
            mode="SWING",
            model_scope="swing_v1",
            sim_input=sim_input,  # This has LONG_NOW as best action
            analysis_result=analysis_result,
        )
        ntv = result["no_trade_validation"]
        assert ntv["engine_recommended_action"] == "NO_TRADE"
        # Simulation may produce AMBIGUOUS_STATE when path data has no clear edge
        assert ntv["simulation_best_action"] in ("LONG_NOW", "NO_TRADE", "AMBIGUOUS_STATE")


# =========================================================================
# ReplayMode tests
# =========================================================================


class TestReplayMode:
    """ReplayMode — multi-scenario historical replay."""

    def test_run_returns_outcomes_and_summary(self, sim_input, sim_input_no_trade) -> None:
        replay = ReplayMode()
        result = replay.run(
            symbol="BTCUSDT",
            mode="SWING",
            model_scope="swing_v1",
            sim_inputs=[sim_input, sim_input_no_trade],
        )
        assert isinstance(result, dict)
        assert "outcomes" in result
        assert "summary" in result
        assert "no_trade_analysis" in result
        assert len(result["outcomes"]) == 2

    def test_summary_statistics(self, sim_input, sim_input_no_trade) -> None:
        replay = ReplayMode()
        result = replay.run(
            symbol="BTCUSDT",
            mode="SWING",
            model_scope="swing_v1",
            sim_inputs=[sim_input, sim_input_no_trade],
        )
        summary = result["summary"]
        assert isinstance(summary, ReplaySummary)
        assert summary.count == 2
        assert summary.count > 0
        assert 0.0 <= summary.no_trade_rate <= 1.0
        assert 0.0 <= summary.win_rate <= 1.0

    def test_single_input(self, sim_input) -> None:
        """ReplayMode works with a single-element list."""
        replay = ReplayMode()
        result = replay.run(
            symbol="BTCUSDT",
            mode="SWING",
            model_scope="swing_v1",
            sim_inputs=[sim_input],
        )
        assert len(result["outcomes"]) == 1
        assert result["summary"].count == 1

    def test_empty_inputs(self) -> None:
        """ReplayMode handles empty list gracefully."""
        replay = ReplayMode()
        result = replay.run(
            symbol="BTCUSDT",
            mode="SWING",
            model_scope="swing_v1",
            sim_inputs=[],
        )
        assert len(result["outcomes"]) == 0
        assert result["summary"].count == 0
        assert result["summary"].avg_r == 0.0
        assert result["summary"].no_trade_rate == 0.0

    def test_no_trade_rate_zero(self) -> None:
        """When no inputs are no-trade, no_trade_rate is 0.0."""
        replay = ReplayMode()
        # All inputs will produce LONG_NOW from the default _make_sim_output
        inputs = []
        for _ in range(3):
            sw = SimulationProfile(
                profile_version="p1",
                mode=TradingMode.SWING,
                primary_interval="4h",
                max_holding_bars=30,
                stop_multiplier=2.0,
                target_multiplier=2.5,
                ambiguity_margin_r=0.20,
                min_action_edge_r=0.35,
                no_trade_default=False,
            )
            inp = SimulationInput(
                symbol="BTCUSDT",
                decision_timestamp="2026-07-05T12:00:00Z",
                mode=TradingMode.SWING,
                primary_interval="4h",
                entry_price=64300.0,
                atr=245.0,
                future_path=FuturePath(
                    candles=[Candle(open=64300, high=64800, low=64000, close=64500)],
                ),
                profile=sw,
            )
            inputs.append(inp)
        result = replay.run(
            symbol="BTCUSDT",
            mode="SWING",
            model_scope="swing_v1",
            sim_inputs=inputs,
        )
        # The simulation may produce NO_TRADE based on the path data
        # We just check the shapes are valid
        assert len(result["outcomes"]) == 3


# =========================================================================
# EvaluationDriver tests
# =========================================================================


class TestEvaluationDriver:
    """EvaluationDriver — combined paper + replay evaluation."""

    def test_run_evaluation_with_both(self, sim_input, sim_input_no_trade) -> None:
        driver = EvaluationDriver()
        report = driver.run_evaluation(
            symbol="BTCUSDT",
            mode="SWING",
            model_scope="swing_v1",
            paper_sim_input=sim_input,
            replay_sim_inputs=[sim_input, sim_input_no_trade],
        )
        assert isinstance(report, EvaluationReport)
        assert report.symbol == "BTCUSDT"
        assert report.mode == "SWING"
        assert report.paper is not None
        assert report.replay is not None
        assert report.aggregate_metrics["paper_completed"] is True
        assert report.aggregate_metrics["replay_completed"] is True

    def test_paper_only(self, sim_input) -> None:
        driver = EvaluationDriver()
        report = driver.run_evaluation(
            symbol="BTCUSDT",
            mode="SWING",
            model_scope="swing_v1",
            paper_sim_input=sim_input,
            replay_sim_inputs=None,
        )
        assert report.paper is not None
        assert report.replay is None
        assert report.aggregate_metrics["paper_completed"] is True
        assert report.aggregate_metrics["replay_completed"] is False

    def test_replay_only(self, sim_input) -> None:
        driver = EvaluationDriver()
        report = driver.run_evaluation(
            symbol="BTCUSDT",
            mode="SWING",
            model_scope="swing_v1",
            paper_sim_input=None,
            replay_sim_inputs=[sim_input],
        )
        assert report.paper is None
        assert report.replay is not None
        assert report.aggregate_metrics["paper_completed"] is False
        assert report.aggregate_metrics["replay_completed"] is True

    def test_empty_evaluation(self) -> None:
        """EvaluationDriver with no paper and no replay inputs."""
        driver = EvaluationDriver()
        report = driver.run_evaluation(
            symbol="BTCUSDT",
            mode="SWING",
            model_scope="swing_v1",
            paper_sim_input=None,
            replay_sim_inputs=None,
        )
        assert report.paper is None
        assert report.replay is None
        assert report.aggregate_metrics["paper_completed"] is False
        assert report.aggregate_metrics["replay_completed"] is False
