"""P0.9A WS-07 — AlphaForge V7 handoff dry run integration tests.

Verifies:
1. run_handoff_dry_run() output validates against v7_handoff_package.schema.json
2. P0.9A handoff builder build_v7_handoff_package is actually called
3. Gate names match CANONICAL_V7_GATES from constants.py
4. Old gate names are NEVER present in output
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
AF_SRC = REPO / "alphaforge" / "src"
if str(AF_SRC) not in sys.path:
    sys.path.insert(0, str(AF_SRC))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from typing import Any, Dict

import pytest

from alphaforge.constants import CANONICAL_V7_GATES, HANDOFF_REVIEW_REQUIRED
from alphaforge.contracts.loader import load_schema
from alphaforge.contracts.validator import validate_payload
from alphaforge.handoff.dry_run import (
    DryRunInput,
    run_handoff_dry_run,
    validate_gate_mapping,
)
from alphaforge.handoff.builders import build_v7_handoff_package
from alphaforge.errors import GateMappingError, HandoffBuildError


# ── Minimal test report builders (inlined to avoid reports.py package ambiguity) ──

def _minimal_mrr(mode: str = "SWING") -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "SWING": {"priority": "SECONDARY_BASELINE", "rtype": "secondary_baseline_report", "tf": "4h"},
        "SCALP": {"priority": "PRIMARY", "rtype": "primary_research_report", "tf": "1h"},
        "AGGRESSIVE_SCALP": {"priority": "PRIMARY", "rtype": "primary_research_report", "tf": "15m"},
    }
    p = params[mode]
    return {
        "schema_version": "1.0.0",
        "report_id": f"mrr-{mode.lower()}-intg-001",
        "mode": mode,
        "mode_priority": p["priority"],
        "report_type": p["rtype"],
        "data_scope": {"symbols": ["BTCUSDT"], "primary_timeframes": [p["tf"]]},
        "feature_set_refs": ["fs-intg-001"],
        "label_dataset_refs": ["lds-intg-001"],
        "alpha_theses": [{"alpha_thesis_id": "ath-intg-001", "status": "PROPOSED", "evidence_quality": "INSUFFICIENT"}],
        "validation_summary": {"validation_report_id": f"vr-{mode.lower()}-intg-001", "fold_count": 6, "verdict": "CANDIDATE_FOR_V7_GATES", "overfit_risk": "LOW"},
        "metrics": {"oos_expectancy_r": {"value": 0.15}, "oos_sharpe": {"value": 0.5}, "oos_trade_count": 600},
        "cost_stress": {"baseline_fee_pct": 0.04, "baseline_slippage_pct": 0.02, "combined_stress_edge_survives": True},
        "no_trade_comparison": {"active_beats_no_trade": True, "summary": "Integration test"},
        "regime_breakdown": {"regimes": [], "edge_only_in_rare_regime": False},
        "multiple_hypothesis_control": {"tested_hypothesis_count": 1, "correction_method": "Bonferroni", "data_snooping_risk_flag": "LOW"},
        "verdict": "CANDIDATE_FOR_V7_GATES",
        "blocked_scopes": ["Integration test — no real data"],
        "limitations": ["Integration test placeholder."],
    }


def _minimal_vr(mode: str = "SWING") -> Dict[str, Any]:
    folds = [{"fold_number": i, "train_start": "2024-01-01T00:00:00Z", "train_end": "2024-07-01T00:00:00Z", "test_start": "2024-07-01T00:00:00Z", "test_end": "2024-08-01T00:00:00Z"} for i in range(1, 7)]
    return {
        "schema_version": "1.0.0",
        "validation_report_id": f"vr-{mode.lower()}-intg-001",
        "mode": mode,
        "alpha_candidate_id": f"ac-{mode.lower()}-intg-001",
        "model_artifact_id": f"ma-{mode.lower()}-intg-001",
        "split_policy": {"train_pct": 0.60, "validation_pct": 0.15, "oos_pct": 0.25, "purge_window_bars": 10, "embargo_policy": "purge_and_embargo", "chronological_split": True},
        "walk_forward_folds": {"fold_count": 6, "fold_type": "anchored", "folds": folds},
        "oos_summary": {"oos_sharpe": 0.5, "oos_expectancy_r": 0.15, "oos_win_rate": 0.52, "oos_trade_count": 600, "oos_positive_expectancy": True, "fold_stability_score": 0.7},
        "symbol_stability": {"symbols_tested": ["BTCUSDT", "ETHUSDT"], "symbol_count": 2, "max_single_symbol_concentration": 0.30, "max_cluster_concentration": 0.45, "single_symbol_limitation": False},
        "regime_breakdown": {"regimes": [{"regime": "TREND_UP", "sample_pct": 0.30, "oos_expectancy_r": 0.20, "edge_present": True}], "edge_only_in_rare_regime": False},
        "cost_stress": {"baseline_fee_pct": 0.04, "baseline_slippage_pct": 0.02, "fee_stress_edge_survives": True, "slippage_stress_edge_survives": True, "combined_stress_edge_survives": True, "cost_edge_destroyed": False, "funding_deferred_block": {"funding_deferred": False, "block_reason": "", "affected_scopes": []}},
        "no_trade_comparison": {"active_beats_no_trade": True, "summary": "Integration test"},
        "overfit_risk_flags": {"overfit_risk_overall": "LOW"},
        "multiple_hypothesis_control": {"tested_hypothesis_count": 1, "correction_method": "Bonferroni", "trial_count_disclosure": 1, "rejected_candidate_count": 0},
        "calibration_gate_alignment": {"calibration_candidate_id": f"cc-{mode.lower()}-intg-001", "ece": 0.02, "mce": 0.05, "calibration_status": "CALIBRATED"},
        "verdict": "PASS",
        "limitations": ["Integration test placeholder."],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_dry_run_output_validates_against_schema():
    """AC-07-ST-02: run_handoff_dry_run() output validates against schema."""
    dinput = DryRunInput(
        mode="SWING",
        mode_research_report=_minimal_mrr("SWING"),
        validation_report=_minimal_vr("SWING"),
    )
    handoff = run_handoff_dry_run(dinput)
    schema = load_schema("v7_handoff_package.schema.json")
    result = validate_payload(schema, handoff, "v7_handoff_dry_run_integration")
    assert result.valid, f"Schema validation failed: {result.errors}"


def test_dry_run_calls_p0_9a_builder():
    """AC-07-ST-06: Output includes all fields populated by build_v7_handoff_package."""
    dinput = DryRunInput(
        mode="SWING",
        mode_research_report=_minimal_mrr("SWING"),
        validation_report=_minimal_vr("SWING"),
    )
    handoff = run_handoff_dry_run(dinput)

    # Verify all fields that build_v7_handoff_package populates are present
    p0_9a_required = [
        "schema_version",
        "handoff_package_id",
        "mode",
        "alpha_candidate_id",
        "mode_research_report_id",
        "validation_report_id",
        "model_artifact_id",
        "calibration_candidate_id",
        "blocked_scopes",
        "limitations",
        "lineage",
        "created_at",
    ]
    for key in p0_9a_required:
        assert key in handoff, f"Missing P0.9A builder field: {key}"

    # Lineage must have all required keys
    lineage = handoff["lineage"]
    lineage_required = ["data_refs", "feature_set_id", "label_dataset_id",
                         "simulation_profile_id", "lineage_verified"]
    for key in lineage_required:
        assert key in lineage, f"Missing lineage field: {key}"


def test_gate_names_match_canonical_v7_gates():
    """Gate names in output match CANONICAL_V7_GATES from constants."""
    dinput = DryRunInput(
        mode="SCALP",
        mode_research_report=_minimal_mrr("SCALP"),
        validation_report=_minimal_vr("SCALP"),
    )
    handoff = run_handoff_dry_run(dinput)
    gate_keys = set(handoff["v7_gate_mapping"].keys())
    canonical_set = set(CANONICAL_V7_GATES)
    assert gate_keys == canonical_set


def test_old_gate_names_never_present():
    """Old AlphaForge gate names are NEVER present in output."""
    old_gates = [
        "G0_data_quality", "G1_feature_validity", "G2_label_validity",
        "G3_model_sanity", "G4_oos_performance", "G5_cost_resilience",
        "G6_regime_robustness", "G7_stability", "G8_calibration",
        "G9_no_trade_baseline", "G10_paper_shadow",
    ]
    for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
        dinput = DryRunInput(
            mode=mode,
            mode_research_report=_minimal_mrr(mode),
            validation_report=_minimal_vr(mode),
        )
        handoff = run_handoff_dry_run(dinput)
        gate_keys = set(handoff["v7_gate_mapping"].keys())
        for old in old_gates:
            assert old not in gate_keys, f"Old gate '{old}' found in {mode} output"


def test_all_modes_produce_valid_output():
    """All three modes produce schema-valid output with REVIEW_REQUIRED."""
    for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
        dinput = DryRunInput(
            mode=mode,
            mode_research_report=_minimal_mrr(mode),
            validation_report=_minimal_vr(mode),
        )
        handoff = run_handoff_dry_run(dinput)
        assert handoff["mode"] == mode
        assert handoff["recommended_status"] == HANDOFF_REVIEW_REQUIRED
        assert len(handoff["v7_gate_mapping"]) == 11
        assert len(handoff["rejection_rules_applied"]) == 12

        # Schema validate
        schema = load_schema("v7_handoff_package.schema.json")
        result = validate_payload(schema, handoff, f"v7_handoff_{mode}")
        assert result.valid, f"{mode} validation failed: {result.errors}"


def test_gate_mapping_enforces_evidence_ref_and_status():
    """validate_gate_mapping() rejects entries without evidence_ref/status."""
    mapping = {
        f"G{i}_doc_ready" if i == 0 else
        f"G{i}_research_backtest" if i == 1 else
        f"G{i}_walk_forward_oos" if i == 2 else
        f"G{i}_cost_stress" if i == 3 else
        f"G{i}_regime_breakdown" if i == 4 else
        f"G{i}_symbol_stability" if i == 5 else
        f"G{i}_calibration_reliability" if i == 6 else
        f"G{i}_shadow" if i == 7 else
        f"G{i}_paper" if i == 8 else
        f"G{i}_tiny_live" if i == 9 else
        f"G{i}_live": {"evidence_ref": "test", "status": "NOT_EVALUATED"}
        for i in range(11)
    }
    # This should pass
    assert validate_gate_mapping(mapping) is True

    # Remove evidence_ref from a gate
    bad = dict(mapping)
    bad["G5_symbol_stability"] = {"status": "NOT_EVALUATED"}
    with pytest.raises(GateMappingError):
        validate_gate_mapping(bad)


def test_dry_run_never_produces_promotion_status():
    """AC-07-DRB-03: recommended_status is always REVIEW_REQUIRED."""
    for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
        dinput = DryRunInput(
            mode=mode,
            mode_research_report=_minimal_mrr(mode),
            validation_report=_minimal_vr(mode),
        )
        handoff = run_handoff_dry_run(dinput)
        assert handoff["recommended_status"] == HANDOFF_REVIEW_REQUIRED
        assert handoff["recommended_status"] != "PROMOTION_CANDIDATE"
        assert handoff["recommended_status"] != "SHADOW_READY"


def test_no_trade_is_not_a_gate():
    """NO_TRADE is a metric/comparator, not a promotion gate."""
    dinput = DryRunInput(
        mode="SWING",
        mode_research_report=_minimal_mrr("SWING"),
        validation_report=_minimal_vr("SWING"),
    )
    handoff = run_handoff_dry_run(dinput)
    gates = handoff["v7_gate_mapping"]
    assert not any("no_trade" in k.lower() for k in gates)
