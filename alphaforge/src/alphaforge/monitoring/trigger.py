"""Recalibration trigger — multi-signal decision engine.

Evaluates drift, decay, and quality signals to produce a recalibration
decision. A recalibration is triggered when the combined evidence from
all three monitors exceeds configured thresholds.

This is the orchestration layer that makes the final
"should we recalibrate now?" decision for the V7 handoff pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from alphaforge.monitoring.calibration_decay import DecayReport
from alphaforge.monitoring.feature_drift import DriftReport
from alphaforge.monitoring.label_quality import LabelQualityReport

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Priority levels
PRIORITY_LOW: str = "LOW"
PRIORITY_MEDIUM: str = "MEDIUM"
PRIORITY_HIGH: str = "HIGH"
PRIORITY_CRITICAL: str = "CRITICAL"

# Cadence suggestions
CADENCE_IMMEDIATE: str = "IMMEDIATE"
CADENCE_NEXT_CYCLE: str = "NEXT_CYCLE"
CADENCE_NEXT_DAY: str = "NEXT_DAY"
CADENCE_NEXT_WEEK: str = "NEXT_WEEK"
CADENCE_NONE: str = "NONE"

# Number of drifted features required to escalate priority
WARNING_DRIFT_THRESHOLD: int = 2
CRITICAL_DRIFT_THRESHOLD: int = 4

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TriggerDecision:
    """Decision output from the recalibration trigger evaluation.

    Attributes:
        should_recalibrate: Whether recalibration is recommended.
        reasons: Human-readable list of reasons for the decision.
        priority: Priority level of the recommendation.
        suggested_cadence: Suggested urgency for performing recalibration.
        drift_report_count: Number of drift reports evaluated.
        drift_detected_count: Number of features flagged as drifted.
        decay_reports: Optional list of decay reports evaluated.
        quality_reports: Optional list of quality reports evaluated.
    """

    should_recalibrate: bool
    reasons: list[str] = field(default_factory=list)
    priority: str = PRIORITY_LOW
    suggested_cadence: str = CADENCE_NONE
    drift_report_count: int = 0
    drift_detected_count: int = 0
    decay_reports: list[DecayReport] = field(default_factory=list)
    quality_reports: list[LabelQualityReport] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Priority and cadence helpers
# ---------------------------------------------------------------------------


def _determine_priority_and_cadence(
    drifted_count: int,
    any_decayed: bool,
    any_quality_regression: bool,
) -> tuple[str, str]:
    """Determine priority and cadence from multi-signal inputs."""
    if drifted_count >= CRITICAL_DRIFT_THRESHOLD or any_decayed:
        return PRIORITY_CRITICAL, CADENCE_IMMEDIATE

    if drifted_count >= WARNING_DRIFT_THRESHOLD or any_quality_regression:
        return PRIORITY_HIGH, CADENCE_NEXT_CYCLE

    if drifted_count > 0:
        return PRIORITY_MEDIUM, CADENCE_NEXT_DAY

    return PRIORITY_LOW, CADENCE_NONE


# ---------------------------------------------------------------------------
# RecalibrationTrigger
# ---------------------------------------------------------------------------


class RecalibrationTrigger:
    """Orchestrates multi-signal drift, decay, and quality evaluation.

    Evaluates whether the collected evidence warrants model recalibration.
    Combines signals from:
      - Feature drift reports (distribution shifts)
      - Calibration decay reports (ECE degradation)
      - Label quality reports (label stability)

    Typical usage::

        trigger = RecalibrationTrigger()
        decision = trigger.evaluate_triggers(
            drift=[drift_report_1, drift_report_2],
            decay=decay_report,
            quality=quality_report,
        )
        if decision.should_recalibrate:
            schedule_recalibration(decision.priority, decision.suggested_cadence)
    """

    def __init__(self, min_drifted_features: int = 1):
        """Initialize the trigger.

        Args:
            min_drifted_features: Minimum number of drifted features
                                  to contribute to recalibration signal.
        """
        self._min_drifted = min_drifted_features

    def evaluate_triggers(
        self,
        drift: DriftReport | Sequence[DriftReport] | None = None,
        decay: DecayReport | Sequence[DecayReport] | None = None,
        quality: LabelQualityReport | Sequence[LabelQualityReport] | None = None,
    ) -> TriggerDecision:
        """Evaluate all signals and produce a recalibration decision.

        Args:
            drift: Single or list of DriftReport from feature drift detection.
            decay: Single or list of DecayReport from calibration decay monitoring.
            quality: Single or list of LabelQualityReport from label quality monitoring.

        Returns:
            TriggerDecision with recalibration recommendation.
        """
        reasons: list[str] = []

        # Normalize inputs
        drift_reports = self._normalize_drift(drift)
        decay_reports = self._normalize_decay(decay)
        quality_reports = self._normalize_quality(quality)

        # Count drifted features
        drifted_features = [r for r in drift_reports if r.is_drifted]
        drifted_count = len(drifted_features)

        # Check any decay detected
        decayed = [r for r in decay_reports if r.is_decayed]
        any_decayed = len(decayed) > 0

        # Check any quality regression
        regressed = [r for r in quality_reports if r.regression_detected]
        any_quality_regression = len(regressed) > 0

        # Build reasons
        for r in drifted_features:
            reasons.append(f"Feature '{r.feature_name}' drifted (score={r.drift_score:.4f}, level={r.alert_level})")

        for r in decayed:
            reasons.append(
                f"Calibration decay detected: current ECE={r.current_ece:.4f} "
                f"vs baseline ECE={r.baseline_ece:.4f} (decay_score={r.decay_score:.2f})"
            )

        for r in regressed:
            reasons.append(
                f"Label quality regression: stability={r.stability_score:.3f}, "
                f"magnitude={r.magnitude:.4f}"
            )

        # Determine decision
        should_recalibrate = drifted_count >= self._min_drifted or any_decayed or any_quality_regression

        if not should_recalibrate:
            return TriggerDecision(
                should_recalibrate=False,
                reasons=["No significant drift, decay, or quality regression detected."],
                priority=PRIORITY_LOW,
                suggested_cadence=CADENCE_NONE,
                drift_report_count=len(drift_reports),
                drift_detected_count=drifted_count,
                decay_reports=decay_reports,
                quality_reports=quality_reports,
            )

        priority, cadence = _determine_priority_and_cadence(
            drifted_count, any_decayed, any_quality_regression,
        )

        return TriggerDecision(
            should_recalibrate=True,
            reasons=reasons,
            priority=priority,
            suggested_cadence=cadence,
            drift_report_count=len(drift_reports),
            drift_detected_count=drifted_count,
            decay_reports=decay_reports,
            quality_reports=quality_reports,
        )

    # ------------------------------------------------------------------
    # Normalization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_drift(drift: DriftReport | Sequence[DriftReport] | None) -> list[DriftReport]:
        if drift is None:
            return []
        if isinstance(drift, DriftReport):
            return [drift]
        return list(drift)

    @staticmethod
    def _normalize_decay(decay: DecayReport | Sequence[DecayReport] | None) -> list[DecayReport]:
        if decay is None:
            return []
        if isinstance(decay, DecayReport):
            return [decay]
        return list(decay)

    @staticmethod
    def _normalize_quality(quality: LabelQualityReport | Sequence[LabelQualityReport] | None) -> list[LabelQualityReport]:
        if quality is None:
            return []
        if isinstance(quality, LabelQualityReport):
            return [quality]
        return list(quality)
