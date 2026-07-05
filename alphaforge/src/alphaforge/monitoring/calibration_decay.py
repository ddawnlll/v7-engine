"""Calibration decay monitoring — tracks model calibration degradation over time.

Detects when a model's calibration quality has degraded relative to a
baseline measurement. This is a leading indicator that model predictions
may be becoming overconfident or underconfident, triggering recalibration.

The monitor compares Expected Calibration Error (ECE) computed on current
production predictions against a baseline ECE recorded at training/calibration
time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Multiplier threshold: decay is flagged when current ECE exceeds
# baseline ECE by this factor
DECAY_MULTIPLIER: float = 1.5

# Minimum number of samples required for meaningful ECE computation
MIN_SAMPLES_FOR_ECE: int = 20

# Default bin count for ECE computation
DEFAULT_ECE_BINS: int = 10

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DecayReport:
    """Result of calibration decay assessment.

    Attributes:
        current_ece: ECE computed on current production predictions.
        baseline_ece: Reference ECE from training/calibration time.
        decay_score: Ratio of current_ece / baseline_ece (if baseline > 0).
        is_decayed: Whether decay exceeds the configured multiplier threshold.
        n_current: Number of samples used for current ECE.
        n_baseline: Number of samples used for baseline ECE.
        details: Optional additional diagnostics.
    """

    current_ece: float
    baseline_ece: float
    decay_score: float
    is_decayed: bool
    n_current: int
    n_baseline: int
    details: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ECE computation
# ---------------------------------------------------------------------------


def _compute_ece_from_probs(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = DEFAULT_ECE_BINS,
) -> float:
    """Compute Expected Calibration Error from predicted probabilities.

    ECE = sum over bins of (bin_count / n_samples) * |accuracy - confidence|

    Args:
        y_true: Ground-truth integer labels (n_samples,).
        y_prob: Predicted probabilities (n_samples, n_classes).
        n_bins: Number of confidence bins.

    Returns:
        ECE score (0 = perfectly calibrated).
    """
    if len(y_true) == 0:
        return 0.0

    predicted_classes = np.argmax(y_prob, axis=1)
    confidences = np.max(y_prob, axis=1)
    correct = (predicted_classes == y_true).astype(np.float64)

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_indices = np.digitize(confidences, bin_edges) - 1
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)

    ece = 0.0
    for i in range(n_bins):
        mask = bin_indices == i
        if not mask.any():
            continue
        bin_acc = float(np.mean(correct[mask]))
        bin_conf = float(np.mean(confidences[mask]))
        ece += mask.sum() * abs(bin_acc - bin_conf)

    return ece / len(y_true)


# ---------------------------------------------------------------------------
# CalibrationDecayMonitor
# ---------------------------------------------------------------------------


class CalibrationDecayMonitor:
    """Monitors calibration decay between a baseline and current period.

    Detects when the model's calibration quality degrades by comparing
    the current ECE against the baseline ECE recorded at calibration time.
    A decay score > 1.0 means calibration has gotten worse; > DECAY_MULTIPLIER
    means actionable decay.

    Typical usage::

        monitor = CalibrationDecayMonitor()
        report = monitor.compute_decay(
            current=(y_true, y_prob_current),
            baseline=(y_true_baseline, y_prob_baseline),
        )
        if report.is_decayed:
            logger.warning("Calibration decay detected: score=%.2f", report.decay_score)
    """

    def __init__(
        self,
        decay_multiplier: float = DECAY_MULTIPLIER,
        ece_bins: int = DEFAULT_ECE_BINS,
    ):
        """Initialize the decay monitor.

        Args:
            decay_multiplier: Threshold ratio; current/baseline ECE above
                              this value flags decay (default 1.5).
            ece_bins: Number of bins for ECE computation (default 10).
        """
        self._decay_multiplier = decay_multiplier
        self._ece_bins = ece_bins

    def compute_decay(
        self,
        current: tuple[np.ndarray, np.ndarray],
        baseline: tuple[np.ndarray, np.ndarray],
    ) -> DecayReport:
        """Compare current calibration against baseline and detect decay.

        Args:
            current: Tuple of (y_true, y_prob) for the current/production
                     period. Both are numpy arrays.
            baseline: Tuple of (y_true, y_prob) for the reference/baseline
                      period. Both are numpy arrays.

        Returns:
            DecayReport with ECE values and decay verdict.

        Raises:
            ValueError: If either pair has empty arrays or mismatched sizes.
        """
        y_true_cur, y_prob_cur = current
        y_true_base, y_prob_base = baseline

        # Input validation
        if len(y_true_cur) == 0:
            raise ValueError("current y_true is empty")
        if len(y_true_base) == 0:
            raise ValueError("baseline y_true is empty")
        if len(y_true_cur) != y_prob_cur.shape[0]:
            raise ValueError("current y_true and y_prob sample count mismatch")
        if len(y_true_base) != y_prob_base.shape[0]:
            raise ValueError("baseline y_true and y_prob sample count mismatch")

        current_ece = _compute_ece_from_probs(y_true_cur, y_prob_cur, self._ece_bins)
        baseline_ece = _compute_ece_from_probs(y_true_base, y_prob_base, self._ece_bins)

        # Decay score: how much worse is current vs baseline
        if baseline_ece <= 0:
            decay_score = float(current_ece / 1e-10)  # effectively infinite
        else:
            decay_score = current_ece / baseline_ece

        is_decayed = decay_score > self._decay_multiplier

        return DecayReport(
            current_ece=current_ece,
            baseline_ece=baseline_ece,
            decay_score=decay_score,
            is_decayed=is_decayed,
            n_current=len(y_true_cur),
            n_baseline=len(y_true_base),
            details={
                "decay_multiplier": self._decay_multiplier,
                "ece_bins": self._ece_bins,
            },
        )
