"""
DataCatalog — extended catalog with gap analysis.

Extends :class:`lib.market_data.catalog.DataCatalog` with methods
to compare a :class:`DatasetSpec` against ingested entries and
produce gap lists, coverage percentages, and summary metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from lib.market_data.catalog import DataCatalog as BaseCatalog
from lib.data_lake.spec import DatasetSpec


class DataCatalog(BaseCatalog):
    """Extended market-data catalog with gap-analysis methods.

    In addition to the base class methods (``add_entry``, ``query``,
    ``save``, ``load``), provides :meth:`find_gaps`, :meth:`coverage_pct`,
    and :meth:`to_summary` for comparing ingested data against a
    :class:`DatasetSpec`.
    """

    # ------------------------------------------------------------------
    # Gap analysis
    # ------------------------------------------------------------------

    def find_gaps(self, spec: DatasetSpec) -> list[dict[str, Any]]:
        """Return gaps between what *spec* requires and what is catalogued.

        For each (symbol, interval, data_type) triple in *spec*, finds
        time ranges within ``[spec.start, spec.end]`` that are not covered
        by any catalog entry.

        Returns a list of dicts, each with keys:
            symbol, interval, data_type, gap_start, gap_end
        """
        gaps: list[dict[str, Any]] = []
        for symbol in spec.symbols:
            for interval in spec.intervals:
                entries = self.query(
                    symbol=symbol,
                    interval=interval,
                )
                # Sort by start_ts
                sorted_entries = sorted(entries, key=lambda e: e["start_ts"])
                cursor = int(spec.start.timestamp() * 1000)
                end_ms = int(spec.end.timestamp() * 1000)

                for entry in sorted_entries:
                    if entry["start_ts"] > cursor:
                        gaps.append({
                            "symbol": symbol,
                            "interval": interval,
                            "data_type": "klines",  # TODO: per data_type when catalog supports it
                            "gap_start": _ts_to_iso(cursor),
                            "gap_end": _ts_to_iso(entry["start_ts"]),
                        })
                    cursor = max(cursor, entry["end_ts"])

                # Tail gap
                if cursor < end_ms:
                    gaps.append({
                        "symbol": symbol,
                        "interval": interval,
                        "data_type": "klines",
                        "gap_start": _ts_to_iso(cursor),
                        "gap_end": _ts_to_iso(end_ms),
                    })
        return gaps

    # ------------------------------------------------------------------
    # Coverage
    # ------------------------------------------------------------------

    def coverage_pct(self, spec: DatasetSpec) -> float:
        """Return the fraction of the *spec* that is covered, as a percentage.

        Compares actual row counts from catalog entries against the
        expected bar count from *spec*.
        """
        expected = spec.expected_bar_count()
        if expected <= 0:
            return 0.0

        actual = 0
        for symbol in spec.symbols:
            for interval in spec.intervals:
                entries = self.query(symbol=symbol, interval=interval)
                actual += sum(e.get("row_count", 0) for e in entries)

        return min(100.0, round(actual / expected * 100, 2))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def to_summary(self, spec: DatasetSpec) -> dict[str, Any]:
        """Produce a human-readable summary dict for reports."""
        gaps = self.find_gaps(spec)
        return {
            "source": spec.source,
            "market": spec.market,
            "symbols": list(spec.symbols),
            "intervals": list(spec.intervals),
            "data_types": list(spec.data_types),
            "coverage_pct": self.coverage_pct(spec),
            "gap_count": len(gaps),
            "expected_bar_count": spec.expected_bar_count(),
            "backtest_required": spec.backtest_required,
            "allow_synthetic": spec.allow_synthetic,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ts_to_iso(ts_ms: int) -> str:
    """Convert a millisecond timestamp to an ISO-8601 string."""
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
