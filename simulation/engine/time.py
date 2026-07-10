"""Canonical timestamp normalization for simulation pipeline.

Single shared authority for converting timestamps into UTC milliseconds
and ISO-8601 strings.  Every pipeline stage (engine, data loader, resolver,
adapter) uses this module — no ad-hoc parsers anywhere.

Supported input types
---------------------
- ``int``: Unix milliseconds
- ``float``: Unix seconds (detected via deterministic threshold)
- ``numpy.integer``: any numpy int type
- ``str`` numeric: Unix milliseconds or seconds (detected via threshold)
- ``str`` ISO-8601: ``2026-07-10T12:00:00Z`` or with timezone offset
- ``datetime``: naive (treated as UTC — logged) or timezone-aware

Deterministic threshold
-----------------------
A numeric value <= 1 000 000 000 000 (year 2001-09-09) is interpreted as
**seconds**; a value larger is **milliseconds**.  This is the same heuristic
used by pandas Timestamp and ensures the same physical instant always maps
to the same UTC result regardless of input shape.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Union

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Values <= this threshold are interpreted as Unix **seconds**; larger values
#: as **milliseconds**.  1e12 corresponds to 2001-09-09T01:46:40 UTC.
_SEC_MS_THRESHOLD: int = 1_000_000_000_000

#: ISO-8601 suffix for UTC.
_ISO_SUFFIX_Z = "Z"

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_timestamp_ms(value: object) -> int:
    """Normalise *value* to UTC milliseconds.

    Parameters
    ----------
    value : object
        One of the supported input types listed in the module docstring.

    Returns
    -------
    int
        UTC timestamp in milliseconds.

    Raises
    ------
    ValueError
        If *value* cannot be interpreted as a valid timestamp, is negative,
        or is exactly zero (Unix epoch is ambiguous for our domain).
    """
    if value is None:
        raise ValueError("timestamp value is None")
    if isinstance(value, bool):
        raise ValueError(f"boolean timestamp: {value!r}")
    # --- int / numpy integer ---
    if isinstance(value, (int, np.integer)):
        return _normalize_numeric(int(value))
    # --- float ---
    if isinstance(value, float):
        return _normalize_numeric(value)
    # --- str ---
    if isinstance(value, str):
        return _normalize_str(value)
    # --- datetime ---
    if isinstance(value, datetime):
        return _normalize_datetime(value)
    raise ValueError(
        f"unsupported timestamp type: {type(value).__name__} ({value!r})"
    )


def normalize_timestamp_iso(value: object) -> str:
    """Normalise *value* to UTC ISO-8601 string.

    Convenience wrapper around :func:`normalize_timestamp_ms` that formats
    the result as ``'2026-07-10T12:00:00.000Z'``.

    Parameters
    ----------
    value : object
        Any type accepted by :func:`normalize_timestamp_ms`.

    Returns
    -------
    str
        UTC ISO-8601 string with milliseconds and ``Z`` suffix.
    """
    ms = normalize_timestamp_ms(value)
    return _ms_to_iso(ms)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_numeric(value: Union[int, float]) -> int:
    """Convert a numeric value (int or float) to ms."""
    if not isinstance(value, (int, float)):
        raise ValueError(f"expected numeric, got {type(value).__name__}")
    if value <= 0:
        raise ValueError(f"non-positive timestamp: {value}")
    if isinstance(value, float) and value != value:  # NaN
        raise ValueError("NaN timestamp")
    if isinstance(value, float) and value == float("inf"):
        raise ValueError("infinite timestamp")
    # Apply sec/ms threshold
    if value <= _SEC_MS_THRESHOLD:
        # Interpret as seconds -> milliseconds
        ms = int(value * 1000)
    else:
        ms = int(value)
    return ms


def _normalize_str(value: str) -> int:
    """Convert a string to ms."""
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"empty/timestamp string: {value!r}")

    # Try numeric interpretation first (no decimal point = ms or sec)
    try:
        numeric = int(stripped)
        return _normalize_numeric(numeric)
    except ValueError:
        pass

    # Try float numeric (e.g. "1700000000.5")
    try:
        numeric = float(stripped)
        return _normalize_numeric(numeric)
    except ValueError:
        pass

    # Try ISO-8601
    try:
        dt = _parse_iso(value)
        return _datetime_to_ms(dt)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"cannot parse timestamp string: {value!r} — {exc}"
        ) from exc


def _normalize_datetime(value: datetime) -> int:
    """Convert a datetime to ms."""
    if value.tzinfo is None:
        logger.warning(
            "naive datetime %s treated as UTC", value.isoformat()
        )
        value = value.replace(tzinfo=timezone.utc)
    return _datetime_to_ms(value)


def _parse_iso(value: str) -> datetime:
    """Parse ISO-8601 string, handling the Z suffix."""
    cleaned = value.replace("Z", "+00:00")
    # Handle fractional seconds with more than 6 digits
    # Python's fromisoformat is strict; strip extra precision
    if "." in cleaned:
        before, after = cleaned.split(".", 1)
        # Keep up to 6 digits + potential trailing Z/timezone
        frac_part = "".join(c for c in after if c.isdigit())[:6]
        # Reconstruct with cleaned fractional part
        # But we need to preserve the timezone offset after the fraction
        tz_part = ""
        for c in after[len(frac_part) if frac_part else 0:]:
            if c in "+-":
                tz_part = after[len(frac_part):]
                break
            if c == "Z":
                tz_part = ""
                break
        cleaned = f"{before}.{frac_part}{tz_part}"
    return datetime.fromisoformat(cleaned)


def _datetime_to_ms(dt: datetime) -> int:
    """Convert an aware datetime to UTC milliseconds."""
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    total_seconds = (dt - epoch).total_seconds()
    if total_seconds <= 0:
        raise ValueError(f"timestamp at or before Unix epoch: {dt}")
    return int(total_seconds * 1000)


def _ms_to_iso(ms: int) -> str:
    """Format UTC milliseconds as ISO-8601 string."""
    seconds = ms / 1000.0
    dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
    # Format with milliseconds
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"
