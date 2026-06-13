"""Repositories for self-learning memories and runs."""

from __future__ import annotations

from sqlalchemy.orm import Session

from runtime.db.models import SelfLearningRun, TradeMemory
from runtime.db.repos._helpers import loads_json


class TradeMemoryRepository:
    def save_trade_memory(self, session: Session, payload: dict) -> dict:
        row = session.query(TradeMemory).filter(TradeMemory.signal_id == payload["signal_id"]).one_or_none()
        if row is None:
            row = TradeMemory(**payload)
            session.add(row)
        else:
            for key, value in payload.items():
                setattr(row, key, value)
        session.commit()
        return self._memory_to_dict(row)

    def get_trade_memory(self, session: Session, signal_id: str) -> dict | None:
        row = session.query(TradeMemory).filter(TradeMemory.signal_id == signal_id).one_or_none()
        return self._memory_to_dict(row) if row else None

    def list_trade_memories(
        self,
        session: Session,
        *,
        lookback_days: int | None = None,
        regime: str | None = None,
        result_label: str | None = None,
        symbol: str | None = None,
        mode: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        query = session.query(TradeMemory)
        if regime:
            query = query.filter(TradeMemory.learning_regime == regime)
        if result_label:
            query = query.filter(TradeMemory.result_label == result_label)
        if symbol:
            query = query.filter(TradeMemory.context_json.contains(f'"symbol": "{symbol}"'))
        if mode:
            query = query.filter(TradeMemory.context_json.contains(f'"mode": "{mode}"'))
        if lookback_days and lookback_days > 0:
            from datetime import datetime, timedelta, timezone

            threshold = (datetime.now(timezone.utc) - timedelta(days=int(lookback_days))).isoformat()
            query = query.filter(TradeMemory.created_at_utc >= threshold)
        rows = query.order_by(TradeMemory.created_at_utc.desc()).limit(limit).all()
        return [self._memory_to_dict(row) for row in rows]

    def search_similar_memories(
        self,
        session: Session,
        *,
        regime: str | None = None,
        result_label: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        query = session.query(TradeMemory)
        if regime:
            query = query.filter(TradeMemory.learning_regime == regime)
        if result_label:
            query = query.filter(TradeMemory.result_label == result_label)
        rows = query.order_by(TradeMemory.created_at_utc.desc()).limit(limit).all()
        return [self._memory_to_dict(row) for row in rows]

    def save_self_learning_run(self, session: Session, payload: dict) -> dict:
        row = SelfLearningRun(**payload)
        session.add(row)
        session.commit()
        return self._run_to_dict(row)

    def update_self_learning_run(self, session: Session, run_id: int, payload: dict) -> dict | None:
        row = session.query(SelfLearningRun).filter(SelfLearningRun.id == run_id).one_or_none()
        if row is None:
            return None
        for key, value in payload.items():
            setattr(row, key, value)
        session.commit()
        return self._run_to_dict(row)

    def list_self_learning_runs(self, session: Session, limit: int = 20) -> list[dict]:
        rows = session.query(SelfLearningRun).order_by(SelfLearningRun.started_at_utc.desc()).limit(limit).all()
        return [self._run_to_dict(row) for row in rows]

    @staticmethod
    def _memory_to_dict(row: TradeMemory) -> dict:
        return {
            "id": row.id,
            "signal_id": row.signal_id,
            "order_id": row.order_id,
            "learning_regime": row.learning_regime,
            "regime_confidence": row.regime_confidence,
            "regime_stability_score": row.regime_stability_score,
            "regime_version": row.regime_version,
            "context": loads_json(row.context_json, {}),
            "outcome": loads_json(row.outcome_json, {}),
            "summary_text": row.summary_text,
            "embedding": row.embedding,
            "result_label": row.result_label,
            "realized_r": row.realized_r,
            "mae": row.mae,
            "mfe": row.mfe,
            "hold_minutes": row.hold_minutes,
            "decay_weight": row.decay_weight,
            "created_at_utc": row.created_at_utc,
        }

    @staticmethod
    def _run_to_dict(row: SelfLearningRun) -> dict:
        return {
            "id": row.id,
            "run_type": row.run_type,
            "status": row.status,
            "started_at_utc": row.started_at_utc,
            "completed_at_utc": row.completed_at_utc,
            "samples_processed": row.samples_processed,
            "notes": row.notes,
        }
