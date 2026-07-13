"""Behavioral tests for #268: feature importance pruning.

Tests ``alphaforge.train.prune_features_by_importance()`` directly,
covering the logic that was previously only tested via source-text grep.
"""
from __future__ import annotations

import numpy as np
import pytest

from alphaforge.train import prune_features_by_importance


class TestPruneFeaturesByImportance:
    """Tests for the pruning helper extracted for Issue #268."""

    def test_drops_features_below_threshold(self):
        """Features with importance below threshold are dropped."""
        X = np.column_stack([np.arange(10) * f for f in [1.0, 0.1, 0.01, 0.001]])
        names = ["high", "medium", "low", "negligible"]
        imp = {"high": 0.6, "medium": 0.2, "low": 0.01, "negligible": 0.001}
        X_pruned, kept, dropped = prune_features_by_importance(
            X, names, imp, threshold=0.05,
        )
        assert kept == ["high", "medium"], f"Expected 2 kept, got {kept}"
        assert dropped == ["low", "negligible"], f"Expected 2 dropped, got {dropped}"
        assert X_pruned.shape == (10, 2), f"Expected (10,2), got {X_pruned.shape}"
        # Column values preserved correctly
        np.testing.assert_array_equal(X_pruned[:, 0], X[:, 0])
        np.testing.assert_array_equal(X_pruned[:, 1], X[:, 1])

    def test_keeps_all_above_threshold(self):
        """When all features are above threshold, nothing is dropped."""
        X = np.column_stack([np.arange(5) * f for f in [1.0, 0.5, 0.3]])
        names = ["a", "b", "c"]
        imp = {"a": 0.5, "b": 0.3, "c": 0.2}
        X_pruned, kept, dropped = prune_features_by_importance(
            X, names, imp, threshold=0.1,
        )
        assert kept == names
        assert dropped == []
        assert X_pruned.shape == (5, 3)

    def test_returns_original_when_no_drop(self):
        """Return same array when no pruning needed (identity)."""
        X = np.ones((4, 2))
        names = ["x", "y"]
        imp = {"x": 0.9, "y": 0.1}
        X_out, kept, dropped = prune_features_by_importance(
            X, names, imp, threshold=0.05,
        )
        assert kept == names
        assert dropped == []
        assert X_out is X  # same object when no-op

    def test_all_features_dropped_returns_all_names(self):
        """When threshold is above every importance, all names returned as dropped."""
        X = np.ones((3, 2))
        names = ["p", "q"]
        imp = {"p": 0.01, "q": 0.02}
        X_out, kept, dropped = prune_features_by_importance(
            X, names, imp, threshold=0.5,
        )
        # All features are below threshold, so all returned as dropped
        assert dropped == names
        # X is unchanged (caller should handle this case)
        assert X_out is X

    def test_zero_threshold_raises(self):
        """Threshold of 0 or negative raises ValueError."""
        X = np.ones((2, 2))
        with pytest.raises(ValueError, match="must be > 0"):
            prune_features_by_importance(X, ["a", "b"], {"a": 0.5, "b": 0.5}, 0.0)
        with pytest.raises(ValueError, match="must be > 0"):
            prune_features_by_importance(X, ["a", "b"], {"a": 0.5, "b": 0.5}, -0.1)

    def test_single_feature_kept(self):
        """Only one feature survives threshold — works correctly."""
        X = np.column_stack([np.arange(6) * f for f in [1.0, 0.001, 0.0005]])
        names = ["dominant", "weak", "noise"]
        imp = {"dominant": 0.95, "weak": 0.03, "noise": 0.02}
        X_p, kept, dropped = prune_features_by_importance(
            X, names, imp, threshold=0.9,
        )
        assert kept == ["dominant"]
        assert dropped == ["weak", "noise"]
        assert X_p.shape == (6, 1)

    def test_non_contiguous_ordering(self):
        """Importance order differs from feature_names order — indices correct."""
        X = np.column_stack([
            np.ones(4) * 1,   # col 0
            np.ones(4) * 10,  # col 1
            np.ones(4) * 100, # col 2
        ])
        names = ["first", "second", "third"]
        # "second" (col 1) has high importance but is between low-importance cols
        imp = {"first": 0.05, "second": 0.9, "third": 0.05}
        X_p, kept, dropped = prune_features_by_importance(
            X, names, imp, threshold=0.5,
        )
        assert kept == ["second"]
        assert dropped == ["first", "third"]
        # The kept column should have value 10 (the SECOND column)
        np.testing.assert_array_equal(X_p[:, 0], 10)
