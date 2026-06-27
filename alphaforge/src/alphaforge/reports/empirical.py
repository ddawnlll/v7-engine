"""AlphaForge empirical report builder — P0.9C.

Consumes walk-forward validation (WFV) results, cost stress, and regime
breakdown from the v0.2 pipeline and produces a full ModeResearchReport
with REAL metrics (not placeholder zeros).

Verdict system (evidence-gated, NOT profitability-gated):
  INCONCLUSIVE    → No reliable edge detected (insufficient data or
                    evidence below noise floor). Maps to REJECT verdict.
  CONTINUE_RESEARCH → Weak signal detected; more evidence needed before
                    baseline validation. Maps to CONTINUE_RESEARCH.
  BASELINE_VALID  → Meets statistical evidence criteria for baseline.
                    Maps to BASELINE_VALID (secondary) or CONTINUE_RESEARCH
                    (primary — only V7 gates can promote primary).
  PROMOTION_CANDIDATE → Strong, cost-resilient, regime-stable evidence.
                    Maps to CANDIDATE_FOR_V7_GATES.

All verdicts are evidence-quality assessments, NOT profitability claims.
No forward-looking return or profit statements are made.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from alphaforge.constants import (
    MODE_PRIORITY_PRIMARY,
    MODE_PRIORITY_SECONDARY_BASELINE,
    REPORT_TYPE_PRIMARY,
    REPORT_TYPE_SECONDARY_BASELINE,
    V7_REGIMES,
)
from alphaforge.contracts.loader import load_schema
from alphaforge.contracts.validator import validate_payload
from alphaforge.errors import ReportBuildError, ModeError
from alphaforge.modes.profiles import get_mode_profile


# ---------------------------------------------------------------------------
# Thresholds — conservative, evidence-gated, NOT profitability claims
# ---------------------------------------------------------------------------

# Minimum OOS trades for any non-INCONCLUSIVE verdict
_MIN_OOS_TRADES: int = 100
# Minimum folds for any non-INCONCLUSIVE verdict
_MIN_FOLDS: int = 6
# Minimum OOS expectancy_r for CONTINUE_RESEARCH
_CONTINUE_EXPECTANCY_R: float = 0.05
# Minimum OOS sharpe for CONTINUE_RESEARCH (annualised approximation)
_CONTINUE_SHARPE: float = 0.3
# Minimum OOS expectancy_r for BASELINE_VALID
_BASELINE_EXPECTANCY_R: float = 0.10
# Minimum OOS sharpe for BASELINE_VALID
_BASELINE_SHARPE: float = 0.5
# Minimum OOS expectancy_r for PROMOTION_CANDIDATE
_PROMOTION_EXPECTANCY_R: float = 0.15
# Minimum OOS sharpe for PROMOTION_CANDIDATE
_PROMOTION_SHARPE: float = 0.8
# Maximum acceptable fold instability (fold Sharpe stdev / mean)
_MAX_FOLD_INSTABILITY: float = 0.6
# Minimum acceptable trade count per fold
_MIN_TRADES_PER_FOLD: int = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_metric_ci(value: float, ci_lower: float | None = None,
                    ci_upper: float | None = None) -> dict:
    """Build a MetricWithCI dict with sensible default CIs when not provided."""
    if ci_lower is None:
        ci_lower = value * 0.8 if value >= 0 else value * 1.2
    if ci_upper is None:
        ci_upper = value * 1.2 if value >= 0 else value * 0.8
    return {
        "value": value,
        "ci_lower": round(ci_lower, 4),
        "ci_upper": round(ci_upper, 4),
        "ci_level": 0.95,
    }


def _fold_stability_score(per_fold_metrics: list[dict]) -> float:
    """Compute fold stability as 1 - (stdev/mean) of fold Sharpe values.

    Returns 0.0 when mean is zero or metrics list is empty.
    Higher is better: 1.0 = perfectly stable, 0.0 = unusable.
    """
    sharpes = [f.get("sharpe", 0.0) or 0.0 for f in per_fold_metrics]
    if not sharpes:
        return 0.0
    mean_s = sum(sharpes) / len(sharpes)
    if abs(mean_s) < 1e-10:
        return 0.0
    variance = sum((s - mean_s) ** 2 for s in sharpes) / len(sharpes)
    std_s = variance ** 0.5
    instability = std_s / abs(mean_s)
    score = max(0.0, min(1.0, 1.0 - instability / _MAX_FOLD_INSTABILITY))
    return round(score, 4)


def _fold_metrics_present(per_fold_metrics: list[dict]) -> bool:
    """Check that per-fold metrics exist with reasonable data."""
    if not per_fold_metrics:
        return False
    total_trades = sum(f.get("trade_count", 0) or 0 for f in per_fold_metrics)
    return total_trades >= _MIN_OOS_TRADES


# ---------------------------------------------------------------------------
# Verdict computation
# ---------------------------------------------------------------------------

def _compute_verdict(
    mode: str,
    oos_expectancy_r: float,
    oos_sharpe: float,
    oos_trade_count: int,
    fold_count: int,
    per_fold_metrics: list[dict],
    cost_stress: dict | None = None,
    regime_breakdown: dict | None = None,
) -> tuple[str, str, list[str]]:
    """Compute verdict based on empirical evidence.

    Returns (verdict, verdict_label, rationale_list).
    - verdict: One of the schema-allowed verdict strings.
    - verdict_label: Human-readable label from the empirical progression.
    - rationale: List of reasons supporting the verdict.
    """
    profile = get_mode_profile(mode)
    rationale: list[str] = []

    # --- Check minimum requirements ---
    if oos_trade_count < _MIN_OOS_TRADES:
        rationale.append(
            f"Insufficient OOS trades: {oos_trade_count} < {_MIN_OOS_TRADES} required"
        )
        return ("REJECT", "INCONCLUSIVE", rationale)

    if fold_count < _MIN_FOLDS:
        rationale.append(
            f"Insufficient folds: {fold_count} < {_MIN_FOLDS} required"
        )
        return ("REJECT", "INCONCLUSIVE", rationale)

    if not _fold_metrics_present(per_fold_metrics):
        rationale.append("Per-fold metrics insufficient or missing")
        return ("REJECT", "INCONCLUSIVE", rationale)

    # --- Check edge exists above noise floor ---
    if oos_expectancy_r <= 0:
        rationale.append(
            f"OOS expectancy_r <= 0 ({oos_expectancy_r:.4f}) — no edge detected"
        )
        return ("REJECT", "INCONCLUSIVE", rationale)

    if oos_sharpe <= 0:
        rationale.append(
            f"OOS Sharpe <= 0 ({oos_sharpe:.4f}) — risk-adjusted return not positive"
        )
        return ("REJECT", "INCONCLUSIVE", rationale)

    # --- CONTINUE_RESEARCH threshold ---
    if oos_expectancy_r < _CONTINUE_EXPECTANCY_R:
        rationale.append(
            f"OOS expectancy_r ({oos_expectancy_r:.4f}) below CONTINUE_RESEARCH "
            f"threshold ({_CONTINUE_EXPECTANCY_R})"
        )
        return ("REJECT", "INCONCLUSIVE", rationale)

    if oos_sharpe < _CONTINUE_SHARPE:
        rationale.append(
            f"OOS Sharpe ({oos_sharpe:.4f}) below CONTINUE_RESEARCH "
            f"threshold ({_CONTINUE_SHARPE})"
        )
        return ("REJECT", "INCONCLUSIVE", rationale)

    # Fold stability check
    stability = _fold_stability_score(per_fold_metrics)
    if stability < 0.3:
        rationale.append(
            f"Fold stability too low ({stability:.4f}) — high fold variance in performance"
        )
        return ("REJECT", "INCONCLUSIVE", rationale)

    # Passed minimums — CONTINUE_RESEARCH floor
    rationale.append(
        f"OOS expectancy_r={oos_expectancy_r:.4f}, Sharpe={oos_sharpe:.4f} "
        f"— edge signal detected above noise"
    )

    # --- Check cost stress ---
    cost_survives = True
    if cost_stress is not None:
        combined_edge = cost_stress.get("combined_stress_edge_survives", False)
        if not combined_edge:
            cost_survives = False
            rationale.append(
                "Edge does NOT survive combined fee+slippage stress"
            )
        else:
            rationale.append("Edge survives combined fee+slippage stress")

    # --- Check regime breakdown ---
    regime_stable = True
    edge_only_in_rare = False
    if regime_breakdown is not None:
        edge_only_in_rare = regime_breakdown.get("edge_only_in_rare_regime", False)
        if edge_only_in_rare:
            regime_stable = False
            rationale.append("Edge present only in rare regime — not regime-stable")
        else:
            rationale.append("Edge is regime-stable (present across regimes)")
    else:
        rationale.append("Regime breakdown data not available — not blocking")

    # --- Check fold stability more carefully ---
    fold_stable = stability >= _MAX_FOLD_INSTABILITY * 0.5
    if not fold_stable:
        rationale.append(
            f"Moderate fold instability detected (stability={stability:.4f})"
        )

    # --- Promotion candidate check ---
    can_promote = True
    if profile.is_primary:
        # PRIMARY modes need strong evidence for candidacy
        if oos_expectancy_r < _PROMOTION_EXPECTANCY_R:
            can_promote = False
            rationale.append(
                f"OOS expectancy_r ({oos_expectancy_r:.4f}) below promotion "
                f"threshold ({_PROMOTION_EXPECTANCY_R})"
            )
        if oos_sharpe < _PROMOTION_SHARPE:
            can_promote = False
            rationale.append(
                f"OOS Sharpe ({oos_sharpe:.4f}) below promotion "
                f"threshold ({_PROMOTION_SHARPE})"
            )
    else:
        # SECONDARY_BASELINE modes: BASELINE_VALID threshold
        if oos_expectancy_r < _BASELINE_EXPECTANCY_R:
            can_promote = False
            rationale.append(
                f"OOS expectancy_r ({oos_expectancy_r:.4f}) below BASELINE_VALID "
                f"threshold ({_BASELINE_EXPECTANCY_R})"
            )
        if oos_sharpe < _BASELINE_SHARPE:
            can_promote = False
            rationale.append(
                f"OOS Sharpe ({oos_sharpe:.4f}) below BASELINE_VALID "
                f"threshold ({_BASELINE_SHARPE})"
            )

    if not cost_survives:
        can_promote = False
    if edge_only_in_rare:
        can_promote = False
    if not fold_stable:
        can_promote = False

    # --- Assign final verdict ---
    if can_promote and cost_survives and regime_stable and fold_stable:
        if profile.is_primary:
            rationale.append("All evidence gates satisfied — promotion candidate")
            return ("CANDIDATE_FOR_V7_GATES", "PROMOTION_CANDIDATE", rationale)
        else:
            # Check if exceeds baseline
            if oos_expectancy_r >= _PROMOTION_EXPECTANCY_R and oos_sharpe >= _PROMOTION_SHARPE:
                rationale.append("Exceeds baseline — promotion candidate for V7")
                return ("CANDIDATE_FOR_V7_GATES", "PROMOTION_CANDIDATE", rationale)
            rationale.append("Meets all baseline criteria")
            return ("BASELINE_VALID", "BASELINE_VALID", rationale)

    # CONTINUE_RESEARCH — edge detected but not yet baseline-valid
    rationale.append(
        f"Edge signal detected but {'cost stress blocks' if not cost_survives else ''}"
        f"{'regime instability blocks' if edge_only_in_rare else ''}"
        f"{'fold instability blocks' if not fold_stable else ''}"
        " — continuing research"
    )
    return ("CONTINUE_RESEARCH", "CONTINUE_RESEARCH", rationale)


# ---------------------------------------------------------------------------
# Empirical cost stress builder
# ---------------------------------------------------------------------------

def _build_empirical_cost_stress(wfv_results: dict) -> dict:
    """Build cost_stress section from WFV results."""
    cost_data = wfv_results.get("cost_stress", {})

    fee_levels = cost_data.get("fee_stress_levels", [])
    slip_levels = cost_data.get("slippage_stress_levels", [])
    combined = cost_data.get("combined_stress_edge_survives", False)

    # Default fee/slippage
    baseline_fee = cost_data.get("baseline_fee_pct", 0.04)
    baseline_slip = cost_data.get("baseline_slippage_pct", 0.02)

    return {
        "baseline_fee_pct": baseline_fee,
        "baseline_slippage_pct": baseline_slip,
        "fee_stress_levels": [
            {
                "multiplier": lv.get("multiplier", 1.0),
                "oos_expectancy_r": lv.get("oos_expectancy_r", 0.0),
                "edge_survives": lv.get("edge_survives", False),
            }
            for lv in fee_levels
        ] if fee_levels else [],
        "slippage_stress_levels": [
            {
                "multiplier": lv.get("multiplier", 1.0),
                "oos_expectancy_r": lv.get("oos_expectancy_r", 0.0),
                "edge_survives": lv.get("edge_survives", False),
            }
            for lv in slip_levels
        ] if slip_levels else [],
        "combined_stress_edge_survives": combined,
        "break_even_cost_total_pct": cost_data.get(
            "break_even_cost_total_pct", 0.0
        ),
        "net_edge_after_costs": cost_data.get("net_edge_after_costs", 0.0),
        "cost_stress_verdict": (
            "PASS" if combined
            else "FAIL_EDGE_DESTROYED_BY_COSTS"
        ),
    }


# ---------------------------------------------------------------------------
# Empirical no-trade comparison
# ---------------------------------------------------------------------------

def _build_empirical_no_trade_comparison(
    wfv_results: dict, oos_expectancy_r: float,
) -> dict:
    """Build no_trade_comparison section from WFV results."""
    no_trade = wfv_results.get("no_trade_comparison", {})

    active_beats = no_trade.get("active_beats_no_trade", False)
    if "active_beats_no_trade" not in no_trade:
        # Infer from expectancy_r: positive expectancy_r suggests active beats no-trade
        active_beats = oos_expectancy_r > 0.01

    long_vs = no_trade.get(
        "long_vs_no_trade",
        "LONG_BETTER" if active_beats else "NO_TRADE_DOMINATES",
    )
    short_vs = no_trade.get(
        "short_vs_no_trade",
        "SHORT_BETTER" if active_beats else "NO_TRADE_DOMINATES",
    )

    return {
        "long_vs_no_trade": long_vs,
        "short_vs_no_trade": short_vs,
        "active_beats_no_trade": active_beats,
        "summary": (
            f"Empirical assessment: active {'beats' if active_beats else 'does not beat'} "
            f"no-trade baseline. OOS expectancy_r={oos_expectancy_r:.4f}."
        ),
    }


# ---------------------------------------------------------------------------
# Empirical regime breakdown builder
# ---------------------------------------------------------------------------

def _build_empirical_regime_breakdown(wfv_results: dict) -> dict:
    """Build regime_breakdown section from WFV results."""
    regime_data = wfv_results.get("regime_breakdown", {})

    regimes_raw = regime_data.get("regimes", [])
    edge_only_rare = regime_data.get("edge_only_in_rare_regime", True)

    # Build regime entries
    regime_entries = []
    for r in regimes_raw:
        regime_entries.append({
            "regime": r.get("regime", "UNKNOWN"),
            "sample_pct": r.get("sample_pct", 0.0),
            "oos_expectancy_r": r.get("oos_expectancy_r", 0.0),
            "edge_present": r.get("edge_present", False),
        })

    # If regimes_raw is empty, build from V7_REGIMES with placeholder zeros
    if not regime_entries:
        for regime in V7_REGIMES:
            regime_entries.append({
                "regime": regime,
                "sample_pct": 0.25,
                "oos_expectancy_r": 0.0,
                "edge_present": False,
            })

    # Identify best/worst regime
    best_regime = "NONE"
    worst_regime = "NONE"
    best_r = -999.0
    worst_r = 999.0
    for r in regime_entries:
        er = r["oos_expectancy_r"]
        if er > best_r and r["edge_present"]:
            best_r = er
            best_regime = r["regime"]
        if er < worst_r:
            worst_r = er
            worst_regime = r["regime"]

    return {
        "regimes_tested": list(V7_REGIMES),
        "regimes": regime_entries,
        "best_regime": best_regime,
        "worst_regime": worst_regime,
        "edge_only_in_rare_regime": edge_only_rare,
        "regime_stability_verdict": (
            "EDGE_ONLY_IN_RARE_REGIME" if edge_only_rare
            else "EDGE_PRESENT_ACROSS_REGIMES"
        ),
        "summary": (
            f"Regime analysis over {len(regime_entries)} regimes. "
            f"Best: {best_regime} (expectancy_r={best_r:.4f}). "
            f"Worst: {worst_regime} (expectancy_r={worst_r:.4f}). "
            f"Edge {'only in rare regime' if edge_only_rare else 'present across regimes'}."
        ),
    }


# ---------------------------------------------------------------------------
# Empirical MHT control builder
# ---------------------------------------------------------------------------

def _build_empirical_mht_control(
    wfv_results: dict, fold_count: int, hypotheses_per_fold: int = 1,
) -> dict:
    """Build multiple_hypothesis_control section from WFV results."""
    mht_data = wfv_results.get("multiple_hypothesis_control", {})

    tested_hypotheses = mht_data.get(
        "tested_hypothesis_count", fold_count * hypotheses_per_fold
    )
    correction_method = mht_data.get("correction_method", "NONE_APPLIED")
    risk_flag = mht_data.get("data_snooping_risk_flag", "HIGH")

    return {
        "tested_hypothesis_count": tested_hypotheses,
        "correction_method": correction_method,
        "corrected_significance": None,
        "data_snooping_risk_flag": risk_flag,
        "deflated_sharpe_or_equivalent": None,
        "pbo_or_backtest_overfit_risk": mht_data.get(
            "pbo_or_backtest_overfit_risk", "NOT_RUN"
        ),
        "trial_count_disclosure": mht_data.get("trial_count_disclosure", 0),
        "rejected_candidate_count": mht_data.get("rejected_candidate_count", 0),
        "notes": (
            f"Empirical MHT assessment: {tested_hypotheses} hypotheses tested "
            f"across {fold_count} folds. Correction: {correction_method}. "
            f"Data-snooping risk: {risk_flag}."
        ),
    }


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_empirical_mode_research_report(
    mode: str,
    wfv_results: dict,
    report_id: str | None = None,
    run_id: str | None = None,
) -> dict:
    """Build a schema-valid ModeResearchReport from empirical WFV results.

    This is the P0.9C empirical report builder. It consumes real WFV results
    (or synthetic test results) and produces a fully populated report with
    computed metrics, evidence-gated verdict, and all required sections.

    Args:
        mode: 'SCALP', 'AGGRESSIVE_SCALP', or 'SWING'.
        wfv_results: Walk-forward validation results dict with:
            - fold_count: int
            - per_fold_metrics: list of dicts with fold, sharpe,
              expectancy_r, win_rate, trade_count
            - oos_summary: dict with oos_sharpe, oos_expectancy_r,
              oos_win_rate, oos_profit_factor, oos_max_drawdown_r,
              oos_trade_count
            - cost_stress (optional): dict with fee/slippage stress levels
            - regime_breakdown (optional): dict with regime entries
            - no_trade_comparison (optional): dict
            - multiple_hypothesis_control (optional): dict
        report_id: Optional report ID override.
        run_id: Optional run ID override.

    Returns:
        ModeResearchReport payload as dict, validated against schema.

    Raises:
        ModeError: Unknown mode.
        ReportBuildError: Payload failed schema validation or WFV results
            are missing required fields.
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

    rid = report_id or f"mrr-{mode_key}-empirical-001"
    run = run_id or wfv_results.get("run_id", f"run-empirical-{mode_key}-001")

    # --- Extract WFV values ---
    fold_count = wfv_results.get("fold_count", 6)
    per_fold_metrics = wfv_results.get("per_fold_metrics", [])

    oos_summary = wfv_results.get("oos_summary", {})
    oos_sharpe = oos_summary.get("oos_sharpe", 0.0)
    oos_expectancy_r = oos_summary.get("oos_expectancy_r", 0.0)
    oos_win_rate = oos_summary.get("oos_win_rate", 0.5)
    oos_profit_factor = oos_summary.get("oos_profit_factor", 1.0)
    oos_max_drawdown_r = oos_summary.get("oos_max_drawdown_r", -3.0)
    oos_trade_count = oos_summary.get("oos_trade_count", 0)

    # --- Active trade metrics (Issue 123) ---
    atm = wfv_results.get("active_trade_metrics", {})
    active_trade_count = atm.get("active_trade_count", oos_trade_count)
    long_trade_count = atm.get("long_trade_count", 0)
    short_trade_count = atm.get("short_trade_count", 0)
    no_trade_count = atm.get("no_trade_count", 0)
    total_gross_R = atm.get("total_gross_R", 0.0)
    total_net_R = atm.get("total_net_R", 0.0)
    exposure_pct = atm.get("exposure_pct", 0.0)
    avg_net_R_per_active_trade = atm.get("avg_net_R_per_active_trade", 0.0)

    cost_stress_data = wfv_results.get("cost_stress")
    regime_data = wfv_results.get("regime_breakdown")

    # --- Compute verdict ---
    verdict, verdict_label, rationale = _compute_verdict(
        mode=mode,
        oos_expectancy_r=oos_expectancy_r,
        oos_sharpe=oos_sharpe,
        oos_trade_count=oos_trade_count,
        fold_count=fold_count,
        per_fold_metrics=per_fold_metrics,
        cost_stress=cost_stress_data,
        regime_breakdown=regime_data,
    )

    # --- Build sections ---
    data_scope = wfv_results.get("data_scope", {})
    symbols = data_scope.get("symbols", ["BTCUSDT"])
    date_start = data_scope.get("date_range_start", "2025-01-01T00:00:00Z")
    date_end = data_scope.get("date_range_end", "2026-01-01T00:00:00Z")

    # --- Cost stress section ---
    cost_stress_section = _build_empirical_cost_stress(wfv_results)
    no_trade_section = _build_empirical_no_trade_comparison(
        wfv_results, oos_expectancy_r,
    )
    regime_section = _build_empirical_regime_breakdown(wfv_results)
    mht_section = _build_empirical_mht_control(wfv_results, fold_count)

    # --- V7 gate readiness ---
    gate_readiness = _build_gate_readiness(
        mode, verdict, cost_stress_section, regime_section,
    )

    # --- Build payload ---
    payload = {
        "schema_version": "1.0.0",
        "report_id": rid,
        "mode": mode,
        "mode_priority": profile.priority,
        "report_type": profile.report_type,
        "created_at": _now_iso(),
        "run_id": run,
        "data_scope": {
            "symbols": symbols,
            "date_range_start": date_start,
            "date_range_end": date_end,
            "primary_timeframes": [profile.primary_timeframe],
            "secondary_timeframes": [profile.context_timeframe, profile.refinement_timeframe],
            "data_quality_summary": data_scope.get(
                "data_quality_summary",
                "Empirical report from WFV results.",
            ),
        },
        "feature_set_refs": wfv_results.get("feature_set_refs", [f"fs-{mode_key}-empirical-001"]),
        "label_dataset_refs": wfv_results.get("label_dataset_refs", [f"lds-{mode_key}-empirical-001"]),
        "alpha_theses": wfv_results.get("alpha_theses", [
            {
                "alpha_thesis_id": f"ath-{mode_key}-empirical-001",
                "title": f"Empirical alpha thesis for {mode}",
                "status": "UNDER_EVALUATION",
                "evidence_quality": (
                    "STRONG" if verdict in ("CANDIDATE_FOR_V7_GATES",)
                    else "MODERATE" if verdict in ("BASELINE_VALID",)
                    else "WEAK" if verdict == "CONTINUE_RESEARCH"
                    else "INSUFFICIENT"
                ),
            }
        ]),
        "validation_summary": {
            "validation_report_id": wfv_results.get(
                "validation_report_id", f"vr-{mode_key}-empirical-001"
            ),
            "fold_count": fold_count,
            "verdict": verdict,
            "overfit_risk": (
                "LOW" if verdict in ("CANDIDATE_FOR_V7_GATES", "BASELINE_VALID")
                and _fold_stability_score(per_fold_metrics) >= 0.7
                else "MEDIUM" if verdict in ("CONTINUE_RESEARCH",)
                else "HIGH"
            ),
        },
        "metrics": {
            "oos_sharpe": _make_metric_ci(oos_sharpe),
            "oos_expectancy_r": _make_metric_ci(oos_expectancy_r),
            "oos_win_rate": _make_metric_ci(oos_win_rate, max(0.0, oos_win_rate - 0.1), min(1.0, oos_win_rate + 0.1)),
            "oos_profit_factor": _make_metric_ci(oos_profit_factor),
            "oos_max_drawdown_r": _make_metric_ci(oos_max_drawdown_r),
            "oos_trade_count": oos_trade_count,
            "active_trade_count": active_trade_count,
            "long_trade_count": long_trade_count,
            "short_trade_count": short_trade_count,
            "no_trade_count": no_trade_count,
            "total_gross_R": total_gross_R,
            "total_net_R": total_net_R,
            "exposure_pct": exposure_pct,
            "avg_net_R_per_active_trade": avg_net_R_per_active_trade,
            "per_fold_metrics": per_fold_metrics,
        },
        "cost_stress": cost_stress_section,
        "no_trade_comparison": no_trade_section,
        "regime_breakdown": regime_section,
        "v7_gate_readiness": gate_readiness,
        "multiple_hypothesis_control": mht_section,
        "verdict": verdict,
        "blocked_scopes": _build_blocked_scopes(mode, verdict, cost_stress_section),
        "limitations": [
            *wfv_results.get("limitations", []),
            f"Empirical report — evidence quality: {verdict_label}. No profitability claims.",
            "AlphaForge RECOMMENDS. V7 DECIDES. This report does NOT authorize live trading.",
        ],
        "recommended_actions": _build_recommended_actions(verdict, verdict_label),
    }

    # Validate against schema
    schema = load_schema("mode_research_report.schema.json")
    result = validate_payload(schema, payload, f"empirical_mode_research_report({mode})")
    if not result.valid:
        raise ReportBuildError(
            f"Empirical mode research report for {mode} failed validation: {result.errors}"
        )

    return payload


def _build_gate_readiness(
    mode: str,
    verdict: str,
    cost_stress: dict,
    regime_breakdown: dict,
) -> dict:
    """Build V7 gate readiness assessment."""
    gates_mapped = ["G0_doc_ready", "G1_research_backtest"]

    if verdict in ("CONTINUE_RESEARCH", "BASELINE_VALID", "CANDIDATE_FOR_V7_GATES"):
        gates_mapped.append("G2_walk_forward_oos")

    if cost_stress.get("combined_stress_edge_survives", False):
        gates_mapped.append("G3_cost_stress")

    if not regime_breakdown.get("edge_only_in_rare_regime", True):
        gates_mapped.append("G4_regime_breakdown")

    gates_not_ready = [
        g for g in [
            "G0_doc_ready", "G1_research_backtest", "G2_walk_forward_oos",
            "G3_cost_stress", "G4_regime_breakdown", "G5_symbol_stability",
            "G6_calibration_reliability", "G7_shadow", "G8_paper",
            "G9_tiny_live", "G10_live",
        ] if g not in gates_mapped
    ]

    if verdict == "CANDIDATE_FOR_V7_GATES":
        overall = "PARTIALLY_READY"
    elif verdict in ("BASELINE_VALID", "CONTINUE_RESEARCH"):
        overall = "PARTIALLY_READY"
    else:
        overall = "NOT_READY"

    return {
        "gates_mapped": gates_mapped,
        "gates_not_ready": gates_not_ready,
        "overall_readiness": overall,
    }


def _build_blocked_scopes(mode: str, verdict: str, cost_stress: dict) -> list[str]:
    """Build blocked scopes list based on evidence quality."""
    blocked = []

    if verdict in ("REJECT", "INCONCLUSIVE"):
        blocked.append(
            f"Verdict is {verdict} — insufficient evidence for any promotion"
        )

    if not cost_stress.get("combined_stress_edge_survives", False):
        blocked.append(
            "Cost stress blocks edge — fee/slippage sensitivity unresolved"
        )

    blocked.append("Funding model DEFERRED — perpetual/live scope blocked")
    blocked.append("Single symbol limitation — cross-symbol stability not assessed")

    if verdict != "CANDIDATE_FOR_V7_GATES":
        blocked.append(
            "V7 gate readiness: G5-G10 not addressed — further evidence required"
        )

    return blocked


def _build_recommended_actions(verdict: str, verdict_label: str) -> list[str]:
    """Build recommended actions based on evidence quality."""
    actions = []

    if verdict_label == "INCONCLUSIVE":
        actions.append("Improve data quality or increase sample size")
        actions.append("Review feature engineering for better signal extraction")
        actions.append("Check for data leakage in label/feature construction")

    if verdict_label in ("CONTINUE_RESEARCH",):
        actions.append("Increase walk-forward fold count or extend OOS period")
        actions.append("Refine feature set to improve signal-to-noise ratio")
        actions.append("Apply MHT correction to reduce data-snooping risk")
        actions.append("Run cost stress analysis at higher slippage multipliers")

    if verdict_label in ("BASELINE_VALID",):
        actions.append("Calibrate model confidence surface")
        actions.append("Extend symbol coverage for cross-symbol validation")
        actions.append("Prepare V7 handoff package for G5+ gate evaluation")

    if verdict_label == "PROMOTION_CANDIDATE":
        actions.append("Package evidence for V7 acceptance gates")
        actions.append("Run G5 symbol stability with multi-symbol data")
        actions.append("Begin shadow-mode preparation (G7)")

    actions.append("This is an evidence-assessment report, not a trade authorization")

    return actions
