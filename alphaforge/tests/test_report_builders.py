"""Test report builders: deterministic, non-profit, no fake evidence."""

from alphaforge.reports import (
    build_minimal_validation_report,
    build_minimal_mode_research_report,
    build_minimal_handoff_package,
    CANONICAL_V7_GATES,
)


def test_validation_report_deterministic():
    r1 = build_minimal_validation_report(mode="SWING")
    r2 = build_minimal_validation_report(mode="SWING")
    r1_no_time = {k: v for k, v in r1.items() if k != "created_at"}
    r2_no_time = {k: v for k, v in r2.items() if k != "created_at"}
    assert r1_no_time == r2_no_time


def test_validation_report_required_fields():
    r = build_minimal_validation_report(mode="SWING")
    assert r["verdict"] == "BLOCKED_FOR_MHT"
    assert len(r["walk_forward_folds"]["folds"]) == 6
    assert r["walk_forward_folds"]["fold_count"] == 6


def test_validation_report_mht_blocked():
    r = build_minimal_validation_report(mode="SWING")
    mht = r["multiple_hypothesis_control"]
    assert mht["mht_status"] == "NOT_RUN"
    assert "mht_block_reason" in mht


def test_mode_research_report_no_fake_profitability():
    r = build_minimal_mode_research_report(mode="SCALP")
    assert r["verdict"] == "BLOCKED_FOR_MHT"
    assert "no real profitability" in " ".join(r["blocked_scopes"]).lower()


def test_mode_research_report_correct_timeframes():
    swing = build_minimal_mode_research_report(mode="SWING")
    assert "4h" in swing["data_scope"]["primary_timeframes"]
    scalp = build_minimal_mode_research_report(mode="SCALP")
    assert "1h" in scalp["data_scope"]["primary_timeframes"]
    agg = build_minimal_mode_research_report(mode="AGGRESSIVE_SCALP")
    assert "15m" in agg["data_scope"]["primary_timeframes"]


def test_handoff_package_uses_canonical_gates():
    pkg = build_minimal_handoff_package(mode="SWING")
    for gate in CANONICAL_V7_GATES:
        assert gate in pkg["v7_gate_mapping"]


def test_handoff_package_no_profitability_claim():
    pkg = build_minimal_handoff_package(mode="SWING")
    assert "No real profitability evidence exists" in " ".join(pkg["blocked_scopes"])


def test_cost_stress_has_funding_deferred():
    r = build_minimal_validation_report(mode="SWING")
    cs = r["cost_stress"]
    assert "spread_or_proxy" in cs
    assert "DEFERRED" in cs["funding_or_deferred_block"]
