"""Paper budget routes for v4."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.runtime.execution_orchestrator import ExecutionOrchestrator
from runtime.runtime.paper_execution import InsufficientFundsError

router = APIRouter(tags=["paper"])
execution_orchestrator = ExecutionOrchestrator()


class DepositRequest(BaseModel):
    profile_id: str = PAPER_PROFILE_ID
    amount: float = Field(gt=0)


class ResetRequest(BaseModel):
    profile_id: str = PAPER_PROFILE_ID
    balance: float | None = Field(default=None, ge=0)


@router.get("/api/v3/paper/balance")
@router.get("/api/admin/paper/balance")
def get_paper_balance(profile_id: str = PAPER_PROFILE_ID):
    return execution_orchestrator.get_paper_balance_payload(profile_id=profile_id)


@router.post("/api/v3/paper/deposit")
@router.post("/api/admin/paper/deposit")
def deposit_paper_balance(payload: DepositRequest):
    try:
        return {"ok": True, **execution_orchestrator.deposit_paper_balance(payload.amount, profile_id=payload.profile_id)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/v3/paper/reset")
@router.post("/api/admin/paper/reset")
def reset_paper_balance(payload: ResetRequest):
    try:
        return {"ok": True, **execution_orchestrator.reset_paper_balance(payload.balance, profile_id=payload.profile_id)}
    except (ValueError, InsufficientFundsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/v3/paper/reconcile")
@router.post("/api/admin/paper/reconcile")
def reconcile_paper_balance(profile_id: str = PAPER_PROFILE_ID):
    try:
        return {"ok": True, **execution_orchestrator.reconcile_legacy_open_orders(profile_id=profile_id)}
    except (ValueError, InsufficientFundsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
