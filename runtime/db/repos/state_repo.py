"""Runtime state repository for v4."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from runtime.db.models import RuntimeState
from runtime.db.repos._helpers import dumps_json, loads_json
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID


class StateRepository:
    def set(self, session: Session, key: str, value, *, profile_id: str = PAPER_PROFILE_ID) -> dict:
        resolved_profile_id = str(profile_id or PAPER_PROFILE_ID)
        payload = dumps_json(value)
        row = self._query(session, key, resolved_profile_id).one_or_none()
        if row is None:
            row = RuntimeState(profile_id=resolved_profile_id, key=key, value_json=payload)
            session.add(row)
        else:
            row.value_json = payload
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            row = self._query(session, key, resolved_profile_id).one_or_none()
            if row is None:
                raise
            row.value_json = payload
            session.commit()
        return {"key": key, "profile_id": resolved_profile_id, "value": loads_json(payload, None)}

    def get(self, session: Session, key: str, default=None, *, profile_id: str = PAPER_PROFILE_ID):
        row = self._query(session, key, str(profile_id or PAPER_PROFILE_ID)).one_or_none()
        if row is None:
            return default
        return loads_json(row.value_json, default)

    def delete(self, session: Session, key: str, *, profile_id: str = PAPER_PROFILE_ID) -> bool:
        row = self._query(session, key, str(profile_id or PAPER_PROFILE_ID)).one_or_none()
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True

    @staticmethod
    def _query(session: Session, key: str, profile_id: str):
        return (
            session.query(RuntimeState)
            .filter(RuntimeState.profile_id == profile_id)
            .filter(RuntimeState.key == key)
        )
