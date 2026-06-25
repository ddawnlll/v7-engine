"""
Checkpoint save/resume for backfill operations.

Checkpoints allow resumption of interrupted backfills by recording
which (symbol, interval, time_range) combinations have been completed.
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class BackfillCheckpoint:
    """Persistent checkpoint for tracking backfill completion.

    File format (JSON):
    {
        "BTCUSDT_1h": {
            "completed_ranges": [
                {"start": 1700000000000, "end": 1700036000000}
            ]
        },
        ...
    }
    """

    def __init__(self, file_path: str = "checkpoints/backfill_checkpoint.json") -> None:
        """Initialize checkpoint storage.

        Args:
            file_path: Path to the checkpoint JSON file.
        """
        self._file_path = file_path

    def save(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
        completed_ranges: list[dict[str, int]],
    ) -> None:
        """Save checkpoint entry for a symbol/interval/time range.

        Args:
            symbol: Trading pair symbol (e.g. "BTCUSDT").
            interval: Kline interval (e.g. "1h").
            start_time: Start of backfill range (ms timestamp).
            end_time: End of backfill range (ms timestamp).
            completed_ranges: List of {start, end} dicts for completed slices.
        """
        data = self.load()
        key = self._make_key(symbol, interval)
        data[key] = {
            "symbol": symbol,
            "interval": interval,
            "start_time": start_time,
            "end_time": end_time,
            "completed_ranges": completed_ranges,
        }
        self._write(data)

    def load(self) -> dict:
        """Load checkpoint data from disk.

        Returns:
            Dictionary of checkpoint entries keyed by symbol_interval.
            Empty dict if file does not exist or is corrupt.
        """
        if not os.path.exists(self._file_path):
            return {}

        try:
            with open(self._file_path, "r") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                logger.warning("Checkpoint file is not a dict, resetting.")
                return {}
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read checkpoint file %s: %s", self._file_path, e)
            return {}

    def is_completed(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
    ) -> bool:
        """Check if a symbol/interval/time range has been fully backfilled.

        The range is considered completed if there is an existing checkpoint
        whose time range fully covers [start_time, end_time).
        """
        data = self.load()
        key = self._make_key(symbol, interval)
        entry = data.get(key)
        if not entry:
            return False
        cp_start = entry.get("start_time", 0)
        cp_end = entry.get("end_time", 0)
        return cp_start <= start_time and cp_end >= end_time

    def remove(self, symbol: str, interval: str) -> None:
        """Remove a checkpoint entry (for testing or re-backfill)."""
        data = self.load()
        key = self._make_key(symbol, interval)
        data.pop(key, None)
        self._write(data)

    def _make_key(self, symbol: str, interval: str) -> str:
        return f"{symbol.upper()}_{interval}"

    def _write(self, data: dict) -> None:
        dir_path = os.path.dirname(self._file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        with open(self._file_path, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
