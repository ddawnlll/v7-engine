"""
AlphaForge V7 Policy Bridge — translates calibrated alpha evidence
into V7-compatible AnalysisResult decisions.

Applies mode-specific policy thresholds:
- Min alpha_R (long/short)
- Min confidence
- Required expected-R above threshold
- Regime-aware constraints
- No-trade gating
"""

from __future__ import annotations

from typing import Any

from alphaforge.errors import AlphaForgeError


# Mode-specific policy thresholds (from ai_summary section 15)
MODE_POLICY: dict[str, dict[str, float]] = {
    "SWING": {
        "min_long_alpha_R": 0.20,
        "min_short_alpha_R": 0.20,
        "min_confidence": 0.58,
        "require_expected_R_above": 0.35,
    },
    "SCALP": {
        "min_long_alpha_R": 0.10,
        "min_short_alpha_R": 0.10,
        "min_confidence": 0.60,
        "require_expected_R_above": 0.15,
    },
    "AGGRESSIVE_SCALP": {
        "min_long_alpha_R": 0.06,
        "min_short_alpha_R": 0.06,
        "min_confidence": 0.65,
        "require_expected_R_above": 0.08,
        "extra_cost_filter_required": 1.0,
    },
}

# Regime constraint levels
REGIME_CONSTRAINTS: dict[str, dict[str, str]] = {
    "TREND_UP": {"SHORT": "SOFT_BLOCK"},
    "TREND_DOWN": {"LONG": "SOFT_BLOCK"},
    "RANGE": {},
    "TRANSITION": {"LONG": "ADVISORY", "SHORT": "ADVISORY"},
}

# Allowed actions
ACTIONS = ("LONG_NOW", "SHORT_NOW", "NO_TRADE")
DIRECTIONS = {"LONG_NOW": "LONG", "SHORT_NOW": "SHORT", "NO_TRADE": "NONE"}


def evaluate_policy(
    alpha_output: dict[str, Any],
    mode: str = "SWING",
    regime: str | None = None,
    **overrides,
) -> dict[str, Any]:
    """Apply policy thresholds to alpha output and produce a decision.

    Args:
        alpha_output: Dict from calibration.engine.predict_calibrated.
        mode: Trading mode for threshold selection.
        regime: Optional regime label for regime-aware constraints.
        **overrides: Override any policy threshold.

    Returns:
        AnalysisResult-compatible decision dict.
    """
    thresholds = dict(MODE_POLICY.get(mode, MODE_POLICY["SWING"]))
    thresholds.update({k: v for k, v in overrides.items() if k in thresholds})

    cal = alpha_output.get("calibrated_probabilities", {})
    expected_r = alpha_output.get("expected_r", {})
    alpha = alpha_output.get("alpha_scores", {})
    confidence = float(alpha_output.get("confidence", 0.0))

    p_long = float(cal.get("long", 0.0))
    p_short = float(cal.get("short", 0.0))
    p_no_trade = float(cal.get("no_trade", 0.0))
    exp_r_long = float(expected_r.get("long", 0.0))
    exp_r_short = float(expected_r.get("short", 0.0))
    long_alpha = float(alpha.get("long_alpha_R", 0.0))
    short_alpha = float(alpha.get("short_alpha_R", 0.0))

    # Track which gates were passed/failed
    gate_results: dict[str, bool] = {}

    # Gate 1: Confidence check
    gate_results["confidence_gate"] = confidence >= float(thresholds["min_confidence"])

    # Gate 2: Long alpha check
    gate_results["long_alpha_gate"] = long_alpha >= float(thresholds["min_long_alpha_R"])

    # Gate 3: Short alpha check
    gate_results["short_alpha_gate"] = short_alpha >= float(thresholds["min_short_alpha_R"])

    # Gate 4: Expected-R check for long
    gate_results["long_expected_r_gate"] = exp_r_long >= float(thresholds["require_expected_R_above"])

    # Gate 5: Expected-R check for short
    gate_results["short_expected_r_gate"] = exp_r_short >= float(thresholds["require_expected_R_above"])

    # Regime constraints
    regime_block_long = False
    regime_block_short = False
    regime_reasons: list[str] = []
    if regime and regime in REGIME_CONSTRAINTS:
        constraints = REGIME_CONSTRAINTS[regime]
        if "LONG" in constraints:
            regime_block_long = constraints["LONG"] in ("SOFT_BLOCK", "HARD_BLOCK")
            regime_reasons.append(f"regime_{regime}_blocks_LONG")
        if "SHORT" in constraints:
            regime_block_short = constraints["SHORT"] in ("SOFT_BLOCK", "HARD_BLOCK")
            regime_reasons.append(f"regime_{regime}_blocks_SHORT")
    gate_results["regime_long_gate"] = not regime_block_long
    gate_results["regime_short_gate"] = not regime_block_short

    # Determine action
    confidence_pass = gate_results["confidence_gate"]
    long_pass = gate_results["long_alpha_gate"] and gate_results["long_expected_r_gate"] and not regime_block_long
    short_pass = gate_results["short_alpha_gate"] and gate_results["short_expected_r_gate"] and not regime_block_short

    if not confidence_pass:
        recommended_action = "NO_TRADE"
        decision_reason = "confidence_below_threshold"
    elif long_pass and short_pass:
        # Both pass — pick the one with higher alpha
        if long_alpha >= short_alpha:
            recommended_action = "LONG_NOW"
            decision_reason = "alpha_long_wins"
        else:
            recommended_action = "SHORT_NOW"
            decision_reason = "alpha_short_wins"
    elif long_pass:
        recommended_action = "LONG_NOW"
        decision_reason = "long_alpha_passes"
    elif short_pass:
        recommended_action = "SHORT_NOW"
        decision_reason = "short_alpha_passes"
    else:
        recommended_action = "NO_TRADE"
        decision_reason = "no_alpha_passes_gates"

    # Build result
    return {
        "recommended_action": recommended_action,
        "direction": DIRECTIONS.get(recommended_action, "NONE"),
        "is_actionable": recommended_action != "NO_TRADE",
        "confidence": round(confidence, 4),
        "confidence_kind": alpha_output.get("confidence_kind", "raw"),
        "decision_reason": decision_reason,
        "scores": {
            "p_long": round(p_long, 4),
            "p_short": round(p_short, 4),
            "p_no_trade": round(p_no_trade, 4),
            "expected_r_long": round(exp_r_long, 4),
            "expected_r_short": round(exp_r_short, 4),
            "long_alpha_R": round(long_alpha, 4),
            "short_alpha_R": round(short_alpha, 4),
        },
        "policy": {
            "thresholds": {k: round(float(v), 4) if isinstance(v, float) else v for k, v in thresholds.items()},
            "gates": gate_results,
            "regime_constraints": regime_reasons,
            "mode": mode,
            "regime": regime,
        },
    }
