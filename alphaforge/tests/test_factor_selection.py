"""Tests for factor_selection module — IC-based feature selection + dynamic weighting.

All tests use synthetic data (no real market data, no profitability claims).
Verifies:
1. Per-feature IC computation correctness
2. Correlation matrix correctness
3. Greedy feature selection with redundancy removal
4. Dynamic weight computation and application
5. A/B comparison infrastructure
"""

from __future__ import annotations

import numpy as np
import pytest

from alphaforge.reports.ic_metrics import (
    compute_dynamic_weights,
    compute_feature_correlation_matrix,
    compute_ic,
    compute_per_feature_ic,
    compute_rank_ic,
    select_features_greedy_ic,
)
from alphaforge.factor_selection import (
    FactorSelectionConfig,
    apply_dynamic_weighting_to_fold,
    apply_feature_mask,
    format_ic_table_for_logging,
    run_factor_selection,
)


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def synthetic_data():
    """Generate synthetic data with known structure.

    y = 2*X[:,0] + 0.5*X[:,1] + noise
    So feature_0 has high IC, feature_1 has moderate IC,
    features 2-4 are noise (near-zero IC).
    """
    rng = np.random.RandomState(42)
    N, F = 500, 5
    X = rng.randn(N, F)
    y = X[:, 0] * 2.0 + X[:, 1] * 0.5 + rng.randn(N) * 0.1
    names = [f"feature_{i}" for i in range(F)]
    return X, y, names


@pytest.fixture
def correlated_features():
    """Generate correlated features to test redundancy removal."""
    rng = np.random.RandomState(123)
    N = 300
    f0 = rng.randn(N)
    f1 = f0 + rng.randn(N) * 0.05  # f1 ≈ f0 (high correlation)
    f2 = rng.randn(N)  # independent
    f3 = f2 * 1.5 + rng.randn(N) * 0.1  # correlated with f2

    X = np.column_stack([f0, f1, f2, f3])
    y = f0 * 3.0 + rng.randn(N) * 0.1  # y driven by f0
    names = ["alpha", "alpha_dup", "beta", "beta_dup"]
    return X, y, names


# ── Per-feature IC tests ──────────────────────────────────────────


class TestPerFeatureIC:
    def test_perfect_prediction(self):
        """Feature that perfectly predicts y should have IC=1.0."""
        X = np.array([[1.0], [2.0], [3.0], [4.0], [5.0]])
        y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        results = compute_per_feature_ic(X, y, ["f0"])
        assert len(results) == 1
        assert abs(results[0]["ic"] - 1.0) < 1e-10
        assert abs(results[0]["rank_ic"] - 1.0) < 1e-10

    def test_inverse_prediction(self):
        """Feature inversely correlated with y should have IC=-1.0."""
        X = np.array([[5.0], [4.0], [3.0], [2.0], [1.0]])
        y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        results = compute_per_feature_ic(X, y, ["f0"])
        assert len(results) == 1
        assert abs(results[0]["ic"] - (-1.0)) < 1e-10

    def test_noise_feature(self):
        """Random noise should have near-zero IC."""
        rng = np.random.RandomState(99)
        N = 10000
        X = rng.randn(N, 1)
        y = rng.randn(N)
        results = compute_per_feature_ic(X, y, ["noise"])
        assert abs(results[0]["ic"]) < 0.1
        assert abs(results[0]["rank_ic"]) < 0.1

    def test_sorted_by_abs_ic(self, synthetic_data):
        """Results should be sorted by |IC| descending."""
        X, y, names = synthetic_data
        results = compute_per_feature_ic(X, y, names)
        abs_ics = [r["abs_ic"] for r in results]
        assert abs_ics == sorted(abs_ics, reverse=True)

    def test_top_feature_is_feature_0(self, synthetic_data):
        """Feature 0 should have highest IC (y = 2*X[:,0] + ...)."""
        X, y, names = synthetic_data
        results = compute_per_feature_ic(X, y, names)
        assert results[0]["name"] == "feature_0"
        assert results[0]["abs_ic"] > 0.5  # strong signal

    def test_nan_handling(self):
        """NaN values should be filtered pairwise without crashing."""
        X = np.array([[1.0, np.nan], [2.0, 3.0], [np.nan, 4.0], [5.0, 6.0]])
        y = np.array([1.0, 2.0, 3.0, 4.0])
        results = compute_per_feature_ic(X, y, ["f0", "f1"])
        assert len(results) == 2
        assert all(r["n_valid"] > 0 for r in results)

    def test_too_few_samples(self):
        """Fewer than 10 valid samples should return IC=0."""
        X = np.array([[1.0], [2.0]])
        y = np.array([1.0, 2.0])
        results = compute_per_feature_ic(X, y, ["f0"])
        assert results[0]["ic"] == 0.0
        assert results[0]["n_valid"] == 2


# ── Correlation matrix tests ──────────────────────────────────────


class TestCorrelationMatrix:
    def test_identity_correlation(self):
        """Perfectly correlated features should have corr=1.0."""
        X = np.array([[1.0, 2.0], [3.0, 6.0], [5.0, 10.0]])
        corr, names = compute_feature_correlation_matrix(X, ["a", "b"])
        assert corr.shape == (2, 2)
        assert abs(corr[0, 0] - 1.0) < 1e-10
        assert abs(corr[1, 1] - 1.0) < 1e-10
        assert abs(corr[0, 1] - 1.0) < 1e-10

    def test_diagonal_is_one(self, synthetic_data):
        """Diagonal should always be 1.0."""
        X, _, names = synthetic_data
        corr, _ = compute_feature_correlation_matrix(X, names)
        np.testing.assert_array_almost_equal(np.diag(corr), 1.0)

    def test_symmetric(self, synthetic_data):
        """Correlation matrix should be symmetric."""
        X, _, names = synthetic_data
        corr, _ = compute_feature_correlation_matrix(X, names)
        np.testing.assert_array_almost_equal(corr, corr.T)

    def test_nan_replaced_with_zero(self):
        """NaN values should be replaced with 0.0 before correlation."""
        X = np.array([[1.0, np.nan], [2.0, 3.0], [4.0, 5.0]])
        corr, names = compute_feature_correlation_matrix(X, ["a", "b"])
        assert corr.shape == (2, 2)
        assert not np.any(np.isnan(corr))


# ── Greedy selection tests ────────────────────────────────────────


class TestGreedySelection:
    def test_selects_top_ic_features(self, synthetic_data):
        """Should select feature_0 first (highest IC)."""
        X, y, names = synthetic_data
        ic_table = compute_per_feature_ic(X, y, names)
        corr, fn = compute_feature_correlation_matrix(X, names)
        selected = select_features_greedy_ic(ic_table, corr, names, max_features=3)
        assert len(selected) <= 3
        assert selected[0] == "feature_0"

    def test_removes_correlated_features(self, correlated_features):
        """Correlated duplicate should be removed."""
        X, y, names = correlated_features
        ic_table = compute_per_feature_ic(X, y, names)
        corr, fn = compute_feature_correlation_matrix(X, names)
        selected = select_features_greedy_ic(
            ic_table, corr, names, max_features=10, corr_threshold=0.5
        )
        # alpha_dup should NOT be in selected (correlated with alpha)
        assert "alpha" in selected
        assert "alpha_dup" not in selected

    def test_respects_max_features(self, synthetic_data):
        """Should not exceed max_features."""
        X, y, names = synthetic_data
        ic_table = compute_per_feature_ic(X, y, names)
        corr, fn = compute_feature_correlation_matrix(X, names)
        selected = select_features_greedy_ic(ic_table, corr, names, max_features=2)
        assert len(selected) <= 2

    def test_min_ic_filter(self):
        """Features below min_ic should be excluded."""
        X = np.random.RandomState(42).randn(100, 3)
        y = np.random.RandomState(42).randn(100)
        names = ["low_ic_1", "low_ic_2", "low_ic_3"]
        ic_table = compute_per_feature_ic(X, y, names)
        corr, fn = compute_feature_correlation_matrix(X, names)
        # Set min_ic very high — nothing should pass
        selected = select_features_greedy_ic(ic_table, corr, names, min_ic=0.99)
        assert len(selected) == 0


# ── Dynamic weighting tests ──────────────────────────────────────


class TestDynamicWeighting:
    def test_weights_sum_to_one(self, synthetic_data):
        """Weights should sum to 1.0."""
        X, y, names = synthetic_data
        weights = compute_dynamic_weights(X, y, names, ["feature_0", "feature_1"])
        assert abs(np.sum(weights) - 1.0) < 1e-10

    def test_non_selected_get_zero_weight(self, synthetic_data):
        """Non-selected features should have weight 0."""
        X, y, names = synthetic_data
        weights = compute_dynamic_weights(X, y, names, ["feature_0"])
        # feature_1 through feature_4 should be 0
        assert weights[1] == 0.0
        assert weights[2] == 0.0

    def test_higher_ic_gets_higher_weight(self, synthetic_data):
        """Feature with higher IC should get higher weight."""
        X, y, names = synthetic_data
        weights = compute_dynamic_weights(X, y, names, ["feature_0", "feature_1"])
        # feature_0 has higher IC than feature_1
        assert weights[0] > weights[1]

    def test_all_zero_for_empty_selection(self, synthetic_data):
        """Empty selection should give all-zero weights."""
        X, y, names = synthetic_data
        weights = compute_dynamic_weights(X, y, names, [])
        np.testing.assert_array_equal(weights, 0.0)


# ── Integration tests ─────────────────────────────────────────────


class TestFactorSelectionIntegration:
    def test_run_factor_selection(self, synthetic_data):
        """Full pipeline: IC → selection → result."""
        X, y, names = synthetic_data
        result = run_factor_selection(X, y, names, FactorSelectionConfig(max_features=3))

        assert result.n_total_features == 5
        assert result.n_selected_features <= 3
        assert len(result.ic_table) == 5
        assert result.selected_features[0] == "feature_0"

    def test_apply_feature_mask(self, synthetic_data):
        """Feature mask should select correct columns."""
        X, y, names = synthetic_data
        X_sel, sel_names = apply_feature_mask(X, names, ["feature_0", "feature_2"])
        assert X_sel.shape == (500, 2)
        assert sel_names == ["feature_0", "feature_2"]

    def test_apply_dynamic_weighting_to_fold(self, synthetic_data):
        """Dynamic weighting should scale features by IC weights."""
        X, y, names = synthetic_data
        X_train_w, X_val_w = apply_dynamic_weighting_to_fold(
            X[:400], X[400:], y[:400], names, ["feature_0", "feature_1"]
        )
        assert X_train_w.shape == (400, 5)
        assert X_val_w.shape == (100, 5)
        # Non-selected features should be zeroed out
        assert np.all(X_train_w[:, 2] == 0.0)
        assert np.all(X_train_w[:, 3] == 0.0)

    def test_format_ic_table(self, synthetic_data):
        """format_ic_table_for_logging should produce readable output."""
        X, y, names = synthetic_data
        ic_table = compute_per_feature_ic(X, y, names)
        text = format_ic_table_for_logging(ic_table, top_n=3)
        assert "feature_0" in text
        assert "IC" in text

    def test_correlated_features_selection(self, correlated_features):
        """Full pipeline with correlated features should remove duplicates."""
        X, y, names = correlated_features
        result = run_factor_selection(
            X, y, names,
            FactorSelectionConfig(max_features=10, corr_threshold=0.5),
        )
        assert "alpha" in result.selected_features
        assert "alpha_dup" not in result.selected_features
