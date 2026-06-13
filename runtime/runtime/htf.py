"""Shared higher-timeframe mapping for runtime scan and replay paths."""

from __future__ import annotations

HTF_MAP: dict[str, str] = {
    "1m": "5m",
    "5m": "15m",
    "15m": "1h",
    "30m": "4h",
    "1h": "4h",
    "2h": "1d",
    "4h": "1d",
    "6h": "1d",
    "12h": "3d",
    "1d": "7d",
    "3d": "1M",
    "7d": "1M",
    "14d": "1M",
}


def resolve_htf_interval(interval: str | None) -> str | None:
    """Return the configured higher timeframe for a base interval, if any."""
    return HTF_MAP.get(str(interval or "").strip())


__all__ = ["HTF_MAP", "resolve_htf_interval"]
