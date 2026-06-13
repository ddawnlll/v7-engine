"""Binance USDⓈ-M user-data websocket runtime owner.

Provides a runtime-managed background worker that:
- Starts/refreshes the listenKey via the existing stream service
- Keeps the listenKey alive on a configurable cadence
- Reconnects/refreshes when stale, expired, or degraded
- Connects to the Binance user-data websocket and routes events to ingest_event
- Rotates the connection before the 60-minute listenKey expiry
- Degrades stream state on failure without crashing the application

All operational thresholds are read from the unified config system.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from threading import Event, Thread
from typing import Any, Protocol

from runtime.db.repos.runtime_profile_repo import RuntimeProfileRepository
from runtime.db.repos.settings_repo import SettingsRepository
from runtime.db.session import session_scope
from runtime.services.binance_usdm_user_data_stream_service import (
    BinanceUsdmUserDataStreamError,
    BinanceUsdmUserDataStreamService,
)
from runtime.services.runtime_profile_service import (
    BINANCE_USDM_VENUE,
    RuntimeProfileNotFoundError,
    RuntimeProfileService,
)

log = logging.getLogger("v4.websocket_owner")


class WebsocketTransport(Protocol):
    """Protocol for a pluggable websocket transport."""

    def connect(self, url: str, *, timeout: float) -> None: ...
    def recv(self, timeout: float) -> str: ...
    def close(self) -> None: ...
    @property
    def connected(self) -> bool: ...


class NullTransport:
    """No-op transport used when no real websocket library is available."""

    def __init__(self) -> None:
        self._connected = False

    def connect(self, url: str, *, timeout: float) -> None:
        self._connected = True

    def recv(self, timeout: float) -> str:
        raise TimeoutError("NullTransport: no real websocket library installed")

    def close(self) -> None:
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected


class WebsocketClientTransport:
    """Real websocket transport using the `websocket-client` library."""

    def __init__(self) -> None:
        self._ws: Any = None

    def connect(self, url: str, *, timeout: float) -> None:
        try:
            import websocket as _ws_mod
        except ImportError as exc:
            raise RuntimeError(
                "websocket-client library is required for real websocket transport. "
                "Install with: pip install websocket-client"
            ) from exc
        self.close()
        self._ws = _ws_mod.WebSocket()
        self._ws.settimeout(timeout)
        self._ws.connect(url)

    def recv(self, timeout: float) -> str:
        if self._ws is None:
            raise TimeoutError("not connected")
        self._ws.settimeout(timeout)
        data = self._ws.recv()
        if data is None or data == "":
            raise TimeoutError("empty frame")
        return str(data)

    def close(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    @property
    def connected(self) -> bool:
        return self._ws is not None and self._ws.connected


def _default_transport() -> WebsocketTransport:
    """Return the best available transport implementation."""
    try:
        import websocket as _ws_mod  # noqa: F401
        return WebsocketClientTransport()
    except ImportError:
        return NullTransport()


class BinanceUsdmWebsocketOwner:
    """Runtime-managed websocket owner for a single Binance USDⓈ-M profile."""

    def __init__(
        self,
        profile_id: str,
        *,
        stream_service: BinanceUsdmUserDataStreamService | None = None,
        runtime_profile_service: RuntimeProfileService | None = None,
        runtime_profile_repo: RuntimeProfileRepository | None = None,
        settings_repo: SettingsRepository | None = None,
        transport: WebsocketTransport | None = None,
    ) -> None:
        self.profile_id = profile_id
        self.stream_service = stream_service or BinanceUsdmUserDataStreamService()
        self.runtime_profile_service = runtime_profile_service or RuntimeProfileService()
        self.runtime_profile_repo = runtime_profile_repo or RuntimeProfileRepository()
        self.settings_repo = settings_repo or SettingsRepository()
        self._transport = transport or _default_transport()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._last_keepalive_at: float = 0.0
        self._last_reconnect_attempt_at: float = 0.0
        self._consecutive_reconnect_failures: int = 0
        self._started = False

    # ── settings ────────────────────────────────────────────

    def _load_settings(self) -> dict[str, Any]:
        with session_scope() as session:
            settings = self.settings_repo.get_all(session, profile_id=self.profile_id)
        return {
            "ws_runtime_enabled": str(settings.get("WS_RUNTIME_ENABLED", "true")).lower() in {"1", "true", "yes", "on"},
            "keepalive_interval": max(60, int(float(settings.get("WS_KEEPALIVE_INTERVAL_SECONDS", "1500")))),
            "reconnect_interval": max(1, int(float(settings.get("WS_RECONNECT_INTERVAL_SECONDS", "5")))),
            "reconnect_max_attempts": max(1, int(float(settings.get("WS_RECONNECT_MAX_ATTEMPTS", "5")))),
            "stale_threshold": max(60, int(float(settings.get("WS_STALE_STREAM_THRESHOLD_SECONDS", "3300")))),
            "rotation_before_expiry": max(60, int(float(settings.get("WS_ROTATION_BEFORE_EXPIRY_SECONDS", "3000")))),
            "receive_timeout": max(1, int(float(settings.get("WS_RECEIVE_TIMEOUT_SECONDS", "30")))),
        }

    # ── eligibility ─────────────────────────────────────────

    def is_eligible(self) -> bool:
        """Check if the profile is eligible for websocket runtime ownership."""
        try:
            access = self.runtime_profile_service.get_profile_access(
                self.profile_id, require_account_reads=True,
            )
        except (RuntimeProfileNotFoundError, Exception):
            return False
        profile = access.get("profile") or {}
        if str(profile.get("venue") or "").upper() != BINANCE_USDM_VENUE:
            return False
        if not access.get("credentials_configured"):
            return False
        if not bool(profile.get("supports_account_reads")):
            return False
        return True

    # ── lifecycle ───────────────────────────────────────────

    def start(self) -> None:
        """Start the background worker thread. Idempotent — does not start duplicates."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._started = True
        self._thread = Thread(
            target=self._run_forever,
            name=f"ws-owner-{self.profile_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the background worker safely. Idempotent."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._started = False
        try:
            self._transport.close()
        except Exception:
            pass

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── main loop ───────────────────────────────────────────

    def _run_forever(self) -> None:
        """Main worker loop. Runs in a daemon thread."""
        log.info("websocket owner starting for profile=%s", self.profile_id)
        try:
            while not self._stop_event.is_set():
                try:
                    self._tick()
                except Exception:
                    log.exception("websocket owner tick error profile=%s", self.profile_id)
                    self._stop_event.wait(5.0)
        finally:
            log.info("websocket owner stopped for profile=%s", self.profile_id)
            try:
                self._transport.close()
            except Exception:
                pass

    def _tick(self) -> None:
        """Single iteration of the owner loop."""
        cfg = self._load_settings()

        if not cfg["ws_runtime_enabled"]:
            self._stop_event.wait(10.0)
            return

        if not self.is_eligible():
            self._stop_event.wait(10.0)
            return

        stream_state = self.stream_service.get_stream_state(self.profile_id)
        status = str(stream_state.get("status") or "INACTIVE").upper()
        reconnect_required = bool(stream_state.get("reconnect_required"))

        # ── Need initial start or reconnect? ────────
        if status in {"INACTIVE", "CLOSED"} or reconnect_required or status in {"EXPIRED", "DEGRADED"}:
            self._handle_reconnect(cfg, stream_state)
            return

        # ── Check for stale / approaching expiry ────
        if self._is_stream_stale(stream_state, cfg["stale_threshold"]):
            log.info("stream stale for profile=%s, refreshing", self.profile_id)
            self._handle_reconnect(cfg, stream_state)
            return

        if self._is_approaching_expiry(stream_state, cfg["rotation_before_expiry"]):
            log.info("stream approaching expiry for profile=%s, rotating", self.profile_id)
            self._handle_reconnect(cfg, stream_state)
            return

        # ── Keepalive check ─────────────────────────
        if self._needs_keepalive(cfg["keepalive_interval"]):
            self._do_keepalive()

        # ── Try to receive a websocket message ──────
        self._try_receive_message(cfg["receive_timeout"])

    # ── reconnect ───────────────────────────────────────────

    def _handle_reconnect(self, cfg: dict[str, Any], stream_state: dict[str, Any]) -> None:
        now = time.monotonic()
        interval = cfg["reconnect_interval"]
        max_attempts = cfg["reconnect_max_attempts"]

        if self._consecutive_reconnect_failures >= max_attempts:
            backoff = min(interval * (2 ** min(self._consecutive_reconnect_failures - max_attempts, 5)), 300)
            if now - self._last_reconnect_attempt_at < backoff:
                self._stop_event.wait(min(backoff, 10.0))
                return
            # Reset after extended backoff to allow another cycle
            self._consecutive_reconnect_failures = 0

        if now - self._last_reconnect_attempt_at < interval:
            self._stop_event.wait(min(interval, 5.0))
            return

        self._last_reconnect_attempt_at = now
        try:
            self._transport.close()
        except Exception:
            pass

        try:
            status = str(stream_state.get("status") or "INACTIVE").upper()
            if status in {"INACTIVE", "CLOSED"}:
                result = self.stream_service.start_stream(self.profile_id, reason="ws_owner_start")
            else:
                result = self.stream_service.refresh_stream(self.profile_id, reason="ws_owner_refresh")

            listen_key = self._extract_listen_key()
            if listen_key:
                ws_url = self._build_ws_url(stream_state, listen_key)
                self._transport.connect(ws_url, timeout=float(cfg["receive_timeout"]))
                log.info("websocket connected for profile=%s", self.profile_id)

            self._consecutive_reconnect_failures = 0
            self._last_keepalive_at = time.monotonic()
        except (BinanceUsdmUserDataStreamError, Exception) as exc:
            self._consecutive_reconnect_failures += 1
            log.warning(
                "websocket reconnect failed profile=%s attempt=%d error=%s",
                self.profile_id, self._consecutive_reconnect_failures, exc,
            )
            try:
                self.stream_service.mark_stream_disconnected(
                    self.profile_id,
                    error_text=f"Websocket owner reconnect failed: {exc}",
                    reconnect_required=True,
                )
            except Exception:
                pass
            self._stop_event.wait(min(interval, 5.0))

    def _extract_listen_key(self) -> str | None:
        """Read the current listen key from persisted stream state."""
        try:
            from runtime.db.repos.state_repo import StateRepository
            from runtime.services.binance_usdm_user_data_stream_service import STREAM_STATE_KEY
            state_repo = StateRepository()
            with session_scope() as session:
                state = state_repo.get(session, STREAM_STATE_KEY, default={}, profile_id=self.profile_id) or {}
            return str(state.get("listen_key") or "").strip() or None
        except Exception:
            return None

    def _build_ws_url(self, stream_state: dict[str, Any], listen_key: str) -> str:
        transport_info = stream_state.get("transport") or {}
        base_url = str(transport_info.get("websocket_base_url") or "wss://fstream.binance.com/private")
        # Strip trailing '/private' — Binance user-data stream connects at /ws/<listenKey>
        if base_url.endswith("/private"):
            base_url = base_url[:-len("/private")]
        return f"{base_url}/ws/{listen_key}"

    # ── keepalive ───────────────────────────────────────────

    def _needs_keepalive(self, interval: int) -> bool:
        return time.monotonic() - self._last_keepalive_at >= interval

    def _do_keepalive(self) -> None:
        try:
            self.stream_service.keepalive_stream(self.profile_id)
            self._last_keepalive_at = time.monotonic()
            log.debug("keepalive sent for profile=%s", self.profile_id)
        except (BinanceUsdmUserDataStreamError, Exception) as exc:
            log.warning("keepalive failed for profile=%s: %s", self.profile_id, exc)

    # ── message receive ─────────────────────────────────────

    def _try_receive_message(self, timeout: float) -> None:
        if not self._transport.connected:
            self._stop_event.wait(1.0)
            return
        try:
            raw = self._transport.recv(timeout)
            if raw:
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    self.stream_service.ingest_event(self.profile_id, payload)
        except TimeoutError:
            pass
        except json.JSONDecodeError as exc:
            log.warning("invalid json from websocket profile=%s: %s", self.profile_id, exc)
        except Exception as exc:
            log.warning("websocket recv error profile=%s: %s", self.profile_id, exc)
            try:
                self.stream_service.mark_stream_disconnected(
                    self.profile_id,
                    error_text=f"Websocket receive error: {exc}",
                    reconnect_required=True,
                )
            except Exception:
                pass

    # ── stream state checks ─────────────────────────────────

    @staticmethod
    def _is_stream_stale(stream_state: dict[str, Any], threshold_seconds: int) -> bool:
        last_event = stream_state.get("last_event_seen_at_utc")
        last_keepalive = stream_state.get("last_keepalive_at_utc")
        last_started = stream_state.get("last_started_at_utc")
        reference = last_event or last_keepalive or last_started
        if not reference:
            return True
        try:
            ref_dt = datetime.fromisoformat(str(reference).replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - ref_dt).total_seconds()
            return age > threshold_seconds
        except (ValueError, TypeError):
            return True

    @staticmethod
    def _is_approaching_expiry(stream_state: dict[str, Any], rotation_threshold: int) -> bool:
        started_at = stream_state.get("last_started_at_utc")
        if not started_at:
            return False
        try:
            started_dt = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - started_dt).total_seconds()
            return age >= rotation_threshold
        except (ValueError, TypeError):
            return False


__all__ = [
    "BinanceUsdmWebsocketOwner",
    "NullTransport",
    "WebsocketClientTransport",
    "WebsocketTransport",
]
