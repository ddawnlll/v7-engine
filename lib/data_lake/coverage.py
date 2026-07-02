"""
CoverageReport — frozen dataclass for reporting how much of a dataset spec
is covered by real data.

Provides pure data structures and pure functions used for coverage reporting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from lib.data_lake.catalog import DataCatalog
from lib.data_lake.spec import DatasetSpec

# ---------------------------------------------------------------------------
# CoverageReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CoverageReport:
    """Immutable report of data coverage for a single dataset spec.

    Attributes:
        dataset_spec: Dict representation of the originating DatasetSpec.
        source: Data source name (e.g. ``"binance"``).
        total_expected_bars: Estimated number of bars the spec requires.
        total_actual_bars: Number of bars actually present in the catalog.
        coverage_pct: Coverage fraction as a float in 0-100.
        gaps: List of gap dicts produced by the catalog gap analysis.
        duplicates: List of detected overlapping / duplicate entries.
        integrity_pass: Whether data passes integrity criteria.
        generated_at: ISO-8601 timestamp of when this report was built.
    """

    dataset_spec: dict[str, Any]
    source: str
    total_expected_bars: int
    total_actual_bars: int
    coverage_pct: float
    gaps: list[dict[str, Any]] = field(default_factory=list)
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    integrity_pass: bool = False
    generated_at: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def coverage_pct_from_counts(actual: int, expected: int) -> float:
    """Return the coverage percentage as a float in 0-100.

    Returns 0.0 when *expected* <= 0 to avoid division by zero.
    Caps the result at 100.0.
    """
    if expected <= 0:
        return 0.0
    return min(100.0, round(actual / expected * 100, 2))


def _find_duplicates(
    spec: DatasetSpec,
    catalog: DataCatalog,
) -> list[dict[str, Any]]:
    """Detect overlapping catalog entries for the symbols and intervals in *spec*.

    Two entries are considered duplicates when they share the same symbol and
    interval and their time ranges overlap.
    """
    duplicates: list[dict[str, Any]] = []
    for symbol in spec.symbols:
        for interval in spec.intervals:
            entries = catalog.query(symbol=symbol, interval=interval)
            sorted_entries = sorted(entries, key=lambda e: e["start_ts"])
            for i in range(len(sorted_entries)):
                for j in range(i + 1, len(sorted_entries)):
                    a = sorted_entries[i]
                    b = sorted_entries[j]
                    if a["end_ts"] > b["start_ts"] and a["start_ts"] < b["end_ts"]:
                        duplicates.append({
                            "symbol": symbol,
                            "interval": interval,
                            "entry_a_start": a["start_ts"],
                            "entry_a_end": a["end_ts"],
                            "entry_b_start": b["start_ts"],
                            "entry_b_end": b["end_ts"],
                        })
    return duplicates


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def build_coverage_report(
    spec: DatasetSpec,
    catalog: DataCatalog,
) -> CoverageReport:
    """Build a :class:`CoverageReport` by comparing *spec* against *catalog*.

    Steps:
        1. Derive expected and actual bar counts.
        2. Compute coverage percentage.
        3. Find gaps and duplicate entries.
        4. Determine integrity pass / fail.
    """
    total_expected = spec.expected_bar_count()

    total_actual = 0
    for symbol in spec.symbols:
        for interval in spec.intervals:
            entries = catalog.query(symbol=symbol, interval=interval)
            total_actual += sum(e.get("row_count", 0) for e in entries)

    pct = coverage_pct_from_counts(total_actual, total_expected)

    gaps = catalog.find_gaps(spec)
    duplicates = _find_duplicates(spec, catalog)

    integrity_pass = pct == 100.0 and len(gaps) == 0 and len(duplicates) == 0

    return CoverageReport(
        dataset_spec={
            "dataset_id": spec.dataset_id,
            "source": spec.source,
            "market": spec.market,
            "symbols": list(spec.symbols),
            "intervals": list(spec.intervals),
            "data_types": list(spec.data_types),
            "start": spec.start.isoformat(),
            "end": spec.end.isoformat(),
            "priority": spec.priority,
            "backtest_required": spec.backtest_required,
            "allow_synthetic": spec.allow_synthetic,
        },
        source=spec.source,
        total_expected_bars=total_expected,
        total_actual_bars=total_actual,
        coverage_pct=pct,
        gaps=gaps,
        duplicates=duplicates,
        integrity_pass=integrity_pass,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


def merge_coverage_reports(reports: list[CoverageReport]) -> CoverageReport:
    """Merge multiple :class:`CoverageReport` instances into a single summary.

    - ``dataset_spec`` and ``source`` come from the *first* report.
    - Bar counts are summed.
    - ``coverage_pct`` is the arithmetic mean of all reports' percentages.
    - Gap and duplicate lists are concatenated.
    - ``integrity_pass`` is ``True`` only when every report passed.
    - ``generated_at`` is the latest timestamp among the reports.
    """
    if not reports:
        raise ValueError("Cannot merge an empty list of reports")

    first = reports[0]
    total_expected = sum(r.total_expected_bars for r in reports)
    total_actual = sum(r.total_actual_bars for r in reports)
    avg_pct = round(sum(r.coverage_pct for r in reports) / len(reports), 2)

    merged_gaps: list[dict[str, Any]] = []
    merged_duplicates: list[dict[str, Any]] = []
    for r in reports:
        merged_gaps.extend(r.gaps)
        merged_duplicates.extend(r.duplicates)

    integrity_pass = all(r.integrity_pass for r in reports)

    generated_at = max(r.generated_at for r in reports)

    return CoverageReport(
        dataset_spec=first.dataset_spec,
        source=first.source,
        total_expected_bars=total_expected,
        total_actual_bars=total_actual,
        coverage_pct=avg_pct,
        gaps=merged_gaps,
        duplicates=merged_duplicates,
        integrity_pass=integrity_pass,
        generated_at=generated_at,
    )
