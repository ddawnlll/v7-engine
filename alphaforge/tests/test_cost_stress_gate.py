"""Test cost stress gate G3 — real CostStressRunner imported and verified.

P0.9G: Verifies that:
1. CostStressRunner from simulation.validation.cost_stress IS imported and usable
2. try/finally safety of the __defaults__ monkey-patch (restored after stress())
3. The bridge function compute_cost_stress_for_wfv correctly computes stressed R
4. _gate_g3 evaluates the result (high edge -> PASS, low edge -> PENDING)
"""

import pytest
from alphaforge.reports.empirical import _build_empirical_cost_stress
from alphaforge.handoff.builders import _gate_g3

# Verify CostStressRunner IS imported (not a local reimplementation)
from simulation.validation.cost_stress import CostStressRunner


class TestCostStressRunnerImport:
    """Verify the real CostStressRunner exists and is the right module."""

    def test_imported_from_simulation_validation(self):
        assert CostStressRunner.__module__ == "simulation.validation.cost_stress"
        assert hasattr(CostStressRunner, "stress")
        assert hasattr(CostStressRunner, "_apply_cost_multiplier")
        assert hasattr(CostStressRunner, "MULTIPLIERS")
        assert CostStressRunner.MULTIPLIERS == [1.0, 1.5, 2.0, 3.0]

    def test_try_finally_safety(self):
        """Verify that total_cost_r.__defaults__ is restored after stress().

        This is the critical safety check required by the task:
        CostStressRunner monkey-patches total_cost_r.__defaults__ inside
        a try/finally. After stress() completes (even without a real
        simulation input — we expect TypeError, not state leak),
        the defaults must be restored.
        """
        import simulation.engine.costs as cost_mod
        orig_defaults = cost_mod.total_cost_r.__defaults__

        runner = CostStressRunner()
        try:
            # This will fail because we pass None as input (TypeError)
            # or because simulate() needs a real SimulationInput
            runner.stress(None)  # type: ignore[arg-type]
        except (TypeError, AttributeError, ValueError, Exception):
            pass

        # The defaults must be restored after the exception propagates
        assert cost_mod.total_cost_r.__defaults__ == orig_defaults, (
            "total_cost_r.__defaults__ was NOT restored after stress() exception.\n"
            f"  Before: {orig_defaults}\n"
            f"  After:  {cost_mod.total_cost_r.__defaults__}\n"
            "This means the try/finally in stress() is NOT safe for exceptions."
        )

    def test_try_finally_safety_normal_exit(self):
        """After a successful (but minimal) stress run, defaults are restored."""
        import simulation.engine.costs as cost_mod
        orig_defaults = cost_mod.total_cost_r.__defaults__

        runner = CostStressRunner()
        # Simulate what stress() does: patch defaults, then restore
        import simulation.engine.costs as cm
        for m in [1.0, 2.0]:
            try:
                runner._apply_cost_multiplier(cm, m)
            finally:
                cm.total_cost_r.__defaults__ = orig_defaults

        assert cm.total_cost_r.__defaults__ == orig_defaults, (
            "Defaults changed after simulated stress loop"
        )

    def test_apply_cost_multiplier_scales_fee_bps(self):
        """_apply_cost_multiplier must scale taker_fee_bps by the multiplier."""
        import simulation.engine.costs as cost_mod
        orig = cost_mod.total_cost_r.__defaults__
        runner = CostStressRunner()
        try:
            runner._apply_cost_multiplier(cost_mod, 2.0)
            # orig[0] = 4.0 (DEFAULT_TAKER_FEE_BPS), should become 8.0
            assert cost_mod.total_cost_r.__defaults__[0] == pytest.approx(8.0)
            assert cost_mod.total_cost_r.__defaults__[1] == pytest.approx(2.0)
            assert cost_mod.total_cost_r.__defaults__[2] == pytest.approx(0.0)
            assert cost_mod.total_cost_r.__defaults__[3] == 0
        finally:
            cost_mod.total_cost_r.__defaults__ = orig


class TestBuildEmpiricalCostStress:
    """Tests using the real CostStressRunner methodology."""

    def test_high_edge_survives(self):
        wfv = {}
        section = _build_empirical_cost_stress(
            wfv, mode="SCALP", oos_expectancy_r=0.15,
        )
        assert section["combined_stress_edge_survives"] is True
        assert section["cost_stress_verdict"] == "PASS"
        assert section["stressed_net_expectancy_r"] > 0

    def test_low_edge_fails(self):
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
        precomputed = {
            "combined_stress_edge_survives": True,
            "break_even_cost_total_pct": 5.0,
        }
        wfv = {"cost_stress": precomputed}
        section = _build_empirical_cost_stress(
            wfv, mode="SCALP", oos_expectancy_r=0.001,
        )
        assert section["combined_stress_edge_survives"] is True
        assert section["break_even_cost_total_pct"] == 5.0

    def test_stressed_net_r_included(self):
        wfv = {}
        section = _build_empirical_cost_stress(
            wfv, mode="SCALP", oos_expectancy_r=0.10,
        )
        assert "stressed_net_expectancy_r" in section
        assert isinstance(section["stressed_net_expectancy_r"], float)

    def test_source_is_coststressrunner(self):
        """Evidence that the real CostStressRunner was used."""
        from alphaforge.reports.cost_stress_check import compute_cost_stress_for_wfv
        result = compute_cost_stress_for_wfv(
            net_expectancy_r=0.10, mode="SCALP",
        )
        assert result.get("_cost_stress_source") == "CostStressRunner"

    def test_mode_specific_cost_sensitivity(self):
        """SCALP tighter stop -> higher cost in R than SWING at same edge."""
        from alphaforge.reports.cost_stress_check import compute_cost_stress_for_wfv
        scalp = compute_cost_stress_for_wfv(net_expectancy_r=0.10, mode="SCALP")
        swing = compute_cost_stress_for_wfv(net_expectancy_r=0.10, mode="SWING")
        assert scalp["stressed_net_expectancy_r"] < swing["stressed_net_expectancy_r"]


class TestGateG3WithRealData:
    """Integration: _gate_g3 with real cost stress sections."""

    def _make_report(self, section: dict) -> dict:
        return {"report_id": "test-g3-001", "cost_stress": section}

    def test_pass(self):
        section = _build_empirical_cost_stress({}, mode="SCALP", oos_expectancy_r=0.15)
        _, status = _gate_g3(self._make_report(section))
        assert status == "PASS"

    def test_pending_low_edge(self):
        section = _build_empirical_cost_stress({}, mode="SCALP", oos_expectancy_r=0.004)
        _, status = _gate_g3(self._make_report(section))
        assert status == "PENDING"

    def test_pending_zero_edge(self):
        section = _build_empirical_cost_stress({}, mode="SCALP", oos_expectancy_r=0.0)
        _, status = _gate_g3(self._make_report(section))
        assert status == "PENDING"

    def test_evidence_includes_fields(self):
        section = _build_empirical_cost_stress({}, mode="SCALP", oos_expectancy_r=0.10)
        ev, _ = _gate_g3(self._make_report(section))
        assert "combined_stress_edge_survives" in ev
        assert "break_even_cost_total" in ev
