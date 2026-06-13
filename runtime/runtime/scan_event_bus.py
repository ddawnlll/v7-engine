"""In-process scan event bus for runtime observability.

This bus mirrors runtime events for WebSocket clients only. Runtime state,
repositories, and traces remain the source of truth.
"""

from __future__ import annotations

from datetime import datetime, timezone
from queue import Full, Queue
from threading import Lock
from typing import Any

PAPER_PROFILE_ID = "paper-main"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ScanEventBus:
    def __init__(self, *, max_recent: int = 250, subscriber_queue_size: int = 500) -> None:
        self.max_recent = max(0, int(max_recent))
        self.subscriber_queue_size = max(1, int(subscriber_queue_size))
        self._lock = Lock()
        self._subscribers: list[tuple[str, str | None, Queue]] = []
        self._recent: list[dict[str, Any]] = []

    def publish(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Publish an event without allowing delivery failures to escape."""
        try:
            payload = self._normalize_event(event)
            with self._lock:
                if self.max_recent:
                    self._recent.append(payload)
                    if len(self._recent) > self.max_recent:
                        del self._recent[: len(self._recent) - self.max_recent]
                subscribers = list(self._subscribers)
            for profile_id, run_id, queue in subscribers:
                if payload["profile_id"] != profile_id:
                    continue
                if run_id is not None and payload["run_id"] != run_id:
                    continue
                self._put_nonblocking(queue, payload)
            return payload
        except Exception:
            return None

    def subscribe(self, *, profile_id: str, run_id: str | None = None) -> Queue:
        resolved_profile_id = str(profile_id or PAPER_PROFILE_ID)
        resolved_run_id = str(run_id).strip() if run_id is not None and str(run_id).strip() else None
        queue: Queue = Queue(maxsize=self.subscriber_queue_size)
        with self._lock:
            self._subscribers.append((resolved_profile_id, resolved_run_id, queue))
            recent = [event for event in self._recent if event.get("profile_id") == resolved_profile_id and (resolved_run_id is None or event.get("run_id") == resolved_run_id)]
        for event in recent:
            self._put_nonblocking(queue, event)
        return queue

    def unsubscribe(self, queue: Queue) -> None:
        with self._lock:
            self._subscribers = [item for item in self._subscribers if item[2] is not queue]

    def _normalize_event(self, event: dict[str, Any]) -> dict[str, Any]:
        payload = dict(event or {})
        event_type = str(payload.get("type") or "").strip().upper()
        if not event_type:
            raise ValueError("scan event type is required")
        profile_id = str(payload.get("profile_id") or PAPER_PROFILE_ID).strip()
        run_id = str(payload.get("run_id") or "").strip()
        if not profile_id or not run_id:
            raise ValueError("scan events require profile_id and run_id")
        payload["type"] = event_type
        payload["timestamp"] = str(payload.get("timestamp") or utc_now_iso())
        payload["profile_id"] = profile_id
        payload["run_id"] = run_id
        return payload

    @staticmethod
    def _put_nonblocking(queue: Queue, event: dict[str, Any]) -> None:
        try:
            queue.put_nowait(event)
            return
        except Full:
            pass
        except Exception:
            return
        try:
            queue.get_nowait()
            queue.put_nowait(event)
        except Exception:
            return


_SHARED_SCAN_EVENT_BUS = ScanEventBus()


def get_scan_event_bus() -> ScanEventBus:
    return _SHARED_SCAN_EVENT_BUS
