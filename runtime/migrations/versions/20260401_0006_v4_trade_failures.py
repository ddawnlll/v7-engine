"""Add trade failure classification storage for v4."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260401_0006"
down_revision = "20260401_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v4_trade_failures",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.String(length=128), nullable=False),
        sa.Column("signal_id", sa.String(length=128), nullable=True),
        sa.Column("failure_source", sa.String(length=64), nullable=False),
        sa.Column("blamed_component", sa.String(length=64), nullable=False),
        sa.Column("severity_score", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("classification", sa.String(length=128), nullable=False, server_default="UNCLASSIFIED"),
        sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
        sa.Column("improvement", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at_utc", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_v4_trade_failures_order_id", "v4_trade_failures", ["order_id"], unique=True)
    op.create_index("ix_v4_trade_failures_signal_id", "v4_trade_failures", ["signal_id"], unique=False)
    op.create_index("ix_v4_trade_failures_failure_source", "v4_trade_failures", ["failure_source"], unique=False)
    op.create_index("ix_v4_trade_failures_blamed_component", "v4_trade_failures", ["blamed_component"], unique=False)
    op.create_index("ix_v4_trade_failures_created_at_utc", "v4_trade_failures", ["created_at_utc"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_v4_trade_failures_created_at_utc", table_name="v4_trade_failures")
    op.drop_index("ix_v4_trade_failures_blamed_component", table_name="v4_trade_failures")
    op.drop_index("ix_v4_trade_failures_failure_source", table_name="v4_trade_failures")
    op.drop_index("ix_v4_trade_failures_signal_id", table_name="v4_trade_failures")
    op.drop_index("ix_v4_trade_failures_order_id", table_name="v4_trade_failures")
    op.drop_table("v4_trade_failures")
