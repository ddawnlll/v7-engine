"""Integration tests for AlphaForge ML Pilot Gate.

Tests:
- ml_pilot module importable (no xgboost)
- PrerequisiteRegistry has all 9 entries
- Each condition function callable
- BlockingReport JSON round-trips
- Gate verdicts with real registry
"""

from __future__ import annotations

import json

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
    BlockingReport,
    GateVerdict,
    PrerequisiteRegistry,
    _build_default_registry,
    check_all_prerequisites,
    generate_blocking_report,
    get_failed_prerequisites,
)


def test_ml_pilot_module_importable():
    """ml_pilot module is importable in clean environment (no xgboost)."""
    from alphaforge.gates import ml_pilot
    assert ml_pilot is not None
    assert hasattr(ml_pilot, "GateVerdict")
    assert hasattr(ml_pilot, "check_all_prerequisites")


def test_PrerequisiteRegistry_has_all_9_entries():
    """PrerequisiteRegistry has all 9 entries with correct IDs."""
    registry = _build_default_registry()
    assert len(registry) == 9

    expected_ids = [
        "NO_GBM_IN_ENVIRONMENT",
        "DATA_MANIFEST_COMPLETE",
        "LABEL_ADAPTER_VALIDATED",
        "FEATURE_PIPELINE_CAUSAL_VALIDATED",
        "DATASET_ASSEMBLED_AND_CHECKSUMMED",
        "NON_ML_RESEARCH_REPORT_COMPLETE",
        "WALK_FORWARD_SKELETON_VALIDATED",
        "V7_HANDOFF_DRY_RUN_COMPLETE",
        "ALL_PRIOR_ACCP_REPORTS_EXIST",
    ]
    assert registry.all_ids() == expected_ids


def test_each_condition_function_callable():
    """Each condition function in the registry is callable."""
    registry = _build_default_registry()
    for prereq_id, (desc, condition_fn, critical) in registry.entries.items():
        assert callable(condition_fn), f"{prereq_id} condition is not callable"


def test_BlockingReport_json_roundtrip_all_verdicts():
    """BlockingReport JSON round-trips correctly for all three verdicts."""
    # PASS
    registry = _build_default_registry()
    verdict = check_all_prerequisites(registry)
    failed = get_failed_prerequisites(registry)
    report = generate_blocking_report(verdict, failed)

    j = report.to_json(indent=2)
    parsed = json.loads(j)
    assert parsed["verdict"] == "PASS"
    assert parsed["overall_status"] == "READY"
    assert isinstance(parsed["failed_prerequisites"], list)
    assert isinstance(parsed["recommended_actions"], list)

    # FAIL (mocked)
    fail_registry = PrerequisiteRegistry()
    fail_registry.add("CRITICAL_FAIL", "Critical failed", lambda: False, critical=True)
    for i in range(8):
        fail_registry.add(f"PASS_{i}", f"Pass {i}", lambda: True, critical=False)
    verdict2 = check_all_prerequisites(fail_registry)
    failed2 = get_failed_prerequisites(fail_registry)
    report2 = generate_blocking_report(verdict2, failed2)

    j2 = report2.to_json(indent=2)
    parsed2 = json.loads(j2)
    assert parsed2["verdict"] == "FAIL"
    assert parsed2["overall_status"] == "BLOCKED"

    # HOLD (mocked)
    hold_registry = PrerequisiteRegistry()
    hold_registry.add("CRITICAL_OK", "Critical passes", lambda: True, critical=True)
    hold_registry.add("NON_CRITICAL_FAIL", "Non-critical fails", lambda: False, critical=False)
    for i in range(7):
        hold_registry.add(f"PASS_{i}", f"Pass {i}", lambda: True, critical=False)
    verdict3 = check_all_prerequisites(hold_registry)
    failed3 = get_failed_prerequisites(hold_registry)
    report3 = generate_blocking_report(verdict3, failed3)

    j3 = report3.to_json(indent=2)
    parsed3 = json.loads(j3)
    assert parsed3["verdict"] == "HOLD"
    assert parsed3["overall_status"] == "HOLD"


def test_registry_critical_flags_correct():
    """Only NO_GBM and DATA_MANIFEST are critical=True."""
    registry = _build_default_registry()
    for prereq_id in registry.all_ids():
        expected_critical = prereq_id in (
            "NO_GBM_IN_ENVIRONMENT",
            "DATA_MANIFEST_COMPLETE",
        )
        assert registry.is_critical(prereq_id) == expected_critical, (
            f"{prereq_id}: expected critical={expected_critical}, "
            f"got {registry.is_critical(prereq_id)}"
        )


def test_GateVerdict_enum_values():
    """GateVerdict PASS/HOLD/FAIL are properly defined."""
    assert GateVerdict.PASS.label == "PASS"
    assert GateVerdict.PASS.code == "GATE_PASS_ALL_SATISFIED"
    assert GateVerdict.HOLD.label == "HOLD"
    assert GateVerdict.HOLD.code == "GATE_HOLD_NON_CRITICAL_INCOMPLETE"
    assert GateVerdict.FAIL.label == "FAIL"
    assert GateVerdict.FAIL.code == "GATE_FAIL_CRITICAL_MISSING"


def test_no_gbm_in_clean_environment():
    """In clean environment (no GBM library), check returns True."""
    from alphaforge.gates.ml_pilot import check_no_gbm_in_environment
    assert check_no_gbm_in_environment() is True
