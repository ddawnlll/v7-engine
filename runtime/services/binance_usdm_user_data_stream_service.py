"""Binance USDⓈ-M user data stream lifecycle and read-only event ingestion."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from runtime.db.repos.runtime_profile_repo import RuntimeProfileRepository
from runtime.db.repos.settings_repo import SettingsRepository
from runtime.db.repos.state_repo import StateRepository
from runtime.db.repos.venue_state_repo import VenueStateRepository
from runtime.db.session import session_scope
from runtime.services.binance_usdm_readonly_service import BinanceUsdmReadonlyService
from runtime.services.binance_usdm_reconciliation_service import BinanceUsdmReconciliationService
from runtime.services.runtime_profile_service import (
    BINANCE_USDM_VENUE,
    RuntimeProfileAccessError,
    RuntimeProfileConnectivityError,
    RuntimeProfileNotFoundError,
    RuntimeProfileService,
)

STREAM_STATE_KEY = "binance_usdm_user_data_stream"
STREAM_EVENT_AUDIT_KEY = "binance_usdm_user_data_stream_last_event"
OPEN_ORDER_STATUSES = {"NEW", "PARTIALLY_FILLED", "PENDING_CANCEL"}


class BinanceUsdmUserDataStreamError(ValueError):
    """Raised when user data stream lifecycle or ingestion cannot complete safely."""


class BinanceUsdmUserDataStreamService:
    def __init__(
        self,
        *,
        runtime_profile_service: RuntimeProfileService | None = None,
        runtime_profile_repo: RuntimeProfileRepository | None = None,
        state_repo: StateRepository | None = None,
        venue_state_repo: VenueStateRepository | None = None,
        readonly_service: BinanceUsdmReadonlyService | None = None,
        reconciliation_service: BinanceUsdmReconciliationService | None = None,
        settings_repo: SettingsRepository | None = None,
    ) -> None:
        self.runtime_profile_service = runtime_profile_service or RuntimeProfileService()
        self.runtime_profile_repo = runtime_profile_repo or RuntimeProfileRepository()
        self.state_repo = state_repo or StateRepository()
        self.venue_state_repo = venue_state_repo or VenueStateRepository()
        self.settings_repo = settings_repo or SettingsRepository()
        self.readonly_service = readonly_service or BinanceUsdmReadonlyService(
            runtime_profile_service=self.runtime_profile_service,
            venue_state_repo=self.venue_state_repo,
            state_repo=self.state_repo,
            runtime_profile_repo=self.runtime_profile_repo,
        )
        self.reconciliation_service = reconciliation_service or BinanceUsdmReconciliationService(
            runtime_profile_service=self.runtime_profile_service,
            runtime_profile_repo=self.runtime_profile_repo,
            state_repo=self.state_repo,
            venue_state_repo=self.venue_state_repo,
        )

    def start_stream(self, profile_id: str, *, reason: str = "manual_start") -> dict[str, Any]:
        access = self._require_live_profile(profile_id)
        now = self._utc_now_iso()
        try:
            payload = self.runtime_profile_service.api_key_request_json(profile_id, "POST", "/fapi/v1/listenKey")
        except (RuntimeProfileAccessError, RuntimeProfileConnectivityError) as exc:
            self._record_degraded_state(profile_id, error_text=str(exc), timestamp=now, reconnect_required=True)
            raise BinanceUsdmUserDataStreamError(str(exc)) from exc
        if not isinstance(payload, dict) or not str(payload.get("listenKey") or "").strip():
            self._record_degraded_state(profile_id, error_text="Listen key response did not include a listenKey.", timestamp=now, reconnect_required=True)
            raise BinanceUsdmUserDataStreamError("Listen key response did not include a listenKey.")
        current = self._load_stream_state(profile_id)
        next_refresh_count = int(current.get("refresh_count") or 0)
        if current.get("listen_key") and current.get("listen_key") != payload["listenKey"]:
            next_refresh_count += 1
        state = {
            **current,
            "status": "ACTIVE",
            "listen_key": str(payload["listenKey"]),
            "listen_key_fingerprint": self._fingerprint(str(payload["listenKey"])),
            "listen_key_present": True,
            "started_at_utc": current.get("started_at_utc") or now,
            "last_started_at_utc": now,
            "last_keepalive_at_utc": current.get("last_keepalive_at_utc"),
            "last_event_seen_at_utc": current.get("last_event_seen_at_utc"),
            "last_event_type": current.get("last_event_type"),
            "last_event_time_utc": current.get("last_event_time_utc"),
            "reconnect_required": False,
            "reconnect_count": int(current.get("reconnect_count") or 0),
            "refresh_count": next_refresh_count,
            "keepalive_count": int(current.get("keepalive_count") or 0),
            "event_count": int(current.get("event_count") or 0),
            "expired_event_count": int(current.get("expired_event_count") or 0),
            "last_error": None,
            "last_error_at_utc": None,
            "last_status_reason": reason,
            "expected_expire_at_utc": self._add_minutes(now, self._listen_key_expire_minutes()),
            "transport": {
                "kind": "binance-usdm-user-data-stream",
                "websocket_base_url": self._resolve_private_websocket_base_url(access["profile"]),
                "requires_private_listen_key": True,
            },
        }
        persisted = self._persist_stream_state(profile_id, state, connectivity_status="CONNECTED", connectivity_error=None, timestamp=now)
        self.reconciliation_service.reconcile(profile_id)
        return persisted

    def keepalive_stream(self, profile_id: str) -> dict[str, Any]:
        self._require_live_profile(profile_id)
        now = self._utc_now_iso()
        try:
            payload = self.runtime_profile_service.api_key_request_json(profile_id, "PUT", "/fapi/v1/listenKey")
        except (RuntimeProfileAccessError, RuntimeProfileConnectivityError) as exc:
            self._record_degraded_state(profile_id, error_text=str(exc), timestamp=now, reconnect_required=True)
            raise BinanceUsdmUserDataStreamError(str(exc)) from exc
        current = self._load_stream_state(profile_id)
        listen_key = str((payload or {}).get("listenKey") or current.get("listen_key") or "").strip()
        if not listen_key:
            self._record_degraded_state(profile_id, error_text="Keepalive response did not preserve a listenKey.", timestamp=now, reconnect_required=True)
            raise BinanceUsdmUserDataStreamError("Keepalive response did not preserve a listenKey.")
        state = {
            **current,
            "status": "ACTIVE",
            "listen_key": listen_key,
            "listen_key_fingerprint": self._fingerprint(listen_key),
            "listen_key_present": True,
            "last_keepalive_at_utc": now,
            "keepalive_count": int(current.get("keepalive_count") or 0) + 1,
            "reconnect_required": False,
            "last_error": None,
            "last_error_at_utc": None,
            "last_status_reason": "keepalive",
            "expected_expire_at_utc": self._add_minutes(now, self._listen_key_expire_minutes()),
        }
        persisted = self._persist_stream_state(profile_id, state, connectivity_status="CONNECTED", connectivity_error=None, timestamp=now)
        self.reconciliation_service.reconcile(profile_id)
        return persisted

    def refresh_stream(self, profile_id: str, *, reason: str = "manual_refresh") -> dict[str, Any]:
        current = self._load_stream_state(profile_id)
        with session_scope() as session:
            self.state_repo.set(
                session,
                STREAM_STATE_KEY,
                {
                    **current,
                    "status": "REFRESHING",
                    "reconnect_required": True,
                    "last_status_reason": reason,
                },
                profile_id=profile_id,
            )
        refreshed = self.start_stream(profile_id, reason=reason)
        with session_scope() as session:
            latest = self.state_repo.get(session, STREAM_STATE_KEY, default={}, profile_id=profile_id) or {}
            latest["reconnect_count"] = int(current.get("reconnect_count") or 0) + 1
            self.state_repo.set(session, STREAM_STATE_KEY, latest, profile_id=profile_id)
        self.reconciliation_service.reconcile(profile_id)
        return self.get_stream_state(profile_id)

    def close_stream(self, profile_id: str) -> dict[str, Any]:
        self._require_live_profile(profile_id)
        now = self._utc_now_iso()
        current = self._load_stream_state(profile_id)
        try:
            self.runtime_profile_service.api_key_request_json(profile_id, "DELETE", "/fapi/v1/listenKey")
        except (RuntimeProfileAccessError, RuntimeProfileConnectivityError) as exc:
            self._record_degraded_state(profile_id, error_text=str(exc), timestamp=now, reconnect_required=False)
            raise BinanceUsdmUserDataStreamError(str(exc)) from exc
        state = {
            **current,
            "status": "CLOSED",
            "listen_key": None,
            "listen_key_present": False,
            "closed_at_utc": now,
            "expected_expire_at_utc": None,
            "reconnect_required": False,
            "last_status_reason": "closed",
            "last_error": None,
            "last_error_at_utc": None,
        }
        persisted = self._persist_stream_state(profile_id, state, connectivity_status="READY", connectivity_error=None, timestamp=now)
        self.reconciliation_service.reconcile(profile_id)
        return persisted

    def ingest_event(self, profile_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        access = self._require_live_profile(profile_id)
        if not isinstance(payload, dict):
            raise BinanceUsdmUserDataStreamError("User data stream event payload must be an object.")
        event_type = str(payload.get("e") or "").strip()
        if not event_type:
            raise BinanceUsdmUserDataStreamError("User data stream event payload is missing 'e'.")
        now = self._utc_now_iso()
        event_time_utc = self._ms_to_iso(payload.get("E")) or now
        current = self._load_stream_state(profile_id)
        updated = {
            **current,
            "status": "ACTIVE" if event_type != "listenKeyExpired" else "EXPIRED",
            "listen_key_present": bool(current.get("listen_key")),
            "last_event_seen_at_utc": now,
            "last_event_type": event_type,
            "last_event_time_utc": event_time_utc,
            "event_count": int(current.get("event_count") or 0) + 1,
            "last_error": None,
            "last_error_at_utc": None,
            "last_status_reason": f"event:{event_type}",
        }
        result: dict[str, Any] = {"event_type": event_type, "event_time_utc": event_time_utc}

        with session_scope() as session:
            if event_type == "ACCOUNT_UPDATE":
                result.update(self._ingest_account_update(session, access, payload, now))
            elif event_type == "ORDER_TRADE_UPDATE":
                result["order"] = self._ingest_order_update(session, access, payload, now)
            elif event_type == "listenKeyExpired":
                updated["expired_event_count"] = int(current.get("expired_event_count") or 0) + 1
                updated["reconnect_required"] = True
                updated["last_error"] = "Listen key expired. Refresh required before more user data events will arrive."
                updated["last_error_at_utc"] = now
            else:
                result["ignored"] = True

            self.state_repo.set(
                session,
                STREAM_EVENT_AUDIT_KEY,
                {
                    "event_type": event_type,
                    "event_time_utc": event_time_utc,
                    "received_at_utc": now,
                    **self._event_audit_summary(event_type, payload),
                },
                profile_id=profile_id,
            )
            self.state_repo.set(session, STREAM_STATE_KEY, updated, profile_id=profile_id)

        connectivity_status = "ERROR" if updated.get("reconnect_required") else "CONNECTED"
        self._update_profile_connectivity(profile_id, connectivity_status, updated.get("last_error"), now)
        reconciliation = self.reconciliation_service.reconcile(profile_id)
        return {
            "stream": self._sanitize_stream_state(updated),
            "reconciliation": reconciliation,
            **result,
        }

    def mark_stream_disconnected(self, profile_id: str, *, error_text: str, reconnect_required: bool = True) -> dict[str, Any]:
        self._require_binance_profile(profile_id)
        now = self._utc_now_iso()
        self._record_degraded_state(profile_id, error_text=error_text, timestamp=now, reconnect_required=reconnect_required)
        self.reconciliation_service.reconcile(profile_id)
        return self.get_stream_state(profile_id)

    def get_stream_state(self, profile_id: str) -> dict[str, Any]:
        self._require_profile_exists(profile_id)
        state = self._load_stream_state(profile_id)
        return self._sanitize_stream_state(state)

    def _ingest_account_update(self, session, access: dict[str, Any], payload: dict[str, Any], synced_at_utc: str) -> dict[str, Any]:
        profile_id = str(access["profile"].get("profile_id") or "")
        account_payload = payload.get("a") or {}
        balances_payload = list(account_payload.get("B") or [])
        positions_payload = list(account_payload.get("P") or [])
        account_id = f"{profile_id}:default"

        saved_balances = []
        for item in balances_payload:
            normalized = self._normalize_account_balance_event(profile_id, account_id, item, synced_at_utc=synced_at_utc)
            saved_balances.append(self.venue_state_repo.upsert_balance(session, normalized))

        saved_positions = []
        removed_positions = []
        for item in positions_payload:
            normalized = self._normalize_account_position_event(profile_id, account_id, item, synced_at_utc=synced_at_utc)
            if abs(float(normalized["quantity"])) <= 0.0:
                removed = self.venue_state_repo.delete_position(
                    session,
                    profile_id,
                    symbol=str(normalized["symbol"]),
                    position_side=str(normalized["position_side"]),
                    account_id=account_id,
                )
                removed_positions.append({
                    "symbol": normalized["symbol"],
                    "position_side": normalized["position_side"],
                    "removed": removed,
                })
                continue

            existing = self.venue_state_repo.get_position(
                session,
                profile_id,
                symbol=str(normalized["symbol"]),
                position_side=str(normalized["position_side"]),
                account_id=account_id,
            )

            if not existing:
                normalized["payload"]["opened_at_source"] = "websocket_observed"
                normalized["payload"]["opened_at_utc"] = normalized["update_time_utc"]
            else:
                existing_payload = existing.get("payload", {})
                if "opened_at_utc" in existing_payload:
                    normalized["payload"]["opened_at_utc"] = existing_payload["opened_at_utc"]
                if "opened_at_source" in existing_payload:
                    normalized["payload"]["opened_at_source"] = existing_payload["opened_at_source"]

            saved_positions.append(self.venue_state_repo.upsert_position(session, normalized))

        existing_account = self.venue_state_repo.get_account_summary(session, profile_id)
        usdt_balance = next((item for item in saved_balances if item.get("asset") == "USDT"), None)
        updated_account = existing_account or {
            "account_id": account_id,
            "profile_id": profile_id,
            "account_key": "default",
            "account_type": "LIVE_FUTURES_USDM_READ_ONLY",
            "venue_account_key": None,
            "balance_ccy": "USDT",
            "balance": 0.0,
            "available_balance": 0.0,
            "equity": 0.0,
            "margin_used": 0.0,
            "payload": {},
            "as_of_utc": synced_at_utc,
            "created_at_utc": synced_at_utc,
            "updated_at_utc": synced_at_utc,
        }
        updated_account = {
            **updated_account,
            "payload": {
                **(updated_account.get("payload") or {}),
                "last_account_update_reason": account_payload.get("m"),
                "last_account_update_event_time": self._as_int(payload.get("E")),
            },
            "as_of_utc": synced_at_utc,
            "updated_at_utc": synced_at_utc,
        }
        if usdt_balance is not None:
            updated_account["balance"] = float(usdt_balance.get("balance") or 0.0)
            updated_account["available_balance"] = float(usdt_balance.get("cross_wallet_balance") or usdt_balance.get("available_balance") or 0.0)
            updated_account["equity"] = float(usdt_balance.get("margin_balance") or updated_account.get("equity") or 0.0)
        self.venue_state_repo.save_account_summary(session, updated_account)

        return {
            "account_update": {
                "reason": account_payload.get("m"),
                "balances": saved_balances,
                "positions": saved_positions,
                "removed_positions": removed_positions,
            }
        }

    def _ingest_order_update(self, session, access: dict[str, Any], payload: dict[str, Any], synced_at_utc: str) -> dict[str, Any]:
        order_payload = payload.get("o") or {}
        normalized = self._normalize_order_update_event(access, order_payload, synced_at_utc=synced_at_utc)

        existing = self.venue_state_repo.get_order(
            session,
            profile_id=normalized["profile_id"],
            symbol=normalized["symbol"],
            venue_order_id=normalized["venue_order_id"],
        )

        existing_payload = existing.get("payload", {}) if existing else {}
        fills = existing_payload.get("fills", [])
        realized_pnl = float(existing_payload.get("realized_pnl") or 0.0)

        execution_type = str(order_payload.get("x") or "")
        last_fill_qty = float(order_payload.get("l") or 0.0)
        last_fill_price = float(order_payload.get("L") or 0.0)
        trade_id = str(order_payload.get("t") or "")
        rp = float(order_payload.get("rp") or 0.0)

        if execution_type == "TRADE" and last_fill_qty > 0.0:
            fill_exists = any(str(f.get("trade_id") or "") == trade_id for f in fills) if trade_id else False
            if not fill_exists:
                fills.append({
                    "trade_id": trade_id,
                    "quantity": last_fill_qty,
                    "price": last_fill_price,
                    "realized_pnl": rp,
                    "time_utc": synced_at_utc,
                })
                realized_pnl += rp

        normalized["payload"]["fills"] = fills
        normalized["payload"]["realized_pnl"] = realized_pnl

        return self.venue_state_repo.upsert_order(session, normalized)

    def _normalize_account_balance_event(self, profile_id: str, account_id: str, payload: dict[str, Any], *, synced_at_utc: str) -> dict[str, Any]:
        asset = str(payload.get("a") or "").upper()
        wallet_balance = self.readonly_service._as_float(payload.get("wb"))
        cross_wallet_balance = self.readonly_service._as_float(payload.get("cw"))
        balance_change = self.readonly_service._as_float(payload.get("bc"))
        return {
            "balance_id": f"{profile_id}:{account_id}:{asset}",
            "profile_id": profile_id,
            "account_id": account_id,
            "venue": BINANCE_USDM_VENUE,
            "asset": asset,
            "balance": wallet_balance,
            "available_balance": cross_wallet_balance,
            "margin_balance": wallet_balance,
            "cross_wallet_balance": cross_wallet_balance,
            "cross_unrealized_pnl": 0.0,
            "max_withdraw_amount": cross_wallet_balance,
            "margin_available": True,
            "update_time_utc": synced_at_utc,
            "synced_at_utc": synced_at_utc,
            "payload": {
                **dict(payload),
                "balance_change": balance_change,
            },
        }

    def _normalize_account_position_event(self, profile_id: str, account_id: str, payload: dict[str, Any], *, synced_at_utc: str) -> dict[str, Any]:
        quantity = self.readonly_service._as_float(payload.get("pa"))
        symbol = str(payload.get("s") or "").upper()
        position_side = str(payload.get("ps") or "BOTH").upper()
        margin_type = str(payload.get("mt") or "cross")
        return {
            "position_id": f"{profile_id}:{symbol}:{position_side}",
            "profile_id": profile_id,
            "account_id": account_id,
            "venue": BINANCE_USDM_VENUE,
            "symbol": symbol,
            "position_side": position_side,
            "status": "OPEN" if abs(quantity) > 0.0 else "CLOSED",
            "quantity": quantity,
            "entry_price": self.readonly_service._as_float(payload.get("ep")),
            "break_even_price": self.readonly_service._as_float(payload.get("bep")),
            "mark_price": 0.0,
            "unrealized_pnl": self.readonly_service._as_float(payload.get("up")),
            "liquidation_price": 0.0,
            "leverage": 0.0,
            "margin_type": margin_type,
            "isolated": margin_type.lower() == "isolated",
            "isolated_margin": self.readonly_service._as_float(payload.get("iw")),
            "notional": 0.0,
            "max_notional_value": 0.0,
            "update_time_utc": synced_at_utc,
            "synced_at_utc": synced_at_utc,
            "payload": dict(payload),
        }

    def _normalize_order_update_event(self, access: dict[str, Any], payload: dict[str, Any], *, synced_at_utc: str) -> dict[str, Any]:
        profile_id = str(access["profile"].get("profile_id") or "")
        account_id = f"{profile_id}:default"
        symbol = str(payload.get("s") or "").upper()
        venue_order_id = str(payload.get("i") or "")
        order_type = str(payload.get("o") or payload.get("ot") or "LIMIT").upper()
        reduce_only = bool(payload.get("R"))
        close_position = bool(payload.get("cp"))
        execution_type = str(payload.get("x") or "")
        status = str(payload.get("X") or "NEW")
        order_role, protective_order_type, is_protective = self.readonly_service.classify_order_posture(
            order_type=order_type,
            orig_type=payload.get("ot"),
            reduce_only=reduce_only,
            close_position=close_position,
        )
        return {
            "order_key": f"{profile_id}:{symbol}:{venue_order_id}",
            "profile_id": profile_id,
            "account_id": account_id,
            "venue": BINANCE_USDM_VENUE,
            "symbol": symbol,
            "venue_order_id": venue_order_id,
            "client_order_id": payload.get("c"),
            "side": str(payload.get("S") or "BUY"),
            "position_side": str(payload.get("ps") or "BOTH"),
            "status": status,
            "order_type": order_type,
            "orig_type": payload.get("ot"),
            "time_in_force": payload.get("f"),
            "quantity": self.readonly_service._as_float(payload.get("q")),
            "executed_quantity": self.readonly_service._as_float(payload.get("z")),
            "price": self.readonly_service._as_float(payload.get("p")),
            "avg_price": self.readonly_service._as_float(payload.get("ap")),
            "stop_price": self.readonly_service._nullable_float(payload.get("sp")),
            "activate_price": self.readonly_service._nullable_float(payload.get("AP")),
            "price_rate": self.readonly_service._nullable_float(payload.get("cr")),
            "reduce_only": reduce_only,
            "close_position": close_position,
            "working_type": payload.get("wt"),
            "price_protect": bool(payload.get("pP")),
            "is_protective": is_protective,
            "order_role": order_role,
            "protective_order_type": protective_order_type,
            "opened_at_utc": self._ms_to_iso(payload.get("T")),
            "updated_at_utc": self._ms_to_iso(payload.get("T")) or synced_at_utc,
            "synced_at_utc": synced_at_utc,
            "payload": {
                **dict(payload),
                "execution_type": execution_type,
            },
        }

    def _event_audit_summary(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        if event_type == "ACCOUNT_UPDATE":
            account = payload.get("a") or {}
            return {
                "balance_assets": [str(item.get("a") or "").upper() for item in list(account.get("B") or []) if str(item.get("a") or "")],
                "positions": [
                    {
                        "symbol": str(item.get("s") or "").upper(),
                        "position_side": str(item.get("ps") or "BOTH").upper(),
                        "quantity": self.readonly_service._as_float(item.get("pa")),
                    }
                    for item in list(account.get("P") or [])
                ],
            }
        if event_type == "ORDER_TRADE_UPDATE":
            order = payload.get("o") or {}
            order_role, protective_order_type, is_protective = self.readonly_service.classify_order_posture(
                order_type=str(order.get("o") or order.get("ot") or "LIMIT").upper(),
                orig_type=order.get("ot"),
                reduce_only=bool(order.get("R")),
                close_position=bool(order.get("cp")),
            )
            return {
                "symbol": str(order.get("s") or "").upper(),
                "venue_order_id": str(order.get("i") or ""),
                "client_order_id": order.get("c"),
                "order_status": str(order.get("X") or "NEW"),
                "execution_type": str(order.get("x") or ""),
                "order_role": order_role,
                "protective_order_type": protective_order_type,
                "is_protective": is_protective,
            }
        if event_type == "listenKeyExpired":
            return {"listen_key_present": bool(payload.get("listenKey"))}
        return {}

    def _persist_stream_state(
        self,
        profile_id: str,
        state: dict[str, Any],
        *,
        connectivity_status: str,
        connectivity_error: str | None,
        timestamp: str,
    ) -> dict[str, Any]:
        with session_scope() as session:
            self.state_repo.set(session, STREAM_STATE_KEY, state, profile_id=profile_id)
        self._update_profile_connectivity(profile_id, connectivity_status, connectivity_error, timestamp)
        return self.get_stream_state(profile_id)

    def _record_degraded_state(self, profile_id: str, *, error_text: str, timestamp: str, reconnect_required: bool) -> None:
        current = self._load_stream_state(profile_id)
        degraded = {
            **current,
            "status": "DEGRADED",
            "reconnect_required": reconnect_required,
            "last_error": error_text,
            "last_error_at_utc": timestamp,
            "last_status_reason": "degraded",
        }
        with session_scope() as session:
            self.state_repo.set(session, STREAM_STATE_KEY, degraded, profile_id=profile_id)
        self._update_profile_connectivity(profile_id, "ERROR", error_text, timestamp)

    def _update_profile_connectivity(self, profile_id: str, status: str, error_text: str | None, timestamp: str) -> None:
        with session_scope() as session:
            profile = self.runtime_profile_repo.get_profile(session, profile_id)
            if profile is None:
                return
            payload = {
                **profile,
                "connectivity_status": status,
                "last_connectivity_check_at_utc": timestamp,
                "last_connectivity_error": error_text,
                "updated_at_utc": timestamp,
            }
            if status in {"CONNECTED", "READY"}:
                payload["last_connectivity_ok_at_utc"] = timestamp
            self.runtime_profile_repo.save_profile(session, payload)

    def _load_stream_state(self, profile_id: str) -> dict[str, Any]:
        with session_scope() as session:
            return self.state_repo.get(session, STREAM_STATE_KEY, default={}, profile_id=profile_id) or {}

    def _sanitize_stream_state(self, state: dict[str, Any]) -> dict[str, Any]:
        if not state:
            return {
                "status": "INACTIVE",
                "listen_key_present": False,
                "reconnect_required": False,
                "event_count": 0,
                "keepalive_count": 0,
                "refresh_count": 0,
                "reconnect_count": 0,
                "expired_event_count": 0,
                "last_error": None,
            }
        return {
            "status": state.get("status") or "INACTIVE",
            "listen_key_present": bool(state.get("listen_key") or state.get("listen_key_present")),
            "listen_key_fingerprint": state.get("listen_key_fingerprint"),
            "started_at_utc": state.get("started_at_utc"),
            "last_started_at_utc": state.get("last_started_at_utc"),
            "last_keepalive_at_utc": state.get("last_keepalive_at_utc"),
            "closed_at_utc": state.get("closed_at_utc"),
            "expected_expire_at_utc": state.get("expected_expire_at_utc"),
            "last_event_seen_at_utc": state.get("last_event_seen_at_utc"),
            "last_event_type": state.get("last_event_type"),
            "last_event_time_utc": state.get("last_event_time_utc"),
            "reconnect_required": bool(state.get("reconnect_required")),
            "reconnect_count": int(state.get("reconnect_count") or 0),
            "refresh_count": int(state.get("refresh_count") or 0),
            "keepalive_count": int(state.get("keepalive_count") or 0),
            "event_count": int(state.get("event_count") or 0),
            "expired_event_count": int(state.get("expired_event_count") or 0),
            "last_status_reason": state.get("last_status_reason"),
            "last_error": state.get("last_error"),
            "last_error_at_utc": state.get("last_error_at_utc"),
            "transport": state.get("transport") or None,
        }

    def _require_profile_exists(self, profile_id: str) -> None:
        self.runtime_profile_service.get_profile(profile_id)

    def _require_binance_profile(self, profile_id: str) -> dict[str, Any]:
        access = self.runtime_profile_service.get_profile_access(profile_id, require_account_reads=True)
        profile = access["profile"]
        if str(profile.get("venue") or "").upper() != BINANCE_USDM_VENUE:
            raise BinanceUsdmUserDataStreamError(f"Runtime profile '{profile_id}' is not a Binance USDⓈ-M profile.")
        return access

    def _require_live_profile(self, profile_id: str) -> dict[str, Any]:
        access = self._require_binance_profile(profile_id)
        if not access["credentials_configured"]:
            raise BinanceUsdmUserDataStreamError("Credential reference is not fully configured.")
        return access

    def _resolve_private_websocket_base_url(self, profile: dict[str, Any]) -> str:
        environment = str(profile.get("venue_environment") or "PRODUCTION").upper()
        if environment == "TESTNET":
            return "wss://fstream.binancefuture.com/private"
        return "wss://fstream.binance.com/private"

    def _listen_key_expire_minutes(self) -> int:
        """Resolve listenKey expiry from unified config."""
        try:
            with session_scope() as session:
                val = self.settings_repo.get_value(session, "LISTEN_KEY_EXPIRE_MINUTES", default="60")
            return max(1, int(float(val)))
        except (TypeError, ValueError, Exception):
            return 60

    @staticmethod
    def _fingerprint(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _as_int(value: Any) -> int | None:
        try:
            return int(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _ms_to_iso(value: Any) -> str | None:
        millis = BinanceUsdmUserDataStreamService._as_int(value)
        if not millis:
            return None
        return datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc).isoformat()

    @staticmethod
    def _add_minutes(value: str, minutes: int) -> str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (parsed + timedelta(minutes=minutes)).isoformat()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()


__all__ = [
    "BinanceUsdmUserDataStreamError",
    "BinanceUsdmUserDataStreamService",
    "STREAM_EVENT_AUDIT_KEY",
    "STREAM_STATE_KEY",
]
