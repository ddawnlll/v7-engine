"""Tests for Nested WFV Autotune Engine.

Tests cover:
- Dataclass construction and defaults
- Input validation
- Synthetic data autotune run (happy path)
- Constraint filtering
- Edge cases (small data, empty grid)
"""

from __future__ import annotations
import pytest
pytestmark = pytest.mark.integration


import math
from typing import Any, Dict, List

import numpy as np
import pytest

from alphaforge.tuning.autotune import (
    AutotuneResult,
    DEFAULT_GRID,
    HyperparameterGrid,
    InnerTrialResult,
    NestedWFVAutotune,
    NestedWFVConfig,
    OuterFoldResult,
    run_nested_wfv_autotune,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_data() -> Dict[str, Any]:
    """Generate synthetic feature matrix and labels for testing.

    Creates data where feature_0 has moderate predictive signal for
    LONG_NOW (positive values) vs SHORT_NOW (negative values), and
    NO_TRADE (near-zero values).
    """
    n_samples = 200
    n_features = 5
    rng = np.random.RandomState(42)

    X = rng.randn(n_samples, n_features).astype(np.float64)

    # Create labels with some signal based on feature_0
    y_list: List[str] = []
    for i in range(n_samples):
        f0 = X[i, 0]
        if f0 > 0.5:
            y_list.append("LONG_NOW")
        elif f0 < -0.5:
            y_list.append("SHORT_NOW")
        else:
            # Random for ambiguous region
            y_list.append(rng.choice(["LONG_NOW", "SHORT_NOW", "NO_TRADE"]))

    # Ensure some NO_TRADE labels exist (at least 15%)
    no_trade_count = sum(1 for yl in y_list if yl == "NO_TRADE")
    if no_trade_count < 30:
        for i in range(30 - no_trade_count):
            idx = rng.randint(0, n_samples)
            y_list[idx] = "NO_TRADE"

    y = np.array(y_list)
    timestamps = [
        f"2025-01-01T{i:06d}" for i in range(n_samples)
    ]
    symbols = ["BTCUSDT"] * n_samples
    feature_names = [f"feature_{i}" for i in range(n_features)]

    return {
        "X": X,
        "y": y,
        "timestamps": timestamps,
        "symbols": symbols,
        "feature_names": feature_names,
    }


@pytest.fixture
def small_config() -> NestedWFVConfig:
    """Small config for fast tests: 2 outer folds, 2 inner folds, tiny grid."""
    return NestedWFVConfig(
        outer_folds=2,
        inner_folds=2,
        train_window_bars=50,
        test_window_bars=20,
        purge_bars=5,
        embargo_bars=3,
        min_active_trades=5,
    )


@pytest.fixture
def tiny_grid() -> HyperparameterGrid:
    """Tiny grid for fast tests: 2 values per parameter = 512 combinations."""
    return HyperparameterGrid(
        max_depth=[3, 4],
        learning_rate=[0.05, 0.10],
        n_estimators=[50, 100],
        subsample=[0.8],
        colsample_bytree=[0.8],
        min_child_weight=[3],
        gamma=[0.1],
        reg_alpha=[0.1],
        reg_lambda=[1.0],
    )


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestHyperparameterGrid:
    """Tests for HyperparameterGrid dataclass."""

    def test_default_grid_has_combinations(self) -> None:
        """DEFAULT_GRID should have a reasonable number of combinations."""
        grid = DEFAULT_GRID
        assert grid.n_combinations > 0
        assert grid.n_combinations > 100  # at least 100 combos

    def test_iter_combinations_yields_dicts(self) -> None:
        """iter_combinations should yield dicts with expected keys."""
        grid = HyperparameterGrid(
            max_depth=[3],
            learning_rate=[0.05],
            n_estimators=[100],
            subsample=[0.8, 1.0],
            colsample_bytree=[0.8],
            min_child_weight=[3],
            gamma=[0.1],
            reg_alpha=[0.1],
            reg_lambda=[1.0],
        )
        combos = list(grid.iter_combinations())
        assert len(combos) == 2  # only subsample varies
        for c in combos:
            assert "max_depth" in c
            assert "learning_rate" in c
            assert c["max_depth"] == 3

    def test_iter_combinations_product(self) -> None:
        """iter_combinations should produce the full Cartesian product."""
        grid = HyperparameterGrid(
            max_depth=[3, 4],
            learning_rate=[0.05, 0.10],
            n_estimators=[100],
            subsample=[0.8],
            colsample_bytree=[0.8],
            min_child_weight=[3],
            gamma=[0.1],
            reg_alpha=[0.1],
            reg_lambda=[1.0],
        )
        combos = list(grid.iter_combinations())
        assert len(combos) == 4  # 2 * 2 = 4


class TestNestedWFVConfig:
    """Tests for NestedWFVConfig dataclass."""

    def test_defaults(self) -> None:
        """Default NestedWFVConfig should have sensible defaults."""
        cfg = NestedWFVConfig()
        assert cfg.outer_folds == 3
        assert cfg.inner_folds == 3
        assert cfg.min_active_trades == 30
        assert cfg.weight_expectancy == 1.0
        assert cfg.no_trade_collapse_threshold == 0.60
        assert cfg.no_trade_collapse_penalty == -2.0


class TestInnerTrialResult:
    """Tests for InnerTrialResult dataclass."""

    def test_construction(self) -> None:
        """InnerTrialResult should store all fields correctly."""
        trial = InnerTrialResult(
            hyperparams={"max_depth": 4, "learning_rate": 0.05},
            inner_score=0.5,
            inner_expectancy=0.1,
            inner_sharpe=0.5,
            inner_active_trades=50,
            inner_no_trade_ratio=0.3,
            inner_cost_survival=True,
            inner_fold_stability=0.8,
            passes_min_active_trades=True,
            passes_no_trade_guard=True,
            passes_cost_survival=True,
            passes_fold_stability=True,
        )
        assert trial.hyperparams["max_depth"] == 4
        assert trial.inner_score == 0.5
        assert trial.inner_active_trades == 50
        assert trial.passes_min_active_trades is True


class TestOuterFoldResult:
    """Tests for OuterFoldResult dataclass."""

    def test_construction(self) -> None:
        """OuterFoldResult should store all fields correctly."""
        result = OuterFoldResult(
            outer_fold_index=0,
            best_inner_hyperparams={"max_depth": 4},
            inner_score=0.5,
            outer_score=0.6,
            outer_expectancy=0.15,
            outer_sharpe=0.8,
            outer_active_trades=60,
            outer_no_trade_ratio=0.2,
            outer_cost_survival=True,
            outer_fold_stability=0.9,
            inner_trials_count=100,
            inner_trials_passing=10,
        )
        assert result.outer_fold_index == 0
        assert result.outer_score == 0.6
        assert result.outer_active_trades == 60


class TestAutotuneResult:
    """Tests for AutotuneResult dataclass."""

    def test_construction(self) -> None:
        """AutotuneResult should store all fields correctly."""
        result = AutotuneResult(
            best_hyperparams={"max_depth": 4},
            best_score=0.6,
            best_outer_expectancy=0.15,
            best_outer_sharpe=0.8,
            best_outer_active_trades=60,
            verdict="PASS",
        )
        assert result.best_hyperparams["max_depth"] == 4
        assert result.best_score == 0.6
        assert result.verdict == "PASS"


# ---------------------------------------------------------------------------
# NestedWFVAutotune unit tests
# ---------------------------------------------------------------------------


class TestNestedWFVAutotuneInit:
    """Tests for NestedWFVAutotune initialization."""

    def test_valid_construction(self) -> None:
        """Constructing with valid mode should work."""
        tuner = NestedWFVAutotune(mode="SWING")
        assert tuner.mode == "SWING"
        assert tuner.config.outer_folds == 3

    def test_invalid_mode_raises(self) -> None:
        """Constructing with invalid mode should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported mode"):
            NestedWFVAutotune(mode="INVALID")

    def test_custom_config(self) -> None:
        """Custom config should override defaults."""
        config = NestedWFVConfig(outer_folds=5, min_active_trades=100)
        tuner = NestedWFVAutotune(config=config)
        assert tuner.config.outer_folds == 5
        assert tuner.config.min_active_trades == 100


class TestInputValidation:
    """Tests for input validation."""

    def test_valid_inputs_pass(self, synthetic_data: Dict[str, Any]) -> None:
        """Valid inputs should not raise."""
        NestedWFVAutotune._validate_inputs(
            synthetic_data["X"],
            synthetic_data["y"],
            synthetic_data["timestamps"],
            synthetic_data["symbols"],
            synthetic_data["feature_names"],
        )

    def test_X_not_ndarray_raises(self, synthetic_data: Dict[str, Any]) -> None:
        """Non-ndarray X should raise TypeError."""
        with pytest.raises(TypeError, match="X must be numpy"):
            NestedWFVAutotune._validate_inputs(
                [1, 2, 3],  # type: ignore[arg-type]
                synthetic_data["y"],
                synthetic_data["timestamps"],
                synthetic_data["symbols"],
                synthetic_data["feature_names"],
            )

    def test_wrong_dimensions_raises(
        self, synthetic_data: Dict[str, Any]
    ) -> None:
        """Wrong-dimensional X should raise ValueError."""
        with pytest.raises(ValueError, match="X must be 2D"):
            NestedWFVAutotune._validate_inputs(
                synthetic_data["X"][:, 0],  # 1D
                synthetic_data["y"],
                synthetic_data["timestamps"],
                synthetic_data["symbols"],
                synthetic_data["feature_names"],
            )

    def test_mismatched_lengths_raises(
        self, synthetic_data: Dict[str, Any]
    ) -> None:
        """Mismatched X/y lengths should raise ValueError."""
        with pytest.raises(ValueError, match="must have same length"):
            NestedWFVAutotune._validate_inputs(
                synthetic_data["X"],
                synthetic_data["y"][:50],
                synthetic_data["timestamps"],
                synthetic_data["symbols"],
                synthetic_data["feature_names"],
            )

    def test_too_few_samples_raises(
        self, synthetic_data: Dict[str, Any]
    ) -> None:
        """Too few samples should raise ValueError."""
        small_X = synthetic_data["X"][:10]
        small_y = synthetic_data["y"][:10]
        with pytest.raises(ValueError, match="at least 50 samples"):
            NestedWFVAutotune._validate_inputs(
                small_X, small_y,
                synthetic_data["timestamps"][:10],
                synthetic_data["symbols"][:10],
                synthetic_data["feature_names"],
            )

    def test_all_nan_raises(self, synthetic_data: Dict[str, Any]) -> None:
        """All-NaN X should raise ValueError."""
        nan_X = np.full_like(synthetic_data["X"], np.nan)
        with pytest.raises(ValueError, match="all NaN"):
            NestedWFVAutotune._validate_inputs(
                nan_X,
                synthetic_data["y"],
                synthetic_data["timestamps"],
                synthetic_data["symbols"],
                synthetic_data["feature_names"],
            )

    def test_wrong_timestamps_length_raises(
        self, synthetic_data: Dict[str, Any]
    ) -> None:
        """Mismatched timestamps length should raise ValueError."""
        with pytest.raises(ValueError, match="timestamps length"):
            NestedWFVAutotune._validate_inputs(
                synthetic_data["X"],
                synthetic_data["y"],
                synthetic_data["timestamps"][:50],
                synthetic_data["symbols"],
                synthetic_data["feature_names"],
            )


class TestEncodeLabels:
    """Tests for label encoding."""

    def test_string_labels(self) -> None:
        """String labels should encode to 0/1/2."""
        y = np.array(["LONG_NOW", "SHORT_NOW", "NO_TRADE"])
        encoded = NestedWFVAutotune._encode_labels(y)
        assert list(encoded) == [0, 1, 2]

    def test_integer_labels(self) -> None:
        """Integer labels should pass through."""
        y = np.array([0, 1, 2, 0], dtype=np.int32)
        encoded = NestedWFVAutotune._encode_labels(y)
        assert list(encoded) == [0, 1, 2, 0]

    def test_invalid_integer_raises(self) -> None:
        """Integer labels outside 0/1/2 should raise ValueError."""
        y = np.array([0, 1, 3])
        with pytest.raises(ValueError, match="must be in"):
            NestedWFVAutotune._encode_labels(y)

    def test_invalid_string_raises(self) -> None:
        """Unknown string labels should raise ValueError."""
        y = np.array(["UNKNOWN"])
        with pytest.raises(ValueError, match="Unknown label"):
            NestedWFVAutotune._encode_labels(y)


class TestPredictionsToReturns:
    """Tests for _predictions_to_returns."""

    def test_correct_direction(self) -> None:
        """Correct active predictions should return +1.0."""
        pred = np.array([0, 1], dtype=np.int32)
        true = np.array([0, 1], dtype=np.int32)
        returns = NestedWFVAutotune._predictions_to_returns(pred, true)
        assert list(returns) == [1.0, 1.0]

    def test_wrong_direction(self) -> None:
        """Wrong direction predictions should return -1.0."""
        pred = np.array([0, 1], dtype=np.int32)
        true = np.array([1, 0], dtype=np.int32)
        returns = NestedWFVAutotune._predictions_to_returns(pred, true)
        assert list(returns) == [-1.0, -1.0]

    def test_false_positive(self) -> None:
        """Active prediction when true is NO_TRADE should return -0.5."""
        pred = np.array([0, 1], dtype=np.int32)
        true = np.array([2, 2], dtype=np.int32)
        returns = NestedWFVAutotune._predictions_to_returns(pred, true)
        assert list(returns) == [-0.5, -0.5]

    def test_no_trade_prediction(self) -> None:
        """NO_TRADE predictions should return 0.0."""
        pred = np.array([2, 2], dtype=np.int32)
        true = np.array([0, 2], dtype=np.int32)
        returns = NestedWFVAutotune._predictions_to_returns(pred, true)
        assert list(returns) == [0.0, 0.0]

    def test_mixed(self) -> None:
        """Mixed predictions should produce correct returns."""
        pred = np.array([0, 1, 2, 0, 1], dtype=np.int32)
        true = np.array([0, 0, 2, 2, 1], dtype=np.int32)
        returns = NestedWFVAutotune._predictions_to_returns(pred, true)
        # 0: correct -> 1.0
        # 1: wrong direction (short vs long) -> -1.0
        # 2: no-trade -> 0.0
        # 3: false positive long -> -0.5
        # 4: correct short -> 1.0
        expected = [1.0, -1.0, 0.0, -0.5, 1.0]
        assert list(returns) == expected


class TestComputeScore:
    """Tests for _compute_score."""

    def test_positive_expectancy_scores_well(self) -> None:
        """Positive expectancy with good metrics should score well."""
        config = NestedWFVConfig(
            weight_expectancy=1.0,
            weight_sharpe=0.5,
            weight_trade_count=0.2,
            weight_stability=0.3,
            no_trade_collapse_threshold=0.60,
            no_trade_collapse_penalty=-2.0,
        )
        tuner = NestedWFVAutotune(config=config)
        score = tuner._compute_score(
            expectancy_r=0.2,
            sharpe=1.0,
            active_trades=100,
            fold_stability=0.8,
            no_trade_ratio=0.3,
            cost_survival=True,
        )
        # 1.0*0.2 + 0.5*1.0 + 0.2*log1p(100) + 0.3*0.8 + 0.1
        expected = 0.2 + 0.5 + 0.2 * math.log1p(100) + 0.24 + 0.1
        assert abs(score - expected) < 1e-6

    def test_no_trade_collapse_penalty(self) -> None:
        """NO_TRADE ratio above threshold should apply penalty."""
        config = NestedWFVConfig(
            no_trade_collapse_threshold=0.60,
            no_trade_collapse_penalty=-2.0,
        )
        tuner = NestedWFVAutotune(config=config)
        score_no_penalty = tuner._compute_score(
            expectancy_r=0.1, sharpe=0.5, active_trades=50,
            fold_stability=0.8, no_trade_ratio=0.59, cost_survival=True,
        )
        score_penalty = tuner._compute_score(
            expectancy_r=0.1, sharpe=0.5, active_trades=50,
            fold_stability=0.8, no_trade_ratio=0.61, cost_survival=True,
        )
        # Penalty should reduce score by -2.0
        assert score_penalty < score_no_penalty
        assert abs(
            (score_penalty - score_no_penalty)
            - NestedWFVConfig().no_trade_collapse_penalty
        ) < 1e-6

    def test_cost_survival_bonus(self) -> None:
        """Cost survival should add a small bonus."""
        config = NestedWFVConfig()
        tuner = NestedWFVAutotune(config=config)
        score_survive = tuner._compute_score(
            expectancy_r=0.1, sharpe=0.5, active_trades=50,
            fold_stability=0.8, no_trade_ratio=0.3, cost_survival=True,
        )
        score_no_survive = tuner._compute_score(
            expectancy_r=0.1, sharpe=0.5, active_trades=50,
            fold_stability=0.8, no_trade_ratio=0.3, cost_survival=False,
        )
        assert abs(score_survive - score_no_survive - 0.1) < 1e-6


class TestCheckCostSurvival:
    """Tests for _check_cost_survival."""

    def test_positive_expectancy_survives(self) -> None:
        """Positive expectancy above cost should survive."""
        assert NestedWFVAutotune._check_cost_survival(0.1) is True

    def test_negative_expectancy_fails(self) -> None:
        """Negative expectancy should not survive."""
        assert NestedWFVAutotune._check_cost_survival(-0.1) is False

    def test_small_positive_may_fail(self) -> None:
        """Very small positive expectancy below cost should not survive."""
        assert NestedWFVAutotune._check_cost_survival(0.01) is False


class TestBuildOuterFolds:
    """Tests for _build_outer_folds."""

    def test_returns_list_of_tuples(self) -> None:
        """_build_outer_folds should return list of (train, oos) tuples."""
        timestamps = [f"2025-01-01T{i:06d}" for i in range(100)]
        config = NestedWFVConfig(outer_folds=2)
        tuner = NestedWFVAutotune(config=config)
        folds = tuner._build_outer_folds(timestamps)
        assert isinstance(folds, list)
        if folds:
            train, oos = folds[0]
            assert isinstance(train, list)
            assert isinstance(oos, list)
            assert len(train) > 0
            assert len(oos) > 0

    def test_chronological_order(self) -> None:
        """Training indices should come before OOS indices chronologically."""
        timestamps = [f"2025-01-01T{i:06d}" for i in range(200)]
        config = NestedWFVConfig(outer_folds=2)
        tuner = NestedWFVAutotune(config=config)
        folds = tuner._build_outer_folds(timestamps)
        for train, oos in folds:
            if train and oos:
                max_train_ts = max(timestamps[i] for i in train)
                min_oos_ts = min(timestamps[i] for i in oos)
                assert max_train_ts < min_oos_ts

    def test_insufficient_data_returns_empty(self) -> None:
        """Very small datasets should return empty list."""
        timestamps = [f"2025-01-01T{i:06d}" for i in range(5)]
        config = NestedWFVConfig(outer_folds=3)
        tuner = NestedWFVAutotune(config=config)
        folds = tuner._build_outer_folds(timestamps)
        assert folds == []


class TestBuildInnerFolds:
    """Tests for _build_inner_folds."""

    def test_returns_list_of_tuples(self) -> None:
        """_build_inner_folds should return list of (train, val) tuples."""
        timestamps = [f"2025-01-01T{i:06d}" for i in range(200)]
        config = NestedWFVConfig(
            inner_folds=2, train_window_bars=50, test_window_bars=20,
        )
        tuner = NestedWFVAutotune(config=config)
        folds = tuner._build_inner_folds(timestamps)
        assert isinstance(folds, list)
        if folds:
            train, val = folds[0]
            assert isinstance(train, list)
            assert isinstance(val, list)

    def test_insufficient_data_returns_empty(self) -> None:
        """Very small datasets should return empty list."""
        timestamps = [f"2025-01-01T{i:06d}" for i in range(5)]
        config = NestedWFVConfig(
            inner_folds=3, train_window_bars=50, test_window_bars=20,
        )
        tuner = NestedWFVAutotune(config=config)
        folds = tuner._build_inner_folds(timestamps)
        assert folds == []


# ---------------------------------------------------------------------------
# Integration tests (require xgboost)
# ---------------------------------------------------------------------------


class TestEndToEnd:
    """End-to-end integration tests that train actual XGBoost models."""

    def test_autotune_runs_with_synthetic_data(
        self, synthetic_data: Dict[str, Any]
    ) -> None:
        """Full autotune should complete with synthetic data."""
        d = synthetic_data
        config = NestedWFVConfig(
            outer_folds=2,
            inner_folds=2,
            train_window_bars=30,
            test_window_bars=15,
            purge_bars=2,
            embargo_bars=1,
            min_active_trades=2,
            min_cost_survival_ratio=0.0,  # lenient for synthetic data
            min_fold_stability=0.0,       # lenient for synthetic data
        )
        # Use a very small grid for speed
        grid = HyperparameterGrid(
            max_depth=[3],
            learning_rate=[0.05, 0.10],
            n_estimators=[20, 30],
            subsample=[0.8],
            colsample_bytree=[0.8],
            min_child_weight=[3],
            gamma=[0.1],
            reg_alpha=[0.1],
            reg_lambda=[1.0],
        )
        result = run_nested_wfv_autotune(
            X=d["X"],
            y=d["y"],
            timestamps=d["timestamps"],
            symbols=d["symbols"],
            feature_names=d["feature_names"],
            mode="SWING",
            grid=grid,
            config=config,
            random_seed=42,
        )

        # Result should have the expected structure
        assert isinstance(result, AutotuneResult)
        # Best hyperparams should be populated
        assert len(result.best_hyperparams) > 0
        # Score should be a float
        assert isinstance(result.best_score, float)
        # Total trials should be tracked
        assert result.n_total_trials >= 0
        # Verdict should be set
        assert result.verdict in (
            "PASS", "PASS_WITH_WARNINGS", "FAIL", "FAIL_NO_VALID_CANDIDATES"
        )

    def test_autotune_with_integer_labels(
        self, synthetic_data: Dict[str, Any]
    ) -> None:
        """Autotune should work with integer labels too."""
        d = synthetic_data
        y_int = np.array([0, 1, 2] * (len(d["y"]) // 3) +
                         [0] * (len(d["y"]) % 3), dtype=np.int32)

        config = NestedWFVConfig(
            outer_folds=2,
            inner_folds=1,
            train_window_bars=30,
            test_window_bars=10,
            purge_bars=2,
            embargo_bars=1,
            min_active_trades=1,
            min_cost_survival_ratio=0.0,
            min_fold_stability=0.0,
        )
        grid = HyperparameterGrid(
            max_depth=[3],
            learning_rate=[0.05],
            n_estimators=[20],
            subsample=[0.8],
            colsample_bytree=[0.8],
            min_child_weight=[3],
            gamma=[0.1],
            reg_alpha=[0.1],
            reg_lambda=[1.0],
        )
        result = run_nested_wfv_autotune(
            X=d["X"],
            y=y_int,
            timestamps=d["timestamps"],
            symbols=d["symbols"],
            feature_names=d["feature_names"],
            mode="SWING",
            grid=grid,
            config=config,
        )
        assert isinstance(result, AutotuneResult)
        assert len(result.best_hyperparams) > 0

    def test_convenience_function(
        self, synthetic_data: Dict[str, Any]
    ) -> None:
        """The convenience function run_nested_wfv_autotune should work."""
        d = synthetic_data
        config = NestedWFVConfig(
            outer_folds=2,
            inner_folds=1,
            train_window_bars=30,
            test_window_bars=10,
            purge_bars=2,
            embargo_bars=1,
            min_active_trades=1,
            min_cost_survival_ratio=0.0,
            min_fold_stability=0.0,
        )
        grid = HyperparameterGrid(
            max_depth=[3],
            learning_rate=[0.05],
            n_estimators=[20],
            subsample=[0.8],
            colsample_bytree=[0.8],
            min_child_weight=[3],
            gamma=[0.1],
            reg_alpha=[0.1],
            reg_lambda=[1.0],
        )
        result = run_nested_wfv_autotune(
            **d,
            mode="SWING",
            grid=grid,
            config=config,
        )
        assert isinstance(result, AutotuneResult)


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests."""

    def test_too_small_data_returns_fail(self) -> None:
        """Very small data should return FAIL_NO_VALID_CANDIDATES."""
        n_samples = 20
        X = np.random.randn(n_samples, 3).astype(np.float64)
        y = np.random.choice(["LONG_NOW", "NO_TRADE"], size=n_samples)
        ts = [f"2025-01-01T{i:06d}" for i in range(n_samples)]
        syms = ["BTCUSDT"] * n_samples
        fnames = ["f0", "f1", "f2"]

        config = NestedWFVConfig(outer_folds=2, inner_folds=1)
        grid = HyperparameterGrid(
            max_depth=[3],
            learning_rate=[0.05],
            n_estimators=[10],
            subsample=[0.8],
            colsample_bytree=[0.8],
            min_child_weight=[3],
            gamma=[0.1],
            reg_alpha=[0.1],
            reg_lambda=[1.0],
        )

        # Should raise ValueError for < 50 samples
        with pytest.raises(ValueError, match="at least 50 samples"):
            run_nested_wfv_autotune(
                X=X, y=y, timestamps=ts, symbols=syms,
                feature_names=fnames, mode="SWING",
                grid=grid, config=config,
            )

    def test_deterministic_seeding(self) -> None:
        """Same seed should produce same result structure."""
        n_samples = 100
        rng = np.random.RandomState(42)
        X = rng.randn(n_samples, 3).astype(np.float64)
        # Signal based on feature_0
        y_list: List[str] = []
        for i in range(n_samples):
            if X[i, 0] > 0.3:
                y_list.append("LONG_NOW")
            elif X[i, 0] < -0.3:
                y_list.append("SHORT_NOW")
            else:
                y_list.append("NO_TRADE")
        y = np.array(y_list)
        ts = [f"2025-01-01T{i:06d}" for i in range(n_samples)]
        syms = ["BTCUSDT"] * n_samples
        fnames = ["f0", "f1", "f2"]

        config = NestedWFVConfig(
            outer_folds=2, inner_folds=1,
            train_window_bars=20, test_window_bars=10,
            purge_bars=2, embargo_bars=1,
            min_active_trades=3,
            min_cost_survival_ratio=0.0,
            min_fold_stability=0.0,
        )
        grid = HyperparameterGrid(
            max_depth=[3],
            learning_rate=[0.05],
            n_estimators=[10],
            subsample=[0.8],
            colsample_bytree=[0.8],
            min_child_weight=[3],
            gamma=[0.1],
            reg_alpha=[0.1],
            reg_lambda=[1.0],
        )

        result1 = run_nested_wfv_autotune(
            X, y, ts, syms, fnames, config=config, grid=grid, random_seed=42,
        )
        result2 = run_nested_wfv_autotune(
            X, y, ts, syms, fnames, config=config, grid=grid, random_seed=42,
        )
        assert result1.best_hyperparams == result2.best_hyperparams


class TestVerifyCheck:
    """Quick verification that the module is importable and runnable."""

    def test_module_importable(self) -> None:
        """The tuning module should be importable."""
        from alphaforge import tuning  # noqa: F811
        assert tuning.NestedWFVAutotune is not None

    def test_default_grid_not_empty(self) -> None:
        """DEFAULT_GRID should have combinations."""
        assert DEFAULT_GRID.n_combinations > 0
        assert len(list(DEFAULT_GRID.iter_combinations())) > 0
