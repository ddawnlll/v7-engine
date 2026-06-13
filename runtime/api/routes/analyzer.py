"""Analyzer engine status and fallback visibility routes."""

from __future__ import annotations

from fastapi import APIRouter

from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID

from runtime.db.repos.state_repo import StateRepository
from runtime.db.session import session_scope
from runtime.services.analyzer_engine_contract import REQUEST_SCHEMA_VERSION, RESPONSE_SCHEMA_VERSION
from runtime.services.analyzer_engine_registry_service import AnalyzerEngineRegistryService
from v6.runtime.runtime_status import describe_runtime_status

router = APIRouter(tags=["analyzer"])
registry_service = AnalyzerEngineRegistryService()
state_repo = StateRepository()


@router.get("/api/v3/analyzer/status")
def get_analyzer_status(profile_id: str = PAPER_PROFILE_ID):
    with session_scope() as session:
        status = state_repo.get(session, "analyzer_status", default={}, profile_id=profile_id)
    runtime_readiness = describe_runtime_status()
    runtime_ready = runtime_readiness.get("runtime_state") == "ready"
    active_engine = runtime_readiness.get("active_engine") if runtime_ready else (status.get("active_engine") or registry_service.active_engine_name())
    active_engine_version = runtime_readiness.get("active_engine_version") if runtime_ready else (status.get("active_engine_version") or runtime_readiness.get("active_engine_version"))
    return {
        "ok": True,
        "active_engine": active_engine,
        "active_engine_version": active_engine_version,
        "champion_version": runtime_readiness.get("champion_version"),
        "fallback_active": bool(runtime_readiness.get("fallback_active")),
        "shadow_status": runtime_readiness.get("shadow_status"),
        "runtime_state": runtime_readiness.get("runtime_state"),
        "runtime_ready": runtime_ready,
        "request_schema_version": status.get("request_schema_version") or REQUEST_SCHEMA_VERSION,
        "response_schema_version": status.get("response_schema_version") or RESPONSE_SCHEMA_VERSION,
        "fallback_count": int(status.get("fallback_count") or 0),
        "last_fallback_reason": status.get("last_fallback_reason"),
        "last_engine_error": status.get("last_engine_error"),
        "last_analysis_at_utc": status.get("last_analysis_at_utc"),
    }


@router.get("/api/v3/analyzer/engines")
def get_analyzer_engines():
    return {
        "ok": True,
        "active_engine": registry_service.active_engine_name(),
        "items": registry_service.list_engines(),
    }


@router.get("/api/v3/analyzer/fallbacks")
def get_analyzer_fallbacks(profile_id: str = PAPER_PROFILE_ID):
    with session_scope() as session:
        payload = state_repo.get(session, "analyzer_fallbacks", default={"count": 0, "recent": []}, profile_id=profile_id)
    return {
        "ok": True,
        "count": int(payload.get("count") or 0),
        "recent": list(payload.get("recent") or []),
    }
