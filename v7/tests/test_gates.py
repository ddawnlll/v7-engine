"""Tests for v7.gates — canonical G0-G10 promotion gate framework."""

import pytest

from v7.gates.evaluator import (
    CANONICAL_GATE_NAMES,
    GATE_DEFINITIONS,
    GateResult,
    GateStatus,
    evaluate_candidate,
    evaluate_gate,
    get_promotion_summary,
)


class TestEvaluateGate:
    """Test individual canonical gate evaluation."""

    def _swing_candidate(self, **overrides):
        base = {
            "request_id": "req_001",
            "mode": "SWING",
            "symbol": "BTCUSDT",
            "model_scope": "swing_v1",
        }
        base.update(overrides)
        return base

    # ── G0: DOC_READY ──────────────────────────────────────────────

    def test_g0_doc_ready_pass(self):
        """G0 DOC_READY should pass for valid candidate."""
        candidate = self._swing_candidate()
        result = evaluate_gate("G0", candidate)
        assert result.status == GateStatus.PASS
        assert result.gate_id == "G0"
        assert result.name == "DOC_READY"

    def test_g0_doc_ready_fail_missing_fields(self):
        """G0 DOC_READY should fail for missing required fields."""
        candidate = {"mode": "SWING"}
        result = evaluate_gate("G0", candidate)
        assert result.status == GateStatus.FAIL

    def test_g0_doc_ready_fail_invalid_mode(self):
        """G0 DOC_READY should fail for invalid mode."""
        candidate = self._swing_candidate(mode="INVALID_MODE")
        result = evaluate_gate("G0", candidate)
        assert result.status == GateStatus.FAIL

    # ── G2: WALK_FORWARD_OOS ───────────────────────────────────────

    def test_g2_walk_forward_oos_pass(self):
        """G2 WALK_FORWARD_OOS should pass when expectancy R >= threshold."""
        candidate = self._swing_candidate()
        ctx = {"expectancy_r": 0.50}
        result = evaluate_gate("G2", candidate, ctx)
        assert result.status == GateStatus.PASS
        assert result.name == "WALK_FORWARD_OOS"

    def test_g2_walk_forward_oos_fail(self):
        """G2 WALK_FORWARD_OOS should fail when expectancy R below threshold."""
        candidate = self._swing_candidate()
        ctx = {"expectancy_r": 0.10}
        result = evaluate_gate("G2", candidate, ctx)
        assert result.status == GateStatus.FAIL

    # ── G3: COST_STRESS ────────────────────────────────────────────

    def test_g3_cost_stress_pass(self):
        """G3 COST_STRESS should pass when expected_r_net > 0."""
        candidate = self._swing_candidate()
        ctx = {"expected_r_net": 0.85}
        result = evaluate_gate("G3", candidate, ctx)
        assert result.status == GateStatus.PASS
        assert result.name == "COST_STRESS"

    def test_g3_cost_stress_fail(self):
        """G3 COST_STRESS should fail when expected_r_net <= 0."""
        candidate = self._swing_candidate()
        ctx = {"expected_r_net": -0.10}
        result = evaluate_gate("G3", candidate, ctx)
        assert result.status == GateStatus.FAIL

    # ── G7/G8/G9/G10: infrastructure gates ─────────────────────────

    def test_g7_shadow_na(self):
        """G7 SHADOW should return NOT_APPLICABLE (infra not built)."""
        candidate = self._swing_candidate()
        result = evaluate_gate("G7", candidate)
        assert result.status == GateStatus.NOT_APPLICABLE
        assert result.name == "SHADOW"

    def test_g8_paper_na(self):
        """G8 PAPER should return NOT_APPLICABLE (infra not built)."""
        candidate = self._swing_candidate()
        result = evaluate_gate("G8", candidate)
        assert result.status == GateStatus.NOT_APPLICABLE

    def test_g9_tiny_live_na(self):
        """G9 TINY_LIVE should return NOT_APPLICABLE (infra not built)."""
        candidate = self._swing_candidate()
        result = evaluate_gate("G9", candidate)
        assert result.status == GateStatus.NOT_APPLICABLE

    def test_g10_live_na(self):
        """G10 LIVE should return NOT_APPLICABLE for baseline."""
        candidate = self._swing_candidate()
        result = evaluate_gate("G10", candidate)
        assert result.status == GateStatus.NOT_APPLICABLE
        assert result.name == "LIVE"

    # ── Canonical gate enforcement ─────────────────────────────────

    def test_unknown_gate_raises(self):
        """Unknown gate ID should raise ValueError."""
        candidate = self._swing_candidate()
        with pytest.raises(ValueError, match="Unknown gate_id"):
            evaluate_gate("G99", candidate)

    def test_canonical_name_lookup(self):
        """Canonical gate name should resolve to correct gate ID."""
        candidate = self._swing_candidate()
        result = evaluate_gate("DOC_READY", candidate)
        assert result.gate_id == "G0"
        assert result.status == GateStatus.PASS

    def test_non_canonical_name_rejected(self):
        """Non-canonical gate names should raise ValueError."""
        candidate = self._swing_candidate()
        with pytest.raises(ValueError, match="Non-canonical gate name"):
            evaluate_gate("Structural Validity", candidate)

    def test_canonical_set_matches_spec(self):
        """CANONICAL_GATE_NAMES must match TR-07 plan and handoff_to_v7.md."""
        expected = {
            "G0": "DOC_READY",
            "G1": "RESEARCH_BACKTEST",
            "G2": "WALK_FORWARD_OOS",
            "G3": "COST_STRESS",
            "G4": "REGIME_BREAKDOWN",
            "G5": "SYMBOL_STABILITY",
            "G6": "CALIBRATION_RELIABILITY",
            "G7": "SHADOW",
            "G8": "PAPER",
            "G9": "TINY_LIVE",
            "G10": "LIVE",
        }
        assert CANONICAL_GATE_NAMES == expected


class TestEvaluateCandidate:
    """Test full candidate evaluation through all canonical gates."""

    def _swing_candidate(self):
        return {
            "request_id": "req_001",
            "mode": "SWING",
            "symbol": "BTCUSDT",
            "model_scope": "swing_v1",
        }

    def test_all_gates_evaluated(self):
        """All 11 canonical gates (G0-G10) should be evaluated."""
        candidate = self._swing_candidate()
        ctx = {
            "expectancy_r": 0.50,
            "expected_r_net": 0.85,
            "ece": 0.05,
            "model_signature": "swing_v1@abc123",
            "g1_research_backtest_pass": True,
        }
        results = evaluate_candidate(candidate, ctx)
        assert len(results) == 11
        for gate_id in [f"G{i}" for i in range(11)]:
            assert gate_id in results, f"Missing gate {gate_id}"

    def test_strong_candidate_passes_all_applicable(self):
        """Strong candidate should pass all applicable gates (G0-G6)."""
        candidate = self._swing_candidate()
        ctx = {
            "expectancy_r": 1.2,
            "expected_r_net": 0.90,
            "ece": 0.03,
            "model_signature": "swing_v1@abc123",
            "g1_research_backtest_pass": True,
        }
        results = evaluate_candidate(candidate, ctx)
        summary = get_promotion_summary(results)
        # G7-G10 are NOT_APPLICABLE for baseline, G0-G6 should PASS
        assert summary["passed"] is True
        assert "PROMOTE" in summary["recommendation"]
        assert "G7" in summary["na_gates"]
        assert "G8" in summary["na_gates"]
        assert "G9" in summary["na_gates"]
        assert "G10" in summary["na_gates"]

    def test_weak_candidate_fails_g2_walk_forward(self):
        """Weak expectancy R candidate should fail G2 WALK_FORWARD_OOS."""
        candidate = self._swing_candidate()
        ctx = {
            "expectancy_r": 0.10,  # Below SWING min 0.35
            "expected_r_net": 0.05,
            "ece": 0.08,
            "model_signature": "swing_v1@abc123",
            "g1_research_backtest_pass": True,
        }
        results = evaluate_candidate(candidate, ctx)
        summary = get_promotion_summary(results)
        assert summary["passed"] is False
        assert "G2" in summary["failed_gates"]
        assert "HOLD" in summary["recommendation"]

    def test_stop_on_fail(self):
        """stop_on_fail should stop after first failure."""
        candidate = {
            "request_id": "req_001",
            "mode": "INVALID_MODE",
            "symbol": "BTCUSDT",
            "model_scope": "swing_v1",
        }
        results = evaluate_candidate(candidate, context={}, stop_on_fail=True)
        assert len(results) < 11
        assert results["G0"].status == GateStatus.FAIL


class TestGetPromotionSummary:
    """Test promotion summary generation."""

    def test_all_pass(self):
        """All PASS should recommend PROMOTE."""
        results = {
            "G0": GateResult("G0", "DOC_READY", GateStatus.PASS, 1.0, 1.0, "ok"),
            "G1": GateResult("G1", "RESEARCH_BACKTEST", GateStatus.PASS, 1.0, 0.9, "ok"),
            "G2": GateResult("G2", "WALK_FORWARD_OOS", GateStatus.PASS, 1.0, 0.35, "ok"),
        }
        summary = get_promotion_summary(results)
        assert summary["passed"] is True
        assert summary["recommendation"] == "PROMOTE"
        assert summary["overall_score"] == 1.0

    def test_one_fail(self):
        """Any FAIL should recommend HOLD."""
        results = {
            "G0": GateResult("G0", "DOC_READY", GateStatus.PASS, 1.0, 1.0, "ok"),
            "G2": GateResult("G2", "WALK_FORWARD_OOS", GateStatus.FAIL, 0.0, 0.35, "bad"),
        }
        summary = get_promotion_summary(results)
        assert summary["passed"] is False
        assert "HOLD" in summary["recommendation"]
        assert "G2" in summary["failed_gates"]

    def test_not_applicable_excluded(self):
        """NOT_APPLICABLE gates should not affect pass/fail."""
        results = {
            "G0": GateResult("G0", "DOC_READY", GateStatus.PASS, 1.0, 1.0, "ok"),
            "G10": GateResult("G10", "LIVE", GateStatus.NOT_APPLICABLE, 0.0, 1.0, "na"),
        }
        summary = get_promotion_summary(results)
        assert summary["passed"] is True
        assert "G10" in summary["na_gates"]


class TestGateResult:
    """Test GateResult dataclass."""

    def test_immutable(self):
        """GateResult should be immutable."""
        result = GateResult("G0", "DOC_READY", GateStatus.PASS, 1.0, 1.0, "ok")
        with pytest.raises(Exception):
            result.status = GateStatus.FAIL  # type: ignore

    def test_repr(self):
        """GateResult should have readable repr."""
        result = GateResult("G0", "DOC_READY", GateStatus.PASS, 1.0, 1.0, "ok")
        assert "G0" in repr(result)
        assert "PASS" in repr(result)


class TestGateDefinitions:
    """Verify GATE_DEFINITIONS integrity."""

    def test_eleven_gates(self):
        """Should have exactly 11 gates (G0-G10)."""
        assert len(GATE_DEFINITIONS) == 11

    def test_sequential(self):
        """Gates should be in canonical G0-G10 order."""
        expected = [f"G{i}" for i in range(11)]
        actual = [gid for gid, _, _ in GATE_DEFINITIONS]
        assert actual == expected

    def test_unique_ids(self):
        """Each gate should have a unique ID."""
        ids = [gid for gid, _, _ in GATE_DEFINITIONS]
        assert len(ids) == len(set(ids))

    def test_canonical_names(self):
        """Each gate should use its canonical name from CANONICAL_GATE_NAMES."""
        for gid, name, fn in GATE_DEFINITIONS:
            assert name == CANONICAL_GATE_NAMES[gid], (
                f"Gate {gid} name '{name}' != canonical '{CANONICAL_GATE_NAMES[gid]}'"
            )
            assert callable(fn), f"Gate {gid} fn is not callable"
