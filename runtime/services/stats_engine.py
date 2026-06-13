"""Stats and learning helpers for v4 using the v4 persistence schema."""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from typing import Any

from runtime.db.repos.order_repo import OrderRepository
from runtime.db.repos.signal_repo import SignalRepository
from runtime.db.session import get_database_url, session_scope

_STATS_CACHE_TTL_SECONDS = 10.0
_ORDERS_CACHE_TTL_SECONDS = 30.0
_CACHE_LOCK = Lock()
_STATS_CACHE = {"ts": 0.0, "stats": None}
_ORDERS_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_CONFIDENCE_WEIGHTS_CACHE: dict[tuple[str, str, str, str, str], tuple[float, dict[str, float] | None]] = {}


def _confidence_band(confidence: float) -> str:
    value = float(confidence or 0.0)
    if value < 40:
        return "0-40"
    if value < 60:
        return "40-60"
    if value < 80:
        return "60-80"
    return "80-100"


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _closed_orders() -> list[dict[str, Any]]:
    database_url = get_database_url()
    now = time.time()
    with _CACHE_LOCK:
        cached = _ORDERS_CACHE.get(database_url)
    if cached and now - cached[0] < _ORDERS_CACHE_TTL_SECONDS:
        return [dict(item) for item in cached[1]]

    repo = OrderRepository()
    signal_repo = SignalRepository()
    with session_scope() as session:
        rows = [row for row in repo.list_orders(session, limit=5000) if str(row.get("status") or "").upper() != "OPEN"]
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row.get("payload") or {})
            signal_payload = dict(payload.get("signal") or {})
            signal = signal_repo.get_signal(session, str(row.get("signal_id") or "")) if row.get("signal_id") else None
            items.append(
                {
                    **row,
                    "realized_r": _as_float(payload.get("realized_r")),
                    "realized_pnl": _as_float(payload.get("realized_pnl")),
                    "regime": signal_payload.get("regime") or (signal or {}).get("regime"),
                    "summary": signal_payload.get("summary") or (signal or {}).get("summary"),
                    "factors": list((signal or {}).get("factors") or signal_payload.get("factors") or []),
                    "confidence_band": _confidence_band(_as_float(row.get("confidence"))),
                }
            )
    with _CACHE_LOCK:
        _ORDERS_CACHE[database_url] = (now, items)
    return [dict(item) for item in items]


def _aggregate(orders: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(orders)
    wins = [o for o in orders if _as_float(o.get("realized_r")) > 0]
    losses = [o for o in orders if _as_float(o.get("realized_r")) <= 0]
    gross_profit = sum(_as_float(o.get("realized_r")) for o in wins)
    gross_loss = abs(sum(_as_float(o.get("realized_r")) for o in losses))
    avg_r = sum(_as_float(o.get("realized_r")) for o in orders) / total if total else 0.0
    return {
        "count": total,
        "total_trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "winrate": round((len(wins) / total * 100.0) if total else 0.0, 2),
        "win_rate": round((len(wins) / total * 100.0) if total else 0.0, 2),
        "avg_r": round(avg_r, 4),
        "avg_win": round((gross_profit / len(wins)) if wins else 0.0, 4),
        "avg_loss": round((gross_loss / len(losses)) if losses else 0.0, 4),
        "avg_rr_win": round((gross_profit / len(wins)) if wins else 0.0, 4),
        "avg_rr_loss": round((gross_loss / len(losses)) if losses else 0.0, 4),
        "profit_factor": round((gross_profit / gross_loss) if gross_loss else (gross_profit if gross_profit else 0.0), 4),
        "gross_profit_r": round(gross_profit, 4),
        "gross_loss_r": round(gross_loss, 4),
        "net_r": round(gross_profit - gross_loss, 4),
        "expectancy": round(avg_r, 4),
    }


def get_confidence_weights(symbol: str, interval: str, regime: str, mode: str) -> dict[str, float] | None:
    cache_key = (get_database_url(), str(symbol or ""), str(interval or ""), str(regime or ""), str(mode or ""))
    now = time.time()
    with _CACHE_LOCK:
        cached = _CONFIDENCE_WEIGHTS_CACHE.get(cache_key)
    if cached and now - cached[0] < _ORDERS_CACHE_TTL_SECONDS:
        value = cached[1]
        return dict(value) if isinstance(value, dict) else None

    orders = [
        row
        for row in _closed_orders()
        if str(row.get("symbol") or "") == symbol
        and str(row.get("interval") or "") == interval
        and str(row.get("mode") or "") == mode
        and str(row.get("regime") or "UNKNOWN") == regime
    ]
    if len(orders) < 5:
        with _CACHE_LOCK:
            _CONFIDENCE_WEIGHTS_CACHE[cache_key] = (now, None)
        return None

    role_scores = {
        "TREND": 0.0,
        "STRUCTURE": 0.0,
        "MOMENTUM": 0.0,
        "VOLUME": 0.0,
    }
    role_counts = {key: 0 for key in role_scores}
    for order in orders:
        realized_r = _as_float(order.get("realized_r"))
        for factor in order.get("factors") or []:
            if not isinstance(factor, dict) or not factor.get("used", True):
                continue
            role = str(factor.get("role") or "").upper()
            if role not in role_scores:
                continue
            factor_score = abs(_as_float(factor.get("score"), 0.0))
            weight = _as_float(factor.get("weight"), 1.0)
            role_scores[role] += max(0.0, realized_r) * max(factor_score, 0.05) * max(weight, 0.1)
            role_counts[role] += 1

    averaged = {}
    for role, total in role_scores.items():
        count = role_counts[role]
        averaged[role] = (total / count) if count else 0.0
    if not any(averaged.values()):
        return None

    normalized = {
        "trend": averaged["TREND"],
        "structure": averaged["STRUCTURE"],
        "momentum": averaged["MOMENTUM"],
        "volume": averaged["VOLUME"],
    }
    total = sum(normalized.values()) or 1.0
    result = {key: round(value / total, 4) for key, value in normalized.items()}
    with _CACHE_LOCK:
        _CONFIDENCE_WEIGHTS_CACHE[cache_key] = (now, dict(result))
    return result


def get_learning_multiplier(symbol: str, interval: str, regime: str, mode: str, direction: str, confidence: float):
    orders = _closed_orders()
    if not orders:
        return {"multiplier": 1.0, "sample_size": 0, "win_rate": 0.0, "profit_factor": 0.0, "scope": "none"}

    exact = [
        row
        for row in orders
        if str(row.get("symbol") or "") == symbol
        and str(row.get("interval") or "") == interval
        and str(row.get("mode") or "") == mode
        and str(row.get("direction") or "") == direction
        and str(row.get("regime") or "UNKNOWN") == regime
        and str(row.get("confidence_band") or "") == _confidence_band(confidence)
    ]
    regime_rows = [row for row in orders if str(row.get("regime") or "UNKNOWN") == regime]
    mode_rows = [row for row in orders if str(row.get("mode") or "") == mode]
    symbol_rows = [row for row in orders if str(row.get("symbol") or "") == symbol]
    for scope, rows in [("EXACT", exact), ("REGIME", regime_rows), ("MODE", mode_rows), ("SYMBOL", symbol_rows)]:
        if len(rows) < 5:
            continue
        agg = _aggregate(rows)
        wr = float(agg["win_rate"])
        pf = float(agg["profit_factor"])
        multiplier = 1.0
        if wr >= 65 and pf >= 1.4:
            multiplier = 1.2
        elif wr >= 58 and pf >= 1.1:
            multiplier = 1.1
        elif wr <= 40 or pf < 0.8:
            multiplier = 0.75
        elif wr <= 48 or pf < 1.0:
            multiplier = 0.9
        return {
            "multiplier": multiplier,
            "sample_size": len(rows),
            "win_rate": wr,
            "profit_factor": pf,
            "scope": scope,
        }
    return {"multiplier": 1.0, "sample_size": 0, "win_rate": 0.0, "profit_factor": 0.0, "scope": "none"}


def calculate_stats():
    now = time.time()
    with _CACHE_LOCK:
        if _STATS_CACHE["stats"] and now - _STATS_CACHE["ts"] < _STATS_CACHE_TTL_SECONDS:
            return _STATS_CACHE["stats"]

    orders = _closed_orders()
    if not orders:
        result = {"total": 0, "resolved": 0, "message": "No resolved trades to compute stats."}
        with _CACHE_LOCK:
            _STATS_CACHE["stats"] = result
            _STATS_CACHE["ts"] = now
        return result

    global_stats = _aggregate(orders)

    def by(field: str):
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for order in orders:
            grouped[str(order.get(field) or "UNKNOWN")].append(order)
        return {key: _aggregate(value) for key, value in grouped.items()}

    result = {
        "resolved": len(orders),
        "total_tracked": len(orders),
        "global": global_stats,
        "summary": global_stats,
        "by_regime": by("regime"),
        "by_mode": by("mode"),
        "by_symbol": by("symbol"),
        "by_interval": by("interval"),
        "by_direction": by("direction"),
        "by_confidence_band": by("confidence_band"),
        "by_source": by("source"),
    }
    with _CACHE_LOCK:
        _STATS_CACHE["stats"] = result
        _STATS_CACHE["ts"] = now
    return result
