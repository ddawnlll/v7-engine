"""Tests for alphaforge.monitoring.label_quality."""

from __future__ import annotations

import numpy as np
import pytest

from alphaforge.monitoring.label_quality import LabelQualityMonitor, LabelQualityReport


class TestLabelQualityMonitor:
    def test_identical_distributions(self):
        monitor = LabelQualityMonitor()
        data = np.array([0.5, 1.0, 1.5, 2.0, 2.5])
        report = monitor.compute_label_quality_regression(data, data)
        assert isinstance(report, LabelQualityReport)
        assert report.stability_score > 0.95
        assert not report.regression_detected
        assert report.magnitude < 0.01

    def test_shifted_distribution(self):
        monitor = LabelQualityMonitor()
        reference = np.array([0.5, 1.0, 1.5, 2.0, 2.5])
        current = np.array([3.0, 3.5, 4.0, 4.5, 5.0])  # shifted
        report = monitor.compute_label_quality_regression(current, reference)
        assert report.regression_detected
        assert report.magnitude > 0.1

    def test_custom_threshold(self):
        monitor = LabelQualityMonitor(regression_threshold=0.5)
        reference = np.array([0.5, 1.0, 1.5])
        current = np.array([0.6, 1.1, 1.6])  # small shift
        report = monitor.compute_label_quality_regression(current, reference)
        assert not report.regression_detected

    def test_empty_current_raises(self):
        monitor = LabelQualityMonitor()
        with pytest.raises(ValueError, match="current array is empty"):
            monitor.compute_label_quality_regression(np.array([]), np.array([1.0]))

    def test_empty_reference_raises(self):
        monitor = LabelQualityMonitor()
        with pytest.raises(ValueError, match="reference array is empty"):
            monitor.compute_label_quality_regression(np.array([1.0]), np.array([]))

    def test_report_fields(self):
        monitor = LabelQualityMonitor()
        current = np.array([1.0, 2.0, 3.0])
        reference = np.array([1.0, 2.0, 3.0])
        report = monitor.compute_label_quality_regression(current, reference)
        assert report.n_current == 3
        assert report.n_reference == 3
        assert report.current_mean is not None
        assert report.reference_mean is not None
        assert "mean_shift" in report.details
        assert "var_discrepancy" in report.details

    def test_high_variance_discrepancy(self):
        monitor = LabelQualityMonitor()
        reference = np.array([1.0, 1.0, 1.0, 1.0, 1.0])  # zero variance
        current = np.array([1.0, 5.0, 1.0, 5.0, 1.0])  # high variance
        report = monitor.compute_label_quality_regression(current, reference)
        assert report.regression_detected

    def test_large_sample_sets(self):
        monitor = LabelQualityMonitor()
        rng = np.random.RandomState(42)
        reference = rng.randn(1000)
        current = rng.randn(1000) * 1.2 + 0.1
        report = monitor.compute_label_quality_regression(current, reference)
        assert 0.0 <= report.stability_score <= 1.0
        assert report.magnitude >= 0.0

    def test_label_quality_report_dataclass(self):
        report = LabelQualityReport(
            stability_score=0.85,
            regression_detected=False,
            magnitude=0.05,
            n_current=100,
            n_reference=100,
            current_mean=1.5,
            reference_mean=1.4,
        )
        assert report.stability_score == 0.85
        assert not report.regression_detected
        assert report.magnitude == 0.05
