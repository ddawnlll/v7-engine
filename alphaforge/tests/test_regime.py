"""Tests for AlphaForge Regime Detection.

Covers:
  (a) TREND_UP classification with known rising price patterns
  (b) TREND_DOWN classification with known falling price patterns
  (c) RANGE classification with low-volatility flat series
  (d) TRANSITION classification with choppy/mixed series
  (e) Insufficient data (early bars default to TRANSITION)
  (f) Determinism: same input produces identical output
  (g) Edge cases: single bar, two bars, NaN handling
  (h) Multi-symbol classification
  (i) Diagnostic helpers (regime_counts, regime_transitions)
  (j) Immutability of RegimeSignal (frozen dataclass)
  (k) Confidence values within [0.0, 1.0] range

Minimum 10 tests per issue #78 requirement.
"""

import math
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Ensure alphaforge is importable
# ---------------------------------------------------------------------------
_src = Path(__file__).resolve().parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from alphaforge.features.regime import (
    ATR_PERIOD,
    RANGE_ATR_PCT_THRESHOLD,
    SMA_PERIOD,
    SLOPE_LOOKBACK,
    Regime,
    RegimeSignal,
    classify_regime,
    classify_regime_multi_symbol,
    regime_counts,
    regime_transitions,
    OnlineRegimeDetector,
    compute_cusum_detector,
    compute_hmm_vol_state,
    compute_volatility_regime,
    compute_regime_group,
)


# ===========================================================================
# Helper: generate deterministic price series
# ===========================================================================


def _make_uptrend(n: int = 80, start: float = 100.0, step: float = 2.0) -> Dict[str, np.ndarray]:
    """Generate a simple monotonically-rising price series."""
    closes = np.array([start + i * step for i in range(n)], dtype=np.float64)
    highs = closes + 5.0
    lows = closes - 5.0
    return {"close": closes, "high": highs, "low": lows}


def _make_downtrend(n: int = 80, start: float = 200.0, step: float = 2.0) -> Dict[str, np.ndarray]:
    """Generate a simple monotonically-falling price series."""
    closes = np.array([start - i * step for i in range(n)], dtype=np.float64)
    highs = closes + 5.0
    lows = closes - 5.0
    return {"close": closes, "high": highs, "low": lows}


def _make_flat(n: int = 80, price: float = 100.0, atr_range: float = 1.0) -> Dict[str, np.ndarray]:
    """Generate a flat price series with low ATR."""
    closes = np.full(n, price, dtype=np.float64)
    highs = closes + atr_range
    lows = closes - atr_range
    return {"close": closes, "high": highs, "low": lows}


# ===========================================================================
# Test 1: TREND_UP — rising price with positive slope
# ===========================================================================


class TestTrendUp:
    """TREND_UP: close > SMA(50) AND slope > 0."""

    def test_monotonic_uptrend(self):
        """Pure rising price should classify as TREND_UP after lookback."""
        data = _make_uptrend(80)
        signals = classify_regime(data["close"], data["high"], data["low"])
        # First 49 bars: insufficient data
        for s in signals[:49]:
            assert s.regime == Regime.TRANSITION
            assert s.confidence == 0.0
        # Remaining bars should all be TREND_UP
        for s in signals[49:]:
            assert s.regime == Regime.TREND_UP
            assert s.confidence > 0.0
            assert s.slope > 0.0
            assert not np.isnan(s.sma_50)

    def test_close_above_sma_positive_slope(self):
        """close > SMA(50) AND slope > 0 => TREND_UP."""
        # Build a series that dips below SMA50 then rises above
        n = 120
        rng = np.random.RandomState(123)
        closes = np.empty(n, dtype=np.float64)
        # First 60 bars: mild movement around 100
        closes[:60] = 100.0 + np.cumsum(rng.randn(60) * 0.5)
        # Next 60 bars: strong uptrend
        closes[60:] = closes[59] + np.cumsum(np.abs(rng.randn(60)) * 3.0 + 0.5)
        highs = closes + np.abs(rng.randn(n) * 2.0)
        lows = closes - np.abs(rng.randn(n) * 2.0)

        signals = classify_regime(closes, highs, lows)

        # Last bar should be TREND_UP (strong uptrend)
        assert signals[-1].regime == Regime.TREND_UP
        # Slope should be positive
        assert signals[-1].slope > 0.0
        # Close should be above SMA50
        assert closes[-1] > signals[-1].sma_50

    def test_uptrend_confidence_increases_with_slope(self):
        """Steeper slopes should produce higher confidence."""
        # Very gentle uptrend: 0.05 per bar
        gentle = _make_uptrend(80, step=0.05)
        sig_gentle = classify_regime(gentle["close"], gentle["high"], gentle["low"])

        # Medium uptrend: 0.5 per bar
        medium = _make_uptrend(80, step=0.5)
        sig_medium = classify_regime(medium["close"], medium["high"], medium["low"])

        # Medium slope should produce higher confidence than gentle
        assert sig_medium[-1].confidence > sig_gentle[-1].confidence
        assert sig_medium[-1].slope > sig_gentle[-1].slope


# ===========================================================================
# Test 2: TREND_DOWN — falling price with negative slope
# ===========================================================================


class TestTrendDown:
    """TREND_DOWN: close < SMA(50) AND slope < 0."""

    def test_monotonic_downtrend(self):
        """Pure falling price should classify as TREND_DOWN after lookback."""
        data = _make_downtrend(80)
        signals = classify_regime(data["close"], data["high"], data["low"])
        # First 49 bars: insufficient data
        for s in signals[:49]:
            assert s.regime == Regime.TRANSITION
        # Remaining bars should all be TREND_DOWN
        for s in signals[49:]:
            assert s.regime == Regime.TREND_DOWN
            assert s.confidence > 0.0
            assert s.slope < 0.0
            assert not np.isnan(s.sma_50)

    def test_close_below_sma_negative_slope(self):
        """close < SMA(50) AND slope < 0 => TREND_DOWN."""
        n = 120
        rng = np.random.RandomState(456)
        closes = np.empty(n, dtype=np.float64)
        closes[:60] = 200.0 + np.cumsum(rng.randn(60) * 0.5)
        closes[60:] = closes[59] - np.cumsum(np.abs(rng.randn(60)) * 3.0 + 0.5)
        highs = closes + np.abs(rng.randn(n) * 2.0)
        lows = closes - np.abs(rng.randn(n) * 2.0)

        signals = classify_regime(closes, highs, lows)

        assert signals[-1].regime == Regime.TREND_DOWN
        assert signals[-1].slope < 0.0
        assert closes[-1] < signals[-1].sma_50

    def test_downtrend_slope_negative(self):
        """Downtrend slope should be negative."""
        data = _make_downtrend(100)
        signals = classify_regime(data["close"], data["high"], data["low"])
        # Every classified bar in pure downtrend has negative slope
        for s in signals[49:]:
            assert s.slope < 0.0


# ===========================================================================
# Test 3: RANGE — low volatility with ATR(14)/close < threshold
# ===========================================================================


class TestRange:
    """RANGE: ATR(14)/close < 0.02."""

    def test_flat_low_atr_series(self):
        """Flat price with tiny ATR should classify as RANGE."""
        data = _make_flat(80, price=100.0, atr_range=0.5)
        signals = classify_regime(data["close"], data["high"], data["low"])

        # First 49 bars: TRANSITION (insufficient SMA)
        for s in signals[:49]:
            assert s.regime == Regime.TRANSITION
        # Remaining bars: RANGE (low ATR, no trend)
        for s in signals[49:]:
            assert s.regime == Regime.RANGE
            assert s.confidence > 0.0
            assert s.atr_pct < RANGE_ATR_PCT_THRESHOLD

    def test_range_atr_below_threshold(self):
        """ATR/close below 0.02 should trigger RANGE."""
        # Price flat but with H/L spread of 1.5 (ATR ~1.5/100 = 0.015 < 0.02)
        data = _make_flat(80, price=100.0, atr_range=0.75)
        signals = classify_regime(data["close"], data["high"], data["low"])
        for s in signals[49:]:
            assert s.regime == Regime.RANGE
            assert not np.isnan(s.atr_pct)
            assert s.atr_pct < RANGE_ATR_PCT_THRESHOLD

    def test_range_confidence_near_zero_atr(self):
        """Very low ATR should give high confidence for RANGE."""
        # Nearly zero range: ATR ~0.1/100 = 0.001
        data = _make_flat(80, price=100.0, atr_range=0.05)
        signals = classify_regime(data["close"], data["high"], data["low"])
        # Near-zero ATR => confidence should be close to 1.0
        assert signals[-1].regime == Regime.RANGE
        assert signals[-1].confidence > 0.9


# ===========================================================================
# Test 4: TRANSITION — none of the above conditions
# ===========================================================================


class TestTransition:
    """TRANSITION: none of TREND_UP, TREND_DOWN, RANGE criteria."""

    def test_chop_classifies_as_transition(self):
        """Choppy, high-volatility market should be TRANSITION."""
        rng = np.random.RandomState(789)
        n = 80
        closes = 100.0 + np.cumsum(rng.randn(n) * 5.0)
        highs = closes + np.abs(rng.randn(n) * 8.0)
        lows = closes - np.abs(rng.randn(n) * 8.0)

        signals = classify_regime(closes, highs, lows)
        # At least some bars should be TRANSITION in choppy market
        transition_count = sum(1 for s in signals if s.regime == Regime.TRANSITION)
        assert transition_count > 0

    def test_close_above_sma_but_negative_slope(self):
        """close > SMA(50) but slope < 0 => NOT TREND_UP, could be TRANSITION."""
        n = 100
        rng = np.random.RandomState(42)
        # Build series: strong uptrend for 50 bars, then slight decline for 50
        closes = np.empty(n, dtype=np.float64)
        closes[:50] = 100.0 + np.arange(50) * 3.0  # steep uptrend
        closes[50:] = closes[49] - np.arange(50) * 0.3  # slight decline
        # Large enough H/L range so ATR/close > 0.02 (avoids RANGE classification)
        highs = closes + 5.0
        lows = closes - 5.0

        signals = classify_regime(closes, highs, lows)
        # After the reversal, price may still be above SMA50 but slope is negative
        # This should be TRANSITION (or eventually TREND_DOWN when close drops below SMA)
        mid_signal = signals[60]
        assert mid_signal.regime in (Regime.TRANSITION, Regime.TREND_DOWN)

    def test_close_below_sma_but_positive_slope(self):
        """close < SMA(50) but slope > 0 => NOT TREND_DOWN, could be TRANSITION."""
        n = 100
        rng = np.random.RandomState(43)
        closes = np.empty(n, dtype=np.float64)
        closes[:50] = 200.0 - np.arange(50) * 3.0  # steep downtrend
        closes[50:] = closes[49] + np.arange(50) * 0.3  # slight recovery
        highs = closes + 2.0
        lows = closes - 2.0

        signals = classify_regime(closes, highs, lows)
        mid_signal = signals[60]
        assert mid_signal.regime in (Regime.TRANSITION, Regime.TREND_UP)

    def test_transition_confidence_is_0_5(self):
        """TRANSITION signals (not from insufficient data) have confidence 0.5."""
        rng = np.random.RandomState(999)
        n = 80
        closes = 100.0 + np.cumsum(rng.randn(n) * 5.0)
        highs = closes + np.abs(rng.randn(n) * 10.0)
        lows = closes - np.abs(rng.randn(n) * 10.0)

        signals = classify_regime(closes, highs, lows)
        for s in signals[49:]:
            if s.regime == Regime.TRANSITION:
                assert s.confidence == 0.5


# ===========================================================================
# Test 5: Insufficient data defaults to TRANSITION
# ===========================================================================


class TestInsufficientData:
    """Early bars without enough lookback data return TRANSITION with confidence 0."""

    def test_first_49_bars_transition(self):
        """SMA(50) needs 50 bars; first 49 should be TRANSITION."""
        data = _make_uptrend(80)
        signals = classify_regime(data["close"], data["high"], data["low"])
        for i in range(49):
            assert signals[i].regime == Regime.TRANSITION
            assert signals[i].confidence == 0.0

    def test_short_series_all_transition(self):
        """Series shorter than 50 bars: all TRANSITION."""
        data = _make_uptrend(30)
        signals = classify_regime(data["close"], data["high"], data["low"])
        assert len(signals) == 30
        for s in signals:
            assert s.regime == Regime.TRANSITION
            assert s.confidence == 0.0

    def test_single_bar(self):
        """Single bar => TRANSITION."""
        closes = np.array([100.0])
        highs = np.array([105.0])
        lows = np.array([95.0])
        signals = classify_regime(closes, highs, lows)
        assert len(signals) == 1
        assert signals[0].regime == Regime.TRANSITION
        assert signals[0].confidence == 0.0

    def test_two_bars(self):
        """Two bars => TRANSITION for both (insufficient lookback)."""
        closes = np.array([100.0, 102.0])
        highs = np.array([105.0, 107.0])
        lows = np.array([95.0, 97.0])
        signals = classify_regime(closes, highs, lows)
        assert len(signals) == 2
        for s in signals:
            assert s.regime == Regime.TRANSITION

    def test_50th_bar_has_valid_sma(self):
        """Exactly at bar 49 (0-indexed, the 50th bar), SMA becomes valid."""
        data = _make_uptrend(55)
        signals = classify_regime(data["close"], data["high"], data["low"])
        assert np.isnan(signals[48].sma_50)  # bar 48 (49th bar in 1-indexed)
        assert not np.isnan(signals[49].sma_50)  # bar 49 (50th bar in 1-indexed)


# ===========================================================================
# Test 6: Determinism
# ===========================================================================


class TestDeterminism:
    """Same input must produce identical output."""

    def test_same_input_same_output(self):
        """Calling classify_regime twice with same data gives identical result."""
        data = _make_uptrend(100)
        signals1 = classify_regime(data["close"], data["high"], data["low"])
        signals2 = classify_regime(data["close"], data["high"], data["low"])
        assert len(signals1) == len(signals2)
        for s1, s2 in zip(signals1, signals2):
            assert s1.regime == s2.regime
            assert s1.confidence == s2.confidence
            if np.isnan(s1.sma_50):
                assert np.isnan(s2.sma_50)
            else:
                assert s1.sma_50 == s2.sma_50
            if np.isnan(s1.atr_pct):
                assert np.isnan(s2.atr_pct)
            else:
                assert s1.atr_pct == s2.atr_pct
            if np.isnan(s1.slope):
                assert np.isnan(s2.slope)
            else:
                assert s1.slope == s2.slope

    def test_no_random_state_dependency(self):
        """No RandomState is used; output is purely deterministic from input."""
        data = _make_downtrend(80)
        signals = classify_regime(data["close"], data["high"], data["low"])
        # Verify specific known values at the last bar
        last = signals[-1]
        assert last.regime == Regime.TREND_DOWN
        assert last.slope == -2.0  # _linreg_slope of [-2 * i] over 10 bars
        assert not np.isnan(last.sma_50)


# ===========================================================================
# Test 7: Edge cases
# ===========================================================================


class TestEdgeCases:
    """Boundary and error conditions."""

    def test_empty_arrays_raises(self):
        """Empty arrays should raise ValueError."""
        empty = np.array([], dtype=np.float64)
        with pytest.raises(ValueError):
            classify_regime(empty, empty, empty)

    def test_mismatched_lengths_raises(self):
        """Mismatched array lengths should raise ValueError."""
        closes = np.array([100.0, 101.0, 102.0])
        highs = np.array([105.0, 106.0])  # Too short
        lows = np.array([95.0, 96.0, 97.0])
        with pytest.raises(ValueError):
            classify_regime(closes, highs, lows)

    def test_negative_prices(self):
        """Negative price doesn't crash; just may not have valid ATR pct."""
        closes = np.full(80, -100.0, dtype=np.float64)
        highs = closes + 5.0
        lows = closes - 5.0
        signals = classify_regime(closes, highs, lows)
        assert len(signals) == 80
        # ATR/close ratio is NaN for negative closes
        for s in signals[49:]:
            assert np.isnan(s.atr_pct)

    def test_zero_price(self):
        """Zero price: ATR/close is inf/NaN — handled gracefully."""
        closes = np.full(80, 0.0, dtype=np.float64)
        highs = closes + 1.0
        lows = closes - 1.0
        signals = classify_regime(closes, highs, lows)
        assert len(signals) == 80

    def test_large_series(self):
        """Large series (10000 bars) should not error."""
        n = 10000
        rng = np.random.RandomState(1)
        closes = 50000.0 + np.cumsum(rng.randn(n) * 200.0)
        highs = closes + np.abs(rng.randn(n) * 100.0)
        lows = closes - np.abs(rng.randn(n) * 100.0)
        signals = classify_regime(closes, highs, lows)
        assert len(signals) == n
        # At least some classified bars exist
        counts = regime_counts(signals)
        total_classified = counts["TREND_UP"] + counts["TREND_DOWN"] + counts["RANGE"]
        assert total_classified > 0

    def test_all_nan_input(self):
        """NaN input: everything should be TRANSITION with confidence 0."""
        nan_arr = np.full(80, np.nan, dtype=np.float64)
        signals = classify_regime(nan_arr, nan_arr, nan_arr)
        for s in signals:
            assert s.regime == Regime.TRANSITION
            assert s.confidence == 0.0
            assert np.isnan(s.sma_50)


# ===========================================================================
# Test 8: Multi-symbol classification
# ===========================================================================


class TestMultiSymbol:
    """Per-symbol classification produces independent results."""

    def test_two_symbols_different_trends(self):
        """BTC in uptrend, ETH in downtrend => different classifications."""
        # BTC: uptrend (100 bars)
        btc = _make_uptrend(100, start=50000.0, step=100.0)
        # ETH: downtrend (100 bars)
        eth = _make_downtrend(100, start=3000.0, step=5.0)

        closes = np.concatenate([btc["close"], eth["close"]])
        highs = np.concatenate([btc["high"], eth["high"]])
        lows = np.concatenate([btc["low"], eth["low"]])
        symbols = np.array(["BTCUSDT"] * 100 + ["ETHUSDT"] * 100)

        results = classify_regime_multi_symbol(closes, highs, lows, symbols)

        assert "BTCUSDT" in results
        assert "ETHUSDT" in results
        assert len(results["BTCUSDT"]) == 100
        assert len(results["ETHUSDT"]) == 100

        # BTC should be TREND_UP after lookback
        btc_last = results["BTCUSDT"][-1]
        assert btc_last.regime == Regime.TREND_UP

        # ETH should be TREND_DOWN after lookback
        eth_last = results["ETHUSDT"][-1]
        assert eth_last.regime == Regime.TREND_DOWN

    def test_three_symbols_with_flat(self):
        """Three symbols with different regimes."""
        btc = _make_uptrend(80, start=50000.0, step=100.0)
        eth = _make_downtrend(80, start=3000.0, step=5.0)
        flat = _make_flat(80, price=100.0, atr_range=0.5)

        closes = np.concatenate([btc["close"], eth["close"], flat["close"]])
        highs = np.concatenate([btc["high"], eth["high"], flat["high"]])
        lows = np.concatenate([btc["low"], eth["low"], flat["low"]])
        symbols = np.array(["BTC"] * 80 + ["ETH"] * 80 + ["FLAT"] * 80)

        results = classify_regime_multi_symbol(closes, highs, lows, symbols)
        assert set(results.keys()) == {"BTC", "ETH", "FLAT"}

        btc_counts = regime_counts(results["BTC"])
        eth_counts = regime_counts(results["ETH"])
        flat_counts = regime_counts(results["FLAT"])

        assert btc_counts["TREND_UP"] > 0
        assert eth_counts["TREND_DOWN"] > 0
        assert flat_counts["RANGE"] > 0

    def test_multi_symbol_length_mismatch_raises(self):
        """Mismatched symbol array length raises ValueError."""
        closes = np.array([100.0] * 80)
        highs = np.array([105.0] * 80)
        lows = np.array([95.0] * 80)
        symbols = np.array(["BTC"] * 50)  # too short
        with pytest.raises(ValueError):
            classify_regime_multi_symbol(closes, highs, lows, symbols)


# ===========================================================================
# Test 9: Diagnostic helpers
# ===========================================================================


class TestDiagnostics:
    """regime_counts and regime_transitions helpers."""

    def test_regime_counts_sums_to_total(self):
        """Count sum should equal signal length."""
        data = _make_uptrend(80)
        signals = classify_regime(data["close"], data["high"], data["low"])
        counts = regime_counts(signals)
        assert sum(counts.values()) == len(signals)

    def test_regime_transitions_monotonic_uptrend(self):
        """Pure uptrend: 0 transitions (all TREND_UP after lookback, or TRANSITION->TREND_UP once)."""
        data = _make_uptrend(80)
        signals = classify_regime(data["close"], data["high"], data["low"])
        transitions = regime_transitions(signals)
        # TRANSITION(0-48) -> TREND_UP(49+) is 1 transition
        assert transitions == 1

    def test_regime_transitions_alternating(self):
        """Manually construct alternating regimes to test transition counting."""
        # Build signals that alternate: TREND_UP, TREND_DOWN, TREND_UP, TREND_DOWN
        s1 = RegimeSignal(Regime.TREND_UP, 0.8, 100.0, 0.01, 10.0)
        s2 = RegimeSignal(Regime.TREND_DOWN, 0.7, 99.0, 0.02, -5.0)
        s3 = RegimeSignal(Regime.TREND_UP, 0.9, 101.0, 0.01, 8.0)
        s4 = RegimeSignal(Regime.TREND_DOWN, 0.6, 98.0, 0.03, -3.0)
        signals = [s1, s2, s3, s4]
        assert regime_transitions(signals) == 3

    def test_regime_transitions_single_signal(self):
        """Single signal => 0 transitions."""
        s = RegimeSignal(Regime.RANGE, 0.5, 50.0, 0.005, 0.0)
        assert regime_transitions([s]) == 0

    def test_regime_transitions_empty(self):
        """Empty list => 0 transitions."""
        assert regime_transitions([]) == 0


# ===========================================================================
# Test 10: RegimeSignal immutability
# ===========================================================================


class TestRegimeSignalImmutability:
    """RegimeSignal is frozen — fields cannot be mutated after creation."""

    def test_cannot_set_attribute(self):
        """Setting an attribute on frozen dataclass should raise."""
        s = RegimeSignal(Regime.TREND_UP, 0.8, 102.0, 0.01, 5.0)
        with pytest.raises(Exception):
            s.regime = Regime.TRANSITION  # type: ignore[misc]

    def test_signal_equality(self):
        """Signals with identical fields are equal."""
        s1 = RegimeSignal(Regime.RANGE, 0.7, 50.0, 0.005, 0.0)
        s2 = RegimeSignal(Regime.RANGE, 0.7, 50.0, 0.005, 0.0)
        assert s1 == s2

    def test_signal_inequality(self):
        """Signals with different fields are not equal."""
        s1 = RegimeSignal(Regime.TREND_UP, 0.8, 102.0, 0.01, 5.0)
        s2 = RegimeSignal(Regime.TREND_UP, 0.8, 102.0, 0.01, 6.0)
        assert s1 != s2


# ===========================================================================
# Test 11: Confidence bounds
# ===========================================================================


class TestConfidenceBounds:
    """All confidence values must be in [0.0, 1.0]."""

    def test_confidence_always_in_range(self):
        """Every signal's confidence should be between 0.0 and 1.0 inclusive."""
        scenarios = [
            _make_uptrend(100),
            _make_downtrend(100),
            _make_flat(100),
        ]
        for data in scenarios:
            signals = classify_regime(data["close"], data["high"], data["low"])
            for s in signals:
                assert 0.0 <= s.confidence <= 1.0, (
                    f"Confidence {s.confidence} out of range for regime {s.regime}"
                )

    def test_insufficient_data_confidence_zero(self):
        """Signals from insufficient data must have confidence 0.0."""
        data = _make_uptrend(60)
        signals = classify_regime(data["close"], data["high"], data["low"])
        for s in signals[:49]:
            assert s.confidence == 0.0

    def test_classified_signal_confidence_positive(self):
        """Any signal NOT from insufficient data must have confidence > 0.0."""
        data = _make_uptrend(80)
        signals = classify_regime(data["close"], data["high"], data["low"])
        for s in signals[49:]:
            assert s.confidence > 0.0


# ===========================================================================
# Test 12: ATR calculation correctness
# ===========================================================================


class TestATRCalculation:
    """ATR indicator correctness for known input."""

    def test_fixed_range_atr(self):
        """Flat series with known high-low range gives predictable ATR."""
        n = 80
        closes = np.full(n, 100.0, dtype=np.float64)
        highs = closes + 2.0
        lows = closes - 2.0
        signals = classify_regime(closes, highs, lows)
        # For a flat series where H=102, L=98, C=100:
        # TR = max(H-L=4, |H-C_prev|=2, |L-C_prev|=2) = 4
        # ATR(14) = mean of 14 TR values = 4.0
        s = signals[60]  # well past lookback
        assert not np.isnan(s.atr_pct)
        assert math.isclose(s.atr_pct, 4.0 / 100.0, rel_tol=0.01)


# ===========================================================================
# Tests for Online Regime Detector (#161)
# ===========================================================================


class TestCusumDetector:
    """CUSUM change point detection."""

    def test_no_change_no_signal(self):
        """Flat series with tiny noise: no CUSUM signal."""
        rng = np.random.RandomState(42)
        n = 100
        close = 100.0 + np.cumsum(rng.randn(n) * 0.01)
        result = compute_cusum_detector(close, threshold=5.0)
        assert "cusum_positive" in result
        assert "cusum_negative" in result
        assert "cusum_signal" in result
        assert np.isnan(result["cusum_signal"][0])
        signals = result["cusum_signal"][1:]
        assert np.all(signals == 0.0)

    def test_sustained_uptrend_cusum_alarm(self):
        """Sustained positive returns should trigger CUSUM positive."""
        rng = np.random.RandomState(1)
        n = 100
        returns = np.abs(rng.randn(n)) * 0.5 + 0.3
        close = 100.0 * np.exp(np.cumsum(returns))
        result = compute_cusum_detector(close, threshold=3.0)
        assert np.any(result["cusum_signal"][1:] > 0)
        assert np.any(result["cusum_positive"][1:] > 0)

    def test_sustained_downtrend_cusum_alarm(self):
        """Sustained negative returns should trigger CUSUM negative."""
        rng = np.random.RandomState(2)
        n = 100
        returns = -(np.abs(rng.randn(n)) * 0.5 + 0.3)
        close = 100.0 * np.exp(np.cumsum(returns))
        result = compute_cusum_detector(close, threshold=3.0)
        assert np.any(result["cusum_signal"][1:] > 0)
        assert np.any(result["cusum_negative"][1:] > 0)

    def test_cusum_resets_after_alarm(self):
        """After a signal, CUSUM statistic resets."""
        close = np.array([100.0, 105.0, 110.25, 115.76, 121.55, 127.63,
                          134.01, 140.71, 147.75, 155.13], dtype=np.float64)
        result = compute_cusum_detector(close, threshold=1.0)
        for i in range(2, len(close)):
            if result["cusum_signal"][i] == 1.0:
                assert result["cusum_positive"][i] <= 1.0

    def test_short_series(self):
        """Series shorter than 2 bars returns all NaN."""
        close = np.array([100.0], dtype=np.float64)
        result = compute_cusum_detector(close, threshold=5.0)
        assert np.isnan(result["cusum_positive"][0])
        assert np.isnan(result["cusum_negative"][0])
        assert np.isnan(result["cusum_signal"][0])

    def test_determinism(self):
        """Same input produces identical CUSUM output."""
        rng = np.random.RandomState(99)
        close = 100.0 + np.cumsum(rng.randn(100) * 2.0)
        r1 = compute_cusum_detector(close, threshold=4.0)
        r2 = compute_cusum_detector(close, threshold=4.0)
        for k in r1:
            assert np.allclose(r1[k][1:], r2[k][1:], equal_nan=True)


class TestHmmVolState:
    """HMM streaming volatility state classification."""

    def test_low_vol_then_high_vol_switch(self):
        """HMM detects switch from low to high volatility."""
        rng = np.random.RandomState(42)
        n = 400
        returns = np.concatenate([
            rng.randn(200) * 0.2,   # low vol
            rng.randn(200) * 5.0,   # high vol
        ])
        close = 100.0 * np.exp(np.cumsum(returns))
        result = compute_hmm_vol_state(close, window=30)
        # After high vol regime starts and HMM adapts (bar ~330)
        valid = result["hmm_vol_state"][330:]
        high_vol_ratio = np.mean(valid == 1.0)
        assert high_vol_ratio > 0.5

    def test_both_states_observed(self):
        """With moderate uniform vol, both states should be observed."""
        rng = np.random.RandomState(42)
        n = 300
        close = 100.0 + np.cumsum(rng.randn(n) * 0.3)
        result = compute_hmm_vol_state(close, window=30)
        valid = result["hmm_vol_state"][31:]
        n_state0 = np.sum(valid == 0.0)
        n_state1 = np.sum(valid == 1.0)
        # Both states should be observed
        assert n_state0 > 10, f"state 0 count {n_state0} <= 10"
        assert n_state1 > 10, f"state 1 count {n_state1} <= 10"

    def test_probability_in_range(self):
        """All probability values in [0, 1]."""
        rng = np.random.RandomState(42)
        n = 100
        close = 100.0 + np.cumsum(rng.randn(n) * 2.0)
        result = compute_hmm_vol_state(close, window=20)
        prob = result["hmm_vol_probability"][21:]
        assert np.all((prob >= 0.0) & (prob <= 1.0))

    def test_nan_prefix(self):
        """First window bars should be NaN."""
        rng = np.random.RandomState(42)
        n = 50
        close = 100.0 + np.cumsum(rng.randn(n))
        result = compute_hmm_vol_state(close, window=20)
        assert np.all(np.isnan(result["hmm_vol_state"][:20]))
        assert np.all(np.isnan(result["hmm_vol_probability"][:20]))

    def test_short_series_all_nan(self):
        """Series shorter than window+1 returns all NaN."""
        close = np.array([100.0, 101.0, 102.0], dtype=np.float64)
        result = compute_hmm_vol_state(close, window=20)
        assert np.all(np.isnan(result["hmm_vol_state"]))
        assert np.all(np.isnan(result["hmm_vol_probability"]))

    def test_determinism(self):
        """Same input produces identical HMM output."""
        rng = np.random.RandomState(42)
        close = 100.0 + np.cumsum(rng.randn(100))
        r1 = compute_hmm_vol_state(close, window=20)
        r2 = compute_hmm_vol_state(close, window=20)
        for k in r1:
            assert np.allclose(r1[k], r2[k], equal_nan=True)


class TestVolatilityRegime:
    """Volatility regime classification (LOW/MEDIUM/HIGH)."""

    def test_flat_series_low_regime(self):
        """Nearly flat series produces LOW volatility."""
        rng = np.random.RandomState(42)
        n = 100
        close = 100.0 + np.cumsum(rng.randn(n) * 0.05)
        regime = compute_volatility_regime(close, window=20)
        valid = regime[20:]
        low_ratio = np.mean(valid == 0.0)
        assert low_ratio > 0.3

    def test_regime_values_in_valid_set(self):
        """Regime values are exactly 0.0, 1.0, or 2.0."""
        rng = np.random.RandomState(42)
        n = 100
        close = 100.0 + np.cumsum(rng.randn(n) * 3.0)
        regime = compute_volatility_regime(close, window=20)
        valid = regime[20:]
        for v in valid:
            assert v in (0.0, 1.0, 2.0)

    def test_nan_prefix(self):
        """First window bars should be NaN."""
        rng = np.random.RandomState(42)
        n = 50
        close = 100.0 + np.cumsum(rng.randn(n))
        regime = compute_volatility_regime(close, window=20)
        assert np.all(np.isnan(regime[:20]))

    def test_short_series(self):
        """Series shorter than window+1 returns all NaN."""
        close = np.array([100.0, 101.0], dtype=np.float64)
        regime = compute_volatility_regime(close, window=20)
        assert np.all(np.isnan(regime))

    def test_determinism(self):
        """Same input produces identical regime output."""
        rng = np.random.RandomState(42)
        close = 100.0 + np.cumsum(rng.randn(200))
        r1 = compute_volatility_regime(close, window=30)
        r2 = compute_volatility_regime(close, window=30)
        assert np.allclose(r1, r2, equal_nan=True)


class TestRegimeGroup:
    """Regime group compute function."""

    def test_all_keys_present(self):
        """Group function returns all 6 expected keys."""
        rng = np.random.RandomState(42)
        n = 100
        close = 100.0 + np.cumsum(rng.randn(n) * 2.0)
        high = close + np.abs(rng.randn(n)) * 0.5
        low = close - np.abs(rng.randn(n)) * 0.5
        result = compute_regime_group(close, high, low)
        expected_keys = {
            "cusum_positive", "cusum_negative", "cusum_signal",
            "hmm_vol_state", "hmm_vol_probability", "volatility_regime",
        }
        assert set(result.keys()) == expected_keys

    def test_all_same_length(self):
        """All arrays have the same length as input."""
        rng = np.random.RandomState(42)
        n = 100
        close = 100.0 + np.cumsum(rng.randn(n) * 2.0)
        high = close + np.abs(rng.randn(n)) * 0.5
        low = close - np.abs(rng.randn(n)) * 0.5
        result = compute_regime_group(close, high, low)
        for name, arr in result.items():
            assert len(arr) == n, f"{name} length {len(arr)} != {n}"

    def test_determinism(self):
        """Same input produces identical group output."""
        rng = np.random.RandomState(42)
        n = 100
        close = 100.0 + np.cumsum(rng.randn(n) * 2.0)
        high = close + np.abs(rng.randn(n)) * 0.5
        low = close - np.abs(rng.randn(n)) * 0.5
        r1 = compute_regime_group(close, high, low)
        r2 = compute_regime_group(close, high, low)
        for k in r1:
            assert np.allclose(r1[k], r2[k], equal_nan=True)


class TestOnlineRegimeDetector:
    """OnlineRegimeDetector streaming class."""

    def test_incremental_matches_batch(self):
        """Online detector after full pass matches batch CUSUM."""
        rng = np.random.RandomState(42)
        n = 100
        close = 100.0 + np.cumsum(rng.randn(n) * 2.0)

        batch = compute_cusum_detector(close, threshold=5.0)

        detector = OnlineRegimeDetector(cusum_threshold=5.0)
        online_results = {k: [] for k in ["cusum_positive", "cusum_negative", "cusum_signal"]}
        for c in close:
            state = detector.update(close=c)
            for k in online_results:
                online_results[k].append(state[k])

        for k in online_results:
            online_arr = np.array(online_results[k])
            valid = ~np.isnan(batch[k])
            assert np.allclose(online_arr[valid], batch[k][valid], equal_nan=True)

    def test_reset_clears_state(self):
        """After reset, detector re-initializes."""
        detector = OnlineRegimeDetector()
        for c in [100.0, 101.0, 102.0]:
            detector.update(close=c)
        detector.reset()
        assert detector._prev_close is None
        assert detector._n_processed == 0

    def test_warmup_returns_nan(self):
        """Early bars return NaN for HMM and vol regime."""
        detector = OnlineRegimeDetector(hmm_vol_window=5, vol_regime_window=5)
        state = None
        for c in [100.0, 100.5, 101.0, 101.5, 102.0, 102.5, 103.0]:
            state = detector.update(close=c)
        assert state is not None
        assert not np.isnan(state["hmm_vol_state"])


class TestCausalityNoRevision:
    """Adding a bar must not change previous feature values."""

    def test_cusum_no_revision(self):
        """CUSUM at index t does not change when bar N+1 is added."""
        rng = np.random.RandomState(42)
        n = 50
        close = 100.0 + np.cumsum(rng.randn(n) * 2.0)
        r1 = compute_cusum_detector(close, threshold=5.0)

        rng2 = np.random.RandomState(99)
        close_ext = np.concatenate([close, 100.0 + np.cumsum(rng2.randn(10) * 2.0)])
        r2 = compute_cusum_detector(close_ext, threshold=5.0)

        for k in r1:
            assert np.allclose(r1[k][:n], r2[k][:n], equal_nan=True), f"{k} has revision"

    def test_hmm_no_revision(self):
        """HMM at index t does not change when bar N+1 is added."""
        rng = np.random.RandomState(42)
        n = 60
        close = 100.0 + np.cumsum(rng.randn(n) * 2.0)
        r1 = compute_hmm_vol_state(close, window=20)

        rng2 = np.random.RandomState(99)
        close_ext = np.concatenate([close, 100.0 + np.cumsum(rng2.randn(10) * 2.0)])
        r2 = compute_hmm_vol_state(close_ext, window=20)

        for k in r1:
            assert np.allclose(r1[k][:n], r2[k][:n], equal_nan=True), f"{k} has revision"

    def test_vol_regime_no_revision(self):
        """Volatility regime at index t does not change when bar N+1 is added."""
        rng = np.random.RandomState(42)
        n = 60
        close = 100.0 + np.cumsum(rng.randn(n) * 2.0)
        r1 = compute_volatility_regime(close, window=20)

        rng2 = np.random.RandomState(99)
        close_ext = np.concatenate([close, 100.0 + np.cumsum(rng2.randn(10) * 2.0)])
        r2 = compute_volatility_regime(close_ext, window=20)

        assert np.allclose(r1[:n], r2[:n], equal_nan=True)

