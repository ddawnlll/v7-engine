"""Binance USDⓈ-M REST read-only account-state sync."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from runtime.db.repos.settings_repo import SettingsRepository
from runtime.db.repos.state_repo import StateRepository
from runtime.db.repos.venue_state_repo import VenueStateRepository
from runtime.db.repos.runtime_profile_repo import RuntimeProfileRepository
from runtime.db.session import session_scope
from runtime.services.binance_usdm_reconciliation_service import BinanceUsdmReconciliationService
from runtime.services.runtime_profile_service import (
    BINANCE_USDM_VENUE,
    RuntimeProfileAccessError,
    RuntimeProfileConnectivityError,
    RuntimeProfileNotFoundError,
    RuntimeProfileService,
)

SYNC_STATE_KEY = "binance_usdm_rest_account_state_sync"
TRADE_HISTORY_STATE_KEY = "binance_usdm_trade_history_snapshot"
# Legacy module-level constants kept for backward compatibility.
# Actual values are now resolved from unified config at runtime via _get_config().
TRADE_HISTORY_REFRESH_HOURS = 6
TRADE_HISTORY_MAX_SYMBOLS = 12
TRADE_HISTORY_LOOKBACK_DAYS = 30
ORDER_HISTORY_LOOKBACK_DAYS = 89


class BinanceUsdmReadonlySyncError(ValueError):
    """Raised when Binance USDⓈ-M read-only sync cannot complete safely."""


class BinanceUsdmReadonlyService:
    def __init__(
        self,
        *,
        runtime_profile_service: RuntimeProfileService | None = None,
        venue_state_repo: VenueStateRepository | None = None,
        state_repo: StateRepository | None = None,
        runtime_profile_repo: RuntimeProfileRepository | None = None,
        reconciliation_service: BinanceUsdmReconciliationService | None = None,
        settings_repo: SettingsRepository | None = None,
    ) -> None:
        self.runtime_profile_service = runtime_profile_service or RuntimeProfileService()
        self.venue_state_repo = venue_state_repo or VenueStateRepository()
        self.state_repo = state_repo or StateRepository()
        self.runtime_profile_repo = runtime_profile_repo or RuntimeProfileRepository()
        self.settings_repo = settings_repo or SettingsRepository()
        self.reconciliation_service = reconciliation_service or BinanceUsdmReconciliationService(
            runtime_profile_service=self.runtime_profile_service,
            runtime_profile_repo=self.runtime_profile_repo,
            state_repo=self.state_repo,
            venue_state_repo=self.venue_state_repo,
        )

    def _get_config(self, profile_id: str) -> dict[str, int]:
        """Resolve operational thresholds from unified config."""
        try:
            with session_scope() as session:
                settings = self.settings_repo.get_all(session, profile_id=profile_id)
        except Exception:
            settings = {}
        return {
            "trade_history_refresh_hours": max(1, int(float(settings.get("TRADE_HISTORY_REFRESH_HOURS", "6")))),
            "trade_history_max_symbols": max(1, int(float(settings.get("TRADE_HISTORY_MAX_SYMBOLS", "12")))),
            "trade_history_lookback_days": max(1, int(float(settings.get("TRADE_HISTORY_LOOKBACK_DAYS", "30")))),
            "order_history_lookback_days": max(1, int(float(settings.get("ORDER_HISTORY_LOOKBACK_DAYS", "89")))),
        }

    def sync_account_state(self, profile_id: str) -> dict[str, Any]:
        access = self._require_live_profile(profile_id)
        now = self._utc_now_iso()
        try:
            account_info = self._request(profile_id, "/fapi/v2/account")
            balances_payload = self._request(profile_id, "/fapi/v2/balance")
            positions_payload = self._request(profile_id, "/fapi/v2/positionRisk")
            open_orders_payload = self._request(profile_id, "/fapi/v1/openOrders")
            open_algo_orders_payload = self._request(profile_id, "/fapi/v1/openAlgoOrders", params={"algoType": "CONDITIONAL"})
        except (RuntimeProfileAccessError, RuntimeProfileConnectivityError) as exc:
            self._record_sync_failure(access["profile"], str(exc), now)
            raise BinanceUsdmReadonlySyncError(str(exc)) from exc

        if not isinstance(account_info, dict):
            self._record_sync_failure(access["profile"], "Account information response was not an object.", now)
            raise BinanceUsdmReadonlySyncError("Account information response was not an object.")
        if not isinstance(balances_payload, list):
            self._record_sync_failure(access["profile"], "Balance response was not an array.", now)
            raise BinanceUsdmReadonlySyncError("Balance response was not an array.")
        if not isinstance(positions_payload, list):
            self._record_sync_failure(access["profile"], "Position risk response was not an array.", now)
            raise BinanceUsdmReadonlySyncError("Position risk response was not an array.")
        if not isinstance(open_orders_payload, list):
            self._record_sync_failure(access["profile"], "Open orders response was not an array.", now)
            raise BinanceUsdmReadonlySyncError("Open orders response was not an array.")
        if not isinstance(open_algo_orders_payload, list):
            self._record_sync_failure(access["profile"], "Open algo orders response was not an array.", now)
            raise BinanceUsdmReadonlySyncError("Open algo orders response was not an array.")

        normalized_account = self._normalize_account_summary(access, account_info, balances_payload, synced_at_utc=now)
        normalized_balances = [
            self._normalize_balance(access, item, synced_at_utc=now)
            for item in balances_payload
        ]
        open_position_payloads = [
            item for item in positions_payload
            if abs(self._as_float(item.get("positionAmt"))) > 0.0
        ]
        try:
            reconstructed_open_times = self._reconstruct_open_position_times(profile_id, open_position_payloads)
        except (RuntimeProfileAccessError, RuntimeProfileConnectivityError, BinanceUsdmReadonlySyncError) as exc:
            self._record_sync_failure(access["profile"], str(exc), now)
            raise BinanceUsdmReadonlySyncError(str(exc)) from exc
        normalized_positions = [
            self._normalize_position(
                access,
                {
                    **item,
                    "reconstructedOpenedAt": reconstructed_open_times.get(
                        (str(item.get("symbol") or "").upper(), str(item.get("positionSide") or "BOTH").upper())
                    ),
                },
                synced_at_utc=now,
            )
            for item in open_position_payloads
        ]
        normalized_orders = [
            self._normalize_order(access, item, synced_at_utc=now)
            for item in open_orders_payload
        ] + [
            self._normalize_algo_order(access, item, synced_at_utc=now)
            for item in open_algo_orders_payload
        ]
        history_warning = None
        try:
            history_snapshot = self._sync_trade_history_snapshot(
                access,
                profile_id=profile_id,
                account_id=f"{profile_id}:default",
                synced_at_utc=now,
                seed_symbols={
                    str(item.get("symbol") or "").upper()
                    for item in [*open_position_payloads, *open_orders_payload, *open_algo_orders_payload]
                    if str(item.get("symbol") or "").strip()
                },
            )
        except (RuntimeProfileAccessError, RuntimeProfileConnectivityError, BinanceUsdmReadonlySyncError) as exc:
            history_warning = str(exc)
            with session_scope() as session:
                history_snapshot = self.state_repo.get(session, TRADE_HISTORY_STATE_KEY, default=None, profile_id=profile_id) or {
                    "generated_at_utc": now,
                    "items": [],
                }
            history_snapshot["warning"] = history_warning
            history_snapshot["generated_at_utc"] = history_snapshot.get("generated_at_utc") or now

        with session_scope() as session:
            account = self.venue_state_repo.save_account_summary(session, normalized_account)
            balances = self.venue_state_repo.replace_balances(session, profile_id, account["account_id"], normalized_balances)
            positions = self.venue_state_repo.replace_positions(session, profile_id, account["account_id"], normalized_positions)
            orders = self.venue_state_repo.upsert_open_orders(session, normalized_orders)
            sync_state = {
                "status": "SYNCED",
                "last_synced_at_utc": now,
                "account_id": account["account_id"],
                "balance_count": len(balances),
                "position_count": len(positions),
                "open_order_count": len([item for item in orders if item["status"] in {"NEW", "PARTIALLY_FILLED", "PENDING_CANCEL"}]),
                "last_error": None,
                "history_warning": history_warning,
            }
            self.state_repo.set(session, SYNC_STATE_KEY, sync_state, profile_id=profile_id)
            self.state_repo.set(session, TRADE_HISTORY_STATE_KEY, history_snapshot, profile_id=profile_id)
            profile = self.runtime_profile_repo.get_profile(session, profile_id)
            assert profile is not None
            updated_profile = self.runtime_profile_repo.save_profile(
                session,
                {
                    **profile,
                    "connectivity_status": "CONNECTED",
                    "last_connectivity_check_at_utc": now,
                    "last_connectivity_ok_at_utc": now,
                    "last_connectivity_error": None,
                    "updated_at_utc": now,
                },
            )

        reconciliation = self.reconciliation_service.reconcile(profile_id)
        return {
            "profile": self.runtime_profile_service._sanitize_profile(updated_profile),
            "account": account,
            "balances": balances,
            "positions": positions,
            "open_orders": [item for item in orders if item["status"] in {"NEW", "PARTIALLY_FILLED", "PENDING_CANCEL"}],
            "sync": sync_state,
            "reconciliation": reconciliation,
        }

    def get_persisted_state(self, profile_id: str) -> dict[str, Any]:
        self._require_profile_exists(profile_id)
        with session_scope() as session:
            account = self.venue_state_repo.get_account_summary(session, profile_id)
            balances = self.venue_state_repo.list_balances(session, profile_id, account_id=account["account_id"] if account else None)
            positions = self.venue_state_repo.list_positions(session, profile_id, account_id=account["account_id"] if account else None)
            open_orders = self.venue_state_repo.list_open_orders(session, profile_id, account_id=account["account_id"] if account else None)
            sync = self.state_repo.get(session, SYNC_STATE_KEY, default=None, profile_id=profile_id)
            trade_history = self.state_repo.get(session, TRADE_HISTORY_STATE_KEY, default=None, profile_id=profile_id)
        return {
            "profile": self.runtime_profile_service.get_profile(profile_id),
            "account": account,
            "balances": balances,
            "positions": positions,
            "open_orders": open_orders,
            "sync": sync,
            "trade_history": trade_history,
            "reconciliation": self.reconciliation_service.get_reconciliation(profile_id),
        }

    def query_order_status(
        self,
        profile_id: str,
        *,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        access = self._require_live_profile(profile_id)
        if not order_id and not client_order_id:
            raise BinanceUsdmReadonlySyncError("Either order_id or client_order_id is required.")
        now = self._utc_now_iso()
        params: dict[str, Any] = {"symbol": str(symbol or "").upper()}
        if order_id:
            params["orderId"] = order_id
        if client_order_id:
            params["origClientOrderId"] = client_order_id
        try:
            payload = self._request(profile_id, "/fapi/v1/order", params=params)
        except (RuntimeProfileAccessError, RuntimeProfileConnectivityError) as exc:
            if not self._is_missing_order_lookup_error(exc):
                self._record_sync_failure(access["profile"], str(exc), now)
            raise BinanceUsdmReadonlySyncError(str(exc)) from exc
        if not isinstance(payload, dict):
            raise BinanceUsdmReadonlySyncError("Order status response was not an object.")
        normalized = self._normalize_order(access, payload, synced_at_utc=now)
        with session_scope() as session:
            saved = self.venue_state_repo.upsert_order(session, normalized)
            sync = self.state_repo.get(session, SYNC_STATE_KEY, default={}, profile_id=profile_id) or {}
            sync["last_order_status_sync_at_utc"] = now
            sync["last_order_status_symbol"] = params["symbol"]
            sync["last_order_status_order_id"] = str(saved["venue_order_id"])
            sync["last_error"] = None
            self.state_repo.set(session, SYNC_STATE_KEY, sync, profile_id=profile_id)
        self.reconciliation_service.reconcile(profile_id)
        return saved

    def query_algo_order_status(
        self,
        profile_id: str,
        *,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        access = self._require_live_profile(profile_id)
        if not order_id and not client_order_id:
            raise BinanceUsdmReadonlySyncError("Either order_id or client_order_id is required.")
        now = self._utc_now_iso()
        params: dict[str, Any] = {}
        if order_id:
            params["algoId"] = order_id
        if client_order_id:
            params["clientAlgoId"] = client_order_id
        try:
            payload = self._request(profile_id, "/fapi/v1/algoOrder", params=params)
        except (RuntimeProfileAccessError, RuntimeProfileConnectivityError) as exc:
            if not self._is_missing_order_lookup_error(exc):
                self._record_sync_failure(access["profile"], str(exc), now)
            raise BinanceUsdmReadonlySyncError(str(exc)) from exc
        if not isinstance(payload, dict):
            raise BinanceUsdmReadonlySyncError("Algo order status response was not an object.")
        normalized = self._normalize_algo_order(access, {"symbol": symbol, **payload}, synced_at_utc=now)
        with session_scope() as session:
            saved = self.venue_state_repo.upsert_order(session, normalized)
            sync = self.state_repo.get(session, SYNC_STATE_KEY, default={}, profile_id=profile_id) or {}
            sync["last_order_status_sync_at_utc"] = now
            sync["last_order_status_symbol"] = str(symbol or "").upper()
            sync["last_order_status_order_id"] = str(saved["venue_order_id"])
            sync["last_error"] = None
            self.state_repo.set(session, SYNC_STATE_KEY, sync, profile_id=profile_id)
        self.reconciliation_service.reconcile(profile_id)
        return saved

    def _require_profile_exists(self, profile_id: str) -> None:
        self.runtime_profile_service.get_profile(profile_id)

    def _require_live_profile(self, profile_id: str) -> dict[str, Any]:
        access = self.runtime_profile_service.get_profile_access(profile_id, require_account_reads=True)
        profile = access["profile"]
        if str(profile.get("venue") or "").upper() != BINANCE_USDM_VENUE:
            raise BinanceUsdmReadonlySyncError(f"Runtime profile '{profile_id}' is not a Binance USDⓈ-M profile.")
        if not access["credentials_configured"]:
            raise BinanceUsdmReadonlySyncError("Credential reference is not fully configured.")
        return access

    @staticmethod
    def _is_missing_order_lookup_error(exc: Exception) -> bool:
        error_text = str(exc).lower()
        return "-2013" in error_text and "order does not exist" in error_text

    def _record_sync_failure(self, profile: dict[str, Any], error_text: str, timestamp: str) -> None:
        with session_scope() as session:
            current = self.runtime_profile_repo.get_profile(session, str(profile.get("profile_id") or ""))
            if current is not None:
                self.runtime_profile_repo.save_profile(
                    session,
                    {
                        **current,
                        "connectivity_status": "ERROR",
                        "last_connectivity_check_at_utc": timestamp,
                        "last_connectivity_error": error_text,
                        "updated_at_utc": timestamp,
                    },
                )
            self.state_repo.set(
                session,
                SYNC_STATE_KEY,
                {
                    "status": "ERROR",
                    "last_synced_at_utc": None,
                    "last_error": error_text,
                    "failed_at_utc": timestamp,
                },
                profile_id=str(profile.get("profile_id") or ""),
            )

    def _request(self, profile_id: str, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
        return self.runtime_profile_service.signed_get_json(profile_id, path, params=params)

    def _normalize_account_summary(self, access: dict[str, Any], payload: dict[str, Any], balances_payload: list[dict[str, Any]], *, synced_at_utc: str) -> dict[str, Any]:
        profile_id = str(access["profile"].get("profile_id") or "")
        venue_account_key = str((balances_payload[0] or {}).get("accountAlias") or payload.get("accountAlias") or "").strip() or None
        return {
            "account_id": f"{profile_id}:default",
            "profile_id": profile_id,
            "account_key": "default",
            "account_type": "LIVE_FUTURES_USDM_READ_ONLY",
            "venue_account_key": venue_account_key,
            "balance_ccy": "USDT",
            "balance": self._as_float(payload.get("totalWalletBalance")),
            "available_balance": self._as_float(payload.get("availableBalance")),
            "equity": self._as_float(payload.get("totalMarginBalance")),
            "margin_used": self._as_float(payload.get("totalInitialMargin")),
            "payload": {
                "venue": BINANCE_USDM_VENUE,
                "fee_tier": self._as_int(payload.get("feeTier")),
                "can_trade": bool(payload.get("canTrade")),
                "can_deposit": bool(payload.get("canDeposit")),
                "can_withdraw": bool(payload.get("canWithdraw")),
                "multi_assets_margin": bool(payload.get("multiAssetsMargin")),
                "trade_group_id": self._as_int(payload.get("tradeGroupId")),
                "total_initial_margin": self._as_float(payload.get("totalInitialMargin")),
                "total_maint_margin": self._as_float(payload.get("totalMaintMargin")),
                "total_wallet_balance": self._as_float(payload.get("totalWalletBalance")),
                "total_unrealized_profit": self._as_float(payload.get("totalUnrealizedProfit")),
                "total_margin_balance": self._as_float(payload.get("totalMarginBalance")),
                "total_position_initial_margin": self._as_float(payload.get("totalPositionInitialMargin")),
                "total_open_order_initial_margin": self._as_float(payload.get("totalOpenOrderInitialMargin")),
                "total_cross_wallet_balance": self._as_float(payload.get("totalCrossWalletBalance")),
                "total_cross_unpnl": self._as_float(payload.get("totalCrossUnPnl")),
                "available_balance": self._as_float(payload.get("availableBalance")),
                "max_withdraw_amount": self._as_float(payload.get("maxWithdrawAmount")),
                "update_time": self._as_int(payload.get("updateTime")),
            },
            "as_of_utc": synced_at_utc,
            "created_at_utc": synced_at_utc,
            "updated_at_utc": synced_at_utc,
        }

    def _normalize_balance(self, access: dict[str, Any], payload: dict[str, Any], *, synced_at_utc: str) -> dict[str, Any]:
        profile_id = str(access["profile"].get("profile_id") or "")
        account_id = f"{profile_id}:default"
        asset = str(payload.get("asset") or "").upper()
        return {
            "balance_id": f"{profile_id}:{account_id}:{asset}",
            "profile_id": profile_id,
            "account_id": account_id,
            "venue": BINANCE_USDM_VENUE,
            "asset": asset,
            "balance": self._as_float(payload.get("balance")),
            "available_balance": self._as_float(payload.get("availableBalance")),
            "margin_balance": self._as_float(payload.get("balance")) + self._as_float(payload.get("crossUnPnl")),
            "cross_wallet_balance": self._as_float(payload.get("crossWalletBalance")),
            "cross_unrealized_pnl": self._as_float(payload.get("crossUnPnl")),
            "max_withdraw_amount": self._as_float(payload.get("maxWithdrawAmount")),
            "margin_available": bool(payload.get("marginAvailable")),
            "update_time_utc": self._ms_to_iso(payload.get("updateTime")),
            "synced_at_utc": synced_at_utc,
            "payload": dict(payload),
        }

    def _normalize_position(self, access: dict[str, Any], payload: dict[str, Any], *, synced_at_utc: str) -> dict[str, Any]:
        profile_id = str(access["profile"].get("profile_id") or "")
        account_id = f"{profile_id}:default"
        symbol = str(payload.get("symbol") or "").upper()
        position_side = str(payload.get("positionSide") or "BOTH").upper()
        quantity = self._as_float(payload.get("positionAmt"))
        return {
            "position_id": f"{profile_id}:{symbol}:{position_side}",
            "profile_id": profile_id,
            "account_id": account_id,
            "venue": BINANCE_USDM_VENUE,
            "symbol": symbol,
            "position_side": position_side,
            "status": "OPEN" if abs(quantity) > 0.0 else "CLOSED",
            "quantity": quantity,
            "entry_price": self._as_float(payload.get("entryPrice")),
            "break_even_price": self._as_float(payload.get("breakEvenPrice")),
            "mark_price": self._as_float(payload.get("markPrice")),
            "unrealized_pnl": self._as_float(payload.get("unRealizedProfit")),
            "liquidation_price": self._as_float(payload.get("liquidationPrice")),
            "leverage": self._as_float(payload.get("leverage")),
            "margin_type": str(payload.get("marginType") or "cross"),
            "isolated": str(payload.get("marginType") or "cross").lower() == "isolated",
            "isolated_margin": self._as_float(payload.get("isolatedMargin")),
            "notional": self._as_float(payload.get("notional")),
            "max_notional_value": self._as_float(payload.get("maxNotionalValue")),
            "update_time_utc": self._ms_to_iso(payload.get("updateTime")),
            "synced_at_utc": synced_at_utc,
            "payload": {
                **dict(payload),
                "marginAsset": payload.get("marginAsset"),
                "initialMargin": self._as_float(payload.get("initialMargin")),
                "maintMargin": self._as_float(payload.get("maintMargin")),
                "positionInitialMargin": self._as_float(payload.get("positionInitialMargin")),
                "openOrderInitialMargin": self._as_float(payload.get("openOrderInitialMargin")),
                "adl": self._as_int(payload.get("adl")),
                "reconstructedOpenedAt": payload.get("reconstructedOpenedAt"),
            },
        }

    def _normalize_order(self, access: dict[str, Any], payload: dict[str, Any], *, synced_at_utc: str) -> dict[str, Any]:
        profile_id = str(access["profile"].get("profile_id") or "")
        account_id = f"{profile_id}:default"
        symbol = str(payload.get("symbol") or "").upper()
        venue_order_id = str(payload.get("orderId") or "")
        order_type = str(payload.get("type") or payload.get("origType") or "LIMIT").upper()
        reduce_only = bool(payload.get("reduceOnly"))
        close_position = bool(payload.get("closePosition"))
        order_role, protective_order_type, is_protective = self.classify_order_posture(
            order_type=order_type,
            orig_type=payload.get("origType"),
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
            "client_order_id": payload.get("clientOrderId"),
            "side": str(payload.get("side") or "BUY"),
            "position_side": str(payload.get("positionSide") or "BOTH"),
            "status": str(payload.get("status") or "NEW"),
            "order_type": order_type,
            "orig_type": payload.get("origType"),
            "time_in_force": payload.get("timeInForce"),
            "quantity": self._as_float(payload.get("origQty")),
            "executed_quantity": self._as_float(payload.get("executedQty")),
            "price": self._as_float(payload.get("price")),
            "avg_price": self._as_float(payload.get("avgPrice")),
            "stop_price": self._nullable_float(payload.get("stopPrice")),
            "activate_price": self._nullable_float(payload.get("activatePrice")),
            "price_rate": self._nullable_float(payload.get("priceRate")),
            "reduce_only": reduce_only,
            "close_position": close_position,
            "working_type": payload.get("workingType"),
            "price_protect": bool(payload.get("priceProtect")),
            "is_protective": is_protective,
            "order_role": order_role,
            "protective_order_type": protective_order_type,
            "opened_at_utc": self._ms_to_iso(payload.get("time")),
            "updated_at_utc": self._ms_to_iso(payload.get("updateTime")),
            "synced_at_utc": synced_at_utc,
            "payload": dict(payload),
        }

    def _normalize_algo_order(self, access: dict[str, Any], payload: dict[str, Any], *, synced_at_utc: str) -> dict[str, Any]:
        profile_id = str(access["profile"].get("profile_id") or "")
        account_id = f"{profile_id}:default"
        symbol = str(payload.get("symbol") or "").upper()
        venue_order_id = str(payload.get("algoId") or "")
        order_type = str(payload.get("orderType") or payload.get("type") or "STOP_MARKET").upper()
        close_position = bool(payload.get("closePosition"))
        reduce_only = bool(payload.get("reduceOnly"))
        order_role, protective_order_type, is_protective = self.classify_order_posture(
            order_type=order_type,
            orig_type=payload.get("orderType") or payload.get("type"),
            reduce_only=reduce_only,
            close_position=close_position,
        )
        status = self._normalize_algo_status(payload.get("algoStatus"))
        return {
            "order_key": f"{profile_id}:{symbol}:algo:{venue_order_id or str(payload.get('clientAlgoId') or '')}",
            "profile_id": profile_id,
            "account_id": account_id,
            "venue": BINANCE_USDM_VENUE,
            "symbol": symbol,
            "venue_order_id": venue_order_id,
            "client_order_id": payload.get("clientAlgoId"),
            "side": str(payload.get("side") or "BUY"),
            "position_side": str(payload.get("positionSide") or "BOTH"),
            "status": status,
            "order_type": order_type,
            "orig_type": payload.get("orderType") or payload.get("type"),
            "time_in_force": payload.get("timeInForce"),
            "quantity": self._as_float(payload.get("quantity")),
            "executed_quantity": self._as_float(payload.get("executedQty") or payload.get("executedQuantity")),
            "price": self._as_float(payload.get("price")),
            "avg_price": self._as_float(payload.get("avgPrice") or payload.get("actualPrice")),
            "stop_price": self._nullable_float(payload.get("triggerPrice")),
            "activate_price": self._nullable_float(payload.get("activatePrice")),
            "price_rate": self._nullable_float(payload.get("callbackRate")),
            "reduce_only": reduce_only,
            "close_position": close_position,
            "working_type": payload.get("workingType"),
            "price_protect": bool(payload.get("priceProtect")),
            "is_protective": is_protective,
            "order_role": order_role,
            "protective_order_type": protective_order_type,
            "opened_at_utc": self._ms_to_iso(payload.get("createTime")),
            "updated_at_utc": self._ms_to_iso(payload.get("updateTime")) or synced_at_utc,
            "synced_at_utc": synced_at_utc,
            "payload": {**dict(payload), "algo_order": True},
        }

    @staticmethod
    def _normalize_algo_status(value: Any) -> str:
        normalized = str(value or "NEW").upper()
        if normalized in {"TRIGGERED", "FILLED"}:
            return "FILLED"
        if normalized in {"CANCELLED", "CANCELED"}:
            return "CANCELED"
        if normalized in {"EXPIRED", "REJECTED", "FAILED"}:
            return normalized
        return "NEW"

    def _reconstruct_open_position_times(self, profile_id: str, positions_payload: list[dict[str, Any]]) -> dict[tuple[str, str], str | None]:
        if not positions_payload:
            return {}
        symbols = sorted({str(item.get("symbol") or "").upper() for item in positions_payload if str(item.get("symbol") or "").strip()})
        trades_by_symbol = {
            symbol: self._fetch_user_trades(profile_id, symbol)
            for symbol in symbols
        }
        result: dict[tuple[str, str], str | None] = {}
        for item in positions_payload:
            symbol = str(item.get("symbol") or "").upper()
            position_side = str(item.get("positionSide") or "BOTH").upper()
            current_quantity = self._as_float(item.get("positionAmt"))
            reconstructed = self._reconstruct_open_time_from_trades(
                trades_by_symbol.get(symbol) or [],
                position_side=position_side,
                current_quantity=current_quantity,
            )
            if reconstructed is None and position_side in {"LONG", "SHORT"}:
                reconstructed = self._reconstruct_open_time_from_trades(
                    trades_by_symbol.get(symbol) or [],
                    position_side="BOTH",
                    current_quantity=current_quantity,
                )
            result[(symbol, position_side)] = reconstructed
        return result

    def _sync_trade_history_snapshot(
        self,
        access: dict[str, Any],
        *,
        profile_id: str,
        account_id: str,
        synced_at_utc: str,
        seed_symbols: set[str] | None = None,
    ) -> dict[str, Any]:
        cfg = self._get_config(profile_id)
        trade_history_lookback_days = cfg["trade_history_lookback_days"]
        trade_history_max_symbols = cfg["trade_history_max_symbols"]
        trade_history_refresh_hours = cfg["trade_history_refresh_hours"]
        order_history_lookback_days = cfg["order_history_lookback_days"]
        with session_scope() as session:
            existing = self.state_repo.get(session, TRADE_HISTORY_STATE_KEY, default=None, profile_id=profile_id) or {}
        if self._history_snapshot_fresh(existing, refresh_hours=trade_history_refresh_hours):
            return existing
        symbols = self._discover_history_symbols(profile_id, seed_symbols=seed_symbols, max_symbols=trade_history_max_symbols)
        rows: list[dict[str, Any]] = []
        order_count = 0
        algo_order_count = 0
        with session_scope() as session:
            for symbol in symbols:
                trades = self._fetch_user_trades(profile_id, symbol, lookback_days=trade_history_lookback_days)
                orders_payload = self._fetch_all_orders(profile_id, symbol, lookback_days=order_history_lookback_days)
                algo_orders_payload = self._fetch_all_algo_orders(profile_id, symbol, lookback_days=order_history_lookback_days)
                normalized_orders = [
                    self._normalize_order(access, item, synced_at_utc=synced_at_utc)
                    for item in orders_payload
                    if isinstance(item, dict)
                ] + [
                    self._normalize_algo_order(access, item, synced_at_utc=synced_at_utc)
                    for item in algo_orders_payload
                    if isinstance(item, dict)
                ]
                if normalized_orders:
                    self.venue_state_repo.upsert_open_orders(session, normalized_orders)
                order_count += len(orders_payload)
                algo_order_count += len(algo_orders_payload)
                rows.extend(
                    self._derive_closed_trade_rows(
                        profile_id=profile_id,
                        account_id=account_id,
                        symbol=symbol,
                        trades=trades,
                        normalized_orders=normalized_orders,
                        synced_at_utc=synced_at_utc,
                    )
                )
        rows.sort(key=lambda row: str(row.get("close_timestamp") or row.get("open_timestamp") or ""), reverse=True)
        return {
            "generated_at_utc": synced_at_utc,
            "lookback_days": trade_history_lookback_days,
            "symbol_count": len(symbols),
            "closed_trade_count": len(rows),
            "order_count": order_count,
            "algo_order_count": algo_order_count,
            "items": rows[:1000],
        }

    def _discover_history_symbols(self, profile_id: str, *, seed_symbols: set[str] | None = None, max_symbols: int = TRADE_HISTORY_MAX_SYMBOLS) -> list[str]:
        symbols = set(seed_symbols or set())
        if not symbols:
            symbols.update(self._fetch_income_symbols(profile_id))
        state = self.get_persisted_state(profile_id)
        symbols.update(
            str(item.get("symbol") or "").upper()
            for item in (state.get("positions") or [])
            if str(item.get("symbol") or "").strip()
        )
        symbols.update(
            str(item.get("symbol") or "").upper()
            for item in (state.get("open_orders") or [])
            if str(item.get("symbol") or "").strip()
        )
        return sorted(item for item in symbols if item)[:max_symbols]

    @staticmethod
    def _history_snapshot_fresh(snapshot: dict[str, Any], *, refresh_hours: int = TRADE_HISTORY_REFRESH_HOURS) -> bool:
        generated_at = str(snapshot.get("generated_at_utc") or "").strip()
        if not generated_at:
            return False
        try:
            created = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        return (datetime.now(timezone.utc) - created) < timedelta(hours=refresh_hours)

    def _fetch_income_symbols(self, profile_id: str, *, lookback_days: int = TRADE_HISTORY_LOOKBACK_DAYS) -> list[str]:
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=lookback_days)
        symbols: set[str] = set()
        cursor = start
        while cursor < now:
            window_end = min(cursor + timedelta(days=7), now)
            payload = self._request(
                profile_id,
                "/fapi/v1/income",
                params={
                    "startTime": int(cursor.timestamp() * 1000),
                    "endTime": int(window_end.timestamp() * 1000),
                    "limit": 1000,
                },
            )
            if not isinstance(payload, list):
                raise BinanceUsdmReadonlySyncError("Income history response was not an array.")
            for row in payload:
                if not isinstance(row, dict):
                    continue
                symbol = str(row.get("symbol") or "").upper().strip()
                if symbol:
                    symbols.add(symbol)
            cursor = window_end
        return sorted(symbols)

    def _fetch_user_trades(self, profile_id: str, symbol: str, *, lookback_days: int = TRADE_HISTORY_LOOKBACK_DAYS) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=lookback_days)
        items: list[dict[str, Any]] = []
        seen: set[tuple[Any, Any, Any]] = set()
        cursor = window_start
        while cursor < now:
            window_end = min(cursor + timedelta(days=7), now)
            payload = self._request(
                profile_id,
                "/fapi/v1/userTrades",
                params={
                    "symbol": symbol,
                    "startTime": int(cursor.timestamp() * 1000),
                    "endTime": int(window_end.timestamp() * 1000),
                    "limit": 1000,
                },
            )
            if not isinstance(payload, list):
                raise BinanceUsdmReadonlySyncError("User trades response was not an array.")
            for row in payload:
                if not isinstance(row, dict):
                    continue
                key = (row.get("id"), row.get("time"), row.get("orderId"))
                if key in seen:
                    continue
                seen.add(key)
                items.append(row)
            cursor = window_end
        items.sort(key=lambda row: (self._as_int(row.get("time")) or 0, self._as_int(row.get("id")) or 0))
        return items

    def _fetch_all_orders(self, profile_id: str, symbol: str, *, lookback_days: int = ORDER_HISTORY_LOOKBACK_DAYS) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=lookback_days)
        items: list[dict[str, Any]] = []
        seen: set[tuple[Any, Any]] = set()
        cursor = start
        while cursor < now:
            window_end = min(cursor + timedelta(days=7), now)
            payload = self._request(
                profile_id,
                "/fapi/v1/allOrders",
                params={
                    "symbol": symbol,
                    "startTime": int(cursor.timestamp() * 1000),
                    "endTime": int(window_end.timestamp() * 1000),
                    "limit": 1000,
                },
            )
            if not isinstance(payload, list):
                raise BinanceUsdmReadonlySyncError("All orders response was not an array.")
            for row in payload:
                if not isinstance(row, dict):
                    continue
                key = (row.get("orderId"), row.get("time"))
                if key in seen:
                    continue
                seen.add(key)
                items.append(row)
            cursor = window_end
        return items

    def _fetch_all_algo_orders(self, profile_id: str, symbol: str, *, lookback_days: int = ORDER_HISTORY_LOOKBACK_DAYS) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=lookback_days)
        items: list[dict[str, Any]] = []
        seen: set[tuple[Any, Any]] = set()
        cursor = start
        while cursor < now:
            window_end = min(cursor + timedelta(days=7), now)
            payload = self._request(
                profile_id,
                "/fapi/v1/allAlgoOrders",
                params={
                    "symbol": symbol,
                    "algoType": "CONDITIONAL",
                    "startTime": int(cursor.timestamp() * 1000),
                    "endTime": int(window_end.timestamp() * 1000),
                    "limit": 1000,
                },
            )
            if not isinstance(payload, list):
                raise BinanceUsdmReadonlySyncError("All algo orders response was not an array.")
            for row in payload:
                if not isinstance(row, dict):
                    continue
                key = (row.get("algoId"), row.get("createTime"))
                if key in seen:
                    continue
                seen.add(key)
                items.append(row)
            cursor = window_end
        return items

    def _derive_closed_trade_rows(
        self,
        *,
        profile_id: str,
        account_id: str,
        symbol: str,
        trades: list[dict[str, Any]],
        normalized_orders: list[dict[str, Any]],
        synced_at_utc: str,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for position_side in sorted({str(item.get("positionSide") or "BOTH").upper() for item in trades} or {"BOTH"}):
            rows.extend(
                self._derive_closed_trade_rows_for_side(
                    profile_id=profile_id,
                    account_id=account_id,
                    symbol=symbol,
                    position_side=position_side,
                    trades=trades,
                    normalized_orders=normalized_orders,
                    synced_at_utc=synced_at_utc,
                )
            )
        return rows

    def _derive_closed_trade_rows_for_side(
        self,
        *,
        profile_id: str,
        account_id: str,
        symbol: str,
        position_side: str,
        trades: list[dict[str, Any]],
        normalized_orders: list[dict[str, Any]],
        synced_at_utc: str,
    ) -> list[dict[str, Any]]:
        epsilon = 1e-9
        side_trades = [item for item in trades if str(item.get("positionSide") or "BOTH").upper() == position_side]
        side_trades.sort(key=lambda row: (self._as_int(row.get("time")) or 0, self._as_int(row.get("id")) or 0))
        rows: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        net = 0.0

        def start_lifecycle(direction: str, qty: float, price: float, timestamp_ms: int | None) -> dict[str, Any]:
            return {
                "direction": direction,
                "entry_qty": qty,
                "entry_value": price * qty,
                "exit_qty": 0.0,
                "exit_value": 0.0,
                "realized_pnl": 0.0,
                "open_ms": timestamp_ms,
                "close_ms": None,
                "max_qty": qty,
            }

        for trade in side_trades:
            qty = self._as_float(trade.get("qty"))
            price = self._as_float(trade.get("price"))
            timestamp_ms = self._as_int(trade.get("time"))
            side = str(trade.get("side") or "").upper()
            if qty <= 0.0 or price <= 0.0 or side not in {"BUY", "SELL"}:
                continue
            delta = self._trade_delta_for_position_side(position_side, side, qty)
            previous_net = net
            if current is None and abs(previous_net) <= epsilon:
                lifecycle_direction = "BUY" if delta > 0 else "SELL"
                current = start_lifecycle(lifecycle_direction, abs(delta), price, timestamp_ms)
                net = previous_net + delta
                current["max_qty"] = max(current["max_qty"], abs(net))
                continue

            if position_side == "BOTH":
                same_direction = (previous_net >= 0 and delta >= 0) or (previous_net <= 0 and delta <= 0)
            else:
                same_direction = delta > 0

            if same_direction:
                if current is None:
                    current = start_lifecycle("BUY" if delta > 0 else "SELL", abs(delta), price, timestamp_ms)
                else:
                    current["entry_qty"] += abs(delta)
                    current["entry_value"] += price * abs(delta)
                net = previous_net + delta
                current["max_qty"] = max(current["max_qty"], abs(net))
                continue

            close_qty = min(abs(previous_net), abs(delta))
            if current is None:
                net = previous_net + delta
                continue
            current["exit_qty"] += close_qty
            current["exit_value"] += price * close_qty
            current["realized_pnl"] += self._as_float(trade.get("realizedPnl"))
            net = previous_net + delta
            if abs(net) <= epsilon or (position_side == "BOTH" and ((previous_net > 0 and net < 0) or (previous_net < 0 and net > 0))):
                current["close_ms"] = timestamp_ms
                row = self._closed_trade_row_from_lifecycle(
                    profile_id=profile_id,
                    account_id=account_id,
                    symbol=symbol,
                    position_side=position_side,
                    lifecycle=current,
                    normalized_orders=normalized_orders,
                    synced_at_utc=synced_at_utc,
                )
                if row is not None:
                    rows.append(row)
                leftover = abs(net)
                if leftover > epsilon:
                    current = start_lifecycle("BUY" if net > 0 else "SELL", leftover, price, timestamp_ms)
                    current["max_qty"] = leftover
                else:
                    current = None
                    net = 0.0
        return rows

    def _closed_trade_row_from_lifecycle(
        self,
        *,
        profile_id: str,
        account_id: str,
        symbol: str,
        position_side: str,
        lifecycle: dict[str, Any],
        normalized_orders: list[dict[str, Any]],
        synced_at_utc: str,
    ) -> dict[str, Any] | None:
        open_ms = self._as_int(lifecycle.get("open_ms"))
        close_ms = self._as_int(lifecycle.get("close_ms"))
        entry_qty = self._as_float(lifecycle.get("entry_qty"))
        exit_qty = self._as_float(lifecycle.get("exit_qty"))
        if not open_ms or not close_ms or entry_qty <= 0.0 or exit_qty <= 0.0:
            return None
        entry_price = self._as_float(lifecycle.get("entry_value")) / entry_qty if entry_qty > 0 else 0.0
        close_price = self._as_float(lifecycle.get("exit_value")) / exit_qty if exit_qty > 0 else 0.0
        direction = str(lifecycle.get("direction") or "BUY").upper()
        protection_history = self._match_historical_protection(
            symbol=symbol,
            position_side=position_side,
            direction=direction,
            open_ms=open_ms,
            close_ms=close_ms,
            normalized_orders=normalized_orders,
        )
        stop_loss = self._nullable_float(protection_history.get("stop_loss"))
        take_profit = self._nullable_float(protection_history.get("take_profit"))
        realized_pnl_pct = self._pnl_pct(direction=direction, entry=entry_price, close_price=close_price)
        expected_r = self._expected_r(entry=entry_price, stop_loss=stop_loss, take_profit=take_profit)
        realized_r = self._realized_r(direction=direction, entry=entry_price, stop_loss=stop_loss, close_price=close_price)
        realized_r_estimated = False
        if realized_r is None:
            realized_r = self._estimated_realized_r_from_price_move(realized_pnl_pct)
            realized_r_estimated = realized_r is not None
        synthetic_order_id = f"venue-history:{profile_id}:{symbol}:{position_side}:{open_ms}:{close_ms}"
        return {
            "id": synthetic_order_id,
            "order_id": synthetic_order_id,
            "profile_id": profile_id,
            "account_id": account_id,
            "execution_mode": "LIVE",
            "venue": BINANCE_USDM_VENUE,
            "source": "READ_ONLY_HISTORY",
            "origin": "VENUE_HISTORY",
            "status": "CLOSED",
            "lifecycle_status": "CLOSED",
            "is_open": False,
            "symbol": symbol,
            "direction": direction,
            "position_side": position_side,
            "interval": "--",
            "mode": "LIVE_HISTORY",
            "quantity": self._as_float(lifecycle.get("max_qty")),
            "entry": round(entry_price, 8),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "close_price": round(close_price, 8),
            "open_timestamp": self._ms_to_iso(open_ms),
            "close_timestamp": self._ms_to_iso(close_ms),
            "expected_r": expected_r,
            "realized_r": realized_r,
            "realized_r_estimated": realized_r_estimated,
            "realized_r_estimation_method": "price_move_pct_over_1pct_risk" if realized_r_estimated else None,
            "realized_pnl": round(self._as_float(lifecycle.get("realized_pnl")), 8),
            "realized_pnl_pct": realized_pnl_pct,
            "close_reason": protection_history.get("exit_reason") or "VENUE_HISTORY",
            "protection_status": protection_history.get("status"),
            "protection_summary": protection_history.get("summary"),
            "signal_payload": {
                "summary": "Reconstructed from Binance user trade history.",
            },
            "payload": {
                "venue_history": True,
                "synced_at_utc": synced_at_utc,
                "protection_history": protection_history,
                "realized_pnl_pct": realized_pnl_pct,
                "expected_r": expected_r,
                "realized_r": realized_r,
                "realized_r_estimated": realized_r_estimated,
                "realized_r_estimation_method": "price_move_pct_over_1pct_risk" if realized_r_estimated else None,
            },
        }

    def _match_historical_protection(
        self,
        *,
        symbol: str,
        position_side: str,
        direction: str,
        open_ms: int,
        close_ms: int,
        normalized_orders: list[dict[str, Any]],
    ) -> dict[str, Any]:
        expected_side = "SELL" if direction == "BUY" else "BUY"
        matched = []
        exit_reason = None
        stop_loss = None
        take_profit = None
        for order in normalized_orders:
            if str(order.get("symbol") or "").upper() != symbol:
                continue
            if str(order.get("position_side") or "BOTH").upper() not in {position_side, "BOTH"}:
                continue
            if str(order.get("side") or "").upper() != expected_side:
                continue
            if str(order.get("order_role") or "").upper() != "PROTECTIVE" and not bool(order.get("is_protective")):
                continue
            order_open_ms = self._iso_to_ms(order.get("opened_at_utc")) or self._iso_to_ms(order.get("updated_at_utc"))
            if order_open_ms is None or order_open_ms < open_ms - 3_600_000 or order_open_ms > close_ms + 3_600_000:
                continue
            matched.append(order)
            protective_type = str(order.get("protective_order_type") or "").upper()
            trigger_price = self._protective_order_trigger_price(order)
            if protective_type == "STOP_LOSS" and stop_loss is None:
                stop_loss = trigger_price
            elif protective_type == "TAKE_PROFIT" and take_profit is None:
                take_profit = trigger_price
            if str(order.get("status") or "").upper() == "FILLED":
                exit_reason = str(order.get("protective_order_type") or "PROTECTIVE_EXIT")
        status = "NONE"
        summary = "No historical protective orders were matched."
        if matched:
            status = "MATCHED"
            summary = f"Matched {len(matched)} historical protective order(s)."
        if exit_reason:
            status = "TRIGGERED"
            summary = f"Historical protective exit matched: {exit_reason}."
        return {
            "status": status,
            "summary": summary,
            "exit_reason": exit_reason,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "orders": matched,
        }

    @staticmethod
    def _protective_order_trigger_price(order: dict[str, Any]) -> float | None:
        for key in ("stop_price", "avg_price", "price"):
            value = BinanceUsdmReadonlyService._nullable_float(order.get(key))
            if value is not None and value > 0.0:
                return value
        return None

    @staticmethod
    def _pnl_pct(*, direction: str, entry: float, close_price: float) -> float | None:
        if entry <= 0.0 or close_price <= 0.0:
            return None
        if str(direction or "BUY").upper() == "BUY":
            return round(((close_price - entry) / entry) * 100.0, 4)
        return round(((entry - close_price) / entry) * 100.0, 4)

    @staticmethod
    def _estimated_realized_r_from_price_move(realized_pnl_pct: float | None) -> float | None:
        if realized_pnl_pct is None:
            return None
        # Venue history can miss the original stop order. Use a conservative,
        # clearly tagged fallback: 1R == 1% price risk, so a +1.01% move is +1.01R.
        return round(realized_pnl_pct, 4)

    @staticmethod
    def _expected_r(*, entry: float, stop_loss: float | None, take_profit: float | None) -> float | None:
        if entry <= 0.0 or stop_loss is None or stop_loss <= 0.0 or take_profit is None or take_profit <= 0.0:
            return None
        risk_per_unit = abs(entry - stop_loss)
        if risk_per_unit <= 0.0:
            return None
        return round(abs(take_profit - entry) / risk_per_unit, 4)

    @staticmethod
    def _realized_r(*, direction: str, entry: float, stop_loss: float | None, close_price: float) -> float | None:
        if entry <= 0.0 or close_price <= 0.0 or stop_loss is None or stop_loss <= 0.0:
            return None
        risk_per_unit = abs(entry - stop_loss)
        if risk_per_unit <= 0.0:
            return None
        if str(direction or "BUY").upper() == "BUY":
            return round((close_price - entry) / risk_per_unit, 4)
        return round((entry - close_price) / risk_per_unit, 4)

    @staticmethod
    def _iso_to_ms(value: Any) -> int | None:
        if not value:
            return None
        try:
            return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp() * 1000)
        except ValueError:
            return None

    def _reconstruct_open_time_from_trades(
        self,
        trades: list[dict[str, Any]],
        *,
        position_side: str,
        current_quantity: float,
    ) -> str | None:
        epsilon = 1e-9
        lifecycle_start_ms: int | None = None
        normalized_side = str(position_side or "BOTH").upper()
        net = 0.0
        for trade in trades:
            trade_position_side = str(trade.get("positionSide") or "BOTH").upper()
            if trade_position_side != normalized_side:
                continue
            qty = self._as_float(trade.get("qty"))
            side = str(trade.get("side") or "").upper()
            if qty <= 0.0 or side not in {"BUY", "SELL"}:
                continue
            delta = self._trade_delta_for_position_side(normalized_side, side, qty)
            previous = net
            updated = net + delta
            trade_time = self._as_int(trade.get("time"))
            if normalized_side == "BOTH":
                if abs(previous) <= epsilon and abs(updated) > epsilon:
                    lifecycle_start_ms = trade_time
                elif (previous > epsilon and updated < -epsilon) or (previous < -epsilon and updated > epsilon):
                    lifecycle_start_ms = trade_time
                elif abs(updated) <= epsilon:
                    lifecycle_start_ms = None
            else:
                if previous <= epsilon and updated > epsilon:
                    lifecycle_start_ms = trade_time
                elif updated <= epsilon:
                    lifecycle_start_ms = None
                    updated = 0.0
            net = updated
        if normalized_side == "BOTH":
            if abs(net) <= epsilon:
                return None
            if current_quantity > epsilon and net < -epsilon:
                return None
            if current_quantity < -epsilon and net > epsilon:
                return None
        elif net <= epsilon:
            return None
        return self._ms_to_iso(lifecycle_start_ms)

    @staticmethod
    def _trade_delta_for_position_side(position_side: str, side: str, qty: float) -> float:
        normalized_position_side = str(position_side or "BOTH").upper()
        normalized_side = str(side or "").upper()
        if normalized_position_side == "LONG":
            return qty if normalized_side == "BUY" else -qty
        if normalized_position_side == "SHORT":
            return qty if normalized_side == "SELL" else -qty
        return qty if normalized_side == "BUY" else -qty

    @staticmethod
    def classify_order_posture(
        *,
        order_type: str | None,
        orig_type: Any = None,
        reduce_only: bool = False,
        close_position: bool = False,
    ) -> tuple[str, str, bool]:
        normalized_type = str(order_type or orig_type or "LIMIT").upper()
        normalized_orig_type = str(orig_type or order_type or normalized_type).upper()
        effective_type = normalized_type or normalized_orig_type
        trailing_types = {"TRAILING_STOP_MARKET"}
        take_profit_types = {"TAKE_PROFIT", "TAKE_PROFIT_MARKET"}
        stop_loss_types = {"STOP", "STOP_MARKET"}
        if effective_type in trailing_types or normalized_orig_type in trailing_types:
            return "PROTECTIVE", "TRAILING_STOP", True
        if effective_type in take_profit_types or normalized_orig_type in take_profit_types:
            return "PROTECTIVE", "TAKE_PROFIT", True
        if effective_type in stop_loss_types or normalized_orig_type in stop_loss_types:
            return "PROTECTIVE", "STOP_LOSS", True
        if bool(reduce_only) or bool(close_position):
            return "PROTECTIVE", "NONE", True
        return "ENTRY", "NONE", False

    @staticmethod
    def _as_float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _nullable_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _ms_to_iso(value: Any) -> str | None:
        millis = BinanceUsdmReadonlyService._as_int(value)
        if not millis:
            return None
        return datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc).isoformat()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()


__all__ = ["BinanceUsdmReadonlyService", "BinanceUsdmReadonlySyncError", "SYNC_STATE_KEY"]
