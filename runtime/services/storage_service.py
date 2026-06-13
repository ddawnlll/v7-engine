"""Operational storage service for v4."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.inspection import inspect as sa_inspect

from runtime.db.models import (
    Alert,
    AnalyticsComponentRegistry,
    Candle,
    CircuitBreakerEvent,
    CounterfactualReplay,
    EngineRunManifest,
    ExpectancyLabelProfile,
    Fill,
    ImprovementChangeEvent,
    Order,
    PaperAccount,
    PerformanceSnapshot,
    PolicyExample,
    PortfolioSnapshot,
    Position,
    RuntimeSetting,
    RuntimeState,
    ScanRun,
    SelfLearningRun,
    ShadowPolicyDecision,
    Signal,
    SignalComponentAttribution,
    SimulationResult,
    SimulationRun,
    TradeComponentOutcome,
    TradeFailure,
    TradeMemory,
    TradeTrace,
)
from runtime.db.repos._helpers import dumps_json, dumps_list
from runtime.db.repos.alert_repo import AlertRepository
from runtime.db.repos.failure_repo import FailureRepository
from runtime.db.repos.order_repo import OrderRepository
from runtime.db.repos.portfolio_repo import PortfolioRepository
from runtime.db.repos.scan_repo import ScanRepository
from runtime.db.repos.settings_repo import SettingsRepository
from runtime.db.repos.signal_repo import SignalRepository
from runtime.db.session import check_database_connection, session_scope


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StorageService:
    TRASH_RETENTION_DAYS = 30
    PROTECTED_FAILURE_COMPONENTS = {"trade_failures", "alerts", "performance_snapshots", "circuit_breaker_events"}
    PROTECTED_LEARNING_COMPONENTS = {
        "trade_memories",
        "self_learning_runs",
        "counterfactual_replays",
        "policy_examples",
        "expectancy_label_profiles",
        "shadow_policy_decisions",
        "engine_run_manifests",
        "improvement_change_events",
        "signal_component_attributions",
        "trade_component_outcomes",
    }

    def __init__(self) -> None:
        self.settings_repo = SettingsRepository()
        self.scan_repo = ScanRepository()
        self.signal_repo = SignalRepository()
        self.order_repo = OrderRepository()
        self.portfolio_repo = PortfolioRepository()
        self.alert_repo = AlertRepository()
        self.failure_repo = FailureRepository()
        self._table_models = {
            "runtime_settings": RuntimeSetting,
            "runtime_state": RuntimeState,
            "paper_accounts": PaperAccount,
            "candles": Candle,
            "scan_runs": ScanRun,
            "signals": Signal,
            "orders": Order,
            "fills": Fill,
            "positions": Position,
            "portfolio_snapshots": PortfolioSnapshot,
            "alerts": Alert,
            "trade_failures": TradeFailure,
            "trade_traces": TradeTrace,
            "performance_snapshots": PerformanceSnapshot,
            "circuit_breaker_events": CircuitBreakerEvent,
            "simulation_runs": SimulationRun,
            "simulation_results": SimulationResult,
            "trade_memories": TradeMemory,
            "self_learning_runs": SelfLearningRun,
            "counterfactual_replays": CounterfactualReplay,
            "policy_examples": PolicyExample,
            "expectancy_label_profiles": ExpectancyLabelProfile,
            "shadow_policy_decisions": ShadowPolicyDecision,
            "analytics_component_registry": AnalyticsComponentRegistry,
            "engine_run_manifests": EngineRunManifest,
            "improvement_change_events": ImprovementChangeEvent,
            "signal_component_attributions": SignalComponentAttribution,
            "trade_component_outcomes": TradeComponentOutcome,
        }
        self._trash_dir = Path(".storage-trash")
        self._clear_groups = {
            "scans": {
                "label": "Scan Data",
                "description": "Scan runs and persisted analyzer signals.",
                "components": ["scan_runs", "signals"],
            },
            "trading": {
                "label": "Trading Data",
                "description": "Orders, fills, positions, portfolio snapshots, traces, and performance snapshots.",
                "components": ["orders", "fills", "positions", "portfolio_snapshots", "trade_traces", "performance_snapshots"],
            },
            "failures_alerts": {
                "label": "Failures & Alerts",
                "description": "Trade failures and operator alerts.",
                "components": ["trade_failures", "alerts"],
            },
            "circuit_breaker": {
                "label": "Circuit Breaker History",
                "description": "Persisted circuit breaker events and cooldown history.",
                "components": ["circuit_breaker_events"],
            },
            "self_learning": {
                "label": "Self-Learning Data",
                "description": "Trade memories, replay rows, policy examples, expectancy labels, and shadow policy decisions.",
                "components": ["trade_memories", "self_learning_runs", "counterfactual_replays", "policy_examples", "expectancy_label_profiles", "shadow_policy_decisions"],
            },
            "improvement_analytics": {
                "label": "Improvement Analytics",
                "description": "Engine manifests, change events, signal attribution, and trade outcome attribution.",
                "components": ["engine_run_manifests", "improvement_change_events", "signal_component_attributions", "trade_component_outcomes"],
            },
            "simulations": {
                "label": "Simulation Data",
                "description": "Simulation runs and simulation results.",
                "components": ["simulation_runs", "simulation_results"],
            },
            "market_data": {
                "label": "Market Data",
                "description": "Persisted candle history.",
                "components": ["candles"],
            },
            "settings_state": {
                "label": "Settings & Runtime State",
                "description": "Runtime settings, runtime state, and paper account state.",
                "components": ["runtime_settings", "runtime_state", "paper_accounts"],
            },
            "recommended_engine_reset": {
                "label": "Recommended Engine Reset",
                "description": "Clears pre-change trading, scan, learning, and analytics data while preserving candles, settings, runtime state, paper account state, and component registry.",
                "components": [
                    "scan_runs",
                    "signals",
                    "orders",
                    "fills",
                    "positions",
                    "portfolio_snapshots",
                    "trade_traces",
                    "performance_snapshots",
                    "trade_failures",
                    "alerts",
                    "circuit_breaker_events",
                    "trade_memories",
                    "self_learning_runs",
                    "counterfactual_replays",
                    "policy_examples",
                    "expectancy_label_profiles",
                    "shadow_policy_decisions",
                    "engine_run_manifests",
                    "improvement_change_events",
                    "signal_component_attributions",
                    "trade_component_outcomes",
                ],
            },
        }

    @staticmethod
    def _supports_profile_scope(model) -> bool:
        return hasattr(model, "profile_id")

    def get_status(self, *, profile_id: str | None = None) -> dict:
        db_connected, db_detail = check_database_connection()
        if not db_connected:
            return {
                "generated_at": utc_now_iso(),
                "postgres": {
                    "backend": "postgresql-primary",
                    "healthy": False,
                    "detail": db_detail,
                    "counts": self._empty_counts(),
                    "total_size_bytes": None,
                },
                "state": {
                    "mode": "degraded",
                    "label": "Database unavailable",
                    "note": db_detail,
                },
                "clear_groups": self.get_clear_groups(profile_id=profile_id),
            }

        with session_scope() as session:
            counts = self._counts(session, profile_id=profile_id)
            state = self._infer_state(session, counts, profile_id=profile_id)
        return {
            "generated_at": utc_now_iso(),
            "postgres": {
                "backend": "postgresql-primary",
                "healthy": True,
                "detail": "connected",
                "counts": counts,
                "total_size_bytes": None,
            },
            "state": state,
            "clear_groups": self.get_clear_groups(profile_id=profile_id),
        }

    def get_clear_groups(self, *, profile_id: str | None = None) -> list[dict]:
        return [
            {
                "group_id": group_id,
                "label": meta["label"],
                "description": meta["description"],
                "components": [
                    component for component in meta["components"]
                    if profile_id is None or self._supports_profile_scope(self._table_models[component])
                ],
            }
            for group_id, meta in self._clear_groups.items()
            if profile_id is None or any(self._supports_profile_scope(self._table_models[component]) for component in meta["components"])
        ]

    def export_operational_state(self, store: str = "postgres", *, profile_id: str | None = None) -> dict:
        self._assert_store(store)
        with session_scope() as session:
            settings = self.settings_repo.get_all(session, profile_id=profile_id or "paper-main") if profile_id else self.settings_repo.get_all(session)
            candles = [] if profile_id else [self._candle_to_dict(row) for row in session.query(Candle).order_by(Candle.id.asc()).all()]
            scan_runs = self.scan_repo.list_runs(session, limit=10_000, profile_id=profile_id)
            signal_columns = self.signal_repo._available_columns(session)
            signal_query = self.signal_repo._base_query(session, signal_columns)
            if profile_id:
                signal_query = signal_query.filter(Signal.profile_id == profile_id)
            signals = [self.signal_repo._to_dict(row, signal_columns) for row in signal_query.order_by(Signal.created_at_utc.desc()).limit(10_000).all()]
            orders = self.order_repo.list_orders(session, limit=10_000, profile_id=profile_id)
            fills_query = session.query(Fill)
            if profile_id:
                fills_query = fills_query.filter(Fill.profile_id == profile_id)
            fills = [self.order_repo._fill_to_dict(row) for row in fills_query.order_by(Fill.id.asc()).limit(10_000).all()]
            positions = self.order_repo.list_positions(session, limit=10_000, profile_id=profile_id)
            portfolio_snapshots = self.portfolio_repo.list_snapshots(session, limit=10_000, profile_id=profile_id)
            alerts = self.alert_repo.list_alerts(session, active_only=False, limit=10_000, profile_id=profile_id or "paper-main") if profile_id else self.alert_repo.list_alerts(session, active_only=False, limit=10_000)
            failures = self.failure_repo.list_recent_failures(session, limit=10_000, profile_id=profile_id or "paper-main") if profile_id else self.failure_repo.list_recent_failures(session, limit=10_000)
            counts = self._counts(session, profile_id=profile_id)
            state = self._infer_state(session, counts, profile_id=profile_id)

        return {
            "exported_at": utc_now_iso(),
            "store": store,
            "kind": "operational_export",
            "counts": counts,
            "state": state,
            "runtime_settings": settings,
            "candles": candles,
            "scan_runs": scan_runs,
            "signals": signals,
            "orders": orders,
            "fills": fills,
            "positions": positions,
            "portfolio_snapshots": portfolio_snapshots,
            "alerts": alerts,
            "failures": failures,
        }

    def import_operational_state(self, payload: dict, *, store: str = "postgres", dry_run: bool = False, confirm_phrase: str | None = None) -> dict:
        self._assert_store(store)
        counts = self._payload_counts(payload)
        if dry_run:
            return {
                "store": store,
                "mode": "import-preview",
                "counts": counts,
                "current_counts": self.get_status()["postgres"]["counts"],
                "dry_run": True,
            }

        with session_scope() as session:
            self._clear_operational_rows(session, keep_settings=False, confirm_phrase=confirm_phrase, operation_label="import")
            self.settings_repo.save_many(session, dict(payload.get("runtime_settings") or {}))
            self._import_candles(session, payload.get("candles") or [])
            self._import_scan_runs(session, payload.get("scan_runs") or [])
            self._import_signals(session, payload.get("signals") or [])
            self._import_orders(session, payload.get("orders") or [])
            self._import_fills(session, payload.get("fills") or [])
            self._import_positions(session, payload.get("positions") or [])
            self._import_portfolio_snapshots(session, payload.get("portfolio_snapshots") or [])
            self._import_alerts(session, payload.get("alerts") or [])
            self._import_failures(session, payload.get("failures") or [])
            current_counts = self._counts(session)

        return {
            "store": store,
            "mode": "import",
            "counts": counts,
            "current_counts": current_counts,
            "dry_run": False,
        }

    def seed_operational_state(self, *, store: str = "postgres", mode: str = "seed", confirm_phrase: str | None = None) -> dict:
        self._assert_store(store)
        if mode not in {"seed", "all", "real"}:
            raise ValueError(f"Unsupported seed mode: {mode}")

        with session_scope() as session:
            if mode == "real":
                self._clear_operational_rows(session, keep_settings=True, confirm_phrase=confirm_phrase, operation_label=f"seed:{mode}")
                current_counts = self._counts(session)
                return {
                    "store": store,
                    "mode": mode,
                    "counts": current_counts,
                    "current_counts": current_counts,
                    "dry_run": False,
                }

            self._clear_operational_rows(session, keep_settings=False, confirm_phrase=confirm_phrase, operation_label=f"seed:{mode}")
            self.settings_repo.save_many(
                session,
                {
                    "AUTONOMOUS_ENABLED": "1",
                    "AUTONOMOUS_SCAN_INTERVAL_SECONDS": "60",
                    "AUTONOMOUS_SCAN_WORKERS": "4",
                    "AUTONOMOUS_SYMBOLS": "BTCUSDT,ETHUSDT,SOLUSDT",
                    "AUTONOMOUS_INTERVALS": "15m,1h",
                    "AUTONOMOUS_MODES": "SCALP,SWING",
                    "MAX_TRADES_PER_DAY": "5",
                },
            )
            self._seed_minimal(session)
            if mode == "all":
                self._seed_full(session)
            current_counts = self._counts(session)

        return {
            "store": store,
            "mode": mode,
            "counts": current_counts,
            "current_counts": current_counts,
            "dry_run": False,
        }

    def clear_operational_state(self, *, store: str = "postgres", keep_settings: bool = False, profile_id: str | None = None, confirm_phrase: str | None = None) -> dict:
        self._assert_store(store)
        with session_scope() as session:
            counts = self._counts(session, profile_id=profile_id)
            self._clear_operational_rows(session, keep_settings=keep_settings, profile_id=profile_id, confirm_phrase=confirm_phrase, operation_label="clear-operational-state")
            current_counts = self._counts(session, profile_id=profile_id)
        return {
            "store": store,
            "mode": "clear-keep-settings" if keep_settings else "clear",
            "counts": counts,
            "current_counts": current_counts,
            "dry_run": False,
        }

    def clear_components(self, *, components: list[str], store: str = "postgres", profile_id: str | None = None, confirm_phrase: str | None = None) -> dict:
        self._assert_store(store)
        normalized = self._normalize_components(components)
        if profile_id:
            normalized = [name for name in normalized if self._supports_profile_scope(self._table_models[name])]
            if not normalized:
                raise ValueError("Selected components are not profile-scoped and cannot be cleared safely for a single profile.")
        with session_scope() as session:
            counts_before = self._counts(session, profile_id=profile_id)
            cleared_counts = {name: counts_before.get(name, 0) for name in normalized}
            self._clear_selected_rows(session, normalized, profile_id=profile_id, confirm_phrase=confirm_phrase, operation_label="clear-components")
            session.commit()
            current_counts = self._counts(session, profile_id=profile_id)
        return {
            "store": store,
            "mode": "clear-components",
            "counts": cleared_counts,
            "current_counts": current_counts,
            "dry_run": False,
            "cleared_components": normalized,
        }

    def clear_group(self, *, group_id: str, store: str = "postgres", profile_id: str | None = None, confirm_phrase: str | None = None) -> dict:
        self._assert_store(store)
        meta = self._clear_groups.get(group_id)
        if meta is None:
            raise ValueError(f"Unsupported clear group: {group_id}")
        result = self.clear_components(components=list(meta["components"]), store=store, profile_id=profile_id, confirm_phrase=confirm_phrase)
        result["mode"] = f"clear-group:{group_id}"
        result["cleared_group"] = group_id
        return result

    def _seed_minimal(self, session) -> None:
        created_at = "2026-03-31T09:00:00Z"
        finished_at = "2026-03-31T09:00:30Z"
        self.scan_repo.save_run(
            session,
            {
                "run_id": "seed-run-1",
                "requested_by": "storage_seed",
                "status": "COMPLETED",
                "symbols_csv": "BTCUSDT,ETHUSDT",
                "intervals_csv": "15m,1h",
                "modes_csv": "SCALP,SWING",
                "signal_count": 2,
                "summary": "Seeded scan run",
                "error_text": None,
                "created_at_utc": created_at,
                "started_at_utc": created_at,
                "finished_at_utc": finished_at,
                "payload_json": dumps_json({"seed": True}),
                "result_json": dumps_json({"signals": 2}),
            },
        )
        self.signal_repo.save_signal(
            session,
            {
                "signal_id": "seed-signal-1",
                "run_id": "seed-run-1",
                "symbol": "BTCUSDT",
                "interval": "15m",
                "mode": "SCALP",
                "direction": "BUY",
                "confidence": 72.0,
                "regime": "TRENDING",
                "trend": "BULLISH",
                "trend_strength": 0.84,
                "summary": "Seed long setup",
                "no_trade_reason": None,
                "strategy_version": "storage_seed",
                "snapshot_json": dumps_json({"seed": True}),
                "features_json": dumps_json({"seed": True}),
                "factors_json": dumps_list(["trend", "volume"]),
                "created_at_utc": created_at,
            },
        )
        self.order_repo.save_order(
            session,
            {
                "order_id": "seed-order-1",
                "signal_id": "seed-signal-1",
                "source": "PAPER",
                "symbol": "BTCUSDT",
                "interval": "15m",
                "mode": "SCALP",
                "direction": "BUY",
                "status": "OPEN",
                "entry": 50000.0,
                "stop_loss": 49500.0,
                "take_profit": 51000.0,
                "close_price": None,
                "risk_reward": 2.0,
                "confidence": 72.0,
                "opened_at_utc": created_at,
                "closed_at_utc": None,
                "payload_json": dumps_json({"quantity": 0.1, "seed": True}),
            },
        )
        self.order_repo.save_fill(
            session,
            {
                "fill_id": "seed-fill-1",
                "order_id": "seed-order-1",
                "symbol": "BTCUSDT",
                "direction": "BUY",
                "quantity": 0.1,
                "price": 50000.0,
                "fee": 1.0,
                "filled_at_utc": created_at,
            },
        )
        self.order_repo.save_position(
            session,
            {
                "position_id": "seed-position-1",
                "symbol": "BTCUSDT",
                "interval": "15m",
                "mode": "SCALP",
                "direction": "BUY",
                "quantity": 0.1,
                "average_entry": 50000.0,
                "mark_price": 50350.0,
                "unrealized_pnl": 35.0,
                "status": "OPEN",
                "opened_at_utc": created_at,
                "closed_at_utc": None,
                "payload_json": dumps_json({"seed": True}),
            },
        )
        self.portfolio_repo.save_snapshot(
            session,
            {
                "snapshot_id": "seed-portfolio-1",
                "total_equity": 10035.0,
                "cash_balance": 9500.0,
                "unrealized_pnl": 35.0,
                "realized_pnl": 0.0,
                "open_positions": 1,
                "closed_trades": 0,
                "snapshot_json": dumps_json({"seed": True}),
                "created_at_utc": finished_at,
            },
        )
        self.alert_repo.save_alert(
            session,
            {
                "alert_id": "seed-alert-1",
                "severity": "warning",
                "kind": "no_recent_scan",
                "scope": "scan",
                "message": "Seed alert for storage testing.",
                "active": True,
                "payload_json": dumps_json({"seed": True}),
                "detected_at_utc": finished_at,
            },
        )

    def _seed_full(self, session) -> None:
        self.signal_repo.save_signal(
            session,
            {
                "signal_id": "seed-signal-2",
                "run_id": "seed-run-1",
                "symbol": "ETHUSDT",
                "interval": "1h",
                "mode": "SWING",
                "direction": "SELL",
                "confidence": 64.0,
                "regime": "RANGING",
                "trend": "BEARISH",
                "trend_strength": 0.51,
                "summary": "Seed short setup",
                "no_trade_reason": None,
                "strategy_version": "storage_seed",
                "snapshot_json": dumps_json({"seed": True}),
                "features_json": dumps_json({"seed": True}),
                "factors_json": dumps_list(["resistance", "momentum"]),
                "created_at_utc": "2026-03-31T10:00:00Z",
            },
        )
        self.order_repo.save_order(
            session,
            {
                "order_id": "seed-order-2",
                "signal_id": "seed-signal-2",
                "source": "PAPER",
                "symbol": "ETHUSDT",
                "interval": "1h",
                "mode": "SWING",
                "direction": "SELL",
                "status": "CLOSED",
                "entry": 2500.0,
                "stop_loss": 2550.0,
                "take_profit": 2400.0,
                "close_price": 2420.0,
                "risk_reward": 1.6,
                "confidence": 64.0,
                "opened_at_utc": "2026-03-31T10:05:00Z",
                "closed_at_utc": "2026-03-31T11:30:00Z",
                "payload_json": dumps_json({"quantity": 1.0, "realized_pnl": 80.0, "realized_r": 1.6, "close_reason": "TP", "seed": True}),
            },
        )
        self.order_repo.save_fill(
            session,
            {
                "fill_id": "seed-fill-2",
                "order_id": "seed-order-2",
                "symbol": "ETHUSDT",
                "direction": "SELL",
                "quantity": 1.0,
                "price": 2500.0,
                "fee": 0.5,
                "filled_at_utc": "2026-03-31T10:05:00Z",
            },
        )
        self.portfolio_repo.save_snapshot(
            session,
            {
                "snapshot_id": "seed-portfolio-2",
                "total_equity": 10115.0,
                "cash_balance": 10115.0,
                "unrealized_pnl": 0.0,
                "realized_pnl": 115.0,
                "open_positions": 0,
                "closed_trades": 1,
                "snapshot_json": dumps_json({"seed": True}),
                "created_at_utc": "2026-03-31T11:30:00Z",
            },
        )
        self.alert_repo.save_alert(
            session,
            {
                "alert_id": "seed-alert-2",
                "severity": "critical",
                "kind": "exchange_failure",
                "scope": "exchange",
                "message": "Seed exchange connectivity issue.",
                "active": False,
                "payload_json": dumps_json({"seed": True}),
                "detected_at_utc": "2026-03-31T11:45:00Z",
            },
        )
        session.add(
            Candle(
                symbol="BTCUSDT",
                interval="15m",
                open_time_utc="2026-03-31T09:00:00Z",
                close_time_utc="2026-03-31T09:14:59Z",
                open=50000.0,
                high=50125.0,
                low=49950.0,
                close=50080.0,
                volume=1250.0,
                source="seed",
                stale=False,
            )
        )
        session.commit()

    def _counts(self, session, *, profile_id: str | None = None) -> dict[str, int]:
        counts: dict[str, int] = {}
        for name, model in self._table_models.items():
            query = session.query(func.count()).select_from(model)
            if profile_id:
                if not self._supports_profile_scope(model):
                    counts[name] = 0
                    continue
                query = query.filter(getattr(model, "profile_id") == profile_id)
            counts[name] = int(query.scalar() or 0)
        return counts

    def _infer_state(self, session, counts: dict[str, int], *, profile_id: str | None = None) -> dict:
        total_records = sum(counts.values())
        if total_records == 0:
            return {
                "mode": "empty",
                "label": "Empty operational state",
                "note": f"No operational rows are currently stored{' for this profile' if profile_id else ''}.",
            }
        scan_seed_query = session.query(func.count()).select_from(ScanRun).filter(ScanRun.requested_by == "storage_seed")
        signal_seed_query = session.query(func.count()).select_from(Signal).filter(Signal.strategy_version == "storage_seed")
        if profile_id:
            scan_seed_query = scan_seed_query.filter(ScanRun.profile_id == profile_id)
            signal_seed_query = signal_seed_query.filter(Signal.profile_id == profile_id)
        seed_records = int(scan_seed_query.scalar() or 0) + int(signal_seed_query.scalar() or 0)
        if seed_records > 0:
            return {
                "mode": "seed",
                "label": "Seeded operational state",
                "note": f"Storage currently contains seeded demo rows for testing{' in this profile' if profile_id else ''}.",
            }
        return {
            "mode": "live",
            "label": "Live operational state",
            "note": f"Storage currently reflects runtime-owned operational data{' for this profile' if profile_id else ''}.",
        }

    def _payload_counts(self, payload: dict) -> dict[str, int]:
        settings = payload.get("runtime_settings") or {}
        counts = self._empty_counts()
        counts.update({
            "runtime_settings": len(settings),
            "candles": len(payload.get("candles") or []),
            "scan_runs": len(payload.get("scan_runs") or []),
            "signals": len(payload.get("signals") or []),
            "orders": len(payload.get("orders") or []),
            "fills": len(payload.get("fills") or []),
            "positions": len(payload.get("positions") or []),
            "portfolio_snapshots": len(payload.get("portfolio_snapshots") or []),
            "alerts": len(payload.get("alerts") or []),
            "trade_failures": len(payload.get("failures") or []),
        })
        return counts

    def _clear_operational_rows(
        self,
        session,
        *,
        keep_settings: bool,
        profile_id: str | None = None,
        confirm_phrase: str | None = None,
        operation_label: str = "clear-operational-rows",
    ) -> None:
        components = list(self._table_models.keys())
        if keep_settings:
            components = [name for name in components if name != "runtime_settings"]
        if profile_id:
            components = [name for name in components if self._supports_profile_scope(self._table_models[name])]
        self._clear_selected_rows(session, components, profile_id=profile_id, confirm_phrase=confirm_phrase, operation_label=operation_label)
        session.commit()

    def _normalize_components(self, components: list[str]) -> list[str]:
        if not components:
            raise ValueError("At least one component is required.")
        normalized: list[str] = []
        for name in components:
            key = str(name or "").strip()
            if key not in self._table_models:
                raise ValueError(f"Unsupported storage component: {key}")
            if key not in normalized:
                normalized.append(key)
        return normalized

    def _clear_selected_rows(
        self,
        session,
        components: list[str],
        *,
        profile_id: str | None = None,
        confirm_phrase: str | None = None,
        operation_label: str = "clear-selected-rows",
    ) -> None:
        delete_order = [
            "fills",
            "positions",
            "orders",
            "signals",
            "scan_runs",
            "portfolio_snapshots",
            "trade_traces",
            "performance_snapshots",
            "trade_failures",
            "alerts",
            "circuit_breaker_events",
            "counterfactual_replays",
            "policy_examples",
            "expectancy_label_profiles",
            "shadow_policy_decisions",
            "trade_memories",
            "self_learning_runs",
            "simulation_results",
            "simulation_runs",
            "trade_component_outcomes",
            "signal_component_attributions",
            "improvement_change_events",
            "engine_run_manifests",
            "candles",
            "paper_accounts",
            "runtime_state",
            "runtime_settings",
            "analytics_component_registry",
        ]
        requested = set(components)
        protected_requirements = self._protected_delete_requirements(requested)
        self._validate_delete_confirmation(protected_requirements, confirm_phrase=confirm_phrase, operation_label=operation_label)
        if requested:
            self._archive_rows_to_trash(session, [name for name in delete_order if name in requested], profile_id=profile_id, operation_label=operation_label)
        for name in delete_order:
            if name not in requested:
                continue
            query = session.query(self._table_models[name])
            if profile_id:
                model = self._table_models[name]
                if not self._supports_profile_scope(model):
                    continue
                query = query.filter(getattr(model, "profile_id") == profile_id)
            query.delete()

    def _protected_delete_requirements(self, components: set[str]) -> list[str]:
        requirements: list[str] = []
        if components & self.PROTECTED_FAILURE_COMPONENTS:
            requirements.append("DELETE FAILURE DATA")
        if components & self.PROTECTED_LEARNING_COMPONENTS:
            requirements.append("DELETE LEARNING DATA")
        return requirements

    @staticmethod
    def _validate_delete_confirmation(requirements: list[str], *, confirm_phrase: str | None, operation_label: str) -> None:
        if not requirements:
            return
        provided = str(confirm_phrase or "").upper()
        missing = [phrase for phrase in requirements if phrase not in provided]
        if missing:
            raise ValueError(
                f"{operation_label} touches protected storage. Type {' and '.join(missing)} to archive to trash and continue."
            )

    def _archive_rows_to_trash(
        self,
        session,
        components: list[str],
        *,
        profile_id: str | None,
        operation_label: str,
    ) -> dict[str, int]:
        self._trash_dir.mkdir(parents=True, exist_ok=True)
        self._purge_expired_trash()
        archived_at = datetime.now(timezone.utc)
        payload: dict[str, object] = {
            "trash_id": f"trash-{archived_at.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}",
            "archived_at": archived_at.isoformat(),
            "expires_at": (archived_at + timedelta(days=self.TRASH_RETENTION_DAYS)).isoformat(),
            "operation": operation_label,
            "profile_id": profile_id,
            "components": components,
            "counts": {},
            "rows": {},
        }
        counts: dict[str, int] = {}
        for name in components:
            model = self._table_models[name]
            query = session.query(model)
            if profile_id:
                if not self._supports_profile_scope(model):
                    continue
                query = query.filter(getattr(model, "profile_id") == profile_id)
            rows = query.all()
            serialized = [self._serialize_model_row(row) for row in rows]
            payload["rows"][name] = serialized
            counts[name] = len(serialized)
        payload["counts"] = counts
        trash_path = self._trash_dir / f"{payload['trash_id']}.json"
        trash_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=self._json_default), encoding="utf-8")
        return counts

    def _purge_expired_trash(self) -> None:
        if not self._trash_dir.exists():
            return
        cutoff = datetime.now(timezone.utc)
        for path in self._trash_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                expires_at = datetime.fromisoformat(str(payload.get("expires_at") or "").replace("Z", "+00:00"))
            except Exception:
                continue
            if expires_at <= cutoff:
                path.unlink(missing_ok=True)

    def list_trash_entries(self) -> list[dict[str, object]]:
        self._trash_dir.mkdir(parents=True, exist_ok=True)
        self._purge_expired_trash()
        entries: list[dict[str, object]] = []
        for path in sorted(self._trash_dir.glob("*.json"), reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            entries.append({
                "trash_id": str(payload.get("trash_id") or path.stem),
                "archived_at": payload.get("archived_at"),
                "expires_at": payload.get("expires_at"),
                "operation": payload.get("operation"),
                "profile_id": payload.get("profile_id"),
                "components": list(payload.get("components") or []),
                "counts": dict(payload.get("counts") or {}),
                "path": str(path),
            })
        return entries

    def delete_trash_entry(self, trash_id: str, *, confirm_phrase: str | None = None) -> dict[str, object]:
        expected = "DELETE TRASH FOREVER"
        if str(confirm_phrase or "").strip().upper() != expected:
            raise ValueError(f"Permanent trash deletion requires typing {expected}.")
        path = self._trash_dir / f"{trash_id}.json"
        if not path.exists():
            raise ValueError(f"Trash entry not found: {trash_id}")
        path.unlink()
        return {"trash_id": trash_id, "deleted_forever": True}

    @staticmethod
    def _serialize_model_row(row) -> dict[str, object]:
        return {
            attr.key: StorageService._json_default(getattr(row, attr.key))
            for attr in sa_inspect(row).mapper.column_attrs
        }

    @staticmethod
    def _json_default(value):
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    def _import_candles(self, session, items: list[dict]) -> None:
        for item in items:
            session.add(
                Candle(
                    symbol=str(item["symbol"]),
                    interval=str(item["interval"]),
                    open_time_utc=str(item["open_time_utc"]),
                    close_time_utc=str(item["close_time_utc"]),
                    open=float(item["open"]),
                    high=float(item["high"]),
                    low=float(item["low"]),
                    close=float(item["close"]),
                    volume=float(item.get("volume") or 0.0),
                    source=str(item.get("source") or "import"),
                    stale=bool(item.get("stale", False)),
                )
            )
        session.commit()

    def _import_scan_runs(self, session, items: list[dict]) -> None:
        for item in items:
            self.scan_repo.save_run(
                session,
                {
                    "run_id": str(item["run_id"]),
                    "requested_by": str(item.get("requested_by") or "import"),
                    "status": str(item.get("status") or "COMPLETED"),
                    "symbols_csv": ",".join(item.get("symbols") or []),
                    "intervals_csv": ",".join(item.get("intervals") or []),
                    "modes_csv": ",".join(item.get("modes") or []),
                    "signal_count": int(item.get("signal_count") or 0),
                    "summary": str(item.get("summary") or ""),
                    "error_text": item.get("error_text"),
                    "created_at_utc": str(item.get("created_at_utc") or utc_now_iso()),
                    "started_at_utc": item.get("started_at_utc"),
                    "finished_at_utc": item.get("finished_at_utc"),
                    "payload_json": dumps_json(item.get("payload") or {}),
                    "result_json": dumps_json(item.get("result") or {}),
                },
            )

    def _import_signals(self, session, items: list[dict]) -> None:
        for item in items:
            self.signal_repo.save_signal(
                session,
                {
                    "signal_id": str(item["signal_id"]),
                    "run_id": str(item["run_id"]),
                    "symbol": str(item["symbol"]),
                    "interval": str(item["interval"]),
                    "mode": str(item["mode"]),
                    "direction": str(item.get("direction") or "NEUTRAL"),
                    "confidence": float(item.get("confidence") or 0.0),
                    "regime": str(item.get("regime") or "RANGING"),
                    "trend": str(item.get("trend") or "MIXED"),
                    "trend_strength": float(item.get("trend_strength") or 0.0),
                    "summary": str(item.get("summary") or ""),
                    "no_trade_reason": item.get("no_trade_reason"),
                    "strategy_version": str(item.get("strategy_version") or "import"),
                    "snapshot_json": dumps_json(item.get("snapshot") or {}),
                    "features_json": dumps_json(item.get("features") or {}),
                    "factors_json": dumps_list(item.get("factors") or []),
                    "created_at_utc": str(item.get("created_at_utc") or utc_now_iso()),
                },
            )

    def _import_orders(self, session, items: list[dict]) -> None:
        for item in items:
            payload = dict(item.get("payload") or {})
            if item.get("close_reason") and "close_reason" not in payload:
                payload["close_reason"] = item["close_reason"]
            if item.get("realized_pnl") is not None and "realized_pnl" not in payload:
                payload["realized_pnl"] = item["realized_pnl"]
            if item.get("realized_r") is not None and "realized_r" not in payload:
                payload["realized_r"] = item["realized_r"]
            self.order_repo.save_order(
                session,
                {
                    "order_id": str(item["order_id"]),
                    "signal_id": item.get("signal_id"),
                    "source": str(item.get("source") or "PAPER"),
                    "symbol": str(item["symbol"]),
                    "interval": str(item["interval"]),
                    "mode": str(item["mode"]),
                    "direction": str(item["direction"]),
                    "status": str(item.get("status") or item.get("state") or "OPEN"),
                    "entry": float(item["entry"]),
                    "stop_loss": item.get("stop_loss", item.get("sl")),
                    "take_profit": item.get("take_profit", item.get("tp")),
                    "close_price": item.get("close_price"),
                    "risk_reward": item.get("risk_reward"),
                    "confidence": float(item.get("confidence") or 0.0),
                    "opened_at_utc": str(item.get("opened_at_utc") or item.get("open_timestamp") or utc_now_iso()),
                    "closed_at_utc": item.get("closed_at_utc") or item.get("close_timestamp"),
                    "payload_json": dumps_json(payload),
                },
            )

    def _import_fills(self, session, items: list[dict]) -> None:
        for item in items:
            self.order_repo.save_fill(
                session,
                {
                    "fill_id": str(item["fill_id"]),
                    "order_id": str(item["order_id"]),
                    "symbol": str(item["symbol"]),
                    "direction": str(item["direction"]),
                    "quantity": float(item.get("quantity") or 0.0),
                    "price": float(item["price"]),
                    "fee": float(item.get("fee") or 0.0),
                    "filled_at_utc": str(item.get("filled_at_utc") or utc_now_iso()),
                },
            )

    def _import_positions(self, session, items: list[dict]) -> None:
        for item in items:
            self.order_repo.save_position(
                session,
                {
                    "position_id": str(item["position_id"]),
                    "symbol": str(item["symbol"]),
                    "interval": str(item["interval"]),
                    "mode": str(item["mode"]),
                    "direction": str(item["direction"]),
                    "quantity": float(item.get("quantity") or 0.0),
                    "average_entry": float(item.get("average_entry") or 0.0),
                    "mark_price": item.get("mark_price"),
                    "unrealized_pnl": float(item.get("unrealized_pnl") or 0.0),
                    "status": str(item.get("status") or "OPEN"),
                    "opened_at_utc": str(item.get("opened_at_utc") or item.get("open_timestamp") or utc_now_iso()),
                    "closed_at_utc": item.get("closed_at_utc") or item.get("close_timestamp"),
                    "payload_json": dumps_json(item.get("payload") or {}),
                },
            )

    def _import_portfolio_snapshots(self, session, items: list[dict]) -> None:
        for item in items:
            snapshot_payload = item.get("snapshot") or {}
            self.portfolio_repo.save_snapshot(
                session,
                {
                    "snapshot_id": str(item["snapshot_id"]),
                    "total_equity": float(item.get("total_equity") or 0.0),
                    "cash_balance": float(item.get("cash_balance") or 0.0),
                    "unrealized_pnl": float(item.get("unrealized_pnl") or 0.0),
                    "realized_pnl": float(item.get("realized_pnl") or 0.0),
                    "open_positions": int(item.get("open_positions") or 0),
                    "closed_trades": int(item.get("closed_trades") or 0),
                    "snapshot_json": dumps_json(snapshot_payload),
                    "created_at_utc": str(item.get("created_at_utc") or utc_now_iso()),
                },
            )

    def _import_alerts(self, session, items: list[dict]) -> None:
        for item in items:
            self.alert_repo.save_alert(
                session,
                {
                    "alert_id": str(item.get("alert_id") or item.get("kind") or f"import-{utc_now_iso()}"),
                    "severity": str(item.get("severity") or "info"),
                    "kind": str(item.get("kind") or "imported_alert"),
                    "scope": str(item.get("scope") or "storage"),
                    "message": str(item.get("message") or ""),
                    "active": bool(item.get("active", True)),
                    "payload_json": dumps_json(item.get("payload") or {}),
                    "detected_at_utc": str(item.get("detected_at_utc") or utc_now_iso()),
                },
            )

    def _import_failures(self, session, items: list[dict]) -> None:
        for item in items:
            self.failure_repo.save_failure(
                session,
                {
                    "order_id": str(item["order_id"]),
                    "signal_id": item.get("signal_id"),
                    "failure_source": str(item.get("failure_source") or "SIGNAL_QUALITY"),
                    "blamed_component": str(item.get("blamed_component") or "Entry Logic"),
                    "severity_score": int(item.get("severity_score") or 1),
                    "confidence": float(item.get("confidence") or 0.0),
                    "classification": str(item.get("classification") or "UNCLASSIFIED"),
                    "explanation": str(item.get("explanation") or ""),
                    "improvement": str(item.get("improvement") or ""),
                    "created_at_utc": str(item.get("created_at_utc") or utc_now_iso()),
                },
            )

    def _assert_store(self, store: str) -> None:
        if store != "postgres":
            raise ValueError(f"Unsupported store for v4: {store}")

    def _empty_counts(self) -> dict[str, int]:
        return {name: 0 for name in self._table_models}

    @staticmethod
    def _candle_to_dict(row: Candle) -> dict:
        return {
            "id": row.id,
            "symbol": row.symbol,
            "interval": row.interval,
            "open_time_utc": row.open_time_utc,
            "close_time_utc": row.close_time_utc,
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.close,
            "volume": row.volume,
            "source": row.source,
            "stale": row.stale,
        }
