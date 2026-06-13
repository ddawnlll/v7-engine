"""Binance USDⓈ-M REST + stream reconciliation foundation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from runtime.db.repos._helpers import dumps_json
from runtime.db.repos.order_repo import OrderRepository
from runtime.db.repos.runtime_profile_repo import RuntimeProfileRepository
from runtime.db.repos.settings_repo import SettingsRepository
from runtime.db.repos.state_repo import StateRepository
from runtime.db.repos.venue_state_repo import VenueStateRepository
from runtime.db.session import session_scope
from runtime.services.runtime_profile_service import BINANCE_USDM_VENUE, RuntimeProfileNotFoundError, RuntimeProfileService

REST_SYNC_STATE_KEY = "binance_usdm_rest_account_state_sync"
STREAM_STATE_KEY = "binance_usdm_user_data_stream"
STREAM_EVENT_AUDIT_KEY = "binance_usdm_user_data_stream_last_event"
RECONCILIATION_STATE_KEY = "binance_usdm_reconciliation"
VENUE_FLAT_SYNC_MIN_AGE_SECONDS = 30  # Legacy default; actual value resolved from unified config.

DEGRADED_WARNING_CODES = {
    "REST_SYNC_UNAVAILABLE",
    "REST_SYNC_ERROR",
    "STREAM_DEGRADED",
    "MISSING_LOCAL_ACCOUNT_STATE",
    "MISSING_LOCAL_BALANCE_FOR_STREAM",
    "MISSING_LOCAL_POSITION_FOR_STREAM",
    "MISSING_LOCAL_ORDER_FOR_STREAM",
    "MISSING_LOCAL_PROTECTIVE_ORDER_FOR_STREAM",
}
WARNING_ONLY_CODES = {
    "STALE_REST_SNAPSHOT",
    "STALE_STREAM_STATE",
    "MISSING_STREAM_UPDATES_AFTER_REST_SYNC",
}


class BinanceUsdmReconciliationError(ValueError):
    """Raised when reconciliation cannot run safely."""


class BinanceUsdmReconciliationService:
    def __init__(
        self,
        *,
        runtime_profile_service: RuntimeProfileService | None = None,
        runtime_profile_repo: RuntimeProfileRepository | None = None,
        state_repo: StateRepository | None = None,
        venue_state_repo: VenueStateRepository | None = None,
        order_repo: OrderRepository | None = None,
        settings_repo: SettingsRepository | None = None,
    ) -> None:
        self.runtime_profile_service = runtime_profile_service or RuntimeProfileService()
        self.runtime_profile_repo = runtime_profile_repo or RuntimeProfileRepository()
        self.state_repo = state_repo or StateRepository()
        self.venue_state_repo = venue_state_repo or VenueStateRepository()
        self.order_repo = order_repo or OrderRepository()
        self.settings_repo = settings_repo or SettingsRepository()

    def reconcile(self, profile_id: str) -> dict[str, Any]:
        profile = self._require_binance_profile(profile_id)
        with session_scope() as session:
            rest = self.state_repo.get(session, REST_SYNC_STATE_KEY, default=None, profile_id=profile_id)
            stream = self.state_repo.get(session, STREAM_STATE_KEY, default=None, profile_id=profile_id)
            audit = self.state_repo.get(session, STREAM_EVENT_AUDIT_KEY, default=None, profile_id=profile_id)
            account = self.venue_state_repo.get_account_summary(session, profile_id)
            account_id = account["account_id"] if account else None
            balances = self.venue_state_repo.list_balances(session, profile_id, account_id=account_id)
            positions = self.venue_state_repo.list_positions(session, profile_id, account_id=account_id)
            open_orders = self.venue_state_repo.list_open_orders(session, profile_id, account_id=account_id)

        now = self._utc_now_iso()
        auto_resolved_orders = self._reconcile_local_live_orders(
            profile_id,
            positions=positions,
            open_orders=open_orders,
            rest=rest or {},
            stream=stream or {},
            reconciled_at_utc=now,
        )
        warnings = self._build_warnings(
            profile_id,
            rest=rest or {},
            stream=stream or {},
            audit=audit or {},
            account=account,
            balances=balances,
            positions=positions,
            open_orders=open_orders,
        )
        protective_summary = self._protective_order_summary(open_orders)
        payload = {
            "profile_id": profile_id,
            "venue": BINANCE_USDM_VENUE,
            "account_id": account_id,
            "status": self._resolve_status(warnings),
            "warning_count": len(warnings),
            "warnings": warnings,
            "rest": {
                "status": (rest or {}).get("status") or "UNAVAILABLE",
                "last_synced_at_utc": (rest or {}).get("last_synced_at_utc"),
                "balance_count": int(((rest or {}).get("balance_count") or 0)),
                "position_count": int(((rest or {}).get("position_count") or 0)),
                "open_order_count": int(((rest or {}).get("open_order_count") or 0)),
                "last_error": (rest or {}).get("last_error"),
            },
            "stream": {
                "status": (stream or {}).get("status") or "INACTIVE",
                "last_event_seen_at_utc": (stream or {}).get("last_event_seen_at_utc"),
                "last_event_time_utc": (stream or {}).get("last_event_time_utc"),
                "last_event_type": (stream or {}).get("last_event_type"),
                "event_count": int(((stream or {}).get("event_count") or 0)),
                "reconnect_required": bool((stream or {}).get("reconnect_required")),
                "last_error": (stream or {}).get("last_error"),
            },
            "venue_state": {
                "account_present": account is not None,
                "balance_count": len(balances),
                "position_count": len(positions),
                "open_order_count": len(open_orders),
                **protective_summary,
            },
            "auto_resolved_orders": auto_resolved_orders,
            "last_reconciled_at_utc": now,
        }
        with session_scope() as session:
            self.state_repo.set(session, RECONCILIATION_STATE_KEY, payload, profile_id=profile_id)
            if str(payload.get("status") or "").upper() == "READY":
                self.state_repo.delete(session, "last_error", profile_id=profile_id)
        return payload

    def get_reconciliation(self, profile_id: str) -> dict[str, Any]:
        self._require_binance_profile(profile_id)
        with session_scope() as session:
            saved = self.state_repo.get(session, RECONCILIATION_STATE_KEY, default=None, profile_id=profile_id)
        if saved is not None:
            return saved
        return self.reconcile(profile_id)

    def _reconcile_local_live_orders(
        self,
        profile_id: str,
        *,
        positions: list[dict[str, Any]],
        open_orders: list[dict[str, Any]],
        rest: dict[str, Any],
        stream: dict[str, Any],
        reconciled_at_utc: str,
    ) -> list[dict[str, Any]]:
        venue_position_symbols = {str(item.get("symbol") or "").upper() for item in positions if abs(float(item.get("quantity") or 0.0)) > 0.0}
        venue_open_order_symbols = {str(item.get("symbol") or "").upper() for item in open_orders}
        resolved: list[dict[str, Any]] = []
        with session_scope() as session:
            orders = self.order_repo.list_orders(session, limit=5000, profile_id=profile_id)
            for item in orders:
                if str(item.get("execution_mode") or "").upper() != "LIVE" or not bool(item.get("is_open")):
                    continue
                if str(item.get("status") or "").upper() != "FILLED":
                    continue
                symbol = str(item.get("symbol") or "").upper()
                if not symbol or symbol in venue_position_symbols or symbol in venue_open_order_symbols:
                    continue
                if not self._can_confirm_venue_flat(item, rest=rest, stream=stream, reconciled_at_utc=reconciled_at_utc):
                    continue
                payload = dict(item.get("payload") or {})
                protection = dict(payload.get("protection") or {})
                protection["status"] = "CLOSED"
                protection["last_checked_at_utc"] = reconciled_at_utc
                protection["message"] = "Venue reconciliation found no remaining open position or open orders for this symbol."
                auto_live = dict(payload.get("auto_live") or {})
                if auto_live:
                    auto_live["order_status"] = "CLOSED"
                    auto_live["completion_status"] = auto_live.get("completion_status") or "VENUE_FLAT_SYNCED"
                    auto_live["completion_reason"] = "Venue reconciliation found the position closed/flat on Binance."
                    auto_live["safe_to_consider_active"] = False
                payload["protection"] = protection
                payload["auto_live"] = auto_live
                payload["close_reason"] = payload.get("close_reason") or "VENUE_FLAT_SYNC"
                self.order_repo.save_order(
                    session,
                    {
                        "order_id": item.get("order_id"),
                        "profile_id": profile_id,
                        "signal_id": item.get("signal_id"),
                        "source": item.get("source"),
                        "execution_mode": item.get("execution_mode"),
                        "venue": item.get("venue"),
                        "origin": item.get("origin"),
                        "client_order_id": item.get("client_order_id"),
                        "venue_order_id": item.get("venue_order_id"),
                        "submission_status": item.get("submission_status"),
                        "submitted_at_utc": item.get("submitted_at_utc"),
                        "last_venue_update_at_utc": reconciled_at_utc,
                        "symbol": item.get("symbol"),
                        "interval": item.get("interval"),
                        "mode": item.get("mode"),
                        "direction": item.get("direction"),
                        "status": "CLOSED",
                        "entry": item.get("entry"),
                        "stop_loss": item.get("stop_loss"),
                        "take_profit": item.get("take_profit"),
                        "close_price": item.get("close_price") or item.get("entry"),
                        "risk_reward": item.get("risk_reward"),
                        "confidence": item.get("confidence"),
                        "opened_at_utc": item.get("opened_at_utc"),
                        "closed_at_utc": item.get("closed_at_utc") or reconciled_at_utc,
                        "payload_json": dumps_json(payload),
                        "resolved_config_hash": item.get("resolved_config_hash") or "",
                    },
                )
                resolved.append({"order_id": item.get("order_id"), "symbol": symbol, "reason": "VENUE_FLAT_SYNC", "closed_at_utc": reconciled_at_utc})
        return resolved

    def _can_confirm_venue_flat(
        self,
        order: dict[str, Any],
        *,
        rest: dict[str, Any],
        stream: dict[str, Any],
        reconciled_at_utc: str,
    ) -> bool:
        if str(rest.get("status") or "").upper() != "SYNCED":
            return False
        reconciled_at = self._parse_iso(reconciled_at_utc)
        rest_synced_at = self._parse_iso(rest.get("last_synced_at_utc"))
        reference_at = self._parse_iso(order.get("last_venue_update_at_utc")) or self._parse_iso(order.get("submitted_at_utc")) or self._parse_iso(order.get("opened_at_utc"))
        if reconciled_at is None or rest_synced_at is None or reference_at is None:
            return False
        if rest_synced_at < reference_at:
            return False
        if reconciled_at - reference_at < timedelta(seconds=self._get_venue_flat_sync_min_age()):
            return False
        stream_status = str(stream.get("status") or "INACTIVE").upper()
        latest_stream_time = self._parse_iso(stream.get("last_event_time_utc")) or self._parse_iso(stream.get("last_event_seen_at_utc"))
        if stream_status == "ACTIVE" and latest_stream_time is not None and latest_stream_time < reference_at:
            return False
        return True

    def _build_warnings(
        self,
        profile_id: str,
        *,
        rest: dict[str, Any],
        stream: dict[str, Any],
        audit: dict[str, Any],
        account: dict[str, Any] | None,
        balances: list[dict[str, Any]],
        positions: list[dict[str, Any]],
        open_orders: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        warnings: list[dict[str, Any]] = []
        rest_status = str(rest.get("status") or "").upper()
        stream_status = str(stream.get("status") or "").upper()
        stream_active = stream_status == "ACTIVE"
        rest_synced_at = self._parse_iso(rest.get("last_synced_at_utc"))
        stream_seen_at = self._parse_iso(stream.get("last_event_seen_at_utc"))
        stream_event_at = self._parse_iso(stream.get("last_event_time_utc"))
        latest_stream_time = stream_event_at or stream_seen_at

        if not rest:
            warnings.append(self._warning("REST_SYNC_UNAVAILABLE", "REST snapshot has not been synced for this profile yet."))
        elif rest_status != "SYNCED":
            warnings.append(self._warning("REST_SYNC_ERROR", "REST snapshot is not in a synced state.", detail={"status": rest_status, "last_error": rest.get("last_error")}))

        if stream_status in {"DEGRADED", "EXPIRED"} or bool(stream.get("reconnect_required")):
            warnings.append(
                self._warning(
                    "STREAM_DEGRADED",
                    "User data stream is degraded or requires refresh before reconciliation can be trusted.",
                    detail={"status": stream_status or "INACTIVE", "last_error": stream.get("last_error")},
                )
            )

        if rest_synced_at and latest_stream_time and latest_stream_time > rest_synced_at:
            warnings.append(
                self._warning(
                    "STALE_REST_SNAPSHOT",
                    "The latest user data stream event is newer than the last REST snapshot.",
                    detail={
                        "last_rest_sync_at_utc": rest.get("last_synced_at_utc"),
                        "last_stream_event_time_utc": stream.get("last_event_time_utc") or stream.get("last_event_seen_at_utc"),
                    },
                )
            )

        if rest_synced_at and stream_active:
            if int(stream.get("event_count") or 0) == 0:
                warnings.append(
                    self._warning(
                        "MISSING_STREAM_UPDATES_AFTER_REST_SYNC",
                        "REST sync succeeded but the active stream has not delivered any events yet.",
                        detail={"last_rest_sync_at_utc": rest.get("last_synced_at_utc")},
                    )
                )
            elif stream_seen_at and stream_seen_at < rest_synced_at:
                warnings.append(
                    self._warning(
                        "STALE_STREAM_STATE",
                        "The active stream has not seen an event as recent as the last REST snapshot.",
                        detail={
                            "last_rest_sync_at_utc": rest.get("last_synced_at_utc"),
                            "last_stream_event_seen_at_utc": stream.get("last_event_seen_at_utc"),
                        },
                    )
                )

        if (rest_status == "SYNCED" or int(stream.get("event_count") or 0) > 0) and account is None:
            warnings.append(self._warning("MISSING_LOCAL_ACCOUNT_STATE", "Reconciliation expected a persisted venue account summary but none was found."))

        if str(audit.get("event_type") or "") == "ACCOUNT_UPDATE":
            expected_assets = list(audit.get("balance_assets") or [])
            expected_positions = list(audit.get("positions") or [])
            existing_assets = {str(item.get("asset") or "") for item in balances}
            for asset in expected_assets:
                if str(asset or "") and str(asset) not in existing_assets:
                    warnings.append(
                        self._warning(
                            "MISSING_LOCAL_BALANCE_FOR_STREAM",
                            "The latest account update referenced a balance asset that is missing from persisted venue state.",
                            detail={"asset": asset},
                        )
                    )
            existing_positions = {
                (str(item.get("symbol") or ""), str(item.get("position_side") or "BOTH"))
                for item in positions
            }
            for item in expected_positions:
                key = (str(item.get("symbol") or ""), str(item.get("position_side") or "BOTH"))
                if float(item.get("quantity") or 0.0) > 0.0 and key not in existing_positions:
                    warnings.append(
                        self._warning(
                            "MISSING_LOCAL_POSITION_FOR_STREAM",
                            "The latest account update referenced an open position missing from persisted venue state.",
                            detail={"symbol": key[0], "position_side": key[1]},
                        )
                    )

        if str(audit.get("event_type") or "") == "ORDER_TRADE_UPDATE":
            symbol = str(audit.get("symbol") or "")
            venue_order_id = str(audit.get("venue_order_id") or "")
            client_order_id = str(audit.get("client_order_id") or "")
            order_role = str(audit.get("order_role") or "ENTRY")
            protective_order_type = str(audit.get("protective_order_type") or "NONE")
            with session_scope() as session:
                found = self.venue_state_repo.get_order(
                    session,
                    profile_id,
                    symbol=symbol,
                    venue_order_id=venue_order_id or None,
                    client_order_id=client_order_id or None,
                )
            if found is None:
                warnings.append(
                    self._warning(
                        "MISSING_LOCAL_PROTECTIVE_ORDER_FOR_STREAM" if order_role == "PROTECTIVE" else "MISSING_LOCAL_ORDER_FOR_STREAM",
                        "The latest order update referenced an order that is missing from persisted venue state.",
                        detail={
                            "symbol": symbol,
                            "venue_order_id": venue_order_id or None,
                            "client_order_id": client_order_id or None,
                            "order_role": order_role,
                            "protective_order_type": protective_order_type,
                        },
                    )
                )

        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in warnings:
            marker = (str(item.get("code") or ""), str(item.get("message") or ""))
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(item)
        return deduped

    def _require_binance_profile(self, profile_id: str) -> dict[str, Any]:
        profile = self.runtime_profile_service.get_profile(profile_id)
        if str(profile.get("venue") or "").upper() != BINANCE_USDM_VENUE:
            raise BinanceUsdmReconciliationError(f"Runtime profile '{profile_id}' is not a Binance USDⓈ-M profile.")
        return profile

    @staticmethod
    def _resolve_status(warnings: list[dict[str, Any]]) -> str:
        codes = {str(item.get("code") or "") for item in warnings}
        if codes & DEGRADED_WARNING_CODES:
            return "DEGRADED"
        if codes & WARNING_ONLY_CODES:
            return "WARNING"
        return "READY"

    @staticmethod
    def _protective_order_summary(open_orders: list[dict[str, Any]]) -> dict[str, Any]:
        entry_count = 0
        protective_count = 0
        stop_loss_count = 0
        take_profit_count = 0
        trailing_stop_count = 0
        for item in open_orders:
            role = str(item.get("order_role") or ("PROTECTIVE" if item.get("is_protective") else "ENTRY"))
            protective_type = str(item.get("protective_order_type") or "NONE")
            if role == "PROTECTIVE":
                protective_count += 1
            else:
                entry_count += 1
            if protective_type == "STOP_LOSS":
                stop_loss_count += 1
            elif protective_type == "TAKE_PROFIT":
                take_profit_count += 1
            elif protective_type == "TRAILING_STOP":
                trailing_stop_count += 1
        return {
            "entry_open_order_count": entry_count,
            "protective_open_order_count": protective_count,
            "stop_loss_order_count": stop_loss_count,
            "take_profit_order_count": take_profit_count,
            "trailing_stop_order_count": trailing_stop_count,
        }

    @staticmethod
    def _warning(code: str, message: str, *, detail: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"code": code, "message": message}
        if detail:
            payload["detail"] = detail
        return payload

    @staticmethod
    def _parse_iso(value: Any) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _get_venue_flat_sync_min_age(self) -> int:
        """Resolve venue flat sync minimum age from unified config."""
        try:
            with session_scope() as session:
                val = self.settings_repo.get_value(session, "VENUE_FLAT_SYNC_MIN_AGE_SECONDS", default="30")
            return max(1, int(float(val)))
        except (TypeError, ValueError, Exception):
            return VENUE_FLAT_SYNC_MIN_AGE_SECONDS

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()


__all__ = [
    "BinanceUsdmReconciliationError",
    "BinanceUsdmReconciliationService",
    "RECONCILIATION_STATE_KEY",
]
