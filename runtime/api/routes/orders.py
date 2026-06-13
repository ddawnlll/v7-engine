"""Order routes for v4."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.runtime.execution_orchestrator import ExecutionOrchestrator

router = APIRouter(tags=["orders"])
execution_orchestrator = ExecutionOrchestrator()


class CloseOrderRequest(BaseModel):
    close_price: float
    close_reason: str = "MANUAL_CLOSE"


class ManualOrderRequest(BaseModel):
    profile_id: str = PAPER_PROFILE_ID
    signal_id: str | None = None
    symbol: str
    interval: str
    mode: str
    direction: str
    confidence: float = 0.0
    entry: float
    sl: float
    tp: float | None = None
    risk_reward: float | None = None
    summary: str | None = None
    regime: str | None = None
    trend: str | None = None
    quantity: float = 1.0
    fee: float = 0.0
    entry_r_multiple: float | None = None
    entry_zone_low: float | None = None
    entry_zone_high: float | None = None
    timing_estimate: dict | None = None
    use_rest_of_balance: bool = False
    use_balance_pct: float | None = None
    leverage: float | None = None


class UpdateOrderRequest(BaseModel):
    status: str | None = None
    close_price: float | None = None
    last_price: float | None = None
    timing_estimate: dict | None = None


class VerifyOrderRequest(BaseModel):
    profile_id: str | None = None
    reason: str = "MANUAL_VERIFY"


class CancelLiveOrderRequest(BaseModel):
    profile_id: str | None = None


@router.get("/api/v3/orders")
@router.get("/api/admin/orders")
def get_orders(
    limit: int = Query(default=500, ge=1, le=2000),
    status: str | None = Query(default=None),
    profile_id: str = Query(default=PAPER_PROFILE_ID),
):
    return execution_orchestrator.get_orders_snapshot(limit=limit, status=status, profile_id=profile_id)


@router.post("/api/v3/orders")
def create_manual_order(payload: ManualOrderRequest):
    try:
        result = execution_orchestrator.create_manual_order(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **result}


@router.patch("/api/v3/orders/{order_id}")
def update_order(order_id: str, payload: UpdateOrderRequest):
    try:
        result = execution_orchestrator.update_manual_order(order_id, payload.model_dump(exclude_none=True))
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message) from exc
    return {"ok": True, **result}


@router.get("/api/v3/orders/{order_id}/query")
def query_live_order(order_id: str, profile_id: str | None = Query(default=None)):
    try:
        result = execution_orchestrator.query_order(order_id, profile_id=profile_id)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message) from exc
    return {"ok": True, **result}


@router.post("/api/v3/orders/{order_id}/verify")
def verify_live_order(order_id: str, payload: VerifyOrderRequest):
    try:
        result = execution_orchestrator.verify_order(order_id, profile_id=payload.profile_id, reason=payload.reason)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message) from exc
    return {"ok": True, **result}


@router.post("/api/v3/orders/{order_id}/cancel")
def cancel_live_order(order_id: str, payload: CancelLiveOrderRequest):
    try:
        result = execution_orchestrator.cancel_order(order_id, profile_id=payload.profile_id)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message) from exc
    return {"ok": True, **result}


@router.post("/api/v3/orders/{order_id}/close")
def close_order(order_id: str, payload: CloseOrderRequest):
    try:
        result = execution_orchestrator.close_order(
            order_id,
            close_price=payload.close_price,
            close_reason=payload.close_reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, **result}


@router.post("/api/v3/orders/close-all-open")
def close_all_open_orders(
    close_reason: str = Query(default="MANUAL_BULK_CLOSE"),
    profile_id: str = Query(default=PAPER_PROFILE_ID),
):
    result = execution_orchestrator.close_all_open_orders(close_reason=close_reason, profile_id=profile_id)
    return {"ok": True, **result}


@router.delete("/api/v3/orders/{order_id}")
def delete_order(order_id: str):
    try:
        deleted = execution_orchestrator.delete_manual_order(order_id)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message) from exc
    return {"ok": deleted}
