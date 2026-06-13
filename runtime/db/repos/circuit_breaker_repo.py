"""Persistence helpers for circuit breaker state transitions."""

from __future__ import annotations

from sqlalchemy.orm import Session

from runtime.db.models import CircuitBreakerEvent
from runtime.db.repos._helpers import dumps_json, dumps_list, loads_json
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID


class CircuitBreakerRepository:
    def save_event(self, session: Session, payload: dict) -> dict:
        row = CircuitBreakerEvent(**{**payload, "profile_id": str(payload.get("profile_id") or PAPER_PROFILE_ID)})
        session.add(row)
        session.commit()
        session.refresh(row)
        return self._to_dict(row)

    def get_current_state(self, session: Session, profile_id: str = PAPER_PROFILE_ID) -> dict | None:
        row = (
            session.query(CircuitBreakerEvent)
            .filter(CircuitBreakerEvent.profile_id == profile_id)
            .filter(CircuitBreakerEvent.resolved_at_utc.is_(None))
            .order_by(CircuitBreakerEvent.created_at_utc.desc())
            .first()
        )
        return self._to_dict(row) if row else None

    def list_events(self, session: Session, limit: int = 100, offset: int = 0, profile_id: str = PAPER_PROFILE_ID) -> list[dict]:
        rows = (
            session.query(CircuitBreakerEvent)
            .filter(CircuitBreakerEvent.profile_id == profile_id)
            .order_by(CircuitBreakerEvent.created_at_utc.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._to_dict(row) for row in rows]

    def resolve_event(self, session: Session, event_id: int, resolved_at_utc: str, profile_id: str = PAPER_PROFILE_ID) -> dict | None:
        row = session.get(CircuitBreakerEvent, event_id)
        if row is None or getattr(row, "profile_id", PAPER_PROFILE_ID) != profile_id:
            return None
        if row is None:
            return None
        row.resolved_at_utc = resolved_at_utc
        session.commit()
        return self._to_dict(row)

    @staticmethod
    def normalize_payload(payload: dict) -> dict:
        return {
            "profile_id": str(payload.get("profile_id") or PAPER_PROFILE_ID),
            "status": payload["status"],
            "reason": payload.get("reason") or "",
            "failure_rate": float(payload.get("failure_rate") or 0.0),
            "consecutive_losses": int(payload.get("consecutive_losses") or 0),
            "triggered_at_utc": payload["triggered_at_utc"],
            "resolved_at_utc": payload.get("resolved_at_utc"),
            "auto_resume_at_utc": payload.get("auto_resume_at_utc"),
            "active_rules_json": dumps_list(payload.get("active_rules") or []),
            "session_breakdown_json": dumps_json(payload.get("session_breakdown") or {}),
            "time_of_day_breakdown_json": dumps_json(payload.get("time_of_day_breakdown") or {}),
            "created_at_utc": payload.get("created_at_utc") or payload["triggered_at_utc"],
        }

    @staticmethod
    def _to_dict(row: CircuitBreakerEvent) -> dict:
        return {
            "id": row.id,
            "profile_id": getattr(row, "profile_id", PAPER_PROFILE_ID),
            "status": row.status,
            "reason": row.reason,
            "failure_rate": row.failure_rate,
            "consecutive_losses": row.consecutive_losses,
            "triggered_at_utc": row.triggered_at_utc,
            "resolved_at_utc": row.resolved_at_utc,
            "auto_resume_at_utc": row.auto_resume_at_utc,
            "active_rules": loads_json(row.active_rules_json, []),
            "session_breakdown": loads_json(row.session_breakdown_json, {}),
            "time_of_day_breakdown": loads_json(row.time_of_day_breakdown_json, {}),
            "created_at_utc": row.created_at_utc,
        }
