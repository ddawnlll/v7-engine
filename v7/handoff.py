"""
V7 HandoffAcceptor — validates and accepts/rejects AlphaForge V7HandoffPackage.

Domain authority:
  - V7 is the final acceptance authority (alphaforge/docs/handoff_to_v7.md).
  - AlphaForge RECOMMENDS; V7 DECIDES.
  - Under NO circumstances does AlphaForge override V7's acceptance decision.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

from v7.gates.evaluator import (
    CANONICAL_GATE_NAMES,
    GateResult,
    GateStatus,
    evaluate_candidate,
    evaluate_gate,
    get_promotion_summary,
)

# ── Schema path ─────────────────────────────────────────────────────────────────

_HANDOFF_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "contracts"
    / "schemas"
    / "alphaforge"
    / "v7_handoff_package.schema.json"
)


# ── Handoff rejection rules (mirrors alphaforge/docs/handoff_to_v7.md) ──────────

HANDOFF_REJECTION_RULES: list[str] = [
    "missing_evidence",
    "incomplete_gate_mapping",
    "lineage_break",
    "checksum_mismatch",
    "validation_failure",
    "cost_vulnerability",
    "overfit_detected",
    "single_symbol_overfitting",
    "calibration_unusable",
    "funding_unknown",
    "blocked_scope_violation",
    "policy_conflict",
]

# ── Data classes ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HandoffAcceptanceRecord:
    """Record produced when V7 accepts or rejects a handoff package.

    Attributes:
        accepted: True if V7 accepted the candidate.
        handoff_package_id: The package's unique identifier.
        mode: The trading mode (SCALP, AGGRESSIVE_SCALP, SWING).
        gates_summary: Summary dict from the gate evaluation.
        schema_errors: List of JSON schema validation errors (empty if valid).
        rejection_rules_triggered: Which handoff rejection rules were triggered.
        rejection_reason: Human-readable reason (empty on acceptance).
        acceptance_id: Unique acceptance identifier (empty on rejection).
        accepted_at: ISO-8601 timestamp (empty on rejection).
    """

    accepted: bool
    handoff_package_id: str
    mode: str
    gates_summary: dict[str, Any] = field(default_factory=dict)
    schema_errors: list[str] = field(default_factory=list)
    rejection_rules_triggered: list[str] = field(default_factory=list)
    rejection_reason: str = ""
    acceptance_id: str = ""
    accepted_at: str = ""


# ── Internal helpers ────────────────────────────────────────────────────────────


def _load_handoff_schema() -> dict[str, Any]:
    """Load the V7HandoffPackage JSON schema from disk."""
    with open(_HANDOFF_SCHEMA_PATH, "r") as fh:
        return json.load(fh)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_candidate_from_package(package: dict) -> dict[str, Any]:
    """Build a gate-compatible candidate dict from a handoff package.

    Handoff packages are cross-symbol artifacts, so ``symbol`` is set to
    ``"MULTI"`` rather than a single ticker.
    """
    return {
        "request_id": package.get("handoff_package_id", ""),
        "mode": package.get("mode", ""),
        "symbol": "MULTI",
        "model_scope": f"{package.get('mode', '').lower()}_v1",
    }


def _extract_context_from_package(package: dict) -> dict[str, Any]:
    """Build a gate context dict from the handoff package's gate mapping.

    Reads v7_gate_mapping statuses and sets context flags.
    For gates with PASS status, sets e.g. G1_research_backtest: True.
    """
    context: dict[str, Any] = {}
    gate_map = package.get("v7_gate_mapping", {})

    for gate_key, gate_entry in gate_map.items():
        if isinstance(gate_entry, dict) and gate_entry.get("status") == "PASS":
            context[gate_key] = True

    # Default calibration ECE when not otherwise specified
    if "G6_calibration_reliability" in gate_map:
        context["ece"] = context.get("ece", 0.05)

    return context


def _gate_result_to_dict(result: GateResult) -> dict[str, Any]:
    """Convert a GateResult to a plain dict for serialization."""
    return {
        "gate_id": result.gate_id,
        "name": result.name,
        "status": result.status.value,
        "score": result.score,
        "threshold": result.threshold,
        "detail": result.detail,
    }


# ── HandoffAcceptor ─────────────────────────────────────────────────────────────


class HandoffAcceptor:
    """V7 handoff package acceptance authority.

    Validates AlphaForge V7HandoffPackages against the JSON schema,
    runs G0-G6 acceptance gates, and produces acceptance or rejection records.

    Usage::

        acceptor = HandoffAcceptor()

        errors = acceptor.validate_contract(package)
        gates = acceptor.run_gates(package)
        record = acceptor.accept_candidate(package, gates)
        # or
        record = acceptor.reject_candidate(package, gates, reason="...")
    """

    def __init__(self) -> None:
        self._schema: dict[str, Any] | None = None

    def _get_schema(self) -> dict[str, Any]:
        if self._schema is None:
            self._schema = _load_handoff_schema()
        return self._schema

    # ── Primary API ──────────────────────────────────────────────────────────

    def validate_contract(self, package: dict) -> list[str]:
        """Validate a handoff package against the JSON schema.

        Args:
            package: The V7HandoffPackage dict to validate.

        Returns:
            A list of validation error messages. An empty list means the
            package is structurally valid.
        """
        schema = self._get_schema()
        try:
            jsonschema.validate(instance=package, schema=schema)
            return []
        except jsonschema.ValidationError as exc:
            return [exc.message]

    def run_gates(
        self,
        package: dict,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run G0-G6 acceptance gates on the handoff package.

        G7-G10 are infrastructure gates not yet evaluated at handoff time;
        they are deferred to the post-acceptance promotion pipeline.

        Args:
            package: The V7HandoffPackage dict.
            context: Optional dict of gate evaluation context values
                     (e.g. ``expectancy_r``, ``expected_r_net``). Merged with
                     context extracted from the package's gate mapping.

        Returns:
            A dict with:
              - ``gates``: {gate_id: gate-dict} for G0-G6
              - ``summary``: promotion summary from ``get_promotion_summary``
        """
        candidate = _extract_candidate_from_package(package)
        ctx = _extract_context_from_package(package)
        if context:
            ctx.update(context)

        results = evaluate_candidate(candidate, ctx)
        summary = get_promotion_summary(results)

        return {
            "gates": {
                gid: _gate_result_to_dict(r)
                for gid, r in results.items()
            },
            "summary": {
                "passed": summary["passed"],
                "overall_score": summary["overall_score"],
                "passed_gates": summary["passed_gates"],
                "failed_gates": summary["failed_gates"],
                "na_gates": summary["na_gates"],
                "recommendation": summary["recommendation"],
            },
        }

    def accept_candidate(
        self,
        package: dict,
        gates: dict[str, Any],
    ) -> HandoffAcceptanceRecord:
        """Produce an acceptance record for a handoff candidate.

        Args:
            package: The V7HandoffPackage dict being accepted.
            gates: The gate evaluation result dict from ``run_gates``.

        Returns:
            A ``HandoffAcceptanceRecord`` with ``accepted=True``.
        """
        schema_errors = self.validate_contract(package)
        acceptance_id = f"v7acc-{uuid.uuid4().hex[:12]}"
        now = _now_iso()

        return HandoffAcceptanceRecord(
            accepted=True,
            handoff_package_id=package.get("handoff_package_id", ""),
            mode=package.get("mode", ""),
            gates_summary=gates.get("summary", {}),
            schema_errors=schema_errors,
            rejection_rules_triggered=[],
            rejection_reason="",
            acceptance_id=acceptance_id,
            accepted_at=now,
        )

    def reject_candidate(
        self,
        package: dict,
        gates: dict[str, Any],
        reason: str,
    ) -> HandoffAcceptanceRecord:
        """Produce a rejection record for a handoff candidate.

        Args:
            package: The V7HandoffPackage dict being rejected.
            gates: The gate evaluation result dict from ``run_gates``.
            reason: Human-readable rejection reason. Also recorded as the
                    triggered rejection rule.

        Returns:
            A ``HandoffAcceptanceRecord`` with ``accepted=False``.
        """
        schema_errors = self.validate_contract(package)

        return HandoffAcceptanceRecord(
            accepted=False,
            handoff_package_id=package.get("handoff_package_id", ""),
            mode=package.get("mode", ""),
            gates_summary=gates.get("summary", {}),
            schema_errors=schema_errors,
            rejection_rules_triggered=[reason],
            rejection_reason=reason,
            acceptance_id="",
            accepted_at="",
        )
