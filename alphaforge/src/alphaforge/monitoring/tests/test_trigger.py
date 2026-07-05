"""Tests for alphaforge.monitoring.trigger."""

from __future__ import annotations

from alphaforge.monitoring.calibration_decay import DecayReport
from alphaforge.monitoring.feature_drift import DriftReport
from alphaforge.monitoring.label_quality import LabelQualityReport
from alphaforge.monitoring.trigger import (
    CADENCE_IMMEDIATE,
    CADENCE_NEXT_CYCLE,
    CADENCE_NEXT_WEEK,
    CADENCE_NONE,
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    RecalibrationTrigger,
    TriggerDecision,
)


class TestRecalibrationTrigger:
    def test_no_signals_returns_no_calibration(self):
        trigger = RecalibrationTrigger()
        decision = trigger.evaluate_triggers()
        assert isinstance(decision, TriggerDecision)
        assert not decision.should_recalibrate
        assert decision.priority == PRIORITY_LOW
        assert decision.suggested_cadence == CADENCE_NONE

    def test_drift_triggers_recalibration(self):
        trigger = RecalibrationTrigger()
        drift = DriftReport(
            feature_name="rsi_4h",
            drift_score=0.35,
            is_drifted=True,
            alert_level="CRITICAL",
        )
        decision = trigger.evaluate_triggers(drift=drift)
        assert decision.should_recalibrate
        assert len(decision.reasons) >= 1
        assert "drifted" in decision.reasons[0]

    def test_decay_triggers_recalibration(self):
        trigger = RecalibrationTrigger()
        decay = DecayReport(
            current_ece=0.15,
            baseline_ece=0.05,
            decay_score=3.0,
            is_decayed=True,
            n_current=100,
            n_baseline=100,
        )
        decision = trigger.evaluate_triggers(decay=decay)
        assert decision.should_recalibrate
        assert any("decay" in r for r in decision.reasons)

    def test_quality_regression_triggers_recalibration(self):
        trigger = RecalibrationTrigger()
        quality = LabelQualityReport(
            stability_score=0.45,
            regression_detected=True,
            magnitude=0.55,
            n_current=100,
            n_reference=100,
            current_mean=2.5,
            reference_mean=1.0,
        )
        decision = trigger.evaluate_triggers(quality=quality)
        assert decision.should_recalibrate
        assert any("quality" in r for r in decision.reasons)

    def test_multiple_drift_features(self):
        trigger = RecalibrationTrigger()
        drifts = [
            DriftReport(f"feat_{i}", drift_score=0.3, is_drifted=True, alert_level="WARNING")
            for i in range(5)
        ]
        decision = trigger.evaluate_triggers(drift=drifts)
        assert decision.should_recalibrate
        assert decision.drift_report_count == 5
        assert decision.drift_detected_count == 5
        assert decision.priority == PRIORITY_CRITICAL
        assert decision.suggested_cadence == CADENCE_IMMEDIATE

    def test_combined_signals_escalate_priority(self):
        trigger = RecalibrationTrigger()
        drift = DriftReport("feat_a", drift_score=0.2, is_drifted=True, alert_level="WARNING")
        decay = DecayReport(
            current_ece=0.12, baseline_ece=0.04, decay_score=3.0,
            is_decayed=True, n_current=100, n_baseline=100,
        )
        decision = trigger.evaluate_triggers(drift=drift, decay=decay)
        assert decision.priority == PRIORITY_CRITICAL

    def test_drift_and_regression_triggers(self):
        trigger = RecalibrationTrigger()
        drift = DriftReport("feat_b", drift_score=0.15, is_drifted=True, alert_level="WARNING")
        quality = LabelQualityReport(
            stability_score=0.6, regression_detected=True, magnitude=0.4,
            n_current=50, n_reference=50, current_mean=1.5, reference_mean=1.0,
        )
        decision = trigger.evaluate_triggers(drift=drift, quality=quality)
        assert decision.should_recalibrate
        assert decision.priority == PRIORITY_HIGH
        assert decision.suggested_cadence == CADENCE_NEXT_CYCLE

    def test_min_drifted_features_gates_drift_only(self):
        trigger = RecalibrationTrigger(min_drifted_features=3)
        drift = DriftReport("feat_c", drift_score=0.2, is_drifted=True, alert_level="WARNING")
        decision = trigger.evaluate_triggers(drift=drift)
        # With min_drifted_features=3 and only 1 drifted feature,
        # drift alone does not trigger. Decay or quality independently would.
        assert not decision.should_recalibrate
        assert decision.drift_detected_count == 1

    def test_reasons_list_includes_all_signals(self):
        trigger = RecalibrationTrigger()
        drift = DriftReport("feat_x", drift_score=0.4, is_drifted=True, alert_level="CRITICAL")
        decay = DecayReport(
            current_ece=0.2, baseline_ece=0.05, decay_score=4.0,
            is_decayed=True, n_current=100, n_baseline=100,
        )
        quality = LabelQualityReport(
            stability_score=0.3, regression_detected=True, magnitude=0.7,
            n_current=50, n_reference=50, current_mean=2.0, reference_mean=1.0,
        )
        decision = trigger.evaluate_triggers(drift=drift, decay=decay, quality=quality)
        assert len(decision.reasons) >= 3

    def test_no_signals_with_non_drifted_features(self):
        trigger = RecalibrationTrigger()
        drift = DriftReport("feat_y", drift_score=0.02, is_drifted=False, alert_level="NONE")
        decision = trigger.evaluate_triggers(drift=drift)
        assert not decision.should_recalibrate
        assert decision.drift_detected_count == 0

    def test_trigger_decision_dataclass(self):
        decision = TriggerDecision(
            should_recalibrate=True,
            reasons=["Feature 'rsi' drifted"],
            priority=PRIORITY_HIGH,
            suggested_cadence=CADENCE_NEXT_CYCLE,
            drift_report_count=1,
            drift_detected_count=1,
        )
        assert decision.should_recalibrate
        assert decision.priority == PRIORITY_HIGH
        assert decision.suggested_cadence == CADENCE_NEXT_CYCLE
