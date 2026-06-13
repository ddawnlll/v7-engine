"""add simulation presets

Revision ID: 20260428_0022
Revises: 20260428_0021
Create Date: 2026-04-28 02:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260428_0022"
down_revision = "20260428_0021"
branch_labels = None
depends_on = None

TABLE_NAME = "v4_simulation_presets"
INDEXES = [
    ("ix_v4_simulation_presets_profile_id", ["profile_id"], False),
    ("ix_v4_simulation_presets_created_at", ["created_at"], False),
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
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("profile_id", sa.String(length=64), nullable=True),
            sa.Column("symbols_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("intervals_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("modes_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("period_start", sa.String(length=64), nullable=True),
            sa.Column("period_end", sa.String(length=64), nullable=True),
            sa.Column("capital", sa.Float(), nullable=True),
            sa.Column("execution_settings_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_by", sa.Text(), nullable=True),
            sa.Column("updated_by", sa.Text(), nullable=True),
            sa.Column("created_at", sa.String(length=64), nullable=False),
            sa.Column("updated_at", sa.String(length=64), nullable=False),
            sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"),
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
