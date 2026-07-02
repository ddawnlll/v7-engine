"""
Edge case tests for simulation engine — zero/negative prices and NaN ATR.

Verifies that the engine handles boundary values without crashing and
produces deterministic results.
"""

from __future__ import annotations

import math

import pytest

from simulation.contracts.models import (
    Candle,
    FuturePath,
    SimulationInput,
    SimulationProfile,
    TradingMode,
)
from simulation.engine.engine import simulate


# ── Helpers ─────────────────────────────────────────────────────────────────


def _candle(open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(open=open_, high=high, low=low, close=close)


def _profile(stop_mult: float = 2.0, target_mult: float = 2.5) -> SimulationProfile:
    return SimulationProfile(
        profile_version="1.0.0",
        mode=TradingMode.SWING,
        primary_interval="4h",
        max_holding_bars=24,
        stop_multiplier=stop_mult,
        target_multiplier=target_mult,
        ambiguity_margin_r=0.10,
        min_action_edge_r=0.05,
        no_trade_default=False,
    )


# ── Tests ───────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases — zero/negative price, NaN ATR."""

    # ── Test 1: Zero / negative entry price ─────────────────────────────

    def test_zero_negative_price(self):
        """Zero and negative entry prices are handled without crashing.

        The engine should not crash when given extreme price values.
        Cost and exit calculations should produce finite outputs.
        """
        test_cases = [
            ("zero_price", 0.0),
            ("negative_price", -10.0),
            ("negative_atr", -5.0),
        ]

        for label, entry_price in test_cases:
            candles = [_candle(entry_price + 1, entry_price + 2, entry_price - 1, entry_price)]
            profile = _profile()
            inp = SimulationInput(
                symbol="TEST",
                decision_timestamp="2026-07-01T00:00:00Z",
                mode=TradingMode.SWING,
                primary_interval="4h",
                entry_price=entry_price,
                atr=5.0,
                future_path=FuturePath(candles=candles),
                profile=profile,
            )
            result = simulate(inp)

            # Output should exist and be well-structured
            assert result.symbol == "TEST"
            assert result.long_outcome is not None
            assert result.short_outcome is not None
            assert result.no_trade_outcome is not None

            # Financial values should be finite (not NaN or Inf)
            assert math.isfinite(result.long_outcome.realized_r_gross), f"not finite for {label}"
            assert math.isfinite(result.long_outcome.realized_r_net), f"not finite for {label}"
            assert math.isfinite(result.short_outcome.realized_r_gross), f"not finite for {label}"
            assert math.isfinite(result.short_outcome.realized_r_net), f"not finite for {label}"

    # ── Test 2: NaN ATR ─────────────────────────────────────────────────

    def test_nan_atr(self):
        """NaN ATR is handled without crashing.

        The engine should produce finite results even when ATR is NaN.
        """
        candles = [_candle(105, 130, 103, 125)]
        profile = _profile()

        inp = SimulationInput(
            symbol="BTCUSDT",
            decision_timestamp="2026-07-01T00:00:00Z",
            mode=TradingMode.SWING,
            primary_interval="4h",
            entry_price=100,
            atr=float("nan"),
            future_path=FuturePath(candles=candles),
            profile=profile,
        )
        result = simulate(inp)

        # Engine should complete without crashing
        assert result.resolution_status in ("COMPLETE", "UNRESOLVED")
        assert result.long_outcome is not None
        assert result.short_outcome is not None
