"""Tests for simulation/engine/interface.py — SimulationEngine ABC, AdapterRegistry, SideEffectFreeCheck.

Verifies:
  - SimulationEngine ABC cannot be instantiated directly (abstract enforcement)
  - AdapterRegistry register / get / list / duplicate / invalid-kind / non-engine rejection
  - Each adapter implements SimulationEngine and returns correct adapter_kind
  - Each adapter validates input correctly (pass and fail cases)
  - Each adapter validates output correctly (pass and fail cases)
  - SideEffectFreeCheck context manager and decorator
"""

from __future__ import annotations

import os
from dataclasses import replace
from typing import List

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
from simulation.engine.interface import (
    ADAPTER_KIND_EVALUATION,
    ADAPTER_KIND_MONTE_CARLO,
    ADAPTER_KIND_PAPER,
    ADAPTER_KIND_REPLAY,
    ADAPTER_KIND_TRAINING,
    STANDARD_ADAPTER_KINDS,
    AdapterRegistry,
    AdapterRegistryError,
    SideEffectFreeCheck,
    SimulationEngine,
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


# ---------------------------------------------------------------------------
# SimulationEngine ABC enforcement
# ---------------------------------------------------------------------------


class TestSimulationEngineABC:
    """SimulationEngine ABC cannot be instantiated directly."""

    def test_cannot_instantiate_abc(self):
        """Attempting to instantiate the ABC directly should raise TypeError."""
        with pytest.raises(TypeError):
            SimulationEngine()  # type: ignore[abstract]

    def test_concrete_subclass_works(self):
        """A minimal concrete subclass should be instantiable."""
        class MinimalEngine(SimulationEngine):
            def run(self, input: SimulationInput) -> SimulationOutput:
                raise NotImplementedError

            def get_adapter_kind(self) -> str:
                return "TRAINING"

        engine = MinimalEngine()
        assert isinstance(engine, SimulationEngine)
        assert engine.get_adapter_kind() == "TRAINING"

    def test_missing_run_raises(self):
        """Subclass without run() should raise TypeError on instantiation."""
        class MissingRun(SimulationEngine):
            def get_adapter_kind(self) -> str:
                return "TRAINING"

        with pytest.raises(TypeError):
            MissingRun()  # type: ignore[abstract]

    def test_missing_get_adapter_kind_raises(self):
        """Subclass without get_adapter_kind() should raise TypeError."""
        class MissingKind(SimulationEngine):
            def run(self, input: SimulationInput) -> SimulationOutput:
                raise NotImplementedError

        with pytest.raises(TypeError):
            MissingKind()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# AdapterRegistry tests
# ---------------------------------------------------------------------------


class TestAdapterRegistry:
    """AdapterRegistry registration, get, list, error handling."""

    @pytest.fixture
    def registry(self) -> AdapterRegistry:
        return AdapterRegistry()

    @pytest.fixture
    def training_engine(self) -> TrainingAdapter:
        return TrainingAdapter()

    def test_register_and_get(
        self, registry: AdapterRegistry, training_engine: TrainingAdapter,
    ):
        """Registered engine should be retrievable by kind."""
        registry.register("TRAINING", training_engine)
        engine = registry.get("TRAINING")
        assert engine is training_engine
        assert engine.get_adapter_kind() == "TRAINING"

    def test_list_adapters_empty(self, registry: AdapterRegistry):
        """Empty registry should list nothing."""
        assert registry.list_adapters() == []

    def test_list_adapters(
        self, registry: AdapterRegistry, training_engine: TrainingAdapter,
    ):
        """list_adapters should return registered kinds."""
        registry.register("TRAINING", training_engine)
        assert registry.list_adapters() == ["TRAINING"]

    def test_list_adapters_multiple(self, registry: AdapterRegistry):
        """list_adapters should return all registered kinds sorted."""
        registry.register("PAPER", PaperDriver())
        registry.register("TRAINING", TrainingAdapter())
        registry.register("EVALUATION", EvaluationAdapter())
        registry.register("REPLAY", ReplayDriver())
        assert registry.list_adapters() == [
            "EVALUATION", "PAPER", "REPLAY", "TRAINING",
        ]

    def test_duplicate_register_raises(
        self, registry: AdapterRegistry, training_engine: TrainingAdapter,
    ):
        """Registering same kind twice should raise AdapterRegistryError."""
        registry.register("TRAINING", training_engine)
        with pytest.raises(AdapterRegistryError, match="already registered"):
            registry.register("TRAINING", training_engine)

    def test_get_unregistered_raises(self, registry: AdapterRegistry):
        """Getting unregistered kind should raise AdapterRegistryError."""
        with pytest.raises(AdapterRegistryError, match="no adapter registered"):
            registry.get("NONEXISTENT")

    def test_register_invalid_kind_raises(self, registry: AdapterRegistry):
        """Registering a non-standard kind should raise AdapterRegistryError."""
        engine = TrainingAdapter()
        with pytest.raises(AdapterRegistryError, match="not a standard kind"):
            registry.register("CUSTOM", engine)

    def test_register_non_engine_raises(self, registry: AdapterRegistry):
        """Registering a non-SimulationEngine should raise AdapterRegistryError."""
        with pytest.raises(AdapterRegistryError, match="must be a SimulationEngine"):
            registry.register("TRAINING", "not_an_engine")  # type: ignore[arg-type]

    def test_contains(self, registry: AdapterRegistry):
        """__contains__ should reflect registration state."""
        assert "TRAINING" not in registry
        registry.register("TRAINING", TrainingAdapter())
        assert "TRAINING" in registry
        assert "EVALUATION" not in registry

    def test_len(self, registry: AdapterRegistry):
        """__len__ should reflect registration count."""
        assert len(registry) == 0
        registry.register("TRAINING", TrainingAdapter())
        assert len(registry) == 1
        registry.register("EVALUATION", EvaluationAdapter())
        assert len(registry) == 2


# ---------------------------------------------------------------------------
# Each adapter: get_adapter_kind correctness
# ---------------------------------------------------------------------------


class TestAdapterKind:
    """Every adapter should return its correct adapter kind."""

    def test_training_kind(self):
        assert TrainingAdapter().get_adapter_kind() == "TRAINING"

    def test_evaluation_kind(self):
        assert EvaluationAdapter().get_adapter_kind() == "EVALUATION"

    def test_paper_kind(self):
        assert PaperDriver().get_adapter_kind() == "PAPER"

    def test_replay_kind(self):
        assert ReplayDriver().get_adapter_kind() == "REPLAY"

    def test_all_adapters_are_simulation_engine(self):
        """Every adapter should be an instance of SimulationEngine."""
        assert isinstance(TrainingAdapter(), SimulationEngine)
        assert isinstance(EvaluationAdapter(), SimulationEngine)
        assert isinstance(PaperDriver(), SimulationEngine)
        assert isinstance(ReplayDriver(), SimulationEngine)


# ---------------------------------------------------------------------------
# Each adapter: validate_input
# ---------------------------------------------------------------------------


class TestValidateInput:
    """validate_input should catch invalid inputs across adapters."""

    @pytest.fixture
    def valid_input(self, fixture_profile: SimulationProfile) -> SimulationInput:
        return make_sim_input(fixture_profile)

    def test_valid_input_returns_empty(
        self, valid_input: SimulationInput,
    ):
        """A well-formed input should produce no errors."""
        for adapter in [TrainingAdapter(), EvaluationAdapter(), PaperDriver(), ReplayDriver()]:
            errors = adapter.validate_input(valid_input)
            assert errors == [], (
                f"{adapter.__class__.__name__}: expected no errors, got {errors}"
            )

    @pytest.mark.parametrize("adapter_cls", [
        TrainingAdapter, EvaluationAdapter, PaperDriver, ReplayDriver,
    ])
    def test_empty_symbol(self, adapter_cls, valid_input: SimulationInput):
        """Empty symbol should produce a validation error."""
        adapter = adapter_cls()
        inp = replace(valid_input, symbol="")
        errors = adapter.validate_input(inp)
        assert any("symbol" in e.lower() for e in errors), errors

    @pytest.mark.parametrize("adapter_cls", [
        TrainingAdapter, EvaluationAdapter, PaperDriver, ReplayDriver,
    ])
    def test_negative_entry_price(self, adapter_cls, valid_input: SimulationInput):
        """Zero or negative entry_price should produce a validation error."""
        adapter = adapter_cls()
        inp = replace(valid_input, entry_price=0.0)
        errors = adapter.validate_input(inp)
        assert any("entry_price" in e.lower() for e in errors), errors

    @pytest.mark.parametrize("adapter_cls", [
        TrainingAdapter, EvaluationAdapter, PaperDriver, ReplayDriver,
    ])
    def test_negative_atr(self, adapter_cls, valid_input: SimulationInput):
        """Zero or negative ATR should produce a validation error."""
        adapter = adapter_cls()
        inp = replace(valid_input, atr=0.0)
        errors = adapter.validate_input(inp)
        assert any("atr" in e.lower() for e in errors), errors

    @pytest.mark.parametrize("adapter_cls", [
        TrainingAdapter, EvaluationAdapter, PaperDriver, ReplayDriver,
    ])
    def test_empty_future_path(self, adapter_cls, valid_input: SimulationInput):
        """Missing future_path candles should produce a validation error."""
        adapter = adapter_cls()
        empty_fp = FuturePath(candles=[], completeness_status="COMPLETE", expected_bars=0)
        inp = replace(valid_input, future_path=empty_fp)
        errors = adapter.validate_input(inp)
        assert any("candle" in e.lower() for e in errors), errors

    @pytest.mark.parametrize("adapter_cls", [
        TrainingAdapter, EvaluationAdapter, PaperDriver, ReplayDriver,
    ])
    def test_none_profile(self, adapter_cls, valid_input: SimulationInput):
        """Missing profile should produce a validation error."""
        adapter = adapter_cls()
        inp = replace(valid_input, profile=None)  # type: ignore[arg-type]
        errors = adapter.validate_input(inp)
        assert any("profile" in e.lower() for e in errors), errors


# ---------------------------------------------------------------------------
# Each adapter: validate_output
# ---------------------------------------------------------------------------


class TestValidateOutput:
    """validate_output should check output completeness."""

    def _make_partial_output(self) -> SimulationOutput:
        """Create a minimally-populated output for validation tests."""
        pm = PathMetrics()
        ao = ActionOutcome(action="LONG_NOW", path_metrics=pm)
        nt = NoTradeOutcome()
        lineage = SimulationLineage(adapter_kind="TRAINING")
        return SimulationOutput(
            simulation_run_id="test123",
            symbol="BTCUSDT",
            decision_timestamp="2024-01-01T00:00:00",
            mode="SWING",
            primary_interval="4h",
            resolution_status="COMPLETE",
            long_outcome=ao,
            short_outcome=replace(ao, action="SHORT_NOW"),
            no_trade_outcome=nt,
            best_action="LONG_NOW",
            action_gap_r=0.5,
            regret_r=0.0,
            is_ambiguous=False,
            lineage=lineage,
        )

    def test_valid_output_returns_empty(self):
        """A well-formed output should produce no errors."""
        output = self._make_partial_output()
        for adapter in [TrainingAdapter(), EvaluationAdapter(), PaperDriver(), ReplayDriver()]:
            errors = adapter.validate_output(output)
            assert errors == [], (
                f"{adapter.__class__.__name__}: expected no errors, got {errors}"
            )

    @pytest.mark.parametrize("adapter_cls", [
        TrainingAdapter, EvaluationAdapter, PaperDriver, ReplayDriver,
    ])
    def test_empty_run_id(self, adapter_cls):
        """Missing simulation_run_id should produce an error."""
        adapter = adapter_cls()
        output = self._make_partial_output()
        output.simulation_run_id = ""
        errors = adapter.validate_output(output)
        assert any("simulation_run_id" in e for e in errors), errors

    @pytest.mark.parametrize("adapter_cls", [
        TrainingAdapter, EvaluationAdapter, PaperDriver, ReplayDriver,
    ])
    def test_invalid_resolution(self, adapter_cls):
        """Invalid resolution_status should produce an error."""
        adapter = adapter_cls()
        output = self._make_partial_output()
        output.resolution_status = "BOGUS"
        errors = adapter.validate_output(output)
        assert any("resolution_status" in e for e in errors), errors

    @pytest.mark.parametrize("adapter_cls", [
        TrainingAdapter, EvaluationAdapter, PaperDriver, ReplayDriver,
    ])
    def test_invalid_best_action(self, adapter_cls):
        """Invalid best_action should produce an error."""
        adapter = adapter_cls()
        output = self._make_partial_output()
        output.best_action = "HODL"
        errors = adapter.validate_output(output)
        assert any("best_action" in e for e in errors), errors

    @pytest.mark.parametrize("adapter_cls", [
        TrainingAdapter, EvaluationAdapter, PaperDriver, ReplayDriver,
    ])
    def test_empty_adapter_kind(self, adapter_cls):
        """Missing lineage.adapter_kind should produce an error."""
        adapter = adapter_cls()
        output = self._make_partial_output()
        output.lineage.adapter_kind = ""
        errors = adapter.validate_output(output)
        assert any("adapter_kind" in e for e in errors), errors

    @pytest.mark.parametrize("adapter_cls", [
        TrainingAdapter, EvaluationAdapter, PaperDriver, ReplayDriver,
    ])
    def test_missing_outcomes(self, adapter_cls):
        """None outcomes should produce errors."""
        adapter = adapter_cls()
        output = self._make_partial_output()
        output.long_outcome = None
        errors = adapter.validate_output(output)
        assert any("long_outcome" in e for e in errors), errors


# ---------------------------------------------------------------------------
# Each adapter: end-to-end simulation (smoke test via validate)
# ---------------------------------------------------------------------------


class TestAdapterEndToEnd:
    """Each adapter produces validatable output from valid input."""

    @pytest.fixture
    def sim_input(self, fixture_profile: SimulationProfile) -> SimulationInput:
        return make_sim_input(fixture_profile)

    def test_training_round_trip(self, sim_input: SimulationInput):
        """TrainingAdapter: input valid, run, output valid."""
        adapter = TrainingAdapter()
        assert adapter.validate_input(sim_input) == []
        output = adapter.run(sim_input)
        assert adapter.validate_output(output) == []
        assert output.lineage.adapter_kind == "TRAINING"

    def test_evaluation_round_trip(self, sim_input: SimulationInput):
        """EvaluationAdapter: input valid, run, output valid."""
        adapter = EvaluationAdapter()
        assert adapter.validate_input(sim_input) == []
        output = adapter.run(sim_input)
        assert adapter.validate_output(output) == []
        assert output.lineage.adapter_kind == "EVALUATION"

    def test_paper_round_trip(self, sim_input: SimulationInput):
        """PaperDriver: input valid, run, output valid."""
        adapter = PaperDriver()
        assert adapter.validate_input(sim_input) == []
        output = adapter.run(sim_input)
        assert adapter.validate_output(output) == []
        assert output.lineage.adapter_kind == "PAPER"

    def test_replay_round_trip(self, sim_input: SimulationInput):
        """ReplayDriver: input valid, run, output valid."""
        adapter = ReplayDriver()
        assert adapter.validate_input(sim_input) == []
        output = adapter.run(sim_input)
        assert adapter.validate_output(output) == []
        assert output.lineage.adapter_kind == "REPLAY"


# ---------------------------------------------------------------------------
# SideEffectFreeCheck
# ---------------------------------------------------------------------------


class TestSideEffectFreeCheck:
    """SideEffectFreeCheck context manager and decorator."""

    def test_context_manager_passes_on_pure_function(self):
        """Context manager should not raise when no files are mutated."""
        with SideEffectFreeCheck():
            x = 1 + 1  # pure operation
        assert x == 2  # noqa: F841

    def test_decorator_passes_on_pure_function(self):
        """Decorator should not raise when no files are mutated."""
        called = []

        @SideEffectFreeCheck()
        def pure_func() -> str:
            called.append(True)
            return "ok"

        result = pure_func()
        assert result == "ok"
        assert called == [True]

    def test_detects_file_creation(self, tmp_path: str):
        """Context manager should raise when a file is created inside the block."""
        with pytest.raises(RuntimeError, match="Side-effect-free violation"):
            with SideEffectFreeCheck(watch_dir=str(tmp_path)):
                # Create a file in the watched directory
                open(os.path.join(tmp_path, "new_file.py"), "w").close()

    def test_detects_file_modification(self, tmp_path: str):
        """Context manager should raise when a file is modified in watch dir."""
        test_file = os.path.join(tmp_path, "test.py")
        with open(test_file, "w") as f:
            f.write("short")

        with pytest.raises(RuntimeError, match="Side-effect-free violation"):
            with SideEffectFreeCheck(watch_dir=str(tmp_path)):
                with open(test_file, "w") as f:
                    f.write("longer_content_here")

    def test_separate_checks_no_cross_contamination(self, tmp_path: str):
        """Each check only observes its own block — modifications between
        checks are not detected (each check snapshots fresh on entry)."""
        test_file = os.path.join(tmp_path, "module.py")
        with open(test_file, "w") as f:
            f.write("original")

        # First check passes — no change inside block
        with SideEffectFreeCheck(watch_dir=str(tmp_path)):
            pass

        # Modify file between checks
        with open(test_file, "w") as f:
            f.write("modified_longer")

        # Second check creates a fresh snapshot, so modifying before
        # entry does not cause a violation — only changes inside the
        # *current* block are flagged.
        with SideEffectFreeCheck(watch_dir=str(tmp_path)):
            pass  # no file I/O inside = no violation

    def test_decorator_detects_file_creation(self, tmp_path: str):
        """Decorator should raise when a file is created inside."""
        @SideEffectFreeCheck(watch_dir=str(tmp_path))
        def create_file() -> None:
            open(os.path.join(tmp_path, "evil.py"), "w").close()

        with pytest.raises(RuntimeError, match="Side-effect-free violation"):
            create_file()

    def test_exception_not_masked(self, tmp_path: str):
        """If the wrapped code raises, the check should not mask it."""
        with SideEffectFreeCheck(watch_dir=str(tmp_path)):
            with pytest.raises(ValueError, match="test error"):
                raise ValueError("test error")

    def test_watch_dir_defaults_to_simulation(self):
        """Default watch dir should be the simulation package directory."""
        check = SideEffectFreeCheck()
        assert "simulation" in check._watch_dir
        assert os.path.isdir(check._watch_dir)


# ---------------------------------------------------------------------------
# Standard adapter kinds constants
# ---------------------------------------------------------------------------


class TestStandardAdapterKinds:
    """STANDARD_ADAPTER_KINDS should contain expected values."""

    def test_all_kinds_present(self):
        assert "TRAINING" in STANDARD_ADAPTER_KINDS
        assert "EVALUATION" in STANDARD_ADAPTER_KINDS
        assert "PAPER" in STANDARD_ADAPTER_KINDS
        assert "REPLAY" in STANDARD_ADAPTER_KINDS
        assert "MONTE_CARLO" in STANDARD_ADAPTER_KINDS

    def test_constants_match(self):
        assert ADAPTER_KIND_TRAINING == "TRAINING"
        assert ADAPTER_KIND_EVALUATION == "EVALUATION"
        assert ADAPTER_KIND_PAPER == "PAPER"
        assert ADAPTER_KIND_REPLAY == "REPLAY"
        assert ADAPTER_KIND_MONTE_CARLO == "MONTE_CARLO"
