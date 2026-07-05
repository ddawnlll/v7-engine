"""Health check service with component-level status."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from runtime.db.session import check_database_connection
from runtime.services.circuit_breaker_service import CircuitBreakerService


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class HealthService:
    """Performs component-level health checks.

    Checks are independent — one component failure does not affect others.
    """

    def __init__(
        self,
        db_checker: Callable[[], tuple[bool, str]] | None = None,
        circuit_breaker_service: CircuitBreakerService | None = None,
    ) -> None:
        self._db_checker = db_checker or check_database_connection
        self._circuit_breaker = circuit_breaker_service or CircuitBreakerService()

    def check_liveness(self) -> dict[str, Any]:
        """Lightweight liveness check — returns immediately.

        This is the first probe orchestrators call; no dependencies.
        """
        return {
            "status": "alive",
            "timestamp": _utc_now_iso(),
        }

    def check_readiness(self) -> dict[str, Any]:
        """Readiness check — can the app serve requests?

        Checks database connectivity. Returns degraded status if DB is down.
        """
        db_connected, db_detail = self._db_checker()
        ready = db_connected
        return {
            "status": "ready" if ready else "not_ready",
            "ready": ready,
            "database": {"connected": db_connected, "detail": db_detail},
            "timestamp": _utc_now_iso(),
        }

    def check_components(self) -> dict[str, Any]:
        """Run all component health checks and return a breakdown.

        Returns:
            Overall status (healthy / degraded / error) plus component-level details.
        """
        # Database
        db_connected, db_detail = self._db_checker()
        db_status = "healthy" if db_connected else "degraded"

        # Circuit breaker
        try:
            cb_state = self._circuit_breaker.evaluate_circuit_state()
            cb_raw = cb_state.get("status", "unknown")
            cb_status = "healthy" if cb_raw == "CLOSED" else cb_raw.lower()
        except Exception as exc:
            cb_state = {}
            cb_status = "error"

        # Compute overall
        statuses = [db_status, cb_status]
        if all(s == "healthy" for s in statuses):
            overall = "healthy"
        elif "error" in statuses:
            overall = "error"
        else:
            overall = "degraded"

        return {
            "status": overall,
            "timestamp": _utc_now_iso(),
            "components": {
                "database": {
                    "status": db_status,
                    "connected": db_connected,
                    "detail": db_detail,
                },
                "circuit_breaker": {
                    "status": cb_status,
                    "state": cb_state.get("status", "unknown"),
                    "rules_triggered": cb_state.get("active_rules", []),
                },
            },
        }
