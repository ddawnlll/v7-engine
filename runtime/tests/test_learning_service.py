"""Tests for runtime/services/learning_service.py.

Pure helpers: _clamp, _blend_multiplier_toward_neutral,
_confidence_bucket_bounds, _confidence_bucket_label, _entry_timing_risk.
"""

from runtime.services.learning_service import (
    LearningService,
    _blend_multiplier_toward_neutral,
    _clamp,
    _confidence_bucket_bounds,
    _confidence_bucket_label,
)


# ── _clamp ──────────────────────────────────────────────────────────

class TestClamp:
    def test_within_range(self):
        assert _clamp(5.0, 0.0, 10.0) == 5.0

    def test_below_min(self):
        assert _clamp(-1.0, 0.0, 10.0) == 0.0

    def test_above_max(self):
        assert _clamp(15.0, 0.0, 10.0) == 10.0

    def test_at_boundaries(self):
        assert _clamp(0.0, 0.0, 10.0) == 0.0
        assert _clamp(10.0, 0.0, 10.0) == 10.0

    def test_int_input(self):
        assert _clamp(5, 0, 10) == 5.0


# ── _blend_multiplier_toward_neutral ────────────────────────────────

class TestBlendMultiplier:
    def test_full_damping_returns_1(self):
        assert _blend_multiplier_toward_neutral(1.5, 1.0) == 1.5
        assert _blend_multiplier_toward_neutral(0.5, 1.0) == 0.5

    def test_zero_damping_returns_1(self):
        assert _blend_multiplier_toward_neutral(1.5, 0.0) == 1.0
        assert _blend_multiplier_toward_neutral(0.5, 0.0) == 1.0

    def test_partial_damping(self):
        # 1.0 + ((1.5 - 1.0) * 0.5) = 1.0 + 0.25 = 1.25
        assert _blend_multiplier_toward_neutral(1.5, 0.5) == 1.25

    def test_clamps_damping(self):
        assert _blend_multiplier_toward_neutral(1.5, 2.0) == 1.5  # clamped to 1.0
        assert _blend_multiplier_toward_neutral(1.5, -0.5) == 1.0  # clamped to 0.0

    def test_below_one_blend(self):
        # 1.0 + ((0.75 - 1.0) * 0.6) = 1.0 - 0.15 = 0.85
        assert _blend_multiplier_toward_neutral(0.75, 0.6) == 0.85


# ── _confidence_bucket_bounds / _confidence_bucket_label ───────────

class TestConfidenceBucket:
    def test_50_59(self):
        lower, upper = _confidence_bucket_bounds(55.0)
        assert lower == 50.0
        assert upper == 60.0
        assert _confidence_bucket_label(55.0) == "50-60"

    def test_60_69(self):
        lower, upper = _confidence_bucket_bounds(63.0)
        assert lower == 60.0
        assert upper == 70.0

    def test_70_79(self):
        assert _confidence_bucket_label(75.0) == "70-80"

    def test_80_89(self):
        assert _confidence_bucket_label(85.0) == "80-90"

    def test_90_100(self):
        assert _confidence_bucket_label(95.0) == "90-100"

    def test_below_50_floors_to_50(self):
        assert _confidence_bucket_label(30.0) == "50-60"

    def test_above_90_ceil_to_100(self):
        lower, upper = _confidence_bucket_bounds(99.0)
        assert lower == 90.0
        assert upper == 100.0
        assert _confidence_bucket_label(99.0) == "90-100"

    def test_exact_boundaries(self):
        assert _confidence_bucket_label(50.0) == "50-60"
        assert _confidence_bucket_label(60.0) == "60-70"
        assert _confidence_bucket_label(90.0) == "90-100"


# ── _entry_timing_risk ─────────────────────────────────────────────

class TestEntryTimingRisk:
    def test_no_risk_factors(self):
        score, reasons, flags = LearningService._entry_timing_risk(
            snap={"price": 100.0, "ema_21": 100.0, "vwap": 100.0, "rsi": 50.0},
            direction="BUY",
        )
        assert score == 0.0
        assert reasons == []
        assert all(v is False for v in flags.values())

    def test_ema_extension(self):
        score, reasons, flags = LearningService._entry_timing_risk(
            snap={"price": 102.0, "ema_21": 100.0},
            direction="BUY",
        )
        assert flags["ema_extension"] is True
        assert score >= 0.28

    def test_vwap_stretch(self):
        score, reasons, flags = LearningService._entry_timing_risk(
            snap={"price": 101.0, "vwap": 100.0},
            direction="BUY",
        )
        assert flags["vwap_stretch"] is True
        assert score >= 0.12

    def test_breakout_no_retest_long(self):
        score, reasons, flags = LearningService._entry_timing_risk(
            snap={"price": 100.0, "breakout_up": True, "retest_support": False},
            direction="BUY",
        )
        assert flags["no_retest_breakout"] is True
        assert score >= 0.28

    def test_breakout_no_retest_short(self):
        score, reasons, flags = LearningService._entry_timing_risk(
            snap={"price": 100.0, "breakout_down": True, "retest_resist": False},
            direction="SELL",
        )
        assert flags["no_retest_breakout"] is True
        assert score >= 0.28

    def test_rsi_stretch_long(self):
        score, reasons, flags = LearningService._entry_timing_risk(
            snap={"price": 100.0, "rsi": 70.0},
            direction="BUY",
        )
        assert flags["rsi_stretch"] is True
        assert score >= 0.1

    def test_rsi_stretch_short(self):
        score, reasons, flags = LearningService._entry_timing_risk(
            snap={"price": 100.0, "rsi": 30.0},
            direction="SELL",
        )
        assert flags["rsi_stretch"] is True
        assert score >= 0.1

    def test_opposing_flow_long(self):
        score, reasons, flags = LearningService._entry_timing_risk(
            snap={"price": 100.0, "flow_imbalance": -0.1},
            direction="BUY",
        )
        assert flags["opposing_flow"] is True
        assert score >= 0.16

    def test_opposing_flow_short(self):
        score, reasons, flags = LearningService._entry_timing_risk(
            snap={"price": 100.0, "orderbook_imbalance": 0.1},
            direction="SELL",
        )
        assert flags["opposing_flow"] is True
        assert score >= 0.16

    def test_impulse_extension(self):
        score, reasons, flags = LearningService._entry_timing_risk(
            snap={"price": 100.0, "_price_5bar_change": 1.5},
            direction="BUY",
        )
        assert flags["impulse_extension"] is True
        assert score >= 0.12

    def test_all_risks_combined(self):
        score, reasons, flags = LearningService._entry_timing_risk(
            snap={
                "price": 105.0,
                "ema_21": 100.0,
                "vwap": 100.0,
                "rsi": 70.0,
                "breakout_up": True,
                "retest_support": False,
                "flow_imbalance": -0.1,
                "_price_5bar_change": 1.5,
            },
            direction="BUY",
        )
        assert score > 0.5
        assert len(reasons) >= 4
        assert flags["ema_extension"]
        assert flags["rsi_stretch"]

    def test_scores_clamped_to_1(self):
        score, reasons, flags = LearningService._entry_timing_risk(
            snap={
                "price": 200.0,
                "ema_21": 100.0,
                "vwap": 100.0,
                "rsi": 99.0,
                "breakout_up": True,
                "retest_support": False,
                "flow_imbalance": -1.0,
                "orderbook_imbalance": -1.0,
                "_price_5bar_change": 999.0,
            },
            direction="BUY",
        )
        assert score <= 1.0
