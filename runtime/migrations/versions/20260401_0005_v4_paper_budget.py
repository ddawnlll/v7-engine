"""Add paper account storage for v4 budgets."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260401_0005"
down_revision = "20260401_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v4_paper_accounts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_key", sa.String(length=64), nullable=False),
        sa.Column("balance", sa.Float(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_v4_paper_accounts_account_key", "v4_paper_accounts", ["account_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_v4_paper_accounts_account_key", table_name="v4_paper_accounts")
    op.drop_table("v4_paper_accounts")
