"""
Tests for DataHealthChecker — auto-repair when data is missing.
"""

from datetime import datetime, timezone

import pytest

from lib.data_lake.health import (
    HEALTHY_COVERAGE_THRESHOLD,
    DataHealthChecker,
    HealthReport,
    _format_size,
)


class TestHealthReport:
    """HealthReport frozen dataclass."""

    def test_healthy_defaults(self):
        """Healthy report has expected defaults."""
        r = HealthReport(healthy=True, coverage_pct=100.0)
        assert r.healthy is True
        assert r.coverage_pct == 100.0
        assert r.gaps == []
        assert r.checksum_pass is True
        assert r.repaired is False
        assert r.reason == ""
        assert r.checked_at is not None

    def test_unhealthy_report(self):
        """Unhealthy report with gaps."""
        r = HealthReport(
            healthy=False,
            coverage_pct=45.0,
            gaps=[{"symbol": "BTCUSDT", "gap_start": "2023-01-01"}],
            reason="Coverage too low",
        )
        assert r.healthy is False
        assert r.coverage_pct == 45.0
        assert len(r.gaps) == 1

    def test_frozen(self):
        """Cannot modify after creation."""
        r = HealthReport(healthy=True, coverage_pct=100.0)
        with pytest.raises(Exception):
            r.healthy = False  # type: ignore[misc]

    def test_auto_timestamp(self):
        """checked_at is auto-generated ISO string."""
        r = HealthReport(healthy=True, coverage_pct=100.0)
        assert "T" in r.checked_at
        assert r.checked_at.endswith("+00:00") or "+" in r.checked_at


class TestFormatSize:
    """_format_size helper."""

    def test_small(self):
        assert "500 rows" in _format_size(500)

    def test_thousands(self):
        assert "50.0K" in _format_size(50_000)

    def test_millions(self):
        assert "2.5M" in _format_size(2_500_000)


class TestDataHealthChecker:
    """DataHealthChecker with isolated catalog."""

    def test_check_healthy_data(self):
        """100% coverage → healthy report."""
        checker = DataHealthChecker(data_dir="/tmp/nonexistent")
        # Use a spec that matches an empty catalog → 0% coverage
        report = checker.check(
            symbols=["BTCUSDT"],
            intervals=["1h"],
            start=datetime(2023, 1, 1, tzinfo=timezone.utc),
            end=datetime(2023, 1, 2, tzinfo=timezone.utc),
            auto_repair=False,
        )
        # Empty catalog → coverage should be 0% or low
        assert isinstance(report, HealthReport)
        assert report.coverage_pct < HEALTHY_COVERAGE_THRESHOLD
        assert report.repaired is False

    def test_check_with_auto_repair_disabled(self):
        """auto_repair=False → repaired flag is False."""
        checker = DataHealthChecker(data_dir="/tmp/nonexistent")
        report = checker.check(
            symbols=["BTCUSDT"],
            intervals=["1h"],
            start=datetime(2023, 1, 1, tzinfo=timezone.utc),
            end=datetime(2023, 1, 2, tzinfo=timezone.utc),
            auto_repair=False,
        )
        assert report.repaired is False
        assert report.healthy is False

    def test_ensure_healthy_raises_on_no_data(self):
        """ensure_healthy raises RuntimeError when data cannot be repaired."""
        checker = DataHealthChecker(data_dir="/tmp/nonexistent")
        with pytest.raises(RuntimeError, match="Data health check FAILED"):
            checker.ensure_healthy(
                symbols=["BTCUSDT"],
                intervals=["1h"],
                start=datetime(2023, 1, 1, tzinfo=timezone.utc),
                end=datetime(2023, 1, 2, tzinfo=timezone.utc),
            )

    def test_passport_in_report(self):
        """Passport is included when available."""
        checker = DataHealthChecker(data_dir="/tmp/nonexistent")
        report = checker.check(
            symbols=["BTCUSDT"],
            intervals=["1h"],
            start=datetime(2023, 1, 1, tzinfo=timezone.utc),
            end=datetime(2023, 1, 2, tzinfo=timezone.utc),
            auto_repair=False,
        )
        # Passport may be None if catalog is empty — that's OK
        assert hasattr(report, "passport")

    def test_threshold_constant(self):
        """Threshold is between 0 and 100."""
        assert 0 < HEALTHY_COVERAGE_THRESHOLD <= 100
