"""Tests for v7.shadow_mode — shadow mode implementation."""

import pytest

from v7.shadow_mode import (
    ShadowModeManager,
    ShadowRecord,
    ShadowDegradationReport,
)


class TestShadowModeManager:
    """Test ShadowModeManager."""

    def _make_proposed(self, decision="LONG_NOW", confidence=0.7, expected_r=0.5):
        return {
            "decision": decision,
            "confidence": confidence,
            "expected_r": expected_r,
        }

    def test_execute_shadow_creates_record(self):
        """Executing shadow should create a record."""
        mgr = ShadowModeManager()
        proposed = self._make_proposed()
        record = mgr.execute_shadow(proposed, "swing_v1")
        assert isinstance(record, ShadowRecord)
        assert record.model_scope == "swing_v1"
        assert record.comparison == "MATCH"  # Default: matches proposed

    def test_execute_shadow_match(self):
        """Shadow should match proposed when no pipeline provided."""
        mgr = ShadowModeManager()
        proposed = self._make_proposed(decision="LONG_NOW", confidence=0.8)
        record = mgr.execute_shadow(proposed, "swing_v1")
        assert record.proposed_decision == "LONG_NOW"
        assert record.shadow_decision == "LONG_NOW"
        assert record.comparison == "MATCH"
        assert record.divergence_r == 0.0

    def test_execute_shadow_stores_multiple(self):
        """Multiple shadow executions should be stored."""
        mgr = ShadowModeManager()
        mgr.execute_shadow(self._make_proposed("LONG_NOW"), "swing_v1")
        mgr.execute_shadow(self._make_proposed("SHORT_NOW"), "swing_v1")
        mgr.execute_shadow(self._make_proposed("NO_TRADE"), "swing_v1")
        records = mgr.get_records("swing_v1")
        assert len(records) == 3

    def test_get_records_limit(self):
        """get_records should respect limit."""
        mgr = ShadowModeManager()
        for i in range(10):
            mgr.execute_shadow(self._make_proposed("LONG_NOW"), "swing_v1")
        records = mgr.get_records("swing_v1", limit=3)
        assert len(records) == 3

    def test_get_records_newest_first(self):
        """get_records should return newest first."""
        mgr = ShadowModeManager()
        mgr.execute_shadow(self._make_proposed("LONG_NOW"), "swing_v1")
        mgr.execute_shadow(self._make_proposed("SHORT_NOW"), "swing_v1")
        records = mgr.get_records("swing_v1")
        assert records[0].proposed_decision == "SHORT_NOW"

    def test_clear_records(self):
        """Clearing records should empty them."""
        mgr = ShadowModeManager()
        mgr.execute_shadow(self._make_proposed("LONG_NOW"), "swing_v1")
        mgr.clear_records("swing_v1")
        assert len(mgr.get_records("swing_v1")) == 0

    def test_unknown_scope_returns_empty(self):
        """Unknown scope should return empty list."""
        mgr = ShadowModeManager()
        assert mgr.get_records("unknown") == []


class TestDetectShadowDegradation:
    """Test shadow degradation detection."""

    def _make_record(self, comparison="MATCH", divergence_r=0.0):
        return ShadowRecord(
            timestamp="2026-01-01T00:00:00Z",
            model_scope="swing_v1",
            proposed_decision="LONG_NOW",
            shadow_decision="LONG_NOW" if comparison == "MATCH" else "SHORT_NOW",
            comparison=comparison,
            divergence_r=divergence_r,
        )

    def test_no_records(self):
        """No records should not detect degradation."""
        mgr = ShadowModeManager()
        report = mgr.detect_shadow_degradation([])
        assert report.total_records == 0
        assert report.degradation_detected is False

    def test_all_matches(self):
        """All matching records should not detect degradation."""
        mgr = ShadowModeManager()
        records = [self._make_record("MATCH") for _ in range(10)]
        report = mgr.detect_shadow_degradation(records)
        assert report.match_rate == 1.0
        assert report.degradation_detected is False

    def test_detects_degradation_high_diverge_rate(self):
        """High divergence rate should detect degradation."""
        mgr = ShadowModeManager()
        records = [self._make_record("MATCH") for _ in range(5)]
        records += [self._make_record("DIVERGE", 0.5) for _ in range(5)]
        report = mgr.detect_shadow_degradation(records, max_diverge_rate=0.2)
        assert report.diverge_count == 5
        assert report.degradation_detected is True

    def test_detects_degradation_large_divergence(self):
        """Large divergence should detect degradation."""
        mgr = ShadowModeManager()
        records = [self._make_record("DIVERGE", 1.5)]
        report = mgr.detect_shadow_degradation(records, divergence_threshold=0.3)
        assert report.avg_divergence_r == 1.5
        assert report.degradation_detected is True

    def test_detects_degradation_critical_max(self):
        """Critical max divergence (>2.0 R) should detect degradation."""
        mgr = ShadowModeManager()
        records = [self._make_record("DIVERGE", 2.5)]
        report = mgr.detect_shadow_degradation(records)
        assert report.max_divergence_r == 2.5
        assert report.degradation_detected is True

    def test_stored_records_analysis(self):
        """Analyzing stored records should work without explicit records."""
        mgr = ShadowModeManager()
        for i in range(10):
            decision = "LONG_NOW" if i < 7 else "SHORT_NOW"
            mgr.execute_shadow(
                {"decision": decision, "confidence": 0.7, "expected_r": 0.5},
                "swing_v1",
            )
        report = mgr.detect_shadow_degradation(model_scope="swing_v1")
        assert report.total_records == 10
        # First 7 should match (LONG_NOW proposed = LONG_NOW shadow)
        # Last 3 should... also match since shadow defaults to proposed
        assert report.match_rate == 1.0


class TestShadowRecord:
    """Test ShadowRecord dataclass."""

    def test_defaults(self):
        """Default ShadowRecord should show MATCH."""
        record = ShadowRecord()
        assert record.comparison == "MATCH"
        assert record.divergence_r == 0.0


class TestShadowDegradationReport:
    """Test ShadowDegradationReport dataclass."""

    def test_defaults(self):
        """Default report should have no degradation."""
        report = ShadowDegradationReport()
        assert report.degradation_detected is False
        assert report.total_records == 0
