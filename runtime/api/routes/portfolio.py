"""Portfolio routes for v4."""

from __future__ import annotations

from fastapi import APIRouter, Query

from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.runtime.execution_orchestrator import ExecutionOrchestrator

router = APIRouter(tags=["portfolio"])
execution_orchestrator = ExecutionOrchestrator()


@router.get("/api/v3/portfolio")
@router.get("/api/portfolio")
def get_portfolio(profile_id: str = Query(default=PAPER_PROFILE_ID)):
    return execution_orchestrator.get_portfolio_payload(profile_id=profile_id)
