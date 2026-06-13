"""Capture signal and trade attribution for engine components."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from runtime.db.models import SignalComponentAttribution, TradeComponentOutcome, TradeFailure
from runtime.db.repos._helpers import dumps_json, loads_json
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.db.session import session_scope
from runtime.services.improvement_registry_service import ImprovementRegistryService


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class DecisionAttributionService:
    FACTOR_COMPONENT_MAP = {
        "TREND": "trend_detector",
        "STRUCTURE": "structure_filter",
        "OSCILLATOR": "oscillator_gate",
        "MOMENTUM": "probability_model",
        "VOLUME": "volume_context",
    }

    def __init__(self, registry_service: ImprovementRegistryService | None = None) -> None:
        self.registry_service = registry_service or ImprovementRegistryService()

    def capture_signal_attribution(
        self,
        signal_id: str,
        run_id: str,
        components_used: list[str],
        factors: list[dict[str, Any]],
        filters: list[dict[str, Any]],
        adjustments: list[dict[str, Any]],
        *,
        signal: dict[str, Any],
        profile_id: str = PAPER_PROFILE_ID,
    ) -> list[dict[str, Any]]:
        rows = []
        seen = set()
        created_at = _utc_now_iso()
        for component_id in components_used:
            rows.append(self._row(signal_id, run_id, component_id, "PRESENCE", {}, created_at, signal, profile_id=profile_id))
            seen.add((component_id, "PRESENCE"))
        for factor in factors:
            component_id = self.FACTOR_COMPONENT_MAP.get(str(factor.get("role") or "").upper(), "probability_model")
            rows.append(self._row(signal_id, run_id, component_id, "DECISION", {
                "name": factor.get("name"),
                "signal": factor.get("signal"),
                "score": factor.get("score"),
                "weight": factor.get("weight"),
                "used": factor.get("used"),
                "reason": factor.get("reason"),
            }, created_at, signal, profile_id=profile_id))
            seen.add((component_id, "DECISION"))
        for item in filters:
            component_id = str(item.get("component_id") or "structure_filter")
            rows.append(self._row(signal_id, run_id, component_id, "DECISION", item, created_at, signal, profile_id=profile_id))
            seen.add((component_id, "DECISION"))
        for item in adjustments:
            component_id = str(item.get("component_id") or "learning_calibration")
            rows.append(self._row(signal_id, run_id, component_id, "DECISION", item, created_at, signal, profile_id=profile_id))
            seen.add((component_id, "DECISION"))
        with session_scope() as session:
            session.execute(
                delete(SignalComponentAttribution)
                .where(SignalComponentAttribution.signal_id == signal_id)
                .where(SignalComponentAttribution.profile_id == profile_id)
            )
            session.add_all([SignalComponentAttribution(**row) for row in rows])
            session.commit()
        return rows

    def capture_trade_attribution(
        self,
        order_id: str,
        signal_id: str | None,
        run_id: str,
        components_used: list[str],
        decision_summary: dict[str, Any],
        profile_id: str = PAPER_PROFILE_ID,
    ) -> list[dict[str, Any]]:
        created_at = _utc_now_iso()
        rows = [
            {
                "order_id": order_id,
                "profile_id": profile_id,
                "signal_id": signal_id,
                "run_id": run_id,
                "component_id": component_id,
                "mode": str(decision_summary.get("mode") or ""),
                "symbol": str(decision_summary.get("symbol") or ""),
                "interval": str(decision_summary.get("interval") or ""),
                "direction": str(decision_summary.get("direction") or ""),
                "regime": str(decision_summary.get("regime") or "UNKNOWN"),
                "realized_r": None,
                "confidence": _as_float(decision_summary.get("confidence")),
                "close_reason": None,
                "failure_source": None,
                "blamed_component": None,
                "payload_json": dumps_json(decision_summary),
                "created_at_utc": created_at,
            }
            for component_id in components_used
        ]
        with session_scope() as session:
            session.execute(
                delete(TradeComponentOutcome)
                .where(TradeComponentOutcome.order_id == order_id)
                .where(TradeComponentOutcome.profile_id == profile_id)
            )
            session.add_all([TradeComponentOutcome(**row) for row in rows])
            session.commit()
        return rows

    def attach_trade_outcome(
        self,
        order_id: str,
        *,
        realized_r: float | None,
        close_reason: str | None,
        realized_pnl: float | None = None,
        closed_at_utc: str | None = None,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> None:
        with session_scope() as session:
            rows = (
                session.query(TradeComponentOutcome)
                .filter(TradeComponentOutcome.order_id == order_id)
                .filter(TradeComponentOutcome.profile_id == profile_id)
                .all()
            )
            failure = (
                session.query(TradeFailure)
                .filter(TradeFailure.order_id == order_id)
                .filter(TradeFailure.profile_id == profile_id)
                .one_or_none()
            )
            for row in rows:
                row.realized_r = realized_r
                row.close_reason = close_reason
                row.failure_source = failure.failure_source if failure else None
                row.blamed_component = failure.blamed_component if failure else None
                payload = loads_json(row.payload_json, {})
                payload.update({
                    "realized_r": realized_r,
                    "realized_pnl": realized_pnl,
                    "close_reason": close_reason,
                    "failure_source": row.failure_source,
                    "blamed_component": row.blamed_component,
                    "outcome_label": "WIN" if realized_r is not None and realized_r > 0 else ("LOSS" if realized_r is not None and realized_r < 0 else "FLAT"),
                    "closed_at_utc": closed_at_utc,
                })
                row.payload_json = dumps_json(payload)
            session.commit()

    def list_signal_attribution(self, signal_id: str, profile_id: str = PAPER_PROFILE_ID) -> list[dict[str, Any]]:
        with session_scope() as session:
            rows = (
                session.query(SignalComponentAttribution)
                .filter(SignalComponentAttribution.signal_id == signal_id)
                .filter(SignalComponentAttribution.profile_id == profile_id)
                .order_by(SignalComponentAttribution.attribution_level.asc(), SignalComponentAttribution.component_id.asc())
                .all()
            )
            return [self._signal_to_dict(row) for row in rows]

    def list_trade_outcomes(self, order_id: str, profile_id: str = PAPER_PROFILE_ID) -> list[dict[str, Any]]:
        with session_scope() as session:
            rows = (
                session.query(TradeComponentOutcome)
                .filter(TradeComponentOutcome.order_id == order_id)
                .filter(TradeComponentOutcome.profile_id == profile_id)
                .all()
            )
            return [self._trade_to_dict(row) for row in rows]

    @staticmethod
    def _row(
        signal_id: str,
        run_id: str,
        component_id: str,
        level: str,
        contribution: dict[str, Any],
        created_at: str,
        signal: dict[str, Any],
        *,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict[str, Any]:
        return {
            "signal_id": signal_id,
            "profile_id": profile_id,
            "order_id": None,
            "run_id": run_id,
            "component_id": component_id,
            "attribution_level": level,
            "mode": str(signal.get("mode") or ""),
            "symbol": str(signal.get("symbol") or ""),
            "interval": str(signal.get("interval") or ""),
            "direction": str(signal.get("direction") or ""),
            "regime": str(signal.get("regime") or "UNKNOWN"),
            "contribution_json": dumps_json(contribution),
            "created_at_utc": created_at,
        }

    @staticmethod
    def _signal_to_dict(row: SignalComponentAttribution) -> dict[str, Any]:
        return {
            "id": row.id,
            "signal_id": row.signal_id,
            "profile_id": getattr(row, "profile_id", PAPER_PROFILE_ID),
            "order_id": row.order_id,
            "run_id": row.run_id,
            "component_id": row.component_id,
            "attribution_level": row.attribution_level,
            "mode": row.mode,
            "symbol": row.symbol,
            "interval": row.interval,
            "direction": row.direction,
            "regime": row.regime,
            "contribution": loads_json(row.contribution_json, {}),
            "created_at_utc": row.created_at_utc,
        }

    @staticmethod
    def _trade_to_dict(row: TradeComponentOutcome) -> dict[str, Any]:
        return {
            "id": row.id,
            "order_id": row.order_id,
            "profile_id": getattr(row, "profile_id", PAPER_PROFILE_ID),
            "signal_id": row.signal_id,
            "run_id": row.run_id,
            "component_id": row.component_id,
            "mode": row.mode,
            "symbol": row.symbol,
            "interval": row.interval,
            "direction": row.direction,
            "regime": row.regime,
            "realized_r": row.realized_r,
            "confidence": row.confidence,
            "close_reason": row.close_reason,
            "failure_source": row.failure_source,
            "blamed_component": row.blamed_component,
            "payload": loads_json(row.payload_json, {}),
            "created_at_utc": row.created_at_utc,
        }
