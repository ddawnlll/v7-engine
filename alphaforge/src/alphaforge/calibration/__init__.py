"""Calibration assessment for model probability/confidence outputs.

Produces CalibrationCandidate artifacts documenting how a mode-specific
model's outputs were calibrated and whether the calibration is usable.
Computes ECE, MCE, confidence bins, and per-fold degradation tracking.

Exports:
    CalibrationResult
    compute_calibration_metrics
    compute_confidence_bins
    assign_calibration_status
    build_calibration_candidate
    compute_per_fold_degradation
"""

from alphaforge.calibration.calculator import (
    CalibrationResult,
    compute_calibration_metrics,
    compute_confidence_bins,
    assign_calibration_status,
    build_calibration_candidate,
    compute_per_fold_degradation,
)

__all__ = [
    "CalibrationResult",
    "compute_calibration_metrics",
    "compute_confidence_bins",
    "assign_calibration_status",
    "build_calibration_candidate",
    "compute_per_fold_degradation",
]
