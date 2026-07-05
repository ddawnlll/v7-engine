"""Test report builders: deterministic, non-profit, no fake evidence."""

from alphaforge.reports import (
    build_minimal_validation_report,
    build_minimal_mode_research_report,
    build_minimal_handoff_package,
    build_alphaforge_research_report,
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


# ---------------------------------------------------------------------------
# AlphaForgeResearchReport tests (cross-mode aggregate)
# ---------------------------------------------------------------------------


def test_build_alphaforge_research_report_auto():
    """Auto-build generates a valid report with all 3 modes."""
    r = build_alphaforge_research_report()
    assert r["schema_version"] == "1.0.0"
    assert len(r["mode_reports"]) == 3
    modes = {m["mode"] for m in r["mode_reports"]}
    assert modes == {"SCALP", "AGGRESSIVE_SCALP", "SWING"}


def test_build_alphaforge_research_report_custom_id():
    """Custom report_id and run_id are respected."""
    r = build_alphaforge_research_report(
        report_id="afrr-custom-001",
        run_id="run-custom-001",
    )
    assert r["alphaforge_report_id"] == "afrr-custom-001"
    assert r["run_id"] == "run-custom-001"


def test_build_alphaforge_research_report_requires_three_modes():
    """Passing fewer than 3 modes raises ReportBuildError."""
    import pytest
    from alphaforge.errors import ReportBuildError
    from alphaforge.reports.builders import build_mode_research_report

    with pytest.raises(ReportBuildError, match="requires all 3 modes"):
        build_alphaforge_research_report(
            [build_mode_research_report("SCALP")]
        )


def test_build_alphaforge_research_report_bad_mode():
    """Passing mode reports with wrong mode raises ReportBuildError."""
    import pytest
    from alphaforge.errors import ReportBuildError

    bad_reports = [
        {"mode": "BAD_MODE", "verdict": "REJECT", "report_id": "x"},
        {"mode": "ALSO_BAD", "verdict": "REJECT", "report_id": "x"},
        {"mode": "WRONG", "verdict": "REJECT", "report_id": "x"},
    ]
    with pytest.raises(ReportBuildError, match="requires all 3 modes"):
        build_alphaforge_research_report(bad_reports)


def test_build_alphaforge_research_report_missing_keys():
    """Passing mode reports without mode/verdict raises ReportBuildError."""
    import pytest
    from alphaforge.errors import ReportBuildError

    with pytest.raises(ReportBuildError, match="must have 'mode' and 'verdict'"):
        build_alphaforge_research_report([
            {"mode": "SCALP", "verdict": "REJECT"},
            {"mode": "AGGRESSIVE_SCALP", "verdict": "REJECT"},
            {"oops": "missing_verdict"},
        ])


def test_build_alphaforge_research_report_mode_summaries():
    """Mode report summaries contain the right keys per schema."""
    r = build_alphaforge_research_report()
    for m in r["mode_reports"]:
        assert "mode" in m
        assert "mode_priority" in m
        assert "report_id" in m
        assert "report_type" in m
        assert "verdict" in m
        assert "summary" in m


def test_build_alphaforge_research_report_mode_report_types():
    """PRIMARY modes get primary_research_report; SWING gets secondary_baseline_report."""
    r = build_alphaforge_research_report()
    type_map = {m["mode"]: m["report_type"] for m in r["mode_reports"]}
    assert type_map["SCALP"] == "primary_research_report"
    assert type_map["AGGRESSIVE_SCALP"] == "primary_research_report"
    assert type_map["SWING"] == "secondary_baseline_report"


def test_build_alphaforge_research_report_promoted_candidates():
    """Modes with CANDIDATE_FOR_V7_GATES verdict appear in promoted_candidates."""
    reports = [
        {"mode": "SCALP", "verdict": "CANDIDATE_FOR_V7_GATES", "report_id": "mrr-scalp-001",
         "mode_priority": "PRIMARY", "report_type": "primary_research_report",
         "limitations": ["Test limitation"], "blocked_scopes": ["Test blocked"],
         "metrics": {}, "multiple_hypothesis_control": {},
         "cost_stress": {}, "regime_breakdown": {}, "v7_gate_readiness": {},
         "validation_summary": {}, "data_scope": {}},
        {"mode": "AGGRESSIVE_SCALP", "verdict": "REJECT", "report_id": "mrr-agg-001",
         "mode_priority": "PRIMARY", "report_type": "primary_research_report",
         "limitations": ["Test limitation"], "blocked_scopes": ["Test blocked"],
         "metrics": {}, "multiple_hypothesis_control": {},
         "cost_stress": {}, "regime_breakdown": {}, "v7_gate_readiness": {},
         "validation_summary": {}, "data_scope": {}},
        {"mode": "SWING", "verdict": "CONTINUE_RESEARCH", "report_id": "mrr-swing-001",
         "mode_priority": "SECONDARY_BASELINE", "report_type": "secondary_baseline_report",
         "limitations": ["Test limitation"], "blocked_scopes": ["Test blocked"],
         "metrics": {}, "multiple_hypothesis_control": {},
         "cost_stress": {}, "regime_breakdown": {}, "v7_gate_readiness": {},
         "validation_summary": {}, "data_scope": {}},
    ]
    r = build_alphaforge_research_report(reports, report_id="afrr-test-promoted")
    assert len(r["promoted_candidates"]) == 1
    assert r["promoted_candidates"][0]["mode"] == "SCALP"
    assert "CANDIDATE_FOR_V7_GATES" in r["promoted_candidates"][0]["reason"]


def test_build_alphaforge_research_report_rejected_candidates():
    """Modes with REJECT/INCONCLUSIVE/BASELINE_WEAK appear in rejected_candidates."""
    reports = [
        {"mode": "SCALP", "verdict": "REJECT", "report_id": "mrr-scalp-001",
         "mode_priority": "PRIMARY", "report_type": "primary_research_report",
         "limitations": ["Test"], "blocked_scopes": ["DEFERRED"],
         "metrics": {}, "multiple_hypothesis_control": {},
         "cost_stress": {}, "regime_breakdown": {}, "v7_gate_readiness": {},
         "validation_summary": {}, "data_scope": {}},
        {"mode": "AGGRESSIVE_SCALP", "verdict": "INCONCLUSIVE", "report_id": "mrr-agg-001",
         "mode_priority": "PRIMARY", "report_type": "primary_research_report",
         "limitations": ["Test"], "blocked_scopes": ["DEFERRED"],
         "metrics": {}, "multiple_hypothesis_control": {},
         "cost_stress": {}, "regime_breakdown": {}, "v7_gate_readiness": {},
         "validation_summary": {}, "data_scope": {}},
        {"mode": "SWING", "verdict": "BASELINE_WEAK", "report_id": "mrr-swing-001",
         "mode_priority": "SECONDARY_BASELINE", "report_type": "secondary_baseline_report",
         "limitations": ["Test"], "blocked_scopes": ["DEFERRED"],
         "metrics": {}, "multiple_hypothesis_control": {},
         "cost_stress": {}, "regime_breakdown": {}, "v7_gate_readiness": {},
         "validation_summary": {}, "data_scope": {}},
    ]
    r = build_alphaforge_research_report(reports, report_id="afrr-test-rejected")
    assert len(r["rejected_candidates"]) == 3
    verdicts = {c["mode"]: c["rejection_reason"] for c in r["rejected_candidates"]}
    assert "REJECT" in verdicts["SCALP"]
    assert "INCONCLUSIVE" in verdicts["AGGRESSIVE_SCALP"]
    assert "BASELINE_WEAK" in verdicts["SWING"]


def test_build_alphaforge_research_report_continue_research_is_rejected():
    """CONTINUE_RESEARCH is treated as rejected (not promoted)."""
    reports = [
        {"mode": "SCALP", "verdict": "CONTINUE_RESEARCH", "report_id": "mrr-scalp-001",
         "mode_priority": "PRIMARY", "report_type": "primary_research_report",
         "limitations": ["Test"], "blocked_scopes": ["DEFERRED"],
         "metrics": {}, "multiple_hypothesis_control": {},
         "cost_stress": {}, "regime_breakdown": {}, "v7_gate_readiness": {},
         "validation_summary": {}, "data_scope": {}},
        {"mode": "AGGRESSIVE_SCALP", "verdict": "CONTINUE_RESEARCH", "report_id": "mrr-agg-001",
         "mode_priority": "PRIMARY", "report_type": "primary_research_report",
         "limitations": ["Test"], "blocked_scopes": ["DEFERRED"],
         "metrics": {}, "multiple_hypothesis_control": {},
         "cost_stress": {}, "regime_breakdown": {}, "v7_gate_readiness": {},
         "validation_summary": {}, "data_scope": {}},
        {"mode": "SWING", "verdict": "CONTINUE_RESEARCH", "report_id": "mrr-swing-001",
         "mode_priority": "SECONDARY_BASELINE", "report_type": "secondary_baseline_report",
         "limitations": ["Test"], "blocked_scopes": ["DEFERRED"],
         "metrics": {}, "multiple_hypothesis_control": {},
         "cost_stress": {}, "regime_breakdown": {}, "v7_gate_readiness": {},
         "validation_summary": {}, "data_scope": {}},
    ]
    r = build_alphaforge_research_report(reports, report_id="afrr-test-continue")
    assert len(r["promoted_candidates"]) == 0
    assert len(r["rejected_candidates"]) == 3
    for c in r["rejected_candidates"]:
        assert "Further research required" in c["rejection_reason"]


def test_build_alphaforge_research_report_global_limitations():
    """Global limitations are extracted from individual mode report limitations."""
    reports = [
        {"mode": "SCALP", "verdict": "CONTINUE_RESEARCH", "report_id": "mrr-scalp-001",
         "mode_priority": "PRIMARY", "report_type": "primary_research_report",
         "limitations": ["L1: single symbol", "L2: funding deferred"],
         "blocked_scopes": ["Blocked by MHT", "DEFERRED"],
         "metrics": {}, "multiple_hypothesis_control": {},
         "cost_stress": {}, "regime_breakdown": {}, "v7_gate_readiness": {},
         "validation_summary": {}, "data_scope": {}},
        {"mode": "AGGRESSIVE_SCALP", "verdict": "CONTINUE_RESEARCH", "report_id": "mrr-agg-001",
         "mode_priority": "PRIMARY", "report_type": "primary_research_report",
         "limitations": ["L3: high frequency noise"],
         "blocked_scopes": ["Blocked by MHT", "DEFERRED"],
         "metrics": {}, "multiple_hypothesis_control": {},
         "cost_stress": {}, "regime_breakdown": {}, "v7_gate_readiness": {},
         "validation_summary": {}, "data_scope": {}},
        {"mode": "SWING", "verdict": "CONTINUE_RESEARCH", "report_id": "mrr-swing-001",
         "mode_priority": "SECONDARY_BASELINE", "report_type": "secondary_baseline_report",
         "limitations": ["L4: small sample"],
         "blocked_scopes": ["Blocked by MHT", "DEFERRED"],
         "metrics": {}, "multiple_hypothesis_control": {},
         "cost_stress": {}, "regime_breakdown": {}, "v7_gate_readiness": {},
         "validation_summary": {}, "data_scope": {}},
    ]
    r = build_alphaforge_research_report(reports, report_id="afrr-test-limits")
    all_limits = " ".join(r["global_limitations"])
    assert "L1:" in all_limits
    assert "L2:" in all_limits
    assert "L3:" in all_limits
    assert "L4:" in all_limits
    assert "DEFERRED" in all_limits


def test_build_alphaforge_research_report_mht_none_applied():
    """When no MHT correction is applied, aggregate reflects NONE_APPLIED."""
    reports = [
        {"mode": "SCALP", "verdict": "CONTINUE_RESEARCH", "report_id": "mrr-scalp-001",
         "mode_priority": "PRIMARY", "report_type": "primary_research_report",
         "limitations": ["Test"], "blocked_scopes": ["DEFERRED"],
         "metrics": {},
         "multiple_hypothesis_control": {
             "mht_status": "NOT_RUN", "correction_method": "NONE",
             "tested_hypothesis_count": 10, "tested_feature_count": 3,
             "trial_count_disclosure": 5,
         },
         "cost_stress": {}, "regime_breakdown": {}, "v7_gate_readiness": {},
         "validation_summary": {}, "data_scope": {}},
        {"mode": "AGGRESSIVE_SCALP", "verdict": "REJECT", "report_id": "mrr-agg-001",
         "mode_priority": "PRIMARY", "report_type": "primary_research_report",
         "limitations": ["Test"], "blocked_scopes": ["DEFERRED"],
         "metrics": {},
         "multiple_hypothesis_control": {
             "mht_status": "NONE_APPLIED", "correction_method": "NONE_APPLIED",
             "tested_hypothesis_count": 0, "tested_feature_count": 0,
             "trial_count_disclosure": 0,
         },
         "cost_stress": {}, "regime_breakdown": {}, "v7_gate_readiness": {},
         "validation_summary": {}, "data_scope": {}},
        {"mode": "SWING", "verdict": "CONTINUE_RESEARCH", "report_id": "mrr-swing-001",
         "mode_priority": "SECONDARY_BASELINE", "report_type": "secondary_baseline_report",
         "limitations": ["Test"], "blocked_scopes": ["DEFERRED"],
         "metrics": {},
         "multiple_hypothesis_control": {
             "mht_status": "NOT_RUN", "correction_method": "NONE",
             "tested_hypothesis_count": 5, "tested_feature_count": 1,
             "trial_count_disclosure": 2,
         },
         "cost_stress": {}, "regime_breakdown": {}, "v7_gate_readiness": {},
         "validation_summary": {}, "data_scope": {}},
    ]
    r = build_alphaforge_research_report(reports, report_id="afrr-test-mht")
    mht = r["multiple_hypothesis_control"]
    assert mht["aggregate_mht_status"] == "NOT_RUN"
    assert mht["aggregate_tested_hypothesis_count"] == 15
    assert mht["aggregate_tested_feature_count"] == 4
    assert mht["aggregate_trial_count"] == 7
    assert "BLOCKED" in mht["mht_block_reason"]


def test_build_alphaforge_research_report_mht_applied():
    """When MHT is applied in some modes, aggregate reflects that."""
    reports = [
        {"mode": "SCALP", "verdict": "CANDIDATE_FOR_V7_GATES", "report_id": "mrr-scalp-001",
         "mode_priority": "PRIMARY", "report_type": "primary_research_report",
         "limitations": ["Test"], "blocked_scopes": ["DEFERRED"],
         "metrics": {},
         "multiple_hypothesis_control": {
             "mht_status": "APPLIED_WITH_WARNINGS", "correction_method": "Bonferroni",
             "tested_hypothesis_count": 50, "tested_feature_count": 10,
             "trial_count_disclosure": 25,
         },
         "cost_stress": {}, "regime_breakdown": {}, "v7_gate_readiness": {},
         "validation_summary": {}, "data_scope": {}},
        {"mode": "AGGRESSIVE_SCALP", "verdict": "REJECT", "report_id": "mrr-agg-001",
         "mode_priority": "PRIMARY", "report_type": "primary_research_report",
         "limitations": ["Test"], "blocked_scopes": ["DEFERRED"],
         "metrics": {},
         "multiple_hypothesis_control": {
             "mht_status": "NONE_APPLIED", "correction_method": "NONE_APPLIED",
             "tested_hypothesis_count": 0, "tested_feature_count": 0, "trial_count_disclosure": 0,
         },
         "cost_stress": {}, "regime_breakdown": {}, "v7_gate_readiness": {},
         "validation_summary": {}, "data_scope": {}},
        {"mode": "SWING", "verdict": "BASELINE_VALID", "report_id": "mrr-swing-001",
         "mode_priority": "SECONDARY_BASELINE", "report_type": "secondary_baseline_report",
         "limitations": ["Test"], "blocked_scopes": ["DEFERRED"],
         "metrics": {},
         "multiple_hypothesis_control": {
             "mht_status": "APPLIED_AND_PASSED", "correction_method": "Benjamini-Hochberg",
             "tested_hypothesis_count": 30, "tested_feature_count": 5,
             "trial_count_disclosure": 15,
         },
         "cost_stress": {}, "regime_breakdown": {}, "v7_gate_readiness": {},
         "validation_summary": {}, "data_scope": {}},
    ]
    r = build_alphaforge_research_report(reports, report_id="afrr-test-mht-applied")
    mht = r["multiple_hypothesis_control"]
    assert mht["aggregate_mht_status"] in ("APPLIED_WITH_WARNINGS",)
    assert mht["aggregate_tested_hypothesis_count"] == 80
    assert mht["aggregate_tested_feature_count"] == 15
    assert "Bonferroni" in mht["correction_method"] or "Benjamini" in mht["correction_method"]


def test_build_alphaforge_research_report_v7_handoff_packages():
    """V7 handoff package references are included when provided."""
    r = build_alphaforge_research_report()
    assert "v7_handoff_packages" in r
    assert isinstance(r["v7_handoff_packages"], list)


def test_build_alphaforge_research_report_handoff_packages_custom():
    """Custom handoff packages appear in the report."""
    handoff_packages = [
        {"handoff_package_id": "v7hp-test-001", "mode": "SWING", "recommended_status": "REVIEW_REQUIRED"},
        {"handoff_package_id": "v7hp-test-002", "mode": "SCALP", "recommended_status": "REVIEW_REQUIRED"},
    ]
    r = build_alphaforge_research_report(
        handoff_packages=handoff_packages,
        report_id="afrr-test-hp",
    )
    assert len(r["v7_handoff_packages"]) == 2
    pkg_ids = {p["handoff_package_id"] for p in r["v7_handoff_packages"]}
    assert "v7hp-test-001" in pkg_ids
    assert "v7hp-test-002" in pkg_ids


def test_build_alphaforge_research_report_schema_validation():
    """Every AlphaForgeResearchReport passes schema validation."""
    from alphaforge.contracts.loader import load_schema
    from alphaforge.contracts.validator import validate_payload

    schema = load_schema("alphaforge_research_report.schema.json")
    r = build_alphaforge_research_report(report_id="afrr-schema-test")
    result = validate_payload(schema, r, "afrr-schema-test")
    assert result.valid, f"Schema validation failed: {result.errors}"


def test_build_alphaforge_research_report_cross_mode_insights():
    """Cross-mode insights are present and non-empty."""
    r = build_alphaforge_research_report(report_id="afrr-insights-test")
    assert len(r["cross_mode_insights"]) > 0
    assert any("PRIMARY" in i for i in r["cross_mode_insights"])


def test_build_alphaforge_research_report_next_priorities():
    """Next research priorities are present and non-empty."""
    r = build_alphaforge_research_report(report_id="afrr-priorities-test")
    assert len(r["next_research_priorities"]) > 0
    assert any("simulation" in p.lower() for p in r["next_research_priorities"])


def test_build_alphaforge_research_report_json_serializable():
    """AlphaForgeResearchReport can be round-tripped through JSON."""
    import json
    r = build_alphaforge_research_report(report_id="afrr-json-test")
    encoded = json.dumps(r)
    decoded = json.loads(encoded)
    assert decoded["alphaforge_report_id"] == "afrr-json-test"
    assert len(decoded["mode_reports"]) == 3


def test_build_alphaforge_research_report_with_real_empirical_reports():
    """Build with real empirical mode reports using various verdicts."""
    from alphaforge.reports.empirical import build_empirical_mode_research_report

    # Report with good metrics -> CANDIDATE_FOR_V7_GATES
    wfv_good = {
        'fold_count': 6,
        'per_fold_metrics': [
            {'fold': i+1, 'sharpe': 1.5, 'expectancy_r': 0.3, 'win_rate': 0.58, 'trade_count': 200}
            for i in range(6)
        ],
        'oos_summary': {'oos_sharpe': 1.5, 'oos_expectancy_r': 0.3, 'oos_win_rate': 0.58,
                         'oos_profit_factor': 1.8, 'oos_max_drawdown_r': -1.5, 'oos_trade_count': 1200},
        'metrics': {'active_trade_count': 800, 'long_trade_count': 400, 'short_trade_count': 400,
                     'no_trade_count': 400, 'total_gross_R': 200.0, 'total_net_R': 180.0,
                     'exposure_pct': 0.65, 'avg_net_R_per_active_trade': 0.225},
        'cost_stress': {'baseline_fee_pct': 0.04, 'baseline_slippage_pct': 0.02,
                         'fee_stress_levels': [{'multiplier': 1.0, 'oos_expectancy_r': 0.2, 'edge_survives': True}],
                         'slippage_stress_levels': [{'multiplier': 1.0, 'oos_expectancy_r': 0.18, 'edge_survives': True}],
                         'combined_stress_edge_survives': True,
                         'break_even_cost_total_pct': 0.05, 'net_edge_after_costs': 0.25},
        'regime_breakdown': {'edge_only_in_rare_regime': False,
                              'regimes': [{'regime': 'TREND_UP', 'sample_pct': 0.3, 'oos_expectancy_r': 0.35, 'edge_present': True},
                                           {'regime': 'TREND_DOWN', 'sample_pct': 0.25, 'oos_expectancy_r': 0.25, 'edge_present': True},
                                           {'regime': 'RANGE', 'sample_pct': 0.3, 'oos_expectancy_r': 0.2, 'edge_present': True},
                                           {'regime': 'TRANSITION', 'sample_pct': 0.15, 'oos_expectancy_r': 0.15, 'edge_present': True}]},
        'limitations': ['Single symbol only', 'Funding DEFERRED'],
    }
    # Report with bad metrics -> REJECT
    wfv_bad = dict(wfv_good)
    wfv_bad['oos_summary'] = {'oos_sharpe': -0.3, 'oos_expectancy_r': -0.05, 'oos_win_rate': 0.42,
                               'oos_profit_factor': 0.85, 'oos_max_drawdown_r': -4.0, 'oos_trade_count': 50}

    mr_scalp = build_empirical_mode_research_report('SCALP', wfv_good)
    mr_agg = build_empirical_mode_research_report('AGGRESSIVE_SCALP', wfv_bad)
    mr_swing = build_empirical_mode_research_report('SWING', wfv_good)

    r = build_alphaforge_research_report(
        [mr_scalp, mr_agg, mr_swing],
        report_id='afrr-empirical-test',
    )
    assert len(r["promoted_candidates"]) >= 1
    assert len(r["rejected_candidates"]) >= 1
    assert r["alphaforge_report_id"] == "afrr-empirical-test"
