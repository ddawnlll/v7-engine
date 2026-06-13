"""Assess whether component attribution backfill is trustworthy enough for analytics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from runtime.db.models import TradeComponentOutcome
from runtime.db.session import session_scope


def _lookback_start(lookback_days: int | None) -> str | None:
    if lookback_days is None or int(lookback_days) <= 0:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=int(lookback_days))).isoformat()


class AttributionIntegrityService:
    def evaluate(self, *, lookback_days: int = 30) -> dict[str, Any]:
        with session_scope() as session:
            return self._evaluate_session(session, lookback_days=lookback_days)

    def _evaluate_session(self, session: Session, *, lookback_days: int = 30) -> dict[str, Any]:
        query = session.query(TradeComponentOutcome)
        date_from = _lookback_start(lookback_days)
        if date_from:
            query = query.filter(TradeComponentOutcome.created_at_utc >= date_from)
        rows = query.all()
        total_rows = len(rows)
        with_outcome = sum(1 for row in rows if row.realized_r is not None)
        missing_outcome = total_rows - with_outcome
        coverage_ratio = (with_outcome / total_rows) if total_rows else 1.0
        if total_rows == 0:
            status = "NO_DATA"
            summary = "No component attribution outcome rows in the selected window."
        elif missing_outcome == 0:
            status = "HEALTHY"
            summary = "Component attribution outcome backfill is complete for the selected window."
        elif coverage_ratio >= 0.85:
            status = "PARTIAL"
            summary = "Component attribution outcome backfill is incomplete; analytics remain provisional."
        else:
            status = "BROKEN"
            summary = "Component attribution outcome coverage is too low to trust component-level conclusions."
        return {
            "status": status,
            "summary": summary,
            "lookback_days": int(lookback_days),
            "total_component_rows": total_rows,
            "rows_with_outcomes": with_outcome,
            "rows_missing_outcomes": missing_outcome,
            "coverage_ratio": round(coverage_ratio, 4),
            "healthy": status == "HEALTHY",
            "provisional": status in {"PARTIAL", "BROKEN", "NO_DATA"},
        }

