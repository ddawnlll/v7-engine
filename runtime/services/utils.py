"""
Shared utility helpers used across the application.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def interval_minutes(interval: str) -> int:
    if not interval:
        return 60
    raw = str(interval).strip()
    if raw == "1M" or raw.lower() in {"1mo", "1month"}:
        return 43200
    suffix = raw[-1].lower()
    value = raw[:-1]
    if not value.isdigit():
        return 60
    amount = int(value)
    if suffix == "m":
        return amount
    if suffix == "h":
        return amount * 60
    if suffix == "d":
        return amount * 1440
    if suffix == "w":
        return amount * 10080
    return 60
