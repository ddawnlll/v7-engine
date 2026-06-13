"""Add profile account/config foundation and resolved config hashes.

Revision ID: 20260423_0017
Revises: 20260423_0016
Create Date: 2026-04-23 20:30:00.000000
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

from alembic import op
import sqlalchemy as sa


revision = "20260423_0017"
down_revision = "20260423_0016"
branch_labels = None
depends_on = None


DEFAULT_RUNTIME_SETTINGS = {
    "AUTONOMOUS_ENABLED": "false",
    "AUTONOMOUS_SYMBOLS": "BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,BNBUSDT,LINKUSDT,AVAXUSDT,TRXUSDT,LTCUSDT,BCHUSDT,ETCUSDT,UNIUSDT,AAVEUSDT",
    "AUTONOMOUS_INTERVALS": "15m,30m,1h,4h,1d,3d,7d,14d,1M",
    "AUTONOMOUS_INTERVALS_SCALP": "15m,30m,1h,4h",
    "AUTONOMOUS_INTERVALS_SWING": "1h,4h,1d,3d,7d",
    "AUTONOMOUS_INTERVALS_AGGRESSIVE_SCALP": "15m,1h,4h",
    "AUTONOMOUS_MODES": "SCALP,SWING,AGGRESSIVE_SCALP",
    "AUTONOMOUS_SCAN_INTERVAL_SECONDS": "900",
    "AUTONOMOUS_MONITOR_INTERVAL_SECONDS": "15",
    "AUTONOMOUS_SCAN_WORKERS": "4",
    "AUTONOMOUS_MIN_CONFIDENCE": "35",
    "AUTONOMOUS_ALLOWED_TRADE_DIRECTIONS": "BOTH",
    "AUTONOMOUS_CONFIDENCE_POLICY": "FIXED",
    "AUTONOMOUS_CONFIDENCE_PERCENTILE": "0.90",
    "AUTONOMOUS_CONFIDENCE_LOOKBACK_TRACES": "200",
    "AUTONOMOUS_CONFIDENCE_MIN_SAMPLES": "50",
    "AUTONOMOUS_CONFIDENCE_MIN_FLOOR": "20",
    "AUTONOMOUS_CONFIDENCE_MAX_CEIL": "40",
    "SCAN_FETCH_TIMEOUT_SECONDS": "90",
    "MAX_TRADES_PER_DAY": "5",
    "PAPER_DEFAULT_BALANCE": "100",
    "PAPER_POSITION_SIZE_MIN_PCT": "2",
    "PAPER_POSITION_SIZE_MAX_PCT": "12",
    "PAPER_POSITION_CONFIDENCE_FLOOR": "60",
    "PAPER_POSITION_CONFIDENCE_CEIL": "90",
    "PAPER_ALLOW_UNFUNDED_TRADES": "true",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolved_hash(settings: dict[str, str]) -> str:
    payload = json.dumps(settings, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("profile_accounts"):
        op.create_table(
            "profile_accounts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("account_key", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("account_type", sa.String(length=64), nullable=False, server_default="PAPER_CASH"),
        sa.Column("venue_account_key", sa.String(length=128), nullable=True),
        sa.Column("balance_ccy", sa.String(length=16), nullable=False, server_default="USD"),
        sa.Column("balance", sa.Float(), nullable=False, server_default="100"),
        sa.Column("available_balance", sa.Float(), nullable=False, server_default="100"),
        sa.Column("equity", sa.Float(), nullable=False, server_default="100"),
        sa.Column("margin_used", sa.Float(), nullable=False, server_default="0"),
        sa.Column("as_of_utc", sa.String(length=64), nullable=False),
        sa.Column("created_at_utc", sa.String(length=64), nullable=False),
        sa.Column("updated_at_utc", sa.String(length=64), nullable=False),
    )
    inspector = sa.inspect(bind)
    if not _has_index(inspector, "profile_accounts", "ix_profile_accounts_account_id"):
        op.create_index("ix_profile_accounts_account_id", "profile_accounts", ["account_id"], unique=True)
    if not _has_index(inspector, "profile_accounts", "ix_profile_accounts_profile_id"):
        op.create_index("ix_profile_accounts_profile_id", "profile_accounts", ["profile_id"], unique=False)
    if not _has_index(inspector, "profile_accounts", "ix_profile_accounts_account_key"):
        op.create_index("ix_profile_accounts_account_key", "profile_accounts", ["account_key"], unique=False)

    if not inspector.has_table("config_templates"):
        op.create_table(
            "config_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("template_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("base_template_id", sa.String(length=128), nullable=True),
        sa.Column("scope", sa.String(length=32), nullable=False, server_default="RUNTIME"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("settings_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at_utc", sa.String(length=64), nullable=False),
        sa.Column("updated_at_utc", sa.String(length=64), nullable=False),
    )
    inspector = sa.inspect(bind)
    if not _has_index(inspector, "config_templates", "ix_config_templates_template_id"):
        op.create_index("ix_config_templates_template_id", "config_templates", ["template_id"], unique=True)

    if not inspector.has_table("profile_config_imports"):
        op.create_table(
            "profile_config_imports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("template_id", sa.String(length=128), nullable=False),
        sa.Column("import_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at_utc", sa.String(length=64), nullable=False),
        sa.Column("updated_at_utc", sa.String(length=64), nullable=False),
    )
    inspector = sa.inspect(bind)
    if not _has_index(inspector, "profile_config_imports", "ix_profile_config_imports_profile_id"):
        op.create_index("ix_profile_config_imports_profile_id", "profile_config_imports", ["profile_id"], unique=False)
    if not _has_index(inspector, "profile_config_imports", "ix_profile_config_imports_template_id"):
        op.create_index("ix_profile_config_imports_template_id", "profile_config_imports", ["template_id"], unique=False)

    if not inspector.has_table("profile_config_overrides"):
        op.create_table(
            "profile_config_overrides",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at_utc", sa.String(length=64), nullable=False),
    )
    inspector = sa.inspect(bind)
    if not _has_index(inspector, "profile_config_overrides", "ix_profile_config_overrides_profile_id"):
        op.create_index("ix_profile_config_overrides_profile_id", "profile_config_overrides", ["profile_id"], unique=False)
    if not _has_index(inspector, "profile_config_overrides", "ix_profile_config_overrides_key"):
        op.create_index("ix_profile_config_overrides_key", "profile_config_overrides", ["key"], unique=False)

    if not inspector.has_table("resolved_profile_configs"):
        op.create_table(
            "resolved_profile_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("resolved_config_hash", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("settings_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("provenance_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("updated_at_utc", sa.String(length=64), nullable=False),
    )
    inspector = sa.inspect(bind)
    if not _has_index(inspector, "resolved_profile_configs", "ix_resolved_profile_configs_profile_id"):
        op.create_index("ix_resolved_profile_configs_profile_id", "resolved_profile_configs", ["profile_id"], unique=True)
    if not _has_index(inspector, "resolved_profile_configs", "ix_resolved_profile_configs_resolved_config_hash"):
        op.create_index("ix_resolved_profile_configs_resolved_config_hash", "resolved_profile_configs", ["resolved_config_hash"], unique=False)

    for table_name in ("v4_scan_runs", "v4_orders", "v4_trade_traces", "v4_engine_run_manifests"):
        if not inspector.has_table(table_name):
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "resolved_config_hash" not in columns:
            op.add_column(table_name, sa.Column("resolved_config_hash", sa.String(length=128), nullable=False, server_default=""))
            inspector = sa.inspect(bind)
        if not _has_index(inspector, table_name, f"ix_{table_name}_resolved_config_hash"):
            op.create_index(f"ix_{table_name}_resolved_config_hash", table_name, ["resolved_config_hash"], unique=False)
        op.execute(sa.text(f"UPDATE {table_name} SET resolved_config_hash = '' WHERE resolved_config_hash IS NULL"))

    timestamp = _utc_now_iso()
    defaults_json = json.dumps(DEFAULT_RUNTIME_SETTINGS, sort_keys=True)
    defaults_hash = _resolved_hash(DEFAULT_RUNTIME_SETTINGS)

    config_template_params = {
        "template_id": "runtime-defaults",
        "name": "Runtime Defaults",
        "base_template_id": None,
        "scope": "RUNTIME",
        "status": "ACTIVE",
        "settings_json": defaults_json,
        "created_at_utc": timestamp,
        "updated_at_utc": timestamp,
    }
    config_template_exists = bind.execute(
        sa.text("SELECT 1 FROM config_templates WHERE template_id = :template_id LIMIT 1"),
        {"template_id": "runtime-defaults"},
    ).scalar()
    if not config_template_exists:
        bind.execute(
            sa.text(
                """
                INSERT INTO config_templates (template_id, name, base_template_id, scope, status, settings_json, created_at_utc, updated_at_utc)
                VALUES (:template_id, :name, :base_template_id, :scope, :status, :settings_json, :created_at_utc, :updated_at_utc)
                """
            ),
            config_template_params,
        )

    profile_import_params = {
        "profile_id": "paper-main",
        "template_id": "runtime-defaults",
        "import_order": 0,
        "created_at_utc": timestamp,
        "updated_at_utc": timestamp,
    }
    profile_import_exists = bind.execute(
        sa.text("SELECT 1 FROM profile_config_imports WHERE profile_id = :profile_id AND template_id = :template_id LIMIT 1"),
        {"profile_id": "paper-main", "template_id": "runtime-defaults"},
    ).scalar()
    if not profile_import_exists:
        bind.execute(
            sa.text(
                """
                INSERT INTO profile_config_imports (profile_id, template_id, import_order, created_at_utc, updated_at_utc)
                VALUES (:profile_id, :template_id, :import_order, :created_at_utc, :updated_at_utc)
                """
            ),
            profile_import_params,
        )

    resolved_config_params = {
        "profile_id": "paper-main",
        "resolved_config_hash": defaults_hash,
        "settings_json": defaults_json,
        "provenance_json": json.dumps({"profile_id": "paper-main", "template_ids": ["runtime-defaults"], "override_keys": []}, sort_keys=True),
        "updated_at_utc": timestamp,
    }
    resolved_config_exists = bind.execute(
        sa.text("SELECT 1 FROM resolved_profile_configs WHERE profile_id = :profile_id LIMIT 1"),
        {"profile_id": "paper-main"},
    ).scalar()
    if not resolved_config_exists:
        bind.execute(
            sa.text(
                """
                INSERT INTO resolved_profile_configs (profile_id, resolved_config_hash, settings_json, provenance_json, updated_at_utc)
                VALUES (:profile_id, :resolved_config_hash, :settings_json, :provenance_json, :updated_at_utc)
                """
            ),
            resolved_config_params,
        )

    conn = bind
    legacy_balance = conn.execute(sa.text("SELECT balance FROM v4_paper_accounts WHERE account_key = 'default' LIMIT 1")).scalar()
    global_balance = conn.execute(sa.text("SELECT value FROM v4_runtime_settings WHERE key = 'PAPER_DEFAULT_BALANCE' LIMIT 1")).scalar()
    try:
        balance = float(legacy_balance if legacy_balance is not None else global_balance if global_balance is not None else 100.0)
    except (TypeError, ValueError):
        balance = 100.0
    account_columns = {column["name"] for column in sa.inspect(bind).get_columns("profile_accounts")}
    payload_fragment = ", payload_json" if "payload_json" in account_columns else ""
    payload_values_fragment = ", :payload_json" if "payload_json" in account_columns else ""
    params = {
        "account_id": "paper-main:default",
        "profile_id": "paper-main",
        "account_key": "default",
        "account_type": "PAPER_CASH",
        "venue_account_key": None,
        "balance_ccy": "USD",
        "balance": balance,
        "available_balance": balance,
        "equity": balance,
        "margin_used": 0.0,
        "payload_json": "{}",
        "as_of_utc": timestamp,
        "created_at_utc": timestamp,
        "updated_at_utc": timestamp,
    }
    account_exists = bind.execute(
        sa.text("SELECT 1 FROM profile_accounts WHERE account_id = :account_id LIMIT 1"),
        {"account_id": "paper-main:default"},
    ).scalar()
    if not account_exists:
        bind.execute(
            sa.text(
                f"""
                INSERT INTO profile_accounts (
                    account_id, profile_id, account_key, account_type, venue_account_key, balance_ccy,
                    balance, available_balance, equity, margin_used{payload_fragment}, as_of_utc, created_at_utc, updated_at_utc
                ) VALUES (
                    :account_id, :profile_id, :account_key, :account_type, :venue_account_key, :balance_ccy,
                    :balance, :available_balance, :equity, :margin_used{payload_values_fragment}, :as_of_utc, :created_at_utc, :updated_at_utc
                )
                """
            ),
            params,
        )


def downgrade() -> None:
    for table_name in reversed(("v4_scan_runs", "v4_orders", "v4_trade_traces", "v4_engine_run_manifests")):
        op.drop_index(f"ix_{table_name}_resolved_config_hash", table_name=table_name)
        op.drop_column(table_name, "resolved_config_hash")

    op.drop_index("ix_resolved_profile_configs_resolved_config_hash", table_name="resolved_profile_configs")
    op.drop_index("ix_resolved_profile_configs_profile_id", table_name="resolved_profile_configs")
    op.drop_table("resolved_profile_configs")

    op.drop_index("ix_profile_config_overrides_key", table_name="profile_config_overrides")
    op.drop_index("ix_profile_config_overrides_profile_id", table_name="profile_config_overrides")
    op.drop_table("profile_config_overrides")

    op.drop_index("ix_profile_config_imports_template_id", table_name="profile_config_imports")
    op.drop_index("ix_profile_config_imports_profile_id", table_name="profile_config_imports")
    op.drop_table("profile_config_imports")

    op.drop_index("ix_config_templates_template_id", table_name="config_templates")
    op.drop_table("config_templates")

    op.drop_index("ix_profile_accounts_account_key", table_name="profile_accounts")
    op.drop_index("ix_profile_accounts_profile_id", table_name="profile_accounts")
    op.drop_index("ix_profile_accounts_account_id", table_name="profile_accounts")
    op.drop_table("profile_accounts")
