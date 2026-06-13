"""Profile-aware execution orchestration for the current paper-first runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from runtime.db.repos.execution_account_repo import ExecutionAccountRepository
from runtime.db.repos.order_repo import OrderRepository
from runtime.db.repos.paper_repo import PaperAccountRepository
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID, RuntimeProfileRepository
from runtime.db.session import session_scope
from runtime.runtime.paper_execution import PaperExecutionService
from runtime.services.binance_usdm_manual_live_service import BinanceUsdmManualLiveService
from runtime.services.runtime_profile_service import RuntimeProfileService

PAPER_EXECUTION_MODE = "PAPER"
PAPER_VENUE = "INTERNAL_PAPER"


class UnsupportedExecutionProfileError(ValueError):
    """Raised when a profile resolves to an adapter that is not implemented yet."""


class ExecutionPolicyViolationError(ValueError):
    """Raised when a profile exists but is not eligible for a requested execution action."""


READ_INTENT = "READ"
AUTO_INTENT = "AUTO"
MANUAL_INTENT = "MANUAL"
MANAGE_INTENT = "MANAGE"
BALANCE_INTENT = "BALANCE"
MONITOR_INTENT = "MONITOR"


@dataclass(frozen=True)
class ExecutionAccountRef:
    profile_id: str
    account_id: str | None
    account_key: str | None
    account_type: str | None
    venue_account_key: str | None
    balance_ccy: str | None
    available_balance: float | None
    equity: float | None
    margin_used: float | None
    execution_mode: str
    venue: str
    routing_key: str
    venue_scope: str
    is_primary: bool = True


@dataclass(frozen=True)
class ExecutionTarget:
    profile_id: str
    profile_name: str
    status: str
    runtime_mode: str
    execution_mode: str
    venue: str
    product_type: str
    venue_environment: str | None
    api_base_url: str | None
    default_for_auto_trading: bool
    manual_trading_enabled: bool
    auto_trading_enabled: bool
    read_only: bool
    supports_account_reads: bool
    supports_order_placement: bool
    credential_ref: str | None = None
    connectivity_status: str | None = None
    account: ExecutionAccountRef | None = None

    @property
    def route_key(self) -> str:
        return f"{self.profile_id}:{self.execution_mode}:{self.venue}"


class ExecutionAdapter(Protocol):
    adapter_key: str

    def open_order(self, signal: dict[str, Any], **kwargs) -> dict[str, Any]: ...
    def close_order(self, order_id: str, **kwargs) -> dict[str, Any]: ...
    def create_manual_order(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def update_manual_order(self, order_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    def delete_manual_order(self, order_id: str) -> bool: ...
    def monitor_open_orders(self, **kwargs) -> dict[str, Any]: ...
    def get_orders_snapshot(self, **kwargs) -> dict[str, Any]: ...
    def get_paper_balance_payload(self, **kwargs) -> dict[str, Any]: ...
    def compute_confidence_position_size(self, entry_price: float, **kwargs) -> dict[str, Any]: ...
    def deposit_paper_balance(self, amount: float, **kwargs) -> dict[str, Any]: ...
    def reconcile_legacy_open_orders(self, **kwargs) -> dict[str, Any]: ...
    def reset_paper_balance(self, balance: float | None = None, **kwargs) -> dict[str, Any]: ...
    def get_portfolio_payload(self, **kwargs) -> dict[str, Any]: ...
    def close_all_open_orders(self, **kwargs) -> dict[str, Any]: ...
    def query_order(self, order_id: str, **kwargs) -> dict[str, Any]: ...
    def verify_order(self, order_id: str, **kwargs) -> dict[str, Any]: ...
    def cancel_order(self, order_id: str, **kwargs) -> dict[str, Any]: ...


class PaperExecutionAdapter:
    """Paper adapter that preserves the existing paper execution implementation."""

    adapter_key = "paper"

    def __init__(self, execution_service: PaperExecutionService | None = None) -> None:
        self.execution_service = execution_service or PaperExecutionService()

    def open_order(self, signal: dict[str, Any], **kwargs) -> dict[str, Any]:
        return self.execution_service.open_order(signal, **kwargs)

    def close_order(self, order_id: str, **kwargs) -> dict[str, Any]:
        return self.execution_service.close_order(order_id, **kwargs)

    def create_manual_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.execution_service.create_manual_order(payload)

    def update_manual_order(self, order_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.execution_service.update_manual_order(order_id, payload)

    def delete_manual_order(self, order_id: str) -> bool:
        return self.execution_service.delete_manual_order(order_id)

    def monitor_open_orders(self, **kwargs) -> dict[str, Any]:
        return self.execution_service.monitor_open_orders(**kwargs)

    def get_orders_snapshot(self, **kwargs) -> dict[str, Any]:
        return self.execution_service.get_orders_snapshot(**kwargs)

    def get_paper_balance_payload(self, **kwargs) -> dict[str, Any]:
        return self.execution_service.get_paper_balance_payload(**kwargs)

    def compute_confidence_position_size(self, entry_price: float, **kwargs) -> dict[str, Any]:
        return self.execution_service.compute_confidence_position_size(entry_price, **kwargs)

    def deposit_paper_balance(self, amount: float, **kwargs) -> dict[str, Any]:
        return self.execution_service.deposit_paper_balance(amount, **kwargs)

    def reconcile_legacy_open_orders(self, **kwargs) -> dict[str, Any]:
        return self.execution_service.reconcile_legacy_open_orders(**kwargs)

    def reset_paper_balance(self, balance: float | None = None, **kwargs) -> dict[str, Any]:
        return self.execution_service.reset_paper_balance(balance, **kwargs)

    def get_portfolio_payload(self, **kwargs) -> dict[str, Any]:
        return self.execution_service.get_portfolio_payload(**kwargs)

    def close_all_open_orders(self, **kwargs) -> dict[str, Any]:
        return self.execution_service.close_all_open_orders(**kwargs)

    def query_order(self, order_id: str, **kwargs) -> dict[str, Any]:
        raise UnsupportedExecutionProfileError("Live query/cancel/verification routes are not applicable to paper orders.")

    def verify_order(self, order_id: str, **kwargs) -> dict[str, Any]:
        raise UnsupportedExecutionProfileError("Live query/cancel/verification routes are not applicable to paper orders.")

    def cancel_order(self, order_id: str, **kwargs) -> dict[str, Any]:
        raise UnsupportedExecutionProfileError("Live query/cancel/verification routes are not applicable to paper orders.")


class BinanceUsdmLiveExecutionAdapter:
    """Minimal manual-live Binance USDⓈ-M adapter for Phase 5A."""

    adapter_key = "binance_usdm_live"

    def __init__(self, service: BinanceUsdmManualLiveService | None = None) -> None:
        self.service = service or BinanceUsdmManualLiveService()

    def create_manual_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.service.create_manual_order(payload)

    def get_orders_snapshot(self, **kwargs) -> dict[str, Any]:
        return self.service.get_orders_snapshot(**kwargs)

    def query_order(self, order_id: str, **kwargs) -> dict[str, Any]:
        return self.service.query_order(order_id)

    def verify_order(self, order_id: str, **kwargs) -> dict[str, Any]:
        return self.service.verify_order(order_id, **kwargs)

    def cancel_order(self, order_id: str, **kwargs) -> dict[str, Any]:
        return self.service.cancel_order(order_id)

    def open_order(self, signal: dict[str, Any], **kwargs) -> dict[str, Any]:
        payload = {
            "profile_id": kwargs.get("profile_id") or signal.get("profile_id"),
            "symbol": signal.get("symbol"),
            "interval": signal.get("interval"),
            "mode": signal.get("mode"),
            "direction": signal.get("direction"),
            "confidence": signal.get("confidence"),
            "entry": signal.get("entry"),
            "sl": signal.get("sl") if signal.get("sl") is not None else signal.get("stop_loss"),
            "tp": signal.get("tp") if signal.get("tp") is not None else signal.get("take_profit"),
            "risk_reward": signal.get("risk_reward"),
            "entry_r_multiple": signal.get("entry_r_multiple"),
            "signal_id": signal.get("signal_id"),
            "decision_id": signal.get("decision_id") or signal.get("decision_event_id") or signal.get("signal_id"),
            "decision_event_id": signal.get("decision_event_id"),
            "request_id": signal.get("request_id"),
            "run_id": signal.get("run_id"),
            "trace_id": signal.get("trace_id"),
            "source": "AUTO",
            "origin": "AUTO",
            "execution_target": signal.get("execution_target"),
            "execution_account": signal.get("execution_account"),
            "execution_account_id": signal.get("execution_account_id"),
            "execution_routing_key": signal.get("execution_routing_key"),
            "auto_live_policy": signal.get("auto_live_policy") or {},
        }
        return self.service.create_manual_order(payload)

    def close_order(self, order_id: str, **kwargs) -> dict[str, Any]:
        raise UnsupportedExecutionProfileError("Live close/cancel flows are deferred beyond Phase 5A.")

    def update_manual_order(self, order_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise UnsupportedExecutionProfileError("Live manual order mutation is deferred beyond Phase 5A.")

    def delete_manual_order(self, order_id: str) -> bool:
        raise UnsupportedExecutionProfileError("Live manual order deletion is deferred beyond Phase 5A.")

    def monitor_open_orders(self, **kwargs) -> dict[str, Any]:
        raise UnsupportedExecutionProfileError("Live monitoring ownership is deferred beyond Phase 5A.")

    def get_paper_balance_payload(self, **kwargs) -> dict[str, Any]:
        raise UnsupportedExecutionProfileError("Paper balance payload is not available for live targets.")

    def compute_confidence_position_size(self, entry_price: float, **kwargs) -> dict[str, Any]:
        raise UnsupportedExecutionProfileError("Paper confidence sizing is not used for live Phase 5A routing.")

    def deposit_paper_balance(self, amount: float, **kwargs) -> dict[str, Any]:
        raise UnsupportedExecutionProfileError("Paper balance mutations are not available for live targets.")

    def reconcile_legacy_open_orders(self, **kwargs) -> dict[str, Any]:
        raise UnsupportedExecutionProfileError("Legacy paper reconciliation is not available for live targets.")

    def reset_paper_balance(self, balance: float | None = None, **kwargs) -> dict[str, Any]:
        raise UnsupportedExecutionProfileError("Paper balance reset is not available for live targets.")

    def get_portfolio_payload(self, **kwargs) -> dict[str, Any]:
        return self.service.get_portfolio_payload(**kwargs)

    def close_all_open_orders(self, **kwargs) -> dict[str, Any]:
        raise UnsupportedExecutionProfileError("Live bulk close is deferred beyond Phase 5A.")


class ExecutionOrchestrator:
    """Minimal profile-aware execution seam for Phase 3A."""

    def __init__(
        self,
        *,
        paper_adapter: PaperExecutionAdapter | None = None,
        binance_usdm_live_adapter: BinanceUsdmLiveExecutionAdapter | None = None,
        runtime_profile_repo: RuntimeProfileRepository | None = None,
        order_repo: OrderRepository | None = None,
        paper_repo: PaperAccountRepository | None = None,
        execution_account_repo: ExecutionAccountRepository | None = None,
        runtime_profile_service: RuntimeProfileService | None = None,
    ) -> None:
        self.paper_adapter = paper_adapter or PaperExecutionAdapter()
        self.binance_usdm_live_adapter = binance_usdm_live_adapter or BinanceUsdmLiveExecutionAdapter()
        self.runtime_profile_repo = runtime_profile_repo or RuntimeProfileRepository()
        self.order_repo = order_repo or OrderRepository()
        self.paper_repo = paper_repo or PaperAccountRepository()
        self.execution_account_repo = execution_account_repo or ExecutionAccountRepository()
        self.runtime_profile_service = runtime_profile_service or RuntimeProfileService()

    @property
    def paper_execution(self) -> PaperExecutionService:
        return self.paper_adapter.execution_service

    def resolve_target(
        self,
        profile_id: str = PAPER_PROFILE_ID,
        *,
        intent: str = READ_INTENT,
        account_id: str | None = None,
    ) -> ExecutionTarget:
        resolved_profile_id = str(profile_id or PAPER_PROFILE_ID)
        with session_scope() as session:
            profile = self.runtime_profile_repo.get_profile(session, resolved_profile_id)
            if profile is None and resolved_profile_id == PAPER_PROFILE_ID:
                profile = self.runtime_profile_repo.ensure_paper_main(session)
            if profile is None:
                raise UnsupportedExecutionProfileError(f"Runtime profile not found: {resolved_profile_id}")

            target = ExecutionTarget(
                profile_id=resolved_profile_id,
                profile_name=str(profile.get("name") or resolved_profile_id),
                status=str(profile.get("status") or "ACTIVE"),
                runtime_mode=str(profile.get("runtime_mode") or PAPER_EXECUTION_MODE),
                execution_mode=str(profile.get("execution_mode") or PAPER_EXECUTION_MODE),
                venue=str(profile.get("venue") or PAPER_VENUE),
                product_type=str(profile.get("product_type") or "SIMULATED"),
                venue_environment=(str(profile.get("venue_environment") or "").strip() or None),
                api_base_url=(str(profile.get("api_base_url") or "").strip() or None),
                default_for_auto_trading=bool(profile.get("default_for_auto_trading")),
                manual_trading_enabled=bool(profile.get("manual_trading_enabled")),
                auto_trading_enabled=bool(profile.get("auto_trading_enabled")),
                read_only=bool(profile.get("read_only")),
                supports_account_reads=bool(profile.get("supports_account_reads")),
                supports_order_placement=bool(profile.get("supports_order_placement")),
                credential_ref=profile.get("credential_ref"),
                connectivity_status=(str(profile.get("connectivity_status") or "").strip() or None),
                account=self._resolve_execution_account(
                    session,
                    profile_id=resolved_profile_id,
                    profile=profile,
                    account_id=account_id,
                ),
            )

        self._enforce_policy(target, intent=intent)
        return target

    def open_order(
        self,
        signal: dict[str, Any],
        *,
        profile_id: str = PAPER_PROFILE_ID,
        **kwargs,
    ) -> dict[str, Any]:
        requested_profile_id = str(signal.get("profile_id") or profile_id or PAPER_PROFILE_ID)
        source = str(kwargs.get("source") or "").upper()
        try:
            target = self.resolve_target(
                requested_profile_id,
                intent=AUTO_INTENT if source == "AUTO" else MANUAL_INTENT,
                account_id=signal.get("execution_account_id"),
            )
        except ExecutionPolicyViolationError as exc:
            if source == "AUTO" and requested_profile_id != PAPER_PROFILE_ID:
                posture = "BLOCKED"
                reason_codes = ["POLICY_VIOLATION"]
                try:
                    auto_live = self.runtime_profile_service.get_auto_live_policy(requested_profile_id, candidate=signal)
                    posture = str(auto_live.get("posture") or posture)
                    reason_codes = list(auto_live.get("reason_codes") or reason_codes)
                except Exception:
                    pass
                self._record_auto_live_attempt(
                    requested_profile_id,
                    signal,
                    outcome="BLOCKED",
                    posture=posture,
                    reason_codes=reason_codes,
                    message=str(exc),
                )
            raise

        auto_live = None
        if source == "AUTO" and not self._is_paper_target(execution_mode=target.execution_mode, venue=target.venue):
            auto_live = self.runtime_profile_service.get_auto_live_policy(
                target.profile_id,
                candidate=signal,
                account=self._serialize_account(target.account) or {},
            )
            if not bool(auto_live.get("eligible")):
                reason_codes = auto_live.get("reason_codes") or ["AUTO_LIVE_NOT_ELIGIBLE"]
                self._record_auto_live_attempt(
                    target.profile_id,
                    signal,
                    outcome="BLOCKED",
                    posture=str(auto_live.get("posture") or "BLOCKED"),
                    reason_codes=reason_codes,
                    message=(auto_live.get("reasons") or [{}])[0].get("message") if auto_live.get("reasons") else None,
                )
                joined_reason_codes = ", ".join(reason_codes) or "AUTO_LIVE_NOT_ELIGIBLE"
                raise ExecutionPolicyViolationError(
                    f"Execution profile '{target.profile_id}' is blocked for autonomous live routing: posture={auto_live.get('posture')} reasons={joined_reason_codes}."
                )
        routed_signal = {
            **signal,
            "profile_id": target.profile_id,
            "source": source or signal.get("source"),
            "execution_target": self._serialize_target(target),
            "execution_account": self._serialize_account(target.account),
            "execution_account_id": target.account.account_id if target.account else None,
            "execution_routing_key": target.account.routing_key if target.account else None,
            "auto_live_policy": auto_live or signal.get("auto_live_policy") or {},
        }
        return self._adapter_for_target(target).open_order(
            routed_signal,
            profile_id=target.profile_id,
            **kwargs,
        )

    def close_order(self, order_id: str, **kwargs) -> dict[str, Any]:
        target = self.resolve_order_target(order_id, intent=MANAGE_INTENT)
        return self._adapter_for_target(target).close_order(order_id, **kwargs)

    def create_manual_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        target = self.resolve_target(
            str(payload.get("profile_id") or PAPER_PROFILE_ID),
            intent=MANUAL_INTENT,
            account_id=payload.get("execution_account_id"),
        )
        return self._adapter_for_target(target).create_manual_order(
            {
                **payload,
                "profile_id": target.profile_id,
                "execution_target": self._serialize_target(target),
                "execution_account": self._serialize_account(target.account),
                "execution_account_id": target.account.account_id if target.account else None,
                "execution_routing_key": target.account.routing_key if target.account else None,
            }
        )

    def update_manual_order(self, order_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        target = self.resolve_order_target(order_id, fallback_profile_id=str(payload.get("profile_id") or PAPER_PROFILE_ID), intent=MANAGE_INTENT)
        return self._adapter_for_target(target).update_manual_order(order_id, payload)

    def delete_manual_order(self, order_id: str, *, profile_id: str | None = None) -> bool:
        target = self.resolve_order_target(order_id, fallback_profile_id=profile_id, intent=MANAGE_INTENT)
        return self._adapter_for_target(target).delete_manual_order(order_id)

    def monitor_open_orders(self, *, profile_id: str = PAPER_PROFILE_ID, **kwargs) -> dict[str, Any]:
        target = self.resolve_target(profile_id, intent=MONITOR_INTENT)
        return self._adapter_for_target(target).monitor_open_orders(profile_id=target.profile_id, **kwargs)

    def get_orders_snapshot(
        self,
        *,
        limit: int = 500,
        status: str | None = None,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict[str, Any]:
        target = self.resolve_target(profile_id, intent=READ_INTENT)
        return self._adapter_for_target(target).get_orders_snapshot(limit=limit, status=status, profile_id=target.profile_id)

    def get_paper_balance_payload(self, *, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any]:
        target = self.resolve_target(profile_id, intent=READ_INTENT)
        return self._adapter_for_target(target).get_paper_balance_payload(profile_id=target.profile_id)

    def compute_confidence_position_size(
        self,
        entry_price: float,
        *,
        profile_id: str = PAPER_PROFILE_ID,
        **kwargs,
    ) -> dict[str, Any]:
        target = self.resolve_target(profile_id, intent=AUTO_INTENT)
        return self._adapter_for_target(target).compute_confidence_position_size(entry_price, profile_id=target.profile_id, **kwargs)

    def deposit_paper_balance(self, amount: float, *, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any]:
        target = self.resolve_target(profile_id, intent=BALANCE_INTENT)
        return self._adapter_for_target(target).deposit_paper_balance(amount, profile_id=target.profile_id)

    def reconcile_legacy_open_orders(self, *, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any]:
        target = self.resolve_target(profile_id, intent=BALANCE_INTENT)
        return self._adapter_for_target(target).reconcile_legacy_open_orders(profile_id=target.profile_id)

    def reset_paper_balance(
        self,
        balance: float | None = None,
        *,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict[str, Any]:
        target = self.resolve_target(profile_id, intent=BALANCE_INTENT)
        return self._adapter_for_target(target).reset_paper_balance(balance, profile_id=target.profile_id)

    def get_portfolio_payload(self, *, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any]:
        target = self.resolve_target(profile_id, intent=READ_INTENT)
        return self._adapter_for_target(target).get_portfolio_payload(profile_id=target.profile_id)

    def close_all_open_orders(
        self,
        *,
        close_reason: str = "MANUAL_BULK_CLOSE",
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict[str, Any]:
        target = self.resolve_target(profile_id, intent=MANAGE_INTENT)
        return self._adapter_for_target(target).close_all_open_orders(close_reason=close_reason, profile_id=target.profile_id)

    def query_order(self, order_id: str, *, profile_id: str | None = None) -> dict[str, Any]:
        target = self.resolve_order_target(order_id, fallback_profile_id=profile_id, intent=READ_INTENT)
        return self._adapter_for_target(target).query_order(order_id)

    def verify_order(self, order_id: str, *, profile_id: str | None = None, reason: str = "MANUAL_VERIFY") -> dict[str, Any]:
        target = self.resolve_order_target(order_id, fallback_profile_id=profile_id, intent=READ_INTENT)
        return self._adapter_for_target(target).verify_order(order_id, reason=reason)

    def cancel_order(self, order_id: str, *, profile_id: str | None = None) -> dict[str, Any]:
        target = self.resolve_order_target(order_id, fallback_profile_id=profile_id, intent=MANAGE_INTENT)
        return self._adapter_for_target(target).cancel_order(order_id)

    def resolve_order_target(
        self,
        order_id: str,
        *,
        fallback_profile_id: str | None = None,
        intent: str = READ_INTENT,
    ) -> ExecutionTarget:
        with session_scope() as session:
            order = self.order_repo.get_order(session, order_id)
        if order is not None:
            return self.resolve_target(str(order.get("profile_id") or PAPER_PROFILE_ID), intent=intent)
        return self.resolve_target(str(fallback_profile_id or PAPER_PROFILE_ID), intent=intent)

    def _record_auto_live_attempt(
        self,
        profile_id: str,
        signal: dict[str, Any],
        *,
        outcome: str,
        posture: str,
        reason_codes: list[str],
        message: str | None,
    ) -> None:
        self.runtime_profile_service.record_auto_live_attempt(
            profile_id,
            {
                "profile_id": profile_id,
                "outcome": outcome,
                "posture": posture,
                "message": message,
                "reason_codes": reason_codes,
                "decision": {
                    "decision_id": signal.get("decision_id") or signal.get("decision_event_id") or signal.get("signal_id"),
                    "signal_id": signal.get("signal_id"),
                    "decision_event_id": signal.get("decision_event_id"),
                    "request_id": signal.get("request_id"),
                    "run_id": signal.get("run_id"),
                    "symbol": signal.get("symbol"),
                    "interval": signal.get("interval"),
                    "mode": signal.get("mode"),
                    "direction": signal.get("direction"),
                    "entry_r_multiple": signal.get("entry_r_multiple"),
                },
                "protection": {
                    "status": None,
                    "safe_to_consider_active": False,
                    "message": message,
                },
            },
        )

    @staticmethod
    def _is_paper_target(*, execution_mode: str, venue: str) -> bool:
        return str(execution_mode or "").upper() == PAPER_EXECUTION_MODE and str(venue or "").upper() == PAPER_VENUE

    def _resolve_execution_account(
        self,
        session,
        *,
        profile_id: str,
        profile: dict[str, Any],
        account_id: str | None = None,
    ) -> ExecutionAccountRef | None:
        execution_mode = str(profile.get("execution_mode") or PAPER_EXECUTION_MODE)
        venue = str(profile.get("venue") or PAPER_VENUE)
        if account_id:
            account_row = self.execution_account_repo.get_account_by_id(session, str(account_id))
            if account_row is not None and str(account_row.get("profile_id") or "") != profile_id:
                raise ExecutionPolicyViolationError(
                    f"Execution account '{account_id}' does not belong to profile '{profile_id}'."
                )
        else:
            account_row = self.execution_account_repo.get_default_account(session, profile_id)
        if account_row is None and self._is_paper_target(execution_mode=execution_mode, venue=venue):
            account_row = self.paper_repo.get_or_create_account(session, profile_id=profile_id)
        if account_row is None:
            return None
        venue_scope = str(account_row.get("venue_account_key") or venue)
        account_id = str(account_row.get("account_id") or "")
        return ExecutionAccountRef(
            profile_id=profile_id,
            account_id=account_id,
            account_key=str(account_row.get("account_key") or ""),
            account_type=str(account_row.get("account_type") or ""),
            venue_account_key=account_row.get("venue_account_key"),
            balance_ccy=account_row.get("balance_ccy"),
            available_balance=float(account_row.get("available_balance")) if account_row.get("available_balance") is not None else None,
            equity=float(account_row.get("equity")) if account_row.get("equity") is not None else None,
            margin_used=float(account_row.get("margin_used")) if account_row.get("margin_used") is not None else None,
            execution_mode=execution_mode,
            venue=venue,
            routing_key=f"{profile_id}:{venue}:{account_id}",
            venue_scope=venue_scope,
        )

    def _enforce_policy(self, target: ExecutionTarget, *, intent: str) -> None:
        status = str(target.status or "ACTIVE").upper()
        if intent != READ_INTENT and status not in {"ACTIVE", "READ_ONLY"}:
            raise ExecutionPolicyViolationError(
                f"Execution profile '{target.profile_id}' is not active for {intent.lower()} routing: status={status}."
            )
        if intent in {AUTO_INTENT, MANUAL_INTENT, MANAGE_INTENT, BALANCE_INTENT} and target.read_only:
            raise ExecutionPolicyViolationError(
                f"Execution profile '{target.profile_id}' is read-only and cannot accept {intent.lower()} changes."
            )
        if intent == MANUAL_INTENT and not target.manual_trading_enabled:
            raise ExecutionPolicyViolationError(
                f"Execution profile '{target.profile_id}' does not allow manual trading."
            )
        if intent in {MANUAL_INTENT, MANAGE_INTENT} and not self._is_paper_target(execution_mode=target.execution_mode, venue=target.venue):
            if not target.supports_order_placement:
                raise ExecutionPolicyViolationError(
                    f"Execution profile '{target.profile_id}' does not support live order placement."
                )
        if intent == AUTO_INTENT and not self._auto_execution_allowed(target):
            raise ExecutionPolicyViolationError(
                f"Execution profile '{target.profile_id}' does not allow autonomous execution."
            )
        if intent == AUTO_INTENT and not self._is_paper_target(execution_mode=target.execution_mode, venue=target.venue):
            auto_live = self.runtime_profile_service.get_auto_live_policy(
                target.profile_id,
                account=self._serialize_account(target.account) or {},
            )
            if not bool(auto_live.get("eligible")):
                reason_codes = ", ".join(auto_live.get("reason_codes") or []) or "AUTO_LIVE_NOT_ELIGIBLE"
                raise ExecutionPolicyViolationError(
                    f"Execution profile '{target.profile_id}' is blocked for autonomous live routing: posture={auto_live.get('posture')} reasons={reason_codes}."
                )
        if intent in {AUTO_INTENT, MANUAL_INTENT, MANAGE_INTENT, BALANCE_INTENT} and target.account is None:
            raise ExecutionPolicyViolationError(
                f"Execution profile '{target.profile_id}' does not have an execution account for {intent.lower()} routing."
            )

    def _adapter_for_target(self, target: ExecutionTarget) -> ExecutionAdapter:
        if self._is_paper_target(execution_mode=target.execution_mode, venue=target.venue):
            return self.paper_adapter
        if str(target.execution_mode or "").upper() == "LIVE" and str(target.venue or "").upper() == "BINANCE_USDM":
            return self.binance_usdm_live_adapter
        raise UnsupportedExecutionProfileError(
            f"Execution profile '{target.profile_id}' routes to unsupported target "
            f"{target.execution_mode}/{target.venue} in Phase 5A."
        )

    @staticmethod
    def _auto_execution_allowed(target: ExecutionTarget) -> bool:
        if target.profile_id == PAPER_PROFILE_ID and target.execution_mode == PAPER_EXECUTION_MODE and target.venue == PAPER_VENUE:
            return True
        return bool(target.auto_trading_enabled and target.default_for_auto_trading)

    @staticmethod
    def _serialize_account(account: ExecutionAccountRef | None) -> dict[str, Any] | None:
        if account is None:
            return None
        return {
            "profile_id": account.profile_id,
            "account_id": account.account_id,
            "account_key": account.account_key,
            "account_type": account.account_type,
            "venue_account_key": account.venue_account_key,
            "balance_ccy": account.balance_ccy,
            "available_balance": account.available_balance,
            "equity": account.equity,
            "margin_used": account.margin_used,
            "execution_mode": account.execution_mode,
            "venue": account.venue,
            "routing_key": account.routing_key,
            "venue_scope": account.venue_scope,
            "is_primary": account.is_primary,
        }

    @staticmethod
    def _serialize_target(target: ExecutionTarget) -> dict[str, Any]:
        return {
            "profile_id": target.profile_id,
            "profile_name": target.profile_name,
            "status": target.status,
            "runtime_mode": target.runtime_mode,
            "execution_mode": target.execution_mode,
            "venue": target.venue,
            "product_type": target.product_type,
            "venue_environment": target.venue_environment,
            "api_base_url": target.api_base_url,
            "default_for_auto_trading": target.default_for_auto_trading,
            "manual_trading_enabled": target.manual_trading_enabled,
            "auto_trading_enabled": target.auto_trading_enabled,
            "read_only": target.read_only,
            "supports_account_reads": target.supports_account_reads,
            "supports_order_placement": target.supports_order_placement,
            "credential_ref": target.credential_ref,
            "connectivity_status": target.connectivity_status,
            "route_key": target.route_key,
        }
