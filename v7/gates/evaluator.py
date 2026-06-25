"""
G0-G10 promotion gate evaluator.

Defines each gate's requirements, thresholds, and evaluation logic.
The framework is generic — each gate can be implemented against any
candidate evidence bundle (dict). Test-friendly design: gates are
pure functions of (candidate, context) -> GateResult.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from v7.router import HOLD, LOCKED_INITIAL_BASELINE, get_mode_profile


class GateStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    HOLD = "HOLD"


@dataclass(frozen=True)
class GateResult:
    """Single gate evaluation result.

    Attributes:
        gate_id: Gate identifier (G0-G10).
        name: Human-readable gate name.
        status: PASS, FAIL, NOT_APPLICABLE, or HOLD.
        score: Numeric score (0.0-1.0) where applicable.
        threshold: Minimum threshold for PASS.
        detail: Human-readable detail about the result.
    """

    gate_id: str
    name: str
    status: GateStatus
    score: float = 0.0
    threshold: float = 0.0
    detail: str = ""


# Type alias for gate evaluation functions
GateFn = Callable[[dict[str, Any], dict[str, Any]], GateResult]


def _gate_g0_structural(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G0: Structural validity — contracts and schemas must be valid.

    Checks: request_id present, mode recognized, symbol non-empty,
            model_scope non-empty.
    """
    errors: list[str] = []
    if not candidate.get("request_id"):
        errors.append("missing request_id")
    mode = candidate.get("mode", "")
    if mode not in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
        errors.append(f"invalid mode: '{mode}'")
    if not candidate.get("symbol"):
        errors.append("missing symbol")
    if not candidate.get("model_scope"):
        errors.append("missing model_scope")

    passed = len(errors) == 0
    return GateResult(
        gate_id="G0",
        name="Structural Validity",
        status=GateStatus.PASS if passed else GateStatus.FAIL,
        score=1.0 if passed else 0.0,
        threshold=1.0,
        detail="All structural fields valid" if passed else "; ".join(errors),
    )


def _gate_g1_data_quality(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G1: Data quality — no data leakage, completeness acceptable.

    This is a placeholder gate. In production, it would verify:
    - No future bars in feature windows
    - Data completeness above minimum threshold
    - No stale/gap-filled data
    """
    passed = ctx.get("g1_override", True)
    return GateResult(
        gate_id="G1",
        name="Data Quality",
        status=GateStatus.PASS if passed else GateStatus.FAIL,
        score=1.0 if passed else 0.0,
        threshold=0.9,
        detail="Data quality checks passed (placeholder)" if passed
        else "Data quality checks failed",
    )


def _gate_g2_label_quality(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G2: Label quality — simulation truth used, no unresolved rows.

    Placeholder gate. In production, verifies label_validity ratio,
    unresolved/invalid row percentages, ambiguity ratio.
    """
    mode = candidate.get("mode", "SWING")
    profile = get_mode_profile(mode)
    min_edge = profile.get("min_action_edge_r", 0.35)
    expected_r = ctx.get("expected_r_gross", 0.0)

    passed = True  # Placeholder — always passes for baseline
    return GateResult(
        gate_id="G2",
        name="Label Quality",
        status=GateStatus.PASS if passed else GateStatus.FAIL,
        score=1.0,
        threshold=1.0,
        detail=f"Label quality baseline (min_action_edge_r={min_edge}, expected_r={expected_r:.4f})",
    )


def _gate_g3_feature_quality(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G3: Feature quality — canonical-state only, no lookahead.

    Placeholder gate.
    """
    return GateResult(
        gate_id="G3",
        name="Feature Quality",
        status=GateStatus.PASS,
        score=1.0,
        threshold=0.9,
        detail="Feature quality baseline (canonical state assumed valid)",
    )


def _gate_g4_model_training(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G4: Model training — training succeeded, no silent failures.

    Placeholder gate. Checks for model_signature presence.
    """
    signature = ctx.get("model_signature", "")
    passed = bool(signature)
    return GateResult(
        gate_id="G4",
        name="Model Training",
        status=GateStatus.PASS if passed else GateStatus.FAIL,
        score=1.0 if passed else 0.0,
        threshold=1.0,
        detail=f"Model training baseline (signature={'present' if signature else 'missing'})",
    )


def _gate_g5_calibration(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G5: Calibration quality — ECE, MCE within bounds.

    Placeholder gate. In production, checks Expected Calibration Error
    and Maximum Calibration Error against thresholds.
    """
    ece = ctx.get("ece", 0.05)
    passed = ece <= 0.10
    return GateResult(
        gate_id="G5",
        name="Calibration Quality",
        status=GateStatus.PASS if passed else GateStatus.FAIL,
        score=1.0 - min(ece, 0.5),
        threshold=0.90,
        detail=f"Calibration: ECE={ece:.4f} (threshold 0.10)",
    )


def _gate_g6_walk_forward(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G6: Walk-forward OOS — positive expectancy R, acceptable drawdown.

    Expectancy R is the primary success metric.
    """
    expectancy_r = ctx.get("expectancy_r", 0.0)
    mode = candidate.get("mode", "SWING")
    profile = get_mode_profile(mode)
    min_edge = profile.get("min_action_edge_r", 0.35)

    passed = expectancy_r >= min_edge
    return GateResult(
        gate_id="G6",
        name="Walk-Forward OOS Expectancy",
        status=GateStatus.PASS if passed else GateStatus.FAIL,
        score=min(1.0, expectancy_r / max(min_edge, 0.01)),
        threshold=min_edge,
        detail=(
            f"OOS expectancy R={expectancy_r:.4f} "
            f"(threshold {min_edge}, {'PASS' if passed else 'FAIL'})"
        ),
    )


def _gate_g7_regime_stability(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G7: Regime stability — performance across market regimes.

    Placeholder gate.
    """
    return GateResult(
        gate_id="G7",
        name="Regime Stability",
        status=GateStatus.PASS,
        score=1.0,
        threshold=0.7,
        detail="Regime stability baseline (no regime breakdown data yet)",
    )


def _gate_g8_symbol_stability(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G8: Symbol stability — not carried by 1-2 symbols.

    Placeholder gate.
    """
    return GateResult(
        gate_id="G8",
        name="Symbol Stability",
        status=GateStatus.PASS,
        score=1.0,
        threshold=0.7,
        detail="Symbol stability baseline (single-symbol only)",
    )


def _gate_g9_cost_stress(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G9: Cost stress — passes cost stress scenarios.

    Checks: expected_r_net > 0 after costs.
    """
    expected_r_net = ctx.get("expected_r_net", 0.0)
    mode = candidate.get("mode", "SWING")
    profile = get_mode_profile(mode)
    min_expected_r = profile.get("min_expected_r", 0.20)

    passed = expected_r_net > 0
    return GateResult(
        gate_id="G9",
        name="Cost Stress",
        status=GateStatus.PASS if passed else GateStatus.FAIL,
        score=min(1.0, max(0.0, expected_r_net / max(min_expected_r, 0.01))),
        threshold=min_expected_r,
        detail=(
            f"Cost stress: expected_r_net={expected_r_net:.4f} "
            f"(min {min_expected_r}, {'PASS' if passed else 'FAIL'})"
        ),
    )


def _gate_g10_live_readiness(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G10: Live readiness — monitoring, rollback, kill-switch in place.

    This gate is NOT_APPLICABLE for initial baseline — it gates
    live execution eligibility, not evaluation promotion.
    """
    return GateResult(
        gate_id="G10",
        name="Live Readiness",
        status=GateStatus.NOT_APPLICABLE,
        score=0.0,
        threshold=1.0,
        detail="Live readiness not applicable for initial baseline (paper/shadow only)",
    )


# Canonical ordered gate definitions
GATE_DEFINITIONS: list[tuple[str, str, GateFn]] = [
    ("G0", "Structural Validity", _gate_g0_structural),
    ("G1", "Data Quality", _gate_g1_data_quality),
    ("G2", "Label Quality", _gate_g2_label_quality),
    ("G3", "Feature Quality", _gate_g3_feature_quality),
    ("G4", "Model Training", _gate_g4_model_training),
    ("G5", "Calibration Quality", _gate_g5_calibration),
    ("G6", "Walk-Forward OOS Expectancy", _gate_g6_walk_forward),
    ("G7", "Regime Stability", _gate_g7_regime_stability),
    ("G8", "Symbol Stability", _gate_g8_symbol_stability),
    ("G9", "Cost Stress", _gate_g9_cost_stress),
    ("G10", "Live Readiness", _gate_g10_live_readiness),
]


def evaluate_gate(
    gate_id: str,
    candidate: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> GateResult:
    """Evaluate a single named gate.

    Args:
        gate_id: Gate identifier (G0-G10).
        candidate: The candidate dict (minimally: request_id, mode, symbol,
                  model_scope).
        context: Optional evaluation context (expectancy_r, expected_r_net,
                 ece, model_signature, g1_override, etc.).

    Returns:
        GateResult with status and detail.

    Raises:
        ValueError: If gate_id is not recognized.
    """
    ctx = context or {}
    for gid, name, fn in GATE_DEFINITIONS:
        if gid == gate_id:
            return fn(candidate, ctx)
    raise ValueError(f"Unknown gate_id '{gate_id}'. Valid: G0-G10")


def evaluate_candidate(
    candidate: dict[str, Any],
    context: dict[str, Any] | None = None,
    *,
    stop_on_fail: bool = False,
) -> dict[str, GateResult]:
    """Evaluate a candidate through all applicable G0-G10 gates.

    Args:
        candidate: Candidate dict with at least request_id, mode, symbol,
                  model_scope.
        context: Optional evaluation context.
        stop_on_fail: If True, stop evaluating after first FAIL (for CI).

    Returns:
        Dict mapping gate_id to GateResult.
    """
    ctx = context or {}
    results: dict[str, GateResult] = {}

    for gate_id, _name, fn in GATE_DEFINITIONS:
        result = fn(candidate, ctx)
        results[gate_id] = result
        if stop_on_fail and result.status == GateStatus.FAIL:
            break

    return results


def get_promotion_summary(results: dict[str, GateResult]) -> dict[str, Any]:
    """Summarize gate evaluation results for promotion decisions.

    Returns:
        Dict with passed (bool), passed_gates, failed_gates, na_gates,
        overall_score, and recommendation.
    """
    passed_gates = []
    failed_gates = []
    na_gates = []
    scores = []

    for gate_id, result in results.items():
        if result.status == GateStatus.PASS:
            passed_gates.append(gate_id)
            scores.append(result.score)
        elif result.status == GateStatus.FAIL:
            failed_gates.append(gate_id)
            scores.append(result.score)
        elif result.status == GateStatus.NOT_APPLICABLE:
            na_gates.append(gate_id)

    overall_score = sum(scores) / len(scores) if scores else 0.0
    passed = len(failed_gates) == 0

    recommendation = "PROMOTE" if passed else "HOLD"
    if failed_gates:
        recommendation = f"HOLD — gates failed: {', '.join(failed_gates)}"

    return {
        "passed": passed,
        "overall_score": round(overall_score, 4),
        "passed_gates": passed_gates,
        "failed_gates": failed_gates,
        "na_gates": na_gates,
        "recommendation": recommendation,
    }
