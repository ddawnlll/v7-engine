"""Performance snapshot repository for v4."""

from __future__ import annotations

from sqlalchemy.orm import Session

from runtime.db.models import PerformanceSnapshot
from runtime.db.repos._helpers import loads_json
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID


class PerformanceRepository:
    def save_snapshot(self, session: Session, payload: dict) -> dict:
        row = PerformanceSnapshot(**{**payload, "profile_id": str(payload.get("profile_id") or PAPER_PROFILE_ID)})
        session.add(row)
        session.commit()
        return self._to_dict(row)

    def list_snapshots(self, session: Session, limit: int = 120, profile_id: str = PAPER_PROFILE_ID) -> list[dict]:
        rows = (
            session.query(PerformanceSnapshot)
            .filter(PerformanceSnapshot.profile_id == profile_id)
            .order_by(PerformanceSnapshot.timestamp_utc.desc(), PerformanceSnapshot.id.desc())
            .limit(limit)
            .all()
        )
        history = [self._to_dict(row) for row in rows]
        history.reverse()
        return history

    def get_latest_snapshot(self, session: Session, profile_id: str = PAPER_PROFILE_ID) -> dict | None:
        row = (
            session.query(PerformanceSnapshot)
            .filter(PerformanceSnapshot.profile_id == profile_id)
            .order_by(PerformanceSnapshot.timestamp_utc.desc(), PerformanceSnapshot.id.desc())
            .first()
        )
        return self._to_dict(row) if row else None

    @staticmethod
    def _to_dict(row: PerformanceSnapshot) -> dict:
        return {
            "id": row.id,
            "profile_id": getattr(row, "profile_id", PAPER_PROFILE_ID),
            "timestamp": row.timestamp_utc,
            "source_event": row.source_event,
            "total_trades": row.total_trades,
            "wins": row.wins,
            "losses": row.losses,
            "win_rate": row.win_rate,
            "profit_factor": row.profit_factor,
            "net_r": row.net_r,
            "open_orders": row.open_orders,
            "closed_trades": row.closed_trades,
            "summary": loads_json(row.summary_json, {}),
            "portfolio": loads_json(row.portfolio_json, {}),
        }
