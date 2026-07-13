"""Immutable AlphaForge candidate admission gate owned by V7.

The gate deliberately runs *before* :func:`v7.policy.evaluate_policy`.  Its
only responsibility is to reject a candidate whose frozen research package is
not eligible for shadow evaluation.  A successful admission is not a trade
decision and never bypasses V7 policy, portfolio, runtime, or risk controls.

The manifest is intentionally JSON-only and contains opaque AlphaForge IDs.
V7 therefore consumes a versioned evidence package without importing
AlphaForge implementation code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from v7.router import validate_scope_compatibility
from v7.portfolio import PortfolioManager, PortfolioResult


MANIFEST_VERSION = "v7-lite-candidate-1.0"
_REQUIRED_PRE_SHADOW_GATES = ("G0", "G1", "G2", "G3", "G4", "G5", "G6")
_SHADOW_ONLY = "SHADOW"


class ManifestValidationError(ValueError):
    """Raised when an immutable candidate manifest is structurally invalid."""


@dataclass(frozen=True)
class FrozenCandidateManifest:
    """The immutable V7 view of an AlphaForge candidate package."""

    candidate_id: str
    mode: str
    model_scope: str
    artifact_id: str
    artifact_sha256: str
    feature_schema_id: str
    supported_symbols: frozenset[str]
    valid_from: datetime
    valid_until: datetime | None
    gate_statuses: Mapping[str, str]
    deployment_stage: str


@dataclass(frozen=True)
class CandidateAdmission:
    """Deterministic pre-policy outcome for one requested market state."""

    allowed: bool
    candidate_id: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class ShadowDispatch:
    """Outcome of the V7-Lite admission boundary around shadow recording.

    ``shadow_record`` is intentionally opaque so V7-Lite does not duplicate
    the ShadowModeManager contract.  It is ``None`` when lineage/evidence did
    not permit an observation to be recorded.
    """

    admission: CandidateAdmission
    shadow_record: Any | None


@dataclass(frozen=True)
class CandidateSignal:
    """An admitted SHADOW signal; this is not an executable order."""

    candidate_id: str
    symbol: str
    direction: str
    expected_r_net: float
    confidence: float
    position_size_pct: float


def apply_shadow_portfolio_controls(
    signals: Iterable[CandidateSignal],
    positions: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> PortfolioResult:
    """Apply the existing V7 portfolio caps after candidate admission."""
    requests: list[dict[str, str]] = []
    results: list[dict[str, Any]] = []
    for signal in signals:
        requests.append({"symbol": signal.symbol, "direction": signal.direction})
        results.append({
            "symbol": signal.symbol, "passed": True, "decision": signal.direction,
            "expected_r_net": signal.expected_r_net, "confidence": signal.confidence,
            "position_size_pct": signal.position_size_pct,
        })
    return PortfolioManager(dict(config or {})).evaluate_portfolio(requests, results, dict(positions))


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestValidationError(f"{field} must be a non-empty string")
    return value


def _parse_timestamp(value: Any, field: str) -> datetime:
    text = _required_string(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ManifestValidationError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ManifestValidationError(f"{field} must include a UTC offset")
    return parsed


def _required_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ManifestValidationError(f"{field} must be an object")
    return value


def parse_frozen_candidate_manifest(data: Mapping[str, Any]) -> FrozenCandidateManifest:
    """Parse and validate the small V7-Lite candidate manifest contract.

    The input is validated strictly enough to prevent accidental research
    configuration drift.  It remains a V7-local admission contract rather
    than a new cross-domain execution contract.
    """
    if not isinstance(data, Mapping):
        raise ManifestValidationError("manifest must be an object")
    if data.get("manifest_version") != MANIFEST_VERSION:
        raise ManifestValidationError(
            f"manifest_version must be '{MANIFEST_VERSION}'"
        )

    mode = _required_string(data.get("mode"), "mode").upper()
    model_scope = _required_string(data.get("model_scope"), "model_scope")
    scope_error = validate_scope_compatibility(mode, model_scope)
    if scope_error:
        raise ManifestValidationError(scope_error)

    artifact = _required_mapping(data.get("artifact"), "artifact")
    scope = _required_mapping(data.get("scope"), "scope")
    evidence = _required_mapping(data.get("evidence"), "evidence")
    gate_statuses = _required_mapping(evidence.get("gate_statuses"), "evidence.gate_statuses")

    symbols = scope.get("supported_symbols")
    if not isinstance(symbols, list) or not symbols or not all(
        isinstance(symbol, str) and symbol for symbol in symbols
    ):
        raise ManifestValidationError("scope.supported_symbols must be a non-empty string list")

    deployment_stage = _required_string(data.get("deployment_stage"), "deployment_stage").upper()
    if deployment_stage != _SHADOW_ONLY:
        raise ManifestValidationError("deployment_stage must be SHADOW; V7-Lite admits no orders")

    valid_from = _parse_timestamp(scope.get("valid_from"), "scope.valid_from")
    valid_until_raw = scope.get("valid_until")
    valid_until = (
        _parse_timestamp(valid_until_raw, "scope.valid_until")
        if valid_until_raw is not None
        else None
    )
    if valid_until is not None and valid_until <= valid_from:
        raise ManifestValidationError("scope.valid_until must be after scope.valid_from")

    return FrozenCandidateManifest(
        candidate_id=_required_string(data.get("candidate_id"), "candidate_id"),
        mode=mode,
        model_scope=model_scope,
        artifact_id=_required_string(artifact.get("artifact_id"), "artifact.artifact_id"),
        artifact_sha256=_required_string(artifact.get("sha256"), "artifact.sha256"),
        feature_schema_id=_required_string(
            artifact.get("feature_schema_id"), "artifact.feature_schema_id"
        ),
        supported_symbols=frozenset(symbols),
        valid_from=valid_from,
        valid_until=valid_until,
        gate_statuses={str(key): str(value) for key, value in gate_statuses.items()},
        deployment_stage=deployment_stage,
    )


def load_frozen_candidate_manifest(path: str | Path) -> FrozenCandidateManifest:
    """Load a JSON candidate manifest without importing AlphaForge code."""
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestValidationError(f"invalid JSON manifest: {source}") from exc
    return parse_frozen_candidate_manifest(raw)


def evaluate_frozen_candidate(
    manifest: FrozenCandidateManifest,
    *,
    symbol: str,
    mode: str,
    model_scope: str,
    decision_timestamp: datetime,
    artifact_sha256: str,
    feature_schema_id: str,
    deployment_stage: str = _SHADOW_ONLY,
) -> CandidateAdmission:
    """Check fixed lineage and scope before the ordinary V7 policy gates.

    ``allowed=True`` only means the candidate may be evaluated in shadow
    mode.  The caller must still execute V7 policy, portfolio, risk, and
    runtime eligibility checks afterwards.
    """
    reasons: list[str] = []
    if deployment_stage.upper() != _SHADOW_ONLY:
        reasons.append("deployment_stage_not_shadow")
    if manifest.deployment_stage != _SHADOW_ONLY:
        reasons.append("manifest_not_shadow_only")
    if mode.upper() != manifest.mode:
        reasons.append("mode_mismatch")
    if model_scope != manifest.model_scope:
        reasons.append("model_scope_mismatch")
    if symbol not in manifest.supported_symbols:
        reasons.append("unsupported_symbol")
    if artifact_sha256 != manifest.artifact_sha256:
        reasons.append("artifact_checksum_mismatch")
    if feature_schema_id != manifest.feature_schema_id:
        reasons.append("feature_schema_mismatch")
    if decision_timestamp.tzinfo is None:
        reasons.append("decision_timestamp_not_timezone_aware")
    elif decision_timestamp < manifest.valid_from:
        reasons.append("candidate_not_yet_valid")
    elif manifest.valid_until is not None and decision_timestamp >= manifest.valid_until:
        reasons.append("candidate_expired")

    for gate_id in _REQUIRED_PRE_SHADOW_GATES:
        if manifest.gate_statuses.get(gate_id) != "PASS":
            reasons.append(f"pre_shadow_gate_not_passed:{gate_id}")

    return CandidateAdmission(
        allowed=not reasons,
        candidate_id=manifest.candidate_id,
        reason_codes=tuple(reasons),
    )


def admit_and_execute_shadow(
    manifest: FrozenCandidateManifest,
    *,
    shadow_manager: Any,
    proposed_decision: Mapping[str, Any],
    symbol: str,
    mode: str,
    model_scope: str,
    decision_timestamp: datetime,
    artifact_sha256: str,
    feature_schema_id: str,
    shadow_pipeline: Any = None,
) -> ShadowDispatch:
    """Enforce immutable admission immediately before shadow observation.

    This is deliberately a *shadow-only* boundary: callers must already have
    run normal V7 policy, portfolio and runtime eligibility.  A rejected
    research candidate cannot create a shadow record, which prevents a HOLD
    experiment from being mistaken for active V7-Lite evidence.
    """
    admission = evaluate_frozen_candidate(
        manifest,
        symbol=symbol,
        mode=mode,
        model_scope=model_scope,
        decision_timestamp=decision_timestamp,
        artifact_sha256=artifact_sha256,
        feature_schema_id=feature_schema_id,
    )
    if not admission.allowed:
        return ShadowDispatch(admission=admission, shadow_record=None)

    record = shadow_manager.execute_shadow(
        dict(proposed_decision),
        model_scope,
        shadow_pipeline=shadow_pipeline,
    )
    return ShadowDispatch(admission=admission, shadow_record=record)
