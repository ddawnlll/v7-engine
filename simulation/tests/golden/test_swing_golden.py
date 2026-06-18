"""
Golden tests for SWING mode simulation.

Deterministic: known input candles → expected exit reason and
directionally correct realized R.

Evidence ref: simulation/docs/contracts.md, simulation/docs/profiles.md
"""

import pytest
from simulation.contracts.models import (
    Candle,
    FuturePath,
    SimulationInput,
    SimulationProfile,
    TradingMode,
)
from simulation.engine.engine import simulate


def _swing_profile() -> SimulationProfile:
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


def _make_input(
    entry_price: float,
    atr: float,
    candles: list[Candle],
) -> SimulationInput:
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


# ── Golden Test 1: TARGET_HIT (bullish path) ─────────────────────────

def test_swing_long_target_hit():
    """LONG hits target before stop in a clear uptrend.

    Entry: 50000, ATR: 1000
    Stop:  50000 - 2000 = 48000
    Target: 50000 + 2500 = 52500

    Path: steady rise → target at bar 4.
    """
    candles = [
        Candle(open=50200, high=50500, low=50100, close=50400),
        Candle(open=50400, high=51000, low=50300, close=50800),
        Candle(open=50800, high=51500, low=50700, close=51300),
        Candle(open=51300, high=52000, low=51200, close=51800),
        Candle(open=51800, high=52600, low=51700, close=52500),  # high > 52500
    ]
    entry_price = 50000.0
    atr = 1000.0

    inp = _make_input(entry_price, atr, candles)
    result = simulate(inp)

    # LONG should hit target
    assert result.long_outcome.exit_reason == "TARGET_HIT"
    assert result.long_outcome.realized_r_gross > 0.5   # ~(52500-50000)/2000 = 1.25R
    assert result.long_outcome.realized_r_net > 0       # net positive after costs
    assert result.long_outcome.realized_r_net < result.long_outcome.realized_r_gross  # costs reduce

    # SHORT should hit stop (price went up)
    assert result.short_outcome.exit_reason == "STOP_HIT"
    assert result.short_outcome.realized_r_gross < 0

    # Best action should be LONG
    assert result.best_action in ("LONG_NOW",)
    assert not result.is_ambiguous


# ── Golden Test 2: STOP_HIT (bearish path) ────────────────────────────

def test_swing_long_stop_hit():
    """LONG hits stop in a clear downtrend.

    Entry: 50000, ATR: 1000
    Stop:  48000, Target: 52500

    Path: steady fall → stop at bar 2.
    """
    candles = [
        Candle(open=49800, high=49900, low=49300, close=49400),
        Candle(open=49400, high=49500, low=48500, close=48600),
        Candle(open=48600, high=48800, low=47300, close=47400),  # low < 47500 = SHORT target
    ]
    entry_price = 50000.0
    atr = 1000.0

    inp = _make_input(entry_price, atr, candles)
    result = simulate(inp)

    # LONG should hit stop (LONG stop = 48000, low=47300 hits it)
    assert result.long_outcome.exit_reason == "STOP_HIT"
    assert result.long_outcome.realized_r_gross < 0   # lost money

    # SHORT should hit target (SHORT target = 47500, low=47300 hits it)
    assert result.short_outcome.exit_reason == "TARGET_HIT"
    assert result.short_outcome.realized_r_gross > 0

    assert result.best_action in ("SHORT_NOW",)


# ── Golden Test 3: TIME_EXIT / no resolution ──────────────────────────

def test_swing_time_exit_no_stop_or_target():
    """Neither stop nor target hit within holding period → TIME_EXIT.

    Entry: 50000, ATR: 500
    Stop:  49000, Target: 51250
    Path: flat/slight rise, no extreme moves.
    """
    candles = [
        Candle(open=50100, high=50300, low=50000, close=50200),
        Candle(open=50200, high=50400, low=50100, close=50300),
        Candle(open=50300, high=50500, low=50200, close=50400),
        Candle(open=50400, high=50600, low=50300, close=50500),
        Candle(open=50500, high=50700, low=50400, close=50600),
    ]
    entry_price = 50000.0
    atr = 500.0  # Smaller ATR → tighter stops? No, wider range needed

    # Use a profile with tight range that won't trigger
    profile = SimulationProfile(
        profile_version="swing_profile-1.0.0",
        mode=TradingMode.SWING,
        primary_interval="4h",
        max_holding_bars=3,  # short hold to trigger time-exit
        stop_multiplier=3.0,  # wide stop
        target_multiplier=4.0,  # far target
        ambiguity_margin_r=0.20,
        min_action_edge_r=0.35,
        no_trade_default=False,
        stop_method="atr_wide",
        target_method="atr_wide",
    )

    inp = SimulationInput(
        symbol="BTCUSDT",
        decision_timestamp="2026-06-01T12:00:00Z",
        mode=TradingMode.SWING,
        primary_interval="4h",
        entry_price=entry_price,
        atr=atr,
        future_path=FuturePath(candles=candles),
        profile=profile,
    )
    result = simulate(inp)

    # Should time-exit (only 3 bars allowed, no extreme moves)
    assert result.long_outcome.exit_reason == "TIME_EXIT"
    assert result.short_outcome.exit_reason == "TIME_EXIT"
    # Slight upward drift → LONG slightly positive, SHORT slightly negative
    assert result.long_outcome.realized_r_gross >= 0
    assert result.short_outcome.realized_r_gross <= 0
