"""Add signal audit trail storage for v4."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260401_0008"
down_revision = "20260401_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "v4_signals",
        sa.Column("audit_json", sa.Text(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("v4_signals", "audit_json")
