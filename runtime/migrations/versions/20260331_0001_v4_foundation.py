"""initial v4 operational schema

Revision ID: 20260331_0001
Revises:
Create Date: 2026-03-31 22:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260331_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v4_runtime_settings",
        sa.Column("key", sa.String(length=255), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "v4_candles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("interval", sa.String(length=16), nullable=False),
        sa.Column("open_time_utc", sa.String(length=64), nullable=False),
        sa.Column("close_time_utc", sa.String(length=64), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("stale", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "v4_scan_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("requested_by", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("symbols_csv", sa.Text(), nullable=False),
        sa.Column("intervals_csv", sa.Text(), nullable=False),
        sa.Column("modes_csv", sa.Text(), nullable=False),
        sa.Column("signal_count", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("created_at_utc", sa.String(length=64), nullable=False),
        sa.Column("started_at_utc", sa.String(length=64), nullable=True),
        sa.Column("finished_at_utc", sa.String(length=64), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.UniqueConstraint("run_id"),
    )
    op.create_table(
        "v4_signals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("signal_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("interval", sa.String(length=16), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("regime", sa.String(length=32), nullable=False),
        sa.Column("trend", sa.String(length=32), nullable=False),
        sa.Column("trend_strength", sa.Float(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("no_trade_reason", sa.Text(), nullable=True),
        sa.Column("strategy_version", sa.String(length=64), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("factors_json", sa.Text(), nullable=False),
        sa.Column("created_at_utc", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("signal_id"),
    )
    op.create_table(
        "v4_orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.String(length=128), nullable=False),
        sa.Column("signal_id", sa.String(length=128), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("interval", sa.String(length=16), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("entry", sa.Float(), nullable=False),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("take_profit", sa.Float(), nullable=True),
        sa.Column("close_price", sa.Float(), nullable=True),
        sa.Column("risk_reward", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("opened_at_utc", sa.String(length=64), nullable=False),
        sa.Column("closed_at_utc", sa.String(length=64), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.UniqueConstraint("order_id"),
    )
    op.create_table(
        "v4_fills",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("fill_id", sa.String(length=128), nullable=False),
        sa.Column("order_id", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("fee", sa.Float(), nullable=False),
        sa.Column("filled_at_utc", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("fill_id"),
    )
    op.create_table(
        "v4_positions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("position_id", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("interval", sa.String(length=16), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("average_entry", sa.Float(), nullable=False),
        sa.Column("mark_price", sa.Float(), nullable=True),
        sa.Column("unrealized_pnl", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("opened_at_utc", sa.String(length=64), nullable=False),
        sa.Column("closed_at_utc", sa.String(length=64), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.UniqueConstraint("position_id"),
    )
    op.create_table(
        "v4_portfolio_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", sa.String(length=128), nullable=False),
        sa.Column("total_equity", sa.Float(), nullable=False),
        sa.Column("cash_balance", sa.Float(), nullable=False),
        sa.Column("unrealized_pnl", sa.Float(), nullable=False),
        sa.Column("realized_pnl", sa.Float(), nullable=False),
        sa.Column("open_positions", sa.Integer(), nullable=False),
        sa.Column("closed_trades", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("created_at_utc", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("snapshot_id"),
    )
    op.create_table(
        "v4_alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("alert_id", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=128), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("detected_at_utc", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("alert_id"),
    )

    op.create_index("ix_v4_candles_symbol", "v4_candles", ["symbol"], unique=False)
    op.create_index("ix_v4_candles_interval", "v4_candles", ["interval"], unique=False)
    op.create_index("ix_v4_candles_open_time_utc", "v4_candles", ["open_time_utc"], unique=False)
    op.create_index("ix_v4_scan_runs_run_id", "v4_scan_runs", ["run_id"], unique=False)
    op.create_index("ix_v4_scan_runs_status", "v4_scan_runs", ["status"], unique=False)
    op.create_index("ix_v4_signals_signal_id", "v4_signals", ["signal_id"], unique=False)
    op.create_index("ix_v4_signals_run_id", "v4_signals", ["run_id"], unique=False)
    op.create_index("ix_v4_signals_symbol", "v4_signals", ["symbol"], unique=False)
    op.create_index("ix_v4_signals_interval", "v4_signals", ["interval"], unique=False)
    op.create_index("ix_v4_signals_mode", "v4_signals", ["mode"], unique=False)
    op.create_index("ix_v4_signals_created_at_utc", "v4_signals", ["created_at_utc"], unique=False)
    op.create_index("ix_v4_orders_order_id", "v4_orders", ["order_id"], unique=False)
    op.create_index("ix_v4_orders_signal_id", "v4_orders", ["signal_id"], unique=False)
    op.create_index("ix_v4_orders_symbol", "v4_orders", ["symbol"], unique=False)
    op.create_index("ix_v4_orders_status", "v4_orders", ["status"], unique=False)
    op.create_index("ix_v4_fills_fill_id", "v4_fills", ["fill_id"], unique=False)
    op.create_index("ix_v4_fills_order_id", "v4_fills", ["order_id"], unique=False)
    op.create_index("ix_v4_fills_symbol", "v4_fills", ["symbol"], unique=False)
    op.create_index("ix_v4_positions_position_id", "v4_positions", ["position_id"], unique=False)
    op.create_index("ix_v4_positions_symbol", "v4_positions", ["symbol"], unique=False)
    op.create_index("ix_v4_positions_status", "v4_positions", ["status"], unique=False)
    op.create_index("ix_v4_portfolio_snapshots_snapshot_id", "v4_portfolio_snapshots", ["snapshot_id"], unique=False)
    op.create_index("ix_v4_portfolio_snapshots_created_at_utc", "v4_portfolio_snapshots", ["created_at_utc"], unique=False)
    op.create_index("ix_v4_alerts_alert_id", "v4_alerts", ["alert_id"], unique=False)
    op.create_index("ix_v4_alerts_severity", "v4_alerts", ["severity"], unique=False)
    op.create_index("ix_v4_alerts_kind", "v4_alerts", ["kind"], unique=False)
    op.create_index("ix_v4_alerts_detected_at_utc", "v4_alerts", ["detected_at_utc"], unique=False)


def downgrade() -> None:
    for index_name, table_name in [
        ("ix_v4_alerts_detected_at_utc", "v4_alerts"),
        ("ix_v4_alerts_kind", "v4_alerts"),
        ("ix_v4_alerts_severity", "v4_alerts"),
        ("ix_v4_alerts_alert_id", "v4_alerts"),
        ("ix_v4_portfolio_snapshots_created_at_utc", "v4_portfolio_snapshots"),
        ("ix_v4_portfolio_snapshots_snapshot_id", "v4_portfolio_snapshots"),
        ("ix_v4_positions_status", "v4_positions"),
        ("ix_v4_positions_symbol", "v4_positions"),
        ("ix_v4_positions_position_id", "v4_positions"),
        ("ix_v4_fills_symbol", "v4_fills"),
        ("ix_v4_fills_order_id", "v4_fills"),
        ("ix_v4_fills_fill_id", "v4_fills"),
        ("ix_v4_orders_status", "v4_orders"),
        ("ix_v4_orders_symbol", "v4_orders"),
        ("ix_v4_orders_signal_id", "v4_orders"),
        ("ix_v4_orders_order_id", "v4_orders"),
        ("ix_v4_signals_created_at_utc", "v4_signals"),
        ("ix_v4_signals_mode", "v4_signals"),
        ("ix_v4_signals_interval", "v4_signals"),
        ("ix_v4_signals_symbol", "v4_signals"),
        ("ix_v4_signals_run_id", "v4_signals"),
        ("ix_v4_signals_signal_id", "v4_signals"),
        ("ix_v4_scan_runs_status", "v4_scan_runs"),
        ("ix_v4_scan_runs_run_id", "v4_scan_runs"),
        ("ix_v4_candles_open_time_utc", "v4_candles"),
        ("ix_v4_candles_interval", "v4_candles"),
        ("ix_v4_candles_symbol", "v4_candles"),
    ]:
        op.drop_index(index_name, table_name=table_name)

    op.drop_table("v4_alerts")
    op.drop_table("v4_portfolio_snapshots")
    op.drop_table("v4_positions")
    op.drop_table("v4_fills")
    op.drop_table("v4_orders")
    op.drop_table("v4_signals")
    op.drop_table("v4_scan_runs")
    op.drop_table("v4_candles")
    op.drop_table("v4_runtime_settings")
