"""Profile-owned venue-state repository for Binance USDⓈ-M read-only storage."""

from __future__ import annotations

from sqlalchemy.orm import Session

from runtime.db.models import ProfileAccount, VenueBalance, VenueOrder, VenuePosition
from runtime.db.repos._helpers import dumps_json, loads_json


class VenueStateRepository:
    def save_account_summary(self, session: Session, payload: dict) -> dict:
        account_id = str(payload["account_id"])
        row = session.query(ProfileAccount).filter(ProfileAccount.account_id == account_id).one_or_none()
        if row is None:
            row = ProfileAccount(**self._account_payload(payload))
            session.add(row)
        else:
            for key, value in self._account_payload(payload).items():
                setattr(row, key, value)
        session.commit()
        session.refresh(row)
        return self._account_to_dict(row)

    def get_account_summary(self, session: Session, profile_id: str) -> dict | None:
        row = (
            session.query(ProfileAccount)
            .filter(ProfileAccount.profile_id == str(profile_id or ""))
            .order_by(ProfileAccount.account_key.asc(), ProfileAccount.id.asc())
            .first()
        )
        return self._account_to_dict(row) if row else None

    def replace_balances(self, session: Session, profile_id: str, account_id: str, items: list[dict]) -> list[dict]:
        session.query(VenueBalance).filter(VenueBalance.profile_id == profile_id).filter(VenueBalance.account_id == account_id).delete()
        rows: list[VenueBalance] = []
        for payload in items:
            row = VenueBalance(**self._balance_payload(payload))
            session.add(row)
            rows.append(row)
        session.commit()
        return [self._balance_to_dict(row) for row in rows]

    def upsert_balance(self, session: Session, payload: dict) -> dict:
        balance_id = str(payload["balance_id"])
        row = session.query(VenueBalance).filter(VenueBalance.balance_id == balance_id).one_or_none()
        if row is None:
            row = VenueBalance(**self._balance_payload(payload))
            session.add(row)
        else:
            for key, value in self._balance_payload(payload).items():
                setattr(row, key, value)
        session.commit()
        session.refresh(row)
        return self._balance_to_dict(row)

    def list_balances(self, session: Session, profile_id: str, account_id: str | None = None) -> list[dict]:
        query = session.query(VenueBalance).filter(VenueBalance.profile_id == str(profile_id or ""))
        if account_id:
            query = query.filter(VenueBalance.account_id == str(account_id))
        rows = query.order_by(VenueBalance.asset.asc()).all()
        return [self._balance_to_dict(row) for row in rows]

    def replace_positions(self, session: Session, profile_id: str, account_id: str, items: list[dict]) -> list[dict]:
        session.query(VenuePosition).filter(VenuePosition.profile_id == profile_id).filter(VenuePosition.account_id == account_id).delete()
        rows: list[VenuePosition] = []
        for payload in items:
            row = VenuePosition(**self._position_payload(payload))
            session.add(row)
            rows.append(row)
        session.commit()
        return [self._position_to_dict(row) for row in rows]

    def upsert_position(self, session: Session, payload: dict) -> dict:
        position_id = str(payload["position_id"])
        row = session.query(VenuePosition).filter(VenuePosition.position_id == position_id).one_or_none()
        if row is None:
            row = VenuePosition(**self._position_payload(payload))
            session.add(row)
        else:
            for key, value in self._position_payload(payload).items():
                setattr(row, key, value)
        session.commit()
        session.refresh(row)
        return self._position_to_dict(row)

    def get_position(self, session: Session, profile_id: str, *, symbol: str, position_side: str, account_id: str | None = None) -> dict | None:
        query = session.query(VenuePosition).filter(VenuePosition.profile_id == str(profile_id or "")).filter(VenuePosition.symbol == str(symbol or "")).filter(VenuePosition.position_side == str(position_side or "BOTH"))
        if account_id:
            query = query.filter(VenuePosition.account_id == str(account_id))
        row = query.one_or_none()
        return self._position_to_dict(row) if row else None

    def delete_position(self, session: Session, profile_id: str, *, symbol: str, position_side: str, account_id: str | None = None) -> bool:
        query = session.query(VenuePosition).filter(VenuePosition.profile_id == str(profile_id or "")).filter(VenuePosition.symbol == str(symbol or "")).filter(VenuePosition.position_side == str(position_side or "BOTH"))
        if account_id:
            query = query.filter(VenuePosition.account_id == str(account_id))
        row = query.one_or_none()
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True

    def list_positions(self, session: Session, profile_id: str, account_id: str | None = None) -> list[dict]:
        query = session.query(VenuePosition).filter(VenuePosition.profile_id == str(profile_id or ""))
        if account_id:
            query = query.filter(VenuePosition.account_id == str(account_id))
        rows = query.order_by(VenuePosition.symbol.asc(), VenuePosition.position_side.asc()).all()
        return [self._position_to_dict(row) for row in rows]

    def upsert_order(self, session: Session, payload: dict) -> dict:
        order_key = str(payload["order_key"])
        row = session.query(VenueOrder).filter(VenueOrder.order_key == order_key).one_or_none()
        if row is None:
            row = VenueOrder(**self._order_payload(payload))
            session.add(row)
        else:
            for key, value in self._order_payload(payload).items():
                setattr(row, key, value)
        session.commit()
        session.refresh(row)
        return self._order_to_dict(row)

    def upsert_open_orders(self, session: Session, items: list[dict]) -> list[dict]:
        saved: list[dict] = []
        for payload in items:
            saved.append(self.upsert_order(session, payload))
        return saved

    def list_open_orders(self, session: Session, profile_id: str, account_id: str | None = None) -> list[dict]:
        open_statuses = {"NEW", "PARTIALLY_FILLED", "PENDING_CANCEL"}
        query = (
            session.query(VenueOrder)
            .filter(VenueOrder.profile_id == str(profile_id or ""))
            .filter(VenueOrder.status.in_(open_statuses))
        )
        if account_id:
            query = query.filter(VenueOrder.account_id == str(account_id))
        rows = query.order_by(VenueOrder.updated_at_utc.desc(), VenueOrder.symbol.asc()).all()
        return [self._order_to_dict(row) for row in rows]

    def get_order(self, session: Session, profile_id: str, *, symbol: str, venue_order_id: str | None = None, client_order_id: str | None = None) -> dict | None:
        query = session.query(VenueOrder).filter(VenueOrder.profile_id == str(profile_id or "")).filter(VenueOrder.symbol == str(symbol or ""))
        if venue_order_id:
            query = query.filter(VenueOrder.venue_order_id == str(venue_order_id))
        elif client_order_id:
            query = query.filter(VenueOrder.client_order_id == str(client_order_id))
        else:
            return None
        row = query.one_or_none()
        return self._order_to_dict(row) if row else None

    @staticmethod
    def _account_payload(payload: dict) -> dict:
        return {
            "account_id": str(payload["account_id"]),
            "profile_id": str(payload["profile_id"]),
            "account_key": str(payload.get("account_key") or "default"),
            "account_type": str(payload.get("account_type") or "LIVE_FUTURES_USDM_READ_ONLY"),
            "venue_account_key": payload.get("venue_account_key"),
            "balance_ccy": str(payload.get("balance_ccy") or "USDT"),
            "balance": float(payload.get("balance") or 0.0),
            "available_balance": float(payload.get("available_balance") or 0.0),
            "equity": float(payload.get("equity") or 0.0),
            "margin_used": float(payload.get("margin_used") or 0.0),
            "payload_json": dumps_json(payload.get("payload") or {}),
            "as_of_utc": str(payload.get("as_of_utc") or ""),
            "created_at_utc": str(payload.get("created_at_utc") or payload.get("as_of_utc") or ""),
            "updated_at_utc": str(payload.get("updated_at_utc") or payload.get("as_of_utc") or ""),
        }

    @staticmethod
    def _balance_payload(payload: dict) -> dict:
        return {
            "balance_id": str(payload["balance_id"]),
            "profile_id": str(payload["profile_id"]),
            "account_id": str(payload["account_id"]),
            "venue": str(payload.get("venue") or "BINANCE_USDM"),
            "asset": str(payload["asset"]),
            "balance": float(payload.get("balance") or 0.0),
            "available_balance": float(payload.get("available_balance") or 0.0),
            "margin_balance": float(payload.get("margin_balance") or 0.0),
            "cross_wallet_balance": float(payload.get("cross_wallet_balance") or 0.0),
            "cross_unrealized_pnl": float(payload.get("cross_unrealized_pnl") or 0.0),
            "max_withdraw_amount": float(payload.get("max_withdraw_amount") or 0.0),
            "margin_available": bool(payload.get("margin_available")),
            "update_time_utc": payload.get("update_time_utc"),
            "synced_at_utc": str(payload.get("synced_at_utc") or ""),
            "payload_json": dumps_json(payload.get("payload") or {}),
        }

    @staticmethod
    def _position_payload(payload: dict) -> dict:
        return {
            "position_id": str(payload["position_id"]),
            "profile_id": str(payload["profile_id"]),
            "account_id": str(payload["account_id"]),
            "venue": str(payload.get("venue") or "BINANCE_USDM"),
            "symbol": str(payload["symbol"]),
            "position_side": str(payload.get("position_side") or "BOTH"),
            "status": str(payload.get("status") or "OPEN"),
            "quantity": float(payload.get("quantity") or 0.0),
            "entry_price": float(payload.get("entry_price") or 0.0),
            "break_even_price": float(payload.get("break_even_price") or 0.0),
            "mark_price": float(payload.get("mark_price") or 0.0),
            "unrealized_pnl": float(payload.get("unrealized_pnl") or 0.0),
            "liquidation_price": float(payload.get("liquidation_price") or 0.0),
            "leverage": float(payload.get("leverage") or 0.0),
            "margin_type": str(payload.get("margin_type") or "cross"),
            "isolated": bool(payload.get("isolated")),
            "isolated_margin": float(payload.get("isolated_margin") or 0.0),
            "notional": float(payload.get("notional") or 0.0),
            "max_notional_value": float(payload.get("max_notional_value") or 0.0),
            "update_time_utc": payload.get("update_time_utc"),
            "synced_at_utc": str(payload.get("synced_at_utc") or ""),
            "payload_json": dumps_json(payload.get("payload") or {}),
        }

    @staticmethod
    def _order_payload(payload: dict) -> dict:
        return {
            "order_key": str(payload["order_key"]),
            "profile_id": str(payload["profile_id"]),
            "account_id": str(payload["account_id"]),
            "venue": str(payload.get("venue") or "BINANCE_USDM"),
            "symbol": str(payload["symbol"]),
            "venue_order_id": str(payload["venue_order_id"]),
            "client_order_id": payload.get("client_order_id"),
            "side": str(payload.get("side") or "BUY"),
            "position_side": str(payload.get("position_side") or "BOTH"),
            "status": str(payload.get("status") or "NEW"),
            "order_type": str(payload.get("order_type") or "LIMIT"),
            "orig_type": payload.get("orig_type"),
            "time_in_force": payload.get("time_in_force"),
            "quantity": float(payload.get("quantity") or 0.0),
            "executed_quantity": float(payload.get("executed_quantity") or 0.0),
            "price": float(payload.get("price") or 0.0),
            "avg_price": float(payload.get("avg_price") or 0.0),
            "stop_price": float(payload.get("stop_price")) if payload.get("stop_price") is not None else None,
            "activate_price": float(payload.get("activate_price")) if payload.get("activate_price") is not None else None,
            "price_rate": float(payload.get("price_rate")) if payload.get("price_rate") is not None else None,
            "reduce_only": bool(payload.get("reduce_only")),
            "close_position": bool(payload.get("close_position")),
            "working_type": payload.get("working_type"),
            "price_protect": bool(payload.get("price_protect")),
            "is_protective": bool(payload.get("is_protective")),
            "opened_at_utc": payload.get("opened_at_utc"),
            "updated_at_utc": payload.get("updated_at_utc"),
            "synced_at_utc": str(payload.get("synced_at_utc") or ""),
            "payload_json": dumps_json(
                {
                    **(payload.get("payload") or {}),
                    "order_role": str(payload.get("order_role") or "ENTRY"),
                    "protective_order_type": str(payload.get("protective_order_type") or "NONE"),
                }
            ),
        }

    @staticmethod
    def _account_to_dict(row: ProfileAccount | None) -> dict | None:
        if row is None:
            return None
        return {
            "id": row.id,
            "account_id": row.account_id,
            "account_key": row.account_key,
            "profile_id": row.profile_id,
            "account_type": row.account_type,
            "venue_account_key": row.venue_account_key,
            "balance_ccy": row.balance_ccy,
            "balance": float(row.balance),
            "available_balance": float(row.available_balance),
            "equity": float(row.equity),
            "margin_used": float(row.margin_used),
            "payload": loads_json(getattr(row, "payload_json", "{}"), {}),
            "as_of_utc": row.as_of_utc,
            "created_at_utc": row.created_at_utc,
            "updated_at_utc": row.updated_at_utc,
        }

    @staticmethod
    def _balance_to_dict(row: VenueBalance) -> dict:
        return {
            "id": row.id,
            "balance_id": row.balance_id,
            "profile_id": row.profile_id,
            "account_id": row.account_id,
            "venue": row.venue,
            "asset": row.asset,
            "balance": float(row.balance),
            "available_balance": float(row.available_balance),
            "margin_balance": float(row.margin_balance),
            "cross_wallet_balance": float(row.cross_wallet_balance),
            "cross_unrealized_pnl": float(row.cross_unrealized_pnl),
            "max_withdraw_amount": float(row.max_withdraw_amount),
            "margin_available": bool(row.margin_available),
            "update_time_utc": row.update_time_utc,
            "synced_at_utc": row.synced_at_utc,
            "payload": loads_json(row.payload_json, {}),
        }

    @staticmethod
    def _position_to_dict(row: VenuePosition) -> dict:
        return {
            "id": row.id,
            "position_id": row.position_id,
            "profile_id": row.profile_id,
            "account_id": row.account_id,
            "venue": row.venue,
            "symbol": row.symbol,
            "position_side": row.position_side,
            "status": row.status,
            "quantity": float(row.quantity),
            "entry_price": float(row.entry_price),
            "break_even_price": float(row.break_even_price),
            "mark_price": float(row.mark_price),
            "unrealized_pnl": float(row.unrealized_pnl),
            "liquidation_price": float(row.liquidation_price),
            "leverage": float(row.leverage),
            "margin_type": row.margin_type,
            "isolated": bool(row.isolated),
            "isolated_margin": float(row.isolated_margin),
            "notional": float(row.notional),
            "max_notional_value": float(row.max_notional_value),
            "update_time_utc": row.update_time_utc,
            "synced_at_utc": row.synced_at_utc,
            "payload": loads_json(row.payload_json, {}),
        }

    @staticmethod
    def _order_to_dict(row: VenueOrder) -> dict:
        return {
            "id": row.id,
            "order_key": row.order_key,
            "profile_id": row.profile_id,
            "account_id": row.account_id,
            "venue": row.venue,
            "symbol": row.symbol,
            "venue_order_id": row.venue_order_id,
            "client_order_id": row.client_order_id,
            "side": row.side,
            "position_side": row.position_side,
            "status": row.status,
            "order_type": row.order_type,
            "orig_type": row.orig_type,
            "time_in_force": row.time_in_force,
            "quantity": float(row.quantity),
            "executed_quantity": float(row.executed_quantity),
            "price": float(row.price),
            "avg_price": float(row.avg_price),
            "stop_price": row.stop_price,
            "activate_price": row.activate_price,
            "price_rate": row.price_rate,
            "reduce_only": bool(row.reduce_only),
            "close_position": bool(row.close_position),
            "working_type": row.working_type,
            "price_protect": bool(row.price_protect),
            "is_protective": bool(row.is_protective),
            "order_role": str(loads_json(row.payload_json, {}).get("order_role") or ("PROTECTIVE" if bool(row.is_protective) else "ENTRY")),
            "protective_order_type": str(loads_json(row.payload_json, {}).get("protective_order_type") or "NONE"),
            "opened_at_utc": row.opened_at_utc,
            "updated_at_utc": row.updated_at_utc,
            "synced_at_utc": row.synced_at_utc,
            "payload": loads_json(row.payload_json, {}),
        }
