"""Add runtime profile identity foundation and minimal profile ownership fields.

Revision ID: 20260423_0015
Revises: 20260406_0014
Create Date: 2026-04-23 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260423_0015"
down_revision = "20260406_0014"
branch_labels = None
depends_on = None


SCOPED_TABLES = (
    "v4_scan_runs",
    "v4_signals",
    "v4_orders",
    "v4_fills",
    "v4_positions",
    "v4_portfolio_snapshots",
    "v4_runtime_state",
)


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("runtime_profiles"):
        op.create_table(
            "runtime_profiles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("profile_id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("runtime_mode", sa.String(length=32), nullable=False),
            sa.Column("execution_mode", sa.String(length=32), nullable=False),
            sa.Column("venue", sa.String(length=64), nullable=False),
            sa.Column("product_type", sa.String(length=64), nullable=False),
            sa.Column("default_for_auto_trading", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("manual_trading_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("auto_trading_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("read_only", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("credential_ref", sa.String(length=255), nullable=True),
            sa.Column("created_at_utc", sa.String(length=64), nullable=False),
            sa.Column("updated_at_utc", sa.String(length=64), nullable=False),
            sa.UniqueConstraint("profile_id"),
        )
        inspector = sa.inspect(bind)

    if not _has_index(inspector, "runtime_profiles", "ix_runtime_profiles_profile_id"):
        op.create_index("ix_runtime_profiles_profile_id", "runtime_profiles", ["profile_id"], unique=True)
    if not _has_index(inspector, "runtime_profiles", "ix_runtime_profiles_status"):
        op.create_index("ix_runtime_profiles_status", "runtime_profiles", ["status"], unique=False)

    for table_name in SCOPED_TABLES:
        if not inspector.has_table(table_name):
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "profile_id" not in columns:
            op.add_column(
                table_name,
                sa.Column("profile_id", sa.String(length=64), nullable=False, server_default="paper-main"),
            )
            inspector = sa.inspect(bind)
        if not _has_index(inspector, table_name, f"ix_{table_name}_profile_id"):
            op.create_index(f"ix_{table_name}_profile_id", table_name, ["profile_id"], unique=False)
        op.execute(sa.text(f"UPDATE {table_name} SET profile_id = 'paper-main' WHERE profile_id IS NULL OR profile_id = ''"))

    op.execute(
        sa.text(
            """
            INSERT INTO runtime_profiles (
                profile_id,
                name,
                status,
                runtime_mode,
                execution_mode,
                venue,
                product_type,
                default_for_auto_trading,
                manual_trading_enabled,
                auto_trading_enabled,
                read_only,
                credential_ref,
                created_at_utc,
                updated_at_utc
            )
            SELECT
                'paper-main',
                'Paper Main',
                'ACTIVE',
                'PAPER',
                'PAPER',
                'INTERNAL_PAPER',
                'SIMULATED',
                true,
                true,
                false,
                false,
                NULL,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1 FROM runtime_profiles WHERE profile_id = 'paper-main'
            )
            """
        )
    )



def downgrade() -> None:
    for table_name in reversed(SCOPED_TABLES):
        op.drop_index(f"ix_{table_name}_profile_id", table_name=table_name)
        op.drop_column(table_name, "profile_id")

    op.drop_index("ix_runtime_profiles_status", table_name="runtime_profiles")
    op.drop_index("ix_runtime_profiles_profile_id", table_name="runtime_profiles")
    op.drop_table("runtime_profiles")
