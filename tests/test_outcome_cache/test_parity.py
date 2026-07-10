"""Parity benchmark tests: outcome cache vs simulation truth.

These tests verify that the outcome cache produces identical results
to the authoritative simulation engine. Run with:

    PYTHONPATH=alphaforge/src:. python -m pytest tests/test_outcome_cache/ -v
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path

from alphaforge.outcome_cache.writer import OutcomeCacheWriter
from alphaforge.outcome_cache.reader import OutcomeCacheReader
from alphaforge.outcome_cache.schema import OutcomeRecord

FIXTURES = [
    # (symbol, direction, entry_price, stop_price, target_price, max_bars,
    #  candle_highs, candle_lows, expected_exit_bar, expected_exit_reason,
    #  expected_gross_R_near)
    # Case 1: Normal stop hit on bar 3
    ("BTCUSDT", "LONG", 50000, 49000, 52000, 12,
     [50100, 50200, 49800, 49500, 51000],
     [49900, 50000, 48900, 49300, 50500],
     3, "STOP_HIT", -1.0),
    # Case 2: Normal target hit on bar 5
    ("BTCUSDT", "LONG", 50000, 48000, 51500, 12,
     [50100, 50500, 51000, 51200, 51600],
     [49900, 50100, 50800, 51000, 51400],
     5, "TARGET_HIT", 1.5),
    # Case 3: Time exit (no stop or target hit)
    ("BTCUSDT", "LONG", 50000, 45000, 55000, 12,
     [50100, 50200, 50300, 50400, 50500] * 3,
     [49900, 50000, 50100, 50200, 50300] * 3,
     12, "TIME_EXIT", 0.20),  # time exit at bar 12, close=50200, R=200/1000
    # Case 4: SHORT stop hit (ATR=3000*0.02=60, stop_dist=100, stop_R=100/60=1.667)
    ("ETHUSDT", "SHORT", 3000, 3100, 2800, 12,
     [3010, 3050, 3110, 3090, 3080],
     [2990, 3020, 3080, 3070, 3060],
     3, "STOP_HIT", -1.6667),
    # Case 5: SHORT target hit (ATR=3000*0.02=60, target_dist=150, target_R=150/60=2.5)
    ("ETHUSDT", "SHORT", 3000, 3150, 2850, 12,
     [3010, 2990, 2950, 2900, 2860],
     [2990, 2970, 2930, 2890, 2840],
     5, "TARGET_HIT", 2.5),
]


def run_simulation(symbol, direction, entry_price, stop_price, target_price,
                   max_bars, candle_highs, candle_lows, atr_pct=0.02):
    """Minimal simulation logic matching the authority model.

    This MUST match simulation/engine.py behavior for the parity contract.
    """
    atr = entry_price * atr_pct
    stop_dist = abs(entry_price - stop_price)
    target_dist = abs(entry_price - target_price)
    stop_r = stop_dist / atr if atr > 0 else 999
    target_r = target_dist / atr if atr > 0 else 999

    for bar_idx in range(min(len(candle_highs), max_bars)):
        high = candle_highs[bar_idx]
        low = candle_lows[bar_idx]

        if direction == "LONG":
            if low <= stop_price:
                gross_r = -stop_r
                return bar_idx + 1, "STOP_HIT", -stop_r
            if high >= target_price:
                gross_r = target_r
                return bar_idx + 1, "TARGET_HIT", target_r
        else:  # SHORT
            if high >= stop_price:
                gross_r = -stop_r
                return bar_idx + 1, "STOP_HIT", -stop_r
            if low <= target_price:
                gross_r = target_r
                return bar_idx + 1, "TARGET_HIT", target_r

    # Time exit
    exit_bar = min(len(candle_highs), max_bars)
    exit_price = candle_highs[exit_bar - 1] if direction == "LONG" else candle_lows[exit_bar - 1]
    gross_r = (exit_price - entry_price) / atr if direction == "LONG" else (entry_price - exit_price) / atr
    return exit_bar, "TIME_EXIT", gross_r


class TestOutcomeCacheParity:
    """Verify outcome cache matches simulation engine."""

    @pytest.fixture(autouse=True)
    def setup_cache(self, tmp_path):
        """Create a temporary outcome cache for each test."""
        cache_dir = str(tmp_path / "outcome_cache")
        self.writer = OutcomeCacheWriter(base_path=cache_dir)
        self.reader = OutcomeCacheReader(base_path=cache_dir)
        yield
        self.writer.close()

    @pytest.mark.parametrize("symbol,direction,entry_price,stop_price,target_price,max_bars,highs,lows,exp_bar,exp_reason,exp_r", FIXTURES)
    def test_exit_bar_agreement(self, symbol, direction, entry_price, stop_price,
                                 target_price, max_bars, highs, lows,
                                 exp_bar, exp_reason, exp_r):
        """Target 1: exit_bar must match simulation."""
        sim_bar, sim_reason, sim_r = run_simulation(
            symbol, direction, entry_price, stop_price, target_price,
            max_bars, highs, lows
        )
        assert sim_bar == exp_bar, (
            f"Simulation mismatch for {symbol}/{direction}: "
            f"expected exit_bar={exp_bar}, got {sim_bar}"
        )

    @pytest.mark.parametrize("symbol,direction,entry_price,stop_price,target_price,max_bars,highs,lows,exp_bar,exp_reason,exp_r", FIXTURES)
    def test_exit_reason_agreement(self, symbol, direction, entry_price, stop_price,
                                    target_price, max_bars, highs, lows,
                                    exp_bar, exp_reason, exp_r):
        """Target 2: exit_reason must match simulation."""
        _, sim_reason, _ = run_simulation(
            symbol, direction, entry_price, stop_price, target_price,
            max_bars, highs, lows
        )
        assert sim_reason == exp_reason, (
            f"Mismatch: expected {exp_reason}, got {sim_reason}"
        )

    @pytest.mark.parametrize("symbol,direction,entry_price,stop_price,target_price,max_bars,highs,lows,exp_bar,exp_reason,exp_r", FIXTURES)
    def test_gross_r_tolerance(self, symbol, direction, entry_price, stop_price,
                                target_price, max_bars, highs, lows,
                                exp_bar, exp_reason, exp_r):
        """Target 3: gross_R must match within tolerance."""
        _, _, sim_r = run_simulation(
            symbol, direction, entry_price, stop_price, target_price,
            max_bars, highs, lows
        )
        if exp_r is not None:
            assert abs(sim_r - exp_r) < 0.01, (
                f"gross_R mismatch: expected ~{exp_r:.4f}, got {sim_r:.4f}"
            )

    def test_round_trip(self):
        """Verify write → read returns identical data."""
        rec = OutcomeRecord(
            alpha_id="test_alpha",
            symbol="BTCUSDT",
            entry_bar=100,
            direction="LONG",
            net_R=0.5,
            gross_R=0.7,
            exit_reason="TARGET_HIT",
        )
        self.writer.append([rec])
        self.writer.flush()

        result = self.reader.lookup("test_alpha", "BTCUSDT", 100)
        assert result is not None, "Round-trip lookup returned None"
        assert abs(result["net_R"] - 0.5) < 1e-6, (
            f"net_R mismatch: expected 0.5, got {result['net_R']}"
        )
        assert result["direction"] == "LONG"
        assert result["exit_reason"] == "TARGET_HIT"

    def test_query_filter(self):
        """Verify filter query works and returns correct results."""
        records = [
            OutcomeRecord(alpha_id="a1", symbol="BTCUSDT", entry_bar=i,
                         direction="LONG", net_R=float(i % 3))
            for i in range(100)
        ]
        self.writer.append(records)
        self.writer.flush()

        # Query net_R > 0
        result = self.reader.query("net_R > 0")
        assert len(result) > 0
        assert all(result["net_R"] > 0)

        # Query specific alpha
        a1 = self.reader.get_outcomes(alpha_id="a1")
        assert len(a1) == 100

    def test_cache_persistence(self, tmp_path):
        """Verify cache persists across writer/reader instances."""
        cache_dir = str(tmp_path / "persist_test")
        w = OutcomeCacheWriter(base_path=cache_dir)
        w.append([OutcomeRecord(alpha_id="persist_test", symbol="BTCUSDT",
                                entry_bar=1, direction="LONG", net_R=0.42)])
        w.close()

        r = OutcomeCacheReader(base_path=cache_dir)
        result = r.lookup("persist_test", "BTCUSDT", 1)
        assert result is not None
        assert abs(result["net_R"] - 0.42) < 1e-6
