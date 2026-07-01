"""AlphaForge report builders.

Build schema-valid ModeResearchReport and AlphaForgeResearchReport
payloads. ModeResearchReport is scaffold/placeholder only.
AlphaForgeResearchReport consumes up to 3 ModeResearchReports and
extracts promoted/rejected candidates, V7 handoff package references,
and cross-mode limitations from actual verdict data.

All payloads are NON-profitability — they describe research quality,
not trading returns.
"""
from datetime import datetime, timezone

from alphaforge.constants import (
    MODE_PRIORITY_PRIMARY,
    MODE_PRIORITY_SECONDARY_BASELINE,
    REPORT_TYPE_PRIMARY,
    REPORT_TYPE_SECONDARY_BASELINE,
    V7_REGIMES,
    MODE_REPORT_VERDICTS,
)
from alphaforge.modes.profiles import get_mode_profile, ModeProfile
from alphaforge.contracts.loader import load_schema
from alphaforge.contracts.validator import validate_payload
from alphaforge.errors import ReportBuildError, ModeError


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_metric_ci(value: float, ci_lower: float, ci_upper: float) -> dict:
    return {
        "value": value,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "ci_level": 0.95,
    }


def _empty_fold_metrics(fold_count: int = 6) -> list[dict]:
    return [
        {"fold": i + 1, "sharpe": 0.0, "expectancy_r": 0.0, "win_rate": 0.0, "trade_count": 0}
        for i in range(fold_count)
    ]


def _make_cost_stress(slippage_pct: float = 0.02) -> dict:
    return {
        "baseline_fee_pct": 0.04,
        "baseline_slippage_pct": slippage_pct,
        "fee_stress_levels": [
            {"multiplier": 1.0, "oos_expectancy_r": 0.0, "edge_survives": False},
            {"multiplier": 1.5, "oos_expectancy_r": -0.1, "edge_survives": False},
            {"multiplier": 2.0, "oos_expectancy_r": -0.2, "edge_survives": False},
        ],
        "slippage_stress_levels": [
            {"multiplier": 1.0, "oos_expectancy_r": 0.0, "edge_survives": False},
            {"multiplier": 1.5, "oos_expectancy_r": -0.1, "edge_survives": False},
            {"multiplier": 2.0, "oos_expectancy_r": -0.2, "edge_survives": False},
        ],
        "combined_stress_edge_survives": False,
        "break_even_cost_total_pct": 0.01,
        "cost_stress_verdict": "FAIL_EDGE_DESTROYED_BY_COSTS",
        "net_edge_after_costs": 0.0,
    }


def _make_no_trade_comparison() -> dict:
    return {
        "long_vs_no_trade": "NO_TRADE dominates in scaffold placeholder (no real data)",
        "short_vs_no_trade": "NO_TRADE dominates in scaffold placeholder (no real data)",
        "active_beats_no_trade": False,
        "no_trade_baseline": "NO_TRADE dominates — scaffold placeholder",
        "saved_loss_count": 0,
        "missed_opportunity_count": 0,
        "trade_vs_no_trade_verdict": "NO_TRADE_DOMINATES",
        "summary": "Scaffold placeholder — no real edge demonstrated.",
    }


def _make_regime_breakdown() -> dict:
    return {
        "regimes_tested": list(V7_REGIMES),
        "regimes": [
            {"regime": r, "sample_pct": 0.25, "oos_expectancy_r": 0.0, "edge_present": False}
            for r in V7_REGIMES
        ],
        "best_regime": "NONE",
        "worst_regime": "NONE",
        "edge_only_in_rare_regime": False,
        "regime_stability_verdict": "NOT_EVALUATED",
        "summary": "Scaffold placeholder — no real regime analysis.",
    }


def _make_mht_control(mode: str) -> dict:
    risk_flag = "CRITICAL" if mode == "AGGRESSIVE_SCALP" else "HIGH" if mode == "SCALP" else "MEDIUM"
    return {
        "tested_hypothesis_count": 1,
        "correction_method": "NONE_APPLIED",
        "corrected_significance": None,
        "data_snooping_risk_flag": risk_flag,
        "deflated_sharpe_or_equivalent": None,
        "notes": f"Scaffold placeholder — no real hypothesis testing for {mode}.",
    }


def _make_v7_gate_readiness(mode: str) -> dict:
    """Return placeholder V7 gate readiness assessment."""
    not_ready = ["G6_calibration_reliability", "G7_shadow", "G8_paper", "G9_tiny_live", "G10_live"]
    return {
        "gates_mapped": [g for g in ["G0_doc_ready", "G1_research_backtest", "G2_walk_forward_oos", "G3_cost_stress", "G4_regime_breakdown", "G5_symbol_stability"]],
        "gates_not_ready": list(not_ready),
        "overall_readiness": "NOT_READY",
    }


def build_mode_research_report(
    mode: str,
    report_id: str | None = None,
    run_id: str | None = None,
) -> dict:
    """Build a schema-valid placeholder ModeResearchReport.

    All values are dummy/example placeholders. This is a scaffold builder
    for testing contract interfaces — NOT a real research report.

    Args:
        mode: 'SCALP', 'AGGRESSIVE_SCALP', or 'SWING'.
        report_id: Optional report ID override.
        run_id: Optional run ID override.

    Returns:
        ModeResearchReport payload as dict.

    Raises:
        ModeError: Unknown mode.
        ReportBuildError: Payload failed schema validation.
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

    rid = report_id or f"mrr-{mode_key}-scaffold-001"
    run = run_id or f"run-scaffold-{mode_key}-001"

    payload = {
        "schema_version": "1.0.0",
        "report_id": rid,
        "mode": mode,
        "mode_priority": profile.priority,
        "report_type": profile.report_type,
        "created_at": _now_iso(),
        "run_id": run,
        "data_scope": {
            "symbols": ["BTCUSDT"],
            "date_range_start": "2025-01-01T00:00:00Z",
            "date_range_end": "2026-01-01T00:00:00Z",
            "primary_timeframes": [profile.primary_timeframe],
            "secondary_timeframes": [profile.context_timeframe, profile.refinement_timeframe],
            "data_quality_summary": f"Scaffold placeholder — no real market data. Mode {mode}, timeframe {profile.primary_timeframe}.",
        },
        "feature_set_refs": [f"fs-{mode_key}-scaffold-001"],
        "label_dataset_refs": [f"lds-{mode_key}-scaffold-001"],
        "alpha_theses": [
            {
                "alpha_thesis_id": f"ath-{mode_key}-scaffold-001",
                "title": f"Scaffold placeholder {mode} thesis",
                "status": "PROPOSED",
                "evidence_quality": "INSUFFICIENT",
            }
        ],
        "validation_summary": {
            "validation_report_id": f"vr-{mode_key}-scaffold-001",
            "fold_count": 6,
            "verdict": "INCONCLUSIVE",
            "overfit_risk": "HIGH",
        },
        "metrics": {
            "oos_sharpe": _make_metric_ci(0.0, -1.0, 1.0),
            "oos_expectancy_r": _make_metric_ci(0.0, -0.5, 0.5),
            "oos_win_rate": _make_metric_ci(0.4, 0.2, 0.6),
            "oos_profit_factor": _make_metric_ci(0.9, 0.5, 1.3),
            "oos_max_drawdown_r": _make_metric_ci(-3.0, -6.0, -1.0),
            "oos_trade_count": 0,
            "active_trade_count": 0,
            "long_trade_count": 0,
            "short_trade_count": 0,
            "no_trade_count": 0,
            "total_gross_R": 0.0,
            "total_fee_cost_R": 0.0,
            "total_slippage_cost_R": 0.0,
            "total_funding_cost_R": 0.0,
            "total_net_R": 0.0,
            "exposure_pct": 0.0,
            "avg_net_R_per_active_trade": 0.0,
            "avg_net_R_per_decision": 0.0,
            "turnover": 0.0,
            "avg_hold_bars": 0.0,
            "per_fold_metrics": _empty_fold_metrics(6),
        },
        "cost_stress": _make_cost_stress(0.03 if mode == "AGGRESSIVE_SCALP" else 0.02),
        "no_trade_comparison": _make_no_trade_comparison(),
        "regime_breakdown": _make_regime_breakdown(),
        "v7_gate_readiness": _make_v7_gate_readiness(mode),
        "multiple_hypothesis_control": _make_mht_control(mode),
        "verdict": "BASELINE_WEAK" if profile.is_baseline else "CONTINUE_RESEARCH",
        "blocked_scopes": [
            "Scaffold placeholder — no real empirical data",
            "Funding model DEFERRED — perpetual/live scope blocked",
            f"{mode} thresholds: {profile.promotion_status}",
        ],
        "limitations": [
            "Scaffold placeholder — do not interpret as real research",
            "All metric values are zeros — no real model was trained",
            "Single symbol limitation (BTCUSDT only)",
            f"P0.8E canonical timeframe: {profile.primary_timeframe} primary",
        ],
        "recommended_actions": [
            f"Obtain real market data at {profile.primary_timeframe} primary timeframe",
            f"Run simulation for {mode} with locked profile",
            "Generate real labels from SimulationOutput",
            "Compute features with leakage controls",
            "Train models with real data",
        ],
    }

    # Validate against schema
    schema = load_schema("mode_research_report.schema.json")
    result = validate_payload(schema, payload, f"mode_research_report({mode})")
    if not result.valid:
        raise ReportBuildError(
            f"Built mode research report for {mode} failed validation: {result.errors}"
        )

    return payload


def _extract_candidate_evidence(mr: dict) -> str:
    """Extract a human-readable evidence summary from a mode report.

    Combines verdict, key metrics, MHT status, and gate readiness into
    a single evidence string for promoted/rejected candidate entries.
    """
    mode = mr.get("mode", "UNKNOWN")
    verdict = mr.get("verdict", "UNKNOWN")

    metrics = mr.get("metrics", {})
    oos_expectancy = metrics.get("oos_expectancy_r", {}).get("value", "N/A")
    oos_sharpe = metrics.get("oos_sharpe", {}).get("value", "N/A")
    oos_trades = metrics.get("oos_trade_count", "N/A")

    mht = mr.get("multiple_hypothesis_control", {})
    mht_status = mht.get("mht_status", mht.get("correction_method", "NOT_EVALUATED"))

    cost_stress = mr.get("cost_stress", {})
    cost_survives = cost_stress.get("combined_stress_edge_survives", False)

    regime = mr.get("regime_breakdown", {})
    regime_stable = not regime.get("edge_only_in_rare_regime", True)

    gate_readiness = mr.get("v7_gate_readiness", {})
    gates_mapped = gate_readiness.get("gates_mapped", [])

    v7_verdict = mr.get("validation_summary", {}).get("verdict", verdict)

    return (
        f"Mode={mode} Verdict={verdict} "
        f"OOS_Expectancy_R={oos_expectancy} Sharpe={oos_sharpe} Trades={oos_trades} "
        f"MHT={mht_status} CostStressSurvives={cost_survives} "
        f"RegimeStable={regime_stable} "
        f"ValidationVerdict={v7_verdict} "
        f"V7GatesMapped={len(gates_mapped)}"
    )


def _promotion_verdicts() -> set:
    """Verdicts that qualify a mode as a promoted candidate."""
    return {"CANDIDATE_FOR_V7_GATES", "BASELINE_VALID"}


def _rejection_verdicts() -> set:
    """Verdicts that qualify a mode as explicitly rejected."""
    return {"REJECT", "INCONCLUSIVE", "BASELINE_WEAK"}


def build_alphaforge_research_report(
    mode_reports: list[dict] | None = None,
    report_id: str | None = None,
    run_id: str | None = None,
    handoff_packages: list[dict] | None = None,
) -> dict:
    """Build a schema-valid AlphaForgeResearchReport.

    Consumes up to 3 ModeResearchReports (SCALP, AGGRESSIVE_SCALP, SWING)
    and extracts promoted/rejected candidates, V7 handoff package references,
    and cross-mode limitations from the actual verdict data in the reports.

    When mode_reports is not provided, builds all three automatically using
    scaffold placeholder reports.

    Args:
        mode_reports: Optional list of mode report payloads. Must include
            exactly SCALP, AGGRESSIVE_SCALP, and SWING. Each report must
            have at minimum 'mode' and 'verdict' keys.
        report_id: Optional report ID override.
        run_id: Optional run ID override.
        handoff_packages: Optional list of V7HandoffPackage payloads to
            reference. When provided, the report includes references to
            these packages for modes that are promoted candidates.

    Returns:
        AlphaForgeResearchReport payload as dict, validated against schema.

    Raises:
        ReportBuildError: If less than 3 mode reports, missing required
            fields, or validation fails.
    """
    if mode_reports is None:
        mode_reports = [
            build_mode_research_report("SCALP"),
            build_mode_research_report("AGGRESSIVE_SCALP"),
            build_mode_research_report("SWING"),
        ]

    # Check each mode report has minimum required fields first
    for mr in mode_reports:
        if not isinstance(mr, dict):
            raise ReportBuildError(
                f"Each mode report must be a dict. Got {type(mr).__name__}"
            )
        if "mode" not in mr or "verdict" not in mr:
            raise ReportBuildError(
                f"Each mode report must have 'mode' and 'verdict' keys. "
                f"Got keys: {sorted(mr.keys())}"
            )

    modes_found = {r["mode"] for r in mode_reports}
    if modes_found != {"SCALP", "AGGRESSIVE_SCALP", "SWING"}:
        raise ReportBuildError(
            f"AlphaForgeResearchReport requires all 3 modes, got {modes_found}"
        )

    rid = report_id or "afrr-scaffold-001"
    run = run_id or "run-scaffold-all-001"

    # --- Build mode report summaries ---
    mode_report_summaries = []
    for mr in mode_reports:
        profile = get_mode_profile(mr["mode"])
        mode_report_summaries.append({
            "mode": mr["mode"],
            "mode_priority": profile.priority,
            "report_id": mr["report_id"],
            "report_type": profile.report_type,
            "verdict": mr["verdict"],
            "summary": mr.get("limitations", [f"Mode {mr['mode']} — {profile.description}"])[0],
        })

    # --- Extract promoted candidates (modes with promotion-worthy verdicts) ---
    promoted_candidates: list[dict] = []
    promoted_modes: set[str] = set()
    for mr in mode_reports:
        verdict = mr.get("verdict", "")
        if verdict in _promotion_verdicts():
            candidate_id = f"ac-{mr['mode'].lower()}-{rid}"
            evidence = _extract_candidate_evidence(mr)
            promoted_candidates.append({
                "alpha_candidate_id": candidate_id,
                "mode": mr["mode"],
                "reason": (
                    f"Mode {mr['mode']} achieved verdict {verdict}. "
                    f"Evidence: {evidence}"
                ),
            })
            promoted_modes.add(mr["mode"])

    # --- Extract rejected candidates (modes with rejection-worthy verdicts) ---
    rejected_candidates: list[dict] = []
    for mr in mode_reports:
        verdict = mr.get("verdict", "")
        if verdict in _rejection_verdicts():
            evidence = _extract_candidate_evidence(mr)
            rejected_candidates.append({
                "alpha_candidate_id": f"ac-{mr['mode'].lower()}-rejected",
                "mode": mr["mode"],
                "rejection_reason": (
                    f"Mode {mr['mode']} verdict: {verdict}. "
                    f"Evidence: {evidence}. "
                    f"Insufficient evidence for promotion at this time."
                ),
            })
        elif verdict not in _promotion_verdicts() and verdict not in _rejection_verdicts():
            # CONTINUE_RESEARCH is neither promoted nor fully rejected
            evidence = _extract_candidate_evidence(mr)
            rejected_candidates.append({
                "alpha_candidate_id": f"ac-{mr['mode'].lower()}-research",
                "mode": mr["mode"],
                "rejection_reason": (
                    f"Mode {mr['mode']} verdict: {verdict}. "
                    f"Evidence: {evidence}. "
                    f"Further research required before promotion consideration."
                ),
            })

    # --- Build aggregate MHT control from mode reports ---
    aggregate_hypotheses = 0
    aggregate_features = 0
    aggregate_trials = 0
    correction_methods: set[str] = set()

    for mr in mode_reports:
        mht = mr.get("multiple_hypothesis_control", {})
        aggregate_hypotheses += mht.get("tested_hypothesis_count", 0)
        aggregate_features += mht.get("tested_feature_count", 0)
        aggregate_trials += mht.get("trial_count_disclosure", mht.get("aggregate_trial_count", 0))
        correction_methods.add(mht.get("correction_method", "NONE_APPLIED"))

    # Determine aggregate MHT status from correction methods
    # "NONE_APPLIED" → aggregate is NOT_RUN
    # Any real correction method → APPLIED_WITH_WARNINGS
    has_real_correction = any(c not in ("NONE_APPLIED", "NONE") for c in correction_methods)

    if has_real_correction:
        aggregate_mht_status = "APPLIED_WITH_WARNINGS"
        aggregate_correction = next(
            (c for c in sorted(correction_methods) if c not in ("NONE_APPLIED", "NONE")),
            "NONE_APPLIED",
        )
        mht_block_reason = (
            f"MHT correction applied ({aggregate_correction}) across mode reports. "
            f"Aggregate hypotheses tested: {aggregate_hypotheses}. "
            "Some modes may have incomplete MHT coverage. "
            "Review individual mode reports for details."
        )
    else:
        aggregate_mht_status = "NOT_RUN"
        aggregate_correction = "NONE_APPLIED"
        mht_block_reason = (
            "No mode report has applied MHT correction. "
            f"Aggregate hypotheses tested: {aggregate_hypotheses}. "
            "Strong edge/profitability claims are BLOCKED. "
            "MHT correction requires model training which is not performed "
            "in this non-ML research phase."
        )

    aggregate_mht = {
        "aggregate_mht_status": aggregate_mht_status,
        "aggregate_tested_hypothesis_count": aggregate_hypotheses,
        "aggregate_tested_feature_count": aggregate_features,
        "aggregate_trial_count": aggregate_trials,
        "correction_method": aggregate_correction,
        "false_discovery_control": "NOT_APPLIED",
        "deflated_sharpe_or_pbo_assessment": "NOT_APPLIED",
        "mht_block_reason": mht_block_reason,
    }

    # --- Build global limitations from mode reports ---
    global_limitations: list[str] = []
    for mr in mode_reports:
        mode = mr.get("mode", "UNKNOWN")
        verdict = mr.get("verdict", "UNKNOWN")
        mode_limitations = mr.get("limitations", [])
        mode_blocked = mr.get("blocked_scopes", [])

        if mode_limitations:
            global_limitations.append(f"{mode} ({verdict}): {mode_limitations[0]}")
        if mode_blocked:
            global_limitations.append(f"{mode} blocked scopes: {mode_blocked[0]}")
        if len(mode_limitations) > 1:
            global_limitations.append(f"{mode} additional: {mode_limitations[1]}")

    # Add overarching limitation
    funding_deferred = all(
        "DEFERRED" in str(mr.get("blocked_scopes", []))
        for mr in mode_reports
    )
    if funding_deferred:
        global_limitations.append("Funding model is DEFERRED for all modes")

    # Deduplicate
    seen: set[str] = set()
    deduped_limitations: list[str] = []
    for lim in global_limitations:
        if lim not in seen:
            seen.add(lim)
            deduped_limitations.append(lim)
    global_limitations = deduped_limitations

    # --- Build V7 handoff package references ---
    v7_handoff_refs: list[dict] = []
    if handoff_packages:
        for hp in handoff_packages:
            v7_handoff_refs.append({
                "handoff_package_id": hp.get("handoff_package_id", "unknown"),
                "mode": hp.get("mode", "UNKNOWN"),
                "recommended_status": hp.get("recommended_status", "REVIEW_REQUIRED"),
            })
    else:
        # Generate minimal handoff references for promoted candidates
        for mr in mode_reports:
            if mr.get("verdict") in _promotion_verdicts():
                mode = mr["mode"]
                profile = get_mode_profile(mode)
                v7_handoff_refs.append({
                    "handoff_package_id": f"v7hp-{mode.lower()}-{rid}",
                    "mode": mode,
                    "recommended_status": "REVIEW_REQUIRED" if profile.is_primary else "REVIEW_REQUIRED",
                })

    # --- Build cross-mode insights from mode data ---
    primary_modes_found = [
        mr for mr in mode_reports
        if get_mode_profile(mr["mode"]).is_primary
    ]
    baseline_modes_found = [
        mr for mr in mode_reports
        if get_mode_profile(mr["mode"]).is_baseline
    ]

    cross_mode_insights: list[str] = []
    promoted_count = len(promoted_candidates)
    rejected_count = len(rejected_candidates)

    if promoted_count > 0:
        promoted_names = ", ".join(c["mode"] for c in promoted_candidates)
        cross_mode_insights.append(
            f"{promoted_count} mode(s) achieved promotion-worthy verdict: {promoted_names}"
        )
    else:
        cross_mode_insights.append("No modes achieved promotion-worthy verdicts")

    cross_mode_insights.append(
        f"{len(primary_modes_found)} PRIMARY modes ({len(primary_modes_found)} total)"
    )
    cross_mode_insights.append(
        f"{len(baseline_modes_found)} SECONDARY_BASELINE modes ({len(baseline_modes_found)} total)"
    )

    # Add mode-specific fact about timeframes
    for mr in mode_reports:
        scope = mr.get("data_scope", {})
        tfs = scope.get("primary_timeframes", ["?"])
        cross_mode_insights.append(
            f"{mr['mode']} primary timeframe: {tfs[0] if tfs else '?'}"
        )

    # --- Build next research priorities ---
    next_priorities: list[str] = []
    if promoted_count > 0:
        next_priorities.append(
            "Prepare V7 handoff packages for promoted candidates"
        )
        next_priorities.append(
            "Initiate G5 symbol stability evaluation for promoted modes"
        )
    if rejected_count > 0:
        next_priorities.append(
            "Review feature engineering and data quality for rejected modes"
        )
    next_priorities.append(
        "Run simulations at locked primary timeframes for all modes"
    )
    next_priorities.append(
        "Generate real labels from SimulationOutput for empirical validation"
    )

    payload = {
        "schema_version": "1.0.0",
        "alphaforge_report_id": rid,
        "run_id": run,
        "created_at": _now_iso(),
        "mode_reports": mode_report_summaries,
        "promoted_candidates": promoted_candidates,
        "multiple_hypothesis_control": aggregate_mht,
        "rejected_candidates": rejected_candidates,
        "global_limitations": global_limitations,
        "v7_handoff_packages": v7_handoff_refs,
        "cross_mode_insights": cross_mode_insights,
        "next_research_priorities": next_priorities,
    }

    # Validate against schema
    schema = load_schema("alphaforge_research_report.schema.json")
    result = validate_payload(schema, payload, "alphaforge_research_report")
    if not result.valid:
        raise ReportBuildError(
            f"Built AlphaForgeResearchReport failed validation: {result.errors}"
        )

    return payload
