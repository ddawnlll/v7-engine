"""Database engine and session ownership for v4."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IllegalStateChangeError
from sqlalchemy.orm import Session, close_all_sessions, sessionmaker
from sqlalchemy.pool import StaticPool

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None
_database_url: str | None = None
_engine_configured_manually: bool = False
_DEFAULT_SQLITE_URL = "sqlite://"


def _is_stale_sqlite_url(url: str) -> bool:
    if not url.startswith("sqlite") or ":memory:" in url:
        return False
    path_text = url[len("sqlite:") :]
    while path_text.startswith("/"):
        path_text = path_text[1:]
    path = Path("/" + path_text) if url.startswith("sqlite:////") else Path(path_text.lstrip("/"))
    return not path.exists() or not os.access(path, os.W_OK)


def resolve_database_url(explicit_url: str | None = None) -> str:
    url = (
        explicit_url
        or os.environ.get("V4_DATABASE_URL")
        or os.environ.get("V4_POSTGRES_URL")
        or os.environ.get("V3_POSTGRES_URL")
        or os.environ.get("DATABASE_URL")
    )
    if not url:
        raise RuntimeError("No database URL configured. Set V4_DATABASE_URL, V4_POSTGRES_URL, V3_POSTGRES_URL, or DATABASE_URL.")
    if url.startswith("postgresql://") and "+psycopg" not in url and "+psycopg2" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def mask_database_url(url: str) -> str:
    if "@" not in url or "://" not in url:
        return url
    prefix, rest = url.split("://", 1)
    creds, host = rest.rsplit("@", 1)
    if ":" in creds:
        user, _password = creds.split(":", 1)
        return f"{prefix}://{user}:***@{host}"
    return f"{prefix}://***@{host}"


def configure_engine(database_url: str | None = None) -> None:
    global _engine, _SessionLocal, _database_url, _engine_configured_manually
    resolved = resolve_database_url(database_url)
    try:
        close_all_sessions()
    except IllegalStateChangeError:
        pass
    if _engine is not None:
        _engine.dispose()
        _engine = None
        _SessionLocal = None
    connect_args = {"check_same_thread": False} if resolved.startswith("sqlite") else {}
    engine_kwargs = {"future": True, "pool_pre_ping": True, "connect_args": connect_args}
    if resolved == "sqlite://":
        engine_kwargs["poolclass"] = StaticPool
    _engine = create_engine(resolved, **engine_kwargs)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    _database_url = resolved
    _engine_configured_manually = database_url is not None


def get_engine() -> Engine:
    global _engine, _database_url, _engine_configured_manually
    if _engine is not None:
        if _engine_configured_manually:
            return _engine
        try:
            resolved = resolve_database_url()
        except RuntimeError:
            resolved = None
        if resolved is not None and resolved != _database_url:
            if _database_url is None or _is_stale_sqlite_url(_database_url):
                configure_engine(resolved)
        return _engine
    if _database_url is not None:
        configure_engine(_database_url)
        assert _engine is not None
        return _engine
    try:
        configure_engine(resolve_database_url())
    except RuntimeError:
        configure_engine(_DEFAULT_SQLITE_URL)
    assert _engine is not None
    return _engine


def get_database_url() -> str:
    global _database_url, _engine_configured_manually
    if _database_url is not None:
        if _engine_configured_manually:
            return _database_url
        try:
            resolved = resolve_database_url()
        except RuntimeError:
            resolved = None
        if resolved is not None and resolved != _database_url:
            if _is_stale_sqlite_url(_database_url):
                configure_engine(resolved)
        return _database_url
    try:
        resolved = resolve_database_url()
    except RuntimeError:
        resolved = _DEFAULT_SQLITE_URL
    configure_engine(resolved)
    assert _database_url is not None
    return _database_url


def dispose_engine() -> None:
    global _engine, _SessionLocal, _database_url, _engine_configured_manually
    try:
        close_all_sessions()
    except IllegalStateChangeError:
        pass
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
    _database_url = None
    _engine_configured_manually = False


def ensure_settings_table() -> None:
    initialize_schema()


def check_database_connection() -> tuple[bool, str]:
    try:
        engine = get_engine()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True, "connected"
    except Exception as exc:
        return False, str(exc)


def initialize_schema() -> None:
    from runtime.db.models import Base
    from runtime.db.repos.settings_repo import SettingsRepository

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _sync_missing_columns(engine, Base)
    _ensure_runtime_state_profile_isolation(engine)
    _seed_runtime_profile_foundation(engine)
    with session_scope() as session:
        SettingsRepository().ensure_profile_defaults(session)


def _seed_runtime_profile_foundation(engine: Engine) -> None:
    from runtime.db.repos.settings_repo import DEFAULT_RUNTIME_SETTINGS, RUNTIME_DEFAULT_TEMPLATE_ID

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "runtime_profiles" not in table_names:
        return

    timestamp = datetime.now(timezone.utc).isoformat()
    scoped_tables = (
        "v4_runtime_state",
        "v4_scan_runs",
        "v4_signals",
        "v4_orders",
        "v4_fills",
        "v4_positions",
        "v4_portfolio_snapshots",
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
    hash_scoped_tables = (
        "v4_scan_runs",
        "v4_orders",
        "v4_trade_traces",
        "v4_engine_run_manifests",
    )

    seeded_profiles = (
        {
            "profile_id": "paper-main",
            "name": "Paper Main",
            "status": "ACTIVE",
            "runtime_mode": "PAPER",
            "execution_mode": "PAPER",
            "venue": "INTERNAL_PAPER",
            "product_type": "SIMULATED",
            "venue_environment": "INTERNAL",
            "api_base_url": None,
            "default_for_auto_trading": True,
            "manual_trading_enabled": True,
            "auto_trading_enabled": False,
            "read_only": False,
            "supports_account_reads": True,
            "supports_order_placement": True,
            "credential_ref": None,
            "connectivity_status": "READY",
            "last_connectivity_check_at_utc": timestamp,
            "last_connectivity_ok_at_utc": timestamp,
            "last_connectivity_error": None,
            "created_at_utc": timestamp,
            "updated_at_utc": timestamp,
        },
        {
            "profile_id": "binance-usdm-main",
            "name": "Binance USDM Main",
            "status": "READ_ONLY",
            "runtime_mode": "LIVE",
            "execution_mode": "LIVE",
            "venue": "BINANCE_USDM",
            "product_type": "USDM_FUTURES",
            "venue_environment": "MAINNET",
            "api_base_url": None,
            "default_for_auto_trading": False,
            "manual_trading_enabled": False,
            "auto_trading_enabled": False,
            "read_only": True,
            "supports_account_reads": True,
            "supports_order_placement": False,
            "credential_ref": "binance-usdm-main",
            "connectivity_status": "UNKNOWN",
            "last_connectivity_check_at_utc": None,
            "last_connectivity_ok_at_utc": None,
            "last_connectivity_error": None,
            "created_at_utc": timestamp,
            "updated_at_utc": timestamp,
        },
    )

    with engine.begin() as connection:
        for profile in seeded_profiles:
            exists = connection.execute(
                text("SELECT 1 FROM runtime_profiles WHERE profile_id = :profile_id LIMIT 1"),
                {"profile_id": profile["profile_id"]},
            ).scalar()
            if exists:
                continue
            connection.execute(
                text(
                    """
                    INSERT INTO runtime_profiles (
                        profile_id,
                        name,
                        status,
                        runtime_mode,
                        execution_mode,
                        venue,
                        product_type,
                        venue_environment,
                        api_base_url,
                        default_for_auto_trading,
                        manual_trading_enabled,
                        auto_trading_enabled,
                        read_only,
                        supports_account_reads,
                        supports_order_placement,
                        credential_ref,
                        connectivity_status,
                        last_connectivity_check_at_utc,
                        last_connectivity_ok_at_utc,
                        last_connectivity_error,
                        created_at_utc,
                        updated_at_utc
                    ) VALUES (
                        :profile_id,
                        :name,
                        :status,
                        :runtime_mode,
                        :execution_mode,
                        :venue,
                        :product_type,
                        :venue_environment,
                        :api_base_url,
                        :default_for_auto_trading,
                        :manual_trading_enabled,
                        :auto_trading_enabled,
                        :read_only,
                        :supports_account_reads,
                        :supports_order_placement,
                        :credential_ref,
                        :connectivity_status,
                        :last_connectivity_check_at_utc,
                        :last_connectivity_ok_at_utc,
                        :last_connectivity_error,
                        :created_at_utc,
                        :updated_at_utc
                    )
                    """
                ),
                profile,
            )
        for table_name in scoped_tables:
            if table_name not in table_names:
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            if "profile_id" in columns:
                connection.execute(text(f"UPDATE {table_name} SET profile_id = 'paper-main' WHERE profile_id IS NULL OR profile_id = ''"))
            if table_name in hash_scoped_tables and "resolved_config_hash" in columns:
                connection.execute(text(f"UPDATE {table_name} SET resolved_config_hash = '' WHERE resolved_config_hash IS NULL"))

        if "config_templates" in table_names:
            exists = connection.execute(
                text("SELECT 1 FROM config_templates WHERE template_id = :template_id LIMIT 1"),
                {"template_id": RUNTIME_DEFAULT_TEMPLATE_ID},
            ).scalar()
            if not exists:
                connection.execute(
                    text(
                        """
                        INSERT INTO config_templates (
                            template_id, name, base_template_id, scope, status, settings_json, created_at_utc, updated_at_utc
                        ) VALUES (
                            :template_id, :name, :base_template_id, :scope, :status, :settings_json, :created_at_utc, :updated_at_utc
                        )
                        """
                    ),
                    {
                        "template_id": RUNTIME_DEFAULT_TEMPLATE_ID,
                        "name": "Runtime Defaults",
                        "base_template_id": None,
                        "scope": "RUNTIME",
                        "status": "ACTIVE",
                        "settings_json": json.dumps(DEFAULT_RUNTIME_SETTINGS, sort_keys=True),
                        "created_at_utc": timestamp,
                        "updated_at_utc": timestamp,
                    },
                )

        if "profile_config_imports" in table_names:
            exists = connection.execute(
                text("SELECT 1 FROM profile_config_imports WHERE profile_id = :profile_id LIMIT 1"),
                {"profile_id": "paper-main"},
            ).scalar()
            if not exists:
                connection.execute(
                    text(
                        """
                        INSERT INTO profile_config_imports (
                            profile_id, template_id, import_order, created_at_utc, updated_at_utc
                        ) VALUES (
                            :profile_id, :template_id, :import_order, :created_at_utc, :updated_at_utc
                        )
                        """
                    ),
                    {
                        "profile_id": "paper-main",
                        "template_id": RUNTIME_DEFAULT_TEMPLATE_ID,
                        "import_order": 0,
                        "created_at_utc": timestamp,
                        "updated_at_utc": timestamp,
                    },
                )

        if "profile_accounts" in table_names:
            exists = connection.execute(
                text("SELECT 1 FROM profile_accounts WHERE profile_id = :profile_id AND account_key = :account_key LIMIT 1"),
                {"profile_id": "paper-main", "account_key": "default"},
            ).scalar()
            if not exists:
                legacy_balance = connection.execute(
                    text("SELECT balance FROM v4_paper_accounts WHERE account_key = 'default' LIMIT 1")
                ).scalar() if "v4_paper_accounts" in table_names else None
                default_balance = connection.execute(
                    text("SELECT value FROM v4_runtime_settings WHERE key = 'PAPER_DEFAULT_BALANCE' LIMIT 1")
                ).scalar() if "v4_runtime_settings" in table_names else None
                try:
                    seeded_balance = float(legacy_balance if legacy_balance is not None else default_balance if default_balance is not None else 100.0)
                except (TypeError, ValueError):
                    seeded_balance = 100.0
                connection.execute(
                    text(
                        """
                        INSERT INTO profile_accounts (
                            account_id, profile_id, account_key, account_type, venue_account_key, balance_ccy,
                            balance, available_balance, equity, margin_used, payload_json, as_of_utc, created_at_utc, updated_at_utc
                        ) VALUES (
                            :account_id, :profile_id, :account_key, :account_type, :venue_account_key, :balance_ccy,
                            :balance, :available_balance, :equity, :margin_used, :payload_json, :as_of_utc, :created_at_utc, :updated_at_utc
                        )
                        """
                    ),
                    {
                        "account_id": "paper-main:default",
                        "profile_id": "paper-main",
                        "account_key": "default",
                        "account_type": "PAPER_CASH",
                        "venue_account_key": None,
                        "balance_ccy": "USD",
                        "balance": seeded_balance,
                        "available_balance": seeded_balance,
                        "equity": seeded_balance,
                        "margin_used": 0.0,
                        "payload_json": "{}",
                        "as_of_utc": timestamp,
                        "created_at_utc": timestamp,
                        "updated_at_utc": timestamp,
                    },
                )



def _ensure_runtime_state_profile_isolation(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("v4_runtime_state"):
        return

    state_columns = list(inspector.get_columns("v4_runtime_state"))
    columns = {column["name"] for column in state_columns}
    pk_columns = list((inspector.get_pk_constraint("v4_runtime_state") or {}).get("constrained_columns") or [])

    with engine.begin() as connection:
        if "profile_id" in columns:
            connection.execute(text("UPDATE v4_runtime_state SET profile_id = 'paper-main' WHERE profile_id IS NULL OR profile_id = ''"))
        if pk_columns == ["profile_id", "key"]:
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_v4_runtime_state_profile_id ON v4_runtime_state (profile_id)"))
            return

        connection.execute(text("ALTER TABLE v4_runtime_state RENAME TO v4_runtime_state_legacy"))
        connection.execute(
            text(
                """
                CREATE TABLE v4_runtime_state (
                    profile_id VARCHAR(64) NOT NULL,
                    key VARCHAR(255) NOT NULL,
                    value_json TEXT NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (profile_id, key)
                )
                """
            )
        )
        legacy_columns = {column["name"] for column in state_columns}
        if "profile_id" in legacy_columns:
            connection.execute(
                text(
                    """
                    INSERT INTO v4_runtime_state (profile_id, key, value_json, updated_at)
                    SELECT COALESCE(NULLIF(profile_id, ''), 'paper-main'), key, value_json, updated_at
                    FROM v4_runtime_state_legacy
                    """
                )
            )
        else:
            connection.execute(
                text(
                    """
                    INSERT INTO v4_runtime_state (profile_id, key, value_json, updated_at)
                    SELECT 'paper-main', key, value_json, updated_at
                    FROM v4_runtime_state_legacy
                    """
                )
            )
        connection.execute(text("DROP TABLE v4_runtime_state_legacy"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_v4_runtime_state_profile_id ON v4_runtime_state (profile_id)"))



def _sync_missing_columns(engine: Engine, base) -> None:
    """Add columns introduced after initial table creation.

    The v4 runtime still relies on lightweight startup bootstrap in local/dev
    environments, so additive schema changes need to be applied even when the
    database was created before a migration file existed.
    """

    inspector = inspect(engine)
    dialect = engine.dialect

    with engine.begin() as connection:
        for table_name, table in base.metadata.tables.items():
            if not inspector.has_table(table_name):
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                if column.primary_key:
                    continue
                column_type = column.type.compile(dialect=dialect)
                default_value = None
                if column.server_default is not None and getattr(column.server_default, "arg", None) is not None:
                    default_value = str(column.server_default.arg)
                elif column.default is not None and getattr(column.default, "is_scalar", False):
                    default_value = column.default.arg

                default_sql = ""
                if default_value is not None:
                    rendered_default = str(default_value).replace("'", "''")
                    default_sql = f" DEFAULT '{rendered_default}'"

                nullable_sql = "" if column.nullable or default_value is None else " NOT NULL"
                connection.execute(
                    text(
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN {column.name} {column_type}{default_sql}{nullable_sql}"
                    )
                )
                if not column.nullable and default_value is None:
                    connection.execute(
                        text(
                            f"UPDATE {table_name} SET {column.name} = '' "
                            f"WHERE {column.name} IS NULL"
                        )
                    )
                    connection.execute(
                        text(
                            f"ALTER TABLE {table_name} "
                            f"ALTER COLUMN {column.name} SET NOT NULL"
                        )
                    )


@contextmanager
def session_scope() -> Iterator[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        configure_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()
