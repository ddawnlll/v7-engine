"""Constants for AlphaForge domain."""

# Canonical mode identifiers — do not add or remove without authority lock
CANONICAL_MODES = frozenset(["SCALP", "AGGRESSIVE_SCALP", "SWING"])

# Mode priority values
MODE_PRIORITY_PRIMARY = "PRIMARY"
MODE_PRIORITY_SECONDARY_BASELINE = "SECONDARY_BASELINE"

# Report types
REPORT_TYPE_PRIMARY = "primary_research_report"
REPORT_TYPE_SECONDARY_BASELINE = "secondary_baseline_report"

# Promotion status
PROMOTION_HOLD = "HOLD_UNTIL_EMPIRICAL_EVIDENCE"
PROMOTION_LOCKED_BASELINE = "LOCKED_INITIAL_BASELINE_WITH_RECALIBRATION"

# Funding status
FUNDING_DEFERRED = "DEFERRED"
FUNDING_NOT_REQUIRED = "NOT_REQUIRED"
FUNDING_SUPPORTED = "SUPPORTED"

# V7 handoff recommended status
HANDOFF_REVIEW_REQUIRED = "REVIEW_REQUIRED"
HANDOFF_SHADOW_READY = "SHADOW_READY"
HANDOFF_PROMOTION_CANDIDATE = "PROMOTION_CANDIDATE"

# V7 canonical gate IDs (source of truth: v7/docs/pipeline/evaluation.md)
# P0.8E: corrected from legacy AlphaForge-invented gate names
CANONICAL_V7_GATES = [
    "G0_doc_ready",
    "G1_research_backtest",
    "G2_walk_forward_oos",
    "G3_cost_stress",
    "G4_regime_breakdown",
    "G5_symbol_stability",
    "G6_calibration_reliability",
    "G7_shadow",
    "G8_paper",
    "G9_tiny_live",
    "G10_live",
]

# V7 canonical gate names (friendly labels)
CANONICAL_V7_GATE_NAMES = {
    "G0_doc_ready": "DOC_READY",
    "G1_research_backtest": "RESEARCH_BACKTEST",
    "G2_walk_forward_oos": "WALK_FORWARD_OOS",
    "G3_cost_stress": "COST_STRESS",
    "G4_regime_breakdown": "REGIME_BREAKDOWN",
    "G5_symbol_stability": "SYMBOL_STABILITY",
    "G6_calibration_reliability": "CALIBRATION_RELIABILITY",
    "G7_shadow": "SHADOW",
    "G8_paper": "PAPER",
    "G9_tiny_live": "TINY_LIVE",
    "G10_live": "LIVE",
}

# Allowed verdicts for ModeResearchReport
MODE_REPORT_VERDICTS = [
    "REJECT",
    "CONTINUE_RESEARCH",
    "CANDIDATE_FOR_V7_GATES",
    "BASELINE_VALID",
    "BASELINE_WEAK",
]

# Verdicts allowed for PRIMARY modes
PRIMARY_MODE_VERDICTS = [
    "REJECT",
    "CONTINUE_RESEARCH",
    "CANDIDATE_FOR_V7_GATES",
]

# Verdicts allowed for SECONDARY_BASELINE modes
BASELINE_MODE_VERDICTS = [
    "REJECT",
    "CONTINUE_RESEARCH",
    "BASELINE_VALID",
    "BASELINE_WEAK",
]

# Regime taxonomy aligned to V7 evaluation.md (P0.8E)
V7_REGIMES = ["TREND_UP", "TREND_DOWN", "RANGE", "TRANSITION"]

# Validation verdicts
VALIDATION_VERDICTS = [
    "PASS",
    "PASS_WITH_LIMITATIONS",
    "FAIL_OVERFIT",
    "FAIL_COST",
    "FAIL_REGIME",
    "FAIL_OOS",
    "INCONCLUSIVE",
]
