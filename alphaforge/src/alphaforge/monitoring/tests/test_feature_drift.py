"""Tests for alphaforge.monitoring.feature_drift."""

from __future__ import annotations

import numpy as np
import pytest

from alphaforge.monitoring.feature_drift import (
    ALERT_CRITICAL,
    ALERT_NONE,
    ALERT_WARNING,
    DriftReport,
    FeatureDriftDetector,
    compute_ks_test,
    compute_psi,
)


class TestComputePSI:
    def test_identical_distributions(self):
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        psi = compute_psi(data, data)
        assert psi < 1e-6

    def test_different_distributions(self):
        expected = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
        actual = np.array([10.0, 10.0, 10.0, 10.0, 10.0])
        psi = compute_psi(expected, actual)
        assert psi > 0.1

    def test_empty_expected_raises(self):
        with pytest.raises(ValueError, match="expected array is empty"):
            compute_psi(np.array([]), np.array([1.0, 2.0]))

    def test_empty_actual_raises(self):
        with pytest.raises(ValueError, match="actual array is empty"):
            compute_psi(np.array([1.0, 2.0]), np.array([]))

    def test_custom_bins(self):
        expected = np.random.RandomState(42).randn(100)
        actual = np.random.RandomState(99).randn(100)
        psi_5 = compute_psi(expected, actual, n_bins=5)
        psi_20 = compute_psi(expected, actual, n_bins=20)
        assert psi_5 >= 0.0
        assert psi_20 >= 0.0


class TestComputeKSTest:
    def test_same_distribution(self):
        rng = np.random.RandomState(42)
        ref = rng.randn(100)
        cur = rng.randn(100)  # same seed
        stat, p = compute_ks_test(ref, cur)
        assert 0.0 <= stat <= 1.0
        assert p > 0.01  # should not be significant

    def test_different_distributions(self):
        ref = np.random.RandomState(42).randn(100)
        cur = np.random.RandomState(42).randn(100) + 2.0  # shifted
        stat, p = compute_ks_test(ref, cur)
        assert p < 0.05  # should be significant

    def test_empty_reference_raises(self):
        with pytest.raises(ValueError, match="reference array is empty"):
            compute_ks_test(np.array([]), np.array([1.0]))

    def test_empty_current_raises(self):
        with pytest.raises(ValueError, match="current array is empty"):
            compute_ks_test(np.array([1.0]), np.array([]))


class TestFeatureDriftDetector:
    def test_detect_psi_no_drift_identical(self):
        detector = FeatureDriftDetector(default_method="psi")
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        report = detector.detect_drift("test_feat", data, data)
        assert isinstance(report, DriftReport)
        assert report.feature_name == "test_feat"
        assert report.drift_score < 0.1
        assert not report.is_drifted
        assert report.alert_level == ALERT_NONE
        assert report.method == "psi"

    def test_detect_psi_drifted(self):
        detector = FeatureDriftDetector(default_method="psi")
        expected = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
        actual = np.array([10.0, 10.0, 10.0, 10.0, 10.0])
        report = detector.detect_drift("shifted_feat", expected, actual)
        assert report.is_drifted
        assert report.alert_level == ALERT_CRITICAL

    def test_detect_ks_no_drift(self):
        detector = FeatureDriftDetector(default_method="ks_test")
        rng = np.random.RandomState(42)
        ref = rng.randn(100)
        cur = rng.randn(100)
        report = detector.detect_drift("test_feat", ref, cur, threshold=0.05)
        assert not report.is_drifted
        assert report.ks_statistic is not None
        assert report.ks_p_value is not None

    def test_detect_ks_drifted(self):
        detector = FeatureDriftDetector(default_method="ks_test")
        ref = np.random.RandomState(42).randn(100)
        cur = np.random.RandomState(42).randn(100) + 3.0
        report = detector.detect_drift("shifted_feat", ref, cur, threshold=0.05)
        assert report.is_drifted

    def test_method_override(self):
        detector = FeatureDriftDetector(default_method="psi")
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        report = detector.detect_drift("test", data, data, method="ks_test")
        assert report.method == "ks_test"

    def test_custom_threshold(self):
        detector = FeatureDriftDetector()
        rng = np.random.RandomState(42)
        expected = rng.randn(500)
        actual = rng.randn(500) * 1.02 + 0.01  # very slight shift
        report = detector.detect_drift("test", expected, actual, threshold=0.5)
        assert not report.is_drifted

    def test_alert_level_warning(self):
        detector = FeatureDriftDetector()
        # Create distributions with moderate drift (PSI ~0.15)
        rng = np.random.RandomState(42)
        expected = rng.randn(1000)
        actual = rng.randn(1000) * 1.5 + 0.3
        report = detector.detect_drift("test", expected, actual, threshold=0.05)
        assert report.is_drifted
        assert report.alert_level in (ALERT_WARNING, ALERT_CRITICAL)

    def test_invalid_method(self):
        with pytest.raises(ValueError, match="Unsupported method"):
            FeatureDriftDetector(default_method="invalid")

    def test_drift_report_dataclass(self):
        report = DriftReport(
            feature_name="test",
            drift_score=0.25,
            is_drifted=True,
            alert_level=ALERT_WARNING,
            method="psi",
        )
        assert report.feature_name == "test"
        assert report.drift_score == 0.25
        assert report.is_drifted
        assert report.alert_level == ALERT_WARNING
        assert report.method == "psi"
