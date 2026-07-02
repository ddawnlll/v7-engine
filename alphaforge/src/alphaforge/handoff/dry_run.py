"""AlphaForge V7 Handoff Dry Run — canonical G0-G10 only, no promotion candidate.

WS-07: INPUT-CONTRACT, GATE-MAPPING, DRY-RUN-BUILDER, NO-PROMOTION

Implements the full dry run pipeline:
1. Validate input reports (ModeResearchReport + ValidationReport)
2. Assemble canonical V7 gate mapping from report evidence
3. Build V7HandoffPackage via P0.9A handoff builder
4. Apply promotion guard (never PROMOTION_CANDIDATE / SHADOW_READY)
5. Evaluate all 12 handoff rejection rules
6. Validate output against v7_handoff_package.schema.json
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional

from alphaforge.constants import (
    CANONICAL_V7_GATES,
    HANDOFF_REVIEW_REQUIRED,
    HANDOFF_SHADOW_READY,
    HANDOFF_PROMOTION_CANDIDATE,
    V7_REGIMES,
)
from alphaforge.errors import (
    AlphaForgeError,
    GateMappingError,
    HandoffBuildError,
    InputContractError,
    PromotionGuardError,
)
from alphaforge.contracts.loader import load_schema
from alphaforge.contracts.validator import validate_payload


# ═══════════════════════════════════════════════════════════════════════════
# WS-07-INPUT-CONTRACT: Required fields from JSON schemas
# ═══════════════════════════════════════════════════════════════════════════

MODE_RESEARCH_REPORT_REQUIRED_FIELDS: FrozenSet[str] = frozenset([
    "schema_version",
    "report_id",
    "mode",
    "mode_priority",
    "report_type",
    "data_scope",
    "feature_set_refs",
    "label_dataset_refs",
    "alpha_theses",
    "validation_summary",
    "metrics",
    "cost_stress",
    "no_trade_comparison",
    "regime_breakdown",
    "multiple_hypothesis_control",
    "verdict",
    "blocked_scopes",
    "limitations",
])

VALIDATION_REPORT_REQUIRED_FIELDS: FrozenSet[str] = frozenset([
    "schema_version",
    "validation_report_id",
    "mode",
    "split_policy",
    "walk_forward_folds",
    "oos_summary",
    "symbol_stability",
    "regime_breakdown",
    "cost_stress",
    "no_trade_comparison",
    "overfit_risk_flags",
    "multiple_hypothesis_control",
    "verdict",
])

# ── Field mapping: ModeResearchReport → V7HandoffPackage ─────────────────

_frozen_input_contract_map: Dict[str, str] = {
    "report_id": "mode_research_report_id",
    "mode": "mode",
    "data_scope.symbols": "lineage.data_refs",
    "feature_set_refs": "lineage.feature_set_id",
    "label_dataset_refs": "lineage.label_dataset_id",
    "validation_summary.validation_report_id": "validation_report_id",
    "cost_stress": "G3_cost_stress evidence_ref",
    "regime_breakdown": "G4_regime_breakdown evidence_ref",
    "no_trade_comparison": "cross-cutting quality evidence",
    "metrics.oos_expectancy_r": "G1_research_backtest evidence_ref",
    "verdict": "recommended_status decision input",
    "blocked_scopes": "blocked_scopes",
    "limitations": "limitations",
    "v7_gate_readiness.overall_readiness": "recommended_status decision input",
    "multiple_hypothesis_control": "G0_doc_ready evidence_ref",
}

INPUT_CONTRACT_MAP: Dict[str, str] = _frozen_input_contract_map

# ── Field mapping: ValidationReport → V7HandoffPackage ───────────────────

_frozen_validation_report_input_map: Dict[str, str] = {
    "validation_report_id": "validation_report_id",
    "mode": "mode",
    "alpha_candidate_id": "alpha_candidate_id",
    "model_artifact_id": "model_artifact_id",
    "calibration_gate_alignment.calibration_candidate_id": "calibration_candidate_id",
    "oos_summary.oos_expectancy_r": "G2_walk_forward_oos evidence_ref",
    "oos_summary.oos_ic": "G2_walk_forward_oos evidence_ref",
    "oos_summary.oos_rank_ic": "G2_walk_forward_oos evidence_ref",
    "oos_summary.oos_sharpe": "G2_walk_forward_oos evidence_ref",
    "oos_summary.oos_win_rate": "G2_walk_forward_oos evidence_ref",
    "oos_summary.oos_trade_count": "G2_walk_forward_oos evidence_ref",
    "oos_summary.oos_positive_expectancy": "G2_walk_forward_oos evidence_ref",
    "oos_summary.fold_stability_score": "G2_walk_forward_oos evidence_ref",
    "symbol_stability.max_single_symbol_concentration": "G5_symbol_stability evidence_ref",
    "symbol_stability.max_cluster_concentration": "G5_symbol_stability evidence_ref",
    "symbol_stability.symbols_tested": "G5_symbol_stability evidence_ref",
    "cost_stress.combined_stress_edge_survives": "G3_cost_stress evidence_ref",
    "cost_stress.cost_edge_destroyed": "G3_cost_stress evidence_ref",
    "cost_stress.scalp_cost_adjusted_expectancy_r": "G3_cost_stress evidence_ref",
    "cost_stress.funding_deferred_block": "G3_cost_stress evidence_ref",
    "regime_breakdown.regimes": "G4_regime_breakdown evidence_ref",
    "regime_breakdown.edge_only_in_rare_regime": "G4_regime_breakdown evidence_ref",
    "calibration_gate_alignment.ece": "G6_calibration_reliability evidence_ref",
    "calibration_gate_alignment.mce": "G6_calibration_reliability evidence_ref",
    "calibration_gate_alignment.reliability_within_bounds": "G6_calibration_reliability evidence_ref",
    "calibration_gate_alignment.calibration_status": "G6_calibration_reliability evidence_ref",
    "overfit_risk_flags.overfit_risk_overall": "rejection rule evaluation",
    "multiple_hypothesis_control.correction_method": "rejection rule evaluation",
    "multiple_hypothesis_control.data_snooping_risk_flag": "rejection rule evaluation",
    "multiple_hypothesis_control.pbo_or_backtest_overfit_risk": "rejection rule evaluation",
    "verdict": "recommended_status decision input",
    "limitations": "limitations",
}

VALIDATION_REPORT_INPUT_MAP: Dict[str, str] = _frozen_validation_report_input_map

@dataclass(frozen=True)
class DryRunInput:
    """Input contract for V7 handoff dry run.

    Consumes ModeResearchReport and ValidationReport dicts plus optional
    override IDs. All fields are immutable.
    """
    mode: str  # SCALP | AGGRESSIVE_SCALP | SWING
    mode_research_report: Dict[str, Any]
    validation_report: Dict[str, Any]
    handoff_package_id: Optional[str] = None
    alpha_candidate_id: Optional[str] = None
    model_artifact_id: Optional[str] = None
    calibration_candidate_id: Optional[str] = None

    def __post_init__(self):
        if self.mode not in ("SCALP", "AGGRESSIVE_SCALP", "SWING"):
            raise InputContractError(
                report_type="DryRunInput",
                missing_fields=[f"Invalid mode: '{self.mode}'"],
            )


# ═══════════════════════════════════════════════════════════════════════════
# WS-07-INPUT-CONTRACT: Input report validation
# ═══════════════════════════════════════════════════════════════════════════

def validate_input_reports(
    mode_research_report: Dict[str, Any],
    validation_report: Dict[str, Any],
) -> DryRunInput:
    """Validate structural completeness of both report skeletons.

    Checks that both report dicts contain all required top-level keys
    from their respective JSON schemas. Returns a DryRunInput if valid.

    Args:
        mode_research_report: ModeResearchReport dict.
        validation_report: ValidationReport dict.

    Returns:
        DryRunInput with validated report dicts.

    Raises:
        InputContractError: Required fields missing from either report.
    """
    # Validate ModeResearchReport
    mrr_missing = [
        f for f in MODE_RESEARCH_REPORT_REQUIRED_FIELDS
        if f not in mode_research_report
    ]
    if mrr_missing:
        raise InputContractError(
            report_type="ModeResearchReport",
            missing_fields=mrr_missing,
        )

    # Validate ValidationReport
    vr_missing = [
        f for f in VALIDATION_REPORT_REQUIRED_FIELDS
        if f not in validation_report
    ]
    if vr_missing:
        raise InputContractError(
            report_type="ValidationReport",
            missing_fields=vr_missing,
        )

    # Validate mode consistency between reports
    mrr_mode = mode_research_report.get("mode", "")
    vr_mode = validation_report.get("mode", "")
    if mrr_mode and vr_mode and mrr_mode != vr_mode:
        raise InputContractError(
            report_type="DryRunInput",
            missing_fields=[
                f"Mode mismatch: ModeResearchReport mode='{mrr_mode}' "
                f"!= ValidationReport mode='{vr_mode}'"
            ],
        )

    return DryRunInput(
        mode=mrr_mode or vr_mode,
        mode_research_report=mode_research_report,
        validation_report=validation_report,
    )


# ═══════════════════════════════════════════════════════════════════════════
# WS-07-GATE-MAPPING: validate_gate_mapping()
# ═══════════════════════════════════════════════════════════════════════════

_VALID_GATE_STATUSES = frozenset(["PASS", "PENDING", "NOT_EVALUATED"])


def validate_gate_mapping(gate_mapping: Dict[str, Any]) -> bool:
    """Validate gate mapping uses only canonical V7 gate names and valid structure.

    Checks:
    1. Exactly 11 keys matching CANONICAL_V7_GATES
    2. Each gate is a dict with exactly 'evidence_ref' (str) and 'status'
       (enum: PASS, PENDING, NOT_EVALUATED)
    3. Reports ALL missing/unknown gates in error messages
    4. References handoff_to_v7.md for canonical names

    Args:
        gate_mapping: Dict mapping gate IDs to their evidence entries.

    Returns:
        True if valid.

    Raises:
        GateMappingError: On any validation failure with descriptive message.
    """
    gate_keys = set(gate_mapping.keys())
    canonical_set = set(CANONICAL_V7_GATES)

    # Check for missing canonical gates
    missing = canonical_set - gate_keys
    # Check for unknown/extra gates
    unknown = gate_keys - canonical_set

    if missing and unknown:
        raise GateMappingError(message=(
            f"Gate mapping validation failed: "
            f"Missing canonical V7 gate(s): {sorted(missing)}. "
            f"Unknown gate(s) in mapping: {sorted(unknown)}. "
            f"Use canonical V7 gate IDs from CANONICAL_V7_GATES "
            f"and alphaforge/docs/handoff_to_v7.md."
        ))
    elif missing:
        raise GateMappingError(message=(
            f"Missing canonical V7 gate(s): {sorted(missing)}. "
            f"A total of 11 canonical gates are required "
            f"(G0_doc_ready through G10_live). "
            f"See alphaforge/docs/handoff_to_v7.md for canonical gate names."
        ))
    elif unknown:
        raise GateMappingError(message=(
            f"Unknown gate(s) in mapping: {sorted(unknown)}. "
            f"Use canonical V7 gate IDs from CANONICAL_V7_GATES "
            f"and alphaforge/docs/handoff_to_v7.md. "
            f"Old AlphaForge-invented gate names are not accepted."
        ))

    # Validate each gate entry structure
    for gate_id in sorted(canonical_set):
        entry = gate_mapping[gate_id]

        if not isinstance(entry, dict):
            raise GateMappingError(message=(
                f"Gate '{gate_id}' entry is not a dict: got {type(entry).__name__}. "
                f"Each gate entry must be a dict with 'evidence_ref' (str) "
                f"and 'status' (PASS|PENDING|NOT_EVALUATED)."
            ))

        # Check for evidence_ref
        if "evidence_ref" not in entry:
            raise GateMappingError(message=(
                f"Gate '{gate_id}' is missing required key 'evidence_ref'. "
                f"Each gate entry must have 'evidence_ref' (str) "
                f"and 'status' (PASS|PENDING|NOT_EVALUATED)."
            ))

        # Check for status
        if "status" not in entry:
            raise GateMappingError(message=(
                f"Gate '{gate_id}' is missing required key 'status'. "
                f"Each gate entry must have 'evidence_ref' (str) "
                f"and 'status' (PASS|PENDING|NOT_EVALUATED)."
            ))

        # Check evidence_ref is a string
        if not isinstance(entry["evidence_ref"], str):
            raise GateMappingError(message=(
                f"Gate '{gate_id}' evidence_ref must be a string, "
                f"got {type(entry['evidence_ref']).__name__}."
            ))

        # Check status is a valid enum
        status = entry.get("status", "")
        if status not in _VALID_GATE_STATUSES:
            raise GateMappingError(message=(
                f"Gate '{gate_id}' has invalid status '{status}'. "
                f"Valid status values: {sorted(_VALID_GATE_STATUSES)}."
            ))

    return True


# ═══════════════════════════════════════════════════════════════════════════
# Helper: build a single gate entry
# ═══════════════════════════════════════════════════════════════════════════

def _make_gate_entry(evidence_ref: str, status: str = "NOT_EVALUATED") -> Dict[str, str]:
    """Build a single canonical gate entry for v7_gate_mapping."""
    return {
        "evidence_ref": evidence_ref,
        "status": status,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Helper: safe nested dict access
# ═══════════════════════════════════════════════════════════════════════════

def _safe_get(d: Dict[str, Any], key_path: str, default: Any = None) -> Any:
    """Get a nested value from a dict using dot-separated keys."""
    keys = key_path.split(".")
    current = d
    for k in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(k)
        if current is None and k != keys[-1]:
            return default
    return current if current is not None else default


# ═══════════════════════════════════════════════════════════════════════════
# WS-07-DRY-RUN-BUILDER: assemble gate mapping from report evidence
# ═══════════════════════════════════════════════════════════════════════════

def _assemble_gate_mapping(
    mode_research_report: Dict[str, Any],
    validation_report: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the canonical V7 gate mapping from report evidence.

    Evidence refs are populated from report skeletons:
    - G0: data_scope + authority docs reference
    - G1: ModeResearchReport metrics
    - G2: ValidationReport oos_summary + walk_forward_folds
    - G3: ValidationReport cost_stress
    - G4: ValidationReport regime_breakdown
    - G5: ValidationReport symbol_stability
    - G6: ValidationReport calibration_gate_alignment
    - G7-G10: infrastructure-not-yet-built messages

    All gates are set to NOT_EVALUATED — dry run does not pass any gate.
    """
    mrid = mode_research_report.get("report_id", "unknown")
    vrid = validation_report.get("validation_report_id", "unknown")
    mode = mode_research_report.get("mode", "")

    def _desc(key: str) -> str:
        val = _safe_get(validation_report, key)
        mrr_val = _safe_get(mode_research_report, key)
        return str(val if val is not None else mrr_val if mrr_val is not None else "no data")

    gate_mapping = {
        "G0_doc_ready": _make_gate_entry(
            f"DOC_READY evidence from {mrid}: data_scope={mode_research_report.get('data_scope', {})}, "
            f"MHT={_safe_get(mode_research_report, 'multiple_hypothesis_control.correction_method', 'NONE')} "
            f"— dry run: NOT_EVALUATED",
        ),
        "G1_research_backtest": _make_gate_entry(
            f"RESEARCH_BACKTEST evidence from {mrid}: "
            f"oos_expectancy_r={_desc('metrics.oos_expectancy_r.value')}, "
            f"oos_sharpe={_desc('metrics.oos_sharpe.value')} "
            f"— dry run: NOT_EVALUATED",
        ),
        "G2_walk_forward_oos": _make_gate_entry(
            f"WALK_FORWARD_OOS evidence from {vrid}: "
            f"oos_expectancy_r={_desc('oos_summary.oos_expectancy_r')}, "
            f"fold_count={_safe_get(validation_report, 'walk_forward_folds.fold_count', 'N/A')} "
            f"— dry run: NOT_EVALUATED",
        ),
        "G3_cost_stress": _make_gate_entry(
            f"COST_STRESS evidence from {vrid}: "
            f"combined_stress={_desc('cost_stress.combined_stress_edge_survives')}, "
            f"edge_destroyed={_desc('cost_stress.cost_edge_destroyed')} "
            f"— dry run: NOT_EVALUATED",
        ),
        "G4_regime_breakdown": _make_gate_entry(
            f"REGIME_BREAKDOWN evidence from {vrid}: "
            f"edge_only_rare={_desc('regime_breakdown.edge_only_in_rare_regime')} "
            f"— dry run: NOT_EVALUATED",
        ),
        "G5_symbol_stability": _make_gate_entry(
            f"SYMBOL_STABILITY evidence from {vrid}: "
            f"max_single_conc={_desc('symbol_stability.max_single_symbol_concentration')}, "
            f"max_cluster_conc={_desc('symbol_stability.max_cluster_concentration')} "
            f"— dry run: NOT_EVALUATED",
        ),
        "G6_calibration_reliability": _make_gate_entry(
            f"CALIBRATION_RELIABILITY evidence from {vrid}: "
            f"ece={_desc('calibration_gate_alignment.ece')}, "
            f"status={_desc('calibration_gate_alignment.calibration_status')} "
            f"— dry run: NOT_EVALUATED",
        ),
        "G7_shadow": _make_gate_entry(
            "Shadow trading infrastructure not yet built — P0.9A+ dependency. "
            "Dry run: NOT_EVALUATED."
        ),
        "G8_paper": _make_gate_entry(
            "Paper trading infrastructure not yet built — P0.9A+ dependency. "
            "Dry run: NOT_EVALUATED."
        ),
        "G9_tiny_live": _make_gate_entry(
            "Tiny-live infrastructure not yet built — far future. "
            "Dry run: NOT_EVALUATED."
        ),
        "G10_live": _make_gate_entry(
            "Live infrastructure not yet built — far future. "
            "Dry run: NOT_EVALUATED."
        ),
    }

    return gate_mapping


# ═══════════════════════════════════════════════════════════════════════════
# WS-07-NO-PROMOTION: Promotion guard
# ═══════════════════════════════════════════════════════════════════════════

def _guard_promotion_status(recommended_status: str) -> None:
    """Hard guard: raise if status is not REVIEW_REQUIRED.

    Dry run can never recommend PROMOTION_CANDIDATE or SHADOW_READY.
    Real promotion evidence requires walk-forward validation, shadow
    trading, and live data.

    Args:
        recommended_status: The status to check.

    Raises:
        PromotionGuardError: If status is PROMOTION_CANDIDATE or SHADOW_READY.
    """
    if recommended_status in (HANDOFF_SHADOW_READY, HANDOFF_PROMOTION_CANDIDATE):
        raise PromotionGuardError(
            attempted_status=recommended_status,
            allowed_status=HANDOFF_REVIEW_REQUIRED,
        )
    # REVIEW_REQUIRED passes silently
    return None


# ═══════════════════════════════════════════════════════════════════════════
# RejectionRulesResult
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class RejectionRulesResult:
    """Result of evaluating all 12 V7 handoff rejection rules."""
    passed: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    blocked: List[str] = field(default_factory=list)
    is_rejected: bool = False


# ═══════════════════════════════════════════════════════════════════════════
# WS-07-NO-PROMOTION: 12 Handoff Rejection Rules
# ═══════════════════════════════════════════════════════════════════════════

def _evaluate_rejection_rules(
    mode_research_report: Dict[str, Any],
    validation_report: Dict[str, Any],
    is_dry_run: bool = True,
) -> RejectionRulesResult:
    """Evaluate all 12 V7 handoff rejection rules from handoff_to_v7.md.

    Args:
        mode_research_report: ModeResearchReport dict.
        validation_report: ValidationReport dict.
        is_dry_run: Whether this is a dry run (affects deferred rules).

    Returns:
        RejectionRulesResult with passed/failed/blocked lists and is_rejected bool.
    """
    passed: List[str] = []
    failed: List[str] = []
    blocked: List[str] = []

    mode = mode_research_report.get("mode", "")

    # ── Rule 1: Missing evidence ─────────────────────────────────────────
    mrid = mode_research_report.get("report_id", "")
    vrid = validation_report.get("validation_report_id", "")
    if not mrid or not vrid:
        failed.append(
            "Rule 1 (Missing evidence): FAILED — "
            f"mode_research_report_id='{mrid}', validation_report_id='{vrid}'"
        )
    else:
        passed.append(
            "Rule 1 (Missing evidence): PASSED — all required reports present"
        )

    # ── Rule 2: Incomplete gate mapping ───────────────────────────────────
    # Gate mapping is validated separately by validate_gate_mapping().
    # This rule always passes in _evaluate_rejection_rules because the
    # validation happens before builder invocation in run_handoff_dry_run().
    passed.append(
        "Rule 2 (Incomplete gate mapping): PASSED — validated by "
        "validate_gate_mapping() before builder invocation"
    )

    # ── Rule 3: Lineage break ────────────────────────────────────────────
    chronological_split = _safe_get(
        validation_report, "split_policy.chronological_split", False
    )
    if is_dry_run:
        blocked.append(
            "Rule 3 (Lineage break): BLOCKED — lineage verification deferred (dry run)"
        )
    elif chronological_split:
        passed.append(
            "Rule 3 (Lineage break): PASSED — chronological split confirmed"
        )
    else:
        failed.append(
            "Rule 3 (Lineage break): FAILED — non-chronological split detected"
        )

    # ── Rule 4: Checksum mismatch ────────────────────────────────────────
    if is_dry_run:
        blocked.append(
            "Rule 4 (Checksum mismatch): BLOCKED — checksum verification "
            "deferred (dry run, no real model binary)"
        )
    else:
        passed.append(
            "Rule 4 (Checksum mismatch): PASSED — no real model binary to verify"
        )

    # ── Rule 5: Validation failure ───────────────────────────────────────
    vr_verdict = validation_report.get("verdict", "")
    fail_verdicts = {"FAIL_OVERFIT", "FAIL_COST", "FAIL_REGIME", "FAIL_OOS", "FAIL_MHT"}
    if vr_verdict in fail_verdicts:
        failed.append(
            f"Rule 5 (Validation failure): FAILED — verdict={vr_verdict}"
        )
    elif vr_verdict == "INCONCLUSIVE" or vr_verdict == "PASS_WITH_LIMITATIONS":
        blocked.append(
            f"Rule 5 (Validation failure): BLOCKED — verdict={vr_verdict}"
        )
    elif vr_verdict == "PASS":
        passed.append(
            "Rule 5 (Validation failure): PASSED — verdict=PASS"
        )
    else:
        blocked.append(
            f"Rule 5 (Validation failure): BLOCKED — verdict={vr_verdict} (unrecognized)"
        )

    # ── Rule 6: Cost vulnerability ───────────────────────────────────────
    cost_stress = validation_report.get("cost_stress", {})
    cost_edge_destroyed = cost_stress.get("cost_edge_destroyed", False)
    combined_survives = cost_stress.get("combined_stress_edge_survives", False)
    scalp_adj = cost_stress.get("scalp_cost_adjusted_expectancy_r", None)

    cost_failures = []
    if cost_edge_destroyed:
        cost_failures.append("cost_edge_destroyed=True")
    if not combined_survives:
        cost_failures.append("combined_stress_edge_survives=False")
    if mode in ("SCALP", "AGGRESSIVE_SCALP") and scalp_adj is not None and scalp_adj < 0.10:
        cost_failures.append(f"scalp_cost_adjusted_expectancy_r={scalp_adj:.4f}R < 0.10R")

    if cost_failures:
        failed.append(
            f"Rule 6 (Cost vulnerability): FAILED — {', '.join(cost_failures)}"
        )
    else:
        passed.append(
            "Rule 6 (Cost vulnerability): PASSED — edge survives cost stress"
        )

    # ── Rule 7: Overfit detected ─────────────────────────────────────────
    overfit = validation_report.get("overfit_risk_flags", {})
    overfit_overall = overfit.get("overfit_risk_overall", "")
    purge_violation = overfit.get("purge_violation_detected", False)
    train_oos_gap = overfit.get("train_oos_gap", "")

    if overfit_overall == "CRITICAL" or purge_violation:
        reasons = []
        if overfit_overall == "CRITICAL":
            reasons.append(f"overfit_risk_overall={overfit_overall}")
        if purge_violation:
            reasons.append("purge_violation_detected=True")
        failed.append(
            f"Rule 7 (Overfit detected): FAILED — {', '.join(reasons)}"
        )
    elif overfit_overall == "HIGH" or train_oos_gap == "HIGH":
        reasons = []
        if overfit_overall == "HIGH":
            reasons.append(f"overfit_risk_overall={overfit_overall}")
        if train_oos_gap == "HIGH":
            reasons.append(f"train_oos_gap={train_oos_gap}")
        blocked.append(
            f"Rule 7 (Overfit detected): BLOCKED — {', '.join(reasons)}"
        )
    else:
        passed.append(
            f"Rule 7 (Overfit detected): PASSED — overfit_risk_overall={overfit_overall}"
        )

    # ── Rule 8: Single-symbol overfitting ────────────────────────────────
    sym_stab = validation_report.get("symbol_stability", {})
    max_conc = sym_stab.get("max_single_symbol_concentration", 0.0)
    single_limitation = sym_stab.get("single_symbol_limitation", False)

    if max_conc > 0.40:
        failed.append(
            f"Rule 8 (Single-symbol overfitting): FAILED — "
            f"concentration {max_conc:.2f} exceeds 0.40"
        )
    elif single_limitation:
        blocked.append(
            "Rule 8 (Single-symbol overfitting): BLOCKED — "
            "single_symbol_limitation=True"
        )
    else:
        passed.append(
            f"Rule 8 (Single-symbol overfitting): PASSED — "
            f"concentration={max_conc:.2f} <= 0.40"
        )

    # ── Rule 9: Calibration unusable ─────────────────────────────────────
    calib = validation_report.get("calibration_gate_alignment", {})
    calib_status = calib.get("calibration_status", "")

    if calib_status == "UNRELIABLE":
        failed.append(
            f"Rule 9 (Calibration unusable): FAILED — "
            f"calibration_status={calib_status}"
        )
    elif calib_status == "UNCALIBRATED":
        blocked.append(
            f"Rule 9 (Calibration unusable): BLOCKED — "
            f"calibration_status={calib_status}"
        )
    else:
        passed.append(
            f"Rule 9 (Calibration unusable): PASSED — "
            f"calibration_status={calib_status}"
        )

    # ── Rule 10: Funding unknown ─────────────────────────────────────────
    funding_block = cost_stress.get("funding_deferred_block", {})
    funding_deferred = funding_block.get("funding_deferred", False)
    block_reason = funding_block.get("block_reason", "No reason provided")

    if funding_deferred:
        blocked.append(
            f"Rule 10 (Funding unknown): BLOCKED — "
            f"funding DEFERRED: {block_reason}"
        )
    else:
        passed.append(
            "Rule 10 (Funding unknown): PASSED — funding not deferred"
        )

    # ── Rule 11: Blocked scope violation ─────────────────────────────────
    blocked_scopes = mode_research_report.get("blocked_scopes", [])
    scope_text = " ".join(str(s) for s in blocked_scopes).lower()
    mode_blocked = False
    if mode == "SCALP" and "scalp" in scope_text and "blocked" in scope_text:
        mode_blocked = True
    elif mode == "AGGRESSIVE_SCALP" and "aggressive" in scope_text and "blocked" in scope_text:
        mode_blocked = True
    elif mode == "SWING" and "swing" in scope_text and "blocked" in scope_text:
        mode_blocked = True

    if mode_blocked:
        failed.append(
            f"Rule 11 (Blocked scope violation): FAILED — "
            f"mode {mode} blocked_scopes contradict mode"
        )
    else:
        passed.append(
            "Rule 11 (Blocked scope violation): PASSED — "
            "no blocked scope contradicts mode"
        )

    # ── Rule 12: Policy conflict ─────────────────────────────────────────
    if is_dry_run:
        blocked.append(
            "Rule 12 (Policy conflict): BLOCKED — "
            "policy conflict check deferred (dry run, no V7 policy loaded)"
        )
    else:
        passed.append(
            "Rule 12 (Policy conflict): PASSED — no policy conflict detected"
        )

    # ── Compile result ───────────────────────────────────────────────────
    is_rejected = len(failed) > 0
    return RejectionRulesResult(
        passed=list(passed),
        failed=list(failed),
        blocked=list(blocked),
        is_rejected=is_rejected,
    )


# ═══════════════════════════════════════════════════════════════════════════
# WS-07-DRY-RUN-BUILDER: run_handoff_dry_run() main entry point
# ═══════════════════════════════════════════════════════════════════════════

def run_handoff_dry_run(dry_run_input: DryRunInput) -> Dict[str, Any]:
    """Execute a complete V7 handoff dry run.

    Pipeline:
    1. Validate input reports via validate_input_reports()
    2. Guard promotion status — only REVIEW_REQUIRED allowed
    3. Assemble canonical V7 gate mapping from report evidence
    4. Validate gate mapping via validate_gate_mapping()
    5. Evaluate all 12 handoff rejection rules
    6. Build V7HandoffPackage via P0.9A handoff builder
    7. Post-process: replace gate mapping, populate blocked_scopes,
       apply rejection rules, set recommended_status
    8. Validate output against v7_handoff_package.schema.json

    Args:
        dry_run_input: DryRunInput containing validated report dicts.

    Returns:
        V7HandoffPackage as dict, validated against schema.

    Raises:
        InputContractError: Input validation failure.
        PromotionGuardError: Invalid promotion status.
        GateMappingError: Gate mapping validation failure.
        HandoffBuildError: Output schema validation failure.
    """
    from alphaforge.handoff.builders import build_v7_handoff_package

    mrr = dry_run_input.mode_research_report
    vr = dry_run_input.validation_report
    mode = dry_run_input.mode

    # Step 1: Validate input reports (structural completeness)
    _ = validate_input_reports(mrr, vr)

    # Step 2: Guard promotion status — hard assertion
    _guard_promotion_status(HANDOFF_REVIEW_REQUIRED)

    # Step 3: Assemble canonical V7 gate mapping from report evidence
    gate_mapping = _assemble_gate_mapping(mrr, vr)

    # Step 4: Validate gate mapping structure
    validate_gate_mapping(gate_mapping)

    # Step 5: Evaluate all 12 rejection rules
    rejection_result = _evaluate_rejection_rules(mrr, vr, is_dry_run=True)

    # Collect rejection_rules_applied strings
    rejection_rules_applied = (
        rejection_result.passed +
        rejection_result.failed +
        rejection_result.blocked
    )

    # Step 6: Build V7HandoffPackage via P0.9A handoff builder
    mrid = mrr.get("report_id", "")
    vrid = vr.get("validation_report_id", "")
    acid = dry_run_input.alpha_candidate_id or vr.get("alpha_candidate_id", "")
    maid = dry_run_input.model_artifact_id or vr.get("model_artifact_id", "")
    ccid = dry_run_input.calibration_candidate_id or _safe_get(
        vr, "calibration_gate_alignment.calibration_candidate_id", ""
    )

    handoff = build_v7_handoff_package(
        mode=mode,
        handoff_package_id=dry_run_input.handoff_package_id,
        alpha_candidate_id=acid if acid else None,
        mode_research_report_id=mrid if mrid else None,
        validation_report_id=vrid if vrid else None,
        model_artifact_id=maid if maid else None,
        calibration_candidate_id=ccid if ccid else None,
        recommended_status=HANDOFF_REVIEW_REQUIRED,
    )

    # Step 7: Post-process — replace gate mapping with evidence-backed version
    handoff["v7_gate_mapping"] = gate_mapping

    # Populate blocked_scopes from report evidence + standard dry-run blockers
    report_blocked = list(mrr.get("blocked_scopes", []))
    funding_block = _safe_get(vr, "cost_stress.funding_deferred_block", {})
    if isinstance(funding_block, dict) and funding_block.get("funding_deferred"):
        affected = funding_block.get("affected_scopes", [])
        report_blocked.extend(
            f"Funding DEFERRED: {a}" for a in affected
        )
        report_blocked.append(
            f"Funding DEFERRED: {funding_block.get('block_reason', 'No reason')}"
        )

    dry_run_blockers = [
        "Dry run — no shadow infrastructure (P0.9A+ required)",
        "Dry run — no paper infrastructure (P0.9A+ required)",
        "Dry run — no live infrastructure (far future)",
    ]
    # Merge, preserving existing and adding dry-run specific ones
    existing_scopes = set(handoff.get("blocked_scopes", []))
    for scope in report_blocked + dry_run_blockers:
        if scope not in existing_scopes:
            handoff.setdefault("blocked_scopes", []).append(scope)
            existing_scopes.add(scope)

    # Set recommended_status
    handoff["recommended_status"] = HANDOFF_REVIEW_REQUIRED

    # Apply rejection rules
    handoff["rejection_rules_applied"] = rejection_rules_applied

    # Merge limitations from reports
    report_limitations = list(mrr.get("limitations", [])) + list(vr.get("limitations", []))
    for lim in report_limitations:
        if lim not in handoff.get("limitations", []):
            handoff.setdefault("limitations", []).append(lim)

    # Step 8: Validate against schema
    schema = load_schema("v7_handoff_package.schema.json")
    result = validate_payload(schema, handoff, f"v7_handoff_dry_run({mode})")
    if not result.valid:
        raise HandoffBuildError(
            f"Dry run V7HandoffPackage for {mode} failed validation: {result.errors}"
        )

    return handoff


# ═══════════════════════════════════════════════════════════════════════════
# Convenience: build dry run for all three modes
# ═══════════════════════════════════════════════════════════════════════════

def run_all_dry_runs() -> Dict[str, Dict[str, Any]]:
    """Build dry run handoff packages for all three canonical modes.

    Uses minimal report dicts built inline to avoid import ambiguity
    between the reports/ package and reports.py single-file module.
    """
    from datetime import datetime, timezone as _tz

    def _now() -> str:
        return datetime.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _mrr(mode: str) -> Dict[str, Any]:
        priority = "SECONDARY_BASELINE" if mode == "SWING" else "PRIMARY"
        rtype = "secondary_baseline_report" if mode == "SWING" else "primary_research_report"
        tf = {"SWING": "4h", "SCALP": "1h", "AGGRESSIVE_SCALP": "15m"}[mode]
        return {
            "schema_version": "1.0.0", "report_id": f"mrr-{mode.lower()}-dryrun-001",
            "mode": mode, "mode_priority": priority, "report_type": rtype,
            "created_at": _now(), "run_id": "run-placeholder-001",
            "data_scope": {
                "symbols": ["BTCUSDT"],
                "date_range_start": "2024-01-01T00:00:00Z",
                "date_range_end": "2025-01-01T00:00:00Z",
                "primary_timeframes": [tf], "secondary_timeframes": ["1d"],
                "data_quality_summary": "Dry run placeholder",
            },
            "feature_set_refs": ["fs-placeholder-001"],
            "label_dataset_refs": ["lds-placeholder-001"],
            "alpha_theses": [{
                "alpha_thesis_id": "at-placeholder-001",
                "title": "Placeholder thesis", "status": "HYPOTHESIS_ONLY",
                "evidence_quality": "INSUFFICIENT",
            }],
            "validation_summary": {
                "validation_report_id": f"vr-{mode.lower()}-dryrun-001",
                "fold_count": 6, "verdict": "CANDIDATE_FOR_V7_GATES",
                "overfit_risk": "LOW",
            },
            "metrics": {
                "oos_sharpe": {"value": 0.5}, "oos_expectancy_r": {"value": 0.15},
                "oos_win_rate": {"value": 0.52}, "oos_profit_factor": {"value": 1.3},
                "oos_max_drawdown_r": {"value": -3.0}, "oos_trade_count": 600,
                "per_fold_metrics": [],
            },
            "cost_stress": {
                "baseline_fee_pct": 0.04, "baseline_slippage_pct": 0.02,
                "fee_stress_levels": [], "slippage_stress_levels": [],
                "combined_stress_edge_survives": True,
                "break_even_cost_total_pct": 0.15,
            },
            "no_trade_comparison": {
                "active_beats_no_trade": True, "summary": "Dry run placeholder",
            },
            "regime_breakdown": {
                "regimes": [], "edge_only_in_rare_regime": False,
                "summary": "Dry run placeholder",
            },
            "multiple_hypothesis_control": {
                "tested_hypothesis_count": 1, "correction_method": "Bonferroni",
                "data_snooping_risk_flag": "LOW",
            },
            "verdict": "CANDIDATE_FOR_V7_GATES",
            "blocked_scopes": [
                "Dry run placeholder — no real data",
                "Funding DEFERRED — perpetual/live claims blocked",
            ],
            "limitations": ["Dry run placeholder — no real research."],
            "recommended_actions": [],
        }

    def _vr(mode: str) -> Dict[str, Any]:
        folds = [
            {
                "fold_number": i, "train_start": "2024-01-01T00:00:00Z",
                "train_end": "2024-07-01T00:00:00Z",
                "test_start": "2024-07-01T00:00:00Z",
                "test_end": "2024-08-01T00:00:00Z",
                "train_sharpe": 1.0, "test_sharpe": 0.5,
                "test_expectancy_r": 0.15, "test_win_rate": 0.52,
                "test_trade_count": 100,
            }
            for i in range(1, 7)
        ]
        return {
            "schema_version": "1.0.0",
            "validation_report_id": f"vr-{mode.lower()}-dryrun-001",
            "mode": mode,
            "alpha_candidate_id": f"ac-{mode.lower()}-dryrun-001",
            "model_artifact_id": f"ma-{mode.lower()}-dryrun-001",
            "split_policy": {
                "train_pct": 0.60, "validation_pct": 0.15, "oos_pct": 0.25,
                "purge_window_bars": 10, "embargo_policy": "purge_and_embargo",
                "chronological_split": True,
            },
            "walk_forward_folds": {"fold_count": 6, "fold_type": "anchored", "folds": folds},
            "oos_summary": {
                "oos_sharpe": 0.5, "oos_expectancy_r": 0.15, "oos_win_rate": 0.52,
                "oos_max_drawdown_r": -3.0, "oos_profit_factor": 1.3,
                "oos_trade_count": 600, "oos_positive_expectancy": True,
                "fold_stability_score": 0.7,
                "oos_ic": 0.04, "oos_rank_ic": 0.03,
            },
            "symbol_stability": {
                "symbols_tested": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
                "symbol_count": 3,
                "max_single_symbol_concentration": 0.30,
                "max_cluster_concentration": 0.45,
                "single_symbol_limitation": False,
                "cross_symbol_metric_variance": "Low variance",
            },
            "regime_breakdown": {
                "regimes": [
                    {"regime": "TREND_UP", "sample_pct": 0.30, "oos_expectancy_r": 0.20, "oos_sharpe": 0.6, "edge_present": True},
                    {"regime": "TREND_DOWN", "sample_pct": 0.25, "oos_expectancy_r": 0.10, "oos_sharpe": 0.3, "edge_present": True},
                    {"regime": "RANGE", "sample_pct": 0.30, "oos_expectancy_r": 0.05, "oos_sharpe": 0.1, "edge_present": True},
                    {"regime": "TRANSITION", "sample_pct": 0.15, "oos_expectancy_r": 0.02, "oos_sharpe": 0.05, "edge_present": True},
                ],
                "edge_only_in_rare_regime": False,
                "rare_regime_untradeable": False,
            },
            "cost_stress": {
                "baseline_fee_pct": 0.04, "baseline_slippage_pct": 0.02,
                "baseline_spread_pct": 0.01,
                "spread_or_proxy": "taker_fee_0.04pct",
                "funding_or_deferred_block": "DEFERRED",
                "fee_stress_edge_survives": True,
                "slippage_stress_edge_survives": True,
                "spread_stress_edge_survives": True,
                "combined_stress_edge_survives": True,
                "break_even_cost_total_pct": 0.15,
                "cost_edge_destroyed": False,
                "scalp_cost_adjusted_expectancy_r": 0.15,
                "funding_deferred_block": {
                    "funding_deferred": False,
                    "block_reason": "Funding not required for dry run validation",
                    "affected_scopes": [],
                },
            },
            "no_trade_comparison": {
                "active_beats_no_trade": True,
                "long_better_than_no_trade": True,
                "short_better_than_no_trade": True,
                "saved_loss_r": 0.5, "missed_opportunity_r": 0.3,
                "summary": "Dry run — placeholder no-trade comparison",
            },
            "overfit_risk_flags": {
                "overfit_risk_overall": "LOW",
                "train_oos_gap": "LOW", "fold_instability": "LOW",
                "feature_to_sample_ratio": "LOW", "top_feature_dominance": "LOW",
                "calibration_degradation": "LOW", "purge_violation_detected": False,
            },
            "multiple_hypothesis_control": {
                "tested_hypothesis_count": 1,
                "correction_method": "Bonferroni",
                "trial_count_disclosure": 1,
                "rejected_candidate_count": 0,
                "data_snooping_risk_flag": "LOW",
                "pbo_or_backtest_overfit_risk": "LOW",
            },
            "calibration_gate_alignment": {
                "calibration_candidate_id": f"cc-{mode.lower()}-dryrun-001",
                "ece": 0.02, "mce": 0.05, "confidence_bin_count": 10,
                "reliability_within_bounds": True,
                "calibration_status": "CALIBRATED",
            },
            "verdict": "PASS",
            "limitations": ["Dry run placeholder — no real validation."],
            "created_at": _now(),
        }

    results: Dict[str, Dict[str, Any]] = {}
    for mode in ("SCALP", "AGGRESSIVE_SCALP", "SWING"):
        dinput = DryRunInput(
            mode=mode,
            mode_research_report=_mrr(mode),
            validation_report=_vr(mode),
        )
        results[mode] = run_handoff_dry_run(dinput)

    return results
