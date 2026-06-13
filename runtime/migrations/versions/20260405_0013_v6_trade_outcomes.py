"""Add V6 trade_outcomes table."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260405_0013"
down_revision = "20260405_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trade_outcomes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trade_outcome_id", sa.String(length=64), nullable=False),
        sa.Column("decision_event_id", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("timestamp_utc", sa.String(length=64), nullable=False),
        sa.Column("outcome_status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("execution_path", sa.String(length=32), nullable=False, server_default="NOT_EVALUATED"),
        sa.Column("outcome_source", sa.String(length=32), nullable=False, server_default="PAPER_EXECUTION"),
        sa.Column("realized_return", sa.Float(), nullable=True),
        sa.Column("realized_r", sa.Float(), nullable=True),
        sa.Column("outcome_label", sa.String(length=32), nullable=True),
        sa.Column("is_good_decision", sa.Boolean(), nullable=True),
        sa.Column("outcome_schema_version", sa.String(length=64), nullable=False, server_default="trade-outcome-0.1"),
        sa.Column("created_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trade_outcome_id"),
    )
    op.create_index("ix_trade_outcomes_decision_event_id", "trade_outcomes", ["decision_event_id"])
    op.create_index("ix_trade_outcomes_request_id", "trade_outcomes", ["request_id"])
    op.create_index("ix_trade_outcomes_outcome_status", "trade_outcomes", ["outcome_status"])


def downgrade() -> None:
    op.drop_index("ix_trade_outcomes_outcome_status", table_name="trade_outcomes")
    op.drop_index("ix_trade_outcomes_request_id", table_name="trade_outcomes")
    op.drop_index("ix_trade_outcomes_decision_event_id", table_name="trade_outcomes")
    op.drop_table("trade_outcomes")
