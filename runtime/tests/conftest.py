"""Shared fixtures and helpers for the runtime test suite.

Provides:
- In-memory SQLite DB engine + session for integration-style tests.
- Mocked repositories for unit tests that isolate business logic.
- Pre-configured service instances.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator, Optional
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import runtime.db.session as _db_session_module


# Use in-memory SQLite to avoid needing a real database
os.environ.setdefault("V4_DATABASE_URL", "sqlite://")


# ---------------------------------------------------------------------------
# In-memory SQLite database
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def in_memory_engine():
    """Create a session-scoped in-memory SQLite engine with the v4 schema."""
    engine = create_engine("sqlite://", echo=False, future=True)
    from runtime.db.models import Base

    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def db_session(in_memory_engine) -> Iterator[Session]:
    """Provide a fresh in-memory SQLAlchemy session for each test."""
    session_factory = sessionmaker(bind=in_memory_engine, autocommit=False, autoflush=False, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def db_session_factory(in_memory_engine):
    factory = sessionmaker(bind=in_memory_engine, autocommit=False, autoflush=False, future=True)

    @contextmanager
    def make_session() -> Iterator[Session]:
        session = factory()
        try:
            yield session
        finally:
            session.rollback()
            session.close()

    return make_session


# ---------------------------------------------------------------------------
# Mocked session_scope
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_session_scope() -> Iterator[MagicMock]:
    """Patch runtime.db.session.session_scope with a MagicMock-based context manager."""
    mock_session = MagicMock(spec=Session)
    with patch.object(
        _db_session_module, "session_scope",
        wraps=contextmanager(lambda: (yield mock_session)),
    ) as mock_scope:
        setattr(mock_session, "add", MagicMock())
        setattr(mock_session, "commit", MagicMock())
        setattr(mock_session, "rollback", MagicMock())
        setattr(mock_session, "refresh", MagicMock())
        setattr(mock_session, "delete", MagicMock())
        setattr(mock_session, "execute", MagicMock())
        setattr(mock_session, "query", MagicMock())
        yield mock_session


# ---------------------------------------------------------------------------
# Mocked repositories
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_state_repo() -> MagicMock:
    from runtime.db.repos.state_repo import StateRepository
    repo = MagicMock(spec=StateRepository)
    repo.set.return_value = {"key": "scan_control", "profile_id": "paper-main", "value": None}
    repo.get.return_value = None
    repo.delete.return_value = True
    return repo


@pytest.fixture
def mock_runtime_profile_repo() -> MagicMock:
    from runtime.db.repos.runtime_profile_repo import RuntimeProfileRepository
    repo = MagicMock(spec=RuntimeProfileRepository)
    repo.get_profile.return_value = {
        "profile_id": "paper-main", "name": "Paper Main", "status": "ACTIVE",
        "runtime_mode": "PAPER", "execution_mode": "PAPER", "venue": "INTERNAL_PAPER",
        "product_type": "SIMULATED", "venue_environment": "INTERNAL",
        "api_base_url": None, "default_for_auto_trading": True,
        "manual_trading_enabled": True, "auto_trading_enabled": False,
        "read_only": False, "supports_account_reads": True,
        "supports_order_placement": True, "credential_ref": None,
        "connectivity_status": "READY",
    }
    repo.ensure_paper_main.return_value = {
        "profile_id": "paper-main", "name": "Paper Main", "status": "ACTIVE",
        "runtime_mode": "PAPER", "execution_mode": "PAPER",
        "venue": "INTERNAL_PAPER", "product_type": "SIMULATED",
        "venue_environment": "INTERNAL", "default_for_auto_trading": True,
        "manual_trading_enabled": True, "auto_trading_enabled": False,
        "read_only": False, "supports_account_reads": True,
        "supports_order_placement": True,
    }
    return repo


@pytest.fixture
def mock_circuit_breaker_repo() -> MagicMock:
    from runtime.db.repos.circuit_breaker_repo import CircuitBreakerRepository
    repo = MagicMock(spec=CircuitBreakerRepository)
    repo.get_current_state.return_value = None
    repo.list_events.return_value = []
    repo.save_event.return_value = {"id": 1, "status": "OPEN"}
    repo.resolve_event.return_value = {"id": 1, "status": "CLOSED"}
    return repo


@pytest.fixture
def mock_settings_repo() -> MagicMock:
    from runtime.db.repos.settings_repo import SettingsRepository
    repo = MagicMock(spec=SettingsRepository)
    repo.get_all.return_value = {
        "CIRCUIT_BREAKER_ENABLED": "true", "CIRCUIT_BREAKER_MANUAL_MODE": "AUTO",
        "CIRCUIT_BREAKER_LOOKBACK_TRADES": "10",
        "CIRCUIT_BREAKER_MAX_CONSECUTIVE_LOSSES": "5",
        "CIRCUIT_BREAKER_MAX_FAILURE_RATE_PCT": "70.0",
        "CIRCUIT_BREAKER_MAX_SEVERITY_AVG": "4.0",
        "CIRCUIT_BREAKER_COOLDOWN_MINUTES": "60",
        "CIRCUIT_BREAKER_DEGRADED_MULTIPLIER": "0.7",
    }
    repo.save_many.return_value = {}
    return repo


# ---------------------------------------------------------------------------
# Service fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def scan_control_service(mock_state_repo: MagicMock) -> Any:
    from runtime.runtime.scan_control import ScanControlService
    svc = ScanControlService(state_repo=mock_state_repo)
    return svc


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

def make_signal(
    symbol: str = "BTCUSDT", interval: str = "4h", mode: str = "SWING",
    direction: str = "LONG", confidence: float = 0.75, entry: float = 50000.0,
    sl: float | None = None, tp: float | None = None,
) -> dict[str, Any]:
    return {
        "symbol": symbol, "interval": interval, "mode": mode,
        "direction": direction, "confidence": confidence, "entry": entry,
        "sl": sl if sl is not None else entry * 0.98,
        "tp": tp if tp is not None else entry * 1.04,
        "stop_loss": sl if sl is not None else entry * 0.98,
        "take_profit": tp if tp is not None else entry * 1.04,
        "risk_reward": 2.0, "entry_r_multiple": 1.0,
        "signal_id": "sig-test-001", "decision_id": "dec-test-001",
        "decision_event_id": "dce-test-001", "request_id": "req-test-001",
        "run_id": "run-test-001", "trace_id": "trace-test-001",
        "source": "TEST", "origin": "AUTO",
    }
