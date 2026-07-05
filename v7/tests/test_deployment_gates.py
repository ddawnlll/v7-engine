"""Tests for v7.deployment_gates — deployment safety and release gates."""

import pytest

from v7.deployment_gates import (
    PaperModeManager,
    PaperExecutionResult,
    PaperModeReport,
    ShadowEvaluationManager,
    ShadowEvaluation,
    ReleaseGatePipeline,
    ReleaseStage,
    ReleasePipelineResult,
)


class TestPaperModeManager:
    """Test PaperModeManager."""

    def _make_decision(self, decision="LONG_NOW", symbol="BTCUSDT", expected_r=0.5, price=100.0):
        return {
            "decision": decision,
            "symbol": symbol,
            "expected_r": expected_r,
            "price": price,
            "holding_bars": 5,
        }

    def test_execute_paper_creates_result(self):
        """Executing paper trade should create a result."""
        mgr = PaperModeManager()
        result = mgr.execute_paper(self._make_decision(), "swing_v1")
        assert isinstance(result, PaperExecutionResult)
        assert result.scope == "swing_v1"
        assert result.decision == "LONG_NOW"

    def test_execute_paper_records_result(self):
        """Paper results should be stored."""
        mgr = PaperModeManager()
        mgr.execute_paper(self._make_decision(), "swing_v1")
        report = mgr.get_report("swing_v1")
        assert report.total_trades == 1
        assert abs(report.total_realized_r) > 0

    def test_empty_scope_report(self):
        """Empty scope should return empty report."""
        mgr = PaperModeManager()
        report = mgr.get_report("unknown")
        assert report.total_trades == 0

    def test_no_trade_decisions_excluded(self):
        """NO_TRADE decisions should not count as trades."""
        mgr = PaperModeManager()
        mgr.execute_paper(self._make_decision(decision="NO_TRADE"), "swing_v1")
        report = mgr.get_report("swing_v1")
        assert report.total_trades == 0

    def test_multiple_trades_aggregate(self):
        """Multiple trades should produce aggregate report."""
        mgr = PaperModeManager()
        mgr.execute_paper(self._make_decision("LONG_NOW", expected_r=0.5), "swing_v1")
        mgr.execute_paper(self._make_decision("SHORT_NOW", expected_r=0.3), "swing_v1")
        mgr.execute_paper(self._make_decision("LONG_NOW", expected_r=-0.2), "swing_v1")
        report = mgr.get_report("swing_v1")
        assert report.total_trades == 3

    def test_win_rate(self):
        """Win rate should be computed correctly."""
        mgr = PaperModeManager()
        mgr.execute_paper(self._make_decision("LONG_NOW", expected_r=0.5), "swing_v1")
        mgr.execute_paper(self._make_decision("LONG_NOW", expected_r=-0.3), "swing_v1")
        report = mgr.get_report("swing_v1")
        # expected_r=0.5 * 0.9 = 0.45 (positive = win)
        # expected_r=-0.3 * 0.9 = -0.27 (negative = loss)
        assert report.total_trades == 2
        assert report.win_rate == 0.5


class TestShadowEvaluationManager:
    """Test ShadowEvaluationManager."""

    def _make_live_decision(self, decision="LONG_NOW"):
        return {"decision": decision}

    class _MockShadowRecord:
        def __init__(self, shadow_decision):
            self.shadow_decision = shadow_decision

    def test_evaluate_consistent(self):
        """Consistent shadow and live should show high consistency."""
        mgr = ShadowEvaluationManager()
        live = [self._make_live_decision("LONG_NOW") for _ in range(5)]
        shadow = [self._MockShadowRecord("LONG_NOW") for _ in range(5)]
        evaluation = mgr.evaluate("swing_v1", live, shadow)
        assert evaluation.consistency == 1.0
        assert evaluation.shadow_decisions == 5

    def test_evaluate_inconsistent(self):
        """Inconsistent shadow and live should show low consistency."""
        mgr = ShadowEvaluationManager()
        live = [self._make_live_decision("LONG_NOW") for _ in range(5)]
        shadow = [self._MockShadowRecord("SHORT_NOW") for _ in range(5)]
        evaluation = mgr.evaluate("swing_v1", live, shadow)
        assert evaluation.consistency == 0.0
        assert len(evaluation.divergence_patterns) == 5

    def test_evaluate_partial(self):
        """Partial consistency should be reflected."""
        mgr = ShadowEvaluationManager()
        live = [self._make_live_decision("LONG_NOW"),
                self._make_live_decision("SHORT_NOW"),
                self._make_live_decision("LONG_NOW")]
        shadow = [self._MockShadowRecord("LONG_NOW"),
                  self._MockShadowRecord("SHORT_NOW"),
                  self._MockShadowRecord("NO_TRADE")]
        evaluation = mgr.evaluate("swing_v1", live, shadow)
        assert evaluation.consistency == 2 / 3

    def test_empty_data(self):
        """Empty data should not cause errors."""
        mgr = ShadowEvaluationManager()
        evaluation = mgr.evaluate("swing_v1", [], [])
        assert evaluation.shadow_decisions == 0

    def test_get_evaluations(self):
        """Evaluation history should be accessible."""
        mgr = ShadowEvaluationManager()
        mgr.evaluate("swing_v1", [self._make_live_decision()], [self._MockShadowRecord("LONG_NOW")])
        mgr.evaluate("scalp_v1", [self._make_live_decision()], [self._MockShadowRecord("LONG_NOW")])
        assert len(mgr.get_evaluations()) == 2
        assert len(mgr.get_evaluations(scope="swing_v1")) == 1


class TestReleaseGatePipeline:
    """Test ReleaseGatePipeline."""

    def _make_stage_result(self, name, passed=True):
        return ReleaseStage(
            name=name, passed=passed,
            detail=f"{name} {'passed' if passed else 'failed'}",
            timestamp="2026-01-01T00:00:00Z",
        )

    def test_evaluate_candidate_stage_passes(self):
        """Candidate stage should pass when result is passing."""
        pipeline = ReleaseGatePipeline()
        stage = pipeline.evaluate_stage(
            "cand_001", "candidate",
            candidate_result={"passed": True, "summary": {"recommendation": "PROMOTE"}},
        )
        assert stage.passed is True
        assert stage.name == "candidate"

    def test_evaluate_candidate_stage_fails(self):
        """Candidate stage should fail when result fails."""
        pipeline = ReleaseGatePipeline()
        stage = pipeline.evaluate_stage(
            "cand_001", "candidate",
            candidate_result={"passed": False, "summary": {"recommendation": "HOLD"}},
        )
        assert stage.passed is False

    def test_evaluate_paper_stage_passes(self):
        """Paper stage should pass with good paper results."""
        pipeline = ReleaseGatePipeline()
        paper = PaperModeReport(scope="swing_v1", total_trades=50, win_rate=0.55)
        stage = pipeline.evaluate_stage("cand_001", "paper", paper_result=paper)
        assert stage.passed is True

    def test_evaluate_paper_stage_fails(self):
        """Paper stage should fail with poor paper results."""
        pipeline = ReleaseGatePipeline()
        paper = PaperModeReport(scope="swing_v1", total_trades=0, win_rate=0.0)
        stage = pipeline.evaluate_stage("cand_001", "paper", paper_result=paper)
        assert stage.passed is False

    def test_evaluate_shadow_stage_passes(self):
        """Shadow stage should pass with high consistency."""
        pipeline = ReleaseGatePipeline()
        shadow = ShadowEvaluation(scope="swing_v1", shadow_decisions=50, consistency=0.95)
        stage = pipeline.evaluate_stage("cand_001", "shadow", shadow_evaluation=shadow)
        assert stage.passed is True

    def test_evaluate_shadow_stage_fails(self):
        """Shadow stage should fail with low consistency."""
        pipeline = ReleaseGatePipeline()
        shadow = ShadowEvaluation(scope="swing_v1", shadow_decisions=50, consistency=0.5)
        stage = pipeline.evaluate_stage("cand_001", "shadow", shadow_evaluation=shadow)
        assert stage.passed is False

    def test_evaluate_live_stage_passes(self):
        """Live stage should pass with G10 PASS."""
        pipeline = ReleaseGatePipeline()
        stage = pipeline.evaluate_stage(
            "cand_001", "live",
            gate_results={"G10": {"status": "PASS", "detail": "Ready"}},
        )
        assert stage.passed is True

    def test_evaluate_live_stage_fails(self):
        """Live stage should fail without G10 PASS."""
        pipeline = ReleaseGatePipeline()
        stage = pipeline.evaluate_stage(
            "cand_001", "live",
            gate_results={"G10": {"status": "FAIL", "detail": "Not ready"}},
        )
        assert stage.passed is False

    def test_unknown_stage_raises(self):
        """Unknown stage name should raise ValueError."""
        pipeline = ReleaseGatePipeline()
        with pytest.raises(ValueError, match="Unknown stage"):
            pipeline.evaluate_stage("cand_001", "unknown")

    def test_run_pipeline_all_pass(self):
        """Full pipeline with all passing should succeed."""
        pipeline = ReleaseGatePipeline()
        result = pipeline.run_pipeline(
            "cand_001",
            candidate_result={"passed": True, "summary": {"recommendation": "PROMOTE"}},
            paper_result=PaperModeReport(scope="swing_v1", total_trades=50, win_rate=0.55),
            shadow_evaluation=ShadowEvaluation(scope="swing_v1", shadow_decisions=50, consistency=0.95),
            gate_results={"G10": {"status": "PASS", "detail": "Ready"}},
        )
        assert result.all_passed is True
        assert len(result.stages) == 4
        assert result.candidate_id == "cand_001"

    def test_run_pipeline_stops_on_fail(self):
        """Pipeline should stop at first failure when stop_on_fail=True."""
        pipeline = ReleaseGatePipeline()
        result = pipeline.run_pipeline(
            "cand_001",
            candidate_result={"passed": False, "summary": {"recommendation": "REJECT"}},
            # The rest don't matter since it stops at candidate
        )
        assert result.all_passed is False
        assert result.current_stage == "candidate"
        assert len(result.stages) >= 1

    def test_run_pipeline_continues_without_stop(self):
        """Pipeline with stop_on_fail=False should continue past failures."""
        pipeline = ReleaseGatePipeline()
        result = pipeline.run_pipeline(
            "cand_001",
            candidate_result={"passed": False, "summary": {"recommendation": "REJECT"}},
            paper_result=PaperModeReport(scope="swing_v1", total_trades=50, win_rate=0.55),
            stop_on_fail=False,
        )
        assert len(result.stages) == 4  # All stages evaluated

    def test_evaluate_stage_no_result(self):
        """Missing result should fail the stage."""
        pipeline = ReleaseGatePipeline()
        stage = pipeline.evaluate_stage("cand_001", "candidate")
        assert stage.passed is False
        assert "No candidate" in stage.detail
