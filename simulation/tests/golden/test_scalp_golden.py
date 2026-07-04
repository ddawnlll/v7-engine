"""Golden tests for SCALP mode simulation.

SCALP: primary=1h, max_holding=12, stop_mult=1.5, target_mult=1.8
"""

from simulation.contracts.models import Candle, FuturePath, SimulationInput, SimulationProfile, TradingMode
from simulation.engine.engine import simulate


def scalp_profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="scalp_profile-1.0.0",
        mode=TradingMode.SCALP,
        primary_interval="1h",
        max_holding_bars=12,
        stop_multiplier=1.5,
        target_multiplier=1.8,
        ambiguity_margin_r=0.10,
        min_action_edge_r=0.15,
        no_trade_default=False,
        context_intervals=["4h", "15m"],
        refinement_intervals=["15m"],
        stop_method="atr_wide",
        target_method="atr_wide",
        mae_penalty_weight=2.0,
        cost_penalty_weight=2.0,
        time_penalty_weight=1.5,
    )


def _input(entry_price: float, atr: float, candles: list[Candle]) -> SimulationInput:
    return SimulationInput(
        symbol="ETHUSDT",
        decision_timestamp="2026-06-01T14:00:00Z",
        mode=TradingMode.SCALP,
        primary_interval="1h",
        entry_price=entry_price,
        atr=atr,
        future_path=FuturePath(candles=candles),
        profile=scalp_profile(),
    )


def test_scalp_long_target_hit():
    """SCALP LONG hits target.
    Entry: 3000, ATR: 50, Stop: 2925, Target: 3090
    """
    candles = [
        Candle(open=3010, high=3020, low=3005, close=3015),
        Candle(open=3015, high=3050, low=3010, close=3040),
        Candle(open=3040, high=3100, low=3035, close=3095),
    ]
    result = simulate(_input(3000.0, 50.0, candles))

    assert result.long_outcome.exit_reason == "TARGET_HIT"
    assert result.long_outcome.realized_r_gross > 0.5
    assert result.long_outcome.realized_r_net > 0
    assert result.best_action in ("LONG_NOW",)
    assert not result.is_ambiguous


def test_scalp_long_stop_hit():
    """SCALP LONG hits stop in downtrend."""
    candles = [
        Candle(open=2980, high=2990, low=2950, close=2960),
        Candle(open=2960, high=2970, low=2900, close=2910),
    ]
    result = simulate(_input(3000.0, 50.0, candles))

    assert result.long_outcome.exit_reason == "STOP_HIT"
    assert result.long_outcome.realized_r_gross < 0
    assert result.short_outcome.exit_reason == "TARGET_HIT"
    assert result.short_outcome.realized_r_gross > 0


def test_scalp_time_exit():
    """SCALP time exit with wide stops."""
    candles = [
        Candle(open=3005, high=3020, low=3000, close=3015),
        Candle(open=3015, high=3030, low=3010, close=3025),
        Candle(open=3025, high=3040, low=3020, close=3035),
    ]
    profile = scalp_profile()
    profile.max_holding_bars = 3
    profile.stop_multiplier = 5.0
    profile.target_multiplier = 5.0

    inp = SimulationInput(
        symbol="ETHUSDT",
        decision_timestamp="2026-06-01T14:00:00Z",
        mode=TradingMode.SCALP,
        primary_interval="1h",
        entry_price=3000.0,
        atr=50.0,
        future_path=FuturePath(candles=candles),
        profile=profile,
    )
    result = simulate(inp)

    assert result.long_outcome.exit_reason == "TIME_EXIT"
    assert result.short_outcome.exit_reason == "TIME_EXIT"
    assert result.long_outcome.realized_r_gross >= 0
    assert result.short_outcome.realized_r_gross <= 0


def test_scalp_short_target_hit():
    """SCALP SHORT hits target.
    Entry: 3000, ATR: 60, Stop: 3090, Target: 2892
    SHORT hits target at bar 1 (fast exit avoids time penalty).
    """
    candles = [
        Candle(open=2980, high=2990, low=2900, close=2910),
        Candle(open=2910, high=2920, low=2850, close=2870),  # low < 2892, target hit
    ]
    result = simulate(_input(3000.0, 60.0, candles))

    assert result.short_outcome.exit_reason == "TARGET_HIT"
    assert result.short_outcome.realized_r_gross > 0
    assert result.long_outcome.exit_reason == "STOP_HIT"
    assert result.best_action in ("SHORT_NOW",)
