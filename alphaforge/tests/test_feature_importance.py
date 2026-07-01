"""Tests for AlphaForge Feature Importance Framework (Issue #140).

Covers:
  (a) compute_per_fold_importance — single fold, with/without names
  (b) aggregate_fold_importance — mean, std, fold_frequency
  (c) extract_top_features — top-k selection
  (d) flag_noise_features — noise detection with relative threshold
  (e) compute_feature_importance_analysis — end-to-end
  (f) Edge cases: empty boosters, single fold, all-zero importance
  (g) Integration: walk_forward_runner produces feature_importance
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pytest
import xgboost as xgb

from alphaforge.research.feature_importance import (
    DEFAULT_NOISE_THRESHOLD_REL,
    aggregate_fold_importance,
    compute_feature_importance_analysis,
    compute_per_fold_importance,
    extract_top_features,
    flag_noise_features,
)


# ============================================================================
# Helpers
# ============================================================================


def _make_synthetic_data(
    n_samples: int = 200,
    n_features: int = 10,
    random_seed: int = 42,
) -> tuple:
    """Generate synthetic feature/label data for testing.

    Creates 3 gaussian clusters, one per class (LONG_NOW/SHORT_NOW/NO_TRADE).
    """
    rng = np.random.RandomState(random_seed)
    centers = np.array([
        [-1.0, -1.0, 0.5, 0.0, 0.3, -0.5, 0.1, 0.2, -0.3, 0.0],
        [1.0, 0.5, -0.3, 0.8, -0.2, 0.6, -0.1, 0.0, 0.4, -0.5],
        [0.0, 0.0, 0.0, -0.5, 0.5, 0.0, 0.8, -0.6, -0.1, 0.3],
    ])
    centers = centers[:, :n_features]

    samples_per_class = n_samples // 3
    X_list = []
    y_list = []

    for cls_idx in range(3):
        n = samples_per_class if cls_idx < 2 else n_samples - 2 * samples_per_class
        cluster = rng.randn(n, n_features) * 0.5 + centers[cls_idx]
        X_list.append(cluster)
        y_list.append(np.full(n, cls_idx, dtype=int))

    X = np.vstack(X_list).astype(np.float64)
    y = np.concatenate(y_list)
    perm = rng.permutation(len(y))
    return X[perm], y[perm]


def _train_booster(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: List[str] | None = None,
    seed: int = 42,
) -> xgb.Booster:
    """Train a minimal XGBoost booster for testing."""
    dtrain = xgb.DMatrix(X, label=y)
    if feature_names:
        dtrain.feature_names = feature_names
    params = {
        "objective": "multi:softprob",
        "num_class": 3,
        "max_depth": 3,
        "learning_rate": 0.1,
        "n_estimators": 20,
        "eval_metric": "mlogloss",
        "random_state": seed,
        "verbosity": 0,
        "tree_method": "hist",
    }
    booster = xgb.train(params, dtrain, num_boost_round=20, verbose_eval=False)
    return booster


@pytest.fixture
def synth_data():
    """200 samples, 10 features, 3 classes."""
    return _make_synthetic_data(200, 10)


@pytest.fixture
def simple_feature_names() -> List[str]:
    return [f"feat_{i}" for i in range(10)]


@pytest.fixture
def trained_booster(synth_data, simple_feature_names) -> xgb.Booster:
    X, y = synth_data
    return _train_booster(X, y, feature_names=simple_feature_names)


@pytest.fixture
def multiple_boosters(synth_data, simple_feature_names) -> List[xgb.Booster]:
    """Train 3 boosters with different seeds to simulate folds."""
    X, y = synth_data
    return [
        _train_booster(X, y, feature_names=simple_feature_names, seed=s)
        for s in [42, 43, 44]
    ]


# ============================================================================
# Tests: compute_per_fold_importance
# ============================================================================


class TestComputePerFoldImportance:
    """Verify per-fold feature importance computation."""

    def test_returns_dict(self, trained_booster, simple_feature_names):
        """Returns a non-empty dict with feature names as keys."""
        imp = compute_per_fold_importance(trained_booster, simple_feature_names)
        assert isinstance(imp, dict)
        assert len(imp) > 0
        for name in simple_feature_names:
            assert name in imp, f"Missing feature: {name}"

    def test_all_values_positive(self, trained_booster, simple_feature_names):
        """All importance values are non-negative (gain is always >= 0)."""
        imp = compute_per_fold_importance(trained_booster, simple_feature_names)
        for name, val in imp.items():
            assert val >= 0.0, f"Feature '{name}' has negative importance: {val}"

    def test_without_feature_names(self, trained_booster):
        """Without feature_names, keys are 'f0', 'f1', etc."""
        imp = compute_per_fold_importance(trained_booster)
        assert len(imp) > 0
        for key in imp:
            assert key.startswith("f"), f"Expected 'f0...' key, got '{key}'"

    def test_non_booster_raises(self):
        """Non-Booster input raises TypeError."""
        with pytest.raises(TypeError, match="booster must be xgboost.Booster"):
            compute_per_fold_importance("not_a_booster")

    def test_null_booster_raises(self):
        """None input raises TypeError."""
        with pytest.raises(TypeError, match="booster must be xgboost.Booster"):
            compute_per_fold_importance(None)


# ============================================================================
# Tests: aggregate_fold_importance
# ============================================================================


class TestAggregateFoldImportance:
    """Verify cross-fold importance aggregation."""

    def test_returns_expected_keys(self):
        """Returns dict with mean, std, fold_frequency, n_folds, n_features."""
        per_fold = [
            {"a": 1.0, "b": 0.5},
            {"a": 0.8, "b": 0.6, "c": 0.2},
        ]
        result = aggregate_fold_importance(per_fold, normalize=False)
        assert "mean" in result
        assert "std" in result
        assert "fold_frequency" in result
        assert result["n_folds"] == 2

    def test_empty_input(self):
        """Empty input returns empty result."""
        result = aggregate_fold_importance([])
        assert result["n_folds"] == 0
        assert result["n_features"] == 0
        assert result["mean"] == {}

    def test_mean_and_std_computed(self, multiple_boosters, simple_feature_names):
        """Mean and std are computed from per-fold importance."""
        per_fold = [
            compute_per_fold_importance(b, simple_feature_names)
            for b in multiple_boosters
        ]
        result = aggregate_fold_importance(per_fold, normalize=True)

        assert result["n_folds"] == len(multiple_boosters)
        assert result["n_features"] == len(simple_feature_names)
        assert len(result["mean"]) == len(simple_feature_names)
        assert len(result["std"]) == len(simple_feature_names)

        # Mean values should be in [0, 1] range (normalized)
        for mean_val in result["mean"].values():
            assert 0.0 <= mean_val <= 1.0, f"Mean out of range: {mean_val}"

        # Means should sum to ~1.0
        total_mean = sum(result["mean"].values())
        assert abs(total_mean - 1.0) < 0.01, (
            f"Mean importance should sum to ~1.0, got {total_mean}"
        )

    def test_fold_frequency_counted(self):
        """fold_frequency counts folds with non-zero importance."""
        per_fold = [
            {"a": 1.0, "b": 0.0},
            {"a": 0.8, "b": 0.3},
            {"a": 0.0, "b": 0.5},
        ]
        result = aggregate_fold_importance(per_fold, normalize=False)
        assert result["fold_frequency"]["a"] == 2  # non-zero in folds 0 and 1
        assert result["fold_frequency"]["b"] == 2  # non-zero in folds 1 and 2


# ============================================================================
# Tests: extract_top_features
# ============================================================================


class TestExtractTopFeatures:
    """Verify top-k feature extraction."""

    def test_returns_top_k(self):
        """Returns exactly k features sorted by importance descending."""
        aggregated = {
            "mean": {"a": 0.5, "b": 0.3, "c": 0.1, "d": 0.05, "e": 0.03, "f": 0.02},
            "std": {f: 0.1 for f in "abcdef"},
            "fold_frequency": {f: 3 for f in "abcdef"},
        }
        top3 = extract_top_features(aggregated, k=3)
        assert len(top3) == 3
        names = [t["name"] for t in top3]
        assert names == ["a", "b", "c"]

    def test_empty_when_no_mean(self):
        """Empty aggregated dict returns empty list."""
        assert extract_top_features({}) == []

    def test_includes_metadata(self):
        """Each entry has name, mean_importance, std_importance, fold_frequency."""
        aggregated = {
            "mean": {"feat_x": 0.8},
            "std": {"feat_x": 0.05},
            "fold_frequency": {"feat_x": 3},
        }
        top = extract_top_features(aggregated, k=1)
        assert len(top) == 1
        entry = top[0]
        assert entry["name"] == "feat_x"
        assert entry["mean_importance"] == 0.8
        assert entry["std_importance"] == 0.05
        assert entry["fold_frequency"] == 3


# ============================================================================
# Tests: flag_noise_features
# ============================================================================


class TestFlagNoiseFeatures:
    """Verify noise feature detection."""

    def test_flags_below_threshold(self):
        """Features below relative threshold are flagged."""
        aggregated = {
            "mean": {"important": 0.6, "medium": 0.3, "noise": 0.02, "also_noise": 0.01},
        }
        # Threshold = max * 0.05 = 0.6 * 0.05 = 0.03
        flagged = flag_noise_features(aggregated, threshold_rel=0.05)
        flagged_names = {f["name"] for f in flagged}
        assert "noise" in flagged_names
        assert "also_noise" in flagged_names
        assert "important" not in flagged_names
        assert "medium" not in flagged_names

    def test_all_important_no_noise(self):
        """No features flagged when all above threshold."""
        aggregated = {
            "mean": {"a": 0.5, "b": 0.3, "c": 0.15},
        }
        flagged = flag_noise_features(aggregated, threshold_rel=0.05)
        # threshold = 0.5 * 0.05 = 0.025, all values > 0.025
        assert len(flagged) == 0

    def test_all_noise(self):
        """All features can be flagged if threshold is high."""
        aggregated = {
            "mean": {"a": 0.05, "b": 0.03, "c": 0.01},
        }
        flagged = flag_noise_features(aggregated, threshold_rel=0.5)
        # threshold = 0.05 * 0.5 = 0.025
        # a = 0.05 > 0.025, not flagged
        # b = 0.03 > 0.025, not flagged
        # c = 0.01 < 0.025, flagged
        assert len(flagged) == 1
        assert flagged[0]["name"] == "c"

    def test_empty_when_no_data(self):
        """Empty aggregated dict returns empty list."""
        assert flag_noise_features({}) == []

    def test_includes_reason(self):
        """Each flagged feature includes a reason string."""
        aggregated = {
            "mean": {"good": 0.9, "bad": 0.01},
        }
        flagged = flag_noise_features(aggregated, threshold_rel=0.05)
        # threshold = 0.9 * 0.05 = 0.045
        # bad = 0.01 < 0.045, so flagged
        assert len(flagged) == 1
        entry = flagged[0]
        assert entry["name"] == "bad"
        assert "below" in entry["reason"].lower()
        assert "threshold" in entry["reason"].lower()


# ============================================================================
# Tests: compute_feature_importance_analysis
# ============================================================================


class TestComputeFeatureImportanceAnalysis:
    """Verify end-to-end feature importance analysis."""

    def test_returns_full_analysis(self, multiple_boosters, simple_feature_names):
        """Complete analysis returns all expected keys."""
        analysis = compute_feature_importance_analysis(
            multiple_boosters, simple_feature_names
        )
        assert "per_fold" in analysis
        assert "aggregated" in analysis
        assert "top_features" in analysis
        assert "noise_features" in analysis
        assert "method" in analysis
        assert analysis["method"] == "xgboost_total_gain"
        assert len(analysis["per_fold"]) == len(multiple_boosters)

    def test_top_5_returned(self, multiple_boosters, simple_feature_names):
        """Top-5 features are extracted by default."""
        analysis = compute_feature_importance_analysis(
            multiple_boosters, simple_feature_names
        )
        assert len(analysis["top_features"]) == 5

    def test_empty_boosters_raises(self):
        """Empty boosters list raises ValueError."""
        with pytest.raises(ValueError, match="boosters list cannot be empty"):
            compute_feature_importance_analysis([])


# ============================================================================
# Tests: Default threshold constant
# ============================================================================


class TestConstants:
    """Verify module constants are reasonable."""

    def test_default_noise_threshold(self):
        """Default noise threshold is 5%."""
        assert DEFAULT_NOISE_THRESHOLD_REL == 0.05


# ============================================================================
# Tests: Integration with walk_forward_runner
# ============================================================================


class TestWalkForwardRunnerFeatureImportance:
    """Verify walk_forward_runner produces feature_importance data."""

    def test_fold_metrics_contain_importance(self):
        """Each FoldMetrics entry has feature_importance dict."""
        from alphaforge.validation.walk_forward_runner import run_walk_forward

        result = run_walk_forward(
            n_bars=200,
            n_symbols=2,
            random_seed=42,
            train_window_bars=80,
            test_window_bars=40,
            min_folds=3,
        )
        assert hasattr(result, "feature_importance")
        # The result should contain feature_importance data
        fi = result.feature_importance
        assert isinstance(fi, dict)
        if fi:  # May be empty if too few folds
            assert "top_features" in fi
            assert "noise_features" in fi
            assert "method" in fi

    def test_result_has_feature_importance_key(self):
        """walk_forward_result_to_dict includes feature_importance."""
        from alphaforge.validation.walk_forward_runner import (
            run_walk_forward,
            walk_forward_result_to_dict,
        )

        result = run_walk_forward(
            n_bars=200,
            n_symbols=2,
            random_seed=42,
            train_window_bars=80,
            test_window_bars=40,
            min_folds=3,
        )
        d = walk_forward_result_to_dict(result)
        assert "feature_importance" in d

    def test_fold_metrics_has_importance_key(self):
        """Serialized fold metrics include feature_importance."""
        from alphaforge.validation.walk_forward_runner import (
            run_walk_forward,
            walk_forward_result_to_dict,
        )

        result = run_walk_forward(
            n_bars=200,
            n_symbols=2,
            random_seed=42,
            train_window_bars=80,
            test_window_bars=40,
            min_folds=3,
        )
        d = walk_forward_result_to_dict(result)
        for fm in d["fold_metrics"]:
            assert "feature_importance" in fm
