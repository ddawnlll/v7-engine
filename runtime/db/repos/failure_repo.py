"""Trade failure repository for v4."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from runtime.db.models import TradeFailure
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID


class FailureRepository:
    def save_failure(self, session: Session, payload: dict) -> dict:
        payload = {**payload, "profile_id": str(payload.get("profile_id") or PAPER_PROFILE_ID)}
        row = (
            session.query(TradeFailure)
            .filter(TradeFailure.order_id == payload["order_id"])
            .filter(TradeFailure.profile_id == payload["profile_id"])
            .one_or_none()
        )
        if row is None:
            row = TradeFailure(**payload)
            session.add(row)
        else:
            for key, value in payload.items():
                setattr(row, key, value)
        session.commit()
        return self._to_dict(row)

    def get_failures_for_order(self, session: Session, order_id: str, profile_id: str = PAPER_PROFILE_ID) -> list[dict]:
        rows = (
            session.query(TradeFailure)
            .filter(TradeFailure.order_id == order_id)
            .filter(TradeFailure.profile_id == profile_id)
            .order_by(TradeFailure.created_at_utc.desc())
            .all()
        )
        return [self._to_dict(row) for row in rows]

    def list_recent_failures(self, session: Session, limit: int = 100, profile_id: str = PAPER_PROFILE_ID) -> list[dict]:
        rows = (
            session.query(TradeFailure)
            .filter(TradeFailure.profile_id == profile_id)
            .order_by(TradeFailure.created_at_utc.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(row) for row in rows]

    def list_failures_by_source(self, session: Session, failure_source: str, limit: int = 100, profile_id: str = PAPER_PROFILE_ID) -> list[dict]:
        rows = (
            session.query(TradeFailure)
            .filter(TradeFailure.profile_id == profile_id)
            .filter(TradeFailure.failure_source == failure_source)
            .order_by(TradeFailure.created_at_utc.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(row) for row in rows]

    def list_failures_by_component(self, session: Session, blamed_component: str, limit: int = 100, profile_id: str = PAPER_PROFILE_ID) -> list[dict]:
        rows = (
            session.query(TradeFailure)
            .filter(TradeFailure.profile_id == profile_id)
            .filter(TradeFailure.blamed_component == blamed_component)
            .order_by(TradeFailure.created_at_utc.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(row) for row in rows]

    def list_failures(
        self,
        session: Session,
        *,
        limit: int = 100,
        offset: int = 0,
        failure_source: str | None = None,
        blamed_component: str | None = None,
        severity_score: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> tuple[list[dict], int]:
        query = session.query(TradeFailure).filter(TradeFailure.profile_id == profile_id)
        query = self._apply_filters(
            query,
            failure_source=failure_source,
            blamed_component=blamed_component,
            severity_score=severity_score,
            date_from=date_from,
            date_to=date_to,
        )
        total = query.count()
        rows = (
            query.order_by(TradeFailure.created_at_utc.desc())
            .offset(max(0, offset))
            .limit(limit)
            .all()
        )
        return [self._to_dict(row) for row in rows], total

    def get_failure_for_order(self, session: Session, order_id: str, profile_id: str = PAPER_PROFILE_ID) -> dict | None:
        row = (
            session.query(TradeFailure)
            .filter(TradeFailure.order_id == order_id)
            .filter(TradeFailure.profile_id == profile_id)
            .one_or_none()
        )
        return self._to_dict(row) if row is not None else None

    def get_summary(
        self,
        session: Session,
        *,
        failure_source: str | None = None,
        blamed_component: str | None = None,
        severity_score: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict:
        query = session.query(TradeFailure).filter(TradeFailure.profile_id == profile_id)
        query = self._apply_filters(
            query,
            failure_source=failure_source,
            blamed_component=blamed_component,
            severity_score=severity_score,
            date_from=date_from,
            date_to=date_to,
        )

        rows = query.all()
        counts_by_source: dict[str, int] = {}
        counts_by_component: dict[str, int] = {}
        top_weakness: dict | None = None

        for row in rows:
            counts_by_source[row.failure_source] = counts_by_source.get(row.failure_source, 0) + 1
            counts_by_component[row.blamed_component] = counts_by_component.get(row.blamed_component, 0) + 1

        if rows:
            grouped = (
                session.query(
                    TradeFailure.failure_source,
                    TradeFailure.blamed_component,
                    func.count(TradeFailure.id).label("count"),
                )
            )
            grouped = self._apply_filters(
                grouped,
                failure_source=failure_source,
                blamed_component=blamed_component,
                severity_score=severity_score,
                date_from=date_from,
                date_to=date_to,
            )
            grouped = grouped.group_by(TradeFailure.failure_source, TradeFailure.blamed_component).all()
            if grouped:
                strongest = max(grouped, key=lambda row: int(row.count))
                top_weakness = {
                    "failure_source": str(strongest.failure_source),
                    "blamed_component": str(strongest.blamed_component),
                    "count": int(strongest.count),
                }

        average_severity = float(sum(row.severity_score for row in rows) / len(rows)) if rows else 0.0
        average_confidence = float(sum(row.confidence for row in rows) / len(rows)) if rows else 0.0
        return {
            "total": len(rows),
            "counts_by_failure_source": counts_by_source,
            "counts_by_blamed_component": counts_by_component,
            "average_severity_score": round(average_severity, 4),
            "average_confidence": round(average_confidence, 4),
            "top_weakness": top_weakness,
        }

    @staticmethod
    def _apply_filters(
        query,
        *,
        failure_source: str | None = None,
        blamed_component: str | None = None,
        severity_score: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ):
        if failure_source:
            query = query.filter(TradeFailure.failure_source == failure_source)
        if blamed_component:
            query = query.filter(TradeFailure.blamed_component == blamed_component)
        if severity_score is not None:
            query = query.filter(TradeFailure.severity_score == severity_score)
        if date_from:
            query = query.filter(TradeFailure.created_at_utc >= date_from)
        if date_to:
            query = query.filter(TradeFailure.created_at_utc <= date_to)
        return query

    @staticmethod
    def _to_dict(row: TradeFailure | None) -> dict:
        if row is None:
            return {}
        return {
            "id": row.id,
            "order_id": row.order_id,
            "profile_id": getattr(row, "profile_id", PAPER_PROFILE_ID),
            "signal_id": row.signal_id,
            "failure_source": row.failure_source,
            "blamed_component": row.blamed_component,
            "severity_score": row.severity_score,
            "confidence": row.confidence,
            "classification": row.classification,
            "explanation": row.explanation,
            "improvement": row.improvement,
            "created_at_utc": row.created_at_utc,
        }
