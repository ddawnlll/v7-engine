"""Order repository for v4."""

from __future__ import annotations

from sqlalchemy.orm import Session

from runtime.db.models import Fill, Order, Position
from runtime.db.repos._helpers import loads_json
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID


class OrderRepository:
    def save_order(self, session: Session, payload: dict) -> dict:
        payload = {
            **payload,
            "profile_id": str(payload.get("profile_id") or PAPER_PROFILE_ID),
            "execution_mode": str(payload.get("execution_mode") or "PAPER"),
            "venue": str(payload.get("venue") or "INTERNAL_PAPER"),
            "origin": str(payload.get("origin") or payload.get("source") or "AUTO").upper(),
            "submission_status": str(payload.get("submission_status") or "NONE"),
            "resolved_config_hash": str(payload.get("resolved_config_hash") or ""),
        }
        row = session.query(Order).filter(Order.order_id == payload["order_id"]).one_or_none()
        if row is None:
            row = Order(**payload)
            session.add(row)
        else:
            for key, value in payload.items():
                setattr(row, key, value)
        session.commit()
        return self._order_to_dict(row)

    def get_order(self, session: Session, order_id: str, profile_id: str | None = None) -> dict | None:
        query = session.query(Order).filter(Order.order_id == order_id)
        if profile_id:
            query = query.filter(Order.profile_id == profile_id)
        row = query.one_or_none()
        return self._order_to_dict(row) if row else None

    def list_orders(self, session: Session, status: str | None = None, limit: int = 250, profile_id: str | None = None) -> list[dict]:
        query = session.query(Order)
        if status:
            query = query.filter(Order.status == status)
        if profile_id:
            query = query.filter(Order.profile_id == profile_id)
        rows = query.order_by(Order.opened_at_utc.desc()).limit(limit).all()
        return [self._order_to_dict(row) for row in rows]

    def save_fill(self, session: Session, payload: dict) -> dict:
        payload = {**payload, "profile_id": str(payload.get("profile_id") or PAPER_PROFILE_ID)}
        row = session.query(Fill).filter(Fill.fill_id == payload["fill_id"]).one_or_none()
        if row is None:
            row = Fill(**payload)
            session.add(row)
        else:
            for key, value in payload.items():
                setattr(row, key, value)
        session.commit()
        return self._fill_to_dict(row)

    def list_fills(self, session: Session, order_id: str, limit: int = 100, profile_id: str | None = None) -> list[dict]:
        query = session.query(Fill).filter(Fill.order_id == order_id)
        if profile_id:
            query = query.filter(Fill.profile_id == profile_id)
        rows = (
            query
            .order_by(Fill.filled_at_utc.asc())
            .limit(limit)
            .all()
        )
        return [self._fill_to_dict(row) for row in rows]

    def save_position(self, session: Session, payload: dict) -> dict:
        payload = {**payload, "profile_id": str(payload.get("profile_id") or PAPER_PROFILE_ID)}
        row = session.query(Position).filter(Position.position_id == payload["position_id"]).one_or_none()
        if row is None:
            row = Position(**payload)
            session.add(row)
        else:
            for key, value in payload.items():
                setattr(row, key, value)
        session.commit()
        return self._position_to_dict(row)

    def list_positions(self, session: Session, status: str | None = None, limit: int = 100, profile_id: str | None = None) -> list[dict]:
        query = session.query(Position)
        if status:
            query = query.filter(Position.status == status)
        if profile_id:
            query = query.filter(Position.profile_id == profile_id)
        rows = query.order_by(Position.opened_at_utc.desc()).limit(limit).all()
        return [self._position_to_dict(row) for row in rows]

    @staticmethod
    def _order_to_dict(row: Order) -> dict:
        payload = loads_json(row.payload_json, {})
        decision_linkage = payload.get("decision_linkage") or {}
        auto_live = payload.get("auto_live") or {}
        lifecycle_status = OrderRepository._order_lifecycle_status(
            status=row.status,
            execution_mode=getattr(row, "execution_mode", "PAPER"),
            closed_at_utc=row.closed_at_utc,
        )
        return {
            "id": row.id,
            "order_id": row.order_id,
            "profile_id": getattr(row, "profile_id", PAPER_PROFILE_ID),
            "signal_id": row.signal_id,
            "source": row.source,
            "execution_mode": getattr(row, "execution_mode", "PAPER"),
            "venue": getattr(row, "venue", "INTERNAL_PAPER"),
            "origin": getattr(row, "origin", row.source),
            "client_order_id": getattr(row, "client_order_id", None),
            "venue_order_id": getattr(row, "venue_order_id", None),
            "submission_status": getattr(row, "submission_status", "NONE"),
            "submitted_at_utc": getattr(row, "submitted_at_utc", None),
            "last_venue_update_at_utc": getattr(row, "last_venue_update_at_utc", None),
            "symbol": row.symbol,
            "interval": row.interval,
            "mode": row.mode,
            "direction": row.direction,
            "status": row.status,
            "lifecycle_status": lifecycle_status,
            "is_open": lifecycle_status == "OPEN",
            "entry": row.entry,
            "stop_loss": row.stop_loss,
            "take_profit": row.take_profit,
            "close_price": row.close_price,
            "risk_reward": row.risk_reward,
            "confidence": row.confidence,
            "opened_at_utc": row.opened_at_utc,
            "closed_at_utc": row.closed_at_utc,
            "open_timestamp": row.opened_at_utc,
            "close_timestamp": row.closed_at_utc,
            "state": row.status,
            "sl": row.stop_loss,
            "tp": row.take_profit,
            "close_reason": payload.get("close_reason"),
            "realized_pnl": payload.get("realized_pnl"),
            "realized_r": payload.get("realized_r"),
            "quantity": payload.get("quantity"),
            "fees": payload.get("fees"),
            "position_id": payload.get("position_id"),
            "signal_payload": payload.get("signal") or {},
            "risk_audit": payload.get("risk_audit") or {},
            "one_r_value": (payload.get("risk_audit") or {}).get("one_r_value"),
            "entry_r_multiple": (payload.get("risk_audit") or {}).get("entry_r_multiple"),
            "trade_risk_budget": (payload.get("risk_audit") or {}).get("trade_risk_budget"),
            "verification": payload.get("verification") or {},
            "verification_status": (payload.get("verification") or {}).get("status"),
            "verification_reason": (payload.get("verification") or {}).get("reason"),
            "verification_checked_at_utc": (payload.get("verification") or {}).get("checked_at_utc"),
            "ambiguity": payload.get("ambiguity") or {},
            "ambiguity_stage": (payload.get("ambiguity") or {}).get("stage"),
            "ambiguity_error": (payload.get("ambiguity") or {}).get("error"),
            "protection": payload.get("protection") or {},
            "protection_status": (payload.get("protection") or {}).get("status"),
            "protection_required": (payload.get("protection") or {}).get("required"),
            "protection_required_types": (payload.get("protection") or {}).get("required_types") or [],
            "protection_requested_types": (payload.get("protection") or {}).get("requested_types") or [],
            "protection_confirmed_at_utc": (payload.get("protection") or {}).get("confirmed_at_utc"),
            "protection_last_checked_at_utc": (payload.get("protection") or {}).get("last_checked_at_utc"),
            "protection_message": (payload.get("protection") or {}).get("message"),
            "protective_orders": (payload.get("protection") or {}).get("children") or [],
            "learning": payload.get("learning") or {},
            "learning_adjustments": (payload.get("learning") or {}).get("adjustments") or {},
            "confidence_before_learning": (payload.get("learning") or {}).get("confidence_before"),
            "confidence_after_learning": (payload.get("learning") or {}).get("confidence_after"),
            "probability_before_learning": (payload.get("learning") or {}).get("probability_before"),
            "probability_after_learning": (payload.get("learning") or {}).get("probability_after"),
            "execution_target": payload.get("execution_target") or {},
            "execution_account": payload.get("execution_account") or {},
            "execution_account_id": (payload.get("execution_account") or {}).get("account_id"),
            "execution_routing_key": (payload.get("execution_account") or {}).get("routing_key"),
            "execution_target_route_key": (payload.get("execution_target") or {}).get("route_key"),
            "symbol_filters": payload.get("symbol_filters") or {},
            "symbol_filter_symbol": (payload.get("symbol_filters") or {}).get("symbol"),
            "tick_size": (payload.get("symbol_filters") or {}).get("tick_size"),
            "step_size": (payload.get("symbol_filters") or {}).get("step_size"),
            "market_step_size": (payload.get("symbol_filters") or {}).get("market_step_size"),
            "min_qty": (payload.get("symbol_filters") or {}).get("min_qty"),
            "market_min_qty": (payload.get("symbol_filters") or {}).get("market_min_qty"),
            "min_notional": (payload.get("symbol_filters") or {}).get("min_notional"),
            "raw_price": (payload.get("symbol_filters") or {}).get("raw_price"),
            "normalized_price": (payload.get("symbol_filters") or {}).get("normalized_price"),
            "raw_quantity": (payload.get("symbol_filters") or {}).get("raw_quantity"),
            "normalized_quantity": (payload.get("symbol_filters") or {}).get("normalized_quantity"),
            "computed_notional": (payload.get("symbol_filters") or {}).get("computed_notional"),
            "symbol_filter_rejection_reason": (payload.get("symbol_filters") or {}).get("rejection_reason"),
            "decision_linkage": decision_linkage,
            "decision_id": decision_linkage.get("decision_id"),
            "decision_event_id": decision_linkage.get("decision_event_id"),
            "decision_request_id": decision_linkage.get("request_id"),
            "decision_run_id": decision_linkage.get("run_id"),
            "auto_live": auto_live,
            "auto_live_status": auto_live.get("status"),
            "auto_live_completion_status": auto_live.get("completion_status"),
            "auto_live_completion_safe": auto_live.get("safe_to_consider_active"),
            "auto_live_completion_reason": auto_live.get("completion_reason"),
            "payload": payload,
            "resolved_config_hash": getattr(row, "resolved_config_hash", ""),
        }

    @staticmethod
    def _order_lifecycle_status(*, status: str | None, execution_mode: str | None, closed_at_utc: str | None) -> str:
        normalized_status = str(status or "").upper()
        normalized_mode = str(execution_mode or "PAPER").upper()
        if closed_at_utc:
            return "CLOSED"
        if normalized_status in {"OPEN", "PENDING", "ORDERED", "NEW", "PARTIALLY_FILLED"}:
            return "OPEN"
        if normalized_status == "FILLED":
            return "OPEN" if normalized_mode == "LIVE" else "CLOSED"
        if normalized_status in {"CANCELED", "CANCELLED", "EXPIRED", "REJECTED", "FAILED", "CLOSED"}:
            return "CLOSED"
        return "OPEN" if normalized_mode == "LIVE" and normalized_status not in {"", "UNKNOWN"} else "CLOSED"

    @staticmethod
    def _fill_to_dict(row: Fill) -> dict:
        return {
            "id": row.id,
            "fill_id": row.fill_id,
            "profile_id": getattr(row, "profile_id", PAPER_PROFILE_ID),
            "order_id": row.order_id,
            "symbol": row.symbol,
            "direction": row.direction,
            "quantity": row.quantity,
            "price": row.price,
            "fee": row.fee,
            "filled_at_utc": row.filled_at_utc,
        }

    @staticmethod
    def _position_to_dict(row: Position) -> dict:
        payload = loads_json(row.payload_json, {})
        return {
            "id": row.id,
            "position_id": row.position_id,
            "profile_id": getattr(row, "profile_id", PAPER_PROFILE_ID),
            "symbol": row.symbol,
            "interval": row.interval,
            "mode": row.mode,
            "direction": row.direction,
            "quantity": row.quantity,
            "average_entry": row.average_entry,
            "mark_price": row.mark_price,
            "unrealized_pnl": row.unrealized_pnl,
            "status": row.status,
            "opened_at_utc": row.opened_at_utc,
            "closed_at_utc": row.closed_at_utc,
            "open_timestamp": row.opened_at_utc,
            "close_timestamp": row.closed_at_utc,
            "execution_target": payload.get("execution_target") or {},
            "execution_account": payload.get("execution_account") or {},
            "execution_account_id": (payload.get("execution_account") or {}).get("account_id"),
            "execution_routing_key": (payload.get("execution_account") or {}).get("routing_key"),
            "execution_target_route_key": (payload.get("execution_target") or {}).get("route_key"),
            "payload": payload,
        }
