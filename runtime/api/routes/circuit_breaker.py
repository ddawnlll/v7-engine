"""Circuit breaker routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.services.circuit_breaker_service import CircuitBreakerService

router = APIRouter(tags=["circuit_breaker"])
service = CircuitBreakerService()


def _is_synthetic_simulation_profile(profile_id: str | None) -> bool:
    return str(profile_id or "").startswith("simulation-")


def _synthetic_circuit_state(profile_id: str) -> dict:
    return {
        "profile_id": profile_id,
        "status": "DISABLED",
        "reason": "Synthetic simulation failure-analysis profile; circuit breaker state is live-profile only.",
        "failure_rate": 0.0,
        "consecutive_losses": 0,
        "active_rules": [],
    }


@router.get("/api/v3/circuit-breaker/state")
@router.get("/api/admin/circuit-breaker/state")
def get_circuit_breaker_state(
    lookback_window: int = Query(default=10, ge=1, le=500),
    profile_id: str = Query(default=PAPER_PROFILE_ID),
):
    if _is_synthetic_simulation_profile(profile_id):
        return {"ok": True, "state": _synthetic_circuit_state(profile_id)}
    return {"ok": True, "state": service.evaluate_circuit_state(lookback_window=lookback_window, profile_id=profile_id)}


@router.get("/api/v3/circuit-breaker/events")
@router.get("/api/admin/circuit-breaker/events")
def list_circuit_breaker_events(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    profile_id: str = Query(default=PAPER_PROFILE_ID),
):
    if _is_synthetic_simulation_profile(profile_id):
        return {"ok": True, "items": []}
    return {"ok": True, "items": service.list_events(limit=limit, offset=offset, profile_id=profile_id)}


@router.post("/api/v3/circuit-breaker/reset")
@router.post("/api/admin/circuit-breaker/reset")
def reset_circuit_breaker(profile_id: str = Query(default=PAPER_PROFILE_ID)):
    if _is_synthetic_simulation_profile(profile_id):
        return {"ok": True, "state": _synthetic_circuit_state(profile_id)}
    return {"ok": True, "state": service.reset(profile_id=profile_id)}


@router.post("/api/v3/circuit-breaker/settings")
@router.post("/api/admin/circuit-breaker/settings")
def update_circuit_breaker_settings(
    payload: dict,
    profile_id: str = Query(default=PAPER_PROFILE_ID),
):
    if _is_synthetic_simulation_profile(profile_id):
        return {"ok": False, "settings": {}, "message": "Synthetic simulation profiles do not have circuit breaker settings."}
    return {"ok": True, "settings": service.update_settings(payload, profile_id=profile_id)}
