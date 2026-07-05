"""Unit tests for AlphaForge non-ML research report analysis.

Tests: analyze_label_distribution, analyze_no_trade_quality,
cost_impact_summary, mht_hold_summary, assemble_non_ml_research_context.

All tests are deterministic. No model training. No profitability claims.
No real market data.
"""

import json

import pytest

from alphaforge.reports.research import (
    _parse_best_action,
    _parse_label_validity,
    analyze_label_distribution,
    analyze_no_trade_quality,
    assemble_non_ml_research_context,
    cost_impact_summary,
    mht_hold_summary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_label(
    best_action_label: str = "NO_TRADE",
    label_validity: str = "VALID",
    gross_r: float = 0.0,
    net_r: float = 0.0,
    no_trade_quality: str = "",
) -> dict:
    """Create a synthetic AlphaForgeLabel dict for testing."""
    return {
        "best_action_label": best_action_label,
        "label_validity": label_validity,
        "gross_r": gross_r,
        "net_r": net_r,
        "no_trade_quality": no_trade_quality,
    }


# ---------------------------------------------------------------------------
# _parse_best_action tests
# ---------------------------------------------------------------------------


def test_parse_best_action_normal():
    assert _parse_best_action({"best_action_label": "LONG_NOW"}) == "LONG_NOW"
    assert _parse_best_action({"best_action_label": "SHORT_NOW"}) == "SHORT_NOW"
    assert _parse_best_action({"best_action_label": "NO_TRADE"}) == "NO_TRADE"


def test_parse_best_action_missing_key():
    assert _parse_best_action({}) == "UNKNOWN"


def test_parse_best_action_non_dict():
    assert _parse_best_action(None) == "UNKNOWN"
    assert _parse_best_action("string") == "UNKNOWN"
    assert _parse_best_action(42) == "UNKNOWN"


def test_parse_best_action_empty_string():
    assert _parse_best_action({"best_action_label": ""}) == ""


# ---------------------------------------------------------------------------
# _parse_label_validity tests
# ---------------------------------------------------------------------------


def test_parse_label_validity_normal():
    assert _parse_label_validity({"label_validity": "VALID"}) == "VALID"
    assert _parse_label_validity({"label_validity": "INVALID"}) == "INVALID"
    assert _parse_label_validity({"label_validity": "AMBIGUOUS"}) == "AMBIGUOUS"


def test_parse_label_validity_missing_key():
    assert _parse_label_validity({}) == "UNKNOWN"


def test_parse_label_validity_non_dict():
    assert _parse_label_validity(None) == "UNKNOWN"


# ---------------------------------------------------------------------------
# WS-05-LABEL-DISTRIBUTION tests
# ---------------------------------------------------------------------------


class TestAnalyzeLabelDistribution:
    """AC-05-LABEL-01 through AC-05-LABEL-07."""

    def test_exists_and_exported(self):
        """AC-05-LABEL-01: Function exists in research.py."""
        from alphaforge.reports import analyze_label_distribution as exported
        assert exported is analyze_label_distribution
        assert callable(analyze_label_distribution)

    def test_return_keys(self):
        """AC-05-LABEL-02: Returns correct dict keys."""
        labels = [_make_label("LONG_NOW") for _ in range(10)]
        result = analyze_label_distribution(labels, "SCALP")
        expected_keys = {
            "total_count", "long_pct", "short_pct", "no_trade_pct",
            "ambiguous_pct", "best_action_counts", "label_validity_distribution",
        }
        assert set(result.keys()) == expected_keys

    def test_distribution_100_mock_labels(self):
        """AC-05-LABEL-03: Percentages sum to ~100% for valid fixture.

        40 LONG, 30 SHORT, 20 NO_TRADE, 10 AMBIGUOUS.
        """
        labels = []
        labels.extend([_make_label("LONG_NOW") for _ in range(40)])
        labels.extend([_make_label("SHORT_NOW") for _ in range(30)])
        labels.extend([_make_label("NO_TRADE") for _ in range(20)])
        labels.extend([_make_label("AMBIGUOUS") for _ in range(10)])

        result = analyze_label_distribution(labels, "SWING")

        assert result["total_count"] == 100
        assert result["long_pct"] == 40.0
        assert result["short_pct"] == 30.0
        assert result["no_trade_pct"] == 20.0
        assert result["ambiguous_pct"] == 10.0

        # AC-05-LABEL-03: Percentages sum to 100.0 (±0.5 tolerance)
        pct_sum = (
            result["long_pct"]
            + result["short_pct"]
            + result["no_trade_pct"]
            + result["ambiguous_pct"]
        )
        assert abs(pct_sum - 100.0) <= 0.5, f"Sum was {pct_sum}"

    def test_best_action_counts(self):
        """AC-05-LABEL-05: best_action_counts maps each action to count."""
        labels = [
            _make_label("LONG_NOW"),
            _make_label("LONG_NOW"),
            _make_label("SHORT_NOW"),
            _make_label("NO_TRADE"),
            _make_label("NO_TRADE"),
            _make_label("NO_TRADE"),
            _make_label("LONG_AGGRESSIVE"),
        ]
        result = analyze_label_distribution(labels, "SWING")

        counts = result["best_action_counts"]
        assert counts["LONG_NOW"] == 2
        assert counts["LONG_AGGRESSIVE"] == 1
        assert counts["SHORT_NOW"] == 1
        assert counts["NO_TRADE"] == 3

    def test_label_validity_distribution(self):
        """AC-05-LABEL-06: label_validity_distribution maps validity to count."""
        labels = [
            _make_label("LONG_NOW", label_validity="VALID"),
            _make_label("LONG_NOW", label_validity="VALID"),
            _make_label("SHORT_NOW", label_validity="VALID"),
            _make_label("NO_TRADE", label_validity="INVALID"),
            _make_label("NO_TRADE", label_validity="INVALID"),
            _make_label("NO_TRADE", label_validity="AMBIGUOUS"),
        ]
        result = analyze_label_distribution(labels, "SWING")

        validity = result["label_validity_distribution"]
        assert validity["VALID"] == 3
        assert validity["INVALID"] == 2
        assert validity["AMBIGUOUS"] == 1

    def test_empty_input(self):
        """AC-05-LABEL-04: Empty input returns all zeros."""
        result = analyze_label_distribution([], "SWING")

        assert result["total_count"] == 0
        assert result["long_pct"] == 0.0
        assert result["short_pct"] == 0.0
        assert result["no_trade_pct"] == 0.0
        assert result["ambiguous_pct"] == 0.0
        assert result["best_action_counts"] == {}
        assert result["label_validity_distribution"] == {}

    def test_handles_unknown_best_action(self):
        """Labels with unknown best_action_label are classified as ambiguous."""
        labels = [
            _make_label("UNKNOWN"),
            _make_label("LONG_NOW"),
        ]
        result = analyze_label_distribution(labels, "SWING")
        assert result["long_pct"] == 50.0
        assert result["ambiguous_pct"] == 50.0

    def test_no_trade_variants(self):
        """Various NO_TRADE spellings are recognized."""
        labels = [
            _make_label("NO_TRADE"),
            _make_label("NO TRADE"),
            _make_label("no_trade"),
        ]
        result = analyze_label_distribution(labels, "SWING")
        assert result["no_trade_pct"] == 100.0

    def test_no_xgboost_import(self):
        """AC-05-LABEL-07: No xgboost import in research.py source code."""
        import inspect
        import alphaforge.reports.research as mod
        source = inspect.getsource(mod)
        assert "import xgboost" not in source
        assert "from xgboost" not in source
        assert "XGBClassifier" not in source
        assert "XGBRegressor" not in source


# ---------------------------------------------------------------------------
# WS-05-NO-TRADE tests
# ---------------------------------------------------------------------------


class TestAnalyzeNoTradeQuality:
    """AC-05-NOTRADE-01 through AC-05-NOTRADE-07."""

    def test_exists_and_signature(self):
        """AC-05-NOTRADE-01: Function exists with correct signature."""
        assert callable(analyze_no_trade_quality)
        result = analyze_no_trade_quality([], "SWING")
        assert isinstance(result, dict)

    def test_return_keys(self):
        """AC-05-NOTRADE-02: Returns correct dict keys."""
        labels = [_make_label("LONG_NOW") for _ in range(10)]
        result = analyze_no_trade_quality(labels, "SWING")
        expected_keys = {
            "total_no_trade", "no_trade_pct", "subcategories",
            "dominates_directional", "directional_pct", "summary",
        }
        assert set(result.keys()) == expected_keys

    def test_four_subcategories(self):
        """AC-05-NOTRADE-03: Exactly 4 subcategories with name/count/pct."""
        labels = [
            _make_label("NO_TRADE"),
            _make_label("NO_TRADE"),
            _make_label("LONG_NOW"),
        ]
        result = analyze_no_trade_quality(labels, "SWING")
        subcats = result["subcategories"]
        assert len(subcats) == 4
        subcat_names = {s["name"] for s in subcats}
        assert subcat_names == {"NO_EDGE", "COST_DOMINATED", "AMBIGUOUS", "EXCLUDED"}
        for s in subcats:
            assert "name" in s
            assert "count" in s
            assert "pct" in s
            assert isinstance(s["count"], int)
            assert isinstance(s["pct"], float)

    def test_dominates_directional_when_no_trade_majority(self):
        """AC-05-NOTRADE-04: dominates when NO_TRADE > 50% and > directional."""
        labels = []
        labels.extend([_make_label("NO_TRADE") for _ in range(60)])
        labels.extend([_make_label("LONG_NOW") for _ in range(25)])
        labels.extend([_make_label("SHORT_NOW") for _ in range(15)])

        result = analyze_no_trade_quality(labels, "SWING")
        assert result["total_no_trade"] == 60
        assert result["no_trade_pct"] == 60.0
        assert result["dominates_directional"] is True

    def test_dominates_directional_false_when_directional_majority(self):
        """AC-05-NOTRADE-05: dominates=False when directional majority."""
        labels = []
        labels.extend([_make_label("NO_TRADE") for _ in range(20)])
        labels.extend([_make_label("LONG_NOW") for _ in range(50)])
        labels.extend([_make_label("SHORT_NOW") for _ in range(30)])

        result = analyze_no_trade_quality(labels, "SWING")
        assert result["total_no_trade"] == 20
        assert result["no_trade_pct"] == 20.0
        assert result["dominates_directional"] is False

    def test_empty_input(self):
        """AC-05-NOTRADE-06: Empty input returns zeros."""
        result = analyze_no_trade_quality([], "SWING")
        assert result["total_no_trade"] == 0
        assert result["no_trade_pct"] == 0.0
        assert result["dominates_directional"] is False
        assert result["directional_pct"] == 0.0
        for s in result["subcategories"]:
            assert s["count"] == 0
            assert s["pct"] == 0.0

    def test_custom_threshold(self):
        """Threshold is configurable."""
        labels = []
        labels.extend([_make_label("NO_TRADE") for _ in range(40)])
        labels.extend([_make_label("LONG_NOW") for _ in range(60)])

        # With default 0.5 threshold: 40% < 50%, so not dominant
        result_default = analyze_no_trade_quality(labels, "SWING")
        assert result_default["dominates_directional"] is False

        # With 0.3 threshold: 40% > 30%, and 40% > max(60%, 0%)... wait,
        # no: 40% < 60%, so still False even with 0.3
        # Actually dominates requires BOTH: pct > threshold AND pct > max(long, short)
        # 40% > 30% threshold is True, but 40% > 60% is False.
        result_03 = analyze_no_trade_quality(labels, "SWING", threshold=0.3)
        assert result_03["dominates_directional"] is False

        # With 0.3 threshold and more NO_TRADE:
        labels2 = []
        labels2.extend([_make_label("NO_TRADE") for _ in range(70)])
        labels2.extend([_make_label("LONG_NOW") for _ in range(30)])
        result2 = analyze_no_trade_quality(labels2, "SWING", threshold=0.3)
        assert result2["dominates_directional"] is True

    def test_scaffold_all_to_no_edge(self):
        """Scaffold labels without no_trade_quality assign all to NO_EDGE."""
        labels = [_make_label("NO_TRADE") for _ in range(5)]
        result = analyze_no_trade_quality(labels, "SWING")
        for s in result["subcategories"]:
            if s["name"] == "NO_EDGE":
                assert s["count"] == 5
                assert s["pct"] == 100.0
            else:
                assert s["count"] == 0
        assert "Scaffold placeholder" in result["summary"]

    def test_no_trade_quality_mapping(self):
        """no_trade_quality field is parsed for subcategory assignment."""
        labels = [
            _make_label("NO_TRADE", no_trade_quality="COST_DOMINATED_LOSS"),
            _make_label("NO_TRADE", no_trade_quality="AMBIGUOUS_DIRECTION"),
            _make_label("NO_TRADE", no_trade_quality="EXCLUDED_BY_FILTER"),
            _make_label("NO_TRADE", no_trade_quality="NO_EDGE_DETECTED"),
        ]
        result = analyze_no_trade_quality(labels, "SWING")
        subcat_map = {s["name"]: s["count"] for s in result["subcategories"]}
        assert subcat_map["COST_DOMINATED"] == 1
        assert subcat_map["AMBIGUOUS"] == 1
        assert subcat_map["EXCLUDED"] == 1
        assert subcat_map["NO_EDGE"] == 1

    def test_no_xgboost_import(self):
        """AC-05-NOTRADE-07: No xgboost in research.py."""
        import inspect
        import alphaforge.reports.research as mod
        source = inspect.getsource(mod)
        assert "import xgboost" not in source
        assert "from xgboost" not in source
        assert "XGBClassifier" not in source
        assert "XGBRegressor" not in source


# ---------------------------------------------------------------------------
# WS-05-COST-MHT: cost_impact_summary tests
# ---------------------------------------------------------------------------


class TestCostImpactSummary:
    """AC-05-COST-01 through AC-05-COST-03."""

    def test_return_keys(self):
        """AC-05-COST-01: Returns correct dict keys."""
        labels = [_make_label("LONG_NOW", gross_r=1.0, net_r=0.8)]
        result = cost_impact_summary(labels, "SWING")
        expected_keys = {
            "gross_r_mean", "net_r_mean", "cost_drag", "cost_drag_pct",
            "sample_count", "has_sufficient_sample", "summary",
        }
        assert set(result.keys()) == expected_keys

    def test_cost_drag_computation(self):
        """AC-05-COST-02: cost_drag = gross_r_mean - net_r_mean."""
        labels = [
            _make_label("LONG_NOW", gross_r=2.0, net_r=1.5),
            _make_label("SHORT_NOW", gross_r=1.0, net_r=0.7),
            _make_label("NO_TRADE", gross_r=0.0, net_r=0.0),
        ]
        result = cost_impact_summary(labels, "SWING")

        expected_gross_mean = (2.0 + 1.0 + 0.0) / 3
        expected_net_mean = (1.5 + 0.7 + 0.0) / 3
        expected_drag = expected_gross_mean - expected_net_mean

        assert result["gross_r_mean"] == round(expected_gross_mean, 4)
        assert result["net_r_mean"] == round(expected_net_mean, 4)
        assert result["cost_drag"] == round(expected_drag, 4)

    def test_cost_drag_pct_when_gross_zero(self):
        """AC-05-COST-02: cost_drag_pct = 0.0 when gross_r_mean == 0."""
        labels = [
            _make_label("NO_TRADE", gross_r=0.0, net_r=0.0),
            _make_label("NO_TRADE", gross_r=0.0, net_r=0.0),
        ]
        result = cost_impact_summary(labels, "SWING")
        assert result["cost_drag_pct"] == 0.0
        assert result["gross_r_mean"] == 0.0

    def test_empty_input(self):
        """AC-05-COST-03: Empty input returns zeros."""
        result = cost_impact_summary([], "SWING")
        assert result["sample_count"] == 0
        assert result["has_sufficient_sample"] is False
        assert result["gross_r_mean"] == 0.0
        assert result["net_r_mean"] == 0.0
        assert result["cost_drag"] == 0.0
        assert result["cost_drag_pct"] == 0.0

    def test_sufficient_sample(self):
        """has_sufficient_sample is True when sample >= 100."""
        labels = [_make_label("LONG_NOW", gross_r=1.0, net_r=0.9) for _ in range(100)]
        result = cost_impact_summary(labels, "SWING")
        assert result["has_sufficient_sample"] is True
        assert result["sample_count"] == 100

    def test_insufficient_sample(self):
        """has_sufficient_sample is False when sample < 100."""
        labels = [_make_label("LONG_NOW", gross_r=1.0, net_r=0.9) for _ in range(99)]
        result = cost_impact_summary(labels, "SWING")
        assert result["has_sufficient_sample"] is False

    def test_alternative_field_names(self):
        """Uses gross_r_multiple and net_r_multiple as fallback."""
        label = {
            "best_action_label": "LONG_NOW",
            "label_validity": "VALID",
            "gross_r_multiple": 1.5,
            "net_r_multiple": 1.2,
        }
        result = cost_impact_summary([label], "SWING")
        assert result["gross_r_mean"] == 1.5
        assert result["net_r_mean"] == 1.2

    def test_no_xgboost_import(self):
        """AC-05-COST-07: No xgboost in research.py."""
        import inspect
        import alphaforge.reports.research as mod
        source = inspect.getsource(mod)
        assert "import xgboost" not in source
        assert "from xgboost" not in source
        assert "XGBClassifier" not in source
        assert "XGBRegressor" not in source


# ---------------------------------------------------------------------------
# WS-05-COST-MHT: mht_hold_summary tests
# ---------------------------------------------------------------------------


class TestMhtHoldSummary:
    """AC-05-COST-04 through AC-05-COST-05."""

    def test_none_applied_hold_active(self):
        """AC-05-COST-04: NONE_APPLIED → hold_active=True, corrected_significance=null."""
        result = mht_hold_summary(10, "NONE_APPLIED")
        assert result["correction_method"] == "NONE_APPLIED"
        assert result["corrected_significance"] is None
        assert result["hold_active"] is True
        assert result["requires_model_training"] is True
        assert result["tested_hypothesis_count"] == 10

    def test_hold_reason_contains_model_training(self):
        """AC-05-COST-05: hold_reason mentions model training."""
        result = mht_hold_summary(5, "NONE_APPLIED")
        assert "model training" in result["hold_reason"].lower()
        assert "multiple comparison" in result["hold_reason"].lower()

    def test_notes_documents_training_artifacts(self):
        """AC-05-COST-05: notes documents training artifacts needed."""
        result = mht_hold_summary(3, "NONE_APPLIED")
        notes = result["notes"]
        assert "training artifacts" in notes.lower()
        assert "trained model" in notes.lower()
        assert "BLOCKING hold" in notes or "BLOCKING" in notes

    def test_applied_method_no_hold(self):
        """When a real correction method is used, hold is not active."""
        result = mht_hold_summary(10, "Bonferroni")
        assert result["hold_active"] is False
        assert result["requires_model_training"] is False
        assert result["correction_method"] == "Bonferroni"

    def test_no_xgboost_import(self):
        """AC-05-COST-07: No xgboost in research.py."""
        import inspect
        import alphaforge.reports.research as mod
        source = inspect.getsource(mod)
        assert "import xgboost" not in source
        assert "from xgboost" not in source
        assert "XGBClassifier" not in source
        assert "XGBRegressor" not in source


# ---------------------------------------------------------------------------
# WS-05-COST-MHT: assemble_non_ml_research_context tests
# ---------------------------------------------------------------------------


class TestAssembleNonMlResearchContext:
    """AC-05-COST-06 through AC-05-COST-07."""

    def test_all_keys_present(self):
        """AC-05-COST-06: All four sub-dicts present."""
        labels = [
            _make_label("LONG_NOW", gross_r=1.0, net_r=0.8) for _ in range(50)
        ] + [
            _make_label("SHORT_NOW", gross_r=0.5, net_r=0.3) for _ in range(30)
        ] + [
            _make_label("NO_TRADE") for _ in range(20)
        ]
        result = assemble_non_ml_research_context(labels, "SWING")

        assert "label_distribution" in result
        assert "no_trade_quality" in result
        assert "cost_impact" in result
        assert "mht_hold" in result

        assert isinstance(result["label_distribution"], dict)
        assert isinstance(result["no_trade_quality"], dict)
        assert isinstance(result["cost_impact"], dict)
        assert isinstance(result["mht_hold"], dict)

    def test_context_empty_input(self):
        """Context works with empty label list."""
        result = assemble_non_ml_research_context([], "SWING")
        assert result["label_distribution"]["total_count"] == 0
        assert result["no_trade_quality"]["total_no_trade"] == 0
        assert result["cost_impact"]["sample_count"] == 0
        assert result["mht_hold"]["hold_active"] is True

    def test_context_json_serializable(self):
        """AC-05-COST-06: Context is JSON-serializable."""
        labels = [
            _make_label("LONG_NOW", gross_r=1.0, net_r=0.8),
            _make_label("SHORT_NOW", gross_r=0.5, net_r=0.3),
            _make_label("NO_TRADE"),
        ]
        result = assemble_non_ml_research_context(labels, "SWING")

        # Should not raise
        encoded = json.dumps(result)
        assert isinstance(encoded, str)
        # Verify round-trip
        decoded = json.loads(encoded)
        assert decoded["label_distribution"]["total_count"] == 3

    def test_no_xgboost_import(self):
        """AC-05-COST-07: No xgboost in research.py."""
        import inspect
        import alphaforge.reports.research as mod
        source = inspect.getsource(mod)
        assert "import xgboost" not in source
        assert "from xgboost" not in source
        assert "XGBClassifier" not in source
        assert "XGBRegressor" not in source
