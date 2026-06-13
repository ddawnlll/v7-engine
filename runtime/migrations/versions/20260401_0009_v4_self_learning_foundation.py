"""Add self-learning foundation tables for v4."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260401_0009"
down_revision = "20260401_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v4_trade_memories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("signal_id", sa.String(length=128), nullable=False),
        sa.Column("order_id", sa.String(length=128), nullable=True),
        sa.Column("learning_regime", sa.String(length=255), nullable=False),
        sa.Column("regime_confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("regime_stability_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("regime_version", sa.String(length=64), nullable=False, server_default="v1"),
        sa.Column("context_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("outcome_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("summary_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("result_label", sa.String(length=32), nullable=False, server_default="BREAKEVEN"),
        sa.Column("realized_r", sa.Float(), nullable=True),
        sa.Column("mae", sa.Float(), nullable=True),
        sa.Column("mfe", sa.Float(), nullable=True),
        sa.Column("hold_minutes", sa.Float(), nullable=True),
        sa.Column("decay_weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at_utc", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_v4_trade_memories_signal_id", "v4_trade_memories", ["signal_id"], unique=True)
    op.create_index("ix_v4_trade_memories_order_id", "v4_trade_memories", ["order_id"], unique=False)
    op.create_index("ix_v4_trade_memories_learning_regime", "v4_trade_memories", ["learning_regime"], unique=False)
    op.create_index("ix_v4_trade_memories_result_label", "v4_trade_memories", ["result_label"], unique=False)
    op.create_index("ix_v4_trade_memories_created_at_utc", "v4_trade_memories", ["created_at_utc"], unique=False)

    op.create_table(
        "v4_self_learning_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("started_at_utc", sa.String(length=64), nullable=False),
        sa.Column("completed_at_utc", sa.String(length=64), nullable=True),
        sa.Column("samples_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_v4_self_learning_runs_run_type", "v4_self_learning_runs", ["run_type"], unique=False)
    op.create_index("ix_v4_self_learning_runs_status", "v4_self_learning_runs", ["status"], unique=False)

    op.create_table(
        "v4_counterfactual_replays",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.String(length=128), nullable=False),
        sa.Column("signal_id", sa.String(length=128), nullable=False),
        sa.Column("action_label", sa.String(length=64), nullable=False),
        sa.Column("is_actual_action", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("learning_regime", sa.String(length=255), nullable=False),
        sa.Column("realized_r", sa.Float(), nullable=True),
        sa.Column("mae", sa.Float(), nullable=True),
        sa.Column("mfe", sa.Float(), nullable=True),
        sa.Column("hold_minutes", sa.Float(), nullable=True),
        sa.Column("outperformed_actual", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("delta_r_vs_actual", sa.Float(), nullable=True),
        sa.Column("created_at_utc", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_v4_counterfactual_replays_order_id", "v4_counterfactual_replays", ["order_id"], unique=False)
    op.create_index("ix_v4_counterfactual_replays_signal_id", "v4_counterfactual_replays", ["signal_id"], unique=False)
    op.create_index("ix_v4_counterfactual_replays_action_label", "v4_counterfactual_replays", ["action_label"], unique=False)
    op.create_index("ix_v4_counterfactual_replays_learning_regime", "v4_counterfactual_replays", ["learning_regime"], unique=False)

    op.create_table(
        "v4_policy_examples",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("signal_id", sa.String(length=128), nullable=False),
        sa.Column("order_id", sa.String(length=128), nullable=True),
        sa.Column("learning_regime", sa.String(length=255), nullable=False),
        sa.Column("context_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("candidate_actions_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("best_action_label", sa.String(length=64), nullable=False, server_default="NO_TRADE"),
        sa.Column("best_action_realized_r", sa.Float(), nullable=True),
        sa.Column("actual_action_label", sa.String(length=64), nullable=False, server_default="ENTER_NOW"),
        sa.Column("actual_action_realized_r", sa.Float(), nullable=True),
        sa.Column("regret_vs_best", sa.Float(), nullable=True),
        sa.Column("provisional", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at_utc", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_v4_policy_examples_signal_id", "v4_policy_examples", ["signal_id"], unique=True)
    op.create_index("ix_v4_policy_examples_order_id", "v4_policy_examples", ["order_id"], unique=False)
    op.create_index("ix_v4_policy_examples_learning_regime", "v4_policy_examples", ["learning_regime"], unique=False)
    op.create_index("ix_v4_policy_examples_created_at_utc", "v4_policy_examples", ["created_at_utc"], unique=False)

    op.create_table(
        "v4_expectancy_label_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("learning_regime", sa.String(length=255), nullable=False),
        sa.Column("lookback_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expected_r", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("stop_hit_probability", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("target_hit_probability", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("avg_mae", sa.Float(), nullable=True),
        sa.Column("avg_mfe", sa.Float(), nullable=True),
        sa.Column("avg_hold_minutes", sa.Float(), nullable=True),
        sa.Column("created_at_utc", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_v4_expectancy_label_profiles_learning_regime", "v4_expectancy_label_profiles", ["learning_regime"], unique=False)
    op.create_index("ix_v4_expectancy_label_profiles_created_at_utc", "v4_expectancy_label_profiles", ["created_at_utc"], unique=False)

    op.create_table(
        "v4_shadow_policy_decisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("signal_id", sa.String(length=128), nullable=False),
        sa.Column("generated_at_utc", sa.String(length=64), nullable=False),
        sa.Column("recommended_action", sa.String(length=64), nullable=False, server_default="NO_RECOMMENDATION"),
        sa.Column("support_samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expected_reward", sa.Float(), nullable=True),
        sa.Column("uncertainty_score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("learning_regime", sa.String(length=255), nullable=False),
        sa.Column("similar_case_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_v4_shadow_policy_decisions_signal_id", "v4_shadow_policy_decisions", ["signal_id"], unique=True)
    op.create_index("ix_v4_shadow_policy_decisions_generated_at_utc", "v4_shadow_policy_decisions", ["generated_at_utc"], unique=False)
    op.create_index("ix_v4_shadow_policy_decisions_learning_regime", "v4_shadow_policy_decisions", ["learning_regime"], unique=False)


def downgrade() -> None:
    for index_name, table_name in [
        ("ix_v4_shadow_policy_decisions_learning_regime", "v4_shadow_policy_decisions"),
        ("ix_v4_shadow_policy_decisions_generated_at_utc", "v4_shadow_policy_decisions"),
        ("ix_v4_shadow_policy_decisions_signal_id", "v4_shadow_policy_decisions"),
        ("ix_v4_expectancy_label_profiles_created_at_utc", "v4_expectancy_label_profiles"),
        ("ix_v4_expectancy_label_profiles_learning_regime", "v4_expectancy_label_profiles"),
        ("ix_v4_policy_examples_created_at_utc", "v4_policy_examples"),
        ("ix_v4_policy_examples_learning_regime", "v4_policy_examples"),
        ("ix_v4_policy_examples_order_id", "v4_policy_examples"),
        ("ix_v4_policy_examples_signal_id", "v4_policy_examples"),
        ("ix_v4_counterfactual_replays_learning_regime", "v4_counterfactual_replays"),
        ("ix_v4_counterfactual_replays_action_label", "v4_counterfactual_replays"),
        ("ix_v4_counterfactual_replays_signal_id", "v4_counterfactual_replays"),
        ("ix_v4_counterfactual_replays_order_id", "v4_counterfactual_replays"),
        ("ix_v4_self_learning_runs_status", "v4_self_learning_runs"),
        ("ix_v4_self_learning_runs_run_type", "v4_self_learning_runs"),
        ("ix_v4_trade_memories_created_at_utc", "v4_trade_memories"),
        ("ix_v4_trade_memories_result_label", "v4_trade_memories"),
        ("ix_v4_trade_memories_learning_regime", "v4_trade_memories"),
        ("ix_v4_trade_memories_order_id", "v4_trade_memories"),
        ("ix_v4_trade_memories_signal_id", "v4_trade_memories"),
    ]:
        op.drop_index(index_name, table_name=table_name)

    op.drop_table("v4_shadow_policy_decisions")
    op.drop_table("v4_expectancy_label_profiles")
    op.drop_table("v4_policy_examples")
    op.drop_table("v4_counterfactual_replays")
    op.drop_table("v4_self_learning_runs")
    op.drop_table("v4_trade_memories")
