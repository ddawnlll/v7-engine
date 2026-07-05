"""Tests for v7.calibration_drift — calibration drift monitoring."""

import pytest

from v7.calibration_drift import (
    CalibrationDriftReport,
    CalibrationDecayTrend,
    compute_drift,
    detect_calibration_decay,
)


class TestComputeDrift:
    """Test calibration drift computation."""

    def test_no_drift_when_identical(self):
        """Identical current and baseline should show zero drift."""
        metrics = {"ece": 0.05, "mce": 0.10, "reliability": 0.95}
        report = compute_drift(metrics, metrics)
        assert report.ece_drift == 0.0
        assert report.mce_drift == 0.0
        assert report.reliability_drift == 0.0
        assert report.significant is False

    def test_detects_ece_worsening(self):
        """Worsening ECE should show positive drift."""
        current = {"ece": 0.12}
        baseline = {"ece": 0.05}
        report = compute_drift(current, baseline)
        assert report.ece_drift == 0.07
        assert report.significant is True

    def test_detects_ece_improvement(self):
        """Improving ECE should show negative drift."""
        current = {"ece": 0.03}
        baseline = {"ece": 0.08}
        report = compute_drift(current, baseline)
        assert report.ece_drift == -0.05
        # Equal to threshold, not strictly greater
        assert report.significant is False

    def test_custom_threshold(self):
        """Custom threshold should control significance."""
        current = {"ece": 0.10}
        baseline = {"ece": 0.05}
        report = compute_drift(current, baseline, threshold=0.1)
        assert report.significant is False  # 0.05 < 0.1

    def test_detects_mce_drift(self):
        """MCE drift should be computed."""
        current = {"ece": 0.05, "mce": 0.25}
        baseline = {"ece": 0.05, "mce": 0.10}
        report = compute_drift(current, baseline)
        assert report.mce_drift == 0.15

    def test_detects_reliability_drift(self):
        """Reliability drift should be computed."""
        current = {"ece": 0.05, "reliability": 0.85}
        baseline = {"ece": 0.05, "reliability": 0.95}
        report = compute_drift(current, baseline)
        assert report.reliability_drift == -0.10

    def test_bucket_drifts(self):
        """Per-bucket drifts should be computed."""
        current = {
            "ece": 0.05,
            "buckets": {
                "low": {"accuracy": 0.55, "confidence": 0.50},
                "high": {"accuracy": 0.85, "confidence": 0.90},
            },
        }
        baseline = {
            "ece": 0.05,
            "buckets": {
                "low": {"accuracy": 0.50, "confidence": 0.50},
                "high": {"accuracy": 0.90, "confidence": 0.90},
            },
        }
        report = compute_drift(current, baseline)
        assert "low" in report.bucket_drifts
        assert "high" in report.bucket_drifts


class TestDetectCalibrationDecay:
    """Test calibration decay detection."""

    def test_insufficient_data(self):
        """Fewer than 2 periods should return no trend."""
        trend = detect_calibration_decay([{"ece": 0.05}])
        assert trend.periods_analyzed == 1
        assert trend.ece_trend == 0.0

    def test_no_decay(self):
        """Stable metrics should show flat trend."""
        history = [{"ece": 0.05, "reliability": 0.95} for _ in range(5)]
        trend = detect_calibration_decay(history)
        assert trend.periods_analyzed == 5
        assert abs(trend.ece_trend) < 0.001

    def test_detects_worsening_ece(self):
        """Rising ECE should show positive trend."""
        history = [
            {"ece": 0.03, "reliability": 0.97},
            {"ece": 0.05, "reliability": 0.95},
            {"ece": 0.08, "reliability": 0.92},
            {"ece": 0.10, "reliability": 0.90},
        ]
        trend = detect_calibration_decay(history)
        assert trend.ece_trend > 0  # ECE increasing = worsening

    def test_accelerating_decay(self):
        """Accelerating ECE increase should be detected."""
        history = [
            {"ece": 0.03},
            {"ece": 0.04},
            {"ece": 0.07},
            {"ece": 0.12},
            {"ece": 0.20},
        ]
        trend = detect_calibration_decay(history)
        assert trend.accelerating is True

    def test_reliability_trend(self):
        """Declining reliability should show negative trend."""
        history = [
            {"ece": 0.05, "reliability": 0.95},
            {"ece": 0.06, "reliability": 0.93},
            {"ece": 0.07, "reliability": 0.90},
        ]
        trend = detect_calibration_decay(history)
        assert trend.reliability_trend < 0

    def test_mce_trend(self):
        """MCE trend should be computed when data available."""
        history = [
            {"ece": 0.05, "mce": 0.10},
            {"ece": 0.06, "mce": 0.12},
            {"ece": 0.07, "mce": 0.15},
        ]
        trend = detect_calibration_decay(history)
        assert abs(trend.mce_trend) > 0


class TestCalibrationDriftReport:
    """Test CalibrationDriftReport dataclass."""

    def test_defaults(self):
        """Default report should have zero values."""
        report = CalibrationDriftReport()
        assert report.ece_drift == 0.0
        assert report.significant is False


class TestCalibrationDecayTrend:
    """Test CalibrationDecayTrend dataclass."""

    def test_defaults(self):
        """Default trend should have zero values."""
        trend = CalibrationDecayTrend()
        assert trend.periods_analyzed == 0
        assert trend.accelerating is False
