"""Tests for runtime/services/failure_analytics_service.py.

Pure functions: _lookback_start, _norm_text, _safe_float, _count_by,
_top_count, _breakdown, _build_page_summary, _build_source_component_matrix,
_build_severity_distribution, _build_ranked_improvements, export_csv.

Regex-based: _simulation_context_fallback (3 code paths).
"""

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

from runtime.services.failure_analytics_service import FailureAnalyticsService


def service() -> FailureAnalyticsService:
    return FailureAnalyticsService()


# ── _utc_now_iso ────────────────────────────────────────────────────

class TestUtcNowIso:
    def test_returns_iso_string(self):
        from runtime.services.failure_analytics_service import _utc_now_iso
        result = _utc_now_iso()
        assert isinstance(result, str)
        assert "T" in result


# ── _lookback_start ─────────────────────────────────────────────────

class TestLookbackStart:
    def test_none(self):
        from runtime.services.failure_analytics_service import _lookback_start
        assert _lookback_start(None) is None

    def test_zero(self):
        from runtime.services.failure_analytics_service import _lookback_start
        assert _lookback_start(0) is None

    def test_positive(self):
        from runtime.services.failure_analytics_service import _lookback_start
        result = _lookback_start(30)
        assert result is not None
        assert result.endswith("+00:00") or result.endswith("Z")

    def test_negative(self):
        from runtime.services.failure_analytics_service import _lookback_start
        assert _lookback_start(-1) is None


# ── _norm_text ──────────────────────────────────────────────────────

class TestNormText:
    def test_basic(self):
        from runtime.services.failure_analytics_service import _norm_text
        assert _norm_text("Stop Loss too tight") == "stop loss too tight"

    def test_special_chars(self):
        from runtime.services.failure_analytics_service import _norm_text
        assert _norm_text("TIMEOUT! (barrier)") == "timeout barrier"

    def test_multi_spaces(self):
        from runtime.services.failure_analytics_service import _norm_text
        assert _norm_text("bad   entry   logic") == "bad entry logic"

    def test_empty(self):
        from runtime.services.failure_analytics_service import _norm_text
        assert _norm_text("") == ""

    def test_trim(self):
        from runtime.services.failure_analytics_service import _norm_text
        assert _norm_text("  hello world  ") == "hello world"


# ── _safe_float ─────────────────────────────────────────────────────

class TestSafeFloat:
    def test_number(self):
        assert FailureAnalyticsService._safe_float(3.14) == 3.14

    def test_string_number(self):
        assert FailureAnalyticsService._safe_float("3.14") == 3.14

    def test_none(self):
        assert FailureAnalyticsService._safe_float(None) is None

    def test_nan(self):
        val = float("nan")
        assert FailureAnalyticsService._safe_float(val) is None

    def test_invalid(self):
        assert FailureAnalyticsService._safe_float("abc") is None


# ── _count_by / _top_count / _breakdown ─────────────────────────────

class TestCountHelpers:
    def test_count_by(self):
        rows = [
            {"failure_source": "RISK_MODEL", "blamed_component": "Stop Loss"},
            {"failure_source": "RISK_MODEL", "blamed_component": "Stop Loss"},
            {"failure_source": "ENTRY_LOGIC", "blamed_component": "Entry Timing"},
        ]
        assert FailureAnalyticsService._count_by(rows, "failure_source") == {
            "RISK_MODEL": 2, "ENTRY_LOGIC": 1
        }

    def test_count_by_empty(self):
        assert FailureAnalyticsService._count_by([], "failure_source") == {}

    def test_count_by_missing_key(self):
        rows = [{"other": "x"}]
        assert FailureAnalyticsService._count_by(rows, "failure_source") == {"UNKNOWN": 1}

    def test_top_count(self):
        assert FailureAnalyticsService._top_count({"a": 5, "b": 3, "c": 7}) == ("c", 7)

    def test_top_count_empty(self):
        assert FailureAnalyticsService._top_count({}) == (None, 0)

    def test_breakdown(self):
        rows = [
            {"failure_source": "RISK_MODEL"},
            {"failure_source": "RISK_MODEL"},
            {"failure_source": "ENTRY_LOGIC"},
        ]
        result = FailureAnalyticsService._breakdown(rows, "failure_source")
        assert len(result) == 2
        assert result[0]["label"] == "RISK_MODEL"
        assert result[0]["count"] == 2
        assert result[0]["percent"] == 66.6667

    def test_breakdown_sorted(self):
        rows = [
            {"failure_source": "A"},
            {"failure_source": "B"},
            {"failure_source": "B"},
        ]
        result = FailureAnalyticsService._breakdown(rows, "failure_source")
        assert result[0]["label"] == "B"  # higher count first

    def test_breakdown_empty(self):
        assert FailureAnalyticsService._breakdown([], "failure_source") == []


# ── _build_page_summary ─────────────────────────────────────────────

class TestBuildPageSummary:
    def test_empty(self):
        result = FailureAnalyticsService._build_page_summary([])
        assert result["total_losses_analyzed"] == 0
        assert result["avg_realized_r"] == 0.0
        assert result["top_failure_source"] is None

    def test_with_data(self):
        rows = [
            {"failure_source": "RISK_MODEL", "blamed_component": "Stop Loss", "realized_r": -1.0},
            {"failure_source": "RISK_MODEL", "blamed_component": "Stop Loss", "realized_r": -2.0},
            {"failure_source": "ENTRY_LOGIC", "blamed_component": "Entry Timing", "realized_r": -0.5},
        ]
        result = FailureAnalyticsService._build_page_summary(rows)
        assert result["total_losses_analyzed"] == 3
        assert result["avg_realized_r"] == round(-3.5 / 3, 4)
        assert result["top_failure_source"] == "RISK_MODEL"
        assert result["top_blamed_component"] == "Stop Loss"


# ── _build_source_component_matrix ─────────────────────────────────

class TestBuildSourceComponentMatrix:
    def test_empty(self):
        result = FailureAnalyticsService._build_source_component_matrix([])
        assert result["sources"] == []
        assert result["components"] == []

    def test_with_data(self):
        rows = [
            {"failure_source": "RISK_MODEL", "blamed_component": "Stop Loss"},
            {"failure_source": "RISK_MODEL", "blamed_component": "Stop Loss"},
            {"failure_source": "ENTRY_LOGIC", "blamed_component": "Entry Timing"},
        ]
        result = FailureAnalyticsService._build_source_component_matrix(rows)
        assert set(result["sources"]) == {"RISK_MODEL", "ENTRY_LOGIC"}
        assert set(result["components"]) == {"Stop Loss", "Entry Timing"}
        assert result["cells"]["RISK_MODEL"]["Stop Loss"] == 2
        assert result["cells"]["ENTRY_LOGIC"]["Entry Timing"] == 1


# ── _build_severity_distribution ────────────────────────────────────

class TestBuildSeverityDistribution:
    def test_empty(self):
        result = FailureAnalyticsService._build_severity_distribution([])
        assert result["avg_severity"] == 0.0
        assert result["avg_confidence"] == 0.0
        assert sum(item["count"] for item in result["items"]) == 0

    def test_with_data(self):
        rows = [
            {"severity_score": 5, "confidence": 0.8},
            {"severity_score": 3, "confidence": 0.6},
            {"severity_score": 1, "confidence": 0.9},
        ]
        result = FailureAnalyticsService._build_severity_distribution(rows)
        assert result["avg_severity"] == 3.0
        assert result["avg_confidence"] == round((0.8 + 0.6 + 0.9) / 3, 4)
        items = {item["severity"]: item["count"] for item in result["items"]}
        assert items[5] == 1
        assert items[3] == 1
        assert items[1] == 1

    def test_clamps_to_1_5_range(self):
        rows = [
            {"severity_score": 0, "confidence": 0.5},
            {"severity_score": 99, "confidence": 0.5},
        ]
        result = FailureAnalyticsService._build_severity_distribution(rows)
        items = {item["severity"]: item["count"] for item in result["items"]}
        assert items[1] == 1   # clamped up from 0
        assert items[5] == 1   # clamped down from 99


# ── _build_ranked_improvements ──────────────────────────────────────

class TestBuildRankedImprovements:
    def test_empty(self):
        assert FailureAnalyticsService._build_ranked_improvements([]) == []

    def test_ranking_and_dedup(self):
        rows = [
            {"failure_source": "RISK_MODEL", "blamed_component": "Stop Loss", "severity_score": 5, "confidence": 0.9, "improvement": "Widen stop"},
            {"failure_source": "RISK_MODEL", "blamed_component": "Stop Loss", "severity_score": 4, "confidence": 0.8, "improvement": "Widen stop"},
            {"failure_source": "ENTRY_LOGIC", "blamed_component": "Entry Timing", "severity_score": 3, "confidence": 0.7, "improvement": "Check momentum"},
        ]
        result = FailureAnalyticsService._build_ranked_improvements(rows)
        assert len(result) == 2  # two distinct (source, component) pairs
        assert result[0]["weight_score"] > result[1]["weight_score"]
        # Duplicate "Widen stop" improvement deduplication logic:
        # Both RISK_MODEL/Stop Loss rows have same improvement text → after dedup only one entry
        risk_entries = [r for r in result if r["failure_source"] == "RISK_MODEL"]
        assert len(risk_entries) == 1  # deduped

    def test_no_improvement_does_not_dedup(self):
        rows = [
            {"failure_source": "A", "blamed_component": "X", "severity_score": 3, "confidence": 0.5, "improvement": ""},
            {"failure_source": "A", "blamed_component": "Y", "severity_score": 3, "confidence": 0.5, "improvement": ""},
        ]
        result = FailureAnalyticsService._build_ranked_improvements(rows)
        assert len(result) == 2  # empty improvements not deduped (not in seen_norms)


# ── export_csv ──────────────────────────────────────────────────────

class TestExportCsv:
    def test_headers_and_rows(self):
        rows = [
            {"order_id": "o1", "symbol": "BTCUSDT", "realized_r": -1.0, "failure_source": "RISK_MODEL"},
            {"order_id": "o2", "symbol": "ETHUSDT", "realized_r": -0.5, "failure_source": "ENTRY_LOGIC"},
        ]
        csv_output = FailureAnalyticsService.export_csv(rows)
        reader = csv.DictReader(io.StringIO(csv_output))
        parsed = list(reader)
        assert len(parsed) == 2
        assert parsed[0]["order_id"] == "o1"
        assert parsed[0]["failure_source"] == "RISK_MODEL"

    def test_empty(self):
        csv_output = FailureAnalyticsService.export_csv([])
        assert "order_id" in csv_output
        assert "symbol" in csv_output


# ── _simulation_context_fallback ────────────────────────────────────

class TestSimulationContextFallback:
    """Three recovery paths: signal_id=simctx|, explanation regex, order_id regex."""

    @staticmethod
    def _make_failure(
        signal_id: str | None = None,
        explanation: str | None = None,
        order_id: str | None = None,
    ) -> MagicMock:
        f = MagicMock()
        f.signal_id = signal_id
        f.explanation = explanation
        f.order_id = order_id
        return f

    def test_simctx_path(self):
        failure = self._make_failure(signal_id="simctx|BTCUSDT|4h|SWING|LONG|-1.5|-50.0")
        result = FailureAnalyticsService._simulation_context_fallback(failure)
        assert result["symbol"] == "BTCUSDT"
        assert result["interval"] == "4h"
        assert result["mode"] == "SWING"
        assert result["direction"] == "LONG"
        assert result["realized_r"] == -1.5
        assert result["pnl"] == -50.0

    def test_simctx_too_short(self):
        """Less than 7 parts → falls through to next path."""
        failure = self._make_failure(signal_id="simctx|BTCUSDT|SWING", explanation="losing SWING LONG trade on BTCUSDT; pnl=-2.0")
        result = FailureAnalyticsService._simulation_context_fallback(failure)
        # Should match explanation regex as fallback
        assert result["symbol"] == "BTCUSDT"
        assert result["mode"] == "SWING"

    def test_explanation_regex_path(self):
        failure = self._make_failure(
            signal_id="",
            explanation="losing SCALP SHORT trade on ETHUSDT; pnl=-1.2",
        )
        result = FailureAnalyticsService._simulation_context_fallback(failure)
        assert result["symbol"] == "ETHUSDT"
        assert result["mode"] == "SCALP"
        assert result["direction"] == "SHORT"
        assert result["realized_r"] == -1.2

    def test_explanation_no_match(self):
        failure = self._make_failure(
            signal_id="",
            explanation="some other failure without standard format",
        )
        result = FailureAnalyticsService._simulation_context_fallback(failure)
        assert result == {}

    def test_order_id_regex_path(self):
        failure = self._make_failure(
            signal_id="",
            explanation="",
            order_id="sim-1-abc123-BTCUSDT-SWING-LONG",
        )
        result = FailureAnalyticsService._simulation_context_fallback(failure)
        assert result["symbol"] == "BTCUSDT"
        assert result["mode"] == "SWING"
        assert result["direction"] == "LONG"
        assert result["realized_r"] is None  # not in order_id

    def test_order_id_no_match(self):
        failure = self._make_failure(
            signal_id="",
            explanation="",
            order_id="regular-order-123",
        )
        result = FailureAnalyticsService._simulation_context_fallback(failure)
        assert result == {}

    def test_all_empty(self):
        failure = self._make_failure()
        result = FailureAnalyticsService._simulation_context_fallback(failure)
        assert result == {}


# ── _base_rows (session-dependent) ──────────────────────────────────

class TestBaseRows:
    def test_empty(self):
        svc = service()
        session = MagicMock()
        session.query.return_value.outerjoin.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = []
        result = svc._base_rows(session, lookback_days=30)
        assert result == []

    def test_with_data(self):
        svc = service()
        session = MagicMock()
        order = MagicMock()
        order.symbol = "BTCUSDT"
        order.interval = "4h"
        order.mode = "SWING"
        order.payload_json = '{"realized_r": -1.5}'
        failure = MagicMock()
        failure.order_id = "o1"
        failure.signal_id = "sig1"
        failure.failure_source = "RISK_MODEL"
        failure.blamed_component = "Stop Loss"
        failure.severity_score = 4
        failure.confidence = 0.8
        failure.classification = ""
        failure.explanation = ""
        failure.improvement = "Widen stop"
        failure.created_at_utc = "2026-06-01T12:00:00Z"
        failure.profile_id = "paper-main"
        session.query.return_value.outerjoin.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = [(failure, order)]
        result = svc._base_rows(session, lookback_days=30)
        assert len(result) == 1
        assert result[0]["symbol"] == "BTCUSDT"
        assert result[0]["failure_source"] == "RISK_MODEL"
        assert result[0]["realized_r"] == -1.5

    def test_mode_filter(self):
        svc = service()
        session = MagicMock()
        order1 = MagicMock(symbol="BTCUSDT", interval="4h", mode="SWING", payload_json='{"realized_r": -1.0}')
        order2 = MagicMock(symbol="ETHUSDT", interval="1h", mode="SCALP", payload_json='{"realized_r": -0.5}')
        f1 = MagicMock(order_id="o1", signal_id="s1", failure_source="A", blamed_component="X", severity_score=3, confidence=0.7, classification="", explanation="", improvement="", created_at_utc="2026-06-01T12:00:00Z", profile_id="paper-main")
        f2 = MagicMock(order_id="o2", signal_id="s2", failure_source="B", blamed_component="Y", severity_score=2, confidence=0.8, classification="", explanation="", improvement="", created_at_utc="2026-06-01T12:00:00Z", profile_id="paper-main")
        session.query.return_value.outerjoin.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = [(f1, order1), (f2, order2)]
        result = svc._base_rows(session, lookback_days=30, mode_filter="SCALP")
        assert len(result) == 1
        assert result[0]["mode"] == "SCALP"


# ── get_ranked_improvements ─────────────────────────────────────────

class TestGetRankedImprovements:
    def test_calls_filtered_rows_and_builds(self):
        svc = service()
        session = MagicMock()
        order = MagicMock(symbol="BTCUSDT", interval="4h", mode="SWING", payload_json='{"realized_r": -1.0}')
        failure = MagicMock(order_id="o1", signal_id="s1", failure_source="RISK_MODEL", blamed_component="Stop Loss", severity_score=4, confidence=0.8, classification="", explanation="", improvement="Widen stop", created_at_utc="2026-06-01T12:00:00Z", profile_id="paper-main")
        session.query.return_value.outerjoin.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = [(failure, order)]
        with __import__("unittest").mock.patch("runtime.services.failure_analytics_service.session_scope") as mock_scope:
            mock_scope.return_value.__enter__.return_value = session
            result = svc.get_ranked_improvements(lookback_days=30, min_confidence=0.0)
        assert len(result) >= 1
