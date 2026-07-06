"""Test handoff builder: canonical gates, no old names, promotion blocking, empirical handoff."""

import pytest
from alphaforge.handoff import (
    build_handoff_package, validate_gate_mapping,
    assert_no_old_gate_names, is_promotion_blocked,
    build_empirical_handoff_package, build_empirical_handoffs,
)
from alphaforge.errors import GateMappingError, HandoffBlockedError, ModeError, HandoffBuildError
from alphaforge.reports import CANONICAL_V7_GATES, FORBIDDEN_GATE_NAMES
from alphaforge.constants import HANDOFF_REVIEW_REQUIRED, HANDOFF_PROMOTION_CANDIDATE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_empirical_mrr(
    mode: str = "SWING",
    verdict: str = "CANDIDATE_FOR_V7_GATES",
    oos_expectancy_r: float = 0.15,
    oos_sharpe: float = 0.8,
    oos_trade_count: int = 300,
    fold_count: int = 6,
    combined_stress_edge_survives: bool = True,
    edge_only_in_rare_regime: bool = False,
    symbols: list[str] | None = None,
    extra: dict | None = None,
) -> dict:
    """Build a deterministic empirical ModeResearchReport dict for testing."""
    if symbols is None:
        symbols = ["BTCUSDT", "ETHUSDT"]

    try:
        from alphaforge.reports.empirical import build_empirical_mode_research_report, _make_per_fold_metrics
    except ImportError:
        # Fallback: build manually
        _make_per_fold_metrics = None

    if _make_per_fold_metrics is not None:
        wfv = {
            "fold_count": fold_count,
            "per_fold_metrics": _make_per_fold_metrics(
                count=fold_count, sharpe=oos_sharpe, expectancy_r=oos_expectancy_r,
            ),
            "oos_summary": {
                "oos_sharpe": oos_sharpe,
                "oos_expectancy_r": oos_expectancy_r,
                "oos_win_rate": 0.55,
                "oos_profit_factor": 1.3,
                "oos_max_drawdown_r": -2.5,
                "oos_trade_count": oos_trade_count,
            },
            "data_scope": {
                "symbols": symbols,
                "date_range_start": "2025-01-01T00:00:00Z",
                "date_range_end": "2026-01-01T00:00:00Z",
            },
            "cost_stress": {
                "baseline_fee_pct": 0.04,
                "baseline_slippage_pct": 0.02,
                "fee_stress_levels": [
                    {"multiplier": 1.0, "oos_expectancy_r": 0.12, "edge_survives": True},
                ],
                "slippage_stress_levels": [
                    {"multiplier": 1.0, "oos_expectancy_r": 0.12, "edge_survives": True},
                ],
                "combined_stress_edge_survives": combined_stress_edge_survives,
                "break_even_cost_total_pct": 0.15,
                "net_edge_after_costs": 0.08,
            },
            "regime_breakdown": {
                "regimes": [
                    {"regime": "TREND_UP", "sample_pct": 0.30, "oos_expectancy_r": 0.20, "edge_present": True},
                    {"regime": "TREND_DOWN", "sample_pct": 0.25, "oos_expectancy_r": 0.10, "edge_present": True},
                    {"regime": "RANGE", "sample_pct": 0.30, "oos_expectancy_r": 0.08, "edge_present": True},
                    {"regime": "TRANSITION", "sample_pct": 0.15, "oos_expectancy_r": 0.05, "edge_present": True},
                ],
                "edge_only_in_rare_regime": edge_only_in_rare_regime,
            },
            "no_trade_comparison": {"active_beats_no_trade": True},
            "multiple_hypothesis_control": {
                "correction_method": "Bonferroni",
                "tested_hypothesis_count": 1,
                "rejected_candidate_count": 0,
                "p_values": [],
            },
        }
        if extra:
            wfv.update(extra)
        return build_empirical_mode_research_report(mode, wfv)

    # Manual fallback
    tf = {"SWING": "4h", "SCALP": "1h", "AGGRESSIVE_SCALP": "15m"}[mode]
    ctx = {"SWING": "1d", "SCALP": "4h", "AGGRESSIVE_SCALP": "1h"}[mode]
    priority = "SECONDARY_BASELINE" if mode == "SWING" else "PRIMARY"
    rtype = "secondary_baseline_report" if mode == "SWING" else "primary_research_report"
    base = {
        "schema_version": "1.0.0",
        "report_id": f"mrr-{mode.lower()}-test-001",
        "mode": mode,
        "mode_priority": priority,
        "report_type": rtype,
        "data_scope": {
            "symbols": symbols,
            "date_range_start": "2025-01-01T00:00:00Z",
            "date_range_end": "2026-01-01T00:00:00Z",
            "primary_timeframes": [tf],
            "secondary_timeframes": [ctx],
        },
        "feature_set_refs": [f"fs-{mode.lower()}-test-001"],
        "label_dataset_refs": [f"lds-{mode.lower()}-test-001"],
        "alpha_theses": [{"alpha_thesis_id": f"ath-{mode.lower()}-test-001"}],
        "validation_summary": {
            "validation_report_id": f"vr-{mode.lower()}-test-001",
            "fold_count": fold_count,
        },
        "metrics": {
            "oos_expectancy_r": {"value": oos_expectancy_r},
            "oos_sharpe": {"value": oos_sharpe},
            "oos_win_rate": {"value": 0.55},
            "oos_profit_factor": {"value": 1.3},
            "oos_max_drawdown_r": {"value": -2.5},
            "oos_trade_count": oos_trade_count,
        },
        "cost_stress": {
            "combined_stress_edge_survives": combined_stress_edge_survives,
            "break_even_cost_total_pct": 0.15,
        },
        "regime_breakdown": {
            "regimes": [
                {"regime": "TREND_UP", "oos_expectancy_r": 0.20, "edge_present": True},
                {"regime": "TREND_DOWN", "oos_expectancy_r": 0.10, "edge_present": True},
                {"regime": "RANGE", "oos_expectancy_r": 0.08, "edge_present": True},
                {"regime": "TRANSITION", "oos_expectancy_r": 0.05, "edge_present": True},
            ],
            "edge_only_in_rare_regime": edge_only_in_rare_regime,
        },
        "multiple_hypothesis_control": {
            "correction_method": "Bonferroni",
            "data_snooping_risk_flag": "LOW",
            "pbo_or_backtest_overfit_risk": "LOW",
            "deflated_sharpe_or_equivalent": 0.5,
            "mht_computed_for_real": True,
        },
        "verdict": verdict,
        "blocked_scopes": ["Test scope"],
        "limitations": ["Test limitation"],
    }
    if extra:
        base.update(extra)
    return base


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


# ═══════════════════════════════════════════════════════════════════════════
# Empirical Handoff — build_empirical_handoff_package
# ═══════════════════════════════════════════════════════════════════════════

class TestEmpiricalHandoffBuilder:
    """Tests for build_empirical_handoff_package."""

    def _make_handoff(self, mode="SWING", **kwargs) -> dict:
        """Build an empirical report and then a handoff from it."""
        report = _make_empirical_mrr(mode=mode, **kwargs)
        return build_empirical_handoff_package(mode, report)

    def test_swing_handoff_builds_and_validates(self):
        """SWING empirical handoff builds and validates against schema."""
        handoff = self._make_handoff("SWING")
        assert handoff["mode"] == "SWING"
        assert handoff["schema_version"] == "1.0.0"
        assert "handoff_package_id" in handoff

    def test_scalp_handoff_builds(self):
        """SCALP empirical handoff builds."""
        handoff = self._make_handoff("SCALP")
        assert handoff["mode"] == "SCALP"

    def test_aggressive_scalp_handoff_builds(self):
        """AGGRESSIVE_SCALP empirical handoff builds."""
        handoff = self._make_handoff("AGGRESSIVE_SCALP")
        assert handoff["mode"] == "AGGRESSIVE_SCALP"

    def test_all_11_gates_present(self):
        """All 11 canonical gates present in handoff."""
        handoff = self._make_handoff("SWING")
        gate_ids = set(handoff["v7_gate_mapping"].keys())
        assert gate_ids == set(CANONICAL_V7_GATES)

    def test_gate_entries_have_evidence_ref_and_status(self):
        """Each gate entry has evidence_ref (str) and status (PASS|PENDING|NOT_EVALUATED)."""
        handoff = self._make_handoff("SWING")
        for gate_id in CANONICAL_V7_GATES:
            entry = handoff["v7_gate_mapping"][gate_id]
            assert "evidence_ref" in entry, f"{gate_id} missing evidence_ref"
            assert isinstance(entry["evidence_ref"], str), f"{gate_id} evidence_ref not str"
            assert "status" in entry, f"{gate_id} missing status"
            assert entry["status"] in ("PASS", "PENDING", "NOT_EVALUATED"), (
                f"{gate_id} invalid status: {entry['status']}"
            )

    def test_g0_g1_pass_for_promotion_candidate(self):
        """G0 (DOC_READY) and G1 (RESEARCH_BACKTEST) PASS for CANDIDATE_FOR_V7_GATES.

        P0.9F: G1 now requires PBO/DS checks. Patch _MHT_AVAILABLE so
        the builder generates real MHT data and G1 can PASS.
        """
        import alphaforge.reports.empirical as mod_emp
        orig = mod_emp._MHT_AVAILABLE
        mod_emp._MHT_AVAILABLE = True
        try:
            handoff = self._make_handoff("SWING", verdict="CANDIDATE_FOR_V7_GATES")
        finally:
            mod_emp._MHT_AVAILABLE = orig
        gm = handoff["v7_gate_mapping"]
        assert gm["G0_doc_ready"]["status"] == "PASS"
        assert gm["G1_research_backtest"]["status"] == "PASS"

    def test_g2_passes_for_validated_verdicts(self):
        """G2 (WALK_FORWARD_OOS) PASS for BASELINE_VALID and CANDIDATE_FOR_V7_GATES."""
        for verdict in ("BASELINE_VALID", "CANDIDATE_FOR_V7_GATES"):
            handoff = self._make_handoff("SWING", verdict=verdict)
            assert handoff["v7_gate_mapping"]["G2_walk_forward_oos"]["status"] == "PASS"

    def test_g2_pending_for_continue_research(self):
        """G2 PENDING for CONTINUE_RESEARCH."""
        handoff = self._make_handoff("SWING", verdict="CONTINUE_RESEARCH")
        assert handoff["v7_gate_mapping"]["G2_walk_forward_oos"]["status"] == "PENDING"

    def test_g3_passes_when_cost_survives(self):
        """G3 (COST_STRESS) PASS when combined_stress_edge_survives=True."""
        handoff = self._make_handoff("SWING", combined_stress_edge_survives=True)
        assert handoff["v7_gate_mapping"]["G3_cost_stress"]["status"] == "PASS"

    def test_g3_pending_when_cost_destroyed(self):
        """G3 PENDING when combined_stress_edge_survives=False."""
        handoff = self._make_handoff("SWING", combined_stress_edge_survives=False)
        assert handoff["v7_gate_mapping"]["G3_cost_stress"]["status"] == "PENDING"

    def test_g4_passes_when_regime_stable(self):
        """G4 (REGIME_BREAKDOWN) PASS when edge_only_in_rare_regime=False."""
        handoff = self._make_handoff("SWING", edge_only_in_rare_regime=False)
        assert handoff["v7_gate_mapping"]["G4_regime_breakdown"]["status"] == "PASS"

    def test_g4_pending_when_edge_only_rare(self):
        """G4 PENDING when edge_only_in_rare_regime=True."""
        handoff = self._make_handoff("SWING", edge_only_in_rare_regime=True)
        assert handoff["v7_gate_mapping"]["G4_regime_breakdown"]["status"] == "PENDING"

    def test_g5_passes_with_multi_symbol(self):
        """G5 (SYMBOL_STABILITY) PASS when >=2 symbols."""
        handoff = self._make_handoff("SWING", symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        assert handoff["v7_gate_mapping"]["G5_symbol_stability"]["status"] == "PASS"

    def test_g5_pending_with_single_symbol(self):
        """G5 PENDING when single symbol."""
        handoff = self._make_handoff("SWING", symbols=["BTCUSDT"])
        assert handoff["v7_gate_mapping"]["G5_symbol_stability"]["status"] == "PENDING"

    def test_g6_always_pending(self):
        """G6 (CALIBRATION_RELIABILITY) always PENDING (needs CalibrationCandidate)."""
        handoff = self._make_handoff("SWING")
        assert handoff["v7_gate_mapping"]["G6_calibration_reliability"]["status"] == "PENDING"

    def test_g7_to_g10_always_not_evaluated(self):
        """G7-G10 always NOT_EVALUATED (infrastructure not built)."""
        handoff = self._make_handoff("SWING")
        for g in ("G7_shadow", "G8_paper", "G9_tiny_live", "G10_live"):
            assert handoff["v7_gate_mapping"][g]["status"] == "NOT_EVALUATED"

    # ── recommended_status tests ────────────────────────────────────────────

    def test_promotion_candidate_verdict_maps_to_promotion_candidate(self):
        """CANDIDATE_FOR_V7_GATES → PROMOTION_CANDIDATE."""
        handoff = self._make_handoff("SWING", verdict="CANDIDATE_FOR_V7_GATES")
        assert handoff["recommended_status"] == HANDOFF_PROMOTION_CANDIDATE

    def test_baseline_valid_maps_to_review_required(self):
        """BASELINE_VALID → REVIEW_REQUIRED."""
        handoff = self._make_handoff("SWING", verdict="BASELINE_VALID")
        assert handoff["recommended_status"] == HANDOFF_REVIEW_REQUIRED

    def test_continue_research_maps_to_review_required(self):
        """CONTINUE_RESEARCH → REVIEW_REQUIRED."""
        handoff = self._make_handoff("SWING", verdict="CONTINUE_RESEARCH")
        assert handoff["recommended_status"] == HANDOFF_REVIEW_REQUIRED

    def test_reject_verdict_maps_to_review_required(self):
        """REJECT → REVIEW_REQUIRED."""
        handoff = self._make_handoff("SWING", verdict="REJECT")
        assert handoff["recommended_status"] == HANDOFF_REVIEW_REQUIRED

    # ── Lineage tests ───────────────────────────────────────────────────────

    def test_lineage_has_required_fields(self):
        """Lineage has all required fields: data_refs, feature_set_id, label_dataset_id, simulation_profile_id, lineage_verified."""
        handoff = self._make_handoff("SWING")
        lineage = handoff["lineage"]
        required = {"data_refs", "feature_set_id", "label_dataset_id",
                     "simulation_profile_id", "lineage_verified"}
        assert required.issubset(set(lineage.keys()))

    def test_lineage_data_refs_from_symbols(self):
        """data_refs derived from report data_scope.symbols."""
        handoff = self._make_handoff("SWING", symbols=["BTCUSDT", "ETHUSDT"])
        refs = handoff["lineage"]["data_refs"]
        assert any("btcusdt" in r.lower() for r in refs)
        assert any("ethusdt" in r.lower() for r in refs)

    def test_lineage_simulation_profile_id(self):
        """simulation_profile_id follows mode pattern."""
        handoff = self._make_handoff("SWING")
        assert "swing" in handoff["lineage"]["simulation_profile_id"]

    def test_lineage_not_verified(self):
        """lineage_verified is False (no binary checksum)."""
        handoff = self._make_handoff("SWING")
        assert handoff["lineage"]["lineage_verified"] is False

    def test_lineage_feature_set_id_from_report(self):
        """feature_set_id extracted from report's feature_set_refs."""
        report = _make_empirical_mrr("SWING")
        expected = report["feature_set_refs"][0]
        handoff = build_empirical_handoff_package("SWING", report)
        assert handoff["lineage"]["feature_set_id"] == expected

    # ── Blocked scopes and limitations ──────────────────────────────────────

    def test_blocked_scopes_from_report_carried_through(self):
        """blocked_scopes from report are present in handoff."""
        report = _make_empirical_mrr("SWING")
        handoff = build_empirical_handoff_package("SWING", report)
        assert "Test scope" in " ".join(handoff["blocked_scopes"])

    def test_limitations_from_report_carried_through(self):
        """limitations from report are present in handoff."""
        report = _make_empirical_mrr("SWING")
        handoff = build_empirical_handoff_package("SWING", report)
        assert "Test limitation" in " ".join(handoff["limitations"])

    def test_funding_deferred_in_blocked_scopes(self):
        """Funding DEFERRED always in blocked_scopes."""
        handoff = self._make_handoff("SWING")
        assert "DEFERRED" in " ".join(handoff["blocked_scopes"])

    # ── Schema validation ───────────────────────────────────────────────────

    def test_schema_validation_passes(self):
        """Handoff validates against v7_handoff_package.schema.json."""
        from alphaforge.contracts.loader import load_schema
        from alphaforge.contracts.validator import validate_payload

        handoff = self._make_handoff("SWING")
        schema = load_schema("v7_handoff_package.schema.json")
        result = validate_payload(schema, handoff, "v7_handoff_package")
        assert result.valid, f"Schema validation failed: {result.errors}"

    def test_schema_validation_passes_all_modes(self):
        """All three modes produce schema-valid handoffs."""
        from alphaforge.contracts.loader import load_schema
        from alphaforge.contracts.validator import validate_payload

        schema = load_schema("v7_handoff_package.schema.json")
        for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
            handoff = self._make_handoff(mode)
            result = validate_payload(schema, handoff, f"v7_handoff_package({mode})")
            assert result.valid, f"{mode} failed schema: {result.errors}"

    # ── Rejection rules ─────────────────────────────────────────────────────

    def test_rejection_rules_applied_present(self):
        """rejection_rules_applied is present and non-empty."""
        handoff = self._make_handoff("SWING")
        rules = handoff.get("rejection_rules_applied", [])
        assert len(rules) == 12

    # ── Error handling ──────────────────────────────────────────────────────

    def test_unknown_mode_raises(self):
        """Unknown mode raises ModeError."""
        with pytest.raises(ModeError):
            build_empirical_handoff_package("INVALID", {})

    def test_empty_report_still_produces_valid_package(self):
        """Empty report produces a valid package with default values."""
        report = {
            "data_scope": {"symbols": ["BTCUSDT"]},
            "metrics": {},
            "verdict": "REJECT",
            "blocked_scopes": [],
            "limitations": [],
        }
        handoff = build_empirical_handoff_package("SWING", report)
        assert handoff["mode"] == "SWING"
        assert len(handoff["v7_gate_mapping"]) == 11

    # ── Rejection rules for all 12 rules ────────────────────────────────────

    def test_rejection_rules_contain_all_rules(self):
        """All 12 rejection rules are listed in rejection_rules_applied."""
        handoff = self._make_handoff("SWING")
        rules_text = " ".join(handoff["rejection_rules_applied"])
        for i in range(1, 13):
            assert f"Rule {i}" in rules_text, f"Rule {i} not found in rejection_rules_applied"

    def test_no_old_gate_names_in_empirical_handoff(self):
        """No forbidden gate names appear in empirical handoff."""
        handoff = self._make_handoff("SWING")
        pkg_text = str(handoff)
        for old in FORBIDDEN_GATE_NAMES:
            assert old not in pkg_text, f"Old gate name found: {old}"

    def test_empirical_handoff_json_serializable(self):
        """Handoff is JSON serializable."""
        import json
        handoff = self._make_handoff("SWING")
        encoded = json.dumps(handoff)
        assert isinstance(encoded, str)

    def test_custom_ids_override_defaults(self):
        """Custom IDs are used when provided."""
        report = _make_empirical_mrr("SWING")
        handoff = build_empirical_handoff_package(
            "SWING", report,
            handoff_package_id="custom-pkg-001",
            validation_report_id="custom-vr-001",
            model_artifact_id="custom-ma-001",
            calibration_candidate_id="custom-cc-001",
        )
        assert handoff["handoff_package_id"] == "custom-pkg-001"
        assert handoff["validation_report_id"] == "custom-vr-001"
        assert handoff["model_artifact_id"] == "custom-ma-001"
        assert handoff["calibration_candidate_id"] == "custom-cc-001"

    def test_custom_alpha_candidate_id_from_report(self):
        """alpha_candidate_id uses first alpha_thesis.alpha_thesis_id."""
        report = _make_empirical_mrr("SWING")
        if report.get("alpha_theses"):
            expected = report["alpha_theses"][0]["alpha_thesis_id"]
            handoff = build_empirical_handoff_package("SWING", report)
            assert handoff["alpha_candidate_id"] == expected


class TestEmpiricalHandoffsBatch:
    """Tests for build_empirical_handoffs."""

    def test_builds_all_three_modes(self):
        """build_empirical_handoffs returns packages for all 3 modes."""
        reports = {
            mode: _make_empirical_mrr(mode)
            for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP")
        }
        handoffs = build_empirical_handoffs(reports)
        assert set(handoffs.keys()) == {"SWING", "SCALP", "AGGRESSIVE_SCALP"}
        assert all(h["mode"] == m for m, h in handoffs.items())

    def test_all_schema_valid(self):
        """All 3 handoffs validate against schema."""
        from alphaforge.contracts.loader import load_schema
        from alphaforge.contracts.validator import validate_payload

        schema = load_schema("v7_handoff_package.schema.json")
        reports = {
            mode: _make_empirical_mrr(mode)
            for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP")
        }
        handoffs = build_empirical_handoffs(reports)
        for mode, handoff in handoffs.items():
            result = validate_payload(schema, handoff, f"v7_handoff_package({mode})")
            assert result.valid, f"{mode} failed schema: {result.errors}"
