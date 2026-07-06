"""Test cost stress gate G3 wiring — real CostStressRunner via cost_stress_check.

P0.9G: Verifies that _build_empirical_cost_stress correctly computes
cost stress from WFV results using the real compute_cost_stress()
function, and that _gate_g3 evaluates the result correctly.

Tests are against real computation (no mocks) but with synthetic
expectancy R values.
"""

import pytest
from alphaforge.reports.empirical import _build_empirical_cost_stress
from alphaforge.handoff.builders import _gate_g3


class TestBuildEmpiricalCostStress:
    """Tests for _build_empirical_cost_stress auto-computation."""

    def test_high_edge_survives(self):
        """High enough expectancy R should survive x2.0 fee stress for SCALP."""
        wfv = {}  # empty cost_stress → triggers auto-compute
        section = _build_empirical_cost_stress(
            wfv, mode="SCALP", oos_expectancy_r=0.15,
        )
        assert section["combined_stress_edge_survives"] is True
        assert section["cost_stress_verdict"] == "PASS"
        assert section["stressed_net_expectancy_r"] > 0

    def test_low_edge_fails_combined_stress(self):
        """Low expectancy R (like 0.004 from real SCALP WFV) fails cost stress."""
        wfv = {}
        section = _build_empirical_cost_stress(
            wfv, mode="SCALP", oos_expectancy_r=0.004,
        )
        assert section["combined_stress_edge_survives"] is False
        assert section["cost_stress_verdict"] == "FAIL_EDGE_DESTROYED_BY_COSTS"

    def test_zero_edge_fails(self):
        wfv = {}
        section = _build_empirical_cost_stress(
            wfv, mode="SCALP", oos_expectancy_r=0.0,
        )
        assert section["combined_stress_edge_survives"] is False

    def test_negative_edge_fails(self):
        wfv = {}
        section = _build_empirical_cost_stress(
            wfv, mode="SCALP", oos_expectancy_r=-0.05,
        )
        assert section["combined_stress_edge_survives"] is False

    def test_precomputed_data_not_overwritten(self):
        """If wfv_results already has cost_stress, it should be used as-is."""
        precomputed = {
            "combined_stress_edge_survives": True,
            "break_even_cost_total_pct": 5.0,
            "fee_stress_levels": [],
            "slippage_stress_levels": [],
        }
        wfv = {"cost_stress": precomputed}
        section = _build_empirical_cost_stress(
            wfv, mode="SCALP", oos_expectancy_r=0.001,
        )
        assert section["combined_stress_edge_survives"] is True
        assert section["break_even_cost_total_pct"] == 5.0

    def test_stressed_net_r_included(self):
        """Stressed net expectancy at 2.0x fee must be included in output."""
        wfv = {}
        section = _build_empirical_cost_stress(
            wfv, mode="SWING", oos_expectancy_r=0.20,
        )
        assert "stressed_net_expectancy_r" in section

    def test_mode_specific_entry_risk(self):
        """SCALP's tighter stop should result in higher cost sensitivity
        (lower stressed net R) than SWING for the same expectancy R."""
        wfv = {}
        scalp = _build_empirical_cost_stress(wfv, mode="SCALP", oos_expectancy_r=0.10)
        swing = _build_empirical_cost_stress(wfv, mode="SWING", oos_expectancy_r=0.10)
        # SCALP has tighter stops → same fee costs more R → lower stressed R
        assert scalp["stressed_net_expectancy_r"] <= swing["stressed_net_expectancy_r"]


class TestGateG3WithRealData:
    """Integration test: _gate_g3 with real cost stress section."""

    def _make_report(self, section: dict) -> dict:
        return {
            "report_id": "test-g3-001",
            "cost_stress": section,
        }

    def test_g3_pass_with_high_edge(self):
        section = _build_empirical_cost_stress({}, mode="SCALP", oos_expectancy_r=0.15)
        report = self._make_report(section)
        _, status = _gate_g3(report)
        assert status == "PASS"

    def test_g3_pending_with_low_edge(self):
        section = _build_empirical_cost_stress({}, mode="SCALP", oos_expectancy_r=0.004)
        report = self._make_report(section)
        _, status = _gate_g3(report)
        assert status == "PENDING"

    def test_g3_pending_with_zero_edge(self):
        section = _build_empirical_cost_stress({}, mode="SCALP", oos_expectancy_r=0.0)
        report = self._make_report(section)
        _, status = _gate_g3(report)
        assert status == "PENDING"

    def test_g3_evidence_includes_break_even(self):
        section = _build_empirical_cost_stress({}, mode="SCALP", oos_expectancy_r=0.10)
        report = self._make_report(section)
        evidence, _ = _gate_g3(report)
        assert "combined_stress_edge_survives" in evidence
        assert "break_even_cost_total" in evidence
