"""Tests for v7.no_trade_validation — no-trade behavior validation."""

import pytest

from v7.no_trade_validation import (
    NoTradeReport,
    compare_to_baseline,
    detect_no_trade_patterns,
    analyze_false_no_trades,
)


class TestDetectNoTradePatterns:
    """Test no-trade pattern detection."""

    def _make_decision(self, decision, outcome_r=0.0, expected_r=0.0, confidence=0.5):
        return {
            "decision": decision,
            "outcome_r": outcome_r,
            "expected_r": expected_r,
            "confidence": confidence,
        }

    def test_empty_decisions(self):
        """Empty decisions should produce empty report."""
        report = detect_no_trade_patterns([])
        assert report.total_decisions == 0
        assert report.no_trade_count == 0

    def test_no_no_trades(self):
        """No NO_TRADE decisions should show zero rate."""
        decisions = [
            self._make_decision("LONG_NOW", outcome_r=0.5),
            self._make_decision("SHORT_NOW", outcome_r=-0.3),
        ]
        report = detect_no_trade_patterns(decisions)
        assert report.no_trade_count == 0
        assert report.no_trade_rate == 0.0

    def test_detects_correct_no_trades(self):
        """NO_TRADE decisions that avoided losses should count as correct."""
        decisions = [
            self._make_decision("NO_TRADE", outcome_r=-0.5),
            self._make_decision("NO_TRADE", outcome_r=-1.2),
            self._make_decision("LONG_NOW", outcome_r=0.3),
        ]
        report = detect_no_trade_patterns(decisions)
        assert report.no_trade_count == 2
        assert report.correct_no_trades == 2
        assert report.saved_loss_r == 1.7

    def test_detects_missed_opportunities(self):
        """NO_TRADE decisions that missed profits should count as missed."""
        decisions = [
            self._make_decision("NO_TRADE", outcome_r=0.8),
            self._make_decision("NO_TRADE", outcome_r=0.5),
        ]
        report = detect_no_trade_patterns(decisions)
        assert report.missed_opportunities == 2
        assert report.missed_opportunity_r == 1.3

    def test_detects_over_suppression(self):
        """NO_TRADE with high expected_r should flag over-suppression."""
        decisions = [
            self._make_decision("NO_TRADE", expected_r=0.8),
            self._make_decision("NO_TRADE", expected_r=0.6),
            self._make_decision("LONG_NOW", expected_r=0.3),
        ]
        report = detect_no_trade_patterns(decisions)
        assert report.over_suppression == 2

    def test_detects_under_suppression(self):
        """Trades with strongly negative outcomes should flag under-suppression."""
        decisions = [
            self._make_decision("LONG_NOW", outcome_r=-2.0),
            self._make_decision("SHORT_NOW", outcome_r=-1.5),
        ]
        report = detect_no_trade_patterns(decisions)
        assert report.under_suppression == 2

    def test_excessive_no_trade_pattern(self):
        """High no-trade rate should produce pattern."""
        decisions = [self._make_decision("NO_TRADE") for _ in range(8)]
        decisions.append(self._make_decision("LONG_NOW", outcome_r=0.5))
        decisions.append(self._make_decision("SHORT_NOW", outcome_r=0.3))
        report = detect_no_trade_patterns(decisions)
        assert "excessive_no_trade" in report.patterns

    def test_metrics_computed(self):
        """Metrics dict should be populated."""
        decisions = [
            self._make_decision("NO_TRADE", outcome_r=-0.5),
            self._make_decision("NO_TRADE", outcome_r=0.3),
            self._make_decision("LONG_NOW", outcome_r=0.2),
        ]
        report = detect_no_trade_patterns(decisions)
        assert "no_trade_rate" in report.metrics
        assert "correct_no_trade_rate" in report.metrics
        assert report.metrics["correct_no_trade_rate"] == 0.5


class TestCompareToBaseline:
    """Test no-trade baseline comparison."""

    def _make_report(self, no_trade_rate=0.3, correct_rate=0.6, saved_loss=5.0, missed_r=2.0):
        return NoTradeReport(
            total_decisions=100,
            no_trade_count=int(100 * no_trade_rate),
            no_trade_rate=no_trade_rate,
            correct_no_trades=int(100 * no_trade_rate * correct_rate),
            saved_loss_r=saved_loss,
            missed_opportunity_r=missed_r,
            metrics={
                "no_trade_rate": no_trade_rate,
                "correct_no_trade_rate": correct_rate,
            },
        )

    def test_no_change(self):
        """Identical reports should show no significant delta."""
        report = self._make_report()
        delta = compare_to_baseline(report, report)
        assert delta.no_trade_rate_delta == 0.0
        assert delta.significant is False

    def test_significant_increase(self):
        """Large increase in no-trade rate should be significant."""
        baseline = self._make_report(no_trade_rate=0.3)
        current = self._make_report(no_trade_rate=0.5)
        delta = compare_to_baseline(current, baseline)
        assert delta.significant is True
        assert delta.no_trade_rate_delta == 0.2

    def test_custom_threshold(self):
        """Custom threshold should control significance."""
        baseline = self._make_report(no_trade_rate=0.3)
        current = self._make_report(no_trade_rate=0.35)
        delta = compare_to_baseline(current, baseline, threshold=0.1)
        assert delta.significant is False


class TestAnalyzeFalseNoTrades:
    """Test false no-trade analysis."""

    def test_no_false_no_trades(self):
        """No false no-trades when all outcomes are negative."""
        decisions = [
            {"event_id": "e1", "decision": "NO_TRADE", "expected_r": 0.0},
            {"event_id": "e2", "decision": "NO_TRADE", "expected_r": 0.0},
        ]
        outcomes = [
            {"event_id": "e1", "outcome_r": -0.5},
            {"event_id": "e2", "outcome_r": -0.3},
        ]
        analysis = analyze_false_no_trades(decisions, outcomes)
        assert analysis["false_no_trade_count"] == 0

    def test_detects_false_no_trades(self):
        """Should detect NO_TRADE decisions where outcome was positive."""
        decisions = [
            {"event_id": "e1", "decision": "NO_TRADE", "expected_r": 0.0},
            {"event_id": "e2", "decision": "LONG_NOW", "expected_r": 0.5},
        ]
        outcomes = [
            {"event_id": "e1", "outcome_r": 0.8},
            {"event_id": "e2", "outcome_r": 0.5},
        ]
        analysis = analyze_false_no_trades(decisions, outcomes)
        assert analysis["false_no_trade_count"] == 1
        assert analysis["total_missed_r"] == 0.8

    def test_total_missed_r_accumulated(self):
        """Total missed R should accumulate across false no-trades."""
        decisions = [
            {"event_id": "e1", "decision": "NO_TRADE", "expected_r": 0.0},
            {"event_id": "e2", "decision": "NO_TRADE", "expected_r": 0.0},
        ]
        outcomes = [
            {"event_id": "e1", "outcome_r": 1.0},
            {"event_id": "e2", "outcome_r": 2.0},
        ]
        analysis = analyze_false_no_trades(decisions, outcomes)
        assert analysis["false_no_trade_count"] == 2
        assert analysis["total_missed_r"] == 3.0

    def test_false_no_trade_rate(self):
        """False no-trade rate should be computed correctly."""
        decisions = [
            {"event_id": f"e{i}", "decision": "NO_TRADE", "expected_r": 0.0}
            for i in range(10)
        ]
        outcomes = [
            {"event_id": f"e{i}", "outcome_r": 0.5 if i < 3 else -0.5}
            for i in range(10)
        ]
        analysis = analyze_false_no_trades(decisions, outcomes)
        assert analysis["total_no_trades"] == 10
        assert analysis["false_no_trade_count"] == 3
        assert analysis["false_no_trade_rate"] == 0.3
