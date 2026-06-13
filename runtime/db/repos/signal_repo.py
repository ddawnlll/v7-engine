"""Signal repository for v4."""

from __future__ import annotations

from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.orm import Session, load_only

from runtime.db.models import Signal
from runtime.db.repos._helpers import loads_json
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID


class SignalRepository:
    COLUMN_DEFAULTS = {
        "features_json": "{}",
        "factors_json": "[]",
        "audit_json": "{}",
        "snapshot_json": "{}",
        "engine_name": "v4_default",
        "engine_version": "v4-phase25",
        "engine_schema_version": "analysis_result.v1",
        "engine_fallback_used": False,
        "profile_id": PAPER_PROFILE_ID,
    }

    def save_signal(self, session: Session, payload: dict) -> dict:
        available_columns = self._available_columns(session)
        existing = self._base_query(session, available_columns).filter(Signal.signal_id == payload["signal_id"]).one_or_none()
        filtered_payload = {key: value for key, value in payload.items() if key in available_columns}
        for key, value in self.COLUMN_DEFAULTS.items():
            if key in available_columns and key not in filtered_payload:
                filtered_payload[key] = value

        if existing is None:
            columns_sql = ", ".join(filtered_payload.keys())
            values_sql = ", ".join(f":{key}" for key in filtered_payload.keys())
            session.execute(
                text(f"INSERT INTO {Signal.__tablename__} ({columns_sql}) VALUES ({values_sql})"),
                filtered_payload,
            )
        else:
            session.execute(
                text(
                    f"UPDATE {Signal.__tablename__} "
                    f"SET {', '.join(f'{key} = :{key}' for key in filtered_payload.keys())} "
                    "WHERE signal_id = :_signal_id"
                ),
                {
                    **filtered_payload,
                    "_signal_id": payload["signal_id"],
                },
            )
        session.commit()

        row = self._base_query(session, available_columns).filter(Signal.signal_id == payload["signal_id"]).one_or_none()
        if row is None:
            raise RuntimeError(f"Signal {payload['signal_id']} was not persisted")
        return self._to_dict(row, available_columns)

    def get_signal(self, session: Session, signal_id: str) -> dict | None:
        available_columns = self._available_columns(session)
        row = self._base_query(session, available_columns).filter(Signal.signal_id == signal_id).one_or_none()
        return self._to_dict(row, available_columns) if row else None

    def list_signals(self, session: Session, run_id: str | None = None, limit: int = 100) -> list[dict]:
        available_columns = self._available_columns(session)
        query = self._base_query(session, available_columns)
        if run_id:
            query = query.filter(Signal.run_id == run_id)
        rows = query.order_by(Signal.created_at_utc.desc()).limit(limit).all()
        return [self._to_dict(row, available_columns) for row in rows]

    def get_audit_trail(self, session: Session, signal_id: str) -> dict | None:
        available_columns = self._available_columns(session)
        row = self._base_query(session, available_columns).filter(Signal.signal_id == signal_id).one_or_none()
        if row is None:
            return None
        if "audit_json" not in available_columns:
            return {}
        return loads_json(getattr(row, "audit_json", "{}"), {})

    @staticmethod
    def _available_columns(session: Session) -> set[str]:
        return {
            column["name"]
            for column in sa_inspect(session.get_bind()).get_columns(Signal.__tablename__)
        }

    @staticmethod
    def _base_query(session: Session, available_columns: set[str]):
        orm_columns = [
            getattr(Signal, column.name)
            for column in Signal.__table__.columns
            if column.name in available_columns
        ]
        query = session.query(Signal)
        if orm_columns:
            query = query.options(load_only(*orm_columns))
        return query

    @staticmethod
    def _to_dict(row: Signal, available_columns: set[str]) -> dict:
        return {
            "id": row.id,
            "signal_id": row.signal_id,
            "profile_id": getattr(row, "profile_id", PAPER_PROFILE_ID) if "profile_id" in available_columns else PAPER_PROFILE_ID,
            "run_id": row.run_id,
            "symbol": row.symbol,
            "interval": row.interval,
            "mode": row.mode,
            "direction": row.direction,
            "confidence": row.confidence,
            "regime": row.regime,
            "trend": row.trend,
            "trend_strength": row.trend_strength,
            "summary": row.summary,
            "no_trade_reason": row.no_trade_reason,
            "strategy_version": row.strategy_version,
            "engine_name": getattr(row, "engine_name", "v4_default") if "engine_name" in available_columns else "v4_default",
            "engine_version": getattr(row, "engine_version", "v4-phase25") if "engine_version" in available_columns else "v4-phase25",
            "engine_schema_version": getattr(row, "engine_schema_version", "analysis_result.v1") if "engine_schema_version" in available_columns else "analysis_result.v1",
            "engine_fallback_used": bool(getattr(row, "engine_fallback_used", False)) if "engine_fallback_used" in available_columns else False,
            "snapshot": loads_json(row.snapshot_json, {}),
            "features": loads_json(getattr(row, "features_json", "{}"), {}) if "features_json" in available_columns else {},
            "factors": loads_json(row.factors_json, []),
            "audit": loads_json(getattr(row, "audit_json", "{}"), {}) if "audit_json" in available_columns else {},
            "created_at_utc": row.created_at_utc,
        }
