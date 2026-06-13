"""Simulation decision trace repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from runtime.db.models import SimulationDecisionTrace
from runtime.db.repos._helpers import dumps_json, loads_json


class SimulationDecisionTraceRepository:
    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def bulk_insert(self, session: Session, simulation_run_id: int, traces: Iterable[dict[str, Any]]) -> int:
        inserted = 0
        for payload in traces:
            row_payload = self._payload_to_row(simulation_run_id, payload)
            existing = session.query(SimulationDecisionTrace).filter(SimulationDecisionTrace.trace_id == row_payload["trace_id"]).one_or_none()
            if existing is not None:
                continue
            session.add(SimulationDecisionTrace(**row_payload))
            inserted += 1
        session.commit()
        return inserted

    def list_for_run(
        self,
        session: Session,
        simulation_run_id: int,
        *,
        symbol: str | None = None,
        interval: str | None = None,
        mode: str | None = None,
        direction: str | None = None,
        signal_status: str | None = None,
        runtime_filter_reason: str | None = None,
        reason: str | None = None,
        fallback_used: bool | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
        start_ts: str | None = None,
        end_ts: str | None = None,
        limit: int = 250,
        cursor: int | None = None,
        sort: str = "asc",
    ) -> dict[str, Any]:
        limit = min(max(int(limit or 250), 1), 1000)
        query = session.query(SimulationDecisionTrace).filter(SimulationDecisionTrace.simulation_run_id == simulation_run_id)
        query = self._apply_filters(
            query,
            symbol=symbol,
            interval=interval,
            mode=mode,
            direction=direction,
            signal_status=signal_status,
            runtime_filter_reason=runtime_filter_reason,
            reason=reason,
            fallback_used=fallback_used,
            min_confidence=min_confidence,
            max_confidence=max_confidence,
            start_ts=start_ts,
            end_ts=end_ts,
        )
        descending = str(sort or "asc").lower() == "desc"
        if cursor is not None:
            query = query.filter(SimulationDecisionTrace.id < cursor if descending else SimulationDecisionTrace.id > cursor)
        order = SimulationDecisionTrace.id.desc() if descending else SimulationDecisionTrace.id.asc()
        rows = query.order_by(order).limit(limit + 1).all()
        has_more = len(rows) > limit
        visible = rows[:limit]
        next_cursor = visible[-1].id if has_more and visible else None
        return {
            "items": [self._to_dict(row) for row in visible],
            "count": len(visible),
            "next_cursor": next_cursor,
            "has_more": has_more,
        }

    def summary(self, session: Session, simulation_run_id: int) -> dict[str, Any]:
        rows = session.query(SimulationDecisionTrace).filter(SimulationDecisionTrace.simulation_run_id == simulation_run_id).all()
        by_reason: dict[str, int] = {}
        by_direction: dict[str, int] = {}
        by_status: dict[str, int] = {}
        fallback_count = 0
        confidence_values: list[float] = []
        for row in rows:
            reason = row.runtime_filter_reason or row.no_trade_reason or "actionable"
            by_reason[reason] = by_reason.get(reason, 0) + 1
            direction = row.direction or "UNKNOWN"
            by_direction[direction] = by_direction.get(direction, 0) + 1
            status = row.signal_status or "UNKNOWN"
            by_status[status] = by_status.get(status, 0) + 1
            if row.fallback_used:
                fallback_count += 1
            if row.confidence is not None:
                confidence_values.append(float(row.confidence))
        return {
            "trace_count": len(rows),
            "fallback_count": fallback_count,
            "by_reason": by_reason,
            "by_direction": by_direction,
            "by_signal_status": by_status,
            "avg_confidence": (sum(confidence_values) / len(confidence_values)) if confidence_values else None,
        }

    def count_for_run(self, session: Session, simulation_run_id: int) -> int:
        return int(session.query(func.count(SimulationDecisionTrace.id)).filter(SimulationDecisionTrace.simulation_run_id == simulation_run_id).scalar() or 0)

    def all_for_run(self, session: Session, simulation_run_id: int, *, limit: int = 5000) -> list[dict[str, Any]]:
        safe_limit = min(max(int(limit or 5000), 1), 50000)
        rows = (
            session.query(SimulationDecisionTrace)
            .filter(SimulationDecisionTrace.simulation_run_id == simulation_run_id)
            .order_by(SimulationDecisionTrace.id.asc())
            .limit(safe_limit)
            .all()
        )
        return [self._to_dict(row) for row in rows]

    @staticmethod
    def _apply_filters(query, **filters):
        if filters.get("symbol"):
            query = query.filter(SimulationDecisionTrace.symbol == str(filters["symbol"]).upper())
        if filters.get("interval"):
            query = query.filter(SimulationDecisionTrace.interval == str(filters["interval"]))
        if filters.get("mode"):
            query = query.filter(SimulationDecisionTrace.mode == str(filters["mode"]).upper())
        if filters.get("direction"):
            query = query.filter(SimulationDecisionTrace.direction == str(filters["direction"]).upper())
        if filters.get("signal_status"):
            query = query.filter(SimulationDecisionTrace.signal_status == str(filters["signal_status"]).upper())
        reason = filters.get("runtime_filter_reason") or filters.get("reason")
        if reason:
            query = query.filter(SimulationDecisionTrace.runtime_filter_reason == str(reason))
        if filters.get("fallback_used") is not None:
            query = query.filter(SimulationDecisionTrace.fallback_used == bool(filters["fallback_used"]))
        if filters.get("min_confidence") is not None:
            query = query.filter(SimulationDecisionTrace.confidence >= float(filters["min_confidence"]))
        if filters.get("max_confidence") is not None:
            query = query.filter(SimulationDecisionTrace.confidence <= float(filters["max_confidence"]))
        if filters.get("start_ts"):
            query = query.filter(SimulationDecisionTrace.timestamp >= str(filters["start_ts"]))
        if filters.get("end_ts"):
            query = query.filter(SimulationDecisionTrace.timestamp <= str(filters["end_ts"]))
        return query

    def _payload_to_row(self, simulation_run_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        created_at = str(payload.get("created_at") or self._utc_now_iso())
        return {
            "simulation_run_id": int(payload.get("simulation_run_id") or simulation_run_id),
            "trace_id": str(payload.get("trace_id") or f"sim-trace-{simulation_run_id}-{created_at}"),
            "symbol": str(payload.get("symbol") or "").upper(),
            "interval": str(payload.get("interval") or ""),
            "mode": str(payload.get("mode") or "").upper(),
            "timestamp": str(payload.get("timestamp") or created_at),
            "direction": self._str_or_none(payload.get("direction")),
            "confidence": self._float_or_none(payload.get("confidence")),
            "signal_status": self._str_or_none(payload.get("signal_status")),
            "selected_action": self._str_or_none(payload.get("selected_action")),
            "selected_head": self._str_or_none(payload.get("selected_head")),
            "runtime_filter_reason": self._str_or_none(payload.get("runtime_filter_reason")),
            "no_trade_reason": self._str_or_none(payload.get("no_trade_reason")),
            "skip_family": self._str_or_none(payload.get("skip_family")),
            "fallback_used": bool(payload.get("fallback_used")),
            "fallback_reason": self._str_or_none(payload.get("fallback_reason")),
            "analysis_error": self._str_or_none(payload.get("analysis_error")),
            "data_error": self._str_or_none(payload.get("data_error")),
            "insufficient_history": bool(payload.get("insufficient_history")),
            "confidence_raw": self._float_or_none(payload.get("confidence_raw")),
            "confidence_final": self._float_or_none(payload.get("confidence_final")),
            "probability_long_raw": self._float_or_none(payload.get("probability_long_raw")),
            "probability_short_raw": self._float_or_none(payload.get("probability_short_raw")),
            "probability_no_trade_raw": self._float_or_none(payload.get("probability_no_trade_raw")),
            "probability_long_final": self._float_or_none(payload.get("probability_long_final")),
            "probability_short_final": self._float_or_none(payload.get("probability_short_final")),
            "probability_no_trade_final": self._float_or_none(payload.get("probability_no_trade_final")),
            "entry_price": self._float_or_none(payload.get("entry_price")),
            "stop_loss": self._float_or_none(payload.get("stop_loss")),
            "take_profit": self._float_or_none(payload.get("take_profit")),
            "summary": self._str_or_none(payload.get("summary")),
            "analyzer_metadata_json": dumps_json(payload.get("analyzer_metadata") or {}),
            "runtime_context_json": dumps_json(payload.get("runtime_context") or {}),
            "snapshot_metadata_json": dumps_json(payload.get("snapshot_metadata") or {}),
            "created_at": created_at,
        }

    @staticmethod
    def _to_dict(row: SimulationDecisionTrace) -> dict[str, Any]:
        return {
            "id": row.id,
            "simulation_run_id": row.simulation_run_id,
            "trace_id": row.trace_id,
            "symbol": row.symbol,
            "interval": row.interval,
            "mode": row.mode,
            "timestamp": row.timestamp,
            "direction": row.direction,
            "confidence": row.confidence,
            "signal_status": row.signal_status,
            "selected_action": row.selected_action,
            "selected_head": row.selected_head,
            "runtime_filter_reason": row.runtime_filter_reason,
            "no_trade_reason": row.no_trade_reason,
            "skip_family": row.skip_family,
            "fallback_used": row.fallback_used,
            "fallback_reason": row.fallback_reason,
            "analysis_error": row.analysis_error,
            "data_error": row.data_error,
            "insufficient_history": row.insufficient_history,
            "confidence_raw": row.confidence_raw,
            "confidence_final": row.confidence_final,
            "probability_long_raw": row.probability_long_raw,
            "probability_short_raw": row.probability_short_raw,
            "probability_no_trade_raw": row.probability_no_trade_raw,
            "probability_long_final": row.probability_long_final,
            "probability_short_final": row.probability_short_final,
            "probability_no_trade_final": row.probability_no_trade_final,
            "entry_price": row.entry_price,
            "stop_loss": row.stop_loss,
            "take_profit": row.take_profit,
            "summary": row.summary,
            "analyzer_metadata": loads_json(row.analyzer_metadata_json, {}),
            "runtime_context": loads_json(row.runtime_context_json, {}),
            "snapshot_metadata": loads_json(row.snapshot_metadata_json, {}),
            "created_at": row.created_at,
        }

    @staticmethod
    def _str_or_none(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value)
        return text if text != "" else None

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except Exception:
            return None
