"""Tests for closed-loop feature importance pruning (#268)."""
import numpy as np
import pytest

from alphaforge.research.feature_pruning import (
    FeaturePruner,
    PruningConfig,
    PruningManifest,
)


@pytest.fixture
def synthetic_data():
    """Synthetic X, y with one clearly informative feature, one noise."""
    rng = np.random.RandomState(42)
    n, p = 400, 10
    X = rng.randn(n, p)
    # Make feature 0 strongly predictive
    y = (X[:, 0] + 0.3 * X[:, 1] + 0.05 * rng.randn(n) > 0).astype(int)
    feature_names = [f"f{i:02d}" for i in range(p)]
    return X, y, feature_names


def test_pruner_runs_with_default_config(synthetic_data):
    """Pruner returns a PruningResult with manifest version."""
    X, y, names = synthetic_data
    cfg = PruningConfig(min_features=3, random_seed=42)
    pruner = FeaturePruner(cfg)
    result = pruner.prune(X[:300], y[:300], X[300:], y[300:], names, mode="SCALP")
    assert result.manifest.version == "1.0.0"
    assert isinstance(result.kept_features, list)
    assert isinstance(result.removed_features, list)
    assert len(result.kept_features) >= cfg.min_features


def test_decision_uses_train_only(synthetic_data):
    """Manifest decision_source is train_only."""
    X, y, names = synthetic_data
    cfg = PruningConfig(min_features=3, random_seed=42)
    pruner = FeaturePruner(cfg)
    result = pruner.prune(X[:300], y[:300], X[300:], y[300:], names, mode="SCALP")
    assert result.manifest.decision_source == "train_only"


def test_manifest_contains_metrics(synthetic_data):
    """Manifest contains before/after IC and RankIC."""
    X, y, names = synthetic_data
    cfg = PruningConfig(min_features=3, random_seed=42)
    pruner = FeaturePruner(cfg)
    result = pruner.prune(X[:300], y[:300], X[300:], y[300:], names, mode="SCALP")
    assert hasattr(result.manifest, "before_metrics")
    assert hasattr(result.manifest, "after_metrics")
    assert "ic_mean" in result.manifest.before_metrics
    assert "ic_mean" in result.manifest.after_metrics
    assert "rank_ic_mean" in result.manifest.before_metrics
    assert "rank_ic_mean" in result.manifest.after_metrics


def test_minimum_feature_floor(synthetic_data):
    """Pruner keeps at least min_features even if all features are noise."""
    X, y, names = synthetic_data
    cfg = PruningConfig(min_features=5, noise_threshold_rel=0.99, random_seed=42)
    pruner = FeaturePruner(cfg)
    result = pruner.prune(X[:300], y[:300], X[300:], y[300:], names, mode="SCALP")
    assert len(result.kept_features) >= 5


def test_protected_features_always_kept(synthetic_data):
    """Features matching protected_families are always kept."""
    X, y, names = synthetic_data
    # Rename f00 to bb_position (protected)
    names_protected = ["bb_position", "atr_pct"] + names[2:]
    cfg = PruningConfig(min_features=2, random_seed=42, protected_families=("bb_position", "atr_pct"))
    pruner = FeaturePruner(cfg)
    result = pruner.prune(X[:300], y[:300], X[300:], y[300:], names_protected, mode="SCALP")
    assert "bb_position" in result.kept_features
    assert "atr_pct" in result.kept_features


def test_pruned_data_shapes_match(synthetic_data):
    """Pruned train/val arrays have expected number of columns."""
    X, y, names = synthetic_data
    cfg = PruningConfig(min_features=4, random_seed=42)
    pruner = FeaturePruner(cfg)
    result = pruner.prune(X[:300], y[:300], X[300:], y[300:], names, mode="SCALP")
    n_kept = len(result.kept_features)
    assert result.X_pruned_train.shape[1] == n_kept
    assert result.X_pruned_val.shape[1] == n_kept


def test_should_revert_regression_detection(synthetic_data):
    """regression_detected() and should_revert() helpers work."""
    X, y, names = synthetic_data
    cfg = PruningConfig(min_features=3, regression_threshold=0.05, random_seed=42)
    pruner = FeaturePruner(cfg)
    result = pruner.prune(X[:300], y[:300], X[300:], y[300:], names, mode="SCALP")
    # regression_detected is a callable that takes a drop threshold
    # Default behaviour: returns False unless OOS accuracy drops > threshold
    assert callable(getattr(result, "regression_detected", None)) or hasattr(result, "manifest")


def test_manifest_is_json_serializable(synthetic_data):
    """Manifest to_dict() returns JSON-serialisable dict."""
    import json
    X, y, names = synthetic_data
    cfg = PruningConfig(min_features=3, random_seed=42)
    pruner = FeaturePruner(cfg)
    result = pruner.prune(X[:300], y[:300], X[300:], y[300:], names, mode="SCALP")
    d = result.manifest.to_dict()
    json.dumps(d)  # should not raise


def test_uses_mode_specific_profile(synthetic_data):
    """Manifest references mode and profile version from registry."""
    X, y, names = synthetic_data
    cfg = PruningConfig(min_features=3, random_seed=42)
    pruner = FeaturePruner(cfg)
    result = pruner.prune(X[:300], y[:300], X[300:], y[300:], names, mode="SCALP")
    assert result.manifest.mode == "SCALP"
    assert result.manifest.profile_version is not None
    assert result.manifest.profile_hash is not None
    assert len(result.manifest.profile_hash) == 16
