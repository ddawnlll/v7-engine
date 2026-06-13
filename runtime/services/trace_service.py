"""Trace logging/query service for v4."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.db.repos.trace_repo import TraceRepository
from runtime.db.session import session_scope


def _signal_payload(signal: dict[str, Any] | None) -> dict[str, Any]:
    if not signal:
        return {}
    advanced = signal.get("advanced_analysis") or {}
    decision_path = advanced.get("decision_path") if isinstance(advanced, dict) else {}
    learning_adjustments = advanced.get("learning_adjustments") if isinstance(advanced, dict) else {}
    self_learning = advanced.get("self_learning") if isinstance(advanced, dict) else {}
    probability_model = advanced.get("probability_model") if isinstance(advanced, dict) else {}
    return {
        "signal_id": signal.get("signal_id"),
        "profile_id": signal.get("profile_id"),
        "symbol": signal.get("symbol"),
        "interval": signal.get("interval"),
        "mode": signal.get("mode"),
        "direction": signal.get("direction"),
        "confidence": signal.get("confidence"),
        "confidence_raw": signal.get("confidence_raw"),
        "confidence_final": signal.get("confidence_final"),
        "probability": signal.get("probability"),
        "probability_raw": signal.get("probability_raw"),
        "probability_final": signal.get("probability_final"),
        "regime": signal.get("regime"),
        "summary": signal.get("summary"),
        "no_trade_reason": signal.get("no_trade_reason"),
        "factors": signal.get("factors") or [],
        "advanced_analysis": {
            "adapter": advanced.get("adapter") if isinstance(advanced, dict) else {},
            "decision_path": decision_path if isinstance(decision_path, dict) else {},
            "probability_model": probability_model if isinstance(probability_model, dict) else {},
            "learning_adjustments": learning_adjustments if isinstance(learning_adjustments, dict) else {},
            "self_learning": self_learning if isinstance(self_learning, dict) else {},
        },
    }


class TraceService:
    def __init__(self, trace_repo: TraceRepository | None = None) -> None:
        self.trace_repo = trace_repo or TraceRepository()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def log_event(
        self,
        event_type: str,
        *,
        run_id: str | None = None,
        signal: dict[str, Any] | None = None,
        source: str | None = None,
        order_id: str | None = None,
        status: str | None = None,
        decision: str | None = None,
        reason_code: str | None = None,
        reason_text: str | None = None,
        details: dict[str, Any] | None = None,
        timestamp_utc: str | None = None,
        profile_id: str = PAPER_PROFILE_ID,
        resolved_config_hash: str = "",
    ) -> dict[str, Any]:
        signal_data = _signal_payload(signal)
        resolved_profile_id = str(signal_data.get("profile_id") or profile_id or PAPER_PROFILE_ID)
        resolved_hash = str((signal or {}).get("resolved_config_hash") or resolved_config_hash or "")
        with session_scope() as session:
            return self.trace_repo.save_trace(
                session,
                {
                    "trace_id": f"trace-{uuid4().hex}",
                    "profile_id": resolved_profile_id,
                    "timestamp_utc": timestamp_utc or self._utc_now_iso(),
                    "run_id": run_id,
                    "event_type": event_type.upper(),
                    "symbol": signal_data.get("symbol"),
                    "interval": signal_data.get("interval"),
                    "mode": signal_data.get("mode"),
                    "direction": signal_data.get("direction"),
                    "confidence": signal_data.get("confidence"),
                    "regime": signal_data.get("regime"),
                    "source": source,
                    "order_id": order_id,
                    "status": status,
                    "decision": decision.upper() if decision else None,
                    "reason_code": (reason_code or event_type).upper(),
                    "reason_text": reason_text,
                    "details_json": json.dumps(details or {}),
                    "signal_payload_json": json.dumps(signal_data),
                    "resolved_config_hash": resolved_hash,
                },
            )

    def get_snapshot(
        self,
        *,
        limit: int = 250,
        run_id: str | None = None,
        symbol: str | None = None,
        event_type: str | None = None,
        decision: str | None = None,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict[str, Any]:
        with session_scope() as session:
            items = self.trace_repo.list_traces(
                session,
                limit=limit,
                run_id=run_id,
                symbol=symbol,
                event_type=event_type,
                decision=decision,
                profile_id=profile_id,
            )
            summary = self.trace_repo.summary_last_24h(session, profile_id=profile_id)
        return {"profile_id": profile_id, "items": items, "count": len(items), "summary": summary}

    def get_export_rows(
        self,
        *,
        limit: int = 1000,
        run_id: str | None = None,
        symbol: str | None = None,
        event_type: str | None = None,
        decision: str | None = None,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> list[dict[str, Any]]:
        snapshot = self.get_snapshot(limit=limit, run_id=run_id, symbol=symbol, event_type=event_type, decision=decision, profile_id=profile_id)
        rows: list[dict[str, Any]] = []
        for item in snapshot["items"]:
            payload = item.get("signal_payload") or {}
            rows.append(
                {
                    "trace_id": item.get("trace_id"),
                    "timestamp": item.get("timestamp"),
                    "run_id": item.get("run_id"),
                    "event_type": item.get("event_type"),
                    "decision": item.get("decision"),
                    "status": item.get("status"),
                    "source": item.get("source"),
                    "order_id": item.get("order_id"),
                    "symbol": item.get("symbol"),
                    "interval": item.get("interval"),
                    "mode": item.get("mode"),
                    "direction": item.get("direction"),
                    "confidence": item.get("confidence"),
                    "confidence_raw": payload.get("confidence_raw") if isinstance(payload, dict) else None,
                    "confidence_final": payload.get("confidence_final") if isinstance(payload, dict) else None,
                    "probability": payload.get("probability") if isinstance(payload, dict) else None,
                    "probability_raw": payload.get("probability_raw") if isinstance(payload, dict) else None,
                    "probability_final": payload.get("probability_final") if isinstance(payload, dict) else None,
                    "regime": item.get("regime"),
                    "reason_code": item.get("reason_code"),
                    "reason_text": item.get("reason_text"),
                    "summary": payload.get("summary") if isinstance(payload, dict) else None,
                    "no_trade_reason": payload.get("no_trade_reason") if isinstance(payload, dict) else None,
                    "factors_json": json.dumps(payload.get("factors") or []),
                    "details_json": json.dumps(item.get("details") or {}),
                    "signal_payload_json": json.dumps(payload),
                }
            )
        rows.reverse()
        return rows

    def get_runtime_logs(self, *, limit: int = 100, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any]:
        snapshot = self.get_snapshot(limit=limit, profile_id=profile_id)
        items = []
        for item in snapshot["items"]:
            event_type = str(item.get("event_type") or "")
            reason_code = str(item.get("reason_code") or "").upper()
            reason_text = str(item.get("reason_text") or event_type or "Event")
            severity = "INFO"
            source = f"{event_type} {reason_code} {item.get('decision') or ''} {reason_text}".upper()
            if "ERROR" in source or "FAILED" in source or "DEAD" in source:
                severity = "ERROR"
            elif "WARN" in source or "SKIP" in source:
                severity = "WARN"
            elif "SIGNAL" in source or "BUY" in source or "SELL" in source:
                severity = "SIGNAL"
            elif "ORDER" in source or "TP" in source or "SL" in source or "TRADE" in source:
                severity = "TRADE"
            elif "SCAN" in source or "QUEUE" in source:
                severity = "SCAN"
            category = reason_code if reason_code and reason_code != event_type else (event_type or "TRACE")
            message = f"{reason_code}: {reason_text}" if reason_code and reason_code not in reason_text.upper() else reason_text
            items.append(
                {
                    "severity": severity,
                    "category": category,
                    "reason_code": reason_code or None,
                    "symbol": item.get("symbol"),
                    "message": message,
                    "timestamp_utc": item.get("timestamp"),
                }
            )
        return {"items": items}
