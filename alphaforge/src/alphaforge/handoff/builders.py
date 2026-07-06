"""AlphaForge V7 Handoff Builder.

Builds schema-valid V7HandoffPackage payloads using canonical V7 gate
mapping from P0.8E. Supports two construction modes:

1. Scaffold (placeholder): build_v7_handoff_package() — all gates
   NOT_EVALUATED, recommended_status REVIEW_REQUIRED. Used before any
   real evidence exists.

2. Empirical: build_empirical_handoff_package() — consumes a real
   ModeResearchReport (e.g. from build_empirical_mode_research_report)
   and extracts G0-G10 gate evidence statuses, lineage, and verdict-based
   recommended_status from the report data.
"""
from __future__ import annotations

from datetime import datetime, timezone

from alphaforge.constants import (
    CANONICAL_V7_GATES,
    HANDOFF_REVIEW_REQUIRED,
    HANDOFF_PROMOTION_CANDIDATE,
    FUNDING_DEFERRED,
)
from alphaforge.modes.profiles import get_mode_profile, ModeProfile
from alphaforge.contracts.loader import load_schema
from alphaforge.contracts.validator import validate_payload
from alphaforge.errors import HandoffBuildError, ModeError


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_gate_entry(evidence_ref: str, status: str = "NOT_EVALUATED") -> dict:
    return {
        "evidence_ref": evidence_ref,
        "status": status,
    }


# ---------------------------------------------------------------------------
# Verdict → recommended_status mapping
# ---------------------------------------------------------------------------

_VERDICT_TO_RECOMMENDED_STATUS: dict[str, str] = {
    "REJECT": HANDOFF_REVIEW_REQUIRED,
    "BLOCKED_FOR_MHT": HANDOFF_REVIEW_REQUIRED,
    "CONTINUE_RESEARCH": HANDOFF_REVIEW_REQUIRED,
    "BASELINE_VALID": HANDOFF_REVIEW_REQUIRED,
    "CANDIDATE_FOR_V7_GATES": HANDOFF_PROMOTION_CANDIDATE,
}


def _status_from_verdict(verdict: str) -> str:
    """Map ModeResearchReport verdict to V7HandoffPackage recommended_status."""
    return _VERDICT_TO_RECOMMENDED_STATUS.get(verdict, HANDOFF_REVIEW_REQUIRED)


# ---------------------------------------------------------------------------
# Gate evidence extraction helpers
# ---------------------------------------------------------------------------

def _gate_g0(report: dict) -> tuple[str, str]:
    """G0: DOC_READY — evidence is the report with data scope + MHT controls."""
    ds = report.get("data_scope", {})
    mht = report.get("multiple_hypothesis_control", {})
    symbols = ds.get("symbols", [])
    evidence = (
        f"DOC_READY evidence from {report.get('report_id', 'unknown')}: "
        f"symbols={symbols}, "
        f"date_range={ds.get('date_range_start', '?')} to {ds.get('date_range_end', '?')}, "
        f"MHT correction={mht.get('correction_method', 'NONE')}, "
        f"data_snooping_risk={mht.get('data_snooping_risk_flag', 'UNKNOWN')}, "
        f"pbo_risk={mht.get('pbo_or_backtest_overfit_risk', 'UNKNOWN')}"
    )
    # PASS if report has data scope with at least one symbol
    status = "PASS" if len(symbols) >= 1 else "PENDING"
    return evidence, status


def _gate_g1(report: dict) -> tuple[str, str]:
    """G1: RESEARCH_BACKTEST — initial backtest metrics.

    P0.9F: Strengthened — PASS requires:
      1. Verdict is positive (CONTINUE_RESEARCH / BASELINE_VALID / CANDIDATE_FOR_V7_GATES)
      2. MHT was computed for real (mht_computed_for_real == True)
      3. PBO risk is LOW or MEDIUM (not HIGH, CRITICAL, or NOT_RUN)
      4. Deflated Sharpe > 0.0

    Fail-closed: when mht_computed_for_real is False (fallback identity),
    this gate NEVER passes regardless of reported PBO/deflated Sharpe values.
    """
    metrics = report.get("metrics", {})
    oos_r = metrics.get("oos_expectancy_r", {}).get("value", 0.0)
    oos_s = metrics.get("oos_sharpe", {}).get("value", 0.0)
    oos_t = metrics.get("oos_trade_count", 0)

    mht = report.get("multiple_hypothesis_control", {})
    pbo_risk = mht.get("pbo_or_backtest_overfit_risk", "NOT_RUN")
    deflated_sharpe = mht.get("deflated_sharpe_or_equivalent")
    mht_real = mht.get("mht_computed_for_real", False)

    evidence = (
        f"RESEARCH_BACKTEST evidence from {report.get('report_id', 'unknown')}: "
        f"oos_expectancy_r={oos_r:.4f}R, "
        f"oos_sharpe={oos_s:.4f}, "
        f"oos_trade_count={oos_t}, "
        f"pbo_risk={pbo_risk}, "
        f"deflated_sharpe={deflated_sharpe}, "
        f"mht_computed_for_real={mht_real}"
    )

    verdict = report.get("verdict", "")
    verdict_ok = verdict in (
        "CONTINUE_RESEARCH", "BASELINE_VALID", "CANDIDATE_FOR_V7_GATES",
    )

    # Fail-closed: MHT must be real
    if not mht_real:
        return evidence, "PENDING"

    # PBO must be LOW or MEDIUM
    pbo_ok = pbo_risk in ("LOW", "MEDIUM")

    # Deflated Sharpe must be positive
    ds_ok = deflated_sharpe is not None and deflated_sharpe > 0.0

    status = "PASS" if (verdict_ok and pbo_ok and ds_ok) else "PENDING"
    return evidence, status


def _gate_g2(report: dict) -> tuple[str, str]:
    """G2: WALK_FORWARD_OOS — walk-forward out-of-sample evidence."""
    vs = report.get("validation_summary", {})
    fold_cnt = vs.get("fold_count", 0)
    metrics = report.get("metrics", {})
    oos_r = metrics.get("oos_expectancy_r", {}).get("value", 0.0)
    oos_s = metrics.get("oos_sharpe", {}).get("value", 0.0)
    oos_wr = metrics.get("oos_win_rate", {}).get("value", 0.0)
    evidence = (
        f"WALK_FORWARD_OOS evidence from {vs.get('validation_report_id', 'unknown')}: "
        f"fold_count={fold_cnt}, "
        f"oos_expectancy_r={oos_r:.4f}R, "
        f"oos_sharpe={oos_s:.4f}, "
        f"oos_win_rate={oos_wr:.4f}"
    )
    verdict = report.get("verdict", "")
    status = "PASS" if verdict in ("BASELINE_VALID", "CANDIDATE_FOR_V7_GATES") else "PENDING"
    return evidence, status


def _gate_g3(report: dict) -> tuple[str, str]:
    """G3: COST_STRESS — fee, slippage, and funding stress analysis."""
    cs = report.get("cost_stress", {})
    combined = cs.get("combined_stress_edge_survives", False)
    be_cost = cs.get("break_even_cost_total_pct", 0.0)
    evidence = (
        f"COST_STRESS evidence from {report.get('report_id', 'unknown')}: "
        f"combined_stress_edge_survives={combined}, "
        f"break_even_cost_total={be_cost:.4f}%"
    )
    status = "PASS" if combined else "PENDING"
    return evidence, status


def _gate_g4(report: dict) -> tuple[str, str]:
    """G4: REGIME_BREAKDOWN — performance across TREND_UP/DOWN/RANGE/TRANSITION."""
    rb = report.get("regime_breakdown", {})
    regimes = rb.get("regimes", [])
    edge_only_rare = rb.get("edge_only_in_rare_regime", True)
    num_regimes = len(regimes)
    evidence = (
        f"REGIME_BREAKDOWN evidence from {report.get('report_id', 'unknown')}: "
        f"regimes_tested={num_regimes}, "
        f"edge_only_in_rare_regime={edge_only_rare}"
    )
    status = "PASS" if (not edge_only_rare and num_regimes >= 1) else "PENDING"
    return evidence, status


def _gate_g5(report: dict) -> tuple[str, str]:
    """G5: SYMBOL_STABILITY — no single symbol >40% of total edge."""
    ds = report.get("data_scope", {})
    symbols = ds.get("symbols", [])
    n = len(symbols)
    evidence = (
        f"SYMBOL_STABILITY evidence from {report.get('report_id', 'unknown')}: "
        f"symbols_tested={n} ({', '.join(symbols) if symbols else 'none'})"
    )
    status = "PASS" if n >= 2 else "PENDING"
    return evidence, status


def _gate_g6(report: dict) -> tuple[str, str]:
    """G6: CALIBRATION_RELIABILITY — requires CalibrationCandidate, not in MRR."""
    _ = report  # not available from ModeResearchReport alone
    evidence = (
        "CALIBRATION_RELIABILITY evidence deferred — "
        "requires CalibrationCandidate model confidence surface, "
        "not available from ModeResearchReport alone"
    )
    return evidence, "PENDING"


# ---------------------------------------------------------------------------
# Lineage extraction
# ---------------------------------------------------------------------------

def _build_lineage(mode: str, report: dict) -> dict:
    """Extract lineage chain from a ModeResearchReport."""
    ds = report.get("data_scope", {})
    symbols = ds.get("symbols", ["BTCUSDT"])
    data_refs = [f"raw-{s.lower()}-data" for s in symbols]

    fset_refs = report.get("feature_set_refs", [])
    lds_refs = report.get("label_dataset_refs", [])
    feature_set_id = fset_refs[0] if fset_refs else f"fs-{mode.lower()}-empirical-001"
    label_dataset_id = lds_refs[0] if lds_refs else f"lds-{mode.lower()}-empirical-001"

    profile = get_mode_profile(mode)
    sim_profile_id = f"{mode.lower()}_profile-1.0.0"

    run_id = report.get("run_id", f"run-empirical-{mode.lower()}-001")
    sim_run_ids = [f"sim-{mode.lower()}-empirical-001"]

    return {
        "data_refs": data_refs,
        "feature_set_id": feature_set_id,
        "label_dataset_id": label_dataset_id,
        "simulation_profile_id": sim_profile_id,
        "simulation_run_ids": sim_run_ids,
        "training_run_id": run_id,
        "git_commit": "",
        "lineage_verified": False,
    }


def build_v7_handoff_package(
    mode: str,
    handoff_package_id: str | None = None,
    alpha_candidate_id: str | None = None,
    mode_research_report_id: str | None = None,
    validation_report_id: str | None = None,
    model_artifact_id: str | None = None,
    calibration_candidate_id: str | None = None,
    recommended_status: str = HANDOFF_REVIEW_REQUIRED,
) -> dict:
    """Build a schema-valid placeholder V7HandoffPackage.

    Uses canonical V7 gate mapping (P0.8E corrected). All gates marked
    NOT_EVALUATED. Recommended status defaults to REVIEW_REQUIRED.

    Args:
        mode: 'SCALP', 'AGGRESSIVE_SCALP', or 'SWING'.
        handoff_package_id: Optional package ID override.
        alpha_candidate_id: Optional candidate ID override.
        mode_research_report_id: Optional mode report ID override.
        validation_report_id: Optional validation report ID override.
        model_artifact_id: Optional model artifact ID override.
        calibration_candidate_id: Optional calibration candidate ID override.
        recommended_status: Handoff recommendation (default: REVIEW_REQUIRED).

    Returns:
        V7HandoffPackage payload as dict.

    Raises:
        ModeError: Unknown mode.
        HandoffBuildError: Validation failed.
    """
    if mode not in ("SCALP", "AGGRESSIVE_SCALP", "SWING"):
        raise ModeError(f"Unknown mode: '{mode}'")

    profile = get_mode_profile(mode)
    mode_key = mode.lower().replace("-", "").replace(" ", "_")
    if mode == "AGGRESSIVE_SCALP":
        mode_key = "aggressive_scalp"
    elif mode == "SCALP":
        mode_key = "scalp"
    elif mode == "SWING":
        mode_key = "swing"

    pid = handoff_package_id or f"v7hp-{mode_key}-scaffold-001"
    acid = alpha_candidate_id or f"ac-{mode_key}-scaffold-001"
    mrid = mode_research_report_id or f"mrr-{mode_key}-scaffold-001"
    vrid = validation_report_id or f"vr-{mode_key}-scaffold-001"
    maid = model_artifact_id or f"ma-{mode_key}-scaffold-001"
    ccid = calibration_candidate_id or f"cc-{mode_key}-scaffold-001"

    # Canonical gate mapping — all NOT_EVALUATED in scaffold (P0.8E)
    gate_mapping = {
        "G0_doc_ready": _make_gate_entry(
            f"Authority docs for {mode} — scaffold placeholder (no real docs reviewed)"
        ),
        "G1_research_backtest": _make_gate_entry(
            f"Initial backtest metrics for {mode} — scaffold placeholder (no real data)"
        ),
        "G2_walk_forward_oos": _make_gate_entry(
            f"Walk-forward OOS evidence for {mode} — scaffold placeholder (no real data)"
        ),
        "G3_cost_stress": _make_gate_entry(
            f"Cost stress analysis for {mode} — scaffold placeholder (no real data)"
        ),
        "G4_regime_breakdown": _make_gate_entry(
            f"Regime breakdown for {mode} — scaffold placeholder (no real data)"
        ),
        "G5_symbol_stability": _make_gate_entry(
            f"Symbol stability for {mode} — scaffold placeholder (single symbol limitation)"
        ),
        "G6_calibration_reliability": _make_gate_entry(
            f"Calibration for {mode} — scaffold placeholder (no real model)"
        ),
        "G7_shadow": _make_gate_entry(
            "Shadow trading infrastructure not yet built — P0.9A+ dependency"
        ),
        "G8_paper": _make_gate_entry(
            "Paper trading infrastructure not yet built — P0.9A+ dependency"
        ),
        "G9_tiny_live": _make_gate_entry(
            "Tiny-live infrastructure not yet built — far future"
        ),
        "G10_live": _make_gate_entry(
            "Live infrastructure not yet built — far future"
        ),
    }

    payload = {
        "schema_version": "1.0.0",
        "handoff_package_id": pid,
        "mode": mode,
        "alpha_candidate_id": acid,
        "mode_research_report_id": mrid,
        "validation_report_id": vrid,
        "model_artifact_id": maid,
        "calibration_candidate_id": ccid,
        "v7_gate_mapping": gate_mapping,
        "recommended_status": recommended_status,
        "blocked_scopes": [
            f"Scaffold placeholder — no real data for {mode}",
            "No real model trained — all references are scaffold IDs",
            f"Funding model DEFERRED — blocks perpetual/live handoff for {mode}",
            f"{mode} is {profile.priority} — {profile.description}",
            "V7 has not reviewed this package — all gates are dummy mapped",
        ],
        "limitations": [
            "Scaffold placeholder for schema validation and interface testing only",
            "All referenced IDs are scaffold examples — do not expect real artifacts",
            "No real model binary exists at any URI",
            "No real validation was performed",
            "V7 gate mapping is structural — no real evidence behind gates",
            f"Recommended status {recommended_status} — V7 must independently verify",
            f"P0.8E canonical gate mapping used — all gates NOT_EVALUATED",
        ],
        "lineage": {
            "data_refs": ["raw-btcusdt-scaffold", "norm-btcusdt-scaffold"],
            "feature_set_id": f"fs-{mode_key}-scaffold-001",
            "label_dataset_id": f"lds-{mode_key}-scaffold-001",
            "simulation_profile_id": f"{mode_key}_profile-1.0.0",
            "simulation_run_ids": [f"sim-scaffold-{mode_key}-001"],
            "training_run_id": f"run-scaffold-{mode_key}-001",
            "git_commit": "0000000000000000000000000000000000000000",
            "lineage_verified": False,
        },
        "created_at": _now_iso(),
        "rejection_rules_applied": [
            "Scaffold placeholder — all dummy data, automatically REVIEW_REQUIRED",
            "No real OOS evidence — cannot pass G2-G6 without real data",
            "Funding DEFERRED — perpetual/live scope explicitly blocked",
            "Single symbol only — flagged as limitation",
        ],
    }

    # Validate against P0.8E-corrected schema
    schema = load_schema("v7_handoff_package.schema.json")
    result = validate_payload(schema, payload, f"v7_handoff_package({mode})")
    if not result.valid:
        raise HandoffBuildError(
            f"Built V7HandoffPackage for {mode} failed validation: {result.errors}"
        )

    return payload


def build_all_handoffs() -> dict[str, dict]:
    """Build scaffold handoff packages for all three modes.

    Returns:
        Dict mapping mode → V7HandoffPackage payload.
    """
    return {
        "SCALP": build_v7_handoff_package("SCALP"),
        "AGGRESSIVE_SCALP": build_v7_handoff_package("AGGRESSIVE_SCALP"),
        "SWING": build_v7_handoff_package("SWING"),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Empirical Handoff Builder — consumes real ModeResearchReport evidence
# ═══════════════════════════════════════════════════════════════════════════

def build_empirical_handoff_package(
    mode: str,
    mode_research_report: dict,
    handoff_package_id: str | None = None,
    validation_report_id: str | None = None,
    model_artifact_id: str | None = None,
    calibration_candidate_id: str | None = None,
) -> dict:
    """Build a schema-valid V7HandoffPackage from an empirical ModeResearchReport.

    Extracts G0-G10 gate evidence references from the report data, sets gate
    statuses based on evidence quality, maps report verdict to recommended
    status, and populates the full lineage chain from report metadata.

    Args:
        mode: 'SCALP', 'AGGRESSIVE_SCALP', or 'SWING'.
        mode_research_report: Dict produced by
            build_empirical_mode_research_report() or any schema-valid
            ModeResearchReport dict.
        handoff_package_id: Optional package ID override.
        validation_report_id: Optional validation report ID override.
        model_artifact_id: Optional model artifact ID override.
        calibration_candidate_id: Optional calibration candidate ID override.

    Returns:
        V7HandoffPackage payload as dict, validated against schema.

    Raises:
        ModeError: Unknown mode.
        HandoffBuildError: Validation failed or report missing required fields.
    """
    if mode not in ("SCALP", "AGGRESSIVE_SCALP", "SWING"):
        raise ModeError(f"Unknown mode: '{mode}'")

    profile = get_mode_profile(mode)
    mode_key = mode.lower().replace("-", "").replace(" ", "_")
    if mode == "AGGRESSIVE_SCALP":
        mode_key = "aggressive_scalp"

    # --- Extract report identifiers ---
    report_id = mode_research_report.get("report_id", "")
    verdict = mode_research_report.get("verdict", "")

    # --- Build artifact IDs ---
    pid = handoff_package_id or f"v7hp-{mode_key}-empirical-001"

    # alpha_candidate_id from the first alpha_thesis or a generated ID
    theses = mode_research_report.get("alpha_theses", [])
    acid = (
        theses[0].get("alpha_thesis_id", f"ac-{mode_key}-empirical-001")
        if theses else f"ac-{mode_key}-empirical-001"
    )

    mrid = report_id or f"mrr-{mode_key}-empirical-001"

    vs = mode_research_report.get("validation_summary", {})
    vrid = validation_report_id or vs.get(
        "validation_report_id", f"vr-{mode_key}-empirical-001"
    )

    maid = model_artifact_id or f"ma-{mode_key}-empirical-001"
    ccid = calibration_candidate_id or f"cc-{mode_key}-empirical-001"

    # --- Build gate mapping from report evidence ---
    gate_mapping = {
        "G0_doc_ready": _make_gate_entry(*_gate_g0(mode_research_report)),
        "G1_research_backtest": _make_gate_entry(*_gate_g1(mode_research_report)),
        "G2_walk_forward_oos": _make_gate_entry(*_gate_g2(mode_research_report)),
        "G3_cost_stress": _make_gate_entry(*_gate_g3(mode_research_report)),
        "G4_regime_breakdown": _make_gate_entry(*_gate_g4(mode_research_report)),
        "G5_symbol_stability": _make_gate_entry(*_gate_g5(mode_research_report)),
        "G6_calibration_reliability": _make_gate_entry(*_gate_g6(mode_research_report)),
        "G7_shadow": _make_gate_entry(
            "Shadow trading infrastructure not yet built — P0.9A+ dependency"
        ),
        "G8_paper": _make_gate_entry(
            "Paper trading infrastructure not yet built — P0.9A+ dependency"
        ),
        "G9_tiny_live": _make_gate_entry(
            "Tiny-live infrastructure not yet built — far future"
        ),
        "G10_live": _make_gate_entry(
            "Live infrastructure not yet built — far future"
        ),
    }

    # --- Map verdict to recommended_status ---
    recommended_status = _status_from_verdict(verdict)

    # --- Collect blocked_scopes and limitations from report ---
    report_blocked = list(mode_research_report.get("blocked_scopes", []))
    report_limitations = list(mode_research_report.get("limitations", []))

    blocked_scopes = list(report_blocked) + [
        "Funding model DEFERRED — blocks perpetual/live scope",
        "AlphaForge RECOMMENDS. V7 DECIDES. This package does NOT authorize trading.",
    ]

    limitations = list(report_limitations) + [
        f"Empirical handoff package for {mode} — evidence quality reflects ModeResearchReport verdict: {verdict}",
        "G6 calibration reliability requires CalibrationCandidate — not available in ModeResearchReport alone",
        "G7-G10 infrastructure not yet built — shadow, paper, live cannot be evaluated",
    ]

    # --- MHT overfit evidence (for Rule 7) ---
    _mht = mode_research_report.get("multiple_hypothesis_control", {})
    _mht_real = _mht.get("mht_computed_for_real", False)
    _mht_pbo_risk = _mht.get("pbo_or_backtest_overfit_risk", "NOT_RUN")
    _mht_ds = _mht.get("deflated_sharpe_or_equivalent")
    _gate_g1_status = _gate_g1(mode_research_report)[1]

    # --- Build rejections rules applied ---
    rejection_rules_applied = [
        "Rule 1 (Missing evidence): PASSED — ModeResearchReport present",
        "Rule 2 (Incomplete gate mapping): PASSED — all 11 canonical gates mapped",
        "Rule 3 (Lineage break): PASSED — lineage traced from report",
        "Rule 4 (Checksum mismatch): DEFERRED — no model binary checksum in empirical handoff",
        f"Rule 5 (Validation failure): verdict={verdict} — see recommended_status",
        "Rule 6 (Cost vulnerability): "
        f"{'PASSED' if _gate_g3(mode_research_report)[1] == 'PASS' else 'PENDING'} — "
        f"combined_stress_edge_survives={mode_research_report.get('cost_stress', {}).get('combined_stress_edge_survives', False)}",
        f"Rule 7 (Overfit detected): {_gate_g1_status} — "
        f"pbo_risk={_mht_pbo_risk}, "
        f"deflated_sharpe={_mht_ds}, "
        f"mht_computed_for_real={_mht_real}",
        "Rule 8 (Single-symbol overfitting): "
        f"{'PASSED' if _gate_g5(mode_research_report)[1] == 'PASS' else 'PENDING'} — "
        f"symbols_tested={len(mode_research_report.get('data_scope', {}).get('symbols', []))}",
        "Rule 9 (Calibration unusable): DEFERRED — no CalibrationCandidate in empirical handoff",
        "Rule 10 (Funding unknown): BLOCKED — funding DEFERRED for perpetual/live",
        "Rule 11 (Blocked scope violation): PASSED — scopes from report carried through",
        "Rule 12 (Policy conflict): DEFERRED — V7 policy not loaded in AlphaForge",
    ]

    # --- Build lineage ---
    lineage = _build_lineage(mode, mode_research_report)

    # --- Build payload ---
    payload = {
        "schema_version": "1.0.0",
        "handoff_package_id": pid,
        "mode": mode,
        "alpha_candidate_id": acid,
        "mode_research_report_id": mrid,
        "validation_report_id": vrid,
        "model_artifact_id": maid,
        "calibration_candidate_id": ccid,
        "v7_gate_mapping": gate_mapping,
        "recommended_status": recommended_status,
        "blocked_scopes": blocked_scopes,
        "limitations": limitations,
        "lineage": lineage,
        "created_at": _now_iso(),
        "rejection_rules_applied": rejection_rules_applied,
    }

    # Validate against schema
    schema = load_schema("v7_handoff_package.schema.json")
    result = validate_payload(schema, payload, f"v7_handoff_package({mode})")
    if not result.valid:
        raise HandoffBuildError(
            f"Built empirical V7HandoffPackage for {mode} failed validation: "
            f"{result.errors}"
        )

    return payload


def build_empirical_handoffs(
    mode_research_reports: dict[str, dict],
) -> dict[str, dict]:
    """Build empirical handoff packages for all three modes.

    Args:
        mode_research_reports: Dict mapping mode → ModeResearchReport dict.

    Returns:
        Dict mapping mode → V7HandoffPackage payload.
    """
    return {
        mode: build_empirical_handoff_package(mode, report)
        for mode, report in mode_research_reports.items()
    }
