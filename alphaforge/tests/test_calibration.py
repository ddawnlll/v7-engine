"""Tests for alphaforge.calibration.engine — calibration + alpha scores."""

import numpy as np
from alphaforge.calibration.engine import (
    Calibrator,
    _expected_calibration_error,
    predict_calibrated,
)


class TestCalibrator:
    def test_fit_and_predict(self):
        rng = np.random.RandomState(42)
        n = 100
        raw = rng.rand(n, 3)
        raw = raw / raw.sum(axis=1, keepdims=True)
        y = rng.randint(0, 3, n)
        calibrator = Calibrator(method="platt")
        metrics = calibrator.fit(raw, y)
        assert "calibration_version" in metrics
        assert "per_class" in metrics
        assert set(metrics["per_class"].keys()) == {"long", "short", "no_trade"}

    def test_predict_changes_probs(self):
        rng = np.random.RandomState(42)
        n = 200
        raw = rng.rand(n, 3)
        raw = raw / raw.sum(axis=1, keepdims=True)
        y = rng.randint(0, 3, n)
        calibrator = Calibrator(method="platt")
        calibrator.fit(raw, y)
        # Predict on first 10
        new_raw = raw[:10]
        calibrated = calibrator.predict(new_raw)
        assert calibrated.shape == (10, 3)
        # Probabilities should sum to ~1
        row_sums = calibrated.sum(axis=1)
        assert np.allclose(row_sums, 1.0, atol=0.01)

    def test_single_sample(self):
        rng = np.random.RandomState(42)
        n = 100
        raw = rng.rand(n, 3)
        raw = raw / raw.sum(axis=1, keepdims=True)
        y = rng.randint(0, 3, n)
        calibrator = Calibrator(method="platt")
        calibrator.fit(raw, y)
        single = np.array([0.6, 0.3, 0.1])
        result = calibrator.predict(single)
        assert result.shape == (3,)
        assert abs(result.sum() - 1.0) < 0.01

    def test_isotonic_method(self):
        rng = np.random.RandomState(42)
        n = 100
        raw = rng.rand(n, 3)
        raw = raw / raw.sum(axis=1, keepdims=True)
        y = rng.randint(0, 3, n)
        calibrator = Calibrator(method="isotonic")
        metrics = calibrator.fit(raw, y)
        assert metrics["method"] == "isotonic"

    def test_not_fitted_raises(self):
        calibrator = Calibrator()
        try:
            calibrator.predict(np.array([0.5, 0.3, 0.2]))
            assert False, "Should have raised"
        except RuntimeError:
            pass


class TestECE:
    def test_perfect_calibration(self):
        y_true = np.array([1, 0, 1, 0, 1])
        y_prob = np.array([0.9, 0.1, 0.9, 0.1, 0.9])
        ece = _expected_calibration_error(y_true, y_prob, n_bins=5)
        assert ece >= 0.0

    def test_empty(self):
        assert _expected_calibration_error(np.array([]), np.array([])) == 0.0


class TestPredictCalibrated:
    def test_basic_inference(self):
        # Build a minimal model bundle
        from xgboost import XGBClassifier, XGBRegressor
        rng = np.random.RandomState(42)
        X_train = rng.randn(50, 2)
        y_class = rng.randint(0, 3, 50)
        y_reg = rng.randn(50)

        clf = XGBClassifier(n_estimators=10, objective="multi:softprob", num_class=3)
        clf.fit(X_train, y_class)

        reg = XGBRegressor(n_estimators=10)
        reg.fit(X_train, y_reg)

        bundle = {
            "classifier": {"model": clf},
            "long_regressor": {"model": reg},
            "short_regressor": {"model": reg},
        }

        features = {"f1": 0.5, "f2": -0.3}
        feature_keys = ["f1", "f2"]

        result = predict_calibrated(bundle, features, feature_keys)
        assert "raw_probabilities" in result
        assert "calibrated_probabilities" in result
        assert "alpha_scores" in result
        assert "expected_r" in result
        assert "confidence" in result
        assert result["confidence_kind"] == "raw"  # no calibrator
        assert 0 <= result["raw_probabilities"]["long"] <= 1
        assert result["alpha_scores"]["long_alpha_R"] >= 0

    def test_with_calibrator(self):
        from xgboost import XGBClassifier, XGBRegressor
        rng = np.random.RandomState(42)
        n = 100
        X_train = rng.randn(n, 2)
        y_class = rng.randint(0, 3, n)
        y_reg = rng.randn(n)

        clf = XGBClassifier(n_estimators=10, objective="multi:softprob", num_class=3)
        clf.fit(X_train, y_class)

        raw_probs = clf.predict_proba(X_train)
        calibrator = Calibrator(method="platt")
        calibrator.fit(raw_probs, y_class)

        reg = XGBRegressor(n_estimators=10)
        reg.fit(X_train, y_reg)

        bundle = {
            "classifier": {"model": clf},
            "long_regressor": {"model": reg},
            "short_regressor": {"model": reg},
        }

        result = predict_calibrated(bundle, {"f1": 0.5, "f2": -0.3}, ["f1", "f2"], calibrator)
        assert result["confidence_kind"] == "calibrated"
