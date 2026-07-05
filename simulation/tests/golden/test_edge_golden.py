"""Additional golden tests — edge cases toward 12+ fixture target."""

from simulation.contracts.models import Candle, FuturePath, SimulationInput, SimulationProfile, TradingMode
from simulation.engine.engine import simulate


def _make_input(
    entry: float,
    atr: float,
    candles: list[Candle],
    mode: TradingMode = TradingMode.SWING,
    stop_mult: float = 2.0,
    target_mult: float = 2.5,
    max_bars: int = 30,
) -> SimulationInput:
    return SimulationInput(
        symbol="BTCUSDT",
        decision_timestamp="2026-06-01T12:00:00Z",
        mode=mode,
        primary_interval="4h",
        entry_price=entry,
        atr=atr,
        future_path=FuturePath(candles=candles),
        profile=SimulationProfile(
            profile_version="golden-1.0",
            mode=mode,
            primary_interval="4h",
            max_holding_bars=max_bars,
            stop_multiplier=stop_mult,
            target_multiplier=target_mult,
            ambiguity_margin_r=0.20,
            min_action_edge_r=0.35,
            no_trade_default=False,
            mae_penalty_weight=1.0,
            cost_penalty_weight=1.0,
            time_penalty_weight=0.3,
        ),
    )


def test_same_candle_stop_and_target():
    """Same candle hits both stop and target; stop-before-target wins."""
    inp = _make_input(
        entry=50000, atr=1000,
        candles=[Candle(open=50500, high=53000, low=47000, close=51000)],
        stop_mult=2.0, target_mult=2.5,
    )
    result = simulate(inp)
    assert result.long_outcome.exit_reason == "STOP_HIT"


def test_no_candles_returns_time_exit():
    """Empty future path → time exit at entry."""
    inp = _make_input(entry=50000, atr=1000, candles=[])
    result = simulate(inp)
    assert result.long_outcome.exit_reason == "TIME_EXIT"
    assert result.short_outcome.exit_reason == "TIME_EXIT"
    assert result.long_outcome.realized_r_gross == 0.0


def test_exact_stop_touch():
    """Price exactly touches stop level without going through."""
    inp = _make_input(
        entry=50000, atr=1000,
        candles=[Candle(open=49900, high=49900, low=48000, close=48100)],
        stop_mult=2.0,
    )
    result = simulate(inp)
    # Long stop = 50000 - 2000 = 48000, low=48000 exactly hits it
    assert result.long_outcome.exit_reason == "STOP_HIT"
    assert result.long_outcome.exit_price == 48000.0


def test_short_hits_stop():
    """SHORT price rises to stop level."""
    inp = _make_input(
        entry=50000, atr=1000,
        candles=[Candle(open=50100, high=52000, low=50000, close=51000)],
        stop_mult=2.0,
    )
    result = simulate(inp)
    # Short stop = 50000 + 2000 = 52000, high=52000 exactly hits it
    assert result.short_outcome.exit_reason == "STOP_HIT"
    assert result.short_outcome.exit_price == 52000.0


def test_short_time_exit_no_extreme():
    """SHORT time exit with slight upward drift."""
    inp = _make_input(
        entry=50000, atr=500,
        candles=[Candle(open=50100, high=50200, low=50000, close=50150) for _ in range(3)],
        stop_mult=5.0, target_mult=5.0, max_bars=3,
    )
    result = simulate(inp)
    assert result.short_outcome.exit_reason == "TIME_EXIT"
    assert result.short_outcome.realized_r_gross <= 0
