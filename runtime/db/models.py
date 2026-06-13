"""SQLAlchemy models for v4 operational state."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RuntimeSetting(Base):
    __tablename__ = "v4_runtime_settings"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class RuntimeState(Base):
    __tablename__ = "v4_runtime_state"

    profile_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True, nullable=False, default="paper-main")
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class RuntimeProfile(Base):
    __tablename__ = "runtime_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="ACTIVE")
    runtime_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="PAPER")
    execution_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="PAPER")
    venue: Mapped[str] = mapped_column(String(64), nullable=False, default="INTERNAL_PAPER")
    product_type: Mapped[str] = mapped_column(String(64), nullable=False, default="SIMULATED")
    venue_environment: Mapped[str] = mapped_column(String(32), nullable=False, default="INTERNAL")
    api_base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_for_auto_trading: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manual_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_account_reads: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_order_placement: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    credential_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    connectivity_status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    last_connectivity_check_at_utc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_connectivity_ok_at_utc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_connectivity_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at_utc: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at_utc: Mapped[str] = mapped_column(String(64), nullable=False)


class PaperAccount(Base):
    __tablename__ = "v4_paper_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False, default="default")
    balance: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ProfileAccount(Base):
    __tablename__ = "profile_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    account_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="default")
    account_type: Mapped[str] = mapped_column(String(64), nullable=False, default="PAPER_CASH")
    venue_account_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    balance_ccy: Mapped[str] = mapped_column(String(16), nullable=False, default="USD")
    balance: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    available_balance: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    equity: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    margin_used: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    as_of_utc: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at_utc: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at_utc: Mapped[str] = mapped_column(String(64), nullable=False)


class VenueBalance(Base):
    __tablename__ = "profile_venue_balances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    balance_id: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    account_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    venue: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="BINANCE_USDM")
    asset: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    available_balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    margin_balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cross_wallet_balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cross_unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_withdraw_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    margin_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    update_time_utc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    synced_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class VenuePosition(Base):
    __tablename__ = "profile_venue_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    account_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    venue: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="BINANCE_USDM")
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    position_side: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="BOTH")
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="OPEN")
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    break_even_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mark_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    liquidation_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    leverage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    margin_type: Mapped[str] = mapped_column(String(32), nullable=False, default="cross")
    isolated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    isolated_margin: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    notional: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_notional_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    update_time_utc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    synced_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class VenueOrder(Base):
    __tablename__ = "profile_venue_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_key: Mapped[str] = mapped_column(String(192), unique=True, index=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    account_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    venue: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="BINANCE_USDM")
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    venue_order_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    client_order_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    side: Mapped[str] = mapped_column(String(16), nullable=False, default="BUY")
    position_side: Mapped[str] = mapped_column(String(16), nullable=False, default="BOTH")
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="NEW")
    order_type: Mapped[str] = mapped_column(String(64), nullable=False, default="LIMIT")
    orig_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    time_in_force: Mapped[str | None] = mapped_column(String(16), nullable=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    executed_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    activate_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    reduce_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    close_position: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    working_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    price_protect: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_protective: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    opened_at_utc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at_utc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    synced_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class ConfigTemplate(Base):
    __tablename__ = "config_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    base_template_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNTIME")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    settings_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at_utc: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at_utc: Mapped[str] = mapped_column(String(64), nullable=False)


class ProfileConfigImport(Base):
    __tablename__ = "profile_config_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    template_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    import_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at_utc: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at_utc: Mapped[str] = mapped_column(String(64), nullable=False)


class ProfileConfigOverride(Base):
    __tablename__ = "profile_config_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    key: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at_utc: Mapped[str] = mapped_column(String(64), nullable=False)


class ResolvedProfileConfig(Base):
    __tablename__ = "resolved_profile_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False, default="paper-main")
    resolved_config_hash: Mapped[str] = mapped_column(String(128), index=True, nullable=False, default="")
    settings_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at_utc: Mapped[str] = mapped_column(String(64), nullable=False)


class Candle(Base):
    __tablename__ = "v4_candles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    interval: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    open_time_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    close_time_utc: Mapped[str] = mapped_column(String(64), nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="binance")
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ScanRun(Base):
    __tablename__ = "v4_scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False, default="system")
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="COMPLETED")
    symbols_csv: Mapped[str] = mapped_column(Text, nullable=False, default="")
    intervals_csv: Mapped[str] = mapped_column(Text, nullable=False, default="")
    modes_csv: Mapped[str] = mapped_column(Text, nullable=False, default="")
    signal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at_utc: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at_utc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    finished_at_utc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    result_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    resolved_config_hash: Mapped[str] = mapped_column(String(128), index=True, nullable=False, default="")


class Signal(Base):
    __tablename__ = "v4_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    run_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    interval: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    regime: Mapped[str] = mapped_column(String(32), nullable=False, default="RANGING")
    trend: Mapped[str] = mapped_column(String(32), nullable=False, default="MIXED")
    trend_strength: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    no_trade_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    strategy_version: Mapped[str] = mapped_column(String(64), nullable=False, default="v3-enhanced-v1")
    engine_name: Mapped[str] = mapped_column(String(64), nullable=False, default="v4_default")
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False, default="v4-phase25")
    engine_schema_version: Mapped[str] = mapped_column(String(64), nullable=False, default="analysis_result.v1")
    engine_fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    features_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    factors_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    audit_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)


class Order(Base):
    __tablename__ = "v4_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    signal_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="PAPER")
    execution_mode: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="PAPER")
    venue: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="INTERNAL_PAPER")
    origin: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="AUTO")
    client_order_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    venue_order_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    submission_status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="NONE")
    submitted_at_utc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_venue_update_at_utc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    interval: Mapped[str] = mapped_column(String(16), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="OPEN")
    entry: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    close_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_reward: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    opened_at_utc: Mapped[str] = mapped_column(String(64), nullable=False)
    closed_at_utc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    resolved_config_hash: Mapped[str] = mapped_column(String(128), index=True, nullable=False, default="")


class Fill(Base):
    __tablename__ = "v4_fills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fill_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    order_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    fee: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    filled_at_utc: Mapped[str] = mapped_column(String(64), nullable=False)


class Position(Base):
    __tablename__ = "v4_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    interval: Mapped[str] = mapped_column(String(16), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    average_entry: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mark_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="OPEN")
    opened_at_utc: Mapped[str] = mapped_column(String(64), nullable=False)
    closed_at_utc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class PortfolioSnapshot(Base):
    __tablename__ = "v4_portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    total_equity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cash_balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    open_positions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    closed_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)


class Alert(Base):
    __tablename__ = "v4_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    severity: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    scope: Mapped[str] = mapped_column(String(128), nullable=False, default="system")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    detected_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)


class TradeTrace(Base):
    __tablename__ = "v4_trade_traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    timestamp_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    interval: Mapped[str | None] = mapped_column(String(16), nullable=True)
    mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    regime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    signal_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    resolved_config_hash: Mapped[str] = mapped_column(String(128), index=True, nullable=False, default="")


class V6ModelRegistryArtifact(Base):
    __tablename__ = "model_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_artifact_version: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    engine_name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="CANDIDATE")
    dataset_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    dataset_version: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    snapshot_builder_version: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    mlflow_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    training_timestamp_utc: Mapped[str] = mapped_column(String(64), nullable=False)
    promoted_at_utc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retired_at_utc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validation_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_report_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at_utc: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at_utc: Mapped[str] = mapped_column(String(64), nullable=False)


class V6ModelRegistryEvent(Base):
    __tablename__ = "model_registry_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    model_artifact_version: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    related_model_artifact_version: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)


class PerformanceSnapshot(Base):
    __tablename__ = "v4_performance_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    timestamp_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_event: Mapped[str] = mapped_column(String(64), nullable=False)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    win_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    profit_factor: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    net_r: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    open_orders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    closed_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    portfolio_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class TradeFailure(Base):
    __tablename__ = "v4_trade_failures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    signal_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    failure_source: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    blamed_component: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    severity_score: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    classification: Mapped[str] = mapped_column(String(128), nullable=False, default="UNCLASSIFIED")
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    improvement: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)


class CircuitBreakerEvent(Base):
    __tablename__ = "v4_circuit_breaker_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    failure_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    consecutive_losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    triggered_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    resolved_at_utc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    auto_resume_at_utc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active_rules_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    session_breakdown_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    time_of_day_breakdown_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)


class SimulationRun(Base):
    __tablename__ = "v4_simulation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    requested_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    parameters_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    started_at_utc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    finished_at_utc: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SimulationResult(Base):
    __tablename__ = "v4_simulation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    interval: Mapped[str] = mapped_column(String(16), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    realized_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at_utc: Mapped[str] = mapped_column(String(64), nullable=False)


class SimulationPreset(Base):
    __tablename__ = "v4_simulation_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    symbols_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    intervals_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    modes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    period_start: Mapped[str | None] = mapped_column(String(64), nullable=True)
    period_end: Mapped[str | None] = mapped_column(String(64), nullable=True)
    capital: Mapped[float | None] = mapped_column(Float, nullable=True)
    execution_settings_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class SimulationDecisionTrace(Base):
    __tablename__ = "v4_simulation_decision_traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_run_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    trace_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    interval: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    timestamp: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    direction: Mapped[str | None] = mapped_column(String(16), index=True, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, index=True, nullable=True)
    signal_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    selected_action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    selected_head: Mapped[str | None] = mapped_column(String(64), nullable=True)
    runtime_filter_reason: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    no_trade_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    skip_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fallback_used: Mapped[bool] = mapped_column(Boolean, index=True, nullable=False, default=False)
    fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    insufficient_history: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence_raw: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_final: Mapped[float | None] = mapped_column(Float, nullable=True)
    probability_long_raw: Mapped[float | None] = mapped_column(Float, nullable=True)
    probability_short_raw: Mapped[float | None] = mapped_column(Float, nullable=True)
    probability_no_trade_raw: Mapped[float | None] = mapped_column(Float, nullable=True)
    probability_long_final: Mapped[float | None] = mapped_column(Float, nullable=True)
    probability_short_final: Mapped[float | None] = mapped_column(Float, nullable=True)
    probability_no_trade_final: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    analyzer_metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    runtime_context_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    snapshot_metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)


class TradeMemory(Base):
    __tablename__ = "v4_trade_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    order_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    learning_regime: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    regime_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    regime_stability_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    regime_version: Mapped[str] = mapped_column(String(64), nullable=False, default="v1")
    context_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    outcome_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    summary_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_label: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="BREAKEVEN")
    realized_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    mae: Mapped[float | None] = mapped_column(Float, nullable=True)
    mfe: Mapped[float | None] = mapped_column(Float, nullable=True)
    hold_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    decay_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)


class SelfLearningRun(Base):
    __tablename__ = "v4_self_learning_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="PENDING")
    started_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    completed_at_utc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    samples_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class CounterfactualReplay(Base):
    __tablename__ = "v4_counterfactual_replays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    order_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    signal_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    action_label: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    is_actual_action: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    learning_regime: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    realized_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    mae: Mapped[float | None] = mapped_column(Float, nullable=True)
    mfe: Mapped[float | None] = mapped_column(Float, nullable=True)
    hold_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    outperformed_actual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delta_r_vs_actual: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)


class PolicyExample(Base):
    __tablename__ = "v4_policy_examples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    order_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    learning_regime: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    context_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    candidate_actions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    best_action_label: Mapped[str] = mapped_column(String(64), nullable=False, default="NO_TRADE")
    best_action_realized_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_action_label: Mapped[str] = mapped_column(String(64), nullable=False, default="ENTER_NOW")
    actual_action_realized_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    regret_vs_best: Mapped[float | None] = mapped_column(Float, nullable=True)
    provisional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)


class ExpectancyLabelProfile(Base):
    __tablename__ = "v4_expectancy_label_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    learning_regime: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    lookback_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expected_r: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stop_hit_probability: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    target_hit_probability: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_mae: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_mfe: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_hold_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)


class ShadowPolicyDecision(Base):
    __tablename__ = "v4_shadow_policy_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    generated_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    recommended_action: Mapped[str] = mapped_column(String(64), nullable=False, default="NO_RECOMMENDATION")
    support_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expected_reward: Mapped[float | None] = mapped_column(Float, nullable=True)
    uncertainty_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    learning_regime: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    similar_case_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class AnalyticsComponentRegistry(Base):
    __tablename__ = "v4_analytics_component_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    component_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    component_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    component_name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="ACTIVE")
    owner: Mapped[str] = mapped_column(String(128), nullable=False, default="engine")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    default_params_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    ui_label: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    module_path: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    object_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    implementation_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    introduced_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    deprecated_at_utc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    updated_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)


class EngineRunManifest(Base):
    __tablename__ = "v4_engine_run_manifests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False, default="v4")
    started_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    finished_at_utc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    component_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    enabled_component_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    disabled_component_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    param_hash: Mapped[str] = mapped_column(String(128), index=True, nullable=False, default="")
    param_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    feature_flags_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    runtime_mode: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="SCAN")
    symbol_scope_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    interval_scope_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    summary_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    resolved_config_hash: Mapped[str] = mapped_column(String(128), index=True, nullable=False, default="")


class ImprovementChangeEvent(Base):
    __tablename__ = "v4_improvement_change_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    change_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    change_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    component_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    old_value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective_from_run_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    effective_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    author: Mapped[str] = mapped_column(String(128), nullable=False, default="system")


class SignalComponentAttribution(Base):
    __tablename__ = "v4_signal_component_attributions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    order_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    component_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    attribution_level: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="PRESENCE")
    mode: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    interval: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    regime: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="UNKNOWN")
    contribution_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)


class TradeComponentOutcome(Base):
    __tablename__ = "v4_trade_component_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="paper-main")
    signal_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    component_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    interval: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    regime: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="UNKNOWN")
    realized_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_source: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    blamed_component: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at_utc: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
