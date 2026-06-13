"""Add V6 model registry tables."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260406_0014"
down_revision = "20260405_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_registry",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("model_artifact_version", sa.String(length=128), nullable=False),
        sa.Column("engine_name", sa.String(length=128), nullable=False),
        sa.Column("engine_version", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="CANDIDATE"),
        sa.Column("dataset_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("dataset_version", sa.String(length=128), nullable=False),
        sa.Column("feature_schema_version", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("snapshot_builder_version", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("mlflow_run_id", sa.String(length=128), nullable=True),
        sa.Column("training_timestamp_utc", sa.String(length=64), nullable=False),
        sa.Column("promoted_at_utc", sa.String(length=64), nullable=True),
        sa.Column("retired_at_utc", sa.String(length=64), nullable=True),
        sa.Column("validation_passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("validation_report_path", sa.Text(), nullable=True),
        sa.Column("artifact_path", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at_utc", sa.String(length=64), nullable=False),
        sa.Column("updated_at_utc", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_artifact_version"),
    )
    op.create_index("ix_model_registry_model_artifact_version", "model_registry", ["model_artifact_version"])
    op.create_index("ix_model_registry_engine_name", "model_registry", ["engine_name"])
    op.create_index("ix_model_registry_engine_version", "model_registry", ["engine_version"])
    op.create_index("ix_model_registry_role", "model_registry", ["role"])
    op.create_index("ix_model_registry_dataset_version", "model_registry", ["dataset_version"])

    op.create_table(
        "model_registry_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("model_artifact_version", sa.String(length=128), nullable=True),
        sa.Column("related_model_artifact_version", sa.String(length=128), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at_utc", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_model_registry_events_event_id", "model_registry_events", ["event_id"])
    op.create_index("ix_model_registry_events_event_type", "model_registry_events", ["event_type"])
    op.create_index("ix_model_registry_events_model_artifact_version", "model_registry_events", ["model_artifact_version"])
    op.create_index("ix_model_registry_events_related_model_artifact_version", "model_registry_events", ["related_model_artifact_version"])
    op.create_index("ix_model_registry_events_created_at_utc", "model_registry_events", ["created_at_utc"])


def downgrade() -> None:
    op.drop_index("ix_model_registry_events_created_at_utc", table_name="model_registry_events")
    op.drop_index("ix_model_registry_events_related_model_artifact_version", table_name="model_registry_events")
    op.drop_index("ix_model_registry_events_model_artifact_version", table_name="model_registry_events")
    op.drop_index("ix_model_registry_events_event_type", table_name="model_registry_events")
    op.drop_index("ix_model_registry_events_event_id", table_name="model_registry_events")
    op.drop_table("model_registry_events")

    op.drop_index("ix_model_registry_dataset_version", table_name="model_registry")
    op.drop_index("ix_model_registry_role", table_name="model_registry")
    op.drop_index("ix_model_registry_engine_version", table_name="model_registry")
    op.drop_index("ix_model_registry_engine_name", table_name="model_registry")
    op.drop_index("ix_model_registry_model_artifact_version", table_name="model_registry")
    op.drop_table("model_registry")
