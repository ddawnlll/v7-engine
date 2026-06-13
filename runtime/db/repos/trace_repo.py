"""Trade trace repository for v4."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from runtime.db.models import TradeTrace
from runtime.db.repos._helpers import loads_json
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID


class TraceRepository:
    def save_trace(self, session: Session, payload: dict) -> dict:
        payload = {
            **payload,
            "profile_id": str(payload.get("profile_id") or PAPER_PROFILE_ID),
            "resolved_config_hash": str(payload.get("resolved_config_hash") or ""),
        }
        row = session.query(TradeTrace).filter(TradeTrace.trace_id == payload["trace_id"]).one_or_none()
        if row is None:
            row = TradeTrace(**payload)
            session.add(row)
        else:
            for key, value in payload.items():
                setattr(row, key, value)
        session.commit()
        return self._to_dict(row)

    def list_traces(
        self,
        session: Session,
        *,
        limit: int = 250,
        run_id: str | None = None,
        symbol: str | None = None,
        event_type: str | None = None,
        decision: str | None = None,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> list[dict]:
        query = session.query(TradeTrace).filter(TradeTrace.profile_id == profile_id)
        if run_id:
            query = query.filter(TradeTrace.run_id == run_id)
        if symbol:
            query = query.filter(TradeTrace.symbol == symbol.upper())
        if event_type:
            query = query.filter(TradeTrace.event_type == event_type.upper())
        if decision:
            query = query.filter(TradeTrace.decision == decision.upper())
        rows = query.order_by(TradeTrace.timestamp_utc.desc(), TradeTrace.id.desc()).limit(limit).all()
        return [self._to_dict(row) for row in rows]

    def summary_last_24h(self, session: Session, profile_id: str = PAPER_PROFILE_ID) -> dict[str, int]:
        threshold = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        rows = (
            session.query(TradeTrace)
            .filter(TradeTrace.profile_id == profile_id)
            .filter(TradeTrace.timestamp_utc >= threshold)
            .order_by(TradeTrace.id.desc())
            .all()
        )
        summary: dict[str, int] = {}
        for row in rows:
            bucket = str(row.decision or "UNKNOWN").upper()
            summary[bucket] = summary.get(bucket, 0) + 1
        return summary

    @staticmethod
    def _to_dict(row: TradeTrace) -> dict:
        return {
            "id": row.id,
            "trace_id": row.trace_id,
            "profile_id": getattr(row, "profile_id", PAPER_PROFILE_ID),
            "timestamp": row.timestamp_utc,
            "run_id": row.run_id,
            "event_type": row.event_type,
            "symbol": row.symbol,
            "interval": row.interval,
            "mode": row.mode,
            "direction": row.direction,
            "confidence": row.confidence,
            "regime": row.regime,
            "source": row.source,
            "order_id": row.order_id,
            "status": row.status,
            "decision": row.decision,
            "reason_code": row.reason_code,
            "reason_text": row.reason_text,
            "details": loads_json(row.details_json, {}),
            "signal_payload": loads_json(row.signal_payload_json, {}),
            "resolved_config_hash": getattr(row, "resolved_config_hash", ""),
        }
