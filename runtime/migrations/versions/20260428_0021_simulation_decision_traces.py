"""Add simulation decision trace table.

Revision ID: 20260428_0021
Revises: 20260424_0020
Create Date: 2026-04-28 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260428_0021"
down_revision = "20260424_0020"
branch_labels = None
depends_on = None

TABLE_NAME = "v4_simulation_decision_traces"
INDEXES = [
    ("ix_v4_sim_decision_traces_run_id", ["simulation_run_id"], False),
    ("ix_v4_sim_decision_traces_trace_id", ["trace_id"], True),
    ("ix_v4_sim_decision_traces_timestamp", ["timestamp"], False),
    ("ix_v4_sim_decision_traces_symbol", ["symbol"], False),
    ("ix_v4_sim_decision_traces_interval", ["interval"], False),
    ("ix_v4_sim_decision_traces_mode", ["mode"], False),
    ("ix_v4_sim_decision_traces_direction", ["direction"], False),
    ("ix_v4_sim_decision_traces_reason", ["runtime_filter_reason"], False),
    ("ix_v4_sim_decision_traces_fallback", ["fallback_used"], False),
    ("ix_v4_sim_decision_traces_confidence", ["confidence"], False),
]


def _has_index(inspector: sa.Inspector, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspector.get_indexes(TABLE_NAME))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE_NAME):
        op.create_table(
            TABLE_NAME,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("simulation_run_id", sa.Integer(), nullable=False),
            sa.Column("trace_id", sa.String(length=128), nullable=False),
            sa.Column("symbol", sa.String(length=32), nullable=False),
            sa.Column("interval", sa.String(length=16), nullable=False),
            sa.Column("mode", sa.String(length=32), nullable=False),
            sa.Column("timestamp", sa.String(length=64), nullable=False),
            sa.Column("direction", sa.String(length=16), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("signal_status", sa.String(length=32), nullable=True),
            sa.Column("selected_action", sa.String(length=64), nullable=True),
            sa.Column("selected_head", sa.String(length=64), nullable=True),
            sa.Column("runtime_filter_reason", sa.String(length=128), nullable=True),
            sa.Column("no_trade_reason", sa.Text(), nullable=True),
            sa.Column("skip_family", sa.String(length=64), nullable=True),
            sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("fallback_reason", sa.Text(), nullable=True),
            sa.Column("analysis_error", sa.Text(), nullable=True),
            sa.Column("data_error", sa.Text(), nullable=True),
            sa.Column("insufficient_history", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("confidence_raw", sa.Float(), nullable=True),
            sa.Column("confidence_final", sa.Float(), nullable=True),
            sa.Column("probability_long_raw", sa.Float(), nullable=True),
            sa.Column("probability_short_raw", sa.Float(), nullable=True),
            sa.Column("probability_no_trade_raw", sa.Float(), nullable=True),
            sa.Column("probability_long_final", sa.Float(), nullable=True),
            sa.Column("probability_short_final", sa.Float(), nullable=True),
            sa.Column("probability_no_trade_final", sa.Float(), nullable=True),
            sa.Column("entry_price", sa.Float(), nullable=True),
            sa.Column("stop_loss", sa.Float(), nullable=True),
            sa.Column("take_profit", sa.Float(), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("analyzer_metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("runtime_context_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("snapshot_metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.String(length=64), nullable=False),
        )
        inspector = sa.inspect(bind)

    for index_name, columns, unique in INDEXES:
        if not _has_index(inspector, index_name):
            op.create_index(index_name, TABLE_NAME, columns, unique=unique)
            inspector = sa.inspect(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE_NAME):
        return
    for index_name, _, _ in reversed(INDEXES):
        if _has_index(inspector, index_name):
            op.drop_index(index_name, table_name=TABLE_NAME)
            inspector = sa.inspect(bind)
    op.drop_table(TABLE_NAME)
