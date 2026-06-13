"""Engine improvements analytics routes."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.services.improvement_analytics_service import ImprovementAnalyticsService

router = APIRouter(tags=["improvements"])
service = ImprovementAnalyticsService()


@router.get("/api/v3/improvements")
@router.get("/api/admin/improvements")
def get_improvements(
    lookback_days: int = Query(default=30, ge=0, le=3650),
    min_samples: int = Query(default=10, ge=1, le=1000),
    component_type: str | None = Query(default=None),
    component_status: str | None = Query(default=None),
    component_id: str | None = Query(default=None),
    mode: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    interval: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    regime: str | None = Query(default=None),
    profile_id: str = Query(default=PAPER_PROFILE_ID),
):
    return service.get_payload(
        lookback_days=lookback_days,
        min_samples=min_samples,
        component_type=component_type,
        component_status=component_status,
        component_id=component_id,
        mode=mode,
        symbol=symbol,
        interval=interval,
        direction=direction,
        regime=regime,
        profile_id=profile_id,
    )


@router.get("/api/v3/improvements/export", response_class=PlainTextResponse)
@router.get("/api/admin/improvements/export", response_class=PlainTextResponse)
def export_improvements(
    lookback_days: int = Query(default=30, ge=0, le=3650),
    min_samples: int = Query(default=10, ge=1, le=1000),
    component_type: str | None = Query(default=None),
    component_status: str | None = Query(default=None),
    component_id: str | None = Query(default=None),
    mode: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    interval: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    regime: str | None = Query(default=None),
    profile_id: str = Query(default=PAPER_PROFILE_ID),
):
    return PlainTextResponse(
        service.export_csv(
            lookback_days=lookback_days,
            min_samples=min_samples,
            component_type=component_type,
            component_status=component_status,
            component_id=component_id,
            mode=mode,
            symbol=symbol,
            interval=interval,
            direction=direction,
            regime=regime,
            profile_id=profile_id,
        ),
        media_type="text/csv; charset=utf-8",
    )


@router.get("/api/v3/improvements/components")
def list_components(
    component_type: str | None = Query(default=None),
    component_status: str | None = Query(default=None),
    profile_id: str = Query(default=PAPER_PROFILE_ID),
):
    payload = service.get_payload(
        lookback_days=30,
        min_samples=10,
        component_type=component_type,
        component_status=component_status,
        profile_id=profile_id,
    )
    return payload.get("component_registry", {})


@router.get("/api/v3/improvements/component/{component_id}")
def get_component_detail(
    component_id: str,
    lookback_days: int = Query(default=30, ge=0, le=3650),
    min_samples: int = Query(default=10, ge=1, le=1000),
    profile_id: str = Query(default=PAPER_PROFILE_ID),
):
    payload = service.get_payload(
        lookback_days=lookback_days,
        min_samples=min_samples,
        component_id=component_id,
        profile_id=profile_id,
    )
    impact = next((item for item in payload.get("component_impact", {}).get("by_component", []) if item.get("component_id") == component_id), None)
    registry = next((item for item in payload.get("component_registry", {}).get("items", []) if item.get("component_id") == component_id), None)
    return {
        "component": registry,
        "impact": impact,
        "related_changes": [item for item in payload.get("recent_changes", {}).get("items", []) if item.get("component_id") == component_id],
        "recommendations": [item for group in payload.get("recommendations", {}).values() for item in group if item.get("component_id") == component_id],
    }


@router.get("/api/v3/improvements/changes")
def list_changes(
    lookback_days: int = Query(default=30, ge=0, le=3650),
    component_id: str | None = Query(default=None),
    profile_id: str = Query(default=PAPER_PROFILE_ID),
):
    payload = service.get_payload(
        lookback_days=lookback_days,
        min_samples=10,
        component_id=component_id,
        profile_id=profile_id,
    )
    return payload.get("recent_changes", {})
