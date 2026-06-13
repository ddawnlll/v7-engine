"""Alerts routes for v4."""

from __future__ import annotations

from fastapi import APIRouter, Query

from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.services.alert_service import AlertService
from runtime.services.trace_service import TraceService

router = APIRouter(tags=["alerts"])
alert_service = AlertService()
trace_service = TraceService()


@router.get("/api/v3/alerts")
@router.get("/api/v3/operator/alerts")
def get_alerts(
    limit: int = Query(default=50, ge=1, le=200),
    profile_id: str = Query(default=PAPER_PROFILE_ID),
):
    return {"items": alert_service.refresh_alerts(limit=limit, profile_id=profile_id)}


@router.get("/api/v3/logs")
def get_logs(
    limit: int = Query(default=50, ge=1, le=500),
    severity: str = Query(default="ALL"),
    profile_id: str = Query(default=PAPER_PROFILE_ID),
):
    payload = trace_service.get_runtime_logs(limit=limit, profile_id=profile_id)
    if severity.upper() == "ALL":
        return payload
    return {
        "items": [
            item
            for item in payload["items"]
            if str(item.get("severity") or "").upper() == severity.upper()
        ]
    }
