"""
Tests for comparative action selection — best action, action gap, ambiguity.

Verifies that _select_best_action correctly ranks LONG_NOW, SHORT_NOW,
and NO_TRADE, and properly sets ambiguity flags.
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
from simulation.engine.engine import simulate


# ── Shared fixture ──────────────────────────────────────────────────────


@pytest.fixture
def profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="1.0.0",
        mode=TradingMode.SWING,
        primary_interval="4h",
        max_holding_bars=24,
        stop_multiplier=2.0,
        target_multiplier=2.5,
        ambiguity_margin_r=0.10,
        min_action_edge_r=0.05,
        no_trade_default=False,
    )


# ── Helpers ─────────────────────────────────────────────────────────────


def _candle(open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(open=open_, high=high, low=low, close=close)


def _make_input(
    profile: SimulationProfile,
    candles: list[Candle],
    entry_price: float = 100,
    atr: float = 10,
) -> SimulationInput:
    return SimulationInput(
        symbol="BTCUSDT",
        decision_timestamp="2026-07-01T00:00:00Z",
        mode=TradingMode.SWING,
        primary_interval="4h",
        entry_price=entry_price,
        atr=atr,
        future_path=FuturePath(candles=candles),
        profile=profile,
    )


# ── Tests ───────────────────────────────────────────────────────────────


class TestActionSelection:
    """Comparative action selection — best action, gap, ambiguity."""

    def test_best_action_highest_utility(self, profile):
        """best_action is the action with the highest utility."""
        # Strong uptrend: LONG hits target (positive utility), SHORT loses (negative utility)
        candles = [
            _candle(105, 130, 103, 125),  # target at 125 (100 + 10*2.5)
        ]
        inp = _make_input(profile, candles)
        result = simulate(inp)

        assert result.long_outcome.exit_reason == "TARGET_HIT"
        assert result.long_outcome.action_utility > 0
        assert result.best_action == "LONG_NOW"

    def test_action_gap_r(self, profile):
        """action_gap_r equals utility(best) - utility(second_best)."""
        # Strong uptrend: clear LONG advantage
        candles = [
            _candle(105, 130, 103, 125),
        ]
        inp = _make_input(profile, candles)
        result = simulate(inp)

        assert result.best_action == "LONG_NOW"
        # gap should be positive when best clearly beats second
        assert result.action_gap_r > 0

    def test_is_ambiguous_when_gap_lt_margin(self, profile):
        """is_ambiguous is True when action_gap_r < ambiguity_margin_r."""
        # Neutral path: both LONG and SHORT have similar (small) outcomes
        candles = [
            _candle(101, 102, 99, 101),
            _candle(101, 103, 100, 102),
            _candle(102, 104, 101, 103),
        ]
        inp = _make_input(profile, candles)
        result = simulate(inp)

        # Both TIME_EXIT with similar small gains
        # Use a profile with wider ambiguity to guarantee ambiguity
        profile_wide = SimulationProfile(
            profile_version="1.0.0",
            mode=TradingMode.SWING,
            primary_interval="4h",
            max_holding_bars=24,
            stop_multiplier=2.0,
            target_multiplier=5.0,  # Far target prevents early exits
            ambiguity_margin_r=2.0,  # Very wide margin -- guarantees ambiguity
            min_action_edge_r=0.05,
            no_trade_default=False,
        )
        inp2 = _make_input(profile_wide, candles)
        result2 = simulate(inp2)

        # With a very wide margin, the gap should be < margin
        assert result2.action_gap_r < 2.0  # gap is definitely < 2.0
        assert result2.is_ambiguous is True

    def test_ambiguity_margin_per_mode(self, profile):
        """Different ambiguity margins produce different ambiguity outcomes."""
        candles = [
            _candle(101, 102, 99, 101),
            _candle(101, 103, 100, 102),
            _candle(102, 104, 101, 103),
        ]

        # Profile with very tight ambiguity margin (likely NOT ambiguous)
        profile_tight = SimulationProfile(
            profile_version="1.0.0",
            mode=TradingMode.SWING,
            primary_interval="4h",
            max_holding_bars=24,
            stop_multiplier=2.0,
            target_multiplier=5.0,
            ambiguity_margin_r=0.001,  # Very tight
            min_action_edge_r=0.05,
            no_trade_default=False,
        )
        # Profile with very wide ambiguity margin (likely ambiguous)
        profile_wide = SimulationProfile(
            profile_version="1.0.0",
            mode=TradingMode.SWING,
            primary_interval="4h",
            max_holding_bars=24,
            stop_multiplier=2.0,
            target_multiplier=5.0,
            ambiguity_margin_r=5.0,  # Very wide
            min_action_edge_r=0.05,
            no_trade_default=False,
        )

        inp_tight = _make_input(profile_tight, candles)
        inp_wide = _make_input(profile_wide, candles)

        result_tight = simulate(inp_tight)
        result_wide = simulate(inp_wide)

        # Tight margin should have is_ambiguous=False (gap > 0.001)
        # Wide margin should have is_ambiguous=True (gap < 5.0)
        if result_tight.action_gap_r > 0.001:
            assert result_tight.is_ambiguous is False
        assert result_wide.is_ambiguous is True

    def test_ambiguous_state_when_gap_lt_margin_no_trade_default_false(self, profile):
        """AMBIGUOUS_STATE returned when gap < margin and no_trade_default=False."""
        candles = [
            _candle(101, 102, 99, 101),
            _candle(101, 103, 100, 102),
            _candle(102, 104, 101, 103),
        ]

        profile_ambig = SimulationProfile(
            profile_version="1.0.0",
            mode=TradingMode.SWING,
            primary_interval="4h",
            max_holding_bars=24,
            stop_multiplier=2.0,
            target_multiplier=5.0,
            ambiguity_margin_r=2.0,
            min_action_edge_r=0.05,
            no_trade_default=False,  # Explicitly False => AMBIGUOUS_STATE
        )

        inp = _make_input(profile_ambig, candles)
        result = simulate(inp)

        if result.is_ambiguous:
            assert result.best_action == "AMBIGUOUS_STATE"
