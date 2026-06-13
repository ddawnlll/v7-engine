"""Add Binance USDM profile posture and connectivity foundation.

Revision ID: 20260424_0019
Revises: 20260423_0018
Create Date: 2026-04-24 21:05:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260424_0019"
down_revision = "20260423_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("runtime_profiles"):
        return

    columns = {column["name"] for column in inspector.get_columns("runtime_profiles")}
    additions = [
        ("venue_environment", sa.Column("venue_environment", sa.String(length=32), nullable=False, server_default="INTERNAL")),
        ("api_base_url", sa.Column("api_base_url", sa.String(length=255), nullable=True)),
        ("supports_account_reads", sa.Column("supports_account_reads", sa.Boolean(), nullable=False, server_default=sa.false())),
        ("supports_order_placement", sa.Column("supports_order_placement", sa.Boolean(), nullable=False, server_default=sa.false())),
        ("connectivity_status", sa.Column("connectivity_status", sa.String(length=32), nullable=False, server_default="UNKNOWN")),
        ("last_connectivity_check_at_utc", sa.Column("last_connectivity_check_at_utc", sa.String(length=64), nullable=True)),
        ("last_connectivity_ok_at_utc", sa.Column("last_connectivity_ok_at_utc", sa.String(length=64), nullable=True)),
        ("last_connectivity_error", sa.Column("last_connectivity_error", sa.Text(), nullable=True)),
    ]
    pending = [column for name, column in additions if name not in columns]
    if pending:
        with op.batch_alter_table("runtime_profiles") as batch_op:
            for column in pending:
                batch_op.add_column(column)

    op.execute(
        sa.text(
            """
            UPDATE runtime_profiles
            SET venue_environment = CASE
                    WHEN profile_id = 'paper-main' THEN 'INTERNAL'
                    ELSE venue_environment
                END,
                supports_account_reads = CASE
                    WHEN profile_id = 'paper-main' THEN true
                    ELSE supports_account_reads
                END,
                supports_order_placement = CASE
                    WHEN profile_id = 'paper-main' THEN true
                    ELSE supports_order_placement
                END,
                connectivity_status = CASE
                    WHEN profile_id = 'paper-main' THEN 'READY'
                    ELSE connectivity_status
                END,
                last_connectivity_check_at_utc = CASE
                    WHEN profile_id = 'paper-main' AND (last_connectivity_check_at_utc IS NULL OR last_connectivity_check_at_utc = '') THEN updated_at_utc
                    ELSE last_connectivity_check_at_utc
                END,
                last_connectivity_ok_at_utc = CASE
                    WHEN profile_id = 'paper-main' AND (last_connectivity_ok_at_utc IS NULL OR last_connectivity_ok_at_utc = '') THEN updated_at_utc
                    ELSE last_connectivity_ok_at_utc
                END,
                last_connectivity_error = NULL
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("runtime_profiles") as batch_op:
        batch_op.drop_column("last_connectivity_error")
        batch_op.drop_column("last_connectivity_ok_at_utc")
        batch_op.drop_column("last_connectivity_check_at_utc")
        batch_op.drop_column("connectivity_status")
        batch_op.drop_column("supports_order_placement")
        batch_op.drop_column("supports_account_reads")
        batch_op.drop_column("api_base_url")
        batch_op.drop_column("venue_environment")
