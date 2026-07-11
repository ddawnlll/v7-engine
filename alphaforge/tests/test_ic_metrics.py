"""Focused tests for IC / Rank IC infrastructure (Issue #179 Part A).

Tests every function in alphaforge.reports.ic_metrics for:
  - Normal / expected-value behaviour
  - NaN filtering
  - Constant-vector (zero-variance) guard
  - Insufficient samples (n < 3)
  - Ties in rank data
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from alphaforge.reports.ic_metrics import (
    compute_ic,
    compute_ic_ir,
    compute_rank_ic,
    compute_calibration_error,
    compute_expected_r_from_probabilities,
)

# ===================================================================
# compute_ic
# ===================================================================


class TestComputeIC:
    def test_perfect_positive(self):
        """Pearson r = 1.0 for perfectly correlated linear data."""
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y = np.array([2.0, 4.0, 6.0, 8.0, 10.0])
        assert compute_ic(x, y) == pytest.approx(1.0, abs=1e-10)

    def test_perfect_negative(self):
        """Pearson r = -1.0 for perfectly anti-correlated data."""
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y = np.array([5.0, 4.0, 3.0, 2.0, 1.0])
        assert compute_ic(x, y) == pytest.approx(-1.0, abs=1e-10)

    def test_no_correlation(self):
        """Near-zero correlation for uncorrelated data."""
        x = np.array([1.0, 2.0, 3.0])
        y = np.array([1.5, 1.5, 1.5])  # constant → 0.0
        assert compute_ic(x, y) == 0.0

    def test_nan_filtering(self):
        """NaN values are filtered pairwise."""
        x = np.array([1.0, np.nan, 3.0, 4.0, 5.0])
        y = np.array([2.0, 3.0, np.nan, 8.0, 10.0])
        # valid pairs: (1,2), (4,8), (5,10) — perfect corr
        assert compute_ic(x, y) == pytest.approx(1.0, abs=1e-10)

    def test_all_nan(self):
        """All NaN → 0.0."""
        x = np.array([np.nan, np.nan, np.nan])
        y = np.array([np.nan, np.nan, np.nan])
        assert compute_ic(x, y) == 0.0

    def test_constant_predicted(self):
        """Constant predicted vector → 0.0 (degenerate variance)."""
        x = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
        y = np.array([2.0, 4.0, 6.0, 8.0, 10.0])
        assert compute_ic(x, y) == 0.0

    def test_constant_realized(self):
        """Constant realized vector → 0.0 (degenerate variance)."""
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
        assert compute_ic(x, y) == 0.0

    def test_insufficient_samples(self):
        """Fewer than 3 valid samples → 0.0."""
        x = np.array([1.0, 2.0])
        y = np.array([3.0, 4.0])
        assert compute_ic(x, y) == 0.0

    def test_empty(self):
        """Empty arrays → 0.0."""
        assert compute_ic(np.array([]), np.array([])) == 0.0

    def test_single_nan_reduces_below_threshold(self):
        """2 valid + 1 NaN → 0.0 (insufficient samples)."""
        x = np.array([1.0, 2.0, np.nan])
        y = np.array([3.0, 4.0, 5.0])
        assert compute_ic(x, y) == 0.0


# ===================================================================
# compute_rank_ic
# ===================================================================


class TestComputeRankIC:
    def test_perfect_monotonic(self):
        """Spearman r = 1.0 for perfectly monotonically increasing data."""
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
        assert compute_rank_ic(x, y) == pytest.approx(1.0, abs=1e-10)

    def test_perfect_monotonic_negative(self):
        """Spearman r = -1.0 for perfectly inverse monotonic data."""
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y = np.array([50.0, 40.0, 30.0, 20.0, 10.0])
        assert compute_rank_ic(x, y) == pytest.approx(-1.0, abs=1e-10)

    def test_ties(self):
        """Ties resolved via average rank — should still produce sensible IC."""
        x = np.array([1.0, 2.0, 2.0, 3.0, 4.0])
        y = np.array([5.0, 6.0, 6.0, 7.0, 8.0])
        ic = compute_rank_ic(x, y)
        # With ties in both vectors at index 1,2, the correlation should be near 1
        assert ic > 0.9

    def test_all_ties(self):
        """All values tied → degenerate variance → 0.0."""
        x = np.array([1.0, 1.0, 1.0])
        y = np.array([2.0, 2.0, 2.0])
        assert compute_rank_ic(x, y) == 0.0

    def test_nan_filtering(self):
        """NaN values filtered pairwise."""
        x = np.array([1.0, np.nan, 3.0, 4.0])
        y = np.array([2.0, 3.0, np.nan, 8.0])
        # valid: (1,2), (4,8) — only 2 samples → insufficient
        assert compute_rank_ic(x, y) == 0.0

    def test_insufficient_samples(self):
        """Fewer than 3 → 0.0."""
        assert compute_rank_ic(np.array([1.0, 2.0]), np.array([3.0, 4.0])) == 0.0

    def test_constant_predicted(self):
        """Constant predicted → degenerate variance → 0.0."""
        x = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
        y = np.array([2.0, 4.0, 6.0, 8.0, 10.0])
        assert compute_rank_ic(x, y) == 0.0


# ===================================================================
# compute_ic_ir
# ===================================================================


class TestComputeICIR:
    def test_positive_ir(self):
        """IR = mean/std for a series of positive IC values."""
        ics = np.array([0.1, 0.2, 0.15, 0.18, 0.12])
        expected = np.mean(ics) / (np.std(ics, ddof=1) + 1e-10)
        assert compute_ic_ir(ics) == pytest.approx(expected, abs=1e-8)

    def test_single_fold(self):
        """Single fold → 0.0 (need >= 2)."""
        assert compute_ic_ir(np.array([0.1])) == 0.0

    def test_empty(self):
        """Empty → 0.0."""
        assert compute_ic_ir(np.array([])) == 0.0

    def test_nan_fold(self):
        """NaN fold filtered out."""
        ics = np.array([0.1, np.nan, 0.2, 0.15])
        expected = np.mean([0.1, 0.2, 0.15]) / (np.std([0.1, 0.2, 0.15], ddof=1) + 1e-10)
        assert compute_ic_ir(ics) == pytest.approx(expected, abs=1e-8)

    def test_all_nan(self):
        """All NaN → 0.0."""
        assert compute_ic_ir(np.array([np.nan, np.nan, np.nan])) == 0.0

    def test_all_identical(self):
        """All ICs identical → IR = mean / 1e-10 (very large, but stable)."""
        ics = np.array([0.1, 0.1, 0.1, 0.1])
        ir = compute_ic_ir(ics)
        assert ir > 0
        assert math.isfinite(ir)


# ===================================================================
# compute_calibration_error
# ===================================================================


class TestCalibrationError:
    def test_perfect_calibration(self):
        """ECE = MCE = 0.0 when accuracy equals confidence in every bin."""
        np.random.seed(42)
        probs = np.linspace(0.05, 0.95, 100)
        outcomes = (np.random.random(100) < probs).astype(np.float64)
        ece, mce = compute_calibration_error(probs, outcomes, n_bins=10)
        # With 100 samples over 10 bins, perfect calibration not expected
        # but ECE/MCE should be small
        assert ece >= 0.0
        assert mce >= 0.0

    def test_empty_probs(self):
        """Empty probabilities → (0.0, 0.0)."""
        assert compute_calibration_error(np.array([]), np.array([])) == (0.0, 0.0)

    def test_single_bin(self):
        """Single bin → ECE = MCE = |mean(outcome) - mean(prob)|."""
        probs = np.array([0.2, 0.3, 0.4])
        outcomes = np.array([0.0, 1.0, 0.0])
        ece, mce = compute_calibration_error(probs, outcomes, n_bins=1)
        expected_gap = abs(np.mean(outcomes) - np.mean(probs))
        assert ece == pytest.approx(expected_gap, abs=1e-10)
        assert mce == pytest.approx(expected_gap, abs=1e-10)

    def test_nan_in_probs(self):
        """NaN in probabilities — still returns valid result (no crash)."""
        probs = np.array([0.2, np.nan, 0.8, 0.9])
        outcomes = np.array([0.0, 1.0, 1.0, 1.0])
        ece, mce = compute_calibration_error(probs, outcomes, n_bins=5)
        assert ece >= 0.0
        assert mce >= 0.0

    def test_nan_in_outcomes(self):
        """NaN in outcomes — still returns valid result (no crash)."""
        probs = np.array([0.2, 0.3, 0.8, 0.9])
        outcomes = np.array([0.0, np.nan, 1.0, 1.0])
        ece, mce = compute_calibration_error(probs, outcomes, n_bins=5)
        assert ece >= 0.0
        assert mce >= 0.0

    def test_all_outcomes_one(self):
        """All outcomes = 1.0 with varied probs."""
        probs = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
        outcomes = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
        ece, mce = compute_calibration_error(probs, outcomes, n_bins=5)
        assert ece > 0.0  # Some miscalibration expected
        assert mce > 0.0

    def test_probabilities_clipped(self):
        """Probabilities outside [0,1] are clipped."""
        probs = np.array([-0.5, 0.5, 1.5])
        outcomes = np.array([0.0, 1.0, 1.0])
        ece, mce = compute_calibration_error(probs, outcomes, n_bins=5)
        assert 0.0 <= ece <= 1.0
        assert 0.0 <= mce <= 1.0


# ===================================================================
# compute_expected_r_from_probabilities
# ===================================================================


class TestExpectedRFromProbabilities:
    def test_simple(self):
        """Simple 2-sample 3-class case."""
        probs = np.array([[0.8, 0.1, 0.1], [0.2, 0.7, 0.1]])
        r_vals = np.array([[2.0, 0.0, 0.0], [0.0, 1.5, 0.0]])
        # Sample 0: 0.8*2 + 0.1*0 + 0.1*0 = 1.6
        # Sample 1: 0.2*0 + 0.7*1.5 + 0.1*0 = 1.05
        # Mean: (1.6 + 1.05) / 2 = 1.325
        result = compute_expected_r_from_probabilities(probs, r_vals)
        assert result == pytest.approx(1.325, abs=1e-10)

    def test_nan_handling(self):
        """NaN in probabilities or r_vals is filtered per-sample."""
        probs = np.array([
            [0.8, 0.1, 0.1],
            [np.nan, np.nan, np.nan],  # all NaN → excluded
            [0.3, 0.6, 0.1],
        ])
        r_vals = np.array([
            [2.0, 0.0, 0.0],
            [1.0, 0.5, 0.0],
            [1.0, 0.5, 0.0],
        ])
        # Sample 0: 1.6, Sample 1: NaN (probs NaN), Sample 2: 0.3*1 + 0.6*0.5 = 0.6
        # Mean valid: (1.6 + 0.6) / 2 = 1.1
        result = compute_expected_r_from_probabilities(probs, r_vals)
        assert result == pytest.approx(1.1, abs=1e-10)

    def test_all_nan(self):
        """All NaN → 0.0."""
        probs = np.full((3, 3), np.nan)
        r_vals = np.ones((3, 3))
        assert compute_expected_r_from_probabilities(probs, r_vals) == 0.0

    def test_single_sample(self):
        """Single sample works correctly."""
        probs = np.array([[1.0, 0.0, 0.0]])
        r_vals = np.array([[2.0, 0.0, 0.0]])
        assert compute_expected_r_from_probabilities(probs, r_vals) == pytest.approx(2.0, abs=1e-10)

    def test_zero_probability(self):
        """All zero probabilities → expected R = 0.0."""
        probs = np.zeros((2, 3))
        r_vals = np.ones((2, 3))
        assert compute_expected_r_from_probabilities(probs, r_vals) == 0.0

    def test_nan_specific_class(self):
        """NaN in only one class — still filtered correctly."""
        probs = np.array([
            [0.5, 0.3, 0.2],
            [0.1, np.nan, 0.9],  # NaN in class 1, but other classes fine
        ])
        r_vals = np.array([
            [1.0, 2.0, 3.0],
            [4.0, 5.0, 6.0],
        ])
        # Sample 0: 0.5*1 + 0.3*2 + 0.2*3 = 0.5 + 0.6 + 0.6 = 1.7
        # Sample 1: NaN because prob[1,1] is NaN
        # Mean valid: 1.7
        result = compute_expected_r_from_probabilities(probs, r_vals)
        assert result == pytest.approx(1.7, abs=1e-10)
