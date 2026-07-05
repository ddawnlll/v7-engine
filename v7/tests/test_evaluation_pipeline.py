"""Tests for v7.evaluation_pipeline — V7 Phase 8 evaluation pipeline."""

import pytest

from v7.evaluation_pipeline import (
    CandidateComparisonEngine,
    CandidateComparisonReport,
    WalkForwardReview,
    WalkForwardReviewReport,
    CalibrationReview,
    CalibrationReviewReport,
)


class TestCandidateComparisonEngine:
    """Test candidate vs baseline comparison."""

    def _make_engine(self):
        return CandidateComparisonEngine()

    def test_compare_identical(self):
        """Identical candidate and baseline should show no deltas."""
        engine = self._make_engine()
        metrics = {"expectancy_r": 0.5, "sharpe": 1.2}
        report = engine.compare(metrics, metrics)
        assert report.regression_count == 0
        assert report.improvement_count == 0
        assert report.overall_verdict == "PROMOTE"

    def test_compare_improvement(self):
        """Candidate with better metrics should show improvements."""
        engine = self._make_engine()
        candidate = {"expectancy_r": 0.8, "sharpe": 1.5}
        baseline = {"expectancy_r": 0.5, "sharpe": 1.2}
        report = engine.compare(candidate, baseline)
        assert report.improvement_count == 2
        assert report.regression_count == 0
        assert report.overall_verdict == "PROMOTE"

    def test_compare_regression(self):
        """Candidate with worse metrics should show regressions."""
        engine = self._make_engine()
        candidate = {"expectancy_r": 0.3, "sharpe": 0.8}
        baseline = {"expectancy_r": 0.5, "sharpe": 1.2}
        report = engine.compare(candidate, baseline)
        assert report.regression_count == 2
        assert report.overall_verdict == "REJECT"

    def test_compare_mixed(self):
        """Mixed regressions/improvements should yield HOLD."""
        engine = self._make_engine()
        candidate = {"expectancy_r": 0.6, "sharpe": 0.9}
        baseline = {"expectancy_r": 0.5, "sharpe": 1.2}
        report = engine.compare(candidate, baseline)
        assert report.improvement_count == 1
        assert report.regression_count == 1
        assert report.overall_verdict == "HOLD"

    def test_custom_threshold(self):
        """Custom threshold should control what counts as regression."""
        engine = self._make_engine()
        candidate = {"expectancy_r": 0.48}
        baseline = {"expectancy_r": 0.50}
        thresholds = {"expectancy_r": 0.05}
        report = engine.compare(candidate, baseline, thresholds=thresholds)
        # delta = -0.02, threshold = 0.05, not a regression since |delta| < threshold
        assert report.regression_count == 0

    def test_get_history(self):
        """Engine should track comparison history."""
        engine = self._make_engine()
        metrics = {"m": 1.0}
        engine.compare(metrics, metrics, candidate_label="v1")
        engine.compare(metrics, {"m": 0.5}, candidate_label="v2")
        assert len(engine.get_history()) == 2
        assert engine.get_history()[0].candidate_label == "v1"

    def test_missing_metrics_in_baseline(self):
        """Missing metrics in baseline should not cause errors."""
        engine = self._make_engine()
        candidate = {"a": 1.0, "b": 2.0}
        baseline = {"a": 0.5}
        report = engine.compare(candidate, baseline)
        assert "a" in report.metric_deltas
        assert "b" in report.metric_deltas


class TestWalkForwardReview:
    """Test walk-forward review."""

    def _make_fold(self, index, expectancy_r, trade_count=100):
        return {"fold_index": index, "expectancy_r": expectancy_r, "trade_count": trade_count}

    def test_review_passes(self):
        """Good fold results should pass."""
        reviewer = WalkForwardReview(min_folds=3)
        folds = [self._make_fold(i, 0.3 + i * 0.05) for i in range(6)]
        report = reviewer.review("swing_v1", folds)
        assert report.verdict == "PASS"
        assert report.fold_count == 6
        assert report.negative_fold_count == 0

    def test_review_fails_low_folds(self):
        """Fewer folds than minimum should fail."""
        reviewer = WalkForwardReview(min_folds=6)
        folds = [self._make_fold(0, 0.3), self._make_fold(1, 0.4)]
        report = reviewer.review("swing_v1", folds)
        assert report.verdict == "FAIL"

    def test_review_fails_low_median_expectancy(self):
        """Low median expectancy should fail."""
        reviewer = WalkForwardReview(min_folds=3)
        folds = [self._make_fold(i, 0.05) for i in range(6)]
        report = reviewer.review("swing_v1", folds, min_expectancy_r=0.15)
        assert report.verdict == "FAIL"
        assert report.median_expectancy < 0.15

    def test_review_fails_negative_folds(self):
        """Too many negative expectancy folds should fail."""
        reviewer = WalkForwardReview(min_folds=3)
        folds = [
            self._make_fold(0, -0.1),
            self._make_fold(1, 0.3),
            self._make_fold(2, 0.4),
            self._make_fold(3, -0.05),
        ]
        report = reviewer.review("swing_v1", folds, max_negative_fold_rate=0.2)
        assert report.verdict == "FAIL"
        assert report.negative_fold_count == 2

    def test_review_empty_folds(self):
        """Empty fold results should fail."""
        reviewer = WalkForwardReview()
        report = reviewer.review("swing_v1", [])
        assert report.verdict == "FAIL"
        assert "No expectancy" in report.detail

    def test_fold_consistency(self):
        """Fold consistency should be computed."""
        reviewer = WalkForwardReview(min_folds=3)
        folds = [self._make_fold(i, 0.5) for i in range(6)]
        report = reviewer.review("swing_v1", folds)
        assert report.fold_consistency == 0.0  # All same value = 0 CV

    def test_get_reviews(self):
        """Review history should be accessible."""
        reviewer = WalkForwardReview()
        reviewer.review("swing_v1", [self._make_fold(0, 0.3)])
        reviewer.review("scalp_v1", [self._make_fold(0, 0.4)])
        assert len(reviewer.get_reviews()) == 2


class TestCalibrationReview:
    """Test calibration review."""

    def test_review_passes(self):
        """Good calibration metrics should pass."""
        reviewer = CalibrationReview()
        metrics = {
            "ece": 0.05,
            "mce": 0.10,
            "reliability": 0.95,
            "buckets": {
                "low": {"accuracy": 0.55, "confidence": 0.50, "count": 100},
                "high": {"accuracy": 0.88, "confidence": 0.90, "count": 100},
            },
        }
        report = reviewer.review(metrics)
        assert report.calibration_verdict == "PASS"
        assert report.ece == 0.05
        assert report.mce == 0.10
        assert report.bucket_count == 2

    def test_review_fails_high_ece(self):
        """High ECE should fail."""
        reviewer = CalibrationReview()
        metrics = {"ece": 0.25, "mce": 0.30, "reliability": 0.70}
        report = reviewer.review(metrics, ece_threshold=0.10)
        assert report.calibration_verdict == "FAIL"

    def test_review_fails_high_mce(self):
        """High MCE should fail."""
        reviewer = CalibrationReview()
        metrics = {"ece": 0.05, "mce": 0.35, "reliability": 0.85}
        report = reviewer.review(metrics, mce_threshold=0.20)
        assert report.calibration_verdict == "FAIL"

    def test_empty_buckets(self):
        """Empty buckets should not cause errors."""
        reviewer = CalibrationReview()
        metrics = {"ece": 0.05, "buckets": {}}
        report = reviewer.review(metrics)
        assert report.bucket_count == 0
        assert report.calibration_verdict == "PASS"

    def test_get_reviews(self):
        """Review history should be accessible."""
        reviewer = CalibrationReview()
        reviewer.review({"ece": 0.05})
        reviewer.review({"ece": 0.08})
        assert len(reviewer.get_reviews()) == 2
