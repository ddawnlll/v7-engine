"""Market and dashboard-facing routes for v4."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from runtime.runtime.market_data import MarketDataRuntime
from runtime.runtime.scan_runtime import HTF_MAP
from runtime.services.binance_client import INTERVALS, POPULAR_PAIRS, DEFAULT_SCAN_SYMBOLS, fetch_all_tickers, fetch_klines, fetch_orderbook, fetch_top_usdt_pairs
from runtime.services.analyzer_engine_adapter import AnalyzerEngineAdapter
from runtime.services.dashboard_service import DashboardService
from runtime.services.indicator_snapshot import build_indicator_snapshot, enrich_snapshot_with_orderbook
from runtime.services.stats_engine import calculate_stats
from runtime.services.trend_service import determine_trend
from v6.contracts.analysis_request import ExecutionContextSection, RuntimeContextSection
from v6.contracts.enums import RequestKind
from v6.runtime.request_assembler import build_analysis_request
from v6.snapshot.builder import UnifiedSnapshotBuilder
from v6.snapshot.modes import SnapshotMode

router = APIRouter(tags=["markets"])
market_runtime: MarketDataRuntime | None = None
dashboard_service: DashboardService = DashboardService()
analyzer_adapter = AnalyzerEngineAdapter()
snapshot_builder = UnifiedSnapshotBuilder()
DEFAULT_MARKET_SYMBOL_LIMIT = 143


def get_market_runtime() -> MarketDataRuntime:
    global market_runtime
    if market_runtime is None:
        market_runtime = MarketDataRuntime()
    return market_runtime


def get_dashboard_service() -> DashboardService:
    return dashboard_service


class MarketOverviewResponse(BaseModel):
    items: list[dict] = Field(default_factory=list)
    top_movers: list[dict] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    intervals: list[str] = Field(default_factory=list)


class MarketSignalsResponse(BaseModel):
    items: list[dict] = Field(default_factory=list)


def _resolve_htf_trend(symbol: str, interval: str) -> str | None:
    htf_interval = HTF_MAP.get(interval)
    if not htf_interval:
        return None
    try:
        market_bundle = get_market_runtime().get_market_snapshot(symbol, htf_interval)
        trend, _strength, _factors = determine_trend(market_bundle["snapshot"])
        if trend == "BULLISH":
            return "BUY"
        if trend == "BEARISH":
            return "SELL"
        return "MIXED"
    except Exception:
        return None


def _analyze_live_bundle(symbol: str, interval: str, mode: str, bundle: dict):
    snapshot = dict(bundle["snapshot"])
    try:
        snapshot = enrich_snapshot_with_orderbook(snapshot, fetch_orderbook(symbol))
    except Exception:
        pass
    htf_interval = HTF_MAP.get(interval)
    raw_htf_candles = {}
    if htf_interval:
        try:
            htf_bundle = get_market_runtime().get_market_snapshot(symbol, htf_interval, limit=250)
            raw_htf_candles[htf_interval] = list(htf_bundle.get("candles") or [])
            htf_trend = _resolve_htf_trend(symbol, interval)
            if htf_trend:
                snapshot["htf_trend"] = htf_trend
        except Exception:
            pass
    raw_candles = list(bundle.get("candles") or [])
    timestamp_utc = datetime.now(timezone.utc).isoformat()
    snapshot_artifact = snapshot_builder.build(
        symbol=symbol,
        interval=interval,
        timestamp_utc=timestamp_utc,
        request_kind=RequestKind.LIVE_SCAN,
        raw_candles=raw_candles,
        raw_htf_candles=raw_htf_candles,
        engine_mode="LIVE",
        runtime_context_hints={"mode": mode, "requested_by": "markets_api"},
        data_source="live",
        mode=SnapshotMode.LIVE_RUNTIME,
    )
    analysis_request = build_analysis_request(
        snapshot=snapshot_artifact,
        execution_context=ExecutionContextSection(
            position_exists=False,
            position_direction="NONE",
            position_size_fraction=0.0,
            symbol_exposure_fraction=0.0,
        ),
        runtime_context=RuntimeContextSection(
            source_context="live_scan",
            requested_by="markets_api",
            paper_or_live_mode=mode,
            engine_budget_hint="normal",
            runtime_phase="market_api",
        ),
        trade_mode=mode,
        request_kind=RequestKind.LIVE_SCAN,
    )
    analysis = analyzer_adapter.analyze_request(analysis_request)
    snapshot["candles"] = raw_candles
    if raw_htf_candles and htf_interval in raw_htf_candles:
        snapshot["htf_candles"] = raw_htf_candles[htf_interval]
    return analysis, snapshot


@router.get("/api/v3/dashboard")
def get_dashboard():
    return get_dashboard_service().get_dashboard()


@router.get("/api/symbols")
def get_symbols():
    symbols = fetch_top_usdt_pairs(limit=DEFAULT_MARKET_SYMBOL_LIMIT)
    return {"symbols": symbols or list(DEFAULT_SCAN_SYMBOLS), "intervals": list(INTERVALS)}


@router.get("/api/market")
def get_market():
    return fetch_all_tickers()


@router.get("/api/v3/market/overview", response_model=MarketOverviewResponse)
def get_market_overview(limit: int = Query(default=50, ge=1, le=500)):
    return get_dashboard_service().get_market_overview(limit=limit)


@router.get("/api/v3/market/signals", response_model=MarketSignalsResponse)
def get_market_signals(limit: int = Query(default=100, ge=1, le=500)):
    return get_dashboard_service().get_market_signals(limit=limit)


@router.get("/api/v3/klines")
@router.get("/api/klines")
def get_klines(
    symbol: str = Query(..., min_length=3),
    interval: str = Query(..., min_length=1),
    limit: int = Query(default=120, ge=1, le=1000),
):
    bundle = get_market_runtime().get_market_snapshot(symbol.upper(), interval, limit=limit)
    return [
        {
            "symbol": symbol.upper(),
            "interval": interval,
            "open_time": row["open_time_utc"],
            "close_time": row["close_time_utc"],
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
            "stale": row.get("stale", bundle["stale"]),
        }
        for row in bundle["candles"]
    ]


@router.get("/api/indicators")
def get_indicators(
    symbol: str = Query(..., min_length=3),
    interval: str = Query(..., min_length=1),
    limit: int = Query(default=120, ge=20, le=250),
):
    frame = fetch_klines(symbol.upper(), interval, limit=limit)
    snapshot = build_indicator_snapshot(frame)
    try:
        snapshot = enrich_snapshot_with_orderbook(snapshot, fetch_orderbook(symbol.upper()))
    except Exception:
        pass
    last_row = frame.tail(1).iloc[0]
    return [{
        "symbol": symbol.upper(),
        "interval": interval,
        "open_time": str(last_row["open_time"].isoformat() if hasattr(last_row["open_time"], "isoformat") else last_row["open_time"]),
        "close_time": str(last_row["close_time"].isoformat() if hasattr(last_row["close_time"], "isoformat") else last_row["close_time"]),
        **snapshot,
    }]


@router.get("/api/v3/analyze")
@router.get("/api/analyze")
def analyze_market(
    symbol: str = Query(..., min_length=3),
    interval: str = Query(..., min_length=1),
    mode: str = Query(default="SCALP", min_length=1),
):
    bundle = get_market_runtime().get_market_snapshot(symbol.upper(), interval, limit=250)
    analysis, snapshot = _analyze_live_bundle(symbol.upper(), interval, mode.upper(), bundle)
    signal = dict(analysis.get("signal") or {})
    ticker = {
        "symbol": symbol.upper(),
        "price": bundle["candles"][-1]["close"] if bundle["candles"] else snapshot.get("price"),
        "volume": bundle["candles"][-1]["volume"] if bundle["candles"] else 0.0,
        "stale": bundle["stale"],
    }
    return {
        **signal,
        "engine": analysis.get("engine_identity"),
        "signal_status": analysis.get("signal_status"),
        "warnings": analysis.get("warnings"),
        "snapshot": snapshot,
        "ticker": ticker,
    }


@router.get("/api/scan")
def scan_market(interval: str = Query(default="1h"), mode: str = Query(default="SWING")):
    results: list[dict] = []
    tickers = {item["symbol"]: item for item in fetch_all_tickers()}
    for symbol in POPULAR_PAIRS:
        try:
            bundle = get_market_runtime().get_market_snapshot(symbol, interval, limit=250)
            analysis, snapshot = _analyze_live_bundle(symbol, interval, mode.upper(), bundle)
            signal = dict(analysis.get("signal") or {})
            ticker = tickers.get(symbol, {"price": snapshot.get("price"), "change_pct": 0.0})
            results.append({
                "symbol": symbol,
                "direction": signal["direction"],
                "confidence": signal["confidence"],
                "trend": signal["trend"],
                "engine_name": analysis.get("engine_name"),
                "engine_version": analysis.get("engine_version"),
                "price": ticker.get("price"),
                "change_pct": ticker.get("change_pct"),
                "summary": signal["summary"],
                "mode": signal["mode"],
                "risk_reward": signal["risk_reward"],
            })
        except Exception as exc:
            results.append({"symbol": symbol, "error": str(exc)})
    results.sort(key=lambda item: (0 if item.get("direction") in {"BUY", "SELL"} else 1, -float(item.get("confidence", 0) or 0)))
    return results


@router.get("/api/orderbook")
def get_orderbook(symbol: str = Query(..., min_length=3)):
    return fetch_orderbook(symbol)


@router.get("/api/stats")
def get_stats():
    return calculate_stats()
