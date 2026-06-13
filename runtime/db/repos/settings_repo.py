"""Runtime settings repository for v4 with profile-aware resolution."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from runtime.db.models import (
    ConfigTemplate,
    ProfileConfigImport,
    ProfileConfigOverride,
    ResolvedProfileConfig,
    RuntimeSetting,
)
from runtime.db.repos._helpers import dumps_json, loads_json
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.services.binance_client import DEFAULT_SCAN_SYMBOLS, sanitize_scan_symbols

SUPPORTED_AUTONOMOUS_INTERVALS = ("15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "3d", "7d", "14d", "1M")
RUNTIME_DEFAULT_TEMPLATE_ID = "runtime-defaults"

DEFAULT_RUNTIME_SETTINGS: dict[str, str] = {
    "AUTONOMOUS_ENABLED": "false",
    "AUTONOMOUS_SYMBOLS": ",".join(DEFAULT_SCAN_SYMBOLS),
    "AUTONOMOUS_INTERVALS": "15m,30m,1h,4h,1d,3d,7d,14d,1M",
    "AUTONOMOUS_INTERVALS_SCALP": "15m,30m,1h,4h",
    "AUTONOMOUS_INTERVALS_SWING": "1h,4h,1d,3d,7d",
    "AUTONOMOUS_INTERVALS_AGGRESSIVE_SCALP": "15m,1h,4h",
    "AUTONOMOUS_MODES": "SCALP,SWING,AGGRESSIVE_SCALP",
    "AUTONOMOUS_SCAN_INTERVAL_SECONDS": "900",
    "AUTONOMOUS_MONITOR_INTERVAL_SECONDS": "15",
    "AUTONOMOUS_SCAN_WORKERS": "4",
    "AUTONOMOUS_INFERENCE_WORKERS": "1",
    "AUTONOMOUS_INFERENCE_QUEUE_SIZE": "64",
    "AUTONOMOUS_MIN_CONFIDENCE": "35",
    "AUTONOMOUS_ALLOWED_TRADE_DIRECTIONS": "BOTH",
    "AUTONOMOUS_CONFIDENCE_POLICY": "FIXED",
    "AUTONOMOUS_CONFIDENCE_PERCENTILE": "0.90",
    "AUTONOMOUS_CONFIDENCE_LOOKBACK_TRACES": "200",
    "AUTONOMOUS_CONFIDENCE_MIN_SAMPLES": "50",
    "AUTONOMOUS_CONFIDENCE_MIN_FLOOR": "20",
    "AUTONOMOUS_CONFIDENCE_MAX_CEIL": "40",
    "SCAN_FETCH_TIMEOUT_SECONDS": "90",
    "MAX_TRADES_PER_DAY": "5",
    "POST_SCAN_CONFIDENCE_RANKED_ENTRY_ENABLED": "false",
    "PAPER_DEFAULT_BALANCE": "100",
    "PAPER_POSITION_SIZE_MIN_PCT": "2",
    "PAPER_POSITION_SIZE_MAX_PCT": "12",
    "PAPER_POSITION_CONFIDENCE_FLOOR": "60",
    "PAPER_POSITION_CONFIDENCE_CEIL": "90",
    "PAPER_ALLOW_UNFUNDED_TRADES": "true",
    "LIVE_RISK_MODEL": "FIXED_R",
    "LIVE_RISK_BASIS": "AVAILABLE_BALANCE",
    "LIVE_RISK_PER_TRADE_PCT": "0.01",
    "LIVE_DEFAULT_ENTRY_R_MULTIPLE": "1.0",
    "LIVE_MAX_POSITION_R": "2.0",
    "LIVE_MAX_TOTAL_OPEN_R": "4.0",
    "LIVE_MAX_DAILY_LOSS_R": "3.0",
    "LIVE_MAX_LEVERAGE": "1",
    "AUTO_LIVE_GLOBAL_KILL_SWITCH": "false",
    "AUTO_LIVE_PROFILE_KILL_SWITCH": "false",
    "AUTO_LIVE_SYMBOL_ALLOWLIST": "",
    "AUTO_LIVE_MAX_CONCURRENT_POSITIONS": "0",
    "LEARNING_LOOKBACK_DAYS": "30",
    "LEARNING_MIN_CONFIDENCE": "0.6",
    "LEARNING_REFRESH_SECONDS": "300",
    "LEARNING_ENGINE_ENABLED": "true",
    "LEARNING_CALIBRATION_ENABLED": "false",
    "LEARNING_ADAPTIVE_STOP_ENABLED": "false",
    "V6_ACTIONABILITY_CONFIDENCE_ENABLED": "true",
    "PHASE24_ENABLED": "false",
    "PHASE24_ENABLED_MODES": "SWING",
    "PHASE24_ROLLOUT_STAGE": "FOUNDATION_ONLY",
    "PHASE24_ACTION_POLICY_ENABLED": "false",
    "PHASE24_ALLOWED_ACTIONS": "NO_TRADE,REDUCE_SIZE_25_PCT,WAIT_1_CANDLE",
    "PHASE24_INFERENCE_TIMEOUT_MS": "250",
    "ANALYZER_ACTIVE_ENGINE": "v4_default",
    "ANALYZER_ENGINE_TIMEOUT_MS": "2500",
    "STATIC_ENGINE_EMIT_THRESHOLD": "0.45",
    "EXECUTION_CONFIDENCE_THRESHOLD": "0.60",
    "EXECUTION_GATE_OWNER": "static_engine",
    "SESSION_NEW_YORK_ENABLED": "false",
    "CIRCUIT_BREAKER_ENABLED": "true",
    "CIRCUIT_BREAKER_LOOKBACK_TRADES": "10",
    "CIRCUIT_BREAKER_MAX_CONSECUTIVE_LOSSES": "5",
    "CIRCUIT_BREAKER_MAX_FAILURE_RATE_PCT": "70",
    "CIRCUIT_BREAKER_MAX_SEVERITY_AVG": "4.0",
    "CIRCUIT_BREAKER_COOLDOWN_MINUTES": "60",
    "CIRCUIT_BREAKER_DEGRADED_MULTIPLIER": "0.7",
    "CIRCUIT_BREAKER_MANUAL_MODE": "AUTO",
    "SYMBOL_THROTTLE_ENABLED": "true",
    "SYMBOL_THROTTLE_LOOKBACK_TRADES": "12",
    "SYMBOL_THROTTLE_MAX_CONSECUTIVE_STOP_HITS": "3",
    "SYMBOL_THROTTLE_MAX_STOP_HIT_RATE_PCT": "70",
    "SYMBOL_THROTTLE_COOLDOWN_MINUTES": "240",
    "SYMBOL_THROTTLE_SEEDED_SYMBOLS": "BFUSDUSDT,COMPUSDT,DOGEUSDT",
    "WS_RUNTIME_ENABLED": "true",
    "WS_KEEPALIVE_INTERVAL_SECONDS": "1500",
    "WS_RECONNECT_INTERVAL_SECONDS": "5",
    "WS_RECONNECT_MAX_ATTEMPTS": "5",
    "WS_STALE_STREAM_THRESHOLD_SECONDS": "3300",
    "WS_ROTATION_BEFORE_EXPIRY_SECONDS": "3000",
    "WS_RECEIVE_TIMEOUT_SECONDS": "30",
    "BINANCE_HTTP_TIMEOUT_SECONDS": "10",
    "BINANCE_HTTP_RETRY_COUNT": "3",
    "TRADE_HISTORY_REFRESH_HOURS": "6",
    "TRADE_HISTORY_MAX_SYMBOLS": "12",
    "TRADE_HISTORY_LOOKBACK_DAYS": "30",
    "ORDER_HISTORY_LOOKBACK_DAYS": "89",
    "LISTEN_KEY_EXPIRE_MINUTES": "60",
    "VENUE_FLAT_SYNC_MIN_AGE_SECONDS": "30",
    "SIMULATION_DIAGNOSTICS_LOW_CONFIDENCE_THRESHOLD": "35",
    "SIMULATION_EXPORT_ROW_LIMIT": "5000",
    "SIMULATION_MAX_SCAN_WORKERS": "4",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def resolve_mode_intervals(settings: dict[str, str], modes: list[str], global_intervals: list[str]) -> dict[str, list[str]]:
    global_allowed = [item for item in global_intervals if item in SUPPORTED_AUTONOMOUS_INTERVALS]
    if not global_allowed:
        global_allowed = list(SUPPORTED_AUTONOMOUS_INTERVALS)

    resolved: dict[str, list[str]] = {}
    for mode in modes:
        key = f"AUTONOMOUS_INTERVALS_{str(mode).upper()}"
        requested = [item for item in split_csv(settings.get(key)) if item in SUPPORTED_AUTONOMOUS_INTERVALS]
        allowed = [item for item in requested if item in global_allowed]
        resolved[str(mode).upper()] = allowed or list(global_allowed)
    return resolved


class SettingsRepository:
    def get_all(self, session: Session, profile_id: str = PAPER_PROFILE_ID) -> dict[str, str]:
        return self.get_resolution(session, profile_id=profile_id, materialize=False)["settings"]

    def get_resolution(self, session: Session, profile_id: str = PAPER_PROFILE_ID, *, materialize: bool = False) -> dict[str, object]:
        resolved_profile_id = str(profile_id or PAPER_PROFILE_ID)
        self._ensure_default_template(session)
        self._ensure_profile_import(session, resolved_profile_id)

        settings = dict(DEFAULT_RUNTIME_SETTINGS)
        template_chain: list[dict[str, object]] = []
        imported_template_ids: list[str] = []
        import_rows = (
            session.query(ProfileConfigImport)
            .filter(ProfileConfigImport.profile_id == resolved_profile_id)
            .order_by(ProfileConfigImport.import_order.asc(), ProfileConfigImport.id.asc())
            .all()
        )
        if not import_rows:
            import_rows = [
                ProfileConfigImport(
                    profile_id=resolved_profile_id,
                    template_id=RUNTIME_DEFAULT_TEMPLATE_ID,
                    import_order=0,
                    created_at_utc=utc_now_iso(),
                    updated_at_utc=utc_now_iso(),
                )
            ]

        for import_row in import_rows:
            chain = self._resolve_template_chain(session, import_row.template_id, seen=set())
            for template in chain:
                template_id = str(template.get("template_id") or "")
                if template_id and template_id not in imported_template_ids:
                    imported_template_ids.append(template_id)
                    settings.update(dict(template.get("settings") or {}))
                    template_chain.append(template)

        legacy_global = self._legacy_global_settings(session)
        settings.update(legacy_global)

        overrides: dict[str, str] = {}
        override_rows = (
            session.query(ProfileConfigOverride)
            .filter(ProfileConfigOverride.profile_id == resolved_profile_id)
            .order_by(ProfileConfigOverride.key.asc())
            .all()
        )
        for row in override_rows:
            normalized = self._normalize_value(row.key, row.value, settings.get(row.key))
            value = normalized if normalized is not None else row.value
            overrides[row.key] = value
            settings[row.key] = value

        resolved_config_hash = self._resolved_hash(settings)
        provenance = {
            "profile_id": resolved_profile_id,
            "template_ids": imported_template_ids,
            "template_chain": template_chain,
            "legacy_global_keys": sorted(legacy_global.keys()),
            "override_keys": sorted(overrides.keys()),
        }
        payload = {
            "profile_id": resolved_profile_id,
            "settings": settings,
            "resolved_config_hash": resolved_config_hash,
            "provenance": provenance,
        }
        if materialize:
            self._materialize_resolution(session, payload)
        return payload

    def get_value(self, session: Session, key: str, default: str | None = None, profile_id: str = PAPER_PROFILE_ID) -> str | None:
        settings = self.get_all(session, profile_id=profile_id)
        if key in settings:
            return settings[key]
        return default

    def save_many(self, session: Session, values: dict[str, str], profile_id: str = PAPER_PROFILE_ID) -> dict[str, str]:
        resolved_profile_id = str(profile_id or PAPER_PROFILE_ID)
        self._ensure_default_template(session)
        self._ensure_profile_import(session, resolved_profile_id)
        baseline = self.get_all(session, profile_id=resolved_profile_id)
        timestamp = utc_now_iso()
        for key, value in values.items():
            normalized = self._normalize_value(key, value, baseline.get(key) or DEFAULT_RUNTIME_SETTINGS.get(key))
            stored = normalized if normalized is not None else str(value)
            row = (
                session.query(ProfileConfigOverride)
                .filter(ProfileConfigOverride.profile_id == resolved_profile_id)
                .filter(ProfileConfigOverride.key == key)
                .one_or_none()
            )
            if row is None:
                session.add(ProfileConfigOverride(profile_id=resolved_profile_id, key=key, value=stored, updated_at_utc=timestamp))
            else:
                row.value = stored
                row.updated_at_utc = timestamp
        session.commit()
        resolution = self.get_resolution(session, profile_id=resolved_profile_id, materialize=True)
        return dict(resolution["settings"])

    def delete_key(self, session: Session, key: str, profile_id: str = PAPER_PROFILE_ID) -> None:
        row = (
            session.query(ProfileConfigOverride)
            .filter(ProfileConfigOverride.profile_id == str(profile_id or PAPER_PROFILE_ID))
            .filter(ProfileConfigOverride.key == key)
            .one_or_none()
        )
        if row:
            session.delete(row)
            session.commit()

    def ensure_profile_defaults(self, session: Session, profile_id: str = PAPER_PROFILE_ID) -> dict[str, object]:
        return self.get_resolution(session, profile_id=profile_id, materialize=True)

    def _ensure_default_template(self, session: Session) -> None:
        row = session.query(ConfigTemplate).filter(ConfigTemplate.template_id == RUNTIME_DEFAULT_TEMPLATE_ID).one_or_none()
        payload = dumps_json(DEFAULT_RUNTIME_SETTINGS)
        timestamp = utc_now_iso()
        if row is None:
            session.add(
                ConfigTemplate(
                    template_id=RUNTIME_DEFAULT_TEMPLATE_ID,
                    name="Runtime Defaults",
                    base_template_id=None,
                    scope="RUNTIME",
                    status="ACTIVE",
                    settings_json=payload,
                    created_at_utc=timestamp,
                    updated_at_utc=timestamp,
                )
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
        elif row.settings_json != payload:
            row.settings_json = payload
            row.updated_at_utc = timestamp
            session.commit()

    def _ensure_profile_import(self, session: Session, profile_id: str) -> None:
        existing = (
            session.query(ProfileConfigImport)
            .filter(ProfileConfigImport.profile_id == profile_id)
            .count()
        )
        if existing > 0:
            return
        timestamp = utc_now_iso()
        session.add(
            ProfileConfigImport(
                profile_id=profile_id,
                template_id=RUNTIME_DEFAULT_TEMPLATE_ID,
                import_order=0,
                created_at_utc=timestamp,
                updated_at_utc=timestamp,
            )
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()

    def _resolve_template_chain(self, session: Session, template_id: str, *, seen: set[str]) -> list[dict[str, object]]:
        normalized = str(template_id or "").strip()
        if not normalized or normalized in seen:
            return []
        seen.add(normalized)
        row = session.query(ConfigTemplate).filter(ConfigTemplate.template_id == normalized).one_or_none()
        if row is None:
            return []
        chain = self._resolve_template_chain(session, row.base_template_id or "", seen=seen)
        chain.append(
            {
                "template_id": row.template_id,
                "name": row.name,
                "base_template_id": row.base_template_id,
                "settings": loads_json(row.settings_json, {}),
            }
        )
        return chain

    def _legacy_global_settings(self, session: Session) -> dict[str, str]:
        values: dict[str, str] = {}
        rows = session.query(RuntimeSetting).order_by(RuntimeSetting.key.asc()).all()
        for row in rows:
            normalized = self._normalize_value(row.key, row.value, DEFAULT_RUNTIME_SETTINGS.get(row.key))
            values[row.key] = normalized if normalized is not None else row.value
        return values

    def _materialize_resolution(self, session: Session, resolution: dict[str, object]) -> None:
        profile_id = str(resolution["profile_id"])
        row = session.query(ResolvedProfileConfig).filter(ResolvedProfileConfig.profile_id == profile_id).one_or_none()
        timestamp = utc_now_iso()
        if row is None:
            row = ResolvedProfileConfig(
                profile_id=profile_id,
                resolved_config_hash=str(resolution["resolved_config_hash"]),
                settings_json=dumps_json(resolution["settings"]),
                provenance_json=dumps_json(resolution["provenance"]),
                updated_at_utc=timestamp,
            )
            session.add(row)
        else:
            row.resolved_config_hash = str(resolution["resolved_config_hash"])
            row.settings_json = dumps_json(resolution["settings"])
            row.provenance_json = dumps_json(resolution["provenance"])
            row.updated_at_utc = timestamp
        session.commit()

    @staticmethod
    def _resolved_hash(settings: dict[str, str]) -> str:
        payload = json.dumps(settings, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_value(key: str, value: str | None, default: str | None) -> str | None:
        text = "" if value is None else str(value).strip()
        if not text and default is not None:
            return default
        if key == "AUTONOMOUS_SYMBOLS":
            symbols = sanitize_scan_symbols(text.split(","))
            return ",".join(symbols) if symbols else default
        if key == "AUTONOMOUS_INTERVALS" or key.startswith("AUTONOMOUS_INTERVALS_"):
            intervals = [item.strip() for item in text.split(",") if item.strip() in SUPPORTED_AUTONOMOUS_INTERVALS]
            if not intervals:
                return default
            deduped = list(dict.fromkeys(intervals))
            return ",".join(deduped)
        if key == "AUTONOMOUS_ENABLED":
            return "true" if text.lower() in {"1", "true", "yes", "on"} else "false"
        if key == "AUTONOMOUS_CONFIDENCE_POLICY":
            normalized = text.strip().upper()
            if normalized not in {"FIXED", "PERCENTILE"}:
                return default or "FIXED"
            return normalized
        if key == "LIVE_RISK_MODEL":
            normalized = text.strip().upper().replace("-", "_")
            return normalized if normalized in {"FIXED_R"} else (default or "FIXED_R")
        if key == "LIVE_RISK_BASIS":
            normalized = text.strip().upper().replace("-", "_")
            allowed = {"AVAILABLE_BALANCE", "EQUITY", "WALLET_BALANCE"}
            return normalized if normalized in allowed else (default or "AVAILABLE_BALANCE")
        if key in {
            "LIVE_RISK_PER_TRADE_PCT",
            "LIVE_DEFAULT_ENTRY_R_MULTIPLE",
            "LIVE_MAX_POSITION_R",
            "LIVE_MAX_TOTAL_OPEN_R",
            "LIVE_MAX_DAILY_LOSS_R",
        }:
            try:
                parsed = float(text)
            except (TypeError, ValueError):
                return default
            if parsed < 0:
                return default
            return str(parsed)
        if key == "LIVE_MAX_LEVERAGE":
            try:
                parsed = int(float(text))
            except (TypeError, ValueError):
                return default or "1"
            if parsed < 1:
                return default or "1"
            return str(min(parsed, 125))
        if key == "AUTONOMOUS_ALLOWED_TRADE_DIRECTIONS":
            normalized = text.strip().upper().replace("-", "_").replace(" ", "_")
            aliases = {
                "LONG": "LONG_ONLY",
                "BUY": "LONG_ONLY",
                "BUY_ONLY": "LONG_ONLY",
                "LONG_ONLY": "LONG_ONLY",
                "SHORT": "SHORT_ONLY",
                "SELL": "SHORT_ONLY",
                "SELL_ONLY": "SHORT_ONLY",
                "SHORT_ONLY": "SHORT_ONLY",
                "BOTH": "BOTH",
                "ALL": "BOTH",
                "LONG_AND_SHORT": "BOTH",
            }
            return aliases.get(normalized, default or "BOTH")
        if key in {
            "LEARNING_ENGINE_ENABLED",
            "LEARNING_CALIBRATION_ENABLED",
            "LEARNING_ADAPTIVE_STOP_ENABLED",
            "V6_ACTIONABILITY_CONFIDENCE_ENABLED",
            "PHASE24_ENABLED",
            "PHASE24_ACTION_POLICY_ENABLED",
            "SESSION_NEW_YORK_ENABLED",
            "CIRCUIT_BREAKER_ENABLED",
            "SYMBOL_THROTTLE_ENABLED",
            "PAPER_ALLOW_UNFUNDED_TRADES",
            "AUTO_LIVE_GLOBAL_KILL_SWITCH",
            "AUTO_LIVE_PROFILE_KILL_SWITCH",
            "POST_SCAN_CONFIDENCE_RANKED_ENTRY_ENABLED",
        }:
            return "true" if text.lower() in {"1", "true", "yes", "on"} else "false"
        if key == "PHASE24_ENABLED_MODES":
            values = [item.strip().upper() for item in text.split(",") if item.strip()]
            return ",".join(list(dict.fromkeys(values))) if values else default
        if key == "PHASE24_ALLOWED_ACTIONS":
            values = [item.strip().upper() for item in text.split(",") if item.strip()]
            return ",".join(list(dict.fromkeys(values))) if values else default
        if key == "PHASE24_ROLLOUT_STAGE":
            normalized = text.upper()
            if normalized not in {"NOT_READY", "FOUNDATION_ONLY", "TRAINING_READY", "CANDIDATE_READY", "PROMOTION_READY", "SHADOW", "ACTIVE"}:
                return default or "FOUNDATION_ONLY"
            return normalized
        if key == "ANALYZER_ACTIVE_ENGINE":
            return text.strip() or (default or "v4_default")
        if key == "EXECUTION_GATE_OWNER":
            normalized = text.strip().lower()
            if normalized not in {"static_engine", "v5"}:
                return default or "static_engine"
            return normalized
        if key == "CIRCUIT_BREAKER_MANUAL_MODE":
            normalized = text.upper()
            if normalized not in {"AUTO", "FORCE_OPEN", "FORCE_CLOSED"}:
                return default or "AUTO"
            return normalized
        if key == "AUTO_LIVE_SYMBOL_ALLOWLIST":
            symbols = sanitize_scan_symbols(text.split(","))
            return ",".join(symbols) if symbols else ""
        if key == "AUTO_LIVE_MAX_CONCURRENT_POSITIONS":
            try:
                parsed = int(float(text))
            except (TypeError, ValueError):
                return default
            return str(parsed) if parsed >= 0 else default
        if key == "SYMBOL_THROTTLE_SEEDED_SYMBOLS":
            symbols = sanitize_scan_symbols(text.split(","))
            return ",".join(symbols) if symbols else default
        if key == "WS_RUNTIME_ENABLED":
            return "true" if text.lower() in {"1", "true", "yes", "on"} else "false"
        if key in {
            "WS_KEEPALIVE_INTERVAL_SECONDS",
            "WS_RECONNECT_INTERVAL_SECONDS",
            "WS_RECONNECT_MAX_ATTEMPTS",
            "WS_STALE_STREAM_THRESHOLD_SECONDS",
            "WS_ROTATION_BEFORE_EXPIRY_SECONDS",
            "WS_RECEIVE_TIMEOUT_SECONDS",
            "BINANCE_HTTP_TIMEOUT_SECONDS",
            "BINANCE_HTTP_RETRY_COUNT",
            "TRADE_HISTORY_REFRESH_HOURS",
            "TRADE_HISTORY_MAX_SYMBOLS",
            "TRADE_HISTORY_LOOKBACK_DAYS",
            "ORDER_HISTORY_LOOKBACK_DAYS",
            "LISTEN_KEY_EXPIRE_MINUTES",
            "VENUE_FLAT_SYNC_MIN_AGE_SECONDS",
        }:
            try:
                parsed = int(float(text))
            except (TypeError, ValueError):
                return default
            return str(parsed) if parsed > 0 else default
        return text
