"""Make runtime state physically profile-scoped.

Revision ID: 20260423_0018
Revises: 20260423_0017
Create Date: 2026-04-23 23:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260423_0018"
down_revision = "20260423_0017"
branch_labels = None
depends_on = None


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("v4_runtime_state"):
        return

    columns = {column["name"] for column in inspector.get_columns("v4_runtime_state")}
    pk_columns = list((inspector.get_pk_constraint("v4_runtime_state") or {}).get("constrained_columns") or [])

    if "profile_id" in columns:
        op.execute(sa.text("UPDATE v4_runtime_state SET profile_id = 'paper-main' WHERE profile_id IS NULL OR profile_id = ''"))

    if pk_columns == ["profile_id", "key"]:
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_v4_runtime_state_profile_id ON v4_runtime_state (profile_id)"))
        return

    op.rename_table("v4_runtime_state", "v4_runtime_state_legacy")
    op.create_table(
        "v4_runtime_state",
        sa.Column("profile_id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("key", sa.String(length=255), primary_key=True, nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_v4_runtime_state_profile_id ON v4_runtime_state (profile_id)"))

    if "profile_id" in columns:
        op.execute(
            sa.text(
                """
                INSERT INTO v4_runtime_state (profile_id, key, value_json, updated_at)
                SELECT COALESCE(NULLIF(profile_id, ''), 'paper-main'), key, value_json, updated_at
                FROM v4_runtime_state_legacy
                """
            )
        )
    else:
        op.execute(
            sa.text(
                """
                INSERT INTO v4_runtime_state (profile_id, key, value_json, updated_at)
                SELECT 'paper-main', key, value_json, updated_at
                FROM v4_runtime_state_legacy
                """
            )
        )

    op.drop_table("v4_runtime_state_legacy")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("v4_runtime_state"):
        return

    op.rename_table("v4_runtime_state", "v4_runtime_state_profile_scoped")
    op.create_table(
        "v4_runtime_state",
        sa.Column("key", sa.String(length=255), primary_key=True, nullable=False),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_v4_runtime_state_profile_id", "v4_runtime_state", ["profile_id"], unique=False)
    op.execute(
        sa.text(
            """
            INSERT INTO v4_runtime_state (key, profile_id, value_json, updated_at)
            SELECT key, profile_id, value_json, updated_at
            FROM v4_runtime_state_profile_scoped
            WHERE profile_id = 'paper-main'
            """
        )
    )
    op.drop_table("v4_runtime_state_profile_scoped")
