"""Centralized logging configuration for the V7 runtime.

Provides structured JSON logging, log rotation, per-module log level overrides,
and request-id propagation through the logging context.

Configuration is driven by environment variables:

    LOG_LEVEL           – root log level (default: INFO)
    LOG_FORMAT          – "json" (default) or "text"
    LOG_DIR             – directory for rotated log files (default: ./logs)
    LOG_LEVELS          – optional per-module overrides:
                          "module.a=DEBUG,module.b=WARNING"
    LOG_REQUEST_ID_HEADER – HTTP header to read request-id from (default: X-Request-ID)

Usage::

    from runtime.logging_config import configure_logging
    configure_logging()

After ``configure_logging()``, any module that does
``logger = logging.getLogger(__name__)`` will inherit the configured handlers,
formatter, and per-module levels.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_LOG_LEVEL = "INFO"
_DEFAULT_LOG_FORMAT = "json"
_DEFAULT_LOG_DIR = "./logs"
_DEFAULT_LOG_FILENAME = "runtime.log"
_DEFAULT_REQUEST_ID_HEADER = "X-Request-ID"
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_DEFAULT_BACKUP_COUNT = 5

# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object.

    Output keys::

        {"timestamp": "...", "level": "...", "module": "...", "message": "...",
         "request_id": "..."}

    ``request_id`` is drawn from the ``request_id`` attribute on the record,
    which is populated by :class:`_RequestIdFilter`.
    """

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None)
        if request_id:
            payload["request_id"] = request_id
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class _TextFormatter(logging.Formatter):
    """Emulate a traditional key=value log line for readability.

    Output example::

        2025-01-01T00:00:00.000Z INFO module.name message here request_id=abc123
    """

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()

    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S.%fZ")
        base = f"{ts} {record.levelname} {record.name} {record.getMessage()}"
        request_id = getattr(record, "request_id", None)
        if request_id:
            base += f" request_id={request_id}"
        if record.exc_info and record.exc_info[0] is not None:
            base += "\n" + self.formatException(record.exc_info)
        return base


# ---------------------------------------------------------------------------
# Request-id injection
# ---------------------------------------------------------------------------


class _RequestIdFilter(logging.Filter):
    """Attach the current request-id (from a context variable) to every record.

    Modules can set the request id via::

        from runtime.logging_config import set_request_id, clear_request_id
        set_request_id("abc-123")
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get()  # type: ignore[attr-defined]
        return True


# ---------------------------------------------------------------------------
# Request-id context
# ---------------------------------------------------------------------------

try:
    from contextvars import ContextVar
except ImportError:
    ContextVar = None  # type: ignore[assignment,misc]  # Python < 3.7 fallback

if ContextVar is not None:
    _request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
else:
    # Minimal fallback — threading.local for Python < 3.7
    import threading as _threading

    class _ThreadLocalRequestId:
        def __init__(self) -> None:
            self._local = _threading.local()

        def get(self) -> str | None:
            return getattr(self._local, "value", None)

        def set(self, val: str | None) -> None:
            self._local.value = val

    _request_id_var = _ThreadLocalRequestId()  # type: ignore[assignment]


def set_request_id(request_id: str | None) -> None:
    """Set the request-id for the current async context or thread."""
    if ContextVar is not None:
        _request_id_var.set(request_id)
    else:
        _request_id_var.set(request_id)  # type: ignore[union-attr]


def clear_request_id() -> None:
    """Remove the request-id for the current async context or thread."""
    if ContextVar is not None:
        _request_id_var.set(None)
    else:
        _request_id_var.set(None)  # type: ignore[union-attr]


def get_request_id() -> str | None:
    """Return the current request-id, or *None*."""
    if ContextVar is not None:
        return _request_id_var.get()
    return _request_id_var.get()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Request-id middleware (optional helper)
# ---------------------------------------------------------------------------


def create_request_id_middleware(
    header_name: str | None = None,
) -> Any:
    """Return an ASGI middleware callable that reads *header_name* from incoming
    requests, sets it on the logging context, and clears it after the response.

    Intended to be attached to the FastAPI app::

        from runtime.logging_config import create_request_id_middleware
        app.add_middleware(create_request_id_middleware())
    """
    header = header_name or os.getenv("LOG_REQUEST_ID_HEADER", _DEFAULT_REQUEST_ID_HEADER)

    class _RequestIdMiddleware:
        def __init__(self, app: Any) -> None:
            self.app = app

        async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return
            raw_headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
            rid: str | None = None
            for key_bytes, val_bytes in raw_headers:
                if key_bytes.decode("latin-1").lower() == header.lower():
                    rid = val_bytes.decode("latin-1")
                    break
            set_request_id(rid)
            try:
                await self.app(scope, receive, send)
            finally:
                clear_request_id()

    return _RequestIdMiddleware


# ---------------------------------------------------------------------------
# Per-module log levels from env
# ---------------------------------------------------------------------------


def _apply_module_levels(env_value: str | None) -> None:
    """Parse ``LOG_LEVELS`` and set per-module levels.

    Expected format: ``"module.a=DEBUG,module.b=WARNING"``
    """
    if not env_value:
        return
    for entry in env_value.split(","):
        entry = entry.strip()
        if "=" not in entry:
            continue
        module_name, level_str = entry.split("=", 1)
        module_name = module_name.strip()
        level_str = level_str.strip().upper()
        numeric = getattr(logging, level_str, None)
        if numeric is not None and isinstance(numeric, int):
            logging.getLogger(module_name).setLevel(numeric)
        else:
            logging.getLogger("runtime.logging_config").warning(
                "invalid LOG_LEVELS entry ignored %s=%s",
                module_name,
                level_str,
            )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_startup_ts = time.time()


def configure_logging() -> None:
    """Configure application-wide logging.

    Reads env vars, attaches a :class:`~logging.StreamHandler` for stdout and
    a :class:`~logging.handlers.RotatingFileHandler` for disk persistence.
    Both handlers share the same formatter (JSON or text).

    This function is idempotent: if logging has already been configured (the
    root logger already has handlers), it is a no-op.
    """
    root = logging.getLogger()
    if root.handlers:
        # Already configured (e.g. called more than once or by a test harness).
        return

    root_level = os.getenv("LOG_LEVEL", _DEFAULT_LOG_LEVEL).upper()
    log_format = os.getenv("LOG_FORMAT", _DEFAULT_LOG_FORMAT).lower()
    log_dir = os.getenv("LOG_DIR", _DEFAULT_LOG_DIR)

    root.setLevel(getattr(logging, root_level, logging.INFO))

    # ---- formatter ----
    if log_format == "json":
        formatter: logging.Formatter = _JsonFormatter()
    else:
        formatter = _TextFormatter()

    # ---- request-id filter ----
    request_id_filter = _RequestIdFilter()

    # ---- stdout handler ----
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(getattr(logging, root_level, logging.INFO))
    console.setFormatter(formatter)
    console.addFilter(request_id_filter)
    root.addHandler(console)

    # ---- file handler (rotating) ----
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        pass  # fall back to stdout-only
    else:
        file_path = os.path.join(log_dir, _DEFAULT_LOG_FILENAME)
        file_handler = RotatingFileHandler(
            file_path,
            maxBytes=_DEFAULT_MAX_BYTES,
            backupCount=_DEFAULT_BACKUP_COUNT,
        )
        file_handler.setLevel(getattr(logging, root_level, logging.INFO))
        file_handler.setFormatter(formatter)
        file_handler.addFilter(request_id_filter)
        root.addHandler(file_handler)

    # ---- per-module levels ----
    _apply_module_levels(os.getenv("LOG_LEVELS"))

    # ---- silence noisy third-party loggers ----
    for noisy in ("uvicorn.access", "uvicorn.error", "asyncio"):
        logging.getLogger(noisy).handlers.clear()
        logging.getLogger(noisy).propagate = True

    elapsed = time.time() - _startup_ts
    root.info(
        "logging configured level=%s format=%s log_dir=%s elapsed_ms=%d",
        root_level,
        log_format,
        log_dir,
        int(elapsed * 1000),
    )


# ---------------------------------------------------------------------------
# Structured health-event logging
# ---------------------------------------------------------------------------


def log_health_event(
    event: str,
    *,
    status: str = "info",
    component: str = "system",
    message: str = "",
    **fields: object,
) -> None:
    """Log a structured health-relevant event.

    Examples::

        log_health_event("circuit_breaker_opened", status="warning",
                         component="circuit_breaker",
                         message="Max consecutive losses reached")
        log_health_event("startup_complete", status="info",
                         component="runtime",
                         message="All services started")

    Args:
        event: Dot-separated event name.
        status: Severity (info, warning, error, critical).
        component: System component name.
        message: Human-readable description.
        **fields: Additional structured fields.
    """
    logger = logging.getLogger("runtime.health")
    payload = {
        "event": event,
        "status": status,
        "component": component,
        "message": message,
    }
    payload.update(fields)

    level = logging.INFO
    if status == "warning":
        level = logging.WARNING
    elif status == "error":
        level = logging.ERROR
    elif status == "critical":
        level = logging.CRITICAL

    logger.log(level, "%s", json.dumps(payload, default=str))


def log_health_summary(extra_fields: dict | None = None) -> None:
    """Emit a periodic health summary log line.

    Called by the runtime scheduler to provide a regular health pulse.
    """
    logger = logging.getLogger("runtime.health")
    fields: dict[str, object] = {
        "event": "health_summary",
        "status": "info",
        "component": "runtime",
    }
    if extra_fields:
        fields.update(extra_fields)
    logger.info("health summary %s", json.dumps(fields, default=str))
