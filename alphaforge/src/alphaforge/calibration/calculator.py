"""Calibration calculator for AlphaForge mode-specific model outputs.

Computes expected calibration error (ECE), maximum calibration error (MCE),
confidence bins (reliability diagram data), assigns calibration status, and
produces the CalibrationCandidate artifact per the JSON schema.

This module is numpy-only — no ML framework dependencies. It operates on
predicted probability vectors and ground-truth integer labels.

Usage:
    from alphaforge.calibration import compute_calibration_metrics

    # y_prob: (n_samples, n_classes) softmax probabilities
    # y_true: (n_samples,) integer labels 0, 1, 2
    result = compute_calibration_metrics(y_true, y_prob, n_bins=10)
    candidate = build_calibration_candidate(
        result, mode="SWING", model_artifact_id="ma-001"
    )
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION: str = "1.0.0"

# Calibration status thresholds per model_artifact_contract.md
ECE_CALIBRATED_THRESHOLD: float = 0.05   # ECE < 0.05  => CALIBRATED
ECE_UNCALIBRATED_THRESHOLD: float = 0.10  # ECE < 0.10  => UNCALIBRATED
                                           # ECE >= 0.10 => UNRELIABLE

# Default number of confidence bins
DEFAULT_N_BINS: int = 10

# Per-fold degradation: a fold is "degraded" if its ECE exceeds the
# aggregate ECE by this relative multiplier
DEGRADATION_MULTIPLIER: float = 1.5


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ConfidenceBin:
    """A single bin in the reliability diagram (calibration assessment).

    Attributes:
        bin_lower: Lower bound of confidence range [0, 1].
        bin_upper: Upper bound of confidence range [0, 1].
        sample_count: Number of predictions in this bin.
        predicted_rate: Average predicted confidence in the bin.
        actual_rate: Empirical frequency of correct predictions in the bin.
        deviation: predicted_rate - actual_rate (positive = overconfidence).
    """

    bin_lower: float
    bin_upper: float
    sample_count: int
    predicted_rate: float
    actual_rate: float
    deviation: float


@dataclass
class CalibrationResult:
    """Complete calibration assessment for a model's probability outputs.

    Attributes:
        ece: Expected Calibration Error (lower is better).
        mce: Maximum Calibration Error.
        brier_score: Brier score (mean squared error of probabilities).
        confidence_bins: List of ConfidenceBin for reliability diagram.
        n_samples: Total number of samples evaluated.
        status: Calibration status string.
        limitations: List of known limitations.
        per_fold_metrics: Optional dict mapping fold_id -> ECE for degradation.
    """

    ece: float
    mce: float
    brier_score: float
    confidence_bins: List[ConfidenceBin]
    n_samples: int
    status: str
    limitations: List[str] = field(default_factory=list)
    per_fold_metrics: Dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Calibration computation
# ---------------------------------------------------------------------------


def compute_confidence_bins(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = DEFAULT_N_BINS,
) -> List[ConfidenceBin]:
    """Compute per-bin calibration statistics (reliability diagram data).

    For each confidence bin [bin_lower, bin_upper), computes:
      - How many predictions fall into the bin
      - The average predicted confidence for those predictions
      - The empirical accuracy (fraction correct)
      - The deviation (predicted - actual)

    Uses the confidence of the predicted class (argmax probability).

    Args:
        y_true: Ground-truth integer labels of shape (n_samples,).
        y_prob: Predicted probabilities of shape (n_samples, n_classes).
        n_bins: Number of equal-width confidence bins (default 10).

    Returns:
        List of ConfidenceBin objects sorted by bin_lower.

    Raises:
        ValueError: If inputs have incompatible shapes or invalid values.
    """
    if y_true.ndim != 1:
        raise ValueError(f"y_true must be 1D, got {y_true.ndim}D")
    if y_prob.ndim != 2:
        raise ValueError(f"y_prob must be 2D, got {y_prob.ndim}D")
    if len(y_true) != y_prob.shape[0]:
        raise ValueError(
            f"y_true ({len(y_true)}) and y_prob ({y_prob.shape[0]}) "
            f"must have same number of samples"
        )
    if n_bins < 1:
        raise ValueError(f"n_bins must be >= 1, got {n_bins}")
    if len(y_true) == 0:
        raise ValueError("Empty input arrays")

    # Predicted class and its confidence
    predicted_classes = np.argmax(y_prob, axis=1)
    confidences = np.max(y_prob, axis=1)

    if np.any((confidences < 0) | (confidences > 1)):
        raise ValueError("Confidence values must be in [0, 1]")

    # Correctness vector
    correct = (predicted_classes == y_true).astype(np.float64)

    # Edge width for bins
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: List[ConfidenceBin] = []

    for i in range(n_bins):
        lower = float(bin_edges[i])
        upper = float(bin_edges[i + 1])

        # Handle the last bin inclusive of upper bound
        if i == n_bins - 1:
            mask = (confidences >= lower) & (confidences <= upper)
        else:
            mask = (confidences >= lower) & (confidences < upper)

        bin_count = int(np.sum(mask))

        if bin_count > 0:
            avg_predicted = float(np.mean(confidences[mask]))
            avg_actual = float(np.mean(correct[mask]))
        else:
            avg_predicted = lower + (upper - lower) / 2
            avg_actual = 0.0

        deviation = avg_predicted - avg_actual

        bins.append(ConfidenceBin(
            bin_lower=lower,
            bin_upper=upper,
            sample_count=bin_count,
            predicted_rate=avg_predicted,
            actual_rate=avg_actual,
            deviation=deviation,
        ))

    return bins


def compute_ece(confidence_bins: List[ConfidenceBin], n_samples: int) -> float:
    """Compute Expected Calibration Error from confidence bins.

    ECE = sum over bins of (bin_count / n_samples) * |deviation|

    Args:
        confidence_bins: List of ConfidenceBin from compute_confidence_bins().
        n_samples: Total number of samples.

    Returns:
        ECE score (0 = perfectly calibrated).
    """
    if n_samples == 0:
        return 0.0
    ece = 0.0
    for bin_ in confidence_bins:
        weight = bin_.sample_count / n_samples
        ece += weight * abs(bin_.deviation)
    return ece


def compute_mce(confidence_bins: List[ConfidenceBin]) -> float:
    """Compute Maximum Calibration Error from confidence bins.

    Only considers bins with at least one sample (empty bins are excluded).
    MCE = max over non-empty bins of |deviation|

    Returns:
        MCE score (0 = perfectly calibrated).
    """
    non_empty = [b for b in confidence_bins if b.sample_count > 0]
    if not non_empty:
        return 0.0
    return max(abs(bin_.deviation) for bin_ in non_empty)


def compute_brier_score(
    y_true: np.ndarray,
    y_prob: np.ndarray,
) -> float:
    """Compute the multi-class Brier score.

    Brier = (1 / N) * sum over samples sum over classes (p_ik - o_ik)^2
    where o_ik = 1 if sample i belongs to class k, else 0.

    Args:
        y_true: Integer labels of shape (n_samples,).
        y_prob: Predicted probabilities of shape (n_samples, n_classes).

    Returns:
        Brier score (0 = perfect, 1 = worst).
    """
    n = len(y_true)
    n_classes = y_prob.shape[1]

    # One-hot encode
    one_hot = np.zeros((n, n_classes), dtype=np.float64)
    one_hot[np.arange(n), y_true] = 1.0

    squared_errors = (y_prob - one_hot) ** 2
    return float(np.mean(np.sum(squared_errors, axis=1)))


def assign_calibration_status(
    ece: float,
    mce: Optional[float] = None,
) -> str:
    """Assign calibration status based on ECE.

    Rules per model_artifact_contract.md:
      - CALIBRATED:   ECE < 0.05
      - UNCALIBRATED: 0.05 <= ECE < 0.10
      - UNRELIABLE:   ECE >= 0.10

    Args:
        ece: Expected Calibration Error.
        mce: Optional Maximum Calibration Error (currently not used for
             status assignment, but available for future refinement).

    Returns:
        One of "CALIBRATED", "UNCALIBRATED", "UNRELIABLE".
    """
    if ece < ECE_CALIBRATED_THRESHOLD:
        return "CALIBRATED"
    elif ece < ECE_UNCALIBRATED_THRESHOLD:
        return "UNCALIBRATED"
    else:
        return "UNRELIABLE"


def compute_calibration_metrics(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = DEFAULT_N_BINS,
) -> CalibrationResult:
    """Compute full calibration assessment.

    Args:
        y_true: Ground-truth integer labels of shape (n_samples,).
        y_prob: Predicted probabilities of shape (n_samples, n_classes).
        n_bins: Number of confidence bins (default 10).

    Returns:
        CalibrationResult with ECE, MCE, Brier score, confidence bins, status.

    Raises:
        ValueError: If inputs are invalid.
    """
    # Input validation
    if not isinstance(y_true, np.ndarray):
        raise TypeError(f"y_true must be numpy.ndarray, got {type(y_true).__name__}")
    if not isinstance(y_prob, np.ndarray):
        raise TypeError(f"y_prob must be numpy.ndarray, got {type(y_prob).__name__}")
    if y_true.ndim != 1:
        raise ValueError(f"y_true must be 1D, got {y_true.ndim}D")
    if y_prob.ndim != 2:
        raise ValueError(f"y_prob must be 2D, got {y_prob.ndim}D")
    if len(y_true) != y_prob.shape[0]:
        raise ValueError(
            f"y_true ({len(y_true)}) and y_prob ({y_prob.shape[0]}) "
            f"must have same number of samples"
        )
    if len(y_true) == 0:
        raise ValueError("Empty input arrays")

    # Validate labels are valid integer labels
    unique_labels = set(y_true.tolist())
    n_classes = y_prob.shape[1]
    if not unique_labels.issubset(set(range(n_classes))):
        raise ValueError(
            f"y_true labels {unique_labels} not valid for {n_classes} classes"
        )

    # Compute confidence bins
    bins = compute_confidence_bins(y_true, y_prob, n_bins=n_bins)

    # Compute metrics
    ece = compute_ece(bins, len(y_true))
    mce = compute_mce(bins)
    brier = compute_brier_score(y_true, y_prob)
    status = assign_calibration_status(ece, mce)

    # Build limitations
    limitations = _build_limitations(status, ece, mce, bins)

    return CalibrationResult(
        ece=ece,
        mce=mce,
        brier_score=brier,
        confidence_bins=bins,
        n_samples=len(y_true),
        status=status,
        limitations=limitations,
    )


# ---------------------------------------------------------------------------
# Per-fold degradation tracking
# ---------------------------------------------------------------------------


def compute_per_fold_degradation(
    per_fold_results: Dict[str, CalibrationResult],
    baseline_ece: Optional[float] = None,
) -> Dict[str, Any]:
    """Compute per-fold calibration degradation relative to aggregate.

    A fold is flagged as "degraded" if its ECE exceeds:
      - baseline_ece * DEGRADATION_MULTIPLIER (if baseline_ece provided)
      - Otherwise, the mean ECE across all folds * DEGRADATION_MULTIPLIER

    Args:
        per_fold_results: Dict mapping fold_id (str) -> CalibrationResult.
        baseline_ece: Optional baseline ECE to compare against. If None,
                      computed as mean ECE across folds.

    Returns:
        Dict with:
          - "per_fold_ece": dict of fold_id -> ece
          - "per_fold_status": dict of fold_id -> status
          - "baseline_ece": the reference ECE used
          - "degraded_folds": list of fold_ids flagged as degraded
          - "degradation_ratio": max(fold_ece / baseline_ece) if baseline > 0
          - "fold_stability": "STABLE" | "DEGRADED" | "CRITICAL"
    """
    if not per_fold_results:
        return {
            "per_fold_ece": {},
            "per_fold_status": {},
            "baseline_ece": 0.0,
            "degraded_folds": [],
            "degradation_ratio": 0.0,
            "fold_stability": "STABLE",
        }

    fold_eces = {fid: res.ece for fid, res in per_fold_results.items()}
    fold_statuses = {fid: res.status for fid, res in per_fold_results.items()}

    if baseline_ece is None:
        baseline_ece = float(np.mean(list(fold_eces.values())))

    degraded_folds = [
        fid for fid, ece in fold_eces.items()
        if baseline_ece > 0 and ece > baseline_ece * DEGRADATION_MULTIPLIER
    ]

    max_ece = max(fold_eces.values()) if fold_eces else 0.0
    degradation_ratio = max_ece / baseline_ece if baseline_ece > 0 else 1.0

    # Fold stability classification
    degraded_ratio = len(degraded_folds) / len(per_fold_results) if per_fold_results else 0.0
    if degraded_ratio == 0.0:
        fold_stability = "STABLE"
    elif degraded_ratio <= 0.3:
        fold_stability = "DEGRADED"
    else:
        fold_stability = "CRITICAL"

    return {
        "per_fold_ece": fold_eces,
        "per_fold_status": fold_statuses,
        "baseline_ece": baseline_ece,
        "degraded_folds": degraded_folds,
        "degradation_ratio": degradation_ratio,
        "fold_stability": fold_stability,
    }


# ---------------------------------------------------------------------------
# CalibrationCandidate builder
# ---------------------------------------------------------------------------


def build_calibration_candidate(
    calibration_result: CalibrationResult,
    mode: str,
    model_artifact_id: str,
    calibration_candidate_id: str = "",
    calibration_method: str = "none",
    per_fold_degradation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a CalibrationCandidate dict matching the JSON schema.

    Args:
        calibration_result: CalibrationResult from compute_calibration_metrics().
        mode: Trading mode (SWING, SCALP, AGGRESSIVE_SCALP).
        model_artifact_id: Associated ModelArtifact ID.
        calibration_candidate_id: Optional unique ID (auto-generated if empty).
        calibration_method: Calibration method applied
                           ("isotonic", "platt", "beta", "sigmoid", "none").
        per_fold_degradation: Optional result from compute_per_fold_degradation().

    Returns:
        Dict matching calibration_candidate.schema.json.

    Raises:
        ValueError: If mode is invalid.
    """
    if mode not in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
        raise ValueError(
            f"Unsupported mode: '{mode}'. Must be SWING, SCALP, or AGGRESSIVE_SCALP."
        )

    if calibration_method not in ("isotonic", "platt", "beta", "sigmoid", "none"):
        raise ValueError(
            f"Unsupported calibration method: '{calibration_method}'. "
            f"Must be isotonic, platt, beta, sigmoid, or none."
        )

    # Generate candidate ID if not provided
    if not calibration_candidate_id:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        raw = f"{mode}|{model_artifact_id}|{ts}"
        h = hashlib.sha256(raw.encode()).hexdigest()[:8]
        calibration_candidate_id = f"cc-{mode.lower()}-{ts}-{h}"

    now_iso = datetime.now(timezone.utc).isoformat()

    # Build confidence bins dicts
    confidence_bins_list = [
        {
            "bin_lower": b.bin_lower,
            "bin_upper": b.bin_upper,
            "sample_count": b.sample_count,
            "predicted_rate": b.predicted_rate,
            "actual_rate": b.actual_rate,
            "deviation": b.deviation,
        }
        for b in calibration_result.confidence_bins
    ]

    # Build limitations list
    limitations = list(calibration_result.limitations)

    # Add per-fold degradation info to limitations if available
    if per_fold_degradation and per_fold_degradation.get("degraded_folds"):
        df = per_fold_degradation["degraded_folds"]
        limitations.append(
            f"Per-fold degradation detected: {len(df)} fold(s) exceed "
            f"{DEGRADATION_MULTIPLIER}x baseline ECE: {df}"
        )
        if per_fold_degradation.get("fold_stability") == "CRITICAL":
            limitations.append(
                "Fold stability is CRITICAL — calibration may not generalize"
            )

    candidate: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "calibration_candidate_id": calibration_candidate_id,
        "mode": mode,
        "model_artifact_id": model_artifact_id,
        "calibration_method": calibration_method,
        "calibration_metrics": {
            "expected_calibration_error": calibration_result.ece,
            "maximum_calibration_error": calibration_result.mce,
            "brier_score": calibration_result.brier_score,
        },
        "confidence_bins": confidence_bins_list,
        "limitations": limitations,
        "status": calibration_result.status,
        "created_at": now_iso,
    }

    return candidate


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_limitations(
    status: str,
    ece: float,
    mce: float,
    bins: List[ConfidenceBin],
) -> List[str]:
    """Build limitations list based on calibration assessment."""
    limitations: List[str] = []

    if status == "UNCALIBRATED":
        limitations.append(
            f"ECE={ece:.4f} exceeds calibrated threshold (<{ECE_CALIBRATED_THRESHOLD})"
        )
        limitations.append("Calibration required before deployment")
    elif status == "UNRELIABLE":
        limitations.append(
            f"ECE={ece:.4f} exceeds unreliable threshold (>{ECE_UNCALIBRATED_THRESHOLD})"
        )
        limitations.append("Model outputs are not reliably calibrated")

    # Check for empty bins
    empty_bins = [b for b in bins if b.sample_count == 0]
    if empty_bins:
        limitations.append(
            f"{len(empty_bins)} confidence bin(s) have zero samples"
        )

    # Check for high deviation bins
    high_dev_bins = [b for b in bins if abs(b.deviation) > 0.10 and b.sample_count > 0]
    if high_dev_bins:
        worst = max(high_dev_bins, key=lambda b: abs(b.deviation))
        limitations.append(
            f"Worst bin deviation {worst.deviation:+.4f} in range "
            f"[{worst.bin_lower:.2f}, {worst.bin_upper:.2f})"
        )

    return limitations


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def calibrate_model(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    mode: str = "SWING",
    model_artifact_id: str = "",
    n_bins: int = DEFAULT_N_BINS,
    calibration_method: str = "none",
    per_fold_results: Optional[Dict[str, CalibrationResult]] = None,
) -> Dict[str, Any]:
    """Complete calibration pipeline: compute metrics, build candidate.

    One-shot convenience for the common case where you have predictions
    and want a full CalibrationCandidate dict.

    Args:
        y_true: Ground-truth integer labels.
        y_prob: Predicted probabilities.
        mode: Trading mode.
        model_artifact_id: ModelArtifact ID.
        n_bins: Number of confidence bins.
        calibration_method: Calibration method applied.
        per_fold_results: Optional per-fold calibration results for degradation.

    Returns:
        CalibrationCandidate dict matching the JSON schema.
    """
    result = compute_calibration_metrics(y_true, y_prob, n_bins=n_bins)

    degradation = None
    if per_fold_results:
        degradation = compute_per_fold_degradation(per_fold_results)

    return build_calibration_candidate(
        calibration_result=result,
        mode=mode,
        model_artifact_id=model_artifact_id,
        calibration_method=calibration_method,
        per_fold_degradation=degradation,
    )
