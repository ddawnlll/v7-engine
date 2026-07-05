"""Tests for alphaforge.model.trainer — XGBoost model training."""

import numpy as np
import pytest
from alphaforge.model.trainer import ModelTrainer, _label_to_idx, _dicts_to_arrays, AlphaForgeError


def _row(
    features: dict | None = None,
    label_action: str = "LONG_NOW",
    long_r: float = 1.0,
    short_r: float = -0.5,
) -> dict:
    return {
        "features": features or {"rsi_14": 55.0, "return_1": 0.01},
        "label": {
            "best_action_label": label_action,
            "long_R_net": long_r,
            "short_R_net": short_r,
        },
    }


def _feature_keys() -> list[str]:
    return ["rsi_14", "return_1"]


class TestDictsToArrays:
    def test_basic_conversion(self):
        rows = [_row(), _row(label_action="NO_TRADE")]
        X, y_class, y_long, y_short = _dicts_to_arrays(rows, _feature_keys())
        assert X.shape == (2, 2)
        assert y_class[0] == 0  # LONG_NOW
        assert y_class[1] == 2  # NO_TRADE
        assert y_long[0] == 1.0

    def test_empty(self):
        X, y_class, y_long, y_short = _dicts_to_arrays([], _feature_keys())
        assert X.shape == (0, 2)

    def test_label_to_idx(self):
        assert _label_to_idx("LONG_NOW") == 0
        assert _label_to_idx("SHORT_NOW") == 1
        assert _label_to_idx("NO_TRADE") == 2
        assert _label_to_idx("AMBIGUOUS_STATE") == 2


class TestModelTrainer:
    def test_train_classifier(self):
        trainer = ModelTrainer()
        X = np.random.randn(50, 2)
        y = np.random.randint(0, 3, 50)
        model, metrics = trainer._train_classifier(X, y)
        assert model is not None
        preds = model.predict(X[:3])
        assert len(preds) == 3

    def test_train_classifier_with_validation(self):
        trainer = ModelTrainer()
        X_train = np.random.randn(40, 2)
        y_train = np.random.randint(0, 3, 40)
        X_val = np.random.randn(10, 2)
        y_val = np.random.randint(0, 3, 10)
        model, metrics = trainer._train_classifier(X_train, y_train, X_val, y_val)
        assert "val_accuracy" in metrics

    def test_train_regressor(self):
        trainer = ModelTrainer()
        X = np.random.randn(50, 2)
        y = np.random.randn(50)
        model, metrics = trainer._train_regressor(X, y)
        assert model is not None
        preds = model.predict(X[:3])
        assert len(preds) == 3

    def test_train_fold_basic(self):
        trainer = ModelTrainer()
        train_rows = [_row() for _ in range(30)]
        val_rows = [_row() for _ in range(10)]
        bundle = trainer.train_fold(train_rows, val_rows, _feature_keys(), mode="SWING")
        assert "classifier" in bundle
        assert "long_regressor" in bundle
        assert "short_regressor" in bundle
        assert bundle["classifier"]["model"] is not None
        assert bundle["metadata"]["mode"] == "SWING"
        assert bundle["metadata"]["num_train"] == 30

    def test_train_fold_raises_on_too_few_rows(self):
        trainer = ModelTrainer()
        with pytest.raises(AlphaForgeError, match="Not enough"):
            trainer.train_fold([_row() for _ in range(3)], [], _feature_keys())

    def test_bundle_artifacts_have_version(self):
        trainer = ModelTrainer()
        bundle = trainer.train_fold(
            [_row() for _ in range(30)],
            [_row() for _ in range(10)],
            _feature_keys(),
            mode="SCALP",
            fold_id="fold_0",
        )
        art = bundle["classifier"]["artifact"]
        assert "artifact_version" in art
        assert art["mode"] == "SCALP"
        assert art["fold_id"] == "fold_0"
        assert "feature_keys" in art

    def test_mixed_actions(self):
        rows = [_row(label_action="LONG_NOW") for _ in range(10)] \
             + [_row(label_action="SHORT_NOW") for _ in range(10)] \
             + [_row(label_action="NO_TRADE") for _ in range(10)]
        trainer = ModelTrainer()
        bundle = trainer.train_fold(rows, rows[5:15], _feature_keys(), mode="SWING")
        assert bundle["classifier"]["model"] is not None
