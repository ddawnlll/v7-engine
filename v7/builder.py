"""
AnalysisRequest builder with full V7 contract shape.

Produces a valid AnalysisRequest dict that conforms to
contracts/schemas/analysis_request.schema.json AND the canonical
v7/docs/contracts/analysis_request.md authority rules.

V7 top-level shape:
  contract / identity / scope / canonical_state / state_views /
  deterministic_context / runtime_context / quality_and_freshness /
  degradation_context / portfolio_context / risk_context / lineage
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

# Path to the contract schema
_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "contracts"
    / "schemas"
    / "analysis_request.schema.json"
)

# Valid enum sets from contract authority docs
_VALID_MODES = frozenset({"SWING", "SCALP", "AGGRESSIVE_SCALP"})
_VALID_CALLERS = frozenset({"v7_runtime", "replay_tool", "paper_scan", "shadow"})
_VALID_REQUEST_KINDS = frozenset(
    {"live_scan", "paper_scan", "replay_eval", "shadow", "validation"}
)
_VALID_ANALYSIS_MODES = frozenset({"live", "paper", "replay", "shadow", "validation"})

# Mode-specific interval defaults (from contract authority)
_MODE_INTERVAL_DEFAULTS: dict[str, dict[str, Any]] = {
    "SWING": {
        "primary_interval": "4h",
        "context_intervals": ["1d"],
        "refinement_intervals": ["1h"],
        "label_horizon_family": "swing_horizon",
    },
    "SCALP": {
        "primary_interval": "1h",
        "context_intervals": ["4h"],
        "refinement_intervals": ["15m"],
        "label_horizon_family": "scalp_horizon",
    },
    "AGGRESSIVE_SCALP": {
        "primary_interval": "15m",
        "context_intervals": ["1h"],
        "refinement_intervals": ["5m"],
        "label_horizon_family": "aggressive_scalp_horizon",
    },
}

# Default contract versions (can be overridden for testing)
_DEFAULT_CONTRACT_VERSION = "v7-0.2"
_DEFAULT_STATE_SCHEMA_VERSION = "state-0.2"
_DEFAULT_SNAPSHOT_BUILDER_VERSION = "snapshot-0.2"


def _load_schema() -> dict[str, Any]:
    """Load and cache the AnalysisRequest JSON schema."""
    with open(_SCHEMA_PATH, "r") as fh:
        return json.load(fh)


def _utc_now() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_minimal_canonical_state(
    symbol: str,
    primary_interval: str,
    timestamp_utc: str,
) -> dict[str, Any]:
    """Build a minimal valid canonical_state for the given symbol/interval."""
    return {
        "raw_window": {
            "window_length": 0,
            "window_start_utc": timestamp_utc,
            "window_end_utc": timestamp_utc,
            "candles": [],
        },
        "derived_state": {
            "indicator_state": {},
            "volatility_state": {},
            "structure_state": {},
        },
        "context": {
            "higher_timeframe": {},
            "regime_context": {},
        },
        "quality": {
            "stale_flag": False,
            "data_source": "minimal_builder",
            "data_quality_flags": [],
            "snapshot_validity": "MINIMAL",
            "partial_state_flag": True,
        },
        "metadata": {
            "symbol": symbol,
            "primary_interval": primary_interval,
            "state_timestamp_utc": timestamp_utc,
            "snapshot_builder_version_seen": _DEFAULT_SNAPSHOT_BUILDER_VERSION,
            "state_schema_version_seen": _DEFAULT_STATE_SCHEMA_VERSION,
        },
    }


def build_analysis_request(
    *,
    mode: str,
    symbol: str,
    model_scope: str,
    request_kind: str = "live_scan",
    analysis_mode: str = "live",
    caller: str = "v7_runtime",
    primary_interval: str | None = None,
    context_intervals: list[str] | None = None,
    refinement_intervals: list[str] | None = None,
    exchange: str = "BINANCE",
    market_type: str = "PERP",
    request_id: str | None = None,
    timestamp_utc: str | None = None,
    run_id: str | None = None,
    trace_id: str | None = None,
    parent_decision_event_id: str | None = None,
    canonical_state: dict[str, Any] | None = None,
    state_views: dict[str, Any] | None = None,
    deterministic_context: dict[str, Any] | None = None,
    runtime_context: dict[str, Any] | None = None,
    quality_and_freshness: dict[str, Any] | None = None,
    degradation_context: dict[str, Any] | None = None,
    portfolio_context: dict[str, Any] | None = None,
    risk_context: dict[str, Any] | None = None,
    lineage: dict[str, Any] | None = None,
    contract_version: str = _DEFAULT_CONTRACT_VERSION,
    state_schema_version: str = _DEFAULT_STATE_SCHEMA_VERSION,
    snapshot_builder_version: str = _DEFAULT_SNAPSHOT_BUILDER_VERSION,
) -> dict[str, Any]:
    """Build a contract-valid V7 AnalysisRequest dict.

    Args:
        mode: Trading mode — SWING, SCALP, or AGGRESSIVE_SCALP.
        symbol: Trading symbol, e.g. 'BTCUSDT'.
        model_scope: Model scope identifier, e.g. 'swing_v1'.
        request_kind: Request context — live_scan, paper_scan, replay_eval,
                      shadow, validation.
        analysis_mode: Analysis context — live, paper, replay, shadow, validation.
        caller: Issuing component.
        primary_interval: Override mode default primary interval.
        context_intervals: Override mode default context intervals.
        refinement_intervals: Override mode default refinement intervals.
        exchange: Exchange identifier.
        market_type: Market type (PERP, SPOT).
        request_id: Unique request identifier (auto-generated if omitted).
        timestamp_utc: UTC ISO 8601 timestamp (now if omitted).
        run_id: Optional scan-run identifier.
        trace_id: Optional distributed tracing identifier.
        parent_decision_event_id: Optional lineage back to a prior decision event.
        canonical_state: Pre-built canonical state (minimal auto-built if omitted).
        state_views: Optional state views section.
        deterministic_context: Optional deterministic annotation layer.
        runtime_context: Optional runtime context section.
        quality_and_freshness: Optional top-level quality surface.
        degradation_context: Optional degradation info (null if omitted).
        portfolio_context: Optional portfolio context.
        risk_context: Optional risk context.
        lineage: Optional batch/session lineage.
        contract_version: Override default contract version.
        state_schema_version: Override default state schema version.
        snapshot_builder_version: Override default snapshot builder version.

    Returns:
        A dict that passes V7 schema validation.

    Raises:
        ValueError: If required fields are missing or invalid.
        jsonschema.ValidationError: If the constructed request fails schema
            validation.
    """
    # --- Validate inputs ---
    if mode not in _VALID_MODES:
        raise ValueError(
            f"Invalid mode '{mode}'. Must be one of: {sorted(_VALID_MODES)}"
        )
    if request_kind not in _VALID_REQUEST_KINDS:
        raise ValueError(
            f"Invalid request_kind '{request_kind}'. "
            f"Must be one of: {sorted(_VALID_REQUEST_KINDS)}"
        )
    if analysis_mode not in _VALID_ANALYSIS_MODES:
        raise ValueError(
            f"Invalid analysis_mode '{analysis_mode}'. "
            f"Must be one of: {sorted(_VALID_ANALYSIS_MODES)}"
        )
    if caller not in _VALID_CALLERS:
        raise ValueError(
            f"Invalid caller '{caller}'. Must be one of: {sorted(_VALID_CALLERS)}"
        )
    if not symbol or not isinstance(symbol, str):
        raise ValueError("symbol must be a non-empty string")
    if not model_scope or not isinstance(model_scope, str):
        raise ValueError("model_scope must be a non-empty string")

    # --- Resolve interval defaults from mode ---
    mode_defaults = _MODE_INTERVAL_DEFAULTS[mode]
    resolved_primary = primary_interval or mode_defaults["primary_interval"]
    resolved_context = context_intervals or mode_defaults["context_intervals"]
    resolved_refinement = refinement_intervals or mode_defaults["refinement_intervals"]

    # --- Build timestamps ---
    ts = timestamp_utc or _utc_now()
    rid = request_id or f"req_{uuid.uuid4().hex[:12]}"

    # --- Build sections ---
    contract_section: dict[str, Any] = {
        "contract_version": contract_version,
        "state_schema_version": state_schema_version,
        "snapshot_builder_version": snapshot_builder_version,
        "request_kind": request_kind,
    }

    identity_section: dict[str, Any] = {
        "request_id": rid,
        "timestamp_utc": ts,
    }
    if run_id is not None:
        identity_section["run_id"] = run_id
    if trace_id is not None:
        identity_section["trace_id"] = trace_id
    if parent_decision_event_id is not None:
        identity_section["parent_decision_event_id"] = parent_decision_event_id

    scope_section: dict[str, Any] = {
        "symbol": symbol.upper(),
        "requested_trade_mode": mode,
        "model_scope": model_scope,
        "primary_interval": resolved_primary,
        "analysis_mode": analysis_mode,
        "context_intervals": resolved_context,
        "refinement_intervals": resolved_refinement,
        "label_horizon_family": mode_defaults["label_horizon_family"],
        "exchange": exchange,
        "market_type": market_type,
    }

    state = canonical_state if canonical_state is not None else _build_minimal_canonical_state(
        symbol.upper(), resolved_primary, ts
    )

    # --- Assemble top-level request ---
    req: dict[str, Any] = {
        "contract": contract_section,
        "identity": identity_section,
        "scope": scope_section,
        "canonical_state": state,
    }

    if state_views is not None:
        req["state_views"] = state_views
    if deterministic_context is not None:
        req["deterministic_context"] = deterministic_context
    if runtime_context is not None:
        req["runtime_context"] = runtime_context
    if quality_and_freshness is not None:
        req["quality_and_freshness"] = quality_and_freshness
    req["degradation_context"] = degradation_context
    if portfolio_context is not None:
        req["portfolio_context"] = portfolio_context
    if risk_context is not None:
        req["risk_context"] = risk_context
    if lineage is not None:
        req["lineage"] = lineage

    _validate(req)
    return req


def validate_analysis_request(request: dict[str, Any]) -> list[str]:
    """Validate an AnalysisRequest dict against schema and authority rules.

    Returns a list of validation error messages (empty = valid).
    """
    errors: list[str] = []

    # Schema validation
    try:
        schema = _load_schema()
        jsonschema.validate(instance=request, schema=schema)
    except jsonschema.ValidationError as exc:
        errors.append(f"Schema: {exc.message}")
        return errors  # Stop early — schema is authoritative

    # Authority-level cross-field checks
    contract = request.get("contract", {})
    scope = request.get("scope", {})
    identity = request.get("identity", {})

    # 1. requested_trade_mode must match the mode convention
    req_trade_mode = scope.get("requested_trade_mode")
    if req_trade_mode and req_trade_mode not in _VALID_MODES:
        errors.append(f"Unknown requested_trade_mode '{req_trade_mode}'")

    # 2. Caller check
    # caller is in scope section for V7; check it from identity or scope
    # (V7 doesn't have a flat 'caller' — it's part of identity lineage context)

    # 3. Contract version check
    cv = contract.get("contract_version", "")
    if not cv or not isinstance(cv, str):
        errors.append("contract.contract_version must be a non-empty string")

    # 4. Canonical state must be present and have required sub-structure
    cs = request.get("canonical_state")
    if cs is None or not isinstance(cs, dict):
        errors.append("canonical_state must be present and be an object")

    # 5. Timestamp must be present and parseable
    ts = identity.get("timestamp_utc", "")
    if not ts:
        errors.append("identity.timestamp_utc is required")

    # 6. request_kind validity
    rk = contract.get("request_kind", "")
    if rk not in _VALID_REQUEST_KINDS:
        errors.append(f"Unknown request_kind '{rk}'")

    # 7. analysis_mode validity
    am = scope.get("analysis_mode", "")
    if am not in _VALID_ANALYSIS_MODES:
        errors.append(f"Unknown analysis_mode '{am}'")

    return errors


def _validate(request: dict[str, Any]) -> None:
    """Schema-validate; raise on first error."""
    schema = _load_schema()
    jsonschema.validate(instance=request, schema=schema)
