"""Tests for v7.gates — G0-G10 promotion gate framework."""

import pytest

from v7.gates.evaluator import (
    GATE_DEFINITIONS,
    GateResult,
    GateStatus,
    evaluate_candidate,
    evaluate_gate,
    get_promotion_summary,
)


class TestEvaluateGate:
    """Test individual gate evaluation."""

    def _swing_candidate(self, **overrides):
        base = {
            "request_id": "req_001",
            "mode": "SWING",
            "symbol": "BTCUSDT",
            "model_scope": "swing_v1",
        }
        base.update(overrides)
        return base

    def test_g0_structural_pass(self):
        """G0 should pass for valid candidate."""
        candidate = self._swing_candidate()
        result = evaluate_gate("G0", candidate)
        assert result.status == GateStatus.PASS
        assert result.gate_id == "G0"

    def test_g0_structural_fail_missing_fields(self):
        """G0 should fail for missing required fields."""
        candidate = {"mode": "SWING"}  # Missing request_id, symbol, model_scope
        result = evaluate_gate("G0", candidate)
        assert result.status == GateStatus.FAIL

    def test_g0_structural_fail_invalid_mode(self):
        """G0 should fail for invalid mode."""
        candidate = self._swing_candidate(mode="INVALID_MODE")
        result = evaluate_gate("G0", candidate)
        assert result.status == GateStatus.FAIL

    def test_g6_walk_forward_pass(self):
        """G6 should pass when expectancy R is above threshold."""
        candidate = self._swing_candidate()
        ctx = {"expectancy_r": 0.50}
        result = evaluate_gate("G6", candidate, ctx)
        assert result.status == GateStatus.PASS

    def test_g6_walk_forward_fail(self):
        """G6 should fail when expectancy R is below threshold."""
        candidate = self._swing_candidate()
        ctx = {"expectancy_r": 0.10}
        result = evaluate_gate("G6", candidate, ctx)
        assert result.status == GateStatus.FAIL

    def test_g9_cost_stress_pass(self):
        """G9 should pass when expected_r_net > 0."""
        candidate = self._swing_candidate()
        ctx = {"expected_r_net": 0.85}
        result = evaluate_gate("G9", candidate, ctx)
        assert result.status == GateStatus.PASS

    def test_g9_cost_stress_fail(self):
        """G9 should fail when expected_r_net <= 0."""
        candidate = self._swing_candidate()
        ctx = {"expected_r_net": -0.10}
        result = evaluate_gate("G9", candidate, ctx)
        assert result.status == GateStatus.FAIL

    def test_g10_live_readiness_na(self):
        """G10 should return NOT_APPLICABLE for baseline."""
        candidate = self._swing_candidate()
        result = evaluate_gate("G10", candidate)
        assert result.status == GateStatus.NOT_APPLICABLE

    def test_unknown_gate_raises(self):
        """Unknown gate ID should raise ValueError."""
        candidate = self._swing_candidate()
        with pytest.raises(ValueError, match="Unknown gate_id"):
            evaluate_gate("G99", candidate)


class TestEvaluateCandidate:
    """Test full candidate evaluation through all gates."""

    def _swing_candidate(self):
        return {
            "request_id": "req_001",
            "mode": "SWING",
            "symbol": "BTCUSDT",
            "model_scope": "swing_v1",
        }

    def test_all_gates_evaluated(self):
        """All 11 gates (G0-G10) should be evaluated."""
        candidate = self._swing_candidate()
        ctx = {
            "expectancy_r": 0.50,
            "expected_r_net": 0.85,
            "ece": 0.05,
            "model_signature": "swing_v1@abc123",
        }
        results = evaluate_candidate(candidate, ctx)
        assert len(results) == 11
        for gate_id in [f"G{i}" for i in range(11)]:
            assert gate_id in results, f"Missing gate {gate_id}"

    def test_strong_candidate_passes_all(self):
        """Strong candidate should pass all applicable gates."""
        candidate = self._swing_candidate()
        ctx = {
            "expectancy_r": 1.2,
            "expected_r_net": 0.90,
            "ece": 0.03,
            "model_signature": "swing_v1@abc123",
        }
        results = evaluate_candidate(candidate, ctx)
        summary = get_promotion_summary(results)
        assert summary["passed"] is True
        assert "PROMOTE" in summary["recommendation"]

    def test_weak_candidate_fails_g6(self):
        """Weak candidate should fail G6 (walk-forward)."""
        candidate = self._swing_candidate()
        ctx = {
            "expectancy_r": 0.10,  # Below SWING min 0.35
            "expected_r_net": 0.05,
            "ece": 0.08,
            "model_signature": "swing_v1@abc123",
        }
        results = evaluate_candidate(candidate, ctx)
        summary = get_promotion_summary(results)
        assert summary["passed"] is False
        assert "G6" in summary["failed_gates"]
        assert "HOLD" in summary["recommendation"]

    def test_stop_on_fail(self):
        """stop_on_fail should stop after first failure."""
        # Use a candidate that fails G0 (invalid mode)
        candidate = {
            "request_id": "req_001",
            "mode": "INVALID_MODE",
            "symbol": "BTCUSDT",
            "model_scope": "swing_v1",
        }
        ctx = {}
        results = evaluate_candidate(candidate, ctx, stop_on_fail=True)
        assert len(results) < 11
        # First gate (G0) should fail
        assert results["G0"].status == GateStatus.FAIL


class TestGetPromotionSummary:
    """Test promotion summary generation."""

    def test_all_pass(self):
        """All PASS should recommend PROMOTE."""
        results = {
            "G0": GateResult("G0", "Structural", GateStatus.PASS, 1.0, 1.0, "ok"),
            "G1": GateResult("G1", "Data", GateStatus.PASS, 1.0, 0.9, "ok"),
            "G2": GateResult("G2", "Labels", GateStatus.PASS, 1.0, 1.0, "ok"),
        }
        summary = get_promotion_summary(results)
        assert summary["passed"] is True
        assert summary["recommendation"] == "PROMOTE"
        assert summary["overall_score"] == 1.0

    def test_one_fail(self):
        """Any FAIL should recommend HOLD."""
        results = {
            "G0": GateResult("G0", "Structural", GateStatus.PASS, 1.0, 1.0, "ok"),
            "G1": GateResult("G1", "Data", GateStatus.FAIL, 0.0, 0.9, "bad"),
        }
        summary = get_promotion_summary(results)
        assert summary["passed"] is False
        assert "HOLD" in summary["recommendation"]
        assert "G1" in summary["failed_gates"]

    def test_not_applicable_excluded(self):
        """NOT_APPLICABLE gates should not affect pass/fail."""
        results = {
            "G0": GateResult("G0", "Structural", GateStatus.PASS, 1.0, 1.0, "ok"),
            "G10": GateResult(
                "G10", "Live", GateStatus.NOT_APPLICABLE, 0.0, 1.0, "na"
            ),
        }
        summary = get_promotion_summary(results)
        assert summary["passed"] is True
        assert "G10" in summary["na_gates"]


class TestGateResult:
    """Test GateResult dataclass."""

    def test_immutable(self):
        """GateResult should be immutable."""
        result = GateResult("G0", "Structural", GateStatus.PASS, 1.0, 1.0, "ok")
        with pytest.raises(Exception):
            result.status = GateStatus.FAIL  # type: ignore

    def test_repr(self):
        """GateResult should have readable repr."""
        result = GateResult("G0", "Structural Validity", GateStatus.PASS, 1.0, 1.0, "ok")
        assert "G0" in repr(result)
        assert "PASS" in repr(result)


class TestGateDefinitions:
    """Verify GATE_DEFINITIONS integrity."""

    def test_eleven_gates(self):
        """Should have exactly 11 gates (G0-G10)."""
        assert len(GATE_DEFINITIONS) == 11

    def test_sequential(self):
        """Gates should be in G0-G10 order."""
        expected = [f"G{i}" for i in range(11)]
        actual = [gid for gid, _, _ in GATE_DEFINITIONS]
        assert actual == expected

    def test_each_gate_has_unique_id(self):
        """Each gate should have a unique ID."""
        ids = [gid for gid, _, _ in GATE_DEFINITIONS]
        assert len(ids) == len(set(ids))

    def test_all_gates_have_names(self):
        """Each gate should have a non-empty name."""
        for gid, name, fn in GATE_DEFINITIONS:
            assert name, f"Gate {gid} has empty name"
            assert callable(fn), f"Gate {gid} fn is not callable"
