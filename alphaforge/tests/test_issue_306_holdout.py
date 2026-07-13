"""Behavioral tests for #306: holdout cutoff split correctness.

Tests ``alphaforge.discovery.pipeline.compute_holdout_split()`` directly.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from alphaforge.discovery.pipeline import compute_holdout_split


def _ms_timestamps(start_date: str, n: int, interval_hours: int = 1) -> np.ndarray:
    """Generate millisecond Unix timestamps from *start_date*, spaced *interval_hours* apart."""
    start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
    base_ms = int(start.timestamp() * 1000)
    step_ms = interval_hours * 3600 * 1000
    return np.array([base_ms + i * step_ms for i in range(n)], dtype=np.int64)


class TestComputeHoldoutSplit:
    """Tests for the extracted holdout split helper (Issue #306)."""

    def test_split_at_boundary(self):
        """Rows on/after cutoff are holdout; rows before are train."""
        ts = _ms_timestamps("2026-01-01", 100)  # hour 0..99 from Jan 1
        cutoff = "2026-01-03"  # 48 hours in
        mask = compute_holdout_split(ts, cutoff)
        assert mask is not None
        assert mask.dtype == bool
        assert mask.shape == (100,)
        # First 48 rows are before cutoff (Jan 1 00:00 + 47h = Jan 2 23:00)
        assert mask[:48].sum() == 0, "Rows before cutoff must be train"
        # Rows from index 48 onward are on/after cutoff
        assert mask[48:].sum() == 52, "Rows on/after cutoff must be holdout"

    def test_holdout_strictly_after_cutoff(self):
        """No holdout row has timestamp < cutoff."""
        ts = _ms_timestamps("2026-04-01", 200, interval_hours=1)
        cutoff = "2026-04-07"
        mask = compute_holdout_split(ts, cutoff)
        assert mask is not None
        holdout_ts = ts[mask]
        cutoff_ts = int(
            datetime.fromisoformat(cutoff).replace(tzinfo=timezone.utc).timestamp() * 1000
        )
        assert (holdout_ts >= cutoff_ts).all(), (
            "All holdout rows must be >= cutoff"
        )

    def test_train_strictly_before_cutoff(self):
        """No train row has timestamp >= cutoff."""
        ts = _ms_timestamps("2026-02-01", 100, interval_hours=1)
        cutoff = "2026-02-04"
        mask = compute_holdout_split(ts, cutoff)
        assert mask is not None
        train_ts = ts[~mask]
        cutoff_ts = int(
            datetime.fromisoformat(cutoff).replace(tzinfo=timezone.utc).timestamp() * 1000
        )
        assert (train_ts < cutoff_ts).all(), (
            "All train rows must be < cutoff"
        )

    def test_insufficient_holdout_returns_none(self):
        """When fewer than min_holdout_rows fall after cutoff, returns None."""
        ts = _ms_timestamps("2026-06-01", 10)  # only 10 rows
        cutoff = "2026-06-01"  # all 10 are on/after
        mask = compute_holdout_split(ts, cutoff, min_holdout_rows=50)
        assert mask is None

    def test_empty_array_returns_none(self):
        """Empty timestamp array returns None."""
        ts = np.array([], dtype=np.int64)
        mask = compute_holdout_split(ts, "2026-01-01")
        assert mask is None

    def test_invalid_date_returns_none(self):
        """Invalid cutoff date string returns None, doesn't crash."""
        ts = np.array([1_000_000], dtype=np.int64)
        mask = compute_holdout_split(ts, "not-a-date")
        assert mask is None

    def test_nanosecond_timestamps(self):
        """Nanosecond timestamps are handled correctly (1e15+)."""
        # Nanosecond timestamps for Jan 2026
        ns_base = int(
            datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1_000_000_000
        )
        step_ns = 3600 * 1_000_000_000  # 1 hour in ns
        ts = np.array([ns_base + i * step_ns for i in range(100)], dtype=np.int64)
        assert abs(ts[0]) > 1e15, "Must be nanosecond range"
        cutoff = "2026-01-03"
        mask = compute_holdout_split(ts, cutoff)
        assert mask is not None
        # First 48 rows are before cutoff (Jan 1 00:00 + 47h)
        assert mask[:48].sum() == 0
        assert mask[48:].sum() > 0

    def test_cutoff_at_first_timestamp(self):
        """Cutoff same as first timestamp puts everything in holdout."""
        ts = _ms_timestamps("2026-03-15", 200)
        cutoff = "2026-03-15"
        mask = compute_holdout_split(ts, cutoff)
        assert mask is not None
        assert mask.all(), "All rows should be holdout when cutoff equals first timestamp"
