"""Tests for runtime/services/performance_service.py.

Pure functions: _aggregate_subset, _group_by, _parse_time, _timing_summary,
_percentile, _composition_from_scan, _family_from_stage, _db_summary_from_stages,
_cache_summary_from_stages, _concurrency_summary_from_stages,
_component_breakdown_from_stages, _aggregate_component_rows.

DB-backed: build_snapshot, store_snapshot, get_analytics (mocked repos).
"""

import math
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

from runtime.services.performance_service import PerformanceService


def svc() -> PerformanceService:
    return PerformanceService(
        order_repo=MagicMock(),
        performance_repo=MagicMock(),
        scan_repo=MagicMock(),
    )


def _order(realized_r: float = 0.0, **kwargs) -> dict[str, Any]:
    base = {
        "symbol": "BTCUSDT",
        "interval": "4h",
        "mode": "SWING",
        "direction": "LONG",
        "regime": "TRENDING",
        "source": "auto",
        "realized_r": realized_r,
    }
    base.update(kwargs)
    return base


# ── _aggregate_subset ───────────────────────────────────────────────

class TestAggregateSubset:
    def test_empty(self):
        result = PerformanceService._aggregate_subset([])
        assert result["total_trades"] == 0
        assert result["win_rate"] == 0.0
        assert result["net_r"] == 0.0

    def test_all_wins(self):
        result = PerformanceService._aggregate_subset([_order(1.0), _order(2.0)])
        assert result["wins"] == 2
        assert result["win_rate"] == 100.0
        assert result["net_r"] == 3.0

    def test_all_losses(self):
        result = PerformanceService._aggregate_subset([_order(-1.0), _order(-2.0)])
        assert result["losses"] == 2
        assert result["win_rate"] == 0.0
        assert result["net_r"] == -3.0

    def test_mixed(self):
        result = PerformanceService._aggregate_subset([_order(1.0), _order(-0.5), _order(0.5)])
        assert result["wins"] == 2
        assert result["losses"] == 1
        assert result["win_rate"] == 66.67
        assert result["net_r"] == 1.0
        assert result["profit_factor"] == 1.5 / 0.5

    def test_profit_factor_no_losses(self):
        result = PerformanceService._aggregate_subset([_order(1.0)])
        assert result["profit_factor"] == 1.0  # gross_wins only

    def test_profit_factor_all_losses(self):
        result = PerformanceService._aggregate_subset([_order(-1.0)])
        assert result["profit_factor"] == 0.0  # no gross_wins

    def test_zero_realized_r_neutral(self):
        """Zero R is neither win nor loss for gross calc, but contributes to net."""
        result = PerformanceService._aggregate_subset([_order(0.0)])
        assert result["wins"] == 0
        assert result["losses"] == 1  # total - wins
        assert result["net_r"] == 0.0


# ── _group_by ───────────────────────────────────────────────────────

class TestGroupBy:
    def test_groups_by_field(self):
        rows = [
            _order(1.0, mode="SWING"),
            _order(-0.5, mode="SWING"),
            _order(2.0, mode="SCALP"),
        ]
        result = PerformanceService()._group_by(rows, "mode")
        assert set(result.keys()) == {"SWING", "SCALP"}
        assert result["SWING"]["total_trades"] == 2
        assert result["SWING"]["net_r"] == 0.5
        assert result["SCALP"]["total_trades"] == 1

    def test_unknown_key(self):
        rows = [_order(1.0, mode="")]
        result = PerformanceService()._group_by(rows, "mode")
        assert "UNKNOWN" in result

    def test_empty(self):
        assert PerformanceService()._group_by([], "mode") == {}


# ── _percentile ─────────────────────────────────────────────────────

class TestPercentile:
    def test_empty(self):
        assert PerformanceService._percentile([], 50) == 0.0

    def test_single_value(self):
        assert PerformanceService._percentile([5.0], 50) == 5.0
        assert PerformanceService._percentile([5.0], 99) == 5.0

    def test_median_odd(self):
        assert PerformanceService._percentile([1.0, 2.0, 3.0], 50) == 2.0

    def test_median_even(self):
        result = PerformanceService._percentile([1.0, 2.0, 3.0, 4.0], 50)
        assert result == 2.5  # (2+3)/2

    def test_p50_same_as_median(self):
        values = [0.1, 0.2, 0.5, 1.0, 3.0, 5.0, 10.0]
        p50 = PerformanceService._percentile(values, 50)
        assert p50 == 1.0

    def test_p95(self):
        values = list(range(1, 101))
        p95 = PerformanceService._percentile(values, 95)
        assert 94.0 <= p95 <= 96.0  # 95th percentile ≈ 95

    def test_p99(self):
        values = list(range(1, 101))
        p99 = PerformanceService._percentile(values, 99)
        assert 98.0 <= p99 <= 100.0

    def test_interpolation(self):
        values = [1.0, 2.0, 3.0, 4.0]
        # rank = (4-1)*50/100 = 1.5, lower=1, upper=2, weight=0.5
        # = values[1] + (values[2]-values[1])*0.5 = 2 + 1*0.5 = 2.5
        assert PerformanceService._percentile(values, 50) == 2.5

    def test_unsorted_input(self):
        values = [10.0, 1.0, 5.0, 3.0]
        p50 = PerformanceService._percentile(values, 50)
        # sorted: [1, 3, 5, 10], rank=1.5, = 3 + (5-3)*0.5 = 4
        assert p50 == 4.0


# ── _timing_summary ─────────────────────────────────────────────────

class TestTimingSummary:
    def test_empty(self):
        result = PerformanceService._timing_summary([])
        assert result["count"] == 0
        assert result["avg_ms"] is None

    def test_single(self):
        result = PerformanceService._timing_summary([100.0])
        assert result["count"] == 1
        assert result["avg_ms"] == 100.0
        assert result["min_ms"] == 100.0
        assert result["max_ms"] == 100.0
        assert result["p50_ms"] == 100.0

    def test_multiple(self):
        result = PerformanceService._timing_summary([10.0, 20.0, 30.0, 40.0, 50.0])
        assert result["count"] == 5
        assert result["avg_ms"] == 30.0
        assert result["min_ms"] == 10.0
        assert result["max_ms"] == 50.0
        assert result["total_ms"] == 150.0
        # p50 of sorted [10,20,30,40,50]: rank=(5-1)*50/100=2, values[2]=30
        assert result["p50_ms"] == 30.0


# ── _parse_time ─────────────────────────────────────────────────────

class TestParseTime:
    def test_none(self):
        assert PerformanceService._parse_time(None) is None

    def test_empty(self):
        assert PerformanceService._parse_time("") is None

    def test_valid_iso(self):
        result = PerformanceService._parse_time("2026-06-01T12:00:00+00:00")
        assert result is not None
        assert result.hour == 12

    def test_z_suffix(self):
        result = PerformanceService._parse_time("2026-06-01T12:00:00Z")
        assert result is not None

    def test_invalid(self):
        assert PerformanceService._parse_time("garbage") is None


# ── _composition_from_scan ──────────────────────────────────────────

class TestCompositionFromScan:
    def test_empty_stages(self):
        result = PerformanceService._composition_from_scan(100.0, {})
        assert result["fetch_ms"] == 0.0
        assert result["analysis_ms"] == 0.0
        assert result["uncovered_ms"] == 100.0

    def test_with_stages(self):
        stages = {
            "market_fetch_total": {"total_ms": 30.0},
            "analysis": {"total_ms": 40.0},
            "signal_audit": {"total_ms": 5.0},
            "market_persist": {"total_ms": 3.0},
            "signal_persist": {"total_ms": 2.0},
            "analyzer_status_write": {"total_ms": 1.0},
            "signal_attribution": {"total_ms": 2.0},
            "execution": {"total_ms": 1.0},
            "self_learning_total": {"total_ms": 4.0},
            "htf_resolve": {"total_ms": 2.0},
        }
        result = PerformanceService._composition_from_scan(100.0, stages)
        assert result["fetch_ms"] == 30.0
        assert result["analysis_ms"] == 40.0
        # known = 30+40+5+(3+2+1)+2+1+4+2 = 90
        assert result["uncovered_ms"] == 10.0

    def test_no_duration(self):
        result = PerformanceService._composition_from_scan(None, {})
        assert result["uncovered_ms"] is None


# ── _component_breakdown_from_stages ────────────────────────────────

class TestComponentBreakdown:
    def test_empty_stages(self):
        assert PerformanceService()._component_breakdown_from_stages({}) == []

    def test_known_component(self):
        stages = {
            "analysis": {"count": 10, "avg_ms": 5.0, "total_ms": 50.0},
        }
        result = PerformanceService()._component_breakdown_from_stages(stages)
        assert len(result) == 1
        assert result[0]["component_id"] == "analysis"
        assert result[0]["label"] == "Analysis"
        assert result[0]["group"] == "engine"
        assert result[0]["count"] == 10
        assert result[0]["total_ms"] == 50.0

    def test_unknown_component(self):
        stages = {"custom_stage": {"count": 1, "total_ms": 5.0}}
        result = PerformanceService()._component_breakdown_from_stages(stages)
        assert result[0]["label"] == "Custom Stage"  # derived from key
        assert result[0]["group"] == "runtime"  # default group

    def test_non_dict_value_skipped(self):
        stages = {"analysis": "not a dict"}
        assert PerformanceService()._component_breakdown_from_stages(stages) == []

    def test_missing_count_skipped(self):
        stages = {"analysis": {"avg_ms": 5.0}}  # no "count" key
        assert PerformanceService()._component_breakdown_from_stages(stages) == []


# ── _family_from_stage / _db_summary_from_stages ────────────────────

class TestDbSummary:
    def test_family_from_stage_empty(self):
        result = PerformanceService._family_from_stage("timeout_lookup", {})
        assert result["count"] == 0

    def test_family_from_stage_with_data(self):
        stages = {"timeout_lookup": {"count": 5, "avg_ms": 2.0, "total_ms": 10.0}}
        result = PerformanceService._family_from_stage("timeout_lookup", stages)
        assert result["count"] == 5
        assert result["avg_ms"] == 2.0

    def test_db_summary_empty(self):
        result = PerformanceService()._db_summary_from_stages({})
        assert result["query_count"] == 0
        assert result["write_count"] == 0

    def test_db_summary_with_data(self):
        stages = {
            "timeout_lookup": {"count": 3, "total_ms": 6.0},
            "analyzer_status_write": {"count": 1, "total_ms": 2.0},
            "rows_written": 10,
        }
        result = PerformanceService()._db_summary_from_stages(stages)
        # query_count sums over all 4 families (some may be 0)
        assert result["query_count"] >= 3
        assert result["write_count"] == 10
        assert result["total_read_ms"] >= 6.0
        assert result["total_write_ms"] >= 2.0


# ── _cache_summary_from_stages ──────────────────────────────────────

class TestCacheSummary:
    def test_empty(self):
        result = PerformanceService._cache_summary_from_stages({})
        assert result["market_bundle"]["requests"] == 0
        assert result["htf_trend"]["hits"] == 0
        assert result["self_learning"]["active_tasks"] == 0

    def test_with_data(self):
        stages = {
            "market_bundle_requests": 100,
            "market_bundle_cache_hits": 80,
            "market_bundle_unique_fetches": 20,
            "market_bundle_cache_hit_rate": 80.0,
            "htf_trend_requests": 50,
            "htf_trend_cache_hits": 30,
            "htf_trend_unique_resolutions": 20,
            "htf_trend_cache_hit_rate": 60.0,
            "self_learning_active_tasks": 5,
            "self_learning_bypassed_tasks": 2,
        }
        result = PerformanceService._cache_summary_from_stages(stages)
        assert result["market_bundle"]["hits"] == 80
        assert result["market_bundle"]["misses"] == 20
        assert result["market_bundle"]["hit_rate_pct"] == 80.0
        assert result["htf_trend"]["hits"] == 30
        assert result["self_learning"]["active_tasks"] == 5


# ── _concurrency_summary_from_stages ────────────────────────────────

class TestConcurrencySummary:
    def test_payload_takes_precedence(self):
        stages = {"fetch_worker_capacity": 4, "analysis_worker_capacity": 2}
        progress = {"completed_tasks": 10, "remaining_tasks": 5}
        payload = {"scan_workers": 6}
        result = PerformanceService._concurrency_summary_from_stages(stages, progress, payload=payload)
        assert result["scan_workers"] == 6  # from payload
        assert result["analysis_worker_capacity"] == 2
        assert result["analysis_serialized"] is False  # 2 > 1

    def test_fallback_to_stages(self):
        stages = {"fetch_worker_capacity": 3}
        result = PerformanceService._concurrency_summary_from_stages(stages, {}, payload={})
        assert result["scan_workers"] == 3  # fallback from stages

    def test_serialized_when_single_worker(self):
        result = PerformanceService._concurrency_summary_from_stages(
            {"analysis_worker_capacity": 1}, {}, payload={}
        )
        assert result["analysis_serialized"] is True


# ── _aggregate_component_rows ───────────────────────────────────────

class TestAggregateComponentRows:
    def test_empty(self):
        assert PerformanceService()._aggregate_component_rows([]) == []

    def test_aggregates_and_sorts(self):
        rows = [
            {"component_id": "analysis", "label": "Analysis", "group": "engine", "count": 10, "total_ms": 100.0, "avg_ms": 10.0, "min_ms": 5.0, "max_ms": 20.0},
            {"component_id": "analysis", "label": "Analysis", "group": "engine", "count": 5, "total_ms": 75.0, "avg_ms": 15.0, "min_ms": 10.0, "max_ms": 25.0},
            {"component_id": "market_fetch", "label": "Market Fetch", "group": "market", "count": 3, "total_ms": 30.0, "avg_ms": 10.0},
        ]
        result = PerformanceService()._aggregate_component_rows(rows)
        assert len(result) == 2
        # Sorted by total_ms desc
        assert result[0]["component_id"] == "analysis"
        assert result[0]["count"] == 15
        assert result[0]["total_ms"] == 175.0
        assert result[1]["component_id"] == "market_fetch"

    def test_empty_component_id_skipped(self):
        rows = [{"component_id": "", "total_ms": 10.0}]
        assert PerformanceService()._aggregate_component_rows(rows) == []


# ── build_snapshot (mocked repos) ───────────────────────────────────

class TestBuildSnapshot:
    def test_empty(self):
        service = svc()
        service.order_repo.list_orders.return_value = []
        service.order_repo.list_positions.return_value = []
        result = service.build_snapshot()
        assert result["closed_trades"] == 0
        assert result["summary"]["total_trades"] == 0
        assert result["summary"]["win_rate"] == 0.0

    def test_with_trades(self):
        service = svc()
        service.order_repo.list_orders.side_effect = [
            [{"order_id": "o1", "status": "CLOSED", "payload": {"realized_r": 1.0, "signal": {"regime": "TRENDING"}}}],
            [],  # open orders
        ]
        service.order_repo.list_fills.return_value = []
        service.order_repo.list_positions.return_value = []
        result = service.build_snapshot()
        assert result["closed_trades"] == 1
        assert result["summary"]["net_r"] == 1.0
        assert result["summary"]["win_rate"] == 100.0


# ── get_analytics (mocked repos) ────────────────────────────────────

class TestGetAnalytics:
    def test_no_scans(self):
        service = svc()
        service.scan_repo.list_runs.return_value = []
        result = service.get_analytics()
        assert result["scan_runs"]["count"] == 0
        assert result["analysis"]["count"] == 0

    def test_with_scan_data(self):
        service = svc()
        service.scan_repo.list_runs.return_value = [
            {
                "run_id": "scan-1",
                "status": "COMPLETED",
                "started_at_utc": "2026-06-01T12:00:00Z",
                "finished_at_utc": "2026-06-01T12:01:00Z",
                "result": {
                    "timing": {
                        "analysis": {"count": 10, "avg_ms": 50.0, "min_ms": 10.0, "max_ms": 100.0},
                        "market_fetch": {"count": 5, "avg_ms": 20.0, "min_ms": 5.0, "max_ms": 50.0},
                    },
                    "created_orders": 2,
                    "progress": {"completed_tasks": 10, "total_tasks": 20},
                },
            },
        ]
        result = service.get_analytics()
        assert result["scan_runs"]["count"] == 1
        assert result["analysis"]["count"] == 10
        assert result["analysis"]["avg_ms"] == 50.0
        assert result["market_fetch"]["count"] == 5
        assert result["status_counts"] == {"COMPLETED": 1}
        assert len(result["recent_scans"]) == 1
        assert result["recent_scans"][0]["duration_ms"] == 60000.0  # 1 min in ms
