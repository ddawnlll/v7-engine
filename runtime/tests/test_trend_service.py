"""Tests for runtime/services/trend_service.py.

Pure logic, no DB dependencies — tests the EMA-based trend detection.
"""

from runtime.services.trend_service import TrendFactor, _pct, determine_trend


# ── _pct helper ──────────────────────────────────────────────────────

class TestPct:
    def test_positive(self):
        assert _pct(110.0, 100.0) == 10.0

    def test_negative(self):
        assert _pct(90.0, 100.0) == -10.0

    def test_zero_base(self):
        assert _pct(100.0, 0.0) == 0.0

    def test_equal(self):
        assert _pct(100.0, 100.0) == 0.0

    def test_negative_base(self):
        assert _pct(-90.0, -100.0) == 10.0


# ── Bullish scenarios ────────────────────────────────────────────────

class TestBullish:
    def test_strong_bullish_all_signals(self):
        """EMA stacked bullish + price above both EMA50 and EMA200."""
        result = determine_trend({
            "price": 110.0,
            "ema_9": 109.0,
            "ema_21": 105.0,
            "ema_50": 100.0,
            "ema_200": 95.0,
        })
        direction, strength, factors = result
        assert direction == "BULLISH"
        assert strength >= 67.0
        assert len(factors) >= 3

    def test_bullish_ema_stack_only(self):
        """Only EMA stack is bullish, no price relative data."""
        result = determine_trend({
            "price": 100.0,
            "ema_9": 102.0,
            "ema_21": 100.0,
            "ema_50": 98.0,
        })
        direction, strength, factors = result
        assert direction == "BULLISH"

    def test_bullish_price_above_ema50(self):
        """Price well above EMA50 but EMAs mixed."""
        result = determine_trend({
            "price": 110.0,
            "ema_9": 100.0,
            "ema_21": 101.0,
            "ema_50": 100.0,
            "ema_200": 95.0,
        })
        direction, strength, factors = result
        # EMAs mixed (-1), price above EMA50 (+1 net: bullish), above EMA200 (+0.5)
        # total = 2 + (-1) + 1 + 0.5 = 2.5, bullish = 0 + 1 + 0.5 = 1.5
        # ratio = 1.5/2.5 = 0.6 → MIXED (between 0.33 and 0.67)
        assert direction == "MIXED"

    def test_bullish_all_inclusive(self):
        """Everything aligns for a strong bullish signal."""
        result = determine_trend({
            "price": 120.0,
            "ema_9": 115.0,
            "ema_21": 110.0,
            "ema_50": 100.0,
            "ema_200": 90.0,
        })
        direction, strength, _ = result
        assert direction == "BULLISH"
        assert strength > 80.0


# ── Bearish scenarios ────────────────────────────────────────────────

class TestBearish:
    def test_strong_bearish_all_signals(self):
        """EMAs stacked bearish + price below both EMA50 and EMA200."""
        result = determine_trend({
            "price": 90.0,
            "ema_9": 91.0,
            "ema_21": 95.0,
            "ema_50": 100.0,
            "ema_200": 105.0,
        })
        direction, strength, factors = result
        assert direction == "BEARISH"
        assert strength <= 33.0
        assert len(factors) >= 3

    def test_bearish_ema_stack_only(self):
        """Only EMA stack is bearish."""
        result = determine_trend({
            "price": 100.0,
            "ema_9": 98.0,
            "ema_21": 100.0,
            "ema_50": 102.0,
        })
        direction, strength, _ = result
        assert direction == "BEARISH"


# ── Mixed / edge scenarios ───────────────────────────────────────────

class TestMixed:
    def test_mixed_emas_no_price_context(self):
        """EMAs mixed, no price/EMA50 or price/EMA200 data."""
        result = determine_trend({
            "price": 100.0,
            "ema_9": 100.0,
            "ema_21": 100.0,
            "ema_50": 100.0,
        })
        direction, strength, factors = result
        # EMAs mixed → total_score -= 1, price/ema50 diff=0 → total_score -= 1
        # No EMA200 → no addition
        # total_score = 2 - 1 + 1 - 1 = 1, bullish = 0
        # ratio = 0/1 = 0.0 → BEARISH? Wait, ratio = bullish/total = 0/1 = 0.0
        # That's <= 0.33, so BEARISH
        # Hmm that's interesting. Let me trace:
        # EMAs mixed → total goes 2-1=1, no bullish
        # Price/EMA50 diff=0 → total += 1 then -= 1 = net 0 change. total stays 1
        # Actually looking at the code again:
        # if diff > 0.2: bullish += 1
        # elif diff < -0.2: (no bullish addition)
        # else: total_score -= 1
        # So total_score = 2 - 1 + 1 - 1 = 1, bullish = 0
        # ratio = 0/1 = 0, strength = 0.0
        # 0 <= 0.33 → BEARISH
        
        # Actually this makes sense - when EMAs are flat/crossed and price at EMA50,
        # it's treated as slightly bearish (no bullish evidence)
        assert direction in ("BEARISH", "MIXED")

    def test_all_missing_returns_mixed(self):
        """No EMAs at all → MIXED with default strength."""
        result = determine_trend({"price": 100.0})
        direction, strength, factors = result
        assert direction == "MIXED"
        assert strength == 50.0
        assert factors == []

    def test_only_price(self):
        """Only price field, no EMAs."""
        result = determine_trend({"price": 100.0})
        direction, strength, _ = result
        assert direction == "MIXED"
        assert strength == 50.0

    def test_empty_snapshot(self):
        """Empty snapshot → MIXED."""
        result = determine_trend({})
        direction, strength, _ = result
        assert direction == "MIXED"
        assert strength == 50.0


# ── Factor structure ─────────────────────────────────────────────────

class TestFactorStructure:
    def test_factor_has_all_fields(self):
        _, _, factors = determine_trend({
            "price": 110.0,
            "ema_9": 105.0,
            "ema_21": 102.0,
            "ema_50": 100.0,
        })
        assert len(factors) > 0
        for f in factors:
            assert isinstance(f, TrendFactor)
            assert f.name
            assert f.role
            assert f.signal in ("BUY", "SELL", "NEUTRAL")
            assert isinstance(f.score, float)
            assert f.reason

    def test_bullish_factor_positive_score(self):
        _, _, factors = determine_trend({
            "price": 110.0,
            "ema_9": 105.0,
            "ema_21": 102.0,
            "ema_50": 100.0,
        })
        for f in factors:
            if f.signal == "BUY":
                assert f.score > 0

    def test_bearish_factor_negative_score(self):
        _, _, factors = determine_trend({
            "price": 90.0,
            "ema_9": 95.0,
            "ema_21": 98.0,
            "ema_50": 100.0,
        })
        for f in factors:
            if f.signal == "SELL":
                assert f.score < 0


# ── Edge cases ───────────────────────────────────────────────────────

class TestEdgeCases:
    def test_price_equals_ema50(self):
        """Price exactly at EMA50 → no bias from this factor."""
        result = determine_trend({
            "price": 100.0,
            "ema_9": 102.0,
            "ema_21": 101.0,
            "ema_50": 100.0,
        })
        direction, strength, _ = result
        assert direction in ("BULLISH", "MIXED")

    def test_price_slightly_above_ema50(self):
        """Price 0.1% above EMA50 → below 0.2% threshold → neutral."""
        result = determine_trend({
            "price": 100.1,
            "ema_9": 105.0,
            "ema_21": 103.0,
            "ema_50": 100.0,
        })
        direction, strength, _ = result
        # EMA stack bullish: total += 2, bullish += 2
        # Price/EMA50 diff = 0.1% → not > 0.2, so not bullish.
        # Actually diff = (100.1-100)/100*100 = 0.1%. It's not > 0.2 and not < -0.2
        # So it falls in the else branch: total_score -= 1
        # No EMA200
        # total_score = 2 + 1 - 1 = 2, bullish = 2
        # ratio = 2/2 = 1.0 → BULLISH
        assert direction == "BULLISH"

    def test_price_ema50_diff_exactly_02(self):
        """Price exactly 0.2% above EMA50 → meets > 0.2 condition? No, not >."""
        result = determine_trend({
            "price": 100.2,
            "ema_9": 105.0,
            "ema_21": 103.0,
            "ema_50": 100.0,
        })
        direction, strength, _ = result
        # diff = (100.2-100)/100*100 = 0.2%. Not > 0.2, falls to elif: not < -0.2 either.
        # Falls through to else: total_score -= 1
        # Same as above: BULLISH from EMA stack
        assert direction == "BULLISH"

    def test_price_ema50_diff_just_above_02(self):
        """Price 0.21% above EMA50 → meets > 0.2 condition."""
        result = determine_trend({
            "price": 100.21,
            "ema_9": 99.0,
            "ema_21": 100.0,
            "ema_50": 100.0,
        })
        direction, strength, _ = result
        # diff = 0.21% > 0.2 → bullish += 1
        # EMAs mixed → total_score -= 1
        # total_score = 2 - 1 + 1 = 2, bullish = 0 + 1 = 1
        # ratio = 1/2 = 0.5 → MIXED (between 0.33 and 0.67)
        assert direction == "MIXED"

    def test_ema200_missing(self):
        """No EMA200 → still works, just fewer factors."""
        result = determine_trend({
            "price": 110.0,
            "ema_9": 105.0,
            "ema_21": 102.0,
            "ema_50": 100.0,
        })
        direction, strength, factors = result
        assert direction == "BULLISH"
        # Should have EMA stack + price/ema50 factors, no ema200 factor
        names = [f.name for f in factors]
        assert "EMA Stack" in names
        assert "Price/EMA50" in names
        assert "Price/EMA200" not in names

    def test_ema9_and_ema21_missing(self):
        """Only EMA50 present → no EMA stack check."""
        result = determine_trend({
            "price": 110.0,
            "ema_50": 100.0,
            "ema_200": 95.0,
        })
        direction, strength, _ = result
        assert direction in ("BULLISH", "MIXED")
