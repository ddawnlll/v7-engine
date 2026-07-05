"""Tests for runtime/services/trade_analytics_service.py.

Pure statics: _volatility_bucket, _profit_factor, _max_drawdown_r,
_classify_time_stop_cause, _simple_group_count, _simple_group_avg,
_avg_realized_r, _threshold_pass_frequency, _factor_score_averages,
_adjustment_presence, _circuit_impact, _prior_window, _current_window.

Instance methods: _group_metrics, _rate_group,
get_confidence_bucket_breakdown_from_rows, get_exit_quality_breakdown_from_rows.
"""

import math
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

from runtime.services.trade_analytics_service import TradeAnalyticsService
from runtime.services.universe_filter_service import UniverseFilterService


def svc() -> TradeAnalyticsService:
    return TradeAnalyticsService(
        universe_filter_service=MagicMock(spec=UniverseFilterService)
    )


def _row(realized_r: float = 0.0, **kwargs) -> dict[str, Any]:
    base = {
        "realized_r": realized_r,
        "closed_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "SWING",
        "interval": "4h",
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "session_label": "LONDON",
        "hold_minutes": 240.0,
        "stop_hit": False,
        "target_hit": False,
        "time_exit": False,
        "stale_exit": False,
        "confidence": 50.0,
        "confidence_before_learning": 50.0,
        "confidence_after_learning": 50.0,
    }
    base.update(kwargs)
    return base


# ── _volatility_bucket ─────────────────────────────────────────────

class TestVolatilityBucket:
    def test_explicit_regime(self):
        assert TradeAnalyticsService._volatility_bucket(
            {"volatility_regime": "EXTREME"}, {}
        ) == "EXTREME"

    def test_high_vol(self):
        assert TradeAnalyticsService._volatility_bucket(
            {"vol_ratio": 2.0}, {}
        ) == "HIGH_VOL"

    def test_normal_vol(self):
        assert TradeAnalyticsService._volatility_bucket(
            {"vol_ratio": 1.2}, {}
        ) == "NORMAL_VOL"

    def test_low_vol(self):
        assert TradeAnalyticsService._volatility_bucket(
            {"vol_ratio": 0.5}, {}
        ) == "LOW_VOL"

    def test_unknown(self):
        assert TradeAnalyticsService._volatility_bucket({}, {}) == "UNKNOWN"

    def test_fallback_to_audit_snapshot(self):
        assert TradeAnalyticsService._volatility_bucket(
            {}, {"raw_snapshot": {"vol_ratio": 1.8}}
        ) == "HIGH_VOL"


# ── _profit_factor ─────────────────────────────────────────────────

class TestProfitFactor:
    def test_all_wins(self):
        rows = [_row(1.0), _row(2.0)]
        assert TradeAnalyticsService._profit_factor(rows) == 3.0

    def test_all_losses(self):
        rows = [_row(-1.0), _row(-2.0)]
        assert TradeAnalyticsService._profit_factor(rows) == 0.0

    def test_mixed(self):
        rows = [_row(2.0), _row(-0.5)]
        assert TradeAnalyticsService._profit_factor(rows) == 2.0 / 0.5  # 4.0

    def test_empty(self):
        assert TradeAnalyticsService._profit_factor([]) == 0.0

    def test_zero_net(self):
        rows = [_row(1.0), _row(-1.0)]
        assert TradeAnalyticsService._profit_factor(rows) == 1.0


# ── _max_drawdown_r ────────────────────────────────────────────────

class TestMaxDrawdown:
    def test_uptrend(self):
        rows = [_row(1.0), _row(2.0), _row(1.0)]
        # equity: 1→3→4, peak=4, drawdown=0
        assert TradeAnalyticsService._max_drawdown_r(rows) == 0.0

    def test_downtrend(self):
        rows = [_row(-1.0), _row(-2.0), _row(-1.0)]
        # equity: -1→-3→-4, peak=0, drawdown=4
        assert TradeAnalyticsService._max_drawdown_r(rows) == 4.0

    def test_peak_then_valley(self):
        rows = [_row(3.0), _row(-1.0), _row(-2.0)]
        # equity: 3→2→0, peak=3, drawdown=3
        assert TradeAnalyticsService._max_drawdown_r(rows) == 3.0

    def test_sorts_by_date(self):
        rows = [
            _row(-2.0, closed_at_utc="2026-06-03T12:00:00Z"),
            _row(3.0, closed_at_utc="2026-06-01T12:00:00Z"),
            _row(-1.0, closed_at_utc="2026-06-02T12:00:00Z"),
        ]
        # sorted: 3→-1→-2, equity: 3→2→0, peak=3, drawdown=3
        assert TradeAnalyticsService._max_drawdown_r(rows) == 3.0

    def test_empty(self):
        assert TradeAnalyticsService._max_drawdown_r([]) == 0.0


# ── _classify_time_stop_cause ──────────────────────────────────────

class TestClassifyTimeStopCause:
    def test_never_developed_premature(self):
        row = _row(0.1, interval_minutes=240, hold_minutes=30)
        assert TradeAnalyticsService._classify_time_stop_cause(row) == "never_developed"
        assert row.get("time_stop_quality") == "premature"

    def test_late_reversal(self):
        row = _row(-0.5, hold_minutes=500, interval_minutes=240)
        assert TradeAnalyticsService._classify_time_stop_cause(row) == "late_reversal"
        assert row.get("time_stop_quality") == "adverse"

    def test_stale_range_bound_overrun(self):
        row = _row(0.05, expected_duration_error_ratio=0.5, hold_minutes=500, interval_minutes=240)
        assert TradeAnalyticsService._classify_time_stop_cause(row) == "stale_range_bound_hold"
        assert row.get("time_stop_quality") == "stale"

    def test_stale_range_bound_flat(self):
        row = _row(0.1, expected_duration_error_ratio=0.0, hold_minutes=500, interval_minutes=240)
        assert TradeAnalyticsService._classify_time_stop_cause(row) == "stale_range_bound_hold"

    def test_slow_drift(self):
        # Must avoid abs(r) <= 0.2 check → r < -0.2 but > -0.4
        row = _row(-0.3, hold_minutes=500, interval_minutes=240)
        assert TradeAnalyticsService._classify_time_stop_cause(row) == "slow_drift"
        assert row.get("time_stop_quality") == "adverse"

    def test_flat_positive(self):
        row = _row(0.3, hold_minutes=500, interval_minutes=240)
        assert TradeAnalyticsService._classify_time_stop_cause(row) == "never_developed"
        assert row.get("time_stop_quality") == "flat_positive"


# ── _simple helpers ─────────────────────────────────────────────────

class TestSimpleHelpers:
    def test_simple_group_count(self):
        rows = [_row(mode="SWING"), _row(mode="SWING"), _row(mode="SCALP")]
        result = TradeAnalyticsService._simple_group_count(rows, "mode")
        assert len(result) == 2
        assert result[0]["label"] == "SWING"
        assert result[0]["count"] == 2

    def test_simple_group_avg(self):
        rows = [_row(1.0, mode="SWING"), _row(-0.5, mode="SWING"), _row(2.0, mode="SCALP")]
        result = TradeAnalyticsService._simple_group_avg(rows, "mode")
        swing = next(r for r in result if r["label"] == "SWING")
        assert swing["avg_realized_r"] == 0.25
        assert swing["count"] == 2

    def test_avg_realized_r(self):
        assert TradeAnalyticsService._avg_realized_r([_row(1.0), _row(2.0)]) == 1.5
        assert TradeAnalyticsService._avg_realized_r([]) == 0.0


# ── _prior_window / _current_window ────────────────────────────────

class TestWindows:
    def test_current_window_filters_recent(self):
        now = datetime.now(timezone.utc)
        rows = [
            _row(1.0, closed_at_utc=(now - timedelta(hours=1)).isoformat()),
            _row(2.0, closed_at_utc=(now - timedelta(days=20)).isoformat()),
        ]
        result = svc()._current_window(rows, lookback_days=7)
        assert len(result) == 1

    def test_prior_window(self):
        now = datetime.now(timezone.utc)
        rows = [
            _row(1.0, closed_at_utc=(now - timedelta(days=5)).isoformat()),  # within current
            _row(2.0, closed_at_utc=(now - timedelta(days=12)).isoformat()), # within prior
            _row(3.0, closed_at_utc=(now - timedelta(days=30)).isoformat()), # outside both
        ]
        prior = svc()._prior_window(rows, lookback_days=7)
        assert len(prior) == 1  # only the day-12 row
        assert prior[0]["realized_r"] == 2.0

    def test_zero_lookback(self):
        rows = [_row()]
        result = svc()._current_window(rows, lookback_days=0)
        assert len(result) == 1
        assert result[0]["realized_r"] == rows[0]["realized_r"]
        assert svc()._prior_window(rows, lookback_days=0) == []


# ── _group_metrics ─────────────────────────────────────────────────

class TestGroupMetrics:
    def test_basic_metrics(self):
        rows = [_row(1.0), _row(-0.5), _row(0.5), _row(-1.0), _row(2.0), _row(1.0), _row(-0.5), _row(0.5), _row(-1.0), _row(2.0)]
        result = svc()._group_metrics("test", rows, min_samples=5)
        assert result["label"] == "test"
        assert result["trades"] == 10
        assert result["win_rate"] == 0.6
        assert result["net_r"] == 4.0
        assert result["stop_hit_pct"] == 0.0
        assert result["reliability"] == "STABLE"

    def test_low_sample(self):
        rows = [_row(1.0)]
        result = svc()._group_metrics("low", rows, min_samples=5)
        assert result["reliability"] == "LOW_SAMPLE"
        assert result["provisional"] is True

    def test_building_sample(self):
        rows = [_row(1.0) for _ in range(6)]
        result = svc()._group_metrics("building", rows, min_samples=5)
        assert result["reliability"] == "BUILDING_SAMPLE"

    def test_positive_expectancy_reason(self):
        rows = [_row(1.0) for _ in range(15)]
        result = svc()._group_metrics("good", rows, min_samples=5)
        assert "best because expectancy is positive" in result["reason_summary"]

    def test_negative_expectancy_reason(self):
        rows = [_row(-1.0) for _ in range(15)]
        result = svc()._group_metrics("bad", rows, min_samples=5)
        assert "worst because repeated stop-outs" in result["reason_summary"]

    def test_expectancy_score(self):
        rows = [_row(0.5) for _ in range(100)]
        result = svc()._group_metrics("good", rows, min_samples=5)
        # avg_r=0.5, trades=100 → expectancy=0.5*sqrt(100)=5.0
        assert result["expectancy_score"] == 5.0

    def test_max_drawdown_in_metrics(self):
        rows = [_row(3.0), _row(-1.0), _row(-2.0)]
        result = svc()._group_metrics("dd", rows, min_samples=5)
        assert result["max_drawdown_r"] == 3.0


# ── get_confidence_bucket_breakdown_from_rows ──────────────────────

class TestConfidenceBuckets:
    def test_single_bucket(self):
        rows = [_row(1.0, confidence_after_learning=55.0) for _ in range(5)]
        result = svc().get_confidence_bucket_breakdown_from_rows(rows)
        assert len(result) == 1
        assert result[0]["label"] == "50-60"

    def test_falls_back_to_confidence(self):
        rows = [_row(1.0, confidence=75.0, confidence_after_learning=None)]
        result = svc().get_confidence_bucket_breakdown_from_rows(rows)
        assert result[0]["label"] == "70-80"

    def test_empty(self):
        assert svc().get_confidence_bucket_breakdown_from_rows([]) == []

    def test_sorted_by_label(self):
        rows = [
            _row(1.0, confidence_after_learning=85.0),
            _row(1.0, confidence_after_learning=25.0),
            _row(1.0, confidence_after_learning=55.0),
        ]
        result = svc().get_confidence_bucket_breakdown_from_rows(rows)
        labels = [item["label"] for item in result]
        assert labels == ["20-30", "50-60", "80-90"]


# ── get_exit_quality_breakdown_from_rows ───────────────────────────

class TestExitQuality:
    def test_no_exits(self):
        rows = [_row() for _ in range(10)]
        result = svc().get_exit_quality_breakdown_from_rows(rows)
        assert result["stop_hit_rate"] == 0.0
        assert result["target_hit_rate"] == 0.0
        assert result["time_exit_rate"] == 0.0

    def test_mixed_exits(self):
        rows = [
            _row(stop_hit=True), _row(stop_hit=True),
            _row(target_hit=True),
            _row(time_exit=True),
            _row(stale_exit=True),
        ]
        result = svc().get_exit_quality_breakdown_from_rows(rows)
        assert result["stop_hit_rate"] == 0.4
        assert result["target_hit_rate"] == 0.2
        assert result["time_exit_rate"] == 0.2
        assert result["stale_exit_rate"] == 0.2

    def test_empty(self):
        result = svc().get_exit_quality_breakdown_from_rows([])
        assert result["stop_hit_rate"] == 0.0


# ── Audit analytics helpers ────────────────────────────────────────

class TestAuditHelpers:
    def test_threshold_pass_frequency(self):
        rows = [
            {"audit": {"threshold_checks": [{"name": "min_conf", "passed": True}, {"name": "min_rr", "passed": False}]}},
            {"audit": {"threshold_checks": [{"name": "min_conf", "passed": True}, {"name": "min_rr", "passed": True}]}},
        ]
        result = TradeAnalyticsService._threshold_pass_frequency(rows)
        assert result["min_conf"] == 1.0
        assert result["min_rr"] == 0.5

    def test_factor_score_averages(self):
        rows = [
            {"audit": {"factor_scores": {"trend": 0.8, "momentum": 0.6}}},
            {"audit": {"factor_scores": {"trend": 0.6, "momentum": 0.4}}},
        ]
        result = TradeAnalyticsService._factor_score_averages(rows)
        assert result["trend"] == 0.7
        assert result["momentum"] == 0.5

    def test_adjustment_presence(self):
        rows = [
            {"audit": {"learning_adjustments_applied": [{"source": "entry_penalty"}, {"source": "component_penalty"}]}},
            {"audit": {"learning_adjustments_applied": [{"source": "entry_penalty"}]}},
        ]
        result = TradeAnalyticsService._adjustment_presence(rows)
        assert result["entry_penalty"] == 1.0
        assert result["component_penalty"] == 0.5

    def test_circuit_impact(self):
        rows = [
            {"audit": {"circuit_breaker_state": "CLOSED"}},
            {"audit": {"circuit_breaker_state": "CLOSED"}},
            {"audit": {"circuit_breaker_state": "DEGRADED"}},
        ]
        result = TradeAnalyticsService._circuit_impact(rows)
        assert result["CLOSED"] == 2 / 3
        assert result["DEGRADED"] == 1 / 3
