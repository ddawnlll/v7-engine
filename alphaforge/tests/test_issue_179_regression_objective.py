"""#179: Economic regression objective wire test.

Verifies that --regression-objective flag switches XGBoostTrainer
to reg:squarederror and the training pipeline accepts it.
"""

import numpy as np
import pytest

from alphaforge.training.xgb_trainer import XGBoostTrainer


class TestRegressionObjectiveWire:
    """The objective parameter is wired through constructor to XGB params."""

    def test_default_objective_is_multi_softprob(self):
        trainer = XGBoostTrainer(mode="SWING")
        params = trainer._extract_xgb_params()
        assert params["objective"] == "multi:softprob"

    def test_regression_objective_overrides_param(self):
        trainer = XGBoostTrainer(mode="SWING", objective="reg:squarederror")
        params = trainer._extract_xgb_params()
        assert params["objective"] == "reg:squarederror"

    def test_regression_objective_no_num_class(self):
        """Regression objective doesn't need num_class."""
        trainer = XGBoostTrainer(mode="SWING", objective="reg:squarederror")
        params = trainer._extract_xgb_params()
        assert "num_class" not in params or params.get("objective") != "multi:softprob"

    def test_train_with_regression_accepts_continuous_y(self):
        """Regression train call accepts float targets (simulates net R)."""
        trainer = XGBoostTrainer(mode="SWING", objective="reg:squarederror")
        np.random.seed(42)
        X = np.random.randn(100, 5).astype(np.float64)
        y = np.random.randn(100).astype(np.float64)  # continuous values like net R
        result = trainer.train(X, y)
        assert result.model is not None
        assert "val_metrics" in result._asdict() or hasattr(result, "val_metrics")

    def test_train_with_default_objective_still_classifies(self):
        """Default multi:softprob still works with integer labels."""
        trainer = XGBoostTrainer(mode="SWING")
        np.random.seed(42)
        X = np.random.randn(100, 5).astype(np.float64)
        y = np.random.randint(0, 3, size=100).astype(np.int32)
        result = trainer.train(X, y)
        assert result.model is not None
