"""Integration test: funding cost flows end-to-end through simulation engine.

Verifies that a non-zero funding_rate in SimulationProfile produces
non-zero funding_cost_r in ActionOutcome, confirming that the #315 fix
(removed adapter hardcodes) unblocks #304.

See: #304 — HIGH: Funding cost not flowing into backtests
"""

import numpy as np
import pytest

from simulation.contracts.models import (
    Candle,
    SimulationInput,
    SimulationProfile,
    FuturePath,
    TradingMode,
)
from simulation.engine.costs import total_cost_r


class TestFundingEndToEnd:
    """Funding flows through cost model when funding_rate is non-zero."""

    def test_nonzero_funding_produces_nonzero_cost_r(self):
        """A non-zero funding_rate must produce non-zero funding_cost_r."""
        atr = 2.0
        stop_mult = 2.0
        risk = atr * stop_mult  # 4.0
        notional = 100_000.0
        entry_price = 100.0

        fcr, scr, fund_r, tcr = total_cost_r(
            notional=notional,
            entry_price=entry_price,
            atr=atr,
            stop_multiplier=stop_mult,
            funding_rate=0.0001,  # 1 bp per bar — typical BTC perp rate
            holding_bars=8,       # held across one full funding interval (8h on 1h bars)
        )

        assert fund_r > 0, f"Expected non-zero funding cost, got {fund_r}"
        assert tcr > fund_r, "Total cost should exceed funding alone (fees + slippage + funding)"

    def test_zero_funding_rate_produces_zero_funding_cost(self):
        """Zero funding_rate must produce zero funding_cost_r (backward compat)."""
        fcr, scr, fund_r, tcr = total_cost_r(
            notional=100_000.0,
            entry_price=100.0,
            atr=2.0,
            stop_multiplier=2.0,
            funding_rate=0.0,
            holding_bars=8,
        )

        assert fund_r == 0.0, f"Expected zero funding cost, got {fund_r}"

    def test_funding_flows_into_simulation_output(self):
        """Non-zero funding_rate in SimulationProfile must produce non-zero
        funding_cost_r in the simulation engine's ActionOutcome."""
        from simulation.engine.engine import simulate

        profile = SimulationProfile(
            profile_version="test-funding-1.0.0",
            mode=TradingMode.SCALP,
            primary_interval="1h",
            max_holding_bars=12,
            stop_multiplier=2.0,
            target_multiplier=2.0,
            ambiguity_margin_r=0.10,
            min_action_edge_r=0.15,
            no_trade_default=False,
            funding_rate=0.0001,  # non-zero funding
        )

        n_bars = 20
        rng = np.random.RandomState(42)
        prices = 100.0 * np.exp(np.cumsum(rng.randn(n_bars) * 0.02))
        candles = [
            Candle(
                open=float(prices[i]),
                high=float(prices[i] * 1.01),
                low=float(prices[i] * 0.99),
                close=float(prices[i]),
            )
            for i in range(n_bars)
        ]

        sim_input = SimulationInput(
            symbol="BTCUSDT",
            decision_timestamp="2026-07-10T12:00:00Z",
            entry_price=100.0,
            atr=2.0,
            future_path=FuturePath(candles=candles),
            profile=profile,
            mode=TradingMode.SCALP,
            primary_interval="1h",
            simulation_family_version="test",
            cost_model_version="test",
        )

        output = simulate(sim_input)

        assert output is not None
        # Check both long and short outcomes for non-zero funding
        for side_name, outcome in [("long", output.long_outcome), ("short", output.short_outcome)]:
            if outcome is not None:
                assert outcome.funding_cost_r != 0.0, (
                    f"Expected non-zero funding_cost_r for {side_name} with "
                    f"funding_rate=0.0001, got {outcome.funding_cost_r}"
                )
                assert outcome.total_cost_r > outcome.funding_cost_r, (
                    f"{side_name}: total cost must include funding plus fees/slippage"
                )
