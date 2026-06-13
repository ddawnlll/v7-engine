"""Add circuit breaker event storage for v4."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260401_0007"
down_revision = "20260401_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v4_circuit_breaker_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("failure_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("consecutive_losses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("triggered_at_utc", sa.String(length=64), nullable=False),
        sa.Column("resolved_at_utc", sa.String(length=64), nullable=True),
        sa.Column("auto_resume_at_utc", sa.String(length=64), nullable=True),
        sa.Column("active_rules_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("session_breakdown_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("time_of_day_breakdown_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at_utc", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_v4_circuit_breaker_events_status", "v4_circuit_breaker_events", ["status"], unique=False)
    op.create_index("ix_v4_circuit_breaker_events_triggered_at_utc", "v4_circuit_breaker_events", ["triggered_at_utc"], unique=False)
    op.create_index("ix_v4_circuit_breaker_events_created_at_utc", "v4_circuit_breaker_events", ["created_at_utc"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_v4_circuit_breaker_events_created_at_utc", table_name="v4_circuit_breaker_events")
    op.drop_index("ix_v4_circuit_breaker_events_triggered_at_utc", table_name="v4_circuit_breaker_events")
    op.drop_index("ix_v4_circuit_breaker_events_status", table_name="v4_circuit_breaker_events")
    op.drop_table("v4_circuit_breaker_events")
