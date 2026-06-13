"""Canonical analytics-engine component registry."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from runtime.db.models import AnalyticsComponentRegistry
from runtime.db.repos._helpers import dumps_json, loads_json
from runtime.db.session import session_scope


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


REGISTRY: dict[str, dict[str, Any]] = {}


def register_component(definition: dict[str, Any]) -> dict[str, Any]:
    payload = dict(definition)
    payload.setdefault("introduced_at_utc", _utc_now_iso())
    payload.setdefault("created_at_utc", _utc_now_iso())
    payload.setdefault("updated_at_utc", _utc_now_iso())
    payload.setdefault("status", "ACTIVE")
    payload.setdefault("owner", "engine")
    payload.setdefault("default_params", {})
    payload.setdefault("ui_label", payload.get("component_name"))
    fingerprint_source = f"{payload.get('module_path','')}::{payload.get('object_name','')}::{payload.get('version','')}"
    payload.setdefault("implementation_fingerprint", hashlib.sha1(fingerprint_source.encode("utf-8")).hexdigest()[:12])
    REGISTRY[str(payload["component_id"])] = payload
    return payload


DEFAULT_COMPONENTS = [
    {"component_id": "regime_detector", "component_type": "regime_detector", "component_name": "Regime Detector", "version": "v1", "description": "Classifies high-level market regime before scoring.", "module_path": "v4.services.analyzer_factors", "object_name": "_detect_regime"},
    {"component_id": "trend_detector", "component_type": "scorer", "component_name": "Trend Detector", "version": "v1", "description": "Builds directional trend bias and strength.", "module_path": "v4.services.analyzer_factors", "object_name": "_determine_trend"},
    {"component_id": "structure_filter", "component_type": "filter", "component_name": "Structure Filter", "version": "v1", "description": "Rejects poor market structure and chop.", "module_path": "v4.services.analyzer_factors", "object_name": "_score_structure"},
    {"component_id": "oscillator_gate", "component_type": "filter", "component_name": "Oscillator Gate", "version": "v1", "description": "Requires oscillator alignment for entries.", "module_path": "v4.services.analyzer_core", "object_name": "analyze"},
    {"component_id": "probability_model", "component_type": "scorer", "component_name": "Probability Model", "version": "v1", "description": "Combines factors into directional probability.", "module_path": "v4.services.analyzer_probability", "object_name": "_calculate_probability"},
    {"component_id": "volume_context", "component_type": "feature_transform", "component_name": "Volume Context", "version": "v1", "description": "Adds volume and flow context to entry quality.", "module_path": "v4.services.analyzer_helpers", "object_name": "_enhanced_volume_context_factor"},
    {"component_id": "session_context", "component_type": "feature_transform", "component_name": "Session Context", "version": "v1", "description": "Session-based quality multiplier.", "module_path": "v4.services.analyzer_helpers", "object_name": "_session_multiplier"},
    {"component_id": "htf_alignment", "component_type": "filter", "component_name": "Higher Timeframe Alignment", "version": "v1", "description": "Adjusts confidence using higher timeframe trend.", "module_path": "v4.services.analyzer_core", "object_name": "analyze"},
    {"component_id": "learning_calibration", "component_type": "confidence_calibrator", "component_name": "Learning Calibration", "version": "v1", "description": "Calibrates confidence using realized outcomes.", "module_path": "v4.services.learning_service", "object_name": "resolve_trade_adjustments"},
    {"component_id": "entry_timing_penalty", "component_type": "penalty", "component_name": "Entry Timing Penalty", "version": "v1", "description": "Penalizes stretched early entries.", "module_path": "v4.services.learning_service", "object_name": "resolve_trade_adjustments"},
    {"component_id": "component_penalty", "component_type": "penalty", "component_name": "Component Penalty", "version": "v1", "description": "Penalizes failure-prone components.", "module_path": "v4.services.learning_service", "object_name": "resolve_trade_adjustments"},
    {"component_id": "execution_penalty", "component_type": "penalty", "component_name": "Execution Penalty", "version": "v1", "description": "Applies execution-quality penalties after raw edge is found.", "module_path": "v4.services.learning_service", "object_name": "resolve_trade_adjustments"},
    {"component_id": "adaptive_stop", "component_type": "risk_modifier", "component_name": "Adaptive Stop", "version": "v1", "description": "Adjusts stop sizing from learning feedback.", "module_path": "v4.services.learning_service", "object_name": "resolve_trade_adjustments"},
    {"component_id": "circuit_breaker", "component_type": "risk_modifier", "component_name": "Circuit Breaker", "version": "v1", "description": "Blocks or degrades trading during hostile conditions.", "module_path": "v4.services.circuit_breaker_service", "object_name": "evaluate_circuit_state"},
    {"component_id": "audit_snapshot", "component_type": "exit_helper", "component_name": "Audit Snapshot", "version": "v1", "description": "Freezes audit details for signal replay.", "module_path": "v4.services.audit_service", "object_name": "build_audit_snapshot"},
    {"component_id": "failure_classifier", "component_type": "exit_helper", "component_name": "Failure Classifier", "version": "v1", "description": "Classifies losing trades after close.", "module_path": "v4.services.failure_classifier", "object_name": "classify"},
    {"component_id": "self_learning_shadow", "component_type": "experimental", "component_name": "Self-Learning Shadow", "version": "v1", "status": "EXPERIMENTAL", "description": "Advisory-only shadow policy recommendations.", "module_path": "v4.services.shadow_policy_service", "object_name": "evaluate_shadow_actions"},
]

for _definition in DEFAULT_COMPONENTS:
    register_component(_definition)


class ImprovementRegistryService:
    def sync_registry(self) -> list[dict[str, Any]]:
        with session_scope() as session:
            return [self._upsert(session, payload) for payload in REGISTRY.values()]

    def list_components(self, *, status: str | None = None, component_type: str | None = None) -> list[dict[str, Any]]:
        self.sync_registry()
        with session_scope() as session:
            query = session.query(AnalyticsComponentRegistry)
            if status:
                query = query.filter(AnalyticsComponentRegistry.status == status)
            if component_type:
                query = query.filter(AnalyticsComponentRegistry.component_type == component_type)
            rows = query.order_by(AnalyticsComponentRegistry.component_type.asc(), AnalyticsComponentRegistry.component_name.asc()).all()
            return [self._to_dict(row) for row in rows]

    def get_component(self, component_id: str) -> dict[str, Any] | None:
        self.sync_registry()
        with session_scope() as session:
            row = session.query(AnalyticsComponentRegistry).filter(AnalyticsComponentRegistry.component_id == component_id).one_or_none()
            return self._to_dict(row) if row else None

    def enabled_component_ids(self) -> list[str]:
        return sorted(component_id for component_id, payload in REGISTRY.items() if str(payload.get("status") or "ACTIVE") not in {"PAUSED", "ROLLED_BACK", "DEPRECATED"})

    def disabled_component_ids(self) -> list[str]:
        return sorted(component_id for component_id, payload in REGISTRY.items() if str(payload.get("status") or "ACTIVE") in {"PAUSED", "ROLLED_BACK", "DEPRECATED"})

    def _upsert(self, session: Session, payload: dict[str, Any]) -> dict[str, Any]:
        now = _utc_now_iso()
        row = session.query(AnalyticsComponentRegistry).filter(AnalyticsComponentRegistry.component_id == payload["component_id"]).one_or_none()
        stored = {
            "component_id": payload["component_id"],
            "component_type": payload["component_type"],
            "component_name": payload["component_name"],
            "version": payload["version"],
            "status": payload.get("status", "ACTIVE"),
            "owner": payload.get("owner", "engine"),
            "description": payload.get("description", ""),
            "default_params_json": dumps_json(payload.get("default_params") or {}),
            "ui_label": payload.get("ui_label") or payload["component_name"],
            "module_path": payload.get("module_path", ""),
            "object_name": payload.get("object_name", ""),
            "implementation_fingerprint": payload.get("implementation_fingerprint"),
            "introduced_at_utc": payload.get("introduced_at_utc") or now,
            "deprecated_at_utc": payload.get("deprecated_at_utc"),
            "created_at_utc": payload.get("created_at_utc") or now,
            "updated_at_utc": now,
        }
        if row is None:
            row = AnalyticsComponentRegistry(**stored)
            session.add(row)
        else:
            for key, value in stored.items():
                setattr(row, key, value)
        session.commit()
        return self._to_dict(row)

    @staticmethod
    def _to_dict(row: AnalyticsComponentRegistry) -> dict[str, Any]:
        return {
            "id": row.id,
            "component_id": row.component_id,
            "component_type": row.component_type,
            "component_name": row.component_name,
            "version": row.version,
            "status": row.status,
            "owner": row.owner,
            "description": row.description,
            "default_params": loads_json(row.default_params_json, {}),
            "ui_label": row.ui_label,
            "module_path": row.module_path,
            "object_name": row.object_name,
            "implementation_fingerprint": row.implementation_fingerprint,
            "introduced_at_utc": row.introduced_at_utc,
            "deprecated_at_utc": row.deprecated_at_utc,
            "created_at_utc": row.created_at_utc,
            "updated_at_utc": row.updated_at_utc,
        }
