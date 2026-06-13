"""Autonomous loop orchestration for v4."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from typing import Any

from sqlalchemy.exc import OperationalError

from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.db.repos.settings_repo import SettingsRepository, resolve_mode_intervals
from runtime.db.repos.state_repo import StateRepository
from runtime.db.session import session_scope
from runtime.runtime.scan_control import ScanControlService
from runtime.runtime.scan_runtime import ScanRuntime
from runtime.runtime.execution_orchestrator import UnsupportedExecutionProfileError
from runtime.services.circuit_breaker_service import CircuitBreakerService

log = logging.getLogger("v4.autonomous_loop")


class AutonomousLoop:
    def __init__(
        self,
        scan_runtime: ScanRuntime | None = None,
        settings_repo: SettingsRepository | None = None,
        state_repo: StateRepository | None = None,
        scan_control: ScanControlService | None = None,
        *,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> None:
        self.profile_id = str(profile_id or PAPER_PROFILE_ID)
        self.scan_runtime = scan_runtime or ScanRuntime()
        self.settings_repo = settings_repo or SettingsRepository()
        self.state_repo = state_repo or StateRepository()
        self.scan_control = scan_control or ScanControlService()
        self.circuit_breaker = CircuitBreakerService()
        self._paused = False
        self._stop_event = Event()
        self._wake_event = Event()
        self._thread: Thread | None = None
        self._next_scan_at = 0.0
        self._next_monitor_at = 0.0
        self._manual_scan_pending = False

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def pause(self) -> None:
        self._paused = True
        self._wake_event.set()

    def resume(self) -> None:
        self._paused = False
        self._wake_event.set()

    def is_paused(self) -> bool:
        return self._paused or self.scan_control.get_state(profile_id=self.profile_id).get("desired_state") == "PAUSED"

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._wake_event.clear()
        self._thread = Thread(target=self.run_forever, name=f"v4-autonomous-loop-{self.profile_id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def trigger_scan_now(self) -> dict[str, Any]:
        circuit_state = self.circuit_breaker.evaluate_circuit_state(profile_id=self.profile_id)
        if circuit_state.get("status") == "OPEN":
            self._record_state(
                "last_scan_trigger",
                {
                    "timestamp": self._utc_now_iso(),
                    "reason": "manual_trigger_blocked",
                    "blocked_reason": circuit_state.get("reason") or "circuit_open",
                    "circuit_breaker": circuit_state,
                },
            )
            return {
                "queued": False,
                "timestamp": self._utc_now_iso(),
                "restarted_loop": False,
                "paused": self.is_paused(),
                "blocked_reason": circuit_state.get("reason") or "circuit_open",
                "circuit_breaker": circuit_state,
            }
        restarted = False
        if self._thread is None or not self._thread.is_alive():
            self.start()
            restarted = True
        self._manual_scan_pending = True
        self._next_scan_at = time.monotonic()
        self._record_next_scan(self._next_scan_at)
        self._record_state(
            "last_scan_trigger",
            {
                "timestamp": self._utc_now_iso(),
                "reason": "manual_trigger",
                "restarted_loop": restarted,
                "force_run": True,
            },
        )
        self._wake_event.set()
        return {
            "queued": True,
            "timestamp": self._utc_now_iso(),
            "restarted_loop": restarted,
            "paused": self.is_paused(),
            "force_run": True,
        }

    def _record_state(self, key: str, value) -> None:
        with session_scope() as session:
            self.state_repo.set(session, key, value, profile_id=self.profile_id)

    def _read_state(self, key: str, default=None):
        with session_scope() as session:
            return self.state_repo.get(session, key, default=default, profile_id=self.profile_id)

    def _record_runner_heartbeat(self, phase: str = "loop") -> None:
        self._record_state(
            "runner_heartbeat",
            {
                "timestamp": self._utc_now_iso(),
                "phase": phase,
                "pid": os.getpid(),
                "paused": self.is_paused(),
                "profile_id": self.profile_id,
            },
        )

    def _record_next_scan(self, next_scan_at_monotonic: float) -> None:
        remaining = max(0.0, next_scan_at_monotonic - time.monotonic())
        next_scan_at_utc = datetime.now(timezone.utc) + timedelta(seconds=remaining)
        self._record_state(
            "next_scan",
            {
                "timestamp": next_scan_at_utc.isoformat(),
                "seconds_remaining": round(remaining, 3),
                "paused": self.is_paused(),
                "disabled": False,
                "reason": None,
            },
        )

    def _record_next_scan_inactive(self, reason: str) -> None:
        self._record_state(
            "next_scan",
            {
                "timestamp": None,
                "seconds_remaining": None,
                "paused": self.is_paused(),
                "disabled": reason == "disabled",
                "reason": reason,
            },
        )

    def run_once(self, *, force: bool = False, requested_by: str = "autonomous") -> dict[str, Any] | None:
        self._record_runner_heartbeat("run_once")
        if self.is_paused():
            log.info("v4 autonomous loop paused")
            self._record_state("last_monitor", {"timestamp": self._utc_now_iso(), "status": "paused"})
            return None
        settings = self._load_settings()
        autonomous_enabled = str(settings.get("AUTONOMOUS_ENABLED", "true")).lower() in {"1", "true", "yes", "on"}
        if not force and not autonomous_enabled:
            log.info("v4 autonomous loop disabled by settings")
            self._record_state("last_monitor", {"timestamp": self._utc_now_iso(), "status": "disabled"})
            return None
        circuit_state = self.circuit_breaker.evaluate_circuit_state(profile_id=self.profile_id)
        if circuit_state.get("status") == "OPEN":
            self._record_state(
                "last_scan",
                {
                    "timestamp": self._utc_now_iso(),
                    "status": "circuit_open",
                    "summary": circuit_state.get("reason"),
                    "circuit_breaker": circuit_state,
                },
            )
            return None
        symbols = self._csv(settings.get("AUTONOMOUS_SYMBOLS")) or ["BTCUSDT", "ETHUSDT"]
        intervals = self._csv(settings.get("AUTONOMOUS_INTERVALS")) or ["15m"]
        modes = self._csv(settings.get("AUTONOMOUS_MODES")) or ["SWING"]
        mode_intervals = resolve_mode_intervals(settings, modes, intervals)
        try:
            result = self.scan_runtime.run_scan(
                symbols,
                intervals,
                modes,
                requested_by=requested_by,
                mode_intervals=mode_intervals,
                profile_id=self.profile_id,
            )
            self._record_state(
                "last_scan",
                {
                    "timestamp": self._utc_now_iso(),
                    "run_id": result["run"]["run_id"],
                    "status": result["run"]["status"],
                    "summary": result["run"]["summary"],
                    "circuit_breaker": circuit_state,
                },
            )
            self._record_state("last_error", None)
            log.info("v4 autonomous loop completed run_id=%s", result["run"]["run_id"])
            return result
        except Exception as exc:
            self._record_state("last_error", {"timestamp": self._utc_now_iso(), "message": str(exc)})
            log.exception("v4 autonomous loop scan failed")
            return None

    def run_monitor_once(self, price_fetcher=None) -> dict[str, Any] | None:
        self._record_runner_heartbeat("monitor_once")
        settings = self._load_settings()
        if str(settings.get("AUTONOMOUS_ENABLED", "true")).lower() not in {"1", "true", "yes", "on"}:
            self._record_state("last_monitor", {"timestamp": self._utc_now_iso(), "status": "disabled"})
            return None
        try:
            result = self.scan_runtime.execution_orchestrator.monitor_open_orders(price_fetcher=price_fetcher, profile_id=self.profile_id)
            self._record_state(
                "last_monitor",
                {
                    "timestamp": self._utc_now_iso(),
                    "status": "completed",
                    "checked": result.get("checked", 0),
                    "closed": result.get("closed", 0),
                    "errors": len(result.get("errors") or []),
                },
            )
            if result.get("errors"):
                self._record_state("last_error", {"timestamp": self._utc_now_iso(), "message": str(result["errors"][0].get("error"))})
            elif result.get("closed"):
                self._record_state("last_error", None)
            return result
        except UnsupportedExecutionProfileError as exc:
            self._record_state(
                "last_monitor",
                {
                    "timestamp": self._utc_now_iso(),
                    "status": "skipped",
                    "reason": "unsupported_profile_monitoring",
                    "message": str(exc),
                },
            )
            last_error = self._read_state("last_error", None)
            if isinstance(last_error, dict) and "Live monitoring ownership is deferred beyond Phase 5A." in str(last_error.get("message") or ""):
                self._record_state("last_error", None)
            return None
        except Exception as exc:
            self._record_state("last_monitor", {"timestamp": self._utc_now_iso(), "status": "failed"})
            self._record_state("last_error", {"timestamp": self._utc_now_iso(), "message": str(exc)})
            log.exception("v4 autonomous loop monitor failed")
            return None

    def run_forever(self) -> None:
        self._next_scan_at = 0.0
        self._next_monitor_at = 0.0
        while not self._stop_event.is_set():
            try:
                settings = self._load_settings()
                autonomous_enabled = str(settings.get("AUTONOMOUS_ENABLED", "true")).lower() in {"1", "true", "yes", "on"}
                scan_interval_seconds = max(30, int(settings.get("AUTONOMOUS_SCAN_INTERVAL_SECONDS", "900")))
                monitor_interval_seconds = max(5, int(settings.get("AUTONOMOUS_MONITOR_INTERVAL_SECONDS", "30")))
                now = time.monotonic()
                manual_scan_pending = self._manual_scan_pending
                loop_paused = self.is_paused()

                if self._next_monitor_at <= 0:
                    self._next_monitor_at = now
                if self._next_scan_at <= 0:
                    self._next_scan_at = now
                if manual_scan_pending:
                    self._record_next_scan(self._next_scan_at)
                elif loop_paused:
                    self._record_next_scan_inactive("paused")
                elif not autonomous_enabled:
                    self._record_next_scan_inactive("disabled")
                else:
                    self._record_next_scan(self._next_scan_at)

                if now >= self._next_monitor_at:
                    self.run_monitor_once()
                    self._next_monitor_at = time.monotonic() + monitor_interval_seconds

                if manual_scan_pending or (autonomous_enabled and now >= self._next_scan_at):
                    requested_by = "manual_trigger" if manual_scan_pending else "autonomous"
                    force_run = manual_scan_pending
                    self._manual_scan_pending = False
                    self._next_scan_at = time.monotonic() + scan_interval_seconds
                    if force_run or autonomous_enabled:
                        self._record_next_scan(self._next_scan_at)
                    self.run_once(force=force_run, requested_by=requested_by)

                if manual_scan_pending:
                    wait_seconds = max(0.5, min(self._next_scan_at, self._next_monitor_at) - time.monotonic())
                elif loop_paused or not autonomous_enabled:
                    wait_seconds = 1.0
                else:
                    wait_seconds = max(0.5, min(self._next_scan_at, self._next_monitor_at) - time.monotonic())
                self._record_state(
                    "last_monitor",
                    {
                        "timestamp": self._utc_now_iso(),
                        "status": "sleeping",
                        "scan_interval_seconds": scan_interval_seconds,
                        "monitor_interval_seconds": monitor_interval_seconds,
                    },
                )
                self._wake_event.wait(wait_seconds)
                self._wake_event.clear()
            except OperationalError as exc:
                if self._stop_event.is_set():
                    break
                log.warning("v4 autonomous loop exiting after database became unavailable: %s", exc)
                self._stop_event.set()
                self._wake_event.set()
                break

    def _load_settings(self) -> dict[str, str]:
        with session_scope() as session:
            return self.settings_repo.get_all(session, profile_id=self.profile_id)

    @staticmethod
    def _csv(value: str | None) -> list[str]:
        return [item.strip() for item in str(value or "").split(",") if item.strip()]
