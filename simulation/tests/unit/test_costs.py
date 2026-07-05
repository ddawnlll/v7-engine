"""
Tests for simulation cost model — fee, slippage, total cost, and lineage.

Verifies the cost functions and their impact on net R through the engine.
"""

from __future__ import annotations

import pytest

from simulation.contracts.models import (
    Candle,
    FuturePath,
    SimulationInput,
    SimulationProfile,
    TradingMode,
)
from simulation.engine.costs import (
    compute_entry_risk,
    fee_cost_r,
    slippage_cost_r,
    total_cost_r,
)
from simulation.engine.engine import simulate


# ── Shared fixture ──────────────────────────────────────────────────────


@pytest.fixture
def swing_profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="1.0.0",
        mode=TradingMode.SWING,
        primary_interval="4h",
        max_holding_bars=24,
        stop_multiplier=2.0,
        target_multiplier=2.5,
        ambiguity_margin_r=0.1,
        min_action_edge_r=0.05,
        no_trade_default=False,
    )


# ── Cost formula tests (pure functions) ────────────────────────────────


class TestCostFormulas:
    """Unit tests for fee_cost_r, slippage_cost_r."""

    def test_fee_formula(self):
        """Fee cost formula: round-trip entry+exit taker fee / entry_risk.

        notional=100, taker=4bps => 2 * 100 * 0.0004 = 0.08 total fee.
        entry_risk=20 => fee_r = 0.08/20 = 0.004.
        """
        risk = compute_entry_risk(atr=10, stop_multiplier=2)
        assert risk == 20.0
        fee = fee_cost_r(notional=100, entry_risk=risk, taker_fee_bps=4.0)
        assert fee == pytest.approx(0.004)

    def test_slippage_formula(self):
        """Slippage formula: base=1bp, vol-adjusted with ATR/price ratio.

        notional=100, entry_price=100, atr=10, base=1bp.
        vol_ratio=0.1, adj_rate=0.0001*1.1=0.00011.
        entry_slippage=100*0.00011=0.011, exit_slippage=0.011, total=0.022.
        entry_risk=20 => slippage_r=0.022/20=0.0011.
        """
        risk = compute_entry_risk(atr=10, stop_multiplier=2)
        slip = slippage_cost_r(
            notional=100, entry_price=100, entry_risk=risk,
            slippage_bps=1.0, atr=10, volatility_adjust=True,
        )
        assert slip == pytest.approx(0.0011)

    def test_vol_adjusted_slippage(self):
        """Volatility-adjusted slippage > base slippage when ATR > 0."""
        risk = compute_entry_risk(atr=10, stop_multiplier=2)
        slip_raw = slippage_cost_r(
            notional=100, entry_price=100, entry_risk=risk,
            slippage_bps=1.0, atr=10, volatility_adjust=False,
        )
        slip_adj = slippage_cost_r(
            notional=100, entry_price=100, entry_risk=risk,
            slippage_bps=1.0, atr=10, volatility_adjust=True,
        )
        # Adjusted should be larger than raw when ATR > 0
        assert slip_adj > slip_raw
        # Raw: base_rate=0.0001, total_slippage=0.02, /20 = 0.001
        assert slip_raw == pytest.approx(0.001)


# ── Cost impact through engine ─────────────────────────────────────────


class TestCostImpact:
    """Cost impact on net R through simulate()."""

    @staticmethod
    def _candle(open_: float, high: float, low: float, close: float) -> Candle:
        return Candle(open=open_, high=high, low=low, close=close)

    def _make_input(
        self, profile: SimulationProfile, candles: list[Candle],
    ) -> SimulationInput:
        return SimulationInput(
            symbol="BTCUSDT",
            decision_timestamp="2026-07-01T00:00:00Z",
            mode=TradingMode.SWING,
            primary_interval="4h",
            entry_price=100,
            atr=10,
            future_path=FuturePath(candles=candles),
            profile=profile,
        )

    def test_fee_reduces_net_r(self, swing_profile):
        """Fee cost reduces net R: realized_r_net < realized_r_gross and fee > 0."""
        candles = [
            self._candle(105, 135, 103, 130),  # high=135 > target=125
        ]
        inp = self._make_input(swing_profile, candles)
        result = simulate(inp)

        # LONG target hit => positive gross
        assert result.long_outcome.exit_reason == "TARGET_HIT"
        assert result.long_outcome.realized_r_gross > 0
        assert result.long_outcome.fee_cost_r > 0
        assert result.long_outcome.realized_r_net < result.long_outcome.realized_r_gross

    def test_slippage_reduces_net_r(self, swing_profile):
        """Slippage cost reduces net R: slippage_cost_r > 0 and net < gross."""
        candles = [
            self._candle(105, 135, 103, 130),
        ]
        inp = self._make_input(swing_profile, candles)
        result = simulate(inp)

        assert result.long_outcome.slippage_cost_r > 0
        assert result.long_outcome.realized_r_net < result.long_outcome.realized_r_gross

    def test_gross_minus_total_cost_equals_net(self, swing_profile):
        """Gross R - total_cost_r = net R (within float epsilon)."""
        candles = [
            self._candle(105, 135, 103, 130),
        ]
        inp = self._make_input(swing_profile, candles)
        result = simulate(inp)

        gross = result.long_outcome.realized_r_gross
        net = result.long_outcome.realized_r_net
        total_cost = result.long_outcome.total_cost_r

        assert net == pytest.approx(gross - total_cost, abs=1e-10)

    def test_cost_version_in_lineage(self, swing_profile):
        """Cost model version is included in output lineage."""
        candles = [
            self._candle(101, 102, 99, 101),
        ]
        inp = self._make_input(swing_profile, candles)
        result = simulate(inp)

        assert result.lineage.cost_model_version == "cost-1.0.0"
        assert result.lineage.fee_model_version == "fee-1.0.0"
        assert result.lineage.slippage_model_version == "slippage-1.0.0"
