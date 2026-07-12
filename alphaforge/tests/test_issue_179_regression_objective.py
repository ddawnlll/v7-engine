"""#179: Economic regression objective wire test."""

import numpy as np
import pytest

try:
    import xgboost  # noqa: F401
    _has_xgboost = True
except ImportError:
    _has_xgboost = False


def _trainer(*a, **kw):
    from alphaforge.training.xgb_trainer import XGBoostTrainer
    return XGBoostTrainer(*a, **kw)


def _extract(*a, **kw):
    return _trainer(*a, **kw)._extract_xgb_params()


@pytest.mark.skipif(not _has_xgboost, reason="xgboost not installed")
class TestRegressionObjectiveWire:

    def test_default_objective_is_multi_softprob(self):
        assert _extract(mode="SWING")["objective"] == "multi:softprob"

    def test_regression_objective_overrides_param(self):
        assert _extract(mode="SWING", objective="reg:squarederror")["objective"] == "reg:squarederror"

    def test_regression_no_num_class(self):
        p = _extract(mode="SWING", objective="reg:squarederror")
        assert "num_class" not in p

    def test_train_with_regression_accepts_continuous_y(self):
        t = _trainer(mode="SWING", objective="reg:squarederror")
        X = np.random.randn(100, 5).astype(np.float64)
        y = np.random.randn(100).astype(np.float64)
        r = t.train(X, y)
        assert r.model is not None
        assert "rmse" in r.val_metrics

    def test_train_with_default_still_classifies(self):
        t = _trainer(mode="SWING")
        X = np.random.randn(100, 5).astype(np.float64)
        y = np.random.randint(0, 3, size=100).astype(np.int32)
        assert t.train(X, y).model is not None
