"""Manual live order placement foundation for Binance USDⓈ-M Futures."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any
from uuid import uuid4

from runtime.db.repos.order_repo import OrderRepository
from runtime.db.repos.settings_repo import SettingsRepository
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.db.session import session_scope
from runtime.services.binance_usdm_readonly_service import BinanceUsdmReadonlyService, BinanceUsdmReadonlySyncError
from runtime.services.runtime_profile_service import (
    BINANCE_USDM_VENUE,
    RuntimeProfileAccessError,
    RuntimeProfileConnectivityError,
    RuntimeProfileService,
)


class BinanceUsdmManualLiveError(ValueError):
    """Raised when a manual live Binance USDⓈ-M order cannot be submitted safely."""


@dataclass(frozen=True)
class LiveRiskConfig:
    risk_model: str
    risk_basis: str
    risk_per_trade_pct: float
    default_entry_r_multiple: float
    max_position_r: float
    max_total_open_r: float
    max_daily_loss_r: float
    max_leverage: int


class BinanceUsdmManualLiveService:
    def __init__(
        self,
        *,
        runtime_profile_service: RuntimeProfileService | None = None,
        order_repo: OrderRepository | None = None,
        settings_repo: SettingsRepository | None = None,
        readonly_service: BinanceUsdmReadonlyService | None = None,
    ) -> None:
        self.runtime_profile_service = runtime_profile_service or RuntimeProfileService()
        self.order_repo = order_repo or OrderRepository()
        self.settings_repo = settings_repo or SettingsRepository()
        self.readonly_service = readonly_service or BinanceUsdmReadonlyService(runtime_profile_service=self.runtime_profile_service)

    def create_manual_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        profile_id = str(payload.get("profile_id") or PAPER_PROFILE_ID)
        is_auto_live = str(payload.get("source") or "").upper() == "AUTO"
        access = self.runtime_profile_service.get_profile_access(profile_id, require_account_reads=True)
        profile = access["sanitized_profile"]
        if str(profile.get("venue") or "").upper() != BINANCE_USDM_VENUE:
            raise BinanceUsdmManualLiveError(f"Runtime profile '{profile_id}' is not a Binance USDⓈ-M profile.")
        payload["profile_id"] = profile_id
        order_input = self._validate_payload(payload)
        account = dict(payload.get("execution_account") or {})
        risk = self._compute_risk(profile_id, account=account, order_input=order_input)
        exchange_rules = self._get_symbol_rules(profile_id, order_input["symbol"])
        normalized_order = self._prepare_limit_order(order_input=order_input, risk=risk, exchange_rules=exchange_rules)
        self._enforce_max_leverage(profile_id, account=account, normalized_order=normalized_order, risk=risk)
        payload["entry"] = normalized_order["price"]
        payload["symbol_filters"] = normalized_order["symbol_filters"]
        quantity = normalized_order["quantity"]
        client_order_id = self._new_client_order_id(profile_id, order_input["symbol"])
        order_id = f"live-{uuid4().hex[:20]}"
        now = self._utc_now_iso()
        venue_request = {
            "symbol": order_input["symbol"],
            "side": order_input["side"],
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": self._format_decimal(quantity),
            "price": self._format_decimal(normalized_order["price"]),
            "newClientOrderId": client_order_id,
            "newOrderRespType": "RESULT",
        }
        self._persist_order_state(
            order_id=order_id,
            profile_id=profile_id,
            payload=payload,
            profile=profile,
            risk=risk,
            quantity=quantity,
            client_order_id=client_order_id,
            venue_order_id=None,
            order_status="PENDING_SUBMIT",
            submission_status="SUBMITTING",
            submitted_at_utc=now,
            last_venue_update_at_utc=now,
            venue_request=venue_request,
            venue_response=None,
            verification=None,
            ambiguity={},
            protection=self._pending_protection_state(order=payload, reason="ENTRY_SUBMITTING"),
        )
        try:
            response = self.runtime_profile_service.signed_request_json(profile_id, "POST", "/fapi/v1/order", params=venue_request)
            if not isinstance(response, dict):
                raise BinanceUsdmManualLiveError("Venue order response was not an object.")
            saved = self._persist_order_state(
                order_id=order_id,
                profile_id=profile_id,
                payload=payload,
                profile=profile,
                risk=risk,
                quantity=quantity,
                client_order_id=client_order_id,
                venue_order_id=str(response.get("orderId") or "") or None,
                order_status=str(response.get("status") or "NEW").upper(),
                submission_status="SUBMITTED",
                submitted_at_utc=now,
                last_venue_update_at_utc=now,
                venue_request=venue_request,
                venue_response=response,
                verification=None,
                ambiguity={},
            )
            verification = self.verify_order(order_id, reason="POST_SUBMIT")
            order_with_protection = self._ensure_protection_posture(verification["order"], reason="POST_SUBMIT")
            if is_auto_live:
                self._record_auto_live_submission(profile_id, order_with_protection)
            return {
                "order": order_with_protection,
                "submission": {
                    "accepted": True,
                    "submission_status": order_with_protection["submission_status"],
                    "submitted_at_utc": order_with_protection["submitted_at_utc"],
                    "client_order_id": order_with_protection["client_order_id"],
                    "venue_order_id": order_with_protection["venue_order_id"],
                },
                "risk": risk,
                "verification": order_with_protection.get("verification") or {},
            }
        except RuntimeProfileAccessError as exc:
            raise BinanceUsdmManualLiveError(str(exc)) from exc
        except (RuntimeProfileConnectivityError, BinanceUsdmReadonlySyncError, BinanceUsdmManualLiveError) as exc:
            ambiguity = self._ambiguity_state(stage="SUBMIT", error_text=str(exc))
            self._persist_order_state(
                order_id=order_id,
                profile_id=profile_id,
                payload=payload,
                profile=profile,
                risk=risk,
                quantity=quantity,
                client_order_id=client_order_id,
                venue_order_id=None,
                order_status="PENDING_SUBMIT_VERIFICATION",
                submission_status="PENDING_SUBMIT_VERIFICATION",
                submitted_at_utc=now,
                last_venue_update_at_utc=now,
                venue_request=venue_request,
                venue_response=None,
                verification=self._verification_state(status="PENDING_VERIFICATION", reason="POST_SUBMIT", checked_at_utc=now, message="Submit confirmation was ambiguous; verification required."),
                ambiguity=ambiguity,
            )
            verification = self.verify_order(order_id, reason="POST_SUBMIT")
            order_with_protection = self._ensure_protection_posture(verification["order"], reason="POST_SUBMIT")
            if is_auto_live:
                self._record_auto_live_submission(profile_id, order_with_protection)
            return {
                "order": order_with_protection,
                "submission": {
                    "accepted": None,
                    "submission_status": order_with_protection["submission_status"],
                    "submitted_at_utc": order_with_protection["submitted_at_utc"],
                    "client_order_id": order_with_protection["client_order_id"],
                    "venue_order_id": order_with_protection["venue_order_id"],
                },
                "risk": risk,
                "verification": order_with_protection.get("verification") or {},
            }

    def get_orders_snapshot(self, *, profile_id: str, limit: int = 500, status: str | None = None) -> dict[str, Any]:
        with session_scope() as session:
            items = self.order_repo.list_orders(session, status=status, limit=limit, profile_id=profile_id)
        persisted_state = self.readonly_service.get_persisted_state(profile_id)
        account = dict(persisted_state.get("account") or {})
        venue_positions = list(persisted_state.get("positions") or [])
        venue_open_orders = list(persisted_state.get("open_orders") or [])
        trade_history_items = list(((persisted_state.get("trade_history") or {}).get("items") or []))
        merged_items = self._merge_readonly_positions_into_snapshot(
            profile_id=profile_id,
            account_id=str(account.get("account_id") or "") or None,
            items=items,
            venue_positions=venue_positions,
            venue_open_orders=venue_open_orders,
        )
        merged_items = self._merge_trade_history_into_snapshot(
            items=merged_items,
            trade_history_items=trade_history_items,
        )
        return {
            "items": merged_items,
            "summary": {
                "total": len(merged_items),
                "open": sum(1 for item in merged_items if bool(item.get("is_open"))),
                "closed": sum(1 for item in merged_items if not bool(item.get("is_open"))),
            },
        }

    def _merge_readonly_positions_into_snapshot(
        self,
        *,
        profile_id: str,
        account_id: str | None,
        items: list[dict[str, Any]],
        venue_positions: list[dict[str, Any]],
        venue_open_orders: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        open_symbols = {
            str(item.get("symbol") or "").upper()
            for item in items
            if bool(item.get("is_open")) and str(item.get("symbol") or "").strip()
        }
        merged = list(items)
        for position in venue_positions:
            symbol = str(position.get("symbol") or "").upper()
            if not symbol or symbol in open_symbols:
                continue
            quantity = self._as_float(position.get("quantity"))
            if quantity == 0.0:
                continue
            direction = "BUY" if quantity > 0 else "SELL"
            position_side = str(position.get("position_side") or ("LONG" if quantity > 0 else "SHORT")).upper()
            venue_payload = dict(position.get("payload") or {})
            protection = self._match_position_protection(
                symbol=symbol,
                direction=direction,
                position_side=position_side,
                venue_open_orders=venue_open_orders,
            )
            stop_loss = protection.get("stop_loss")
            take_profit = protection.get("take_profit")
            trailing_stop = protection.get("trailing_stop")
            last_price = self._as_float(position.get("mark_price"))
            entry_price = self._as_float(position.get("entry_price"))
            expected_r = self._current_r_from_levels(
                direction=direction,
                entry=entry_price,
                stop_loss=stop_loss,
                last_price=last_price,
            )
            progress = self._calc_progress_from_levels(
                direction=direction,
                entry=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                last_price=last_price,
            )
            explicit_initial_margin = self._as_float(venue_payload.get("positionInitialMargin")) or self._as_float(venue_payload.get("initialMargin"))
            reconstructed_opened_at = venue_payload.get("reconstructedOpenedAt")
            estimated_initial_margin = 0.0
            if explicit_initial_margin <= 0.0:
                leverage = self._as_float(position.get("leverage"))
                notional = abs(self._as_float(position.get("notional")))
                estimated_initial_margin = (notional / leverage) if leverage > 0.0 and notional > 0.0 else 0.0
            initial_margin = explicit_initial_margin if explicit_initial_margin > 0.0 else estimated_initial_margin
            unrealized_pnl = self._as_float(position.get("unrealized_pnl"))
            roe_pct = (unrealized_pnl / initial_margin * 100.0) if initial_margin > 0.0 else None
            synthetic_order_id = f"venue-position:{profile_id}:{symbol}:{direction}"
            merged.append(
                {
                    "id": synthetic_order_id,
                    "order_id": synthetic_order_id,
                    "profile_id": profile_id,
                    "account_id": account_id,
                    "execution_mode": "LIVE",
                    "venue": BINANCE_USDM_VENUE,
                    "source": "READ_ONLY_SYNC",
                    "origin": "VENUE_SYNC",
                    "status": "OPEN_POSITION",
                    "lifecycle_status": "OPEN",
                    "is_open": True,
                    "symbol": symbol,
                    "direction": direction,
                    "position_side": position_side,
                    "interval": "--",
                    "mode": "LIVE_SYNC",
                    "quantity": abs(quantity),
                    "entry": entry_price,
                    "break_even_price": self._as_float(position.get("break_even_price")),
                    "last_price": last_price,
                    "open_timestamp": reconstructed_opened_at,
                    "close_timestamp": None,
                    "realized_r": None,
                    "realized_pnl": None,
                    "sl": stop_loss,
                    "tp": take_profit,
                    "expected_r": expected_r,
                    "progress": progress,
                    "unrealized_pnl": unrealized_pnl,
                    "leverage": self._as_float(position.get("leverage")),
                    "notional": self._as_float(position.get("notional")),
                    "liquidation_price": self._as_float(position.get("liquidation_price")),
                    "margin_type": position.get("margin_type"),
                    "isolated": bool(position.get("isolated")),
                    "isolated_margin": self._as_float(position.get("isolated_margin")),
                    "initial_margin": explicit_initial_margin,
                    "estimated_initial_margin": estimated_initial_margin,
                    "maint_margin": self._as_float(venue_payload.get("maintMargin")),
                    "position_initial_margin": self._as_float(venue_payload.get("positionInitialMargin")),
                    "open_order_initial_margin": self._as_float(venue_payload.get("openOrderInitialMargin")),
                    "margin_asset": venue_payload.get("marginAsset"),
                    "roe_pct": roe_pct,
                    "last_venue_update_at_utc": position.get("update_time_utc"),
                    "reconstructed_opened_at": reconstructed_opened_at,
                    "protection_status": protection.get("status"),
                    "protection_summary": protection.get("summary"),
                    "signal_payload": {
                        "summary": "Imported from Binance read-only position sync.",
                    },
                    "payload": {
                        "venue_position": position,
                        "protection_orders": protection.get("orders") or [],
                        "trailing_stop": trailing_stop,
                    },
                }
            )
        merged.sort(key=lambda row: str(row.get("close_timestamp") or row.get("open_timestamp") or ""), reverse=True)
        return merged

    def _merge_trade_history_into_snapshot(
        self,
        *,
        items: list[dict[str, Any]],
        trade_history_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged = []
        unmatched_history = list(trade_history_items)

        for item in items:
            row = dict(item)
            symbol = str(row.get("symbol") or "").upper()
            direction = str(row.get("direction") or "BUY").upper()
            
            # Match with venue history if local order is closed
            if not bool(row.get("is_open")):
                best_match = None
                best_match_idx = -1
                
                # Simple temporal matching: within 24h
                open_dt = self._parse_iso(row.get("opened_at_utc") or row.get("open_timestamp"))
                open_time = open_dt.timestamp() if open_dt else None
                if open_time:
                    for i, h_row in enumerate(unmatched_history):
                        if str(h_row.get("symbol") or "").upper() != symbol:
                            continue
                        if str(h_row.get("direction") or "BUY").upper() != direction:
                            continue
                        h_open_dt = self._parse_iso(h_row.get("open_timestamp"))
                        h_open = h_open_dt.timestamp() if h_open_dt else None
                        if h_open and abs(h_open - open_time) < 86400:
                            best_match = h_row
                            best_match_idx = i
                            break
                            
                if best_match:
                    unmatched_history.pop(best_match_idx)
                    row["entry"] = best_match.get("entry") or row.get("entry")
                    row["close_price"] = best_match.get("close_price")
                    row["close_timestamp"] = best_match.get("close_timestamp")
                    row["realized_pnl"] = best_match.get("realized_pnl")
                    
                    if row.get("close_reason") in ("VENUE_FLAT_SYNC", None):
                        row["close_reason"] = best_match.get("close_reason") or "VENUE_HISTORY_MERGE"

            # Compute R and PnL %
            entry = self._as_float(row.get("entry"))
            close_price = self._as_float(row.get("close_price"))
            stop_loss = self._as_float(row.get("stop_loss") or row.get("sl"))
            take_profit = self._as_float(row.get("take_profit") or row.get("tp"))
            
            if entry > 0 and close_price > 0:
                if direction == "BUY":
                    row["realized_pnl_pct"] = round(((close_price - entry) / entry) * 100.0, 4)
                else:
                    row["realized_pnl_pct"] = round(((entry - close_price) / entry) * 100.0, 4)
            else:
                row["realized_pnl_pct"] = None

            if entry > 0 and stop_loss > 0:
                risk_per_unit = abs(entry - stop_loss)
                if risk_per_unit > 0:
                    if take_profit > 0:
                        row["expected_r"] = round(abs(take_profit - entry) / risk_per_unit, 4)
                    else:
                        row["expected_r"] = None
                    
                    if close_price > 0:
                        if direction == "BUY":
                            row["realized_r"] = round((close_price - entry) / risk_per_unit, 4)
                        else:
                            row["realized_r"] = round((entry - close_price) / risk_per_unit, 4)
                    else:
                        row["realized_r"] = None
                else:
                    row["expected_r"] = None
                    row["realized_r"] = None
            else:
                row["expected_r"] = None
                row["realized_r"] = None

            merged.append(row)

        for h_row in unmatched_history:
            row = dict(h_row)
            entry = self._as_float(row.get("entry"))
            close_price = self._as_float(row.get("close_price"))
            direction = str(row.get("direction") or "BUY").upper()
            
            if entry > 0 and close_price > 0:
                if direction == "BUY":
                    row["realized_pnl_pct"] = round(((close_price - entry) / entry) * 100.0, 4)
                else:
                    row["realized_pnl_pct"] = round(((entry - close_price) / entry) * 100.0, 4)
            else:
                row["realized_pnl_pct"] = None
            
            stop_loss = self._as_float(row.get("stop_loss") or row.get("sl"))
            take_profit = self._as_float(row.get("take_profit") or row.get("tp"))
            if row.get("realized_r") is None and entry > 0 and close_price > 0:
                if stop_loss > 0:
                    risk_per_unit = abs(entry - stop_loss)
                    if risk_per_unit > 0:
                        if direction == "BUY":
                            row["realized_r"] = round((close_price - entry) / risk_per_unit, 4)
                        else:
                            row["realized_r"] = round((entry - close_price) / risk_per_unit, 4)
                elif row.get("realized_pnl_pct") is not None:
                    row["realized_r"] = round(self._as_float(row.get("realized_pnl_pct")), 4)
                    row["realized_r_estimated"] = True
                    row["realized_r_estimation_method"] = "price_move_pct_over_1pct_risk"
            if row.get("expected_r") is None and entry > 0 and stop_loss > 0 and take_profit > 0:
                risk_per_unit = abs(entry - stop_loss)
                if risk_per_unit > 0:
                    row["expected_r"] = round(abs(take_profit - entry) / risk_per_unit, 4)
            merged.append(row)

        merged.sort(key=lambda row: str(row.get("close_timestamp") or row.get("open_timestamp") or row.get("last_venue_update_at_utc") or ""), reverse=True)
        return merged

    def _match_position_protection(
        self,
        *,
        symbol: str,
        direction: str,
        position_side: str,
        venue_open_orders: list[dict[str, Any]],
    ) -> dict[str, Any]:
        protective_orders: list[dict[str, Any]] = []
        expected_side = "SELL" if str(direction or "BUY").upper() == "BUY" else "BUY"
        normalized_position_side = str(position_side or "BOTH").upper()
        for order in venue_open_orders:
            if str(order.get("symbol") or "").upper() != symbol:
                continue
            if not bool(order.get("is_protective")) and str(order.get("order_role") or "").upper() != "PROTECTIVE":
                continue
            order_side = str(order.get("side") or "").upper()
            order_position_side = str(order.get("position_side") or "BOTH").upper()
            if order_side != expected_side:
                continue
            if order_position_side not in {normalized_position_side, "BOTH"}:
                continue
            if not bool(order.get("reduce_only")) and not bool(order.get("close_position")) and str(order.get("order_type") or "").upper() not in {"STOP_MARKET", "TAKE_PROFIT_MARKET", "TRAILING_STOP_MARKET", "STOP", "TAKE_PROFIT"}:
                continue
            protective_orders.append(order)

        stop_loss = None
        take_profit = None
        trailing_stop = None
        stop_order = None
        take_profit_order = None
        trailing_order = None
        for order in protective_orders:
            protective_type = str(order.get("protective_order_type") or "").upper()
            if protective_type == "STOP_LOSS" and stop_order is None:
                stop_order = order
                stop_loss = self._nullable_float(order.get("stop_price") if order.get("stop_price") not in (None, "") else order.get("price"))
            elif protective_type == "TAKE_PROFIT" and take_profit_order is None:
                take_profit_order = order
                take_profit = self._nullable_float(order.get("stop_price") if order.get("stop_price") not in (None, "") else order.get("price"))
            elif protective_type == "TRAILING_STOP" and trailing_order is None:
                trailing_order = order
                trailing_stop = {
                    "activate_price": self._nullable_float(order.get("activate_price")),
                    "callback_rate": self._nullable_float(order.get("price_rate")),
                    "working_type": order.get("working_type"),
                    "order_id": order.get("venue_order_id"),
                }
        status = "NONE"
        summary = "No protective orders were matched to this venue position."
        if stop_order and take_profit_order:
            status = "PROTECTED"
            summary = "Matched stop-loss and take-profit protective orders from Binance."
        elif stop_order:
            status = "STOP_ONLY"
            summary = "Matched stop-loss protection from Binance."
        elif take_profit_order:
            status = "TAKE_PROFIT_ONLY"
            summary = "Matched take-profit protection from Binance."
        elif trailing_order:
            status = "TRAILING_ONLY"
            summary = "Matched trailing-stop protection from Binance."
        return {
            "status": status,
            "summary": summary,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "trailing_stop": trailing_stop,
            "orders": protective_orders,
        }

    @staticmethod
    def _current_r_from_levels(*, direction: str, entry: float, stop_loss: float | None, last_price: float) -> float | None:
        if stop_loss in (None, ""):
            return None
        stop_value = BinanceUsdmManualLiveService._as_float(stop_loss)
        risk = abs(entry - stop_value)
        if risk <= 0.0:
            return None
        if str(direction or "BUY").upper() == "BUY":
            return round((last_price - entry) / risk, 6)
        return round((entry - last_price) / risk, 6)

    @staticmethod
    def _calc_progress_from_levels(
        *,
        direction: str,
        entry: float,
        stop_loss: float | None,
        take_profit: float | None,
        last_price: float,
    ) -> dict[str, Any] | None:
        if stop_loss in (None, "") or take_profit in (None, ""):
            return None
        stop_value = BinanceUsdmManualLiveService._as_float(stop_loss)
        take_value = BinanceUsdmManualLiveService._as_float(take_profit)
        if str(direction or "BUY").upper() == "BUY":
            total_range = take_value - stop_value
            current_pos = last_price - stop_value
            pnl_pct = ((last_price - entry) / entry * 100.0) if entry else 0.0
            side = "tp" if last_price >= entry else "sl"
        else:
            total_range = stop_value - take_value
            current_pos = stop_value - last_price
            pnl_pct = ((entry - last_price) / entry * 100.0) if entry else 0.0
            side = "tp" if last_price <= entry else "sl"
        if total_range == 0:
            return None
        pct = max(0.0, min(100.0, current_pos / total_range * 100.0))
        return {"pct": round(pct, 2), "side": side, "pnl_pct": round(pnl_pct, 4)}

    def get_portfolio_payload(self, *, profile_id: str) -> dict[str, Any]:
        try:
            state = self.readonly_service.sync_account_state(profile_id)
        except BinanceUsdmReadonlySyncError:
            state = self.readonly_service.get_persisted_state(profile_id)
        account = dict(state.get("account") or {})
        balances = list(state.get("balances") or [])
        venue_positions = list(state.get("positions") or [])
        venue_open_orders = list(state.get("open_orders") or [])
        reconciliation = dict(state.get("reconciliation") or {})
        sync = dict(state.get("sync") or {})
        profile = dict(state.get("profile") or self.runtime_profile_service.get_profile(profile_id))
        with session_scope() as session:
            orders = self.order_repo.list_orders(session, limit=5000, profile_id=profile_id)
        open_orders = [item for item in orders if bool(item.get("is_open"))]
        closed_orders = [item for item in orders if not bool(item.get("is_open"))]
        closed_orders.sort(key=lambda row: str(row.get("close_timestamp") or row.get("open_timestamp") or ""), reverse=True)
        today_realized = sum(self._as_float(item.get("realized_pnl")) for item in closed_orders if self._is_within_days(item.get("closed_at_utc"), days=1))
        three_day_realized = sum(self._as_float(item.get("realized_pnl")) for item in closed_orders if self._is_within_days(item.get("closed_at_utc"), days=3))
        balance_base = max(self._as_float(account.get("balance")), 1.0)
        today_symbols = sorted({str(item.get("symbol") or "").upper() for item in closed_orders if self._is_within_days(item.get("closed_at_utc"), days=1) and str(item.get("symbol") or "").strip()})
        pnl_assets = [item for item in balances if abs(self._as_float(item.get("cross_unrealized_pnl"))) > 0.0]
        daily_by_date: dict[str, dict[str, Any]] = defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0, "net_r": 0.0, "realized_pnl": 0.0})
        for item in closed_orders:
            closed_at = self._parse_iso(item.get("closed_at_utc"))
            if closed_at is None:
                continue
            key = closed_at.date().isoformat()
            bucket = daily_by_date[key]
            bucket["trades"] += 1
            realized_r = self._as_float(item.get("realized_r"))
            realized_pnl = self._as_float(item.get("realized_pnl"))
            if realized_r > 0:
                bucket["wins"] += 1
            elif realized_r < 0:
                bucket["losses"] += 1
            bucket["net_r"] += realized_r
            bucket["realized_pnl"] += realized_pnl
        daily = [
            {"date": key, **value}
            for key, value in sorted(daily_by_date.items())
        ]
        summary = {
            "available_balance": self._as_float(account.get("available_balance")),
            "paper_balance": self._as_float(account.get("available_balance")),
            "total_balance": self._as_float(account.get("balance")),
            "total_equity": self._as_float(account.get("equity")),
            "margin_used": self._as_float(account.get("margin_used")),
            "unrealized_pnl": round(sum(self._as_float(item.get("unrealized_pnl")) for item in venue_positions), 8),
            "open_positions": len(open_orders),
            "venue_open_positions": len(venue_positions),
            "open_orders": len(venue_open_orders),
            "closed_trades": len(closed_orders),
            "total_trades": len(orders),
            "net_r": round(sum(self._as_float(item.get("realized_r")) for item in closed_orders), 8),
            "open_expected_r": round(sum(self._as_float(item.get("entry_r_multiple")) for item in open_orders), 8),
            "expected_net_r": round(sum(self._as_float(item.get("entry_r_multiple")) for item in open_orders), 8),
            "win_rate": round((sum(1 for item in closed_orders if self._as_float(item.get("realized_pnl") or item.get("realized_pnl_pct") or item.get("realized_r")) > 0) / len(closed_orders)) * 100.0, 4) if closed_orders else 0.0,
            "profit_factor": self._profit_factor(closed_orders),
            "today_pnl": round(today_realized, 8),
            "today_pnl_pct": round((today_realized / balance_base) * 100.0, 4),
            "three_day_pnl": round(three_day_realized, 8),
            "three_day_pnl_pct": round((three_day_realized / balance_base) * 100.0, 4),
            "performance_windows": {
                "today": {"closed_trades": sum(1 for item in closed_orders if self._is_within_days(item.get("closed_at_utc"), days=1)), "equity_change": round(today_realized, 8)},
                "three_day": {"closed_trades": sum(1 for item in closed_orders if self._is_within_days(item.get("closed_at_utc"), days=3)), "equity_change": round(three_day_realized, 8)},
            },
            "today_symbols": today_symbols,
        }
        return {
            "generated_at": self._utc_now_iso(),
            "profile_id": profile_id,
            "account_id": account.get("account_id"),
            "summary": summary,
            "portfolio": {
                "profile_id": profile_id,
                "execution_mode": profile.get("execution_mode") or "LIVE",
                "venue": profile.get("venue") or BINANCE_USDM_VENUE,
                "total_equity": summary["total_equity"],
                "cash_balance": summary["available_balance"],
                "unrealized_pnl": summary["unrealized_pnl"],
                "open_positions": summary["open_positions"],
            },
            "paper_account": account,
            "account": account,
            "balances": balances,
            "pnl_assets": pnl_assets,
            "avg_hold_minutes": self._average_hold_minutes(closed_orders),
            "daily": daily,
            "recent_closed": closed_orders[:100],
            "open_positions": open_orders,
            "venue_positions": venue_positions,
            "venue_open_orders": venue_open_orders,
            "engine": {
                "status": str(reconciliation.get("status") or sync.get("status") or "UNKNOWN").lower(),
                "sync_status": sync.get("status"),
                "reconciliation_status": reconciliation.get("status"),
                "last_synced_at_utc": sync.get("last_synced_at_utc"),
                "last_reconciled_at_utc": reconciliation.get("last_reconciled_at_utc"),
            },
            "equity_curve": [],
        }

    def query_order(self, order_id: str) -> dict[str, Any]:
        order = self._get_live_order(order_id)
        verified = self._verify_live_order(order, reason="MANUAL_QUERY")
        order_with_protection = self._ensure_protection_posture(verified["order"], reason="MANUAL_QUERY")
        return {"order": order_with_protection, "verification": order_with_protection.get("verification") or {}}

    def verify_order(self, order_id: str, *, reason: str = "MANUAL_VERIFY") -> dict[str, Any]:
        order = self._get_live_order(order_id)
        verified = self._verify_live_order(order, reason=reason)
        order_with_protection = self._ensure_protection_posture(verified["order"], reason=reason)
        return {"order": order_with_protection, "verification": order_with_protection.get("verification") or {}}

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        order = self._get_live_order(order_id)
        profile_id = str(order.get("profile_id") or PAPER_PROFILE_ID)
        identity = self._resolve_query_identity(order)
        params = {"symbol": str(order.get("symbol") or "").upper()}
        if identity["venue_order_id"]:
            params["orderId"] = identity["venue_order_id"]
        elif identity["client_order_id"]:
            params["origClientOrderId"] = identity["client_order_id"]
        else:
            raise BinanceUsdmManualLiveError("Live order does not have persisted venue/client identity for cancel.")
        now = self._utc_now_iso()
        try:
            response = self.runtime_profile_service.signed_request_json(profile_id, "DELETE", "/fapi/v1/order", params=params)
            if not isinstance(response, dict):
                raise BinanceUsdmManualLiveError("Cancel response was not an object.")
            updated = self._persist_verification_update(
                order,
                order_status=str(response.get("status") or order.get("status") or "NEW").upper(),
                submission_status="CANCEL_SUBMITTED",
                venue_order_id=str(response.get("orderId") or order.get("venue_order_id") or "") or None,
                client_order_id=str(response.get("clientOrderId") or order.get("client_order_id") or "") or None,
                verification=self._verification_state(status="PENDING_VERIFICATION", reason="POST_CANCEL", checked_at_utc=now, message="Cancel submitted; verification required."),
                ambiguity={},
                venue_response=response,
            )
        except (RuntimeProfileConnectivityError, BinanceUsdmManualLiveError) as exc:
            updated = self._persist_verification_update(
                order,
                order_status=str(order.get("status") or "NEW").upper(),
                submission_status="CANCEL_PENDING_VERIFICATION",
                venue_order_id=str(order.get("venue_order_id") or "") or None,
                client_order_id=str(order.get("client_order_id") or "") or None,
                verification=self._verification_state(status="PENDING_VERIFICATION", reason="POST_CANCEL", checked_at_utc=now, message="Cancel confirmation was ambiguous; verification required."),
                ambiguity=self._ambiguity_state(stage="CANCEL", error_text=str(exc)),
                venue_response=None,
            )
        verified = self._verify_live_order(updated, reason="POST_CANCEL")
        return {"order": verified["order"], "verification": verified["verification"]}

    def _get_live_order(self, order_id: str) -> dict[str, Any]:
        with session_scope() as session:
            order = self.order_repo.get_order(session, order_id)
        if order is None:
            raise BinanceUsdmManualLiveError(f"Order not found: {order_id}")
        if str(order.get("execution_mode") or "").upper() != "LIVE" or str(order.get("venue") or "").upper() != BINANCE_USDM_VENUE:
            raise BinanceUsdmManualLiveError(f"Order '{order_id}' is not a Binance USDⓈ-M live order.")
        return order

    def _verify_live_order(self, order: dict[str, Any], *, reason: str) -> dict[str, Any]:
        profile_id = str(order.get("profile_id") or PAPER_PROFILE_ID)
        identity = self._resolve_query_identity(order)
        now = self._utc_now_iso()
        try:
            venue_order = self.readonly_service.query_order_status(
                profile_id,
                symbol=str(order.get("symbol") or "").upper(),
                order_id=identity["venue_order_id"],
                client_order_id=None if identity["venue_order_id"] else identity["client_order_id"],
            )
            venue_status = str(venue_order.get("status") or order.get("status") or "UNKNOWN").upper()
            if venue_status in {"CANCELED", "EXPIRED"}:
                verification_status = "CONFIRMED_CANCELED"
                submission_status = "CANCELED_CONFIRMED"
                message = "Cancel/final state verified from venue query."
            elif reason == "POST_CANCEL":
                verification_status = "PENDING_VERIFICATION"
                submission_status = "CANCEL_PENDING_VERIFICATION"
                message = "Cancel not yet confirmed by venue query."
            else:
                verification_status = "CONFIRMED_SUBMITTED"
                submission_status = "SUBMITTED_VERIFIED"
                message = "Submission verified from venue query."
            updated = self._persist_verification_update(
                order,
                order_status=venue_status,
                submission_status=submission_status,
                venue_order_id=str(venue_order.get("venue_order_id") or order.get("venue_order_id") or "") or None,
                client_order_id=str(venue_order.get("client_order_id") or order.get("client_order_id") or "") or None,
                verification=self._verification_state(status=verification_status, reason=reason, checked_at_utc=now, query_status=venue_status, message=message),
                ambiguity={},
                venue_response=venue_order,
            )
            return {"order": updated, "verification": updated.get("verification") or {}}
        except (BinanceUsdmReadonlySyncError, RuntimeProfileConnectivityError, RuntimeProfileAccessError) as exc:
            submission_status = "FAILED_VERIFICATION"
            if reason == "POST_SUBMIT":
                submission_status = "PENDING_SUBMIT_VERIFICATION"
            elif reason == "POST_CANCEL":
                submission_status = "AMBIGUOUS_UNRESOLVED"
            updated = self._persist_verification_update(
                order,
                order_status=str(order.get("status") or "UNKNOWN").upper(),
                submission_status=submission_status,
                venue_order_id=str(order.get("venue_order_id") or "") or None,
                client_order_id=str(order.get("client_order_id") or "") or None,
                verification=self._verification_state(status="AMBIGUOUS_UNRESOLVED" if reason in {"POST_SUBMIT", "POST_CANCEL"} else "FAILED_VERIFICATION", reason=reason, checked_at_utc=now, message="Venue verification could not confirm final state."),
                ambiguity=self._ambiguity_state(stage="VERIFY", error_text=str(exc)),
                venue_response=None,
            )
            return {"order": updated, "verification": updated.get("verification") or {}}

    def _resolve_query_identity(self, order: dict[str, Any]) -> dict[str, str | None]:
        venue_order_id = str(order.get("venue_order_id") or "").strip() or None
        client_order_id = str(order.get("client_order_id") or "").strip() or None
        return {"venue_order_id": venue_order_id, "client_order_id": client_order_id}

    def _validate_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        required = ["symbol", "interval", "mode", "direction", "entry", "sl"]
        for key in required:
            if payload.get(key) in (None, ""):
                raise BinanceUsdmManualLiveError(f"Missing required field: {key}")
        entry = self._as_float(payload.get("entry"))
        stop_price = self._as_float(payload.get("sl"))
        if entry <= 0 or stop_price <= 0:
            raise BinanceUsdmManualLiveError("Entry and stop price must be positive.")
        stop_distance = abs(entry - stop_price)
        if stop_distance <= 0:
            raise BinanceUsdmManualLiveError("Live R-based sizing requires a non-zero stop distance.")
        side = str(payload.get("direction") or "BUY").upper()
        if side not in {"BUY", "SELL"}:
            raise BinanceUsdmManualLiveError("Direction must be BUY or SELL.")
        return {
            "symbol": str(payload.get("symbol") or "").upper(),
            "interval": str(payload.get("interval") or "").lower(),
            "mode": str(payload.get("mode") or "").upper(),
            "side": side,
            "entry": entry,
            "stop_price": stop_price,
            "take_profit": self._nullable_float(payload.get("tp")),
            "confidence": self._as_float(payload.get("confidence")),
            "risk_reward": self._nullable_float(payload.get("risk_reward")),
            "entry_r_multiple": self._nullable_float(payload.get("entry_r_multiple")),
            "use_rest_of_balance": bool(payload.get("use_rest_of_balance")),
            "use_balance_pct": self._nullable_float(payload.get("use_balance_pct")),
            "leverage": self._nullable_float(payload.get("leverage")),
        }

    def _compute_risk(self, profile_id: str, *, account: dict[str, Any], order_input: dict[str, Any]) -> dict[str, Any]:
        with session_scope() as session:
            resolution = self.settings_repo.get_resolution(session, profile_id=profile_id)
            open_orders = self.order_repo.list_orders(session, limit=5000, profile_id=profile_id)
        config = self._risk_config(resolution["settings"])
        entry_r_multiple = order_input.get("entry_r_multiple") or config.default_entry_r_multiple
        if entry_r_multiple <= 0:
            raise BinanceUsdmManualLiveError("Entry R multiple must be positive.")
        
        open_r = sum(self._as_float((item.get("payload") or {}).get("risk_audit", {}).get("entry_r_multiple")) for item in open_orders if str(item.get("execution_mode") or "").upper() == "LIVE" and bool(item.get("is_open")))
        daily_loss_r = sum(abs(self._as_float(item.get("realized_r"))) for item in open_orders if str(item.get("execution_mode") or "").upper() == "LIVE" and self._is_today(item.get("closed_at_utc")) and self._as_float(item.get("realized_r")) < 0)

        # Manual trades explicitly bypass system max_position_r, max_total_open_r, and max_daily_loss_r safety nets.
        
        risk_basis_amount = self._risk_basis_amount(account, config.risk_basis)
        one_r_value = risk_basis_amount * config.risk_per_trade_pct
        trade_risk_budget = one_r_value * entry_r_multiple
        stop_distance = abs(order_input["entry"] - order_input["stop_price"])
        
        system_max_leverage = max(1, int(self._as_float(config.max_leverage, 1.0)))
        effective_leverage = system_max_leverage

        if order_input.get("use_balance_pct") is not None:
            pct = max(0.0, min(100.0, self._as_float(order_input["use_balance_pct"]))) / 100.0
            available_balance = max(0.0, self._as_float(account.get("available_balance")))
            
            # Use explicit leverage if provided, bypassing the system config cap for manual overrides
            if order_input.get("leverage"):
                effective_leverage = max(1.0, self._as_float(order_input["leverage"]))
            
            # calculate notional based on specific % of balance and leverage
            notional = (available_balance * pct * effective_leverage) * 0.99
            raw_quantity = notional / order_input["entry"] if order_input["entry"] > 0 else 0.0
        elif order_input.get("use_rest_of_balance"):
            available_balance = max(0.0, self._as_float(account.get("available_balance")))
            # multiply by 0.99 to give a 1% buffer for rounding and fees
            max_notional = (available_balance * effective_leverage) * 0.99
            raw_quantity = max_notional / order_input["entry"] if order_input["entry"] > 0 else 0.0
        else:
            raw_quantity = trade_risk_budget / stop_distance if stop_distance > 0 else 0.0

        return {
            "risk_model": config.risk_model,
            "risk_basis": config.risk_basis,
            "risk_basis_amount": round(risk_basis_amount, 8),
            "risk_per_trade_pct": config.risk_per_trade_pct,
            "one_r_value": round(one_r_value, 8),
            "entry_r_multiple": round(entry_r_multiple, 8),
            "trade_risk_budget": round(trade_risk_budget, 8),
            "stop_distance": round(stop_distance, 8),
            "raw_quantity": round(raw_quantity, 8),
            "max_position_r": config.max_position_r,
            "max_total_open_r": config.max_total_open_r,
            "max_daily_loss_r": config.max_daily_loss_r,
            "max_leverage": int(effective_leverage),
            "current_total_open_r": round(open_r, 8),
            "current_daily_loss_r": round(daily_loss_r, 8),
        }

    def _risk_config(self, settings: dict[str, str]) -> LiveRiskConfig:
        return LiveRiskConfig(
            risk_model=str(settings.get("LIVE_RISK_MODEL") or "FIXED_R").upper(),
            risk_basis=str(settings.get("LIVE_RISK_BASIS") or "AVAILABLE_BALANCE").upper(),
            risk_per_trade_pct=self._as_float(settings.get("LIVE_RISK_PER_TRADE_PCT"), 0.01),
            default_entry_r_multiple=self._as_float(settings.get("LIVE_DEFAULT_ENTRY_R_MULTIPLE"), 1.0),
            max_position_r=self._as_float(settings.get("LIVE_MAX_POSITION_R"), 2.0),
            max_total_open_r=self._as_float(settings.get("LIVE_MAX_TOTAL_OPEN_R"), 4.0),
            max_daily_loss_r=self._as_float(settings.get("LIVE_MAX_DAILY_LOSS_R"), 3.0),
            max_leverage=max(1, int(self._as_float(settings.get("LIVE_MAX_LEVERAGE"), 1.0))),
        )

    def _risk_basis_amount(self, account: dict[str, Any], risk_basis: str) -> float:
        if risk_basis == "EQUITY":
            return max(0.0, self._as_float(account.get("equity")))
        if risk_basis == "WALLET_BALANCE":
            return max(0.0, self._as_float(account.get("balance")))
        return max(0.0, self._as_float(account.get("available_balance")))

    def _enforce_max_leverage(
        self,
        profile_id: str,
        *,
        account: dict[str, Any],
        normalized_order: dict[str, Any],
        risk: dict[str, Any],
    ) -> dict[str, Any]:
        max_leverage = max(1, int(self._as_float(risk.get("max_leverage"), 1.0)))
        symbol_filters = dict(normalized_order.get("symbol_filters") or {})
        symbol = str(symbol_filters.get("symbol") or "").upper()
        computed_notional = self._as_float(symbol_filters.get("computed_notional"))
        available_balance = max(0.0, self._as_float(account.get("available_balance")))
        max_notional = round(available_balance * max_leverage, 8)
        if computed_notional > max_notional:
            raise BinanceUsdmManualLiveError(
                f"Order blocked by max leverage policy for {symbol}: computed_notional={round(computed_notional, 8)} exceeds available_balance*max_leverage={round(max_notional, 8)} (available_balance={round(available_balance, 8)}, max_leverage={max_leverage})."
            )
        response = self.runtime_profile_service.signed_request_json(
            profile_id,
            "POST",
            "/fapi/v1/leverage",
            params={"symbol": symbol, "leverage": max_leverage},
        )
        if not isinstance(response, dict):
            raise BinanceUsdmManualLiveError("Leverage response was not an object.")
        applied = max(1, int(self._as_float(response.get("leverage"), float(max_leverage))))
        if applied > max_leverage:
            raise BinanceUsdmManualLiveError(
                f"Exchange leverage posture for {symbol} exceeded configured max leverage: applied={applied} max_leverage={max_leverage}."
            )
        symbol_filters["max_leverage"] = max_leverage
        symbol_filters["applied_leverage"] = applied
        normalized_order["symbol_filters"] = symbol_filters
        return response

    def _get_symbol_rules(self, profile_id: str, symbol: str) -> dict[str, float]:
        profile = self.runtime_profile_service.get_profile(profile_id)
        base_url = str(profile.get("resolved_api_base_url") or "")
        payload = self.runtime_profile_service._request_json("GET", f"{base_url}/fapi/v1/exchangeInfo")
        if not isinstance(payload, dict):
            raise BinanceUsdmManualLiveError("Exchange info response was not an object.")
        for item in payload.get("symbols", []):
            if str(item.get("symbol") or "").upper() != symbol:
                continue
            filters = {str(row.get("filterType") or "").upper(): row for row in item.get("filters", [])}
            lot_size = filters.get("LOT_SIZE") or {}
            market_lot_size = filters.get("MARKET_LOT_SIZE") or {}
            price_filter = filters.get("PRICE_FILTER") or {}
            min_notional = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL") or {}
            resolved_min_notional = self._as_float(
                min_notional.get("notional") if min_notional.get("notional") not in (None, "") else min_notional.get("minNotional"),
                0.0,
            )
            return {
                "symbol": symbol,
                "tick_size": self._as_float(price_filter.get("tickSize"), 0.01),
                "step_size": self._as_float(lot_size.get("stepSize"), 0.001),
                "min_qty": self._as_float(lot_size.get("minQty"), 0.0),
                "market_step_size": self._as_float(market_lot_size.get("stepSize"), 0.0),
                "market_min_qty": self._as_float(market_lot_size.get("minQty"), 0.0),
                "min_notional": resolved_min_notional,
            }
        raise BinanceUsdmManualLiveError(f"Exchange symbol metadata not found for {symbol}.")

    def _persist_order_state(
        self,
        *,
        order_id: str,
        profile_id: str,
        payload: dict[str, Any],
        profile: dict[str, Any],
        risk: dict[str, Any],
        quantity: float,
        client_order_id: str | None,
        venue_order_id: str | None,
        order_status: str,
        submission_status: str,
        submitted_at_utc: str,
        last_venue_update_at_utc: str | None,
        venue_request: dict[str, Any] | None,
        venue_response: dict[str, Any] | None,
        verification: dict[str, Any] | None,
        ambiguity: dict[str, Any] | None,
        protection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with session_scope() as session:
            resolution = self.settings_repo.get_resolution(session, profile_id=profile_id)
            existing = self.order_repo.get_order(session, order_id)
            current_payload = dict((existing or {}).get("payload") or {})
            resolved_verification = current_payload.get("verification") if verification is None else verification
            resolved_ambiguity = current_payload.get("ambiguity") if ambiguity is None else ambiguity
            resolved_protection = current_payload.get("protection") if protection is None else protection
            current_payload.update(
                {
                    "quantity": quantity,
                    "requested_quantity": risk.get("raw_quantity"),
                    "risk_audit": risk,
                    "symbol_filters": payload.get("symbol_filters") or current_payload.get("symbol_filters") or {},
                    "execution_target": payload.get("execution_target") or current_payload.get("execution_target") or {},
                    "execution_account": payload.get("execution_account") or current_payload.get("execution_account") or {},
                    "decision_linkage": self._decision_linkage_payload(payload, current_payload=current_payload),
                    "auto_live_policy": payload.get("auto_live_policy") or current_payload.get("auto_live_policy") or {},
                    "live_submission": {
                        "request": self._safe_request_payload(venue_request or ((current_payload.get("live_submission") or {}).get("request") or {})),
                        "response": self._safe_response_payload(venue_response or ((current_payload.get("live_submission") or {}).get("response") or {})),
                    },
                    "verification": resolved_verification,
                    "ambiguity": resolved_ambiguity,
                    "protection": resolved_protection,
                    "auto_live": self._auto_live_state(
                        payload,
                        current_payload=current_payload,
                        order_id=order_id,
                        client_order_id=client_order_id,
                        venue_order_id=venue_order_id,
                        submission_status=submission_status,
                        order_status=order_status,
                        verification=resolved_verification,
                        protection=resolved_protection,
                    ),
                }
            )
            saved = self.order_repo.save_order(
                session,
                {
                    "order_id": order_id,
                    "profile_id": profile_id,
                    "signal_id": payload.get("signal_id") or (existing or {}).get("signal_id"),
                    "source": str(payload.get("source") or (existing or {}).get("source") or "MANUAL").upper(),
                    "execution_mode": str(profile.get("execution_mode") or "LIVE"),
                    "venue": str(profile.get("venue") or BINANCE_USDM_VENUE),
                    "origin": str(payload.get("origin") or (existing or {}).get("origin") or payload.get("source") or "MANUAL").upper(),
                    "client_order_id": client_order_id,
                    "venue_order_id": venue_order_id,
                    "submission_status": submission_status,
                    "submitted_at_utc": submitted_at_utc,
                    "last_venue_update_at_utc": last_venue_update_at_utc,
                    "symbol": str(payload.get("symbol") or (existing or {}).get("symbol") or "").upper(),
                    "interval": str(payload.get("interval") or (existing or {}).get("interval") or "").lower(),
                    "mode": str(payload.get("mode") or (existing or {}).get("mode") or "").upper(),
                    "direction": str(payload.get("direction") or (existing or {}).get("direction") or "BUY").upper(),
                    "status": order_status,
                    "entry": self._as_float(payload.get("entry") if payload.get("entry") is not None else (existing or {}).get("entry")),
                    "stop_loss": self._nullable_float(payload.get("sl") if payload.get("sl") is not None else (existing or {}).get("stop_loss")),
                    "take_profit": self._nullable_float(payload.get("tp") if payload.get("tp") is not None else (existing or {}).get("take_profit")),
                    "close_price": (existing or {}).get("close_price"),
                    "risk_reward": self._nullable_float(payload.get("risk_reward") if payload.get("risk_reward") is not None else (existing or {}).get("risk_reward")),
                    "confidence": self._as_float(payload.get("confidence") if payload.get("confidence") is not None else (existing or {}).get("confidence")),
                    "opened_at_utc": submitted_at_utc,
                    "closed_at_utc": (existing or {}).get("closed_at_utc"),
                    "payload_json": self._dumps(current_payload),
                    "resolved_config_hash": str(resolution.get("resolved_config_hash") or ""),
                },
            )
        return saved

    def _persist_verification_update(
        self,
        order: dict[str, Any],
        *,
        order_status: str,
        submission_status: str,
        venue_order_id: str | None,
        client_order_id: str | None,
        verification: dict[str, Any],
        ambiguity: dict[str, Any] | None,
        venue_response: dict[str, Any] | None,
    ) -> dict[str, Any]:
        profile = self.runtime_profile_service.get_profile(str(order.get("profile_id") or PAPER_PROFILE_ID))
        return self._persist_order_state(
            order_id=str(order.get("order_id") or ""),
            profile_id=str(order.get("profile_id") or PAPER_PROFILE_ID),
            payload=order,
            profile=profile,
            risk=dict(order.get("risk_audit") or {}),
            quantity=self._as_float(order.get("quantity")),
            client_order_id=client_order_id,
            venue_order_id=venue_order_id,
            order_status=order_status,
            submission_status=submission_status,
            submitted_at_utc=str(order.get("submitted_at_utc") or order.get("opened_at_utc") or self._utc_now_iso()),
            last_venue_update_at_utc=self._utc_now_iso(),
            venue_request=((order.get("payload") or {}).get("live_submission") or {}).get("request") or {},
            venue_response=venue_response,
            verification=verification,
            ambiguity=ambiguity,
            protection=(order.get("payload") or {}).get("protection"),
        )

    def _ensure_protection_posture(self, order: dict[str, Any], *, reason: str) -> dict[str, Any]:
        now = self._utc_now_iso()
        if str(order.get("execution_mode") or "").upper() != "LIVE" or str(order.get("venue") or "").upper() != BINANCE_USDM_VENUE:
            return order
        protection = dict(((order.get("payload") or {}).get("protection") or {}))
        parent_status = str(order.get("status") or "").upper()
        if not self._entry_allows_protection(order):
            if parent_status in {"CANCELED", "EXPIRED", "REJECTED", "CLOSED"}:
                return self._persist_protection_update(
                    order,
                    protection=self._close_protection_lifecycle(order, protection=protection, reason=reason),
                )
            pending = self._pending_protection_state(order=order, reason=reason)
            pending["children"] = protection.get("children") or []
            return self._persist_protection_update(order, protection=pending)

        children = {str(item.get("kind") or "").upper(): dict(item) for item in protection.get("children") or []}
        stop_child = self._ensure_protective_child(
            order,
            existing=children.get("STOP_LOSS"),
            kind="STOP_LOSS",
            trigger_reason=reason,
            price=order.get("stop_loss"),
            required=True,
        )
        children["STOP_LOSS"] = stop_child
        take_profit_price = order.get("take_profit")
        if take_profit_price not in (None, ""):
            children["TAKE_PROFIT"] = self._ensure_protective_child(
                order,
                existing=children.get("TAKE_PROFIT"),
                kind="TAKE_PROFIT",
                trigger_reason=reason,
                price=take_profit_price,
                required=False,
            )
        children = self._apply_terminal_protection_closure(order, children=children, reason=reason)
        ordered_children = [children[key] for key in ("STOP_LOSS", "TAKE_PROFIT") if key in children]
        overall_status, message = self._summarize_protection_status(ordered_children, parent_status=parent_status)
        maintenance_mode = "CLOSE_POSITION_COMPATIBILITY" if parent_status == "PARTIALLY_FILLED" else None
        protection.update(
            {
                "status": overall_status,
                "required": True,
                "required_types": ["STOP_LOSS"],
                "requested_types": [item["kind"] for item in ordered_children],
                "last_checked_at_utc": now,
                "confirmed_at_utc": now if overall_status == "CONFIRMED" else protection.get("confirmed_at_utc"),
                "message": message,
                "maintenance_mode": maintenance_mode,
                "children": ordered_children,
            }
        )
        return self._persist_protection_update(order, protection=protection)

    def _ensure_protective_child(
        self,
        order: dict[str, Any],
        *,
        existing: dict[str, Any] | None,
        kind: str,
        trigger_reason: str,
        price: Any,
        required: bool,
    ) -> dict[str, Any]:
        child = dict(existing or {})
        profile_id = str(order.get("profile_id") or PAPER_PROFILE_ID)
        symbol = str(order.get("symbol") or "").upper()
        child.setdefault("kind", kind)
        child.setdefault("required", required)
        child.setdefault("parent_order_id", order.get("order_id"))
        child.setdefault("symbol", symbol)
        child.setdefault("trigger_reason", trigger_reason)
        child.setdefault("price", self._nullable_float(price))
        child.setdefault("order_role", "PROTECTIVE")
        child.setdefault("protective_order_type", kind)
        child.setdefault("side", self._protective_side(order))
        if child.get("venue_order_id") or child.get("client_order_id"):
            return self._confirm_protective_child(
                order,
                child=child,
                kind=kind,
                ambiguous=str(child.get("status") or "").upper() in {"PENDING", "DEGRADED"},
            )
        client_order_id = self._new_client_order_id(profile_id, f"{symbol[:6]}-{kind[:4]}")
        request_payload = self._protective_order_request(order, kind=kind, client_order_id=client_order_id, price=price)
        now = self._utc_now_iso()
        try:
            response = self.runtime_profile_service.signed_request_json(profile_id, "POST", "/fapi/v1/algoOrder", params=request_payload)
            if not isinstance(response, dict):
                raise BinanceUsdmManualLiveError("Protective algo order response was not an object.")
            child.update(
                {
                    "status": "PENDING",
                    "algo_order": True,
                    "client_order_id": str(response.get("clientAlgoId") or client_order_id),
                    "venue_order_id": str(response.get("algoId") or "") or None,
                    "venue_order_status": str(response.get("algoStatus") or "NEW").upper(),
                    "submitted_at_utc": now,
                    "last_checked_at_utc": now,
                    "request": self._safe_request_payload(request_payload),
                    "response": self._safe_response_payload(response),
                    "last_error": None,
                }
            )
            return self._confirm_protective_child(order, child=child, kind=kind, ambiguous=False)
        except RuntimeProfileAccessError as exc:
            child.update(
                {
                    "status": "FAILED",
                    "client_order_id": client_order_id,
                    "submitted_at_utc": now,
                    "last_checked_at_utc": now,
                    "request": self._safe_request_payload(request_payload),
                    "response": None,
                    "last_error": str(exc),
                }
            )
            return child
        except (RuntimeProfileConnectivityError, BinanceUsdmManualLiveError) as exc:
            if self._is_rejected_order_error(exc):
                child.update(
                    {
                        "status": "FAILED",
                        "algo_order": True,
                        "client_order_id": client_order_id,
                        "submitted_at_utc": now,
                        "last_checked_at_utc": now,
                        "request": self._safe_request_payload(request_payload),
                        "response": None,
                        "last_error": str(exc),
                    }
                )
                return child
            child.update(
                {
                    "status": "PENDING",
                    "algo_order": True,
                    "client_order_id": client_order_id,
                    "submitted_at_utc": now,
                    "last_checked_at_utc": now,
                    "request": self._safe_request_payload(request_payload),
                    "response": None,
                    "last_error": str(exc),
                }
            )
            return self._confirm_protective_child(order, child=child, kind=kind, ambiguous=True)

    def _confirm_protective_child(
        self,
        order: dict[str, Any],
        *,
        child: dict[str, Any],
        kind: str,
        ambiguous: bool,
    ) -> dict[str, Any]:
        now = self._utc_now_iso()
        try:
            query_status = self.readonly_service.query_algo_order_status if bool(child.get("algo_order")) else self.readonly_service.query_order_status
            venue_order = query_status(
                str(order.get("profile_id") or PAPER_PROFILE_ID),
                symbol=str(order.get("symbol") or "").upper(),
                order_id=str(child.get("venue_order_id") or "") or None,
                client_order_id=None if child.get("venue_order_id") else str(child.get("client_order_id") or "") or None,
            )
            venue_status = str(venue_order.get("status") or child.get("venue_order_status") or "NEW").upper()
            confirmed = str(venue_order.get("order_role") or "PROTECTIVE").upper() == "PROTECTIVE"
            child_status = self._child_status_from_venue_status(venue_status, confirmed=confirmed, ambiguous=ambiguous)
            child.update(
                {
                    "status": child_status,
                    "venue_order_id": str(venue_order.get("venue_order_id") or child.get("venue_order_id") or "") or None,
                    "client_order_id": str(venue_order.get("client_order_id") or child.get("client_order_id") or "") or None,
                    "venue_order_status": venue_status,
                    "confirmed_at_utc": now if child_status == "CONFIRMED" else child.get("confirmed_at_utc"),
                    "last_checked_at_utc": now,
                    "last_error": None if child_status in {"CONFIRMED", "TRIGGERED", "CANCELED", "EXPIRED"} else child.get("last_error"),
                }
            )
            return child
        except (BinanceUsdmReadonlySyncError, RuntimeProfileConnectivityError, RuntimeProfileAccessError) as exc:
            child.update(
                {
                    "status": "DEGRADED" if ambiguous else "FAILED",
                    "last_checked_at_utc": now,
                    "last_error": str(exc),
                }
            )
            return child

    def _persist_protection_update(self, order: dict[str, Any], *, protection: dict[str, Any]) -> dict[str, Any]:
        profile = self.runtime_profile_service.get_profile(str(order.get("profile_id") or PAPER_PROFILE_ID))
        return self._persist_order_state(
            order_id=str(order.get("order_id") or ""),
            profile_id=str(order.get("profile_id") or PAPER_PROFILE_ID),
            payload=order,
            profile=profile,
            risk=dict(order.get("risk_audit") or {}),
            quantity=self._as_float(order.get("quantity")),
            client_order_id=str(order.get("client_order_id") or "") or None,
            venue_order_id=str(order.get("venue_order_id") or "") or None,
            order_status=str(order.get("status") or "UNKNOWN").upper(),
            submission_status=str(order.get("submission_status") or "NONE"),
            submitted_at_utc=str(order.get("submitted_at_utc") or order.get("opened_at_utc") or self._utc_now_iso()),
            last_venue_update_at_utc=str(order.get("last_venue_update_at_utc") or self._utc_now_iso()),
            venue_request=((order.get("payload") or {}).get("live_submission") or {}).get("request") or {},
            venue_response=((order.get("payload") or {}).get("live_submission") or {}).get("response") or {},
            verification=(order.get("payload") or {}).get("verification") or order.get("verification") or {},
            ambiguity=(order.get("payload") or {}).get("ambiguity") or order.get("ambiguity") or {},
            protection=protection,
        )

    def _apply_terminal_protection_closure(
        self,
        order: dict[str, Any],
        *,
        children: dict[str, dict[str, Any]],
        reason: str,
    ) -> dict[str, dict[str, Any]]:
        parent_status = str(order.get("status") or "").upper()
        if parent_status in {"CANCELED", "EXPIRED", "REJECTED", "CLOSED"}:
            for kind, child in list(children.items()):
                if self._is_active_child(child):
                    children[kind] = self._cancel_protective_child(order, child=child, reason=f"PARENT_{parent_status}")
            return children
        triggered_kind = next((kind for kind, child in children.items() if str(child.get("venue_order_status") or "").upper() == "FILLED" or str(child.get("status") or "").upper() == "TRIGGERED"), None)
        if triggered_kind is None:
            return children
        for kind, child in list(children.items()):
            if kind == triggered_kind:
                continue
            if self._is_active_child(child):
                children[kind] = self._cancel_protective_child(order, child=child, reason=f"SIBLING_{triggered_kind}_TRIGGERED")
        return children

    def _cancel_protective_child(self, order: dict[str, Any], *, child: dict[str, Any], reason: str) -> dict[str, Any]:
        now = self._utc_now_iso()
        params = {"symbol": str(order.get("symbol") or "").upper()}
        venue_order_id = str(child.get("venue_order_id") or "") or None
        client_order_id = str(child.get("client_order_id") or "") or None
        if venue_order_id:
            params["orderId"] = venue_order_id
        elif client_order_id:
            params["origClientOrderId"] = client_order_id
        else:
            child.update({"status": "DEGRADED", "last_checked_at_utc": now, "last_error": "Protective child has no persisted identity for cleanup."})
            return child
        try:
            if bool(child.get("algo_order")):
                algo_params = {}
                if venue_order_id:
                    algo_params["algoId"] = venue_order_id
                elif client_order_id:
                    algo_params["clientAlgoId"] = client_order_id
                response = self.runtime_profile_service.signed_request_json(str(order.get("profile_id") or PAPER_PROFILE_ID), "DELETE", "/fapi/v1/algoOrder", params=algo_params)
            else:
                response = self.runtime_profile_service.signed_request_json(str(order.get("profile_id") or PAPER_PROFILE_ID), "DELETE", "/fapi/v1/order", params=params)
            if isinstance(response, dict):
                child["response"] = self._safe_response_payload(response)
            return self._confirm_protective_child(order, child=child, kind=str(child.get("kind") or "UNKNOWN"), ambiguous=True)
        except (RuntimeProfileConnectivityError, RuntimeProfileAccessError, BinanceUsdmManualLiveError) as exc:
            child.update({"status": "DEGRADED", "last_checked_at_utc": now, "last_error": str(exc)})
            return child

    def _close_protection_lifecycle(self, order: dict[str, Any], *, protection: dict[str, Any], reason: str) -> dict[str, Any]:
        children = {str(item.get("kind") or "").upper(): dict(item) for item in protection.get("children") or []}
        children = self._apply_terminal_protection_closure(order, children=children, reason=reason)
        ordered_children = [children[key] for key in ("STOP_LOSS", "TAKE_PROFIT") if key in children]
        status = "CLOSED" if all(self._is_terminal_child(item) for item in ordered_children) or not ordered_children else "DEGRADED"
        return {
            **protection,
            "status": status,
            "required": True,
            "required_types": ["STOP_LOSS"],
            "requested_types": [item.get("kind") for item in ordered_children],
            "last_checked_at_utc": self._utc_now_iso(),
            "message": "Protection lifecycle is closed for the terminal parent order." if status == "CLOSED" else "Terminal parent order left degraded protective cleanup state.",
            "children": ordered_children,
        }

    def _record_auto_live_submission(self, profile_id: str, order: dict[str, Any]) -> None:
        auto_live = dict(order.get("auto_live") or {})
        linkage = dict(order.get("decision_linkage") or {})
        self.runtime_profile_service.record_auto_live_attempt(
            profile_id,
            {
                "profile_id": profile_id,
                "outcome": "SUBMITTED",
                "posture": "AUTO_LIVE_ENABLED",
                "message": auto_live.get("completion_reason") or order.get("protection_message") or "Auto-live order routed into manual-live submission path.",
                "decision": {
                    "decision_id": linkage.get("decision_id"),
                    "signal_id": linkage.get("signal_id"),
                    "decision_event_id": linkage.get("decision_event_id"),
                    "request_id": linkage.get("request_id"),
                    "run_id": linkage.get("run_id"),
                    "symbol": order.get("symbol"),
                    "interval": order.get("interval"),
                    "mode": order.get("mode"),
                    "direction": order.get("direction"),
                    "entry_r_multiple": order.get("entry_r_multiple"),
                },
                "order": {
                    "order_id": order.get("order_id"),
                    "client_order_id": order.get("client_order_id"),
                    "venue_order_id": order.get("venue_order_id"),
                    "submission_status": order.get("submission_status"),
                    "status": order.get("status"),
                },
                "protection": {
                    "status": order.get("protection_status"),
                    "safe_to_consider_active": auto_live.get("safe_to_consider_active"),
                    "message": auto_live.get("completion_reason") or order.get("protection_message"),
                },
            },
        )

    @staticmethod
    def _decision_linkage_payload(payload: dict[str, Any], *, current_payload: dict[str, Any]) -> dict[str, Any]:
        existing = dict(current_payload.get("decision_linkage") or {})
        decision_id = payload.get("decision_id") or existing.get("decision_id") or payload.get("decision_event_id") or payload.get("signal_id")
        return {
            "decision_id": decision_id,
            "signal_id": payload.get("signal_id") or existing.get("signal_id"),
            "decision_event_id": payload.get("decision_event_id") or existing.get("decision_event_id"),
            "request_id": payload.get("request_id") or existing.get("request_id"),
            "run_id": payload.get("run_id") or existing.get("run_id"),
            "trace_id": payload.get("trace_id") or existing.get("trace_id"),
            "source": str(payload.get("source") or existing.get("source") or "MANUAL").upper(),
        }

    @staticmethod
    def _auto_live_state(
        payload: dict[str, Any],
        *,
        current_payload: dict[str, Any],
        order_id: str,
        client_order_id: str | None,
        venue_order_id: str | None,
        submission_status: str,
        order_status: str,
        verification: dict[str, Any] | None,
        protection: dict[str, Any] | None,
    ) -> dict[str, Any]:
        existing = dict(current_payload.get("auto_live") or {})
        if str(payload.get("source") or existing.get("source") or "").upper() != "AUTO":
            return existing
        protection_payload = dict(protection or {})
        protection_status = str(protection_payload.get("status") or "PENDING").upper()
        completion_status = "PROTECTION_PENDING"
        safe_to_consider_active = False
        completion_reason = str(protection_payload.get("message") or "Auto-live entry is not yet in a safely active protected state.")
        if protection_status == "CONFIRMED":
            completion_status = "PROTECTION_CONFIRMED"
            safe_to_consider_active = True
            completion_reason = str(protection_payload.get("message") or "Required native protection is confirmed on the venue.")
        elif protection_status in {"DEGRADED", "FAILED"}:
            completion_status = "PROTECTION_DEGRADED"
            completion_reason = str(protection_payload.get("message") or "Required native protection is degraded or missing on the venue.")
        return {
            "source": "AUTO",
            "status": "SUBMITTED",
            "submission_status": submission_status,
            "order_status": order_status,
            "verification_status": (verification or {}).get("status"),
            "order_linkage": {
                "order_id": order_id,
                "client_order_id": client_order_id,
                "venue_order_id": venue_order_id,
            },
            "protection_status": protection_status,
            "completion_status": completion_status,
            "safe_to_consider_active": safe_to_consider_active,
            "completion_reason": completion_reason,
        }

    @staticmethod
    def _child_status_from_venue_status(venue_status: str, *, confirmed: bool, ambiguous: bool) -> str:
        normalized = str(venue_status or "UNKNOWN").upper()
        if normalized == "FILLED":
            return "TRIGGERED"
        if normalized in {"CANCELED", "EXPIRED"}:
            return normalized
        if normalized == "REJECTED":
            return "FAILED"
        if confirmed:
            return "CONFIRMED"
        return "DEGRADED" if ambiguous else "FAILED"

    @staticmethod
    def _is_active_child(child: dict[str, Any]) -> bool:
        return str(child.get("status") or "").upper() in {"PENDING", "CONFIRMED", "DEGRADED"}

    @staticmethod
    def _is_terminal_child(child: dict[str, Any]) -> bool:
        return str(child.get("status") or "").upper() in {"TRIGGERED", "CANCELED", "EXPIRED", "FAILED", "CLOSED"}

    def _entry_allows_protection(self, order: dict[str, Any]) -> bool:
        return str(order.get("status") or "").upper() in {"FILLED", "PARTIALLY_FILLED", "OPEN"}

    def _protective_side(self, order: dict[str, Any]) -> str:
        return "SELL" if str(order.get("direction") or "BUY").upper() == "BUY" else "BUY"

    def _protective_order_request(self, order: dict[str, Any], *, kind: str, client_order_id: str, price: Any) -> dict[str, Any]:
        order_type = "STOP_MARKET" if kind == "STOP_LOSS" else "TAKE_PROFIT_MARKET"
        stop_price = self._nullable_float(price)
        if stop_price is None or stop_price <= 0:
            raise BinanceUsdmManualLiveError(f"Protective {kind.lower()} requires a positive trigger price.")
        return {
            "algoType": "CONDITIONAL",
            "symbol": str(order.get("symbol") or "").upper(),
            "side": self._protective_side(order),
            "type": order_type,
            "triggerPrice": self._format_decimal(stop_price),
            "closePosition": "true",
            "workingType": "MARK_PRICE",
            "clientAlgoId": client_order_id,
            "newOrderRespType": "RESULT",
        }

    def _pending_protection_state(self, *, order: dict[str, Any], reason: str) -> dict[str, Any]:
        requested_types = ["STOP_LOSS"]
        if order.get("take_profit") not in (None, "") or order.get("tp") not in (None, ""):
            requested_types.append("TAKE_PROFIT")
        return {
            "status": "PENDING",
            "required": True,
            "required_types": ["STOP_LOSS"],
            "requested_types": requested_types,
            "last_checked_at_utc": self._utc_now_iso(),
            "maintenance_mode": None,
            "message": f"Entry is not yet in a protection-eligible state ({reason}); native protection is not assumed.",
            "children": [],
        }

    @staticmethod
    def _summarize_protection_status(children: list[dict[str, Any]], *, parent_status: str) -> tuple[str, str]:
        required_children = [item for item in children if item.get("required")]
        requested_children = list(children)
        if parent_status in {"CANCELED", "EXPIRED", "REJECTED", "CLOSED"} and (not requested_children or all(BinanceUsdmManualLiveService._is_terminal_child(item) for item in requested_children)):
            return "CLOSED", "Protection lifecycle is closed for the terminal parent order."
        if any(str(item.get("status") or "").upper() == "TRIGGERED" for item in requested_children):
            if all(BinanceUsdmManualLiveService._is_terminal_child(item) for item in requested_children):
                return "CLOSED", "A protective child triggered and remaining siblings were closed."
            return "DEGRADED", "A protective child triggered but sibling cleanup is incomplete."
        if any(str(item.get("status") or "").upper() == "FAILED" for item in required_children):
            return "FAILED", "Required native stop-loss protection could not be confirmed."
        if all(str(item.get("status") or "").upper() == "CONFIRMED" for item in required_children) and all(str(item.get("status") or "").upper() == "CONFIRMED" for item in requested_children):
            message = "Required native protection is confirmed on the venue."
            if parent_status == "PARTIALLY_FILLED":
                message = "Required native protection is confirmed and maintained through partial fills using close-position compatibility."
            return "CONFIRMED", message
        if any(str(item.get("status") or "").upper() in {"DEGRADED", "FAILED"} for item in requested_children):
            return "DEGRADED", "Native protection is degraded or incomplete on the venue."
        return "PENDING", "Native protection is pending venue confirmation."

    @staticmethod
    def _verification_state(
        *,
        status: str,
        reason: str,
        checked_at_utc: str,
        query_status: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "reason": reason,
            "checked_at_utc": checked_at_utc,
            "query_status": query_status,
            "message": message,
        }

    @staticmethod
    def _ambiguity_state(*, stage: str, error_text: str) -> dict[str, Any]:
        return {
            "active": True,
            "stage": stage,
            "error": error_text,
            "detected_at_utc": BinanceUsdmManualLiveService._utc_now_iso(),
        }

    @staticmethod
    def _safe_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {"algoType", "symbol", "side", "type", "timeInForce", "quantity", "price", "stopPrice", "triggerPrice", "closePosition", "workingType", "newClientOrderId", "clientAlgoId", "newOrderRespType"}
        return {key: value for key, value in payload.items() if key in allowed}

    @staticmethod
    def _safe_response_payload(payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {"symbol", "orderId", "clientOrderId", "status", "price", "origQty", "executedQty", "type", "origType", "side", "timeInForce", "stopPrice", "triggerPrice", "closePosition", "reduceOnly", "updateTime", "algoId", "clientAlgoId", "algoStatus", "orderType", "createTime"}
        return {key: value for key, value in payload.items() if key in allowed}

    @staticmethod
    def _is_rejected_order_error(exc: Exception) -> bool:
        error_text = str(exc).upper()
        return "HTTP 4" in error_text or "CODE -" in error_text

    def _prepare_limit_order(self, *, order_input: dict[str, Any], risk: dict[str, Any], exchange_rules: dict[str, float]) -> dict[str, float | dict[str, Any]]:
        raw_quantity = self._as_float(risk.get("raw_quantity"))
        normalized_quantity = self._quantize_quantity(raw_quantity, exchange_rules.get("step_size", 0.0))
        raw_price = self._as_float(order_input.get("entry"))
        normalized_price = self._quantize_price(raw_price, exchange_rules.get("tick_size", 0.0))
        normalized_notional = normalized_price * normalized_quantity
        filter_audit = {
            "symbol": str(order_input.get("symbol") or exchange_rules.get("symbol") or "").upper(),
            "order_type": "LIMIT",
            "tick_size": exchange_rules.get("tick_size", 0.0),
            "step_size": exchange_rules.get("step_size", 0.0),
            "market_step_size": exchange_rules.get("market_step_size", 0.0),
            "min_qty": exchange_rules.get("min_qty", 0.0),
            "market_min_qty": exchange_rules.get("market_min_qty", 0.0),
            "min_notional": exchange_rules.get("min_notional", 0.0),
            "raw_price": round(raw_price, 8),
            "normalized_price": round(normalized_price, 8),
            "raw_quantity": round(raw_quantity, 8),
            "normalized_quantity": round(normalized_quantity, 8),
            "computed_notional": round(normalized_notional, 8),
            "rejection_reason": None,
        }
        rejection_reason = self._validate_symbol_filters(
            price=normalized_price,
            quantity=normalized_quantity,
            exchange_rules=exchange_rules,
            filter_audit=filter_audit,
        )
        if rejection_reason:
            filter_audit["rejection_reason"] = rejection_reason
            raise BinanceUsdmManualLiveError(self._symbol_filter_error_message(filter_audit))
        return {"price": normalized_price, "quantity": normalized_quantity, "symbol_filters": filter_audit}

    @staticmethod
    def _quantize_quantity(value: float, step_size: float) -> float:
        if value <= 0 or step_size <= 0:
            return 0.0
        quantity = Decimal(str(value))
        step = Decimal(str(step_size))
        return float((quantity / step).to_integral_value(rounding=ROUND_DOWN) * step)

    @staticmethod
    def _quantize_price(value: float, tick_size: float) -> float:
        if value <= 0 or tick_size <= 0:
            return value
        price = Decimal(str(value))
        tick = Decimal(str(tick_size))
        return float((price / tick).to_integral_value(rounding=ROUND_DOWN) * tick)

    @staticmethod
    def _validate_symbol_filters(
        *,
        price: float,
        quantity: float,
        exchange_rules: dict[str, float],
        filter_audit: dict[str, Any],
    ) -> str | None:
        tick_size = BinanceUsdmManualLiveService._as_float(exchange_rules.get("tick_size"))
        step_size = BinanceUsdmManualLiveService._as_float(exchange_rules.get("step_size"))
        min_qty = BinanceUsdmManualLiveService._as_float(exchange_rules.get("min_qty"))
        min_notional = BinanceUsdmManualLiveService._as_float(exchange_rules.get("min_notional"))
        if quantity <= 0:
            return "normalized quantity is zero after step-size normalization"
        if tick_size > 0 and BinanceUsdmManualLiveService._quantize_price(price, tick_size) != price:
            return "price does not respect tick size"
        if step_size > 0 and BinanceUsdmManualLiveService._quantize_quantity(quantity, step_size) != quantity:
            return "quantity does not respect step size"
        if min_qty > 0 and quantity < min_qty:
            return "normalized quantity is below min quantity"
        if min_notional > 0 and filter_audit.get("computed_notional", 0.0) < min_notional:
            return "normalized notional is below minimum notional"
        return None

    @staticmethod
    def _symbol_filter_error_message(filter_audit: dict[str, Any]) -> str:
        return (
            f"Order blocked by Binance symbol filters for {filter_audit.get('symbol')}: "
            f"{filter_audit.get('rejection_reason')} "
            f"(tick_size={filter_audit.get('tick_size')}, step_size={filter_audit.get('step_size')}, "
            f"min_qty={filter_audit.get('min_qty')}, min_notional={filter_audit.get('min_notional')}, "
            f"raw_quantity={filter_audit.get('raw_quantity')}, normalized_quantity={filter_audit.get('normalized_quantity')}, "
            f"raw_price={filter_audit.get('raw_price')}, normalized_price={filter_audit.get('normalized_price')}, "
            f"computed_notional={filter_audit.get('computed_notional')})."
        )

    @staticmethod
    def _new_client_order_id(profile_id: str, symbol: str) -> str:
        suffix = uuid4().hex[:18]
        return f"{profile_id[:12]}-{symbol[:10]}-{suffix}"[:36]

    @staticmethod
    def _is_today(value: Any) -> bool:
        if not value:
            return False
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return False
        return dt.astimezone(timezone.utc).date() == datetime.now(timezone.utc).date()

    @staticmethod
    def _parse_iso(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def _is_within_days(value: Any, *, days: int) -> bool:
        dt = BinanceUsdmManualLiveService._parse_iso(value)
        if dt is None:
            return False
        return dt >= (datetime.now(timezone.utc) - timedelta(days=max(1, int(days))))

    @staticmethod
    def _average_hold_minutes(rows: list[dict[str, Any]]) -> float:
        values: list[float] = []
        now = datetime.now(timezone.utc)
        for item in rows:
            opened = BinanceUsdmManualLiveService._parse_iso(item.get("open_timestamp") or item.get("opened_at_utc"))
            closed = BinanceUsdmManualLiveService._parse_iso(item.get("close_timestamp") or item.get("closed_at_utc")) or now
            if opened is None:
                continue
            values.append(max(0.0, (closed - opened).total_seconds() / 60.0))
        return round(sum(values) / len(values), 4) if values else 0.0

    def _profit_factor(self, rows: list[dict[str, Any]]) -> float:
        gross_profit = sum(max(0.0, self._as_float(item.get("realized_pnl"))) for item in rows)
        gross_loss = sum(abs(min(0.0, self._as_float(item.get("realized_pnl")))) for item in rows)
        if gross_loss <= 0.0:
            return gross_profit if gross_profit > 0.0 else 0.0
        return round(gross_profit / gross_loss, 4)

    @staticmethod
    def _format_decimal(value: float) -> str:
        return format(Decimal(str(value)).normalize(), "f")

    @staticmethod
    def _dumps(payload: dict[str, Any]) -> str:
        import json

        return json.dumps(payload, sort_keys=True)

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _as_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _nullable_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


__all__ = ["BinanceUsdmManualLiveError", "BinanceUsdmManualLiveService"]
