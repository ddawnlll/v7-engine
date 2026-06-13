"""Health routes for v4."""

from __future__ import annotations

from datetime import datetime, timezone
from time import time

from fastapi import APIRouter, Request
from pydantic import BaseModel

from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.db.repos.state_repo import StateRepository
from runtime.db.session import check_database_connection
from runtime.runtime.scan_control import ScanControlService
from runtime.services.alert_service import AlertService
from runtime.services.calibration_service import CalibrationStatusService
from runtime.services.dashboard_service import DashboardService
from runtime.services.performance_service import PerformanceService
from runtime.services.analyzer_engine_registry_service import AnalyzerEngineRegistryService
from v5.model_registry_service import SelfLearningModelRegistryService
from runtime.services.universe_filter_service import UniverseFilterService
from runtime.services.trace_service import TraceService
from runtime.services.simulation_service import SimulationService
from runtime.services.binance_usdm_reconciliation_service import BinanceUsdmReconciliationError, BinanceUsdmReconciliationService
from runtime.services.binance_usdm_user_data_stream_service import BinanceUsdmUserDataStreamService
from runtime.services.runtime_profile_service import RuntimeProfileNotFoundError, RuntimeProfileService
from v6.runtime.runtime_status import describe_runtime_status

router = APIRouter(tags=["health"])
alert_service = AlertService()
state_repo = StateRepository()
dashboard_service = DashboardService()
performance_service = PerformanceService()
trace_service = TraceService()
simulation_service = SimulationService()
calibration_service = CalibrationStatusService()
runtime_profile_service = RuntimeProfileService()
user_data_stream_service = BinanceUsdmUserDataStreamService()
reconciliation_service = BinanceUsdmReconciliationService()
scan_control_service = ScanControlService()
universe_filter_service = UniverseFilterService()
self_learning_registry_service = SelfLearningModelRegistryService()
analyzer_registry_service = AnalyzerEngineRegistryService()


def _is_current_runtime_error(last_error: object) -> bool:
    if not last_error:
        return False
    if not isinstance(last_error, dict):
        return True
    message = str(last_error.get("message") or "").strip()
    if "Live monitoring ownership is deferred beyond Phase 5A." in message:
        return False
    timestamp = str(last_error.get("timestamp") or "").strip()
    if not timestamp:
        return True
    try:
        error_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - error_at).total_seconds() <= 900


class AlertSummaryResponse(BaseModel):
    total_active: int
    critical: int
    warning: int
    info: int
    items: list[dict]


class HealthResponse(BaseModel):
    status: str
    uptime_seconds: int
    db_status: str
    db_connected: bool
    exchange_status: str
    runtime_status: str
    degraded_reason: str | None = None
    last_error: dict | None = None
    last_scan_completed_at_utc: str | None = None
    next_scan_at_utc: str | None = None
    runner_heartbeat: dict | None = None
    heartbeat_age_seconds: float | None = None
    scan_control: dict | None = None
    symbol_throttle: dict | None = None
    self_learning: dict | None = None
    analyzer: dict | None = None
    runtime_readiness: dict | None = None
    profile: dict | None = None
    auto_live: dict | None = None
    stream: dict | None = None
    reconciliation: dict | None = None
    alert_summary: AlertSummaryResponse


@router.get("/api/v3/health", response_model=HealthResponse)
@router.get("/api/v3/engine/health", response_model=HealthResponse)
def get_health(request: Request, profile_id: str = PAPER_PROFILE_ID) -> HealthResponse:
    db_connected, db_detail = check_database_connection()
    alert_summary = alert_service.summary(probe_exchange=False, profile_id=profile_id)
    started_at = getattr(request.app.state, "started_at", time())
    try:
        profile_payload = runtime_profile_service.get_profile(profile_id)
    except RuntimeProfileNotFoundError:
        profile_payload = None
    try:
        auto_live_payload = runtime_profile_service.get_auto_live_policy(profile_id)
    except RuntimeProfileNotFoundError:
        auto_live_payload = None
    try:
        stream_payload = user_data_stream_service.get_stream_state(profile_id)
    except RuntimeProfileNotFoundError:
        stream_payload = None
    try:
        reconciliation_payload = reconciliation_service.get_reconciliation(profile_id)
    except (RuntimeProfileNotFoundError, BinanceUsdmReconciliationError):
        reconciliation_payload = None
    from runtime.db.session import session_scope
    with session_scope() as session:
        runner_heartbeat = state_repo.get(session, "runner_heartbeat", default=None, profile_id=profile_id)
        last_scan = state_repo.get(session, "last_scan", default=None, profile_id=profile_id)
        next_scan = state_repo.get(session, "next_scan", default=None, profile_id=profile_id)
        last_error = state_repo.get(session, "last_error", default=None, profile_id=profile_id)
        analyzer_status = state_repo.get(session, "analyzer_status", default=None, profile_id=profile_id)
        analyzer_fallbacks = state_repo.get(session, "analyzer_fallbacks", default=None, profile_id=profile_id)
    scan_control = scan_control_service.get_state(profile_id=profile_id)
    symbol_throttle = universe_filter_service.evaluate(profile_id=profile_id)
    active_model = self_learning_registry_service.get_active_model()
    runtime_readiness = describe_runtime_status()
    heartbeat_age = None
    runtime_status = "running" if db_connected else "degraded"
    if isinstance(runner_heartbeat, dict) and runner_heartbeat.get("timestamp"):
        try:
            stamp = datetime.fromisoformat(str(runner_heartbeat["timestamp"]).replace("Z", "+00:00"))
            heartbeat_age = max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds())
            if heartbeat_age > 180:
                runtime_status = "degraded"
        except ValueError:
            heartbeat_age = None
    has_critical = alert_summary["critical"] > 0
    status = "healthy" if db_connected and not has_critical and runtime_status == "running" else "degraded"
    degraded_reason = None
    if not db_connected:
        degraded_reason = "database_unavailable"
    elif runtime_status != "running":
        degraded_reason = "runner_heartbeat_stale"
    elif has_critical:
        degraded_reason = "critical_alert"
    if _is_current_runtime_error(last_error):
        status = "degraded"
        degraded_reason = "last_error"
    exchange_status = "degraded" if any(item.get("kind") == "exchange_failure" for item in alert_summary["items"]) else "unknown"
    if profile_payload is not None:
        connectivity_status = str(((profile_payload.get("connectivity") or {}).get("status") or "")).lower()
        if connectivity_status in {"connected", "ready"}:
            exchange_status = "connected"
        elif connectivity_status in {"error", "missing_credentials"}:
            exchange_status = "degraded"
    if stream_payload is not None and (
        str(stream_payload.get("status") or "").upper() in {"DEGRADED", "EXPIRED"}
        or bool(stream_payload.get("reconnect_required"))
    ):
        exchange_status = "degraded"
        if degraded_reason is None:
            degraded_reason = "stream_degraded"
    if reconciliation_payload is not None and str(reconciliation_payload.get("status") or "").upper() == "DEGRADED":
        exchange_status = "degraded"
        if degraded_reason is None:
            degraded_reason = "reconciliation_degraded"
    return HealthResponse(
        status=status,
        uptime_seconds=max(0, int(time() - started_at)),
        db_status=db_detail,
        db_connected=db_connected,
        exchange_status=exchange_status,
        runtime_status=runtime_status,
        degraded_reason=degraded_reason,
        last_error=last_error if isinstance(last_error, dict) else ({"message": str(last_error)} if last_error else None),
        last_scan_completed_at_utc=(last_scan or {}).get("timestamp") if isinstance(last_scan, dict) else None,
        next_scan_at_utc=(next_scan or {}).get("timestamp") if isinstance(next_scan, dict) else None,
        runner_heartbeat=runner_heartbeat if isinstance(runner_heartbeat, dict) else None,
        heartbeat_age_seconds=heartbeat_age,
        scan_control=scan_control,
        symbol_throttle=symbol_throttle,
        self_learning={
            "active_model_version": active_model.get("model_version") if active_model else None,
            "status": active_model.get("status") if active_model else "INACTIVE",
            "rollout_stage": active_model.get("rollout_stage") if active_model else None,
        },
        analyzer={
            "active_engine": runtime_readiness.get("active_engine") or ((analyzer_status or {}).get("active_engine") if isinstance(analyzer_status, dict) else analyzer_registry_service.active_engine_name()),
            "active_engine_version": runtime_readiness.get("active_engine_version") or ((analyzer_status or {}).get("active_engine_version") if isinstance(analyzer_status, dict) else None),
            "request_schema_version": (analyzer_status or {}).get("request_schema_version") if isinstance(analyzer_status, dict) else None,
            "response_schema_version": (analyzer_status or {}).get("response_schema_version") if isinstance(analyzer_status, dict) else None,
            "fallback_count": int(((analyzer_fallbacks or {}).get("count") if isinstance(analyzer_fallbacks, dict) else 0) or 0),
            "last_fallback_reason": runtime_readiness.get("fallback_reason") or ((analyzer_status or {}).get("last_fallback_reason") if isinstance(analyzer_status, dict) else None),
            "last_engine_error": (analyzer_status or {}).get("last_engine_error") if isinstance(analyzer_status, dict) else None,
        },
        runtime_readiness=runtime_readiness,
        profile=profile_payload,
        auto_live=auto_live_payload,
        stream=stream_payload,
        reconciliation=reconciliation_payload,
        alert_summary=AlertSummaryResponse(**alert_summary),
    )


@router.get("/api/admin/state")
def get_admin_state(profile_id: str = PAPER_PROFILE_ID):
    dashboard = dashboard_service.get_dashboard()
    queue = dashboard.get("job_queue") or {}
    return {
        "engine": {
            "enabled": str((dashboard.get("settings") or {}).get("AUTONOMOUS_ENABLED", "1")).lower() in {"1", "true", "yes", "on"},
            "scan_interval_seconds": (dashboard.get("settings") or {}).get("AUTONOMOUS_SCAN_INTERVAL_SECONDS"),
            "monitor_interval_seconds": (dashboard.get("settings") or {}).get("AUTONOMOUS_MONITOR_INTERVAL_SECONDS"),
            "min_confidence": (dashboard.get("settings") or {}).get("AUTONOMOUS_MIN_CONFIDENCE"),
            "scan_workers": (dashboard.get("settings") or {}).get("AUTONOMOUS_SCAN_WORKERS"),
            "symbols": (dashboard.get("symbols") or {}).get("symbols"),
            "intervals": (dashboard.get("symbols") or {}).get("intervals"),
            "modes": str((dashboard.get("settings") or {}).get("AUTONOMOUS_MODES", "")).split(",") if (dashboard.get("settings") or {}).get("AUTONOMOUS_MODES") else [],
            "max_trades_per_day": (dashboard.get("settings") or {}).get("MAX_TRADES_PER_DAY"),
            "last_scan": (dashboard.get("engine") or {}).get("last_scan"),
            "last_monitor": (dashboard.get("engine_health") or {}).get("runner_heartbeat"),
            "last_error": None,
            "scan_control": scan_control_service.get_state(profile_id=profile_id),
            "queue": {
                "pending": queue.get("pending", 0),
                "running": queue.get("running", 0),
                "completed": queue.get("completed", 0),
                "failed": queue.get("failed", 0),
            },
        },
        "engine_health": dashboard.get("engine_health"),
        "settings": dashboard.get("settings"),
        "orders": dashboard.get("orders"),
        "performance": performance_service.get_snapshot(profile_id=profile_id),
        "trace_logs": trace_service.get_snapshot(limit=80, profile_id=profile_id),
        "job_queue": queue,
        "simulations": simulation_service.list_runs(limit=20).get("summary"),
        "calibration": calibration_service.get_status(),
    }
