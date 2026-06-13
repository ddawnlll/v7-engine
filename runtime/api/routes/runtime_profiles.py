"""Runtime profile visibility routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.services.binance_usdm_readonly_service import BinanceUsdmReadonlyService, BinanceUsdmReadonlySyncError
from runtime.services.binance_usdm_reconciliation_service import BinanceUsdmReconciliationService, BinanceUsdmReconciliationError
from runtime.services.binance_usdm_user_data_stream_service import (
    BinanceUsdmUserDataStreamError,
    BinanceUsdmUserDataStreamService,
)
from runtime.services.runtime_profile_service import (
    BINANCE_USDM_VENUE,
    RuntimeProfileConnectivityError,
    RuntimeProfileNotFoundError,
    RuntimeProfileService,
)

router = APIRouter(tags=["runtime-profiles"])
runtime_profile_service = RuntimeProfileService()
binance_usdm_readonly_service = BinanceUsdmReadonlyService()
binance_usdm_user_data_stream_service = BinanceUsdmUserDataStreamService()
binance_usdm_reconciliation_service = BinanceUsdmReconciliationService()


def _is_synthetic_simulation_profile(profile_id: str | None) -> bool:
    return str(profile_id or "").startswith("simulation-")


def _synthetic_simulation_profile(profile_id: str) -> dict:
    return {
        "profile_id": profile_id,
        "name": f"Simulation analysis {profile_id.replace('simulation-', '#')}",
        "runtime_mode": "SIMULATION_ANALYSIS",
        "execution_mode": "SIMULATION_ANALYSIS",
        "venue": "SIMULATION",
        "status": "ACTIVE",
        "read_only": True,
        "supports_account_reads": False,
        "supports_order_placement": False,
        "manual_trading_enabled": False,
        "auto_trading_enabled": False,
        "default_for_auto_trading": False,
        "connectivity": {"status": "NOT_APPLICABLE"},
    }


def _synthetic_read_only_exposure(profile_id: str) -> dict:
    profile = _synthetic_simulation_profile(profile_id)
    return {
        "profile": profile,
        "auto_live": {"posture": "NOT_APPLICABLE", "reason_codes": ["SYNTHETIC_SIMULATION_PROFILE"]},
        "health": {
            "profile_id": profile_id,
            "exchange_status": "not_applicable",
            "connectivity_status": "NOT_APPLICABLE",
            "read_only": True,
            "supports_account_reads": False,
            "supports_order_placement": False,
            "rest_sync_status": "NOT_APPLICABLE",
            "stream_status": "NOT_APPLICABLE",
            "reconciliation_status": "NOT_APPLICABLE",
            "last_synced_at_utc": None,
            "last_event_seen_at_utc": None,
            "last_reconciled_at_utc": None,
        },
        "sync": None,
        "stream": None,
        "reconciliation": None,
        "account": None,
        "balances": [],
        "positions": [],
        "open_orders": [],
        "protective_summary": {
            "entry_open_order_count": 0,
            "protective_open_order_count": 0,
            "stop_loss_order_count": 0,
            "take_profit_order_count": 0,
            "trailing_stop_order_count": 0,
        },
        "pre_deploy_readiness": {"status": "NOT_APPLICABLE", "checks": []},
    }


class RuntimeProfileListResponse(BaseModel):
    items: list[dict]
    count: int


class RuntimeProfileSettingPreset(BaseModel):
    preset_id: str
    label: str
    description: str | None = None
    capabilities: dict[str, bool] = Field(default_factory=dict)
    runtime_settings: dict[str, str] = Field(default_factory=dict)
    risk_settings: dict[str, str] = Field(default_factory=dict)


class RuntimeProfileSettingsResponse(BaseModel):
    profile_id: str
    capabilities: dict[str, bool]
    runtime_settings: dict[str, str]
    risk_settings: dict[str, str]
    auto_live: dict
    resolved_config_hash: str | None = None
    preset_profiles: list[RuntimeProfileSettingPreset] = Field(default_factory=list)


class RuntimeProfileSettingsUpdateRequest(BaseModel):
    capabilities: dict[str, bool | str | int | None] = Field(default_factory=dict)
    runtime_settings: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    risk_settings: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


@router.get("/api/v3/runtime/profiles", response_model=RuntimeProfileListResponse)
def list_runtime_profiles() -> RuntimeProfileListResponse:
    items = runtime_profile_service.list_profiles()
    return RuntimeProfileListResponse(items=items, count=len(items))


@router.get("/api/v3/runtime/profiles/{profile_id}")
def get_runtime_profile(profile_id: str = PAPER_PROFILE_ID):
    if _is_synthetic_simulation_profile(profile_id):
        return _synthetic_simulation_profile(profile_id)
    try:
        return runtime_profile_service.get_profile(profile_id)
    except RuntimeProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/v3/runtime/profiles/{profile_id}/settings", response_model=RuntimeProfileSettingsResponse)
def get_runtime_profile_settings(profile_id: str):
    try:
        return runtime_profile_service.get_profile_settings(profile_id)
    except RuntimeProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/v3/runtime/profiles/{profile_id}/settings", response_model=RuntimeProfileSettingsResponse)
def update_runtime_profile_settings(profile_id: str, payload: RuntimeProfileSettingsUpdateRequest):
    try:
        return runtime_profile_service.update_profile_settings(
            profile_id,
            capabilities=dict(payload.capabilities),
            runtime_settings=dict(payload.runtime_settings),
            risk_settings=dict(payload.risk_settings),
        )
    except RuntimeProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/v3/runtime/profiles/{profile_id}/auto-live")
def get_runtime_profile_auto_live_posture(
    profile_id: str,
    symbol: str | None = Query(default=None),
    entry_r_multiple: float | None = Query(default=None),
):
    try:
        candidate = {"symbol": symbol, "entry_r_multiple": entry_r_multiple}
        return runtime_profile_service.get_auto_live_policy(profile_id, candidate=candidate)
    except RuntimeProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/v3/runtime/profiles/{profile_id}/connectivity")
def probe_runtime_profile_connectivity(profile_id: str):
    try:
        return runtime_profile_service.probe_connectivity(profile_id)
    except RuntimeProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeProfileConnectivityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/v3/runtime/profiles/{profile_id}/read-only/sync")
def sync_runtime_profile_read_only_state(profile_id: str):
    try:
        return binance_usdm_readonly_service.sync_account_state(profile_id)
    except RuntimeProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BinanceUsdmReadonlySyncError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/v3/runtime/profiles/{profile_id}/read-only/state")
def get_runtime_profile_read_only_state(profile_id: str):
    try:
        return binance_usdm_readonly_service.get_persisted_state(profile_id)
    except RuntimeProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/v3/runtime/profiles/{profile_id}/read-only/exposure")
def get_runtime_profile_read_only_exposure(profile_id: str):
    if _is_synthetic_simulation_profile(profile_id):
        return _synthetic_read_only_exposure(profile_id)
    try:
        profile = runtime_profile_service.get_profile(profile_id)
    except RuntimeProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if str(profile.get("venue") or "").upper() != BINANCE_USDM_VENUE:
        connectivity = profile.get("connectivity") or {}
        return {
            "profile": profile,
            "auto_live": runtime_profile_service.get_auto_live_policy(profile_id),
            "health": {
                "profile_id": profile.get("profile_id"),
                "exchange_status": "not_applicable",
                "connectivity_status": connectivity.get("status") or "NOT_APPLICABLE",
                "read_only": bool(profile.get("read_only")),
                "supports_account_reads": bool(profile.get("supports_account_reads")),
                "supports_order_placement": bool(profile.get("supports_order_placement")),
                "rest_sync_status": "NOT_APPLICABLE",
                "stream_status": "NOT_APPLICABLE",
                "reconciliation_status": "NOT_APPLICABLE",
                "last_synced_at_utc": None,
                "last_event_seen_at_utc": None,
                "last_reconciled_at_utc": None,
            },
            "sync": None,
            "stream": None,
            "reconciliation": None,
            "account": None,
            "balances": [],
            "positions": [],
            "open_orders": [],
            "protective_summary": {
                "entry_open_order_count": 0,
                "protective_open_order_count": 0,
                "stop_loss_order_count": 0,
                "take_profit_order_count": 0,
                "trailing_stop_order_count": 0,
            },
            "pre_deploy_readiness": {
                "status": "NOT_APPLICABLE",
                "checks": [],
            },
        }

    state = binance_usdm_readonly_service.get_persisted_state(profile_id)
    sync = state.get("sync") or {}
    stream = binance_usdm_user_data_stream_service.get_stream_state(profile_id)
    reconciliation = state.get("reconciliation") or {}
    connectivity = profile.get("connectivity") or {}
    exchange_status = "unknown"
    connectivity_status = str(connectivity.get("status") or "UNKNOWN").upper()
    if connectivity_status in {"CONNECTED", "READY"}:
        exchange_status = "connected"
    elif connectivity_status in {"ERROR", "MISSING_CREDENTIALS"}:
        exchange_status = "degraded"
    stream_status = str(stream.get("status") or "INACTIVE").upper()
    stream_reconnect_required = bool(stream.get("reconnect_required"))
    if stream_status in {"DEGRADED", "EXPIRED"} or stream_reconnect_required:
        exchange_status = "degraded"
    reconciliation_status = str(reconciliation.get("status") or "UNAVAILABLE").upper()
    if reconciliation_status == "DEGRADED":
        exchange_status = "degraded"
    readiness_checks = [
        {
            "code": "READ_ONLY_MODE",
            "ok": bool(profile.get("read_only")),
            "message": "Runtime profile must remain explicitly read-only.",
        },
        {
            "code": "ACCOUNT_READS_ENABLED",
            "ok": bool(profile.get("supports_account_reads")),
            "message": "Runtime profile must keep read-only account access enabled.",
        },
        {
            "code": "ORDER_PLACEMENT_DISABLED",
            "ok": not bool(profile.get("supports_order_placement")) and not bool(profile.get("manual_trading_enabled")) and not bool(profile.get("auto_trading_enabled")),
            "message": "Live order placement must remain disabled for the read-only slice.",
        },
        {
            "code": "CREDENTIALS_CONFIGURED",
            "ok": bool((profile.get("credential_status") or {}).get("configured")),
            "message": "Credential reference must resolve fully before persistent read-only usage.",
        },
        {
            "code": "REST_SYNC_HEALTHY",
            "ok": str(sync.get("status") or "").upper() == "SYNCED",
            "message": "A fresh REST account-state snapshot should be available.",
        },
        {
            "code": "STREAM_NOT_DEGRADED",
            "ok": stream_status not in {"DEGRADED", "EXPIRED"} and not stream_reconnect_required,
            "message": "User data stream should not currently require reconnect or be expired/degraded.",
        },
        {
            "code": "RECONCILIATION_NOT_DEGRADED",
            "ok": reconciliation_status in {"READY", "WARNING"},
            "message": "Reconciliation posture should be available without degraded warnings.",
        },
    ]
    venue_state = reconciliation.get("venue_state") or {}
    return {
        "profile": state.get("profile") or profile,
        "auto_live": runtime_profile_service.get_auto_live_policy(profile_id),
        "health": {
            "profile_id": profile.get("profile_id"),
            "exchange_status": exchange_status,
            "connectivity_status": connectivity_status,
            "read_only": bool(profile.get("read_only")),
            "supports_account_reads": bool(profile.get("supports_account_reads")),
            "supports_order_placement": bool(profile.get("supports_order_placement")),
            "rest_sync_status": str(sync.get("status") or "UNAVAILABLE").upper(),
            "stream_status": stream_status,
            "reconciliation_status": reconciliation_status,
            "last_synced_at_utc": sync.get("last_synced_at_utc"),
            "last_event_seen_at_utc": stream.get("last_event_seen_at_utc"),
            "last_reconciled_at_utc": reconciliation.get("last_reconciled_at_utc"),
        },
        "sync": state.get("sync"),
        "stream": stream,
        "reconciliation": reconciliation,
        "account": state.get("account"),
        "balances": state.get("balances") or [],
        "positions": state.get("positions") or [],
        "open_orders": state.get("open_orders") or [],
        "protective_summary": {
            "entry_open_order_count": int(venue_state.get("entry_open_order_count") or 0),
            "protective_open_order_count": int(venue_state.get("protective_open_order_count") or 0),
            "stop_loss_order_count": int(venue_state.get("stop_loss_order_count") or 0),
            "take_profit_order_count": int(venue_state.get("take_profit_order_count") or 0),
            "trailing_stop_order_count": int(venue_state.get("trailing_stop_order_count") or 0),
        },
        "pre_deploy_readiness": {
            "status": "READY" if all(bool(item.get("ok")) for item in readiness_checks) else "NOT_READY",
            "checks": readiness_checks,
        },
    }


@router.get("/api/v3/runtime/profiles/{profile_id}/read-only/order")
def get_runtime_profile_read_only_order_status(
    profile_id: str,
    symbol: str = Query(...),
    order_id: str | None = Query(default=None),
    client_order_id: str | None = Query(default=None),
):
    try:
        return binance_usdm_readonly_service.query_order_status(
            profile_id,
            symbol=symbol,
            order_id=order_id,
            client_order_id=client_order_id,
        )
    except RuntimeProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BinanceUsdmReadonlySyncError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/v3/runtime/profiles/{profile_id}/user-data-stream")
def get_runtime_profile_user_data_stream_state(profile_id: str):
    try:
        return binance_usdm_user_data_stream_service.get_stream_state(profile_id)
    except RuntimeProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/v3/runtime/profiles/{profile_id}/user-data-stream/start")
def start_runtime_profile_user_data_stream(profile_id: str):
    try:
        return binance_usdm_user_data_stream_service.start_stream(profile_id)
    except RuntimeProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BinanceUsdmUserDataStreamError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/v3/runtime/profiles/{profile_id}/user-data-stream/keepalive")
def keepalive_runtime_profile_user_data_stream(profile_id: str):
    try:
        return binance_usdm_user_data_stream_service.keepalive_stream(profile_id)
    except RuntimeProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BinanceUsdmUserDataStreamError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/v3/runtime/profiles/{profile_id}/user-data-stream/refresh")
def refresh_runtime_profile_user_data_stream(profile_id: str):
    try:
        return binance_usdm_user_data_stream_service.refresh_stream(profile_id)
    except RuntimeProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BinanceUsdmUserDataStreamError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/v3/runtime/profiles/{profile_id}/user-data-stream/close")
def close_runtime_profile_user_data_stream(profile_id: str):
    try:
        return binance_usdm_user_data_stream_service.close_stream(profile_id)
    except RuntimeProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BinanceUsdmUserDataStreamError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/v3/runtime/profiles/{profile_id}/reconciliation")
def get_runtime_profile_reconciliation(profile_id: str):
    try:
        return binance_usdm_reconciliation_service.get_reconciliation(profile_id)
    except RuntimeProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BinanceUsdmReconciliationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
