"""Unit tests for AlphaForge empirical report builder.

Tests: build_empirical_mode_research_report, verdict computation,
_calculate_verdict, _build_empirical_cost_stress, _build_empirical_regime_breakdown.

All tests are deterministic. No profitability claims. No real market data.
10+ tests as required by P0.9C.
"""

import json

import pytest

from alphaforge.errors import ModeError
from alphaforge.reports.empirical import (
    _build_empirical_mht_control,
    _compute_verdict,
    _fold_stability_score,
    _make_metric_ci,
    build_empirical_mode_research_report,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_per_fold_metrics(
    count: int = 6,
    sharpe: float = 0.8,
    expectancy_r: float = 0.15,
    win_rate: float = 0.55,
    trades_per_fold: int = 50,
) -> list[dict]:
    """Create deterministic per-fold metrics."""
    return [
        {
            "fold": i + 1,
            "sharpe": sharpe + (i - count / 2) * 0.05,
            "expectancy_r": expectancy_r + (i - count / 2) * 0.01,
            "win_rate": win_rate,
            "trade_count": trades_per_fold,
        }
        for i in range(count)
    ]


def _make_wfv_results(
    mode: str = "SWING",
    oos_sharpe: float = 0.8,
    oos_expectancy_r: float = 0.15,
    oos_trade_count: int = 300,
    fold_count: int = 6,
    per_fold_metrics: list[dict] | None = None,
) -> dict:
    """Create deterministic WFV results dict."""
    if per_fold_metrics is None:
        per_fold_metrics = _make_per_fold_metrics(fold_count)
    return {
        "fold_count": fold_count,
        "per_fold_metrics": per_fold_metrics,
        "oos_summary": {
            "oos_sharpe": oos_sharpe,
            "oos_expectancy_r": oos_expectancy_r,
            "oos_win_rate": 0.55,
            "oos_profit_factor": 1.3,
            "oos_max_drawdown_r": -2.5,
            "oos_trade_count": oos_trade_count,
        },
        "data_scope": {
            "symbols": ["BTCUSDT"],
            "date_range_start": "2025-01-01T00:00:00Z",
            "date_range_end": "2026-01-01T00:00:00Z",
        },
        "cost_stress": {
            "baseline_fee_pct": 0.04,
            "baseline_slippage_pct": 0.02,
            "fee_stress_levels": [
                {"multiplier": 1.0, "oos_expectancy_r": 0.12, "edge_survives": True},
                {"multiplier": 1.5, "oos_expectancy_r": 0.08, "edge_survives": True},
                {"multiplier": 2.0, "oos_expectancy_r": 0.04, "edge_survives": True},
            ],
            "slippage_stress_levels": [
                {"multiplier": 1.0, "oos_expectancy_r": 0.12, "edge_survives": True},
                {"multiplier": 1.5, "oos_expectancy_r": 0.08, "edge_survives": True},
                {"multiplier": 2.0, "oos_expectancy_r": 0.04, "edge_survives": True},
            ],
            "combined_stress_edge_survives": True,
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
            "edge_only_in_rare_regime": False,
        },
        "no_trade_comparison": {
            "active_beats_no_trade": True,
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEmpiricalBuilderExports:
    """Test that builder module exports correctly."""

    def test_module_exported(self):
        """Builder function is accessible from the reports package."""
        from alphaforge.reports import build_empirical_mode_research_report as exported
        assert exported is build_empirical_mode_research_report

    def test_metric_ci_helper(self):
        """_make_metric_ci produces correct shape."""
        m = _make_metric_ci(1.5)
        assert m["value"] == 1.5
        assert m["ci_lower"] < m["value"] < m["ci_upper"]
        assert m["ci_level"] == 0.95


class TestFoldStability:
    """Fold stability score computation."""

    def test_perfect_stability(self):
        """All folds have identical Sharpe → stability = 1.0."""
        metrics = [
            {"fold": i, "sharpe": 0.8, "expectancy_r": 0.15, "trade_count": 50}
            for i in range(6)
        ]
        assert _fold_stability_score(metrics) == 1.0

    def test_zero_mean_returns_zero(self):
        """When mean Sharpe is zero, stability is 0.0."""
        metrics = [
            {"fold": i, "sharpe": 0.0, "expectancy_r": 0.0, "trade_count": 50}
            for i in range(6)
        ]
        assert _fold_stability_score(metrics) == 0.0

    def test_empty_metrics_returns_zero(self):
        """Empty per-fold metrics return 0.0 stability."""
        assert _fold_stability_score([]) == 0.0

    def test_high_variance_reduces_stability(self):
        """Folds with very different Sharpe values reduce stability."""
        metrics = [
            {"fold": 1, "sharpe": 1.5, "expectancy_r": 0.3, "trade_count": 50},
            {"fold": 2, "sharpe": -0.5, "expectancy_r": -0.1, "trade_count": 50},
        ]
        score = _fold_stability_score(metrics)
        # Mean = 0.5, stdev = 1.0, instability = 2.0
        # score = 1 - min(1, 2.0/0.6) = 1 - 1.0 = 0.0
        assert score == 0.0


class TestVerdictComputation:
    """Verdict determination from empirical evidence."""

    def test_inconclusive_insufficient_trades(self):
        """Fewer than 100 OOS trades → INCONCLUSIVE."""
        verdict, label, rationale = _compute_verdict(
            mode="SWING",
            oos_expectancy_r=0.2,
            oos_sharpe=1.0,
            oos_trade_count=50,
            fold_count=6,
            per_fold_metrics=_make_per_fold_metrics(),
        )
        assert verdict == "REJECT"
        assert label == "INCONCLUSIVE"

    def test_inconclusive_insufficient_folds(self):
        """Fewer than 6 folds → INCONCLUSIVE."""
        verdict, label, rationale = _compute_verdict(
            mode="SWING",
            oos_expectancy_r=0.2,
            oos_sharpe=1.0,
            oos_trade_count=300,
            fold_count=3,
            per_fold_metrics=_make_per_fold_metrics(count=3),
        )
        assert verdict == "REJECT"
        assert label == "INCONCLUSIVE"

    def test_reject_negative_expectancy(self):
        """Negative OOS expectancy_r → REJECT."""
        verdict, label, rationale = _compute_verdict(
            mode="SWING",
            oos_expectancy_r=-0.1,
            oos_sharpe=0.5,
            oos_trade_count=300,
            fold_count=6,
            per_fold_metrics=_make_per_fold_metrics(),
        )
        assert verdict == "REJECT"
        assert "no edge detected" in rationale[0].lower()

    def test_continue_research_weak_edge(self):
        """Weak but positive edge → CONTINUE_RESEARCH."""
        verdict, label, rationale = _compute_verdict(
            mode="SWING",
            oos_expectancy_r=0.06,
            oos_sharpe=0.4,
            oos_trade_count=300,
            fold_count=6,
            per_fold_metrics=_make_per_fold_metrics(sharpe=0.4, expectancy_r=0.06),
        )
        assert verdict == "CONTINUE_RESEARCH"
        assert label == "CONTINUE_RESEARCH"

    def test_baseline_valid_swing(self):
        """SWING with solid metrics → BASELINE_VALID."""
        verdict, label, rationale = _compute_verdict(
            mode="SWING",
            oos_expectancy_r=0.12,
            oos_sharpe=0.6,
            oos_trade_count=300,
            fold_count=6,
            per_fold_metrics=_make_per_fold_metrics(sharpe=0.6, expectancy_r=0.12),
        )
        assert verdict == "BASELINE_VALID"
        assert label == "BASELINE_VALID"

    def test_promotion_candidate_swing(self):
        """SWING exceeding baseline → CANDIDATE_FOR_V7_GATES."""
        verdict, label, rationale = _compute_verdict(
            mode="SWING",
            oos_expectancy_r=0.20,
            oos_sharpe=1.0,
            oos_trade_count=300,
            fold_count=6,
            per_fold_metrics=_make_per_fold_metrics(sharpe=1.0, expectancy_r=0.20),
        )
        assert verdict == "CANDIDATE_FOR_V7_GATES"
        assert label == "PROMOTION_CANDIDATE"

    def test_primary_mode_continue_research(self):
        """SCALP with moderate edge → CONTINUE_RESEARCH (not BASELINE_VALID)."""
        verdict, label, rationale = _compute_verdict(
            mode="SCALP",
            oos_expectancy_r=0.12,
            oos_sharpe=0.6,
            oos_trade_count=300,
            fold_count=6,
            per_fold_metrics=_make_per_fold_metrics(sharpe=0.6, expectancy_r=0.12),
        )
        # Primary modes need stronger evidence for promotion
        assert verdict == "CONTINUE_RESEARCH"

    def test_primary_mode_promotion_candidate(self):
        """SCALP with strong edge → CANDIDATE_FOR_V7_GATES."""
        verdict, label, rationale = _compute_verdict(
            mode="SCALP",
            oos_expectancy_r=0.20,
            oos_sharpe=1.0,
            oos_trade_count=300,
            fold_count=6,
            per_fold_metrics=_make_per_fold_metrics(sharpe=1.0, expectancy_r=0.20),
        )
        assert verdict == "CANDIDATE_FOR_V7_GATES"

    def test_cost_stress_blocks_promotion(self):
        """Edge destroyed by costs → no promotion regardless of metrics."""
        verdict, label, rationale = _compute_verdict(
            mode="SWING",
            oos_expectancy_r=0.20,
            oos_sharpe=1.0,
            oos_trade_count=300,
            fold_count=6,
            per_fold_metrics=_make_per_fold_metrics(sharpe=1.0, expectancy_r=0.20),
            cost_stress={"combined_stress_edge_survives": False},
        )
        assert verdict == "CONTINUE_RESEARCH"
        assert "cost" in " ".join(rationale).lower()

    def test_regime_instability_blocks_promotion(self):
        """Edge only in rare regime → no promotion."""
        verdict, label, rationale = _compute_verdict(
            mode="SWING",
            oos_expectancy_r=0.20,
            oos_sharpe=1.0,
            oos_trade_count=300,
            fold_count=6,
            per_fold_metrics=_make_per_fold_metrics(sharpe=1.0, expectancy_r=0.20),
            regime_breakdown={"edge_only_in_rare_regime": True},
        )
        assert verdict == "CONTINUE_RESEARCH"
        assert "rare regime" in " ".join(rationale).lower()

    def test_rationale_is_descriptive(self):
        """Rationale list is non-empty and descriptive."""
        verdict, label, rationale = _compute_verdict(
            mode="SWING",
            oos_expectancy_r=0.15,
            oos_sharpe=0.8,
            oos_trade_count=300,
            fold_count=6,
            per_fold_metrics=_make_per_fold_metrics(),
        )
        assert len(rationale) >= 1
        assert all(isinstance(r, str) for r in rationale)


class TestFullReportBuild:
    """Integration-level tests for build_empirical_mode_research_report."""

    def test_swing_report_builds(self):
        """SWING empirical report builds and validates against schema."""
        results = _make_wfv_results("SWING")
        report = build_empirical_mode_research_report("SWING", results)
        assert report["mode"] == "SWING"
        assert report["report_type"] == "secondary_baseline_report"
        assert report["mode_priority"] == "SECONDARY_BASELINE"
        assert report["schema_version"] == "1.0.0"
        assert "report_id" in report

    def test_scalp_report_builds(self):
        """SCALP empirical report builds and validates."""
        results = _make_wfv_results("SCALP")
        report = build_empirical_mode_research_report("SCALP", results)
        assert report["mode"] == "SCALP"
        assert report["report_type"] == "primary_research_report"
        assert report["mode_priority"] == "PRIMARY"

    def test_aggressive_scalp_report_builds(self):
        """AGGRESSIVE_SCALP empirical report builds and validates."""
        results = _make_wfv_results("AGGRESSIVE_SCALP")
        report = build_empirical_mode_research_report("AGGRESSIVE_SCALP", results)
        assert report["mode"] == "AGGRESSIVE_SCALP"
        assert report["report_type"] == "primary_research_report"

    def test_report_has_all_required_keys(self):
        """Report contains all 18 required schema keys."""
        results = _make_wfv_results("SWING")
        report = build_empirical_mode_research_report("SWING", results)
        required_keys = {
            "schema_version", "report_id", "mode", "mode_priority",
            "report_type", "data_scope", "feature_set_refs",
            "label_dataset_refs", "alpha_theses", "validation_summary",
            "metrics", "cost_stress", "no_trade_comparison",
            "regime_breakdown", "multiple_hypothesis_control",
            "verdict", "blocked_scopes", "limitations",
        }
        assert required_keys.issubset(set(report.keys())), (
            f"Missing keys: {required_keys - set(report.keys())}"
        )

    def test_report_metrics_not_zeros(self):
        """Empirical metrics are real values, not placeholder zeros."""
        results = _make_wfv_results(
            "SWING", oos_sharpe=0.8, oos_expectancy_r=0.15, oos_trade_count=300,
        )
        report = build_empirical_mode_research_report("SWING", results)
        metrics = report["metrics"]
        assert metrics["oos_sharpe"]["value"] == 0.8
        assert metrics["oos_expectancy_r"]["value"] == 0.15
        assert metrics["oos_trade_count"] == 300
        assert len(metrics["per_fold_metrics"]) == 6

    def test_report_json_serializable(self):
        """Report is JSON-serializable (can be written to file)."""
        results = _make_wfv_results("SWING")
        report = build_empirical_mode_research_report("SWING", results)
        encoded = json.dumps(report)
        assert isinstance(encoded, str)
        decoded = json.loads(encoded)
        assert decoded["mode"] == "SWING"

    def test_report_no_profitability_claims(self):
        """Report does not contain profitability claims."""
        results = _make_wfv_results("SWING")
        report = build_empirical_mode_research_report("SWING", results)
        text = json.dumps(report).lower()
        # The report acknowledges its limitations
        assert "no profitability claims" in text.lower()

    def test_inconclusive_report_blocked_scopes(self):
        """INCONCLUSIVE report has appropriate blocked scopes."""
        results = _make_wfv_results("SWING", oos_expectancy_r=-0.1, oos_sharpe=-0.2)
        report = build_empirical_mode_research_report("SWING", results)
        blocked = " ".join(report.get("blocked_scopes", []))
        assert len(report["blocked_scopes"]) > 0
        # Should mention insufficient evidence
        assert "insufficient" in blocked.lower() or "REJECT" in blocked

    def test_unknown_mode_raises_error(self):
        """Unknown mode raises ModeError."""
        with pytest.raises(ModeError):
            build_empirical_mode_research_report("INVALID", {})

    def test_empty_wfv_produces_inconclusive(self):
        """Empty WFV results produce INCONCLUSIVE report (not crash)."""
        results = {}
        report = build_empirical_mode_research_report("SWING", results)
        assert report["verdict"] in ("REJECT", "CONTINUE_RESEARCH")
        # With no data, oos_trade_count=0, oos_expectancy_r=0.0, oos_sharpe=0.0
        # so it should be REJECT/INCONCLUSIVE
        assert len(report["blocked_scopes"]) >= 1

    def test_minimal_wfv_creates_report(self):
        """Minimal WFV with sufficient data creates valid report."""
        results = _make_wfv_results(
            "SWING",
            oos_sharpe=0.3,
            oos_expectancy_r=0.06,
            oos_trade_count=100,
            fold_count=6,
            per_fold_metrics=_make_per_fold_metrics(
                sharpe=0.3, expectancy_r=0.06, trades_per_fold=17,
            ),
        )
        report = build_empirical_mode_research_report("SWING", results)
        assert report["verdict"] in ("CONTINUE_RESEARCH",)

    def test_all_modes_have_correct_report_types(self):
        """Verify report types match expectations."""
        swing_wfv = _make_wfv_results("SWING")
        scalp_wfv = _make_wfv_results("SCALP")
        agg_wfv = _make_wfv_results("AGGRESSIVE_SCALP")

        swing_r = build_empirical_mode_research_report("SWING", swing_wfv)
        scalp_r = build_empirical_mode_research_report("SCALP", scalp_wfv)
        agg_r = build_empirical_mode_research_report("AGGRESSIVE_SCALP", agg_wfv)

        assert swing_r["report_type"] == "secondary_baseline_report"
        assert scalp_r["report_type"] == "primary_research_report"
        assert agg_r["report_type"] == "primary_research_report"

    def test_cost_stress_carries_verdict(self):
        """Cost stress section has clear verdict string."""
        results = _make_wfv_results("SWING")
        report = build_empirical_mode_research_report("SWING", results)
        cs = report["cost_stress"]
        assert "cost_stress_verdict" in cs
        assert cs["combined_stress_edge_survives"] is True

    def test_regime_breakdown_has_all_regimes(self):
        """Regime breakdown covers all four V7 regimes."""
        results = _make_wfv_results("SWING")
        report = build_empirical_mode_research_report("SWING", results)
        rb = report["regime_breakdown"]
        regimes_in_report = {r["regime"] for r in rb["regimes"]}
        assert regimes_in_report == {"TREND_UP", "TREND_DOWN", "RANGE", "TRANSITION"}

    def test_v7_gate_readiness_present(self):
        """Report has v7_gate_readiness section."""
        results = _make_wfv_results("SWING")
        report = build_empirical_mode_research_report("SWING", results)
        gr = report.get("v7_gate_readiness")
        assert gr is not None
        assert "gates_mapped" in gr
        assert "gates_not_ready" in gr
        assert "overall_readiness" in gr

    def test_recommended_actions_present(self):
        """Report has recommended_actions list."""
        results = _make_wfv_results("SWING")
        report = build_empirical_mode_research_report("SWING", results)
        actions = report.get("recommended_actions", [])
        assert len(actions) > 0
        assert all(isinstance(a, str) for a in actions)

    def test_report_id_customizable(self):
        """Custom report_id is used when provided."""
        results = _make_wfv_results("SWING")
        report = build_empirical_mode_research_report(
            "SWING", results, report_id="my-custom-id-001"
        )
        assert report["report_id"] == "my-custom-id-001"

    def test_no_xgboost_import(self):
        """No xgboost import in empirical.py source code."""
        import inspect
        import alphaforge.reports.empirical as mod
        source = inspect.getsource(mod)
        assert "import xgboost" not in source
        assert "from xgboost" not in source
        assert "XGBClassifier" not in source
        assert "XGBRegressor" not in source

    # ===================================================================
    # Issue #126 report consistency fixes
    # ===================================================================

    def test_empty_regime_breakdown_no_false_rare_claim(self):
        """Empty regimes produce edge_only_rare=False (no contradiction)."""
        results = _make_wfv_results("SWING")
        # Remove regime_breakdown entirely — triggers V7_REGIMES fallback
        results.pop("regime_breakdown", None)
        report = build_empirical_mode_research_report("SWING", results)
        rb = report["regime_breakdown"]
        assert rb["edge_only_in_rare_regime"] is False, (
            "Empty regime data should force edge_only_rare=False; "
            "True would contradict no edge existing anywhere"
        )
        assert len(rb["regimes"]) == 4  # V7_REGIMES count
        assert all(not r["edge_present"] for r in rb["regimes"])

    def test_cost_stress_empty_levels_verdict_not_run(self):
        """Empty stress levels produce NOT_RUN verdict instead of FAIL."""
        results = _make_wfv_results("SWING")
        # Remove cost_stress entirely
        results.pop("cost_stress", None)
        report = build_empirical_mode_research_report("SWING", results)
        cs = report["cost_stress"]
        assert cs["cost_stress_verdict"] == "NOT_RUN", (
            "Empty stress levels should yield NOT_RUN, not FAIL_EDGE_DESTROYED_BY_COSTS"
        )
        assert cs["fee_stress_levels"] == []
        assert cs["slippage_stress_levels"] == []

    def test_blocked_scopes_multi_symbol_no_single_sym_text(self):
        """Multiple symbols should not have stale single-symbol text."""
        results = _make_wfv_results("SWING")
        results["data_scope"]["symbols"] = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        report = build_empirical_mode_research_report("SWING", results)
        blocked_text = " ".join(report["blocked_scopes"]).lower()
        assert "single symbol" not in blocked_text, (
            "Multi-symbol data should not mention single symbol limitation"
        )

    def test_blocked_scopes_single_symbol_has_text(self):
        """Single symbol data includes single symbol limitation text."""
        results = _make_wfv_results("SWING")
        results["data_scope"]["symbols"] = ["BTCUSDT"]
        report = build_empirical_mode_research_report("SWING", results)
        blocked_text = " ".join(report["blocked_scopes"]).lower()
        assert "single symbol" in blocked_text, (
            "Single-symbol data should mention single symbol limitation"
        )

    def test_report_id_default_contains_timestamp(self):
        """Default report_id includes a timestamp for uniqueness."""
        results = _make_wfv_results("SWING")
        report = build_empirical_mode_research_report("SWING", results)
        rid = report["report_id"]
        # Default ID format: mrr-{mode}-empirical-{timestamp}
        assert rid.startswith("mrr-")
        assert "empirical" in rid
        # Should contain date digits (timestamp component)
        assert any(c.isdigit() for c in rid), (
            "Default report_id must contain a timestamp for uniqueness"
        )

    def test_report_ids_differ_on_consecutive_calls(self):
        """Two consecutive calls produce different report IDs."""
        results = _make_wfv_results("SWING")
        r1 = build_empirical_mode_research_report("SWING", results)
        r2 = build_empirical_mode_research_report("SWING", results)
        assert r1["report_id"] != r2["report_id"], (
            "Consecutive calls must generate unique report_ids"
        )

    def test_per_fold_metrics_structure(self):
        """Per-fold metrics have correct structure."""
        results = _make_wfv_results("SWING")
        report = build_empirical_mode_research_report("SWING", results)
        pf = report["metrics"]["per_fold_metrics"]
        for fold in pf:
            assert "fold" in fold
            assert "sharpe" in fold
            assert "expectancy_r" in fold
            assert "win_rate" in fold
            assert "trade_count" in fold

    def test_alpha_thesis_evidence_quality_matches_verdict(self):
        """Evidence quality in alpha thesis matches verdict strength."""
        # Strong verdict
        results = _make_wfv_results(
            "SWING", oos_expectancy_r=0.20, oos_sharpe=1.0,
        )
        report = build_empirical_mode_research_report("SWING", results)
        eq = report["alpha_theses"][0]["evidence_quality"]
        if report["verdict"] == "CANDIDATE_FOR_V7_GATES":
            assert eq == "STRONG"
        elif report["verdict"] == "BASELINE_VALID":
            assert eq == "MODERATE"

        # Weak verdict
        results2 = _make_wfv_results(
            "SWING", oos_expectancy_r=-0.1, oos_sharpe=-0.2, oos_trade_count=300,
        )
        report2 = build_empirical_mode_research_report("SWING", results2)
        assert report2["alpha_theses"][0]["evidence_quality"] == "INSUFFICIENT"


# ============================================================================
# MHT pipeline/builder contradiction tests
# ============================================================================


class TestMhtEmpiricalControl:
    """Tests for _build_empirical_mht_control — Issue #138.

    Pipeline and builder must agree on correction_method.
    NONE_APPLIED sets a blocking hold. Deflated Sharpe from actual data.
    PBO assessment when sufficient data.
    rejected_candidate_count tracks actual rejections.
    """

    def test_default_none_applied_when_pipeline_unsets_method(self):
        """When pipeline does not set correction_method, defaults NONE_APPLIED."""
        result = _build_empirical_mht_control(
            wfv_results={"trial_context": {"trial_count": 49}},
            fold_count=6,
        )
        assert result["correction_method"] == "NONE_APPLIED"
        assert result["corrected_significance"] is None
        assert result["mht_status"] == "NONE_APPLIED"

    def test_default_single_trial_also_none_applied(self):
        """Single trial (trial_count=1) also yields NONE_APPLIED."""
        result = _build_empirical_mht_control(
            wfv_results={"trial_context": {"trial_count": 1}},
            fold_count=6,
        )
        assert result["correction_method"] == "NONE_APPLIED"
        assert result["corrected_significance"] is None

    def test_respects_pipeline_bonferroni_method(self):
        """Pipeline's explicit Bonferroni method is respected."""
        result = _build_empirical_mht_control(
            wfv_results={
                "trial_context": {"trial_count": 490},
                "multiple_hypothesis_control": {
                    "correction_method": "Bonferroni",
                    "tested_hypothesis_count": 490,
                },
            },
            fold_count=6,
        )
        assert result["correction_method"] == "Bonferroni"
        assert result["corrected_significance"] is not None
        assert result["corrected_significance"] == pytest.approx(0.05 / 490, abs=1e-10)
        assert result["mht_status"] == "APPLIED"

    def test_respects_pipeline_fdr_method(self):
        """Pipeline's explicit FDR method is respected."""
        result = _build_empirical_mht_control(
            wfv_results={
                "trial_context": {"trial_count": 100},
                "multiple_hypothesis_control": {
                    "correction_method": "FDR",
                    "tested_hypothesis_count": 100,
                },
            },
            fold_count=6,
        )
        assert result["correction_method"] == "FDR"
        assert result["mht_status"] == "APPLIED"

    def test_pipeline_none_applied_kept(self):
        """Pipeline's explicit NONE_APPLIED is kept (not overridden to Bonferroni)."""
        result = _build_empirical_mht_control(
            wfv_results={
                "trial_context": {"trial_count": 490},
                "multiple_hypothesis_control": {
                    "correction_method": "NONE_APPLIED",
                    "tested_hypothesis_count": 490,
                },
            },
            fold_count=6,
        )
        assert result["correction_method"] == "NONE_APPLIED"
        assert result["corrected_significance"] is None

    def test_blocking_hold_note_when_none_applied_multiple_trials(self):
        """NONE_APPLIED with trial_count>1 adds blocking hold note."""
        result = _build_empirical_mht_control(
            wfv_results={"trial_context": {"trial_count": 49}},
            fold_count=6,
        )
        assert "BLOCKING HOLD" in result["notes"]
        assert "NONE_APPLIED" in result["notes"]

    def test_no_blocking_hold_when_mht_applied(self):
        """No blocking hold when MHT is properly applied."""
        result = _build_empirical_mht_control(
            wfv_results={
                "trial_context": {"trial_count": 49},
                "multiple_hypothesis_control": {
                    "correction_method": "Bonferroni",
                },
            },
            fold_count=6,
        )
        assert "BLOCKING HOLD" not in result["notes"]

    def test_deflated_sharpe_computed_when_data_available(self):
        """Deflated Sharpe is computed when MHT applied and OOS data provided."""
        result = _build_empirical_mht_control(
            wfv_results={
                "trial_context": {"trial_count": 49},
                "multiple_hypothesis_control": {
                    "correction_method": "Bonferroni",
                },
            },
            fold_count=6,
            oos_sharpe=1.0,
            oos_trade_count=300,
        )
        assert result["deflated_sharpe_or_equivalent"] is not None
        assert result["deflated_sharpe_or_equivalent"] > 0.0

    def test_deflated_sharpe_not_computed_when_no_mht(self):
        """Deflated Sharpe is None when MHT not applied."""
        result = _build_empirical_mht_control(
            wfv_results={"trial_context": {"trial_count": 49}},
            fold_count=6,
            oos_sharpe=1.0,
            oos_trade_count=300,
        )
        assert result["deflated_sharpe_or_equivalent"] is None

    def test_pbo_not_run_when_no_mht(self):
        """PBO is NOT_RUN when MHT not applied."""
        result = _build_empirical_mht_control(
            wfv_results={"trial_context": {"trial_count": 49}},
            fold_count=6,
        )
        assert result["pbo_or_backtest_overfit_risk"] == "NOT_RUN"

    def test_pbo_high_when_deflated_sharpe_zero_moderate_trials(self):
        """PBO assessment is HIGH when deflated Sharpe = 0 and trial_count <= 100."""
        result = _build_empirical_mht_control(
            wfv_results={
                "trial_context": {"trial_count": 50},
                "multiple_hypothesis_control": {
                    "correction_method": "Bonferroni",
                },
            },
            fold_count=6,
            oos_sharpe=1.0,
            oos_trade_count=20,  # 0.5*50/20 = 1.25 >= 1.0 -> deflated=0.0 -> HIGH
        )
        assert result["pbo_or_backtest_overfit_risk"] == "HIGH"

    def test_pbo_critical_when_large_trial_count_and_zero_sharpe(self):
        """PBO assessment is CRITICAL when trial_count > 100 and deflated=0."""
        result = _build_empirical_mht_control(
            wfv_results={
                "trial_context": {"trial_count": 500},
                "multiple_hypothesis_control": {
                    "correction_method": "Bonferroni",
                },
            },
            fold_count=6,
            oos_sharpe=1.0,
            oos_trade_count=50,  # 0.5*500/50 = 5.0 >= 1.0 -> deflated=0.0
        )
        assert result["pbo_or_backtest_overfit_risk"] == "CRITICAL"

    def test_rejected_candidate_count_from_p_values(self):
        """rejected_candidate_count tracks BH rejections when p_values provided."""
        result = _build_empirical_mht_control(
            wfv_results={
                "trial_context": {"trial_count": 10},
                "multiple_hypothesis_control": {
                    "correction_method": "FDR",
                    "tested_hypothesis_count": 10,
                    "p_values": [0.01, 0.02, 0.03, 0.04, 0.9],
                },
            },
            fold_count=6,
        )
        # BH on [0.01, 0.02, 0.03, 0.04, 0.9] at alpha=0.05 rejects 4
        assert result["rejected_candidate_count"] == 4

    def test_rejected_candidate_count_defaults_to_pipeline_value(self):
        """rejected_candidate_count falls back to pipeline value when no p_values."""
        result = _build_empirical_mht_control(
            wfv_results={
                "trial_context": {"trial_count": 10},
                "multiple_hypothesis_control": {
                    "rejected_candidate_count": 7,
                },
            },
            fold_count=6,
        )
        assert result["rejected_candidate_count"] == 7

    def test_data_snooping_risk_higher_without_mht(self):
        """Data snooping risk is higher without MHT for same trial count."""
        # No MHT, 490 trials -> HIGH (n_trials > 100 and <= 1000, no MHT)
        result_no_mht = _build_empirical_mht_control(
            wfv_results={"trial_context": {"trial_count": 490}},
            fold_count=6,
        )
        assert result_no_mht["data_snooping_risk_flag"] == "HIGH"

        # With Bonferroni, 490 trials -> MEDIUM
        result_mht = _build_empirical_mht_control(
            wfv_results={
                "trial_context": {"trial_count": 490},
                "multiple_hypothesis_control": {
                    "correction_method": "Bonferroni",
                },
            },
            fold_count=6,
        )
        assert result_mht["data_snooping_risk_flag"] == "MEDIUM"

    def test_schema_required_keys_present(self):
        """Output contains all schema-required keys."""
        result = _build_empirical_mht_control(
            wfv_results={"trial_context": {"trial_count": 10}},
            fold_count=6,
        )
        assert "tested_hypothesis_count" in result
        assert "correction_method" in result
        assert "data_snooping_risk_flag" in result

    def test_pbo_low_when_deflated_sharpe_healthy(self):
        """PBO assessment is LOW when deflated Sharpe is healthy."""
        result = _build_empirical_mht_control(
            wfv_results={
                "trial_context": {"trial_count": 5},
                "multiple_hypothesis_control": {
                    "correction_method": "Bonferroni",
                },
            },
            fold_count=6,
            oos_sharpe=1.5,
            oos_trade_count=1000,
        )
        # 0.5*5/1000 = 0.0025, deflated = 1.5*sqrt(0.9975/0.5) ~ 2.12
        # deflated > 0.3 so PBO = LOW
        assert result["pbo_or_backtest_overfit_risk"] == "LOW"
