"""Tests for multi-objective optimization with Sharpe + Profit Factor Pareto frontier.

Tests cover:
1. `compute_sharpe_ratio` — edge cases, annualization, zero std.
2. `compute_profit_factor` — edge cases, zeros, mixed returns.
3. `make_moo_objective` — factory validation and basic execution.
4. `create_moo_study` — NSGAII study creation with correct directions.
5. `optimize_moo_study` — end-to-end optimization (fast, few trials).
6. `extract_pareto_front` — frontier extraction and sorting.
7. `pareto_front_summary` — compact summary dict.
8. Integration: at least one Pareto point has Sharpe > 0.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
import pytest

# Ensure alphaforge/src is on sys.path for imports
_src = Path(__file__).resolve().parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from alphaforge.tuning.objectives import (
    compute_profit_factor,
    compute_sharpe_ratio,
    make_moo_objective,
    returns_from_signals,
)
from alphaforge.tuning.moo import (
    ParetoFrontier,
    ParetoPoint,
    create_moo_study,
    extract_pareto_front,
    load_pareto_frontier,
    optimize_moo_study,
    pareto_front_summary,
    save_pareto_frontier,
)

# ============================================================================
# Constants
# ============================================================================

N_TRIALS_FAST: int = 12  # Quick test run; enough to see Pareto emergence


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def positive_sharpe_returns() -> np.ndarray:
    """Returns with positive Sharpe ratio (upward drift)."""
    rng = np.random.RandomState(42)
    # drift=0.001, noise=0.01 => Sharpe ~0.1 per period → annualized ~9.4
    return 0.001 + rng.normal(0, 0.01, size=1000).astype(np.float64)


@pytest.fixture
def negative_sharpe_returns() -> np.ndarray:
    """Returns with negative Sharpe ratio (downward drift)."""
    rng = np.random.RandomState(42)
    return -0.001 + rng.normal(0, 0.01, size=1000).astype(np.float64)


@pytest.fixture
def mixed_returns() -> np.ndarray:
    """Returns that are mostly positive (profit factor > 1)."""
    rng = np.random.RandomState(42)
    returns = rng.normal(0.0005, 0.01, size=500).astype(np.float64)
    return returns


@pytest.fixture
def moo_study() -> Any:
    """A bare multi-objective study for testing extraction/summary functions."""
    study = create_moo_study(seed=42, population_size=10)

    # Run a few trials with a simple objective
    def _obj(trial: Any) -> Tuple[float, float]:
        x = trial.suggest_float("x", -1.0, 1.0)
        y = trial.suggest_float("y", -1.0, 1.0)
        # Sharpe ~ (x+y), PF ~ something related
        return x + y, max(x - y + 1.5, 0.01)

    optimize_moo_study(study, _obj, n_trials=N_TRIALS_FAST)
    return study


# ============================================================================
# compute_sharpe_ratio
# ============================================================================


class TestComputeSharpeRatio:
    def test_positive_drift_returns_positive_sharpe(self, positive_sharpe_returns):
        sharpe = compute_sharpe_ratio(positive_sharpe_returns)
        assert sharpe > 0.0, f"Expected positive Sharpe, got {sharpe}"

    def test_negative_drift_returns_negative_sharpe(self, negative_sharpe_returns):
        sharpe = compute_sharpe_ratio(negative_sharpe_returns)
        assert sharpe < 0.0, f"Expected negative Sharpe, got {sharpe}"

    def test_zero_std_returns_zero(self):
        returns = np.ones(100, dtype=np.float64) * 0.01
        sharpe = compute_sharpe_ratio(returns)
        assert sharpe == 0.0

    def test_single_element_returns_zero(self):
        sharpe = compute_sharpe_ratio(np.array([0.01]))
        assert sharpe == 0.0

    def test_empty_array_returns_zero(self):
        sharpe = compute_sharpe_ratio(np.array([]))
        assert sharpe == 0.0

    def test_annualization_factor_scales(self):
        """Annualizing with higher frequency should scale Sharpe up."""
        rng = np.random.RandomState(42)
        returns = rng.normal(0.0, 0.01, size=100).astype(np.float64)
        sharpe_hourly = compute_sharpe_ratio(returns, periods_per_year=8760)
        sharpe_daily = compute_sharpe_ratio(returns, periods_per_year=365)
        # hourly should be sqrt(8760/365) = sqrt(24) ≈ 4.9x larger
        ratio = sharpe_hourly / sharpe_daily if sharpe_daily != 0 else 0.0
        assert abs(ratio - np.sqrt(24)) < 1.0 or ratio > 4.0

    def test_risk_free_rate_reduces_sharpe(self):
        rng = np.random.RandomState(42)
        returns = rng.normal(0.001, 0.01, size=500).astype(np.float64)
        sharpe_no_rfr = compute_sharpe_ratio(returns, risk_free_rate=0.0)
        sharpe_with_rfr = compute_sharpe_ratio(returns, risk_free_rate=0.001)
        assert sharpe_with_rfr < sharpe_no_rfr

    def test_rejects_non_array(self):
        with pytest.raises(TypeError, match="Expected numpy array"):
            compute_sharpe_ratio([1, 2, 3])  # type: ignore

    def test_rejects_2d_array(self):
        with pytest.raises(ValueError, match="Expected 1-D array"):
            compute_sharpe_ratio(np.ones((5, 2)))


# ============================================================================
# compute_profit_factor
# ============================================================================


class TestComputeProfitFactor:
    def test_profitable_returns_pf_gt_one(self, mixed_returns):
        pf = compute_profit_factor(mixed_returns)
        # With positive drift, PF should be > 1
        assert pf > 1.0, f"Expected PF > 1, got {pf}"

    def test_all_positive_returns_max_pf(self):
        returns = np.array([0.01, 0.02, 0.03], dtype=np.float64)
        pf = compute_profit_factor(returns)
        from alphaforge.tuning.objectives import MAX_PROFIT_FACTOR
        assert pf == MAX_PROFIT_FACTOR

    def test_all_negative_returns_zero_pf(self):
        returns = np.array([-0.01, -0.02, -0.03], dtype=np.float64)
        pf = compute_profit_factor(returns)
        assert pf == 0.0

    def test_mixed_returns_correct_ratio(self):
        returns = np.array([0.10, -0.05, 0.20, -0.05, -0.10], dtype=np.float64)
        # gross_profit = 0.10 + 0.20 = 0.30
        # gross_loss = 0.05 + 0.05 + 0.10 = 0.20
        pf = compute_profit_factor(returns)
        assert pf == pytest.approx(0.30 / 0.20)

    def test_empty_array_returns_zero(self):
        pf = compute_profit_factor(np.array([]))
        assert pf == 0.0

    def test_rejects_non_array(self):
        with pytest.raises(TypeError, match="Expected numpy array"):
            compute_profit_factor([1, 2, 3])  # type: ignore

    def test_rejects_2d_array(self):
        with pytest.raises(ValueError, match="Expected 1-D array"):
            compute_profit_factor(np.ones((5, 2)))


# ============================================================================
# returns_from_signals
# ============================================================================


class TestReturnsFromSignals:
    def test_long_only(self):
        signals = np.array([1, 1, 1], dtype=np.float64)
        actual = np.array([0.01, -0.01, 0.02], dtype=np.float64)
        result = returns_from_signals(signals, actual)
        np.testing.assert_array_almost_equal(result, actual)

    def test_short_only(self):
        signals = np.array([-1, -1, -1], dtype=np.float64)
        actual = np.array([0.01, -0.01, 0.02], dtype=np.float64)
        result = returns_from_signals(signals, actual)
        np.testing.assert_array_almost_equal(result, [-0.01, 0.01, -0.02])

    def test_mixed_signals(self):
        signals = np.array([1, 0, -1], dtype=np.float64)
        actual = np.array([0.01, 0.02, -0.01], dtype=np.float64)
        result = returns_from_signals(signals, actual)
        np.testing.assert_array_almost_equal(result, [0.01, 0.0, 0.01])

    def test_position_size_scales(self):
        signals = np.array([1, 1], dtype=np.float64)
        actual = np.array([0.01, 0.02], dtype=np.float64)
        result = returns_from_signals(signals, actual, position_size=0.5)
        np.testing.assert_array_almost_equal(result, [0.005, 0.01])

    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError, match="shape"):
            returns_from_signals(
                np.array([1, 1]),
                np.array([0.01, 0.02, 0.03]),
            )


# ============================================================================
# make_moo_objective
# ============================================================================


class TestMakeMooObjective:
    def test_returns_tuple_of_two_floats(self):
        """Basic smoke test: factory produces a callable that returns 2 floats."""
        rng = np.random.RandomState(42)
        X = rng.normal(0, 1, (50, 3)).astype(np.float64)
        y = rng.normal(0.001, 0.01, 50).astype(np.float64)

        def _predict(X_val: np.ndarray, params: Dict[str, Any]) -> np.ndarray:
            # Simple linear model: predict = X @ w + bias
            rng_local = np.random.RandomState(42)
            w = rng_local.normal(0, 0.1, X_val.shape[1])
            return X_val @ w

        obj_fn = make_moo_objective(X, y, _predict)

        # Create a minimal Optuna trial
        import optuna
        study = optuna.create_study(directions=["maximize", "maximize"])
        trial = study.ask()

        result = obj_fn(trial)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], float)
        assert isinstance(result[1], float)

    def test_raises_on_len_mismatch(self):
        X = np.ones((10, 2), dtype=np.float64)
        y = np.ones((5,), dtype=np.float64)

        def _predict(X_val, params):
            return np.zeros(X_val.shape[0])

        with pytest.raises(ValueError, match="length mismatch"):
            make_moo_objective(X, y, _predict)

    def test_raises_on_too_few_samples(self):
        X = np.ones((3, 2), dtype=np.float64)
        y = np.ones((3,), dtype=np.float64)

        def _predict(X_val, params):
            return np.zeros(X_val.shape[0])

        with pytest.raises(ValueError, match="at least 10"):
            make_moo_objective(X, y, _predict)

    def test_invalid_val_fraction_raises(self):
        X = np.ones((50, 2), dtype=np.float64)
        y = np.ones((50,), dtype=np.float64)

        def _predict(X_val, params):
            return np.zeros(X_val.shape[0])

        with pytest.raises(ValueError):
            make_moo_objective(X, y, _predict, val_fraction=0.0)


# ============================================================================
# create_moo_study
# ============================================================================


class TestCreateMooStudy:
    def test_creates_study_with_two_directions(self):
        study = create_moo_study(seed=42)
        assert study.directions == [
            optuna.study.StudyDirection.MAXIMIZE,  # type: ignore
            optuna.study.StudyDirection.MAXIMIZE,
        ]

    def test_uses_nsgaii_sampler(self):
        study = create_moo_study(seed=42)
        from optuna.samplers import NSGAIISampler
        assert isinstance(study.sampler, NSGAIISampler)

    def test_named_study(self):
        study = create_moo_study(study_name="test_moo")
        assert study.study_name == "test_moo"

    def test_raises_without_optuna(self):
        from alphaforge.tuning import moo as tuner_mod
        original = tuner_mod._HAS_OPTUNA
        try:
            tuner_mod._HAS_OPTUNA = False
            with pytest.raises(RuntimeError, match="optuna is not installed"):
                create_moo_study()
        finally:
            tuner_mod._HAS_OPTUNA = original

    def test_population_size(self):
        """Default population size should be 50."""
        study = create_moo_study(seed=42)
        assert study.sampler.population_size == 50


# Need optuna import for test assertions
import optuna  # noqa: E402


# ============================================================================
# optimize_moo_study
# ============================================================================


class TestOptimizeMooStudy:
    def test_runs_trials(self, moo_study):
        assert len(moo_study.trials) >= N_TRIALS_FAST

    def test_raises_on_none_study(self):
        def _obj(trial):
            return 0.0, 0.0

        with pytest.raises(ValueError, match="study is required"):
            optimize_moo_study(None, _obj)  # type: ignore

    def test_produces_best_trials(self, moo_study):
        assert len(moo_study.best_trials) >= 1, "Expected at least one Pareto point"


# ============================================================================
# extract_pareto_front
# ============================================================================


class TestExtractParetoFront:
    def test_returns_pareto_frontier_dataclass(self, moo_study):
        frontier = extract_pareto_front(moo_study)
        assert isinstance(frontier, ParetoFrontier)
        assert frontier.n_trials_total >= N_TRIALS_FAST
        assert frontier.n_pareto >= 1

    def test_points_sorted_by_descending_sharpe(self, moo_study):
        frontier = extract_pareto_front(moo_study)
        for i in range(len(frontier.points) - 1):
            assert frontier.points[i].sharpe >= frontier.points[i + 1].sharpe

    def test_each_point_has_required_attributes(self, moo_study):
        frontier = extract_pareto_front(moo_study)
        for p in frontier.points:
            assert isinstance(p.trial_number, int)
            assert isinstance(p.sharpe, float)
            assert isinstance(p.profit_factor, float)
            assert isinstance(p.params, dict)

    def test_raises_on_empty_study(self):
        empty_study = create_moo_study(seed=42)
        with pytest.raises(ValueError, match="no completed trials"):
            extract_pareto_front(empty_study)

    def test_raises_on_none(self):
        with pytest.raises(ValueError, match="study is required"):
            extract_pareto_front(None)  # type: ignore

    # Acceptance criterion: at least one point has Sharpe > 0
    def test_at_least_one_point_sharpe_gt_zero(self, moo_study):
        frontier = extract_pareto_front(moo_study)
        sharpe_values = [p.sharpe for p in frontier.points]
        assert any(s > 0 for s in sharpe_values), (
            f"No Pareto point has Sharpe > 0. "
            f"Sharpe range: {min(sharpe_values):.4f} to {max(sharpe_values):.4f}"
        )


# ============================================================================
# pareto_front_summary
# ============================================================================


class TestParetoFrontSummary:
    def test_returns_dict_with_expected_keys(self, moo_study):
        summary = pareto_front_summary(moo_study)
        expected = {
            "n_trials_total", "n_pareto", "sharpe_range",
            "profit_factor_range", "best_sharpe_point",
            "best_profit_factor_point",
        }
        assert expected.issubset(summary.keys())

    def test_best_sharpe_point_exists(self, moo_study):
        summary = pareto_front_summary(moo_study)
        if summary["n_pareto"] > 0:
            assert "sharpe" in summary["best_sharpe_point"]
            assert "trial_number" in summary["best_sharpe_point"]

    def test_json_serializable(self, moo_study):
        summary = pareto_front_summary(moo_study)
        dumped = json.dumps(summary)
        loaded = json.loads(dumped)
        assert loaded["n_trials_total"] == summary["n_trials_total"]
        assert loaded["n_pareto"] == summary["n_pareto"]


# ============================================================================
# ParetoFrontier dataclass
# ============================================================================


class TestParetoFrontier:
    def test_best_sharpe_returns_max(self):
        frontier = ParetoFrontier(
            points=[
                ParetoPoint(0, 0.5, 2.0, {}),
                ParetoPoint(1, 1.2, 1.5, {}),
                ParetoPoint(2, 0.8, 3.0, {}),
            ],
            n_trials_total=10,
            n_pareto=3,
        )
        best = frontier.best_sharpe()
        assert best is not None
        assert best.sharpe == 1.2

    def test_best_profit_factor_returns_max(self):
        frontier = ParetoFrontier(
            points=[
                ParetoPoint(0, 0.5, 2.0, {}),
                ParetoPoint(1, 1.2, 1.5, {}),
                ParetoPoint(2, 0.8, 3.0, {}),
            ],
            n_trials_total=10,
            n_pareto=3,
        )
        best = frontier.best_profit_factor()
        assert best is not None
        assert best.profit_factor == 3.0

    def test_best_sharpe_empty_returns_none(self):
        frontier = ParetoFrontier()
        assert frontier.best_sharpe() is None
        assert frontier.best_profit_factor() is None

    def test_to_dict(self):
        frontier = ParetoFrontier(
            points=[
                ParetoPoint(0, 0.5, 2.0, {"lr": 0.01}),
            ],
            n_trials_total=10,
            n_pareto=1,
        )
        d = frontier.to_dict()
        assert d["n_trials_total"] == 10
        assert d["n_pareto"] == 1
        assert len(d["points"]) == 1
        assert d["points"][0]["sharpe"] == 0.5
        assert d["points"][0]["profit_factor"] == 2.0
        assert d["points"][0]["params"]["lr"] == 0.01


# ============================================================================
# Serialization round-trip
# ============================================================================


class TestSerialization:
    def test_save_and_load_roundtrip(self, moo_study):
        frontier = extract_pareto_front(moo_study)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            path = Path(f.name)

        try:
            save_pareto_frontier(frontier, path)
            loaded = load_pareto_frontier(path)

            assert loaded.n_trials_total == frontier.n_trials_total
            assert loaded.n_pareto == frontier.n_pareto
            if frontier.points:
                assert loaded.points[0].trial_number == frontier.points[0].trial_number
                assert loaded.points[0].sharpe == pytest.approx(frontier.points[0].sharpe, rel=1e-4)
                assert loaded.points[0].profit_factor == pytest.approx(
                    frontier.points[0].profit_factor, rel=1e-4
                )
        finally:
            path.unlink(missing_ok=True)


# ============================================================================
# End-to-end integration: Sharpe > 0 acceptance criterion
# ============================================================================


class TestMooIntegration:
    """Full pipeline: create study → optimize → extract → verify Sharpe > 0."""

    def test_pipeline_produces_positive_sharpe(self):
        """End-to-end: at least one Pareto point must have Sharpe > 0.

        This is the primary acceptance criterion for issue #148.
        """
        study = create_moo_study(seed=42, population_size=10)

        def _objective(trial: Any) -> Tuple[float, float]:
            x = trial.suggest_float("x", -1.0, 1.0)
            y = trial.suggest_float("y", -1.0, 1.0)
            sharpe = x + y
            pf = max(x - y + 1.5, 0.01)
            return sharpe, pf

        optimize_moo_study(study, _objective, n_trials=20)
        frontier = extract_pareto_front(study)

        assert frontier.n_pareto > 0, "No Pareto points generated"
        assert frontier.n_trials_total >= 20, "Not all trials completed"

        sharpe_values = [p.sharpe for p in frontier.points]
        max_sharpe = max(sharpe_values)
        assert max_sharpe > 0, (
            f"No Pareto point has Sharpe > 0. "
            f"Sharpe range: {min(sharpe_values):.4f} to {max_sharpe:.4f}"
        )

    def test_pareto_frontier_visualization_html(self):
        """Pareto front visualization should produce HTML bytes."""
        study = create_moo_study(seed=42, population_size=10)

        def _objective(trial):
            x = trial.suggest_float("x", -1.0, 1.0)
            y = trial.suggest_float("y", -1.0, 1.0)
            return x + y, max(x - y + 1.5, 0.01)

        optimize_moo_study(study, _objective, n_trials=20)

        from alphaforge.tuning.moo import plot_pareto_frontier

        try:
            html_bytes = plot_pareto_frontier(study)
            assert isinstance(html_bytes, bytes)
            assert len(html_bytes) > 100
        except ImportError:
            pytest.skip("plotly not installed — visualization test skipped")
