"""add runtime state table to v4

Revision ID: 20260401_0003
Revises: 20260401_0002
Create Date: 2026-04-01 13:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260401_0003"
down_revision = "20260401_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v4_runtime_state",
        sa.Column("key", sa.String(length=255), primary_key=True),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("v4_runtime_state")
