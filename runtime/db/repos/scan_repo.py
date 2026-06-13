"""Scan repository for v4."""

from __future__ import annotations

from sqlalchemy.orm import Session

from runtime.db.models import ScanRun
from runtime.db.repos._helpers import loads_json
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID


class ScanRepository:
    def save_run(self, session: Session, payload: dict) -> dict:
        payload = {
            **payload,
            "profile_id": str(payload.get("profile_id") or PAPER_PROFILE_ID),
            "resolved_config_hash": str(payload.get("resolved_config_hash") or ""),
        }
        row = session.query(ScanRun).filter(ScanRun.run_id == payload["run_id"]).one_or_none()
        if row is None:
            row = ScanRun(**payload)
            session.add(row)
        else:
            for key, value in payload.items():
                setattr(row, key, value)
        session.commit()
        return self._to_dict(row)

    def get_run(self, session: Session, run_id: str, profile_id: str | None = None) -> dict | None:
        query = session.query(ScanRun).filter(ScanRun.run_id == run_id)
        if profile_id:
            query = query.filter(ScanRun.profile_id == profile_id)
        row = query.one_or_none()
        return self._to_dict(row) if row else None

    def list_runs(self, session: Session, limit: int = 100, profile_id: str | None = None) -> list[dict]:
        query = session.query(ScanRun)
        if profile_id:
            query = query.filter(ScanRun.profile_id == profile_id)
        rows = query.order_by(ScanRun.created_at_utc.desc()).limit(limit).all()
        return [self._to_dict(row) for row in rows]

    @staticmethod
    def _to_dict(row: ScanRun) -> dict:
        return {
            "id": row.id,
            "run_id": row.run_id,
            "profile_id": getattr(row, "profile_id", PAPER_PROFILE_ID),
            "requested_by": row.requested_by,
            "status": row.status,
            "symbols": [item for item in row.symbols_csv.split(",") if item],
            "intervals": [item for item in row.intervals_csv.split(",") if item],
            "modes": [item for item in row.modes_csv.split(",") if item],
            "signal_count": row.signal_count,
            "summary": row.summary,
            "error_text": row.error_text,
            "created_at_utc": row.created_at_utc,
            "started_at_utc": row.started_at_utc,
            "finished_at_utc": row.finished_at_utc,
            "payload": loads_json(row.payload_json, {}),
            "result": loads_json(row.result_json, {}),
            "resolved_config_hash": getattr(row, "resolved_config_hash", ""),
        }
