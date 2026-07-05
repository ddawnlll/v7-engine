"""
V7 V7PromotionEngine — promotes AlphaForge handoff candidates through G0-G10 gates.

The promotion pipeline:
  1. Schema validation (structural contract check)
  2. Pre-acceptance gates  (G0-G4): doc readiness, research backtest, OOS edge,
     cost stress, regime breakdown
  3. Acceptance record      (V7 accepts the candidate)
  4. Artifact registration  (V7 registers the promoted artifact)
  5. Post-acceptance gates  (G5-G10): symbol stability, calibration, shadow,
     paper, tiny-live, live
  6. Promotion result       (final decision with next steps)

Domain rules:
  - Pre-acceptance failure -> rejection (no post gates run).
  - Post-acceptance failure -> candidate held with diagnostic next steps.
  - G7-G10 return NOT_APPLICABLE until infrastructure is built (P0.9A+).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from v7.gates.evaluator import (
    GateResult,
    GateStatus,
    evaluate_gate,
)
from v7.handoff import HandoffAcceptor, _extract_candidate_from_package

# ── Pre/post gate sets ─────────────────────────────────────────────────────────

PRE_ACCEPTANCE_GATES: list[str] = ["G0", "G1", "G2", "G3", "G4"]
POST_ACCEPTANCE_GATES: list[str] = ["G5", "G6", "G7", "G8", "G9", "G10"]


# ── Data classes ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PromotionResult:
    """Result of promoting a handoff package through V7 gates.

    Attributes:
        promoted: True if all applicable gates passed.
        artifact_id: V7 artifact identifier (empty if not promoted).
        gates_summary: Summary dict from post-acceptance gates (or error).
        next_steps: List of recommended next actions.
        pre_acceptance: Pre-acceptance gate evaluation result (G0-G4).
        post_acceptance: Post-acceptance gate evaluation result (G5-G10).
        handoff_package_id: The originating package ID.
        mode: The trading mode.
        acceptance_id: V7 acceptance record ID (empty if not reached).
    """

    promoted: bool
    artifact_id: str
    gates_summary: dict[str, Any]
    next_steps: list[str]
    pre_acceptance: dict[str, Any] = field(default_factory=dict)
    post_acceptance: dict[str, Any] = field(default_factory=dict)
    handoff_package_id: str = ""
    mode: str = ""
    acceptance_id: str = ""


# ── Internal helpers ────────────────────────────────────────────────────────────


def _extract_context(package: dict) -> dict[str, Any]:
    """Extract gate context from the handoff package.

    Reads ``v7_gate_mapping`` statuses and sets context flags.
    """
    context: dict[str, Any] = {}
    gate_map = package.get("v7_gate_mapping", {})
    for gate_key, gate_entry in gate_map.items():
        if isinstance(gate_entry, dict) and gate_entry.get("status") == "PASS":
            context[gate_key] = True
    return context


def _result_to_dict(result: GateResult) -> dict[str, Any]:
    return {
        "gate_id": result.gate_id,
        "name": result.name,
        "status": result.status.value,
        "score": result.score,
        "threshold": result.threshold,
        "detail": result.detail,
    }


def _make_subset_summary(results: dict[str, GateResult]) -> dict[str, Any]:
    """Build a promotion summary for a subset of gates (pre or post)."""
    passed_gates: list[str] = []
    failed_gates: list[str] = []
    na_gates: list[str] = []
    scores: list[float] = []

    for gid, r in results.items():
        if r.status == GateStatus.PASS:
            passed_gates.append(gid)
            scores.append(r.score)
        elif r.status == GateStatus.FAIL:
            failed_gates.append(gid)
            scores.append(r.score)
        elif r.status == GateStatus.NOT_APPLICABLE:
            na_gates.append(gid)

    overall_score = sum(scores) / len(scores) if scores else 0.0
    passed = len(failed_gates) == 0

    recommendation = "PROMOTE" if passed else f"HOLD — gates failed: {', '.join(failed_gates)}"

    return {
        "passed": passed,
        "overall_score": round(overall_score, 4),
        "passed_gates": passed_gates,
        "failed_gates": failed_gates,
        "na_gates": na_gates,
        "recommendation": recommendation,
    }


def _run_gate_subset(
    package: dict,
    gate_ids: list[str],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a predefined set of gates and return results + summary.

    Args:
        package: The V7HandoffPackage dict.
        gate_ids: List of canonical gate IDs to evaluate.
        context: Optional gate context values merged with extracted context.

    Returns:
        A dict with ``gates`` (individual results) and ``summary``.
    """
    candidate = _extract_candidate_from_package(package)
    ctx = _extract_context(package)
    if context:
        ctx.update(context)

    results: dict[str, GateResult] = {}
    for gate_id in gate_ids:
        result = evaluate_gate(gate_id, candidate, ctx)
        results[gate_id] = result

    summary = _make_subset_summary(results)

    return {
        "gates": {gid: _result_to_dict(r) for gid, r in results.items()},
        "summary": summary,
    }


# ── V7PromotionEngine ───────────────────────────────────────────────────────────


class V7PromotionEngine:
    """Promotes AlphaForge handoff candidates through V7 promotion gates.

    The promotion pipeline performs schema validation, pre-acceptance gates,
    acceptance record creation, artifact registration, and post-acceptance gates.

    Usage::

        engine = V7PromotionEngine()
        result = engine.promote_from_alphaforge(handoff_package)
        if result.promoted:
            print(f"Promoted! Artifact ID: {result.artifact_id}")
        else:
            print(f"Next steps: {result.next_steps}")
    """

    def __init__(self) -> None:
        self._acceptor = HandoffAcceptor()

    # ── Primary API ──────────────────────────────────────────────────────────

    def promote_from_alphaforge(
        self,
        handoff_package: dict,
        context: dict[str, Any] | None = None,
    ) -> PromotionResult:
        """Run the full promotion pipeline on a handoff package.

        Pipeline steps:
          1. Schema validation — reject if structural errors.
          2. Pre-acceptance gates (G0-G4) — reject if any fail.
          3. Acceptance record — V7 formally accepts the candidate.
          4. Artifact registration — produce a V7 artifact ID.
          5. Post-acceptance gates (G5-G10) — evaluate remaining gates.
          6. Promotion result — final state with next steps.

        Args:
            handoff_package: A valid V7HandoffPackage dict.
            context: Optional gate evaluation context (e.g. ``expectancy_r``,
                     ``expected_r_net``, ``ece``). Merged with context
                     extracted from the package.

        Returns:
            A ``PromotionResult`` with promotion status, artifact ID, and
            comprehensive gate evaluation summaries.
        """
        pid = handoff_package.get("handoff_package_id", "")
        mode = handoff_package.get("mode", "")

        # ── Step 1: Schema validation ──
        schema_errors = self._acceptor.validate_contract(handoff_package)
        if schema_errors:
            return PromotionResult(
                promoted=False,
                artifact_id="",
                gates_summary={
                    "passed": False,
                    "overall_score": 0.0,
                    "passed_gates": [],
                    "failed_gates": [],
                    "na_gates": [],
                    "recommendation": f"REJECTED — schema errors: {', '.join(schema_errors)}",
                    "schema_errors": schema_errors,
                },
                next_steps=["Fix schema validation errors and resubmit"],
                handoff_package_id=pid,
                mode=mode,
            )

        # ── Step 2: Pre-acceptance gates (G0-G4) ──
        pre_result = self.run_pre_acceptance_gates(handoff_package, context=context)
        pre_summary = pre_result["summary"]
        pre_failed = pre_summary.get("failed_gates", [])

        if pre_failed:
            rejection_reason = (
                f"Pre-acceptance gates failed: {', '.join(pre_failed)}"
            )
            self._acceptor.reject_candidate(
                handoff_package, pre_result, rejection_reason
            )
            return PromotionResult(
                promoted=False,
                artifact_id="",
                gates_summary=pre_summary,
                next_steps=[
                    f"Address failed pre-acceptance gates: {', '.join(pre_failed)}"
                ],
                pre_acceptance=pre_result,
                handoff_package_id=pid,
                mode=mode,
            )

        # ── Step 3: Acceptance record ──
        accept_record = self._acceptor.accept_candidate(
            handoff_package, pre_result
        )
        acceptance_id = accept_record.acceptance_id

        # ── Step 4: Artifact registration ──
        artifact_id = self.register_artifact(handoff_package)

        # ── Step 5: Post-acceptance gates (G5-G10) ──
        post_result = self.run_post_acceptance_gates(handoff_package, context=context)
        post_summary = post_result["summary"]
        post_failed = post_summary.get("failed_gates", [])
        na_gates = post_summary.get("na_gates", [])

        # ── Step 6: Final promotion decision ──
        promoted = len(post_failed) == 0

        next_steps: list[str] = []
        if post_failed:
            next_steps.append(
                f"Address post-acceptance gates: {', '.join(post_failed)}"
            )
        if na_gates:
            next_steps.append(
                f"Infrastructure gates not yet applicable: {', '.join(na_gates)}"
            )
        if promoted:
            next_steps.append(
                "Promotion complete — candidate is eligible for pipeline advancement"
            )

        return PromotionResult(
            promoted=promoted,
            artifact_id=artifact_id,
            gates_summary=post_summary,
            next_steps=next_steps,
            pre_acceptance=pre_result,
            post_acceptance=post_result,
            handoff_package_id=pid,
            mode=mode,
            acceptance_id=acceptance_id,
        )

    def run_pre_acceptance_gates(
        self,
        package: dict,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run G0-G4 gates (pre-acceptance evaluation).

        Args:
            package: The V7HandoffPackage dict.
            context: Optional gate context values (e.g. ``expectancy_r``,
                     ``expected_r_net``). Merged with context extracted from
                     the package's gate mapping.

        Returns:
            Dict with ``gates`` map and ``summary``.
        """
        return _run_gate_subset(package, PRE_ACCEPTANCE_GATES, context=context)

    def run_post_acceptance_gates(
        self,
        package: dict,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run G5-G10 gates (post-acceptance evaluation).

        Args:
            package: The V7HandoffPackage dict.
            context: Optional gate context values (e.g. ``ece``). Merged with
                     context extracted from the package's gate mapping.

        Returns:
            Dict with ``gates`` map and ``summary``.
        """
        return _run_gate_subset(package, POST_ACCEPTANCE_GATES, context=context)

    def register_artifact(self, artifact: dict) -> str:
        """Register a promoted artifact and return its V7 artifact ID.

        In the current baseline, registration produces an identifier and
        records the artifact metadata. Full storage integration is deferred.

        Args:
            artifact: The artifact metadata dict (typically the handoff
                      package or a subset thereof).

        Returns:
            A unique V7 artifact ID string.
        """
        artifact_id = f"v7art-{uuid.uuid4().hex[:12]}"
        return artifact_id
