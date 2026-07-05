"""Dead-letter store for failed trading decisions.

Persists failed analyzer decisions, order execution failures, and system
errors for post-mortem analysis. Wraps the existing ``TradeFailure`` model
under a cleaner API.

Usage::

    from runtime.services.failed_decision_store import failed_decision_store
    failed_decision_store.record(
        order_id="abc-123",
        failure_source="ANALYZER",
        blamed_component="ENTRY_CONFIRMATION",
        severity=3,
        confidence=0.65,
        classification="TIMING_MISALIGNMENT",
        explanation="Entry triggered 2 bars before confirmation candle closed",
    )
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from runtime.db.repos.failure_repo import FailureRepository
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.db.session import session_scope


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FailedDecisionStore:
    """Persists failed decisions / trade failures for analysis.

    Wraps ``FailureRepository`` with a simpler API and adds automatic
    timestamping and profile binding.
    """

    def __init__(self, repo: FailureRepository | None = None) -> None:
        self._repo = repo or FailureRepository()

    def record(
        self,
        order_id: str,
        failure_source: str,
        blamed_component: str,
        severity: int = 1,
        confidence: float = 0.0,
        classification: str = "UNCLASSIFIED",
        explanation: str = "",
        improvement: str = "",
        signal_id: str | None = None,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict[str, Any]:
        """Persist a single failure record.

        Args:
            order_id: The failed order or decision identifier.
            failure_source: Uppercase category (ANALYZER, EXECUTION, SYSTEM, …).
            blamed_component: Specific component (ENTRY_CONFIRMATION, STOP_LOSS, …).
            severity: 1-5 severity score (5 = most severe).
            confidence: Confidence at time of failure (0.0-1.0).
            classification: Failure classification label.
            explanation: Human-readable explanation.
            improvement: Suggested improvement.
            signal_id: Optional signal identifier.
            profile_id: Runtime profile identifier.

        Returns:
            The saved record as a dict.
        """
        payload: dict[str, Any] = {
            "order_id": order_id,
            "failure_source": failure_source.upper()[:64],
            "blamed_component": blamed_component[:64],
            "severity_score": max(1, min(5, int(severity))),
            "confidence": float(confidence),
            "classification": str(classification)[:128],
            "explanation": str(explanation),
            "improvement": str(improvement),
            "created_at_utc": _utc_now(),
            "profile_id": profile_id,
        }
        if signal_id is not None:
            payload["signal_id"] = signal_id

        with session_scope() as session:
            return self._repo.save_failure(session, payload)

    def list(
        self,
        limit: int = 100,
        source: str | None = None,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> list[dict[str, Any]]:
        """List recent failures, optionally filtered by source."""
        with session_scope() as session:
            if source:
                return self._repo.list_failures_by_source(
                    session, source.upper(), limit=limit, profile_id=profile_id,
                )
            return self._repo.list_recent_failures(
                session, limit=limit, profile_id=profile_id,
            )

    def get_for_order(
        self,
        order_id: str,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> list[dict[str, Any]]:
        """Get all failure records for a specific order."""
        with session_scope() as session:
            return self._repo.get_failures_for_order(session, order_id, profile_id=profile_id)

    def summary(
        self,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict[str, Any]:
        """Get a summary of failure counts by source and component."""
        with session_scope() as session:
            return self._repo.failure_summary(session, profile_id=profile_id)


# Module-level singleton
_failed_decision_store: FailedDecisionStore | None = None


def get_failed_decision_store() -> FailedDecisionStore:
    """Get the module-level FailedDecisionStore singleton."""
    global _failed_decision_store
    if _failed_decision_store is None:
        _failed_decision_store = FailedDecisionStore()
    return _failed_decision_store
