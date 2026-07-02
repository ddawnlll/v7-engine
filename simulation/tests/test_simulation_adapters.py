"""Tests for simulation adapters — training, evaluation, replay, paper.

Verifies:
  - adapter_kind correctness per adapter
  - Output structure validity
  - Determinism (identical input → identical output fields)
  - No side effects (input unchanged after run)
  - Parity across adapters (same input → same output, differing only by adapter_kind)
"""

from __future__ import annotations

from dataclasses import replace
from typing import List

import pytest

from simulation.contracts.models import (
    Candle,
    FuturePath,
    SimulationInput,
    SimulationOutput,
    SimulationProfile,
    TradingMode,
)
from simulation.adapters.training_adapter import TrainingAdapter
from simulation.adapters.evaluation_adapter import EvaluationAdapter
from simulation.adapters.replay_driver import ReplayDriver
from simulation.adapters.paper_driver import PaperDriver


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_profile() -> SimulationProfile:
    """Standard SWING profile for testing."""
    return SimulationProfile(
        profile_version="1.0.0",
        mode=TradingMode.SWING,
        primary_interval="4h",
        max_holding_bars=24,
        stop_multiplier=2.0,
        target_multiplier=3.0,
        ambiguity_margin_r=0.1,
        min_action_edge_r=0.05,
        no_trade_default=False,
    )


def make_sim_input(
    profile: SimulationProfile,
    symbol: str = "BTCUSDT",
    entry_price: float = 50000.0,
    atr: float = 500.0,
    decision_idx: int = 0,
) -> SimulationInput:
    """Create a SimulationInput with a synthetic uptrend future path."""
    candles = [
        Candle(
            open=entry_price + i * 10,
            high=entry_price + i * 10 + 100,
            low=entry_price + i * 10 - 100,
            close=entry_price + i * 10 + 50,
        )
        for i in range(48)
    ]
    future_path = FuturePath(
        candles=candles,
        completeness_status="COMPLETE",
        expected_bars=48,
    )
    return SimulationInput(
        symbol=symbol,
        decision_timestamp=f"2024-01-01T00:00:{decision_idx:02d}",
        mode=profile.mode,
        primary_interval=profile.primary_interval,
        entry_price=entry_price,
        atr=atr,
        future_path=future_path,
        profile=profile,
    )


def assert_output_shape(output: SimulationOutput) -> None:
    """Verify a SimulationOutput has all expected fields populated."""
    assert isinstance(output, SimulationOutput)
    assert output.symbol, "symbol should be non-empty"
    assert output.decision_timestamp, "decision_timestamp should be non-empty"
    assert output.mode, "mode should be non-empty"
    assert output.resolution_status in ("COMPLETE", "UNRESOLVED", "INVALIDATED")
    assert output.best_action in (
        "LONG_NOW", "SHORT_NOW", "NO_TRADE", "AMBIGUOUS_STATE"
    )
    assert output.long_outcome is not None
    assert output.short_outcome is not None
    assert output.no_trade_outcome is not None
    assert output.lineage.adapter_kind, "adapter_kind should be non-empty"


def outputs_match_except_run_id(
    a: SimulationOutput, b: SimulationOutput,
) -> bool:
    """Return True if two outputs match except for simulation_run_id."""
    return (
        a.symbol == b.symbol
        and a.decision_timestamp == b.decision_timestamp
        and a.mode == b.mode
        and a.primary_interval == b.primary_interval
        and a.resolution_status == b.resolution_status
        and a.best_action == b.best_action
        and a.second_best_action == b.second_best_action
        and a.action_gap_r == b.action_gap_r
        and a.regret_r == b.regret_r
        and a.is_ambiguous == b.is_ambiguous
        and a.lineage.adapter_kind == b.lineage.adapter_kind
    )


# ---------------------------------------------------------------------------
# TrainingAdapter tests (4 tests)
# ---------------------------------------------------------------------------


class TestTrainingAdapter:
    """TrainingAdapter unit tests."""

    ADAPTER_KIND = "TRAINING"

    @pytest.fixture
    def adapter(self) -> TrainingAdapter:
        return TrainingAdapter()

    @pytest.fixture
    def sim_input(self, fixture_profile: SimulationProfile) -> SimulationInput:
        return make_sim_input(fixture_profile)

    def test_adapter_kind(
        self, adapter: TrainingAdapter, sim_input: SimulationInput,
    ):
        """Lineage adapter_kind should be TRAINING."""
        output = adapter.run(sim_input)
        assert output.lineage.adapter_kind == "TRAINING"

    def test_output_structure(
        self, adapter: TrainingAdapter, sim_input: SimulationInput,
    ):
        """Output should be a valid SimulationOutput with expected fields."""
        output = adapter.run(sim_input)
        assert_output_shape(output)
        assert output.resolution_status == "COMPLETE"

    def test_determinism(
        self, adapter: TrainingAdapter, sim_input: SimulationInput,
    ):
        """Same input should produce same output fields (modulo run_id)."""
        output1 = adapter.run(sim_input)
        output2 = adapter.run(sim_input)
        assert output1.simulation_run_id != output2.simulation_run_id, (
            "run_id should differ across calls"
        )
        assert outputs_match_except_run_id(output1, output2), (
            "outputs should match except for run_id"
        )

    def test_no_side_effects(
        self, adapter: TrainingAdapter, sim_input: SimulationInput,
    ):
        """Input should remain unchanged after adapter.run()."""
        original_entry = sim_input.entry_price
        original_atr = sim_input.atr
        original_symbol = sim_input.symbol
        original_ts = sim_input.decision_timestamp
        _ = adapter.run(sim_input)
        assert sim_input.entry_price == original_entry
        assert sim_input.atr == original_atr
        assert sim_input.symbol == original_symbol
        assert sim_input.decision_timestamp == original_ts


# ---------------------------------------------------------------------------
# EvaluationAdapter tests (4 tests)
# ---------------------------------------------------------------------------


class TestEvaluationAdapter:
    """EvaluationAdapter unit tests."""

    ADAPTER_KIND = "EVALUATION"

    @pytest.fixture
    def adapter(self) -> EvaluationAdapter:
        return EvaluationAdapter()

    @pytest.fixture
    def sim_input(self, fixture_profile: SimulationProfile) -> SimulationInput:
        return make_sim_input(fixture_profile)

    def test_adapter_kind(
        self, adapter: EvaluationAdapter, sim_input: SimulationInput,
    ):
        """Lineage adapter_kind should be EVALUATION."""
        output = adapter.run(sim_input)
        assert output.lineage.adapter_kind == "EVALUATION"

    def test_output_structure(
        self, adapter: EvaluationAdapter, sim_input: SimulationInput,
    ):
        """Output should be a valid SimulationOutput."""
        output = adapter.run(sim_input)
        assert_output_shape(output)

    def test_determinism(
        self, adapter: EvaluationAdapter, sim_input: SimulationInput,
    ):
        """Same input should produce same output fields (modulo run_id)."""
        output1 = adapter.run(sim_input)
        output2 = adapter.run(sim_input)
        assert output1.simulation_run_id != output2.simulation_run_id
        assert outputs_match_except_run_id(output1, output2)

    def test_no_side_effects(
        self, adapter: EvaluationAdapter, sim_input: SimulationInput,
    ):
        """Input should remain unchanged after adapter.run()."""
        original = replace(sim_input)
        _ = adapter.run(sim_input)
        assert sim_input.entry_price == original.entry_price
        assert sim_input.atr == original.atr
        assert sim_input.symbol == original.symbol


# ---------------------------------------------------------------------------
# ReplayDriver tests (4 tests)
# ---------------------------------------------------------------------------


class TestReplayDriver:
    """ReplayDriver unit tests."""

    @pytest.fixture
    def adapter(self) -> ReplayDriver:
        return ReplayDriver()

    @pytest.fixture
    def sim_input(self, fixture_profile: SimulationProfile) -> SimulationInput:
        return make_sim_input(fixture_profile)

    def test_adapter_kind(
        self, adapter: ReplayDriver, sim_input: SimulationInput,
    ):
        """Lineage adapter_kind should be REPLAY."""
        output = adapter.run(sim_input)
        assert output.lineage.adapter_kind == "REPLAY"

    def test_output_structure(
        self, adapter: ReplayDriver, sim_input: SimulationInput,
    ):
        """Output should be a valid SimulationOutput."""
        output = adapter.run(sim_input)
        assert_output_shape(output)

    def test_determinism(
        self, adapter: ReplayDriver, sim_input: SimulationInput,
    ):
        """Same input should produce same output fields (modulo run_id)."""
        output1 = adapter.run(sim_input)
        output2 = adapter.run(sim_input)
        assert output1.simulation_run_id != output2.simulation_run_id
        assert outputs_match_except_run_id(output1, output2)

    def test_no_side_effects(
        self, adapter: ReplayDriver, sim_input: SimulationInput,
    ):
        """Input should remain unchanged after adapter.run()."""
        original = replace(sim_input)
        _ = adapter.run(sim_input)
        assert sim_input.entry_price == original.entry_price
        assert sim_input.atr == original.atr
        assert sim_input.symbol == original.symbol


# ---------------------------------------------------------------------------
# PaperDriver tests (4 tests)
# ---------------------------------------------------------------------------


class TestPaperDriver:
    """PaperDriver unit tests."""

    @pytest.fixture
    def adapter(self) -> PaperDriver:
        return PaperDriver()

    @pytest.fixture
    def sim_input(self, fixture_profile: SimulationProfile) -> SimulationInput:
        return make_sim_input(fixture_profile)

    def test_adapter_kind(
        self, adapter: PaperDriver, sim_input: SimulationInput,
    ):
        """Lineage adapter_kind should be PAPER."""
        output = adapter.run(sim_input)
        assert output.lineage.adapter_kind == "PAPER"

    def test_output_structure(
        self, adapter: PaperDriver, sim_input: SimulationInput,
    ):
        """Output should be a valid SimulationOutput."""
        output = adapter.run(sim_input)
        assert_output_shape(output)

    def test_determinism(
        self, adapter: PaperDriver, sim_input: SimulationInput,
    ):
        """Same input should produce same output fields (modulo run_id)."""
        output1 = adapter.run(sim_input)
        output2 = adapter.run(sim_input)
        assert output1.simulation_run_id != output2.simulation_run_id
        assert outputs_match_except_run_id(output1, output2)

    def test_no_side_effects(
        self, adapter: PaperDriver, sim_input: SimulationInput,
    ):
        """Input should remain unchanged after adapter.run()."""
        original = replace(sim_input)
        _ = adapter.run(sim_input)
        assert sim_input.entry_price == original.entry_price
        assert sim_input.atr == original.atr
        assert sim_input.symbol == original.symbol


# ---------------------------------------------------------------------------
# Cross-adapter parity tests
# ---------------------------------------------------------------------------


class TestAdapterParity:
    """All 4 adapters should produce identical outputs (same input, modulo adapter_kind)."""

    @pytest.fixture
    def sim_input(self, fixture_profile: SimulationProfile) -> SimulationInput:
        return make_sim_input(fixture_profile)

    def test_all_adapters_same_best_action(
        self,
        sim_input: SimulationInput,
    ):
        """All adapters running same input should select same best_action."""
        train_out = TrainingAdapter().run(sim_input)
        eval_out = EvaluationAdapter().run(sim_input)
        replay_out = ReplayDriver().run(sim_input)
        paper_out = PaperDriver().run(sim_input)

        assert train_out.best_action == eval_out.best_action
        assert eval_out.best_action == replay_out.best_action
        assert replay_out.best_action == paper_out.best_action

    def test_all_adapters_same_resolution(
        self,
        sim_input: SimulationInput,
    ):
        """All adapters running same input should produce same resolution."""
        train_out = TrainingAdapter().run(sim_input)
        eval_out = EvaluationAdapter().run(sim_input)
        replay_out = ReplayDriver().run(sim_input)
        paper_out = PaperDriver().run(sim_input)

        assert train_out.resolution_status == eval_out.resolution_status
        assert eval_out.resolution_status == replay_out.resolution_status
        assert replay_out.resolution_status == paper_out.resolution_status

    def test_all_adapters_same_long_outcome(
        self,
        sim_input: SimulationInput,
    ):
        """All adapters should produce identical long outcome R values."""
        train_out = TrainingAdapter().run(sim_input)
        eval_out = EvaluationAdapter().run(sim_input)
        replay_out = ReplayDriver().run(sim_input)
        paper_out = PaperDriver().run(sim_input)

        assert train_out.long_outcome.realized_r_net == pytest.approx(
            eval_out.long_outcome.realized_r_net
        )
        assert eval_out.long_outcome.realized_r_net == pytest.approx(
            replay_out.long_outcome.realized_r_net
        )
        assert replay_out.long_outcome.realized_r_net == pytest.approx(
            paper_out.long_outcome.realized_r_net
        )

    def test_all_adapters_unique_adapter_kinds(
        self,
        sim_input: SimulationInput,
    ):
        """Each adapter should produce a distinct adapter_kind."""
        train_out = TrainingAdapter().run(sim_input)
        eval_out = EvaluationAdapter().run(sim_input)
        replay_out = ReplayDriver().run(sim_input)
        paper_out = PaperDriver().run(sim_input)

        kinds = [
            train_out.lineage.adapter_kind,
            eval_out.lineage.adapter_kind,
            replay_out.lineage.adapter_kind,
            paper_out.lineage.adapter_kind,
        ]
        assert len(set(kinds)) == 4, (
            f"Expected 4 distinct adapter_kinds, got {kinds}"
        )
        assert "TRAINING" in kinds
        assert "EVALUATION" in kinds
        assert "REPLAY" in kinds
        assert "PAPER" in kinds
