"""Composite trade analytics for ranking real edge from closed trades."""

from __future__ import annotations

import csv
import io
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from runtime.db.models import Order, Signal, TradeFailure
from runtime.db.repos._helpers import loads_json
from runtime.db.session import session_scope
from runtime.services.universe_filter_service import UniverseFilterService

ANALYTICS_TIMEZONE = "UTC"


def _lookback_start(lookback_days: int | None) -> str | None:
    if lookback_days is None or int(lookback_days) <= 0:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=int(lookback_days))).isoformat()


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class TradeAnalyticsService:
    def __init__(self, universe_filter_service: UniverseFilterService | None = None) -> None:
        self.universe_filter_service = universe_filter_service or UniverseFilterService()

    def get_payload(
        self,
        *,
        lookback_days: int = 30,
        min_samples: int = 10,
        mode: str | None = None,
        symbol: str | None = None,
        interval: str | None = None,
        direction: str | None = None,
    ) -> dict[str, Any]:
        filters = {
            "mode": mode,
            "symbol": symbol,
            "interval": interval,
            "direction": direction,
        }
        with session_scope() as session:
            source_rows = self._base_rows(session, lookback_days=(lookback_days * 2 if lookback_days > 0 else 0), filters=filters)
        current = self._current_window(source_rows, lookback_days=lookback_days)
        prior = self._prior_window(source_rows, lookback_days=lookback_days)
        return {
            "ok": True,
            "filters": {
                "lookback_days": lookback_days,
                "min_samples": min_samples,
                "mode": mode,
                "symbol": symbol,
                "interval": interval,
                "direction": direction,
                "timezone": ANALYTICS_TIMEZONE,
            },
            "overview": self.get_overview_from_rows(current, min_samples=min_samples),
            "leaderboards": self.get_method_leaderboard_from_rows(current, min_samples=min_samples),
            "timing": self.get_timing_breakdown_from_rows(current),
            "symbols": self.get_symbol_breakdown_from_rows(current, min_samples=min_samples),
            "market_conditions": self.get_market_condition_breakdown_from_rows(current, min_samples=min_samples),
            "direction": self.get_direction_breakdown_from_rows(current, min_samples=min_samples),
            "confidence_buckets": self.get_confidence_bucket_breakdown_from_rows(current),
            "confidence_monotonicity": self.get_confidence_monotonicity_from_rows(current),
            "exit_quality": self.get_exit_quality_breakdown_from_rows(current),
            "time_stop_analysis": self.get_time_stop_analysis_from_rows(current),
            "validation_dashboards": self.get_validation_dashboards_from_rows(current),
            "symbol_throttles": self.universe_filter_service.evaluate(),
            "recommendations": self.get_recommendations_from_rows(current, min_samples=min_samples),
            "comparison": self.get_comparison_from_rows(current, prior, min_samples=min_samples),
            "audit_analytics": self.get_audit_analytics_from_rows(current),
            "meta": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "total_rows": len(current),
                "timezone": ANALYTICS_TIMEZONE,
                "has_audit_data": any(bool(row.get("audit")) for row in current),
            },
        }

    def export_csv(
        self,
        *,
        lookback_days: int = 30,
        mode: str | None = None,
        symbol: str | None = None,
        interval: str | None = None,
        direction: str | None = None,
    ) -> str:
        filters = {"mode": mode, "symbol": symbol, "interval": interval, "direction": direction}
        with session_scope() as session:
            rows = self._base_rows(session, lookback_days=lookback_days, filters=filters)
        fieldnames = [
            "order_id",
            "symbol",
            "interval",
            "mode",
            "setup_method",
            "direction",
            "regime",
            "trend",
            "session_label",
            "hour_of_day",
            "day_of_week",
            "confidence",
            "confidence_before_learning",
            "realized_r",
            "close_reason",
            "hold_minutes",
            "stop_hit",
            "target_hit",
            "time_exit",
            "opened_at_utc",
            "closed_at_utc",
        ]
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name) for name in fieldnames})
        return out.getvalue()

    def _base_rows(self, session: Session, *, lookback_days: int, filters: dict[str, Any]) -> list[dict[str, Any]]:
        query = session.query(Order, Signal, TradeFailure).outerjoin(Signal, Signal.signal_id == Order.signal_id).outerjoin(TradeFailure, TradeFailure.order_id == Order.order_id)
        query = query.filter(Order.status != "OPEN")
        date_from = _lookback_start(lookback_days)
        if date_from:
            query = query.filter(Order.closed_at_utc >= date_from)
        if filters.get("mode"):
            query = query.filter(Order.mode == filters["mode"])
        if filters.get("symbol"):
            query = query.filter(Order.symbol == filters["symbol"])
        if filters.get("interval"):
            query = query.filter(Order.interval == filters["interval"])
        if filters.get("direction"):
            query = query.filter(Order.direction == filters["direction"])
        query = query.order_by(Order.closed_at_utc.desc())

        rows: list[dict[str, Any]] = []
        for order, signal, failure in query.all():
            payload = loads_json(order.payload_json, {})
            signal_payload = dict(payload.get("signal") or {})
            learning = dict(payload.get("learning") or {})
            audit = loads_json(getattr(signal, "audit_json", "{}"), {}) if signal is not None else {}
            snapshot = loads_json(getattr(signal, "snapshot_json", "{}"), {}) if signal is not None else {}
            stop_model = dict(audit.get("stop_model") or {})
            learning_adjustments_applied = list(audit.get("learning_adjustments_applied") or [])
            opened_at = _parse_iso(order.opened_at_utc)
            closed_at = _parse_iso(order.closed_at_utc)
            session_label = str(audit.get("session_label") or (snapshot.get("session_label")) or "unknown")
            regime = str(signal_payload.get("regime") or getattr(signal, "regime", None) or "UNKNOWN")
            trend = str(signal_payload.get("trend") or getattr(signal, "trend", None) or "UNKNOWN")
            direction_value = str(order.direction or signal_payload.get("direction") or "UNKNOWN")
            close_reason = str(payload.get("close_reason") or "UNKNOWN")
            realized_r_raw = payload.get("realized_r")
            realized_r = float(realized_r_raw) if realized_r_raw is not None else None
            hold_minutes = max(0.0, ((closed_at or opened_at or datetime.now(timezone.utc)) - (opened_at or datetime.now(timezone.utc))).total_seconds() / 60.0) if opened_at else 0.0
            volatility_bucket = self._volatility_bucket(snapshot, audit)
            row = {
                "order_id": order.order_id,
                "signal_id": order.signal_id,
                "symbol": order.symbol,
                "source": str(order.source or "UNKNOWN").upper(),
                "interval": order.interval,
                "mode": order.mode,
                "setup_method": f"{order.mode}|{regime}|{session_label}|{direction_value}",
                "direction": direction_value,
                "regime": regime,
                "trend": trend,
                "volatility_bucket": volatility_bucket,
                "session_label": session_label,
                "hour_of_day": opened_at.hour if opened_at else None,
                "day_of_week": opened_at.strftime("%a") if opened_at else "UNK",
                "confidence": _as_float(order.confidence),
                "confidence_before_learning": _as_float(learning.get("confidence_before")),
                "confidence_after_learning": _as_float(learning.get("confidence_after"), _as_float(order.confidence)),
                "probability_before_learning": _as_float(learning.get("probability_before")),
                "probability_after_learning": _as_float(learning.get("probability_after")),
                "realized_r": realized_r,
                "close_reason": close_reason,
                "hold_minutes": hold_minutes,
                "stop_hit": close_reason == "HIT_SL",
                "target_hit": close_reason == "HIT_TP",
                "time_exit": close_reason == "TIME_STOP",
                "stale_exit": close_reason == "EARLY_STALE_EXIT",
                "stop_method": stop_model.get("stop_method"),
                "stop_distance_atr": _as_float(stop_model.get("stop_distance_atr")),
                "atr_floor_stop": _as_float(stop_model.get("atr_floor_stop")),
                "structure_stop": _as_float(stop_model.get("structure_stop")),
                "atr_value": _as_float(snapshot.get("atr") or (audit.get("raw_snapshot") or {}).get("atr")),
                "failure_source": getattr(failure, "failure_source", None),
                "blamed_component": getattr(failure, "blamed_component", None),
                "failure_classification": getattr(failure, "classification", None),
                "learning_adjustments_applied": learning_adjustments_applied,
                "component_penalty_multiplier": next(
                    (
                        _as_float(item.get("multiplier"))
                        for item in learning_adjustments_applied
                        if str(item.get("source") or "") == "component_penalty"
                    ),
                    None,
                ),
                "expected_candles_target": _as_float(payload.get("expected_candles_target")),
                "expected_candles_max": _as_float(payload.get("expected_candles_max")),
                "interval_minutes": _as_float(payload.get("interval_minutes")),
                "opened_at_utc": order.opened_at_utc,
                "closed_at_utc": order.closed_at_utc,
                "time_stop_cause": None,
                "audit": audit,
            }
            row["time_stop_cause"] = self._classify_time_stop_cause(row)
            rows.append(row)
        return rows

    @staticmethod
    def _volatility_bucket(snapshot: dict[str, Any], audit: dict[str, Any]) -> str:
        if snapshot.get("volatility_regime"):
            return str(snapshot["volatility_regime"])
        vol_ratio = _as_float(snapshot.get("vol_ratio") or (audit.get("raw_snapshot") or {}).get("vol_ratio"))
        if vol_ratio >= 1.5:
            return "HIGH_VOL"
        if vol_ratio >= 1.0:
            return "NORMAL_VOL"
        if vol_ratio > 0:
            return "LOW_VOL"
        return "UNKNOWN"

    @staticmethod
    def _profit_factor(rows: list[dict[str, Any]]) -> float:
        gross_profit = sum(max(_as_float(row.get("realized_r")), 0.0) for row in rows)
        gross_loss = sum(abs(min(_as_float(row.get("realized_r")), 0.0)) for row in rows)
        if gross_loss <= 0:
            return gross_profit if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    @staticmethod
    def _max_drawdown_r(rows: list[dict[str, Any]]) -> float:
        equity = 0.0
        peak = 0.0
        max_drawdown = 0.0
        for row in sorted(rows, key=lambda item: str(item.get("closed_at_utc") or "")):
            equity += _as_float(row.get("realized_r"))
            peak = max(peak, equity)
            max_drawdown = min(max_drawdown, equity - peak)
        return abs(max_drawdown)

    def _group_metrics(self, label: str, rows: list[dict[str, Any]], *, min_samples: int) -> dict[str, Any]:
        trades = len(rows)
        wins = sum(1 for row in rows if _as_float(row.get("realized_r")) > 0.0)
        avg_r = sum(_as_float(row.get("realized_r")) for row in rows) / trades if trades else 0.0
        expectancy_score = avg_r * math.sqrt(trades) if trades else 0.0
        reliability = "LOW_SAMPLE" if trades < min_samples else "BUILDING_SAMPLE" if trades < (min_samples * 2) else "STABLE"
        reason = (
            "best because expectancy is positive and sample is stable"
            if avg_r > 0 and reliability == "STABLE"
            else "worst because repeated stop-outs drive negative expectancy"
            if avg_r < 0
            else "sample is still building"
        )
        return {
            "label": label,
            "trades": trades,
            "win_rate": wins / trades if trades else 0.0,
            "avg_realized_r": avg_r,
            "net_r": sum(_as_float(row.get("realized_r")) for row in rows),
            "profit_factor": self._profit_factor(rows),
            "max_drawdown_r": self._max_drawdown_r(rows),
            "avg_hold_minutes": sum(_as_float(row.get("hold_minutes")) for row in rows) / trades if trades else 0.0,
            "stop_hit_pct": sum(1 for row in rows if row.get("stop_hit")) / trades if trades else 0.0,
            "target_hit_pct": sum(1 for row in rows if row.get("target_hit")) / trades if trades else 0.0,
            "time_exit_pct": sum(1 for row in rows if row.get("time_exit")) / trades if trades else 0.0,
            "expectancy_score": expectancy_score,
            "reliability": reliability,
            "provisional": trades < min_samples,
            "reason_summary": reason,
        }

    def _leaderboard(self, rows: list[dict[str, Any]], key: str, *, min_samples: int) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row.get(key) or "UNKNOWN")].append(row)
        metrics = [self._group_metrics(label, group_rows, min_samples=min_samples) for label, group_rows in grouped.items()]
        ranked = [row for row in metrics if not row["provisional"]]
        ranked.sort(key=lambda item: (float(item["expectancy_score"]), float(item["avg_realized_r"])), reverse=True)
        provisional = [row for row in metrics if row["provisional"]]
        provisional.sort(key=lambda item: item["trades"], reverse=True)
        return ranked + provisional

    def get_overview_from_rows(self, rows: list[dict[str, Any]], *, min_samples: int) -> dict[str, Any]:
        total = len(rows)
        wins = sum(1 for row in rows if _as_float(row.get("realized_r")) > 0.0)
        mode_board = self._leaderboard(rows, "mode", min_samples=min_samples)
        setup_board = self._leaderboard(rows, "setup_method", min_samples=min_samples)
        ranked_modes = [row for row in mode_board if not row["provisional"]]
        ranked_setups = [row for row in setup_board if not row["provisional"]]
        return {
            "total_closed_trades": total,
            "win_rate": wins / total if total else 0.0,
            "avg_realized_r": sum(_as_float(row.get("realized_r")) for row in rows) / total if total else 0.0,
            "net_r": sum(_as_float(row.get("realized_r")) for row in rows),
            "profit_factor": self._profit_factor(rows),
            "best_mode": ranked_modes[0]["label"] if ranked_modes else None,
            "worst_mode": ranked_modes[-1]["label"] if ranked_modes else None,
            "best_setup_method": ranked_setups[0]["label"] if ranked_setups else None,
            "worst_setup_method": ranked_setups[-1]["label"] if ranked_setups else None,
        }

    def get_method_leaderboard_from_rows(self, rows: list[dict[str, Any]], *, min_samples: int) -> dict[str, Any]:
        mode_rows = self._leaderboard(rows, "mode", min_samples=min_samples)
        setup_rows = self._leaderboard(rows, "setup_method", min_samples=min_samples)
        return {
            "best_modes": [row for row in mode_rows if not row["provisional"]][:5],
            "worst_modes": list(reversed([row for row in mode_rows if not row["provisional"]][-5:])),
            "best_setup_methods": [row for row in setup_rows if not row["provisional"]][:10],
            "worst_setup_methods": list(reversed([row for row in setup_rows if not row["provisional"]][-10:])),
            "provisional_modes": [row for row in mode_rows if row["provisional"]],
            "provisional_setup_methods": [row for row in setup_rows if row["provisional"]],
        }

    def get_timing_breakdown_from_rows(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        session_rows = self._leaderboard(rows, "session_label", min_samples=1)
        hour_rows = self._leaderboard(rows, "hour_of_day", min_samples=1)
        day_rows = self._leaderboard(rows, "day_of_week", min_samples=1)
        heatmap: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for row in rows:
            heatmap[str(row.get("session_label") or "unknown")][str(row.get("hour_of_day") if row.get("hour_of_day") is not None else "--")] += 1
        return {
            "by_session": session_rows,
            "by_hour_of_day": hour_rows,
            "by_day_of_week": day_rows,
            "session_hour_heatmap": {session: dict(hours) for session, hours in heatmap.items()},
            "timezone": ANALYTICS_TIMEZONE,
        }

    def get_symbol_breakdown_from_rows(self, rows: list[dict[str, Any]], *, min_samples: int) -> dict[str, Any]:
        symbol_interval_rows = []
        for row in rows:
            cloned = dict(row)
            cloned["symbol_interval"] = f"{row.get('symbol')} · {row.get('interval')}"
            symbol_interval_rows.append(cloned)
        symbol_board = self._leaderboard(rows, "symbol", min_samples=min_samples)
        combo_board = self._leaderboard(symbol_interval_rows, "symbol_interval", min_samples=min_samples)
        interval_board = self._leaderboard(rows, "interval", min_samples=min_samples)
        return {
            "best_symbols": [row for row in symbol_board if not row["provisional"]][:10],
            "worst_symbols": list(reversed([row for row in symbol_board if not row["provisional"]][-10:])),
            "best_symbol_intervals": [row for row in combo_board if not row["provisional"]][:10],
            "worst_symbol_intervals": list(reversed([row for row in combo_board if not row["provisional"]][-10:])),
            "best_intervals": [row for row in interval_board if not row["provisional"]][:10],
            "worst_intervals": list(reversed([row for row in interval_board if not row["provisional"]][-10:])),
        }

    def get_market_condition_breakdown_from_rows(self, rows: list[dict[str, Any]], *, min_samples: int) -> dict[str, Any]:
        return {
            "by_regime": self._leaderboard(rows, "regime", min_samples=min_samples),
            "by_trend": self._leaderboard(rows, "trend", min_samples=min_samples),
            "by_volatility_bucket": self._leaderboard(rows, "volatility_bucket", min_samples=min_samples),
        }

    def get_direction_breakdown_from_rows(self, rows: list[dict[str, Any]], *, min_samples: int) -> dict[str, Any]:
        return {"by_direction": self._leaderboard(rows, "direction", min_samples=min_samples)}

    def get_confidence_bucket_breakdown_from_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            confidence = _as_float(row.get("confidence_after_learning") or row.get("confidence"))
            bucket_floor = int(max(0, min(90, math.floor(confidence / 10.0) * 10)))
            label = f"{bucket_floor}-{bucket_floor + 10}"
            grouped[label].append(row)
        items = []
        for label, bucket_rows in grouped.items():
            trades = len(bucket_rows)
            items.append(
                {
                    "label": label,
                    "trades": trades,
                    "win_rate": sum(1 for row in bucket_rows if _as_float(row.get("realized_r")) > 0.0) / trades if trades else 0.0,
                    "avg_realized_r": sum(_as_float(row.get("realized_r")) for row in bucket_rows) / trades if trades else 0.0,
                    "avg_raw_confidence": sum(_as_float(row.get("confidence_before_learning")) for row in bucket_rows) / trades if trades else 0.0,
                    "avg_calibrated_confidence": sum(_as_float(row.get("confidence_after_learning") or row.get("confidence")) for row in bucket_rows) / trades if trades else 0.0,
                }
            )
        items.sort(key=lambda item: int(str(item["label"]).split("-")[0]))
        return items

    def get_confidence_monotonicity_from_rows(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "pre_learning": self._confidence_monotonicity(rows, "confidence_before_learning"),
            "post_learning": self._confidence_monotonicity(rows, "confidence_after_learning"),
        }

    def get_exit_quality_breakdown_from_rows(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(rows)
        return {
            "stop_hit_rate": sum(1 for row in rows if row.get("stop_hit")) / total if total else 0.0,
            "target_hit_rate": sum(1 for row in rows if row.get("target_hit")) / total if total else 0.0,
            "time_exit_rate": sum(1 for row in rows if row.get("time_exit")) / total if total else 0.0,
            "stale_exit_rate": sum(1 for row in rows if row.get("stale_exit")) / total if total else 0.0,
            "avg_hold_minutes": sum(_as_float(row.get("hold_minutes")) for row in rows) / total if total else 0.0,
            "mfe_available": False,
            "mae_available": False,
        }

    def get_time_stop_analysis_from_rows(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        time_stops = [row for row in rows if row.get("time_exit")]
        total = len(rows)
        expected_accuracy = []
        within_band = 0
        overrun = 0
        underrun = 0
        for row in time_stops:
            target = _as_float(row.get("expected_candles_target"))
            maximum = _as_float(row.get("expected_candles_max"))
            interval_minutes = _as_float(row.get("interval_minutes"))
            if target > 0 and interval_minutes > 0:
                expected_minutes = target * interval_minutes
                hold_minutes = _as_float(row.get("hold_minutes"))
                error_ratio = (hold_minutes - expected_minutes) / max(expected_minutes, 1.0)
                expected_accuracy.append(error_ratio)
                if abs(error_ratio) <= 0.25:
                    within_band += 1
                elif error_ratio > 0.25:
                    overrun += 1
                else:
                    underrun += 1
                row["expected_duration_error_ratio"] = round(error_ratio, 4)
                if maximum > 0:
                    row["expected_duration_overrun"] = hold_minutes > (maximum * interval_minutes)
            row["time_stop_cause"] = self._classify_time_stop_cause(row)
        return {
            "total_time_stops": len(time_stops),
            "time_stop_rate": len(time_stops) / total if total else 0.0,
            "avg_hold_minutes": sum(_as_float(row.get("hold_minutes")) for row in time_stops) / len(time_stops) if time_stops else 0.0,
            "avg_realized_r": sum(_as_float(row.get("realized_r")) for row in time_stops) / len(time_stops) if time_stops else 0.0,
            "expected_duration_accuracy": round(sum(expected_accuracy) / len(expected_accuracy), 4) if expected_accuracy else None,
            "expected_duration_accuracy_abs": round(sum(abs(item) for item in expected_accuracy) / len(expected_accuracy), 4) if expected_accuracy else None,
            "expected_duration_within_25pct": round(within_band / len(expected_accuracy), 4) if expected_accuracy else None,
            "expected_duration_overrun_rate": round(overrun / len(expected_accuracy), 4) if expected_accuracy else None,
            "expected_duration_underrun_rate": round(underrun / len(expected_accuracy), 4) if expected_accuracy else None,
            "by_mode": self._simple_group_avg(time_stops, "mode"),
            "by_interval": self._simple_group_avg(time_stops, "interval"),
            "by_session": self._simple_group_avg(time_stops, "session_label"),
            "by_regime": self._simple_group_avg(time_stops, "regime"),
            "by_source": self._simple_group_avg(time_stops, "source"),
            "cause_breakdown": self._simple_group_count(time_stops, "time_stop_cause"),
            "quality_breakdown": self._simple_group_count(time_stops, "time_stop_quality"),
            "mfe_available": False,
            "mae_available": False,
        }

    def get_validation_dashboards_from_rows(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        stop_hits = [row for row in rows if row.get("stop_hit")]
        time_stops = [row for row in rows if row.get("time_exit")]
        stale_exits = [row for row in rows if row.get("stale_exit")]
        return {
            "stop_hit_rate": {
                "overall": sum(1 for row in rows if row.get("stop_hit")) / len(rows) if rows else 0.0,
                "by_mode": self._rate_group(rows, "mode", predicate=lambda row: bool(row.get("stop_hit"))),
                "by_interval": self._rate_group(rows, "interval", predicate=lambda row: bool(row.get("stop_hit"))),
                "by_session": self._rate_group(rows, "session_label", predicate=lambda row: bool(row.get("stop_hit"))),
                "by_regime": self._rate_group(rows, "regime", predicate=lambda row: bool(row.get("stop_hit"))),
                "avg_realized_r_when_hit": self._avg_realized_r(stop_hits),
            },
            "time_stop_rate": {
                "overall": len(time_stops) / len(rows) if rows else 0.0,
                "avg_realized_r": self._avg_realized_r(time_stops),
                "by_mode": self._rate_group(rows, "mode", predicate=lambda row: bool(row.get("time_exit")), include_avg_r=True),
                "by_interval": self._rate_group(rows, "interval", predicate=lambda row: bool(row.get("time_exit")), include_avg_r=True),
                "by_session": self._rate_group(rows, "session_label", predicate=lambda row: bool(row.get("time_exit")), include_avg_r=True),
                "by_regime": self._rate_group(rows, "regime", predicate=lambda row: bool(row.get("time_exit")), include_avg_r=True),
                "by_source": self._rate_group(rows, "source", predicate=lambda row: bool(row.get("time_exit")), include_avg_r=True),
            },
            "stale_exit_rate": {
                "overall": len(stale_exits) / len(rows) if rows else 0.0,
                "avg_realized_r": self._avg_realized_r(stale_exits),
                "by_mode": self._rate_group(rows, "mode", predicate=lambda row: bool(row.get("stale_exit")), include_avg_r=True),
                "by_interval": self._rate_group(rows, "interval", predicate=lambda row: bool(row.get("stale_exit")), include_avg_r=True),
                "by_session": self._rate_group(rows, "session_label", predicate=lambda row: bool(row.get("stale_exit")), include_avg_r=True),
                "by_regime": self._rate_group(rows, "regime", predicate=lambda row: bool(row.get("stale_exit")), include_avg_r=True),
                "by_source": self._rate_group(rows, "source", predicate=lambda row: bool(row.get("stale_exit")), include_avg_r=True),
            },
        }

    @staticmethod
    def _classify_time_stop_cause(row: dict[str, Any]) -> str:
        realized_r = _as_float(row.get("realized_r"))
        expected_error = _as_float(row.get("expected_duration_error_ratio"))
        hold_minutes = _as_float(row.get("hold_minutes"))
        interval_minutes = max(_as_float(row.get("interval_minutes")), 1.0)
        if hold_minutes <= (interval_minutes * 0.75) and realized_r <= 0.15:
            row["time_stop_quality"] = "premature"
            return "never_developed"
        if realized_r <= -0.4:
            row["time_stop_quality"] = "adverse"
            return "late_reversal"
        if expected_error > 0.25 and realized_r <= 0.1:
            row["time_stop_quality"] = "stale"
            return "stale_range_bound_hold"
        if abs(realized_r) <= 0.2:
            row["time_stop_quality"] = "stale"
            return "stale_range_bound_hold"
        if realized_r < 0.0:
            row["time_stop_quality"] = "adverse"
            return "slow_drift"
        row["time_stop_quality"] = "flat_positive"
        return "never_developed"

    @staticmethod
    def _simple_group_count(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        grouped: dict[str, int] = defaultdict(int)
        for row in rows:
            grouped[str(row.get(key) or "UNKNOWN")] += 1
        return [{"label": label, "count": count} for label, count in sorted(grouped.items(), key=lambda item: (-item[1], item[0]))]

    @staticmethod
    def _simple_group_avg(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row.get(key) or "UNKNOWN")].append(row)
        return [
            {
                "label": label,
                "count": len(items),
                "avg_realized_r": sum(_as_float(item.get("realized_r")) for item in items) / len(items) if items else 0.0,
                "avg_hold_minutes": sum(_as_float(item.get("hold_minutes")) for item in items) / len(items) if items else 0.0,
            }
            for label, items in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
        ]

    @staticmethod
    def _avg_realized_r(rows: list[dict[str, Any]]) -> float:
        return sum(_as_float(row.get("realized_r")) for row in rows) / len(rows) if rows else 0.0

    def _rate_group(
        self,
        rows: list[dict[str, Any]],
        key: str,
        *,
        predicate,
        include_avg_r: bool = False,
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row.get(key) or "UNKNOWN")].append(row)
        items = []
        for label, group_rows in grouped.items():
            matched = [row for row in group_rows if predicate(row)]
            item = {
                "label": label,
                "trades": len(group_rows),
                "rate": len(matched) / len(group_rows) if group_rows else 0.0,
            }
            if include_avg_r:
                item["avg_realized_r"] = self._avg_realized_r(matched)
            items.append(item)
        return sorted(items, key=lambda item: (-int(item["trades"]), str(item["label"])))

    def _confidence_monotonicity(self, rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
        buckets = []
        for item in self.get_confidence_bucket_breakdown_from_rows([
            {**row, "confidence_after_learning": row.get(field), "confidence": row.get(field), "confidence_before_learning": row.get(field)}
            for row in rows
            if row.get(field) is not None
        ]):
            buckets.append({
                "label": item["label"],
                "trades": item["trades"],
                "win_rate": item["win_rate"],
                "avg_realized_r": item["avg_realized_r"],
            })
        monotonic_pairs = 0
        valid_pairs = 0
        for left, right in zip(buckets, buckets[1:]):
            if int(left["trades"]) <= 0 or int(right["trades"]) <= 0:
                continue
            valid_pairs += 1
            if _as_float(right["avg_realized_r"]) >= _as_float(left["avg_realized_r"]):
                monotonic_pairs += 1
        score = monotonic_pairs / valid_pairs if valid_pairs else None
        status = "INSUFFICIENT_DATA"
        if score is not None:
            status = "PASS" if score >= 0.75 else "MIXED" if score >= 0.5 else "FAILED"
        return {
            "status": status,
            "score": round(score, 4) if score is not None else None,
            "buckets": buckets,
        }

    def get_recommendations_from_rows(self, rows: list[dict[str, Any]], *, min_samples: int) -> dict[str, Any]:
        mode_board = [row for row in self._leaderboard(rows, "mode", min_samples=min_samples) if not row["provisional"]]
        setup_board = [row for row in self._leaderboard(rows, "setup_method", min_samples=min_samples) if not row["provisional"]]
        session_board = [row for row in self._leaderboard(rows, "session_label", min_samples=min_samples) if not row["provisional"]]
        hour_board = [row for row in self._leaderboard(rows, "hour_of_day", min_samples=min_samples) if not row["provisional"]]
        confidence_rows = [row for row in self.get_confidence_bucket_breakdown_from_rows(rows) if int(row["trades"]) >= min_samples]
        weaker_buckets = [row for row in confidence_rows if _as_float(row.get("avg_realized_r")) < 0.0]
        return {
            "scale_up_methods": mode_board[:3] + [row for row in setup_board[:3] if row["label"] not in {item["label"] for item in mode_board[:3]}],
            "reduce_or_pause_methods": list(reversed(mode_board[-3:])) + [row for row in list(reversed(setup_board[-3:])) if row["label"] not in {item["label"] for item in mode_board[-3:]}],
            "strongest_sessions": session_board[:3],
            "weakest_sessions": list(reversed(session_board[-3:])),
            "strongest_hours": hour_board[:3],
            "weakest_hours": list(reversed(hour_board[-3:])),
            "tighten_confidence_buckets": weaker_buckets[:3],
        }

    def _prior_window(self, rows: list[dict[str, Any]], *, lookback_days: int) -> list[dict[str, Any]]:
        if lookback_days <= 0:
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        prior_start = cutoff - timedelta(days=lookback_days)
        prior_rows = []
        for row in rows:
            closed_at = _parse_iso(str(row.get("closed_at_utc") or ""))
            if closed_at and prior_start <= closed_at < cutoff:
                prior_rows.append(row)
        return prior_rows

    def _current_window(self, rows: list[dict[str, Any]], *, lookback_days: int) -> list[dict[str, Any]]:
        if lookback_days <= 0:
            return rows
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        current_rows = []
        for row in rows:
            closed_at = _parse_iso(str(row.get("closed_at_utc") or ""))
            if closed_at and closed_at >= cutoff:
                current_rows.append(row)
        return current_rows

    def get_comparison_from_rows(self, current: list[dict[str, Any]], prior: list[dict[str, Any]], *, min_samples: int) -> dict[str, Any]:
        current_board = {row["label"]: row for row in self._leaderboard(current, "setup_method", min_samples=min_samples) if not row["provisional"]}
        prior_board = {row["label"]: row for row in self._leaderboard(prior, "setup_method", min_samples=min_samples) if not row["provisional"]}
        improving = []
        decaying = []
        worsening = []
        emerging = []
        for label, row in current_board.items():
            previous = prior_board.get(label)
            if previous is None:
                emerging.append(row)
                continue
            delta = _as_float(row.get("avg_realized_r")) - _as_float(previous.get("avg_realized_r"))
            if delta > 0.2:
                improving.append({"label": label, "delta_avg_r": delta, "current": row, "prior": previous})
            elif delta < -0.2 and _as_float(previous.get("avg_realized_r")) > 0 and _as_float(row.get("avg_realized_r")) < 0:
                worsening.append({"label": label, "delta_avg_r": delta, "current": row, "prior": previous})
            elif delta < -0.2:
                decaying.append({"label": label, "delta_avg_r": delta, "current": row, "prior": previous})
        return {
            "improving_methods": sorted(improving, key=lambda item: item["delta_avg_r"], reverse=True)[:5],
            "decaying_methods": sorted(decaying, key=lambda item: item["delta_avg_r"])[:5],
            "worsening_methods": sorted(worsening, key=lambda item: item["delta_avg_r"])[:5],
            "emerging_methods": emerging[:5],
            "edge_decay_warning": bool(worsening),
        }

    def get_audit_analytics_from_rows(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        winners = [row for row in rows if _as_float(row.get("realized_r")) > 0.0 and row.get("audit")]
        losers = [row for row in rows if _as_float(row.get("realized_r")) <= 0.0 and row.get("audit")]
        if not winners and not losers:
            return {"available": False}
        return {
            "available": True,
            "threshold_pass_frequency": {
                "winners": self._threshold_pass_frequency(winners),
                "losers": self._threshold_pass_frequency(losers),
            },
            "factor_score_distributions": {
                "winners": self._factor_score_averages(winners),
                "losers": self._factor_score_averages(losers),
            },
            "learning_adjustments_presence": {
                "winners": self._adjustment_presence(winners),
                "losers": self._adjustment_presence(losers),
            },
            "circuit_breaker_impact": {
                "winners": self._circuit_impact(winners),
                "losers": self._circuit_impact(losers),
            },
        }

    @staticmethod
    def _threshold_pass_frequency(rows: list[dict[str, Any]]) -> dict[str, float]:
        counts: dict[str, int] = defaultdict(int)
        total: dict[str, int] = defaultdict(int)
        for row in rows:
            for item in row.get("audit", {}).get("threshold_checks", []) or []:
                name = str(item.get("name") or "unknown")
                total[name] += 1
                if item.get("passed"):
                    counts[name] += 1
        return {name: counts[name] / total[name] for name in total}

    @staticmethod
    def _factor_score_averages(rows: list[dict[str, Any]]) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        counts: dict[str, int] = defaultdict(int)
        for row in rows:
            for name, value in (row.get("audit", {}).get("factor_scores", {}) or {}).items():
                totals[str(name)] += _as_float(value)
                counts[str(name)] += 1
        return {name: totals[name] / counts[name] for name in counts}

    @staticmethod
    def _adjustment_presence(rows: list[dict[str, Any]]) -> dict[str, float]:
        counts: dict[str, int] = defaultdict(int)
        total = len(rows)
        for row in rows:
            for item in row.get("audit", {}).get("learning_adjustments_applied", []) or []:
                counts[str(item.get("source") or "unknown")] += 1
        return {name: count / total for name, count in counts.items()} if total else {}

    @staticmethod
    def _circuit_impact(rows: list[dict[str, Any]]) -> dict[str, float]:
        counts: dict[str, int] = defaultdict(int)
        total = len(rows)
        for row in rows:
            counts[str(row.get("audit", {}).get("circuit_breaker_state") or "UNKNOWN")] += 1
        return {name: count / total for name, count in counts.items()} if total else {}
