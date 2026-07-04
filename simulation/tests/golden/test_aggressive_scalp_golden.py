"""Golden tests for AGGRESSIVE_SCALP mode simulation.

AGGRESSIVE_SCALP: primary=15m, max_holding=5, stop_mult=1.2, target_mult=1.2
"""

from simulation.contracts.models import Candle, FuturePath, SimulationInput, SimulationProfile, TradingMode
from simulation.engine.engine import simulate


def agg_profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="aggressive_scalp_profile-1.0.0",
        mode=TradingMode.AGGRESSIVE_SCALP,
        primary_interval="15m",
        max_holding_bars=5,
        stop_multiplier=1.2,
        target_multiplier=1.2,
        ambiguity_margin_r=0.05,
        min_action_edge_r=0.08,
        no_trade_default=True,
        context_intervals=["1h", "5m"],
        refinement_intervals=["5m"],
        stop_method="atr_wide",
        target_method="atr_wide",
        mae_penalty_weight=3.0,
        cost_penalty_weight=3.0,
        time_penalty_weight=2.5,
    )


def _input(entry_price: float, atr: float, candles: list[Candle]) -> SimulationInput:
    return SimulationInput(
        symbol="SOLUSDT",
        decision_timestamp="2026-06-01T14:00:00Z",
        mode=TradingMode.AGGRESSIVE_SCALP,
        primary_interval="15m",
        entry_price=entry_price,
        atr=atr,
        future_path=FuturePath(candles=candles),
        profile=agg_profile(),
    )


def test_aggressive_long_target_hit():
    """AGGRESSIVE_SCALP LONG hits target.
    Entry: 150, ATR: 4, Stop: 145.2, Target: 154.8
    """
    candles = [
        Candle(open=151, high=152, low=150, close=151),
        Candle(open=151, high=155, low=151, close=154),  # high > 154.8
    ]
    result = simulate(_input(150.0, 4.0, candles))

    assert result.long_outcome.exit_reason == "TARGET_HIT"
    assert result.long_outcome.realized_r_gross > 0.3
    assert result.long_outcome.realized_r_net > 0


def test_aggressive_long_stop_hit():
    """AGGRESSIVE_SCALP LONG hits stop."""
    candles = [
        Candle(open=149, high=150, low=146, close=147),
        Candle(open=147, high=148, low=144, close=145),  # low < 145.2
    ]
    result = simulate(_input(150.0, 4.0, candles))

    assert result.long_outcome.exit_reason == "STOP_HIT"
    assert result.long_outcome.realized_r_gross < 0
    assert result.short_outcome.exit_reason == "TARGET_HIT"
    assert result.short_outcome.realized_r_gross > 0


def test_aggressive_time_exit():
    """AGGRESSIVE_SCALP time exit with wide stops."""
    candles = [
        Candle(open=151, high=152, low=150, close=151),
        Candle(open=151, high=153, low=151, close=152),
    ]
    profile = agg_profile()
    profile.max_holding_bars = 2
    profile.stop_multiplier = 6.0
    profile.target_multiplier = 6.0

    inp = SimulationInput(
        symbol="SOLUSDT",
        decision_timestamp="2026-06-01T14:00:00Z",
        mode=TradingMode.AGGRESSIVE_SCALP,
        primary_interval="15m",
        entry_price=150.0,
        atr=4.0,
        future_path=FuturePath(candles=candles),
        profile=profile,
    )
    result = simulate(inp)

    assert result.long_outcome.exit_reason == "TIME_EXIT"
    assert result.short_outcome.exit_reason == "TIME_EXIT"


def test_aggressive_no_trade_default():
    """AGGRESSIVE_SCALP defaults to NO_TRADE when ambiguous."""
    profile = agg_profile()
    profile.ambiguity_margin_r = 0.50
    profile.min_action_edge_r = 0.50
    profile.no_trade_default = True

    candles = [
        Candle(open=150, high=151, low=149, close=150),
        Candle(open=150, high=151, low=149, close=150),
        Candle(open=150, high=151, low=149, close=150),
    ]
    inp = SimulationInput(
        symbol="SOLUSDT",
        decision_timestamp="2026-06-01T14:00:00Z",
        mode=TradingMode.AGGRESSIVE_SCALP,
        primary_interval="15m",
        entry_price=150.0,
        atr=4.0,
        future_path=FuturePath(candles=candles),
        profile=profile,
    )
    result = simulate(inp)

    assert result.best_action == "NO_TRADE"
    assert result.is_ambiguous
