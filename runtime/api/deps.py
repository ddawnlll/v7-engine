"""Shared API dependencies for v4.

This file will own:
- request-scoped DB session access
- service wiring
- runtime/service access helpers
"""

from __future__ import annotations

from typing import Iterator

from sqlalchemy.orm import Session

from runtime.db.session import session_scope


def get_db_session() -> Iterator[Session]:
    """Request-scoped DB session dependency."""
    with session_scope() as session:
        yield session
