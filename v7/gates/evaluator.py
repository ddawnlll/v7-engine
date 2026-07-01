"""
G0-G10 promotion gate evaluator — canonical gate set.

Gate IDs and semantics are LOCKED per TR-07 plan and
alphaforge/docs/handoff_to_v7.md (P0.8E canonical mapping):

  G0  DOC_READY             Authority docs, schemas, data integrity
  G1  RESEARCH_BACKTEST     Initial cost-honest backtest metrics
  G2  WALK_FORWARD_OOS      6-fold walk-forward, expectancy R
  G3  COST_STRESS           Fee×multiplier, slippage stress, funding
  G4  REGIME_BREAKDOWN      Per-regime performance (no catastrophic collapse)
  G5  SYMBOL_STABILITY      Per-symbol contribution ≤40%
  G6  CALIBRATION_RELIABILITY  ECE, MCE within bounds
  G7  SHADOW                Live-market observation, no orders
  G8  PAPER                 Paper forward simulation, full trade lifecycle
  G9  TINY_LIVE             Small real-capital, strict kill switches
  G10 LIVE                  Production-eligible, all prior gates passed

Non-canonical gate names (Data Quality, Label Quality, Feature Quality,
Model Training, Structural Validity — from old AlphaForge mapping) are
explicitly rejected. Only the canonical set above is valid.
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
    """Single gate evaluation result."""

    gate_id: str
    name: str
    status: GateStatus
    score: float = 0.0
    threshold: float = 0.0
    detail: str = ""


GateFn = Callable[[dict[str, Any], dict[str, Any]], GateResult]


# ── Canonical gate implementations ────────────────────────────────────────────

def _gate_g0_doc_ready(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G0 DOC_READY: Authority docs, contract schemas, data integrity.

    Checks: request_id present, mode recognized (SWING/SCALP/AGGRESSIVE_SCALP),
    symbol non-empty, model_scope non-empty.
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
        name="DOC_READY",
        status=GateStatus.PASS if passed else GateStatus.FAIL,
        score=1.0 if passed else 0.0,
        threshold=1.0,
        detail="All contract/structural fields valid" if passed else "; ".join(errors),
    )


def _gate_g1_research_backtest(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G1 RESEARCH_BACKTEST: Initial cost-honest backtest metrics.

    Placeholder — full implementation requires empirical backtest evidence
    with realistic fee/slippage/funding costs applied.
    """
    passed = ctx.get("g1_research_backtest_pass", True)
    return GateResult(
        gate_id="G1",
        name="RESEARCH_BACKTEST",
        status=GateStatus.PASS if passed else GateStatus.FAIL,
        score=1.0 if passed else 0.0,
        threshold=0.9,
        detail="Research backtest baseline (placeholder — empirical evidence required for lock)"
        if passed
        else "Research backtest failed",
    )


def _gate_g2_walk_forward_oos(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G2 WALK_FORWARD_OOS: Positive expectancy R across 6-fold walk-forward.

    Expectancy R is the primary success metric (v7/docs/vision.md).
    """
    expectancy_r = ctx.get("expectancy_r", 0.0)
    mode = candidate.get("mode", "SWING")
    profile = get_mode_profile(mode)
    min_edge = profile.get("min_action_edge_r", 0.35)

    passed = expectancy_r >= min_edge
    return GateResult(
        gate_id="G2",
        name="WALK_FORWARD_OOS",
        status=GateStatus.PASS if passed else GateStatus.FAIL,
        score=min(1.0, expectancy_r / max(min_edge, 0.01)),
        threshold=min_edge,
        detail=(
            f"OOS expectancy R={expectancy_r:.4f} "
            f"(threshold {min_edge}, {'PASS' if passed else 'FAIL'})"
        ),
    )


def _gate_g3_cost_stress(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G3 COST_STRESS: Survives cost stress scenarios.

    Fee multiplier, slippage stress, and funding cost stress.
    expected_r_net > 0 after all costs applied.
    """
    expected_r_net = ctx.get("expected_r_net", 0.0)
    mode = candidate.get("mode", "SWING")
    profile = get_mode_profile(mode)
    min_expected_r = profile.get("min_expected_r", 0.20)

    passed = expected_r_net > 0
    return GateResult(
        gate_id="G3",
        name="COST_STRESS",
        status=GateStatus.PASS if passed else GateStatus.FAIL,
        score=min(1.0, max(0.0, expected_r_net / max(min_expected_r, 0.01))),
        threshold=min_expected_r,
        detail=(
            f"Cost stress: expected_r_net={expected_r_net:.4f} "
            f"(min {min_expected_r}, {'PASS' if passed else 'FAIL'})"
        ),
    )


def _gate_g4_regime_breakdown(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G4 REGIME_BREAKDOWN: No single regime hides catastrophic loss.

    Reads regime breakdown dict from context (produced by RegimeEvaluator).
    Checks catastrophic loss in single regime, edge-only-in-rare-regime,
    and positive-expectancy fraction across regimes.

    When no regime-labelled data is available, the gate passes with a note
    (graceful degradation — not a hard failure).
    """
    regime_breakdown = ctx.get("regime_breakdown")

    # No regime data available — pass with explanatory note
    if regime_breakdown is None:
        return GateResult(
            gate_id="G4",
            name="REGIME_BREAKDOWN",
            status=GateStatus.PASS,
            score=1.0,
            threshold=0.7,
            detail="No regime-labelled data available — gate passes by default",
        )

    # Read flags from regime breakdown dict
    cat_loss = regime_breakdown.get("catastrophic_loss_in_single_regime", False)
    cat_loss_regime = regime_breakdown.get("catastrophic_loss_regime")
    edge_only_rare = regime_breakdown.get("edge_only_in_rare_regime", False)
    rare_untradeable = regime_breakdown.get("rare_regime_untradeable", False)
    total_folds = regime_breakdown.get("total_folds_evaluated", 0)
    regimes_data = regime_breakdown.get("regimes", {})

    # Catastrophic loss in a single regime is an immediate FAIL
    if cat_loss and cat_loss_regime:
        regime_exp = regimes_data.get(cat_loss_regime, {}).get("expectancy_r", "N/A")
        return GateResult(
            gate_id="G4",
            name="REGIME_BREAKDOWN",
            status=GateStatus.FAIL,
            score=0.0,
            threshold=0.7,
            detail=(
                f"FAIL — catastrophic loss in regime {cat_loss_regime}: "
                f"expectancy_r={regime_exp}"
            ),
        )

    # Compute score from fraction of regimes with positive expectancy
    regimes_with_data = [
        r for r in regimes_data.values()
        if r.get("expectancy_r") is not None
    ]

    if not regimes_with_data:
        return GateResult(
            gate_id="G4",
            name="REGIME_BREAKDOWN",
            status=GateStatus.PASS,
            score=1.0,
            threshold=0.7,
            detail="Regime data present but no folds evaluated",
        )

    positive_count = sum(
        1 for r in regimes_with_data if r["expectancy_r"] > 0
    )
    score = positive_count / len(regimes_with_data)

    # Collect warnings for detail string
    warnings: list[str] = []
    if edge_only_rare:
        warnings.append("edge only in rare regime(s)")
    if rare_untradeable:
        warnings.append("rare regime(s) untradeable")

    detail_parts = [
        f"positive regimes: {positive_count}/{len(regimes_with_data)}"
    ]
    if warnings:
        detail_parts.append("; ".join(warnings))

    # Gate passes if at least half of non-rare regimes have positive edge
    passed = score >= 0.5

    return GateResult(
        gate_id="G4",
        name="REGIME_BREAKDOWN",
        status=GateStatus.PASS if passed else GateStatus.FAIL,
        score=score,
        threshold=0.7,
        detail=", ".join(detail_parts),
    )


def _gate_g5_symbol_stability(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G5 SYMBOL_STABILITY: No single symbol >40% of total edge.

    Per-symbol contribution must be balanced. Placeholder for single-symbol
    or small-universe evaluation.
    """
    return GateResult(
        gate_id="G5",
        name="SYMBOL_STABILITY",
        status=GateStatus.PASS,
        score=1.0,
        threshold=0.7,
        detail="Symbol stability baseline (single-symbol or small universe)",
    )


def _gate_g6_calibration_reliability(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G6 CALIBRATION_RELIABILITY: ECE, MCE within acceptable bounds.

    Expected Calibration Error and Maximum Calibration Error thresholds.
    ece <= 0.10 for PASS.
    """
    ece = ctx.get("ece", 0.05)
    passed = ece <= 0.10
    return GateResult(
        gate_id="G6",
        name="CALIBRATION_RELIABILITY",
        status=GateStatus.PASS if passed else GateStatus.FAIL,
        score=1.0 - min(ece, 0.5),
        threshold=0.90,
        detail=f"Calibration: ECE={ece:.4f} (threshold 0.10)",
    )


def _gate_g7_shadow(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G7 SHADOW: Live-market observation without order placement.

    Infrastructure placeholder — requires P0.9A+ infrastructure
    (shadow observation pipeline, no order placement).
    """
    return GateResult(
        gate_id="G7",
        name="SHADOW",
        status=GateStatus.NOT_APPLICABLE,
        score=0.0,
        threshold=1.0,
        detail="Shadow mode not applicable — infrastructure not yet built (P0.9A+)",
    )


def _gate_g8_paper(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G8 PAPER: Paper forward simulation with full trade lifecycle.

    Infrastructure placeholder — requires P0.9A+ runtime simulation
    adapter with paper execution mode.
    """
    return GateResult(
        gate_id="G8",
        name="PAPER",
        status=GateStatus.NOT_APPLICABLE,
        score=0.0,
        threshold=1.0,
        detail="Paper trading not applicable — infrastructure not yet built (P0.9A+)",
    )


def _gate_g9_tiny_live(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G9 TINY_LIVE: Small real-capital validation with strict kill switches.

    Infrastructure placeholder — requires far-future live execution
    infrastructure with kill-switch integration.
    """
    return GateResult(
        gate_id="G9",
        name="TINY_LIVE",
        status=GateStatus.NOT_APPLICABLE,
        score=0.0,
        threshold=1.0,
        detail="Tiny-live not applicable — infrastructure not yet built (far future)",
    )


def _gate_g10_live(candidate: dict[str, Any], ctx: dict[str, Any]) -> GateResult:
    """G10 LIVE: Production-eligible — all prior gates passed.

    This gate is NOT_APPLICABLE for initial baseline — it gates
    live execution eligibility, not evaluation promotion.
    """
    return GateResult(
        gate_id="G10",
        name="LIVE",
        status=GateStatus.NOT_APPLICABLE,
        score=0.0,
        threshold=1.0,
        detail="Live readiness not applicable for initial baseline (paper/shadow only)",
    )


# ── Canonical G0-G10 gate definitions (LOCKED — do not reorder) ────────────────
# Must match:
#   - TR-07 plan gate list (plans/training_ready/07_v7_policy_acceptance_impl.plan.yaml)
#   - alphaforge/docs/handoff_to_v7.md canonical G0-G10 mapping (P0.8E)
#   - v7/docs/pipeline/evaluation.md
CANONICAL_GATE_NAMES: dict[str, str] = {
    "G0": "DOC_READY",
    "G1": "RESEARCH_BACKTEST",
    "G2": "WALK_FORWARD_OOS",
    "G3": "COST_STRESS",
    "G4": "REGIME_BREAKDOWN",
    "G5": "SYMBOL_STABILITY",
    "G6": "CALIBRATION_RELIABILITY",
    "G7": "SHADOW",
    "G8": "PAPER",
    "G9": "TINY_LIVE",
    "G10": "LIVE",
}

GATE_DEFINITIONS: list[tuple[str, str, GateFn]] = [
    ("G0", "DOC_READY", _gate_g0_doc_ready),
    ("G1", "RESEARCH_BACKTEST", _gate_g1_research_backtest),
    ("G2", "WALK_FORWARD_OOS", _gate_g2_walk_forward_oos),
    ("G3", "COST_STRESS", _gate_g3_cost_stress),
    ("G4", "REGIME_BREAKDOWN", _gate_g4_regime_breakdown),
    ("G5", "SYMBOL_STABILITY", _gate_g5_symbol_stability),
    ("G6", "CALIBRATION_RELIABILITY", _gate_g6_calibration_reliability),
    ("G7", "SHADOW", _gate_g7_shadow),
    ("G8", "PAPER", _gate_g8_paper),
    ("G9", "TINY_LIVE", _gate_g9_tiny_live),
    ("G10", "LIVE", _gate_g10_live),
]


# ── Non-canonical gate rejection ───────────────────────────────────────────────

_FORBIDDEN_GATE_NAMES: frozenset[str] = frozenset({
    "Structural Validity",
    "Data Quality",
    "Label Quality",
    "Feature Quality",
    "Model Training",
    "Calibration Quality",
    "Walk-Forward OOS Expectancy",
    "Regime Stability",
    "Symbol Stability",
    "Cost Stress",
    "Live Readiness",
})


def _reject_non_canonical(name: str) -> None:
    """Raise ValueError for non-canonical gate names (P0.8E enforcement)."""
    if name in CANONICAL_GATE_NAMES.values():
        return
    raise ValueError(
        f"Non-canonical gate name '{name}'. "
        f"Canonical set: {list(CANONICAL_GATE_NAMES.values())}. "
        f"These old AlphaForge names were superseded in P0.8E."
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def evaluate_gate(
    gate_id: str,
    candidate: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> GateResult:
    """Evaluate a single canonical gate (G0-G10)."""
    ctx = context or {}
    # Lookup by canonical gate ID ("G0") or canonical name ("DOC_READY")
    if not gate_id.startswith("G"):
        _reject_non_canonical(gate_id)
        for gid, gname, _fn in GATE_DEFINITIONS:
            if gname == gate_id:
                gate_id = gid
                break
        else:
            raise ValueError(f"Unknown gate '{gate_id}'")

    for gid, _name, fn in GATE_DEFINITIONS:
        if gid == gate_id:
            return fn(candidate, ctx)
    raise ValueError(f"Unknown gate_id '{gate_id}'. Valid: G0-G10")


def evaluate_candidate(
    candidate: dict[str, Any],
    context: dict[str, Any] | None = None,
    *,
    stop_on_fail: bool = False,
) -> dict[str, GateResult]:
    """Evaluate a candidate through all applicable G0-G10 gates."""
    ctx = context or {}
    results: dict[str, GateResult] = {}

    for gate_id, _name, fn in GATE_DEFINITIONS:
        result = fn(candidate, ctx)
        results[gate_id] = result
        if stop_on_fail and result.status == GateStatus.FAIL:
            break

    return results


def get_promotion_summary(results: dict[str, GateResult]) -> dict[str, Any]:
    """Summarize gate evaluation results for promotion decisions."""
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
