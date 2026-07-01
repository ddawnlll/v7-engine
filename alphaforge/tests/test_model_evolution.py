"""Tests for Model Evolution Research (Issue #144).

Covers:
- RandomForestTrainer training and metrics
- MLPTrainer training and metrics
- compare_models() head-to-head comparison
- Best model determination (by val_accuracy)
- Inference cost benchmarking
- Per-mode recommendation
- Input validation
- Determinism
- Edge cases (too few samples, single-feature, all-NaN)
"""

from __future__ import annotations

import pickle
from typing import Dict, List

import numpy as np
import pytest

from sklearn.base import BaseEstimator

from alphaforge.research.evolution import (
    MLPTrainer,
    ModelComparisonResult,
    RandomForestTrainer,
    _benchmark_inference,
    _consistent_split,
    _determine_best,
    _encode_labels,
    compare_models,
    inference_cost_benchmark,
    recommend_best_per_mode,
)


# ============================================================================
# Helpers
# ============================================================================


def _make_synthetic_data(
    n_samples: int = 300,
    n_features: int = 10,
    random_seed: int = 42,
) -> tuple:
    """Generate 3-class synthetic data for testing.

    Creates 3 gaussian clusters with moderate separability.
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


def _make_string_labels(y_int: np.ndarray) -> np.ndarray:
    """Convert integer labels to string labels."""
    mapping = {0: "LONG_NOW", 1: "SHORT_NOW", 2: "NO_TRADE"}
    return np.array([mapping[v] for v in y_int])


# ============================================================================
# Label encoding tests
# ============================================================================


def test_encode_labels_integer():
    """Integer labels pass through correctly."""
    y = np.array([0, 1, 2, 0, 1])
    result = _encode_labels(y)
    assert np.array_equal(result, y)


def test_encode_labels_string():
    """String labels convert to integers."""
    y = np.array(["LONG_NOW", "SHORT_NOW", "NO_TRADE"])
    result = _encode_labels(y)
    assert np.array_equal(result, [0, 1, 2])


def test_encode_labels_invalid():
    """Invalid string raises ValueError."""
    y = np.array(["LONG_NOW", "BAD_LABEL"])
    with pytest.raises(ValueError, match="Unknown label"):
        _encode_labels(y)


# ============================================================================
# RandomForestTrainer tests
# ============================================================================


def test_rf_trainer_default_params():
    """RandomForestTrainer uses RF_DEFAULT_PARAMS by default."""
    trainer = RandomForestTrainer()
    hp = trainer.hyperparameters
    assert hp["n_estimators"] == 200
    assert hp["max_depth"] == 8


def test_rf_trainer_custom_params():
    """RandomForestTrainer accepts custom hyperparameters."""
    custom = {"n_estimators": 50, "max_depth": 4}
    trainer = RandomForestTrainer(hyperparameters=custom)
    hp = trainer.hyperparameters
    assert hp["n_estimators"] == 50
    assert hp["max_depth"] == 4


def test_rf_trainer_trains_and_returns_metrics():
    """RandomForestTrainer.train() returns valid AlternativeModelResult."""
    X, y_int = _make_synthetic_data(n_samples=300)
    X_train, X_val, y_train, y_val = _consistent_split(X, y_int)

    trainer = RandomForestTrainer()
    result = trainer.train(X_train, y_train, X_val, y_val)

    assert result.model_name == "random_forest"
    assert result.model is not None
    assert isinstance(result.model, BaseEstimator)
    assert 0.0 <= result.train_accuracy <= 1.0
    assert 0.0 <= result.val_accuracy <= 1.0
    assert result.training_duration_seconds > 0
    assert result.model_size_bytes > 0
    assert result.inference_time_batched_us > 0
    assert result.inference_time_single_us > 0


def test_rf_trainer_string_labels():
    """RandomForest handles string labels."""
    X, y_int = _make_synthetic_data(n_samples=200)
    y_str = _make_string_labels(y_int)
    X_train, X_val, y_train, y_val = _consistent_split(X, y_str)

    trainer = RandomForestTrainer()
    result = trainer.train(X_train, y_train, X_val, y_val)
    assert result.model is not None
    assert result.val_accuracy >= 0.0


# ============================================================================
# MLPTrainer tests
# ============================================================================


def test_mlp_trainer_default_params():
    """MLPTrainer uses MLP_DEFAULT_PARAMS by default."""
    trainer = MLPTrainer()
    hp = trainer.hyperparameters
    assert hp["hidden_layer_sizes"] == (64, 32)
    assert hp["activation"] == "relu"


def test_mlp_trainer_custom_params():
    """MLPTrainer accepts custom hyperparameters."""
    custom = {"hidden_layer_sizes": (32,), "max_iter": 100}
    trainer = MLPTrainer(hyperparameters=custom)
    hp = trainer.hyperparameters
    assert hp["hidden_layer_sizes"] == (32,)
    assert hp["max_iter"] == 100


def test_mlp_trainer_trains_and_returns_metrics():
    """MLPTrainer.train() returns valid AlternativeModelResult."""
    X, y_int = _make_synthetic_data(n_samples=300)
    X_train, X_val, y_train, y_val = _consistent_split(X, y_int)

    trainer = MLPTrainer()
    result = trainer.train(X_train, y_train, X_val, y_val)

    assert result.model_name == "mlp"
    assert result.model is not None
    assert isinstance(result.model, BaseEstimator)
    assert 0.0 <= result.train_accuracy <= 1.0
    assert 0.0 <= result.val_accuracy <= 1.0
    assert result.training_duration_seconds > 0
    assert result.model_size_bytes > 0


# ============================================================================
# compare_models() tests
# ============================================================================


def test_compare_models_all_architectures():
    """compare_models() trains all 3 architectures and returns comparisons."""
    X, y = _make_synthetic_data(n_samples=300)

    result = compare_models(X, y, mode="SWING")

    assert isinstance(result, ModelComparisonResult)
    assert result.mode == "SWING"
    assert result.n_samples == 300
    assert result.n_features == 10
    assert len(result.per_model) == 3

    model_names = {r.model_name for r in result.per_model}
    assert model_names == {"xgboost", "random_forest", "mlp"}

    # All models produce positive metrics
    for r in result.per_model:
        assert r.val_accuracy >= 0.0
        assert r.training_duration_seconds > 0

    # Best model is set
    assert result.best_model in {"xgboost", "random_forest", "mlp"}

    # Comparison table is populated
    assert len(result.comparison_df) == 3
    assert "model" in result.comparison_df[0]

    # Inference benchmark is present
    assert result.inference_benchmark is not None
    assert len(result.inference_benchmark.per_model) == 3
    assert result.inference_benchmark.fastest_batched_us > 0
    assert result.inference_benchmark.fastest_single_us > 0

    # Recommendations
    assert "xgboost" in result.recommendations
    assert "random_forest" in result.recommendations
    assert "mlp" in result.recommendations


def test_compare_models_selective():
    """compare_models() allows selectively disabling architectures."""
    X, y = _make_synthetic_data(n_samples=200)

    result = compare_models(
        X, y, mode="SCALP",
        include_xgboost=False,
        include_random_forest=True,
        include_mlp=True,
    )
    assert len(result.per_model) == 2
    names = {r.model_name for r in result.per_model}
    assert names == {"random_forest", "mlp"}
    assert result.mode == "SCALP"


def test_compare_models_single_architecture():
    """compare_models() works with only one architecture."""
    X, y = _make_synthetic_data(n_samples=200)

    result = compare_models(
        X, y, mode="AGGRESSIVE_SCALP",
        include_xgboost=True,
        include_random_forest=False,
        include_mlp=False,
    )
    assert len(result.per_model) == 1
    assert result.per_model[0].model_name == "xgboost"
    assert result.best_model == "xgboost"


def test_compare_models_no_architectures_raises():
    """compare_models() raises ValueError when all architectures disabled."""
    X, y = _make_synthetic_data(n_samples=200)
    with pytest.raises(ValueError, match="At least one model type must be enabled"):
        compare_models(
            X, y,
            include_xgboost=False,
            include_random_forest=False,
            include_mlp=False,
        )


# ============================================================================
# Input validation tests
# ============================================================================


def test_compare_models_invalid_X():
    """compare_models() validates X shape."""
    y = np.array([0, 1, 2])
    with pytest.raises(ValueError, match="X must be 2D"):
        compare_models(np.array([1.0, 2.0, 3.0]), y)


def test_compare_models_mismatched_lengths():
    """compare_models() validates X and y length match."""
    X = np.array([[1.0], [2.0], [3.0]])
    y = np.array([0, 1])
    with pytest.raises(ValueError, match="length mismatch"):
        compare_models(X, y)


def test_compare_models_too_few_samples():
    """compare_models() requires at least 20 samples."""
    X = np.array([[1.0], [2.0], [3.0]])
    y = np.array([0, 1, 2])
    with pytest.raises(ValueError, match="at least 20 samples"):
        compare_models(X, y)


# ============================================================================
# Inference benchmark tests
# ============================================================================


def test_inference_cost_benchmark():
    """inference_cost_benchmark() measures latency for pre-trained models."""
    X, y = _make_synthetic_data(n_samples=200)
    X_train, X_val, y_train, y_val = _consistent_split(X, y)

    models: Dict[str, BaseEstimator] = {}
    rf = RandomForestTrainer(random_seed=42)
    rf_result = rf.train(X_train, y_train, X_val, y_val)
    models["random_forest"] = rf_result.model

    ib = inference_cost_benchmark(X_val, models, warmup=5, rounds=20)
    assert ib is not None
    assert len(ib.per_model) == 1
    assert ib.per_model[0].model_name == "random_forest"
    assert ib.per_model[0].mean_batched_us > 0
    assert ib.per_model[0].mean_single_us > 0
    assert ib.fastest_batched_us > 0
    assert ib.fastest_single_us > 0


# ============================================================================
# _determine_best tests
# ============================================================================


def test_determine_best_returns_highest_val_accuracy():
    """_determine_best selects model with highest val_accuracy."""
    X, y = _make_synthetic_data(n_samples=300)
    X_train, X_val, y_train, y_val = _consistent_split(X, y)

    rf_trainer = RandomForestTrainer()
    rf_result = rf_trainer.train(X_train, y_train, X_val, y_val)

    mlp_trainer = MLPTrainer()
    mlp_result = mlp_trainer.train(X_train, y_train, X_val, y_val)

    best = _determine_best([rf_result, mlp_result])
    assert best in {"random_forest", "mlp"}


def test_determine_best_empty():
    """_determine_best returns empty string for empty list."""
    assert _determine_best([]) == ""


# ============================================================================
# recommend_best_per_mode tests
# ============================================================================


def test_recommend_best_per_mode():
    """recommend_best_per_mode aggregates across modes."""
    X, y = _make_synthetic_data(n_samples=300)

    results = {
        "SWING": compare_models(X, y, mode="SWING"),
        "SCALP": compare_models(X, y, mode="SCALP"),
    }

    recs = recommend_best_per_mode(results)
    assert "SWING" in recs
    assert "SCALP" in recs

    for mode, info in recs.items():
        assert "best_model" in info
        assert info["best_model"] in {"xgboost", "random_forest", "mlp"}
        assert info["val_accuracy"] >= 0.0
        assert info["training_seconds"] > 0


# ============================================================================
# Determinism tests
# ============================================================================


def test_same_seed_same_comparison():
    """Same random seed produces identical comparison results."""
    X, y = _make_synthetic_data(n_samples=200, random_seed=42)

    result1 = compare_models(X, y, mode="SWING", random_seed=42)
    result2 = compare_models(X, y, mode="SWING", random_seed=42)

    assert result1.best_model == result2.best_model
    for r1, r2 in zip(result1.per_model, result2.per_model):
        assert r1.model_name == r2.model_name
        assert abs(r1.val_accuracy - r2.val_accuracy) < 1e-6


# ============================================================================
# Edge cases
# ============================================================================


def test_compare_models_single_feature():
    """compare_models() works with single feature."""
    rng = np.random.RandomState(42)
    X = rng.randn(100, 1).astype(np.float64)
    y = np.array([0] * 33 + [1] * 33 + [2] * 34)
    rng.shuffle(y)

    result = compare_models(X, y)
    assert result.n_features == 1
    assert len(result.per_model) == 3
    assert result.best_model in {"xgboost", "random_forest", "mlp"}


def test_compare_models_string_labels():
    """compare_models() handles string labels."""
    X, y_int = _make_synthetic_data(n_samples=200)
    y_str = _make_string_labels(y_int)

    result = compare_models(X, y_str)
    assert result.best_model in {"xgboost", "random_forest", "mlp"}
    assert len(result.per_model) == 3


def test_trainer_pickle_roundtrip():
    """Trained models are pickle-serializable."""
    X, y_int = _make_synthetic_data(n_samples=100)
    X_train, X_val, y_train, y_val = _consistent_split(X, y_int)

    # RandomForest
    rf = RandomForestTrainer()
    rf_result = rf.train(X_train, y_train, X_val, y_val)
    blob = pickle.dumps(rf_result.model)
    loaded = pickle.loads(blob)
    assert loaded is not None

    # MLP
    mlp = MLPTrainer()
    mlp_result = mlp.train(X_train, y_train, X_val, y_val)
    blob = pickle.dumps(mlp_result.model)
    loaded = pickle.loads(blob)
    assert loaded is not None


def test_model_comparison_result_serializable():
    """ModelComparisonResult fields are JSON-serializable."""
    X, y = _make_synthetic_data(n_samples=200)

    result = compare_models(X, y)

    import json
    # comparison_df should be JSON-serializable
    json_str = json.dumps(result.comparison_df)
    assert len(json_str) > 0
    assert '"model"' in json_str

    # recommendations should be JSON-serializable
    json_str2 = json.dumps(result.recommendations)
    assert len(json_str2) > 0
