"""Counterfactual replay persistence."""

from __future__ import annotations

from sqlalchemy import delete, func
from sqlalchemy.orm import Session

from runtime.db.models import CounterfactualReplay
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID


class CounterfactualRepository:
    def save_replays(
        self,
        session: Session,
        order_id: str,
        replays: list[dict],
        profile_id: str = PAPER_PROFILE_ID,
    ) -> list[dict]:
        session.execute(
            delete(CounterfactualReplay)
            .where(CounterfactualReplay.order_id == order_id)
            .where(CounterfactualReplay.profile_id == profile_id)
        )
        rows = [CounterfactualReplay(**{**payload, "profile_id": str(payload.get("profile_id") or profile_id)}) for payload in replays]
        session.add_all(rows)
        session.commit()
        return [self._to_dict(row) for row in rows]

    def list_replays(self, session: Session, limit: int = 5000, profile_id: str = PAPER_PROFILE_ID) -> list[dict]:
        rows = (
            session.query(CounterfactualReplay)
            .filter(CounterfactualReplay.profile_id == profile_id)
            .order_by(CounterfactualReplay.created_at_utc.desc(), CounterfactualReplay.id.desc())
            .limit(max(1, int(limit)))
            .all()
        )
        return [self._to_dict(row) for row in rows]

    def list_replays_for_order(self, session: Session, order_id: str, profile_id: str = PAPER_PROFILE_ID) -> list[dict]:
        rows = (
            session.query(CounterfactualReplay)
            .filter(CounterfactualReplay.order_id == order_id)
            .filter(CounterfactualReplay.profile_id == profile_id)
            .order_by(CounterfactualReplay.created_at_utc.asc(), CounterfactualReplay.action_label.asc())
            .all()
        )
        return [self._to_dict(row) for row in rows]

    def list_best_actions_by_regime(self, session: Session, lookback_days: int = 30, profile_id: str = PAPER_PROFILE_ID) -> list[dict]:
        from datetime import datetime, timedelta, timezone

        threshold = (datetime.now(timezone.utc) - timedelta(days=int(lookback_days))).isoformat()
        rows = (
            session.query(
                CounterfactualReplay.learning_regime,
                CounterfactualReplay.action_label,
                func.count(CounterfactualReplay.id).label("count"),
                func.avg(CounterfactualReplay.realized_r).label("avg_realized_r"),
            )
            .filter(CounterfactualReplay.profile_id == profile_id)
            .filter(CounterfactualReplay.created_at_utc >= threshold)
            .group_by(CounterfactualReplay.learning_regime, CounterfactualReplay.action_label)
            .all()
        )
        results = [
            {
                "learning_regime": str(row.learning_regime),
                "action_label": str(row.action_label),
                "count": int(row.count or 0),
                "avg_realized_r": float(row.avg_realized_r or 0.0),
            }
            for row in rows
        ]
        results.sort(key=lambda item: (item["learning_regime"], -item["avg_realized_r"], -item["count"]))
        return results

    @staticmethod
    def _to_dict(row: CounterfactualReplay) -> dict:
        return {
            "id": row.id,
            "order_id": row.order_id,
            "profile_id": getattr(row, "profile_id", PAPER_PROFILE_ID),
            "signal_id": row.signal_id,
            "action_label": row.action_label,
            "is_actual_action": row.is_actual_action,
            "learning_regime": row.learning_regime,
            "realized_r": row.realized_r,
            "mae": row.mae,
            "mfe": row.mfe,
            "hold_minutes": row.hold_minutes,
            "outperformed_actual": row.outperformed_actual,
            "delta_r_vs_actual": row.delta_r_vs_actual,
            "created_at_utc": row.created_at_utc,
        }
