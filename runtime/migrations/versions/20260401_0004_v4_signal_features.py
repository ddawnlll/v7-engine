"""add signal features storage to v4

Revision ID: 20260401_0004
Revises: 20260401_0003
Create Date: 2026-04-01 23:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260401_0004"
down_revision = "20260401_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "v4_signals",
        sa.Column("features_json", sa.Text(), nullable=False, server_default="{}"),
    )
    bind = op.get_bind()
    if inspect(bind).dialect.name != "sqlite":
        op.alter_column("v4_signals", "features_json", server_default=None)


def downgrade() -> None:
    op.drop_column("v4_signals", "features_json")
