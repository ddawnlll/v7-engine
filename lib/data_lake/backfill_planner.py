"""
BackfillPlanner — compare a DatasetSpec against DataCatalog to produce
a DownloadManifest of missing data.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from lib.data_lake.catalog import DataCatalog
from lib.data_lake.spec import DatasetSpec

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


from dataclasses import dataclass


@dataclass(frozen=True)
class DownloadEntry:
    """A single data range that needs to be downloaded.

    Attributes:
        symbol: Trading pair symbol (e.g. ``"BTCUSDT"``).
        interval: Candle interval (e.g. ``"1h"``).
        data_type: Type of data (e.g. ``"klines"``).
        start_ms: Inclusive start of the missing range (millisecond epoch).
        end_ms: Exclusive end of the missing range (millisecond epoch).
        estimated_rows: Approximate number of rows expected.
        source_url: Direct download URL if known, else ``""``.
    """

    symbol: str
    interval: str
    data_type: str
    start_ms: int
    end_ms: int
    estimated_rows: int = 0
    source_url: str = ""


@dataclass(frozen=True)
class DownloadManifest:
    """A manifest describing a set of data files that need downloading.

    Attributes:
        manifest_id: Unique UUID for this manifest.
        dataset_spec: The original ``DatasetSpec`` as a plain dict.
        entries: Tuple of ``DownloadEntry`` items to fetch.
        total_entries: Number of entries (convenience field).
        total_estimated_rows: Sum of all entries' estimated rows.
        source: Data source name (e.g. ``"binance"``).
        generated_at: ISO-8601 timestamp of manifest creation.
    """

    manifest_id: str
    dataset_spec: dict[str, Any]
    entries: tuple[DownloadEntry, ...]
    total_entries: int
    total_estimated_rows: int
    source: str
    generated_at: str


# ---------------------------------------------------------------------------
# Interval → seconds lookup (mirrors spec.py)
# ---------------------------------------------------------------------------

_INTERVAL_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
    "3d": 259200,
    "1w": 604800,
    "1mo": 2592000,
}


def _gap_entries_for_spec(
    gaps: list[dict[str, Any]],
    spec: DatasetSpec,
) -> list[DownloadEntry]:
    """Convert raw gap dicts from ``catalog.find_gaps()`` to ``DownloadEntry`` list.

    Uses the spec's smallest interval to estimate row counts.
    """
    min_interval_secs = spec.interval_seconds
    entries: list[DownloadEntry] = []
    for gap in gaps:
        start_ms = int(
            datetime.fromisoformat(gap["gap_start"]).timestamp() * 1000
        )
        end_ms = int(
            datetime.fromisoformat(gap["gap_end"]).timestamp() * 1000
        )
        duration_secs = (end_ms - start_ms) / 1000
        estimated = int(duration_secs // min_interval_secs) if min_interval_secs > 0 else 0
        entries.append(
            DownloadEntry(
                symbol=gap["symbol"],
                interval=gap["interval"],
                data_type=gap["data_type"],
                start_ms=start_ms,
                end_ms=end_ms,
                estimated_rows=estimated,
            )
        )
    return entries


# ---------------------------------------------------------------------------
# BackfillPlanner
# ---------------------------------------------------------------------------


class BackfillPlanner:
    """Planner that converts a ``DatasetSpec`` + ``DataCatalog`` into a
    ``DownloadManifest`` of missing data ranges."""

    @staticmethod
    def plan(spec: DatasetSpec, catalog: DataCatalog) -> DownloadManifest:
        """Produce a ``DownloadManifest`` of data missing from *catalog*.

        Args:
            spec: The dataset specification describing what data is needed.
            catalog: The data catalog to check against.

        Returns:
            A ``DownloadManifest`` with entries for every gap found.
        """
        gaps = catalog.find_gaps(spec)
        entries = _gap_entries_for_spec(gaps, spec)

        total_estimated = sum(e.estimated_rows for e in entries)
        now_iso = datetime.now(timezone.utc).isoformat()

        return DownloadManifest(
            manifest_id=str(uuid4()),
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
            entries=tuple(entries),
            total_entries=len(entries),
            total_estimated_rows=total_estimated,
            source=spec.source,
            generated_at=now_iso,
        )

    @staticmethod
    def estimate_size(manifest: DownloadManifest) -> int:
        """Estimate the download size in bytes.

        Rough heuristic: ~1 KB per 1 000 rows (bars).

        Args:
            manifest: The manifest to estimate.

        Returns:
            Estimated size in bytes (minimum 1).
        """
        total_bars = manifest.total_estimated_rows
        # ~1 KB per 1000 bars
        bytes_estimate = max(1, (total_bars * 1024) // 1000)
        return bytes_estimate


# ---------------------------------------------------------------------------
# Chunking helper
# ---------------------------------------------------------------------------


def chunk_manifest(
    manifest: DownloadManifest,
    chunk_size: int = 50,
) -> list[DownloadManifest]:
    """Split a large ``DownloadManifest`` into smaller chunks.

    Each chunk is a full ``DownloadManifest`` (with its own UUID) containing
    at most *chunk_size* entries.

    Args:
        manifest: The manifest to split.
        chunk_size: Maximum entries per chunk (default 50).

    Returns:
        A list of ``DownloadManifest`` chunks.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    chunks: list[DownloadManifest] = []
    entries = list(manifest.entries)
    spec_dict = copy.deepcopy(manifest.dataset_spec)
    now_iso = datetime.now(timezone.utc).isoformat()

    if not entries:
        # Return a single empty chunk rather than nothing
        return [
            DownloadManifest(
                manifest_id=str(uuid4()),
                dataset_spec=spec_dict,
                entries=(),
                total_entries=0,
                total_estimated_rows=0,
                source=manifest.source,
                generated_at=now_iso,
            )
        ]

    for i in range(0, len(entries), chunk_size):
        chunk_entries = tuple(entries[i : i + chunk_size])
        total_estimated = sum(e.estimated_rows for e in chunk_entries)
        chunks.append(
            DownloadManifest(
                manifest_id=str(uuid4()),
                dataset_spec=spec_dict,
                entries=chunk_entries,
                total_entries=len(chunk_entries),
                total_estimated_rows=total_estimated,
                source=manifest.source,
                generated_at=now_iso,
            )
        )

    return chunks
