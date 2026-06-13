"""Failure analysis routes for v4."""

from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Query

from runtime.db.repos.failure_repo import FailureRepository
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.db.session import session_scope
from runtime.services.weakness_service import WeaknessService

router = APIRouter(tags=["failures"])
failure_repo = FailureRepository()
weakness_service = WeaknessService(failure_repo=failure_repo)


class FailureRecordModel(BaseModel):
    id: int
    order_id: str
    signal_id: str | None = None
    failure_source: str
    blamed_component: str
    severity_score: int = Field(ge=1, le=5)
    confidence: float = Field(ge=0.0, le=1.0)
    classification: str
    explanation: str
    improvement: str
    profile_id: str
    created_at_utc: str


class WeaknessSummaryModel(BaseModel):
    failure_source: str
    blamed_component: str
    count: int


class FailureSummaryModel(BaseModel):
    total: int
    counts_by_failure_source: dict[str, int]
    counts_by_blamed_component: dict[str, int]
    average_severity_score: float
    average_confidence: float
    top_weakness: WeaknessSummaryModel | None = None


class FailureListResponse(BaseModel):
    ok: bool = True
    count: int
    total: int
    limit: int
    offset: int
    items: list[FailureRecordModel]


class FailureDetailResponse(BaseModel):
    ok: bool = True
    item: FailureRecordModel


class FailureSummaryResponse(BaseModel):
    ok: bool = True
    summary: FailureSummaryModel


class RankedComponentModel(BaseModel):
    blamed_component: str
    count: int
    avg_severity: float
    avg_confidence: float
    weight_score: float
    top_failure_source: str | None = None
    best_improvement: str


class RankedSourceModel(BaseModel):
    failure_source: str
    count: int
    avg_severity: float
    weight_score: float
    top_component: str | None = None
    best_improvement: str
    components: list[RankedComponentModel]


class WeaknessProfileModel(BaseModel):
    generated_at: str
    lookback_days: int
    min_confidence: float
    profile_id: str
    total_losses_analyzed: int
    top_failure_source: str | None = None
    top_blamed_component: str | None = None
    ranked_sources: list[RankedSourceModel]
    ranked_components: list[RankedComponentModel]


class WeaknessProfileResponse(BaseModel):
    ok: bool = True
    profile: WeaknessProfileModel


@router.get("/api/v3/failures", response_model=FailureListResponse)
@router.get("/api/admin/failures", response_model=FailureListResponse)
def get_failures(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    failure_source: str | None = Query(default=None),
    blamed_component: str | None = Query(default=None),
    severity_score: int | None = Query(default=None, ge=1, le=5),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    profile_id: str = Query(default=PAPER_PROFILE_ID),
):
    with session_scope() as session:
        items, total = failure_repo.list_failures(
            session,
            limit=limit,
            offset=offset,
            failure_source=failure_source,
            blamed_component=blamed_component,
            severity_score=severity_score,
            date_from=date_from,
            date_to=date_to,
            profile_id=profile_id,
        )
    return {
        "ok": True,
        "count": len(items),
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items,
    }


@router.get("/api/v3/failures/summary", response_model=FailureSummaryResponse)
@router.get("/api/admin/failures/summary", response_model=FailureSummaryResponse)
def get_failure_summary(
    failure_source: str | None = Query(default=None),
    blamed_component: str | None = Query(default=None),
    severity_score: int | None = Query(default=None, ge=1, le=5),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    profile_id: str = Query(default=PAPER_PROFILE_ID),
):
    with session_scope() as session:
        summary = failure_repo.get_summary(
            session,
            failure_source=failure_source,
            blamed_component=blamed_component,
            severity_score=severity_score,
            date_from=date_from,
            date_to=date_to,
            profile_id=profile_id,
        )
    return {"ok": True, "summary": summary}


@router.get("/api/v3/failures/weakness-profile", response_model=WeaknessProfileResponse)
@router.get("/api/admin/failures/weakness-profile", response_model=WeaknessProfileResponse)
def get_weakness_profile(
    lookback_days: int = Query(default=30, ge=1, le=365),
    min_confidence: float = Query(default=0.6, ge=0.0, le=1.0),
    profile_id: str = Query(default=PAPER_PROFILE_ID),
):
    return {
        "ok": True,
        "profile": weakness_service.get_weakness_profile(
            lookback_days=lookback_days,
            min_confidence=min_confidence,
            profile_id=profile_id,
        ),
    }


@router.get("/api/v3/failures/{order_id}", response_model=FailureDetailResponse)
@router.get("/api/admin/failures/{order_id}", response_model=FailureDetailResponse)
def get_failure_detail(order_id: str, profile_id: str = Query(default=PAPER_PROFILE_ID)):
    with session_scope() as session:
        item = failure_repo.get_failure_for_order(session, order_id, profile_id=profile_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"No failure record found for order {order_id}")
    return {"ok": True, "item": item}
