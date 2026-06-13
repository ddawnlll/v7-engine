"""Paper execution runtime for v4."""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta, timezone
from typing import Callable
from uuid import uuid4

from runtime.db.repos._helpers import dumps_json
from runtime.db.repos.failure_repo import FailureRepository
from runtime.db.repos.order_repo import OrderRepository
from runtime.db.repos.paper_repo import PaperAccountRepository
from runtime.db.repos.portfolio_repo import PortfolioRepository
from runtime.db.repos.signal_repo import SignalRepository
from runtime.db.repos.settings_repo import SettingsRepository
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.db.session import session_scope
from runtime.services.decision_attribution_service import DecisionAttributionService
from runtime.services.failure_classifier import FailureClassifier
from runtime.services.improvement_registry_service import ImprovementRegistryService
from runtime.services.performance_service import PerformanceService
from runtime.services.signal_features import merge_labeled_outcome
from runtime.services.trace_service import TraceService
from v6.runtime.outcome_recorder import OutcomeRecorder


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _round_money(value: float) -> float:
    return round(float(value), 8)


def _valid_market_price(value) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if price > 0.0 else None


def _interval_to_minutes(interval: str) -> int:
    original = str(interval or "1h").strip()
    raw = original.lower()
    if original == "1M" or raw in {"1mo", "1month"}:
        return 43200
    if raw.endswith("m"):
        return max(1, int(raw[:-1] or "1"))
    if raw.endswith("h"):
        return max(1, int(raw[:-1] or "1")) * 60
    if raw.endswith("d"):
        return max(1, int(raw[:-1] or "1")) * 1440
    if raw.endswith("w"):
        return max(1, int(raw[:-1] or "1")) * 10080
    return 60


class InsufficientFundsError(ValueError):
    """Raised when the paper account cannot fund a requested trade."""


class PaperExecutionService:
    def __init__(
        self,
        order_repo: OrderRepository | None = None,
        paper_repo: PaperAccountRepository | None = None,
        portfolio_repo: PortfolioRepository | None = None,
        signal_repo: SignalRepository | None = None,
        failure_repo: FailureRepository | None = None,
        failure_classifier: FailureClassifier | None = None,
    ) -> None:
        self.order_repo = order_repo or OrderRepository()
        self.paper_repo = paper_repo or PaperAccountRepository()
        self.portfolio_repo = portfolio_repo or PortfolioRepository()
        self.signal_repo = signal_repo or SignalRepository()
        self.failure_repo = failure_repo or FailureRepository()
        self.failure_classifier = failure_classifier or FailureClassifier()
        self.settings_repo = SettingsRepository()
        self.trace_service = TraceService()
        self.performance_service = PerformanceService(order_repo=self.order_repo)
        self.registry_service = ImprovementRegistryService()
        self.attribution_service = DecisionAttributionService(self.registry_service)
        self.outcome_recorder = OutcomeRecorder()

    @staticmethod
    def _execution_identity(signal: dict, *, profile_id: str) -> tuple[dict, dict]:
        execution_target = dict(signal.get("execution_target") or {})
        execution_account = dict(signal.get("execution_account") or {})
        if not execution_target:
            execution_target = {
                "profile_id": profile_id,
                "profile_name": profile_id,
                "status": "ACTIVE",
                "runtime_mode": "PAPER",
                "execution_mode": "PAPER",
                "venue": "INTERNAL_PAPER",
                "product_type": "SIMULATED",
                "default_for_auto_trading": profile_id == PAPER_PROFILE_ID,
                "manual_trading_enabled": True,
                "auto_trading_enabled": profile_id == PAPER_PROFILE_ID,
                "read_only": False,
                "credential_ref": None,
                "route_key": f"{profile_id}:PAPER:INTERNAL_PAPER",
            }
        if not execution_account:
            account_id = str(signal.get("execution_account_id") or f"{profile_id}:default")
            execution_account = {
                "profile_id": profile_id,
                "account_id": account_id,
                "account_key": "default",
                "account_type": "PAPER_CASH",
                "venue_account_key": signal.get("venue_account_key"),
                "balance_ccy": "USD",
                "available_balance": None,
                "equity": None,
                "margin_used": None,
                "execution_mode": execution_target.get("execution_mode") or "PAPER",
                "venue": execution_target.get("venue") or "INTERNAL_PAPER",
                "routing_key": str(signal.get("execution_routing_key") or f"{profile_id}:INTERNAL_PAPER:{account_id}"),
                "venue_scope": signal.get("venue_account_key") or execution_target.get("venue") or "INTERNAL_PAPER",
                "is_primary": True,
            }
        return execution_target, execution_account

    @staticmethod
    def _artifact_identity(payload: dict, *, profile_id: str) -> dict:
        execution_target = dict(payload.get("execution_target") or {})
        execution_account = dict(payload.get("execution_account") or {})
        if not execution_target:
            execution_target = {
                "profile_id": profile_id,
                "route_key": f"{profile_id}:PAPER:INTERNAL_PAPER",
                "execution_mode": "PAPER",
                "venue": "INTERNAL_PAPER",
            }
        if not execution_account:
            account_id = f"{profile_id}:default"
            execution_account = {
                "profile_id": profile_id,
                "account_id": account_id,
                "account_key": "default",
                "account_type": "PAPER_CASH",
                "balance_ccy": "USD",
                "execution_mode": execution_target.get("execution_mode") or "PAPER",
                "venue": execution_target.get("venue") or "INTERNAL_PAPER",
                "routing_key": f"{profile_id}:INTERNAL_PAPER:{account_id}",
                "venue_scope": execution_target.get("venue") or "INTERNAL_PAPER",
                "is_primary": True,
            }
        return {
            "execution_target": execution_target,
            "execution_account": execution_account,
            "execution_account_id": execution_account.get("account_id"),
            "execution_routing_key": execution_account.get("routing_key"),
            "execution_target_route_key": execution_target.get("route_key"),
            "profile_id": profile_id,
        }

    @staticmethod
    def _paper_account_identity(account: dict, *, profile_id: str) -> dict:
        account_id = str(account.get("account_id") or f"{profile_id}:default")
        return {
            "execution_account": {
                "profile_id": profile_id,
                "account_id": account_id,
                "account_key": account.get("account_key"),
                "account_type": account.get("account_type"),
                "venue_account_key": account.get("venue_account_key"),
                "balance_ccy": account.get("balance_ccy"),
                "available_balance": account.get("available_balance"),
                "equity": account.get("equity"),
                "margin_used": account.get("margin_used"),
                "execution_mode": "PAPER",
                "venue": "INTERNAL_PAPER",
                "routing_key": f"{profile_id}:INTERNAL_PAPER:{account_id}",
                "venue_scope": account.get("venue_account_key") or "INTERNAL_PAPER",
                "is_primary": True,
            },
            "execution_target": {
                "profile_id": profile_id,
                "profile_name": profile_id,
                "status": "ACTIVE",
                "runtime_mode": "PAPER",
                "execution_mode": "PAPER",
                "venue": "INTERNAL_PAPER",
                "product_type": "SIMULATED",
                "default_for_auto_trading": profile_id == PAPER_PROFILE_ID,
                "manual_trading_enabled": True,
                "auto_trading_enabled": profile_id == PAPER_PROFILE_ID,
                "read_only": False,
                "credential_ref": None,
                "route_key": f"{profile_id}:PAPER:INTERNAL_PAPER",
            },
            "execution_account_id": account_id,
            "execution_routing_key": f"{profile_id}:INTERNAL_PAPER:{account_id}",
            "execution_target_route_key": f"{profile_id}:PAPER:INTERNAL_PAPER",
        }

    def open_order(
        self,
        signal: dict,
        *,
        quantity: float = 1.0,
        entry_price: float | None = None,
        fee: float = 0.0,
        source: str = "PAPER",
        opened_at_utc: str | None = None,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict:
        opened_at = opened_at_utc or utc_now_iso()
        order_id = f"ord-{uuid4().hex[:16]}"
        fill_id = f"fill-{uuid4().hex[:16]}"
        position_id = f"pos-{uuid4().hex[:16]}"

        profile_id = str(signal.get("profile_id") or profile_id or PAPER_PROFILE_ID)
        signal_id = str(signal.get("signal_id") or "")
        entry = _as_float(entry_price if entry_price is not None else signal.get("entry"), 0.0)
        stop_loss = signal.get("stop_loss")
        take_profit = signal.get("take_profit")
        requested_quantity = max(_as_float(quantity, 1.0), 0.0)
        quantity_value = requested_quantity
        opening_fee = _round_money(_as_float(fee))
        entry_notional = _round_money(entry * quantity_value)
        reserved_cost = _round_money(entry_notional + opening_fee)
        requested_reserved_cost = reserved_cost
        budget_mode = "FUNDED"
        cash_settled = True
        timing_estimate = dict(signal.get("timing_estimate") or {})
        interval_minutes = int(timing_estimate.get("interval_minutes") or _interval_to_minutes(str(signal.get("interval") or "1h")))
        execution_target, execution_account = self._execution_identity(signal, profile_id=profile_id)
        payload = {
            "position_id": position_id,
            "quantity": quantity_value,
            "requested_quantity": requested_quantity,
            "fees": opening_fee,
            "entry_notional": entry_notional,
            "reserved_cost": reserved_cost,
            "requested_reserved_cost": requested_reserved_cost,
            "budget_mode": budget_mode,
            "cash_settled": cash_settled,
            "paper_sizing": dict(signal.get("paper_sizing") or {}),
            "realized_pnl": None,
            "realized_r": None,
            "close_reason": None,
            "last_price": entry,
            "timing_estimate": timing_estimate,
            "expected_candles_min": _as_float(timing_estimate.get("candles_min")) if timing_estimate.get("candles_min") is not None else None,
            "expected_candles_max": _as_float(timing_estimate.get("candles_max")) if timing_estimate.get("candles_max") is not None else None,
            "expected_candles_target": _as_float(timing_estimate.get("candles_target")) if timing_estimate.get("candles_target") is not None else None,
            "interval_minutes": interval_minutes,
            "stale_exit_candles": int(_as_float(timing_estimate.get("stale_exit_candles"), 0.0)),
            "stale_exit_min_progress_pct": _as_float(timing_estimate.get("stale_exit_min_progress_pct")),
            "stale_exit_max_abs_r": _as_float(timing_estimate.get("stale_exit_max_abs_r")),
            "time_stop_candles": int(_as_float(timing_estimate.get("time_stop_candles"), 0.0)),
            "signal": {
                "signal_id": signal_id,
                "summary": signal.get("summary"),
                "regime": signal.get("regime"),
                "trend": signal.get("trend"),
                "direction": signal.get("direction"),
                "confidence": signal.get("confidence"),
                "mode": signal.get("mode"),
                "interval": signal.get("interval"),
                "symbol": signal.get("symbol"),
                "no_trade_reason": signal.get("no_trade_reason"),
                "factors": list(signal.get("factors") or []),
                "decision_event_id": signal.get("decision_event_id"),
                "trade_outcome_id": signal.get("trade_outcome_id"),
                "request_id": signal.get("request_id"),
            },
            "learning": {
                "applied_at_utc": opened_at,
                "confidence_before": _as_float(signal.get("confidence_raw"), _as_float(signal.get("confidence"))),
                "confidence_after": _as_float(signal.get("confidence")),
                "probability_before": _as_float(signal.get("probability_raw"), _as_float(signal.get("probability"))),
                "probability_after": _as_float(signal.get("probability")),
                "expected_value_after": signal.get("expected_value"),
                "adjustments": dict(((signal.get("advanced_analysis") or {}).get("learning_adjustments") or {})),
            },
            "self_learning": dict(((signal.get("advanced_analysis") or {}).get("self_learning") or {})),
            "execution_target": execution_target,
            "execution_account": execution_account,
        }

        with session_scope() as session:
            settings_resolution = self.settings_repo.get_resolution(session, profile_id=profile_id)
            resolved_config_hash = str(settings_resolution.get("resolved_config_hash") or "")
            account = self._get_paper_account(session, profile_id=profile_id)
            available_balance = _round_money(_as_float(account.get("balance")))
            allow_unfunded = self._allow_unfunded_trades(session, profile_id=profile_id)
            if (reserved_cost > available_balance or requested_quantity <= 0.0) and available_balance <= 0.0 and allow_unfunded:
                    quantity_value = 0.0
                    opening_fee = 0.0
                    entry_notional = 0.0
                    reserved_cost = 0.0
                    budget_mode = "UNFUNDED"
                    cash_settled = False
                    payload.update(
                        {
                            "quantity": quantity_value,
                            "fees": opening_fee,
                            "entry_notional": entry_notional,
                            "reserved_cost": reserved_cost,
                            "budget_mode": budget_mode,
                            "cash_settled": cash_settled,
                        }
                    )
            elif reserved_cost > available_balance:
                self._require_paper_balance(session, required=reserved_cost, profile_id=profile_id)
            try:
                if cash_settled and reserved_cost > 0:
                    self.paper_repo.update_balance(session, -reserved_cost, profile_id=profile_id)
                order = self.order_repo.save_order(
                    session,
                    {
                        "order_id": order_id,
                        "profile_id": profile_id,
                        "signal_id": signal_id or None,
                        "source": source,
                        "symbol": str(signal.get("symbol") or ""),
                        "interval": str(signal.get("interval") or ""),
                        "mode": str(signal.get("mode") or ""),
                        "direction": str(signal.get("direction") or "BUY"),
                        "status": "OPEN",
                        "entry": entry,
                        "stop_loss": _as_float(stop_loss) if stop_loss is not None else None,
                        "take_profit": _as_float(take_profit) if take_profit is not None else None,
                        "close_price": None,
                        "risk_reward": _as_float(signal.get("risk_reward")) if signal.get("risk_reward") is not None else None,
                        "confidence": _as_float(signal.get("confidence")),
                        "opened_at_utc": opened_at,
                        "closed_at_utc": None,
                        "payload_json": dumps_json(payload),
                        "resolved_config_hash": resolved_config_hash,
                    },
                )
                fill = self.order_repo.save_fill(
                    session,
                    {
                        "fill_id": fill_id,
                        "profile_id": profile_id,
                        "order_id": order_id,
                        "symbol": order["symbol"],
                        "direction": order["direction"],
                        "quantity": quantity_value,
                        "price": entry,
                        "fee": opening_fee,
                        "filled_at_utc": opened_at,
                    },
                )
                position = self.order_repo.save_position(
                    session,
                    {
                        "position_id": position_id,
                        "profile_id": profile_id,
                        "symbol": order["symbol"],
                        "interval": order["interval"],
                        "mode": order["mode"],
                        "direction": order["direction"],
                        "quantity": quantity_value,
                        "average_entry": entry,
                        "mark_price": entry,
                        "unrealized_pnl": 0.0,
                        "status": "OPEN",
                        "opened_at_utc": opened_at,
                        "closed_at_utc": None,
                        "payload_json": dumps_json(
                            {
                                "order_id": order_id,
                                "stop_loss": order.get("stop_loss"),
                                "take_profit": order.get("take_profit"),
                                "confidence": order.get("confidence"),
                                "source": order.get("source"),
                                "execution_target": execution_target,
                                "execution_account": execution_account,
                            }
                        ),
                    },
                )
                signal_outcome = self.persist_signal_outcome(
                    signal_id or None,
                    {
                        "status": "ORDER_OPENED",
                        "order_id": order_id,
                        "position_id": position_id,
                        "opened_at_utc": opened_at,
                        "budget_mode": budget_mode,
                    },
                    session=session,
                )
                portfolio = self.refresh_portfolio_snapshot(session=session, profile_id=profile_id)
            except Exception:
                if cash_settled and reserved_cost > 0:
                    self.paper_repo.update_balance(session, reserved_cost, profile_id=profile_id)
                raise
        self.trace_service.log_event(
            "ORDER_CREATED",
            signal={**signal, "profile_id": profile_id},
            source=source,
            order_id=order_id,
            status="OPEN",
            decision=str(signal.get("direction") or "BUY"),
            reason_text=f"Opened {source.lower()} order",
            details={
                "entry": entry,
                "quantity": quantity_value,
                "position_id": position_id,
                "reserved_cost": reserved_cost,
                "paper_balance_before": account["balance"],
                "budget_mode": budget_mode,
            },
            profile_id=profile_id,
            resolved_config_hash=resolved_config_hash,
        )
        self.attribution_service.capture_trade_attribution(
            order_id,
            signal_id or None,
            str(signal.get("run_id") or payload.get("signal", {}).get("run_id") or "manual"),
            self._components_used_for_trade(signal),
            self._decision_summary(signal, sizing=signal.get("paper_sizing"), order_id=order_id),
            profile_id=profile_id,
        )
        self.performance_service.store_snapshot("order_created", profile_id=profile_id)
        artifact_identity = self._artifact_identity(payload, profile_id=profile_id)
        return {
            "order": {**order, **artifact_identity},
            "fill": {**fill, **artifact_identity},
            "position": {**position, **artifact_identity},
            "signal_outcome": signal_outcome,
            "portfolio": portfolio,
        }

    def close_order(
        self,
        order_id: str,
        *,
        close_price: float,
        close_reason: str = "MANUAL_CLOSE",
        fee: float = 0.0,
        closed_at_utc: str | None = None,
    ) -> dict:
        closed_at = closed_at_utc or utc_now_iso()
        fill_id = f"fill-{uuid4().hex[:16]}"

        with session_scope() as session:
            order = self.order_repo.get_order(session, order_id)
            if order is None:
                raise ValueError(f"Order not found: {order_id}")
            if str(order.get("status") or "").upper() != "OPEN":
                raise ValueError(f"Order is not open: {order_id}")

            profile_id = str(order.get("profile_id") or PAPER_PROFILE_ID)
            payload = dict(order.get("payload") or {})
            normalized_close_price = self._resolve_close_price(order, close_price=close_price, close_reason=close_reason)
            if normalized_close_price is None:
                raise ValueError(f"Invalid close price for {order_id}: {close_price!r}")
            quantity = max(_as_float(payload.get("quantity"), 1.0), 0.0)
            cash_settled = bool(payload.get("cash_settled", True))
            entry = _as_float(order.get("entry"))
            closing_fee = _round_money(_as_float(fee))
            if not cash_settled:
                closing_fee = 0.0
            gross_proceeds = _round_money(normalized_close_price * quantity)
            net_proceeds = _round_money(gross_proceeds - closing_fee)
            realized_pnl = self._realized_pnl(
                direction=str(order.get("direction") or "BUY"),
                entry=entry,
                exit_price=normalized_close_price,
                quantity=quantity,
            ) - _round_money(_as_float(payload.get("fees"), 0.0) + closing_fee)
            realized_r = self._realized_r(
                direction=str(order.get("direction") or "BUY"),
                entry=entry,
                stop_loss=order.get("stop_loss"),
                exit_price=normalized_close_price,
            )
            if realized_r is not None:
                realized_r = _round_money(realized_r)

            updated_payload = dict(payload)
            updated_payload.update(
                {
                    "fees": _round_money(_as_float(payload.get("fees"), 0.0) + closing_fee),
                    "realized_pnl": _round_money(realized_pnl),
                    "realized_r": realized_r,
                    "close_reason": close_reason,
                    "gross_proceeds": gross_proceeds,
                    "net_proceeds": net_proceeds,
                }
            )
            try:
                if cash_settled and net_proceeds:
                    self.paper_repo.update_balance(session, net_proceeds, profile_id=profile_id)
                saved_order = self.order_repo.save_order(
                    session,
                    {
                        "order_id": order["order_id"],
                        "profile_id": profile_id,
                        "signal_id": order.get("signal_id"),
                        "source": str(order.get("source") or "PAPER"),
                        "symbol": str(order.get("symbol") or ""),
                        "interval": str(order.get("interval") or ""),
                        "mode": str(order.get("mode") or ""),
                        "direction": str(order.get("direction") or "BUY"),
                        "status": "CLOSED",
                        "entry": entry,
                        "stop_loss": order.get("stop_loss"),
                        "take_profit": order.get("take_profit"),
                        "close_price": normalized_close_price,
                        "risk_reward": order.get("risk_reward"),
                        "confidence": _as_float(order.get("confidence")),
                        "opened_at_utc": str(order.get("opened_at_utc") or order.get("open_timestamp") or closed_at),
                        "closed_at_utc": closed_at,
                        "payload_json": dumps_json(updated_payload),
                    },
                )
                closing_direction = "SELL" if str(order.get("direction") or "BUY").upper() == "BUY" else "BUY"
                fill = self.order_repo.save_fill(
                    session,
                    {
                        "fill_id": fill_id,
                        "profile_id": profile_id,
                        "order_id": order_id,
                        "symbol": str(order.get("symbol") or ""),
                        "direction": closing_direction,
                        "quantity": quantity,
                        "price": normalized_close_price,
                        "fee": closing_fee,
                        "filled_at_utc": closed_at,
                    },
                )
                position_id = str(payload.get("position_id") or f"pos-{order_id}")
                position = self.order_repo.save_position(
                    session,
                    {
                        "position_id": position_id,
                        "profile_id": profile_id,
                        "symbol": str(order.get("symbol") or ""),
                        "interval": str(order.get("interval") or ""),
                        "mode": str(order.get("mode") or ""),
                        "direction": str(order.get("direction") or "BUY"),
                        "quantity": quantity,
                        "average_entry": entry,
                        "mark_price": normalized_close_price,
                        "unrealized_pnl": 0.0,
                        "status": "CLOSED",
                        "opened_at_utc": str(order.get("opened_at_utc") or order.get("open_timestamp") or closed_at),
                        "closed_at_utc": closed_at,
                        "payload_json": dumps_json(
                            {
                                "order_id": order_id,
                                "stop_loss": order.get("stop_loss"),
                                "take_profit": order.get("take_profit"),
                                "confidence": order.get("confidence"),
                                "source": order.get("source"),
                                "realized_pnl": _round_money(realized_pnl),
                                "realized_r": realized_r,
                                "close_reason": close_reason,
                                "execution_target": payload.get("execution_target") or {},
                                "execution_account": payload.get("execution_account") or {},
                            }
                        ),
                    },
                )
                signal_outcome = self.persist_signal_outcome(
                    order.get("signal_id"),
                    {
                        "status": "ORDER_CLOSED",
                        "order_id": order_id,
                        "close_price": normalized_close_price,
                        "close_reason": close_reason,
                        "realized_pnl": _round_money(realized_pnl),
                        "realized_r": realized_r,
                        "closed_at_utc": closed_at,
                    },
                    session=session,
                )
                portfolio = self.refresh_portfolio_snapshot(session=session, profile_id=profile_id)
                signal_record = self.signal_repo.get_signal(session, str(order.get("signal_id") or "")) if order.get("signal_id") else None
                self._resolve_linked_trade_outcome(
                    session=session,
                    order=saved_order,
                    payload=updated_payload,
                    close_price=normalized_close_price,
                    close_reason=close_reason,
                    realized_pnl=_round_money(realized_pnl),
                    realized_r=realized_r,
                    closed_at_utc=closed_at,
                )
            except Exception:
                if cash_settled and net_proceeds:
                    self.paper_repo.update_balance(session, -net_proceeds, profile_id=profile_id)
                raise
        failure = self._classify_and_persist_failure(
            order=saved_order,
            signal=signal_record,
            realized_r=realized_r,
            closed_at_utc=closed_at,
        )
        self.attribution_service.attach_trade_outcome(
            order_id,
            realized_r=realized_r,
            close_reason=close_reason,
            realized_pnl=_round_money(realized_pnl),
            closed_at_utc=closed_at,
            profile_id=str(order.get("profile_id") or PAPER_PROFILE_ID),
        )
        self.trace_service.log_event(
            "ORDER_CLOSED",
            signal={
                "signal_id": order.get("signal_id"),
                "symbol": order.get("symbol"),
                "interval": order.get("interval"),
                "mode": order.get("mode"),
                "direction": order.get("direction"),
                "confidence": order.get("confidence"),
                "summary": order.get("signal_payload", {}).get("summary"),
                "regime": order.get("signal_payload", {}).get("regime"),
                "profile_id": order.get("profile_id"),
            },
            source=str(order.get("source") or "PAPER"),
            order_id=order_id,
            status="CLOSED",
            decision=close_reason,
            reason_code=close_reason,
            reason_text=f"Closed order via {close_reason.lower()}",
            details={"close_price": normalized_close_price, "realized_pnl": _round_money(realized_pnl), "realized_r": realized_r},
            profile_id=str(order.get("profile_id") or PAPER_PROFILE_ID),
        )
        self.performance_service.store_snapshot(close_reason.lower(), profile_id=str(order.get("profile_id") or PAPER_PROFILE_ID))
        artifact_identity = self._artifact_identity(updated_payload, profile_id=str(order.get("profile_id") or PAPER_PROFILE_ID))
        return {
            "order": {**saved_order, **artifact_identity},
            "fill": {**fill, **artifact_identity},
            "position": {**position, **artifact_identity},
            "signal_outcome": signal_outcome,
            "portfolio": portfolio,
            "failure": failure,
        }

    def create_manual_order(self, payload: dict) -> dict:
        required = ["symbol", "interval", "mode", "direction", "confidence", "entry", "sl", "tp"]
        for key in required:
            if payload.get(key) in (None, ""):
                raise ValueError(f"Missing required field: {key}")
        sizing_meta = None
        requested_quantity = _as_float(payload.get("quantity"), 0.0)
        if requested_quantity <= 0:
            sizing_meta = self.compute_confidence_position_size(
                _as_float(payload.get("entry")),
                confidence=_as_float(payload.get("confidence")),
                fee=_as_float(payload.get("fee"), 0.0),
                profile_id=str(payload.get("profile_id") or PAPER_PROFILE_ID),
            )
            requested_quantity = _as_float(sizing_meta.get("quantity"), 0.0)
        return self.open_order(
            {
                "signal_id": payload.get("signal_id"),
                "profile_id": str(payload.get("profile_id") or PAPER_PROFILE_ID),
                "symbol": str(payload["symbol"]).upper(),
                "interval": str(payload["interval"]).lower(),
                "mode": str(payload["mode"]).upper(),
                "direction": str(payload["direction"]).upper(),
                "confidence": _as_float(payload.get("confidence")),
                "entry": _as_float(payload.get("entry")),
                "entry_zone_low": payload.get("entry_zone_low"),
                "entry_zone_high": payload.get("entry_zone_high"),
                "stop_loss": _as_float(payload.get("sl")),
                "take_profit": _as_float(payload.get("tp")),
                "risk_reward": payload.get("risk_reward"),
                "summary": payload.get("summary"),
                "regime": payload.get("regime"),
                "trend": payload.get("trend"),
                "timing_estimate": dict(payload.get("timing_estimate") or {}),
                "paper_sizing": sizing_meta,
            },
            quantity=requested_quantity,
            fee=_as_float(payload.get("fee"), 0.0),
            source="MANUAL",
            profile_id=str(payload.get("profile_id") or PAPER_PROFILE_ID),
        )

    def update_manual_order(self, order_id: str, payload: dict) -> dict:
        with session_scope() as session:
            order = self.order_repo.get_order(session, order_id)
            if order is None:
                raise ValueError(f"Order not found: {order_id}")
            if str(order.get("source") or "").upper() != "MANUAL":
                raise ValueError(f"Order is not manual: {order_id}")
            profile_id = str(order.get("profile_id") or PAPER_PROFILE_ID)
            current_payload = dict(order.get("payload") or {})

            last_price = payload.get("last_price")
            if last_price is not None:
                current_payload["last_price"] = _as_float(last_price)

            timing_estimate = payload.get("timing_estimate")
            if isinstance(timing_estimate, dict):
                current_payload["timing_estimate"] = dict(timing_estimate)
                current_payload["expected_candles_min"] = _as_float(timing_estimate.get("candles_min")) if timing_estimate.get("candles_min") is not None else None
                current_payload["expected_candles_max"] = _as_float(timing_estimate.get("candles_max")) if timing_estimate.get("candles_max") is not None else None
                current_payload["expected_candles_target"] = _as_float(timing_estimate.get("candles_target")) if timing_estimate.get("candles_target") is not None else None
                current_payload["interval_minutes"] = int(timing_estimate.get("interval_minutes") or _interval_to_minutes(str(order.get("interval") or "1h")))
                current_payload["stale_exit_candles"] = int(_as_float(timing_estimate.get("stale_exit_candles"), 0.0))
                current_payload["stale_exit_min_progress_pct"] = _as_float(timing_estimate.get("stale_exit_min_progress_pct"))
                current_payload["stale_exit_max_abs_r"] = _as_float(timing_estimate.get("stale_exit_max_abs_r"))
                current_payload["time_stop_candles"] = int(_as_float(timing_estimate.get("time_stop_candles"), 0.0))

            if payload.get("status") is not None:
                status_value = str(payload["status"]).upper()
                if status_value in {"MANUAL_CLOSE", "HIT_TP", "HIT_SL", "CANCELLED"}:
                    close_price = _as_float(payload.get("close_price"), _as_float(current_payload.get("last_price"), _as_float(order.get("entry"))))
                    return self.close_order(order_id, close_price=close_price, close_reason=status_value)
                if status_value not in {"OPEN", "PENDING", "ORDERED"}:
                    raise ValueError("Invalid manual order status")

            saved_order = self.order_repo.save_order(
                session,
                {
                    "order_id": order["order_id"],
                    "profile_id": profile_id,
                    "signal_id": order.get("signal_id"),
                    "source": "MANUAL",
                    "symbol": str(order.get("symbol") or ""),
                    "interval": str(order.get("interval") or ""),
                    "mode": str(order.get("mode") or ""),
                    "direction": str(order.get("direction") or "BUY"),
                    "status": "OPEN",
                    "entry": _as_float(order.get("entry")),
                    "stop_loss": order.get("stop_loss"),
                    "take_profit": order.get("take_profit"),
                    "close_price": None,
                    "risk_reward": order.get("risk_reward"),
                    "confidence": _as_float(order.get("confidence")),
                    "opened_at_utc": str(order.get("open_timestamp") or order.get("opened_at_utc") or utc_now_iso()),
                    "closed_at_utc": None,
                    "payload_json": dumps_json(current_payload),
                },
            )
            position_id = str(current_payload.get("position_id") or "")
            position = None
            if position_id:
                current_position = next(
                    (
                        item
                        for item in self.order_repo.list_positions(session, limit=500, profile_id=profile_id)
                        if str(item.get("position_id")) == position_id
                    ),
                    None,
                )
                if current_position:
                    position = self.order_repo.save_position(
                        session,
                        {
                            "position_id": position_id,
                            "profile_id": profile_id,
                            "symbol": str(current_position.get("symbol") or saved_order["symbol"]),
                            "interval": str(current_position.get("interval") or saved_order["interval"]),
                            "mode": str(current_position.get("mode") or saved_order["mode"]),
                            "direction": str(current_position.get("direction") or saved_order["direction"]),
                            "quantity": _as_float(current_position.get("quantity"), 1.0),
                            "average_entry": _as_float(current_position.get("average_entry"), _as_float(saved_order.get("entry"))),
                            "mark_price": _as_float(current_payload.get("last_price"), _as_float(current_position.get("mark_price"), _as_float(saved_order.get("entry")))),
                            "unrealized_pnl": 0.0,
                            "status": "OPEN",
                            "opened_at_utc": str(current_position.get("open_timestamp") or current_position.get("opened_at_utc") or saved_order["open_timestamp"]),
                            "closed_at_utc": None,
                            "payload_json": dumps_json(dict(current_position.get("payload") or {})),
                        },
                    )
            portfolio = self.refresh_portfolio_snapshot(session=session, profile_id=profile_id)
        self.trace_service.log_event(
            "MANUAL_ORDER_UPDATED",
            signal={
                "signal_id": saved_order.get("signal_id"),
                "symbol": saved_order.get("symbol"),
                "interval": saved_order.get("interval"),
                "mode": saved_order.get("mode"),
                "direction": saved_order.get("direction"),
                "confidence": saved_order.get("confidence"),
                "profile_id": saved_order.get("profile_id"),
            },
            source="MANUAL",
            order_id=order_id,
            status="OPEN",
            decision="UPDATE",
            reason_text="Manual order updated",
            details={"last_price": current_payload.get("last_price"), "timing_estimate": current_payload.get("timing_estimate")},
            profile_id=str(saved_order.get("profile_id") or PAPER_PROFILE_ID),
        )
        self.performance_service.store_snapshot("manual_order_updated", profile_id=str(saved_order.get("profile_id") or PAPER_PROFILE_ID))
        artifact_identity = self._artifact_identity(current_payload, profile_id=str(saved_order.get("profile_id") or PAPER_PROFILE_ID))
        return {
            "order": {**saved_order, **artifact_identity},
            "position": {**position, **artifact_identity} if position is not None else None,
            "portfolio": portfolio,
        }

    def delete_manual_order(self, order_id: str) -> bool:
        with session_scope() as session:
            order = self.order_repo.get_order(session, order_id)
            if order is None:
                raise ValueError(f"Order not found: {order_id}")
            if str(order.get("source") or "").upper() != "MANUAL":
                raise ValueError(f"Order is not manual: {order_id}")
            if str(order.get("status") or "").upper() == "OPEN":
                raise ValueError("Open manual orders must be closed before deletion")
        with session_scope() as session:
            from runtime.db.models import Fill, Order, Position

            order_row = session.query(Order).filter(Order.order_id == order_id).one_or_none()
            if order_row is None:
                raise ValueError(f"Order not found: {order_id}")
            payload = dict(order.get("payload") or {})
            position_id = str(payload.get("position_id") or "")
            session.query(Fill).filter(Fill.order_id == order_id).delete()
            if position_id:
                session.query(Position).filter(Position.position_id == position_id).delete()
            session.delete(order_row)
            session.commit()
        self.trace_service.log_event(
            "MANUAL_ORDER_DELETED",
            signal={
                "signal_id": order.get("signal_id"),
                "symbol": order.get("symbol"),
                "interval": order.get("interval"),
                "mode": order.get("mode"),
                "direction": order.get("direction"),
                "confidence": order.get("confidence"),
                "profile_id": order.get("profile_id"),
            },
            source="MANUAL",
            order_id=order_id,
            status="DELETED",
            decision="DELETE",
            reason_text="Manual order deleted",
            profile_id=str(order.get("profile_id") or PAPER_PROFILE_ID),
        )
        self.performance_service.store_snapshot("manual_order_deleted", profile_id=str(order.get("profile_id") or PAPER_PROFILE_ID))
        return True

    def monitor_open_orders(self, price_fetcher: Callable[[str], float | None] | None = None, *, profile_id: str = PAPER_PROFILE_ID) -> dict:
        if price_fetcher is None:
            from runtime.services.binance_client import fetch_ticker

            def price_fetcher(symbol: str) -> float | None:
                return _valid_market_price(fetch_ticker(symbol).get("price"))

        with session_scope() as session:
            open_orders = [self._hydrate_order(session, row) for row in self.order_repo.list_orders(session, status="OPEN", limit=1000, profile_id=profile_id)]

        checked = 0
        closed = 0
        errors: list[dict[str, str]] = []
        for order in open_orders:
            symbol = str(order.get("symbol") or "")
            try:
                price = price_fetcher(symbol)
            except Exception as exc:
                errors.append({"order_id": str(order.get("order_id") or ""), "symbol": symbol, "error": str(exc)})
                continue
            price = _valid_market_price(price)
            if price is None:
                errors.append({"order_id": str(order.get("order_id") or ""), "symbol": symbol, "error": "Invalid market price"})
                continue
            checked += 1
            updated = self._update_open_order_mark(str(order["order_id"]), float(price))
            close_reason = self._close_reason(updated)
            if close_reason is None:
                close_reason = self._stale_exit_reason(updated)
            if close_reason is None and self._should_time_stop(updated):
                close_reason = "TIME_STOP"
            if close_reason is not None:
                settlement_price = self._resolve_close_price(updated, close_price=float(price), close_reason=close_reason)
                if settlement_price is None:
                    errors.append({"order_id": str(order.get("order_id") or ""), "symbol": symbol, "error": "Invalid settlement price"})
                    continue
                self.close_order(str(order["order_id"]), close_price=settlement_price, close_reason=close_reason)
                closed += 1
        if checked or closed:
            self.performance_service.store_snapshot("monitor_open_orders", profile_id=profile_id)
        return {"checked": checked, "closed": closed, "errors": errors}

    def persist_fill(self, payload: dict, *, session=None) -> dict:
        if session is not None:
            return self.order_repo.save_fill(session, payload)
        with session_scope() as local_session:
            return self.order_repo.save_fill(local_session, payload)

    def persist_position_update(self, payload: dict, *, session=None) -> dict:
        if session is not None:
            saved = self.order_repo.save_position(session, payload)
            self.refresh_portfolio_snapshot(session=session, profile_id=str(payload.get("profile_id") or PAPER_PROFILE_ID))
            return saved
        with session_scope() as local_session:
            saved = self.order_repo.save_position(local_session, payload)
            self.refresh_portfolio_snapshot(session=local_session, profile_id=str(payload.get("profile_id") or PAPER_PROFILE_ID))
            return saved

    def _resolve_linked_trade_outcome(
        self,
        *,
        session,
        order: dict,
        payload: dict,
        close_price: float,
        close_reason: str,
        realized_pnl: float,
        realized_r: float | None,
        closed_at_utc: str,
    ) -> None:
        signal_payload = dict(payload.get("signal") or {})
        outcome_id = signal_payload.get("trade_outcome_id") or payload.get("trade_outcome_id")
        decision_event_id = signal_payload.get("decision_event_id") or payload.get("decision_event_id")
        if not outcome_id and not decision_event_id:
            return
        hold_minutes = self._holding_minutes(order)
        interval_minutes = int(_as_float(payload.get("interval_minutes"), 0.0)) or _interval_to_minutes(str(order.get("interval") or "1h"))
        hold_bars = int(round(hold_minutes / interval_minutes)) if hold_minutes is not None and interval_minutes > 0 else None
        entry = _as_float(order.get("entry"))
        realized_return = ((close_price - entry) / entry) if entry > 0 else None
        paper_trade = {
            "order_id": order.get("order_id"),
            "paper_trade_id": order.get("order_id"),
            "decision_event_id": decision_event_id,
            "trade_outcome_id": outcome_id,
            "close_reason": close_reason,
            "close_price": close_price,
            "closed_at_utc": closed_at_utc,
            "realized_return": realized_return,
            "realized_r": realized_r,
            "gross_pnl": payload.get("gross_proceeds"),
            "net_pnl": realized_pnl,
            "realized_pnl": realized_pnl,
            "hold_duration_minutes": hold_minutes,
            "hold_duration_bars": hold_bars,
        }
        self.outcome_recorder.resolve_from_paper_trade(outcome_id, paper_trade, session=session)

    def persist_signal_outcome(self, signal_id: str | None, outcome: dict, *, session=None) -> dict | None:
        if not signal_id:
            return None
        if session is None:
            with session_scope() as local_session:
                return self.persist_signal_outcome(signal_id, outcome, session=local_session)
        signal = self.signal_repo.get_signal(session, signal_id)
        if signal is None:
            return None
        snapshot = dict(signal.get("snapshot") or {})
        features = merge_labeled_outcome(signal.get("features") or {}, outcome)
        snapshot["execution_outcome"] = dict(outcome)
        saved = self.signal_repo.save_signal(
            session,
            {
                "signal_id": signal["signal_id"],
                "profile_id": str(signal.get("profile_id") or PAPER_PROFILE_ID),
                "run_id": signal["run_id"],
                "symbol": signal["symbol"],
                "interval": signal["interval"],
                "mode": signal["mode"],
                "direction": signal["direction"],
                "confidence": signal["confidence"],
                "regime": signal["regime"],
                "trend": signal["trend"],
                "trend_strength": signal["trend_strength"],
                "summary": signal["summary"],
                "no_trade_reason": signal["no_trade_reason"],
                "strategy_version": signal["strategy_version"],
                "snapshot_json": dumps_json(snapshot),
                "features_json": dumps_json(features),
                "factors_json": dumps_json(signal.get("factors") or []),
                "audit_json": dumps_json(signal.get("audit") or {}),
                "created_at_utc": signal["created_at_utc"],
            },
        )
        return saved.get("snapshot", {}).get("execution_outcome")

    def _classify_and_persist_failure(
        self,
        *,
        order: dict,
        signal: dict | None,
        realized_r: float | None,
        closed_at_utc: str,
    ) -> dict | None:
        if realized_r is None or realized_r >= 0:
            return None
        try:
            record = self.failure_classifier.classify(
                order=order,
                signal=signal,
                snapshot=dict((signal or {}).get("snapshot") or {}),
                realized_r=realized_r,
                created_at_utc=closed_at_utc,
            )
            with session_scope() as session:
                return self.failure_repo.save_failure(session, {**record.to_dict(), "profile_id": str(order.get("profile_id") or PAPER_PROFILE_ID)})
        except Exception as exc:
            self.trace_service.log_event(
                "FAILURE_CLASSIFICATION_ERROR",
                source=str(order.get("source") or "PAPER"),
                order_id=str(order.get("order_id") or ""),
                status="ERROR",
                decision="CLASSIFY_FAILURE",
                reason_code="FAILURE_CLASSIFIER_ERROR",
                reason_text=str(exc),
                details={
                    "signal_id": order.get("signal_id"),
                    "symbol": order.get("symbol"),
                    "realized_r": realized_r,
                },
                profile_id=str(order.get("profile_id") or PAPER_PROFILE_ID),
            )
            return None

    def _components_used_for_trade(self, signal: dict) -> list[str]:
        components = {
            "regime_detector",
            "trend_detector",
            "structure_filter",
            "probability_model",
        }
        advanced = dict(signal.get("advanced_analysis") or {})
        learning = dict(advanced.get("learning_adjustments") or {})
        if signal.get("factors"):
            components.add("oscillator_gate")
        if advanced.get("session_label"):
            components.add("session_context")
        if dict(advanced.get("circuit_breaker") or {}):
            components.add("circuit_breaker")
        if float(learning.get("entry_penalty") or 0.0) > 0.0:
            components.add("entry_timing_penalty")
        if float(learning.get("component_penalty") or 0.0) > 0.0:
            components.add("component_penalty")
        if float(learning.get("execution_penalty") or 0.0) > 0.0:
            components.add("execution_penalty")
        if float(learning.get("stop_loss_multiplier") or 1.0) > 1.0:
            components.add("adaptive_stop")
        if learning:
            components.add("learning_calibration")
        return sorted(components)

    @staticmethod
    def _decision_summary(signal: dict, *, sizing: dict | None, order_id: str) -> dict:
        advanced = dict(signal.get("advanced_analysis") or {})
        learning = dict(advanced.get("learning_adjustments") or {})
        return {
            "order_id": order_id,
            "symbol": signal.get("symbol"),
            "interval": signal.get("interval"),
            "mode": signal.get("mode"),
            "direction": signal.get("direction"),
            "regime": signal.get("regime"),
            "confidence": signal.get("confidence"),
            "session_label": advanced.get("session_label"),
            "hold_minutes": None,
            "confidence_bucket": signal.get("confidence"),
            "sizing": sizing or {},
            "learning_adjustments": learning,
            "self_learning": dict(advanced.get("self_learning") or {}),
        }

    def get_orders_snapshot(self, *, limit: int = 500, status: str | None = None, profile_id: str = PAPER_PROFILE_ID) -> dict:
        with session_scope() as session:
            orders = self.order_repo.list_orders(session, status=status, limit=limit, profile_id=profile_id)
            items = [self._hydrate_order(session, order) for order in orders]
        open_items = [item for item in items if str(item.get("status") or "").upper() == "OPEN"]
        closed_items = [item for item in items if str(item.get("status") or "").upper() != "OPEN"]
        open_analysis = self._open_trade_analysis(open_items)
        return {
            "items": items,
            "summary": {
                "open": len(open_items),
                "closed": len(closed_items),
                "total": len(items),
                "net_r": round(sum(_as_float(item.get("realized_r")) for item in closed_items), 4),
                "open_expected_r": open_analysis["open_expected_r"],
                "expected_net_r": round(sum(_as_float(item.get("realized_r")) for item in closed_items) + _as_float(open_analysis["open_expected_r"]), 4),
            },
            "open_trade_analysis": open_analysis,
        }

    def get_paper_balance_payload(self, *, profile_id: str = PAPER_PROFILE_ID) -> dict:
        with session_scope() as session:
            account = self._get_paper_account(session, profile_id=profile_id)
            default_balance = self._default_paper_balance(session, profile_id=profile_id)
            settings_resolution = self.settings_repo.get_resolution(session, profile_id=profile_id)
        identity = self._paper_account_identity(account, profile_id=profile_id)
        return {
            "profile_id": profile_id,
            "account": account,
            "balance": account["balance"],
            "default_balance": default_balance,
            "resolved_config_hash": settings_resolution.get("resolved_config_hash"),
            **identity,
        }

    def compute_affordable_quantity(self, entry_price: float, *, requested_quantity: float = 1.0, fee: float = 0.0, profile_id: str = PAPER_PROFILE_ID) -> float:
        entry_value = _as_float(entry_price)
        requested = max(_as_float(requested_quantity, 1.0), 0.0)
        fixed_fee = max(_round_money(_as_float(fee)), 0.0)
        if entry_value <= 0 or requested <= 0:
            return 0.0
        with session_scope() as session:
            balance = self._get_paper_account(session, profile_id=profile_id)["balance"]
        available_for_notional = max(0.0, _as_float(balance) - fixed_fee)
        if available_for_notional <= 0:
            return 0.0
        affordable = available_for_notional / entry_value
        return round(max(0.0, min(requested, affordable)), 8)

    def compute_confidence_position_size(
        self,
        entry_price: float,
        *,
        confidence: float,
        fee: float = 0.0,
        requested_quantity: float | None = None,
        risk_adjustment_factor: float = 1.0,
        stop_distance_atr: float | None = None,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict:
        entry_value = _as_float(entry_price)
        fixed_fee = max(_round_money(_as_float(fee)), 0.0)
        confidence_value = _as_float(confidence)
        sizing_confidence = min(confidence_value, 80.0)
        if entry_value <= 0:
            return {
                "quantity": 0.0,
                "allocation_pct": 0.0,
                "allocated_notional": 0.0,
                "available_balance": 0.0,
                "confidence": confidence_value,
                "sizing_confidence": sizing_confidence,
            }
        with session_scope() as session:
            balance = _round_money(self._get_paper_account(session, profile_id=profile_id)["balance"])
            sizing = self._paper_position_sizing(session, profile_id=profile_id)
        available_for_notional = max(0.0, balance - fixed_fee)
        if available_for_notional <= 0:
            return {
                "quantity": 0.0,
                "allocation_pct": 0.0,
                "allocated_notional": 0.0,
                "available_balance": balance,
                "confidence": confidence_value,
                "sizing_confidence": sizing_confidence,
                **sizing,
            }
        safe_risk_adjustment = max(0.35, min(1.0, _as_float(risk_adjustment_factor, 1.0)))
        allocation_pct = self._confidence_allocation_pct(sizing_confidence, sizing) * safe_risk_adjustment
        target_notional = _round_money(available_for_notional * (allocation_pct / 100.0))
        quantity = target_notional / entry_value if entry_value else 0.0
        if requested_quantity is not None:
            requested_cap = max(_as_float(requested_quantity), 0.0)
            if requested_cap > 0:
                quantity = min(quantity, requested_cap)
        quantity = round(max(0.0, quantity), 8)
        return {
            "quantity": quantity,
            "allocation_pct": round(allocation_pct, 4),
            "allocated_notional": _round_money(quantity * entry_value),
            "available_balance": balance,
            "confidence": confidence_value,
            "sizing_confidence": sizing_confidence,
            "risk_adjustment_factor": round(safe_risk_adjustment, 4),
            "stop_distance_atr": round(_as_float(stop_distance_atr), 4) if stop_distance_atr is not None else None,
            "stop_width_normalized": bool(stop_distance_atr is not None and _as_float(stop_distance_atr) > 1.5 and safe_risk_adjustment < 1.0),
            **sizing,
        }

    def deposit_paper_balance(self, amount: float, *, profile_id: str = PAPER_PROFILE_ID) -> dict:
        delta = _round_money(_as_float(amount))
        if delta <= 0:
            raise ValueError("Deposit amount must be positive")
        with session_scope() as session:
            account = self.paper_repo.update_balance(
                session,
                delta,
                initial_balance=self._default_paper_balance(session, profile_id=profile_id),
                profile_id=profile_id,
            )
            portfolio = self.refresh_portfolio_snapshot(session=session, profile_id=profile_id)
        return {"account": account, "balance": account["balance"], "portfolio": portfolio}

    def reconcile_legacy_open_orders(self, *, profile_id: str = PAPER_PROFILE_ID) -> dict:
        with session_scope() as session:
            account = self._get_paper_account(session, profile_id=profile_id)
            starting_balance = _round_money(_as_float(account.get("balance")))
            open_orders = [self._hydrate_order(session, row) for row in self.order_repo.list_orders(session, status="OPEN", limit=5000, profile_id=profile_id)]
            reconciled_orders: list[dict] = []
            already_reconciled = 0
            total_reserved_cost = 0.0

            for order in open_orders:
                payload = dict(order.get("payload") or {})
                if _as_float(payload.get("reserved_cost")) > 0:
                    already_reconciled += 1
                    continue

                quantity = max(_as_float(payload.get("quantity"), 1.0), 0.0)
                entry = _as_float(order.get("entry"))
                opening_fee = _round_money(_as_float(payload.get("fees"), 0.0))
                entry_notional = _round_money(entry * quantity)
                reserved_cost = _round_money(entry_notional + opening_fee)

                payload.update(
                    {
                        "entry_notional": entry_notional,
                        "reserved_cost": reserved_cost,
                        "budget_reconciled_at_utc": utc_now_iso(),
                    }
                )
                self.order_repo.save_order(
                    session,
                    {
                        "order_id": order["order_id"],
                        "profile_id": str(order.get("profile_id") or profile_id),
                        "signal_id": order.get("signal_id"),
                        "source": str(order.get("source") or "PAPER"),
                        "symbol": str(order.get("symbol") or ""),
                        "interval": str(order.get("interval") or ""),
                        "mode": str(order.get("mode") or ""),
                        "direction": str(order.get("direction") or "BUY"),
                        "status": str(order.get("status") or "OPEN"),
                        "entry": entry,
                        "stop_loss": order.get("stop_loss"),
                        "take_profit": order.get("take_profit"),
                        "close_price": order.get("close_price"),
                        "risk_reward": order.get("risk_reward"),
                        "confidence": _as_float(order.get("confidence")),
                        "opened_at_utc": str(order.get("open_timestamp") or order.get("opened_at_utc") or utc_now_iso()),
                        "closed_at_utc": order.get("close_timestamp") or order.get("closed_at_utc"),
                        "payload_json": dumps_json(payload),
                    },
                )
                total_reserved_cost = _round_money(total_reserved_cost + reserved_cost)
                reconciled_orders.append(
                    {
                        "order_id": order["order_id"],
                        "symbol": order.get("symbol"),
                        "entry_notional": entry_notional,
                        "reserved_cost": reserved_cost,
                    }
                )

            if total_reserved_cost > 0:
                account = self.paper_repo.update_balance(session, -total_reserved_cost, initial_balance=self._default_paper_balance(session, profile_id=profile_id), profile_id=profile_id)
            ending_balance = _round_money(_as_float(account.get("balance")))
            portfolio = self.refresh_portfolio_snapshot(session=session, profile_id=profile_id)

        deficit = _round_money(abs(min(ending_balance, 0.0)))
        return {
            "account": account,
            "balance": ending_balance,
            "portfolio": portfolio,
            "reconciliation": {
                "reconciled_orders": len(reconciled_orders),
                "already_reconciled": already_reconciled,
                "total_open_orders": len(open_orders),
                "starting_balance": starting_balance,
                "ending_balance": ending_balance,
                "total_reserved_cost": _round_money(total_reserved_cost),
                "deficit": deficit,
                "orders": reconciled_orders,
            },
        }

    def reset_paper_balance(self, balance: float | None = None, *, profile_id: str = PAPER_PROFILE_ID) -> dict:
        with session_scope() as session:
            open_orders = self.order_repo.list_orders(session, status="OPEN", limit=10, profile_id=profile_id)
            if open_orders:
                raise InsufficientFundsError("Cannot reset paper balance while open paper orders exist")
            target_balance = _round_money(_as_float(balance, self._default_paper_balance(session, profile_id=profile_id)))
            account = self.paper_repo.set_balance(session, target_balance, profile_id=profile_id)
            portfolio = self.refresh_portfolio_snapshot(session=session, profile_id=profile_id)
        return {"account": account, "balance": account["balance"], "portfolio": portfolio}

    def get_portfolio_payload(self, *, profile_id: str = PAPER_PROFILE_ID) -> dict:
        with session_scope() as session:
            latest = self.portfolio_repo.get_latest_snapshot(session, profile_id=profile_id)
            if latest is None:
                latest = self.refresh_portfolio_snapshot(session=session, profile_id=profile_id)
            history = self.portfolio_repo.list_snapshots(session, limit=250, profile_id=profile_id)
            open_positions = self.order_repo.list_positions(session, status="OPEN", limit=250, profile_id=profile_id)
            paper_account = self._get_paper_account(session, profile_id=profile_id)
            default_balance = self._default_paper_balance(session, profile_id=profile_id)
            closed_orders = [
                self._hydrate_order(session, row)
                for row in self.order_repo.list_orders(session, limit=1000, profile_id=profile_id)
                if str(row.get("status") or "").upper() != "OPEN"
            ]
        closed_orders.sort(key=lambda row: str(row.get("close_timestamp") or row.get("open_timestamp") or ""), reverse=True)
        open_rows = [self._portfolio_open_position_row(item) for item in open_positions]
        daily = self._build_daily(closed_orders)
        equity_curve = self._build_equity_curve(history)
        summary = self._build_summary(latest, closed_orders, history=history, default_balance=default_balance, open_orders=open_rows)
        return {
            "generated_at": utc_now_iso(),
            "profile_id": profile_id,
            "summary": summary,
            "portfolio": latest or self._empty_portfolio(),
            "paper_account": {
                **paper_account,
                "default_balance": default_balance,
                **self._paper_account_identity(paper_account, profile_id=profile_id),
            },
            "avg_hold_minutes": self._average_hold_minutes(closed_orders),
            "daily": daily,
            "recent_closed": closed_orders[:100],
            "open_positions": open_rows,
            "engine": {"status": "healthy"},
            "equity_curve": equity_curve,
        }

    def close_all_open_orders(
        self,
        *,
        close_reason: str = "MANUAL_BULK_CLOSE",
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict:
        closed_items: list[dict] = []
        errors: list[dict[str, str]] = []
        with session_scope() as session:
            open_orders = [
                self._hydrate_order(session, row)
                for row in self.order_repo.list_orders(session, status="OPEN", limit=5000, profile_id=profile_id)
            ]
        for order in open_orders:
            order_id = str(order.get("order_id") or "")
            if not order_id:
                continue
            close_price = _valid_market_price(order.get("last_price")) or _valid_market_price(order.get("entry"))
            if close_price is None:
                errors.append({"order_id": order_id, "error": "No valid close price available."})
                continue
            try:
                result = self.close_order(order_id, close_price=close_price, close_reason=close_reason)
                closed_items.append(result.get("order") or {})
            except ValueError as exc:
                errors.append({"order_id": order_id, "error": str(exc)})
        portfolio = self.get_portfolio_payload(profile_id=profile_id)
        return {
            "closed_count": len(closed_items),
            "errors": errors,
            "orders": closed_items,
            "portfolio": portfolio,
        }

    def refresh_portfolio_snapshot(self, *, session=None, profile_id: str = PAPER_PROFILE_ID) -> dict:
        if session is None:
            with session_scope() as local_session:
                return self.refresh_portfolio_snapshot(session=local_session, profile_id=profile_id)

        orders = self.order_repo.list_orders(session, limit=5000, profile_id=profile_id)
        positions = self.order_repo.list_positions(session, status="OPEN", limit=1000, profile_id=profile_id)
        open_orders = [item for item in orders if str(item.get("status") or "").upper() == "OPEN"]
        closed_orders = [self._hydrate_order(session, item) for item in orders if str(item.get("status") or "").upper() != "OPEN"]

        realized_pnl = sum(_as_float(item.get("realized_pnl")) for item in closed_orders)
        unrealized_pnl = sum(_as_float(item.get("unrealized_pnl")) for item in positions)
        paper_account = self._get_paper_account(session, profile_id=profile_id)
        cash_balance = _round_money(paper_account["balance"])
        invested_capital = _round_money(sum(_as_float(item.get("quantity")) * _as_float(item.get("average_entry")) for item in positions))
        total_equity = _round_money(cash_balance + invested_capital + unrealized_pnl)
        routing_key = next(
            (
                item.get("execution_routing_key")
                for item in (open_orders + closed_orders + positions)
                if item.get("execution_routing_key")
            ),
            f"{profile_id}:INTERNAL_PAPER:{paper_account.get('account_id')}",
        )
        snapshot_json = {
            "net_r": _round_money(sum(_as_float(item.get("realized_r")) for item in closed_orders)),
            "open_order_ids": [item.get("order_id") for item in open_orders],
            "open_position_ids": [item.get("position_id") for item in positions],
            "invested_capital": invested_capital,
            "paper_balance": cash_balance,
            "execution_account_id": paper_account.get("account_id"),
            "execution_routing_key": routing_key,
            "execution_target_route_key": f"{profile_id}:PAPER:INTERNAL_PAPER",
        }
        return self.portfolio_repo.save_snapshot(
            session,
            {
                "snapshot_id": f"snap-{uuid4().hex[:16]}",
                "profile_id": profile_id,
                "total_equity": total_equity,
                "cash_balance": cash_balance,
                "unrealized_pnl": _round_money(unrealized_pnl),
                "realized_pnl": _round_money(realized_pnl),
                "open_positions": len(positions),
                "closed_trades": len(closed_orders),
                "snapshot_json": dumps_json(snapshot_json),
                "created_at_utc": utc_now_iso(),
            },
        )

    def _hydrate_order(self, session, order: dict) -> dict:
        payload = dict(order.get("payload") or {})
        fills = self.order_repo.list_fills(session, order["order_id"], limit=100, profile_id=str(order.get("profile_id") or PAPER_PROFILE_ID))
        artifact_identity = self._artifact_identity(payload, profile_id=str(order.get("profile_id") or PAPER_PROFILE_ID))
        enriched_fills = [{**fill, **artifact_identity} for fill in fills]
        timing_estimate = dict(payload.get("timing_estimate") or {})
        timing_progress = self._calc_timing_progress(order)
        progress = self._calc_progress(order.get("direction"), order.get("entry"), order.get("stop_loss"), order.get("take_profit"), payload.get("last_price"))
        side = self._position_side(order.get("direction"))
        enriched = dict(order)
        enriched.update(
            {
                "state": order.get("status"),
                "open_timestamp": order.get("opened_at_utc"),
                "close_timestamp": order.get("closed_at_utc"),
                "sl": order.get("stop_loss"),
                "tp": order.get("take_profit"),
                "quantity": _as_float(payload.get("quantity"), 1.0),
                "fees": _as_float(payload.get("fees"), 0.0),
                "realized_pnl": payload.get("realized_pnl"),
                "realized_r": payload.get("realized_r"),
                "close_reason": payload.get("close_reason"),
                "last_price": payload.get("last_price"),
                "signal_payload": payload.get("signal") or {},
                "position_id": payload.get("position_id"),
                "unrealized_r": self._current_r(order) if str(order.get("status") or "").upper() == "OPEN" else None,
                "expected_r": self._current_r(order) if str(order.get("status") or "").upper() == "OPEN" else payload.get("realized_r"),
                "timing_estimate": timing_estimate,
                "estimated_duration": self._format_expected_duration(timing_estimate),
                "position_side": side,
                "holding_minutes": self._holding_minutes(order),
                "progress": progress,
                "timing_progress": timing_progress,
                "timing_status": self._timing_status(order, timing_progress),
                "fills": enriched_fills,
                **artifact_identity,
            }
        )
        return enriched

    @staticmethod
    def _realized_pnl(*, direction: str, entry: float, exit_price: float, quantity: float) -> float:
        multiplier = 1.0 if direction.upper() == "BUY" else -1.0
        return _round_money((exit_price - entry) * quantity * multiplier)

    @staticmethod
    def _realized_r(*, direction: str, entry: float, stop_loss, exit_price: float) -> float | None:
        if stop_loss is None:
            return None
        risk = abs(entry - _as_float(stop_loss))
        if risk <= 0:
            return None
        pnl_per_unit = (exit_price - entry) if direction.upper() == "BUY" else (entry - exit_price)
        return pnl_per_unit / risk

    @staticmethod
    def _average_hold_minutes(rows: list[dict]) -> float:
        values: list[float] = []
        for row in rows:
            opened = PaperExecutionService._parse_time(row.get("open_timestamp"))
            closed = PaperExecutionService._parse_time(row.get("close_timestamp"))
            if not opened or not closed:
                continue
            values.append(max(0.0, (closed - opened).total_seconds() / 60.0))
        if not values:
            return 0.0
        return round(sum(values) / len(values), 2)

    @staticmethod
    def _parse_time(value) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _calc_progress(direction, entry, stop_loss, take_profit, last_price):
        entry_value = _as_float(entry)
        stop_value = _as_float(stop_loss)
        take_value = _as_float(take_profit)
        price_value = _as_float(last_price)
        if not all(value is not None for value in (entry_value, stop_value, take_value, price_value)):
            return None
        if str(direction).upper() == "BUY":
            total_range = take_value - stop_value
            current_pos = price_value - stop_value
            pnl_pct = ((price_value - entry_value) / entry_value * 100.0) if entry_value else 0.0
            side = "tp" if price_value >= entry_value else "sl"
        else:
            total_range = stop_value - take_value
            current_pos = stop_value - price_value
            pnl_pct = ((entry_value - price_value) / entry_value * 100.0) if entry_value else 0.0
            side = "tp" if price_value <= entry_value else "sl"
        if not total_range:
            return None
        pct = max(0.0, min(100.0, current_pos / total_range * 100.0))
        return {"pct": round(pct, 2), "side": side, "pnl_pct": round(pnl_pct, 4)}

    @staticmethod
    def _calc_timing_progress(order: dict):
        opened = PaperExecutionService._parse_time(order.get("open_timestamp") or order.get("opened_at_utc"))
        if opened is None:
            return None
        closed = PaperExecutionService._parse_time(order.get("close_timestamp") or order.get("closed_at_utc")) or datetime.now(timezone.utc)
        payload = dict(order.get("payload") or {})
        expected_target = _as_float(payload.get("expected_candles_target"))
        expected_max = _as_float(payload.get("expected_candles_max"))
        if not expected_target:
            return None
        interval_minutes = int(_as_float(payload.get("interval_minutes"), _interval_to_minutes(str(order.get("interval") or "1h"))))
        elapsed_minutes = max(0.0, (closed - opened).total_seconds() / 60.0)
        elapsed_candles = round(elapsed_minutes / max(interval_minutes, 1), 2)
        pct = min(100.0, (elapsed_candles / expected_target) * 100.0)
        return {
            "elapsed_candles": elapsed_candles,
            "expected_candles": expected_target,
            "expected_max_candles": expected_max,
            "pct": round(pct, 2),
            "overdue": bool(expected_max and elapsed_candles > expected_max),
            "timing_accuracy": "ON_TIME" if expected_max and elapsed_candles <= expected_max else "OVERDUE" if expected_max and elapsed_candles > expected_max else "UNKNOWN",
        }

    @staticmethod
    def _position_side(direction: object) -> str:
        return "LONG" if str(direction or "").upper() == "BUY" else "SHORT" if str(direction or "").upper() == "SELL" else "--"

    @staticmethod
    def _holding_minutes(order: dict) -> float:
        opened = PaperExecutionService._parse_time(order.get("open_timestamp") or order.get("opened_at_utc"))
        closed = PaperExecutionService._parse_time(order.get("close_timestamp") or order.get("closed_at_utc")) or datetime.now(timezone.utc)
        if opened is None:
            return 0.0
        return round(max(0.0, (closed - opened).total_seconds() / 60.0), 2)

    @staticmethod
    def _format_expected_duration(timing_estimate: dict) -> str | None:
        candles_min = _as_float(timing_estimate.get("candles_min"))
        candles_max = _as_float(timing_estimate.get("candles_max"))
        minutes_target = _as_float(timing_estimate.get("minutes_target"))
        if not candles_min and not candles_max and not minutes_target:
            return None

        def fmt_minutes(total_minutes: float) -> str:
            if total_minutes <= 0:
                return "--"
            if total_minutes < 60:
                return f"{round(total_minutes)}m"
            if total_minutes < 1440:
                hours = total_minutes / 60.0
                return f"{hours:.1f}h" if hours % 1 else f"{int(hours)}h"
            days = total_minutes / 1440.0
            return f"{days:.1f}d" if days % 1 else f"{int(days)}d"

        candle_part = None
        if candles_min and candles_max:
            candle_part = f"{int(candles_min)}-{int(candles_max)} candles"
        elif candles_max:
            candle_part = f"up to {int(candles_max)} candles"
        elif candles_min:
            candle_part = f"{int(candles_min)} candles"

        minute_part = fmt_minutes(minutes_target) if minutes_target else None
        if candle_part and minute_part:
            return f"{candle_part} (~{minute_part})"
        return candle_part or minute_part

    @staticmethod
    def _timing_status(order: dict, timing_progress: dict | None) -> str:
        if str(order.get("status") or "").upper() != "OPEN":
            return "CLOSED"
        if not timing_progress:
            return "UNSPECIFIED"
        if timing_progress.get("overdue"):
            return "OVERDUE"
        pct = _as_float(timing_progress.get("pct"))
        if pct >= 100.0:
            return "DUE"
        return "TRACKING"

    @staticmethod
    def _should_time_stop(order: dict) -> bool:
        progress = PaperExecutionService._calc_timing_progress(order)
        if not progress:
            return False
        payload = dict(order.get("payload") or {})
        time_stop_candles = _as_float(payload.get("time_stop_candles"))
        if time_stop_candles and progress["elapsed_candles"] >= time_stop_candles:
            return True
        expected_max = _as_float(payload.get("expected_candles_max"))
        return bool(expected_max and progress["elapsed_candles"] >= expected_max)

    @staticmethod
    def _current_r(order: dict) -> float | None:
        payload = dict(order.get("payload") or {})
        last_price = _valid_market_price(payload.get("last_price"))
        if last_price is None:
            return None
        return PaperExecutionService._realized_r(
            direction=str(order.get("direction") or "BUY"),
            entry=_as_float(order.get("entry")),
            stop_loss=order.get("stop_loss"),
            exit_price=last_price,
        )

    @staticmethod
    def _directional_progress_pct(order: dict) -> float | None:
        payload = dict(order.get("payload") or {})
        direction = str(order.get("direction") or "BUY").upper()
        entry = _as_float(order.get("entry"))
        take_profit = _as_float(order.get("take_profit"))
        last_price = _valid_market_price(payload.get("last_price"))
        if entry is None or take_profit is None or last_price is None:
            return None
        if direction == "BUY":
            target_distance = take_profit - entry
            if target_distance <= 0:
                return None
            progressed = max(0.0, last_price - entry)
        else:
            target_distance = entry - take_profit
            if target_distance <= 0:
                return None
            progressed = max(0.0, entry - last_price)
        return round(min(100.0, (progressed / target_distance) * 100.0), 4)

    @staticmethod
    def _stale_exit_reason(order: dict) -> str | None:
        progress = PaperExecutionService._calc_timing_progress(order)
        if not progress:
            return None
        payload = dict(order.get("payload") or {})
        stale_exit_candles = _as_float(payload.get("stale_exit_candles"))
        if not stale_exit_candles or progress["elapsed_candles"] < stale_exit_candles:
            return None
        progress_pct = PaperExecutionService._directional_progress_pct(order)
        current_r = PaperExecutionService._current_r(order)
        max_abs_r = _as_float(payload.get("stale_exit_max_abs_r"), 0.2)
        min_progress_pct = _as_float(payload.get("stale_exit_min_progress_pct"), 15.0)
        if progress_pct is None or current_r is None:
            return None
        if progress_pct < min_progress_pct and abs(current_r) <= max_abs_r:
            return "EARLY_STALE_EXIT"
        return None

    def _update_open_order_mark(self, order_id: str, last_price: float) -> dict:
        normalized_price = _valid_market_price(last_price)
        if normalized_price is None:
            raise ValueError(f"Invalid market price for {order_id}: {last_price!r}")
        with session_scope() as session:
            order = self.order_repo.get_order(session, order_id)
            if order is None:
                raise ValueError(f"Order not found: {order_id}")
            payload = dict(order.get("payload") or {})
            payload["last_price"] = _round_money(normalized_price)
            saved_order = self.order_repo.save_order(
                session,
                {
                    "order_id": order["order_id"],
                    "profile_id": str(order.get("profile_id") or PAPER_PROFILE_ID),
                    "signal_id": order.get("signal_id"),
                    "source": str(order.get("source") or "PAPER"),
                    "symbol": str(order.get("symbol") or ""),
                    "interval": str(order.get("interval") or ""),
                    "mode": str(order.get("mode") or ""),
                    "direction": str(order.get("direction") or "BUY"),
                    "status": str(order.get("status") or "OPEN"),
                    "entry": _as_float(order.get("entry")),
                    "stop_loss": order.get("stop_loss"),
                    "take_profit": order.get("take_profit"),
                    "close_price": order.get("close_price"),
                    "risk_reward": order.get("risk_reward"),
                    "confidence": _as_float(order.get("confidence")),
                    "opened_at_utc": str(order.get("open_timestamp") or order.get("opened_at_utc") or utc_now_iso()),
                    "closed_at_utc": order.get("close_timestamp") or order.get("closed_at_utc"),
                    "payload_json": dumps_json(payload),
                },
            )
            position_id = str(payload.get("position_id") or "")
            if position_id:
                current_position = next(
                    (
                        item
                        for item in self.order_repo.list_positions(
                            session,
                            limit=500,
                            profile_id=str(saved_order.get("profile_id") or PAPER_PROFILE_ID),
                        )
                        if str(item.get("position_id")) == position_id
                    ),
                    None,
                )
                if current_position:
                    direction = str(current_position.get("direction") or saved_order.get("direction") or "BUY")
                    quantity = _as_float(current_position.get("quantity"), 1.0)
                    average_entry = _as_float(current_position.get("average_entry"), _as_float(saved_order.get("entry")))
                    multiplier = 1.0 if direction.upper() == "BUY" else -1.0
                    unrealized_pnl = _round_money((normalized_price - average_entry) * quantity * multiplier)
                    self.order_repo.save_position(
                        session,
                        {
                            "position_id": position_id,
                            "profile_id": str(saved_order.get("profile_id") or PAPER_PROFILE_ID),
                            "symbol": str(current_position.get("symbol") or saved_order["symbol"]),
                            "interval": str(current_position.get("interval") or saved_order["interval"]),
                            "mode": str(current_position.get("mode") or saved_order["mode"]),
                            "direction": direction,
                            "quantity": quantity,
                            "average_entry": average_entry,
                            "mark_price": _round_money(normalized_price),
                            "unrealized_pnl": unrealized_pnl,
                            "status": "OPEN",
                            "opened_at_utc": str(current_position.get("open_timestamp") or current_position.get("opened_at_utc") or saved_order["open_timestamp"]),
                            "closed_at_utc": None,
                            "payload_json": dumps_json(dict(current_position.get("payload") or {})),
                        },
                    )
            self.refresh_portfolio_snapshot(session=session, profile_id=str(saved_order.get("profile_id") or PAPER_PROFILE_ID))
            return self._hydrate_order(session, saved_order)

    @staticmethod
    def _close_reason(order: dict) -> str | None:
        price = _valid_market_price(order.get("last_price"))
        stop_loss = _as_float(order.get("stop_loss"))
        take_profit = _as_float(order.get("take_profit"))
        if price is None or stop_loss is None or take_profit is None:
            return None
        direction = str(order.get("direction") or "BUY").upper()
        if direction == "BUY":
            if price >= take_profit:
                return "HIT_TP"
            if price <= stop_loss:
                return "HIT_SL"
        else:
            if price <= take_profit:
                return "HIT_TP"
            if price >= stop_loss:
                return "HIT_SL"
        return None

    @staticmethod
    def _resolve_close_price(order: dict, *, close_price: float, close_reason: str) -> float | None:
        reason = str(close_reason or "").upper()
        if reason == "HIT_SL":
            return _valid_market_price(order.get("stop_loss"))
        if reason == "HIT_TP":
            return _valid_market_price(order.get("take_profit"))
        return _valid_market_price(close_price)

    @staticmethod
    def _build_daily(rows: list[dict]) -> list[dict]:
        buckets: dict[str, dict] = {}
        ordered = sorted(rows, key=lambda item: str(item.get("close_timestamp") or item.get("open_timestamp") or ""))
        for row in ordered:
            stamp = PaperExecutionService._parse_time(row.get("close_timestamp") or row.get("open_timestamp"))
            if stamp is None:
                continue
            day = stamp.date().isoformat()
            bucket = buckets.setdefault(day, {"date": day, "trades": 0, "wins": 0, "losses": 0, "net_r": 0.0})
            bucket["trades"] += 1
            realized_r = _as_float(row.get("realized_r"), 0.0)
            bucket["net_r"] = _round_money(bucket["net_r"] + realized_r)
            if realized_r > 0:
                bucket["wins"] += 1
            elif realized_r < 0:
                bucket["losses"] += 1
        result = []
        for day in sorted(buckets):
            bucket = buckets[day]
            trades = bucket["trades"]
            bucket["win_rate"] = round((bucket["wins"] / trades * 100.0) if trades else 0.0, 2)
            result.append(bucket)
        return result[-60:]

    @staticmethod
    def _build_equity_curve(history: list[dict]) -> list[dict]:
        rows = []
        for item in reversed(history):
            snapshot = dict(item.get("snapshot") or {})
            rows.append(
                {
                    "time": item.get("created_at_utc"),
                    "timestamp": item.get("created_at_utc"),
                    "equity": item.get("total_equity", 0.0),
                    "net_r": snapshot.get("net_r", item.get("realized_pnl", 0.0)),
                }
            )
        return rows

    @staticmethod
    def _build_summary(
        latest: dict | None,
        closed_orders: list[dict],
        *,
        history: list[dict] | None = None,
        default_balance: float = 100.0,
        open_orders: list[dict] | None = None,
    ) -> dict:
        gross_profit = sum(max(_as_float(item.get("realized_r"), 0.0), 0.0) for item in closed_orders)
        gross_loss = sum(abs(min(_as_float(item.get("realized_r"), 0.0), 0.0)) for item in closed_orders)
        wins = sum(1 for item in closed_orders if _as_float(item.get("realized_r"), 0.0) > 0)
        total = len(closed_orders)
        snapshot = dict((latest or {}).get("snapshot") or {})
        performance_windows = PaperExecutionService._build_performance_windows(
            history or [],
            closed_orders,
            latest,
            default_balance=default_balance,
        )
        open_analysis = PaperExecutionService._open_trade_analysis(open_orders or [])
        return {
            "total_equity": (latest or {}).get("total_equity", 0.0),
            "cash_balance": (latest or {}).get("cash_balance", 0.0),
            "paper_balance": snapshot.get("paper_balance", (latest or {}).get("cash_balance", 0.0)),
            "invested_capital": snapshot.get("invested_capital", 0.0),
            "unrealized_pnl": (latest or {}).get("unrealized_pnl", 0.0),
            "realized_pnl": (latest or {}).get("realized_pnl", 0.0),
            "open_positions": (latest or {}).get("open_positions", 0),
            "closed_trades": (latest or {}).get("closed_trades", 0),
            "total_trades": total,
            "win_rate": round((wins / total * 100.0) if total else 0.0, 2),
            "profit_factor": round((gross_profit / gross_loss) if gross_loss else (gross_profit if gross_profit else 0.0), 4),
            "net_r": snapshot.get("net_r", sum(_as_float(item.get("realized_r"), 0.0) for item in closed_orders)),
            "open_expected_r": open_analysis["open_expected_r"],
            "expected_net_r": round(_as_float(snapshot.get("net_r", sum(_as_float(item.get("realized_r"), 0.0) for item in closed_orders))) + _as_float(open_analysis["open_expected_r"]), 4),
            "open_trade_analysis": open_analysis,
            "today_pnl": performance_windows["today"]["equity_change"],
            "today_pnl_pct": performance_windows["today"]["equity_change_pct"],
            "three_day_pnl": performance_windows["three_day"]["equity_change"],
            "three_day_pnl_pct": performance_windows["three_day"]["equity_change_pct"],
            "performance_windows": performance_windows,
        }

    @staticmethod
    def _build_performance_windows(
        history: list[dict],
        closed_orders: list[dict],
        latest: dict | None = None,
        *,
        default_balance: float = 100.0,
    ) -> dict:
        now = datetime.now(timezone.utc)
        latest_equity = _round_money(_as_float((latest or {}).get("total_equity"), default_balance))
        ordered_history = sorted(
            [
                {
                    **item,
                    "_timestamp": PaperExecutionService._parse_time(item.get("created_at_utc")),
                    "_equity": _as_float(item.get("total_equity"), default_balance),
                }
                for item in history
            ],
            key=lambda item: item["_timestamp"] or datetime.min.replace(tzinfo=timezone.utc),
        )

        def baseline_equity(cutoff: datetime) -> float:
            baseline = default_balance
            for item in ordered_history:
                timestamp = item["_timestamp"]
                if timestamp is None:
                    continue
                if timestamp <= cutoff:
                    baseline = item["_equity"]
                else:
                    break
            return _round_money(baseline)

        def realized_since(cutoff: datetime) -> tuple[float, int]:
            realized = 0.0
            count = 0
            for order in closed_orders:
                timestamp = PaperExecutionService._parse_time(order.get("close_timestamp") or order.get("open_timestamp"))
                if timestamp is None or timestamp < cutoff:
                    continue
                realized = _round_money(realized + _as_float(order.get("realized_pnl")))
                count += 1
            return realized, count

        windows = {
            "today": datetime.combine(now.date(), time.min, tzinfo=timezone.utc),
            "three_day": now - timedelta(days=3),
        }
        result: dict[str, dict] = {}
        for label, cutoff in windows.items():
            start_equity = baseline_equity(cutoff)
            equity_change = _round_money(latest_equity - start_equity)
            realized_pnl, closed_count = realized_since(cutoff)
            equity_change_pct = round((equity_change / start_equity * 100.0), 4) if start_equity else 0.0
            result[label] = {
                "start_at_utc": cutoff.isoformat(),
                "start_equity": start_equity,
                "current_equity": latest_equity,
                "equity_change": equity_change,
                "equity_change_pct": equity_change_pct,
                "realized_pnl": realized_pnl,
                "closed_trades": closed_count,
            }
        return result

    def _default_paper_balance(self, session, *, profile_id: str = PAPER_PROFILE_ID) -> float:
        env_default = _as_float(os.getenv("V4_PAPER_STARTING_CASH"), 100.0)
        value = self.settings_repo.get_value(session, "PAPER_DEFAULT_BALANCE", str(env_default), profile_id=profile_id)
        return _round_money(_as_float(value, env_default))

    def _paper_position_sizing(self, session, *, profile_id: str = PAPER_PROFILE_ID) -> dict:
        min_pct = max(0.0, _as_float(self.settings_repo.get_value(session, "PAPER_POSITION_SIZE_MIN_PCT", "2", profile_id=profile_id), 2.0))
        max_pct = max(min_pct, _as_float(self.settings_repo.get_value(session, "PAPER_POSITION_SIZE_MAX_PCT", "12", profile_id=profile_id), 12.0))
        confidence_floor = _as_float(self.settings_repo.get_value(session, "PAPER_POSITION_CONFIDENCE_FLOOR", "60", profile_id=profile_id), 60.0)
        confidence_ceil = max(confidence_floor, _as_float(self.settings_repo.get_value(session, "PAPER_POSITION_CONFIDENCE_CEIL", "90", profile_id=profile_id), 90.0))
        return {
            "min_pct": min_pct,
            "max_pct": max_pct,
            "confidence_floor": confidence_floor,
            "confidence_ceil": confidence_ceil,
        }

    @staticmethod
    def _confidence_allocation_pct(confidence: float, sizing: dict) -> float:
        min_pct = _as_float(sizing.get("min_pct"), 2.0)
        max_pct = max(min_pct, _as_float(sizing.get("max_pct"), 12.0))
        confidence_floor = _as_float(sizing.get("confidence_floor"), 60.0)
        confidence_ceil = max(confidence_floor, _as_float(sizing.get("confidence_ceil"), 90.0))
        if confidence_ceil <= confidence_floor:
            return max_pct if confidence >= confidence_ceil else min_pct
        normalized = max(0.0, min(1.0, (confidence - confidence_floor) / (confidence_ceil - confidence_floor)))
        return min_pct + (max_pct - min_pct) * normalized

    def _get_paper_account(self, session, *, profile_id: str = PAPER_PROFILE_ID) -> dict:
        default_balance = self._default_paper_balance(session, profile_id=profile_id)
        account = self.paper_repo.get_or_create_account(session, initial_balance=default_balance, profile_id=profile_id)
        existing_orders = self.order_repo.list_orders(session, limit=1, profile_id=profile_id)
        is_pristine_seed = (
            str(account.get("created_at_utc") or "")
            and str(account.get("created_at_utc") or "") == str(account.get("updated_at_utc") or "")
            and str(account.get("updated_at_utc") or "") == str(account.get("as_of_utc") or "")
        )
        if is_pristine_seed and not existing_orders and abs(_as_float(account.get("balance")) - default_balance) > 1e-9:
            account = self.paper_repo.set_balance(session, default_balance, profile_id=profile_id)
        return account

    def _allow_unfunded_trades(self, session, *, profile_id: str = PAPER_PROFILE_ID) -> bool:
        value = self.settings_repo.get_value(session, "PAPER_ALLOW_UNFUNDED_TRADES", "true", profile_id=profile_id)
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

    def _require_paper_balance(self, session, *, required: float, profile_id: str = PAPER_PROFILE_ID) -> dict:
        account = self._get_paper_account(session, profile_id=profile_id)
        balance = _round_money(_as_float(account.get("balance")))
        needed = _round_money(_as_float(required))
        if needed > balance:
            raise InsufficientFundsError(
                f"Insufficient paper balance. Required {needed:.2f}, available {balance:.2f}."
            )
        return account

    @staticmethod
    def _portfolio_open_position_row(position: dict) -> dict:
        payload = dict(position.get("payload") or {})
        artifact_identity = PaperExecutionService._artifact_identity(payload, profile_id=str(position.get("profile_id") or PAPER_PROFILE_ID))
        current_r = PaperExecutionService._position_unrealized_r(position)
        progress = PaperExecutionService._calc_progress(
            position.get("direction"),
            position.get("average_entry"),
            payload.get("stop_loss"),
            payload.get("take_profit"),
            position.get("mark_price"),
        )
        return {
            "position_id": position.get("position_id"),
            "symbol": position.get("symbol"),
            "direction": position.get("direction"),
            "source": payload.get("source", "PAPER"),
            "entry": position.get("average_entry"),
            "sl": payload.get("stop_loss"),
            "tp": payload.get("take_profit"),
            "confidence": payload.get("confidence"),
            "open_timestamp": position.get("opened_at_utc"),
            "quantity": position.get("quantity"),
            "mark_price": position.get("mark_price"),
            "unrealized_pnl": position.get("unrealized_pnl"),
            "unrealized_r": current_r,
            "expected_r": current_r,
            "progress": progress,
            "status": position.get("status"),
            "interval": position.get("interval"),
            "mode": position.get("mode"),
            **artifact_identity,
        }

    @staticmethod
    def _position_unrealized_r(position: dict) -> float | None:
        payload = dict(position.get("payload") or {})
        return PaperExecutionService._realized_r(
            direction=str(position.get("direction") or "BUY"),
            entry=_as_float(position.get("average_entry")),
            stop_loss=payload.get("stop_loss"),
            exit_price=_as_float(position.get("mark_price")),
        )

    @staticmethod
    def _open_trade_analysis(open_rows: list[dict]) -> dict:
        open_expected_r = round(sum(_as_float(item.get("expected_r")) for item in open_rows), 4)
        unrealized_pnl = round(sum(_as_float(item.get("unrealized_pnl")) for item in open_rows), 4)
        avg_progress_pct = round(
            sum(_as_float((item.get("progress") or {}).get("pct")) for item in open_rows) / len(open_rows),
            2,
        ) if open_rows else 0.0
        near_target_count = sum(1 for item in open_rows if _as_float((item.get("progress") or {}).get("pct")) >= 75.0)
        adverse_count = sum(1 for item in open_rows if _as_float(item.get("expected_r")) < 0.0)
        return {
            "open_count": len(open_rows),
            "open_expected_r": open_expected_r,
            "unrealized_pnl": unrealized_pnl,
            "avg_progress_pct": avg_progress_pct,
            "near_target_count": near_target_count,
            "adverse_count": adverse_count,
        }

    @staticmethod
    def _empty_portfolio() -> dict:
        return {
            "total_equity": 0.0,
            "cash_balance": 0.0,
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "open_positions": 0,
            "closed_trades": 0,
            "snapshot": {"net_r": 0.0, "invested_capital": 0.0, "paper_balance": 0.0},
            "created_at_utc": None,
        }
