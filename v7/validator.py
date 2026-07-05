"""
AnalysisResult builder and validator — full V7 contract shape.

Produces / validates AnalysisResult dicts that conform to
contracts/schemas/analysis_result.schema.json AND the canonical
v7/docs/contracts/analysis_result.md authority rules.

V7 top-level shape:
  contract / identity / request_link / status / decision / scores /
  execution_guidance / uncertainty_and_quality / deterministic_interaction /
  fallback_and_degradation / observability / lineage

V7-style decisions: LONG_NOW, SHORT_NOW, NO_TRADE (replaces V6's
ENTER_LONG/ENTER_SHORT/EXIT_LONG/EXIT_SHORT/HOLD).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "contracts"
    / "schemas"
    / "analysis_result.schema.json"
)

# V7 action enums (V6-style ENTER_LONG/ENTER_SHORT/EXIT_LONG/EXIT_SHORT/HOLD removed)
_VALID_RECOMMENDED_ACTIONS = frozenset({"LONG_NOW", "SHORT_NOW", "NO_TRADE"})
_VALID_DIRECTIONS = frozenset({"LONG", "SHORT", "NONE"})
_VALID_MODES = frozenset({"SWING", "SCALP", "AGGRESSIVE_SCALP"})
_VALID_SIGNAL_STATUSES = frozenset(
    {"SIGNAL", "NO_TRADE", "FILTERED", "DEGRADED", "ERROR"}
)
_VALID_DECISION_STATUSES = frozenset(
    {"VALID", "LOW_CONFIDENCE", "BLOCKED", "DEGRADED", "FAILED"}
)
_VALID_TIME_SENSITIVITIES = frozenset(
    {"IMMEDIATE", "STANDARD", "CAN_WAIT", "EXPIRING_SOON"}
)
_VALID_ENTRY_READINESS = frozenset(
    {"READY_NOW", "WAIT", "CHASING", "EXPIRING", "MISSED", "NOT_APPLICABLE"}
)

# Action-to-direction mapping
_ACTION_DIRECTION_MAP: dict[str, str] = {
    "LONG_NOW": "LONG",
    "SHORT_NOW": "SHORT",
    "NO_TRADE": "NONE",
}

# Default contract versions
_DEFAULT_CONTRACT_VERSION = "v7-0.3"
_DEFAULT_RESPONSE_SCHEMA_VERSION = "result-0.3"
_DEFAULT_ENGINE_OUTPUT_VERSION = "engine-out-0.3"


def _load_schema() -> dict[str, Any]:
    with open(_SCHEMA_PATH, "r") as fh:
        return json.load(fh)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_analysis_result(
    *,
    request_id: str,
    recommended_action: str = "NO_TRADE",
    direction: str | None = None,
    decision_summary: str = "",
    confidence: float = 0.0,
    confidence_kind: str = "RAW",
    expected_r: float = 0.0,
    signal_status: str = "NO_TRADE",
    decision_status: str = "VALID",
    is_actionable: bool = False,
    engine_name: str = "v7",
    engine_version: str = "0.3.0",
    model_scope: str = "",
    trade_mode: str = "",
    analysis_result_id: str | None = None,
    timestamp_utc: str | None = None,
    run_id: str | None = None,
    # Execution guidance (required for actionable directional trades)
    entry_price: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    time_sensitivity: str | None = None,
    entry_readiness: str | None = None,
    entry_valid_for_bars: int | None = None,
    entry_zone: list[float] | None = None,
    size_multiplier: float | None = None,
    risk_expression: str | None = None,
    execution_notes: str | None = None,
    # Scores extras
    long_score: float | None = None,
    short_score: float | None = None,
    no_trade_score: float | None = None,
    decision_margin: float | None = None,
    probability: float | None = None,
    expected_drawdown: float | None = None,
    # Fallback
    fallback_used: bool = False,
    degraded_reason: Any = None,
    fallback_reason: Any = None,
    fallback_source: Any = None,
    runtime_safe_action: Any = None,
    is_timeout_fallback: bool = False,
    is_schema_fallback: bool = False,
    # Optional sections (fully custom)
    request_link: dict[str, Any] | None = None,
    uncertainty_and_quality: dict[str, Any] | None = None,
    deterministic_interaction: dict[str, Any] | None = None,
    observability: dict[str, Any] | None = None,
    lineage: dict[str, Any] | None = None,
    # Contract version overrides
    contract_version: str = _DEFAULT_CONTRACT_VERSION,
    response_schema_version: str = _DEFAULT_RESPONSE_SCHEMA_VERSION,
    engine_output_version: str = _DEFAULT_ENGINE_OUTPUT_VERSION,
) -> dict[str, Any]:
    """Build a contract-valid V7 AnalysisResult dict.

    Args:
        request_id: The request_id of the originating AnalysisRequest.
        recommended_action: V7 recommended action — LONG_NOW, SHORT_NOW, NO_TRADE.
        direction: Trade direction (auto-set from action if omitted).
        decision_summary: Human-readable decision summary.
        confidence: Model confidence score, normalized 0-1.
        confidence_kind: Kind of confidence (RAW, CALIBRATED, etc.).
        expected_r: Expected R-multiple for the recommended action.
        signal_status: Signal status — SIGNAL, NO_TRADE, FILTERED, DEGRADED, ERROR.
        decision_status: Decision status — VALID, LOW_CONFIDENCE, BLOCKED,
                         DEGRADED, FAILED.
        is_actionable: True if result is eligible for execution consideration.
        engine_name: Engine name, e.g. 'v7'.
        engine_version: Engine version, e.g. '0.3.0'.
        model_scope: Model scope that produced this result.
        trade_mode: Trade mode under which result was produced.
        analysis_result_id: Unique result ID (auto-generated if omitted).
        timestamp_utc: UTC ISO 8601 (now if omitted).
        run_id: Optional scan-run identifier.
        entry_price: Recommended entry price.
        stop_loss: Recommended stop-loss price.
        take_profit: Recommended take-profit price.
        time_sensitivity: Entry timing urgency.
        entry_readiness: Current entry readiness.
        entry_valid_for_bars: Expected validity in bars (0-5).
        entry_zone: Entry zone as [low, high].
        size_multiplier: Position size multiplier.
        risk_expression: Risk expression (LOW, MEDIUM, HIGH).
        execution_notes: Free-form execution notes.
        long_score: Score for LONG action.
        short_score: Score for SHORT action.
        no_trade_score: Score for NO_TRADE action.
        decision_margin: Margin between top action and next best.
        probability: Action probability estimate.
        expected_drawdown: Expected adverse drawdown in R.
        fallback_used: True if fallback path was used.
        degraded_reason: Reason for degradation.
        fallback_reason: Reason for fallback.
        fallback_source: Source component of fallback.
        runtime_safe_action: Safe action for runtime.
        is_timeout_fallback: True if fallback due to timeout.
        is_schema_fallback: True if fallback due to schema mismatch.
        request_link: Custom request_link dict (auto-built if omitted and
                      model_scope/trade_mode provided).
        uncertainty_and_quality: Optional uncertainty section.
        deterministic_interaction: Optional deterministic interaction section.
        observability: Optional observability section.
        lineage: Optional lineage section.
        contract_version: Override default contract version.
        response_schema_version: Override default response schema version.
        engine_output_version: Override default engine output version.

    Returns:
        A dict that passes V7 schema validation.

    Raises:
        ValueError: If required fields are invalid.
        jsonschema.ValidationError: If schema validation fails.
    """
    # --- Validate inputs ---
    if recommended_action not in _VALID_RECOMMENDED_ACTIONS:
        raise ValueError(
            f"Invalid recommended_action '{recommended_action}'. "
            f"Must be one of: {sorted(_VALID_RECOMMENDED_ACTIONS)}"
        )
    if trade_mode and trade_mode not in _VALID_MODES:
        raise ValueError(
            f"Invalid trade_mode '{trade_mode}'. Must be one of: {sorted(_VALID_MODES)}"
        )
    if signal_status not in _VALID_SIGNAL_STATUSES:
        raise ValueError(
            f"Invalid signal_status '{signal_status}'. "
            f"Must be one of: {sorted(_VALID_SIGNAL_STATUSES)}"
        )
    if decision_status not in _VALID_DECISION_STATUSES:
        raise ValueError(
            f"Invalid decision_status '{decision_status}'. "
            f"Must be one of: {sorted(_VALID_DECISION_STATUSES)}"
        )
    if time_sensitivity is not None and time_sensitivity not in _VALID_TIME_SENSITIVITIES:
        raise ValueError(
            f"Invalid time_sensitivity '{time_sensitivity}'. "
            f"Must be one of: {sorted(_VALID_TIME_SENSITIVITIES)}"
        )
    if entry_readiness is not None and entry_readiness not in _VALID_ENTRY_READINESS:
        raise ValueError(
            f"Invalid entry_readiness '{entry_readiness}'. "
            f"Must be one of: {sorted(_VALID_ENTRY_READINESS)}"
        )
    if not (0.0 <= confidence <= 1.0):
        raise ValueError(f"confidence must be 0.0-1.0, got {confidence}")

    # Resolve direction from action if not explicitly provided
    resolved_direction = direction if direction is not None else _ACTION_DIRECTION_MAP[recommended_action]
    if resolved_direction not in _VALID_DIRECTIONS:
        raise ValueError(
            f"Invalid direction '{resolved_direction}'. "
            f"Must be one of: {sorted(_VALID_DIRECTIONS)}"
        )

    # --- Build timestamps / IDs ---
    ts = timestamp_utc or _utc_now()
    ar_id = analysis_result_id or f"ar_{uuid.uuid4().hex[:12]}"

    # --- Contract section ---
    contract_section: dict[str, Any] = {
        "contract_version": contract_version,
        "response_schema_version": response_schema_version,
        "engine_output_version": engine_output_version,
    }

    # --- Identity section ---
    identity_section: dict[str, Any] = {
        "request_id": request_id,
        "engine_name": engine_name,
        "engine_version": engine_version,
        "timestamp_utc": ts,
    }
    if run_id is not None:
        identity_section["run_id"] = run_id
    if model_scope:
        identity_section["model_scope"] = model_scope
    if trade_mode:
        identity_section["trade_mode"] = trade_mode

    # --- Request link section (auto-build if not provided) ---
    if request_link is None and model_scope and trade_mode:
        request_link = {
            "model_scope": model_scope,
            "trade_mode": trade_mode,
        }

    # --- Status section ---
    status_section: dict[str, Any] = {
        "signal_status": signal_status,
        "decision_status": decision_status,
        "is_actionable": is_actionable,
    }

    # --- Decision section ---
    decision_section: dict[str, Any] = {
        "recommended_action": recommended_action,
        "direction": resolved_direction,
        "decision_summary": decision_summary,
    }

    # --- Scores section ---
    scores_section: dict[str, Any] = {
        "confidence": confidence,
        "confidence_kind": confidence_kind,
        "expected_r": expected_r,
    }
    if probability is not None:
        scores_section["probability"] = probability
    if expected_drawdown is not None:
        scores_section["expected_drawdown"] = expected_drawdown
    if decision_margin is not None:
        scores_section["decision_margin"] = decision_margin
    if long_score is not None:
        scores_section["long_score"] = long_score
    if short_score is not None:
        scores_section["short_score"] = short_score
    if no_trade_score is not None:
        scores_section["no_trade_score"] = no_trade_score

    # --- Execution guidance (conditional on actionable trades) ---
    execution_guidance: dict[str, Any] | None = None
    if recommended_action in ("LONG_NOW", "SHORT_NOW") and is_actionable:
        execution_guidance = {}
        if entry_price is not None:
            execution_guidance["entry_price"] = entry_price
        if stop_loss is not None:
            execution_guidance["stop_loss"] = stop_loss
        if take_profit is not None:
            execution_guidance["take_profit"] = take_profit
        if time_sensitivity is not None:
            execution_guidance["time_sensitivity"] = time_sensitivity
        if entry_readiness is not None:
            execution_guidance["entry_readiness"] = entry_readiness
        if entry_valid_for_bars is not None:
            execution_guidance["entry_valid_for_bars"] = entry_valid_for_bars
        if entry_zone is not None:
            execution_guidance["entry_zone"] = entry_zone
        if size_multiplier is not None:
            execution_guidance["size_multiplier"] = size_multiplier
        if risk_expression is not None:
            execution_guidance["risk_expression"] = risk_expression
        if execution_notes is not None:
            execution_guidance["execution_notes"] = execution_notes
    elif recommended_action == "NO_TRADE" and entry_readiness is not None:
        # Non-actionable can optionally carry entry_readiness metadata
        if entry_readiness is not None:
            execution_guidance = {"entry_readiness": entry_readiness}

    # --- Fallback and degradation section ---
    fallback_section: dict[str, Any] = {
        "fallback_used": fallback_used,
        "degraded_reason": degraded_reason,
        "fallback_reason": fallback_reason,
        "fallback_source": fallback_source,
        "runtime_safe_action": runtime_safe_action,
        "is_timeout_fallback": is_timeout_fallback,
        "is_schema_fallback": is_schema_fallback,
    }

    # --- Assemble result ---
    result: dict[str, Any] = {
        "contract": contract_section,
        "identity": identity_section,
        "status": status_section,
        "decision": decision_section,
        "scores": scores_section,
        "fallback_and_degradation": fallback_section,
    }

    if request_link is not None:
        result["request_link"] = request_link
    if execution_guidance is not None:
        result["execution_guidance"] = execution_guidance
    if uncertainty_and_quality is not None:
        result["uncertainty_and_quality"] = uncertainty_and_quality
    if deterministic_interaction is not None:
        result["deterministic_interaction"] = deterministic_interaction
    if observability is not None:
        result["observability"] = observability
    if lineage is not None:
        result["lineage"] = lineage

    _validate(result)
    return result


def validate_analysis_result(result: dict[str, Any]) -> list[str]:
    """Validate an AnalysisResult dict against schema and authority rules.

    Returns a list of validation error messages (empty = valid).
    """
    errors: list[str] = []

    # Schema validation
    try:
        schema = _load_schema()
        jsonschema.validate(instance=result, schema=schema)
    except jsonschema.ValidationError as exc:
        errors.append(f"Schema: {exc.message}")
        return errors

    # --- Authority-level cross-field checks ---
    contract = result.get("contract", {})
    status = result.get("status", {})
    decision = result.get("decision", {})
    scores = result.get("scores", {})
    guidance = result.get("execution_guidance")
    fallback = result.get("fallback_and_degradation", {})
    req_link = result.get("request_link", {})

    recommended_action = decision.get("recommended_action", "")
    direction = decision.get("direction", "")
    signal_status = status.get("signal_status", "")
    decision_status = status.get("decision_status", "")
    is_actionable = status.get("is_actionable", False)
    fallback_used = fallback.get("fallback_used", False)

    # --- 1. Action-direction consistency ---
    expected_direction = _ACTION_DIRECTION_MAP.get(recommended_action)
    if expected_direction and direction != expected_direction:
        errors.append(
            f"direction '{direction}' does not match recommended_action "
            f"'{recommended_action}' (expected '{expected_direction}')"
        )

    # --- 2. Actionability consistency ---
    # NO_TRADE must not be actionable
    if recommended_action == "NO_TRADE" and is_actionable:
        errors.append(
            "NO_TRADE recommended_action but is_actionable is true"
        )
    # SIGNAL/DEGRADED/ERROR signal_status with actionable inconsistent
    if signal_status in ("NO_TRADE", "FILTERED", "ERROR") and is_actionable:
        errors.append(
            f"signal_status '{signal_status}' but is_actionable is true"
        )

    # --- 3. Execution guidance for actionable directional trades ---
    if recommended_action in ("LONG_NOW", "SHORT_NOW") and is_actionable:
        if guidance is None:
            errors.append(
                "execution_guidance required for actionable directional trade"
            )
        else:
            if guidance.get("entry_price") is None:
                errors.append("execution_guidance.entry_price required for actionable trade")
            if guidance.get("stop_loss") is None:
                errors.append("execution_guidance.stop_loss required for actionable trade")
            if guidance.get("take_profit") is None:
                errors.append("execution_guidance.take_profit required for actionable trade")
            if guidance.get("time_sensitivity") is None:
                errors.append("execution_guidance.time_sensitivity required for actionable trade")

    # --- 4. entry_valid_for_bars range check ---
    if guidance and guidance.get("entry_valid_for_bars") is not None:
        evfb = guidance["entry_valid_for_bars"]
        if not isinstance(evfb, int) or evfb < 0 or evfb > 5:
            errors.append(
                f"entry_valid_for_bars must be integer 0-5, got {evfb}"
            )

    # --- 5. entry_readiness consistency ---
    if guidance and guidance.get("entry_readiness") is not None:
        er = guidance["entry_readiness"]
        if er not in _VALID_ENTRY_READINESS:
            errors.append(f"Unknown entry_readiness '{er}'")
        # NOT_APPLICABLE should only appear for NO_TRADE
        if er == "NOT_APPLICABLE" and recommended_action != "NO_TRADE":
            errors.append(
                "entry_readiness NOT_APPLICABLE should only appear for NO_TRADE"
            )

    # --- 6. Fallback consistency ---
    if fallback_used and fallback.get("degraded_reason") is None:
        errors.append(
            "fallback_used is true but degraded_reason is null/missing"
        )
    if not fallback_used and fallback.get("degraded_reason") is not None:
        errors.append(
            "fallback_used is false but degraded_reason is provided"
        )

    # --- 7. Confidence range ---
    confidence = scores.get("confidence", 0.0)
    if not (0.0 <= confidence <= 1.0):
        errors.append(f"confidence must be 0.0-1.0, got {confidence}")

    # --- 8. Decision_status with actionable ---
    if decision_status in ("FAILED", "BLOCKED") and is_actionable:
        errors.append(
            f"decision_status '{decision_status}' but is_actionable is true"
        )

    # --- 9. Contract version check ---
    cv = contract.get("contract_version", "")
    if not cv or not isinstance(cv, str):
        errors.append("contract.contract_version must be a non-empty string")

    # --- 10. Request link consistency (if present) ---
    if req_link:
        rl_trade_mode = req_link.get("trade_mode")
        identity_trade_mode = result.get("identity", {}).get("trade_mode")
        if rl_trade_mode and identity_trade_mode and rl_trade_mode != identity_trade_mode:
            errors.append(
                f"request_link.trade_mode '{rl_trade_mode}' != "
                f"identity.trade_mode '{identity_trade_mode}'"
            )

        # model_scope consistency check
        rl_model_scope = req_link.get("model_scope")
        identity_model_scope = result.get("identity", {}).get("model_scope")
        if rl_model_scope and identity_model_scope and rl_model_scope != identity_model_scope:
            errors.append(
                f"request_link.model_scope '{rl_model_scope}' != "
                f"identity.model_scope '{identity_model_scope}'"
            )

        # symbol must be non-empty if present
        rl_symbol = req_link.get("symbol")
        if rl_symbol is not None and (not isinstance(rl_symbol, str) or not rl_symbol):
            errors.append(
                "request_link.symbol must be a non-empty string when present"
            )

    return errors


def validate_result_against_request(
    result: dict[str, Any],
    request: dict[str, Any],
) -> list[str]:
    """Cross-validate an AnalysisResult against its originating AnalysisRequest.

    Checks that request_link fields and identity match the originating request
    per the V7 contract request compatibility rules.

    Returns a list of validation error messages (empty = valid).
    """
    errors: list[str] = []

    # 1. request_id must match
    result_req_id = result.get("identity", {}).get("request_id", "")
    request_req_id = request.get("identity", {}).get("request_id", "")
    if result_req_id and request_req_id and result_req_id != request_req_id:
        errors.append(
            f"result identity.request_id '{result_req_id}' != "
            f"request identity.request_id '{request_req_id}'"
        )

    # 2. request_link validation against request scope
    req_link = result.get("request_link", {})
    request_scope = request.get("scope", {})
    request_contract = request.get("contract", {})
    request_lineage = request.get("lineage", {})
    result_lineage = result.get("lineage", {})

    if req_link:
        # symbol match
        rl_symbol = req_link.get("symbol")
        req_symbol = request_scope.get("symbol")
        if rl_symbol and req_symbol and rl_symbol != req_symbol:
            errors.append(
                f"request_link.symbol '{rl_symbol}' != "
                f"request.scope.symbol '{req_symbol}'"
            )

        # model_scope match
        rl_model_scope = req_link.get("model_scope")
        req_model_scope = request_scope.get("model_scope")
        if rl_model_scope and req_model_scope and rl_model_scope != req_model_scope:
            errors.append(
                f"request_link.model_scope '{rl_model_scope}' != "
                f"request.scope.model_scope '{req_model_scope}'"
            )

        # trade_mode match
        rl_trade_mode = req_link.get("trade_mode")
        req_trade_mode = request_scope.get("requested_trade_mode")
        if rl_trade_mode and req_trade_mode and rl_trade_mode != req_trade_mode:
            errors.append(
                f"request_link.trade_mode '{rl_trade_mode}' != "
                f"request.scope.requested_trade_mode '{req_trade_mode}'"
            )

        # primary_interval match
        rl_primary = req_link.get("primary_interval")
        req_primary = request_scope.get("primary_interval")
        if rl_primary and req_primary and rl_primary != req_primary:
            errors.append(
                f"request_link.primary_interval '{rl_primary}' != "
                f"request.scope.primary_interval '{req_primary}'"
            )

        # request_contract_version match
        rl_contract_ver = req_link.get("request_contract_version")
        req_contract_ver = request_contract.get("contract_version")
        if rl_contract_ver and req_contract_ver and rl_contract_ver != req_contract_ver:
            errors.append(
                f"request_link.request_contract_version '{rl_contract_ver}' != "
                f"request.contract.contract_version '{req_contract_ver}'"
            )

    # 3. Lineage consistency (when both exist)
    result_batch_id = result_lineage.get("analysis_batch_id")
    request_batch_id = request_lineage.get("analysis_batch_id")
    if result_batch_id and request_batch_id and result_batch_id != request_batch_id:
        errors.append(
            f"result lineage.analysis_batch_id '{result_batch_id}' != "
            f"request lineage.analysis_batch_id '{request_batch_id}'"
        )

    result_session_id = result_lineage.get("decision_session_id")
    request_session_id = request_lineage.get("decision_session_id")
    if result_session_id and request_session_id and result_session_id != request_session_id:
        errors.append(
            f"result lineage.decision_session_id '{result_session_id}' != "
            f"request lineage.decision_session_id '{request_session_id}'"
        )

    return errors


def _validate(result: dict[str, Any]) -> None:
    schema = _load_schema()
    jsonschema.validate(instance=result, schema=schema)
