"""Tests for canonical timestamp normalization.

Coverage checklist:
 1. Unix ms int
 2. Unix sec int
 3. Unix ms numeric string
 4. Unix sec numeric string
 5. ISO Z
 6. timezone offset
 7. numpy integer
 8. malformed string fail-fast
 9. zero/negative timestamp fail-fast
"""

from __future__ import annotations

import datetime

import numpy as np
import pytest

from simulation.engine.time import (
    normalize_timestamp_ms,
    normalize_timestamp_iso,
    _SEC_MS_THRESHOLD,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

# Unix epoch 2024-06-15T12:30:00.000Z in ms
TS_MS = 1_718_454_600_000  # computed from datetime(2024,6,15,12,30, tzinfo=utc)
TS_SEC = 1_718_454_600


class TestNormalizeTimestampMs:
    """Canonical ms normalization — all input formats."""

    # 1. Unix ms int
    def test_unix_ms_int(self) -> None:
        assert normalize_timestamp_ms(TS_MS) == TS_MS

    # 2. Unix sec int
    def test_unix_sec_int(self) -> None:
        assert normalize_timestamp_ms(TS_SEC) == TS_MS

    # 3. Unix ms numeric string
    def test_unix_ms_numeric_string(self) -> None:
        assert normalize_timestamp_ms(str(TS_MS)) == TS_MS

    # 4. Unix sec numeric string
    def test_unix_sec_numeric_string(self) -> None:
        assert normalize_timestamp_ms(str(TS_SEC)) == TS_MS

    # 5. ISO Z
    def test_iso_z(self) -> None:
        assert normalize_timestamp_ms("2024-06-15T12:30:00Z") == TS_MS

    # 6. Timezone offset
    def test_iso_timezone_offset(self) -> None:
        # +02:00 offset → 10:30 local = 08:30 UTC
        expected = TS_MS - 4 * 3_600_000  # 4 hours earlier than 12:30 UTC
        assert normalize_timestamp_ms("2024-06-15T10:30:00+02:00") == expected

    # 7. Numpy integer
    def test_numpy_int64(self) -> None:
        assert normalize_timestamp_ms(np.int64(TS_MS)) == TS_MS

    def test_numpy_int32(self) -> None:
        assert normalize_timestamp_ms(np.int32(TS_SEC)) == TS_MS

    # 8. Malformed string fail-fast
    def test_malformed_string_raises(self) -> None:
        for bad in ("", "not-a-timestamp", "2024/06/15", "abc123"):
            with pytest.raises(ValueError, match="cannot parse|empty"):
                normalize_timestamp_ms(bad)

    def test_none_raises(self) -> None:
        with pytest.raises(ValueError, match="None"):
            normalize_timestamp_ms(None)

    def test_boolean_raises(self) -> None:
        with pytest.raises(ValueError, match="boolean"):
            normalize_timestamp_ms(True)

    # 9. Zero/negative timestamp fail-fast
    def test_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="non-positive"):
            normalize_timestamp_ms(0)

    def test_negative_int_raises(self) -> None:
        with pytest.raises(ValueError, match="non-positive"):
            normalize_timestamp_ms(-100)

    def test_negative_float_raises(self) -> None:
        with pytest.raises(ValueError, match="non-positive"):
            normalize_timestamp_ms(-1.0)

    def test_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="NaN"):
            normalize_timestamp_ms(float("nan"))

    def test_inf_raises(self) -> None:
        with pytest.raises(ValueError, match="infinite"):
            normalize_timestamp_ms(float("inf"))

    # ── Deterministic threshold ─────────────────────────────────────────
    def test_threshold_boundary_seconds(self) -> None:
        """Value exactly at threshold is interpreted as seconds."""
        # _SEC_MS_THRESHOLD = 1_000_000_000_000 → as seconds = 1e12 * 1000 ms
        assert normalize_timestamp_ms(_SEC_MS_THRESHOLD) == _SEC_MS_THRESHOLD * 1000
        # One less → still seconds
        assert normalize_timestamp_ms(_SEC_MS_THRESHOLD - 1) == (_SEC_MS_THRESHOLD - 1) * 1000

    def test_threshold_boundary_milliseconds(self) -> None:
        """Value above threshold is interpreted as ms."""
        assert normalize_timestamp_ms(_SEC_MS_THRESHOLD + 1) == _SEC_MS_THRESHOLD + 1

    # ── Float seconds ───────────────────────────────────────────────────
    def test_float_seconds(self) -> None:
        assert normalize_timestamp_ms(TS_SEC * 1.0) == TS_MS

    def test_float_fractional_seconds(self) -> None:
        """Float with fractional part (e.g. TS_SEC + 0.5) → ms."""
        result = normalize_timestamp_ms(TS_SEC + 0.5)
        assert result == TS_MS + 500  # 0.5 sec = 500 ms

    # ── ISO with fractional seconds ─────────────────────────────────────
    def test_iso_with_milliseconds(self) -> None:
        assert normalize_timestamp_ms("2024-06-15T12:30:00.123Z") == TS_MS + 123

    # ── String with whitespace ──────────────────────────────────────────
    def test_strip_whitespace(self) -> None:
        assert normalize_timestamp_ms(f"  {TS_MS}  ") == TS_MS


class TestNormalizeTimestampIso:
    """ISO-8601 formatting."""

    def test_roundtrip_ms(self) -> None:
        iso = normalize_timestamp_iso(TS_MS)
        assert iso.endswith("Z")
        # Re-parse should give same ms
        assert normalize_timestamp_ms(iso) == TS_MS

    def test_roundtrip_sec(self) -> None:
        iso = normalize_timestamp_iso(TS_SEC)
        assert normalize_timestamp_ms(iso) == TS_MS

    def test_roundtrip_iso(self) -> None:
        iso = normalize_timestamp_iso("2024-06-15T12:30:00Z")
        assert normalize_timestamp_ms(iso) == TS_MS
