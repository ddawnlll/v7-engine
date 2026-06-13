"""Internal analyzer-engine compatibility and normalization boundary.

This adapter keeps the public runtime API engine-agnostic.
HTTP routes should call stable runtime services and consume normalized payloads
from this adapter rather than binding to engine-generation-specific contracts
or public route namespaces.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from runtime.db.repos.shadow_policy_repo import ShadowPolicyRepository
from runtime.db.repos.state_repo import StateRepository
from runtime.db.repos.settings_repo import SettingsRepository
from runtime.db.session import session_scope
from runtime.services.analyzer_engine_contract import (
    AnalysisRequest,
    AnalysisResult,
    REQUEST_SCHEMA_VERSION,
    RESPONSE_SCHEMA_VERSION,
)
from runtime.services.analyzer_engine_registry_service import AnalyzerEngineRegistryService
from v6.config import V6Config
from v6.contracts.analysis_request import AnalysisRequest as V6Request
from v6.contracts.analysis_result import AnalysisResult as V6AnalysisResult
from v6.contracts.analysis_result import AnalysisResultValidationError
from v6.contracts.compat import from_legacy_request, from_v5_result, is_legacy_result
from v6.contracts.decision_event import DecisionEvent, DecisionEventValidationError
from v6.contracts.enums import ExecutionPath
from v6.engine import EngineManager

log = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_blank(value: Any) -> bool:
    return value is None or not str(value).strip()


def _looks_machine_generated_summary(value: str | None) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True
    machine_markers = ("scores(", "thresholds(", "path=", "winner=", "safe_fallback:")
    return any(marker in text for marker in machine_markers) or ";" in text


def _format_expected_duration(expected_hold_time: float | None) -> str | None:
    if expected_hold_time is None:
        return None
    rounded = int(round(float(expected_hold_time)))
    if rounded <= 0:
        return None
    unit = "bar" if rounded == 1 else "bars"
    return f"~{rounded} {unit}"


def _format_recommended_size(size_multiplier: float | None) -> str | None:
    if size_multiplier is None:
        return None
    percent = round(float(size_multiplier) * 100.0)
    return f"{percent}% base risk"


def _display_regime(v6_request, request: AnalysisRequest | V6Request) -> str:
    snapshot = dict(getattr(request, "snapshot", None) or {})
    market_context = dict(getattr(request, "market_context", None) or {})
    candidates = (
        getattr(v6_request.deterministic_context, "regime_label", None),
        snapshot.get("regime"),
        snapshot.get("market_state"),
        market_context.get("regime"),
        market_context.get("regime_label"),
    )
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text and text.upper() not in {"UNKNOWN", "NONE", "NULL"}:
            return text.upper()
    trend_candidates = (
        snapshot.get("trend"),
        snapshot.get("htf_trend"),
        market_context.get("trend"),
    )
    if any(str(candidate or "").upper() in {"BUY", "SELL", "BULLISH", "BEARISH"} for candidate in trend_candidates):
        return "TRENDING"
    return "UNCLASSIFIED"


def _regime_detail(v6_request, response: V6AnalysisResult) -> str | None:
    for candidate in (
        getattr(v6_request.deterministic_context, "deterministic_summary", None),
        response.deterministic_interaction.deterministic_warning,
        response.deterministic_interaction.deterministic_disagreement_reason,
        response.deterministic_interaction.regime_transition_risk,
    ):
        if not _is_blank(candidate):
            return str(candidate)
    return None


def _human_summary(response: V6AnalysisResult, *, regime: str, direction: str) -> str:
    decision_summary = response.decision.decision_summary
    if not _looks_machine_generated_summary(decision_summary):
        return str(decision_summary)

    reason_summary = response.observability.reason_summary
    if not _looks_machine_generated_summary(reason_summary):
        return str(reason_summary)

    confidence = response.scores.confidence * 100.0 if response.scores.confidence <= 1.0 else response.scores.confidence
    confidence_text = f"{round(float(confidence))}% confidence"
    if response.fallback_degradation.fallback_used:
        reason = str(response.fallback_degradation.fallback_reason or response.fallback_degradation.degraded_reason or "fallback")
        return f"Degraded analysis in {regime}: {reason.replace('_', ' ').lower()}."
    if direction in {"BUY", "SELL"}:
        rr = response.scores.risk_reward_estimate
        rr_text = f" Targeting {float(rr):.2f}R." if rr is not None else ""
        return f"{direction} setup in {regime} with {confidence_text}.{rr_text}".strip()
    return f"No-trade bias in {regime} with {confidence_text}."


def _percent_confidence(score: float) -> float:
    return score * 100.0 if score <= 1.0 else score


class AnalyzerEngineAdapter:
    _STATUS_WRITE_INTERVAL_SECONDS = 30.0
    _SETTINGS_CACHE_TTL_SECONDS = 10.0

    def __init__(
        self,
        registry_service: AnalyzerEngineRegistryService | None = None,
        settings_repo: SettingsRepository | None = None,
        state_repo: StateRepository | None = None,
        shadow_repo: ShadowPolicyRepository | None = None,
    ) -> None:
        self._uses_default_registry_service = registry_service is None
        self.registry_service = registry_service or AnalyzerEngineRegistryService()
        self.settings_repo = settings_repo or SettingsRepository()
        self.state_repo = state_repo or StateRepository()
        self.shadow_repo = shadow_repo or ShadowPolicyRepository()
        self._last_success_recorded_at = 0.0
        self._timeout_cache: tuple[float, float] | None = None
        self._settings_cache: tuple[float, dict[str, str]] | None = None
        self._lock = Lock()
        self.v6_config = V6Config.load(Path("config/v6_config_defaults.json")) if Path("config/v6_config_defaults.json").exists() else V6Config.defaults()
        try:
            from v6.registry.model_registry import ModelRegistry
            self.engine_manager = EngineManager(ModelRegistry(), self.v6_config) if self._uses_default_registry_service else None
        except Exception:
            self.engine_manager = None

    def build_request(
        self,
        *,
        symbol: str,
        interval: str,
        mode: str,
        snapshot: dict[str, Any],
        market_context: dict[str, Any] | None = None,
        runtime_context: dict[str, Any] | None = None,
        request_id: str | None = None,
        timestamp: str | None = None,
    ) -> AnalysisRequest:
        normalized_snapshot = dict(snapshot or {})
        request = AnalysisRequest(
            request_id=request_id or f"anreq-{uuid.uuid4().hex[:12]}",
            symbol=str(symbol or "").upper(),
            interval=str(interval or ""),
            mode=str(mode or "").upper(),
            timestamp=str(timestamp or _utc_now_iso()),
            snapshot=normalized_snapshot,
            market_context=dict(market_context or {}),
            runtime_context=dict(runtime_context or {}),
            schema_version=REQUEST_SCHEMA_VERSION,
        )
        self._validate_request_v6(request)
        return request

    def analyze(
        self,
        *,
        symbol: str,
        interval: str,
        mode: str,
        snapshot: dict[str, Any],
        market_context: dict[str, Any] | None = None,
        runtime_context: dict[str, Any] | None = None,
        request_id: str | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        request = self.build_request(
            symbol=symbol,
            interval=interval,
            mode=mode,
            snapshot=snapshot,
            market_context=market_context,
            runtime_context=runtime_context,
            request_id=request_id,
            timestamp=timestamp,
        )
        return self.analyze_request(request)

    def analyze_request(self, request: AnalysisRequest) -> dict[str, Any]:
        started = time.perf_counter()
        v6_request = self._validate_request_v6(request)
        comparison_group_id = f"{v6_request.scope.symbol}_{v6_request.scope.interval}_{v6_request.identity.timestamp_utc}"
        engine_lookup_started = time.perf_counter()
        if self.engine_manager is not None:
            self.engine_manager.check_health()
            engine = self.engine_manager.get_primary_engine()
            shadow_engine = self.engine_manager.get_shadow_engine()
            engine_name = getattr(engine, "engine_name", getattr(engine, "name", "unknown"))
            shadow_name = getattr(shadow_engine, "engine_name", None) if shadow_engine is not None else None
        else:
            engine_name = self.registry_service.active_engine_name()
            engine = self.registry_service.get_engine(engine_name)
            shadow_name_getter = getattr(self.registry_service, "shadow_engine_name", None)
            shadow_name = shadow_name_getter() if callable(shadow_name_getter) else None
            shadow_engine = None
        engine_lookup_ms = round((time.perf_counter() - engine_lookup_started) * 1000.0, 4)

        if engine is None:
            fallback = self._fallback_result(v6_request, engine_name=engine_name, reason=f"UNKNOWN_ENGINE_{engine_name.upper()}")
            event = self._build_decision_event(v6_request, fallback)
            payload = self._result_payload(request, v6_request, fallback, event)
            payload["adapter_metrics"] = {
                "adapter_total_ms": round((time.perf_counter() - started) * 1000.0, 4),
                "engine_lookup_ms": engine_lookup_ms,
                "engine_analyze_ms": None,
                "response_validation_ms": None,
                "timeout_lookup_ms": None,
                "status_persist_ms": self._record_failure(payload, last_error="unknown engine"),
                "status_written": True,
            }
            return payload

        last_error: str | None = None
        shadow_elapsed_ms = None

        try:
            engine_started = time.perf_counter()
            response = engine.infer(v6_request) if hasattr(engine, "infer") else engine.analyze(request)
            engine_analyze_ms = round((time.perf_counter() - engine_started) * 1000.0, 4)
            validation_started = time.perf_counter()
            validated = self._validate_result_v6(response=response, request=v6_request, engine_name=engine_name)
            validation_ms = round((time.perf_counter() - validation_started) * 1000.0, 4)
            timeout_lookup_started = time.perf_counter()
            timeout_ms = self._timeout_ms(engine_name)
            timeout_lookup_ms = round((time.perf_counter() - timeout_lookup_started) * 1000.0, 4)
            if (validated.observability.analysis_latency_ms or 0.0) > timeout_ms:
                raise TimeoutError(f"Engine response exceeded timeout {timeout_ms}ms")

            event = self._build_decision_event(v6_request, validated)
            event.identity.comparison_group_id = comparison_group_id
            payload = self._result_payload(request, v6_request, validated, event)
            status_persist_ms, status_written = self._record_success(payload)

            if shadow_name and shadow_name != engine_name:
                shadow_started = time.perf_counter()
                if shadow_engine is not None and hasattr(shadow_engine, "infer"):
                    shadow_result = shadow_engine.infer(v6_request, shadow=True)
                    shadow_event = self._build_decision_event(v6_request, shadow_result)
                    shadow_event.identity.comparison_group_id = comparison_group_id
                    shadow_event.decision_summary.is_actionable = False
                else:
                    self._execute_and_persist_shadow(request, v6_request, shadow_name, validated)
                shadow_elapsed_ms = round((time.perf_counter() - shadow_started) * 1000.0, 4)

            payload["adapter_metrics"] = {
                "adapter_total_ms": round((time.perf_counter() - started) * 1000.0, 4),
                "engine_lookup_ms": engine_lookup_ms,
                "engine_analyze_ms": engine_analyze_ms,
                "response_validation_ms": validation_ms,
                "timeout_lookup_ms": timeout_lookup_ms,
                "status_persist_ms": status_persist_ms,
                "status_written": status_written,
                "shadow_execution_ms": shadow_elapsed_ms,
            }
            return payload
        except Exception as exc:
            last_error = str(exc)
            fallback_reason = self._classify_fallback_reason(exc)
            log.warning("analyzer adapter fallback: engine=%s reason=%s error=%s", engine_name, fallback_reason, last_error)
            fallback = self._fallback_result(v6_request, engine_name=engine_name, reason=fallback_reason)
            event = self._build_decision_event(v6_request, fallback)
            event.identity.comparison_group_id = comparison_group_id
            payload = self._result_payload(request, v6_request, fallback, event)
            payload["fallback_used"] = True
            payload["warnings"] = [*list(payload.get("warnings") or []), last_error]
            payload["fallback_reason"] = fallback_reason
            status_persist_ms = self._record_failure(payload, last_error=last_error)
            payload["adapter_metrics"] = {
                "adapter_total_ms": round((time.perf_counter() - started) * 1000.0, 4),
                "engine_lookup_ms": engine_lookup_ms,
                "engine_analyze_ms": None,
                "response_validation_ms": None,
                "timeout_lookup_ms": None,
                "status_persist_ms": status_persist_ms,
                "status_written": True,
            }
            return payload

    def _validate_request_v6(self, request: AnalysisRequest | V6Request):
        if isinstance(request, V6Request):
            return request.validate()
        model_dump = getattr(request, "model_dump", None)
        if callable(model_dump):
            payload = model_dump()
        else:
            payload = request.dict() if hasattr(request, "dict") and callable(getattr(request, "dict")) else request
        v6_request = from_legacy_request(payload)
        return v6_request.validate()

    def _validate_result_v6(self, *, response: Any, request, engine_name: str) -> V6AnalysisResult:
        if isinstance(response, V6AnalysisResult):
            return response.validate()
        if isinstance(response, AnalysisResult):
            response = response.model_dump()
        else:
            model_dump = getattr(response, "model_dump", None)
            if callable(model_dump):
                response = model_dump()
            elif hasattr(response, "dict") and callable(getattr(response, "dict")):
                response = response.dict()
        if isinstance(response, dict) and is_legacy_result(response):
            return from_v5_result(response, request).validate()
        if isinstance(response, dict):
            return V6AnalysisResult.from_dict(response).validate()
        raise AnalysisResultValidationError(f"Unsupported engine response type from {engine_name}: {type(response)!r}")

    def _build_decision_event(self, request, result: V6AnalysisResult) -> DecisionEvent:
        runtime_interpretation = {
            "execution_path": ExecutionPath.NOT_EVALUATED.value,
            "execution_decision": "NO_ACTION" if not result.status.is_actionable else "ACTIONABLE",
            "runtime_actionability": "ACTIONABLE" if result.status.is_actionable else "NO_ACTION",
            "should_persist_as_signal": result.status.is_actionable,
            "should_surface_to_review": True,
        }
        event = DecisionEvent.from_request_and_result(request, result, runtime_interpretation)
        return event.validate()

    def _execute_and_persist_shadow(self, request: AnalysisRequest, v6_request, shadow_name: str, primary_result: V6AnalysisResult) -> None:
        """Runs the shadow engine and saves the result to the Phase 24 table using payload JSON for extensions."""
        try:
            shadow_engine = self.registry_service.get_engine(shadow_name)
            shadow_resp = shadow_engine.analyze(request)
            shadow_result = self._validate_result_v6(response=shadow_resp, request=v6_request, engine_name=shadow_name)

            v4_dir = primary_result.decision.direction.value
            v5_dir = shadow_result.decision.direction.value
            agreement = v4_dir == v5_dir

            payload_data = {
                "v4_direction": v4_dir,
                "v4_confidence": primary_result.scores.confidence,
                "v4_probability": primary_result.scores.probability,
                "v5_direction": v5_dir,
                "v5_corrected_probability": shadow_result.scores.probability,
                "v5_recommended_action": shadow_result.decision.recommended_action.value,
                "v5_model_version": shadow_result.identity.model_artifact_version,
                "agreement": agreement,
                "realized_outcome": None,
                "delta_r_vs_v4": None,
            }

            from runtime.db.repos._helpers import dumps_json

            shadow_record = {
                "signal_id": primary_result.identity.request_id,
                "generated_at_utc": _utc_now_iso(),
                "recommended_action": shadow_result.decision.recommended_action.value,
                "support_samples": 0,
                "expected_reward": shadow_result.scores.expected_return,
                "uncertainty_score": shadow_result.uncertainty_quality.uncertainty_score or 0.0,
                "learning_regime": v6_request.deterministic_context.regime_label,
                "similar_case_count": 0,
                "reason_summary": shadow_result.observability.reason_summary or "",
                "payload_json": dumps_json(payload_data),
            }

            with session_scope() as session:
                self.shadow_repo.save_shadow_decision(session, shadow_record)

        except Exception as exc:
            log.warning("Shadow engine execution failed: %s", exc)

    # V6 uses LONG/SHORT/NONE internally; legacy runtime consumers expect BUY/SELL/NEUTRAL.
    _LEGACY_DIRECTION = {"LONG": "BUY", "SHORT": "SELL", "NONE": "NEUTRAL"}

    def _result_payload(self, request: AnalysisRequest, v6_request, response: V6AnalysisResult, event: DecisionEvent) -> dict[str, Any]:
        score_breakdown = dict(response.observability.score_breakdown or {})
        legacy_direction = self._LEGACY_DIRECTION.get(response.decision.direction.value, "NEUTRAL")
        confidence_raw_score = float(score_breakdown.get("confidence_raw", score_breakdown.get("selected_action_raw_score", response.scores.confidence)) or 0.0)
        confidence_raw = _percent_confidence(confidence_raw_score)
        confidence_final_score = float(score_breakdown.get("confidence_final", response.scores.confidence) or 0.0)
        confidence_final = _percent_confidence(confidence_final_score)
        probability_raw = float(score_breakdown.get("probability_raw", score_breakdown.get("selected_action_raw_probability", response.scores.probability)) or 0.0)
        probability_final = float(score_breakdown.get("probability_final", response.scores.probability) or 0.0)
        raw_head_scores = dict(score_breakdown.get("raw_head_scores") or {})
        calibrated_head_scores = dict(score_breakdown.get("calibrated_head_scores") or {})
        if legacy_direction in {"BUY", "SELL"} and not self._final_actionability_confidence_enabled():
            confidence_raw_score = float(score_breakdown.get("selected_action_raw_score", confidence_raw_score) or 0.0)
            confidence_final_score = float(score_breakdown.get("selected_action_calibrated_score", confidence_final_score) or 0.0)
            confidence_raw = _percent_confidence(confidence_raw_score)
            confidence_final = _percent_confidence(confidence_final_score)
            score_breakdown["confidence_raw"] = confidence_raw_score
            score_breakdown["confidence_final"] = confidence_final_score
            score_breakdown["confidence_kind"] = "selected_head_probability"
            score_breakdown["actionability_confidence_disabled"] = True
        regime_label = _display_regime(v6_request, request)
        regime_detail = _regime_detail(v6_request, response)
        summary_text = _human_summary(response, regime=regime_label, direction=legacy_direction)
        expected_duration = _format_expected_duration(response.scores.expected_hold_time)
        recommended_size = _format_recommended_size(response.execution_guidance.size_multiplier)
        entry_zone = list(response.execution_guidance.entry_zone or [])
        no_trade_reason = None
        if response.fallback_degradation.fallback_reason:
            no_trade_reason = response.fallback_degradation.fallback_reason
        elif response.status.signal_status.value in {"NO_TRADE", "FILTERED", "REJECTED", "DEGRADED", "ERROR"} or legacy_direction == "NEUTRAL":
            no_trade_reason = summary_text
        advanced_probability_model = {
            "component_scores": {
                "factor_edge": score_breakdown.get("directional_margin"),
                "return_edge": response.scores.expected_return,
                "volatility_edge": response.scores.expected_drawdown,
                "microstructure_edge": response.scores.risk_reward_estimate,
            },
            "raw_head_scores": raw_head_scores,
            "calibrated_head_scores": calibrated_head_scores,
            "score_breakdown": score_breakdown,
        }
        advanced_decision_path = {
            "confidence_raw": confidence_raw,
            "confidence_final": confidence_final,
            "confidence_kind": score_breakdown.get("confidence_kind"),
            "probability_raw": probability_raw,
            "probability_final": probability_final,
            "selected_head": score_breakdown.get("selected_head"),
            "selected_action": score_breakdown.get("selected_action"),
            "selected_action_raw_score": score_breakdown.get("selected_action_raw_score"),
            "selected_action_calibrated_score": score_breakdown.get("selected_action_calibrated_score"),
            "winner_head": score_breakdown.get("winner_head"),
            "winner_score": score_breakdown.get("winner_score"),
            "runner_up_head": score_breakdown.get("runner_up_head"),
            "runner_up_score": score_breakdown.get("runner_up_score"),
            "selected_vs_runner_up_gap": score_breakdown.get("selected_vs_runner_up_gap"),
            "selected_vs_no_trade_gap": score_breakdown.get("selected_vs_no_trade_gap"),
            "selected_vs_no_trade_gap_raw": score_breakdown.get("selected_vs_no_trade_gap_raw"),
            "selected_vs_no_trade_gap_compression_points": score_breakdown.get("selected_vs_no_trade_gap_compression_points"),
            "directional_margin": score_breakdown.get("directional_margin"),
            "directional_margin_raw": score_breakdown.get("directional_margin_raw"),
            "directional_margin_compression_points": score_breakdown.get("directional_margin_compression_points"),
            "selected_probability_compression_points": score_breakdown.get("selected_probability_compression_points"),
            "selected_probability_compression_ratio": score_breakdown.get("selected_probability_compression_ratio"),
            "decision_margin": score_breakdown.get("decision_margin"),
            "decision_margin_hit": score_breakdown.get("decision_margin_hit"),
            "no_trade_threshold_hit": score_breakdown.get("no_trade_threshold_hit"),
            "thresholds": score_breakdown.get("thresholds"),
            "calibration_scope": score_breakdown.get("calibration_scope"),
            "calibration_diagnostics": score_breakdown.get("calibration_diagnostics"),
            "deterministic_setup_score": score_breakdown.get("deterministic_setup_score"),
            "ml_conviction_score": score_breakdown.get("ml_conviction_score"),
            "final_hybrid_conviction": score_breakdown.get("final_hybrid_conviction"),
            "hybrid_gate_triggered": score_breakdown.get("hybrid_gate_triggered"),
            "hybrid_gate_reason": score_breakdown.get("hybrid_gate_reason"),
            "suppression": score_breakdown.get("suppression"),
        }
        request_symbol = getattr(request, "symbol", None) or getattr(getattr(request, "scope", None), "symbol", None)
        request_interval = getattr(request, "interval", None) or getattr(getattr(request, "scope", None), "interval", None)
        request_mode = getattr(request, "mode", None)
        if request_mode is None:
            scope_mode = getattr(getattr(request, "scope", None), "mode", None)
            request_mode = getattr(scope_mode, "value", scope_mode)
        request_dump_fn = getattr(request, "model_dump", None)
        if callable(request_dump_fn):
            serialized_request = request_dump_fn()
        elif hasattr(request, "dict") and callable(getattr(request, "dict")):
            serialized_request = request.dict()
        elif hasattr(request, "to_dict") and callable(getattr(request, "to_dict")):
            serialized_request = request.to_dict()
        else:
            serialized_request = {}
        signal = {
            "symbol": request_symbol,
            "interval": request_interval,
            "mode": request_mode,
            "direction": legacy_direction,
            "confidence": confidence_final,
            "confidence_raw": confidence_raw,
            "confidence_final": confidence_final,
            "probability": probability_final,
            "probability_raw": probability_raw,
            "probability_final": probability_final,
            "entry_price": response.execution_guidance.entry_price,
            "entry_zone_low": entry_zone[0] if len(entry_zone) >= 1 else None,
            "entry_zone_high": entry_zone[1] if len(entry_zone) >= 2 else None,
            "stop_loss": response.execution_guidance.stop_loss,
            "take_profit": response.execution_guidance.take_profit,
            "risk_reward": response.scores.risk_reward_estimate,
            "expected_value": response.scores.expected_return,
            "summary": summary_text,
            "regime": regime_label,
            "regime_detail": regime_detail,
            "trend": v6_request.htf_context.htf_bias,
            "trend_strength": v6_request.deterministic_context.trend_strength,
            "no_trade_reason": no_trade_reason,
            "expected_duration": expected_duration,
            "recommended_size": recommended_size,
            "advanced_analysis": {
                "adapter": {
                    "fallback_reason": response.fallback_degradation.fallback_reason,
                    "request_schema_version": REQUEST_SCHEMA_VERSION,
                    "response_schema_version": RESPONSE_SCHEMA_VERSION,
                    "v6_contract_version": response.contract.contract_version,
                    "reason_summary": response.observability.reason_summary,
                },
                "probability_model": advanced_probability_model,
                "decision_path": advanced_decision_path,
            },
            "adaptive_context": {},
            "factors": [],
        }
        payload = {
            "signal_status": response.status.signal_status.value,
            "direction": legacy_direction,
            "confidence": confidence_final,
            "confidence_raw": confidence_raw,
            "confidence_final": confidence_final,
            "probability": probability_final,
            "probability_raw": probability_raw,
            "probability_final": probability_final,
            "entry_price": response.execution_guidance.entry_price,
            "entry_zone_low": entry_zone[0] if len(entry_zone) >= 1 else None,
            "entry_zone_high": entry_zone[1] if len(entry_zone) >= 2 else None,
            "stop_loss": response.execution_guidance.stop_loss,
            "take_profit": response.execution_guidance.take_profit,
            "risk_reward": response.scores.risk_reward_estimate,
            "expected_value": response.scores.expected_return,
            "summary": summary_text,
            "regime": regime_label,
            "regime_detail": regime_detail,
            "no_trade_reason": no_trade_reason,
            "expected_duration": expected_duration,
            "recommended_size": recommended_size,
            "engine_name": response.identity.engine_name,
            "engine_version": response.identity.engine_version,
            "schema_version": response.contract.response_schema_version,
            "analysis_latency_ms": response.observability.analysis_latency_ms or 0.0,
            "fallback_used": bool(response.fallback_degradation.fallback_used),
            "fallback_reason": response.fallback_degradation.fallback_reason,
            "warnings": list(response.observability.warnings),
            "decision_payload": {"signal": signal},
            "request": serialized_request,
            "trusted_fields": [
                "signal_status",
                "direction",
                "confidence",
                "confidence_raw",
                "confidence_final",
                "probability",
                "probability_raw",
                "probability_final",
                "engine_name",
                "engine_version",
                "fallback_used",
            ],
            "signal": signal,
            "request_schema_version": REQUEST_SCHEMA_VERSION,
            "response_schema_version": RESPONSE_SCHEMA_VERSION,
            "engine_identity": {
                "engine_name": response.identity.engine_name,
                "engine_version": response.identity.engine_version,
                "schema_version": response.contract.response_schema_version,
                "fallback_used": bool(response.fallback_degradation.fallback_used),
            },
            "v6_request": v6_request.to_dict(),
            "v6_result": response.to_dict(),
            "decision_event": event.to_dict(),
        }
        return payload

    def _fallback_result(self, request, *, engine_name: str, reason: str) -> V6AnalysisResult:
        return V6AnalysisResult.make_safe_fallback(reason=reason, engine_name=engine_name, request_id=request.identity.request_id)

    def _record_success(self, payload: dict[str, Any]) -> tuple[float, bool]:
        now = time.time()
        with self._lock:
            if now - self._last_success_recorded_at < self._STATUS_WRITE_INTERVAL_SECONDS:
                return 0.0, False
        started = time.perf_counter()
        with session_scope() as session:
            current = self.state_repo.get(session, "analyzer_fallbacks", default={"count": 0, "recent": []})
            self.state_repo.set(session, "analyzer_status", {
                "active_engine": payload["engine_name"],
                "active_engine_version": payload["engine_version"],
                "request_schema_version": payload["request_schema_version"],
                "response_schema_version": payload["response_schema_version"],
                "last_engine_error": None,
                "last_fallback_reason": None,
                "fallback_count": int((current or {}).get("count") or 0),
                "last_analysis_at_utc": _utc_now_iso(),
            })
        with self._lock:
            self._last_success_recorded_at = now
        return round((time.perf_counter() - started) * 1000.0, 4), True

    def _record_failure(self, payload: dict[str, Any], *, last_error: str) -> float:
        started = time.perf_counter()
        with session_scope() as session:
            current = self.state_repo.get(session, "analyzer_fallbacks", default={"count": 0, "recent": []})
            recent = list((current or {}).get("recent") or [])
            recent.append({
                "timestamp": _utc_now_iso(),
                "engine_name": payload.get("engine_name"),
                "engine_version": payload.get("engine_version"),
                "reason": payload.get("fallback_reason"),
                "error": last_error,
            })
            fallback_count = int((current or {}).get("count") or 0) + 1
            self.state_repo.set(session, "analyzer_fallbacks", {
                "count": fallback_count,
                "recent": recent[-25:],
            })
            self.state_repo.set(session, "analyzer_status", {
                "active_engine": self.registry_service.active_engine_name(),
                "active_engine_version": payload.get("engine_version"),
                "request_schema_version": payload["request_schema_version"],
                "response_schema_version": payload["response_schema_version"],
                "last_engine_error": last_error,
                "last_fallback_reason": payload.get("fallback_reason"),
                "fallback_count": fallback_count,
                "last_analysis_at_utc": _utc_now_iso(),
            })
        return round((time.perf_counter() - started) * 1000.0, 4)

    def _timeout_ms(self, engine_name: str) -> float:
        settings = self._runtime_settings()
        try:
            val = max(50.0, float(settings.get("ANALYZER_ENGINE_TIMEOUT_MS") or 2500.0))
        except (TypeError, ValueError):
            val = 2500.0
        with self._lock:
            self._timeout_cache = (time.time(), val)

        if engine_name == "v5":
            return min(val, 500.0)
        return val

    def _runtime_settings(self) -> dict[str, str]:
        now = time.time()
        with self._lock:
            cached = self._settings_cache
        if cached and now - cached[0] < self._SETTINGS_CACHE_TTL_SECONDS:
            return dict(cached[1])
        with session_scope() as session:
            settings = self.settings_repo.get_all(session)
        with self._lock:
            self._settings_cache = (now, dict(settings))
        return dict(settings)

    def _final_actionability_confidence_enabled(self) -> bool:
        settings = self._runtime_settings()
        return str(settings.get("V6_ACTIONABILITY_CONFIDENCE_ENABLED", "true")).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _classify_fallback_reason(exc: Exception) -> str:
        if isinstance(exc, TimeoutError):
            return "ENGINE_TIMEOUT"
        if isinstance(exc, (ValueError, AnalysisResultValidationError, DecisionEventValidationError)):
            return "SCHEMA_VALIDATION_FAILURE"
        return "ENGINE_CRASH"
