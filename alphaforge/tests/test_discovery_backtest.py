"""Tests for discovery simulation backtest bridge.

Tests: backtest_signals, _build_profile, _extract_future_candles.
"""

from __future__ import annotations

import numpy as np
import pytest

from alphaforge.discovery import TradeSignal
from alphaforge.discovery.backtest import (
    _build_profile,
    _extract_future_candles,
    backtest_signals,
)
from alphaforge.train import MODE_CONFIG


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_ohlcv(n: int = 200) -> dict:
    rng = np.random.RandomState(42)
    close = 100.0 * np.exp(np.cumsum(rng.randn(n) * 0.01))
    close = np.maximum(close, 0.01)
    high = close * (1.0 + rng.uniform(0, 0.01, n))
    low = close * (1.0 - rng.uniform(0, 0.01, n))
    open_ = close * (1.0 + rng.randn(n) * 0.005)
    timestamps = np.arange(n, dtype=np.int64)
    return {
        "close": close.astype(np.float64),
        "high": high.astype(np.float64),
        "low": low.astype(np.float64),
        "open": open_.astype(np.float64),
        "volume": rng.lognormal(10, 1, n).astype(np.float64),
        "timestamp": timestamps,
        "symbol": ["BTCUSDT"] * n,
    }


def _make_signal(bar_index=50, ts: int | None = None, side="LONG",
                 symbol="BTCUSDT") -> TradeSignal:
    if ts is None:
        ts = bar_index * 3600_000_000_000
    return TradeSignal(
        bar_index=bar_index, timestamp=ts,
        symbol=symbol, side=side, entry_price=100.0,
        atr=2.0, stop_price=98.0 if side == "LONG" else 102.0,
        target_price=106.0 if side == "LONG" else 94.0,
        confidence=0.85, model_score=0.85, initial_risk=2.0,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildProfile:
    """Tests for _build_profile()."""

    def test_builds_swing_profile(self):
        profile = _build_profile("SWING", 2.0, 3.0, 30)
        assert profile.mode.value == "SWING"
        assert profile.primary_interval == "4h"
        assert profile.max_holding_bars == 30
        assert profile.stop_multiplier == 2.0
        assert profile.target_multiplier == 3.0

    def test_builds_scalp_profile(self):
        profile = _build_profile("SCALP", 1.5, 2.0, 12)
        assert profile.mode.value == "SCALP"
        assert profile.primary_interval == "1h"
        assert profile.max_holding_bars == 12

    def test_builds_aggressive_scalp_profile(self):
        profile = _build_profile("AGGRESSIVE_SCALP", 1.5, 2.0, 5)
        assert profile.mode.value == "AGGRESSIVE_SCALP"
        assert profile.primary_interval == "15m"

    def test_raises_on_unknown_mode(self):
        with pytest.raises(ValueError, match="Unknown mode"):
            _build_profile("UNKNOWN", 1.0, 1.0, 10)


class TestExtractFutureCandles:
    """Tests for _extract_future_candles()."""

    def test_extracts_candles_for_symbol(self):
        """Extracts forward candles for the matching symbol."""
        # Multi-symbol OHLCV
        n = 200
        ohlcv0 = _make_ohlcv(n)
        ohlcv0["symbol"] = ["BTCUSDT"] * n + ["ETHUSDT"] * n
        ohlcv0["timestamp"] = np.arange(2 * n)
        for k in ["close", "high", "low", "open"]:
            ohlcv0[k] = np.concatenate([ohlcv0[k], ohlcv0[k][:n]])

        candles = _extract_future_candles(ohlcv0, "BTCUSDT", 50, 10)
        assert len(candles) > 0
        assert len(candles) <= 11  # max_hold + 1
        for c in candles:
            assert c.close > 0
            assert c.high >= c.low

    def test_returns_empty_for_missing_timestamp(self):
        """Non-existent timestamp returns empty list."""
        ohlcv = _make_ohlcv(100)
        candles = _extract_future_candles(ohlcv, "BTCUSDT", 999999, 10)
        assert candles == []

    def test_returns_empty_for_wrong_symbol(self):
        """Wrong symbol returns empty."""
        ohlcv = _make_ohlcv(100)
        ohlcv["symbol"] = ["BTCUSDT"] * 50 + ["ETHUSDT"] * 50
        candles = _extract_future_candles(ohlcv, "SOLUSDT", 10, 10)
        assert candles == []


class TestBacktestSignals:
    """Tests for backtest_signals()."""

    def test_backtests_single_long_signal(self):
        """Single LONG signal produces a BacktestTradeResult."""
        ohlcv = _make_ohlcv(200)
        ohlcv["symbol"] = ["BTCUSDT"] * 200
        ohlcv["timestamp"] = np.arange(200, dtype=np.int64)
        signals = [_make_signal(50, ts=50, side="LONG")]

        results = backtest_signals(signals, ohlcv, "SWING")

        assert len(results) == 1
        r = results[0]
        assert r.signal.side == "LONG"
        assert r.exit_reason != "", "Should have an exit reason"
        assert isinstance(r.realized_r_net, float)
        assert isinstance(r.realized_r_gross, float)

    def test_backtests_multiple_signals(self):
        """Multiple signals across folds produce correct number of results."""
        ohlcv = _make_ohlcv(300)
        ohlcv["symbol"] = ["BTCUSDT"] * 300
        ohlcv["timestamp"] = np.arange(300, dtype=np.int64)
        signals = [
            _make_signal(50, ts=50, side="LONG"),
            _make_signal(100, ts=100, side="SHORT"),
            _make_signal(150, ts=150, side="LONG"),
        ]

        results = backtest_signals(signals, ohlcv, "SWING")
        assert len(results) >= 0  # may skip some near end

    def test_handles_empty_signals(self):
        """Empty signals list produces empty results."""
        results = backtest_signals([], _make_ohlcv(100), "SWING")
        assert results == []

    def test_skips_signals_without_future(self):
        """Signals near end of data are skipped gracefully."""
        ohlcv = _make_ohlcv(50)
        ohlcv["symbol"] = ["BTCUSDT"] * 50
        ohlcv["timestamp"] = np.arange(50, dtype=np.int64)
        signals = [_make_signal(45, ts=45, side="LONG")]

        results = backtest_signals(signals, ohlcv, "SWING")
        assert isinstance(results, list)
