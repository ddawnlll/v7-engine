"""Add Binance USDⓈ-M read-only REST venue-state storage.

Revision ID: 20260424_0020
Revises: 20260424_0019
Create Date: 2026-04-24 22:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260424_0020"
down_revision = "20260424_0019"
branch_labels = None
depends_on = None


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("profile_accounts"):
        account_columns = {column["name"] for column in inspector.get_columns("profile_accounts")}
        if "payload_json" not in account_columns:
            with op.batch_alter_table("profile_accounts") as batch_op:
                batch_op.add_column(sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"))
            inspector = sa.inspect(bind)

    if not inspector.has_table("profile_venue_balances"):
        op.create_table(
            "profile_venue_balances",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("balance_id", sa.String(length=160), nullable=False),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("venue", sa.String(length=64), nullable=False, server_default="BINANCE_USDM"),
        sa.Column("asset", sa.String(length=32), nullable=False),
        sa.Column("balance", sa.Float(), nullable=False, server_default="0"),
        sa.Column("available_balance", sa.Float(), nullable=False, server_default="0"),
        sa.Column("margin_balance", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cross_wallet_balance", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cross_unrealized_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("max_withdraw_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("margin_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("update_time_utc", sa.String(length=64), nullable=True),
        sa.Column("synced_at_utc", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
    )
    inspector = sa.inspect(bind)
    for index_name, columns, unique in (
        ("ix_profile_venue_balances_balance_id", ["balance_id"], True),
        ("ix_profile_venue_balances_profile_id", ["profile_id"], False),
        ("ix_profile_venue_balances_account_id", ["account_id"], False),
        ("ix_profile_venue_balances_venue", ["venue"], False),
        ("ix_profile_venue_balances_asset", ["asset"], False),
        ("ix_profile_venue_balances_synced_at_utc", ["synced_at_utc"], False),
    ):
        if not _has_index(inspector, "profile_venue_balances", index_name):
            op.create_index(index_name, "profile_venue_balances", columns, unique=unique)

    if not inspector.has_table("profile_venue_positions"):
        op.create_table(
            "profile_venue_positions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("position_id", sa.String(length=160), nullable=False),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("venue", sa.String(length=64), nullable=False, server_default="BINANCE_USDM"),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("position_side", sa.String(length=16), nullable=False, server_default="BOTH"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="OPEN"),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("entry_price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("break_even_price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("mark_price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("unrealized_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("liquidation_price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("leverage", sa.Float(), nullable=False, server_default="0"),
        sa.Column("margin_type", sa.String(length=32), nullable=False, server_default="cross"),
        sa.Column("isolated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("isolated_margin", sa.Float(), nullable=False, server_default="0"),
        sa.Column("notional", sa.Float(), nullable=False, server_default="0"),
        sa.Column("max_notional_value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("update_time_utc", sa.String(length=64), nullable=True),
        sa.Column("synced_at_utc", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
    )
    inspector = sa.inspect(bind)
    for index_name, columns, unique in (
        ("ix_profile_venue_positions_position_id", ["position_id"], True),
        ("ix_profile_venue_positions_profile_id", ["profile_id"], False),
        ("ix_profile_venue_positions_account_id", ["account_id"], False),
        ("ix_profile_venue_positions_venue", ["venue"], False),
        ("ix_profile_venue_positions_symbol", ["symbol"], False),
        ("ix_profile_venue_positions_position_side", ["position_side"], False),
        ("ix_profile_venue_positions_status", ["status"], False),
        ("ix_profile_venue_positions_synced_at_utc", ["synced_at_utc"], False),
    ):
        if not _has_index(inspector, "profile_venue_positions", index_name):
            op.create_index(index_name, "profile_venue_positions", columns, unique=unique)

    if not inspector.has_table("profile_venue_orders"):
        op.create_table(
            "profile_venue_orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_key", sa.String(length=192), nullable=False),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("venue", sa.String(length=64), nullable=False, server_default="BINANCE_USDM"),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("venue_order_id", sa.String(length=128), nullable=False),
        sa.Column("client_order_id", sa.String(length=128), nullable=True),
        sa.Column("side", sa.String(length=16), nullable=False, server_default="BUY"),
        sa.Column("position_side", sa.String(length=16), nullable=False, server_default="BOTH"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="NEW"),
        sa.Column("order_type", sa.String(length=64), nullable=False, server_default="LIMIT"),
        sa.Column("orig_type", sa.String(length=64), nullable=True),
        sa.Column("time_in_force", sa.String(length=16), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("executed_quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("stop_price", sa.Float(), nullable=True),
        sa.Column("activate_price", sa.Float(), nullable=True),
        sa.Column("price_rate", sa.Float(), nullable=True),
        sa.Column("reduce_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("close_position", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("working_type", sa.String(length=32), nullable=True),
        sa.Column("price_protect", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_protective", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("opened_at_utc", sa.String(length=64), nullable=True),
        sa.Column("updated_at_utc", sa.String(length=64), nullable=True),
        sa.Column("synced_at_utc", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
    )
    inspector = sa.inspect(bind)
    for index_name, columns, unique in (
        ("ix_profile_venue_orders_order_key", ["order_key"], True),
        ("ix_profile_venue_orders_profile_id", ["profile_id"], False),
        ("ix_profile_venue_orders_account_id", ["account_id"], False),
        ("ix_profile_venue_orders_venue", ["venue"], False),
        ("ix_profile_venue_orders_symbol", ["symbol"], False),
        ("ix_profile_venue_orders_venue_order_id", ["venue_order_id"], False),
        ("ix_profile_venue_orders_client_order_id", ["client_order_id"], False),
        ("ix_profile_venue_orders_status", ["status"], False),
        ("ix_profile_venue_orders_synced_at_utc", ["synced_at_utc"], False),
    ):
        if not _has_index(inspector, "profile_venue_orders", index_name):
            op.create_index(index_name, "profile_venue_orders", columns, unique=unique)


def downgrade() -> None:
    op.drop_index("ix_profile_venue_orders_synced_at_utc", table_name="profile_venue_orders")
    op.drop_index("ix_profile_venue_orders_status", table_name="profile_venue_orders")
    op.drop_index("ix_profile_venue_orders_client_order_id", table_name="profile_venue_orders")
    op.drop_index("ix_profile_venue_orders_venue_order_id", table_name="profile_venue_orders")
    op.drop_index("ix_profile_venue_orders_symbol", table_name="profile_venue_orders")
    op.drop_index("ix_profile_venue_orders_venue", table_name="profile_venue_orders")
    op.drop_index("ix_profile_venue_orders_account_id", table_name="profile_venue_orders")
    op.drop_index("ix_profile_venue_orders_profile_id", table_name="profile_venue_orders")
    op.drop_index("ix_profile_venue_orders_order_key", table_name="profile_venue_orders")
    op.drop_table("profile_venue_orders")

    op.drop_index("ix_profile_venue_positions_synced_at_utc", table_name="profile_venue_positions")
    op.drop_index("ix_profile_venue_positions_status", table_name="profile_venue_positions")
    op.drop_index("ix_profile_venue_positions_position_side", table_name="profile_venue_positions")
    op.drop_index("ix_profile_venue_positions_symbol", table_name="profile_venue_positions")
    op.drop_index("ix_profile_venue_positions_venue", table_name="profile_venue_positions")
    op.drop_index("ix_profile_venue_positions_account_id", table_name="profile_venue_positions")
    op.drop_index("ix_profile_venue_positions_profile_id", table_name="profile_venue_positions")
    op.drop_index("ix_profile_venue_positions_position_id", table_name="profile_venue_positions")
    op.drop_table("profile_venue_positions")

    op.drop_index("ix_profile_venue_balances_synced_at_utc", table_name="profile_venue_balances")
    op.drop_index("ix_profile_venue_balances_asset", table_name="profile_venue_balances")
    op.drop_index("ix_profile_venue_balances_venue", table_name="profile_venue_balances")
    op.drop_index("ix_profile_venue_balances_account_id", table_name="profile_venue_balances")
    op.drop_index("ix_profile_venue_balances_profile_id", table_name="profile_venue_balances")
    op.drop_index("ix_profile_venue_balances_balance_id", table_name="profile_venue_balances")
    op.drop_table("profile_venue_balances")

    with op.batch_alter_table("profile_accounts") as batch_op:
        batch_op.drop_column("payload_json")
