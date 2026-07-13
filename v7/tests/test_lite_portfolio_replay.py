"""Tests for V7-Lite interval-aware shadow portfolio replay."""

from datetime import datetime, timedelta, timezone

import pytest

from v7.lite.portfolio_replay import ReplaySignal, replay_shadow_portfolio
from v7.lite.replay_trace import signals_from_trace


T0 = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _signal(candidate_id, symbol, entry_hours, exit_hours, expected_r, realized_r, size=5.0):
    return ReplaySignal(
        candidate_id=candidate_id, symbol=symbol, direction="LONG",
        entry_timestamp=T0 + timedelta(hours=entry_hours),
        exit_timestamp=T0 + timedelta(hours=exit_hours),
        expected_r_net=expected_r, confidence=0.8, position_size_pct=size,
        realized_r_net=realized_r,
    )


def test_replay_uses_expected_r_for_selection_and_only_books_r_at_exit():
    # Same layer1 cluster: high expected R is selected even though its later
    # realized R is worse. This proves outcome does not leak into ranking.
    result = replay_shadow_portfolio([
        _signal("high-expected", "SOLUSDT", 0, 4, 0.9, -0.6),
        _signal("low-expected", "ADAUSDT", 0, 4, 0.1, 1.4),
    ], portfolio_config={"max_cluster_exposure_pct": 5.0})

    assert result.selected_candidate_ids == ("high-expected",)
    assert result.suppressed_symbols == ("ADAUSDT",)
    assert result.realized_candidate_ids == ("high-expected",)
    assert result.realized_r_sum == -0.6


def test_open_position_blocks_later_entry_until_its_exit():
    result = replay_shadow_portfolio([
        _signal("first", "BTCUSDT", 0, 4, 0.5, 0.2, 6.0),
        _signal("blocked", "ETHUSDT", 1, 2, 0.5, 3.0, 6.0),
        _signal("after-exit", "ETHUSDT", 4, 6, 0.5, 0.4, 6.0),
    ], portfolio_config={"max_total_exposure_pct": 10.0})

    assert result.selected_candidate_ids == ("first", "after-exit")
    assert result.suppressed_symbols == ("ETHUSDT",)
    assert result.realized_candidate_ids == ("first", "after-exit")
    assert result.realized_r_sum == pytest.approx(0.6)
    assert result.max_active_positions == 1


def test_same_symbol_signal_is_suppressed_while_prior_trace_position_is_open():
    result = replay_shadow_portfolio([
        _signal("first", "BTCUSDT", 0, 4, 0.5, 0.2, 5.0),
        _signal("overlap", "BTCUSDT", 1, 3, 0.9, 99.0, 5.0),
    ])

    assert result.selected_candidate_ids == ("first",)
    assert result.suppressed_symbols == ("BTCUSDT",)
    assert result.realized_candidate_ids == ("first",)
    assert result.realized_r_sum == pytest.approx(0.2)


def test_replay_rejects_ambiguous_same_symbol_entry():
    with pytest.raises(ValueError, match="one signal per symbol"):
        replay_shadow_portfolio([
            _signal("a", "BTCUSDT", 0, 2, 0.1, 0.1),
            _signal("b", "BTCUSDT", 0, 3, 0.2, 0.2),
        ])


def test_trace_adapter_preserves_exit_interval_and_never_uses_realized_r_as_expected_r():
    signals = signals_from_trace([{
        "timestamp": 1780000000000000000,
        "exit_timestamp": 1780043200000000000,
        "symbol": "BTCUSDT",
        "decision": "LONG_NOW",
        "confidence": 0.76,
        "realized_r_net": 3.5,
    }], position_size_pct=5.0)

    assert len(signals) == 1
    assert signals[0].exit_timestamp > signals[0].entry_timestamp
    assert signals[0].realized_r_net == 3.5
    assert signals[0].expected_r_net == 0.0
