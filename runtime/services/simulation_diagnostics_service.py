"""Trace-derived diagnostics for historical simulation runs."""

from __future__ import annotations

import csv
import io
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from runtime.db.repos.settings_repo import SettingsRepository
from runtime.db.repos.simulation_decision_trace_repo import SimulationDecisionTraceRepository
from runtime.db.repos.simulation_repo import SimulationRepository
from runtime.db.session import session_scope

DEFAULT_LOW_CONFIDENCE_THRESHOLD = 35.0
DEFAULT_EXPORT_ROW_LIMIT = 5000
HISTOGRAM_BUCKET_SIZE = 10.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class SimulationDiagnosticsService:
    def __init__(
        self,
        simulation_repo: SimulationRepository | None = None,
        trace_repo: SimulationDecisionTraceRepository | None = None,
        settings_repo: SettingsRepository | None = None,
    ) -> None:
        self.simulation_repo = simulation_repo or SimulationRepository()
        self.trace_repo = trace_repo or SimulationDecisionTraceRepository()
        self.settings_repo = settings_repo or SettingsRepository()

    def get_diagnostics(self, run_id: int) -> dict[str, Any] | None:
        data = self._load(run_id)
        if data is None:
            return None
        run, traces, results, settings = data
        threshold = self._low_confidence_threshold(run, settings)
        base = self._base_payload(run, traces)
        if not traces:
            base.update(self._empty_diagnostics(run, threshold))
            return base
        distribution = self._decision_distribution(traces, threshold)
        histogram = self._confidence_histogram(traces, threshold)
        top_blockers = self._top_blockers(traces)
        per_symbol = self._per_symbol_summary(traces, results, threshold)
        per_mode = self._per_mode_summary(traces, results, threshold)
        directional = self._directional_filtered_counts(traces)
        health = self._health(run, traces, distribution, threshold)
        base.update({
            "trace_coverage": self._trace_coverage(run, traces),
            "decision_distribution": distribution,
            "confidence_summary": self._confidence_summary(traces, threshold),
            "confidence_histogram": histogram,
            "directional_but_filtered": directional,
            "top_blockers": top_blockers,
            "per_symbol_summary": per_symbol,
            "per_mode_summary": per_mode,
            "health": health,
            "meta": {"generated_at": _utc_now_iso(), "estimate_type": "trace_derived", "low_confidence_threshold": threshold},
        })
        return base

    def get_confidence_histogram(self, run_id: int) -> dict[str, Any] | None:
        data = self._load(run_id)
        if data is None:
            return None
        run, traces, _results, settings = data
        threshold = self._low_confidence_threshold(run, settings)
        return {
            "ok": True,
            "run_id": run_id,
            "has_traces": bool(traces),
            "threshold": threshold,
            "bucket_size": HISTOGRAM_BUCKET_SIZE,
            "items": self._confidence_histogram(traces, threshold),
        }

    def get_what_if(self, run_id: int, **params: Any) -> dict[str, Any] | None:
        data = self._load(run_id)
        if data is None:
            return None
        run, traces, _results, settings = data
        current = self._low_confidence_threshold(run, settings)
        hypo = _as_float(params.get("min_confidence"), current) or current
        if not traces:
            return {
                "ok": True,
                "run_id": run_id,
                "available": False,
                "reason": "no_decision_traces",
                "estimate_type": "unavailable",
                "current_min_confidence": current,
                "hypothetical_min_confidence": hypo,
            }
        current_actionable = [t for t in traces if self._is_actionable(t, current)]
        hypothetical = [t for t in traces if self._is_actionable(t, hypo)]
        added = [t for t in hypothetical if t not in current_actionable]
        return {
            "ok": True,
            "run_id": run_id,
            "available": True,
            "estimate_type": "approximate",
            "current_min_confidence": current,
            "hypothetical_min_confidence": hypo,
            "current_actionable_count": len(current_actionable),
            "hypothetical_actionable_count": len(hypothetical),
            "additional_directional_candidates": len(added),
            "newly_included_symbols": sorted({t.get("symbol") for t in added if t.get("symbol")}),
            "newly_included_modes": sorted({t.get("mode") for t in added if t.get("mode")}),
            "fee_slippage_sensitivity": self._fee_slippage_sensitivity(params),
            "max_hold_sensitivity": {"max_hold_bars": _as_int(params.get("max_hold_bars"), 0), "estimate_type": "not_rerun"},
            "risk_per_trade_estimate": self._risk_estimate(params, len(hypothetical)),
        }

    def get_parity_report(self, run_id: int) -> dict[str, Any] | None:
        data = self._load(run_id)
        if data is None:
            return None
        _run, traces, _results, _settings = data
        return {
            "ok": True,
            "run_id": run_id,
            "available": False,
            "reason": "no_comparable_scan_data",
            "compared_decision_count": 0,
            "direction_match_pct": None,
            "actionability_match_pct": None,
            "confidence_delta_avg": None,
            "fallback_rate_delta": None,
            "no_trade_reason_match_pct": None,
            "missing_scan_context_count": len(traces),
            "missing_sim_context_count": 0,
            "mismatches": [],
        }

    def export(self, run_id: int, *, target: str, format: str, limit: int | None = None) -> dict[str, Any] | None:
        data = self._load(run_id)
        if data is None:
            return None
        run, traces, results, settings = data
        row_limit = self._export_limit(settings, limit)
        rows = self._export_rows(run, traces, results, target)[:row_limit]
        fmt = str(format or "json").lower()
        if fmt == "csv":
            return {"content": self._csv(rows), "media_type": "text/csv", "count": len(rows)}
        if fmt == "jsonl":
            body = "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows)
            return {"content": (body + "\n") if body else "", "media_type": "application/x-ndjson", "count": len(rows)}
        return {"json": {"ok": True, "run_id": run_id, "target": target, "count": len(rows), "limit": row_limit, "items": rows}}

    def _load(self, run_id: int) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, str]] | None:
        with session_scope() as session:
            run = self.simulation_repo.get_run(session, run_id)
            if not run:
                return None
            traces = self.trace_repo.all_for_run(session, run_id, limit=self._export_limit(self.settings_repo.get_all(session), None))
            results = self.simulation_repo.results_for_run(session, run_id, limit=5000)
            settings = self.settings_repo.get_all(session)
        return run, traces, results, settings

    def _base_payload(self, run: dict[str, Any], traces: list[dict[str, Any]]) -> dict[str, Any]:
        return {"ok": True, "run_id": run.get("id"), "run_status": run.get("status"), "has_traces": bool(traces)}

    def _empty_diagnostics(self, run: dict[str, Any], threshold: float) -> dict[str, Any]:
        return {
            "trace_coverage": self._trace_coverage(run, []),
            "decision_distribution": self._zero_distribution(),
            "confidence_summary": self._confidence_summary([], threshold),
            "confidence_histogram": self._confidence_histogram([], threshold),
            "directional_but_filtered": {"directional_buy_filtered": 0, "directional_sell_filtered": 0, "directional_total_filtered": 0},
            "top_blockers": [],
            "per_symbol_summary": [],
            "per_mode_summary": [],
            "health": {"status": "UNKNOWN", "score": None, "reasons": ["no_decision_traces"], "recommended_actions": ["Run or backfill SIM-1 decision trace capture for this simulation."]},
            "meta": {"generated_at": _utc_now_iso(), "estimate_type": "limited", "low_confidence_threshold": threshold},
        }

    def _trace_coverage(self, run: dict[str, Any], traces: list[dict[str, Any]]) -> dict[str, Any]:
        metrics = dict(run.get("metrics") or {})
        expected = metrics.get("decision_count") or metrics.get("analyzer_call_count") or metrics.get("scan_replay_count")
        trace_count = len(traces)
        if trace_count == 0:
            status = "missing"
        elif expected is None:
            status = "unknown"
        elif trace_count >= int(expected or 0):
            status = "full"
        else:
            status = "partial"
        return {"has_traces": bool(traces), "trace_count": trace_count, "expected_decision_count": expected, "coverage_status": status}

    def _decision_distribution(self, traces: list[dict[str, Any]], threshold: float) -> dict[str, int]:
        counts = self._zero_distribution()
        for trace in traces:
            key = self._classify(trace, threshold)
            counts[key] = counts.get(key, 0) + 1
        return counts

    @staticmethod
    def _zero_distribution() -> dict[str, int]:
        keys = ["BUY", "SELL", "NO_TRADE", "low_confidence", "engine_filtered", "analysis_fallback", "duplicate_open", "analysis_error", "data_error", "insufficient_history", "insufficient_htf_history", "htf_data_error", "other"]
        return {key: 0 for key in keys}

    def _classify(self, trace: dict[str, Any], threshold: float) -> str:
        reason = str(trace.get("runtime_filter_reason") or trace.get("no_trade_reason") or "").lower()
        direction = str(trace.get("direction") or "").upper()
        confidence = _as_float(trace.get("confidence"), None)
        if trace.get("analysis_error"):
            return "analysis_error"
        if trace.get("data_error"):
            return "data_error"
        if trace.get("insufficient_history") or "insufficient_history" in reason:
            return "insufficient_htf_history" if "htf" in reason else "insufficient_history"
        if "htf_data_error" in reason:
            return "htf_data_error"
        if trace.get("fallback_used") or "fallback" in reason:
            return "analysis_fallback"
        if "duplicate" in reason:
            return "duplicate_open"
        if "low_confidence" in reason or (confidence is not None and confidence < threshold and direction in {"BUY", "SELL"}):
            return "low_confidence"
        if reason and reason not in {"actionable", "none"}:
            return "engine_filtered"
        if direction in {"BUY", "LONG"}:
            return "BUY"
        if direction in {"SELL", "SHORT"}:
            return "SELL"
        if direction in {"NEUTRAL", "NO_TRADE"}:
            return "NO_TRADE"
        return "other"

    def _confidence_summary(self, traces: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
        values = sorted(v for v in (_as_float(t.get("confidence"), None) for t in traces) if v is not None)
        return {
            "avg_confidence": round(sum(values) / len(values), 6) if values else None,
            "median_confidence": statistics.median(values) if values else None,
            "p10_confidence": self._percentile(values, 0.10),
            "p90_confidence": self._percentile(values, 0.90),
            "below_threshold_count": len([v for v in values if v < threshold]),
            "above_threshold_count": len([v for v in values if v >= threshold]),
            "threshold": threshold,
        }

    def _confidence_histogram(self, traces: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
        buckets = []
        for start in range(0, 100, int(HISTOGRAM_BUCKET_SIZE)):
            end = float(start + HISTOGRAM_BUCKET_SIZE)
            bucket_traces = [t for t in traces if (c := _as_float(t.get("confidence"), None)) is not None and float(start) <= c < end]
            buckets.append({
                "bucket_start": float(start), "bucket_end": end, "count": len(bucket_traces), "threshold_in_bucket": float(start) <= threshold < end,
                "buy_count": len([t for t in bucket_traces if str(t.get("direction") or "").upper() in {"BUY", "LONG"}]),
                "sell_count": len([t for t in bucket_traces if str(t.get("direction") or "").upper() in {"SELL", "SHORT"}]),
                "no_trade_count": len([t for t in bucket_traces if str(t.get("direction") or "").upper() in {"NEUTRAL", "NO_TRADE", ""}]),
                "low_confidence_count": len([t for t in bucket_traces if (_as_float(t.get("confidence"), 0.0) or 0.0) < threshold]),
            })
        return buckets

    def _directional_filtered_counts(self, traces: list[dict[str, Any]]) -> dict[str, int]:
        buy = sell = 0
        for t in traces:
            reason = t.get("runtime_filter_reason") or t.get("no_trade_reason")
            direction = str(t.get("direction") or "").upper()
            if not reason:
                continue
            if direction in {"BUY", "LONG"}:
                buy += 1
            elif direction in {"SELL", "SHORT"}:
                sell += 1
        return {"directional_buy_filtered": buy, "directional_sell_filtered": sell, "directional_total_filtered": buy + sell}

    def _top_blockers(self, traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[str, dict[str, Any]] = {}
        total = max(1, len(traces))
        for t in traces:
            reason = str(t.get("runtime_filter_reason") or t.get("no_trade_reason") or t.get("analysis_error") or t.get("data_error") or "actionable")
            if reason == "actionable":
                continue
            item = groups.setdefault(reason, {"reason": reason, "count": 0, "symbols": set(), "intervals": set(), "modes": set()})
            item["count"] += 1
            item["symbols"].add(t.get("symbol")); item["intervals"].add(t.get("interval")); item["modes"].add(t.get("mode"))
        rows = []
        for item in groups.values():
            rows.append({"reason": item["reason"], "count": item["count"], "percentage": round(item["count"] * 100.0 / total, 4), "affected_symbols": sorted(v for v in item["symbols"] if v), "affected_intervals": sorted(v for v in item["intervals"] if v), "affected_modes": sorted(v for v in item["modes"] if v)})
        return sorted(rows, key=lambda r: (-r["count"], r["reason"]))[:10]

    def _per_symbol_summary(self, traces: list[dict[str, Any]], results: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
        result_groups = self._result_groups(results, "symbol")
        rows = []
        for symbol, items in self._group(traces, "symbol").items():
            rows.append({**self._decision_counts(items, threshold), "symbol": symbol, **result_groups.get(symbol, {"executed_trade_count": 0, "total_pnl": 0.0})})
        return sorted(rows, key=lambda r: r["symbol"])

    def _per_mode_summary(self, traces: list[dict[str, Any]], results: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
        result_groups = self._result_groups(results, "mode")
        rows = []
        for mode, items in self._group(traces, "mode").items():
            confidences = [v for v in (_as_float(t.get("confidence"), None) for t in items) if v is not None]
            filtered = len([t for t in items if t.get("runtime_filter_reason") or t.get("no_trade_reason")])
            rows.append({"mode": mode, "decision_count": len(items), "executed_trade_count": result_groups.get(mode, {}).get("executed_trade_count", 0), "filtered_count": filtered, "avg_confidence": round(sum(confidences) / len(confidences), 6) if confidences else None, "fallback_rate": round(len([t for t in items if t.get("fallback_used")]) / len(items), 6), "total_pnl": result_groups.get(mode, {}).get("total_pnl", 0.0)})
        return sorted(rows, key=lambda r: r["mode"])

    def _health(self, run: dict[str, Any], traces: list[dict[str, Any]], distribution: dict[str, int], threshold: float) -> dict[str, Any]:
        total = max(1, len(traces)); score = 100; reasons = []; actions = []
        fallback_rate = distribution.get("analysis_fallback", 0) / total
        data_error_rate = (distribution.get("data_error", 0) + distribution.get("htf_data_error", 0)) / total
        insuff_rate = (distribution.get("insufficient_history", 0) + distribution.get("insufficient_htf_history", 0)) / total
        low_rate = distribution.get("low_confidence", 0) / total
        neutral_rate = distribution.get("NO_TRADE", 0) / total
        if dict(run.get("metrics") or {}).get("force_stopped"):
            score -= 30; reasons.append("force_stopped"); actions.append("Review partial coverage before trusting diagnostics.")
        for label, rate, penalty in [("fallback_dominated", fallback_rate, 45), ("data_error_dominated", data_error_rate, 70), ("insufficient_history_high", insuff_rate, 35), ("low_confidence_concentration", low_rate, 25), ("neutral_concentration", neutral_rate, 15)]:
            if rate >= 0.50:
                score -= penalty; reasons.append(label); actions.append(f"Investigate {label.replace('_', ' ')}.")
            elif rate >= 0.20:
                score -= penalty // 2; reasons.append(label)
        status = "GOOD" if score >= 80 else "WARNING" if score >= 50 else "BAD"
        if len(traces) < 3 or (dict(run.get("metrics") or {}).get("force_stopped") and len(traces) < 10):
            status = "UNKNOWN" if len(traces) < 3 else status
            reasons.append("low_decision_count")
        return {"status": status, "score": max(0, score), "reasons": sorted(set(reasons)) or ["within_expected_ranges"], "recommended_actions": actions or ["No immediate action from trace-derived checks."]}

    def _export_rows(self, run: dict[str, Any], traces: list[dict[str, Any]], results: list[dict[str, Any]], target: str) -> list[dict[str, Any]]:
        diagnostics = self.get_diagnostics(int(run["id"])) or {}
        metrics = dict(run.get("metrics") or {})
        target = str(target or "decision_traces")
        if target == "trades":
            return results
        if target == "decision_traces":
            return traces
        if target == "skip_breakdown":
            return list(metrics.get("skip_breakdown") or [])
        if target == "skip_samples":
            return list(metrics.get("skip_samples") or [])
        if target == "confidence_histogram":
            return list(diagnostics.get("confidence_histogram") or [])
        if target == "per_symbol_summary":
            return list(diagnostics.get("per_symbol_summary") or [])
        if target == "per_mode_summary":
            return list(diagnostics.get("per_mode_summary") or [])
        if target == "parity_report":
            return [self.get_parity_report(int(run["id"])) or {}]
        return [{k: v for k, v in diagnostics.items() if k not in {"per_symbol_summary", "per_mode_summary", "confidence_histogram"}}]

    @staticmethod
    def _csv(rows: list[dict[str, Any]]) -> str:
        out = io.StringIO()
        fieldnames = sorted({key for row in rows for key in row.keys()}) or ["empty"]
        writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value) if isinstance(value, (dict, list)) else value for key, value in row.items()})
        return out.getvalue()

    @staticmethod
    def _percentile(values: list[float], pct: float) -> float | None:
        if not values:
            return None
        idx = min(len(values) - 1, max(0, round((len(values) - 1) * pct)))
        return values[idx]

    @staticmethod
    def _group(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row.get(key) or "UNKNOWN")].append(row)
        return grouped

    def _decision_counts(self, rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
        return {"decision_count": len(rows), "buy_count": len([r for r in rows if str(r.get("direction") or "").upper() in {"BUY", "LONG"}]), "sell_count": len([r for r in rows if str(r.get("direction") or "").upper() in {"SELL", "SHORT"}]), "no_trade_count": len([r for r in rows if str(r.get("direction") or "").upper() in {"NEUTRAL", "NO_TRADE", ""}]), "low_confidence_count": len([r for r in rows if (_as_float(r.get("confidence"), 0.0) or 0.0) < threshold]), "fallback_count": len([r for r in rows if r.get("fallback_used")]), "data_error_count": len([r for r in rows if r.get("data_error")])}

    @staticmethod
    def _result_groups(results: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
        groups: dict[str, dict[str, Any]] = defaultdict(lambda: {"executed_trade_count": 0, "total_pnl": 0.0})
        for row in results:
            item = groups[str(row.get(key) or "UNKNOWN")]
            item["executed_trade_count"] += 1
            item["total_pnl"] += _as_float(row.get("realized_r") or dict(row.get("details") or {}).get("pnl"), 0.0) or 0.0
        return dict(groups)

    @staticmethod
    def _is_actionable(trace: dict[str, Any], threshold: float) -> bool:
        direction = str(trace.get("direction") or "").upper()
        reason = str(trace.get("runtime_filter_reason") or "").lower()
        confidence = _as_float(trace.get("confidence"), 0.0) or 0.0
        if direction not in {"BUY", "SELL", "LONG", "SHORT"} or confidence < threshold:
            return False
        return not reason or reason == "low_confidence"

    @staticmethod
    def _fee_slippage_sensitivity(params: dict[str, Any]) -> dict[str, Any]:
        fees = _as_float(params.get("fees_bps"), 0.0) or 0.0
        slip = _as_float(params.get("slippage_bps"), 0.0) or 0.0
        return {"fees_bps": fees, "slippage_bps": slip, "combined_bps": fees + slip, "estimate_type": "not_rerun"}

    @staticmethod
    def _risk_estimate(params: dict[str, Any], count: int) -> dict[str, Any]:
        risk = _as_float(params.get("risk_per_trade"), None)
        return {"risk_per_trade": risk, "candidate_count": count, "total_nominal_risk": (risk * count) if risk is not None else None, "estimate_type": "not_rerun"}

    @staticmethod
    def _low_confidence_threshold(run: dict[str, Any], settings: dict[str, str]) -> float:
        params = dict(run.get("parameters") or {})
        return _as_float(params.get("min_confidence") or settings.get("SIMULATION_DIAGNOSTICS_LOW_CONFIDENCE_THRESHOLD"), DEFAULT_LOW_CONFIDENCE_THRESHOLD) or DEFAULT_LOW_CONFIDENCE_THRESHOLD

    @staticmethod
    def _export_limit(settings: dict[str, str], requested: int | None) -> int:
        configured = _as_int(settings.get("SIMULATION_EXPORT_ROW_LIMIT"), DEFAULT_EXPORT_ROW_LIMIT)
        if requested is None:
            return max(1, configured)
        return min(max(1, int(requested)), max(1, configured))
