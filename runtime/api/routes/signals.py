"""Signal routes, including analyzer audit snapshots."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from runtime.db.repos.signal_repo import SignalRepository
from runtime.db.session import session_scope

router = APIRouter(tags=["signals"])
signal_repo = SignalRepository()


@router.get("/api/v3/signals/{signal_id}")
@router.get("/api/admin/signals/{signal_id}")
def get_signal(signal_id: str):
    with session_scope() as session:
        row = signal_repo.get_signal(session, signal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    audit = dict(row.get("audit") or {})
    row["audit_summary"] = {
        "confidence_before_learning": audit.get("confidence_before_learning"),
        "confidence_after_learning": audit.get("confidence_after_learning"),
        "circuit_breaker_state": audit.get("circuit_breaker_state"),
        "learning_adjustments_applied": len(audit.get("learning_adjustments_applied") or []),
    }
    return {"ok": True, "signal": row}


@router.get("/api/v3/signals/{signal_id}/audit")
@router.get("/api/admin/signals/{signal_id}/audit")
def get_signal_audit(signal_id: str):
    with session_scope() as session:
        audit = signal_repo.get_audit_trail(session, signal_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="Signal audit not found")
    return {"ok": True, "audit": audit}
