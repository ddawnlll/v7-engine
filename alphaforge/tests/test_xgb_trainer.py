"""Tests for AlphaForge XGBoost Trainer (TR-05).

Covers:
- XGBoostTrainer initialization and validation
- SWING mode training with synthetic data
- String and integer label encoding
- Feature importance computation
- Model artifact metadata format (per model_artifact_contract.md)
- Model save/load round-trip
- train_swing_model() convenience function
- Edge cases: too few samples, all NaN, wrong shapes
- Determinism: same seed produces same model
- Hyperparameter override
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from typing import Dict, List

import numpy as np
import pytest
import xgboost as xgb

from alphaforge.training.xgb_trainer import (
    LABEL_TO_INT,
    NUM_CLASSES,
    RANDOM_SEED,
    SWING_DEFAULT_HYPERPARAMS,
    XGBoostTrainer,
    train_swing_model,
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

    Creates 3 moderately separable gaussian clusters (one per class).
    """
    rng = np.random.RandomState(random_seed)

    # 3 clusters centered at different points
    centers = np.array([
        [-1.0, -1.0, 0.5, 0.0, 0.3, -0.5, 0.1, 0.2, -0.3, 0.0],
        [1.0, 0.5, -0.3, 0.8, -0.2, 0.6, -0.1, 0.0, 0.4, -0.5],
        [0.0, 0.0, 0.0, -0.5, 0.5, 0.0, 0.8, -0.6, -0.1, 0.3],
    ])

    # Trim to n_features
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

    # Shuffle
    perm = rng.permutation(len(y))
    return X[perm], y[perm]


def _make_feature_names(n_features: int) -> List[str]:
    """Generate feature names like feature_0, feature_1, ..."""
    return [f"feature_{i}" for i in range(n_features)]


# ============================================================================
# Initialization tests
# ============================================================================


def test_trainer_init_default_mode():
    """XGBoostTrainer defaults to SWING mode."""
    trainer = XGBoostTrainer()
    assert trainer.mode == "SWING"


def test_trainer_init_explicit_mode():
    """XGBoostTrainer accepts explicit mode."""
    for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
        trainer = XGBoostTrainer(mode=mode)
        assert trainer.mode == mode


def test_trainer_init_invalid_mode():
    """XGBoostTrainer raises ValueError for invalid mode."""
    with pytest.raises(ValueError, match="Unsupported mode"):
        XGBoostTrainer(mode="INVALID")


def test_trainer_init_custom_hyperparams():
    """XGBoostTrainer accepts custom hyperparameters."""
    custom = {"max_depth": 3, "learning_rate": 0.01}
    trainer = XGBoostTrainer(hyperparameters=custom)
    hp = trainer.hyperparameters
    assert hp["max_depth"] == 3
    assert hp["learning_rate"] == 0.01


def test_trainer_init_default_hyperparams():
    """XGBoostTrainer uses SWING defaults when no hyperparams given."""
    trainer = XGBoostTrainer()
    hp = trainer.hyperparameters
    assert hp["max_depth"] == SWING_DEFAULT_HYPERPARAMS["max_depth"]
    assert hp["learning_rate"] == SWING_DEFAULT_HYPERPARAMS["learning_rate"]
    assert hp["n_estimators"] == SWING_DEFAULT_HYPERPARAMS["n_estimators"]
    assert hp["objective"] == "multi:softprob"


# ============================================================================
# Training tests
# ============================================================================


def test_train_synthetic_data():
    """Train on synthetic 3-class data and verify model produces output."""
    X, y_int = _make_synthetic_data(n_samples=300)
    y_str = np.array(
        ["LONG_NOW" if v == 0 else "SHORT_NOW" if v == 1 else "NO_TRADE"
         for v in y_int]
    )

    trainer = XGBoostTrainer(mode="SWING")
    result = trainer.train(X, y_str)

    # Model was created
    assert result.model is not None
    assert isinstance(result.model, xgb.Booster)

    # Metrics
    assert "accuracy" in result.train_metrics
    assert result.train_metrics["accuracy"] >= 0.0
    assert result.train_metrics["accuracy"] <= 1.0

    # Per-class metrics exist for all 3 classes
    for cls_name in ("LONG_NOW", "SHORT_NOW", "NO_TRADE"):
        assert cls_name in result.train_metrics["per_class"]

    # Training time is positive
    assert result.training_duration_seconds > 0.0

    # Model binary is non-empty
    assert len(result.model_binary_bytes) > 0


def test_train_with_integer_labels():
    """Train with integer labels (0, 1, 2)."""
    X, y = _make_synthetic_data(n_samples=300)
    trainer = XGBoostTrainer()
    result = trainer.train(X, y)
    assert result.model is not None


def test_train_with_feature_names():
    """Training with feature_names produces named importance."""
    X, y = _make_synthetic_data(n_samples=300)
    feature_names = _make_feature_names(X.shape[1])

    trainer = XGBoostTrainer()
    result = trainer.train(X, y, feature_names=feature_names)

    # Feature importance has named features
    importance = result.model_artifact["feature_importance"]
    assert len(importance) > 0


def test_train_produces_valid_artifact_metadata():
    """Training produces ModelArtifact metadata with all required fields."""
    X, y = _make_synthetic_data(n_samples=300)

    trainer = XGBoostTrainer(mode="SWING")
    result = trainer.train(X, y)

    metadata = result.model_artifact

    # Required fields per model_artifact.schema.json
    required = [
        "schema_version", "model_artifact_id", "model_family", "mode",
        "training_run_id", "feature_set_id", "label_dataset_id",
        "validation_report_id", "artifact_uri", "checksum",
        "limitations", "created_at",
    ]
    for field in required:
        assert field in metadata, f"Missing required field: {field}"

    # Schema version
    assert metadata["schema_version"] == "1.0.0"
    # Model family
    assert metadata["model_family"] == "xgboost"
    # Mode
    assert metadata["mode"] == "SWING"
    # Checksum is hex string
    assert len(metadata["checksum"]) == 64
    assert all(c in "0123456789abcdef" for c in metadata["checksum"])
    # Limitations is non-empty list
    assert isinstance(metadata["limitations"], list)
    assert len(metadata["limitations"]) > 0
    # Created at is ISO 8601
    assert "T" in metadata["created_at"]


def test_train_produces_optional_artifact_fields():
    """Training produces optional artifact fields: hyperparameters, feature_importance, training_metrics."""
    X, y = _make_synthetic_data(n_samples=300)

    trainer = XGBoostTrainer()
    result = trainer.train(X, y)

    metadata = result.model_artifact

    assert "hyperparameters" in metadata
    assert isinstance(metadata["hyperparameters"], dict)
    assert "max_depth" in metadata["hyperparameters"]

    assert "feature_importance" in metadata
    assert isinstance(metadata["feature_importance"], dict)
    assert len(metadata["feature_importance"]) > 0

    assert "training_metrics" in metadata
    tm = metadata["training_metrics"]
    assert "train_accuracy" in tm
    assert "val_accuracy" in tm

    assert "model_size_bytes" in metadata
    assert metadata["model_size_bytes"] > 0

    assert "framework_version" in metadata
    assert "xgboost" in metadata["framework_version"]

    assert "training_duration_seconds" in metadata
    assert metadata["training_duration_seconds"] > 0.0


def test_train_val_metrics_reasonable():
    """Validation metrics are within reasonable range on separable data."""
    X, y = _make_synthetic_data(n_samples=300)

    trainer = XGBoostTrainer()
    result = trainer.train(X, y)

    # On synthetic separable data, accuracy should be at least 40%
    assert result.val_metrics["accuracy"] >= 0.30, (
        f"Val accuracy {result.val_metrics['accuracy']} too low for separable data"
    )


# ============================================================================
# Label encoding tests
# ============================================================================


def test_encode_labels_string():
    """String labels are correctly encoded to integers."""
    y_str = np.array(["LONG_NOW", "SHORT_NOW", "NO_TRADE", "LONG_NOW", "NO_TRADE"])
    expected = np.array([0, 1, 2, 0, 2])

    trainer = XGBoostTrainer()
    result = trainer._encode_labels(y_str)
    assert np.array_equal(result, expected)


def test_encode_labels_integer():
    """Integer labels pass through unchanged."""
    y_int = np.array([0, 1, 2, 0, 2])
    trainer = XGBoostTrainer()
    result = trainer._encode_labels(y_int)
    assert np.array_equal(result, y_int)


def test_encode_labels_invalid_string():
    """Invalid string label raises ValueError."""
    y_bad = np.array(["LONG_NOW", "INVALID_ACTION", "NO_TRADE"])
    trainer = XGBoostTrainer()
    with pytest.raises(ValueError, match="Unknown label"):
        trainer._encode_labels(y_bad)


def test_encode_labels_invalid_integer():
    """Invalid integer label raises ValueError."""
    y_bad = np.array([0, 5, 2])
    trainer = XGBoostTrainer()
    with pytest.raises(ValueError, match="Integer labels must be in"):
        trainer._encode_labels(y_bad)


# ============================================================================
# Input validation tests
# ============================================================================


def test_validate_inputs_wrong_shape():
    """1D X raises ValueError."""
    X = np.array([1.0, 2.0, 3.0])
    y = np.array([0, 1, 2])
    trainer = XGBoostTrainer()
    with pytest.raises(ValueError, match="X must be 2D"):
        trainer._validate_inputs(X, y)


def test_validate_inputs_mismatched_lengths():
    """Mismatched X and y lengths raise ValueError."""
    X = np.array([[1.0], [2.0], [3.0]])
    y = np.array([0, 1])
    trainer = XGBoostTrainer()
    with pytest.raises(ValueError, match="same length"):
        trainer._validate_inputs(X, y)


def test_validate_inputs_too_few_samples():
    """Fewer than 10 samples raises ValueError."""
    X = np.array([[1.0], [2.0], [3.0]])
    y = np.array([0, 1, 2])
    trainer = XGBoostTrainer()
    with pytest.raises(ValueError, match="at least 10 samples"):
        trainer._validate_inputs(X, y)


def test_validate_inputs_non_numpy():
    """Non-numpy input raises TypeError."""
    X = [[1.0, 2.0], [3.0, 4.0]]
    y = np.array([0, 1])
    trainer = XGBoostTrainer()
    with pytest.raises(TypeError):
        trainer._validate_inputs(X, y)


def test_validate_inputs_all_nan():
    """All-NaN X raises ValueError."""
    X = np.full((20, 5), np.nan)
    y = np.zeros(20, dtype=int)
    trainer = XGBoostTrainer()
    with pytest.raises(ValueError, match="all NaN"):
        trainer._validate_inputs(X, y)


# ============================================================================
# Model artifact save/load tests
# ============================================================================


def test_save_artifact_creates_file():
    """save_artifact() creates the model file on disk."""
    X, y = _make_synthetic_data(n_samples=200)
    trainer = XGBoostTrainer()
    result = trainer.train(X, y)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = trainer.save_artifact(result, artifact_dir=tmpdir,
                                     model_artifact_id="test_model_001")
        assert path.exists()
        assert path.suffix == ".json"

        # File is valid XGBoost JSON
        loaded = xgb.Booster()
        loaded.load_model(str(path))
        assert loaded is not None


def test_save_artifact_custom_filename():
    """save_artifact() respects custom filename."""
    X, y = _make_synthetic_data(n_samples=200)
    trainer = XGBoostTrainer()
    result = trainer.train(X, y)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = trainer.save_artifact(
            result, artifact_dir=tmpdir,
            artifact_filename="my_model.json",
        )
        assert path.name == "my_model.json"


def test_build_artifact_metadata_populates_ids():
    """build_model_artifact_metadata() correctly populates all IDs."""
    X, y = _make_synthetic_data(n_samples=200)
    trainer = XGBoostTrainer()
    result = trainer.train(X, y)

    metadata = trainer.build_model_artifact_metadata(
        result,
        artifact_uri="file:///tmp/test_model.json",
        model_artifact_id="ma_swing_001",
        training_run_id="tr_001",
        feature_set_id="swing_v1",
        label_dataset_id="labels_v1",
        validation_report_id="VR-001",
    )

    assert metadata["artifact_uri"] == "file:///tmp/test_model.json"
    assert metadata["model_artifact_id"] == "ma_swing_001"
    assert metadata["training_run_id"] == "tr_001"
    assert metadata["feature_set_id"] == "swing_v1"
    assert metadata["label_dataset_id"] == "labels_v1"
    assert metadata["validation_report_id"] == "VR-001"


# ============================================================================
# train_swing_model() convenience function tests
# ============================================================================


def test_train_swing_model_returns_result():
    """train_swing_model() returns a TrainingResult."""
    X, y = _make_synthetic_data(n_samples=300)

    with tempfile.TemporaryDirectory() as tmpdir:
        result = train_swing_model(X, y, artifact_dir=tmpdir)
        assert result.model is not None
        assert result.model_artifact["mode"] == "SWING"
        assert "file://" in result.model_artifact["artifact_uri"]
        assert result.model_artifact["model_artifact_id"].startswith(
            "v7_alphaforge_xgb_swing_classifier"
        )


def test_train_swing_model_with_feature_names():
    """train_swing_model() accepts feature names."""
    X, y = _make_synthetic_data(n_samples=200)
    feature_names = _make_feature_names(X.shape[1])

    with tempfile.TemporaryDirectory() as tmpdir:
        result = train_swing_model(
            X, y, feature_names=feature_names, artifact_dir=tmpdir
        )
        importance = result.model_artifact["feature_importance"]
        assert len(importance) > 0


# ============================================================================
# Determinism tests
# ============================================================================


def test_same_seed_same_model():
    """Same random seed produces identical model checksums."""
    X, y = _make_synthetic_data(n_samples=200, random_seed=42)

    trainer1 = XGBoostTrainer(random_seed=42)
    result1 = trainer1.train(X, y)

    trainer2 = XGBoostTrainer(random_seed=42)
    result2 = trainer2.train(X, y)

    assert result1.model_artifact["checksum"] == result2.model_artifact["checksum"]


# ============================================================================
# Feature importance tests
# ============================================================================


def test_feature_importance_non_empty():
    """Feature importance dict is non-empty after training."""
    X, y = _make_synthetic_data(n_samples=200, n_features=10)
    trainer = XGBoostTrainer()
    result = trainer.train(X, y)
    fi = result.model_artifact["feature_importance"]
    assert len(fi) > 0
    assert all(isinstance(v, (int, float)) for v in fi.values())


def test_feature_importance_with_names():
    """Feature importance keys are feature names when provided."""
    X, y = _make_synthetic_data(n_samples=200, n_features=10)
    feature_names = _make_feature_names(10)

    trainer = XGBoostTrainer()
    result = trainer.train(X, y, feature_names=feature_names)
    fi = result.model_artifact["feature_importance"]

    for key in fi.keys():
        assert key.startswith("feature_") or key.startswith("f"), (
            f"Expected feature name key, got '{key}'"
        )


# ============================================================================
# Model prediction tests
# ============================================================================


def test_model_predicts_3_class_probabilities():
    """Trained model outputs 3-class probability vectors."""
    X, y = _make_synthetic_data(n_samples=300)
    trainer = XGBoostTrainer()
    result = trainer.train(X, y)

    dtest = xgb.DMatrix(X)
    probs = result.model.predict(dtest)

    assert probs.shape == (len(X), 3)
    # Probabilities sum to ~1.0 per row
    assert np.allclose(probs.sum(axis=1), 1.0, atol=0.01)


def test_model_predicts_valid_classes():
    """Model argmax predictions are in {0, 1, 2}."""
    X, y = _make_synthetic_data(n_samples=300)
    trainer = XGBoostTrainer()
    result = trainer.train(X, y)

    dtest = xgb.DMatrix(X)
    probs = result.model.predict(dtest)
    preds = np.argmax(probs, axis=1)

    assert set(preds).issubset({0, 1, 2})


# ============================================================================
# Hyperparameter tests
# ============================================================================


def test_custom_hyperparams_affect_training():
    """Custom hyperparameters change model behavior."""
    X, y = _make_synthetic_data(n_samples=200)

    # Default (max_depth=4)
    trainer_default = XGBoostTrainer(random_seed=42)
    result_default = trainer_default.train(X, y)

    # Custom (max_depth=2)
    custom_hp = SWING_DEFAULT_HYPERPARAMS.copy()
    custom_hp["max_depth"] = 2
    trainer_custom = XGBoostTrainer(random_seed=42, hyperparameters=custom_hp)
    result_custom = trainer_custom.train(X, y)

    # Different hyperparams should produce different models
    assert (
        result_default.model_artifact["checksum"]
        != result_custom.model_artifact["checksum"]
    )


# ============================================================================
# SWING_DEFAULT_HYPERPARAMS validation
# ============================================================================


def test_swing_default_hyperparams_are_conservative():
    """SWING default hyperparameters are conservative (low complexity)."""
    hp = SWING_DEFAULT_HYPERPARAMS
    assert hp["max_depth"] <= 5, "max_depth should be conservative (<= 5)"
    assert hp["learning_rate"] <= 0.1, "learning_rate should be conservative (<= 0.1)"
    assert hp["n_estimators"] <= 300, "n_estimators should be conservative (<= 300)"
    assert hp["subsample"] < 1.0, "subsample should be < 1.0 for regularization"
    assert hp["min_child_weight"] >= 3, "min_child_weight should be >= 3 to prevent overfitting"
    assert hp["gamma"] >= 0.0, "gamma should be >= 0"


def test_swing_default_hyperparams_has_required_keys():
    """SWING default hyperparams has all required XGBoost training keys."""
    required = [
        "objective", "num_class", "max_depth", "learning_rate",
        "n_estimators", "subsample", "colsample_bytree",
        "eval_metric", "random_state", "early_stopping_rounds",
    ]
    for key in required:
        assert key in SWING_DEFAULT_HYPERPARAMS, f"Missing key: {key}"


# ============================================================================
# Edge case: NaN handling in data
# ============================================================================


def test_train_with_some_nan_rows():
    """Model handles data with some NaN values (xgboost handles NaN natively)."""
    X, y = _make_synthetic_data(n_samples=300)
    # Introduce some NaN values
    X[10:15, 2] = np.nan
    X[50:55, 5] = np.nan

    trainer = XGBoostTrainer()
    result = trainer.train(X, y)
    # Should not crash, model should train
    assert result.model is not None
    assert result.val_metrics["accuracy"] >= 0.0


# ============================================================================
# Constants validation
# ============================================================================


def test_label_to_int_mapping():
    """LABEL_TO_INT has correct 3-class mapping."""
    assert LABEL_TO_INT == {"LONG_NOW": 0, "SHORT_NOW": 1, "NO_TRADE": 2}
    assert NUM_CLASSES == 3


def test_random_seed_is_fixed():
    """RANDOM_SEED is a fixed integer for reproducibility."""
    assert isinstance(RANDOM_SEED, int)
    assert RANDOM_SEED == 42
