"""
Quality checks for market data: gap detection, duplicate detection, completeness.
"""

from lib.market_data.contracts import DataQualityReport, KlineRecord


def compute_expected_count(
    start_timestamp: int,
    end_timestamp: int,
    interval_minutes: int,
) -> int:
    """Number of expected records between start (inclusive) and end (exclusive)."""
    duration_minutes = (end_timestamp - start_timestamp) / 60_000
    return int(duration_minutes // interval_minutes)


def detect_gaps(
    records: list[KlineRecord],
    interval_minutes: int,
) -> list[tuple[int, int]]:
    """Return list of (expected_start_ms, expected_end_ms) for gaps.

    Gaps are detected as missing intervals between consecutive records.
    """
    if not records:
        return []

    gaps: list[tuple[int, int]] = []
    for i in range(1, len(records)):
        expected_next = records[i - 1].timestamp + interval_minutes * 60_000
        if records[i].timestamp != expected_next:
            gaps.append((expected_next, records[i].timestamp))
    return gaps


def detect_duplicates(
    records: list[KlineRecord],
) -> list[int]:
    """Return list of indices that are duplicates (same timestamp as previous)."""
    if not records:
        return []
    seen: set[int] = set()
    duplicates: list[int] = []
    for i, r in enumerate(records):
        if r.timestamp in seen:
            duplicates.append(i)
        seen.add(r.timestamp)
    return duplicates


def build_quality_report(
    records: list[KlineRecord],
    interval_minutes: int,
    expected_count: int,
) -> DataQualityReport:
    """Build a DataQualityReport from fetched records."""
    received = len(records)
    gaps = detect_gaps(records, interval_minutes)
    duplicate_indices = detect_duplicates(records)

    warnings: list[str] = []
    if gaps:
        warnings.append(f"Found {len(gaps)} gap(s) in data")
    if duplicate_indices:
        warnings.append(f"Found {len(duplicate_indices)} duplicate(s) in data")
    if received != expected_count:
        warnings.append(f"Expected {expected_count} records, got {received}")

    return DataQualityReport(
        total_expected=expected_count,
        total_received=received,
        gap_count=len(gaps),
        duplicate_count=len(duplicate_indices),
        is_complete=len(gaps) == 0 and received == expected_count,
        warnings=warnings,
    )
