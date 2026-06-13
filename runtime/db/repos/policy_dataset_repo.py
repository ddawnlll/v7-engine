"""Policy dataset persistence for self-learning."""

from __future__ import annotations

from sqlalchemy.orm import Session

from runtime.db.models import PolicyExample
from runtime.db.repos._helpers import loads_json


class PolicyDatasetRepository:
    def save_policy_examples(self, session: Session, rows: list[dict]) -> list[dict]:
        saved: list[dict] = []
        for payload in rows:
            row = session.query(PolicyExample).filter(PolicyExample.signal_id == payload["signal_id"]).one_or_none()
            if row is None:
                row = PolicyExample(**payload)
                session.add(row)
            else:
                for key, value in payload.items():
                    setattr(row, key, value)
            saved.append(payload)
        session.commit()
        return [self.get_policy_example(session, str(row["signal_id"])) for row in saved if row.get("signal_id")]

    def get_policy_example(self, session: Session, signal_id: str) -> dict | None:
        row = session.query(PolicyExample).filter(PolicyExample.signal_id == signal_id).one_or_none()
        return self._to_dict(row) if row else None

    def list_policy_examples(self, session: Session, lookback_days: int = 30, regime: str | None = None, limit: int = 100) -> list[dict]:
        from datetime import datetime, timedelta, timezone

        threshold = (datetime.now(timezone.utc) - timedelta(days=int(lookback_days))).isoformat()
        query = session.query(PolicyExample).filter(PolicyExample.created_at_utc >= threshold)
        if regime:
            query = query.filter(PolicyExample.learning_regime == regime)
        rows = query.order_by(PolicyExample.created_at_utc.desc()).limit(limit).all()
        return [self._to_dict(row) for row in rows]

    def get_regime_action_stats(self, session: Session, lookback_days: int = 30) -> list[dict]:
        rows = self.list_policy_examples(session, lookback_days=lookback_days, limit=5000)
        stats: dict[tuple[str, str], dict] = {}
        for row in rows:
            for candidate in row.get("candidate_actions") or []:
                key = (str(row.get("learning_regime") or ""), str(candidate.get("action_label") or ""))
                bucket = stats.setdefault(key, {
                    "learning_regime": key[0],
                    "action_label": key[1],
                    "count": 0,
                    "avg_realized_r": 0.0,
                    "_sum": 0.0,
                })
                bucket["count"] += 1
                bucket["_sum"] += float(candidate.get("realized_r") or 0.0)
        for bucket in stats.values():
            count = max(1, int(bucket["count"]))
            bucket["avg_realized_r"] = bucket["_sum"] / count
            bucket.pop("_sum", None)
        return sorted(stats.values(), key=lambda item: (item["learning_regime"], -item["avg_realized_r"], -item["count"]))

    @staticmethod
    def _to_dict(row: PolicyExample) -> dict:
        return {
            "id": row.id,
            "signal_id": row.signal_id,
            "order_id": row.order_id,
            "learning_regime": row.learning_regime,
            "context": loads_json(row.context_json, {}),
            "candidate_actions": loads_json(row.candidate_actions_json, []),
            "best_action_label": row.best_action_label,
            "best_action_realized_r": row.best_action_realized_r,
            "actual_action_label": row.actual_action_label,
            "actual_action_realized_r": row.actual_action_realized_r,
            "regret_vs_best": row.regret_vs_best,
            "provisional": row.provisional,
            "created_at_utc": row.created_at_utc,
        }
