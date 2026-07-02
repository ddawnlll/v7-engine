"""Tests for AlphaForge Tuned Feature Ablation (Issue #151).

Covers:
  (a) compute_tuned_importance — gain importance, normalization, accuracy
  (b) run_feature_ablation — end-to-end, feature reduction, stopping criteria
  (c) recommend_minimum_feature_set — recommendation logic
  (d) Input validation — type, shape, NaN, empty
  (e) FeatureAblationResult structure
  (f) Edge cases
"""

from __future__ import annotations

from typing import List

import numpy as np
import pytest
import xgboost as xgb

from alphaforge.tuning.ablation import (
    DEFAULT_IMPORTANCE_THRESHOLD_REL,
    DEFAULT_MAX_PERFORMANCE_DROP_REL,
    TUNED_HYPERPARAMS,
    FeatureAblationResult,
    _validate_ablation_inputs,
    compute_tuned_importance,
    recommend_minimum_feature_set,
    run_feature_ablation,
)


# ============================================================================
# Helpers
# ============================================================================

TEST_HP = {"n_estimators": 15, "max_depth": 3, "early_stopping_rounds": 5}


def _make_synthetic_data(
    n_samples: int = 200,
    n_features: int = 15,
    random_seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.RandomState(random_seed)
    base_centers = np.array([
        [-1.0, -1.0, 0.5, 0.0, 0.3, -0.5],
        [1.0, 0.5, -0.3, 0.8, -0.2, 0.6],
        [0.0, 0.0, 0.0, -0.5, 0.5, 0.0],
    ])
    centers = np.zeros((3, n_features))
    for c in range(3):
        n_common = min(6, n_features)
        centers[c, :n_common] = base_centers[c, :n_common]
        centers[c, n_common:] = rng.randn(n_features - n_common) * 0.15
    samples_per_class = n_samples // 3
    X_parts = []
    y_parts = []
    for cls_idx in range(3):
        n = samples_per_class if cls_idx < 2 else n_samples - 2 * samples_per_class
        cluster = rng.randn(n, n_features) * 0.5 + centers[cls_idx]
        X_parts.append(cluster)
        y_parts.append(np.full(n, cls_idx, dtype=int))
    X = np.vstack(X_parts).astype(np.float64)
    y = np.concatenate(y_parts)
    perm = rng.permutation(len(y))
    return X[perm], y[perm]


def _make_feature_names(n: int = 15) -> List[str]:
    base = [
        "log_return_1", "log_return_N", "return_volatility_N", "return_zscore_N",
        "realized_volatility_N", "high_low_range_N", "atr_N", "atr_pct_N",
        "momentum_N", "roc_N", "rsi_N", "macd",
        "volume_ratio_N", "volume_trend_N", "vwap_deviation",
    ]
    return base[:n]


def _small_ablatable_data(
    n_features: int = 6, n_noise: int = 0, n_samples: int = 120,
) -> tuple[np.ndarray, np.ndarray, List[str]]:
    """Create a small dataset suitable for fast ablation tests."""
    rng = np.random.RandomState(42)
    total_features = n_features + n_noise
    n_per_class = n_samples // 3

    X = np.zeros((n_samples, total_features), dtype=np.float64)
    for i in range(3):
        sl = slice(i * n_per_class, (i + 1) * n_per_class if i < 2 else n_samples)
        n = sl.stop - sl.start
        center = [-1.0 + i, -1.0 + i * 0.5, 0.5 - i * 0.3]
        for j in range(min(3, n_features)):
            X[sl, j] = rng.randn(n) * 0.3 + center[j]
        for j in range(3, n_features):
            X[sl, j] = rng.randn(n) * 0.2 + (center[j % 3] * 0.5)
        X[sl, n_features:] = rng.randn(n, n_noise) * 0.02

    y = np.array([0]*n_per_class + [1]*n_per_class +
                 [2]*(n_samples - 2*n_per_class), dtype=int)
    feature_names = [f"signal_{i}" for i in range(n_features)]
    feature_names += [f"noise_{i}" for i in range(n_noise)]
    perm = np.argsort(rng.rand(n_samples))
    return X[perm], y[perm], feature_names


# ============================================================================
# Module-scoped fixtures (computed once, shared across all tests in this module)
# ============================================================================


@pytest.fixture(scope="module")
def basic_data():
    X, y = _make_synthetic_data(200, 15)
    fn = _make_feature_names(15)
    return X, y, fn


@pytest.fixture(scope="module")
def small_data():
    """80 samples, 6 features — fast for ablation."""
    X, y, fn = _small_ablatable_data(6, 0, 80)
    return X, y, fn


@pytest.fixture(scope="module")
def ablation_result(small_data):
    """Pre-computed ablation result shared by all tests."""
    X, y, fn = small_data
    return run_feature_ablation(
        X, y, feature_names=fn,
        hyperparameters=TEST_HP,
        target_feature_count=3,
    )


@pytest.fixture(scope="module")
def big_ablation_result():
    """35-feature ablation result (pre-computed once)."""
    X, y = _make_synthetic_data(200, 35)
    fn = [
        "log_return_1", "log_return_N", "return_volatility_N", "return_zscore_N",
        "realized_volatility_N", "high_low_range_N", "garman_klass_vol_N",
        "parkinson_vol_N",
        "atr_N", "atr_pct_N", "atr_expansion_N",
        "momentum_N", "roc_N", "rsi_N", "macd", "macd_signal", "macd_histogram",
        "volume_ratio_N", "volume_trend_N", "vwap_deviation", "obv_N",
        "bb_position", "bb_width", "highest_N", "lowest_N", "range_breakout_N",
        "spread_pct_N", "volume_imbalance_N", "trade_intensity_N",
        "amihud_illiquidity_N", "roll_spread_N", "microstructure_noise_N",
        "serial_correlation_N", "vpin_N", "price_impact_slope_N",
    ]
    return run_feature_ablation(
        X, y, feature_names=fn,
        hyperparameters={"n_estimators": 10, "max_depth": 3},
        target_feature_count=30,
    )


# ============================================================================
# Tests: Constants
# ============================================================================


class TestConstants:
    def test_tuned_hyperparams_has_hist_tree_method(self):
        assert TUNED_HYPERPARAMS["tree_method"] == "hist"

    def test_tuned_hyperparams_num_class_is_3(self):
        assert TUNED_HYPERPARAMS["num_class"] == 3

    def test_default_performance_drop_threshold(self):
        assert DEFAULT_MAX_PERFORMANCE_DROP_REL == 0.10

    def test_default_importance_threshold(self):
        assert DEFAULT_IMPORTANCE_THRESHOLD_REL == 0.05


# ============================================================================
# Tests: Input Validation (fast)
# ============================================================================


class TestInputValidation:
    def test_empty_X_raises(self):
        X = np.array([]).reshape(0, 5)
        y = np.array([])
        with pytest.raises(ValueError, match="at least 10"):
            _validate_ablation_inputs(X, y, None)

    def test_1d_X_raises(self):
        X = np.ones(30)
        y = np.ones(30, dtype=int)
        with pytest.raises(ValueError, match="must be 2D"):
            _validate_ablation_inputs(X, y, None)

    def test_mismatched_lengths_raises(self):
        X = np.ones((30, 5))
        y = np.ones(20, dtype=int)
        with pytest.raises(ValueError, match="same length"):
            _validate_ablation_inputs(X, y, None)

    def test_all_NaN_X_raises(self):
        X = np.full((30, 5), np.nan)
        y = np.ones(30, dtype=int)
        with pytest.raises(ValueError, match="all NaN"):
            _validate_ablation_inputs(X, y, None)

    def test_feature_names_length_mismatch_raises(self):
        X = np.ones((30, 5))
        y = np.ones(30, dtype=int)
        with pytest.raises(ValueError, match="feature_names length"):
            _validate_ablation_inputs(X, y, feature_names=["a", "b", "c"])

    def test_non_numpy_X_raises(self):
        with pytest.raises(TypeError, match="must be numpy"):
            _validate_ablation_inputs([1, 2, 3], np.ones(3), None)


# ============================================================================
# Tests: compute_tuned_importance
# ============================================================================


class TestComputeTunedImportance:
    def test_returns_tuple(self, basic_data):
        X, y, fn = basic_data
        result = compute_tuned_importance(X, y, feature_names=fn, hyperparameters=TEST_HP)
        booster, importance, accuracy, logloss = result
        assert isinstance(booster, xgb.Booster)
        assert isinstance(importance, dict)
        assert isinstance(accuracy, float)
        assert isinstance(logloss, float)

    def test_importance_all_features_present(self, basic_data):
        X, y, fn = basic_data
        _, importance, _, _ = compute_tuned_importance(
            X, y, feature_names=fn, hyperparameters=TEST_HP,
        )
        for name in fn:
            assert name in importance, f"Missing feature: {name}"

    def test_importance_sum_to_one(self, basic_data):
        X, y, fn = basic_data
        _, importance, _, _ = compute_tuned_importance(
            X, y, feature_names=fn, hyperparameters=TEST_HP,
        )
        total = sum(importance.values())
        assert abs(total - 1.0) < 0.01, f"Importance should sum to ~1.0, got {total}"

    def test_importance_all_non_negative(self, basic_data):
        X, y, fn = basic_data
        _, importance, _, _ = compute_tuned_importance(
            X, y, feature_names=fn, hyperparameters=TEST_HP,
        )
        for name, val in importance.items():
            assert val >= 0.0, f"Feature '{name}' has negative importance: {val}"

    def test_accuracy_in_range(self, basic_data):
        X, y, fn = basic_data
        _, _, accuracy, _ = compute_tuned_importance(
            X, y, feature_names=fn, hyperparameters=TEST_HP,
        )
        assert 0.0 <= accuracy <= 1.0

    def test_accuracy_above_random(self, basic_data):
        X, y, fn = basic_data
        _, _, accuracy, _ = compute_tuned_importance(
            X, y, feature_names=fn, hyperparameters=TEST_HP,
        )
        assert accuracy > 0.4, f"Accuracy {accuracy} should beat random baseline"

    def test_without_feature_names(self, basic_data):
        X, y, fn = basic_data
        _, importance, _, _ = compute_tuned_importance(X, y, hyperparameters=TEST_HP)
        assert len(importance) > 0
        keys = list(importance.keys())
        assert all(k.startswith("f") for k in keys[:5])

    def test_custom_hyperparameters(self, basic_data):
        X, y, fn = basic_data
        custom_hp = {"n_estimators": 10, "max_depth": 3}
        _, _, accuracy, _ = compute_tuned_importance(
            X, y, feature_names=fn, hyperparameters=custom_hp,
        )
        assert 0.0 <= accuracy <= 1.0


# ============================================================================
# Tests: run_feature_ablation (all use pre-computed fixture)
# ============================================================================


class TestRunFeatureAblation:
    def test_returns_result(self, ablation_result):
        assert isinstance(ablation_result, FeatureAblationResult)

    def test_feature_count_reduced(self, ablation_result):
        r = ablation_result
        assert r.initial_feature_count == 6
        assert r.final_feature_count < 6
        assert r.final_feature_count >= 2

    def test_ablation_steps_recorded(self, ablation_result):
        assert len(ablation_result.ablation_steps) > 0
        for step in ablation_result.ablation_steps:
            assert "step" in step
            assert "removed_feature" in step
            assert "remaining_features" in step
            assert "accuracy" in step
            assert "relative_accuracy_drop" in step

    def test_importance_ranked(self, ablation_result):
        ranked = ablation_result.feature_importance_ranked
        assert len(ranked) > 0
        assert len(ranked) <= 6
        importances = [r["importance"] for r in ranked]
        for i in range(len(importances) - 1):
            assert importances[i] >= importances[i + 1]

    def test_baseline_metric_is_reasonable(self, ablation_result):
        assert 0.0 <= ablation_result.baseline_accuracy <= 1.0
        assert ablation_result.baseline_logloss >= 0.0

    def test_accuracy_retained(self, ablation_result):
        assert ablation_result.accuracy_retained >= 0.4

    def test_removed_features_listed(self, ablation_result):
        assert len(ablation_result.removed_features) > 0
        for rf in ablation_result.removed_features:
            assert rf not in ablation_result.minimum_viable_features

    def test_timing_recorded(self, ablation_result):
        assert ablation_result.total_duration_seconds > 0

    def test_without_feature_names(self, small_data):
        X, y, _ = small_data
        result = run_feature_ablation(X, y, hyperparameters=TEST_HP, target_feature_count=3)
        assert result.initial_feature_count == 6
        assert result.final_feature_count < 6

    def test_with_35_features(self, big_ablation_result):
        r = big_ablation_result
        assert r.initial_feature_count == 35
        assert r.final_feature_count < 35
        assert r.final_feature_count >= 2
        # Some features may have zero gain importance and not appear in ranked
        assert len(r.feature_importance_ranked) > 0
        assert len(r.feature_importance_ranked) <= 35


# ============================================================================
# Tests: recommend_minimum_feature_set (uses pre-computed result)
# ============================================================================


class TestRecommendMinimumFeatureSet:
    def test_returns_dict_with_expected_keys(self, ablation_result):
        rec = recommend_minimum_feature_set(ablation_result)
        assert "recommended_feature_count" in rec
        assert "recommended_features" in rec
        assert "expected_accuracy" in rec
        assert "expected_accuracy_retained" in rec
        assert "feature_reduction_ratio" in rec

    def test_feature_count_within_range(self, ablation_result):
        rec = recommend_minimum_feature_set(ablation_result, min_features=2, max_features=5)
        assert rec["recommended_feature_count"] >= 2
        assert rec["feature_reduction_ratio"] <= 1.0

    def test_recommended_features_match_minimum_viable(self, ablation_result):
        rec = recommend_minimum_feature_set(ablation_result)
        assert rec["recommended_features"] == ablation_result.minimum_viable_features


# ============================================================================
# Tests: FeatureAblationResult structure
# ============================================================================


class TestFeatureAblationResult:
    def test_frozen_dataclass(self):
        result = FeatureAblationResult()
        with pytest.raises(AttributeError):
            result.baseline_accuracy = 0.9  # type: ignore

    def test_default_values(self):
        result = FeatureAblationResult()
        assert result.initial_feature_count == 0
        assert result.final_feature_count == 0
        assert result.minimum_viable_features == []
        assert len(result.limitations) > 0

    def test_limitations_contain_no_profit_claims(self):
        result = FeatureAblationResult()
        for lim in result.limitations:
            assert "sharpe" not in lim.lower() or "does NOT" in lim


# ============================================================================
# Tests: Edge cases (fast, no iterative retraining needed)
# ============================================================================


class TestEdgeCases:
    def test_constant_labels_raises(self):
        rng = np.random.RandomState(42)
        X = rng.randn(50, 5).astype(np.float64)
        y = np.zeros(50, dtype=int)
        with pytest.raises((ValueError, RuntimeError)):
            run_feature_ablation(
                X, y, feature_names=[f"f{i}" for i in range(5)],
                hyperparameters=TEST_HP, target_feature_count=3,
            )


# ============================================================================
# Tests: Descriptive-only enforcement
# ============================================================================


class TestDescriptiveOnly:
    CLAIM_TERMS = ["win_rate", "winrate", "win rate", "expectancy", "pnl ", "p&l"]

    def test_result_limitations_no_claims(self, ablation_result):
        all_text = " ".join(ablation_result.limitations).lower()
        for term in self.CLAIM_TERMS:
            assert term not in all_text
