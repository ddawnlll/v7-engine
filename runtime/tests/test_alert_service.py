"""Tests for runtime/services/alert_service.py.

AlertService depends on injected repos and services — all mockable.
"""

from unittest.mock import MagicMock, patch

from runtime.services.alert_service import AlertService


class _AlertStore:
    """Stores saved alerts and returns them on list_alerts."""
    def __init__(self):
        self._alerts: dict[str, dict] = {}
        self._active: dict[str, dict] = {}

    def list_alerts(self, session=None, *, active_only=False, limit=200, profile_id=""):
        store = self._active if active_only else self._alerts
        return list(store.values())[:limit]

    def save_alert(self, session=None, payload=None):
        if payload is None:
            payload = {}
        aid = payload.get("alert_id", "unknown")
        payload_copy = dict(payload)
        if payload.get("active", True):
            self._active[aid] = payload_copy
            self._alerts[aid] = payload_copy
        elif aid in self._active:
            del self._active[aid]
        return payload_copy


def _mock_alert_repo():
    return _AlertStore()


def _mock_scan_repo():
    repo = MagicMock()
    repo.list_runs.return_value = []
    return repo


def _mock_settings_repo():
    repo = MagicMock()
    repo.get_all.return_value = {}
    return repo


def _make_service(
    alert_repo=None,
    scan_repo=None,
    db_checker=None,
    exchange_probe=None,
    settings_repo=None,
    cb_service=None,
    metrics_service=None,
) -> AlertService:
    service = AlertService(
        alert_repo=alert_repo or _mock_alert_repo(),
        scan_repo=scan_repo or _mock_scan_repo(),
        db_checker=db_checker or (lambda: (True, "ok")),
        exchange_probe=exchange_probe or (lambda: {"healthy": True}),
        settings_repo=settings_repo or _mock_settings_repo(),
    )
    # Override real services with mocks to avoid DB access
    mock_cb = MagicMock()
    mock_cb.evaluate_circuit_state.return_value = {"status": "CLOSED", "enabled": True}
    service.circuit_breaker_service = cb_service or mock_cb
    mock_metrics = MagicMock()
    mock_metrics.build_alerts.return_value = []
    service.v6_runtime_metrics = metrics_service or mock_metrics
    return service


# ── Database health ──────────────────────────────────────────────────

class TestDatabaseAlert:
    def test_db_failure_creates_critical_alert(self):
        service = _make_service(db_checker=lambda: (False, "connection refused"))
        result = service.refresh_alerts(probe_exchange=False)
        alert_ids = [a.get("alert_id") for a in result]
        assert "db-failure" in alert_ids


# ── Exchange health ──────────────────────────────────────────────────

class TestExchangeAlert:
    def test_exchange_failure_creates_alert(self):
        service = _make_service(exchange_probe=lambda: {"healthy": False, "detail": "timeout"})
        result = service.refresh_alerts(probe_exchange=True)
        alert_ids = [a.get("alert_id") for a in result]
        assert "exchange-failure" in alert_ids

    def test_exchange_healthy_no_alert(self):
        service = _make_service(exchange_probe=lambda: {"healthy": True})
        result = service.refresh_alerts(probe_exchange=True)
        alert_ids = [a.get("alert_id") for a in result]
        assert "exchange-failure" not in alert_ids


# ── Circuit breaker alerts ───────────────────────────────────────────

class TestCircuitBreakerAlert:
    def test_open_cb_creates_critical_alert(self):
        cb = MagicMock()
        cb.evaluate_circuit_state.return_value = {
            "status": "OPEN",
            "reason": "Too many losses",
            "auto_resume_at": None,
        }
        service = _make_service(cb_service=cb)
        result = service.refresh_alerts(probe_exchange=False)
        alert_ids = [a.get("alert_id") for a in result]
        assert "circuit-breaker-open" in alert_ids

    def test_degraded_cb_creates_warning(self):
        cb = MagicMock()
        cb.evaluate_circuit_state.return_value = {
            "status": "DEGRADED",
            "reason": "Approaching limits",
            "enabled": True,
        }
        service = _make_service(cb_service=cb)
        result = service.refresh_alerts(probe_exchange=False)
        alert_ids = [a.get("alert_id") for a in result]
        assert "circuit-breaker-degraded" in alert_ids

    def test_closed_cb_no_alert(self):
        cb = MagicMock()
        cb.evaluate_circuit_state.return_value = {
            "status": "CLOSED",
            "enabled": True,
        }
        service = _make_service(cb_service=cb)
        result = service.refresh_alerts(probe_exchange=False)
        alert_ids = [a.get("alert_id") for a in result]
        assert "circuit-breaker-open" not in alert_ids
        assert "circuit-breaker-degraded" not in alert_ids

    def test_disabled_cb_creates_warning(self):
        cb = MagicMock()
        cb.evaluate_circuit_state.return_value = {
            "status": "CLOSED",
            "enabled": False,
        }
        service = _make_service(cb_service=cb)
        result = service.refresh_alerts(probe_exchange=False)
        alert_ids = [a.get("alert_id") for a in result]
        assert "circuit-breaker-disabled" in alert_ids


# ── Scan alerts ──────────────────────────────────────────────────────

class TestScanAlert:
    def test_no_completed_scan_creates_warning(self):
        scan_repo = _mock_scan_repo()
        scan_repo.list_runs.return_value = [
            {"run_id": "r1", "status": "RUNNING", "created_at_utc": "2026-06-01T12:00:00+00:00"},
        ]
        settings_repo = _mock_settings_repo()
        settings_repo.get_all.return_value = {"AUTONOMOUS_ENABLED": "true"}
        service = _make_service(scan_repo=scan_repo, settings_repo=settings_repo)
        result = service.refresh_alerts(probe_exchange=False)
        alert_ids = [a.get("alert_id") for a in result]
        assert "no-recent-scan" in alert_ids


# ── Summary ───────────────────────────────────────────────────────────

class TestSummary:
    def test_summary_returns_counts(self):
        service = _make_service()
        summary = service.summary(probe_exchange=False)
        assert "total_active" in summary
        assert "critical" in summary
        assert "warning" in summary
        assert "info" in summary

    def test_summary_items_limited(self):
        service = _make_service()
        summary = service.summary(probe_exchange=False, limit=5)
        assert len(summary["items"]) <= 5


# ── Scan alerts with fresh data ───────────────────────────────────────

class TestScanAlertFresh:
    def test_recent_completed_scan_no_alert(self):
        """Scan finished 5 min ago, within 30 min stale threshold → no alert."""
        finished = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        scan_repo = _mock_scan_repo()
        scan_repo.list_runs.return_value = [
            {
                "run_id": "r1",
                "status": "COMPLETED",
                "created_at_utc": (finished - __import__("datetime").timedelta(minutes=10)).isoformat(),
                "started_at_utc": (finished - __import__("datetime").timedelta(minutes=15)).isoformat(),
                "finished_at_utc": (finished - __import__("datetime").timedelta(minutes=5)).isoformat(),
            },
        ]
        settings_repo = _mock_settings_repo()
        settings_repo.get_all.return_value = {"AUTONOMOUS_ENABLED": "true"}
        service = _make_service(scan_repo=scan_repo, settings_repo=settings_repo)
        result = service.refresh_alerts(probe_exchange=False)
        alert_ids = [a.get("alert_id") for a in result]
        assert "no-recent-scan" not in alert_ids


# ── DB exception handling ────────────────────────────────────────────

class TestDbException:
    def test_db_exception_falls_back(self):
        alert_repo = MagicMock()
        alert_repo.list_alerts.side_effect = Exception("DB crash")
        service = _make_service(alert_repo=alert_repo)
        result = service.refresh_alerts(probe_exchange=False)
        assert len(result) > 0
