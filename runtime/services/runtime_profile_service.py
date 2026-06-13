"""Runtime profile exposure and Binance USDM connectivity foundation."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import requests

from runtime.db.repos.execution_account_repo import ExecutionAccountRepository
from runtime.db.repos.order_repo import OrderRepository
from runtime.db.repos.venue_state_repo import VenueStateRepository
from runtime.db.repos.runtime_profile_repo import BINANCE_USDM_PROFILE_ID, PAPER_PROFILE_ID, RuntimeProfileRepository
from runtime.db.repos.settings_repo import DEFAULT_RUNTIME_SETTINGS, SettingsRepository, split_csv
from runtime.db.repos.state_repo import StateRepository
from runtime.db.session import session_scope

BINANCE_USDM_VENUE = "BINANCE_USDM"
BINANCE_USDM_PRODUCTION_BASE_URL = "https://fapi.binance.com"
BINANCE_USDM_TESTNET_BASE_URL = "https://demo-fapi.binance.com"
AUTO_LIVE_ACTIVITY_STATE_KEY = "auto_live_activity"
AUTO_LIVE_ACTIVITY_LIMIT = 50
PROFILE_CAPABILITY_FIELDS = (
    "read_only",
    "manual_trading_enabled",
    "auto_trading_enabled",
    "default_for_auto_trading",
)
PROFILE_RUNTIME_SETTINGS_FIELDS = (
    "AUTONOMOUS_ENABLED",
    "AUTO_LIVE_GLOBAL_KILL_SWITCH",
    "AUTO_LIVE_PROFILE_KILL_SWITCH",
    "AUTO_LIVE_SYMBOL_ALLOWLIST",
    "AUTO_LIVE_MAX_CONCURRENT_POSITIONS",
)
PROFILE_SETTING_RUNTIME_FIELDS_FOR_PRESETS = PROFILE_RUNTIME_SETTINGS_FIELDS
PROFILE_RISK_SETTINGS_FIELDS = (
    "LIVE_RISK_BASIS",
    "LIVE_RISK_PER_TRADE_PCT",
    "LIVE_DEFAULT_ENTRY_R_MULTIPLE",
    "LIVE_MAX_POSITION_R",
    "LIVE_MAX_TOTAL_OPEN_R",
    "LIVE_MAX_DAILY_LOSS_R",
    "LIVE_MAX_LEVERAGE",
)


class RuntimeProfileNotFoundError(ValueError):
    """Raised when a requested runtime profile does not exist."""


class RuntimeProfileConnectivityError(ValueError):
    """Raised when a profile cannot complete a connectivity probe safely."""


class RuntimeProfileAccessError(ValueError):
    """Raised when internal profile access requirements are not satisfied."""


class RuntimeProfileService:
    def __init__(
        self,
        *,
        runtime_profile_repo: RuntimeProfileRepository | None = None,
        http_session: requests.sessions.Session | None = None,
        settings_repo: SettingsRepository | None = None,
        order_repo: OrderRepository | None = None,
        state_repo: StateRepository | None = None,
        execution_account_repo: ExecutionAccountRepository | None = None,
        venue_state_repo: VenueStateRepository | None = None,
    ) -> None:
        self.runtime_profile_repo = runtime_profile_repo or RuntimeProfileRepository()
        self.http_session = http_session or requests.Session()
        if hasattr(self.http_session, "trust_env"):
            trust_env = os.environ.get("RUNTIME_HTTP_TRUST_ENV")
            if trust_env is not None:
                self.http_session.trust_env = str(trust_env).strip().lower() in {"1", "true", "yes", "on"}
        self.settings_repo = settings_repo or SettingsRepository()
        self.order_repo = order_repo or OrderRepository()
        self.state_repo = state_repo or StateRepository()
        self.execution_account_repo = execution_account_repo or ExecutionAccountRepository()
        self.venue_state_repo = venue_state_repo or VenueStateRepository()

    def list_profiles(self) -> list[dict[str, Any]]:
        with session_scope() as session:
            items = self.runtime_profile_repo.list_profiles(session)
        return [self._sanitize_profile(item) for item in items]

    def get_profile(self, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any]:
        with session_scope() as session:
            profile = self.runtime_profile_repo.get_profile(session, profile_id)
        if profile is None:
            raise RuntimeProfileNotFoundError(f"Runtime profile not found: {profile_id}")
        return self._sanitize_profile(profile)

    def get_profile_access(self, profile_id: str, *, require_account_reads: bool = False) -> dict[str, Any]:
        with session_scope() as session:
            profile = self.runtime_profile_repo.get_profile(session, profile_id)
        if profile is None:
            raise RuntimeProfileNotFoundError(f"Runtime profile not found: {profile_id}")
        sanitized = self._sanitize_profile(profile)
        resolved = self._resolve_credentials(profile)
        if require_account_reads and not bool(profile.get("supports_account_reads")):
            raise RuntimeProfileAccessError(f"Runtime profile '{profile_id}' does not support read-only account access.")
        return {
            "profile": profile,
            "sanitized_profile": sanitized,
            "resolved_api_base_url": sanitized.get("resolved_api_base_url"),
            "credential_ref": resolved.get("credential_ref"),
            "api_key": resolved.get("api_key"),
            "api_secret": resolved.get("api_secret"),
            "credentials_configured": bool(resolved.get("configured")),
        }

    def signed_get_json(self, profile_id: str, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
        return self.signed_request_json(profile_id, "GET", path, params=params)

    def signed_request_json(
        self,
        profile_id: str,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        access = self.get_profile_access(profile_id, require_account_reads=True)
        if not access["credentials_configured"]:
            raise RuntimeProfileAccessError("Credential reference is not fully configured.")
        payload = dict(params or {})
        payload.setdefault("timestamp", self._epoch_ms())
        return self._signed_request_json(
            method.upper(),
            str(access["resolved_api_base_url"]),
            path,
            api_key=str(access["api_key"]),
            api_secret=str(access["api_secret"]),
            params=payload,
        )

    def api_key_request_json(
        self,
        profile_id: str,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        access = self.get_profile_access(profile_id, require_account_reads=True)
        if not access["credentials_configured"]:
            raise RuntimeProfileAccessError("Credential reference is not fully configured.")
        base_url = str(access["resolved_api_base_url"])
        query = urlencode(params or {})
        url = f"{base_url}{path}"
        if query:
            url = f"{url}?{query}"
        return self._request_json(
            method.upper(),
            url,
            headers={"X-MBX-APIKEY": str(access["api_key"])} ,
        )

    def probe_connectivity(self, profile_id: str) -> dict[str, Any]:
        with session_scope() as session:
            profile = self.runtime_profile_repo.get_profile(session, profile_id)
            if profile is None:
                raise RuntimeProfileNotFoundError(f"Runtime profile not found: {profile_id}")

            if str(profile.get("venue") or "").upper() != BINANCE_USDM_VENUE:
                now = self._utc_now_iso()
                updated = self.runtime_profile_repo.save_profile(
                    session,
                    {
                        **profile,
                        "connectivity_status": "NOT_APPLICABLE",
                        "last_connectivity_check_at_utc": now,
                        "last_connectivity_error": None,
                        "updated_at_utc": now,
                    },
                )
                return self._sanitize_profile(updated)

            credential_status = self._credential_status(profile)
            if not credential_status["configured"]:
                now = self._utc_now_iso()
                updated = self.runtime_profile_repo.save_profile(
                    session,
                    {
                        **profile,
                        "connectivity_status": "MISSING_CREDENTIALS",
                        "last_connectivity_check_at_utc": now,
                        "last_connectivity_error": "Credential reference is not fully configured.",
                        "updated_at_utc": now,
                    },
                )
                return self._sanitize_profile(updated)

        try:
            result = self._probe_binance_usdm(profile_id)
            status = "CONNECTED"
            error_text = None
        except RuntimeProfileConnectivityError as exc:
            result = {
                "connectivity_probe": {
                    "ok": False,
                    "status": "ERROR",
                    "exchange_server_time": None,
                    "exchange_account_alias": None,
                    "can_read_account": False,
                    "error": str(exc),
                }
            }
            status = "ERROR"
            error_text = str(exc)

        now = self._utc_now_iso()
        with session_scope() as session:
            profile = self.runtime_profile_repo.get_profile(session, profile_id)
            assert profile is not None
            payload = {
                **profile,
                "connectivity_status": status,
                "last_connectivity_check_at_utc": now,
                "last_connectivity_error": error_text,
                "updated_at_utc": now,
            }
            if status == "CONNECTED":
                payload["last_connectivity_ok_at_utc"] = now
            updated = self.runtime_profile_repo.save_profile(session, payload)
        sanitized = self._sanitize_profile(updated)
        sanitized.update(result)
        return sanitized

    def _probe_binance_usdm(self, profile_id: str) -> dict[str, Any]:
        profile = self.get_profile(profile_id)
        access = self.get_profile_access(profile_id, require_account_reads=True)
        if not access["credentials_configured"]:
            raise RuntimeProfileConnectivityError("Credential reference is not fully configured.")
        base_url = str(profile["resolved_api_base_url"])
        server_time = self._request_json("GET", f"{base_url}/fapi/v1/time")
        timestamp = int(server_time.get("serverTime") or self._epoch_ms())
        account_payload = self._signed_request_json(
            "GET",
            base_url,
            "/fapi/v2/account",
            api_key=str(access["api_key"]),
            api_secret=str(access["api_secret"]),
            params={"timestamp": timestamp},
        )
        return {
            "connectivity_probe": {
                "ok": True,
                "status": "CONNECTED",
                "exchange_server_time": server_time.get("serverTime"),
                "exchange_account_alias": account_payload.get("accountAlias"),
                "can_read_account": True,
                "error": None,
            }
        }

    def _resolve_credentials(self, profile: dict[str, Any]) -> dict[str, Any]:
        credential_ref = str(profile.get("credential_ref") or "").strip()
        env_prefix = self._credential_env_prefix(credential_ref)
        api_key = os.environ.get(f"{env_prefix}_API_KEY") if env_prefix else None
        api_secret = os.environ.get(f"{env_prefix}_API_SECRET") if env_prefix else None
        env_base_url = os.environ.get(f"{env_prefix}_BASE_URL") if env_prefix else None
        return {
            "credential_ref": credential_ref or None,
            "env_prefix": env_prefix or None,
            "configured": bool(api_key and api_secret),
            "has_api_key": bool(api_key),
            "has_api_secret": bool(api_secret),
            "api_key": api_key,
            "api_secret": api_secret,
            "env_base_url": env_base_url,
        }

    def _credential_status(self, profile: dict[str, Any]) -> dict[str, Any]:
        resolved = self._resolve_credentials(profile)
        return {
            "credential_ref": resolved["credential_ref"],
            "env_prefix": resolved["env_prefix"],
            "configured": resolved["configured"],
            "has_api_key": resolved["has_api_key"],
            "has_api_secret": resolved["has_api_secret"],
        }

    def get_profile_settings(self, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any]:
        with session_scope() as session:
            profile = self.runtime_profile_repo.get_profile(session, profile_id)
            if profile is None:
                raise RuntimeProfileNotFoundError(f"Runtime profile not found: {profile_id}")
            resolution = self.settings_repo.get_resolution(session, profile_id=profile_id, materialize=True)
        auto_live = self.get_auto_live_policy(profile_id)
        settings = dict(resolution.get("settings") or {})
        capabilities = {
            key: bool(profile.get(key))
            for key in PROFILE_CAPABILITY_FIELDS
        }
        runtime_settings = {
            key: str(settings.get(key) or "")
            for key in PROFILE_RUNTIME_SETTINGS_FIELDS
        }
        risk_settings = {
            key: str(settings.get(key) or "")
            for key in PROFILE_RISK_SETTINGS_FIELDS
        }
        return {
            "profile_id": profile_id,
            "capabilities": capabilities,
            "runtime_settings": runtime_settings,
            "risk_settings": risk_settings,
            "auto_live": auto_live,
            "resolved_config_hash": str(resolution.get("resolved_config_hash") or ""),
            "preset_profiles": self._build_setting_presets(
                profile_id,
                capabilities=capabilities,
                runtime_settings=runtime_settings,
                risk_settings=risk_settings,
            ),
        }

    def update_profile_settings(
        self,
        profile_id: str,
        *,
        capabilities: dict[str, Any] | None = None,
        runtime_settings: dict[str, Any] | None = None,
        risk_settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        allowed_capabilities = {key for key in PROFILE_CAPABILITY_FIELDS}
        capability_updates = {
            key: self._is_truthy(value)
            for key, value in dict(capabilities or {}).items()
            if key in allowed_capabilities
        }
        settings_updates = {
            key: str(value)
            for key, value in {
                **dict(runtime_settings or {}),
                **dict(risk_settings or {}),
            }.items()
            if key in {*PROFILE_RUNTIME_SETTINGS_FIELDS, *PROFILE_RISK_SETTINGS_FIELDS} and value is not None
        }
        with session_scope() as session:
            profile = self.runtime_profile_repo.get_profile(session, profile_id)
            if profile is None:
                raise RuntimeProfileNotFoundError(f"Runtime profile not found: {profile_id}")
            if capability_updates:
                now = self._utc_now_iso()
                self.runtime_profile_repo.save_profile(
                    session,
                    {
                        **profile,
                        **capability_updates,
                        "updated_at_utc": now,
                    },
                )
            if settings_updates:
                self.settings_repo.save_many(session, settings_updates, profile_id=profile_id)
        return self.get_profile_settings(profile_id)

    def _build_setting_presets(
        self,
        profile_id: str,
        *,
        capabilities: dict[str, bool],
        runtime_settings: dict[str, str],
        risk_settings: dict[str, str],
    ) -> list[dict[str, Any]]:
        runtime_defaults = {
            key: str(DEFAULT_RUNTIME_SETTINGS.get(key) or "")
            for key in PROFILE_SETTING_RUNTIME_FIELDS_FOR_PRESETS
        }
        risk_defaults = {
            key: str(DEFAULT_RUNTIME_SETTINGS.get(key) or "")
            for key in PROFILE_RISK_SETTINGS_FIELDS
        }
        return [
            {
                "preset_id": "runtime-defaults",
                "label": "Runtime defaults",
                "description": "Restore the default runtime policy bundle published by the backend.",
                "capabilities": {},
                "runtime_settings": runtime_defaults,
                "risk_settings": risk_defaults,
            },
            {
                "preset_id": "manual-trading",
                "label": "Manual trading",
                "description": "Manual live allowed, autonomous and auto-live routing disabled for this profile.",
                "capabilities": {
                    "read_only": False,
                    "manual_trading_enabled": True,
                    "auto_trading_enabled": False,
                    "default_for_auto_trading": False,
                },
                "runtime_settings": {
                    **runtime_defaults,
                    "AUTONOMOUS_ENABLED": "false",
                    "AUTO_LIVE_PROFILE_KILL_SWITCH": "true",
                },
                "risk_settings": risk_defaults,
            },
            {
                "preset_id": "automatic-live-trading",
                "label": "Automatic live trading",
                "description": "Enable autonomous loop plus auto-live routing with conservative live-risk defaults.",
                "capabilities": {
                    "read_only": False,
                    "manual_trading_enabled": True,
                    "auto_trading_enabled": True,
                    "default_for_auto_trading": True,
                },
                "runtime_settings": {
                    **runtime_defaults,
                    "AUTONOMOUS_ENABLED": "true",
                    "AUTO_LIVE_PROFILE_KILL_SWITCH": "false",
                    "AUTO_LIVE_MAX_CONCURRENT_POSITIONS": runtime_settings.get("AUTO_LIVE_MAX_CONCURRENT_POSITIONS") or "1",
                },
                "risk_settings": {
                    **risk_defaults,
                    "LIVE_RISK_BASIS": risk_settings.get("LIVE_RISK_BASIS") or risk_defaults.get("LIVE_RISK_BASIS") or "AVAILABLE_BALANCE",
                    "LIVE_RISK_PER_TRADE_PCT": risk_settings.get("LIVE_RISK_PER_TRADE_PCT") or risk_defaults.get("LIVE_RISK_PER_TRADE_PCT") or "0.01",
                    "LIVE_DEFAULT_ENTRY_R_MULTIPLE": risk_settings.get("LIVE_DEFAULT_ENTRY_R_MULTIPLE") or risk_defaults.get("LIVE_DEFAULT_ENTRY_R_MULTIPLE") or "1.0",
                    "LIVE_MAX_POSITION_R": risk_settings.get("LIVE_MAX_POSITION_R") or risk_defaults.get("LIVE_MAX_POSITION_R") or "2.0",
                    "LIVE_MAX_TOTAL_OPEN_R": risk_settings.get("LIVE_MAX_TOTAL_OPEN_R") or risk_defaults.get("LIVE_MAX_TOTAL_OPEN_R") or "4.0",
                    "LIVE_MAX_DAILY_LOSS_R": risk_settings.get("LIVE_MAX_DAILY_LOSS_R") or risk_defaults.get("LIVE_MAX_DAILY_LOSS_R") or "3.0",
                    "LIVE_MAX_LEVERAGE": risk_settings.get("LIVE_MAX_LEVERAGE") or risk_defaults.get("LIVE_MAX_LEVERAGE") or "1",
                },
            },
            {
                "preset_id": "read-only-monitoring",
                "label": "Read-only monitoring",
                "description": "Monitoring-only posture. No manual live or auto-live execution changes allowed.",
                "capabilities": {
                    "read_only": True,
                    "manual_trading_enabled": False,
                    "auto_trading_enabled": False,
                    "default_for_auto_trading": False,
                },
                "runtime_settings": {
                    **runtime_defaults,
                    "AUTONOMOUS_ENABLED": "false",
                    "AUTO_LIVE_PROFILE_KILL_SWITCH": "true",
                },
                "risk_settings": risk_defaults,
            },
        ]

    def get_auto_live_policy(
        self,
        profile_id: str,
        *,
        candidate: dict[str, Any] | None = None,
        account: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with session_scope() as session:
            profile = self.runtime_profile_repo.get_profile(session, profile_id)
            if profile is None:
                raise RuntimeProfileNotFoundError(f"Runtime profile not found: {profile_id}")
            resolution = self.settings_repo.get_resolution(session, profile_id=profile_id)
            orders = self.order_repo.list_orders(session, limit=5000, profile_id=profile_id)
            reconciliation = self.state_repo.get(session, "binance_usdm_reconciliation", default=None, profile_id=profile_id)
            stream = self.state_repo.get(session, "binance_usdm_user_data_stream", default=None, profile_id=profile_id)
            recent_activity = self.state_repo.get(session, AUTO_LIVE_ACTIVITY_STATE_KEY, default=[], profile_id=profile_id)
            default_account = account or self.execution_account_repo.get_default_account(session, profile_id)
            venue_positions = self.venue_state_repo.list_positions(session, profile_id, account_id=default_account["account_id"] if default_account else None)
            venue_open_orders = self.venue_state_repo.list_open_orders(session, profile_id, account_id=default_account["account_id"] if default_account else None)
        policy = self._evaluate_auto_live_policy(
            profile=profile,
            settings=dict(resolution.get("settings") or {}),
            orders=orders,
            reconciliation=reconciliation or {},
            stream=stream or {},
            account=default_account or {},
            candidate=candidate or {},
            venue_positions=venue_positions,
            venue_open_orders=venue_open_orders,
        )
        activity_items = self._normalize_auto_live_activity(recent_activity)[:10]
        policy["recent_activity"] = {
            "total": len(self._normalize_auto_live_activity(recent_activity)),
            "blocked": sum(1 for item in activity_items if str(item.get("outcome") or "").upper() == "BLOCKED"),
            "submitted": sum(1 for item in activity_items if str(item.get("outcome") or "").upper() == "SUBMITTED"),
            "items": activity_items,
        }
        return policy

    def _sanitize_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        environment = self._normalize_environment(profile.get("venue_environment"))
        credential_status = self._credential_status(profile)
        resolved_api_base_url = self._resolve_api_base_url(profile, env_base_url=self._resolve_credentials(profile).get("env_base_url"))
        auto_live = self.get_auto_live_policy(str(profile.get("profile_id") or PAPER_PROFILE_ID))
        return {
            "id": profile.get("id"),
            "profile_id": profile.get("profile_id"),
            "name": profile.get("name"),
            "status": profile.get("status"),
            "runtime_mode": profile.get("runtime_mode"),
            "execution_mode": profile.get("execution_mode"),
            "venue": profile.get("venue"),
            "product_type": profile.get("product_type"),
            "venue_environment": environment,
            "api_base_url": profile.get("api_base_url"),
            "resolved_api_base_url": resolved_api_base_url,
            "default_for_auto_trading": bool(profile.get("default_for_auto_trading")),
            "manual_trading_enabled": bool(profile.get("manual_trading_enabled")),
            "auto_trading_enabled": bool(profile.get("auto_trading_enabled")),
            "read_only": bool(profile.get("read_only")),
            "supports_account_reads": bool(profile.get("supports_account_reads")),
            "supports_order_placement": bool(profile.get("supports_order_placement")),
            "credential_ref": credential_status["credential_ref"],
            "credential_status": credential_status,
            "connectivity": {
                "status": profile.get("connectivity_status") or "UNKNOWN",
                "last_checked_at_utc": profile.get("last_connectivity_check_at_utc"),
                "last_connected_at_utc": profile.get("last_connectivity_ok_at_utc"),
                "last_error": profile.get("last_connectivity_error"),
            },
            "auto_live": auto_live,
            "created_at_utc": profile.get("created_at_utc"),
            "updated_at_utc": profile.get("updated_at_utc"),
        }

    def _resolve_api_base_url(self, profile: dict[str, Any], *, env_base_url: str | None) -> str | None:
        explicit = str(profile.get("api_base_url") or "").strip() or None
        if explicit:
            return explicit
        if env_base_url:
            return str(env_base_url).strip() or None
        if str(profile.get("venue") or "").upper() != BINANCE_USDM_VENUE:
            return None
        if self._normalize_environment(profile.get("venue_environment")) == "TESTNET":
            return BINANCE_USDM_TESTNET_BASE_URL
        return BINANCE_USDM_PRODUCTION_BASE_URL

    def _evaluate_auto_live_policy(
        self,
        *,
        profile: dict[str, Any],
        settings: dict[str, str],
        orders: list[dict[str, Any]],
        reconciliation: dict[str, Any],
        stream: dict[str, Any],
        account: dict[str, Any],
        candidate: dict[str, Any],
        venue_positions: list[dict[str, Any]],
        venue_open_orders: list[dict[str, Any]],
    ) -> dict[str, Any]:
        profile_id = str(profile.get("profile_id") or PAPER_PROFILE_ID)
        venue = str(profile.get("venue") or "").upper()
        execution_mode = str(profile.get("execution_mode") or "PAPER").upper()
        connectivity_status = str(profile.get("connectivity_status") or "UNKNOWN").upper()
        reconciliation_status = str(reconciliation.get("status") or "UNAVAILABLE").upper()
        stream_status = str(stream.get("status") or "INACTIVE").upper()
        reasons: list[dict[str, Any]] = []
        projected_total_open_r = None
        trade_risk_budget = None
        one_r_value = None
        entry_r_multiple = self._as_float(candidate.get("entry_r_multiple") or settings.get("LIVE_DEFAULT_ENTRY_R_MULTIPLE"), 1.0)
        risk_basis = str(settings.get("LIVE_RISK_BASIS") or "AVAILABLE_BALANCE").upper()
        risk_per_trade_pct = self._as_float(settings.get("LIVE_RISK_PER_TRADE_PCT"), 0.01)
        max_position_r = self._as_float(settings.get("LIVE_MAX_POSITION_R"), 2.0)
        max_total_open_r = self._as_float(settings.get("LIVE_MAX_TOTAL_OPEN_R"), 4.0)
        max_daily_loss_r = self._as_float(settings.get("LIVE_MAX_DAILY_LOSS_R"), 3.0)
        symbol_allowlist = [item.upper() for item in split_csv(settings.get("AUTO_LIVE_SYMBOL_ALLOWLIST"))]
        max_concurrent_positions = self._safe_int(settings.get("AUTO_LIVE_MAX_CONCURRENT_POSITIONS"))
        global_kill = self._is_truthy(settings.get("AUTO_LIVE_GLOBAL_KILL_SWITCH"))
        profile_kill = self._is_truthy(settings.get("AUTO_LIVE_PROFILE_KILL_SWITCH"))
        current_open_r = sum(
            self._as_float((item.get("payload") or {}).get("risk_audit", {}).get("entry_r_multiple"))
            for item in orders
            if str(item.get("execution_mode") or "").upper() == "LIVE" and bool(item.get("is_open"))
        )
        current_daily_loss_r = sum(
            abs(self._as_float(item.get("realized_r")))
            for item in orders
            if str(item.get("execution_mode") or "").upper() == "LIVE" and self._is_today(item.get("closed_at_utc")) and self._as_float(item.get("realized_r")) < 0
        )
        local_open_symbols = {
            str(item.get("symbol") or "").upper()
            for item in orders
            if str(item.get("execution_mode") or "").upper() == "LIVE" and bool(item.get("is_open"))
        }
        venue_position_symbols = {
            str(item.get("symbol") or "").upper()
            for item in venue_positions
            if abs(self._as_float(item.get("quantity"))) > 0.0
        }
        venue_open_order_symbols = {
            str(item.get("symbol") or "").upper()
            for item in venue_open_orders
            if str(item.get("status") or "").upper() in {"NEW", "PARTIALLY_FILLED", "PENDING_CANCEL"}
        }
        open_symbols = {symbol for symbol in (*local_open_symbols, *venue_position_symbols, *venue_open_order_symbols) if symbol}
        ambiguity_backlog = [
            item for item in orders
            if str(item.get("execution_mode") or "").upper() == "LIVE"
            and (
                str(item.get("submission_status") or "").upper() in {"AMBIGUOUS_UNRESOLVED", "PENDING_SUBMIT_VERIFICATION", "CANCEL_PENDING_VERIFICATION"}
                or bool((item.get("ambiguity") or {}).get("active"))
            )
        ]
        degraded_protection_backlog = [
            item for item in orders
            if str(item.get("execution_mode") or "").upper() == "LIVE"
            and bool(item.get("is_open"))
            and str(item.get("protection_status") or "PENDING").upper() in {"PENDING", "DEGRADED", "FAILED"}
        ]

        posture = "DISABLED"
        if execution_mode != "LIVE" or venue != BINANCE_USDM_VENUE:
            reasons.append(self._reason("NOT_LIVE_AUTO_TARGET", "Auto-live posture is only applicable to Binance USDⓈ-M live profiles in this slice."))
        elif bool(profile.get("read_only")):
            posture = "READ_ONLY"
            reasons.append(self._reason("PROFILE_READ_ONLY", "Profile is explicitly read-only."))
        elif not bool(profile.get("manual_trading_enabled")) and not bool(profile.get("auto_trading_enabled")):
            reasons.append(self._reason("LIVE_DISABLED", "Live trading is disabled for this profile."))
        elif not bool(profile.get("auto_trading_enabled")) or not bool(profile.get("default_for_auto_trading")):
            posture = "MANUAL_LIVE"
            reasons.append(self._reason("AUTO_LIVE_NOT_ENABLED", "Profile allows manual live but is not enabled for autonomous live."))
        else:
            posture = "AUTO_LIVE_ENABLED"

        if posture == "AUTO_LIVE_ENABLED":
            if global_kill:
                posture = "BLOCKED"
                reasons.append(self._reason("GLOBAL_AUTO_LIVE_KILL_SWITCH", "Global auto-live kill switch is enabled."))
            if profile_kill:
                posture = "BLOCKED"
                reasons.append(self._reason("PROFILE_AUTO_LIVE_KILL_SWITCH", "Profile auto-live kill switch is enabled."))
            if connectivity_status not in {"CONNECTED", "READY"}:
                posture = "DEGRADED"
                reasons.append(self._reason("CONNECTIVITY_NOT_READY", "Venue connectivity posture is not ready for autonomous live.", detail={"connectivity_status": connectivity_status}))
            if reconciliation_status not in {"READY", "WARNING"}:
                posture = "DEGRADED"
                reasons.append(self._reason("RECONCILIATION_NOT_READY", "Reconciliation posture is missing or degraded for autonomous live.", detail={"reconciliation_status": reconciliation_status}))
            if stream_status in {"DEGRADED", "EXPIRED"} or bool(stream.get("reconnect_required")):
                posture = "DEGRADED"
                reasons.append(self._reason("STREAM_DEGRADED", "User data stream posture is degraded for autonomous live.", detail={"stream_status": stream_status, "reconnect_required": bool(stream.get("reconnect_required"))}))
            if ambiguity_backlog:
                posture = "DEGRADED"
                reasons.append(self._reason("AMBIGUITY_BACKLOG", "Unresolved live ambiguity backlog blocks autonomous live.", detail={"count": len(ambiguity_backlog)}))
            if degraded_protection_backlog:
                posture = "DEGRADED"
                reasons.append(self._reason("PROTECTION_BACKLOG", "Existing live orders have missing or degraded protection posture.", detail={"count": len(degraded_protection_backlog)}))
            if not symbol_allowlist:
                posture = "BLOCKED"
                reasons.append(self._reason("MISSING_SYMBOL_ALLOWLIST", "Auto-live symbol allowlist is not configured."))
            if max_concurrent_positions is None or max_concurrent_positions <= 0:
                posture = "BLOCKED"
                reasons.append(self._reason("MISSING_MAX_CONCURRENT_POSITIONS", "Auto-live max concurrent positions is not configured."))

            risk_basis_amount = self._risk_basis_amount(account, risk_basis)
            one_r_value = round(risk_basis_amount * risk_per_trade_pct, 8)
            trade_risk_budget = round(one_r_value * entry_r_multiple, 8)
            projected_total_open_r = round(current_open_r + entry_r_multiple, 8)
            if entry_r_multiple > max_position_r:
                posture = "BLOCKED"
                reasons.append(self._reason("MAX_POSITION_R_EXCEEDED", "Candidate entry R exceeds profile max position R.", detail={"entry_r_multiple": entry_r_multiple, "max_position_r": max_position_r}))
            if projected_total_open_r > max_total_open_r:
                posture = "BLOCKED"
                reasons.append(self._reason("MAX_TOTAL_OPEN_R_EXCEEDED", "Projected total open R exceeds profile limit.", detail={"projected_total_open_r": projected_total_open_r, "max_total_open_r": max_total_open_r}))
            if current_daily_loss_r >= max_daily_loss_r:
                posture = "BLOCKED"
                reasons.append(self._reason("MAX_DAILY_LOSS_R_EXCEEDED", "Profile daily loss R limit has been reached.", detail={"daily_loss_r": current_daily_loss_r, "max_daily_loss_r": max_daily_loss_r}))
            candidate_symbol = str(candidate.get("symbol") or "").upper()
            if candidate_symbol and candidate_symbol not in symbol_allowlist:
                posture = "BLOCKED"
                reasons.append(self._reason("SYMBOL_NOT_ALLOWED", "Candidate symbol is outside the auto-live allowlist.", detail={"symbol": candidate_symbol, "allowlist": symbol_allowlist}))
            if candidate_symbol and candidate_symbol in open_symbols:
                posture = "BLOCKED"
                reasons.append(self._reason("SYMBOL_ALREADY_OPEN", "Candidate symbol already has an active Binance-tracked live position or order.", detail={"symbol": candidate_symbol}))
            projected_positions = len(open_symbols) + (1 if candidate_symbol and candidate_symbol not in open_symbols else 0)
            if max_concurrent_positions and projected_positions > max_concurrent_positions:
                posture = "BLOCKED"
                reasons.append(self._reason("MAX_CONCURRENT_POSITIONS_EXCEEDED", "Candidate trade would exceed max concurrent positions.", detail={"projected_positions": projected_positions, "max_concurrent_positions": max_concurrent_positions}))

        return {
            "profile_id": profile_id,
            "posture": posture,
            "eligible": posture == "AUTO_LIVE_ENABLED",
            "blocked": posture in {"BLOCKED", "DEGRADED", "READ_ONLY", "MANUAL_LIVE", "DISABLED"},
            "reasons": reasons,
            "reason_codes": [item["code"] for item in reasons],
            "kill_switches": {
                "global_auto_live": global_kill,
                "profile_auto_live": profile_kill,
            },
            "policy": {
                "risk_basis": risk_basis,
                "risk_per_trade_pct": risk_per_trade_pct,
                "default_entry_r_multiple": self._as_float(settings.get("LIVE_DEFAULT_ENTRY_R_MULTIPLE"), 1.0),
                "max_position_r": max_position_r,
                "max_total_open_r": max_total_open_r,
                "max_daily_loss_r": max_daily_loss_r,
                "symbol_allowlist": symbol_allowlist,
                "max_concurrent_positions": max_concurrent_positions,
            },
            "metrics": {
                "one_r_value": one_r_value,
                "entry_r_multiple": round(entry_r_multiple, 8),
                "trade_risk_budget": trade_risk_budget,
                "current_total_open_r": round(current_open_r, 8),
                "projected_total_open_r": projected_total_open_r,
                "current_daily_loss_r": round(current_daily_loss_r, 8),
                "current_open_positions": len(open_symbols),
            },
            "dependencies": {
                "connectivity_status": connectivity_status,
                "reconciliation_status": reconciliation_status,
                "stream_status": stream_status,
                "stream_reconnect_required": bool(stream.get("reconnect_required")),
                "ambiguity_backlog_count": len(ambiguity_backlog),
                "degraded_protection_count": len(degraded_protection_backlog),
            },
        }

    def record_auto_live_attempt(self, profile_id: str, attempt: dict[str, Any]) -> dict[str, Any]:
        normalized_attempt = self._normalize_auto_live_attempt(attempt)
        with session_scope() as session:
            existing = self.state_repo.get(session, AUTO_LIVE_ACTIVITY_STATE_KEY, default=[], profile_id=profile_id)
            items = [normalized_attempt, *self._normalize_auto_live_activity(existing)]
            self.state_repo.set(session, AUTO_LIVE_ACTIVITY_STATE_KEY, items[:AUTO_LIVE_ACTIVITY_LIMIT], profile_id=profile_id)
        return normalized_attempt

    @staticmethod
    def _normalize_auto_live_activity(items: Any) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]

    def _normalize_auto_live_attempt(self, attempt: dict[str, Any]) -> dict[str, Any]:
        decision = dict(attempt.get("decision") or {})
        order = dict(attempt.get("order") or {})
        protection = dict(attempt.get("protection") or {})
        reason_codes = [str(item) for item in list(attempt.get("reason_codes") or []) if str(item)]
        return {
            "recorded_at_utc": str(attempt.get("recorded_at_utc") or self._utc_now_iso()),
            "profile_id": str(attempt.get("profile_id") or ""),
            "outcome": str(attempt.get("outcome") or "UNKNOWN").upper(),
            "posture": str(attempt.get("posture") or "UNKNOWN").upper(),
            "message": str(attempt.get("message") or "").strip() or None,
            "reason_codes": reason_codes,
            "decision": {
                "decision_id": decision.get("decision_id"),
                "signal_id": decision.get("signal_id"),
                "decision_event_id": decision.get("decision_event_id"),
                "request_id": decision.get("request_id"),
                "run_id": decision.get("run_id"),
                "symbol": decision.get("symbol"),
                "interval": decision.get("interval"),
                "mode": decision.get("mode"),
                "direction": decision.get("direction"),
                "entry_r_multiple": decision.get("entry_r_multiple"),
            },
            "order": {
                "order_id": order.get("order_id"),
                "client_order_id": order.get("client_order_id"),
                "venue_order_id": order.get("venue_order_id"),
                "submission_status": order.get("submission_status"),
                "status": order.get("status"),
            },
            "protection": {
                "status": protection.get("status"),
                "safe_to_consider_active": protection.get("safe_to_consider_active"),
                "message": protection.get("message"),
            },
        }

    @staticmethod
    def _normalize_environment(raw_value: Any) -> str:
        value = str(raw_value or "PRODUCTION").strip().upper().replace("-", "_")
        aliases = {
            "PROD": "PRODUCTION",
            "PRODUCTION": "PRODUCTION",
            "LIVE": "PRODUCTION",
            "TEST": "TESTNET",
            "TESTNET": "TESTNET",
            "SANDBOX": "TESTNET",
            "INTERNAL": "INTERNAL",
        }
        return aliases.get(value, value or "PRODUCTION")

    @staticmethod
    def _credential_env_prefix(credential_ref: str) -> str:
        return re.sub(r"[^A-Z0-9]+", "_", str(credential_ref or "").upper()).strip("_")

    def _request_json(self, method: str, url: str, *, headers: dict[str, str] | None = None) -> dict[str, Any] | list[Any]:
        timeout_seconds = self._request_timeout_seconds()
        attempts = self._request_attempts()
        last_error: requests.RequestException | None = None
        for attempt in range(1, attempts + 1):
            try:
                response = self.http_session.request(method, url, headers=headers, timeout=timeout_seconds)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, (dict, list)):
                    raise RuntimeProfileConnectivityError("Connectivity probe returned a non-JSON payload.")
                return payload
            except requests.RequestException as exc:
                last_error = exc
                if attempt < attempts and self._is_retryable_request_error(exc):
                    continue
                detail = ""
                response = getattr(exc, "response", None)
                if response is not None:
                    status_code = getattr(response, "status_code", None)
                    response_message = None
                    response_code = None
                    try:
                        error_payload = response.json()
                    except ValueError:
                        error_payload = None
                    if isinstance(error_payload, dict):
                        response_message = error_payload.get("msg") or error_payload.get("message")
                        response_code = error_payload.get("code")
                    elif getattr(response, "text", None):
                        response_message = str(response.text).strip()
                    parts = []
                    if status_code is not None:
                        parts.append(f"HTTP {status_code}")
                    if response_code not in (None, ""):
                        parts.append(f"code {response_code}")
                    if response_message:
                        parts.append(str(response_message))
                    if parts:
                        detail = f" ({' · '.join(parts)})"
                raise RuntimeProfileConnectivityError(f"Connectivity probe failed: {exc}{detail}") from exc
        assert last_error is not None
        raise RuntimeProfileConnectivityError(f"Connectivity probe failed: {last_error}") from last_error

    def _signed_request_json(
        self,
        method: str,
        base_url: str,
        path: str,
        *,
        api_key: str,
        api_secret: str,
        params: dict[str, Any],
    ) -> dict[str, Any] | list[Any]:
        encoded = urlencode(params)
        signature = hmac.new(api_secret.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()
        separator = "?" if encoded else ""
        return self._request_json(
            method.upper(),
            f"{base_url}{path}{separator}{encoded}&signature={signature}" if encoded else f"{base_url}{path}?signature={signature}",
            headers={"X-MBX-APIKEY": api_key},
        )

    @staticmethod
    def _reason(code: str, message: str, *, detail: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"code": code, "message": message}
        if detail:
            payload["detail"] = detail
        return payload

    @staticmethod
    def _risk_basis_amount(account: dict[str, Any], risk_basis: str) -> float:
        if risk_basis == "EQUITY":
            return max(0.0, RuntimeProfileService._as_float(account.get("equity")))
        if risk_basis == "WALLET_BALANCE":
            return max(0.0, RuntimeProfileService._as_float(account.get("balance")))
        return max(0.0, RuntimeProfileService._as_float(account.get("available_balance")))

    @staticmethod
    def _is_truthy(value: Any) -> bool:
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _as_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            parsed = int(float(value))
        except (TypeError, ValueError):
            return None
        return parsed

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
    def _is_retryable_request_error(exc: requests.RequestException) -> bool:
        return isinstance(exc, (requests.Timeout, requests.ConnectionError)) and getattr(exc, "response", None) is None

    def _request_timeout_seconds(self) -> float:
        try:
            with session_scope() as session:
                val = self.settings_repo.get_value(session, "BINANCE_HTTP_TIMEOUT_SECONDS", default="10")
            return max(1.0, float(val))
        except (TypeError, ValueError, Exception):
            return 10.0

    def _request_attempts(self) -> int:
        try:
            with session_scope() as session:
                val = self.settings_repo.get_value(session, "BINANCE_HTTP_RETRY_COUNT", default="3")
            return max(1, int(float(val)))
        except (TypeError, ValueError, Exception):
            return 3

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _epoch_ms() -> int:
        return int(datetime.now(timezone.utc).timestamp() * 1000)


__all__ = [
    "BINANCE_USDM_PROFILE_ID",
    "BINANCE_USDM_PRODUCTION_BASE_URL",
    "BINANCE_USDM_TESTNET_BASE_URL",
    "BINANCE_USDM_VENUE",
    "RuntimeProfileAccessError",
    "RuntimeProfileConnectivityError",
    "RuntimeProfileNotFoundError",
    "RuntimeProfileService",
]
