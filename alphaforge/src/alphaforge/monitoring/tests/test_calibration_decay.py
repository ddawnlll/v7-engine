"""Tests for alphaforge.monitoring.calibration_decay."""

from __future__ import annotations

import numpy as np
import pytest

from alphaforge.monitoring.calibration_decay import (
    CalibrationDecayMonitor,
    DecayReport,
)


class TestCalibrationDecayMonitor:
    def test_no_decay_identical(self):
        monitor = CalibrationDecayMonitor()
        rng = np.random.RandomState(42)
        y_true = rng.randint(0, 3, 200)
        y_prob = rng.rand(200, 3)
        y_prob = y_prob / y_prob.sum(axis=1, keepdims=True)

        report = monitor.compute_decay(
            current=(y_true, y_prob),
            baseline=(y_true, y_prob),
        )
        assert isinstance(report, DecayReport)
        assert abs(report.decay_score - 1.0) < 0.01
        assert not report.is_decayed

    def test_decay_detected(self):
        monitor = CalibrationDecayMonitor()
        rng = np.random.RandomState(42)
        n = 200

        # Baseline: well-calibrated (confidences match accuracy)
        y_true_base = rng.randint(0, 3, n)
        y_prob_base = np.zeros((n, 3))
        y_prob_base[np.arange(n), y_true_base] = 0.8
        y_prob_base[np.arange(n), (y_true_base + 1) % 3] = 0.15
        y_prob_base[np.arange(n), (y_true_base + 2) % 3] = 0.05

        # Current: overconfident (high confidence, lower accuracy)
        y_true_cur = rng.randint(0, 3, n)
        y_prob_cur = np.zeros((n, 3))
        y_prob_cur[:, 0] = 0.9
        y_prob_cur[:, 1] = 0.05
        y_prob_cur[:, 2] = 0.05

        report = monitor.compute_decay(
            current=(y_true_cur, y_prob_cur),
            baseline=(y_true_base, y_prob_base),
        )
        assert report.is_decayed
        assert report.decay_score > 1.0

    def test_empty_current_raises(self):
        monitor = CalibrationDecayMonitor()
        rng = np.random.RandomState(42)
        y_prob = rng.rand(10, 3)
        y_prob = y_prob / y_prob.sum(axis=1, keepdims=True)
        with pytest.raises(ValueError, match="current y_true is empty"):
            monitor.compute_decay(
                current=(np.array([]), y_prob[:0]),
                baseline=(rng.randint(0, 3, 10), y_prob),
            )

    def test_empty_baseline_raises(self):
        monitor = CalibrationDecayMonitor()
        rng = np.random.RandomState(42)
        y_prob = rng.rand(10, 3)
        y_prob = y_prob / y_prob.sum(axis=1, keepdims=True)
        with pytest.raises(ValueError, match="baseline y_true is empty"):
            monitor.compute_decay(
                current=(rng.randint(0, 3, 10), y_prob),
                baseline=(np.array([]), y_prob[:0]),
            )

    def test_mismatched_sizes_raises(self):
        monitor = CalibrationDecayMonitor()
        rng = np.random.RandomState(42)
        y_prob = rng.rand(10, 3)
        y_prob = y_prob / y_prob.sum(axis=1, keepdims=True)
        with pytest.raises(ValueError, match="sample count mismatch"):
            monitor.compute_decay(
                current=(rng.randint(0, 3, 10), rng.rand(5, 3)),
                baseline=(rng.randint(0, 3, 10), y_prob),
            )

    def test_custom_multiplier(self):
        monitor = CalibrationDecayMonitor(decay_multiplier=3.0)
        rng = np.random.RandomState(42)
        y_true = rng.randint(0, 3, 200)
        y_prob = rng.rand(200, 3)
        y_prob = y_prob / y_prob.sum(axis=1, keepdims=True)

        report = monitor.compute_decay(
            current=(y_true, y_prob),
            baseline=(y_true, y_prob),
        )
        assert not report.is_decayed  # 3x threshold, score ~1.0

    def test_report_fields(self):
        monitor = CalibrationDecayMonitor()
        rng = np.random.RandomState(42)
        y_true = rng.randint(0, 3, 100)
        y_prob = rng.rand(100, 3)
        y_prob = y_prob / y_prob.sum(axis=1, keepdims=True)

        report = monitor.compute_decay(
            current=(y_true, y_prob),
            baseline=(y_true, y_prob),
        )
        assert report.n_current == 100
        assert report.n_baseline == 100
        assert 0.0 <= report.current_ece <= 1.0
        assert 0.0 <= report.baseline_ece <= 1.0

    def test_decay_report_dataclass(self):
        report = DecayReport(
            current_ece=0.12,
            baseline_ece=0.04,
            decay_score=3.0,
            is_decayed=True,
            n_current=200,
            n_baseline=200,
        )
        assert report.current_ece == 0.12
        assert report.baseline_ece == 0.04
        assert report.decay_score == 3.0
        assert report.is_decayed
