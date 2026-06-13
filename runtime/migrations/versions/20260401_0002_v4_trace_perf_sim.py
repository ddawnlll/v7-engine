"""add trace, performance, and simulation tables to v4

Revision ID: 20260401_0002
Revises: 20260331_0001
Create Date: 2026-04-01 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260401_0002"
down_revision = "20260331_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v4_trade_traces",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("timestamp_utc", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("interval", sa.String(length=16), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=True),
        sa.Column("direction", sa.String(length=16), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("regime", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("order_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("reason_code", sa.String(length=128), nullable=True),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("signal_payload_json", sa.Text(), nullable=False),
    )
    op.create_table(
        "v4_performance_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("timestamp_utc", sa.String(length=64), nullable=False),
        sa.Column("source_event", sa.String(length=64), nullable=False),
        sa.Column("total_trades", sa.Integer(), nullable=False),
        sa.Column("wins", sa.Integer(), nullable=False),
        sa.Column("losses", sa.Integer(), nullable=False),
        sa.Column("win_rate", sa.Float(), nullable=False),
        sa.Column("profit_factor", sa.Float(), nullable=False),
        sa.Column("net_r", sa.Float(), nullable=False),
        sa.Column("open_orders", sa.Integer(), nullable=False),
        sa.Column("closed_trades", sa.Integer(), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("portfolio_json", sa.Text(), nullable=False),
    )
    op.create_table(
        "v4_simulation_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_by", sa.Text(), nullable=True),
        sa.Column("parameters_json", sa.Text(), nullable=False),
        sa.Column("metrics_json", sa.Text(), nullable=False),
        sa.Column("created_at_utc", sa.String(length=64), nullable=False),
        sa.Column("started_at_utc", sa.String(length=64), nullable=True),
        sa.Column("finished_at_utc", sa.String(length=64), nullable=True),
    )
    op.create_table(
        "v4_simulation_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("interval", sa.String(length=16), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("realized_r", sa.Float(), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("created_at_utc", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_v4_trade_traces_trace_id", "v4_trade_traces", ["trace_id"], unique=False)
    op.create_index("ix_v4_trade_traces_timestamp_utc", "v4_trade_traces", ["timestamp_utc"], unique=False)
    op.create_index("ix_v4_trade_traces_event_type", "v4_trade_traces", ["event_type"], unique=False)
    op.create_index("ix_v4_trade_traces_symbol", "v4_trade_traces", ["symbol"], unique=False)
    op.create_index("ix_v4_performance_snapshots_timestamp_utc", "v4_performance_snapshots", ["timestamp_utc"], unique=False)
    op.create_index("ix_v4_simulation_runs_created_at_utc", "v4_simulation_runs", ["created_at_utc"], unique=False)
    op.create_index("ix_v4_simulation_results_run_id", "v4_simulation_results", ["run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_v4_simulation_results_run_id", table_name="v4_simulation_results")
    op.drop_index("ix_v4_simulation_runs_created_at_utc", table_name="v4_simulation_runs")
    op.drop_index("ix_v4_performance_snapshots_timestamp_utc", table_name="v4_performance_snapshots")
    op.drop_index("ix_v4_trade_traces_symbol", table_name="v4_trade_traces")
    op.drop_index("ix_v4_trade_traces_event_type", table_name="v4_trade_traces")
    op.drop_index("ix_v4_trade_traces_timestamp_utc", table_name="v4_trade_traces")
    op.drop_index("ix_v4_trade_traces_trace_id", table_name="v4_trade_traces")
    op.drop_table("v4_simulation_results")
    op.drop_table("v4_simulation_runs")
    op.drop_table("v4_performance_snapshots")
    op.drop_table("v4_trade_traces")
