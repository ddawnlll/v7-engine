"""Alert evaluation and lightweight runtime log service for v4."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import requests

from runtime.db.repos._helpers import dumps_json
from runtime.db.repos.alert_repo import AlertRepository
from runtime.db.repos.scan_repo import ScanRepository
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.db.repos.settings_repo import SettingsRepository
from runtime.db.session import check_database_connection, session_scope
from runtime.services.circuit_breaker_service import CircuitBreakerService
from runtime.services.v6_runtime_metrics_service import V6RuntimeMetricsService
from v6.config import V6Config


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class AlertService:
    def __init__(
        self,
        alert_repo: AlertRepository | None = None,
        scan_repo: ScanRepository | None = None,
        db_checker: Callable[[], tuple[bool, str]] | None = None,
        exchange_probe: Callable[[], dict] | None = None,
        settings_repo: SettingsRepository | None = None,
    ) -> None:
        self.alert_repo = alert_repo or AlertRepository()
        self.scan_repo = scan_repo or ScanRepository()
        self.db_checker = db_checker or check_database_connection
        self.exchange_probe = exchange_probe or self._default_exchange_probe
        self.settings_repo = settings_repo or SettingsRepository()
        self.circuit_breaker_service = CircuitBreakerService()
        self.v6_runtime_metrics = V6RuntimeMetricsService(V6Config.load(__import__('pathlib').Path('config/v6_config_defaults.json')))

    def refresh_alerts(
        self,
        *,
        probe_exchange: bool = True,
        limit: int = 50,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> list[dict]:
        db_connected, db_detail = self.db_checker()
        next_alerts: dict[str, dict] = {}
        runs: list[dict] = []
        existing: dict[str, dict] = {}

        if not db_connected:
            next_alerts["db-failure"] = self._build_alert(
                alert_id="db-failure",
                severity="critical",
                kind="db_failure",
                scope="database",
                message=f"Database connection failed: {db_detail}",
                payload={"db_status": db_detail},
            )

        try:
            with session_scope() as session:
                runs = self.scan_repo.list_runs(session, limit=50, profile_id=profile_id)
                settings = self.settings_repo.get_all(session, profile_id=profile_id)
                existing = {
                    item["alert_id"]: item
                    for item in self.alert_repo.list_alerts(session, active_only=False, limit=200, profile_id=profile_id)
                }
                next_alerts.update(self._scan_alerts_from_runs(runs, scans_enabled=self._is_truthy(settings.get("AUTONOMOUS_ENABLED"))))
                self._append_circuit_breaker_alert(next_alerts, profile_id=profile_id)
                self._append_v6_runtime_alerts(next_alerts)
                if probe_exchange:
                    self._append_exchange_alert(next_alerts)

                for payload in next_alerts.values():
                    self.alert_repo.save_alert(session, {**payload, "profile_id": profile_id})

                for alert_id, item in existing.items():
                    if alert_id in next_alerts:
                        continue
                    self.alert_repo.save_alert(
                        session,
                        {
                            "alert_id": alert_id,
                            "profile_id": profile_id,
                            "severity": item["severity"],
                            "kind": item["kind"],
                            "scope": item["scope"],
                            "message": item["message"],
                            "active": False,
                            "payload_json": dumps_json(item.get("payload") or {}),
                            "detected_at_utc": item["detected_at_utc"],
                        },
                    )

                return self.alert_repo.list_alerts(session, active_only=True, limit=limit, profile_id=profile_id)
        except Exception as exc:
            next_alerts["db-failure"] = self._build_alert(
                alert_id="db-failure",
                severity="critical",
                kind="db_failure",
                scope="database",
                message=f"Database access failed while collecting alerts: {exc}",
                payload={"db_status": str(exc)},
            )

        next_alerts.update(self._scan_alerts_from_runs(runs, scans_enabled=True))
        self._append_circuit_breaker_alert(next_alerts, profile_id=profile_id)
        self._append_v6_runtime_alerts(next_alerts)
        if probe_exchange:
            self._append_exchange_alert(next_alerts)
        return list(next_alerts.values())[:limit]

    def summary(self, *, probe_exchange: bool = False, limit: int = 8, profile_id: str = PAPER_PROFILE_ID) -> dict:
        items = self.refresh_alerts(probe_exchange=probe_exchange, limit=limit, profile_id=profile_id)
        counts = {"critical": 0, "warning": 0, "info": 0}
        for item in items:
            severity = str(item.get("severity") or "info").lower()
            counts[severity if severity in counts else "info"] += 1
        return {
            "total_active": len(items),
            "critical": counts["critical"],
            "warning": counts["warning"],
            "info": counts["info"],
            "items": items[:limit],
        }

    def get_runtime_logs(self, *, limit: int = 50, profile_id: str = PAPER_PROFILE_ID) -> dict:
        alerts = self.refresh_alerts(probe_exchange=False, limit=limit, profile_id=profile_id)
        db_connected, db_detail = self.db_checker()
        runs: list[dict] = []
        try:
            with session_scope() as session:
                runs = self.scan_repo.list_runs(session, limit=limit, profile_id=profile_id)
        except Exception as exc:
            items = [
                {
                    "severity": "ERROR",
                    "category": "DATABASE",
                    "symbol": None,
                    "message": f"Database access failed while collecting logs: {exc}",
                    "timestamp_utc": utc_now_iso(),
                }
            ]
            return {"items": items}

        items: list[dict] = []
        if not db_connected:
            items.append(
                {
                    "severity": "ERROR",
                    "category": "DATABASE",
                    "symbol": None,
                    "message": f"Database connection failed: {db_detail}",
                    "timestamp_utc": utc_now_iso(),
                }
            )

        for alert in alerts:
            items.append(
                {
                    "severity": str(alert.get("severity") or "info").upper(),
                    "category": "ALERT",
                    "symbol": None,
                    "message": f"{alert.get('kind')}: {alert.get('message')}",
                    "timestamp_utc": alert.get("detected_at_utc"),
                }
            )

        for run in runs:
            status = str(run.get("status") or "UNKNOWN").upper()
            severity = "INFO" if status == "COMPLETED" else "WARN" if status in {"RUNNING", "DEGRADED"} else "ERROR"
            items.append(
                {
                    "severity": severity,
                    "category": "SCAN",
                    "symbol": ",".join((run.get("symbols") or [])[:2]) or None,
                    "message": str(run.get("summary") or run.get("error_text") or f"Scan {status.lower()}"),
                    "timestamp_utc": run.get("finished_at_utc") or run.get("started_at_utc") or run.get("created_at_utc"),
                }
            )

        items.sort(key=lambda item: str(item.get("timestamp_utc") or ""), reverse=True)
        return {"items": items[:limit]}

    @staticmethod
    def _build_alert(
        *,
        alert_id: str,
        severity: str,
        kind: str,
        scope: str,
        message: str,
        payload: dict,
    ) -> dict:
        return {
            "alert_id": alert_id,
            "severity": severity,
            "kind": kind,
            "scope": scope,
            "message": message,
            "active": True,
            "payload_json": dumps_json(payload),
            "detected_at_utc": utc_now_iso(),
        }

    @staticmethod
    def _default_exchange_probe() -> dict:
        try:
            response = requests.get(
                "https://api.binance.com/api/v3/ticker/24hr",
                params={"symbol": "BTCUSDT"},
                timeout=5,
            )
            response.raise_for_status()
            payload = response.json()
            return {
                "healthy": bool(payload),
                "detail": "Exchange probe succeeded." if payload else "Exchange probe returned an empty payload.",
                "count": 1 if payload else 0,
            }
        except Exception as exc:
            return {"healthy": False, "detail": f"Exchange probe failed: {exc}"}

    def _safe_exchange_probe(self) -> dict:
        try:
            result = self.exchange_probe()
        except Exception as exc:
            return {"healthy": False, "detail": f"Exchange probe failed: {exc}"}
        if isinstance(result, dict):
            return result
        return {"healthy": bool(result), "detail": "Exchange probe completed."}

    def _append_exchange_alert(self, next_alerts: dict[str, dict]) -> None:
        exchange_state = self._safe_exchange_probe()
        if exchange_state.get("healthy", False):
            return
        next_alerts["exchange-failure"] = self._build_alert(
            alert_id="exchange-failure",
            severity="critical",
            kind="exchange_failure",
            scope="exchange",
            message=str(exchange_state.get("detail") or "Exchange probe failed."),
            payload=exchange_state,
        )

    def _append_circuit_breaker_alert(self, next_alerts: dict[str, dict], *, profile_id: str = PAPER_PROFILE_ID) -> None:
        state = self.circuit_breaker_service.evaluate_circuit_state(profile_id=profile_id)
        status = str(state.get("status") or "CLOSED").upper()
        if status == "OPEN":
            message = str(state.get("reason") or "Autonomous trading is paused by the circuit breaker.")
            if state.get("auto_resume_at"):
                message = f"{message} Auto resume: {state.get('auto_resume_at')}."
            next_alerts["circuit-breaker-open"] = self._build_alert(
                alert_id="circuit-breaker-open",
                severity="critical",
                kind="circuit_breaker_open",
                scope="operations",
                message=message,
                payload=state,
            )
        elif status == "DEGRADED":
            next_alerts["circuit-breaker-degraded"] = self._build_alert(
                alert_id="circuit-breaker-degraded",
                severity="warning",
                kind="circuit_breaker_degraded",
                scope="operations",
                message=str(state.get("reason") or "Circuit breaker is dampening autonomous confidence."),
                payload=state,
            )
        elif not bool(state.get("enabled", True)):
            next_alerts["circuit-breaker-disabled"] = self._build_alert(
                alert_id="circuit-breaker-disabled",
                severity="warning",
                kind="circuit_breaker_disabled",
                scope="operations",
                message="Circuit breaker is disabled. Autonomous scans will not be safety-stopped by recent losses.",
                payload=state,
            )

    def _append_v6_runtime_alerts(self, next_alerts: dict[str, dict]) -> None:
        for record in self.v6_runtime_metrics.build_alerts():
            next_alerts[record.alert_id] = self._build_alert(
                alert_id=record.alert_id,
                severity=record.severity,
                kind=record.kind,
                scope=record.scope,
                message=record.message,
                payload=record.payload,
            )

    @staticmethod
    def _is_truthy(value: object) -> bool:
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

    def _scan_alerts_from_runs(self, runs: list[dict], *, scans_enabled: bool) -> dict[str, dict]:
        next_alerts: dict[str, dict] = {}
        if not scans_enabled:
            return next_alerts
        latest_completed = next(
            (row for row in runs if str(row.get("status") or "").upper() in {"COMPLETED", "DEGRADED"}),
            None,
        )
        stale_after_minutes = 30
        if latest_completed is None:
            next_alerts["no-recent-scan"] = self._build_alert(
                alert_id="no-recent-scan",
                severity="warning",
                kind="no_recent_scan",
                scope="scan",
                message="No completed scan has been recorded yet.",
                payload={},
            )
            return next_alerts

        finished_at = parse_iso(latest_completed.get("finished_at_utc") or latest_completed.get("created_at_utc"))
        if finished_at is None or (datetime.now(timezone.utc) - finished_at).total_seconds() > stale_after_minutes * 60:
            next_alerts["no-recent-scan"] = self._build_alert(
                alert_id="no-recent-scan",
                severity="warning",
                kind="no_recent_scan",
                scope="scan",
                message="No recent completed scan is within the expected freshness window.",
                payload={
                    "last_run_id": latest_completed.get("run_id"),
                    "last_finished_at_utc": latest_completed.get("finished_at_utc"),
                },
            )

        slow_scan_threshold_seconds = 45
        started_at = parse_iso(latest_completed.get("started_at_utc") or latest_completed.get("created_at_utc"))
        if started_at and finished_at:
            duration_seconds = max(0.0, (finished_at - started_at).total_seconds())
            if duration_seconds > slow_scan_threshold_seconds:
                next_alerts["slow-scan"] = self._build_alert(
                    alert_id="slow-scan",
                    severity="warning",
                    kind="slow_scan",
                    scope="scan",
                    message=f"Latest scan completed in {duration_seconds:.0f}s, above the expected threshold.",
                    payload={
                        "run_id": latest_completed.get("run_id"),
                        "duration_seconds": duration_seconds,
                    },
                )
        return next_alerts
