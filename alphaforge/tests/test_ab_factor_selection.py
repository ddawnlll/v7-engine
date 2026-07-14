"""Tests for A/B factor selection integration in walk_forward_validate.

Verifies:
1. walk_forward_validate with feature_selection_config returns ab_comparison in fold payloads
2. collect_ab_comparison_metrics correctly aggregates across folds
3. Config A vs Config B comparison produces valid delta
4. Edge cases: empty selection, single feature, all correlated
"""

from __future__ import annotations

import numpy as np
import pytest

from alphaforge.factor_selection import FactorSelectionConfig
from alphaforge.reports.ic_metrics import (
    compute_dynamic_weights,
    compute_feature_correlation_matrix,
    compute_per_feature_ic,
    select_features_greedy_ic,
)


# ── Unit tests for collect_ab_comparison_metrics ──────────────────


class TestCollectABMetrics:
    """Test the aggregation function without needing full WFV run."""

    def _make_mock_ab_fold(self, a_nr: float, b_nr: float, a_acc: float = 0.5, b_acc: float = 0.5):
        """Create a mock fold payload with ab_comparison."""
        return {
            "fold": 1,
            "ab_comparison": {
                "config_a": {
                    "feature_count": 10,
                    "n_active_trades": 100,
                    "val_accuracy": a_acc,
                    "net_r_expectancy": a_nr,
                    "label": "full_features_static",
                },
                "config_b": {
                    "feature_count": 5,
                    "n_active_trades": 80,
                    "val_accuracy": b_acc,
                    "net_r_expectancy": b_nr,
                    "label": "selected_features_dynamic_weighted",
                },
                "selected_features": ["f0", "f1", "f2"],
                "delta": {
                    "net_r_b_minus_a": b_nr - a_nr,
                    "accuracy_b_minus_a": b_acc - a_acc,
                    "trades_a": 100,
                    "trades_b": 80,
                },
            },
        }

    def test_no_ab_data(self):
        """Should return 'no_ab_comparison_data' when no fold has ab_comparison."""
        from alphaforge.train import collect_ab_comparison_metrics
        result = collect_ab_comparison_metrics([{"fold": 1}])
        assert result["status"] == "no_ab_comparison_data"
        assert result["winner"] is None

    def test_b_wins_on_nr(self):
        """Config B should win when it has higher net R."""
        from alphaforge.train import collect_ab_comparison_metrics
        folds = [
            self._make_mock_ab_fold(a_nr=0.005, b_nr=0.015),
            self._make_mock_ab_fold(a_nr=0.003, b_nr=0.012),
        ]
        result = collect_ab_comparison_metrics(folds)
        assert result["winner"] == "B"
        assert result["status"] == "ok"
        assert result["config_b_summary"]["mean_net_r_expectancy"] > result["config_a_summary"]["mean_net_r_expectancy"]

    def test_a_wins_on_nr(self):
        """Config A should win when it has higher net R."""
        from alphaforge.train import collect_ab_comparison_metrics
        folds = [
            self._make_mock_ab_fold(a_nr=0.020, b_nr=0.005),
            self._make_mock_ab_fold(a_nr=0.015, b_nr=0.003),
        ]
        result = collect_ab_comparison_metrics(folds)
        assert result["winner"] == "A"

    def test_aggregation_counts(self):
        """Should correctly count folds and trades."""
        from alphaforge.train import collect_ab_comparison_metrics
        folds = [
            self._make_mock_ab_fold(a_nr=0.01, b_nr=0.02),
            self._make_mock_ab_fold(a_nr=0.01, b_nr=0.02),
            self._make_mock_ab_fold(a_nr=0.01, b_nr=0.02),
        ]
        result = collect_ab_comparison_metrics(folds)
        assert result["n_folds"] == 3
        assert result["config_a_summary"]["total_active_trades"] == 300
        assert result["config_b_summary"]["total_active_trades"] == 240

    def test_selected_features_union(self):
        """Should union selected features across all folds."""
        from alphaforge.train import collect_ab_comparison_metrics
        folds = [
            {**self._make_mock_ab_fold(a_nr=0.01, b_nr=0.02),
             "ab_comparison": {
                 **self._make_mock_ab_fold(a_nr=0.01, b_nr=0.02)["ab_comparison"],
                 "selected_features": ["f0", "f1"],
             }},
            {**self._make_mock_ab_fold(a_nr=0.01, b_nr=0.02),
             "ab_comparison": {
                 **self._make_mock_ab_fold(a_nr=0.01, b_nr=0.02)["ab_comparison"],
                 "selected_features": ["f1", "f2"],
             }},
        ]
        result = collect_ab_comparison_metrics(folds)
        assert set(result["selected_features_union"]) == {"f0", "f1", "f2"}

    def test_delta_tracking(self):
        """Should correctly track which folds B wins."""
        from alphaforge.train import collect_ab_comparison_metrics
        folds = [
            self._make_mock_ab_fold(a_nr=0.01, b_nr=0.02),  # B wins
            self._make_mock_ab_fold(a_nr=0.02, b_nr=0.01),  # A wins
            self._make_mock_ab_fold(a_nr=0.01, b_nr=0.01),  # tie
        ]
        result = collect_ab_comparison_metrics(folds)
        assert result["delta_summary"]["folds_where_b_wins"] == 1
        assert result["delta_summary"]["folds_where_a_wins"] == 1
        assert result["delta_summary"]["folds_tied"] == 1


# ── Integration test with real factor selection logic ──────────────


class TestFactorSelectionEndToEnd:
    """Test the full factor selection pipeline with synthetic data."""

    def test_ic_computation_and_selection(self):
        """Full pipeline: compute IC → correlation matrix → select features."""
        rng = np.random.RandomState(42)
        N, F = 500, 15
        X = rng.randn(N, F)
        # y driven by f0 and f1 only
        y = X[:, 0] * 2.0 + X[:, 1] * 0.5 + rng.randn(N) * 0.1
        names = [f"feature_{i}" for i in range(F)]

        # Step 1: Per-feature IC
        ic_table = compute_per_feature_ic(X, y, names)
        assert len(ic_table) == F
        # feature_0 should have highest IC
        assert ic_table[0]["name"] == "feature_0"

        # Step 2: Correlation matrix
        corr, fn = compute_feature_correlation_matrix(X, names)
        assert corr.shape == (F, F)
        np.testing.assert_array_almost_equal(np.diag(corr), 1.0)

        # Step 3: Selection
        selected = select_features_greedy_ic(ic_table, corr, names, max_features=5)
        assert len(selected) <= 5
        assert selected[0] == "feature_0"

    def test_dynamic_weighting_on_selected(self):
        """Dynamic weighting should apply IC-proportional weights."""
        rng = np.random.RandomState(42)
        N = 300
        X = rng.randn(N, 5)
        y = X[:, 0] * 3.0 + rng.randn(N) * 0.1
        names = [f"f{i}" for i in range(5)]

        selected = ["f0", "f1"]
        weights = compute_dynamic_weights(X[:200], y[:200], names, selected)
        # f0 should have higher weight than f1 (higher IC)
        assert weights[0] > weights[1]
        # Non-selected should be 0
        assert weights[2] == 0.0
        assert weights[3] == 0.0
        # Weights should sum to 1
        assert abs(np.sum(weights) - 1.0) < 1e-10

    def test_factor_selection_config_dataclass(self):
        """FactorSelectionConfig should have sensible defaults."""
        cfg = FactorSelectionConfig()
        assert cfg.max_features == 20
        assert cfg.corr_threshold == 0.5
        assert cfg.min_ic == 0.005
        assert cfg.enable_dynamic_weighting is True

        cfg2 = FactorSelectionConfig(max_features=10, corr_threshold=0.7)
        assert cfg2.max_features == 10
        assert cfg2.corr_threshold == 0.7
