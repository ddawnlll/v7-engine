"""Test handoff builder: canonical gates, no old names, promotion blocking."""

import pytest
from alphaforge.handoff import (
    build_handoff_package, validate_gate_mapping,
    assert_no_old_gate_names, is_promotion_blocked,
)
from alphaforge.errors import GateMappingError, HandoffBlockedError
from alphaforge.reports import CANONICAL_V7_GATES, FORBIDDEN_GATE_NAMES


def test_build_minimal_handoff_uses_canonical_gates():
    pkg = build_handoff_package(mode="SWING")
    for gate in CANONICAL_V7_GATES:
        assert gate in pkg["v7_gate_mapping"], f"Missing canonical gate: {gate}"


def test_build_handoff_no_old_gate_names():
    pkg = build_handoff_package(mode="SCALP")
    for old in FORBIDDEN_GATE_NAMES:
        assert old not in pkg["v7_gate_mapping"], f"Old gate leaked: {old}"


def test_validate_gate_mapping_rejects_old_names():
    bad = {"G3_model_sanity": "evidence", "G10_paper_shadow": "evidence"}
    with pytest.raises(GateMappingError) as exc:
        validate_gate_mapping(bad)
    assert "G3_model_sanity" in str(exc.value)


def test_validate_gate_mapping_rejects_missing():
    with pytest.raises(GateMappingError):
        validate_gate_mapping({"G0_doc_ready": "ok"})


def test_assert_no_old_gate_names_in_string():
    with pytest.raises(GateMappingError):
        assert_no_old_gate_names("refs G3_model_sanity in text")


def test_assert_no_old_gate_names_in_key():
    with pytest.raises(GateMappingError):
        assert_no_old_gate_names({"G10_paper_shadow": "bad"})


def test_promotion_blocked_for_review_required():
    pkg = build_handoff_package(mode="SWING")
    assert pkg["recommended_status"] == "REVIEW_REQUIRED"
    assert is_promotion_blocked(pkg)


def test_promotion_candidate_blocked_without_evidence():
    with pytest.raises(HandoffBlockedError):
        build_handoff_package(mode="SWING", recommended_status="PROMOTION_CANDIDATE")


def test_no_trade_not_a_promotion_gate():
    pkg = build_handoff_package(mode="SWING")
    gates = pkg["v7_gate_mapping"]
    assert "G9_no_trade_baseline" not in gates
    assert not any("no_trade" in k.lower() for k in gates)


def test_build_all_modes():
    for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
        pkg = build_handoff_package(mode=mode)
        assert pkg["mode"] == mode
        assert len(pkg["v7_gate_mapping"]) == 11


def test_funding_deferred_blocked():
    pkg = build_handoff_package(mode="SWING")
    assert "DEFERRED" in " ".join(pkg["blocked_scopes"])
