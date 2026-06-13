"""Calibration readiness summaries for the analyzer feedback loop.

This service intentionally aggregates in Python instead of pushing JSON parsing
into SQL so the same logic works against both SQLite test databases and the
PostgreSQL runtime store.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from runtime.db.repos.signal_repo import SignalRepository
from runtime.db.session import session_scope


class CalibrationStatusService:
    """Summarize how much labeled data exists for probability calibration."""

    def __init__(self, *, calibration_threshold: int = 200) -> None:
        self._signals = SignalRepository()
        self._threshold = calibration_threshold

    def get_status(self, *, limit: int = 5000) -> dict[str, Any]:
        with session_scope() as session:
            signals = self._signals.list_signals(session, limit=limit)

        grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(self._new_bucket)
        total_signals = 0
        total_labeled = 0

        for signal in signals:
            total_signals += 1
            regime = str(signal.get("regime") or "UNKNOWN")
            mode = str(signal.get("mode") or "UNKNOWN")
            features = signal.get("features") or {}
            outcome_label = str(features.get("outcome_label") or "OPEN").upper()
            realized_r = self._to_float(features.get("realized_r"))

            bucket = grouped[(regime, mode)]
            bucket["regime"] = regime
            bucket["mode"] = mode
            bucket["total"] += 1

            if outcome_label != "OPEN":
                total_labeled += 1
                bucket["labeled"] += 1
                if outcome_label == "WIN" and realized_r is not None:
                    bucket["_win_sum"] += realized_r
                    bucket["_win_count"] += 1
                elif outcome_label == "LOSS" and realized_r is not None:
                    bucket["_loss_sum"] += realized_r
                    bucket["_loss_count"] += 1
                if realized_r is not None:
                    bucket["_realized_sum"] += realized_r
                    bucket["_realized_count"] += 1
            else:
                bucket["open"] += 1

        scopes = [self._finalize_bucket(bucket) for bucket in grouped.values()]
        scopes.sort(key=lambda item: (-item["labeled"], -item["total"], item["regime"], item["mode"]))

        ready_scopes = [item for item in scopes if item["ready_for_calibration"]]
        top_scope = scopes[0] if scopes else None

        return {
            "ok": True,
            "summary": {
                "total_signals": total_signals,
                "total_labeled": total_labeled,
                "calibration_threshold": self._threshold,
                "ready_scope_count": len(ready_scopes),
                "top_scope": top_scope,
            },
            "scopes": scopes,
        }

    @staticmethod
    def _new_bucket() -> dict[str, Any]:
        return {
            "regime": "UNKNOWN",
            "mode": "UNKNOWN",
            "total": 0,
            "labeled": 0,
            "open": 0,
            "_win_sum": 0.0,
            "_win_count": 0,
            "_loss_sum": 0.0,
            "_loss_count": 0,
            "_realized_sum": 0.0,
            "_realized_count": 0,
        }

    def _finalize_bucket(self, bucket: dict[str, Any]) -> dict[str, Any]:
        labeled = int(bucket["labeled"])
        remaining = max(0, self._threshold - labeled)
        return {
            "regime": bucket["regime"],
            "mode": bucket["mode"],
            "total": int(bucket["total"]),
            "labeled": labeled,
            "open": int(bucket["open"]),
            "avg_win_r": self._average(bucket["_win_sum"], bucket["_win_count"]),
            "avg_loss_r": self._average(bucket["_loss_sum"], bucket["_loss_count"]),
            "avg_realized_r": self._average(bucket["_realized_sum"], bucket["_realized_count"]),
            "ready_for_calibration": labeled >= self._threshold,
            "remaining_to_threshold": remaining,
        }

    @staticmethod
    def _average(total: float, count: int) -> float | None:
        if count <= 0:
            return None
        return round(total / count, 6)

    @staticmethod
    def _to_float(value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
