"""Performance snapshot service for v4."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

from runtime.db.repos.order_repo import OrderRepository
from runtime.db.repos.performance_repo import PerformanceRepository
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.db.repos.scan_repo import ScanRepository
from runtime.db.session import session_scope


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class PerformanceService:
    COMPONENT_META: dict[str, tuple[str, str]] = {
        "analysis": ("Analysis", "engine"),
        "analysis_queue_wait": ("Analysis Queue Wait", "runtime"),
        "adapter_total": ("Adapter Total", "engine"),
        "engine_lookup": ("Engine Lookup", "engine"),
        "response_validation": ("Response Validation", "engine"),
        "timeout_lookup": ("Timeout Settings Lookup", "db"),
        "analyzer_status_write": ("Analyzer Status Write", "db"),
        "engine_total": ("Engine Total", "engine"),
        "base_analyzer": ("Base Analyzer", "engine"),
        "self_learning_total": ("Self-Learning Total", "learning"),
        "self_learning_inference": ("Self-Learning Inference", "learning"),
        "self_learning_retrieval": ("Self-Learning Retrieval", "learning"),
        "market_fetch_total": ("Market Fetch Total", "market"),
        "market_fetch_live": ("Market Fetch Live", "market"),
        "market_fetch_cache_load": ("Market Fetch Cache Load", "market"),
        "market_persist": ("Candle Persist", "db"),
        "indicator_build": ("Indicator Build", "market"),
        "htf_resolve": ("HTF Resolve", "engine"),
        "signal_audit": ("Signal Audit", "engine"),
        "signal_persist": ("Signal Persist", "db"),
        "signal_attribution": ("Signal Attribution", "engine"),
        "execution": ("Order Execution", "execution"),
    }

    def __init__(
        self,
        order_repo: OrderRepository | None = None,
        performance_repo: PerformanceRepository | None = None,
        scan_repo: ScanRepository | None = None,
    ) -> None:
        self.order_repo = order_repo or OrderRepository()
        self.performance_repo = performance_repo or PerformanceRepository()
        self.scan_repo = scan_repo or ScanRepository()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def build_snapshot(self, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any]:
        with session_scope() as session:
            all_closed = [
                self._hydrate_order(session, row)
                for row in self.order_repo.list_orders(session, limit=5000, profile_id=profile_id)
                if str(row.get("status") or "").upper() != "OPEN"
            ]
            open_orders = [
                row for row in self.order_repo.list_orders(session, status="OPEN", limit=5000, profile_id=profile_id)
            ]
            open_positions = self.order_repo.list_positions(session, status="OPEN", limit=1000, profile_id=profile_id)
        summary = self._aggregate_subset(all_closed)
        breakdown = {
            "symbol": self._group_by(all_closed, "symbol"),
            "interval": self._group_by(all_closed, "interval"),
            "regime": self._group_by(all_closed, "regime"),
            "mode": self._group_by(all_closed, "mode"),
            "source": self._group_by(all_closed, "source"),
        }
        portfolio_summary = {
            "success_pct": round(summary["win_rate"], 2),
            "total_orders": len(open_orders) + len(all_closed),
            "open_orders": len(open_orders),
            "wins": summary["wins"],
            "losses": summary["losses"],
        }
        return {
            "profile_id": profile_id,
            "summary": summary,
            "breakdown": breakdown,
            "portfolio": portfolio_summary,
            "open_trades": len(open_orders),
            "closed_trades": len(all_closed),
            "recent_closed": all_closed[:12],
            "open_positions": open_positions,
        }

    def store_snapshot(self, source_event: str, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any]:
        snapshot = self.build_snapshot(profile_id=profile_id)
        summary = snapshot["summary"]
        portfolio = snapshot["portfolio"]
        with session_scope() as session:
            latest = self.performance_repo.get_latest_snapshot(session, profile_id=profile_id)
            comparable = {
                "total_trades": summary["total_trades"],
                "wins": summary["wins"],
                "losses": summary["losses"],
                "win_rate": round(summary["win_rate"], 2),
                "profit_factor": round(summary["profit_factor"], 4),
                "net_r": round(summary["net_r"], 4),
                "open_orders": snapshot["open_trades"],
                "closed_trades": snapshot["closed_trades"],
            }
            if latest and {
                "total_trades": latest["total_trades"],
                "wins": latest["wins"],
                "losses": latest["losses"],
                "win_rate": round(_as_float(latest["win_rate"]), 2),
                "profit_factor": round(_as_float(latest["profit_factor"]), 4),
                "net_r": round(_as_float(latest["net_r"]), 4),
                "open_orders": latest["open_orders"],
                "closed_trades": latest["closed_trades"],
            } == comparable:
                return latest
            return self.performance_repo.save_snapshot(
                session,
                {
                    "profile_id": profile_id,
                    "timestamp_utc": self._utc_now_iso(),
                    "source_event": source_event,
                    "total_trades": summary["total_trades"],
                    "wins": summary["wins"],
                    "losses": summary["losses"],
                    "win_rate": summary["win_rate"],
                    "profit_factor": summary["profit_factor"],
                    "net_r": summary["net_r"],
                    "open_orders": snapshot["open_trades"],
                    "closed_trades": snapshot["closed_trades"],
                    "summary_json": json.dumps(summary),
                    "portfolio_json": json.dumps(portfolio),
                },
            )

    def get_snapshot(self, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any]:
        return self.build_snapshot(profile_id=profile_id)

    def get_history(self, *, limit: int = 120, profile_id: str = PAPER_PROFILE_ID) -> list[dict[str, Any]]:
        with session_scope() as session:
            return self.performance_repo.list_snapshots(session, limit=limit, profile_id=profile_id)

    def get_analytics(self, *, limit: int = 250, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any]:
        with session_scope() as session:
            runs = self.scan_repo.list_runs(session, limit=limit, profile_id=profile_id)

        scan_durations_ms: list[float] = []
        analysis_duration_samples: list[float] = []
        market_fetch_duration_samples: list[float] = []
        analysis_count = 0
        analysis_total_ms = 0.0
        analysis_min_ms: float | None = None
        analysis_max_ms: float | None = None
        market_fetch_count = 0
        market_fetch_total_ms = 0.0
        market_fetch_min_ms: float | None = None
        market_fetch_max_ms: float | None = None
        status_counts: dict[str, int] = {}
        recent_scans: list[dict[str, Any]] = []
        component_rows: list[dict[str, Any]] = []
        analysis_worker_capacities: list[float] = []
        fetch_worker_capacities: list[float] = []
        max_concurrent_fetches: list[float] = []
        avg_concurrent_fetches: list[float] = []

        for run in runs:
            status = str(run.get("status") or "UNKNOWN").upper()
            status_counts[status] = status_counts.get(status, 0) + 1
            started_at = self._parse_time(run.get("started_at_utc") or run.get("created_at_utc"))
            finished_at = self._parse_time(run.get("finished_at_utc"))
            duration_ms = None
            if started_at and finished_at:
                duration_ms = round(max(0.0, (finished_at - started_at).total_seconds() * 1000.0), 4)
                scan_durations_ms.append(duration_ms)

            result = dict(run.get("result") or {})
            analysis = dict((result.get("timing") or {}).get("analysis") or {})
            analysis_item_count = int(analysis.get("count") or 0)
            analysis_avg_ms = analysis.get("avg_ms")
            analysis_min = analysis.get("min_ms")
            analysis_max = analysis.get("max_ms")
            if analysis_avg_ms is not None:
                analysis_duration_samples.append(float(analysis_avg_ms))
            market_fetch = dict((result.get("timing") or {}).get("market_fetch") or {})
            market_fetch_item_count = int(market_fetch.get("count") or 0)
            market_fetch_avg_ms = market_fetch.get("avg_ms")
            market_fetch_min = market_fetch.get("min_ms")
            market_fetch_max = market_fetch.get("max_ms")
            if market_fetch_avg_ms is not None:
                market_fetch_duration_samples.append(float(market_fetch_avg_ms))
            if analysis_item_count > 0 and analysis_avg_ms is not None:
                analysis_count += analysis_item_count
                analysis_total_ms += float(analysis_avg_ms) * analysis_item_count
                if analysis_min is not None:
                    analysis_min_ms = float(analysis_min) if analysis_min_ms is None else min(analysis_min_ms, float(analysis_min))
                if analysis_max is not None:
                    analysis_max_ms = float(analysis_max) if analysis_max_ms is None else max(analysis_max_ms, float(analysis_max))
            if market_fetch_item_count > 0 and market_fetch_avg_ms is not None:
                market_fetch_count += market_fetch_item_count
                market_fetch_total_ms += float(market_fetch_avg_ms) * market_fetch_item_count
                if market_fetch_min is not None:
                    market_fetch_min_ms = float(market_fetch_min) if market_fetch_min_ms is None else min(market_fetch_min_ms, float(market_fetch_min))
                if market_fetch_max is not None:
                    market_fetch_max_ms = float(market_fetch_max) if market_fetch_max_ms is None else max(market_fetch_max_ms, float(market_fetch_max))

            timing = dict(result.get("timing") or {})
            stages = dict(timing.get("stages") or {})
            progress = dict(result.get("progress") or {})
            scope = dict(result.get("scope") or {})
            debug = dict(result.get("debug") or {})
            component_breakdown = self._component_breakdown_from_stages(stages)
            component_rows.extend(component_breakdown)
            top_components = sorted(
                component_breakdown,
                key=lambda item: float(item.get("total_ms") or 0.0),
                reverse=True,
            )[:10]
            db_summary = self._db_summary_from_stages(stages)
            cache_summary = self._cache_summary_from_stages(stages)
            concurrency = self._concurrency_summary_from_stages(stages, progress, payload=run.get("payload") or {})
            if concurrency.get("analysis_worker_capacity") is not None:
                analysis_worker_capacities.append(float(concurrency["analysis_worker_capacity"]))
            if concurrency.get("fetch_worker_capacity") is not None:
                fetch_worker_capacities.append(float(concurrency["fetch_worker_capacity"]))
            if concurrency.get("max_concurrent_fetches") is not None:
                max_concurrent_fetches.append(float(concurrency["max_concurrent_fetches"]))
            if concurrency.get("avg_concurrent_fetches") is not None:
                avg_concurrent_fetches.append(float(concurrency["avg_concurrent_fetches"]))
            composition = self._composition_from_scan(duration_ms, stages)
            progress = dict(result.get("progress") or {})
            recent_scans.append(
                {
                    "run_id": run.get("run_id"),
                    "status": status,
                    "requested_by": run.get("requested_by"),
                    "duration_ms": duration_ms,
                    "analysis_avg_ms": float(analysis_avg_ms) if analysis_avg_ms is not None else None,
                    "analysis_min_ms": float(analysis_min) if analysis_min is not None else None,
                    "analysis_max_ms": float(analysis_max) if analysis_max is not None else None,
                    "analysis_count": analysis_item_count,
                    "market_fetch_avg_ms": float(market_fetch_avg_ms) if market_fetch_avg_ms is not None else None,
                    "market_fetch_min_ms": float(market_fetch_min) if market_fetch_min is not None else None,
                    "market_fetch_max_ms": float(market_fetch_max) if market_fetch_max is not None else None,
                    "market_fetch_count": market_fetch_item_count,
                    "completed_tasks": int(progress.get("completed_tasks") or 0),
                    "total_tasks": int(progress.get("total_tasks") or 0),
                    "created_orders": int(result.get("created_orders") or 0),
                    "started_at_utc": run.get("started_at_utc"),
                    "finished_at_utc": run.get("finished_at_utc"),
                    "composition": composition,
                    "component_breakdown": component_breakdown,
                    "top_components": top_components,
                    "db": db_summary,
                    "caches": cache_summary,
                    "concurrency": concurrency,
                    "scope": scope,
                    "debug": debug,
                    "stages": stages,
                }
            )

        aggregated_components = self._aggregate_component_rows(component_rows)
        slow_components = sorted(aggregated_components, key=lambda item: float(item.get("total_ms") or 0.0), reverse=True)[:10]
        db_aggregate = self._aggregate_db_from_scans(recent_scans)
        cache_aggregate = self._aggregate_caches_from_scans(recent_scans)
        concurrency_aggregate = {
            "analysis_worker_capacity": round(sum(analysis_worker_capacities) / len(analysis_worker_capacities), 4) if analysis_worker_capacities else None,
            "fetch_worker_capacity": round(sum(fetch_worker_capacities) / len(fetch_worker_capacities), 4) if fetch_worker_capacities else None,
            "max_concurrent_fetches": max(max_concurrent_fetches) if max_concurrent_fetches else None,
            "avg_concurrent_fetches": round(sum(avg_concurrent_fetches) / len(avg_concurrent_fetches), 4) if avg_concurrent_fetches else None,
            "analysis_serialized": (round(sum(analysis_worker_capacities) / len(analysis_worker_capacities), 4) if analysis_worker_capacities else 1) <= 1,
            "queue_wait_avg_ms": None,
            "db_connection_wait_avg_ms": None,
        }

        return {
            "profile_id": profile_id,
            "scan_runs": self._timing_summary(scan_durations_ms),
            "analysis": {
                "count": analysis_count,
                "avg_ms": round((analysis_total_ms / analysis_count), 4) if analysis_count else None,
                "min_ms": round(analysis_min_ms, 4) if analysis_min_ms is not None else None,
                "max_ms": round(analysis_max_ms, 4) if analysis_max_ms is not None else None,
                "p50_ms": round(self._percentile(analysis_duration_samples, 50), 4) if analysis_duration_samples else None,
                "p95_ms": round(self._percentile(analysis_duration_samples, 95), 4) if analysis_duration_samples else None,
                "p99_ms": round(self._percentile(analysis_duration_samples, 99), 4) if analysis_duration_samples else None,
                "total_ms": round(analysis_total_ms, 4) if analysis_count else None,
            },
            "market_fetch": {
                "count": market_fetch_count,
                "avg_ms": round((market_fetch_total_ms / market_fetch_count), 4) if market_fetch_count else None,
                "min_ms": round(market_fetch_min_ms, 4) if market_fetch_min_ms is not None else None,
                "max_ms": round(market_fetch_max_ms, 4) if market_fetch_max_ms is not None else None,
                "p50_ms": round(self._percentile(market_fetch_duration_samples, 50), 4) if market_fetch_duration_samples else None,
                "p95_ms": round(self._percentile(market_fetch_duration_samples, 95), 4) if market_fetch_duration_samples else None,
                "p99_ms": round(self._percentile(market_fetch_duration_samples, 99), 4) if market_fetch_duration_samples else None,
                "total_ms": round(market_fetch_total_ms, 4) if market_fetch_count else None,
            },
            "status_counts": status_counts,
            "recent_scans": recent_scans[:25],
            "component_breakdown": aggregated_components,
            "slow_components": slow_components,
            "db": db_aggregate,
            "caches": cache_aggregate,
            "concurrency": concurrency_aggregate,
        }

    @staticmethod
    def _aggregate_subset(rows: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(rows)
        wins = sum(1 for row in rows if _as_float(row.get("realized_r")) > 0)
        losses = total - wins
        gross_wins = sum(_as_float(row.get("realized_r")) for row in rows if _as_float(row.get("realized_r")) > 0)
        gross_losses = abs(sum(_as_float(row.get("realized_r")) for row in rows if _as_float(row.get("realized_r")) < 0))
        net_r = sum(_as_float(row.get("realized_r")) for row in rows)
        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": round((wins / total * 100.0) if total else 0.0, 2),
            "profit_factor": round((gross_wins / gross_losses) if gross_losses else (gross_wins if gross_wins else 0.0), 4),
            "net_r": round(net_r, 4),
        }

    def _group_by(self, rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            key = str(row.get(field) or "UNKNOWN")
            grouped.setdefault(key, []).append(row)
        return {key: self._aggregate_subset(value) for key, value in grouped.items()}

    def _hydrate_order(self, session, order: dict[str, Any]) -> dict[str, Any]:
        payload = dict(order.get("payload") or {})
        fills = self.order_repo.list_fills(session, order["order_id"], limit=100)
        signal_payload = dict(payload.get("signal") or {})
        return {
            **order,
            "fills": fills,
            "realized_pnl": payload.get("realized_pnl"),
            "realized_r": payload.get("realized_r"),
            "close_reason": payload.get("close_reason"),
            "regime": signal_payload.get("regime"),
            "summary": signal_payload.get("summary"),
        }

    @staticmethod
    def _parse_time(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _timing_summary(values: list[float]) -> dict[str, float | int | None]:
        if not values:
            return {
                "count": 0,
                "avg_ms": None,
                "min_ms": None,
                "max_ms": None,
                "p50_ms": None,
                "p95_ms": None,
                "p99_ms": None,
                "total_ms": None,
            }
        sorted_values = sorted(float(item) for item in values)
        return {
            "count": len(values),
            "avg_ms": round(sum(values) / len(values), 4),
            "min_ms": round(min(values), 4),
            "max_ms": round(max(values), 4),
            "p50_ms": round(PerformanceService._percentile(sorted_values, 50), 4),
            "p95_ms": round(PerformanceService._percentile(sorted_values, 95), 4),
            "p99_ms": round(PerformanceService._percentile(sorted_values, 99), 4),
            "total_ms": round(sum(values), 4),
        }

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float:
        if not values:
            return 0.0
        sorted_values = sorted(float(item) for item in values)
        if len(sorted_values) == 1:
            return float(sorted_values[0])
        rank = (len(sorted_values) - 1) * (percentile / 100.0)
        lower = int(math.floor(rank))
        upper = int(math.ceil(rank))
        if lower == upper:
            return float(sorted_values[lower])
        weight = rank - lower
        return float(sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * weight)

    def _component_breakdown_from_stages(self, stages: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for key, value in stages.items():
            if not isinstance(value, dict) or "count" not in value:
                continue
            label, group = self.COMPONENT_META.get(key, (key.replace("_", " ").title(), "runtime"))
            rows.append({
                "component_id": key,
                "label": label,
                "group": group,
                "count": int(value.get("count") or 0),
                "avg_ms": _as_float(value.get("avg_ms"), 0.0) if value.get("avg_ms") is not None else None,
                "min_ms": _as_float(value.get("min_ms"), 0.0) if value.get("min_ms") is not None else None,
                "max_ms": _as_float(value.get("max_ms"), 0.0) if value.get("max_ms") is not None else None,
                "p50_ms": _as_float(value.get("p50_ms"), 0.0) if value.get("p50_ms") is not None else None,
                "p95_ms": _as_float(value.get("p95_ms"), 0.0) if value.get("p95_ms") is not None else None,
                "p99_ms": _as_float(value.get("p99_ms"), 0.0) if value.get("p99_ms") is not None else None,
                "total_ms": _as_float(value.get("total_ms"), 0.0) if value.get("total_ms") is not None else None,
            })
        return rows

    def _aggregate_component_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        aggregates: dict[str, dict[str, Any]] = {}
        percentile_samples: dict[str, list[float]] = {}
        for row in rows:
            key = str(row.get("component_id") or "")
            if not key:
                continue
            aggregate = aggregates.setdefault(key, {
                "component_id": key,
                "label": row.get("label"),
                "group": row.get("group"),
                "count": 0,
                "total_ms": 0.0,
                "min_ms": None,
                "max_ms": None,
            })
            count = int(row.get("count") or 0)
            total_ms = _as_float(row.get("total_ms"), 0.0)
            aggregate["count"] += count
            aggregate["total_ms"] += total_ms
            if row.get("min_ms") is not None:
                aggregate["min_ms"] = row["min_ms"] if aggregate["min_ms"] is None else min(float(aggregate["min_ms"]), float(row["min_ms"]))
            if row.get("max_ms") is not None:
                aggregate["max_ms"] = row["max_ms"] if aggregate["max_ms"] is None else max(float(aggregate["max_ms"]), float(row["max_ms"]))
            avg_ms = row.get("avg_ms")
            if avg_ms is not None:
                percentile_samples.setdefault(key, []).append(float(avg_ms))
        output: list[dict[str, Any]] = []
        for key, aggregate in aggregates.items():
            samples = percentile_samples.get(key) or []
            count = int(aggregate["count"] or 0)
            total_ms = float(aggregate["total_ms"] or 0.0)
            output.append({
                **aggregate,
                "avg_ms": round(total_ms / count, 4) if count else None,
                "p50_ms": round(self._percentile(samples, 50), 4) if samples else None,
                "p95_ms": round(self._percentile(samples, 95), 4) if samples else None,
                "p99_ms": round(self._percentile(samples, 99), 4) if samples else None,
                "total_ms": round(total_ms, 4),
            })
        return sorted(output, key=lambda item: float(item.get("total_ms") or 0.0), reverse=True)

    def _db_summary_from_stages(self, stages: dict[str, Any]) -> dict[str, Any]:
        families = {
            "runtime_settings_lookup": self._family_from_stage("timeout_lookup", stages),
            "analyzer_status_write": self._family_from_stage("analyzer_status_write", stages),
            "candle_persist": self._family_from_stage("market_persist", stages),
            "signal_persist": self._family_from_stage("signal_persist", stages),
        }
        write_count = int(stages.get("rows_written") or 0)
        return {
            "query_count": sum(int((families[key].get("count") or 0)) for key in families),
            "write_count": write_count,
            "rows_written": write_count,
            "commit_count": None,
            "rollback_count": None,
            "connection_wait_avg_ms": None,
            "total_read_ms": round(sum(_as_float(families[key].get("total_ms")) for key in ("runtime_settings_lookup",)), 4),
            "total_write_ms": round(sum(_as_float(families[key].get("total_ms")) for key in ("analyzer_status_write", "candle_persist", "signal_persist")), 4),
            "families": families,
        }

    @staticmethod
    def _family_from_stage(stage_name: str, stages: dict[str, Any]) -> dict[str, Any]:
        stage = dict(stages.get(stage_name) or {})
        if "count" not in stage:
            return {"count": 0, "avg_ms": None, "p95_ms": None, "total_ms": None}
        return {
            "count": int(stage.get("count") or 0),
            "avg_ms": stage.get("avg_ms"),
            "p95_ms": stage.get("p95_ms"),
            "total_ms": stage.get("total_ms"),
        }

    @staticmethod
    def _cache_summary_from_stages(stages: dict[str, Any]) -> dict[str, Any]:
        return {
            "market_bundle": {
                "requests": int(stages.get("market_bundle_requests") or 0),
                "hits": int(stages.get("market_bundle_cache_hits") or 0),
                "misses": max(0, int(stages.get("market_bundle_unique_fetches") or 0)),
                "hit_rate_pct": stages.get("market_bundle_cache_hit_rate"),
            },
            "htf_trend": {
                "requests": int(stages.get("htf_trend_requests") or 0),
                "hits": int(stages.get("htf_trend_cache_hits") or 0),
                "misses": max(0, int(stages.get("htf_trend_unique_resolutions") or 0)),
                "hit_rate_pct": stages.get("htf_trend_cache_hit_rate"),
            },
            "self_learning": {
                "active_tasks": int(stages.get("self_learning_active_tasks") or 0),
                "bypassed_tasks": int(stages.get("self_learning_bypassed_tasks") or 0),
            },
        }

    @staticmethod
    def _concurrency_summary_from_stages(stages: dict[str, Any], progress: dict[str, Any], *, payload: dict[str, Any]) -> dict[str, Any]:
        analysis_capacity = int(stages.get("analysis_worker_capacity") or 1)
        return {
            "scan_workers": int((payload or {}).get("scan_workers") or stages.get("fetch_worker_capacity") or 0),
            "fetch_worker_capacity": int(stages.get("fetch_worker_capacity") or 0),
            "analysis_worker_capacity": analysis_capacity,
            "max_concurrent_fetches": int(stages.get("max_concurrent_fetches") or 0),
            "avg_concurrent_fetches": stages.get("avg_concurrent_fetches"),
            "queue_wait_avg_ms": None,
            "db_connection_wait_avg_ms": None,
            "completed_tasks": int(progress.get("completed_tasks") or 0),
            "remaining_tasks": int(progress.get("remaining_tasks") or 0),
            "analysis_serialized": analysis_capacity <= 1,
        }

    @staticmethod
    def _composition_from_scan(duration_ms: float | None, stages: dict[str, Any]) -> dict[str, Any]:
        fetch_ms = _as_float(dict(stages.get("market_fetch_total") or {}).get("total_ms"))
        analysis_ms = _as_float(dict(stages.get("analysis") or {}).get("total_ms"))
        audit_ms = _as_float(dict(stages.get("signal_audit") or {}).get("total_ms"))
        db_write_ms = _as_float(dict(stages.get("market_persist") or {}).get("total_ms")) + _as_float(dict(stages.get("signal_persist") or {}).get("total_ms")) + _as_float(dict(stages.get("analyzer_status_write") or {}).get("total_ms"))
        attribution_ms = _as_float(dict(stages.get("signal_attribution") or {}).get("total_ms"))
        execution_ms = _as_float(dict(stages.get("execution") or {}).get("total_ms"))
        learning_ms = _as_float(dict(stages.get("self_learning_total") or {}).get("total_ms"))
        htf_ms = _as_float(dict(stages.get("htf_resolve") or {}).get("total_ms"))
        known = fetch_ms + analysis_ms + audit_ms + db_write_ms + attribution_ms + execution_ms + learning_ms + htf_ms
        uncovered = max(0.0, _as_float(duration_ms) - known) if duration_ms is not None else None
        return {
            "fetch_ms": round(fetch_ms, 4),
            "analysis_ms": round(analysis_ms, 4),
            "audit_ms": round(audit_ms, 4),
            "db_write_ms": round(db_write_ms, 4),
            "attribution_ms": round(attribution_ms, 4),
            "execution_ms": round(execution_ms, 4),
            "learning_ms": round(learning_ms, 4),
            "htf_ms": round(htf_ms, 4),
            "uncovered_ms": round(uncovered, 4) if uncovered is not None else None,
        }

    def _aggregate_db_from_scans(self, scans: list[dict[str, Any]]) -> dict[str, Any]:
        families: dict[str, list[dict[str, Any]]] = {}
        total_query_count = 0
        total_write_count = 0
        total_rows_written = 0
        total_read_ms = 0.0
        total_write_ms = 0.0
        for scan in scans:
            db = dict(scan.get("db") or {})
            total_query_count += int(db.get("query_count") or 0)
            total_write_count += int(db.get("write_count") or 0)
            total_rows_written += int(db.get("rows_written") or 0)
            total_read_ms += _as_float(db.get("total_read_ms"))
            total_write_ms += _as_float(db.get("total_write_ms"))
            for key, value in dict(db.get("families") or {}).items():
                families.setdefault(key, []).append(dict(value or {}))
        return {
            "query_count": total_query_count,
            "write_count": total_write_count,
            "rows_written": total_rows_written,
            "commit_count": None,
            "rollback_count": None,
            "connection_wait_avg_ms": None,
            "total_read_ms": round(total_read_ms, 4),
            "total_write_ms": round(total_write_ms, 4),
            "families": {
                key: {
                    "count": sum(int(item.get("count") or 0) for item in items),
                    "avg_ms": round(sum(_as_float(item.get("avg_ms")) for item in items) / len(items), 4) if items else None,
                    "p95_ms": round(self._percentile([_as_float(item.get("p95_ms")) for item in items if item.get("p95_ms") is not None], 95), 4) if any(item.get("p95_ms") is not None for item in items) else None,
                    "total_ms": round(sum(_as_float(item.get("total_ms")) for item in items), 4),
                }
                for key, items in families.items()
            },
        }

    @staticmethod
    def _aggregate_caches_from_scans(scans: list[dict[str, Any]]) -> dict[str, Any]:
        market_requests = sum(int((((scan.get("caches") or {}).get("market_bundle") or {})).get("requests") or 0) for scan in scans)
        market_hits = sum(int((((scan.get("caches") or {}).get("market_bundle") or {})).get("hits") or 0) for scan in scans)
        htf_requests = sum(int((((scan.get("caches") or {}).get("htf_trend") or {})).get("requests") or 0) for scan in scans)
        htf_hits = sum(int((((scan.get("caches") or {}).get("htf_trend") or {})).get("hits") or 0) for scan in scans)
        learning_active = sum(int((((scan.get("caches") or {}).get("self_learning") or {})).get("active_tasks") or 0) for scan in scans)
        learning_bypassed = sum(int((((scan.get("caches") or {}).get("self_learning") or {})).get("bypassed_tasks") or 0) for scan in scans)
        return {
            "market_bundle": {
                "requests": market_requests,
                "hits": market_hits,
                "misses": max(0, market_requests - market_hits),
                "hit_rate_pct": round((market_hits / market_requests) * 100.0, 2) if market_requests else None,
            },
            "htf_trend": {
                "requests": htf_requests,
                "hits": htf_hits,
                "misses": max(0, htf_requests - htf_hits),
                "hit_rate_pct": round((htf_hits / htf_requests) * 100.0, 2) if htf_requests else None,
            },
            "self_learning": {
                "active_tasks": learning_active,
                "bypassed_tasks": learning_bypassed,
            },
        }
