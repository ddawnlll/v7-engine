"""AlphaForge report builders.

Build schema-valid placeholder ModeResearchReport and
AlphaForgeResearchReport payloads. All payloads use dummy/example
values — NO real research, NO profitability claims.
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


def build_alphaforge_research_report(
    mode_reports: list[dict] | None = None,
    report_id: str | None = None,
    run_id: str | None = None,
) -> dict:
    """Build a schema-valid placeholder AlphaForgeResearchReport.

    Requires all three mode reports (SCALP, AGGRESSIVE_SCALP, SWING).
    If not provided, builds all three automatically.

    Args:
        mode_reports: Optional list of mode report payloads.
        report_id: Optional report ID override.
        run_id: Optional run ID override.

    Returns:
        AlphaForgeResearchReport payload as dict.

    Raises:
        ReportBuildError: If less than 3 mode reports or validation fails.
    """
    if mode_reports is None:
        mode_reports = [
            build_mode_research_report("SCALP"),
            build_mode_research_report("AGGRESSIVE_SCALP"),
            build_mode_research_report("SWING"),
        ]

    modes_found = {r["mode"] for r in mode_reports}
    if modes_found != {"SCALP", "AGGRESSIVE_SCALP", "SWING"}:
        raise ReportBuildError(
            f"AlphaForgeResearchReport requires all 3 modes, got {modes_found}"
        )

    rid = report_id or "afrr-scaffold-001"
    run = run_id or "run-scaffold-all-001"

    mode_report_summaries = []
    for mr in mode_reports:
        profile = get_mode_profile(mr["mode"])
        mode_report_summaries.append({
            "mode": mr["mode"],
            "mode_priority": profile.priority,
            "report_id": mr["report_id"],
            "report_type": profile.report_type,
            "verdict": mr["verdict"],
            "summary": f"Scaffold placeholder {mr['mode']} — {profile.description}",
        })

    payload = {
        "schema_version": "1.0.0",
        "alphaforge_report_id": rid,
        "run_id": run,
        "created_at": _now_iso(),
        "mode_reports": mode_report_summaries,
        "promoted_candidates": [],
        "multiple_hypothesis_control": {
            "aggregate_mht_status": "NOT_RUN",
            "aggregate_tested_hypothesis_count": 0,
            "aggregate_tested_feature_count": 0,
            "aggregate_trial_count": 0,
            "correction_method": "NONE_APPLIED",
            "false_discovery_control": "NOT_APPLIED",
            "deflated_sharpe_or_pbo_assessment": "NOT_APPLIED",
            "mht_block_reason": (
                "Scaffold placeholder — no real empirical MHT performed. "
                "Strong edge/profitability claims are BLOCKED."
            ),
        },
        "rejected_candidates": [
            {
                "alpha_candidate_id": "ac-scaffold-001",
                "mode": "SCALP",
                "rejection_reason": "Scaffold placeholder — no real data. All candidates rejected by default.",
            }
        ],
        "global_limitations": [
            "Scaffold placeholder — no real market data was used",
            "No real models were trained",
            "No real validation was performed",
            "All three modes have zero empirical evidence",
            "Funding model is DEFERRED for all modes",
        ],
        "v7_handoff_packages": [],
        "cross_mode_insights": [
            "Scaffold placeholder — no cross-mode insights available",
            "SCALP (1h) and AGGRESSIVE_SCALP (15m) are PRIMARY research targets",
            "SWING (4h) provides SECONDARY baseline for architectural validation",
        ],
        "next_research_priorities": [
            "Obtain real market data at locked primary timeframes",
            "Run simulations for SCALP (1h) and AGGRESSIVE_SCALP (15m)",
            "Validate SWING baseline (4h) with real data",
        ],
    }

    # Validate against schema
    schema = load_schema("alphaforge_research_report.schema.json")
    result = validate_payload(schema, payload, "alphaforge_research_report")
    if not result.valid:
        raise ReportBuildError(
            f"Built AlphaForgeResearchReport failed validation: {result.errors}"
        )

    return payload
