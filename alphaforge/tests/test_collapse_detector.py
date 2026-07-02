"""Unit tests for NO_TRADE Collapse Detector (Issue #117).

Tests: compute_no_trade_trend, detect_no_trade_collapse,
build_collapse_root_cause_tree, counterfactual_analysis,
build_collapse_report.

All tests are deterministic. No model training. No profitability claims.
No real market data.
"""

from __future__ import annotations
import pytest
pytestmark = pytest.mark.integration


import json

import pytest

from alphaforge.reports.collapse_detector import (
    COLLAPSE_ROOT_CAUSE_ORDER,
    DEFAULT_COLLAPSE_THRESHOLD,
    DEFAULT_WINDOW_SIZE,
    _classify_no_trade_quality,
    _is_directional,
    _is_no_trade,
    _sliding_window_pcts,
    build_collapse_report,
    build_collapse_root_cause_tree,
    compute_no_trade_trend,
    counterfactual_analysis,
    detect_no_trade_collapse,
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
# _is_no_trade tests
# ---------------------------------------------------------------------------


class TestIsNoTrade:
    def test_exact_match(self):
        assert _is_no_trade("NO_TRADE") is True

    def test_with_space(self):
        assert _is_no_trade("NO TRADE") is True

    def test_lowercase(self):
        assert _is_no_trade("no_trade") is True

    def test_long_action(self):
        assert _is_no_trade("LONG_NOW") is False

    def test_short_action(self):
        assert _is_no_trade("SHORT_NOW") is False

    def test_ambiguous(self):
        assert _is_no_trade("AMBIGUOUS") is False

    def test_empty(self):
        assert _is_no_trade("") is False


# ---------------------------------------------------------------------------
# _is_directional tests
# ---------------------------------------------------------------------------


class TestIsDirectional:
    def test_long_now(self):
        assert _is_directional("LONG_NOW") is True

    def test_short_now(self):
        assert _is_directional("SHORT_NOW") is True

    def test_long_aggressive(self):
        assert _is_directional("LONG_AGGRESSIVE") is True

    def test_no_trade(self):
        assert _is_directional("NO_TRADE") is False

    def test_ambiguous(self):
        assert _is_directional("AMBIGUOUS") is False

    def test_unknown(self):
        assert _is_directional("UNKNOWN") is False


# ---------------------------------------------------------------------------
# _classify_no_trade_quality tests
# ---------------------------------------------------------------------------


class TestClassifyNoTradeQuality:
    def test_cost_dominated(self):
        assert _classify_no_trade_quality({"no_trade_quality": "COST_DOMINATED_LOSS"}) == "cost"
        assert _classify_no_trade_quality({"no_trade_quality": "FEE_EXCEEDS_EDGE"}) == "cost"
        assert _classify_no_trade_quality({"no_trade_quality": "SLIPPAGE_TOO_HIGH"}) == "cost"
        assert _classify_no_trade_quality({"no_trade_quality": "SPREAD_CONSUMES_PROFIT"}) == "cost"

    def test_signal_no_edge(self):
        assert _classify_no_trade_quality({"no_trade_quality": "NO_EDGE_DETECTED"}) == "signal"
        assert _classify_no_trade_quality({"no_trade_quality": "EDGE_BELOW_NOISE"}) == "signal"
        assert _classify_no_trade_quality({"no_trade_quality": "WEAK_SIGNAL"}) == "signal"
        assert _classify_no_trade_quality({"no_trade_quality": "SAVED_LOSS"}) == "signal"

    def test_model_ambiguous(self):
        assert _classify_no_trade_quality({"no_trade_quality": "AMBIGUOUS_DIRECTION"}) == "model"
        assert _classify_no_trade_quality({"no_trade_quality": "UNCERTAIN_OUTLOOK"}) == "model"
        assert _classify_no_trade_quality({"no_trade_quality": "LOW_CONFIDENCE"}) == "model"
        assert _classify_no_trade_quality({"no_trade_quality": "MISSED_OPPORTUNITY"}) == "model"

    def test_threshold_excluded(self):
        assert _classify_no_trade_quality({"no_trade_quality": "THRESHOLD_NOT_MET"}) == "threshold"
        assert _classify_no_trade_quality({"no_trade_quality": "FILTER_EXCLUDED"}) == "threshold"
        assert _classify_no_trade_quality({"no_trade_quality": "EXCLUDED_BY_SCOPE"}) == "threshold"

    def test_empty_quality(self):
        assert _classify_no_trade_quality({"no_trade_quality": ""}) == "unknown"

    def test_missing_key(self):
        assert _classify_no_trade_quality({}) == "unknown"


# ---------------------------------------------------------------------------
# _sliding_window_pcts tests
# ---------------------------------------------------------------------------


class TestSlidingWindowPcts:
    def test_below_window_size(self):
        actions = ["LONG_NOW", "NO_TRADE", "SHORT_NOW"]
        result = _sliding_window_pcts(actions, window_size=10)
        assert result == []

    def test_single_window(self):
        actions = ["NO_TRADE"] * 5 + ["LONG_NOW"] * 5
        result = _sliding_window_pcts(actions, window_size=10)
        assert len(result) == 1
        assert result[0]["no_trade_pct"] == 50.0

    def test_multiple_windows(self):
        actions = (["NO_TRADE"] * 80 + ["LONG_NOW"] * 20) * 2
        result = _sliding_window_pcts(actions, window_size=50)
        assert len(result) >= 2
        for w in result:
            assert 0 <= w["no_trade_pct"] <= 100.0
            assert w["total_count"] <= 50
            assert w["no_trade_count"] >= 0
            assert w["no_trade_count"] <= w["total_count"]

    def test_zero_no_trade(self):
        actions = ["LONG_NOW"] * 100
        result = _sliding_window_pcts(actions, window_size=50)
        assert all(w["no_trade_pct"] == 0.0 for w in result)

    def test_all_no_trade(self):
        actions = ["NO_TRADE"] * 100
        result = _sliding_window_pcts(actions, window_size=50)
        assert all(w["no_trade_pct"] == 100.0 for w in result)


# ---------------------------------------------------------------------------
# compute_no_trade_trend tests
# ---------------------------------------------------------------------------


class TestComputeNoTradeTrend:
    def test_empty_input(self):
        result = compute_no_trade_trend([])
        assert result["total_bars"] == 0
        assert result["trend_direction"] == "insufficient_data"
        assert result["collapse_detected"] is False

    def test_all_long_no_collapse(self):
        labels = [_make_label("LONG_NOW") for _ in range(200)]
        result = compute_no_trade_trend(labels)
        assert result["overall_no_trade_pct"] == 0.0
        assert result["collapse_detected"] is False
        assert result["total_bars"] == 200

    def test_all_no_trade_collapse(self):
        labels = [_make_label("NO_TRADE") for _ in range(200)]
        result = compute_no_trade_trend(labels)
        assert result["overall_no_trade_pct"] == 100.0
        assert result["collapse_detected"] is True
        assert result["trend_direction"] in ("stable", "increasing", "decreasing")

    def test_trend_increasing(self):
        # First half: low NO_TRADE, second half: high NO_TRADE
        labels = (
            [_make_label("LONG_NOW") for _ in range(100)]
            + [_make_label("NO_TRADE") for _ in range(100)]
        )
        result = compute_no_trade_trend(labels, window_size=50)
        assert result["trend_direction"] == "increasing"
        assert result["total_bars"] == 200

    def test_trend_decreasing(self):
        labels = (
            [_make_label("NO_TRADE") for _ in range(100)]
            + [_make_label("LONG_NOW") for _ in range(100)]
        )
        result = compute_no_trade_trend(labels, window_size=50)
        assert result["trend_direction"] == "decreasing"

    def test_trend_stable(self):
        labels = (
            [_make_label("NO_TRADE") for _ in range(50)]
            + [_make_label("LONG_NOW") for _ in range(50)]
            + [_make_label("NO_TRADE") for _ in range(50)]
            + [_make_label("LONG_NOW") for _ in range(50)]
        )
        result = compute_no_trade_trend(labels, window_size=50)
        # Should be stable since both halves have ~50% NO_TRADE
        assert result["trend_direction"] == "stable"

    def test_json_serializable(self):
        labels = [_make_label("NO_TRADE") for _ in range(50)] + [_make_label("LONG_NOW") for _ in range(50)]
        result = compute_no_trade_trend(labels)
        encoded = json.dumps(result)
        assert isinstance(encoded, str)
        decoded = json.loads(encoded)
        assert decoded["total_bars"] == 100

    def test_custom_window_size(self):
        labels = [_make_label("NO_TRADE") for _ in range(100)]
        result = compute_no_trade_trend(labels, window_size=100)
        assert len(result["windows"]) >= 1
        assert result["overall_no_trade_pct"] == 100.0

    def test_few_labels(self):
        """Fewer labels than window size should still produce trend info."""
        labels = [_make_label("NO_TRADE") for _ in range(60)]
        result = compute_no_trade_trend(labels, window_size=100)
        # Should still have overall_no_trade_pct but no windows
        assert result["overall_no_trade_pct"] == 100.0
        assert result["windows"] == []


# ---------------------------------------------------------------------------
# detect_no_trade_collapse tests
# ---------------------------------------------------------------------------


class TestDetectNoTradeCollapse:
    def test_no_collapse(self):
        labels = [_make_label("LONG_NOW") for _ in range(100)]
        result = detect_no_trade_collapse(labels, "SWING")
        assert result["collapse_detected"] is False
        assert result["collapse_severity"] == "NONE"
        assert result["mode"] == "SWING"

    def test_collapse_above_threshold(self):
        labels = [_make_label("NO_TRADE") for _ in range(80)] + [_make_label("LONG_NOW") for _ in range(20)]
        result = detect_no_trade_collapse(labels, "SCALP", collapse_threshold=0.70)
        assert result["collapse_detected"] is True
        assert result["overall_no_trade_pct"] == 80.0

    def test_collapse_critical(self):
        """85%+ NO_TRADE should be CRITICAL severity."""
        labels = [_make_label("NO_TRADE") for _ in range(90)] + [_make_label("LONG_NOW") for _ in range(10)]
        result = detect_no_trade_collapse(labels, "SWING", collapse_threshold=0.70)
        assert result["collapse_detected"] is True
        assert result["collapse_severity"] == "CRITICAL"

    def test_collapse_warning(self):
        """70-85% NO_TRADE should be WARNING severity."""
        labels = [_make_label("NO_TRADE") for _ in range(75)] + [_make_label("LONG_NOW") for _ in range(25)]
        result = detect_no_trade_collapse(labels, "SWING", collapse_threshold=0.70)
        assert result["collapse_detected"] is True
        assert result["collapse_severity"] == "WARNING"

    def test_threshold_boundary(self):
        """Exactly at threshold should trigger collapse."""
        labels = [_make_label("NO_TRADE") for _ in range(70)] + [_make_label("LONG_NOW") for _ in range(30)]
        result = detect_no_trade_collapse(labels, "SWING", collapse_threshold=0.70)
        assert result["collapse_detected"] is True

    def test_below_threshold(self):
        labels = [_make_label("NO_TRADE") for _ in range(69)] + [_make_label("LONG_NOW") for _ in range(31)]
        result = detect_no_trade_collapse(labels, "SWING", collapse_threshold=0.70)
        assert result["collapse_detected"] is False
        assert result["collapse_severity"] == "NONE"

    def test_empty_input(self):
        result = detect_no_trade_collapse([], "SWING")
        assert result["collapse_detected"] is False
        assert result["collapse_severity"] == "NONE"
        assert result["overall_no_trade_pct"] == 0.0

    def test_custom_threshold(self):
        labels = [_make_label("NO_TRADE") for _ in range(50)] + [_make_label("LONG_NOW") for _ in range(50)]
        # With 0.50 threshold, 50% should trigger
        result = detect_no_trade_collapse(labels, "SWING", collapse_threshold=0.50)
        assert result["collapse_detected"] is True
        assert result["collapse_severity"] == "WARNING"

        # With 0.60 threshold, 50% should not trigger
        result2 = detect_no_trade_collapse(labels, "SWING", collapse_threshold=0.60)
        assert result2["collapse_detected"] is False

    def test_aggressive_scalp_mode(self):
        labels = [_make_label("NO_TRADE") for _ in range(200)]
        result = detect_no_trade_collapse(labels, "AGGRESSIVE_SCALP")
        assert result["mode"] == "AGGRESSIVE_SCALP"
        assert result["collapse_detected"] is True

    def test_return_keys(self):
        result = detect_no_trade_collapse([_make_label("LONG_NOW")], "SWING")
        expected_keys = {
            "collapse_detected", "collapse_severity", "overall_no_trade_pct",
            "collapse_threshold_used", "windows_above_threshold", "total_windows",
            "mode", "summary",
        }
        assert set(result.keys()) == expected_keys


# ---------------------------------------------------------------------------
# build_collapse_root_cause_tree tests
# ---------------------------------------------------------------------------


class TestBuildCollapseRootCauseTree:
    def test_empty_input(self):
        result = build_collapse_root_cause_tree([])
        assert result["total_no_trade"] == 0
        assert result["primary_cause"] == "unknown"
        assert "No label data" in result["summary"]

    def test_no_no_trade_labels(self):
        labels = [_make_label("LONG_NOW") for _ in range(10)]
        result = build_collapse_root_cause_tree(labels)
        assert result["total_no_trade"] == 0
        assert result["primary_cause"] == "none"

    def test_all_cost_dominated(self):
        labels = [_make_label("NO_TRADE", no_trade_quality="COST_DOMINATED") for _ in range(10)]
        result = build_collapse_root_cause_tree(labels)
        assert result["total_no_trade"] == 10
        assert result["primary_cause"] == "cost"
        assert result["root_cause_breakdown"]["cost"] == 100.0

    def test_all_signal(self):
        labels = [_make_label("NO_TRADE", no_trade_quality="NO_EDGE_DETECTED") for _ in range(10)]
        result = build_collapse_root_cause_tree(labels)
        assert result["primary_cause"] == "signal"
        assert result["root_cause_breakdown"]["signal"] == 100.0

    def test_all_model(self):
        labels = [_make_label("NO_TRADE", no_trade_quality="AMBIGUOUS_DIRECTION") for _ in range(10)]
        result = build_collapse_root_cause_tree(labels)
        assert result["primary_cause"] == "model"
        assert result["root_cause_breakdown"]["model"] == 100.0

    def test_all_threshold(self):
        labels = [_make_label("NO_TRADE", no_trade_quality="THRESHOLD_NOT_MET") for _ in range(10)]
        result = build_collapse_root_cause_tree(labels)
        assert result["primary_cause"] == "threshold"
        assert result["root_cause_breakdown"]["threshold"] == 100.0

    def test_mixed_causes(self):
        labels = (
            [_make_label("NO_TRADE", no_trade_quality="COST_DOMINATED") for _ in range(5)]
            + [_make_label("NO_TRADE", no_trade_quality="NO_EDGE_DETECTED") for _ in range(3)]
            + [_make_label("NO_TRADE", no_trade_quality="AMBIGUOUS") for _ in range(2)]
        )
        result = build_collapse_root_cause_tree(labels)
        assert result["total_no_trade"] == 10
        assert result["primary_cause"] == "cost"  # highest count
        assert result["root_cause_breakdown"]["cost"] == 50.0
        assert result["root_cause_breakdown"]["signal"] == 30.0
        assert result["root_cause_breakdown"]["model"] == 20.0

    def test_unclassified_labels(self):
        labels = [_make_label("NO_TRADE") for _ in range(5)]  # no no_trade_quality
        result = build_collapse_root_cause_tree(labels)
        assert result["total_no_trade"] == 5
        assert result["unclassified_count"] == 5
        assert result["primary_cause"] == "unknown"

    def test_with_collapse_result(self):
        labels = [_make_label("NO_TRADE", no_trade_quality="COST_DOMINATED") for _ in range(100)]
        collapse_result = {
            "collapse_detected": True,
            "collapse_severity": "CRITICAL",
            "overall_no_trade_pct": 100.0,
        }
        result = build_collapse_root_cause_tree(labels, collapse_result=collapse_result)
        assert result["primary_cause"] == "cost"
        assert "CRITICAL" in result["summary"]
        assert "100.0%" in result["summary"]

    def test_secondary_causes(self):
        labels = (
            [_make_label("NO_TRADE", no_trade_quality="COST_DOMINATED") for _ in range(4)]
            + [_make_label("NO_TRADE", no_trade_quality="NO_EDGE_DETECTED") for _ in range(3)]
            + [_make_label("NO_TRADE", no_trade_quality="AMBIGUOUS") for _ in range(2)]
            + [_make_label("NO_TRADE", no_trade_quality="THRESHOLD_NOT_MET") for _ in range(1)]
        )
        result = build_collapse_root_cause_tree(labels)
        # cost is primary (4 labels), so it should NOT be secondary
        assert "cost" not in result["secondary_causes"]
        assert "signal" in result["secondary_causes"]  # 3 labels
        assert "model" in result["secondary_causes"]   # 2 labels
        assert "threshold" in result["secondary_causes"]  # 1 label

    def test_return_keys(self):
        result = build_collapse_root_cause_tree([_make_label("LONG_NOW")])
        expected_keys = {
            "root_cause_breakdown", "primary_cause", "secondary_causes",
            "unclassified_count", "total_no_trade", "evidence", "summary",
        }
        assert set(result.keys()) == expected_keys


# ---------------------------------------------------------------------------
# counterfactual_analysis tests
# ---------------------------------------------------------------------------


class TestCounterfactualAnalysis:
    def test_empty_input(self):
        result = counterfactual_analysis([])
        assert result["total_no_trade"] == 0
        assert result["saved_missed_ratio"] is None

    def test_all_saved_losses(self):
        labels = [
            _make_label("NO_TRADE", net_r=-0.5),
            _make_label("NO_TRADE", net_r=-1.0),
            _make_label("NO_TRADE", net_r=-0.3),
        ]
        result = counterfactual_analysis(labels)
        assert result["total_no_trade"] == 3
        assert result["saved_loss_count"] == 3
        assert result["missed_opportunity_count"] == 0
        assert result["saved_loss_r"] == 1.8  # sum of abs values
        assert result["saved_missed_ratio"] == float("inf")

    def test_all_missed_opportunities(self):
        labels = [
            _make_label("NO_TRADE", net_r=0.5),
            _make_label("NO_TRADE", net_r=1.0),
        ]
        result = counterfactual_analysis(labels)
        assert result["total_no_trade"] == 2
        assert result["missed_opportunity_count"] == 2
        assert result["missed_opportunity_r"] == 1.5
        assert result["saved_missed_ratio"] == 0.0  # saved_r=0 / missed_r=1.5 = 0

    def test_mixed_outcomes(self):
        labels = [
            _make_label("NO_TRADE", net_r=-1.0),
            _make_label("NO_TRADE", net_r=-0.5),
            _make_label("NO_TRADE", net_r=0.3),
            _make_label("NO_TRADE", net_r=0.2),
            _make_label("LONG_NOW", net_r=2.0),  # Should be ignored (not NO_TRADE)
        ]
        result = counterfactual_analysis(labels)
        assert result["total_no_trade"] == 4
        assert result["saved_loss_count"] == 2
        assert result["missed_opportunity_count"] == 2
        assert result["saved_loss_r"] == 1.5  # |-1.0| + |-0.5|
        assert result["missed_opportunity_r"] == 0.5  # 0.3 + 0.2
        assert result["saved_missed_ratio"] == 3.0  # 1.5 / 0.5
        assert result["total_counterfactual_r"] == 1.0  # 1.5 - 0.5

    def test_neutral_trades(self):
        labels = [
            _make_label("NO_TRADE", net_r=0.0),
            _make_label("NO_TRADE", net_r=0.0),
        ]
        result = counterfactual_analysis(labels)
        assert result["total_no_trade"] == 2
        assert result["neutral_count"] == 2
        assert result["saved_loss_count"] == 0
        assert result["missed_opportunity_count"] == 0
        assert result["saved_missed_ratio"] is None

    def test_no_directional_labels(self):
        """LONG/SHORT labels should not affect counterfactual."""
        labels = [
            _make_label("LONG_NOW", net_r=5.0),
            _make_label("SHORT_NOW", net_r=3.0),
        ]
        result = counterfactual_analysis(labels)
        assert result["total_no_trade"] == 0

    def test_saved_dominates_recommendation(self):
        """When saved > missed, summary should say 'correctly risk-averse'."""
        labels = [
            _make_label("NO_TRADE", net_r=-2.0),
            _make_label("NO_TRADE", net_r=-1.0),
            _make_label("NO_TRADE", net_r=0.1),
        ]
        result = counterfactual_analysis(labels)
        assert "correctly avoids more loss" in result["summary"].lower()

    def test_missed_dominates_recommendation(self):
        """When missed > saved, summary should suggest reducing threshold."""
        labels = [
            _make_label("NO_TRADE", net_r=2.0),
            _make_label("NO_TRADE", net_r=1.0),
            _make_label("NO_TRADE", net_r=-0.1),
        ]
        result = counterfactual_analysis(labels)
        assert "misses more opportunity" in result["summary"].lower()

    def test_return_keys(self):
        result = counterfactual_analysis([_make_label("NO_TRADE", net_r=-0.5)])
        expected_keys = {
            "total_no_trade", "saved_loss_count", "missed_opportunity_count",
            "saved_loss_r", "missed_opportunity_r", "total_counterfactual_r",
            "saved_missed_ratio", "neutral_count", "summary",
        }
        assert set(result.keys()) == expected_keys


# ---------------------------------------------------------------------------
# build_collapse_report tests (integration)
# ---------------------------------------------------------------------------


class TestBuildCollapseReport:
    def test_no_collapse_scenario(self):
        """Mixed labels with no collapse should report no collapse."""
        labels = (
            [_make_label("LONG_NOW") for _ in range(150)]
            + [_make_label("SHORT_NOW") for _ in range(50)]
        )
        result = build_collapse_report(labels, "SWING")
        assert result["collapse_detected"] is False
        assert result["collapse_severity"] == "NONE"
        assert result["mode"] == "SWING"
        assert "no collapse" in result["summary"].lower()

    def test_collapse_scenario(self):
        """Mostly NO_TRADE labels should detect collapse."""
        labels = (
            [_make_label("NO_TRADE", net_r=-0.5, no_trade_quality="COST_DOMINATED") for _ in range(80)]
            + [_make_label("LONG_NOW", net_r=1.0) for _ in range(20)]
        )
        result = build_collapse_report(labels, "SCALP")
        assert result["collapse_detected"] is True
        assert result["trend"]["overall_no_trade_pct"] == 80.0
        assert result["detection"]["collapse_severity"] == "WARNING"
        assert result["root_cause"]["primary_cause"] == "cost"
        assert result["counterfactual"]["saved_loss_count"] > 0

    def test_critical_collapse_with_root_cause(self):
        """Severe collapse with root cause attribution."""
        labels = (
            [_make_label("NO_TRADE", net_r=-1.0, no_trade_quality="NO_EDGE_DETECTED") for _ in range(180)]
            + [_make_label("LONG_NOW", net_r=0.5) for _ in range(20)]
        )
        result = build_collapse_report(labels, "AGGRESSIVE_SCALP")
        assert result["collapse_detected"] is True
        assert result["collapse_severity"] == "CRITICAL"
        assert result["root_cause"]["primary_cause"] == "signal"
        assert result["counterfactual"]["saved_loss_count"] > 0

    def test_all_keys_present(self):
        labels = [_make_label("LONG_NOW") for _ in range(50)]
        result = build_collapse_report(labels, "SWING")
        expected_keys = {
            "collapse_detected", "collapse_severity", "trend",
            "detection", "root_cause", "counterfactual",
            "mode", "summary",
        }
        assert set(result.keys()) == expected_keys

    def test_empty_input(self):
        result = build_collapse_report([], "SWING")
        assert result["collapse_detected"] is False
        assert result["mode"] == "SWING"
        assert isinstance(result["trend"], dict)
        assert isinstance(result["detection"], dict)
        assert isinstance(result["root_cause"], dict)
        assert isinstance(result["counterfactual"], dict)

    def test_json_serializable(self):
        labels = (
            [_make_label("NO_TRADE", net_r=-0.5, no_trade_quality="COST_DOMINATED") for _ in range(70)]
            + [_make_label("LONG_NOW", net_r=1.0) for _ in range(30)]
        )
        result = build_collapse_report(labels, "SWING")
        encoded = json.dumps(result)
        assert isinstance(encoded, str)
        decoded = json.loads(encoded)
        assert decoded["collapse_detected"] is True
        assert decoded["mode"] == "SWING"

    def test_custom_threshold(self):
        """Custom threshold should affect detection."""
        labels = [_make_label("NO_TRADE") for _ in range(50)] + [_make_label("LONG_NOW") for _ in range(50)]
        result_default = build_collapse_report(labels, "SWING")
        assert result_default["collapse_detected"] is False

        result_custom = build_collapse_report(labels, "SWING", collapse_threshold=0.50)
        assert result_custom["collapse_detected"] is True

    def test_exists_in_reports_package(self):
        """All functions should be exported from reports package."""
        from alphaforge.reports import (
            build_collapse_report as exported_report,
            build_collapse_root_cause_tree as exported_rct,
            compute_no_trade_trend as exported_trend,
            counterfactual_analysis as exported_cfa,
            detect_no_trade_collapse as exported_detect,
        )
        assert exported_report is build_collapse_report
        assert exported_rct is build_collapse_root_cause_tree
        assert exported_trend is compute_no_trade_trend
        assert exported_cfa is counterfactual_analysis
        assert exported_detect is detect_no_trade_collapse
        assert callable(exported_report)
        assert callable(exported_rct)
        assert callable(exported_trend)
        assert callable(exported_cfa)
        assert callable(exported_detect)

    def test_no_xgboost_import(self):
        """No xgboost import in collapse_detector.py."""
        import inspect
        import alphaforge.reports.collapse_detector as mod
        source = inspect.getsource(mod)
        assert "import xgboost" not in source
        assert "from xgboost" not in source
        assert "XGBClassifier" not in source
        assert "XGBRegressor" not in source


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_single_label(self):
        """Single label should not crash."""
        labels = [_make_label("NO_TRADE")]
        result = compute_no_trade_trend(labels)
        assert result["total_bars"] == 1
        assert result["overall_no_trade_pct"] == 100.0

    def test_exactly_window_size(self):
        """Exactly window_size labels should produce one window."""
        labels = [_make_label("NO_TRADE") for _ in range(100)]
        result = compute_no_trade_trend(labels, window_size=100)
        assert len(result["windows"]) >= 1

    def test_all_different_actions(self):
        """Mix of all action types."""
        labels = [
            _make_label("LONG_NOW"),
            _make_label("SHORT_NOW"),
            _make_label("NO_TRADE"),
            _make_label("AMBIGUOUS"),
            _make_label("UNKNOWN"),
        ]
        result = compute_no_trade_trend(labels)
        assert result["total_bars"] == 5
        assert result["overall_no_trade_pct"] == 20.0  # 1/5 = 20%

    def test_no_trade_quality_with_net_r_zero(self):
        """Labels with no_trade_quality but zero net_r."""
        labels = [_make_label("NO_TRADE", net_r=0.0, no_trade_quality="COST_DOMINATED")]
        result = counterfactual_analysis(labels)
        assert result["neutral_count"] == 1

    def test_no_trade_variants(self):
        """Different NO_TRADE spellings should all be detected."""
        labels = [
            _make_label("NO_TRADE"),
            _make_label("NO TRADE"),
            _make_label("no_trade"),
            _make_label("NO_TRADE_LABEL"),
        ]
        result = compute_no_trade_trend(labels)
        assert result["overall_no_trade_pct"] == 100.0
        assert result["total_bars"] == 4
