"""Performance routes for v4."""

from __future__ import annotations

from fastapi import APIRouter, Query

from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.services.performance_service import PerformanceService

router = APIRouter(tags=["performance"])
performance_service = PerformanceService()


@router.get("/api/v3/performance")
@router.get("/api/admin/performance")
def get_performance(
    limit: int = Query(default=120, ge=1, le=1000),
    profile_id: str = Query(default=PAPER_PROFILE_ID),
):
    return {
        "ok": True,
        "snapshot": performance_service.get_snapshot(profile_id=profile_id),
        "history": performance_service.get_history(limit=limit, profile_id=profile_id),
        "analytics": performance_service.get_analytics(limit=max(limit, 250), profile_id=profile_id),
    }
