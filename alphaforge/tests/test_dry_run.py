"""AlphaForge WS-07: V7 Handoff Dry Run — comprehensive unit tests.

Covers:
- Gate mapping validation (7 tests)
- Dry run builder (9 tests)
- Promotion guard (4 tests)
- Rejection rules (12 tests)

All fixtures use skeleton/dummy IDs — no real model paths, no real data paths,
no live exchange references.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from alphaforge.handoff.dry_run import (
    DryRunInput,
    InputContractError,
    MODE_RESEARCH_REPORT_REQUIRED_FIELDS,
    PromotionGuardError,
    RejectionRulesResult,
    VALIDATION_REPORT_REQUIRED_FIELDS,
    _evaluate_rejection_rules,
    _guard_promotion_status,
    run_handoff_dry_run,
    validate_gate_mapping,
)
from alphaforge.errors import GateMappingError, HandoffBuildError
from alphaforge.constants import (
    CANONICAL_V7_GATES,
    HANDOFF_REVIEW_REQUIRED,
    HANDOFF_SHADOW_READY,
    HANDOFF_PROMOTION_CANDIDATE,
)


# ═══════════════════════════════════════════════════════════════════════════
# Shared fixtures — minimal valid reports
# ═══════════════════════════════════════════════════════════════════════════

def _minimal_mrr(mode: str = "SWING", **overrides) -> Dict[str, Any]:
    """Build a minimal ModeResearchReport dict."""
    data = {
        "schema_version": "1.0.0",
        "report_id": f"mrr-{mode.lower()}-test-001",
        "mode": mode,
        "mode_priority": "SECONDARY_BASELINE" if mode == "SWING" else "PRIMARY",
        "report_type": "secondary_baseline_report" if mode == "SWING" else "primary_research_report",
        "data_scope": {
            "symbols": ["BTCUSDT"],
            "primary_timeframes": ["4h"],
        },
        "feature_set_refs": ["fs-test-001"],
        "label_dataset_refs": ["lds-test-001"],
        "alpha_theses": [
            {"alpha_thesis_id": "ath-test-001", "status": "PROPOSED",
             "evidence_quality": "INSUFFICIENT"}
        ],
        "validation_summary": {
            "validation_report_id": f"vr-{mode.lower()}-test-001",
            "fold_count": 6,
            "verdict": "CANDIDATE_FOR_V7_GATES",
            "overfit_risk": "LOW",
        },
        "metrics": {
            "oos_expectancy_r": {"value": 0.15},
            "oos_sharpe": {"value": 0.5},
            "oos_trade_count": 600,
        },
        "cost_stress": {
            "baseline_fee_pct": 0.04,
            "baseline_slippage_pct": 0.02,
            "combined_stress_edge_survives": True,
        },
        "no_trade_comparison": {
            "active_beats_no_trade": True,
            "summary": "Test placeholder",
        },
        "regime_breakdown": {
            "regimes": [],
            "edge_only_in_rare_regime": False,
        },
        "multiple_hypothesis_control": {
            "tested_hypothesis_count": 1,
            "correction_method": "Bonferroni",
            "data_snooping_risk_flag": "LOW",
        },
        "verdict": "CANDIDATE_FOR_V7_GATES",
        "blocked_scopes": ["Test placeholder — no real data"],
        "limitations": ["Test placeholder — no real research."],
    }
    data.update(overrides)
    return data


def _minimal_vr(mode: str = "SWING", **overrides) -> Dict[str, Any]:
    """Build a minimal ValidationReport dict (PASS verdict)."""
    folds = [
        {
            "fold_number": i,
            "train_start": "2024-01-01T00:00:00Z",
            "train_end": "2024-07-01T00:00:00Z",
            "test_start": "2024-07-01T00:00:00Z",
            "test_end": "2024-08-01T00:00:00Z",
        }
        for i in range(1, 7)
    ]
    data = {
        "schema_version": "1.0.0",
        "validation_report_id": f"vr-{mode.lower()}-test-001",
        "mode": mode,
        "split_policy": {
            "train_pct": 0.60,
            "validation_pct": 0.15,
            "oos_pct": 0.25,
            "purge_window_bars": 10,
            "embargo_policy": "purge_and_embargo",
            "chronological_split": True,
        },
        "walk_forward_folds": {
            "fold_count": 6,
            "fold_type": "anchored",
            "folds": folds,
        },
        "oos_summary": {
            "oos_sharpe": 0.5,
            "oos_expectancy_r": 0.15,
            "oos_win_rate": 0.52,
            "oos_trade_count": 600,
            "oos_positive_expectancy": True,
            "fold_stability_score": 0.7,
        },
        "symbol_stability": {
            "symbols_tested": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            "symbol_count": 3,
            "max_single_symbol_concentration": 0.30,
            "max_cluster_concentration": 0.45,
            "single_symbol_limitation": False,
        },
        "regime_breakdown": {
            "regimes": [
                {"regime": "TREND_UP", "sample_pct": 0.30, "oos_expectancy_r": 0.20, "edge_present": True},
                {"regime": "TREND_DOWN", "sample_pct": 0.25, "oos_expectancy_r": 0.10, "edge_present": True},
                {"regime": "RANGE", "sample_pct": 0.30, "oos_expectancy_r": 0.05, "edge_present": True},
                {"regime": "TRANSITION", "sample_pct": 0.15, "oos_expectancy_r": 0.02, "edge_present": True},
            ],
            "edge_only_in_rare_regime": False,
        },
        "cost_stress": {
            "baseline_fee_pct": 0.04,
            "baseline_slippage_pct": 0.02,
            "fee_stress_edge_survives": True,
            "slippage_stress_edge_survives": True,
            "combined_stress_edge_survives": True,
            "cost_edge_destroyed": False,
            "funding_deferred_block": {
                "funding_deferred": False,
                "block_reason": "",
                "affected_scopes": [],
            },
        },
        "no_trade_comparison": {
            "active_beats_no_trade": True,
            "summary": "Test — active beats no-trade",
        },
        "overfit_risk_flags": {
            "overfit_risk_overall": "LOW",
        },
        "multiple_hypothesis_control": {
            "tested_hypothesis_count": 1,
            "correction_method": "Bonferroni",
            "trial_count_disclosure": 1,
            "rejected_candidate_count": 0,
        },
        "calibration_gate_alignment": {
            "calibration_candidate_id": f"cc-{mode.lower()}-test-001",
            "ece": 0.02,
            "mce": 0.05,
            "calibration_status": "CALIBRATED",
        },
        "verdict": "PASS",
        "limitations": ["Test placeholder — no real validation."],
    }
    data.update(overrides)
    return data


def _valid_gate_mapping() -> Dict[str, Any]:
    """Build a valid gate mapping with all 11 canonical gates."""
    return {
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
        f"G{i}_live": {"evidence_ref": f"Test evidence for gate {g}", "status": "NOT_EVALUATED"}
        for i, g in enumerate([
            "doc_ready", "research_backtest", "walk_forward_oos", "cost_stress",
            "regime_breakdown", "symbol_stability", "calibration_reliability",
            "shadow", "paper", "tiny_live", "live"
        ])
    }


# ═══════════════════════════════════════════════════════════════════════════
# TestGateMappingValidation — 7 tests
# ═══════════════════════════════════════════════════════════════════════════

class TestGateMappingValidation:
    """AC-07-GM-01 through AC-07-GM-07, AC-07-ST-01"""

    def test_all_canonical_gates_present_and_valid(self):
        """AC-07-GM-01: All 11 canonical gates with valid entries returns True."""
        mapping = _valid_gate_mapping()
        result = validate_gate_mapping(mapping)
        assert result is True

    def test_missing_gates_raises_listing_all_missing(self):
        """AC-07-GM-02: Missing G4 and G7 lists both in error message."""
        mapping = _valid_gate_mapping()
        del mapping["G4_regime_breakdown"]
        del mapping["G7_shadow"]
        with pytest.raises(GateMappingError) as exc:
            validate_gate_mapping(mapping)
        msg = str(exc.value)
        assert "G4_regime_breakdown" in msg
        assert "G7_shadow" in msg
        assert "handoff_to_v7.md" in msg

    def test_unknown_gate_names_raises_listing_all_unknown(self):
        """AC-07-GM-03: Old AlphaForge-invented gates raise error listing them."""
        mapping = {
            "G0_data_quality": {"evidence_ref": "x"},
            "G1_feature_validity": {"evidence_ref": "x"},
        }
        with pytest.raises(GateMappingError) as exc:
            validate_gate_mapping(mapping)
        msg = str(exc.value)
        assert "G0_data_quality" in msg
        assert "G1_feature_validity" in msg
        assert "Unknown gate" in msg

    def test_missing_evidence_ref_raises(self):
        """AC-07-GM-04: Gate entry missing evidence_ref raises."""
        mapping = _valid_gate_mapping()
        del mapping["G3_cost_stress"]["evidence_ref"]
        with pytest.raises(GateMappingError) as exc:
            validate_gate_mapping(mapping)
        assert "evidence_ref" in str(exc.value)

    def test_missing_status_raises(self):
        """AC-07-GM-04: Gate entry missing status raises."""
        mapping = _valid_gate_mapping()
        del mapping["G5_symbol_stability"]["status"]
        with pytest.raises(GateMappingError) as exc:
            validate_gate_mapping(mapping)
        assert "status" in str(exc.value)

    def test_invalid_status_enum_raises(self):
        """AC-07-GM-05: Invalid status value (FAILED, UNKNOWN, IN_PROGRESS) raises."""
        mapping = _valid_gate_mapping()
        mapping["G0_doc_ready"]["status"] = "FAILED"
        with pytest.raises(GateMappingError) as exc:
            validate_gate_mapping(mapping)
        assert "FAILED" in str(exc.value)

    def test_empty_dict_raises_listing_all_11_missing(self):
        """AC-07-GM-06: Empty dict raises listing all 11 missing gates."""
        with pytest.raises(GateMappingError) as exc:
            validate_gate_mapping({})
        msg = str(exc.value)
        assert "Missing canonical" in msg
        missing_count = sum(1 for g in CANONICAL_V7_GATES if g in msg)
        assert missing_count == 11, f"Expected 11 missing gates, got {missing_count}"

    def test_error_message_references_handoff_to_v7(self):
        """AC-07-GM-07: Error message references handoff_to_v7.md."""
        with pytest.raises(GateMappingError) as exc:
            validate_gate_mapping({})
        assert "handoff_to_v7.md" in str(exc.value)


# ═══════════════════════════════════════════════════════════════════════════
# TestDryRunBuilder — 9 tests
# ═══════════════════════════════════════════════════════════════════════════

class TestDryRunBuilder:
    """AC-07-DRB-01 through AC-07-DRB-07"""

    def test_valid_swing_input_produces_valid_output(self):
        """AC-07-DRB-01: SWING input produces schema-valid output."""
        dinput = DryRunInput(
            mode="SWING",
            mode_research_report=_minimal_mrr("SWING"),
            validation_report=_minimal_vr("SWING"),
        )
        handoff = run_handoff_dry_run(dinput)
        assert handoff["schema_version"] == "1.0.0"
        assert handoff["handoff_package_id"]
        assert handoff["mode"] == "SWING"
        assert handoff["alpha_candidate_id"]
        assert handoff["mode_research_report_id"]
        assert handoff["validation_report_id"]
        assert handoff["model_artifact_id"]
        assert handoff["calibration_candidate_id"]
        assert "v7_gate_mapping" in handoff
        assert "recommended_status" in handoff
        assert "blocked_scopes" in handoff
        assert "limitations" in handoff
        assert "lineage" in handoff

    def test_valid_scalp_input_produces_valid_output(self):
        """AC-07-DRB-01: SCALP input produces schema-valid output."""
        dinput = DryRunInput(
            mode="SCALP",
            mode_research_report=_minimal_mrr("SCALP"),
            validation_report=_minimal_vr("SCALP"),
        )
        handoff = run_handoff_dry_run(dinput)
        assert handoff["mode"] == "SCALP"
        assert len(handoff["v7_gate_mapping"]) == 11

    def test_valid_aggressive_scalp_input_produces_valid_output(self):
        """AC-07-DRB-01: AGGRESSIVE_SCALP input produces schema-valid output."""
        dinput = DryRunInput(
            mode="AGGRESSIVE_SCALP",
            mode_research_report=_minimal_mrr("AGGRESSIVE_SCALP"),
            validation_report=_minimal_vr("AGGRESSIVE_SCALP"),
        )
        handoff = run_handoff_dry_run(dinput)
        assert handoff["mode"] == "AGGRESSIVE_SCALP"

    def test_all_gates_not_evaluated(self):
        """AC-07-DRB-02, AC-07-ST-03: All 11 gates have status NOT_EVALUATED."""
        dinput = DryRunInput(
            mode="SWING",
            mode_research_report=_minimal_mrr("SWING"),
            validation_report=_minimal_vr("SWING"),
        )
        handoff = run_handoff_dry_run(dinput)
        gate_mapping = handoff["v7_gate_mapping"]
        assert len(gate_mapping) == 11
        for gate_id in CANONICAL_V7_GATES:
            assert gate_id in gate_mapping, f"Missing canonical gate: {gate_id}"
            entry = gate_mapping[gate_id]
            assert entry["status"] == "NOT_EVALUATED", (
                f"Gate {gate_id} status is '{entry['status']}', expected NOT_EVALUATED"
            )

    def test_recommended_status_review_required(self):
        """AC-07-DRB-03, AC-07-ST-04: recommended_status is REVIEW_REQUIRED."""
        dinput = DryRunInput(
            mode="SWING",
            mode_research_report=_minimal_mrr("SWING"),
            validation_report=_minimal_vr("SWING"),
        )
        handoff = run_handoff_dry_run(dinput)
        assert handoff["recommended_status"] == HANDOFF_REVIEW_REQUIRED

    def test_blocked_scopes_populated_from_reports(self):
        """AC-07-DRB-04: blocked_scopes includes report scopes + dry-run blockers."""
        mrr = _minimal_mrr("SWING")
        mrr["blocked_scopes"] = ["Scope A from MRR", "Scope B from MRR"]
        dinput = DryRunInput(mode="SWING", mode_research_report=mrr, validation_report=_minimal_vr("SWING"))
        handoff = run_handoff_dry_run(dinput)
        blocked = " ".join(handoff["blocked_scopes"])
        assert "Scope A from MRR" in blocked
        assert "Scope B from MRR" in blocked
        # Dry-run blockers should be present
        assert "shadow" in blocked.lower() or "SHADOW" in blocked

    def test_missing_mrr_fields_raises(self):
        """AC-07-DRB-06: Missing ModeResearchReport fields raises InputContractError."""
        # Missing 'report_id'
        bad_mrr = _minimal_mrr("SWING")
        del bad_mrr["report_id"]
        dinput = DryRunInput(mode="SWING", mode_research_report=bad_mrr, validation_report=_minimal_vr("SWING"))
        with pytest.raises(InputContractError) as exc:
            run_handoff_dry_run(dinput)
        assert "report_id" in str(exc.value)
        assert "ModeResearchReport" in str(exc.value)

    def test_missing_vr_fields_raises(self):
        """AC-07-DRB-07: Missing ValidationReport fields raises InputContractError."""
        # Missing 'validation_report_id'
        bad_vr = _minimal_vr("SWING")
        del bad_vr["validation_report_id"]
        dinput = DryRunInput(mode="SWING", mode_research_report=_minimal_mrr("SWING"), validation_report=bad_vr)
        with pytest.raises(InputContractError) as exc:
            run_handoff_dry_run(dinput)
        assert "validation_report_id" in str(exc.value)
        assert "ValidationReport" in str(exc.value)

    def test_rejection_rules_applied_12_entries(self):
        """AC-07-NP-11: rejection_rules_applied has exactly 12 entries."""
        dinput = DryRunInput(
            mode="SWING",
            mode_research_report=_minimal_mrr("SWING"),
            validation_report=_minimal_vr("SWING"),
        )
        handoff = run_handoff_dry_run(dinput)
        rules = handoff["rejection_rules_applied"]
        assert len(rules) == 12, f"Expected 12 rejection rules, got {len(rules)}: {rules}"
        # Each rule string should start with "Rule N" where N is 1-12
        for i in range(1, 13):
            prefix = f"Rule {i}"
            found = any(r.startswith(prefix) for r in rules)
            assert found, f"Rule {i} not found in rejection_rules_applied"


# ═══════════════════════════════════════════════════════════════════════════
# TestPromotionGuard — 4 tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPromotionGuard:
    """AC-07-NP-01 through AC-07-NP-04, AC-07-ST-05"""

    def test_promotion_candidate_raises(self):
        """AC-07-NP-01: PROMOTION_CANDIDATE raises PromotionGuardError."""
        with pytest.raises(PromotionGuardError) as exc:
            _guard_promotion_status(HANDOFF_PROMOTION_CANDIDATE)
        assert "PROMOTION_CANDIDATE" in str(exc.value)
        assert "REVIEW_REQUIRED" in str(exc.value)

    def test_shadow_ready_raises(self):
        """AC-07-NP-02: SHADOW_READY raises PromotionGuardError."""
        with pytest.raises(PromotionGuardError) as exc:
            _guard_promotion_status(HANDOFF_SHADOW_READY)
        assert "SHADOW_READY" in str(exc.value)

    def test_review_required_passes_silently(self):
        """AC-07-NP-03: REVIEW_REQUIRED returns None (passes silently)."""
        result = _guard_promotion_status(HANDOFF_REVIEW_REQUIRED)
        assert result is None

    def test_guard_called_before_builder(self):
        """AC-07-NP-04: run_handoff_dry_run with REVIEW_REQUIRED does not raise."""
        dinput = DryRunInput(
            mode="SWING",
            mode_research_report=_minimal_mrr("SWING"),
            validation_report=_minimal_vr("SWING"),
        )
        # Should not raise
        handoff = run_handoff_dry_run(dinput)
        assert handoff["recommended_status"] == HANDOFF_REVIEW_REQUIRED

    def test_promotion_guard_error_references_v7_authority(self):
        """AC-07-NP-12: Error message references V7 final authority."""
        with pytest.raises(PromotionGuardError) as exc:
            _guard_promotion_status(HANDOFF_PROMOTION_CANDIDATE)
        msg = str(exc.value)
        assert "RECOMMENDS" in msg
        assert "DECIDES" in msg
        assert "handoff_to_v7.md" in msg


# ═══════════════════════════════════════════════════════════════════════════
# TestRejectionRules — 12 tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRejectionRules:
    """AC-07-NP-05 through AC-07-NP-11, AC-07-ST-07"""

    def _base_mrr(self) -> Dict[str, Any]:
        return {"mode": "SWING", "report_id": "mrr-test-001", "blocked_scopes": [], "limitations": []}

    def _base_vr(self, **overrides) -> Dict[str, Any]:
        """Build a VR with safe defaults."""
        data = {
            "validation_report_id": "vr-test-001",
            "verdict": "PASS",
            "cost_stress": {
                "cost_edge_destroyed": False,
                "combined_stress_edge_survives": True,
            },
            "overfit_risk_flags": {
                "overfit_risk_overall": "LOW",
                "purge_violation_detected": False,
                "train_oos_gap": "LOW",
            },
            "symbol_stability": {
                "max_single_symbol_concentration": 0.30,
                "single_symbol_limitation": False,
            },
            "calibration_gate_alignment": {
                "calibration_status": "CALIBRATED",
            },
            "split_policy": {},
        }
        data.update(overrides)
        return data

    def test_rule1_missing_evidence_fails(self):
        """Rule 1: Missing report_id fails."""
        mrr = {"mode": "SWING", "report_id": "", "blocked_scopes": [], "limitations": []}
        result = _evaluate_rejection_rules(mrr, self._base_vr(), is_dry_run=True)
        assert result.is_rejected is True
        assert any("Rule 1" in f for f in result.failed)

    def test_rule5_fail_overfit_verdict_fails(self):
        """AC-07-NP-05: FAIL_OVERFIT verdict fails."""
        result = _evaluate_rejection_rules(self._base_mrr(), self._base_vr(verdict="FAIL_OVERFIT"), is_dry_run=True)
        assert result.is_rejected is True
        assert any("Rule 5" in f and "FAIL_OVERFIT" in f for f in result.failed)

    def test_rule5_inconclusive_verdict_blocked(self):
        """Rule 5: INCONCLUSIVE verdict is blocked, not failed."""
        result = _evaluate_rejection_rules(self._base_mrr(), self._base_vr(verdict="INCONCLUSIVE"), is_dry_run=True)
        assert any("Rule 5" in b and "INCONCLUSIVE" in b for b in result.blocked)

    def test_rule6_cost_edge_destroyed_fails(self):
        """AC-07-NP-06: cost_edge_destroyed=True fails."""
        vr = self._base_vr()
        vr["cost_stress"] = {"cost_edge_destroyed": True, "combined_stress_edge_survives": False}
        result = _evaluate_rejection_rules(self._base_mrr(), vr, is_dry_run=True)
        assert result.is_rejected is True
        assert any("Rule 6" in f for f in result.failed)

    def test_rule7_overfit_critical_fails(self):
        """AC-07-NP-07: overfit_risk_overall=CRITICAL fails."""
        vr = self._base_vr()
        vr["overfit_risk_flags"]["overfit_risk_overall"] = "CRITICAL"
        result = _evaluate_rejection_rules(self._base_mrr(), vr, is_dry_run=True)
        assert result.is_rejected is True
        assert any("Rule 7" in f for f in result.failed)

    def test_rule7_overfit_high_blocked(self):
        """Rule 7: overfit_risk_overall=HIGH is blocked, not failed."""
        vr = self._base_vr()
        vr["overfit_risk_flags"]["overfit_risk_overall"] = "HIGH"
        result = _evaluate_rejection_rules(self._base_mrr(), vr, is_dry_run=True)
        assert any("Rule 7" in b for b in result.blocked)

    def test_rule8_single_symbol_overfitting_fails(self):
        """AC-07-NP-08: max_single_symbol_concentration=0.45 (>0.40) fails."""
        vr = self._base_vr()
        vr["symbol_stability"]["max_single_symbol_concentration"] = 0.45
        result = _evaluate_rejection_rules(self._base_mrr(), vr, is_dry_run=True)
        assert result.is_rejected is True
        assert any("Rule 8" in f and "0.45" in f for f in result.failed)

    def test_rule9_calibration_unreliable_fails(self):
        """AC-07-NP-09: calibration_status=UNRELIABLE fails."""
        vr = self._base_vr()
        vr["calibration_gate_alignment"]["calibration_status"] = "UNRELIABLE"
        result = _evaluate_rejection_rules(self._base_mrr(), vr, is_dry_run=True)
        assert result.is_rejected is True
        assert any("Rule 9" in f and "UNRELIABLE" in f for f in result.failed)

    def test_rule10_funding_deferred_blocked(self):
        """AC-07-NP-10: funding_deferred=True is blocked, not failed."""
        vr = self._base_vr()
        vr["cost_stress"]["funding_deferred_block"] = {
            "funding_deferred": True,
            "block_reason": "Not yet available",
        }
        result = _evaluate_rejection_rules(self._base_mrr(), vr, is_dry_run=True)
        assert any("Rule 10" in b and "Fund" in b for b in result.blocked)
        # Should NOT be in failed — blocked only
        assert not any("Rule 10" in f for f in result.failed)

    def test_rule12_policy_conflict_blocked_in_dry_run(self):
        """Rule 12: In dry run, policy conflict is always blocked."""
        result = _evaluate_rejection_rules(self._base_mrr(), self._base_vr(), is_dry_run=True)
        assert any("Rule 12" in b and "deferred" in b.lower() for b in result.blocked)

    def test_all_pass_scenario_is_not_rejected(self):
        """AC-07-ST-07: Clean PASS produces is_rejected=False, all rules PASSED where applicable."""
        result = _evaluate_rejection_rules(self._base_mrr(), self._base_vr(), is_dry_run=True)
        assert result.is_rejected is False
        # In dry run, rules 3, 4, 12 are blocked, rest passed
        assert len(result.passed) == 9
        assert len(result.failed) == 0
        assert len(result.blocked) == 3

    def test_multiple_failures_returns_all_in_failed_list(self):
        """Multiple failures returns all failures in failed list."""
        vr = self._base_vr()
        vr["verdict"] = "FAIL_OVERFIT"
        vr["overfit_risk_flags"]["overfit_risk_overall"] = "CRITICAL"
        vr["cost_stress"]["cost_edge_destroyed"] = True
        vr["cost_stress"]["combined_stress_edge_survives"] = False
        vr["symbol_stability"]["max_single_symbol_concentration"] = 0.50
        result = _evaluate_rejection_rules(self._base_mrr(), vr, is_dry_run=True)
        assert result.is_rejected is True
        assert len(result.failed) >= 3  # Multiple failures expected


# ═══════════════════════════════════════════════════════════════════════════
# TestInputContractValidation
# ═══════════════════════════════════════════════════════════════════════════

class TestInputContractValidation:
    """AC-07-IC-01 through AC-07-IC-06"""

    def test_mode_research_report_required_fields_match_schema(self):
        """AC-07-IC-04: MRR required fields derived from schema."""
        assert len(MODE_RESEARCH_REPORT_REQUIRED_FIELDS) == 18
        # Check key fields are present
        for key in ("schema_version", "report_id", "mode", "metrics", "verdict",
                     "cost_stress", "regime_breakdown", "multiple_hypothesis_control"):
            assert key in MODE_RESEARCH_REPORT_REQUIRED_FIELDS, f"Missing MRR field: {key}"

    def test_validation_report_required_fields_match_schema(self):
        """AC-07-IC-05: VR required fields derived from schema."""
        assert len(VALIDATION_REPORT_REQUIRED_FIELDS) == 13
        for key in ("schema_version", "validation_report_id", "mode", "split_policy",
                     "walk_forward_folds", "oos_summary", "symbol_stability", "verdict"):
            assert key in VALIDATION_REPORT_REQUIRED_FIELDS, f"Missing VR field: {key}"

    def test_dry_run_input_has_exactly_7_fields(self):
        """AC-07-IC-03: DryRunInput has exactly 7 fields."""
        from dataclasses import fields
        fnames = {f.name for f in fields(DryRunInput)}
        expected = {"mode", "mode_research_report", "validation_report",
                     "handoff_package_id", "alpha_candidate_id",
                     "model_artifact_id", "calibration_candidate_id"}
        assert fnames == expected, f"Fields mismatch: {fnames} vs {expected}"

    def test_validate_input_reports_raises_on_missing_fields(self):
        """AC-07-IC-06: validate_input_reports raises InputContractError on missing fields."""
        from alphaforge.handoff.dry_run import validate_input_reports
        bad_mrr = {"mode": "SWING"}  # Missing most required fields
        vr = _minimal_vr("SWING")
        with pytest.raises(InputContractError):
            validate_input_reports(bad_mrr, vr)


# ═══════════════════════════════════════════════════════════════════════════
# TestSchemaValidation
# ═══════════════════════════════════════════════════════════════════════════

class TestSchemaValidation:
    """AC-07-ST-02: Output validates against v7_handoff_package.schema.json"""

    def test_output_validates_against_v7_handoff_package_schema(self):
        """AC-07-ST-02: run_handoff_dry_run output validates against schema."""
        from alphaforge.contracts.loader import load_schema
        from alphaforge.contracts.validator import validate_payload

        dinput = DryRunInput(
            mode="SWING",
            mode_research_report=_minimal_mrr("SWING"),
            validation_report=_minimal_vr("SWING"),
        )
        handoff = run_handoff_dry_run(dinput)

        schema = load_schema("v7_handoff_package.schema.json")
        result = validate_payload(schema, handoff, "v7_handoff_package")
        assert result.valid, f"Schema validation failed: {result.errors}"


# ═══════════════════════════════════════════════════════════════════════════
# TestGateNamesAreCanonical
# ═══════════════════════════════════════════════════════════════════════════

class TestGateNamesAreCanonical:
    """Verify output gate names match CANONICAL_V7_GATES exactly."""

    def test_all_gate_keys_are_canonical(self):
        """Gate keys match CANONICAL_V7_GATES from constants.py."""
        dinput = DryRunInput(
            mode="SWING",
            mode_research_report=_minimal_mrr("SWING"),
            validation_report=_minimal_vr("SWING"),
        )
        handoff = run_handoff_dry_run(dinput)
        gate_keys = set(handoff["v7_gate_mapping"].keys())
        canonical_set = set(CANONICAL_V7_GATES)
        assert gate_keys == canonical_set, (
            f"Gate key mismatch. Extra: {gate_keys - canonical_set}, "
            f"Missing: {canonical_set - gate_keys}"
        )

    def test_old_gate_names_never_present(self):
        """Old AlphaForge gate names (e.g., G0_data_quality) are NEVER in output."""
        dinput = DryRunInput(
            mode="SWING",
            mode_research_report=_minimal_mrr("SWING"),
            validation_report=_minimal_vr("SWING"),
        )
        handoff = run_handoff_dry_run(dinput)
        gate_keys = set(handoff["v7_gate_mapping"].keys())
        old_names = {
            "G0_data_quality", "G1_feature_validity", "G2_label_validity",
            "G3_model_sanity", "G4_oos_performance", "G5_cost_resilience",
            "G6_regime_robustness", "G7_stability", "G8_calibration",
            "G9_no_trade_baseline", "G10_paper_shadow",
        }
        intersection = gate_keys & old_names
        assert not intersection, f"Old gate names found in output: {intersection}"
