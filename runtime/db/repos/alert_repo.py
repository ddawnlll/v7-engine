"""Alert repository for v4."""

from __future__ import annotations

from sqlalchemy.orm import Session

from runtime.db.models import Alert
from runtime.db.repos._helpers import loads_json
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID


class AlertRepository:
    def save_alert(self, session: Session, payload: dict) -> dict:
        payload = {**payload, "profile_id": str(payload.get("profile_id") or PAPER_PROFILE_ID)}
        public_alert_id = str(payload["alert_id"])
        storage_alert_id = self._storage_alert_id(public_alert_id, payload["profile_id"])
        row = (
            session.query(Alert)
            .filter(Alert.profile_id == payload["profile_id"])
            .filter(Alert.alert_id.in_([public_alert_id, storage_alert_id]))
            .one_or_none()
        )
        persisted = {**payload, "alert_id": storage_alert_id}
        if row is None:
            row = Alert(**persisted)
            session.add(row)
        else:
            for key, value in persisted.items():
                setattr(row, key, value)
        session.commit()
        return self._to_dict(row)

    def get_alert(self, session: Session, alert_id: str, profile_id: str = PAPER_PROFILE_ID) -> dict | None:
        storage_alert_id = self._storage_alert_id(alert_id, profile_id)
        row = (
            session.query(Alert)
            .filter(Alert.profile_id == profile_id)
            .filter(Alert.alert_id.in_([alert_id, storage_alert_id]))
            .one_or_none()
        )
        return self._to_dict(row) if row else None

    def list_alerts(
        self,
        session: Session,
        active_only: bool = False,
        limit: int = 100,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> list[dict]:
        query = session.query(Alert).filter(Alert.profile_id == profile_id)
        if active_only:
            query = query.filter(Alert.active.is_(True))
        rows = query.order_by(Alert.detected_at_utc.desc()).limit(limit).all()
        return [self._to_dict(row) for row in rows]

    def delete_alert(self, session: Session, alert_id: str, profile_id: str = PAPER_PROFILE_ID) -> None:
        storage_alert_id = self._storage_alert_id(alert_id, profile_id)
        row = (
            session.query(Alert)
            .filter(Alert.profile_id == profile_id)
            .filter(Alert.alert_id.in_([alert_id, storage_alert_id]))
            .one_or_none()
        )
        if row:
            session.delete(row)
            session.commit()

    @staticmethod
    def _storage_alert_id(alert_id: str, profile_id: str) -> str:
        return f"{str(profile_id or PAPER_PROFILE_ID)}:{str(alert_id or '')}"

    @classmethod
    def _public_alert_id(cls, alert_id: str, profile_id: str) -> str:
        prefix = f"{str(profile_id or PAPER_PROFILE_ID)}:"
        return str(alert_id)[len(prefix):] if str(alert_id).startswith(prefix) else str(alert_id)

    @classmethod
    def _to_dict(cls, row: Alert) -> dict:
        profile_id = getattr(row, "profile_id", PAPER_PROFILE_ID)
        return {
            "id": row.id,
            "alert_id": cls._public_alert_id(row.alert_id, profile_id),
            "profile_id": getattr(row, "profile_id", PAPER_PROFILE_ID),
            "severity": row.severity,
            "kind": row.kind,
            "scope": row.scope,
            "message": row.message,
            "active": row.active,
            "payload": loads_json(row.payload_json, {}),
            "detected_at_utc": row.detected_at_utc,
        }
