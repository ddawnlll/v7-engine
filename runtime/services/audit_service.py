"""Build frozen analyzer audit payloads for persisted signals."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class AuditService:
    def build_audit_snapshot(
        self,
        signal: dict[str, Any],
        snap: dict[str, Any],
        learning_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        advanced = dict(signal.get("advanced_analysis") or {})
        decision_path = dict(advanced.get("decision_path") or {})
        probability_model = dict(advanced.get("probability_model") or {})
        component_scores = dict(probability_model.get("component_scores") or {})
        learning_adjustments = dict(advanced.get("learning_adjustments") or {})
        circuit_breaker = dict(advanced.get("circuit_breaker") or {})
        mode = str(signal.get("mode") or "")

        threshold_checks = [
            self._check("min_confidence", (advanced.get("mode_thresholds") or {}).get("min_confidence"), signal.get("confidence"), signal.get("direction") != "NEUTRAL"),
            self._check("min_rr", (advanced.get("mode_thresholds") or {}).get("min_rr"), signal.get("risk_reward"), signal.get("risk_reward") is None or signal.get("direction") == "NEUTRAL" or float(signal.get("risk_reward") or 0.0) >= float((advanced.get("mode_thresholds") or {}).get("min_rr") or 0.0)),
            self._check("min_ev", (advanced.get("mode_thresholds") or {}).get("min_expected_value_r"), signal.get("expected_value"), signal.get("expected_value") is None or signal.get("direction") == "NEUTRAL" or float(signal.get("expected_value") or 0.0) >= float((advanced.get("mode_thresholds") or {}).get("min_expected_value_r") or 0.0)),
        ]

        factor_scores = {}
        for factor in signal.get("factors") or []:
            key = f"{str(factor.get('name') or 'factor').lower().replace(' ', '_')}_score"
            factor_scores[key] = factor.get("score")

        applied_adjustments = []
        calibration_mode = str(learning_adjustments.get("calibration_mode") or "ACTIVE")
        if calibration_mode != "ACTIVE":
            applied_adjustments.append({"source": "confidence_calibration_disabled", "multiplier": 1.0, "reason": f"Calibration bypassed: {calibration_mode}."})
        elif abs(float(learning_adjustments.get("calibration_multiplier") or 1.0) - 1.0) >= 0.01:
            applied_adjustments.append({"source": "confidence_calibration", "multiplier": learning_adjustments.get("calibration_multiplier"), "reason": "Calibrated from realized outcomes."})
        if float(learning_adjustments.get("entry_penalty") or 0.0) > 0.0:
            applied_adjustments.append({"source": "entry_timing_penalty", "multiplier": round(1.0 - float(learning_adjustments.get("entry_penalty") or 0.0), 4), "reason": "; ".join(learning_adjustments.get("reasons") or ["Entry timing penalty applied."])})
        if mode != "SWING" and float(learning_adjustments.get("component_penalty") or 0.0) > 0.0:
            applied_adjustments.append({"source": "component_penalty", "multiplier": round(1.0 - float(learning_adjustments.get("component_penalty") or 0.0), 4), "reason": f"Applied components: {', '.join(learning_adjustments.get('applied_components') or []) or 'n/a'}"})
        if float(learning_adjustments.get("execution_penalty") or 0.0) > 0.0:
            applied_adjustments.append({"source": "execution_penalty", "multiplier": round(1.0 - float(learning_adjustments.get("execution_penalty") or 0.0), 4), "reason": "; ".join(learning_adjustments.get("reasons") or ["Execution penalty applied."])})
        if float(learning_adjustments.get("stop_loss_multiplier") or 1.0) > 1.0:
            applied_adjustments.append({"source": "adaptive_stop", "multiplier": learning_adjustments.get("stop_loss_multiplier"), "reason": "Adaptive stop multiplier active."})
        if circuit_breaker.get("status") == "DEGRADED":
            applied_adjustments.append({"source": "circuit_breaker_degraded", "multiplier": circuit_breaker.get("multiplier"), "reason": circuit_breaker.get("reason")})

        return {
            "signal_id": signal.get("signal_id"),
            "captured_at": _utc_now_iso(),
            "mode": signal.get("mode"),
            "regime": signal.get("regime"),
            "trend": signal.get("trend"),
            "session_label": advanced.get("session_label"),
            "circuit_breaker_state": circuit_breaker.get("status") or "CLOSED",
            "factor_scores": factor_scores,
            "threshold_checks": threshold_checks,
            "probability_components": {
                "factor_edge": component_scores.get("factor_edge"),
                "return_edge": component_scores.get("distribution_edge"),
                "volatility_edge": component_scores.get("volatility_edge"),
                "microstructure_edge": component_scores.get("microstructure_edge"),
            },
            "learning_adjustments_applied": applied_adjustments,
            "confidence_before_learning": decision_path.get("confidence_raw"),
            "confidence_after_learning": decision_path.get("confidence_final") or signal.get("confidence"),
            "confidence_model_raw": decision_path.get("confidence_raw"),
            "confidence_post_learning": decision_path.get("confidence_final") or signal.get("confidence"),
            "confidence_post_execution": None,
            "entry_price": signal.get("entry_price"),
            "entry_zone_low": signal.get("entry_zone_low"),
            "entry_zone_high": signal.get("entry_zone_high"),
            "stop_loss": signal.get("stop_loss"),
            "take_profit": signal.get("take_profit"),
            "risk_reward": signal.get("risk_reward"),
            "expected_value": signal.get("expected_value"),
            "probability_before_learning": decision_path.get("probability_raw"),
            "probability_after_learning": decision_path.get("probability_final") or signal.get("probability"),
            "probability_model_raw": decision_path.get("probability_raw"),
            "probability_post_learning": decision_path.get("probability_final") or signal.get("probability"),
            "probability_post_execution": None,
            "execution_quality_multiplier": decision_path.get("quality_multiplier"),
            "calibration_state": calibration_mode,
            "stop_model": dict(advanced.get("stop_model") or {}),
            "timing_model": dict(advanced.get("timing_model") or {}),
            "confirmation": dict(advanced.get("confirmation") or {}),
            "regime_policy": dict(advanced.get("regime_policy") or {}),
            "learning_profile": learning_profile or {},
            "raw_snapshot": {
                "price": snap.get("price"),
                "regime_detail": snap.get("regime_detail"),
                "vol_ratio": snap.get("vol_ratio"),
                "atr": snap.get("atr"),
                "bb_width": snap.get("bb_width"),
            },
        }

    @staticmethod
    def _check(name: str, threshold: Any, value: Any, passed: bool) -> dict[str, Any]:
        return {
            "name": name,
            "threshold": _as_float(threshold, threshold),
            "value": _as_float(value, value),
            "passed": bool(passed),
        }
