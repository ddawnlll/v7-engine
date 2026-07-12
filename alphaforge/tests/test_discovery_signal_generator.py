"""Tests for discovery signal generator.

Tests: generate_trade_signals, filter_overlapping_signals.
"""

from __future__ import annotations

import numpy as np
import pytest

from alphaforge.discovery import TradeSignal
from alphaforge.discovery.signal_generator import (
    _compute_atr_at_index,
    filter_overlapping_signals,
    generate_trade_signals,
)
from lib.config_training import load_training_config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MODE_CFG = load_training_config("SWING")


def _make_ohlcv(n: int = 200) -> dict:
    rng = np.random.RandomState(42)
    close = 100.0 * np.exp(np.cumsum(rng.randn(n) * 0.01))
    close = np.maximum(close, 0.01)
    high = close * (1.0 + rng.uniform(0, 0.01, n))
    low = close * (1.0 - rng.uniform(0, 0.01, n))
    open_ = close * (1.0 + rng.randn(n) * 0.005)
    return {
        "close": close.astype(np.float64),
        "high": high.astype(np.float64),
        "low": low.astype(np.float64),
        "open": open_.astype(np.float64),
        "volume": rng.lognormal(10, 1, n).astype(np.float64),
        "timestamp": np.arange(n, dtype=np.int64),
        "symbol": ["BTCUSDT"] * n,
    }


def _make_fold_results(n_folds: int = 3, n_val: int = 30) -> list[dict]:
    results = []
    for f in range(n_folds):
        train_end = (f + 1) * 50 + 100  # pad to ensure enough lookback
        val_start = train_end
        val_end = val_start + n_val
        embargo = max(1, n_val // 8)
        eff_start = val_start + embargo
        if eff_start >= val_end:
            eff_start = val_start  # no room for embargo
        results.append({
            "fold": f + 1,
            "val_start": val_start,
            "val_end": val_end,
            "effective_val_start": eff_start,
            "n_val": n_val,
            "n_train": train_end,
        })
    return results


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGenerateTradeSignals:
    """Tests for generate_trade_signals()."""

    def test_basic_signal_generation(self):
        """Generates signals from valid predictions above threshold."""
        ohlcv = _make_ohlcv(300)
        n = 300
        symbols = np.array(["BTCUSDT"] * n, dtype=object)
        timestamps = np.arange(n, dtype=np.int64)
        close = ohlcv["close"].astype(np.float64)

        fold_results = _make_fold_results(2, 30)

        # Build fold_preds/fold_y_class matching the effective val window size
        fold_preds_list, fold_y_class_list = [], []
        for fr in fold_results:
            eff_start = fr.get("effective_val_start", fr["val_start"])
            val_end = fr["val_end"]
            eff_n = val_end - eff_start
            fold_preds_list.append(np.full(eff_n, 0.85, dtype=np.float64))
            # Mix of LONG (0) and SHORT (1), some NO_TRADE (2)
            fold_y_class_list.append(
                np.array([0 if i % 3 != 0 else 2 for i in range(eff_n)], dtype=np.int32)
            )

        signals = generate_trade_signals(
            fold_results, fold_preds_list, fold_y_class_list,
            ohlcv, _MODE_CFG, timestamps, symbols, close,
            confidence_threshold=0.55,
        )

        assert len(signals) > 0, "Should generate some signals"
        for s in signals:
            assert s.side in ("LONG", "SHORT"), f"Unexpected side: {s.side}"
            assert s.confidence >= 0.55, f"Confidence below threshold: {s.confidence}"
            assert s.stop_price > 0, "Stop price must be positive"
            assert s.target_price > 0, "Target price must be positive"
            assert s.initial_risk > 0, "Initial risk must be positive"

    def test_confidence_threshold_filters_low_confidence(self):
        """Signals below confidence threshold are excluded."""
        ohlcv = _make_ohlcv(200)
        n = 200
        symbols = np.array(["BTCUSDT"] * n, dtype=object)
        timestamps = np.arange(n, dtype=np.int64)
        close = ohlcv["close"].astype(np.float64)

        fold_results = _make_fold_results(1, 20)
        fr = fold_results[0]
        eff_start = fr.get("effective_val_start", fr["val_start"])
        eff_n = fr["val_end"] - eff_start

        # All low-confidence predictions
        fold_preds = [np.full(eff_n, 0.45, dtype=np.float64)]
        fold_y_class = [np.zeros(eff_n, dtype=np.int32)]  # all LONG

        signals = generate_trade_signals(
            fold_results, fold_preds, fold_y_class,
            ohlcv, _MODE_CFG, timestamps, symbols, close,
            confidence_threshold=0.55,
        )

        assert len(signals) == 0, "All predictions below threshold"

    def test_no_signals_when_all_no_trade(self):
        """All-NO_TRADE predictions produce no signals."""
        ohlcv = _make_ohlcv(200)
        n = 200
        symbols = np.array(["BTCUSDT"] * n, dtype=object)
        timestamps = np.arange(n, dtype=np.int64)
        close = ohlcv["close"].astype(np.float64)

        fold_results = _make_fold_results(1, 20)
        fr = fold_results[0]
        eff_n = fr["val_end"] - fr.get("effective_val_start", fr["val_start"])

        # All NO_TRADE (class 2)
        fold_preds = [np.full(eff_n, 0.95, dtype=np.float64)]
        fold_y_class = [np.full(eff_n, 2, dtype=np.int32)]

        signals = generate_trade_signals(
            fold_results, fold_preds, fold_y_class,
            ohlcv, _MODE_CFG, timestamps, symbols, close,
            confidence_threshold=0.55,
        )

        assert len(signals) == 0, "NO_TRADE predictions filtered out"

    def test_handles_empty_folds(self):
        """Empty fold results produce empty signals."""
        signals = generate_trade_signals(
            [], [], [], _make_ohlcv(100), _MODE_CFG,
            np.array([], dtype=np.int64), np.array([], dtype=object), None,
        )
        assert signals == []


class TestFilterOverlappingSignals:
    """Tests for filter_overlapping_signals()."""

    def make_signal(self, symbol, bar_index, side="LONG"):
        return TradeSignal(
            bar_index=bar_index, timestamp=bar_index * 1000,
            symbol=symbol, side=side, entry_price=100.0,
            atr=2.0, stop_price=98.0, target_price=106.0,
            confidence=0.85, model_score=0.85, initial_risk=2.0,
        )

    def test_deduplicates_same_symbol(self):
        """Consecutive same-symbol signals are deduplicated."""
        signals = [
            self.make_signal("BTCUSDT", 10),
            self.make_signal("BTCUSDT", 12),  # too close → removed
            self.make_signal("BTCUSDT", 25),  # far enough → kept
        ]
        filtered = filter_overlapping_signals(signals)
        assert len(filtered) == 2
        assert filtered[0].bar_index == 10
        assert filtered[1].bar_index == 25

    def test_keeps_different_symbols(self):
        """Different symbols are never overlapping."""
        signals = [
            self.make_signal("BTCUSDT", 10),
            self.make_signal("ETHUSDT", 12),
        ]
        filtered = filter_overlapping_signals(signals)
        assert len(filtered) == 2

    def test_handles_empty_list(self):
        assert filter_overlapping_signals([]) == []


class TestComputeAtrAtIndex:
    """Tests for _compute_atr_at_index()."""

    def test_computes_atr_from_lookback(self):
        """ATR computed from preceding bars of same symbol."""
        n = 100
        close = np.ones(n, dtype=np.float64) * 100.0
        high = np.ones(n, dtype=np.float64) * 102.0
        low = np.ones(n, dtype=np.float64) * 98.0
        symbols = np.array(["BTCUSDT"] * n, dtype=object)

        atr = _compute_atr_at_index(close, high, low, symbols, "BTCUSDT", 50)
        assert atr is not None
        assert atr > 0
        # With constant high-low=4, TR=4, ATR should be ~4
        assert abs(atr - 4.0) < 1.0, f"Unexpected ATR: {atr}"

    def test_returns_none_at_start(self):
        """Not enough lookback data returns None."""
        n = 5
        close = np.ones(n) * 100.0
        high = np.ones(n) * 102.0
        low = np.ones(n) * 98.0
        symbols = np.array(["BTCUSDT"] * n, dtype=object)

        atr = _compute_atr_at_index(close, high, low, symbols, "BTCUSDT", 3)
        assert atr is None
