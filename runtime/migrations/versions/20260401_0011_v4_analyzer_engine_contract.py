"""Add explicit analyzer engine metadata to persisted signals."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260401_0011"
down_revision = "20260401_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("v4_signals", sa.Column("engine_name", sa.String(length=64), nullable=False, server_default="v4_default"))
    op.add_column("v4_signals", sa.Column("engine_version", sa.String(length=64), nullable=False, server_default="v4-phase25"))
    op.add_column("v4_signals", sa.Column("engine_schema_version", sa.String(length=64), nullable=False, server_default="analysis_result.v1"))
    op.add_column("v4_signals", sa.Column("engine_fallback_used", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("v4_signals", "engine_fallback_used")
    op.drop_column("v4_signals", "engine_schema_version")
    op.drop_column("v4_signals", "engine_version")
    op.drop_column("v4_signals", "engine_name")
