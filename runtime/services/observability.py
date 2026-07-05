"""
Observability utilities: structured logging helpers and lightweight metrics.

Provides:
- log_event: structured event logging
- MetricsCollector: thread-safe in-memory metrics (counters, gauges, timers)
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Structured event logging
# ---------------------------------------------------------------------------


def log_event(event: str, **fields: Any) -> None:
    """Emit a structured JSON event to stdout.

    Args:
        event: Event name (e.g. ``'circuit_breaker_opened'``).
        **fields: Arbitrary key-value pairs to include.
    """
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "pid": os.getpid(),
    }
    payload.update(fields)
    sys.stdout.write(json.dumps(payload, ensure_ascii=True) + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Metrics collector
# ---------------------------------------------------------------------------


class MetricsCollector:
    """Thread-safe in-memory metrics collector.

    Supports counters (monotonically increasing), gauges (point-in-time
    values), and timers (duration distributions).
    Metrics are process-local and reset on restart.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._timers: dict[str, list[float]] = defaultdict(list)

    def increment(self, name: str, value: int = 1, tags: dict[str, str] | None = None) -> None:
        """Increment a counter.

        Args:
            name: Counter name (e.g. ``'scans.total'``).
            value: Amount to increment by (default 1).
            tags: Optional tags appended as key=value suffixes.
        """
        key = self._key_with_tags(name, tags)
        with self._lock:
            self._counters[key] += value

    def gauge(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Set a gauge value.

        Args:
            name: Gauge name (e.g. ``'db.connection_pool_size'``).
            value: Current value.
            tags: Optional tags.
        """
        key = self._key_with_tags(name, tags)
        with self._lock:
            self._gauges[key] = value

    def record_timing(self, name: str, duration_seconds: float, tags: dict[str, str] | None = None) -> None:
        """Record a timing measurement.

        Args:
            name: Timer name (e.g. ``'request.duration'``).
            duration_seconds: Duration in seconds.
            tags: Optional tags.
        """
        key = self._key_with_tags(name, tags)
        with self._lock:
            self._timers[key].append(duration_seconds)

    @contextmanager
    def timer(self, name: str, tags: dict[str, str] | None = None):
        """Context manager recording execution duration.

        Usage::

            with metrics.timer('request.process'):
                do_something()
        """
        start = time.monotonic()
        try:
            yield
        finally:
            duration = time.monotonic() - start
            self.record_timing(name, duration, tags=tags)

    def snapshot(self) -> dict[str, Any]:
        """Snapshot of all current metrics.

        Returns:
            Dict with ``'counters'``, ``'gauges'``, and ``'timers'`` keys.
            Timer values include count, sum, avg, min, max.
        """
        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            timers_snap: dict[str, dict[str, float]] = {}
            for name, values in self._timers.items():
                if values:
                    timers_snap[name] = {
                        "count": len(values),
                        "sum": round(sum(values), 4),
                        "avg": round(sum(values) / len(values), 4),
                        "min": round(min(values), 4),
                        "max": round(max(values), 4),
                    }
                else:
                    timers_snap[name] = {"count": 0, "sum": 0.0, "avg": 0.0, "min": 0.0, "max": 0.0}
        return {
            "counters": dict(sorted(counters.items())),
            "gauges": dict(sorted(gauges.items())),
            "timers": dict(sorted(timers_snap.items())),
        }

    def reset(self) -> None:
        """Reset all metrics (testing / clean-up)."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._timers.clear()

    @staticmethod
    def _key_with_tags(name: str, tags: dict[str, str] | None) -> str:
        if not tags:
            return name
        tag_parts = [f"{k}={v}" for k, v in sorted(tags.items())]
        return f"{name}[{','.join(tag_parts)}]"


# Module-level singleton
_metrics: MetricsCollector | None = None
_metrics_lock = threading.Lock()


def get_metrics() -> MetricsCollector:
    """Get the module-level MetricsCollector singleton."""
    global _metrics
    if _metrics is None:
        with _metrics_lock:
            if _metrics is None:
                _metrics = MetricsCollector()
    return _metrics
