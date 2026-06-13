"""Portfolio repository for v4."""

from __future__ import annotations

from sqlalchemy.orm import Session

from runtime.db.models import PortfolioSnapshot
from runtime.db.repos._helpers import loads_json
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID


class PortfolioRepository:
    def save_snapshot(self, session: Session, payload: dict) -> dict:
        payload = {**payload, "profile_id": str(payload.get("profile_id") or PAPER_PROFILE_ID)}
        row = session.query(PortfolioSnapshot).filter(PortfolioSnapshot.snapshot_id == payload["snapshot_id"]).one_or_none()
        if row is None:
            row = PortfolioSnapshot(**payload)
            session.add(row)
        else:
            for key, value in payload.items():
                setattr(row, key, value)
        session.commit()
        return self._to_dict(row)

    def get_latest_snapshot(self, session: Session, profile_id: str | None = None) -> dict | None:
        query = session.query(PortfolioSnapshot)
        if profile_id:
            query = query.filter(PortfolioSnapshot.profile_id == profile_id)
        row = query.order_by(PortfolioSnapshot.created_at_utc.desc()).first()
        return self._to_dict(row) if row else None

    def list_snapshots(self, session: Session, limit: int = 100, profile_id: str | None = None) -> list[dict]:
        query = session.query(PortfolioSnapshot)
        if profile_id:
            query = query.filter(PortfolioSnapshot.profile_id == profile_id)
        rows = query.order_by(PortfolioSnapshot.created_at_utc.desc()).limit(limit).all()
        return [self._to_dict(row) for row in rows]

    @staticmethod
    def _to_dict(row: PortfolioSnapshot) -> dict:
        snapshot = loads_json(row.snapshot_json, {})
        return {
            "id": row.id,
            "snapshot_id": row.snapshot_id,
            "profile_id": getattr(row, "profile_id", PAPER_PROFILE_ID),
            "total_equity": row.total_equity,
            "cash_balance": row.cash_balance,
            "unrealized_pnl": row.unrealized_pnl,
            "realized_pnl": row.realized_pnl,
            "open_positions": row.open_positions,
            "closed_trades": row.closed_trades,
            "snapshot": snapshot,
            "execution_account_id": snapshot.get("execution_account_id"),
            "execution_routing_key": snapshot.get("execution_routing_key"),
            "execution_target_route_key": snapshot.get("execution_target_route_key"),
            "created_at_utc": row.created_at_utc,
        }
