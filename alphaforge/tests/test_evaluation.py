"""Tests for alphaforge.evaluation.engine — eval metrics + monitoring."""

import numpy as np
from alphaforge.evaluation.engine import (
    evaluate_classification,
    evaluate_regression,
    evaluate_trading,
    feature_psi,
    detect_drift,
)


class TestEvaluateClassification:
    def test_perfect(self):
        y_true = [0, 1, 2, 0, 1, 2]
        y_pred = [0, 1, 2, 0, 1, 2]
        result = evaluate_classification(y_true, y_pred)
        assert result["accuracy"] == 1.0
        assert result["f1_macro"] == 1.0

    def test_empty(self):
        result = evaluate_classification([], [])
        assert result["samples"] == 0

    def test_per_class_counts(self):
        y_true = [0, 0, 0, 1, 1, 2]
        y_pred = [0, 0, 1, 1, 0, 2]
        result = evaluate_classification(y_true, y_pred)
        assert result["per_class"]["LONG_NOW"]["samples"] == 3
        assert result["per_class"]["SHORT_NOW"]["samples"] == 2


class TestEvaluateRegression:
    def test_perfect(self):
        y_true = [1.0, 2.0, 3.0]
        y_pred = [1.0, 2.0, 3.0]
        result = evaluate_regression(y_true, y_pred)
        assert result["rmse"] == 0.0
        assert result["r2"] == 1.0

    def test_empty(self):
        result = evaluate_regression([], [])
        assert result["samples"] == 0


class TestEvaluateTrading:
    def test_all_wins(self):
        result = evaluate_trading([1.0, 2.0, 0.5])
        assert result["win_rate"] == 1.0
        assert result["net_r"] == 3.5
        assert result["total_trades"] == 3

    def test_mixed(self):
        result = evaluate_trading([1.0, -0.5, 0.5, -1.0, 2.0])
        assert result["win_rate"] == 0.6
        assert result["net_r"] == 2.0
        assert result["profit_factor"] > 0

    def test_empty(self):
        result = evaluate_trading([])
        assert result["total_trades"] == 0


class TestFeaturePSI:
    def test_identical(self):
        psi = feature_psi(np.array([0.5] * 100), np.array([0.5] * 100))
        assert psi == 0.0

    def test_different(self):
        expected = np.array([0.1] * 100)
        actual = np.array([0.9] * 100)
        psi = feature_psi(expected, actual)
        assert psi > 0.1


class TestDetectDrift:
    def test_no_drift(self):
        train = {"feature_means": {"rsi_14": 50.0}, "confidence_mean": 0.7}
        prod = {"feature_means": {"rsi_14": 51.0}, "confidence_mean": 0.71}
        result = detect_drift(train, prod)
        assert result["drift_detected"] is False

    def test_drift_detected(self):
        train = {"feature_means": {"rsi_14": 50.0}, "confidence_mean": 0.7}
        prod = {"feature_means": {"rsi_14": 80.0}, "confidence_mean": 0.3}
        result = detect_drift(train, prod)
        assert result["drift_detected"] is True
        assert len(result["drifted_features"]) == 1
