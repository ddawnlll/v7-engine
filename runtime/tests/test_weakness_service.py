"""Tests for runtime/services/weakness_service.py."""

from unittest.mock import MagicMock

from runtime.services.weakness_service import WeaknessService


def svc() -> WeaknessService:
    return WeaknessService(failure_repo=MagicMock())


# ── _normalize_date_from ───────────────────────────────────────────

class TestNormalizeDateFrom:
    def test_positive(self):
        from runtime.services.weakness_service import _normalize_date_from
        result = _normalize_date_from(30)
        assert result.endswith("+00:00") or result.endswith("Z")

    def test_minimum_1(self):
        from runtime.services.weakness_service import _normalize_date_from
        assert _normalize_date_from(0) is not None
        assert _normalize_date_from(-5) is not None


# ── _average ────────────────────────────────────────────────────────

class TestAverage:
    def test_basic(self):
        assert WeaknessService._average([1.0, 2.0, 3.0]) == 2.0

    def test_empty(self):
        assert WeaknessService._average([]) == 0.0

    def test_single(self):
        assert WeaknessService._average([5.0]) == 5.0


# ── _most_common ────────────────────────────────────────────────────

class TestMostCommon:
    def test_basic(self):
        assert WeaknessService._most_common(["a", "b", "a", "c", "a"]) == "a"

    def test_empty(self):
        assert WeaknessService._most_common([]) is None

    def test_single(self):
        assert WeaknessService._most_common(["x"]) == "x"


# ── _build_component_row ───────────────────────────────────────────

class TestBuildComponentRow:
    def test_basic(self):
        items = [
            {"severity_score": 4, "confidence": 0.8, "failure_source": "RISK_MODEL", "improvement": "Widen stop"},
            {"severity_score": 2, "confidence": 0.6, "failure_source": "RISK_MODEL", "improvement": "Widen stop"},
        ]
        result = svc()._build_component_row("Stop Loss", items)
        assert result["blamed_component"] == "Stop Loss"
        assert result["count"] == 2
        assert result["avg_severity"] == 3.0
        assert result["avg_confidence"] == 0.7
        assert result["weight_score"] == 6.0
        assert result["top_failure_source"] == "RISK_MODEL"

    def test_single_item(self):
        result = svc()._build_component_row("Test", [{"severity_score": 3, "confidence": 0.7, "failure_source": "SRC", "improvement": ""}])
        assert result["count"] == 1
        assert result["avg_severity"] == 3.0


# ── _build_source_row ──────────────────────────────────────────────

class TestBuildSourceRow:
    def test_basic(self):
        items = [
            {"severity_score": 5, "confidence": 0.9, "blamed_component": "Stop Loss", "improvement": "Widen stop"},
            {"severity_score": 3, "confidence": 0.7, "blamed_component": "Stop Loss", "improvement": "Widen stop"},
            {"severity_score": 4, "confidence": 0.8, "blamed_component": "Entry Timing", "improvement": "Check momentum"},
        ]
        result = svc()._build_source_row("RISK_MODEL", items)
        assert result["failure_source"] == "RISK_MODEL"
        assert result["count"] == 3
        assert result["avg_severity"] == 4.0
        assert result["weight_score"] == 12.0
        assert result["top_component"] == "Stop Loss"
        assert result["best_improvement"] == "Widen stop"
        assert len(result["components"]) == 2

    def test_single_source(self):
        result = svc()._build_source_row("TEST", [{"severity_score": 3, "confidence": 0.7, "blamed_component": "C", "improvement": ""}])
        assert result["count"] == 1
        assert result["top_component"] == "C"


# ── get_weakness_profile (mocked) ──────────────────────────────────

class TestGetWeaknessProfile:
    def test_empty(self):
        service = svc()
        service.failure_repo.list_failures.return_value = ([], 0)
        result = service.get_weakness_profile()
        assert result["total_losses_analyzed"] == 0
        assert result["top_failure_source"] is None

    def test_with_data(self):
        service = svc()
        service.failure_repo.list_failures.return_value = ([
            {"failure_source": "RISK_MODEL", "blamed_component": "Stop Loss", "severity_score": 5, "confidence": 0.9, "improvement": "Widen"},
            {"failure_source": "RISK_MODEL", "blamed_component": "Stop Loss", "severity_score": 3, "confidence": 0.7, "improvement": "Widen"},
            {"failure_source": "ENTRY_LOGIC", "blamed_component": "Entry Timing", "severity_score": 4, "confidence": 0.8, "improvement": "Check"},
        ], 3)
        result = service.get_weakness_profile(min_confidence=0.0)
        assert result["total_losses_analyzed"] == 3
        assert result["top_failure_source"] == "RISK_MODEL"
        assert result["top_blamed_component"] == "Stop Loss"
        assert len(result["ranked_sources"]) == 2
        assert len(result["ranked_components"]) == 2

    def test_confidence_filter(self):
        service = svc()
        service.failure_repo.list_failures.return_value = ([
            {"failure_source": "A", "blamed_component": "X", "severity_score": 3, "confidence": 0.9, "improvement": ""},
            {"failure_source": "A", "blamed_component": "Y", "severity_score": 3, "confidence": 0.5, "improvement": ""},
        ], 2)
        result = service.get_weakness_profile(min_confidence=0.7)
        assert result["total_losses_analyzed"] == 1
