"""Runtime settings routes for v4."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from runtime.api.deps import get_db_session
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.db.repos.settings_repo import (
    DEFAULT_RUNTIME_SETTINGS,
    SUPPORTED_AUTONOMOUS_INTERVALS,
    SettingsRepository,
)
from runtime.services.binance_client import DEFAULT_SCAN_SYMBOLS

router = APIRouter(tags=["settings"])
settings_repo = SettingsRepository()

BOOLEAN_SETTING_KEYS = {
    "AUTONOMOUS_ENABLED",
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
}

NUMBER_SETTING_METADATA: dict[str, dict[str, Any]] = {
    "AUTONOMOUS_SCAN_INTERVAL_SECONDS": {"min": 30, "max": 3600, "step": 15, "unit": "seconds"},
    "AUTONOMOUS_MONITOR_INTERVAL_SECONDS": {"min": 5, "max": 300, "step": 5, "unit": "seconds"},
    "AUTONOMOUS_SCAN_WORKERS": {"min": 1, "max": 128, "step": 1, "unit": "workers"},
    "AUTONOMOUS_INFERENCE_WORKERS": {"min": 1, "max": 32, "step": 1, "unit": "workers"},
    "AUTONOMOUS_INFERENCE_QUEUE_SIZE": {"min": 1, "max": 512, "step": 1, "unit": "items"},
    "AUTONOMOUS_MIN_CONFIDENCE": {"min": 0, "max": 100, "step": 1, "unit": "percent"},
    "AUTONOMOUS_CONFIDENCE_PERCENTILE": {"min": 0.5, "max": 0.99, "step": 0.01, "unit": "ratio"},
    "AUTONOMOUS_CONFIDENCE_LOOKBACK_TRACES": {"min": 10, "max": 5000, "step": 10, "unit": "traces"},
    "AUTONOMOUS_CONFIDENCE_MIN_SAMPLES": {"min": 1, "max": 1000, "step": 1, "unit": "samples"},
    "AUTONOMOUS_CONFIDENCE_MIN_FLOOR": {"min": 0, "max": 100, "step": 1, "unit": "percent"},
    "AUTONOMOUS_CONFIDENCE_MAX_CEIL": {"min": 0, "max": 100, "step": 1, "unit": "percent"},
    "SCAN_FETCH_TIMEOUT_SECONDS": {"min": 5, "max": 600, "step": 5, "unit": "seconds"},
    "MAX_TRADES_PER_DAY": {"min": 0, "max": 100, "step": 1, "unit": "trades"},
    "PAPER_DEFAULT_BALANCE": {"min": 10, "max": 1000000, "step": 10, "unit": "usdt"},
    "PAPER_POSITION_SIZE_MIN_PCT": {"min": 0, "max": 100, "step": 0.5, "unit": "percent"},
    "PAPER_POSITION_SIZE_MAX_PCT": {"min": 0, "max": 100, "step": 0.5, "unit": "percent"},
    "PAPER_POSITION_CONFIDENCE_FLOOR": {"min": 0, "max": 100, "step": 1, "unit": "percent"},
    "PAPER_POSITION_CONFIDENCE_CEIL": {"min": 0, "max": 100, "step": 1, "unit": "percent"},
    "LIVE_RISK_PER_TRADE_PCT": {"min": 0.001, "max": 1.0, "step": 0.001, "unit": "ratio"},
    "LIVE_DEFAULT_ENTRY_R_MULTIPLE": {"min": 0.25, "max": 10.0, "step": 0.25, "unit": "R"},
    "LIVE_MAX_POSITION_R": {"min": 0.25, "max": 10.0, "step": 0.25, "unit": "R"},
    "LIVE_MAX_TOTAL_OPEN_R": {"min": 0.25, "max": 20.0, "step": 0.25, "unit": "R"},
    "LIVE_MAX_DAILY_LOSS_R": {"min": 0.25, "max": 20.0, "step": 0.25, "unit": "R"},
    "LIVE_MAX_LEVERAGE": {"min": 1, "max": 125, "step": 1, "unit": "x"},
    "AUTO_LIVE_MAX_CONCURRENT_POSITIONS": {"min": 0, "max": 20, "step": 1, "unit": "positions"},
    "LEARNING_LOOKBACK_DAYS": {"min": 1, "max": 365, "step": 1, "unit": "days"},
    "LEARNING_MIN_CONFIDENCE": {"min": 0, "max": 1, "step": 0.05, "unit": "ratio"},
    "LEARNING_REFRESH_SECONDS": {"min": 60, "max": 86400, "step": 30, "unit": "seconds"},
    "PHASE24_INFERENCE_TIMEOUT_MS": {"min": 50, "max": 10000, "step": 50, "unit": "ms"},
    "ANALYZER_ENGINE_TIMEOUT_MS": {"min": 100, "max": 10000, "step": 50, "unit": "ms"},
    "STATIC_ENGINE_EMIT_THRESHOLD": {"min": 0, "max": 1, "step": 0.01, "unit": "ratio"},
    "EXECUTION_CONFIDENCE_THRESHOLD": {"min": 0, "max": 1, "step": 0.01, "unit": "ratio"},
    "CIRCUIT_BREAKER_LOOKBACK_TRADES": {"min": 1, "max": 500, "step": 1, "unit": "trades"},
    "CIRCUIT_BREAKER_MAX_CONSECUTIVE_LOSSES": {"min": 1, "max": 50, "step": 1, "unit": "trades"},
    "CIRCUIT_BREAKER_MAX_FAILURE_RATE_PCT": {"min": 1, "max": 100, "step": 1, "unit": "percent"},
    "CIRCUIT_BREAKER_MAX_SEVERITY_AVG": {"min": 0, "max": 10, "step": 0.1, "unit": "score"},
    "CIRCUIT_BREAKER_COOLDOWN_MINUTES": {"min": 1, "max": 1440, "step": 1, "unit": "minutes"},
    "CIRCUIT_BREAKER_DEGRADED_MULTIPLIER": {"min": 0, "max": 1, "step": 0.05, "unit": "ratio"},
    "SYMBOL_THROTTLE_LOOKBACK_TRADES": {"min": 1, "max": 100, "step": 1, "unit": "trades"},
    "SYMBOL_THROTTLE_MAX_CONSECUTIVE_STOP_HITS": {"min": 1, "max": 20, "step": 1, "unit": "trades"},
    "SYMBOL_THROTTLE_MAX_STOP_HIT_RATE_PCT": {"min": 1, "max": 100, "step": 1, "unit": "percent"},
    "SYMBOL_THROTTLE_COOLDOWN_MINUTES": {"min": 1, "max": 2880, "step": 1, "unit": "minutes"},
    "SIMULATION_DIAGNOSTICS_LOW_CONFIDENCE_THRESHOLD": {"min": 0, "max": 100, "step": 1, "unit": "percent"},
    "SIMULATION_EXPORT_ROW_LIMIT": {"min": 1, "max": 50000, "step": 100, "unit": "rows"},
}

SETTING_DESCRIPTIONS = {
    "AUTONOMOUS_ENABLED": "Master switch for the autonomous loop.",
    "AUTONOMOUS_SYMBOLS": "Symbols the runtime may scan and trade.",
    "AUTONOMOUS_INTERVALS": "Global interval universe available to autonomous scanning.",
    "AUTONOMOUS_MODES": "Trading modes currently enabled in runtime.",
    "AUTONOMOUS_ALLOWED_TRADE_DIRECTIONS": "Allowed side selection for autonomous decisions.",
    "AUTO_LIVE_SYMBOL_ALLOWLIST": "Live auto-routing is limited to these symbols.",
    "LIVE_RISK_PER_TRADE_PCT": "Fraction of balance risked per 1R trade.",
    "LIVE_DEFAULT_ENTRY_R_MULTIPLE": "Default order size when a signal does not provide entry_r_multiple.",
    "LIVE_MAX_POSITION_R": "Maximum R size allowed for one position.",
    "LIVE_MAX_TOTAL_OPEN_R": "Maximum total open risk across positions.",
    "LIVE_MAX_DAILY_LOSS_R": "Daily loss cap measured in R.",
    "LIVE_MAX_LEVERAGE": "Maximum leverage the runtime may request before submitting live orders.",
    "ANALYZER_ACTIVE_ENGINE": "Analyzer engine selected by runtime configuration.",
    "SIMULATION_DIAGNOSTICS_LOW_CONFIDENCE_THRESHOLD": "Display threshold used by SIM-1 trace-derived diagnostics and health classification.",
    "SIMULATION_EXPORT_ROW_LIMIT": "Maximum rows returned by SIM-1 simulation export endpoints.",
}


class SettingsResponse(BaseModel):
    profile_id: str = PAPER_PROFILE_ID
    settings: Dict[str, str]
    resolved_config_hash: str | None = None


class SettingsUpdateResponse(BaseModel):
    ok: bool
    profile_id: str = PAPER_PROFILE_ID
    settings: Dict[str, str]
    resolved_config_hash: str | None = None


class SettingOption(BaseModel):
    value: str
    label: str
    description: str | None = None


class SettingControlMetadata(BaseModel):
    key: str
    label: str
    description: str | None = None
    group: str
    control: str
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    unit: str | None = None
    options: list[SettingOption] = Field(default_factory=list)


class SettingsMetadataResponse(BaseModel):
    profile_id: str = PAPER_PROFILE_ID
    controls: list[SettingControlMetadata]
    catalogs: dict[str, list[str]] = Field(default_factory=dict)


@router.get("/api/v3/settings", response_model=SettingsResponse)
@router.get("/api/v3/runtime/settings", response_model=SettingsResponse)
@router.get("/api/admin/settings", response_model=SettingsResponse)
def get_settings(
    profile_id: str = Query(default=PAPER_PROFILE_ID),
    session: Session = Depends(get_db_session),
) -> SettingsResponse:
    resolution = settings_repo.get_resolution(session, profile_id=profile_id, materialize=True)
    return SettingsResponse(
        profile_id=profile_id,
        settings=dict(resolution["settings"]),
        resolved_config_hash=str(resolution["resolved_config_hash"]),
    )


@router.get("/api/v3/settings/metadata", response_model=SettingsMetadataResponse)
def get_settings_metadata(
    profile_id: str = Query(default=PAPER_PROFILE_ID),
    session: Session = Depends(get_db_session),
) -> SettingsMetadataResponse:
    resolution = settings_repo.get_resolution(session, profile_id=profile_id, materialize=False)
    settings = dict(resolution["settings"])
    catalogs = _build_catalogs()
    controls = [_build_control_metadata(key, settings.get(key), catalogs) for key in sorted(settings.keys())]
    return SettingsMetadataResponse(profile_id=profile_id, controls=controls, catalogs=catalogs)


@router.post("/api/v3/settings", response_model=SettingsUpdateResponse)
@router.post("/api/v3/runtime/settings", response_model=SettingsUpdateResponse)
@router.post("/api/admin/settings", response_model=SettingsUpdateResponse)
def update_settings(
    payload: dict[str, str],
    profile_id: str = Query(default=PAPER_PROFILE_ID),
    session: Session = Depends(get_db_session),
) -> SettingsUpdateResponse:
    from runtime.runtime.autonomous_runtime import start_autonomous_loop

    saved = settings_repo.save_many(session, payload, profile_id=profile_id)
    resolution = settings_repo.get_resolution(session, profile_id=profile_id, materialize=True)
    start_autonomous_loop(profile_id)
    return SettingsUpdateResponse(
        ok=True,
        profile_id=profile_id,
        settings=saved,
        resolved_config_hash=str(resolution["resolved_config_hash"]),
    )


def _humanize_key(key: str) -> str:
    return key.replace("_", " ").title().replace(" Usdt", " USDT").replace(" R ", " R ")


def _group_for_key(key: str) -> str:
    normalized = key.upper()
    if normalized.startswith("AUTO_LIVE_") or normalized.startswith("LIVE_"):
        return "profile-settings"
    if "LEARNING" in normalized or "CALIBRATION" in normalized:
        return "learning"
    if "ENGINE" in normalized or normalized.startswith("V6_") or normalized.startswith("PHASE24"):
        return "engine"
    if "RISK" in normalized or "LOSS" in normalized or "BREAKER" in normalized or "CONFIDENCE" in normalized:
        return "risk"
    if "SYMBOL" in normalized or "INTERVAL" in normalized or "MODE" in normalized:
        return "universe"
    if "BUDGET" in normalized or "TIMEOUT" in normalized:
        return "budgeting"
    if normalized.startswith("AUTONOMOUS_") or normalized.startswith("SCAN_") or "WORKER" in normalized:
        return "execution"
    return "execution"


def _options(values: list[str]) -> list[SettingOption]:
    return [SettingOption(value=item, label=item.replace("_", " ")) for item in values]


def _build_catalogs() -> dict[str, list[str]]:
    try:
        from runtime.services.analyzer_engine_registry_service import AnalyzerEngineRegistryService

        engine_names = [str(item.get("engine_name") or "") for item in AnalyzerEngineRegistryService().list_engines() if item.get("engine_name")]
    except ModuleNotFoundError as exc:
        if exc.name != "lancedb":
            raise
        engine_names = []
    return {
        "symbols": list(DEFAULT_SCAN_SYMBOLS),
        "intervals": list(SUPPORTED_AUTONOMOUS_INTERVALS),
        "modes": ["SCALP", "SWING", "AGGRESSIVE_SCALP"],
        "trade_directions": ["BOTH", "LONG_ONLY", "SHORT_ONLY"],
        "confidence_policies": ["FIXED", "PERCENTILE"],
        "live_risk_models": ["FIXED_R"],
        "live_risk_basis": ["AVAILABLE_BALANCE", "EQUITY", "WALLET_BALANCE"],
        "phase24_rollout_stages": ["NOT_READY", "FOUNDATION_ONLY", "TRAINING_READY", "CANDIDATE_READY", "PROMOTION_READY", "SHADOW", "ACTIVE"],
        "phase24_allowed_actions": ["NO_TRADE", "REDUCE_SIZE_25_PCT", "WAIT_1_CANDLE"],
        "circuit_breaker_manual_modes": ["AUTO", "FORCE_OPEN", "FORCE_CLOSED"],
        "execution_gate_owners": ["static_engine", "v5"],
        "analyzer_engines": engine_names or ["v4_default"],
    }


def _build_control_metadata(key: str, value: str | None, catalogs: dict[str, list[str]]) -> SettingControlMetadata:
    label = _humanize_key(key)
    description = SETTING_DESCRIPTIONS.get(key)
    group = _group_for_key(key)

    if key in BOOLEAN_SETTING_KEYS:
        return SettingControlMetadata(key=key, label=label, description=description, group=group, control="boolean")

    if key in {"AUTONOMOUS_ALLOWED_TRADE_DIRECTIONS"}:
        return SettingControlMetadata(key=key, label=label, description=description, group=group, control="enum", options=_options(catalogs["trade_directions"]))

    if key in {"AUTONOMOUS_CONFIDENCE_POLICY"}:
        return SettingControlMetadata(key=key, label=label, description=description, group=group, control="enum", options=_options(catalogs["confidence_policies"]))

    if key in {"LIVE_RISK_MODEL"}:
        return SettingControlMetadata(key=key, label=label, description=description, group=group, control="enum", options=_options(catalogs["live_risk_models"]))

    if key in {"LIVE_RISK_BASIS"}:
        return SettingControlMetadata(key=key, label=label, description=description, group=group, control="enum", options=_options(catalogs["live_risk_basis"]))

    if key in {"PHASE24_ROLLOUT_STAGE"}:
        return SettingControlMetadata(key=key, label=label, description=description, group=group, control="enum", options=_options(catalogs["phase24_rollout_stages"]))

    if key in {"CIRCUIT_BREAKER_MANUAL_MODE"}:
        return SettingControlMetadata(key=key, label=label, description=description, group=group, control="enum", options=_options(catalogs["circuit_breaker_manual_modes"]))

    if key in {"EXECUTION_GATE_OWNER"}:
        return SettingControlMetadata(key=key, label=label, description=description, group=group, control="enum", options=_options(catalogs["execution_gate_owners"]))

    if key in {"ANALYZER_ACTIVE_ENGINE"}:
        return SettingControlMetadata(key=key, label=label, description=description, group=group, control="enum", options=_options(catalogs["analyzer_engines"]))

    if key in {"AUTONOMOUS_SYMBOLS", "AUTO_LIVE_SYMBOL_ALLOWLIST", "SYMBOL_THROTTLE_SEEDED_SYMBOLS"}:
        return SettingControlMetadata(key=key, label=label, description=description, group=group, control="multi_enum", options=_options(catalogs["symbols"]))

    if key in {"AUTONOMOUS_INTERVALS", "AUTONOMOUS_INTERVALS_SCALP", "AUTONOMOUS_INTERVALS_SWING", "AUTONOMOUS_INTERVALS_AGGRESSIVE_SCALP"}:
        return SettingControlMetadata(key=key, label=label, description=description, group=group, control="multi_enum", options=_options(catalogs["intervals"]))

    if key in {"AUTONOMOUS_MODES", "PHASE24_ENABLED_MODES"}:
        return SettingControlMetadata(key=key, label=label, description=description, group=group, control="multi_enum", options=_options(catalogs["modes"]))

    if key in {"PHASE24_ALLOWED_ACTIONS"}:
        return SettingControlMetadata(key=key, label=label, description=description, group=group, control="multi_enum", options=_options(catalogs["phase24_allowed_actions"]))

    if key in NUMBER_SETTING_METADATA:
        meta = NUMBER_SETTING_METADATA[key]
        return SettingControlMetadata(
            key=key,
            label=label,
            description=description,
            group=group,
            control="number",
            min_value=float(meta["min"]),
            max_value=float(meta["max"]),
            step=float(meta["step"]),
            unit=str(meta["unit"]),
        )

    default_value = DEFAULT_RUNTIME_SETTINGS.get(key)
    if default_value is not None:
        try:
            float(str(value if value is not None else default_value))
            meta = NUMBER_SETTING_METADATA.get(key)
            if meta:
                return SettingControlMetadata(
                    key=key,
                    label=label,
                    description=description,
                    group=group,
                    control="number",
                    min_value=float(meta["min"]),
                    max_value=float(meta["max"]),
                    step=float(meta["step"]),
                    unit=str(meta["unit"]),
                )
        except (TypeError, ValueError):
            pass

    return SettingControlMetadata(key=key, label=label, description=description, group=group, control="readonly")
