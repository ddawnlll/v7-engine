"""Minimal deterministic report builder helpers.

All reports are schema-valid placeholders marked as non-profit evidence.
No real training, no fake OOS, no fake model artifact.
"""

from datetime import datetime, timezone
from typing import Dict, Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_minimal_validation_report(
    mode: str,
    validation_report_id: str = "vr-minimal-001",
) -> Dict[str, Any]:
    """Build a minimal schema-valid validation report. All values are placeholders."""
    folds = []
    for i in range(1, 7):
        folds.append({
            "fold_number": i,
            "train_start": "2024-01-01T00:00:00Z",
            "train_end": "2024-07-01T00:00:00Z",
            "test_start": "2024-07-01T00:00:00Z",
            "test_end": "2024-08-01T00:00:00Z",
            "train_sharpe": 1.0,
            "test_sharpe": 0.5,
            "test_expectancy_r": 0.15,
            "test_win_rate": 0.52,
            "test_trade_count": 100,
        })
    return {
        "schema_version": "1.0.0",
        "validation_report_id": validation_report_id,
        "mode": mode,
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
        },
        "symbol_stability": {
            "symbols_tested": ["BTCUSDT"], "symbol_count": 1,
            "max_single_symbol_concentration": 1.0, "max_cluster_concentration": 1.0,
            "single_symbol_limitation": True,
            "cross_symbol_metric_variance": "Single symbol — no cross-symbol assessment",
        },
        "regime_breakdown": {
            "regimes": [
                {"regime": "TREND_UP", "sample_pct": 0.30, "oos_expectancy_r": 0.20, "oos_sharpe": 0.6, "edge_present": True},
                {"regime": "TREND_DOWN", "sample_pct": 0.25, "oos_expectancy_r": 0.10, "oos_sharpe": 0.3, "edge_present": True},
                {"regime": "RANGE", "sample_pct": 0.30, "oos_expectancy_r": -0.05, "oos_sharpe": -0.1, "edge_present": False},
                {"regime": "TRANSITION", "sample_pct": 0.15, "oos_expectancy_r": 0.05, "oos_sharpe": 0.1, "edge_present": False},
            ],
            "edge_only_in_rare_regime": False, "rare_regime_untradeable": False,
        },
        "cost_stress": {
            "baseline_fee_pct": 0.04, "baseline_slippage_pct": 0.02,
            "spread_or_proxy": "taker_fee_0.04pct",
            "funding_or_deferred_block": "DEFERRED — perpetual/live claims blocked",
            "fee_stress_edge_survives": True, "slippage_stress_edge_survives": True,
            "combined_stress_edge_survives": True, "break_even_cost_total_pct": 0.15,
            "cost_edge_destroyed": False,
        },
        "no_trade_comparison": {
            "long_better_than_no_trade": True, "short_better_than_no_trade": False,
            "active_beats_no_trade": True, "summary": "Placeholder — no real evidence",
        },
        "overfit_risk_flags": {
            "train_oos_gap": "MEDIUM", "fold_instability": "MEDIUM",
            "feature_to_sample_ratio": "MEDIUM", "top_feature_dominance": "MEDIUM",
            "calibration_degradation": "MEDIUM", "purge_violation_detected": False,
            "overfit_risk_overall": "MEDIUM",
        },
        "multiple_hypothesis_control": {
            "mht_status": "NOT_RUN",
            "tested_hypothesis_count": 0, "tested_feature_count": 0,
            "tested_thesis_count": 0, "correction_method": "NONE",
            "false_discovery_control": "NONE",
            "deflated_sharpe_or_pbo_assessment": "NOT_RUN",
            "trial_count_disclosure": 0, "rejected_candidate_count": 0,
            "mht_block_reason": "P0.9A scaffold — no real research has been run.",
        },
        "verdict": "BLOCKED_FOR_MHT",
        "limitations": [
            "Deterministic placeholder — no real validation performed.",
            "MHT not applied — all edge/profitability claims blocked.",
            "Funding DEFERRED — perpetual/live claims blocked.",
        ],
        "created_at": _utc_now(),
    }


def build_minimal_mode_research_report(
    mode: str, report_id: str = "mrr-minimal-001",
) -> Dict[str, Any]:
    """Build a minimal mode research report. No real evidence."""
    priority = "SECONDARY_BASELINE" if mode == "SWING" else "PRIMARY"
    rtype = "secondary_baseline_report" if mode == "SWING" else "primary_research_report"
    tf = {"SWING": "4h", "SCALP": "1h", "AGGRESSIVE_SCALP": "15m"}[mode]
    ctx = {"SWING": "1d", "SCALP": "4h", "AGGRESSIVE_SCALP": "1h"}[mode]
    return {
        "schema_version": "1.0.0", "report_id": report_id,
        "mode": mode, "mode_priority": priority, "report_type": rtype,
        "created_at": _utc_now(), "run_id": "run-placeholder-001",
        "data_scope": {
            "symbols": ["BTCUSDT"],
            "date_range_start": "2024-01-01T00:00:00Z",
            "date_range_end": "2025-01-01T00:00:00Z",
            "primary_timeframes": [tf], "secondary_timeframes": [ctx],
            "data_quality_summary": "Placeholder — no real data",
        },
        "feature_set_refs": ["fs-placeholder-001"],
        "label_dataset_refs": ["lds-placeholder-001"],
        "alpha_theses": [{
            "alpha_thesis_id": "at-placeholder-001",
            "title": "Placeholder thesis", "status": "HYPOTHESIS_ONLY",
            "evidence_quality": "INSUFFICIENT",
        }],
        "validation_summary": {
            "validation_report_id": f"vr-{mode.lower()}-001",
            "fold_count": 6, "verdict": "BLOCKED_FOR_MHT", "overfit_risk": "MEDIUM",
        },
        "metrics": {
            "oos_sharpe": {"value": 0.0, "ci_lower": -0.5, "ci_upper": 0.5, "ci_level": 0.95},
            "oos_expectancy_r": {"value": 0.0, "ci_lower": -0.1, "ci_upper": 0.1, "ci_level": 0.95},
            "oos_win_rate": {"value": 0.5, "ci_lower": 0.45, "ci_upper": 0.55, "ci_level": 0.95},
            "oos_profit_factor": {"value": 1.0, "ci_lower": 0.8, "ci_upper": 1.2, "ci_level": 0.95},
            "oos_max_drawdown_r": {"value": -1.0, "ci_lower": -3.0, "ci_upper": -0.5, "ci_level": 0.95},
            "oos_trade_count": 0, "per_fold_metrics": [],
        },
        "cost_stress": {
            "baseline_fee_pct": 0.04, "baseline_slippage_pct": 0.02,
            "fee_stress_levels": [], "slippage_stress_levels": [],
            "combined_stress_edge_survives": False, "break_even_cost_total_pct": 0.0,
        },
        "no_trade_comparison": {
            "long_vs_no_trade": "NOT_EVALUATED", "short_vs_no_trade": "NOT_EVALUATED",
            "active_beats_no_trade": False, "summary": "Placeholder",
        },
        "regime_breakdown": {
            "regimes": [], "edge_only_in_rare_regime": False,
            "summary": "No regime breakdown — placeholder",
        },
        "multiple_hypothesis_control": {
            "mht_status": "NOT_RUN",
            "tested_hypothesis_count": 0, "tested_feature_count": 0,
            "tested_thesis_count": 0, "correction_method": "NONE",
            "false_discovery_control": "NONE",
            "deflated_sharpe_or_pbo_assessment": "NOT_RUN",
            "trial_count_disclosure": 0, "rejected_candidate_count": 0,
            "mht_block_reason": "P0.9A scaffold — no research has been run.",
        },
        "verdict": "BLOCKED_FOR_MHT",
        "blocked_scopes": ["No real profitability evidence exists yet."],
        "limitations": ["P0.9A scaffold report — no real research."],
        "recommended_actions": ["Do not interpret as profitability evidence."],
    }


def build_minimal_handoff_package(
    mode: str = "SWING",
    handoff_package_id: str = "v7hp-minimal-001",
) -> Dict[str, Any]:
    """Build a minimal V7 handoff package with canonical G0-G10 gates."""
    gate_placeholder = "P0.9A scaffold — no real evidence"
    return {
        "schema_version": "1.0.0",
        "handoff_package_id": handoff_package_id,
        "mode": mode,
        "alpha_candidate_id": "ac-placeholder-001",
        "mode_research_report_id": f"mrr-{mode.lower()}-001",
        "validation_report_id": f"vr-{mode.lower()}-001",
        "model_artifact_id": "ma-placeholder-001",
        "calibration_candidate_id": "cc-placeholder-001",
        "v7_gate_mapping": {
            "G0_doc_ready": gate_placeholder,
            "G1_research_backtest": gate_placeholder,
            "G2_walk_forward_oos": gate_placeholder,
            "G3_cost_stress": gate_placeholder,
            "G4_regime_breakdown": gate_placeholder,
            "G5_symbol_stability": gate_placeholder,
            "G6_calibration_reliability": gate_placeholder,
            "G7_shadow": gate_placeholder,
            "G8_paper": gate_placeholder,
            "G9_tiny_live": gate_placeholder,
            "G10_live": "P0.9A scaffold — not ready",
        },
        "recommended_status": "REVIEW_REQUIRED",
        "blocked_scopes": [
            "No real profitability evidence exists yet.",
            "Funding DEFERRED — perpetual/live claims blocked.",
        ],
        "limitations": [
            "Deterministic placeholder — no real evidence.",
            "P0.9A increases implementation readiness, not economic proof.",
        ],
        "lineage": {
            "data_refs": ["placeholder-btcusdt"],
            "feature_set_id": "fs-placeholder-001",
            "label_dataset_id": "lds-placeholder-001",
            "simulation_profile_id": f"{mode.lower()}_profile-1.0.0",
            "simulation_run_ids": ["sim-placeholder-001"],
            "training_run_id": "run-placeholder-001",
            "git_commit": "0000000000000000000000000000000000000000",
            "lineage_verified": False,
        },
        "created_at": _utc_now(),
        "rejection_rules_applied": [
            "P0.9A scaffold — automatically REVIEW_REQUIRED.",
        ],
    }


# Canonical V7 gate names
CANONICAL_V7_GATES = [
    "G0_doc_ready", "G1_research_backtest", "G2_walk_forward_oos",
    "G3_cost_stress", "G4_regime_breakdown", "G5_symbol_stability",
    "G6_calibration_reliability", "G7_shadow", "G8_paper",
    "G9_tiny_live", "G10_live",
]

# Old gate names that must never appear in handoff outputs
FORBIDDEN_GATE_NAMES = [
    "G3_model_sanity", "G5_cost_resilience", "G8_calibration",
    "G9_no_trade_baseline", "G10_paper_shadow",
]
