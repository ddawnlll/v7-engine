"""FastAPI entrypoint for the runtime package.

This file will own:
- app creation
- env loading
- router registration
- startup logging
"""

from __future__ import annotations

import inspect
import logging
import os
from contextlib import asynccontextmanager
from time import time

from fastapi import FastAPI, Request
from runtime.db.repos.runtime_profile_repo import RuntimeProfileRepository
from runtime.db.session import (
    check_database_connection,
    configure_engine,
    ensure_settings_table,
    get_database_url,
    initialize_schema,
    mask_database_url,
    session_scope,
)


def _load_environment() -> None:
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", ".env")
    env_path = os.path.abspath(env_path)
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip()


def _start_profile_autonomous_loops() -> None:
    from runtime.runtime.autonomous_runtime import start_autonomous_loop

    repo = RuntimeProfileRepository()
    with session_scope() as session:
        profiles = repo.list_profiles(session)
    started: set[str] = set()
    for profile in profiles:
        profile_id = str(profile.get("profile_id") or "").strip()
        if not profile_id or profile_id in started:
            continue
        start_autonomous_loop(profile_id)
        started.add(profile_id)
    if "paper-main" not in started:
        start_autonomous_loop()


def _log_runtime_code_fingerprint() -> None:
    from runtime.runtime.scan_runtime import ScanRuntime

    descriptor = ScanRuntime.__dict__.get("_classify_skip")
    raw_callable = descriptor.__func__ if isinstance(descriptor, staticmethod) else descriptor
    source_file = inspect.getsourcefile(ScanRuntime) or "unknown"
    try:
        source_line = inspect.getsourcelines(raw_callable)[1] if raw_callable is not None else None
    except (OSError, TypeError):
        source_line = None
    print(
        "runtime code fingerprint"
        f" scan_runtime_file={source_file}"
        f" classify_skip_static={isinstance(descriptor, staticmethod)}"
        f" classify_skip_line={source_line}"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_environment()
    if not getattr(app.state, "database_url_override", None):
        configure_engine()
    ensure_settings_table()
    app.state.started_at = time()
    _log_runtime_code_fingerprint()
    _start_profile_autonomous_loops()
    from runtime.runtime.autonomous_runtime import start_autonomous_loop, stop_autonomous_loop
    from runtime.runtime.learning_loop import start_learning_loop, stop_learning_loop
    from runtime.runtime.websocket_runtime import start_eligible_websocket_owners, stop_websocket_owner
    from v5.runtime.refresh_loop import start_self_learning_loop, stop_self_learning_loop

    app.state.autonomous_loop = start_autonomous_loop()
    app.state.learning_loop = start_learning_loop()
    app.state.self_learning_loop = start_self_learning_loop()
    try:
        app.state.websocket_owner_profiles = start_eligible_websocket_owners()
    except Exception:
        app.state.websocket_owner_profiles = []
    db_connected, db_status = check_database_connection()
    print(
        "runtime api boot"
        f" database={mask_database_url(get_database_url())}"
        f" db_connected={db_connected}"
        f" db_status={db_status}"
    )
    try:
        yield
    finally:
        stop_websocket_owner()
        stop_learning_loop()
        stop_self_learning_loop()
        stop_autonomous_loop()


logger = logging.getLogger(__name__)


def _install_request_logging(app: FastAPI) -> None:
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        started_at = time()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("api request failed method=%s path=%s", request.method, request.url.path)
            raise
        elapsed_ms = (time() - started_at) * 1000
        if response.status_code >= 500:
            logger.error(
                "api request returned server error method=%s path=%s status=%s elapsed_ms=%.1f",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
        elif response.status_code >= 400:
            logger.warning(
                "api request returned client error method=%s path=%s status=%s elapsed_ms=%.1f",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
        return response


def create_app(
    database_url: str | None = None,
    *,
    include_scans: bool = True,
    include_markets: bool = True,
) -> FastAPI:
    """Create the runtime FastAPI application."""
    _load_environment()
    if database_url:
        configure_engine(database_url)
        initialize_schema()
    logging.basicConfig(level=os.getenv("RUNTIME_LOG_LEVEL", "INFO"))
    app = FastAPI(title="Trading Bot Runtime API", version="0.1.0", lifespan=lifespan)
    app.state.database_url_override = database_url
    _install_request_logging(app)
    from runtime.api.routes.health import router as health_router
    from runtime.api.routes.analyzer import router as analyzer_router
    from runtime.api.routes.alerts import router as alerts_router
    from runtime.api.routes.calibration import router as calibration_router
    from runtime.api.routes.analytics import router as analytics_router
    from runtime.api.routes.improvements import router as improvements_router
    from runtime.api.routes.failure_analytics import router as failure_analytics_router
    from runtime.api.routes.failures import router as failures_router
    from runtime.api.routes.learning import router as learning_router
    try:
        from v5.routes import router as self_learning_router
        from v5.api import router as v5_router
    except ModuleNotFoundError as exc:
        if exc.name not in {"lancedb", "lightgbm"}:
            raise
        self_learning_router = None
        v5_router = None
    from runtime.api.routes.circuit_breaker import router as circuit_breaker_router
    from runtime.api.routes.orders import router as orders_router
    from runtime.api.routes.paper import router as paper_router
    from runtime.api.routes.performance import router as performance_router
    from runtime.api.routes.portfolio import router as portfolio_router
    from runtime.api.routes.settings import router as settings_router
    from runtime.api.routes.storage import router as storage_router
    from runtime.api.routes.signals import router as signals_router
    from runtime.api.routes.traces import router as traces_router
    from runtime.api.routes.simulations import router as simulations_router
    from runtime.api.routes.scan_events import router as scan_events_router
    from runtime.api.routes.runtime_profiles import router as runtime_profiles_router
    from runtime.api.routes.phase7_review import router as phase7_review_router
    from runtime.api.routes.phase7_operate import router as phase7_operate_router

    app.include_router(health_router)
    app.include_router(analyzer_router)
    app.include_router(alerts_router)
    app.include_router(calibration_router)
    app.include_router(analytics_router)
    app.include_router(improvements_router)
    app.include_router(failure_analytics_router)
    app.include_router(failures_router)
    app.include_router(learning_router)
    if self_learning_router is not None:
        app.include_router(self_learning_router)
    if v5_router is not None:
        app.include_router(v5_router)
    app.include_router(circuit_breaker_router)
    app.include_router(settings_router)
    app.include_router(storage_router)
    app.include_router(signals_router)
    app.include_router(orders_router)
    app.include_router(paper_router)
    app.include_router(portfolio_router)
    app.include_router(performance_router)
    app.include_router(traces_router)
    app.include_router(simulations_router)
    app.include_router(scan_events_router)
    app.include_router(runtime_profiles_router)
    app.include_router(phase7_review_router)
    app.include_router(phase7_operate_router)
    if include_scans:
        from runtime.api.routes.scans import router as scans_router

        app.include_router(scans_router)
    if include_markets:
        from runtime.api.routes.markets import router as markets_router

        app.include_router(markets_router)
    return app
