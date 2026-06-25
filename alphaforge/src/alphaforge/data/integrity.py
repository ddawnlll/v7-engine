"""Storage integrity validation for AlphaForge market data.

Validates persisted kline Parquet files:
  - SHA-256 checksum sidecar matches file contents
  - Timestamps are monotonically sorted
  - No duplicate timestamps
  - No gaps larger than one interval
  - Optional: row count matches the expected [start, end) range

This module lives in alphaforge.data so that AlphaForge owns the
quality gate for data it consumes, while the actual IO primitives
remain in lib.market_data.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import pyarrow.parquet as pq

from lib.market_data.binance.klines_service import interval_to_minutes

logger = logging.getLogger(__name__)


@dataclass
class IntegrityReport:
    """Result of validating a single kline Parquet file."""

    path: str
    interval: str
    ok: bool = False
    checksum_ok: bool = False
    sorted_ok: bool = False
    no_duplicates: bool = False
    no_gaps: bool = False
    row_count: int = 0
    expected_count: Optional[int] = None
    first_timestamp: Optional[int] = None
    last_timestamp: Optional[int] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize report to a plain dict suitable for logging / JSON."""
        return {
            "path": self.path,
            "interval": self.interval,
            "ok": self.ok,
            "checksum_ok": self.checksum_ok,
            "sorted_ok": self.sorted_ok,
            "no_duplicates": self.no_duplicates,
            "no_gaps": self.no_gaps,
            "row_count": self.row_count,
            "expected_count": self.expected_count,
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
            "warnings": self.warnings,
        }


def _interval_to_ms(interval: str) -> int:
    """Convert a Binance interval string to milliseconds."""
    return interval_to_minutes(interval) * 60_000


def _verify_checksum(path: str) -> tuple[bool, list[str]]:
    """Return (matches, warnings)."""
    warnings: list[str] = []
    sidecar = path + ".sha256"
    if not os.path.exists(sidecar):
        warnings.append(f"Missing checksum sidecar: {sidecar}")
        return False, warnings

    with open(sidecar, "r", encoding="utf-8") as f:
        expected = f.read().strip()

    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    actual = sha256.hexdigest()

    if actual != expected:
        warnings.append("SHA-256 checksum mismatch")
        return False, warnings

    return True, warnings


def validate_kline_parquet(
    path: str,
    interval: str,
    expected_start: Optional[int] = None,
    expected_end: Optional[int] = None,
) -> IntegrityReport:
    """Validate a kline Parquet file and its sidecar.

    Args:
        path: Path to the Parquet file.
        interval: Binance kline interval (e.g. "1h", "4h").
        expected_start: Optional inclusive start timestamp in milliseconds.
        expected_end: Optional exclusive end timestamp in milliseconds.

    Returns:
        IntegrityReport with all check results and warnings.
    """
    report = IntegrityReport(path=path, interval=interval)

    if not os.path.exists(path):
        report.warnings.append(f"File missing: {path}")
        return report

    # ---- Checksum sidecar ----
    report.checksum_ok, checksum_warnings = _verify_checksum(path)
    report.warnings.extend(checksum_warnings)

    # ---- Read timestamps ----
    try:
        table = pq.read_table(path)
    except Exception as exc:  # pragma: no cover - filesystem corruption path
        report.warnings.append(f"Failed to read Parquet: {exc}")
        return report

    df = table.to_pandas()
    report.row_count = len(df)

    if "timestamp" not in df.columns:
        report.warnings.append("Missing 'timestamp' column")
        return report

    timestamps = df["timestamp"].astype("int64").tolist()
    if not timestamps:
        report.warnings.append("No records in file")
        return report

    report.first_timestamp = int(timestamps[0])
    report.last_timestamp = int(timestamps[-1])

    # ---- Sort / duplicate checks ----
    report.sorted_ok = timestamps == sorted(timestamps)
    report.no_duplicates = len(timestamps) == len(set(timestamps))

    if not report.sorted_ok:
        report.warnings.append("Timestamps are not monotonically sorted")
    if not report.no_duplicates:
        report.warnings.append("Duplicate timestamps detected")

    # ---- Gap detection ----
    interval_ms = _interval_to_ms(interval)
    gaps: list[tuple[int, int]] = []
    for i in range(1, len(timestamps)):
        expected_next = timestamps[i - 1] + interval_ms
        if timestamps[i] != expected_next:
            gaps.append((expected_next, timestamps[i]))
    report.no_gaps = not gaps
    if gaps:
        preview = gaps[:3]
        report.warnings.append(f"Found {len(gaps)} gap(s): {preview}")

    # ---- Expected count check ----
    if expected_start is not None and expected_end is not None and interval_ms:
        report.expected_count = (expected_end - expected_start) // interval_ms
        if report.row_count != report.expected_count:
            report.warnings.append(
                f"Expected {report.expected_count} records, got {report.row_count}"
            )

    # ---- Overall verdict ----
    report.ok = (
        report.checksum_ok
        and report.sorted_ok
        and report.no_duplicates
        and report.no_gaps
    )

    return report
