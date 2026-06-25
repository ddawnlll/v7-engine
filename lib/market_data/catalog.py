"""
Data catalog tracking what market data has been ingested.

Maintains a JSON catalog file per data directory recording
ingested symbol/interval/time ranges with row counts and
checksums for auditability.
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class DataCatalog:
    """Persistent catalog of ingested market data.

    Catalog file format (JSON):
    {
        "entries": [
            {
                "symbol": "BTCUSDT",
                "interval": "1h",
                "start_ts": 1700000000000,
                "end_ts": 1700036000000,
                "row_count": 1000,
                "checksum": "abc123...",
                "ingested_at": "2026-01-01T00:00:00"
            },
            ...
        ]
    }
    """

    def __init__(self, catalog_path: str = "data/catalog.json") -> None:
        """Initialize data catalog.

        Args:
            catalog_path: Path to the catalog JSON file.
        """
        self._catalog_path = catalog_path
        self._entries: list[dict] = []
        self._load()

    def add_entry(
        self,
        symbol: str,
        interval: str,
        start_ts: int,
        end_ts: int,
        row_count: int,
        checksum: str,
    ) -> None:
        """Add a catalog entry for an ingested data file."""
        entry = {
            "symbol": symbol.upper(),
            "interval": interval,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "row_count": row_count,
            "checksum": checksum,
            "ingested_at": datetime.utcnow().isoformat(),
        }
        self._entries.append(entry)
        logger.info(
            "Catalog entry: %s %s [%d, %d) %d rows",
            entry["symbol"], entry["interval"],
            entry["start_ts"], entry["end_ts"], entry["row_count"],
        )

    def query(
        self,
        symbol: Optional[str] = None,
        interval: Optional[str] = None,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
    ) -> list[dict]:
        """Query catalog entries with optional filters.

        All filters are AND-ed.  Time filters are inclusive of
        ``start_ts`` and exclusive of ``end_ts``.
        """
        results = list(self._entries)
        if symbol is not None:
            results = [e for e in results if e["symbol"] == symbol.upper()]
        if interval is not None:
            results = [e for e in results if e["interval"] == interval]
        if start_ts is not None:
            results = [e for e in results if e["start_ts"] >= start_ts]
        if end_ts is not None:
            results = [e for e in results if e["end_ts"] <= end_ts]
        return results

    def save(self) -> None:
        """Persist catalog to disk."""
        dir_path = os.path.dirname(self._catalog_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        with open(self._catalog_path, "w") as f:
            json.dump({"entries": self._entries}, f, indent=2, sort_keys=True)

    def load(self) -> None:
        """Reload catalog from disk."""
        self._load()

    def _load(self) -> None:
        """Load catalog entries from the JSON file."""
        if not os.path.exists(self._catalog_path):
            self._entries = []
            return
        try:
            with open(self._catalog_path, "r") as f:
                data = json.load(f)
            self._entries = data.get("entries", [])
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read catalog %s: %s", self._catalog_path, e)
            self._entries = []

    def clear(self) -> None:
        """Clear all entries (for testing)."""
        self._entries = []
