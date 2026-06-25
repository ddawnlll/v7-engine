"""
AnalysisResult validator — contract schema validation and sanity checks.

Validates against contracts/schemas/analysis_result.schema.json and the
canonical authority rules in v7/docs/contracts/analysis_result.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "contracts"
    / "schemas"
    / "analysis_result.schema.json"
)

# Valid enum sets from contract authority
_VALID_DECISIONS = frozenset({"ENTER_LONG", "ENTER_SHORT", "EXIT_LONG", "EXIT_SHORT", "HOLD"})
_VALID_MODES = frozenset({"SCALP", "AGGRESSIVE_SCALP", "SWING"})


def _load_schema() -> dict[str, Any]:
    with open(_SCHEMA_PATH, "r") as fh:
        return json.load(fh)


def build_analysis_result(
    *,
    request_id: str,
    decision: str,
    confidence: float,
    stop_loss_price: float,
    take_profit_price: float,
    entry_price: float,
    position_size_pct: float,
    reasoning: str,
    model_signature: str,
    mode: str,
    symbol: str,
    analysis_result_id: str | None = None,
    analysis_timestamp: str | None = None,
    execution_eligibility: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a contract-valid AnalysisResult dict.

    Args:
        request_id: The request_id of the originating AnalysisRequest.
        decision: Trade decision — ENTER_LONG, ENTER_SHORT, EXIT_LONG,
                  EXIT_SHORT, or HOLD.
        confidence: Model confidence score, normalized 0-1.
        stop_loss_price: Recommended stop-loss price.
        take_profit_price: Recommended take-profit price.
        entry_price: Recommended entry price.
        position_size_pct: Position size as percentage of portfolio (0-100).
        reasoning: Human- or machine-readable reasoning.
        model_signature: Model identifier, e.g. 'swing_v1@abc123'.
        mode: Trading mode — SCALP, AGGRESSIVE_SCALP, SWING.
        symbol: Trading symbol, e.g. 'BTCUSDT'.
        analysis_result_id: Unique result ID (auto-generated if omitted).
        analysis_timestamp: UTC ISO 8601 (now if omitted).
        execution_eligibility: Gate result dict (auto-built if omitted).

    Returns:
        A dict that passes schema validation.

    Raises:
        ValueError: If required fields are invalid.
        jsonschema.ValidationError: If schema validation fails.
    """
    import uuid
    from datetime import datetime, timezone

    if decision not in _VALID_DECISIONS:
        raise ValueError(
            f"Invalid decision '{decision}'. Must be one of: {sorted(_VALID_DECISIONS)}"
        )
    if mode not in _VALID_MODES:
        raise ValueError(
            f"Invalid mode '{mode}'. Must be one of: {sorted(_VALID_MODES)}"
        )
    if not (0.0 <= confidence <= 1.0):
        raise ValueError(f"confidence must be 0.0-1.0, got {confidence}")
    if position_size_pct < 0:
        raise ValueError(f"position_size_pct must be >= 0, got {position_size_pct}")

    # Build default execution eligibility gates
    if execution_eligibility is None:
        execution_eligibility = {
            "confidence_gate": True,
            "risk_gate": True,
            "regime_gate": True,
            "cost_gate": True,
            "overall_eligible": True,
        }

    result: dict[str, Any] = {
        "analysis_result_id": analysis_result_id or f"ar_{uuid.uuid4().hex[:12]}",
        "request_id": request_id,
        "decision": decision,
        "confidence": confidence,
        "stop_loss_price": stop_loss_price,
        "take_profit_price": take_profit_price,
        "entry_price": entry_price,
        "position_size_pct": position_size_pct,
        "reasoning": reasoning,
        "model_signature": model_signature,
        "analysis_timestamp": analysis_timestamp or datetime.now(timezone.utc).isoformat(),
        "execution_eligibility": execution_eligibility,
        "mode": mode,
        "symbol": symbol.upper(),
    }

    _validate(result)
    return result


def validate_analysis_result(result: dict[str, Any]) -> list[str]:
    """Validate an AnalysisResult dict against schema and sanity rules.

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

    # Sanity checks
    decision = result.get("decision", "")
    confidence = result.get("confidence", 0.0)

    # Entry prices must be positive for directional trades
    if decision in ("ENTER_LONG", "ENTER_SHORT", "EXIT_LONG", "EXIT_SHORT"):
        entry = result.get("entry_price", 0.0)
        stop = result.get("stop_loss_price", 0.0)
        take = result.get("take_profit_price", 0.0)
        if entry <= 0:
            errors.append("entry_price must be > 0 for directional trades")
        if stop <= 0:
            errors.append("stop_loss_price must be > 0 for directional trades")
        if take <= 0:
            errors.append("take_profit_price must be > 0 for directional trades")
        # Stop/take sanity for longs
        if decision == "ENTER_LONG" and stop >= entry:
            errors.append("stop_loss_price must be < entry_price for ENTER_LONG")
        if decision == "ENTER_LONG" and take <= entry:
            errors.append("take_profit_price must be > entry_price for ENTER_LONG")
        # Stop/take sanity for shorts
        if decision == "ENTER_SHORT" and stop <= entry:
            errors.append("stop_loss_price must be > entry_price for ENTER_SHORT")
        if decision == "ENTER_SHORT" and take >= entry:
            errors.append("take_profit_price must be < entry_price for ENTER_SHORT")

    # Execution eligibility consistency
    eligibility = result.get("execution_eligibility", {})
    if eligibility:
        gates_ok = all(
            eligibility.get(g, True)
            for g in ("confidence_gate", "risk_gate", "regime_gate", "cost_gate")
        )
        overall = eligibility.get("overall_eligible", None)
        if gates_ok and overall is False:
            errors.append(
                "execution_eligibility: all gates passed but overall_eligible is false"
            )
        if not gates_ok and overall is True:
            errors.append(
                "execution_eligibility: some gates failed but overall_eligible is true"
            )

    return errors


def _validate(result: dict[str, Any]) -> None:
    schema = _load_schema()
    jsonschema.validate(instance=result, schema=schema)
