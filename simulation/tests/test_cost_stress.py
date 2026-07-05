"""
Tests for cost stress validation framework.

Verifies CostStressRunner stress() produces correct outputs across
all default multipliers and that is_cost_sensitive() correctly detects
cost-dependent edge.  Covers normal, edge, and degenerate cases.
"""

from __future__ import annotations

from simulation.contracts.models import (
    Candle,
    FuturePath,
    SimulationInput,
    SimulationProfile,
    TradingMode,
)
from simulation.engine.engine import simulate
from simulation.validation.cost_stress import (
    CostStressResult,
    CostStressRunner,
)


# ── Helpers ────────────────────────────────────────────────────────


def _swing_profile() -> SimulationProfile:
    """Canonical SWING profile matching the golden test setup."""
    return SimulationProfile(
        profile_version="swing_profile-1.0.0",
        mode=TradingMode.SWING,
        primary_interval="4h",
        max_holding_bars=30,
        stop_multiplier=2.0,
        target_multiplier=2.5,
        ambiguity_margin_r=0.20,
        min_action_edge_r=0.35,
        no_trade_default=False,
        context_intervals=["1d", "1h"],
        refinement_intervals=["1h"],
        stop_method="atr_wide",
        target_method="atr_wide",
        mae_penalty_weight=1.0,
        cost_penalty_weight=1.0,
        time_penalty_weight=0.3,
    )


def _bullish_candles() -> list[Candle]:
    """Five candles in a steady uptrend (golden test fixture).

    Entry: 50000, ATR: 1000
    Stop:  48000, Target: 52500
    """
    return [
        Candle(open=50200, high=50500, low=50100, close=50400),
        Candle(open=50400, high=51000, low=50300, close=50800),
        Candle(open=50800, high=51500, low=50700, close=51300),
        Candle(open=51300, high=52000, low=51200, close=51800),
        Candle(open=51800, high=52600, low=51700, close=52500),
    ]


def _make_swing_input(
    entry_price: float = 50000.0,
    atr: float = 1000.0,
    candles: list[Candle] | None = None,
) -> SimulationInput:
    """Build a SWING SimulationInput from the golden test fixture."""
    if candles is None:
        candles = _bullish_candles()
    return SimulationInput(
        symbol="BTCUSDT",
        decision_timestamp="2026-06-01T12:00:00Z",
        mode=TradingMode.SWING,
        primary_interval="4h",
        entry_price=entry_price,
        atr=atr,
        future_path=FuturePath(candles=candles),
        profile=_swing_profile(),
    )


# ── Tests ──────────────────────────────────────────────────────────


class TestCostStressRunner:
    """Cost stress validation — stress() method."""

    def test_baseline_profitable_at_1x(self):
        """1x multiplier produces profitable LONG (matches golden test)."""
        runner = CostStressRunner()
        inp = _make_swing_input()
        results = runner.stress(inp)

        r1x = results[0]
        assert r1x.multiplier == 1.0
        # Golden: bullish path → TARGET_HIT
        assert r1x.outputs.long_outcome.exit_reason == "TARGET_HIT"
        assert r1x.outputs.long_outcome.realized_r_gross > 0.5
        assert r1x.outputs.long_outcome.realized_r_net > 0

    def test_higher_multipliers_reduce_net_r(self):
        """Each higher cost multiplier reduces LONG realized_r_net.

        Because fee and slippage scale linearly, net R = gross R - (costs * m)
        should decrease strictly monotonically.
        """
        runner = CostStressRunner()
        inp = _make_swing_input()
        results = runner.stress(inp)

        net_rs = [r.outputs.long_outcome.realized_r_net for r in results]
        for i in range(len(net_rs) - 1):
            assert net_rs[i] > net_rs[i + 1], (
                f"Net R must decrease from"
                f" {results[i].multiplier}x ({net_rs[i]:.6f}) to"
                f" {results[i+1].multiplier}x ({net_rs[i+1]:.6f})"
            )

    def test_cost_increases_with_multiplier(self):
        """total_cost_r scales proportionally with multiplier."""
        runner = CostStressRunner()
        inp = _make_swing_input()
        results = runner.stress(inp)

        # Total costs should increase with each multiplier step
        total_costs = [r.outputs.long_outcome.total_cost_r for r in results]
        for i in range(len(total_costs) - 1):
            assert total_costs[i] < total_costs[i + 1], (
                f"Total cost must increase from"
                f" {results[i].multiplier}x ({total_costs[i]:.6f}) to"
                f" {results[i+1].multiplier}x ({total_costs[i+1]:.6f})"
            )

    def test_all_default_multipliers_present(self):
        """Stress output contains exactly the 4 default multipliers."""
        runner = CostStressRunner()
        inp = _make_swing_input()
        results = runner.stress(inp)

        assert len(results) == 4
        assert [r.multiplier for r in results] == [1.0, 1.5, 2.0, 3.0]


class TestCostSensitivity:
    """Cost sensitivity detection — is_cost_sensitive()."""

    def test_detects_cost_sensitive_strategy(self):
        """Realistic costs produce monotonic net R decrease → sensitive."""
        runner = CostStressRunner()
        inp = _make_swing_input()
        results = runner.stress(inp)
        assert runner.is_cost_sensitive(results) is True

    def test_not_sensitive_with_single_result(self):
        """Fewer than 2 results is never cost-sensitive."""
        runner = CostStressRunner()
        assert runner.is_cost_sensitive([]) is False

        inp = _make_swing_input()
        output = simulate(inp)
        single = [CostStressResult(multiplier=1.0, outputs=output)]
        assert runner.is_cost_sensitive(single) is False


class TestCostStressEdgeCases:
    """Edge and degenerate cases."""

    def test_zero_cost_multiplier_returns_gross_r(self):
        """At 0x cost multiplier, fee/slippage = 0 → net R == gross R."""
        import simulation.engine.costs as cost_mod

        runner = CostStressRunner()
        inp = _make_swing_input()

        # Snapshot and patch to zero costs
        orig_defaults = cost_mod.total_cost_r.__defaults__
        try:
            runner._apply_cost_multiplier(cost_mod, 0.0)
            output = simulate(inp)
        finally:
            cost_mod.total_cost_r.__defaults__ = orig_defaults

        lo = output.long_outcome
        assert lo.fee_cost_r == 0.0
        assert lo.slippage_cost_r == 0.0
        assert lo.total_cost_r == 0.0
        assert abs(lo.realized_r_net - lo.realized_r_gross) < 1e-9

    def test_not_sensitive_with_zero_costs(self):
        """Flat net R across multipliers → not cost-sensitive."""
        import simulation.engine.costs as cost_mod

        runner = CostStressRunner()
        inp = _make_swing_input()

        orig_defaults = cost_mod.total_cost_r.__defaults__
        results: list[CostStressResult] = []
        try:
            for m in [1.0, 2.0, 3.0]:
                runner._apply_cost_multiplier(cost_mod, 0.0)
                output = simulate(inp)
                results.append(CostStressResult(multiplier=m, outputs=output))
        finally:
            cost_mod.total_cost_r.__defaults__ = orig_defaults

        # All results have zero costs, so net R is identical → not sensitive
        assert runner.is_cost_sensitive(results) is False

    def test_same_candle_ambiguity_preserved_under_stress(self):
        """Stress preserves exit semantics (not just cost patching).

        Ensure the stress runner doesn't accidentally alter the exit path
        resolution by using a scenario where stop and target cross in the
        same candle.
        """
        candles = [
            Candle(open=105, high=125, low=85, close=110),
        ]
        inp = _make_swing_input(entry_price=100.0, atr=5.0, candles=candles)
        # Stop = 100 - 10 = 90, Target = 100 + 12.5 = 112.5

        runner = CostStressRunner()
        results = runner.stress(inp)

        for r in results:
            # Stop should be hit before target (conservative ordering)
            assert r.outputs.long_outcome.exit_reason in ("STOP_HIT", "STOP_HIT")
