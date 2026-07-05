"""
Tests for simulation engine exit logic — stop/target/time-exit precedence.

Tests simulate_path() directly with synthetic candle data to verify
conservative stop-before-target rule and all exit paths.
"""

from __future__ import annotations

import pytest

from simulation.contracts.models import Candle
from simulation.engine.exits import simulate_path


class TestEngineExits:
    """Engine exit logic — stop/target/time-exit precedence."""

    @staticmethod
    def _candle(open_: float, high: float, low: float, close: float) -> Candle:
        return Candle(open=open_, high=high, low=low, close=close)

    # ── Stop-before-target tests ─────────────────────────────────────

    def test_stop_hit_before_target_long(self):
        """Stop hit before target for LONG — low touches stop first."""
        candles = [self._candle(95, 105, 85, 90)]
        result = simulate_path(
            "LONG", entry_price=100, stop_price=90, target_price=120,
            candles=candles, max_holding_bars=10, entry_risk=10,
        )
        assert result.exit_reason == "STOP_HIT"
        assert result.exit_price == 90
        assert result.exit_bar_index == 0
        # (stop - entry) / risk = (90 - 100) / 10 = -1.0
        assert result.realized_r_gross == pytest.approx(-1.0)

    def test_stop_hit_before_target_short(self):
        """Stop hit before target for SHORT — high touches stop first."""
        candles = [self._candle(105, 115, 95, 110)]
        result = simulate_path(
            "SHORT", entry_price=100, stop_price=110, target_price=80,
            candles=candles, max_holding_bars=10, entry_risk=10,
        )
        assert result.exit_reason == "STOP_HIT"
        assert result.exit_price == 110
        assert result.exit_bar_index == 0
        # (entry - stop) / risk = (100 - 110) / 10 = -1.0
        assert result.realized_r_gross == pytest.approx(-1.0)

    # ── Target-before-stop tests ─────────────────────────────────────

    def test_target_hit_before_stop_long(self):
        """Target hit before stop for LONG — high touches target."""
        candles = [self._candle(105, 125, 95, 120)]
        result = simulate_path(
            "LONG", entry_price=100, stop_price=90, target_price=120,
            candles=candles, max_holding_bars=10, entry_risk=10,
        )
        assert result.exit_reason == "TARGET_HIT"
        assert result.exit_price == 120
        assert result.exit_bar_index == 0
        # (target - entry) / risk = (120 - 100) / 10 = 2.0
        assert result.realized_r_gross == pytest.approx(2.0)

    def test_target_hit_before_stop_short(self):
        """Target hit before stop for SHORT — low touches target."""
        candles = [self._candle(95, 105, 75, 80)]
        result = simulate_path(
            "SHORT", entry_price=100, stop_price=110, target_price=80,
            candles=candles, max_holding_bars=10, entry_risk=10,
        )
        assert result.exit_reason == "TARGET_HIT"
        assert result.exit_price == 80
        assert result.exit_bar_index == 0
        # (entry - target) / risk = (100 - 80) / 10 = 2.0
        assert result.realized_r_gross == pytest.approx(2.0)

    # ── Same-candle ambiguity ─────────────────────────────────────────

    def test_same_candle_ambiguity_stop_first(self):
        """Same-candle stop/target ambiguity -> stop-first (conservative).

        Both stop (90) and target (120) are crossed in the same candle.
        Stop check precedes target check, so STOP_HIT wins.
        """
        candles = [self._candle(105, 125, 85, 110)]
        result = simulate_path(
            "LONG", entry_price=100, stop_price=90, target_price=120,
            candles=candles, max_holding_bars=10, entry_risk=10,
        )
        assert result.exit_reason == "STOP_HIT"
        assert result.same_candle_ambiguity is True

    # ── Time-exit ─────────────────────────────────────────────────────

    def test_time_exit_after_max_holding_bars(self):
        """Time exit when max_holding_bars elapses without stop/target hit."""
        candles = [
            self._candle(101, 102, 99, 101),
            self._candle(101, 103, 100, 102),
            self._candle(102, 104, 101, 103),
            self._candle(103, 105, 102, 104),
            self._candle(104, 106, 103, 105),
        ]
        result = simulate_path(
            "LONG", entry_price=100, stop_price=90, target_price=120,
            candles=candles, max_holding_bars=3, entry_risk=10,
        )
        assert result.exit_reason == "TIME_EXIT"
        # loop ran bars 0,1,2 → exit_bar_index = 2
        assert result.exit_bar_index == 2
        assert result.hold_duration_bars == 3

    def test_horizon_end_when_path_exhausted(self):
        """Horizon end when candle path is shorter than max_holding_bars.

        Only 1 candle available but max_holding_bars=10 — engine uses
        whatever bars exist and time-exits after all are consumed.
        """
        candles = [self._candle(101, 102, 99, 101)]
        result = simulate_path(
            "LONG", entry_price=100, stop_price=90, target_price=120,
            candles=candles, max_holding_bars=10, entry_risk=10,
        )
        assert result.exit_reason == "TIME_EXIT"
        assert result.exit_bar_index == 0
        assert result.hold_duration_bars == 1

    # ── Ordering invariants ───────────────────────────────────────────

    def test_stop_checked_before_target_in_each_bar(self):
        """Stop checked before target per bar — conservative ordering.

        Two bars: bar 0 is benign, bar 1 triggers both stop and target.
        Stop is checked first, so it wins even though target also crossed.
        """
        candles = [
            self._candle(101, 102, 99, 101),
            self._candle(102, 125, 85, 110),
        ]
        result = simulate_path(
            "LONG", entry_price=100, stop_price=90, target_price=120,
            candles=candles, max_holding_bars=10, entry_risk=10,
        )
        assert result.exit_reason == "STOP_HIT"
        assert result.exit_bar_index == 1
        assert result.same_candle_ambiguity is True
        # stop_before_target flag confirms target was also reachable
        assert result.stop_before_target is True

    def test_time_exit_after_stop_and_target_checked(self):
        """Time exit is checked only after all bars are scanned.

        With no stop or target ever triggered, the engine reaches the
        time-exit fallback after exhausting available bars.
        """
        candles = [
            self._candle(101, 102, 99, 101),
            self._candle(101, 103, 100, 102),
            self._candle(102, 104, 101, 103),
        ]
        result = simulate_path(
            "LONG", entry_price=100, stop_price=90, target_price=120,
            candles=candles, max_holding_bars=5, entry_risk=10,
        )
        assert result.exit_reason == "TIME_EXIT"
        # Neither stop nor target was ever triggered
        assert result.stop_before_target is False
        assert result.target_before_stop is False
        assert result.same_candle_ambiguity is False
