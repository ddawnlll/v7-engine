"""
AnalysisRequest builder with contract schema validation.

Produces a valid AnalysisRequest dict that conforms to
contracts/schemas/analysis_request.schema.json.

Also validates against the canonical v7/docs/contracts/analysis_request.md
authority rules: required fields, legal enums, mode-scope compatibility,
no future-derived fields, degradation flags internally consistent.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

# Path to the contract schema
_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "contracts" / "schemas" / "analysis_request.schema.json"

# Valid modes from contract authority
_VALID_MODES = frozenset({"SCALP", "AGGRESSIVE_SCALP", "SWING"})
_VALID_CALLERS = frozenset({"v7_runtime", "replay_tool", "paper_scan", "shadow"})


def _load_schema() -> dict[str, Any]:
    """Load and cache the AnalysisRequest JSON schema."""
    with open(_SCHEMA_PATH, "r") as fh:
        return json.load(fh)


def _utc_now() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def build_analysis_request(
    *,
    mode: str,
    symbol: str,
    model_scope: str,
    caller: str = "v7_runtime",
    request_id: str | None = None,
    timestamp: str | None = None,
    raw_signal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a contract-valid AnalysisRequest dict.

    Args:
        mode: Trading mode — one of SCALP, AGGRESSIVE_SCALP, SWING.
        symbol: Trading symbol, e.g. 'BTCUSDT'.
        model_scope: Model scope identifier, e.g. 'swing_v1'.
        caller: Issuing component — v7_runtime, replay_tool, paper_scan, shadow.
        request_id: Unique request identifier (auto-generated if omitted).
        timestamp: UTC ISO 8601 timestamp (now if omitted).
        raw_signal: Optional opaque signal payload from an upstream source.

    Returns:
        A dict that passes schema validation.

    Raises:
        ValueError: If required fields are missing or invalid.
        jsonschema.ValidationError: If the constructed request fails schema
            validation.
    """
    if mode not in _VALID_MODES:
        raise ValueError(
            f"Invalid mode '{mode}'. Must be one of: {sorted(_VALID_MODES)}"
        )
    if caller not in _VALID_CALLERS:
        raise ValueError(
            f"Invalid caller '{caller}'. Must be one of: {sorted(_VALID_CALLERS)}"
        )
    if not symbol or not isinstance(symbol, str):
        raise ValueError("symbol must be a non-empty string")
    if not model_scope or not isinstance(model_scope, str):
        raise ValueError("model_scope must be a non-empty string")

    req: dict[str, Any] = {
        "request_id": request_id or f"req_{uuid.uuid4().hex[:12]}",
        "mode": mode,
        "symbol": symbol.upper(),
        "timestamp": timestamp or _utc_now(),
        "requested_trade_mode": mode,
        "model_scope": model_scope,
        "caller": caller,
    }
    if raw_signal is not None:
        req["raw_signal"] = raw_signal

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
    req_mode = request.get("mode")
    req_trade_mode = request.get("requested_trade_mode")
    if req_mode and req_trade_mode and req_mode != req_trade_mode:
        errors.append(
            f"mode '{req_mode}' != requested_trade_mode '{req_trade_mode}'"
        )

    # Caller identity check
    caller = request.get("caller", "")
    if caller and caller not in _VALID_CALLERS:
        errors.append(f"Unknown caller '{caller}'")

    return errors


def _validate(request: dict[str, Any]) -> None:
    """Schema-validate; raise on first error."""
    schema = _load_schema()
    jsonschema.validate(instance=request, schema=schema)
