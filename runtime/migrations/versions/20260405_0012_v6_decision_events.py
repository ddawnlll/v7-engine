"""Add V6 decision_events table."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260405_0012"
down_revision = "20260401_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decision_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("decision_event_id", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("timestamp_utc", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("interval", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("engine_name", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("engine_version", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("request_kind", sa.String(length=32), nullable=False, server_default="live_scan"),
        sa.Column("signal_status", sa.String(length=32), nullable=False, server_default="NO_TRADE"),
        sa.Column("decision_status", sa.String(length=32), nullable=False, server_default="VALID"),
        sa.Column("is_actionable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("recommended_action", sa.String(length=32), nullable=False, server_default="NO_TRADE"),
        sa.Column("direction", sa.String(length=16), nullable=False, server_default="NONE"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("deterministic_alignment", sa.String(length=32), nullable=True),
        sa.Column("deterministic_block", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("degraded_reason", sa.Text(), nullable=True),
        sa.Column("execution_path", sa.String(length=32), nullable=True),
        sa.Column("trade_outcome_id", sa.String(length=64), nullable=True),
        sa.Column("event_schema_version", sa.String(length=64), nullable=False, server_default="decision-event-0.1"),
        sa.Column("snapshot_builder_version", sa.String(length=64), nullable=True),
        sa.Column("feature_schema_version", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_event_id"),
    )
    op.create_index("ix_decision_events_request_id", "decision_events", ["request_id"])
    op.create_index("ix_decision_events_run_id", "decision_events", ["run_id"])
    op.create_index("ix_decision_events_symbol", "decision_events", ["symbol"])
    op.create_index("ix_decision_events_timestamp_utc", "decision_events", ["timestamp_utc"])


def downgrade() -> None:
    op.drop_index("ix_decision_events_timestamp_utc", table_name="decision_events")
    op.drop_index("ix_decision_events_symbol", table_name="decision_events")
    op.drop_index("ix_decision_events_run_id", table_name="decision_events")
    op.drop_index("ix_decision_events_request_id", table_name="decision_events")
    op.drop_table("decision_events")
