"""Add engine improvements registry, manifests, and attribution tables."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260401_0010"
down_revision = "20260401_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v4_analytics_component_registry",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("component_id", sa.String(length=128), nullable=False),
        sa.Column("component_type", sa.String(length=64), nullable=False),
        sa.Column("component_name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("owner", sa.String(length=128), nullable=False, server_default="engine"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("default_params_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("ui_label", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("module_path", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("object_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("implementation_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("introduced_at_utc", sa.String(length=64), nullable=False),
        sa.Column("deprecated_at_utc", sa.String(length=64), nullable=True),
        sa.Column("created_at_utc", sa.String(length=64), nullable=False),
        sa.Column("updated_at_utc", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_v4_analytics_component_registry_component_id", "v4_analytics_component_registry", ["component_id"], unique=True)
    op.create_index("ix_v4_analytics_component_registry_component_type", "v4_analytics_component_registry", ["component_type"], unique=False)
    op.create_index("ix_v4_analytics_component_registry_status", "v4_analytics_component_registry", ["status"], unique=False)
    op.create_index("ix_v4_analytics_component_registry_version", "v4_analytics_component_registry", ["version"], unique=False)

    op.create_table(
        "v4_engine_run_manifests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("engine_version", sa.String(length=64), nullable=False, server_default="v4"),
        sa.Column("started_at_utc", sa.String(length=64), nullable=False),
        sa.Column("finished_at_utc", sa.String(length=64), nullable=True),
        sa.Column("component_snapshot_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("enabled_component_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("disabled_component_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("param_hash", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("param_snapshot_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("feature_flags_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("runtime_mode", sa.String(length=64), nullable=False, server_default="SCAN"),
        sa.Column("symbol_scope_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("interval_scope_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("summary_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_v4_engine_run_manifests_run_id", "v4_engine_run_manifests", ["run_id"], unique=True)
    op.create_index("ix_v4_engine_run_manifests_param_hash", "v4_engine_run_manifests", ["param_hash"], unique=False)

    op.create_table(
        "v4_improvement_change_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("change_id", sa.String(length=128), nullable=False),
        sa.Column("change_type", sa.String(length=64), nullable=False),
        sa.Column("component_id", sa.String(length=128), nullable=False),
        sa.Column("old_value_json", sa.Text(), nullable=True),
        sa.Column("new_value_json", sa.Text(), nullable=True),
        sa.Column("effective_from_run_id", sa.String(length=128), nullable=False),
        sa.Column("effective_at_utc", sa.String(length=64), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("author", sa.String(length=128), nullable=False, server_default="system"),
    )
    op.create_index("ix_v4_improvement_change_events_change_id", "v4_improvement_change_events", ["change_id"], unique=True)
    op.create_index("ix_v4_improvement_change_events_change_type", "v4_improvement_change_events", ["change_type"], unique=False)
    op.create_index("ix_v4_improvement_change_events_component_id", "v4_improvement_change_events", ["component_id"], unique=False)
    op.create_index("ix_v4_improvement_change_events_effective_at_utc", "v4_improvement_change_events", ["effective_at_utc"], unique=False)

    op.create_table(
        "v4_signal_component_attributions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("signal_id", sa.String(length=128), nullable=False),
        sa.Column("order_id", sa.String(length=128), nullable=True),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("component_id", sa.String(length=128), nullable=False),
        sa.Column("attribution_level", sa.String(length=32), nullable=False, server_default="PRESENCE"),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("interval", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("regime", sa.String(length=64), nullable=False, server_default="UNKNOWN"),
        sa.Column("contribution_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at_utc", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_v4_signal_component_attributions_signal_id", "v4_signal_component_attributions", ["signal_id"], unique=False)
    op.create_index("ix_v4_signal_component_attributions_order_id", "v4_signal_component_attributions", ["order_id"], unique=False)
    op.create_index("ix_v4_signal_component_attributions_run_id", "v4_signal_component_attributions", ["run_id"], unique=False)
    op.create_index("ix_v4_signal_component_attributions_component_id", "v4_signal_component_attributions", ["component_id"], unique=False)
    op.create_index("ix_v4_signal_component_attributions_created_at_utc", "v4_signal_component_attributions", ["created_at_utc"], unique=False)

    op.create_table(
        "v4_trade_component_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.String(length=128), nullable=False),
        sa.Column("signal_id", sa.String(length=128), nullable=True),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("component_id", sa.String(length=128), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("interval", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("regime", sa.String(length=64), nullable=False, server_default="UNKNOWN"),
        sa.Column("realized_r", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("close_reason", sa.String(length=64), nullable=True),
        sa.Column("failure_source", sa.String(length=64), nullable=True),
        sa.Column("blamed_component", sa.String(length=64), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at_utc", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_v4_trade_component_outcomes_order_id", "v4_trade_component_outcomes", ["order_id"], unique=False)
    op.create_index("ix_v4_trade_component_outcomes_signal_id", "v4_trade_component_outcomes", ["signal_id"], unique=False)
    op.create_index("ix_v4_trade_component_outcomes_run_id", "v4_trade_component_outcomes", ["run_id"], unique=False)
    op.create_index("ix_v4_trade_component_outcomes_component_id", "v4_trade_component_outcomes", ["component_id"], unique=False)
    op.create_index("ix_v4_trade_component_outcomes_failure_source", "v4_trade_component_outcomes", ["failure_source"], unique=False)
    op.create_index("ix_v4_trade_component_outcomes_blamed_component", "v4_trade_component_outcomes", ["blamed_component"], unique=False)
    op.create_index("ix_v4_trade_component_outcomes_created_at_utc", "v4_trade_component_outcomes", ["created_at_utc"], unique=False)


def downgrade() -> None:
    for index_name, table_name in [
        ("ix_v4_trade_component_outcomes_created_at_utc", "v4_trade_component_outcomes"),
        ("ix_v4_trade_component_outcomes_blamed_component", "v4_trade_component_outcomes"),
        ("ix_v4_trade_component_outcomes_failure_source", "v4_trade_component_outcomes"),
        ("ix_v4_trade_component_outcomes_component_id", "v4_trade_component_outcomes"),
        ("ix_v4_trade_component_outcomes_run_id", "v4_trade_component_outcomes"),
        ("ix_v4_trade_component_outcomes_signal_id", "v4_trade_component_outcomes"),
        ("ix_v4_trade_component_outcomes_order_id", "v4_trade_component_outcomes"),
        ("ix_v4_signal_component_attributions_created_at_utc", "v4_signal_component_attributions"),
        ("ix_v4_signal_component_attributions_component_id", "v4_signal_component_attributions"),
        ("ix_v4_signal_component_attributions_run_id", "v4_signal_component_attributions"),
        ("ix_v4_signal_component_attributions_order_id", "v4_signal_component_attributions"),
        ("ix_v4_signal_component_attributions_signal_id", "v4_signal_component_attributions"),
        ("ix_v4_improvement_change_events_effective_at_utc", "v4_improvement_change_events"),
        ("ix_v4_improvement_change_events_component_id", "v4_improvement_change_events"),
        ("ix_v4_improvement_change_events_change_type", "v4_improvement_change_events"),
        ("ix_v4_improvement_change_events_change_id", "v4_improvement_change_events"),
        ("ix_v4_engine_run_manifests_param_hash", "v4_engine_run_manifests"),
        ("ix_v4_engine_run_manifests_run_id", "v4_engine_run_manifests"),
        ("ix_v4_analytics_component_registry_version", "v4_analytics_component_registry"),
        ("ix_v4_analytics_component_registry_status", "v4_analytics_component_registry"),
        ("ix_v4_analytics_component_registry_component_type", "v4_analytics_component_registry"),
        ("ix_v4_analytics_component_registry_component_id", "v4_analytics_component_registry"),
    ]:
        op.drop_index(index_name, table_name=table_name)

    op.drop_table("v4_trade_component_outcomes")
    op.drop_table("v4_signal_component_attributions")
    op.drop_table("v4_improvement_change_events")
    op.drop_table("v4_engine_run_manifests")
    op.drop_table("v4_analytics_component_registry")
