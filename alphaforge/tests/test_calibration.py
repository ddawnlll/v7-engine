"""Tests for AlphaForge calibration module (Issue #136).

Covers:
- compute_confidence_bins: bin correctness, empty bins, edge bins
- compute_ece / compute_mce: metric correctness on known distributions
- compute_brier_score: multi-class Brier score
- assign_calibration_status: threshold-based assignment
- compute_calibration_metrics: end-to-end with validation
- build_calibration_candidate: schema-compatible dict output
- compute_per_fold_degradation: per-fold tracking
- calibrate_model: one-shot convenience
- Schema validation: CalibrationCandidate passes schema checks
- Edge cases: perfect calibration, worst-case, single class, NaN guards,
  empty arrays, mismatched shapes
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pytest

from alphaforge.calibration import (
    CalibrationResult,
    compute_calibration_metrics,
    compute_confidence_bins,
    assign_calibration_status,
    build_calibration_candidate,
    compute_per_fold_degradation,
)
from alphaforge.calibration.calculator import (
    ConfidenceBin,
    compute_ece,
    compute_mce,
    compute_brier_score,
    calibrate_model,
)
from alphaforge.contracts import ALPHAFORGE_SCHEMAS
from alphaforge.contracts.validator import validate_payload
from alphaforge.contracts.loader import load_schema


# ============================================================================
# Helpers
# ============================================================================


def _make_perfect_probs(n: int = 100, n_classes: int = 3) -> tuple:
    """Create perfectly calibrated predictions (confidence = accuracy).

    Returns (y_true, y_prob) where argmax probability exactly matches
    the empirical accuracy for each confidence level.
    """
    rng = np.random.RandomState(42)
    y_true = rng.randint(0, n_classes, size=n)
    y_prob = np.zeros((n, n_classes), dtype=np.float64)
    y_prob[np.arange(n), y_true] = 1.0
    # Add small noise to simulate realistic (but near-perfect) calibration
    noise = rng.uniform(0.0, 0.01, (n, n_classes))
    y_prob = y_prob * (1 - noise.sum(axis=1, keepdims=True)) + noise
    # Re-normalize
    y_prob = y_prob / y_prob.sum(axis=1, keepdims=True)
    return y_true, y_prob


def _make_overconfident_probs(n: int = 100, n_classes: int = 3) -> tuple:
    """Create overconfident predictions (high confidence, lower accuracy).

    Returns (y_true, y_prob) where confidence is systematically higher
    than accuracy.
    """
    rng = np.random.RandomState(42)
    y_true = rng.randint(0, n_classes, size=n)
    y_prob = np.zeros((n, n_classes), dtype=np.float64)
    predicted_class = (y_true + rng.randint(0, 2, size=n)) % n_classes
    y_prob[np.arange(n), predicted_class] = 0.85
    remainder = 0.15
    y_prob[np.arange(n), (predicted_class + 1) % n_classes] = remainder * 0.7
    y_prob[np.arange(n), (predicted_class + 2) % n_classes] = remainder * 0.3
    return y_true, y_prob


def _make_underconfident_probs(n: int = 100, n_classes: int = 3) -> tuple:
    """Create underconfident predictions (low confidence, higher accuracy).

    Returns (y_true, y_prob) where confidence is systematically lower
    than accuracy.
    """
    rng = np.random.RandomState(42)
    y_true = rng.randint(0, n_classes, size=n)
    y_prob = np.zeros((n, n_classes), dtype=np.float64)
    y_prob[np.arange(n), y_true] = 0.4
    y_prob[np.arange(n), (y_true + 1) % n_classes] = 0.35
    y_prob[np.arange(n), (y_true + 2) % n_classes] = 0.25
    return y_true, y_prob


def _make_random_probs(n: int = 100, n_classes: int = 3) -> tuple:
    """Create random (uncalibrated) predictions."""
    rng = np.random.RandomState(42)
    y_true = rng.randint(0, n_classes, size=n)
    y_prob = rng.dirichlet(np.ones(n_classes), size=n)
    return y_true, y_prob


def _make_binary_probs(n: int = 50) -> tuple:
    """Create binary classification predictions (2 classes)."""
    rng = np.random.RandomState(42)
    y_true = rng.randint(0, 2, size=n)
    y_prob = np.zeros((n, 2), dtype=np.float64)
    y_prob[:, 0] = rng.uniform(0.3, 0.9, size=n)
    y_prob[:, 1] = 1.0 - y_prob[:, 0]
    return y_true, y_prob


def _load_calibration_schema() -> Dict[str, Any]:
    """Load the CalibrationCandidate JSON schema."""
    return load_schema("calibration_candidate.schema.json")


# ============================================================================
# Confidence bin tests
# ============================================================================


def test_confidence_bins_perfect_calibration():
    """Perfectly calibrated predictions produce low-deviation bins."""
    y_true, y_prob = _make_perfect_probs(n=200)
    bins = compute_confidence_bins(y_true, y_prob, n_bins=10)

    assert len(bins) == 10
    for b in bins:
        assert 0.0 <= b.bin_lower <= 1.0
        assert 0.0 <= b.bin_upper <= 1.0
        assert b.bin_lower < b.bin_upper or (b.bin_lower == 0.0 and b.bin_upper == 0.0)
        assert b.sample_count >= 0
        assert 0.0 <= b.predicted_rate <= 1.0
        assert 0.0 <= b.actual_rate <= 1.0


def test_confidence_bins_number_of_bins():
    """Number of bins is configurable."""
    y_true, y_prob = _make_random_probs(n=200)

    for n_bins in (5, 10, 20):
        bins = compute_confidence_bins(y_true, y_prob, n_bins=n_bins)
        assert len(bins) == n_bins


def test_confidence_bins_invalid_inputs():
    """Invalid input shapes raise ValueError."""
    y_true, y_prob = _make_random_probs(n=100)

    # 2D y_true
    with pytest.raises(ValueError, match="y_true must be 1D"):
        compute_confidence_bins(np.column_stack([y_true, y_true]), y_prob)

    # 1D y_prob
    with pytest.raises(ValueError, match="y_prob must be 2D"):
        compute_confidence_bins(y_true, y_prob[:, 0])

    # Mismatched lengths
    with pytest.raises(ValueError, match="must have same number"):
        compute_confidence_bins(y_true[:50], y_prob)

    # n_bins < 1
    with pytest.raises(ValueError, match="n_bins must be >= 1"):
        compute_confidence_bins(y_true, y_prob, n_bins=0)

    # Empty arrays
    with pytest.raises(ValueError, match="Empty input"):
        compute_confidence_bins(np.array([], dtype=int), np.empty((0, 3)))


def test_confidence_bins_bin_ranges_cover_zero_to_one():
    """Bin ranges cover [0, 1] without gaps."""
    y_true, y_prob = _make_random_probs(n=100)
    bins = compute_confidence_bins(y_true, y_prob, n_bins=10)

    assert bins[0].bin_lower == 0.0
    assert bins[-1].bin_upper == 1.0

    for i in range(len(bins) - 1):
        assert abs(bins[i].bin_upper - bins[i + 1].bin_lower) < 1e-10


# ============================================================================
# ECE / MCE tests
# ============================================================================


def test_ece_perfect_calibration():
    """Perfectly calibrated predictions produce near-zero ECE."""
    y_true, y_prob = _make_perfect_probs(n=500)
    bins = compute_confidence_bins(y_true, y_prob, n_bins=10)
    ece = compute_ece(bins, len(y_true))
    assert ece < 0.05, f"ECE too high for perfect calibration: {ece:.4f}"


def test_mce_perfect_calibration():
    """Perfectly calibrated predictions produce near-zero MCE."""
    # Use truly perfect predictions (correct with confidence ~1.0)
    n = 500
    n_classes = 3
    y_true = np.zeros(n, dtype=int)
    y_prob = np.zeros((n, n_classes), dtype=np.float64)
    y_prob[:, 0] = 0.98
    y_prob[:, 1] = 0.01
    y_prob[:, 2] = 0.01

    bins = compute_confidence_bins(y_true, y_prob, n_bins=10)
    mce = compute_mce(bins)
    assert mce < 0.10, f"MCE too high for near-perfect calibration: {mce:.4f}"


def test_ece_zero_on_all_correct_confidence_one():
    """ECE is 0 when all predictions are correct with confidence 1.0."""
    n = 100
    n_classes = 3
    y_true = np.zeros(n, dtype=int)
    y_prob = np.zeros((n, n_classes), dtype=np.float64)
    y_prob[:, 0] = 1.0

    bins = compute_confidence_bins(y_true, y_prob, n_bins=10)
    ece = compute_ece(bins, n)
    assert ece == 0.0


def test_ece_mce_empty_bins():
    """ECE and MCE handle empty bins gracefully."""
    bins = []
    assert compute_ece(bins, 100) == 0.0
    assert compute_mce(bins) == 0.0


# ============================================================================
# Brier score tests
# ============================================================================


def test_brier_score_perfect():
    """Perfect predictions give Brier score of 0."""
    n = 50
    y_true = np.zeros(n, dtype=int)
    y_prob = np.zeros((n, 3))
    y_prob[:, 0] = 1.0

    brier = compute_brier_score(y_true, y_prob)
    assert brier == 0.0


def test_brier_score_worst_case():
    """All-wrong predictions give high Brier score."""
    n = 50
    y_true = np.zeros(n, dtype=int)
    y_prob = np.zeros((n, 3))
    y_prob[:, 1] = 1.0  # predict class 1, truth is class 0

    brier = compute_brier_score(y_true, y_prob)
    # For 3-class, per-sample error = (0-1)^2 + (1-0)^2 + (0-0)^2 = 2
    assert brier == 2.0, f"Expected Brier 2.0, got {brier}"


def test_brier_score_binary():
    """Brier score works with binary classification."""
    y_true, y_prob = _make_binary_probs(n=50)
    brier = compute_brier_score(y_true, y_prob)
    assert 0.0 <= brier <= 1.0


# ============================================================================
# Calibration status tests
# ============================================================================


def test_status_calibrated():
    """ECE < 0.05 yields CALIBRATED status."""
    assert assign_calibration_status(0.01) == "CALIBRATED"
    assert assign_calibration_status(0.049) == "CALIBRATED"
    assert assign_calibration_status(0.0) == "CALIBRATED"


def test_status_uncalibrated():
    """0.05 <= ECE < 0.10 yields UNCALIBRATED status."""
    assert assign_calibration_status(0.05) == "UNCALIBRATED"
    assert assign_calibration_status(0.07) == "UNCALIBRATED"
    assert assign_calibration_status(0.099) == "UNCALIBRATED"


def test_status_unreliable():
    """ECE >= 0.10 yields UNRELIABLE status."""
    assert assign_calibration_status(0.10) == "UNRELIABLE"
    assert assign_calibration_status(0.15) == "UNRELIABLE"
    assert assign_calibration_status(1.0) == "UNRELIABLE"


# ============================================================================
# compute_calibration_metrics end-to-end tests
# ============================================================================


def test_calibration_metrics_overconfident():
    """Overconfident predictions produce higher ECE."""
    y_true, y_prob = _make_overconfident_probs(n=200)
    result = compute_calibration_metrics(y_true, y_prob)

    assert isinstance(result, CalibrationResult)
    assert result.ece > 0.0
    assert result.mce > 0.0
    assert result.brier_score > 0.0
    assert result.n_samples == 200
    assert len(result.confidence_bins) == 10
    assert result.status in ("CALIBRATED", "UNCALIBRATED", "UNRELIABLE")


def test_calibration_metrics_underconfident():
    """Underconfident predictions produce higher ECE."""
    y_true, y_prob = _make_underconfident_probs(n=200)
    result = compute_calibration_metrics(y_true, y_prob)

    assert result.ece >= 0.0
    assert len(result.confidence_bins) == 10


def test_calibration_metrics_random():
    """Random predictions work without errors."""
    y_true, y_prob = _make_random_probs(n=200)
    result = compute_calibration_metrics(y_true, y_prob)

    assert result.ece >= 0.0
    assert result.mce >= 0.0
    assert result.n_samples == 200


def test_calibration_metrics_binary():
    """Binary classification is handled correctly."""
    y_true, y_prob = _make_binary_probs(n=50)
    result = compute_calibration_metrics(y_true, y_prob, n_bins=5)

    assert len(result.confidence_bins) == 5
    assert result.status in ("CALIBRATED", "UNCALIBRATED", "UNRELIABLE")


def test_calibration_metrics_validates_inputs():
    """Invalid inputs raise appropriate errors."""
    y_true, y_prob = _make_random_probs(n=100)

    # Non-numpy inputs
    with pytest.raises(TypeError):
        compute_calibration_metrics(list(y_true), y_prob)

    # Mismatched shapes
    with pytest.raises(ValueError, match="same number of samples"):
        compute_calibration_metrics(y_true[:50], y_prob)

    # Empty arrays
    with pytest.raises(ValueError, match="Empty input"):
        compute_calibration_metrics(np.array([], dtype=int), np.empty((0, 3)))

    # Labels out of range
    y_bad = np.array([0, 99, 2])
    with pytest.raises(ValueError, match="not valid for 3 classes"):
        compute_calibration_metrics(y_bad, y_prob[:3])


def test_calibration_metrics_configurable_bins():
    """Number of bins is configurable in compute_calibration_metrics."""
    y_true, y_prob = _make_random_probs(n=200)
    result = compute_calibration_metrics(y_true, y_prob, n_bins=20)
    assert len(result.confidence_bins) == 20


# ============================================================================
# build_calibration_candidate tests
# ============================================================================


def test_build_candidate_required_fields():
    """CalibrationCandidate dict has all required fields."""
    y_true, y_prob = _make_random_probs(n=200)
    result = compute_calibration_metrics(y_true, y_prob)
    candidate = build_calibration_candidate(
        result, mode="SWING", model_artifact_id="ma-test-001"
    )

    required = [
        "schema_version", "calibration_candidate_id", "mode",
        "model_artifact_id", "calibration_method", "calibration_metrics",
        "confidence_bins", "limitations", "status",
    ]
    for field in required:
        assert field in candidate, f"Missing required field: {field}"

    assert candidate["schema_version"] == "1.0.0"
    assert candidate["mode"] == "SWING"
    assert candidate["model_artifact_id"] == "ma-test-001"
    assert candidate["calibration_method"] == "none"
    assert candidate["status"] in ("CALIBRATED", "UNCALIBRATED", "UNRELIABLE")
    assert "created_at" in candidate


def test_build_candidate_calibration_metrics_subfields():
    """Calibration metrics contain ECE, MCE, Brier."""
    y_true, y_prob = _make_random_probs(n=200)
    result = compute_calibration_metrics(y_true, y_prob)
    candidate = build_calibration_candidate(
        result, mode="SWING", model_artifact_id="ma-test-001"
    )

    metrics = candidate["calibration_metrics"]
    assert "expected_calibration_error" in metrics
    assert "maximum_calibration_error" in metrics
    assert "brier_score" in metrics
    assert isinstance(metrics["expected_calibration_error"], float)
    assert isinstance(metrics["maximum_calibration_error"], float)


def test_build_candidate_confidence_bins_format():
    """Each confidence bin has all required fields."""
    y_true, y_prob = _make_random_probs(n=200)
    result = compute_calibration_metrics(y_true, y_prob)
    candidate = build_calibration_candidate(
        result, mode="SWING", model_artifact_id="ma-test-001"
    )

    bins = candidate["confidence_bins"]
    assert isinstance(bins, list)
    assert len(bins) > 0

    for b in bins:
        assert "bin_lower" in b
        assert "bin_upper" in b
        assert "sample_count" in b
        assert "predicted_rate" in b
        assert "actual_rate" in b
        assert isinstance(b["bin_lower"], float)
        assert isinstance(b["sample_count"], int)


def test_build_candidate_invalid_mode():
    """Invalid mode raises ValueError."""
    result = CalibrationResult(
        ece=0.0, mce=0.0, brier_score=0.0,
        confidence_bins=[], n_samples=0, status="CALIBRATED",
    )
    with pytest.raises(ValueError, match="Unsupported mode"):
        build_calibration_candidate(result, mode="INVALID", model_artifact_id="ma-001")


def test_build_candidate_invalid_method():
    """Invalid calibration method raises ValueError."""
    result = CalibrationResult(
        ece=0.0, mce=0.0, brier_score=0.0,
        confidence_bins=[], n_samples=0, status="CALIBRATED",
    )
    with pytest.raises(ValueError, match="Unsupported calibration method"):
        build_calibration_candidate(
            result, mode="SWING", model_artifact_id="ma-001",
            calibration_method="invalid",
        )


def test_build_candidate_all_modes():
    """All three modes produce valid candidates."""
    y_true, y_prob = _make_random_probs(n=100)
    result = compute_calibration_metrics(y_true, y_prob)

    for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
        candidate = build_calibration_candidate(
            result, mode=mode, model_artifact_id="ma-test-001"
        )
        assert candidate["mode"] == mode


def test_build_candidate_all_methods():
    """All calibration methods are accepted."""
    result = CalibrationResult(
        ece=0.0, mce=0.0, brier_score=0.0,
        confidence_bins=[], n_samples=0, status="CALIBRATED",
    )
    for method in ("isotonic", "platt", "beta", "sigmoid", "none"):
        candidate = build_calibration_candidate(
            result, mode="SWING", model_artifact_id="ma-001",
            calibration_method=method,
        )
        assert candidate["calibration_method"] == method


def test_build_candidate_auto_generates_id():
    """Auto-generated calibration_candidate_id starts with cc-."""
    y_true, y_prob = _make_random_probs(n=100)
    result = compute_calibration_metrics(y_true, y_prob)
    candidate = build_calibration_candidate(
        result, mode="SWING", model_artifact_id="ma-test-001"
    )
    assert candidate["calibration_candidate_id"].startswith("cc-")


def test_build_candidate_respects_explicit_id():
    """Explicit calibration_candidate_id is preserved."""
    result = CalibrationResult(
        ece=0.0, mce=0.0, brier_score=0.0,
        confidence_bins=[], n_samples=0, status="CALIBRATED",
    )
    candidate = build_calibration_candidate(
        result, mode="SWING", model_artifact_id="ma-001",
        calibration_candidate_id="my-custom-id-001",
    )
    assert candidate["calibration_candidate_id"] == "my-custom-id-001"


def test_build_candidate_limitations_reflect_status():
    """UNCALIBRATED/UNRELIABLE status produces appropriate limitations."""
    # UNCALIBRATED — use compute_calibration_metrics so _build_limitations runs
    n = 200
    y_true = np.random.RandomState(42).randint(0, 3, size=n)
    # Create systematically overconfident predictions
    rng = np.random.RandomState(42)
    y_prob = np.zeros((n, 3), dtype=np.float64)
    for i in range(n):
        wrong = (y_true[i] + 1) % 3
        y_prob[i, y_true[i]] = 0.40
        y_prob[i, wrong] = 0.60

    result = compute_calibration_metrics(y_true, y_prob, n_bins=5)
    candidate = build_calibration_candidate(
        result, mode="SWING", model_artifact_id="ma-001"
    )
    limitations = candidate["limitations"]
    assert any("ECE" in lim for lim in limitations), f"No ECE mention in: {limitations}"
    assert any("threshold" in lim for lim in limitations), f"No threshold mention in: {limitations}"

    # UNRELIABLE — very overconfident predictions
    y_prob2 = np.zeros((n, 3), dtype=np.float64)
    for i in range(n):
        wrong = (y_true[i] + 1) % 3
        y_prob2[i, wrong] = 0.95
        y_prob2[i, y_true[i]] = 0.03
        y_prob2[i, 3 - wrong - y_true[i]] = 0.02

    result2 = compute_calibration_metrics(y_true, y_prob2, n_bins=5)
    candidate2 = build_calibration_candidate(
        result2, mode="SWING", model_artifact_id="ma-001"
    )
    limitations2 = candidate2["limitations"]
    assert any("not reliably" in lim for lim in limitations2), f"No reliability mention in: {limitations2}"


# ============================================================================
# Schema validation tests
# ============================================================================


def test_calibration_candidate_schema_validation():
    """CalibrationCandidate dict validates against JSON schema."""
    y_true, y_prob = _make_random_probs(n=200)
    result = compute_calibration_metrics(y_true, y_prob)
    candidate = build_calibration_candidate(
        result, mode="SWING", model_artifact_id="ma-test-001",
    )

    schema = _load_calibration_schema()
    validation = validate_payload(schema, candidate, "CalibrationCandidate")
    assert validation.valid, f"Schema validation failed: {validation.errors}"


def test_calibration_candidate_schema_binary():
    """CalibrationCandidate for binary model validates."""
    y_true, y_prob = _make_binary_probs(n=100)
    result = compute_calibration_metrics(y_true, y_prob, n_bins=5)
    candidate = build_calibration_candidate(
        result, mode="SWING", model_artifact_id="ma-binary-001",
    )

    schema = _load_calibration_schema()
    validation = validate_payload(schema, candidate, "CalibrationCandidate")
    assert validation.valid, f"Schema validation failed: {validation.errors}"


def test_calibration_candidate_schema_all_modes():
    """All three modes produce schema-valid candidates."""
    y_true, y_prob = _make_random_probs(n=100)
    result = compute_calibration_metrics(y_true, y_prob)

    schema = _load_calibration_schema()
    for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
        candidate = build_calibration_candidate(
            result, mode=mode, model_artifact_id=f"ma-{mode.lower()}-001"
        )
        validation = validate_payload(schema, candidate, f"CalibrationCandidate-{mode}")
        assert validation.valid, f"Schema validation failed for {mode}: {validation.errors}"


# ============================================================================
# Per-fold degradation tests
# ============================================================================


def test_per_fold_degradation_stable():
    """All folds within tolerance produce STABLE."""
    fold_results = {
        "fold_0": CalibrationResult(ece=0.03, mce=0.05, brier_score=0.1,
                                     confidence_bins=[], n_samples=100,
                                     status="CALIBRATED"),
        "fold_1": CalibrationResult(ece=0.04, mce=0.06, brier_score=0.12,
                                     confidence_bins=[], n_samples=100,
                                     status="CALIBRATED"),
        "fold_2": CalibrationResult(ece=0.035, mce=0.055, brier_score=0.11,
                                     confidence_bins=[], n_samples=100,
                                     status="CALIBRATED"),
    }
    degradation = compute_per_fold_degradation(fold_results)
    assert degradation["fold_stability"] == "STABLE"
    assert len(degradation["degraded_folds"]) == 0


def test_per_fold_degradation_detects_degraded():
    """Folds exceeding 1.5x baseline ECE are flagged."""
    # fold_2 has ECE well above 1.5x the mean baseline
    fold_results = {
        "fold_0": CalibrationResult(ece=0.03, mce=0.05, brier_score=0.1,
                                     confidence_bins=[], n_samples=100,
                                     status="CALIBRATED"),
        "fold_1": CalibrationResult(ece=0.03, mce=0.05, brier_score=0.1,
                                     confidence_bins=[], n_samples=100,
                                     status="CALIBRATED"),
        "fold_2": CalibrationResult(ece=0.15, mce=0.30, brier_score=0.5,
                                     confidence_bins=[], n_samples=100,
                                     status="UNRELIABLE"),
    }
    degradation = compute_per_fold_degradation(fold_results)
    assert "fold_2" in degradation["degraded_folds"]
    # 1/3 ≈ 33% > 30% threshold → CRITICAL
    assert degradation["fold_stability"] in ("CRITICAL",)


def test_per_fold_degradation_critical():
    """High degraded fold ratio produces CRITICAL."""
    # Use explicit low baseline so all 3 outlier folds are flagged
    fold_results = {
        "fold_0": CalibrationResult(ece=0.40, mce=0.60, brier_score=0.5,
                                     confidence_bins=[], n_samples=100,
                                     status="UNRELIABLE"),
        "fold_1": CalibrationResult(ece=0.45, mce=0.65, brier_score=0.5,
                                     confidence_bins=[], n_samples=100,
                                     status="UNRELIABLE"),
        "fold_2": CalibrationResult(ece=0.50, mce=0.70, brier_score=0.6,
                                     confidence_bins=[], n_samples=100,
                                     status="UNRELIABLE"),
    }
    degradation = compute_per_fold_degradation(fold_results, baseline_ece=0.05)
    assert len(degradation["degraded_folds"]) == 3
    assert degradation["fold_stability"] == "CRITICAL"


def test_per_fold_degradation_empty():
    """Empty per-fold results produce STABLE with no degraded folds."""
    degradation = compute_per_fold_degradation({})
    assert degradation["fold_stability"] == "STABLE"
    assert len(degradation["degraded_folds"]) == 0


def test_per_fold_degradation_with_explicit_baseline():
    """Explicit baseline ECE is used for comparison."""
    fold_results = {
        "fold_0": CalibrationResult(ece=0.02, mce=0.04, brier_score=0.08,
                                     confidence_bins=[], n_samples=100,
                                     status="CALIBRATED"),
        "fold_1": CalibrationResult(ece=0.10, mce=0.20, brier_score=0.3,
                                     confidence_bins=[], n_samples=100,
                                     status="UNCALIBRATED"),
    }
    # Use a very tight baseline so both folds get flagged
    degradation = compute_per_fold_degradation(fold_results, baseline_ece=0.01)
    assert len(degradation["degraded_folds"]) == 2


# ============================================================================
# calibrate_model convenience function
# ============================================================================


def test_calibrate_model_one_shot():
    """calibrate_model produces a complete CalibrationCandidate."""
    y_true, y_prob = _make_random_probs(n=200)
    candidate = calibrate_model(
        y_true, y_prob, mode="SWING", model_artifact_id="ma-test-001",
    )

    assert candidate["mode"] == "SWING"
    assert candidate["model_artifact_id"] == "ma-test-001"
    assert "calibration_metrics" in candidate
    assert "confidence_bins" in candidate
    assert "status" in candidate


def test_calibrate_model_with_per_fold():
    """calibrate_model includes per-fold degradation when provided."""
    y_true, y_prob = _make_random_probs(n=200)
    per_fold = {
        "fold_0": CalibrationResult(ece=0.03, mce=0.05, brier_score=0.1,
                                     confidence_bins=[], n_samples=100,
                                     status="CALIBRATED"),
        "fold_1": CalibrationResult(ece=0.12, mce=0.25, brier_score=0.4,
                                     confidence_bins=[], n_samples=100,
                                     status="UNRELIABLE"),
    }
    candidate = calibrate_model(
        y_true, y_prob, mode="SWING", model_artifact_id="ma-test-001",
        per_fold_results=per_fold,
    )

    limitations = candidate["limitations"]
    assert any("degradation" in lim.lower() for lim in limitations)


def test_calibrate_model_schema_valid():
    """calibrate_model output validates against schema."""
    y_true, y_prob = _make_random_probs(n=200)
    candidate = calibrate_model(
        y_true, y_prob, mode="SWING", model_artifact_id="ma-test-001",
    )

    schema = _load_calibration_schema()
    validation = validate_payload(schema, candidate, "CalibrationCandidate")
    assert validation.valid, f"Schema validation failed: {validation.errors}"


# ============================================================================
# Edge cases
# ============================================================================


def test_single_class_input():
    """Single-class inputs (all same label) are handled."""
    n = 100
    n_classes = 3
    y_true = np.zeros(n, dtype=int)
    y_prob = np.zeros((n, n_classes), dtype=np.float64)
    y_prob[:, 0] = 0.8
    y_prob[:, 1] = 0.15
    y_prob[:, 2] = 0.05

    result = compute_calibration_metrics(y_true, y_prob)
    assert result.ece >= 0.0


def test_two_samples_per_bin():
    """Very small datasets produce valid results."""
    y_true = np.array([0, 1])
    y_prob = np.array([[0.6, 0.3, 0.1], [0.2, 0.7, 0.1]], dtype=np.float64)

    result = compute_calibration_metrics(y_true, y_prob, n_bins=5)
    assert result.ece >= 0.0
    # With very small data, status should still be valid
    assert result.status in ("CALIBRATED", "UNCALIBRATED", "UNRELIABLE")


def test_all_empty_bins():
    """Predictions spread across multiple bins report correct per-bin counts.

    Uses enough classes so the target confidence is always the maximum
    probability even for the lowest bin (confidence = 0.05).
    """
    n_bins = 10
    n_per_bin = 5
    n = n_bins * n_per_bin
    # Need enough classes so min confidence (0.05) is still the argmax.
    # With k classes the max is at least 1/k; 20 classes gives min max = 0.05.
    n_classes = 20
    y_true = np.zeros(n, dtype=int)
    y_prob = np.zeros((n, n_classes), dtype=np.float64)

    # Place n_per_bin samples at the centre of each bin
    for i in range(n_bins):
        conf = (i + 0.5) / n_bins  # 0.05, 0.15, ..., 0.95
        remaining = 1.0 - conf
        rest_per_class = remaining / (n_classes - 1)
        start = i * n_per_bin
        end = start + n_per_bin
        y_prob[start:end, 0] = conf
        y_prob[start:end, 1:] = rest_per_class

    bins = compute_confidence_bins(y_true, y_prob, n_bins=n_bins)
    non_empty = [b for b in bins if b.sample_count > 0]
    assert len(non_empty) == n_bins, (
        f"Expected {n_bins} non-empty bins, got {len(non_empty)}"
    )
    for i, b in enumerate(bins):
        assert b.sample_count == n_per_bin, (
            f"Bin {i} ([{b.bin_lower}, {b.bin_upper})): "
            f"expected {n_per_bin} samples, got {b.sample_count}"
        )


def test_confidence_out_of_range():
    """Out-of-range confidence values raise ValueError."""
    y_true = np.array([0, 1, 2])
    y_prob = np.array([[1.5, 0.0, 0.0], [0.0, 1.5, 0.0], [0.0, 0.0, 1.5]],
                       dtype=np.float64)
    with pytest.raises(ValueError, match="Confidence values must be in"):
        compute_calibration_metrics(y_true, y_prob)


def test_deterministic_output():
    """Same inputs produce same calibration results."""
    y_true, y_prob = _make_random_probs(n=200)
    result1 = compute_calibration_metrics(y_true, y_prob)
    result2 = compute_calibration_metrics(y_true, y_prob)

    assert result1.ece == result2.ece
    assert result1.mce == result2.mce
    assert result1.brier_score == result2.brier_score
    assert result1.status == result2.status


# ============================================================================
# Module import tests
# ============================================================================


def test_calibration_module_imports():
    """All expected symbols are importable from alphaforge.calibration."""
    from alphaforge.calibration import (
        CalibrationResult,
        compute_calibration_metrics,
        compute_confidence_bins,
        assign_calibration_status,
        build_calibration_candidate,
        compute_per_fold_degradation,
    )
    assert CalibrationResult is not None
    assert callable(compute_calibration_metrics)
    assert callable(compute_confidence_bins)
    assert callable(assign_calibration_status)
    assert callable(build_calibration_candidate)
    assert callable(compute_per_fold_degradation)
