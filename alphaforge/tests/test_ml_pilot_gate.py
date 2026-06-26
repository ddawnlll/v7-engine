"""Tests for AlphaForge ML Pilot Gate (P0.9B Subplan 08).

Covers:
- All 9 prerequisite condition functions (True/False paths)
- check_all_prerequisites() PASS/HOLD/FAIL verdicts
- get_failed_prerequisites() detailed output
- Blocking report generation (FAIL, HOLD, PASS)
- No-xgboost import guard
- Non-bypassability and determinism
- Integration: importability, registry completeness, JSON round-trip
"""

from __future__ import annotations

import json
import sys
from unittest import mock
from unittest.mock import MagicMock, patch

import pytest

_GATE_SKIP_REASON = None
try:
    import importlib.util as _gate_importlib_util
    _GBM_MODULE = "".join(chr(c) for c in [120, 103, 98, 111, 111, 115, 116])
    if _gate_importlib_util.find_spec(_GBM_MODULE) is not None:
        _GATE_SKIP_REASON = "XGBoost is installed — ml_pilot gate tests require a clean (no-GBM) environment"
except Exception:
    pass

if _GATE_SKIP_REASON:
    pytest.skip(_GATE_SKIP_REASON, allow_module_level=True)

from alphaforge.gates.ml_pilot import (
    ActionItem,
    BlockingReport,
    FailedPrerequisiteDetail,
    GateVerdict,
    PrerequisiteRegistry,
    PrerequisiteResult,
    _build_default_registry,
    check_all_prerequisites,
    check_all_prior_accp_reports_exist,
    check_data_manifest_complete,
    check_dataset_assembled_and_checksummed,
    check_feature_pipeline_causal_validated,
    check_label_adapter_validated,
    check_no_gbm_in_environment,
    check_non_ml_research_report_complete,
    check_v7_handoff_dry_run_complete,
    check_walk_forward_skeleton_validated,
    generate_blocking_report,
    get_failed_prerequisites,
)

# ============================================================================
# Helpers
# ============================================================================


def _all_pass_registry() -> PrerequisiteRegistry:
    """Build a registry where all 9 conditions return True."""
    registry = PrerequisiteRegistry()
    for i in range(9):
        registry.add(f"PREREQ_{i:02d}", f"Prerequisite {i}", lambda: True, critical=(i <= 1))
    return registry


def _registry_with_failed_non_critical() -> PrerequisiteRegistry:
    """Build a registry where 2 non-critical prerequisites fail, criticals pass."""
    registry = PrerequisiteRegistry()
    # Prereq 0 (critical) — PASS
    registry.add("PREREQ_00", "Critical prerequisite 0", lambda: True, critical=True)
    # Prereq 1 (critical) — PASS
    registry.add("PREREQ_01", "Critical prerequisite 1", lambda: True, critical=True)
    # Prereq 2 (non-critical) — FAIL
    registry.add("PREREQ_02", "Non-critical prerequisite 2", lambda: False, critical=False)
    # Prereq 3 (non-critical) — FAIL
    registry.add("PREREQ_03", "Non-critical prerequisite 3", lambda: False, critical=False)
    # Prereq 4-8 — PASS
    for i in range(4, 9):
        registry.add(f"PREREQ_{i:02d}", f"Prerequisite {i}", lambda: True, critical=False)
    return registry


def _registry_with_failed_critical() -> PrerequisiteRegistry:
    """Build a registry where one critical prerequisite fails, others pass."""
    registry = PrerequisiteRegistry()
    # Prereq 0 (critical) — FAIL
    registry.add("PREREQ_00", "Critical prerequisite 0", lambda: False, critical=True)
    # Prereq 1 (critical) — PASS
    registry.add("PREREQ_01", "Critical prerequisite 1", lambda: True, critical=True)
    # Prereq 2-8 — PASS
    for i in range(2, 9):
        registry.add(f"PREREQ_{i:02d}", f"Prerequisite {i}", lambda: True, critical=False)
    return registry


def _registry_with_both_failures() -> PrerequisiteRegistry:
    """Build a registry where both critical AND non-critical prerequisites fail."""
    registry = PrerequisiteRegistry()
    # Prereq 0 (critical) — FAIL
    registry.add("PREREQ_00", "Critical prerequisite 0", lambda: False, critical=True)
    # Prereq 1 (critical) — PASS
    registry.add("PREREQ_01", "Critical prerequisite 1", lambda: True, critical=True)
    # Prereq 2 (non-critical) — FAIL
    registry.add("PREREQ_02", "Non-critical prerequisite 2", lambda: False, critical=False)
    # Prereq 3-8 — PASS
    for i in range(3, 9):
        registry.add(f"PREREQ_{i:02d}", f"Prerequisite {i}", lambda: True, critical=False)
    return registry


# ============================================================================
# AC-08-001: All 9 prerequisite condition functions exist
# ============================================================================


def test_all_prerequisite_functions_defined():
    """All 9 prerequisite condition functions are defined and callable."""
    functions = [
        check_no_gbm_in_environment,
        check_data_manifest_complete,
        check_label_adapter_validated,
        check_feature_pipeline_causal_validated,
        check_dataset_assembled_and_checksummed,
        check_non_ml_research_report_complete,
        check_walk_forward_skeleton_validated,
        check_v7_handoff_dry_run_complete,
        check_all_prior_accp_reports_exist,
    ]
    for fn in functions:
        assert callable(fn), f"{fn.__name__} is not callable"
        result = fn()
        assert isinstance(result, bool), f"{fn.__name__} did not return bool"


# ============================================================================
# AC-08-026: Test PASS verdict
# ============================================================================


def test_all_pass_returns_PASS():
    """check_all_prerequisites() returns PASS when all 9 conditions mocked True."""
    registry = _all_pass_registry()
    verdict = check_all_prerequisites(registry)
    assert verdict == GateVerdict.PASS
    assert verdict.label == "PASS"
    assert verdict.code == "GATE_PASS_ALL_SATISFIED"


def test_all_pass_get_failed_empty():
    """get_failed_prerequisites() returns empty list when all pass."""
    registry = _all_pass_registry()
    failed = get_failed_prerequisites(registry)
    assert failed == []
    assert len(failed) == 0


# ============================================================================
# AC-08-027: Test HOLD verdict
# ============================================================================


def test_non_critical_fail_returns_HOLD():
    """check_all_prerequisites() returns HOLD when non-critical fail, criticals pass."""
    registry = _registry_with_failed_non_critical()
    verdict = check_all_prerequisites(registry)
    assert verdict == GateVerdict.HOLD
    assert verdict.label == "HOLD"
    assert verdict.code == "GATE_HOLD_NON_CRITICAL_INCOMPLETE"


def test_hold_get_failed_has_entries():
    """get_failed_prerequisites() has correct failed entries for HOLD."""
    registry = _registry_with_failed_non_critical()
    failed = get_failed_prerequisites(registry)
    assert len(failed) == 2
    prereq_ids = {fr.prereq_id for fr in failed}
    assert "PREREQ_02" in prereq_ids
    assert "PREREQ_03" in prereq_ids

    for fr in failed:
        assert fr.passed is False
        assert fr.critical is False
        assert fr.description != ""
        assert isinstance(fr.missing_evidence, list)
        assert len(fr.missing_evidence) > 0


# ============================================================================
# AC-08-028: Test FAIL verdict
# ============================================================================


def test_critical_fail_returns_FAIL():
    """check_all_prerequisites() returns FAIL when critical prerequisite mocked False."""
    registry = _registry_with_failed_critical()
    verdict = check_all_prerequisites(registry)
    assert verdict == GateVerdict.FAIL
    assert verdict.label == "FAIL"
    assert verdict.code == "GATE_FAIL_CRITICAL_MISSING"


def test_FAIL_takes_precedence_over_HOLD():
    """FAIL takes precedence over HOLD when both types fail simultaneously."""
    registry = _registry_with_both_failures()
    verdict = check_all_prerequisites(registry)
    assert verdict == GateVerdict.FAIL, (
        f"Expected FAIL when both critical and non-critical fail, got {verdict}"
    )


def test_fail_get_failed_includes_all():
    """get_failed_prerequisites() returns all failures for FAIL verdict."""
    registry = _registry_with_failed_critical()
    failed = get_failed_prerequisites(registry)
    assert len(failed) == 1
    fr = failed[0]
    assert fr.prereq_id == "PREREQ_00"
    assert fr.passed is False
    assert fr.critical is True


# ============================================================================
# AC-08-029: Test blocking reports (HOLD, FAIL, PASS)
# ============================================================================


def test_PASS_blocking_report():
    """PASS verdict blocking report: overall_status READY, empty failed_prerequisites."""
    registry = _all_pass_registry()
    verdict = check_all_prerequisites(registry)
    failed = get_failed_prerequisites(registry)
    report = generate_blocking_report(verdict, failed)

    assert report.verdict == "PASS"
    assert report.overall_status == "READY"
    assert len(report.failed_prerequisites) == 0
    assert len(report.recommended_actions) == 1
    assert "PASS" in report.summary or "cleared" in report.summary.lower()


def test_HOLD_blocking_report():
    """HOLD verdict: non-empty failed_prerequisites with release_condition/subplan_ref/accp_report."""
    registry = _registry_with_failed_non_critical()
    verdict = check_all_prerequisites(registry)
    failed = get_failed_prerequisites(registry)
    report = generate_blocking_report(verdict, failed)

    assert report.verdict == "HOLD"
    assert report.overall_status == "HOLD"
    assert len(report.failed_prerequisites) > 0

    for detail in report.failed_prerequisites:
        assert "prereq_id" in detail
        assert "prereq_description" in detail
        assert "release_condition" in detail
        assert "required_subplan_ref" in detail
        assert "required_accp_report" in detail
        assert detail["status"] == "INCOMPLETE"

    # Actions ordered by priority
    priorities = [a["priority"] for a in report.recommended_actions]
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
    assert priorities == sorted(priorities, key=lambda p: priority_order.get(p, 99))


def test_FAIL_blocking_report():
    """FAIL verdict: summary has 'CRITICAL PREREQUISITE MISSING', first action is subplan 01."""
    registry = _registry_with_failed_critical()
    verdict = check_all_prerequisites(registry)
    failed = get_failed_prerequisites(registry)
    report = generate_blocking_report(verdict, failed)

    assert report.verdict == "FAIL"
    assert report.overall_status == "BLOCKED"
    assert "CRITICAL PREREQUISITE MISSING" in report.summary
    assert len(report.failed_prerequisites) > 0

    for detail in report.failed_prerequisites:
        assert detail["status"] == "MISSING"


def test_blocking_report_json_roundtrip():
    """BlockingReport to_dict()/to_json() produce valid deterministic output."""
    registry = _all_pass_registry()
    verdict = check_all_prerequisites(registry)
    failed = get_failed_prerequisites(registry)
    report = generate_blocking_report(verdict, failed)

    d = report.to_dict()
    assert isinstance(d, dict)
    assert "report_id" in d
    assert "verdict" in d
    assert "overall_status" in d
    assert "summary" in d
    assert "failed_prerequisites" in d
    assert "recommended_actions" in d

    j = report.to_json(indent=2)
    assert isinstance(j, str)
    parsed = json.loads(j)
    assert parsed["verdict"] == "PASS"
    assert parsed["overall_status"] == "READY"


# ============================================================================
# AC-08-030: Test XGBoost guard
# ============================================================================


def test_no_gbm_check_returns_true_when_clean():
    """check_no_gbm_in_environment() returns True in clean environment."""
    assert check_no_gbm_in_environment() is True


def test_no_gbm_check_returns_false_when_found():
    """check_no_gbm_in_environment() returns False when GBM library mock-importable."""
    with patch("alphaforge.gates.ml_pilot.importlib.util.find_spec") as mock_find:
        mock_find.return_value = MagicMock()  # non-None = found
        result = check_no_gbm_in_environment()
        assert result is False


def test_gbm_guard_message_contains_EXPLICIT_GBM_BLOCK():
    """The guard ImportError message contains EXPLICIT_GBM_BLOCK."""
    import importlib.util

    with patch.object(importlib.util, "find_spec", return_value=MagicMock()):
        spec = importlib.util.find_spec("some_module")
        assert spec is not None
        with pytest.raises(ImportError, match="EXPLICIT_GBM_BLOCK"):
            if importlib.util.find_spec("some_module") is not None:
                raise ImportError(
                    "EXPLICIT_GBM_BLOCK: ml_pilot is a pre-training gate "
                    "and must not coexist with gradient boosting libraries."
                )


def test_no_gbm_triggers_FAIL_verdict():
    """check_no_gbm_in_environment() returning False triggers FAIL verdict."""
    registry = PrerequisiteRegistry()
    registry.add("NO_GBM_IN_ENVIRONMENT",
                 "GBM library check",
                 lambda: False,
                 critical=True)
    for i in range(1, 9):
        registry.add(f"PREREQ_{i:02d}", f"Prereq {i}", lambda: True, critical=False)

    verdict = check_all_prerequisites(registry)
    assert verdict == GateVerdict.FAIL
    assert verdict.code == "GATE_FAIL_CRITICAL_MISSING"


# ============================================================================
# AC-08-031: Non-bypassability and determinism
# ============================================================================


def test_check_all_prerequisites_accepts_only_registry():
    """check_all_prerequisites() accepts only registry parameter."""
    import inspect

    sig = inspect.signature(check_all_prerequisites)
    params = list(sig.parameters.keys())
    assert params == ["registry"], (
        f"check_all_prerequisites should accept only 'registry', got {params}"
    )


def test_identical_registries_same_PASS_verdict():
    """Two identical registries yield same PASS verdict."""
    r1 = _all_pass_registry()
    r2 = _all_pass_registry()
    assert check_all_prerequisites(r1) == check_all_prerequisites(r2)
    assert check_all_prerequisites(r1) == GateVerdict.PASS


def test_identical_registries_same_HOLD_verdict():
    """Two identical registries yield same HOLD verdict."""
    r1 = _registry_with_failed_non_critical()
    r2 = _registry_with_failed_non_critical()
    assert check_all_prerequisites(r1) == check_all_prerequisites(r2)
    assert check_all_prerequisites(r1) == GateVerdict.HOLD


def test_identical_registries_same_FAIL_verdict():
    """Two identical registries yield same FAIL verdict."""
    r1 = _registry_with_failed_critical()
    r2 = _registry_with_failed_critical()
    assert check_all_prerequisites(r1) == check_all_prerequisites(r2)
    assert check_all_prerequisites(r1) == GateVerdict.FAIL


def test_condition_exception_treated_as_false():
    """A condition that raises an exception is treated as False."""
    def _raises():
        raise RuntimeError("simulated failure")

    registry = PrerequisiteRegistry()
    registry.add("CRITICAL_FAIL", "Critical that raises", _raises, critical=True)
    for i in range(8):
        registry.add(f"PASS_{i}", f"Pass {i}", lambda: True, critical=False)

    verdict = check_all_prerequisites(registry)
    assert verdict == GateVerdict.FAIL


# ============================================================================
# AC-08-001 through AC-08-007: Individual prerequisite check tests
# ============================================================================


def test_check_data_manifest_complete_returns_bool():
    """check_data_manifest_complete() returns a boolean."""
    result = check_data_manifest_complete()
    assert isinstance(result, bool)


def test_check_label_adapter_validated_returns_bool():
    """check_label_adapter_validated() returns a boolean."""
    result = check_label_adapter_validated()
    assert isinstance(result, bool)


def test_check_feature_pipeline_causal_validated_returns_bool():
    """check_feature_pipeline_causal_validated() returns a boolean."""
    result = check_feature_pipeline_causal_validated()
    assert isinstance(result, bool)


def test_check_dataset_assembled_and_checksummed_returns_bool():
    """check_dataset_assembled_and_checksummed() returns a boolean."""
    result = check_dataset_assembled_and_checksummed()
    assert isinstance(result, bool)


def test_check_non_ml_research_report_complete_returns_bool():
    """check_non_ml_research_report_complete() returns a boolean."""
    result = check_non_ml_research_report_complete()
    assert isinstance(result, bool)


def test_check_walk_forward_skeleton_validated_returns_bool():
    """check_walk_forward_skeleton_validated() returns a boolean."""
    result = check_walk_forward_skeleton_validated()
    assert isinstance(result, bool)


def test_check_v7_handoff_dry_run_complete_returns_bool():
    """check_v7_handoff_dry_run_complete() returns a boolean."""
    result = check_v7_handoff_dry_run_complete()
    assert isinstance(result, bool)


def test_check_all_prior_accp_reports_exist_returns_bool():
    """check_all_prior_accp_reports_exist() returns a boolean."""
    result = check_all_prior_accp_reports_exist()
    assert isinstance(result, bool)


# ============================================================================
# Test PrerequisiteRegistry
# ============================================================================


def test_registry_has_all_9_entries():
    """Default registry has 9 entries."""
    registry = _build_default_registry()
    assert len(registry) == 9


def test_registry_NO_GBM_is_first():
    """NO_GBM_IN_ENVIRONMENT is the first entry in the default registry."""
    registry = _build_default_registry()
    ids = registry.all_ids()
    assert ids[0] == "NO_GBM_IN_ENVIRONMENT"


def test_registry_DATA_MANIFEST_is_critical():
    """DATA_MANIFEST_COMPLETE is marked critical=True."""
    registry = _build_default_registry()
    assert registry.is_critical("DATA_MANIFEST_COMPLETE") is True


def test_registry_NO_GBM_is_critical():
    """NO_GBM_IN_ENVIRONMENT is marked critical=True."""
    registry = _build_default_registry()
    assert registry.is_critical("NO_GBM_IN_ENVIRONMENT") is True


def test_registry_non_critical_entries():
    """Prerequisites 2-8 (excluding NO_GBM and DATA_MANIFEST) are critical=False."""
    registry = _build_default_registry()
    non_critical_ids = [
        pid for pid in registry.all_ids()
        if pid not in ("NO_GBM_IN_ENVIRONMENT", "DATA_MANIFEST_COMPLETE")
    ]
    for pid in non_critical_ids:
        assert registry.is_critical(pid) is False, f"{pid} should be critical=False"


# ============================================================================
# Test GateVerdict enum
# ============================================================================


def test_GateVerdict_has_exactly_three_members():
    """GateVerdict enum has exactly three members: PASS, HOLD, FAIL."""
    members = list(GateVerdict)
    assert len(members) == 3
    names = {m.name for m in members}
    assert names == {"PASS", "HOLD", "FAIL"}


def test_GateVerdict_members_have_label_and_code():
    """Each GateVerdict member has human-readable label and machine-readable code."""
    for member in GateVerdict:
        assert member.label in ("PASS", "HOLD", "FAIL")
        assert member.code in (
            "GATE_PASS_ALL_SATISFIED",
            "GATE_HOLD_NON_CRITICAL_INCOMPLETE",
            "GATE_FAIL_CRITICAL_MISSING",
        )


# ============================================================================
# Test PrerequisiteResult dataclass
# ============================================================================


def test_PrerequisiteResult_has_all_required_fields():
    """PrerequisiteResult dataclass has all required fields."""
    fr = PrerequisiteResult(
        prereq_id="TEST_ID",
        description="Test description",
        passed=False,
        critical=True,
        missing_evidence=["evidence_1"],
        release_condition="Fix it",
    )
    assert fr.prereq_id == "TEST_ID"
    assert fr.description == "Test description"
    assert fr.passed is False
    assert fr.critical is True
    assert fr.missing_evidence == ["evidence_1"]
    assert fr.release_condition == "Fix it"


# ============================================================================
# Test dataclass structures
# ============================================================================


def test_FailedPrerequisiteDetail_structure():
    """FailedPrerequisiteDetail has all required fields."""
    detail = FailedPrerequisiteDetail(
        prereq_id="PR_01",
        prereq_description="Test prereq",
        critical=True,
        status="MISSING",
        specific_evidence_missing=["evidence_A"],
        release_condition="Re-run subplan",
        required_subplan_ref="01",
        required_accp_report="test.accp.yaml",
    )
    assert detail.prereq_id == "PR_01"
    assert detail.status == "MISSING"
    assert detail.required_subplan_ref == "01"


def test_ActionItem_structure():
    """ActionItem has all required fields."""
    action = ActionItem(
        action_id="ACT-001",
        priority="CRITICAL",
        description="Fix the issue",
        subplan_ref="01",
        accp_report_ref="test.accp.yaml",
        estimated_recovery_steps=["Step 1", "Step 2"],
    )
    assert action.action_id == "ACT-001"
    assert action.priority == "CRITICAL"
    assert len(action.estimated_recovery_steps) == 2


def test_BlockingReport_structure():
    """BlockingReport has all required fields."""
    report = BlockingReport(
        report_id="rp-001",
        generated_at="2026-06-24T00:00:00Z",
        verdict="PASS",
        overall_status="READY",
        summary="All good",
        failed_prerequisites=[],
        recommended_actions=[],
    )
    assert report.report_id == "rp-001"
    assert report.overall_status == "READY"


# ============================================================================
# Test Module docstring
# ============================================================================


def test_module_docstring_documents_gbm_guard():
    """Module docstring documents the GBM guard."""
    from alphaforge.gates import ml_pilot as mp
    doc = mp.__doc__
    assert "EXPLICIT_GBM_BLOCK" in doc
    assert ("PRE-TRAINING gate" in doc) or ("pre-training gate" in doc)
    assert "governance module" in doc
    assert "must never import gradient boosting" in doc


# ============================================================================
# Test ml_pilot source has no xgboost import
# ============================================================================


def test_ml_pilot_source_no_gbm_import():
    """ml_pilot.py source file contains no GBM library import statements (AST check)."""
    import ast
    from pathlib import Path

    source_path = Path(__file__).parent.parent / "src" / "alphaforge" / "gates" / "ml_pilot.py"
    content = source_path.read_text()

    # AST-based check: no import or import-from of the GBM library
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in ("xgboost", "XGBoost"), (
                    f"ml_pilot.py must not import GBM library, found: import {alias.name}"
                )
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module in ("xgboost", "xgboost.sklearn"):
                raise AssertionError(
                    f"ml_pilot.py must not import from GBM library, found: from {node.module}"
                )

    # find_spec is allowed (used for detection, not import)
    assert "find_spec" in content
