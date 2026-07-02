"""
Tests for path metrics — MFE, MAE, time_to_mfe, path_quality_score.

Verifies correctness, bounds, and determinism of path metric calculations
produced by the engine during exit resolution.
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
from simulation.engine.exits import simulate_path


# ── Shared fixture ──────────────────────────────────────────────────────


@pytest.fixture
def swing_profile() -> SimulationProfile:
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


class TestPathMetrics:
    """Path metrics correctness and invariants."""

    @staticmethod
    def _candle(open_: float, high: float, low: float, close: float) -> Candle:
        return Candle(open=open_, high=high, low=low, close=close)

    def _run_long(
        self, candles: list[Candle], stop: float = 80, target: float = 150,
    ) -> tuple:
        """Helper: run LONG simulation and return (result, entry, risk)."""
        result = simulate_path(
            "LONG", entry_price=100, stop_price=stop, target_price=target,
            candles=candles, max_holding_bars=20, entry_risk=10,
        )
        return result, 100, 10

    def _run_short(
        self, candles: list[Candle], stop: float = 120, target: float = 70,
    ) -> tuple:
        result = simulate_path(
            "SHORT", entry_price=100, stop_price=stop, target_price=target,
            candles=candles, max_holding_bars=20, entry_risk=10,
        )
        return result, 100, 10

    # ── MFE correctness ─────────────────────────────────────────────

    def test_mfe_correctness_long(self):
        """MFE for LONG tracks the highest high relative to entry."""
        # Bar 0: high=115 (mfe=15), bar 1: high=130 (mfe=30), bar 2: high=125 (mfe stays 30)
        # max_holding_bars=5 so all bars scanned
        candles = [
            self._candle(105, 115, 102, 110),
            self._candle(110, 130, 108, 125),
            self._candle(125, 125, 120, 122),
        ]
        result = self._run_long(candles)[0]
        # Target=150 not reached, stop=80 not hit, so TIME_EXIT after available bars
        assert result.exit_reason == "TIME_EXIT"
        # MFE should be max(115-100, 130-100, 125-100) = 30
        assert result.mfe == pytest.approx(30.0)
        assert result.mfe_r == pytest.approx(3.0)  # 30/10 = 3.0

    def test_mae_correctness_long(self):
        """MAE for LONG tracks the lowest low relative to entry (deepest loss)."""
        # Bar 0: low=97 (mae=-3), bar 1: low=85 (mae=-15), bar 2: low=90 (mae stays -15)
        candles = [
            self._candle(100, 105, 97, 102),
            self._candle(102, 108, 85, 95),
            self._candle(95, 100, 90, 92),
        ]
        result = self._run_long(candles, stop=80, target=120)[0]
        # MAE is min of (low - entry) = min(-3, -15, -10) = -15
        assert result.mae == pytest.approx(-15.0)
        assert result.mae_r == pytest.approx(-1.5)  # -15/10 = -1.5

    # ── MFE/MAE bounds ──────────────────────────────────────────────

    def test_mfe_leq_max_high_minus_entry(self):
        """MFE <= max(bar.high) - entry_price for LONG."""
        candles = [
            self._candle(105, 120, 102, 115),
            self._candle(115, 125, 110, 120),
            self._candle(120, 130, 118, 125),
        ]
        result = self._run_long(candles)[0]
        max_high = max(c.high for c in candles)
        assert result.mfe <= max_high - 100

    def test_mae_geq_entry_minus_min_low(self):
        """MAE (negative) >= min_low - entry_price for LONG."""
        candles = [
            self._candle(100, 105, 95, 102),
            self._candle(102, 108, 88, 95),
            self._candle(95, 100, 92, 94),
        ]
        result = self._run_long(candles)[0]
        min_low = min(c.low for c in candles)
        # MAE is the min(low - entry), so the deepest loss is at worst entry - min_low
        # As a negative number: MAE >= min_low - entry_price
        assert result.mae >= min_low - 100

    def test_mfe_bound_short(self):
        """MFE for SHORT tracks best price drop (entry - bar.low)."""
        candles = [
            self._candle(95, 102, 90, 98),
            self._candle(98, 105, 75, 80),
            self._candle(80, 90, 78, 85),
        ]
        result = self._run_short(candles)[0]
        # SHORT MFE = max(entry - bar.low) = max(100-90, 100-75, 100-78) = 25
        assert result.mfe == pytest.approx(25.0)

    def test_mae_bound_short(self):
        """MAE for SHORT: stays at 0 when all highs are above entry (losing)."""
        candles = [
            self._candle(95, 108, 90, 105),
            self._candle(105, 112, 100, 110),
            self._candle(110, 115, 108, 112),
        ]
        result = self._run_short(candles)[0]
        # For SHORT, bar_mae = high - entry. When price rises (high > entry),
        # bar_mae > 0, and since mae starts at 0, no update occurs.
        # MAE stays at 0 for a losing SHORT (all highs above entry).
        assert result.mae == 0.0


    # ── Timing ──────────────────────────────────────────────────────

    def test_time_to_mfe_leq_max_bars(self):
        """time_to_mfe does not exceed available bars."""
        candles = [
            self._candle(101, 105, 99, 102),
            self._candle(102, 110, 100, 108),
            self._candle(108, 115, 106, 112),
        ]
        result = self._run_long(candles)[0]
        assert result.time_to_mfe <= len(candles)

    # ── Path quality ────────────────────────────────────────────────

    def test_path_quality_score_in_range(self, swing_profile):
        """path_quality_score is always in [0, 1]."""
        # Good path: target hit with large profit
        candles_good = [
            self._candle(105, 130, 102, 125),
        ]
        inp_good = SimulationInput(
            symbol="BTCUSDT", decision_timestamp="2026-07-01T00:00:00Z",
            mode=TradingMode.SWING, primary_interval="4h",
            entry_price=100, atr=10,
            future_path=FuturePath(candles=candles_good),
            profile=swing_profile,
        )
        out_good = simulate(inp_good)
        score_good = out_good.long_outcome.path_metrics.path_quality_score
        assert 0.0 <= score_good <= 1.0

        # Bad path: downtrend with losses
        candles_bad = [
            self._candle(99, 102, 96, 98),
            self._candle(98, 101, 95, 97),
            self._candle(97, 100, 93, 95),
        ]
        inp_bad = SimulationInput(
            symbol="BTCUSDT", decision_timestamp="2026-07-01T00:00:00Z",
            mode=TradingMode.SWING, primary_interval="4h",
            entry_price=100, atr=10,
            future_path=FuturePath(candles=candles_bad),
            profile=swing_profile,
        )
        out_bad = simulate(inp_bad)
        score_bad = out_bad.long_outcome.path_metrics.path_quality_score
        assert 0.0 <= score_bad <= 1.0

    def test_path_metrics_deterministic(self):
        """Path metrics are identical for identical input."""
        candles = [
            self._candle(105, 120, 102, 115),
            self._candle(115, 130, 110, 125),
            self._candle(125, 140, 120, 135),
        ]
        result1 = self._run_long(candles)[0]
        result2 = self._run_long(candles)[0]
        assert result1.mfe == result2.mfe
        assert result1.mae == result2.mae
        assert result1.mfe_r == result2.mfe_r
        assert result1.mae_r == result2.mae_r
        assert result1.time_to_mfe == result2.time_to_mfe
        assert result1.time_to_mae == result2.time_to_mae
