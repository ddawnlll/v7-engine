"""
Standardized tests for all simulation adapters (#46).

Verifies:
  1. Protocol compliance -- each adapter implements SimulationEngine ABC
  2. Input validation -- each adapter rejects invalid input
  3. Output validation -- each adapter produces valid output
  4. Lineage tags -- each adapter sets correct adapter_kind
  5. Registration -- register_all_adapters() works
  6. Side-effect-free -- adapters don't mutate filesystem state
  7. MonteCarloAdapter -- runs, validates, aggregates stats
  8. Import boundary -- new modules don't violate domain constraints

Usage:
    PYTHONPATH=. python3 -m pytest simulation/tests/test_adapters_standardized.py -v
"""

from __future__ import annotations

import importlib
from dataclasses import replace
from typing import Any

import pytest

from simulation.adapters import (
    # Adapter classes
    TrainingAdapter,
    EvaluationAdapter,
    PaperDriver,
    ReplayDriver,
    MonteCarloAdapter,
    # Registration
    register_all_adapters,
    # Kind constants
    ADAPTER_KIND_TRAINING,
    ADAPTER_KIND_EVALUATION,
    ADAPTER_KIND_PAPER,
    ADAPTER_KIND_REPLAY,
    ADAPTER_KIND_MONTE_CARLO,
    STANDARD_ADAPTER_KINDS,
    # Registry
    AdapterRegistry,
    AdapterRegistryError,
    # Side-effect check
    SideEffectFreeCheck,
    # Validation helpers
    validate_simulation_input,
    validate_simulation_output,
    validate_monte_carlo_output,
)
from simulation.contracts.models import (
    Candle,
    FuturePath,
    MonteCarloOutput,
    SimulationInput,
    SimulationOutput,
    SimulationProfile,
    TradingMode,
)
from simulation.engine.interface import SimulationEngine


# ====================================================================
# Fixtures
# ====================================================================


@pytest.fixture
def swing_profile() -> SimulationProfile:
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


def make_valid_input(
    profile: SimulationProfile,
    symbol: str = "BTCUSDT",
    entry_price: float = 50000.0,
    atr: float = 500.0,
    decision_idx: int = 0,
) -> SimulationInput:
    """Create a valid SimulationInput with synthetic uptrend future path."""
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


def make_invalid_input(profile: SimulationProfile) -> SimulationInput:
    """Create an invalid SimulationInput (entry_price <= 0)."""
    valid = make_valid_input(profile)
    return replace(valid, entry_price=0.0)


# ====================================================================
# 1. Protocol compliance
# ====================================================================


class TestProtocolCompliance:
    """Every standard adapter implements SimulationEngine ABC."""

    @pytest.mark.parametrize(
        "cls,name",
        [
            (TrainingAdapter, "TrainingAdapter"),
            (EvaluationAdapter, "EvaluationAdapter"),
            (PaperDriver, "PaperDriver"),
            (ReplayDriver, "ReplayDriver"),
        ],
    )
    def test_is_simulation_engine(self, cls: type, name: str) -> None:
        """All standard adapters should be SimulationEngine instances."""
        instance = cls()
        assert isinstance(instance, SimulationEngine), (
            f"{name} does not implement SimulationEngine"
        )

    @pytest.mark.parametrize(
        "cls,name,expected_kind",
        [
            (TrainingAdapter, "TrainingAdapter", "TRAINING"),
            (EvaluationAdapter, "EvaluationAdapter", "EVALUATION"),
            (PaperDriver, "PaperDriver", "PAPER"),
            (ReplayDriver, "ReplayDriver", "REPLAY"),
            (MonteCarloAdapter, "MonteCarloAdapter", "MONTE_CARLO"),
        ],
    )
    def test_get_adapter_kind(
        self, cls: type, name: str, expected_kind: str
    ) -> None:
        """Each adapter returns correct kind."""
        instance = cls()
        assert instance.get_adapter_kind() == expected_kind, (
            f"{name}.get_adapter_kind() should be '{expected_kind}'"
        )

    @pytest.mark.parametrize(
        "cls,name",
        [
            (TrainingAdapter, "TrainingAdapter"),
            (EvaluationAdapter, "EvaluationAdapter"),
            (PaperDriver, "PaperDriver"),
            (ReplayDriver, "ReplayDriver"),
            (MonteCarloAdapter, "MonteCarloAdapter"),
        ],
    )
    def test_side_effect_free_declaration(
        self, cls: type, name: str
    ) -> None:
        """Each adapter declares itself side-effect-free."""
        instance = cls()
        assert instance.is_side_effect_free() is True, (
            f"{name} should declare itself side-effect-free"
        )


# ====================================================================
# 2. Input validation
# ====================================================================


class TestInputValidation:
    """Each adapter rejects invalid input."""

    @pytest.fixture
    def valid_input(self, swing_profile: SimulationProfile) -> SimulationInput:
        return make_valid_input(swing_profile)

    @pytest.fixture
    def invalid_input(
        self, swing_profile: SimulationProfile
    ) -> SimulationInput:
        return make_invalid_input(swing_profile)

    @pytest.mark.parametrize(
        "adapter_factory",
        [
            lambda: TrainingAdapter(),
            lambda: EvaluationAdapter(),
            lambda: PaperDriver(),
            lambda: ReplayDriver(),
        ],
    )
    def test_accepts_valid_input(
        self,
        adapter_factory: Any,
        valid_input: SimulationInput,
    ) -> None:
        """Valid input should pass validation."""
        adapter = adapter_factory()  # type: ignore
        errors = adapter.validate_input(valid_input)
        assert errors == [], f"Expected no errors, got: {errors}"

    @pytest.mark.parametrize(
        "adapter_factory",
        [
            lambda: TrainingAdapter(),
            lambda: EvaluationAdapter(),
            lambda: PaperDriver(),
            lambda: ReplayDriver(),
        ],
    )
    def test_rejects_invalid_input(
        self,
        adapter_factory: Any,
        invalid_input: SimulationInput,
    ) -> None:
        """Invalid input should fail validation."""
        adapter = adapter_factory()  # type: ignore
        errors = adapter.validate_input(invalid_input)
        assert len(errors) > 0, "Expected validation errors for invalid input"

    @pytest.mark.parametrize(
        "adapter_factory",
        [
            lambda: TrainingAdapter(),
            lambda: EvaluationAdapter(),
            lambda: PaperDriver(),
            lambda: ReplayDriver(),
        ],
    )
    def test_run_raises_on_invalid(
        self,
        adapter_factory: Any,
        invalid_input: SimulationInput,
    ) -> None:
        """run() should raise ValueError on invalid input."""
        adapter = adapter_factory()  # type: ignore
        with pytest.raises(ValueError, match="validation failed"):
            adapter.run(invalid_input)

    # -- Edge cases --

    def test_empty_symbol(
        self, swing_profile: SimulationProfile
    ) -> None:
        """Empty symbol should be caught by validation."""
        inp = make_valid_input(swing_profile, symbol="")
        adapter = TrainingAdapter()
        errors = adapter.validate_input(inp)
        assert any("symbol" in e for e in errors)

    def test_negative_atr(
        self, swing_profile: SimulationProfile
    ) -> None:
        """Negative ATR should be caught by validation."""
        inp = make_valid_input(swing_profile, atr=-1.0)
        adapter = TrainingAdapter()
        errors = adapter.validate_input(inp)
        assert any("atr" in e for e in errors)

    def test_empty_future_path(
        self, swing_profile: SimulationProfile
    ) -> None:
        """Empty future path should be caught."""
        inp = make_valid_input(swing_profile)
        inp = replace(
            inp,
            future_path=FuturePath(
                candles=[], completeness_status="COMPLETE", expected_bars=0
            ),
        )
        adapter = TrainingAdapter()
        errors = adapter.validate_input(inp)
        assert any("candle" in e.lower() for e in errors)


# ====================================================================
# 3. Output validation
# ====================================================================


class TestOutputValidation:
    """Each adapter produces valid output structure."""

    @pytest.fixture
    def valid_input(self, swing_profile: SimulationProfile) -> SimulationInput:
        return make_valid_input(swing_profile)

    @pytest.mark.parametrize(
        "adapter_factory,name",
        [
            (lambda: TrainingAdapter(), "TrainingAdapter"),
            (lambda: EvaluationAdapter(), "EvaluationAdapter"),
            (lambda: PaperDriver(), "PaperDriver"),
            (lambda: ReplayDriver(), "ReplayDriver"),
        ],
    )
    def test_valid_output(
        self,
        adapter_factory: Any,
        name: str,
        valid_input: SimulationInput,
    ) -> None:
        """Adapter run() produces a valid SimulationOutput."""
        adapter = adapter_factory()  # type: ignore
        output = adapter.run(valid_input)
        errors = validate_simulation_output(output)
        assert errors == [], (
            f"{name} produced invalid output: {'; '.join(errors)}"
        )

    @pytest.mark.parametrize(
        "adapter_factory,name",
        [
            (lambda: TrainingAdapter(), "TrainingAdapter"),
            (lambda: EvaluationAdapter(), "EvaluationAdapter"),
            (lambda: PaperDriver(), "PaperDriver"),
            (lambda: ReplayDriver(), "ReplayDriver"),
        ],
    )
    def test_output_has_run_id(
        self,
        adapter_factory: Any,
        name: str,
        valid_input: SimulationInput,
    ) -> None:
        """Each output should have a non-empty simulation_run_id."""
        adapter = adapter_factory()  # type: ignore
        output = adapter.run(valid_input)
        assert output.simulation_run_id, (
            f"{name} output should have non-empty simulation_run_id"
        )


# ====================================================================
# 4. Lineage tags
# ====================================================================


class TestLineageTags:
    """Each adapter sets correct adapter_kind in output lineage."""

    @pytest.mark.parametrize(
        "adapter_factory,name,expected_kind",
        [
            (lambda: TrainingAdapter(), "TrainingAdapter", "TRAINING"),
            (lambda: EvaluationAdapter(), "EvaluationAdapter", "EVALUATION"),
            (lambda: PaperDriver(), "PaperDriver", "PAPER"),
            (lambda: ReplayDriver(), "ReplayDriver", "REPLAY"),
        ],
    )
    def test_adapter_kind_in_lineage(
        self,
        adapter_factory: Any,
        name: str,
        expected_kind: str,
        swing_profile: SimulationProfile,
    ) -> None:
        """Output lineage adapter_kind should match the adapter's kind."""
        adapter = adapter_factory()  # type: ignore
        inp = make_valid_input(swing_profile)
        output = adapter.run(inp)
        assert output.lineage.adapter_kind == expected_kind, (
            f"{name} lineage.adapter_kind should be '{expected_kind}', "
            f"got '{output.lineage.adapter_kind}'"
        )

    def test_all_kinds_unique(
        self, swing_profile: SimulationProfile
    ) -> None:
        """All adapter kinds should be distinct."""
        inp = make_valid_input(swing_profile)
        kinds = {
            TrainingAdapter().run(inp).lineage.adapter_kind,
            EvaluationAdapter().run(inp).lineage.adapter_kind,
            PaperDriver().run(inp).lineage.adapter_kind,
            ReplayDriver().run(inp).lineage.adapter_kind,
        }
        assert len(kinds) == 4, (
            f"Expected 4 distinct adapter kinds, got {len(kinds)}: {kinds}"
        )


# ====================================================================
# 5. Registration
# ====================================================================


class TestRegistration:
    """register_all_adapters() works correctly."""

    def test_register_all(self) -> None:
        """All 4 standard adapters should be registerable."""
        registry = AdapterRegistry()
        register_all_adapters(registry)
        assert len(registry) == 4, (
            f"Expected 4 registered adapters, got {len(registry)}"
        )

    def test_all_kinds_present(self) -> None:
        """All standard adapter kinds should be present after registration."""
        registry = AdapterRegistry()
        register_all_adapters(registry)
        for kind in (ADAPTER_KIND_TRAINING, ADAPTER_KIND_EVALUATION,
                      ADAPTER_KIND_PAPER, ADAPTER_KIND_REPLAY):
            assert kind in registry, f"Adapter kind '{kind}' not registered"
            engine = registry.get(kind)
            assert engine.get_adapter_kind() == kind

    def test_double_register_raises(self) -> None:
        """Registering the same kind twice should raise."""
        registry = AdapterRegistry()
        register_all_adapters(registry)
        with pytest.raises(AdapterRegistryError, match="already registered"):
            registry.register(ADAPTER_KIND_TRAINING, TrainingAdapter())

    def test_unregistered_kind_raises(self) -> None:
        """Getting an unregistered kind should raise."""
        registry = AdapterRegistry()
        with pytest.raises(AdapterRegistryError, match="no adapter registered"):
            registry.get(ADAPTER_KIND_TRAINING)

    def test_list_adapters(self) -> None:
        """list_adapters() should return sorted registered kinds."""
        registry = AdapterRegistry()
        register_all_adapters(registry)
        kinds = registry.list_adapters()
        assert kinds == sorted(kinds), "Adapter kinds should be sorted"
        assert ADAPTER_KIND_TRAINING in kinds
        assert ADAPTER_KIND_EVALUATION in kinds
        assert ADAPTER_KIND_PAPER in kinds
        assert ADAPTER_KIND_REPLAY in kinds


# ====================================================================
# 6. Side-effect-free
# ====================================================================


class TestSideEffectFree:
    """Adapters must not mutate filesystem state during execution."""

    @pytest.mark.parametrize(
        "adapter_factory,name",
        [
            (lambda: TrainingAdapter(), "TrainingAdapter"),
            (lambda: EvaluationAdapter(), "EvaluationAdapter"),
            (lambda: PaperDriver(), "PaperDriver"),
            (lambda: ReplayDriver(), "ReplayDriver"),
        ],
    )
    def test_no_file_mutation(
        self,
        adapter_factory: Any,
        name: str,
        swing_profile: SimulationProfile,
    ) -> None:
        """Adapter run() should not create/modify/delete any files."""
        adapter = adapter_factory()  # type: ignore
        inp = make_valid_input(swing_profile)
        with SideEffectFreeCheck():
            _ = adapter.run(inp)

    def test_monte_carlo_no_file_mutation(
        self, swing_profile: SimulationProfile
    ) -> None:
        """MonteCarloAdapter run() should not create/modify/delete files."""
        adapter = MonteCarloAdapter(n_perturbations=5, seed=42)
        inp = make_valid_input(swing_profile)
        with SideEffectFreeCheck():
            _ = adapter.run(inp)


# ====================================================================
# 7. MonteCarloAdapter
# ====================================================================


class TestMonteCarloAdapter:
    """MonteCarloAdapter-specific tests."""

    def test_adapter_kind(self) -> None:
        """Kind should be MONTE_CARLO."""
        adapter = MonteCarloAdapter()
        assert adapter.get_adapter_kind() == "MONTE_CARLO"

    def test_returns_monte_carlo_output(
        self, swing_profile: SimulationProfile
    ) -> None:
        """run() should return MonteCarloOutput."""
        adapter = MonteCarloAdapter(n_perturbations=5, seed=42)
        inp = make_valid_input(swing_profile)
        result = adapter.run(inp)
        assert isinstance(result, MonteCarloOutput), (
            f"Expected MonteCarloOutput, got {type(result).__name__}"
        )

    def test_perturbation_count(
        self, swing_profile: SimulationProfile
    ) -> None:
        """Should return correct number of perturbations."""
        n = 10
        adapter = MonteCarloAdapter(n_perturbations=n, seed=42)
        inp = make_valid_input(swing_profile)
        result = adapter.run(inp)
        assert len(result.perturbed_outputs) == n, (
            f"Expected {n} perturbed outputs, got {len(result.perturbed_outputs)}"
        )

    def test_baseline_output_valid(
        self, swing_profile: SimulationProfile
    ) -> None:
        """Baseline output should be valid SimulationOutput."""
        adapter = MonteCarloAdapter(n_perturbations=5, seed=42)
        inp = make_valid_input(swing_profile)
        result = adapter.run(inp)
        errors = validate_simulation_output(result.baseline_output)
        assert errors == [], (
            f"Baseline output invalid: {'; '.join(errors)}"
        )

    def test_perturbed_outputs_valid(
        self, swing_profile: SimulationProfile
    ) -> None:
        """Each perturbed output should be valid."""
        adapter = MonteCarloAdapter(n_perturbations=10, seed=42)
        inp = make_valid_input(swing_profile)
        result = adapter.run(inp)
        for i, po in enumerate(result.perturbed_outputs):
            errors = validate_simulation_output(po)
            assert errors == [], (
                f"Perturbed output[{i}] invalid: {'; '.join(errors)}"
            )

    def test_lineage_has_monte_carlo_kind(
        self, swing_profile: SimulationProfile
    ) -> None:
        """All outputs should have MONTE_CARLO adapter_kind."""
        adapter = MonteCarloAdapter(n_perturbations=5, seed=42)
        inp = make_valid_input(swing_profile)
        result = adapter.run(inp)
        assert result.baseline_output.lineage.adapter_kind == "MONTE_CARLO"
        for i, po in enumerate(result.perturbed_outputs):
            assert po.lineage.adapter_kind == "MONTE_CARLO", (
                f"Perturbed output[{i}] has wrong adapter_kind"
            )

    def test_monte_carlo_run_id_consistent(
        self, swing_profile: SimulationProfile
    ) -> None:
        """All outputs should share the same monte_carlo_run_id."""
        adapter = MonteCarloAdapter(n_perturbations=5, seed=42)
        inp = make_valid_input(swing_profile)
        result = adapter.run(inp)
        run_id = result.monte_carlo_run_id
        assert run_id, "monte_carlo_run_id should be non-empty"
        assert result.baseline_output.monte_carlo_run_id == run_id
        for i, po in enumerate(result.perturbed_outputs):
            assert po.monte_carlo_run_id == run_id, (
                f"Perturbed output[{i}] has different monte_carlo_run_id"
            )

    def test_aggregate_stats_present(
        self, swing_profile: SimulationProfile
    ) -> None:
        """Aggregate stats should have expected keys."""
        adapter = MonteCarloAdapter(n_perturbations=10, seed=42)
        inp = make_valid_input(swing_profile)
        result = adapter.run(inp)
        stats = result.aggregate_stats
        assert "long_realized_r_net" in stats
        assert "short_realized_r_net" in stats
        assert "best_action_distribution" in stats
        assert "action_gap_r" in stats
        # Check nested stat keys
        for key in ("long_realized_r_net", "short_realized_r_net"):
            for stat_key in ("mean", "std", "min", "max", "p5", "p25", "p50", "p75", "p95"):
                assert stat_key in stats[key], (
                    f"Missing '{stat_key}' in {key}"
                )

    def test_perturbation_params_recorded(
        self, swing_profile: SimulationProfile
    ) -> None:
        """Perturbation params should be recorded in output."""
        adapter = MonteCarloAdapter(n_perturbations=5, noise_std=0.02, seed=123)
        inp = make_valid_input(swing_profile)
        result = adapter.run(inp)
        params = result.perturbation_params
        assert params["n_perturbations"] == 5
        assert params["noise_std"] == 0.02
        assert params["seed"] == 123

    def test_determinism(
        self, swing_profile: SimulationProfile
    ) -> None:
        """Same seed should produce identical results."""
        inp = make_valid_input(swing_profile)
        adapter1 = MonteCarloAdapter(n_perturbations=5, seed=42)
        adapter2 = MonteCarloAdapter(n_perturbations=5, seed=42)
        result1 = adapter1.run(inp)
        result2 = adapter2.run(inp)
        # Baseline outputs should match (same input)
        assert result1.baseline_output.best_action == result2.baseline_output.best_action
        assert result1.baseline_output.action_gap_r == pytest.approx(
            result2.baseline_output.action_gap_r
        )
        # Aggregate stats should match (same seed)
        for key in ("long_realized_r_net", "short_realized_r_net"):
            assert result1.aggregate_stats[key]["mean"] == pytest.approx(
                result2.aggregate_stats[key]["mean"]
            )

    def test_different_seed_different_results(
        self, swing_profile: SimulationProfile
    ) -> None:
        """Different seed should produce different perturbed results."""
        inp = make_valid_input(swing_profile)
        adapter1 = MonteCarloAdapter(n_perturbations=5, seed=42)
        adapter2 = MonteCarloAdapter(n_perturbations=5, seed=999)
        result1 = adapter1.run(inp)
        result2 = adapter2.run(inp)
        # Baseline should be same (same input)
        assert result1.baseline_output.best_action == result2.baseline_output.best_action
        # But perturbed paths should differ -> stats should differ
        # It's theoretically possible but astronomically unlikely that
        # different seeds produce identical mean values.
        assert result1.aggregate_stats["long_realized_r_net"]["mean"] != pytest.approx(
            result2.aggregate_stats["long_realized_r_net"]["mean"]
        ) or result1.aggregate_stats["short_realized_r_net"]["mean"] != pytest.approx(
            result2.aggregate_stats["short_realized_r_net"]["mean"]
        ), "Different seeds should produce different results"

    def test_validates_output(
        self, swing_profile: SimulationProfile
    ) -> None:
        """MonteCarloOutput should pass validate_monte_carlo_output."""
        adapter = MonteCarloAdapter(n_perturbations=5, seed=42)
        inp = make_valid_input(swing_profile)
        result = adapter.run(inp)
        errors = validate_monte_carlo_output(result)
        assert errors == [], f"MC output validation failed: {'; '.join(errors)}"

    def test_rejects_invalid_input(
        self, swing_profile: SimulationProfile
    ) -> None:
        """Should reject invalid input."""
        adapter = MonteCarloAdapter(n_perturbations=5)
        inp = make_invalid_input(swing_profile)
        with pytest.raises(ValueError, match="validation failed"):
            adapter.run(inp)

    def test_rejects_zero_perturbations(self) -> None:
        """Should reject n_perturbations < 1."""
        with pytest.raises(ValueError, match="n_perturbations"):
            MonteCarloAdapter(n_perturbations=0)

    def test_rejects_negative_noise(self) -> None:
        """Should reject non-positive noise_std."""
        with pytest.raises(ValueError, match="noise_std"):
            MonteCarloAdapter(noise_std=-0.01)


# ====================================================================
# 8. Import boundary
# ====================================================================


class TestImportBoundary:
    """New adapter modules must not violate domain constraints."""

    FORBIDDEN_PATTERNS = [
        "import v7",
        "from v7",
        "import alphaforge",
        "from alphaforge",
        "import runtime",
        "from runtime",
        "import interface",
        "from interface",
    ]

    @pytest.mark.parametrize(
        "module_path",
        [
            "simulation.adapters",
            "simulation.adapters.monte_carlo_adapter",
            "simulation.adapters._validation",
            "simulation.adapters.training_adapter",
            "simulation.adapters.evaluation_adapter",
            "simulation.adapters.paper_driver",
            "simulation.adapters.replay_driver",
        ],
    )
    def test_module_importable(self, module_path: str) -> None:
        """Each module should be importable without error."""
        importlib.import_module(module_path)

    def test_no_forbidden_imports_in_new_modules(self) -> None:
        """New adapter modules must not import from forbidden domains."""
        import os

        sim_dir = os.path.join(
            os.path.dirname(__file__), "..", "adapters"
        )
        for fname in os.listdir(sim_dir):
            if not fname.endswith(".py") or fname.startswith("__"):
                continue
            filepath = os.path.join(sim_dir, fname)
            with open(filepath) as fh:
                for lineno, line in enumerate(fh, 1):
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("'"):
                        continue
                    for pattern in self.FORBIDDEN_PATTERNS:
                        if pattern in stripped:
                            pytest.fail(
                                f"{filepath}:{lineno}: forbidden import "
                                f"pattern '{pattern}': {stripped}"
                            )


# ====================================================================
# 9. Cross-adapter parity (from existing test, minimal)
# ====================================================================


class TestAdapterParity:
    """All standard adapters should produce identical outputs for same input."""

    def test_all_adapters_same_best_action(
        self, swing_profile: SimulationProfile
    ) -> None:
        """All adapters on same input should select same best_action."""
        inp = make_valid_input(swing_profile)
        train_out = TrainingAdapter().run(inp)
        eval_out = EvaluationAdapter().run(inp)
        replay_out = ReplayDriver().run(inp)
        paper_out = PaperDriver().run(inp)

        assert train_out.best_action == eval_out.best_action
        assert eval_out.best_action == replay_out.best_action
        assert replay_out.best_action == paper_out.best_action

    def test_all_adapters_same_long_r_net(
        self, swing_profile: SimulationProfile
    ) -> None:
        """All adapters should produce identical long realized_r_net."""
        inp = make_valid_input(swing_profile)
        train_out = TrainingAdapter().run(inp)
        eval_out = EvaluationAdapter().run(inp)
        replay_out = ReplayDriver().run(inp)
        paper_out = PaperDriver().run(inp)

        assert train_out.long_outcome.realized_r_net == pytest.approx(
            eval_out.long_outcome.realized_r_net
        )
        assert eval_out.long_outcome.realized_r_net == pytest.approx(
            replay_out.long_outcome.realized_r_net
        )
        assert replay_out.long_outcome.realized_r_net == pytest.approx(
            paper_out.long_outcome.realized_r_net
        )

    def test_all_adapters_same_resolution(
        self, swing_profile: SimulationProfile
    ) -> None:
        """All adapters should produce same resolution_status."""
        inp = make_valid_input(swing_profile)
        results = [
            TrainingAdapter().run(inp).resolution_status,
            EvaluationAdapter().run(inp).resolution_status,
            ReplayDriver().run(inp).resolution_status,
            PaperDriver().run(inp).resolution_status,
        ]
        assert all(r == results[0] for r in results), (
            f"Resolution mismatch: {results}"
        )
