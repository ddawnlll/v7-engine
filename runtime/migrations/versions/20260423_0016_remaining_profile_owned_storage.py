"""Add profile ownership to remaining profile-owned operational tables.

Revision ID: 20260423_0016
Revises: 20260423_0015
Create Date: 2026-04-23 16:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260423_0016"
down_revision = "20260423_0015"
branch_labels = None
depends_on = None


SCOPED_TABLES = (
    "v4_alerts",
    "v4_trade_traces",
    "v4_performance_snapshots",
    "v4_trade_failures",
    "v4_circuit_breaker_events",
    "v4_counterfactual_replays",
    "v4_shadow_policy_decisions",
    "v4_engine_run_manifests",
    "v4_signal_component_attributions",
    "v4_trade_component_outcomes",
)


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
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


def downgrade() -> None:
    for table_name in reversed(SCOPED_TABLES):
        op.drop_index(f"ix_{table_name}_profile_id", table_name=table_name)
        op.drop_column(table_name, "profile_id")
