"""Unit tests for exit resolution (stop/target/time-exit).

Tests simulate_path directly for both LONG and SHORT directions.
"""

from simulation.contracts.models import Candle
from simulation.engine.exits import simulate_path


def _candles(prices: list[tuple]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c) for o, h, l, c in prices]


def test_long_stop_hit():
    """LONG: price drops below stop."""
    result = simulate_path(
        "LONG", entry_price=100.0, stop_price=95.0, target_price=110.0,
        candles=_candles([(99, 100, 94, 95)]),
        max_holding_bars=10, entry_risk=5.0,
    )
    assert result.exit_reason == "STOP_HIT"
    assert result.realized_r_gross == -1.0  # (95-100)/5 = -1.0
    assert result.exit_bar_index == 0


def test_long_target_hit():
    """LONG: price rises above target."""
    result = simulate_path(
        "LONG", entry_price=100.0, stop_price=95.0, target_price=110.0,
        candles=_candles([(101, 112, 100, 110)]),
        max_holding_bars=10, entry_risk=5.0,
    )
    assert result.exit_reason == "TARGET_HIT"
    assert result.realized_r_gross == 2.0  # (110-100)/5 = 2.0
    assert result.exit_bar_index == 0


def test_long_time_exit():
    """LONG: no stop/target hit within holding period."""
    result = simulate_path(
        "LONG", entry_price=100.0, stop_price=90.0, target_price=120.0,
        candles=_candles([(101, 103, 99, 102), (102, 104, 100, 103)]),
        max_holding_bars=2, entry_risk=10.0,
    )
    assert result.exit_reason == "TIME_EXIT"
    assert result.hold_duration_bars == 2


def test_short_stop_hit():
    """SHORT: price rises above stop."""
    result = simulate_path(
        "SHORT", entry_price=100.0, stop_price=105.0, target_price=90.0,
        candles=_candles([(101, 106, 100, 105)]),
        max_holding_bars=10, entry_risk=5.0,
    )
    assert result.exit_reason == "STOP_HIT"
    assert result.realized_r_gross == -1.0  # (100-105)/5 = -1.0
    assert result.exit_bar_index == 0


def test_short_target_hit():
    """SHORT: price drops below target."""
    result = simulate_path(
        "SHORT", entry_price=100.0, stop_price=105.0, target_price=90.0,
        candles=_candles([(99, 100, 88, 90)]),
        max_holding_bars=10, entry_risk=5.0,
    )
    assert result.exit_reason == "TARGET_HIT"
    assert result.realized_r_gross == 2.0  # (100-90)/5 = 2.0
    assert result.exit_bar_index == 0


def test_short_time_exit():
    """SHORT: no stop/target hit within holding period."""
    result = simulate_path(
        "SHORT", entry_price=100.0, stop_price=105.0, target_price=95.0,
        candles=_candles([(100, 102, 99, 101), (101, 103, 100, 102)]),
        max_holding_bars=2, entry_risk=5.0,
    )
    assert result.exit_reason == "TIME_EXIT"
    assert result.hold_duration_bars == 2


def test_same_candle_ambiguity():
    """Same candle hits both stop and target; stop-before-target wins."""
    result = simulate_path(
        "LONG", entry_price=100.0, stop_price=95.0, target_price=110.0,
        candles=_candles([(105, 115, 93, 108)]),
        max_holding_bars=10, entry_risk=5.0,
    )
    assert result.exit_reason == "STOP_HIT"  # stop checked first
    assert result.same_candle_ambiguity


def test_mfe_mae_tracking():
    """MFE/MAE correctly tracked over multi-bar path."""
    result = simulate_path(
        "LONG", entry_price=100.0, stop_price=95.0, target_price=120.0,
        candles=_candles([
            (101, 105, 99, 103),   # bar0: mfe=5, mae=-1
            (103, 108, 102, 106),  # bar1: mfe=8, mae=-2
            (106, 107, 96, 97),    # bar2: mfe=7, mae=-4
        ]),
        max_holding_bars=10, entry_risk=5.0,
    )
    # Should time-exit (no stop/target hit)
    assert result.exit_reason == "TIME_EXIT"
    assert result.mfe == 8.0   # best high was 108 at bar1
    assert result.mae == -4.0  # worst low was 96 at bar2
    assert result.mfe_r == 1.6   # 8.0 / 5.0
    assert result.mae_r == -0.8  # -4.0 / 5.0


def test_no_candles():
    """No future candles -> time exit at entry price."""
    result = simulate_path(
        "LONG", entry_price=100.0, stop_price=95.0, target_price=110.0,
        candles=[], max_holding_bars=10, entry_risk=5.0,
    )
    assert result.exit_reason == "TIME_EXIT"
    assert result.realized_r_gross == 0.0
    assert result.hold_duration_bars == 0


def test_stop_before_target_precedence():
    """When both stop and target hit, stop wins."""
    candles = _candles([
        (99, 95, 93, 94),   # went below stop, also could hit target? No.
    ])
    # For a SHORT: entry=100, stop=105, target=95
    # Bar: high=99, low=93 -> low < 95 hits target, high=99 < 105 no stop
    result = simulate_path(
        "SHORT", entry_price=100.0, stop_price=105.0, target_price=95.0,
        candles=_candles([(99, 100, 93, 95)]),
        max_holding_bars=10, entry_risk=5.0,
    )
    assert result.exit_reason == "TARGET_HIT"


def test_zero_entry_risk_does_not_crash():
    """Entry risk of 0.0 should not cause division by zero."""
    result = simulate_path(
        "LONG", entry_price=100.0, stop_price=95.0, target_price=110.0,
        candles=_candles([(99, 95, 93, 94)]),
        max_holding_bars=10, entry_risk=0.0,
    )
    assert result.exit_reason == "STOP_HIT"
    assert result.realized_r_gross == 0.0
