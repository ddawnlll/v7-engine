"""
Interval conversion utilities.

Shared by both v7/ and alphaforge/ for time-related operations.
"""

from typing import Optional

_INTERVAL_TO_MINUTES: dict[str, int] = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "6h": 360, "8h": 480, "12h": 720,
    "1d": 1440, "3d": 4320, "1w": 10080,
}

_MINUTES_TO_INTERVAL: dict[int, str] = {v: k for k, v in _INTERVAL_TO_MINUTES.items()}

VALID_INTERVALS: set[str] = set(_INTERVAL_TO_MINUTES.keys())


def interval_to_minutes(interval: str) -> int:
    """Convert interval string to minutes.

    Args:
        interval: e.g. "1m", "15m", "1h", "4h", "1d".

    Returns:
        Number of minutes.

    Raises:
        ValueError: If interval is unknown.
    """
    if interval not in _INTERVAL_TO_MINUTES:
        raise ValueError(f"Unknown interval: {interval!r}. Valid: {sorted(VALID_INTERVALS)}")
    return _INTERVAL_TO_MINUTES[interval]


def minutes_to_interval(minutes: int) -> Optional[str]:
    """Convert minutes to nearest interval string.

    Args:
        minutes: Number of minutes.

    Returns:
        Interval string or None if no match.
    """
    return _MINUTES_TO_INTERVAL.get(minutes)


def validate_interval(interval: str) -> bool:
    """Check if an interval string is valid."""
    return interval in _INTERVAL_TO_MINUTES
