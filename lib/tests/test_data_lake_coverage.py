"""
Tests for CoverageReport — frozen dataclass and helper functions.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

import pytest

from lib.data_lake.coverage import (
    CoverageReport,
    build_coverage_report,
    coverage_pct_from_counts,
    merge_coverage_reports,
)
from lib.data_lake.catalog import DataCatalog
from lib.data_lake.spec import DatasetSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spec(**kw: object) -> DatasetSpec:
    """Build a valid DatasetSpec with overridable defaults."""
    defaults: dict[str, object] = dict(
        dataset_id="test-cov-001",
        source="binance",
        market="um_futures",
        symbols=("BTCUSDT",),
        intervals=("1h",),
        data_types=("klines",),
        start=datetime(2022, 1, 1, tzinfo=timezone.utc),
        end=datetime(2022, 1, 3, tzinfo=timezone.utc),
        priority="P0",
        backtest_required=True,
        allow_synthetic=False,
    )
    defaults.update(kw)
    return DatasetSpec(**defaults)  # type: ignore[arg-type]


def _catalog(entries: list[dict] | None = None) -> DataCatalog:
    """Create an isolated DataCatalog backed by a temp file path."""
    tmp = os.path.join(tempfile.mkdtemp(), "test_coverage_catalog.json")
    cat = DataCatalog(catalog_path=tmp)
    if entries:
        for e in entries:
            cat.add_entry(**e)
    return cat


# ---------------------------------------------------------------------------
# coverage_pct_from_counts
# ---------------------------------------------------------------------------


def test_coverage_pct_from_counts() -> None:
    """50 actual / 100 expected -> 50.0."""
    assert coverage_pct_from_counts(50, 100) == 50.0


def test_coverage_pct_zero_expected() -> None:
    """0 expected -> 0.0 regardless of actual."""
    assert coverage_pct_from_counts(50, 0) == 0.0
    assert coverage_pct_from_counts(0, 0) == 0.0


def test_coverage_pct_full() -> None:
    """actual == expected -> 100.0."""
    assert coverage_pct_from_counts(100, 100) == 100.0


def test_coverage_pct_capped() -> None:
    """actual > expected -> capped at 100.0."""
    assert coverage_pct_from_counts(150, 100) == 100.0


def test_coverage_pct_negative_expected() -> None:
    """negative expected -> 0.0."""
    assert coverage_pct_from_counts(50, -10) == 0.0


def test_coverage_pct_zero_actual() -> None:
    """0 actual -> 0.0."""
    assert coverage_pct_from_counts(0, 100) == 0.0


def test_coverage_pct_fractional() -> None:
    """1 out of 3 -> ~33.33."""
    result = coverage_pct_from_counts(1, 3)
    assert abs(result - 33.33) < 0.01


# ---------------------------------------------------------------------------
# CoverageReport immutability
# ---------------------------------------------------------------------------


def test_coverage_report_frozen() -> None:
    """Cannot modify a CoverageReport after creation."""
    report = CoverageReport(
        dataset_spec={"id": "test"},
        source="binance",
        total_expected_bars=100,
        total_actual_bars=50,
        coverage_pct=50.0,
        generated_at="2024-01-01T00:00:00+00:00",
    )
    with pytest.raises(Exception):
        report.coverage_pct = 75.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# build_coverage_report
# ---------------------------------------------------------------------------


def test_build_coverage_report() -> None:
    """Builds a CoverageReport from a spec and a fully-covered catalog."""
    spec = _spec()
    start_ms = int(spec.start.timestamp() * 1000)
    end_ms = int(spec.end.timestamp() * 1000)
    cat = _catalog([
        {"symbol": "BTCUSDT", "interval": "1h",
         "start_ts": start_ms, "end_ts": end_ms,
         "row_count": 48, "checksum": "a"},
    ])

    report = build_coverage_report(spec, cat)

    assert report.source == "binance"
    assert report.total_expected_bars > 0
    assert report.total_actual_bars == 48
    assert report.coverage_pct == 100.0
    assert isinstance(report.dataset_spec, dict)
    assert report.dataset_spec["dataset_id"] == "test-cov-001"
    assert isinstance(report.generated_at, str)
    assert report.generated_at != ""
    assert report.integrity_pass is True


def test_build_with_gaps() -> None:
    """Gaps from the catalog are correctly included in the report."""
    spec = _spec()
    start_ms = int(spec.start.timestamp() * 1000)
    end_ms = int(spec.end.timestamp() * 1000)
    mid_ms = start_ms + int((end_ms - start_ms) / 2)

    cat = _catalog([
        {"symbol": "BTCUSDT", "interval": "1h",
         "start_ts": start_ms, "end_ts": mid_ms,
         "row_count": 24, "checksum": "a"},
    ])

    report = build_coverage_report(spec, cat)

    assert len(report.gaps) >= 1
    assert report.coverage_pct < 100.0
    assert report.integrity_pass is False


def test_build_empty_catalog() -> None:
    """Empty catalog produces 0% coverage and a gap."""
    spec = _spec()
    cat = _catalog()

    report = build_coverage_report(spec, cat)

    assert report.coverage_pct == 0.0
    assert len(report.gaps) >= 1
    assert report.integrity_pass is False


# ---------------------------------------------------------------------------
# merge_coverage_reports
# ---------------------------------------------------------------------------


def test_merge_reports() -> None:
    """Average of 50% and 100% -> 75%."""
    r1 = CoverageReport(
        dataset_spec={"id": "a"},
        source="binance",
        total_expected_bars=100,
        total_actual_bars=50,
        coverage_pct=50.0,
        gaps=[],
        duplicates=[],
        integrity_pass=False,
        generated_at="2024-01-01T00:00:00+00:00",
    )
    r2 = CoverageReport(
        dataset_spec={"id": "b"},
        source="coinalyze",
        total_expected_bars=100,
        total_actual_bars=100,
        coverage_pct=100.0,
        gaps=[],
        duplicates=[],
        integrity_pass=True,
        generated_at="2024-01-02T00:00:00+00:00",
    )

    merged = merge_coverage_reports([r1, r2])

    assert merged.coverage_pct == 75.0
    assert merged.total_expected_bars == 200
    assert merged.total_actual_bars == 150
    assert merged.integrity_pass is False  # AND of True and False
    # Uses first report's dataset_spec and source
    assert merged.dataset_spec == {"id": "a"}
    assert merged.source == "binance"
    # Uses latest generated_at
    assert merged.generated_at == "2024-01-02T00:00:00+00:00"


def test_merge_single_report() -> None:
    """Merging a single report returns a report with same values."""
    r = CoverageReport(
        dataset_spec={"id": "x"},
        source="test",
        total_expected_bars=200,
        total_actual_bars=150,
        coverage_pct=75.0,
        generated_at="2024-06-01T00:00:00+00:00",
    )
    merged = merge_coverage_reports([r])
    assert merged.coverage_pct == 75.0
    assert merged.total_expected_bars == 200
    assert merged.total_actual_bars == 150


def test_merge_empty_list_raises() -> None:
    """Empty list raises ValueError."""
    with pytest.raises(ValueError, match="Cannot merge an empty list"):
        merge_coverage_reports([])


def test_merge_all_pass_integrity() -> None:
    """All reports pass -> merged integrity_pass is True."""
    r1 = CoverageReport(
        dataset_spec={}, source="a",
        total_expected_bars=10, total_actual_bars=10,
        coverage_pct=100.0, integrity_pass=True,
        generated_at="2024-01-01T00:00:00+00:00",
    )
    r2 = CoverageReport(
        dataset_spec={}, source="a",
        total_expected_bars=10, total_actual_bars=10,
        coverage_pct=100.0, integrity_pass=True,
        generated_at="2024-01-01T00:00:00+00:00",
    )
    merged = merge_coverage_reports([r1, r2])
    assert merged.integrity_pass is True
