"""Dashboard and market query aggregation service for v4."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from runtime.db.models import Candle
from runtime.db.repos.alert_repo import AlertRepository
from runtime.db.repos.order_repo import OrderRepository
from runtime.db.repos.performance_repo import PerformanceRepository
from runtime.db.repos.portfolio_repo import PortfolioRepository
from runtime.db.repos.scan_repo import ScanRepository
from runtime.db.repos.settings_repo import SettingsRepository
from runtime.db.repos.signal_repo import SignalRepository
from runtime.db.repos.simulation_repo import SimulationRepository
from runtime.db.repos.trace_repo import TraceRepository
from runtime.db.session import check_database_connection, session_scope
from runtime.services.binance_client import INTERVALS, POPULAR_PAIRS, DEFAULT_SCAN_SYMBOLS, fetch_all_tickers, fetch_top_usdt_pairs

DEFAULT_MARKET_SYMBOL_LIMIT = 143


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _split_csv(value: str | None, fallback: list[str]) -> list[str]:
    if not value:
        return list(fallback)
    return [item.strip() for item in value.split(",") if item.strip()] or list(fallback)


def _resolve_symbols(settings: dict[str, str]) -> list[str]:
    raw = settings.get("AUTONOMOUS_SYMBOLS")
    symbols = _split_csv(raw, list(DEFAULT_SCAN_SYMBOLS))
    if raw and symbols:
        return symbols
    live_symbols = fetch_top_usdt_pairs(limit=DEFAULT_MARKET_SYMBOL_LIMIT)
    return live_symbols or list(DEFAULT_SCAN_SYMBOLS)


class DashboardService:
    def __init__(
        self,
        settings_repo: SettingsRepository | None = None,
        scan_repo: ScanRepository | None = None,
        signal_repo: SignalRepository | None = None,
        order_repo: OrderRepository | None = None,
        portfolio_repo: PortfolioRepository | None = None,
        performance_repo: PerformanceRepository | None = None,
        alert_repo: AlertRepository | None = None,
        trace_repo: TraceRepository | None = None,
        simulation_repo: SimulationRepository | None = None,
        market_overview_fetcher: Callable[[list[str] | None], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.settings_repo = settings_repo or SettingsRepository()
        self.scan_repo = scan_repo or ScanRepository()
        self.signal_repo = signal_repo or SignalRepository()
        self.order_repo = order_repo or OrderRepository()
        self.portfolio_repo = portfolio_repo or PortfolioRepository()
        self.performance_repo = performance_repo or PerformanceRepository()
        self.alert_repo = alert_repo or AlertRepository()
        self.trace_repo = trace_repo or TraceRepository()
        self.simulation_repo = simulation_repo or SimulationRepository()
        self.market_overview_fetcher = market_overview_fetcher or fetch_all_tickers

    def get_dashboard(self) -> dict[str, Any]:
        with session_scope() as session:
            settings = self.settings_repo.get_all(session)
            symbols = _resolve_symbols(settings)
            intervals = _split_csv(settings.get("AUTONOMOUS_INTERVALS"), ["15m", "30m", "1h", "4h", "1d", "3d", "7d", "14d", "1M"])
            runs = self.scan_repo.list_runs(session, limit=50)
            signals = self.signal_repo.list_signals(session, limit=100)
            orders = self.order_repo.list_orders(session, limit=200)
            positions = self.order_repo.list_positions(session, status="OPEN", limit=100)
            portfolio = self.portfolio_repo.get_latest_snapshot(session)
            portfolio_history = self.portfolio_repo.list_snapshots(session, limit=30)
            performance = self.performance_repo.get_latest_snapshot(session)
            trace_logs = self.trace_repo.list_traces(session, limit=80)
            simulations = self.simulation_repo.list_runs(session, limit=20)
            simulation_summary = self.simulation_repo.summary(session)
            alerts = self.alert_repo.list_alerts(session, active_only=True, limit=20)
            market = self._build_market_overview(session, symbols, intervals, signals)

        db_connected, db_status = check_database_connection()
        latest_run = runs[0] if runs else None
        running = sum(1 for row in runs if row["status"] == "RUNNING")
        completed = sum(1 for row in runs if row["status"] == "COMPLETED")
        failed = sum(1 for row in runs if row["status"] not in {"RUNNING", "COMPLETED"})
        engine_status = "healthy" if db_connected and failed == 0 else "degraded" if db_connected else "down"

        open_orders = [order for order in orders if str(order.get("status", "")).upper() == "OPEN"]
        closed_orders = [order for order in orders if str(order.get("status", "")).upper() != "OPEN"]
        recent_events = self._build_recent_events(signals, runs)
        equity_curve = self._build_equity_curve(portfolio_history)

        return {
            "generated_at": utc_now_iso(),
            "engine": {
                "status": engine_status,
                "last_scan": {
                    "timestamp": latest_run.get("finished_at_utc") if latest_run else None,
                    "status": latest_run.get("status") if latest_run else "IDLE",
                    "summary": latest_run.get("summary") if latest_run else "No scans yet.",
                },
            },
            "engine_health": {
                "status": engine_status,
                "db_status": db_status,
                "db_connected": db_connected,
                "runtime_status": "running" if db_connected else "degraded",
                "exchange_status": "unknown",
                "last_scan_completed_at_utc": latest_run.get("finished_at_utc") if latest_run else None,
                "queue_depth": running,
                "active_workers": 1 if running else 0,
                "worker_capacity": 1,
                "open_orders": len(open_orders),
            },
            "job_queue": {
                "pending": 0,
                "running": running,
                "completed": completed,
                "failed": failed,
                "items": [
                    {
                        "id": row["run_id"],
                        "job_type": "SCAN_RUN",
                        "status": row["status"],
                        "requested_by": row["requested_by"],
                        "run_id": row["run_id"],
                        "created_at": row["created_at_utc"],
                        "started_at": row["started_at_utc"],
                        "finished_at": row["finished_at_utc"],
                        "result": row["result"],
                    }
                    for row in runs[:20]
                ],
            },
            "settings": settings,
            "performance": {
                "summary": (performance or {}).get("summary", {}),
                "breakdown": (performance or {}).get("breakdown", {}),
            },
            "orders": {
                "open_orders": open_orders,
                "closed_orders": closed_orders[:100],
            },
            "trace_logs": {
                "items": trace_logs,
            },
            "portfolio": {
                "summary": self._build_portfolio_summary(portfolio),
                "portfolio": portfolio or {},
                "avg_hold_minutes": 0,
                "daily": [],
                "recent_closed": [],
                "open_positions": positions,
                "engine": {"status": engine_status},
                "equity_curve": equity_curve,
            },
            "market": {
                "items": market["items"],
                "top_movers": market["top_movers"],
            },
            "simulations": {
                "summary": simulation_summary,
                "runs": simulations,
            },
            "highlights": {
                "top_movers": market["top_movers"],
                "recent_events": recent_events,
                "recent_simulations": simulations[:6],
            },
            "symbols": {
                "symbols": symbols,
                "intervals": intervals,
            },
            "alerts": {
                "items": [
                    {
                        "severity": alert["severity"],
                        "kind": alert["kind"],
                        "scope": alert["scope"],
                        "message": alert["message"],
                        "detected_at_utc": alert["detected_at_utc"],
                    }
                    for alert in alerts
                ],
            },
        }

    def get_market_overview(self, limit: int = 50) -> dict[str, Any]:
        with session_scope() as session:
            settings = self.settings_repo.get_all(session)
            symbols = _resolve_symbols(settings)
            intervals = _split_csv(settings.get("AUTONOMOUS_INTERVALS"), ["15m", "30m", "1h", "4h", "1d", "3d", "7d", "14d", "1M"])
            signals = self.signal_repo.list_signals(session, limit=max(limit * 4, 100))
            overview = self._build_market_overview(session, symbols, intervals, signals)
        overview["items"] = overview["items"][:limit]
        overview["top_movers"] = overview["top_movers"][: min(limit, 20)]
        return overview

    def get_market_signals(self, limit: int = 100) -> dict[str, Any]:
        with session_scope() as session:
            signals = self.signal_repo.list_signals(session, limit=limit)
        return {"items": signals}

    def _build_market_overview(
        self,
        session: Session,
        symbols: list[str],
        intervals: list[str],
        signals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        signal_by_symbol: dict[str, dict[str, Any]] = {}
        for signal in signals:
            signal_by_symbol.setdefault(str(signal["symbol"]), signal)

        live_items: list[dict[str, Any]] = []
        try:
            live_items = self.market_overview_fetcher(symbols)
        except Exception:
            live_items = []

        live_by_symbol = {str(item["symbol"]): item for item in live_items}
        cached_by_symbol = self._cached_market_fallback(session, symbols, intervals[0] if intervals else "15m")
        items: list[dict[str, Any]] = []
        for symbol in symbols:
            base = dict(cached_by_symbol.get(symbol, {"symbol": symbol}))
            base.update(live_by_symbol.get(symbol, {}))
            signal = signal_by_symbol.get(symbol, {})
            items.append({
                "symbol": symbol,
                "price": float(base.get("price", 0.0) or 0.0),
                "last": float(base.get("price", 0.0) or 0.0),
                "change_pct": float(base.get("change_pct", 0.0) or 0.0),
                "high_24h": float(base.get("high_24h", 0.0) or 0.0),
                "low_24h": float(base.get("low_24h", 0.0) or 0.0),
                "volume": float(base.get("volume_24h", base.get("volume", 0.0)) or 0.0),
                "quote_volume": float(base.get("quote_volume_24h", base.get("quote_volume", 0.0)) or 0.0),
                "count": int(base.get("trades_24h", base.get("count", 0)) or 0),
                "interval": signal.get("interval") or (intervals[0] if intervals else "15m"),
                "mode": signal.get("mode"),
                "direction": signal.get("direction"),
                "confidence": signal.get("confidence"),
                "regime": signal.get("regime"),
                "trend": signal.get("trend"),
                "summary": signal.get("summary"),
                "created_at_utc": signal.get("created_at_utc"),
            })
        top_movers = sorted(items, key=lambda item: abs(float(item.get("change_pct", 0.0) or 0.0)), reverse=True)
        return {
            "items": items,
            "top_movers": top_movers[:12],
            "symbols": symbols,
            "intervals": intervals,
        }

    @staticmethod
    def _cached_market_fallback(session: Session, symbols: list[str], interval: str) -> dict[str, dict[str, Any]]:
        fallback: dict[str, dict[str, Any]] = {}
        for symbol in symbols:
            rows = (
                session.query(Candle)
                .filter(Candle.symbol == symbol, Candle.interval == interval)
                .order_by(Candle.open_time_utc.desc())
                .limit(2)
                .all()
            )
            if not rows:
                continue
            latest = rows[0]
            previous = rows[1] if len(rows) > 1 else None
            change_pct = 0.0
            if previous and previous.close:
                change_pct = ((latest.close - previous.close) / previous.close) * 100.0
            fallback[symbol] = {
                "symbol": symbol,
                "price": latest.close,
                "change_pct": change_pct,
                "high_24h": latest.high,
                "low_24h": latest.low,
                "volume": latest.volume,
                "quote_volume": 0.0,
                "count": 0,
            }
        return fallback

    @staticmethod
    def _build_recent_events(signals: list[dict[str, Any]], runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        signal_events = [
            {
                "timestamp": signal["created_at_utc"],
                "event_type": "SIGNAL_EMITTED",
                "decision": signal["direction"],
                "symbol": signal["symbol"],
                "reason_text": signal["summary"],
            }
            for signal in signals[:12]
        ]
        run_events = [
            {
                "timestamp": run["finished_at_utc"] or run["created_at_utc"],
                "event_type": "SCAN_COMPLETED",
                "decision": run["status"],
                "symbol": ",".join(run.get("symbols", [])[:2]),
                "reason_text": run["summary"],
            }
            for run in runs[:8]
        ]
        events = signal_events + run_events
        return sorted(events, key=lambda item: str(item.get("timestamp") or ""), reverse=True)[:20]

    @staticmethod
    def _build_portfolio_summary(portfolio: dict[str, Any] | None) -> dict[str, Any]:
        if not portfolio:
            return {
                "total_equity": 0.0,
                "cash_balance": 0.0,
                "unrealized_pnl": 0.0,
                "realized_pnl": 0.0,
                "open_positions": 0,
                "closed_trades": 0,
                "net_r": 0.0,
            }
        snapshot = dict(portfolio.get("snapshot") or {})
        return {
            "total_equity": portfolio.get("total_equity", 0.0),
            "cash_balance": portfolio.get("cash_balance", 0.0),
            "unrealized_pnl": portfolio.get("unrealized_pnl", 0.0),
            "realized_pnl": portfolio.get("realized_pnl", 0.0),
            "open_positions": portfolio.get("open_positions", 0),
            "closed_trades": portfolio.get("closed_trades", 0),
            "net_r": snapshot.get("net_r", portfolio.get("realized_pnl", 0.0)),
        }

    @staticmethod
    def _build_equity_curve(portfolio_history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in reversed(portfolio_history):
            snapshot = dict(item.get("snapshot") or {})
            rows.append({
                "timestamp": item["created_at_utc"],
                "equity": item["total_equity"],
                "net_r": snapshot.get("net_r", item.get("realized_pnl", 0.0)),
            })
        return rows
