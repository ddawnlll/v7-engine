"""Composite failure analytics routes for the dedicated failures page."""

from __future__ import annotations

from fastapi import APIRouter, Query, Response

from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.services.failure_analytics_service import FailureAnalyticsService

router = APIRouter(tags=["failure-analytics"])
failure_analytics_service = FailureAnalyticsService()


@router.get("/api/v3/failures/analytics")
def get_failure_analytics(
    lookback_days: int = Query(default=30, ge=0, le=3650),
    mode: str | None = Query(default=None),
    min_confidence: float = Query(default=0.6, ge=0.0, le=1.0),
    profile_id: str = Query(default=PAPER_PROFILE_ID),
):
    return failure_analytics_service.get_payload(
        lookback_days=lookback_days,
        mode_filter=mode,
        min_confidence=min_confidence,
        profile_id=profile_id,
    )


@router.get("/api/v3/failures/export")
def export_failures_csv(
    lookback_days: int = Query(default=30, ge=0, le=3650),
    mode: str | None = Query(default=None),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    profile_id: str = Query(default=PAPER_PROFILE_ID),
):
    rows = failure_analytics_service.export_rows(
        lookback_days=lookback_days,
        mode_filter=mode,
        min_confidence=min_confidence,
        profile_id=profile_id,
    )
    csv_payload = failure_analytics_service.export_csv(rows)
    return Response(
        content=csv_payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="failure-analytics.csv"'},
    )
