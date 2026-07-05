"""Historical runtime simulation engine for v4.

This module intentionally stays isolated from live scan/order execution. It reuses
market snapshots and analyzer decisions, but writes no orders, scan runs, or
portfolio rows.
"""

from __future__ import annotations

import math
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable

import pandas as pd

from runtime.db.repos.candle_repo import CandleRepository
from runtime.db.repos.settings_repo import DEFAULT_RUNTIME_SETTINGS
from runtime.db.session import session_scope
from runtime.services.binance_client import fetch_klines_range
from runtime.runtime.htf import resolve_htf_interval
from runtime.services.indicator_snapshot import build_indicator_snapshot
from runtime.services.incremental_indicators import extract_snapshot, precompute_all_indicators
from v6.contracts.analysis_request import ExecutionContextSection, RuntimeContextSection
from v6.contracts.compat import to_v5_request
from v6.contracts.enums import RequestKind
from v6.runtime.request_assembler import build_analysis_request
from v6.snapshot.builder import UnifiedSnapshotBuilder
from v6.snapshot.modes import SnapshotMode


def _parse_dt(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("date value is required")
    if len(text) == 10:
        text = f"{text}T00:00:00+00:00"
    resolved = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return resolved if resolved.tzinfo else resolved.replace(tzinfo=timezone.utc)


def _iso(value: Any) -> str:
    return pd.Timestamp(value).to_pydatetime().astimezone(timezone.utc).isoformat()


def _hours_between(start: Any, end: Any) -> float:
    return max(0.0, (pd.Timestamp(end) - pd.Timestamp(start)).total_seconds() / 3600.0)


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def _stage(key: str, label: str, status: str, detail: str) -> dict[str, str]:
    return {"key": key, "label": label, "status": status, "detail": detail}


class SimulationPerf:
    def __init__(self) -> None:
        self.started_at = perf_counter()
        self.buckets: dict[str, float] = defaultdict(float)
        self.counts: Counter[str] = Counter()
        self.slowest: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def add(self, bucket: str, elapsed: float, *, detail: dict[str, Any] | None = None) -> None:
        self.buckets[bucket] += max(0.0, elapsed)
        self.counts[bucket] += 1
        if detail:
            rows = self.slowest[bucket]
            rows.append({**detail, "elapsed_ms": round(elapsed * 1000, 3)})
            rows.sort(key=lambda row: float(row.get("elapsed_ms") or 0), reverse=True)
            del rows[10:]

    def measure(self, bucket: str, *, detail: dict[str, Any] | None = None):
        parent = self

        class _Measure:
            def __enter__(self):
                self.start = perf_counter()
                return self

            def __exit__(self, exc_type, exc, tb):
                parent.add(bucket, perf_counter() - self.start, detail=detail)
                return False

        return _Measure()

    def payload(self) -> dict[str, Any]:
        total = max(0.0, perf_counter() - self.started_at)
        buckets = []
        for name, seconds in sorted(self.buckets.items(), key=lambda item: item[1], reverse=True):
            buckets.append({
                "key": name,
                "seconds": round(seconds, 6),
                "ms": round(seconds * 1000, 3),
                "pct_of_measured": round((seconds / total) * 100, 3) if total else 0.0,
                "count": int(self.counts.get(name) or 0),
                "avg_ms": round((seconds / max(1, self.counts.get(name))) * 1000, 3),
            })
        return {
            "wall_clock_seconds": round(total, 6),
            "wall_clock_ms": round(total * 1000, 3),
            "buckets": buckets,
            "slowest": dict(self.slowest),
        }


@dataclass
class SimPosition:
    trade_id: str
    symbol: str
    interval: str
    mode: str
    direction: str
    confidence: float
    entry_price: float
    stop_loss: float
    take_profit: float
    quantity: float
    notional: float
    risk_amount: float
    opened_at: Any
    max_exit_index: int
    engine_summary: str


class HistoricalCandleLoader:
    def __init__(self, candle_repo: CandleRepository | None = None, fetcher: Callable[..., pd.DataFrame] | None = None) -> None:
        self.candle_repo = candle_repo or CandleRepository()
        self.fetcher = fetcher or fetch_klines_range

    def load(self, symbol: str, interval: str, start: datetime, end: datetime) -> pd.DataFrame:
        try:
            frame = self.fetcher(symbol, interval, start, end)
            if not frame.empty:
                self._persist(symbol, interval, frame)
                return frame.sort_values("open_time").reset_index(drop=True)
        except Exception:
            # Fall through to cache. The caller will raise a controlled failure
            # if no cached candles exist.
            pass

        with session_scope() as session:
            rows = self.candle_repo.list_candles_between(session, symbol, interval, start.isoformat(), end.isoformat())
        if not rows:
            raise RuntimeError(f"No historical candles available for {symbol} {interval} in requested range")
        frame = pd.DataFrame(rows)
        frame["open_time"] = pd.to_datetime(frame["open_time_utc"])
        frame["close_time"] = pd.to_datetime(frame["close_time_utc"])
        for column in ("open", "high", "low", "close", "volume"):
            frame[column] = frame[column].astype(float)
        frame["trades"] = frame.get("trades", 0)
        frame["quote_volume"] = frame.get("quote_volume", 0.0)
        return frame[["open_time", "open", "high", "low", "close", "volume", "trades", "quote_volume", "close_time"]].sort_values("open_time").reset_index(drop=True)

    def _persist(self, symbol: str, interval: str, frame: pd.DataFrame) -> None:
        payloads = []
        for row in frame.to_dict(orient="records"):
            payloads.append({
                "symbol": symbol.upper(),
                "interval": interval,
                "open_time_utc": _iso(row["open_time"]),
                "close_time_utc": _iso(row.get("close_time") or row["open_time"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0.0)),
                "source": "binance",
                "stale": False,
            })
        with session_scope() as session:
            self.candle_repo.bulk_upsert_candles(session, payloads)


class HistoricalSimulationEngine:
    def __init__(
        self,
        candle_loader: HistoricalCandleLoader | None = None,
        analyzer: Any | None = None,
        snapshot_builder: Callable[[pd.DataFrame], dict[str, Any]] | None = None,
    ) -> None:
        self.candle_loader = candle_loader or HistoricalCandleLoader()
        self.analyzer = analyzer
        self.snapshot_builder = snapshot_builder or build_indicator_snapshot
        self.unified_snapshot_builder = UnifiedSnapshotBuilder() if analyzer is None else None
        # Pre-computed indicator cache (set per symbol/interval run)
        self._indicator_frame: pd.DataFrame | None = None

    def run(
        self,
        payload: dict[str, Any],
        *,
        stop_checker: Callable[[], bool] | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        trace_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        start = _parse_dt(str(payload.get("period_start") or payload.get("start") or ""))
        end = _parse_dt(str(payload.get("period_end") or payload.get("end") or ""))
        if end <= start:
            raise ValueError("period_end must be after period_start")

        symbols = [str(s).upper().strip() for s in payload.get("symbols") or [] if str(s).strip()]
        intervals = [str(i).strip() for i in payload.get("intervals") or [] if str(i).strip()]
        modes = [str(m).upper().strip() for m in payload.get("modes") or [] if str(m).strip()]
        if not symbols or not intervals or not modes:
            raise ValueError("symbols, intervals, and modes are required")

        capital = float(payload.get("capital") or 50_000)
        risk_pct = max(0.01, float(payload.get("risk_per_trade_pct") or 1.0))
        execution_settings = dict(payload.get("execution_settings") or {})
        min_confidence = self._number_setting(payload, execution_settings, ["min_confidence", "AUTONOMOUS_MIN_CONFIDENCE", "MIN_CONFIDENCE"], 55.0) or 55.0
        scan_step_bars = max(1, int(self._number_setting(payload, execution_settings, ["scan_step_bars", "SIMULATION_SCAN_STEP_BARS", "SCAN_STEP_BARS"], 1) or 1))
        time_forward_step_bars = max(1, int(self._number_setting(payload, execution_settings, ["time_forward_step_bars", "SIMULATION_TIME_FORWARD_STEP_BARS", "TIME_FORWARD_STEP_BARS"], 1) or 1))
        max_hold_bars_payload = self._setting(payload, execution_settings, ["max_hold_bars", "SIMULATION_MAX_HOLD_BARS", "MAX_HOLD_BARS"], None)
        fee_bps = max(0.0, float(self._number_setting(payload, execution_settings, ["fee_bps", "SIMULATION_FEE_BPS", "FEE_BPS"], 0.0) or 0.0))
        slippage_bps = max(0.0, float(self._number_setting(payload, execution_settings, ["slippage_bps", "SIMULATION_SLIPPAGE_BPS", "SLIPPAGE_BPS"], 0.0) or 0.0))
        record_htf_availability = self._bool_setting(self._setting(payload, execution_settings, ["record_htf_availability", "SIMULATION_RECORD_HTF_AVAILABILITY"], True), True)
        require_htf_context = self._bool_setting(self._setting(payload, execution_settings, ["require_htf_context", "SIMULATION_REQUIRE_HTF_CONTEXT"], False), False)
        perf = SimulationPerf()
        requested_workers = max(1, int(self._number_setting(payload, execution_settings, ["scan_workers", "AUTONOMOUS_SCAN_WORKERS", "SCAN_WORKERS"], 1) or 1))
        max_workers = max(1, int(self._number_setting(payload, execution_settings, ["max_scan_workers", "SIMULATION_MAX_SCAN_WORKERS", "MAX_SCAN_WORKERS"], float(DEFAULT_RUNTIME_SETTINGS.get("SIMULATION_MAX_SCAN_WORKERS", "4") or 4)) or 4))
        effective_workers = min(requested_workers, max_workers, max(1, len(symbols) * len(intervals) * len(modes)))
        if effective_workers > 1:
            return self._run_parallel(
                payload,
                symbols=symbols,
                intervals=intervals,
                modes=modes,
                capital=capital,
                stop_checker=stop_checker,
                progress_callback=progress_callback,
                trace_callback=trace_callback,
                requested_workers=requested_workers,
                effective_workers=effective_workers,
                start=start,
                end=end,
                perf=perf,
            )

        total_tasks = max(1, len(symbols) * len(intervals) * len(modes))
        completed_tasks = 0
        trades: list[dict[str, Any]] = []
        skip_counts: Counter[str] = Counter()
        skip_samples: list[dict[str, Any]] = []
        blocked_until: dict[str, int] = {}
        equity_points = [capital]
        per_mode: dict[str, dict[str, float]] = defaultdict(lambda: {"pnl": 0.0, "trades": 0.0, "wins": 0.0})
        stages = [
            _stage("data_load", "Historical candle load", "ACTIVE", "loading historical candles"),
            _stage("scan_replay", "Historical scan replay", "PENDING", "pending"),
            _stage("trade_calc", "Time-forward trade calc", "PENDING", "pending"),
            _stage("pnl_attr", "P&L attribution", "PENDING", "pending"),
        ]
        htf_metrics: dict[str, Any] = {
            "requested": 0,
            "available": 0,
            "missing": 0,
            "missing_by_symbol": Counter(),
            "missing_by_interval": Counter(),
        }

        for symbol in symbols:
            for interval in intervals:
                try:
                    with perf.measure("candle_load", detail={"symbol": symbol, "interval": interval}):
                        frame = self.candle_loader.load(symbol, interval, start, end)
                except Exception as exc:
                    skip_counts["data_error"] += len(modes)
                    for mode in modes:
                        self._record_skip_sample(skip_samples, reason="data_error", symbol=symbol, interval=interval, mode=mode, timestamp=start.isoformat(), message=str(exc))
                    if progress_callback is not None:
                        progress_callback({
                            "event_type": "data_error",
                            "progress_pct": round((completed_tasks / max(1, total_tasks)) * 100),
                            "symbol": symbol,
                            "interval": interval,
                            "message": str(exc),
                            "skip_breakdown": [{"key": k, "count": v} for k, v in skip_counts.items()],
                        })
                    continue
                if len(frame) < 8:
                    skip_counts["insufficient_history"] += len(modes)
                    for mode in modes:
                        self._record_skip_sample(skip_samples, reason="insufficient_history", symbol=symbol, interval=interval, mode=mode, timestamp=start.isoformat(), message=f"Only {len(frame)} candles available")
                    continue
                htf_interval = resolve_htf_interval(interval)
                htf_frame: pd.DataFrame | None = None
                htf_load_error: str | None = None
                if htf_interval and (record_htf_availability or require_htf_context):
                    try:
                        with perf.measure("htf_candle_load", detail={"symbol": symbol, "interval": htf_interval}):
                            htf_frame = self.candle_loader.load(symbol, htf_interval, start, end)
                    except Exception as exc:
                        htf_load_error = str(exc)
                stages[0] = _stage("data_load", "Historical candle load", "DONE", f"loaded {len(frame)} candles")
                stages[1] = _stage("scan_replay", "Historical scan replay", "ACTIVE", f"replaying {symbol} {interval}")
                warmup = min(80, max(5, len(frame) // 5))
                # ── Precompute all indicators once per symbol/interval ──
                with perf.measure("precompute_indicators"):
                    self._indicator_frame = precompute_all_indicators(frame)
                for mode in modes:
                    if stop_checker and stop_checker():
                        return self._finalize(payload, capital, equity_points, trades, per_mode, skip_counts, skip_samples, stages, "STOPPED", completed_tasks, total_tasks, start, end, htf_metrics, perf)
                    default_hold = self._default_hold_bars(interval, mode)
                    max_hold_bars = int(max_hold_bars_payload or default_hold)
                    for idx in range(warmup, len(frame) - 1, scan_step_bars):
                        if stop_checker and stop_checker():
                            return self._finalize(payload, capital, equity_points, trades, per_mode, skip_counts, skip_samples, stages, "STOPPED", completed_tasks, total_tasks, start, end, htf_metrics, perf)
                        candle = frame.iloc[idx]
                        timestamp = _iso(candle.get("close_time") or candle.get("open_time"))
                        htf_window = None
                        htf_status = {"htf_interval": htf_interval, "available": False, "missing_reason": None}
                        if htf_interval and (record_htf_availability or require_htf_context):
                            htf_metrics["requested"] += 1
                            if htf_load_error:
                                self._mark_htf_missing(htf_metrics, symbol, htf_interval)
                                htf_status["missing_reason"] = "htf_data_error"
                                if require_htf_context:
                                    skip_counts["htf_data_error"] += 1
                                    self._record_skip_sample(skip_samples, reason="htf_data_error", symbol=symbol, interval=interval, mode=mode, timestamp=timestamp, message=htf_load_error)
                                    continue
                            else:
                                with perf.measure("htf_window_align"):
                                    htf_window = self._htf_window(htf_frame, timestamp)
                                if htf_window is None or htf_window.empty:
                                    self._mark_htf_missing(htf_metrics, symbol, htf_interval)
                                    htf_status["missing_reason"] = "insufficient_htf_history"
                                    if require_htf_context:
                                        skip_counts["insufficient_htf_history"] += 1
                                        self._record_skip_sample(skip_samples, reason="insufficient_htf_history", symbol=symbol, interval=interval, mode=mode, timestamp=timestamp, message=f"No aligned {htf_interval} candles available")
                                        continue
                                else:
                                    htf_metrics["available"] += 1
                                    htf_status["available"] = True
                        try:
                            with perf.measure("analyzer", detail={"symbol": symbol, "interval": interval, "mode": mode, "timestamp": timestamp}):
                                analysis = self._analyze_window(symbol=symbol, interval=interval, mode=mode, frame=frame, idx=idx, htf_interval=htf_interval, htf_window=htf_window)
                        except Exception as exc:
                            skip_counts["analysis_error"] += 1
                            self._record_skip_sample(skip_samples, reason="analysis_error", symbol=symbol, interval=interval, mode=mode, timestamp=timestamp, message=str(exc))
                            self._emit_trace(trace_callback, self._build_decision_trace(symbol=symbol, interval=interval, mode=mode, timestamp=timestamp, analysis={}, signal={}, runtime_filter_reason="analysis_error", skip_family="error", analysis_error=str(exc), htf_status=htf_status))
                            continue
                        signal = dict(analysis.get("signal") or analysis)
                        direction = str(signal.get("direction") or analysis.get("direction") or "NEUTRAL").upper()
                        confidence = float(_num(signal.get("confidence", analysis.get("confidence")), 0.0) or 0.0)
                        signal_status = str(analysis.get("signal_status") or "").upper()
                        if direction not in {"BUY", "SELL"}:
                            if analysis.get("fallback_used") or signal_status in {"DEGRADED", "ERROR"}:
                                reason = str(analysis.get("fallback_reason") or signal.get("no_trade_reason") or "analysis_fallback").lower()
                                trace_reason = f"analysis_fallback:{reason}"
                                skip_counts[trace_reason] += 1
                                self._record_skip_sample(skip_samples, reason=trace_reason, symbol=symbol, interval=interval, mode=mode, timestamp=timestamp, analysis=analysis, signal=signal)
                                self._emit_trace(trace_callback, self._build_decision_trace(symbol=symbol, interval=interval, mode=mode, timestamp=timestamp, analysis=analysis, signal=signal, runtime_filter_reason=trace_reason, skip_family="analysis_fallback", htf_status=htf_status))
                            elif signal_status in {"FILTERED", "REJECTED"}:
                                skip_counts["engine_filtered"] += 1
                                self._record_skip_sample(skip_samples, reason="engine_filtered", symbol=symbol, interval=interval, mode=mode, timestamp=timestamp, analysis=analysis, signal=signal)
                                self._emit_trace(trace_callback, self._build_decision_trace(symbol=symbol, interval=interval, mode=mode, timestamp=timestamp, analysis=analysis, signal=signal, runtime_filter_reason="engine_filtered", skip_family="decision_output", htf_status=htf_status))
                            else:
                                skip_counts["neutral"] += 1
                                self._record_skip_sample(skip_samples, reason="neutral", symbol=symbol, interval=interval, mode=mode, timestamp=timestamp, analysis=analysis, signal=signal)
                                self._emit_trace(trace_callback, self._build_decision_trace(symbol=symbol, interval=interval, mode=mode, timestamp=timestamp, analysis=analysis, signal=signal, runtime_filter_reason="neutral", skip_family="decision_output", htf_status=htf_status))
                            continue
                        if confidence < min_confidence:
                            skip_counts["low_confidence"] += 1
                            self._record_skip_sample(skip_samples, reason="low_confidence", symbol=symbol, interval=interval, mode=mode, timestamp=timestamp, analysis=analysis, signal=signal)
                            self._emit_trace(trace_callback, self._build_decision_trace(symbol=symbol, interval=interval, mode=mode, timestamp=timestamp, analysis=analysis, signal=signal, runtime_filter_reason="low_confidence", skip_family="decision_output", htf_status=htf_status))
                            continue
                        open_key = f"{symbol}:{interval}:{mode}:{direction}"
                        if idx <= blocked_until.get(open_key, -1):
                            skip_counts["duplicate_open"] += 1
                            self._record_skip_sample(skip_samples, reason="duplicate_open", symbol=symbol, interval=interval, mode=mode, timestamp=timestamp, analysis=analysis, signal=signal)
                            self._emit_trace(trace_callback, self._build_decision_trace(symbol=symbol, interval=interval, mode=mode, timestamp=timestamp, analysis=analysis, signal=signal, runtime_filter_reason="duplicate_open", skip_family="runtime_filter", htf_status=htf_status))
                            continue
                        self._emit_trace(trace_callback, self._build_decision_trace(symbol=symbol, interval=interval, mode=mode, timestamp=timestamp, analysis=analysis, signal=signal, runtime_filter_reason=None, skip_family="actionable", htf_status=htf_status))
                        position = self._open_position(payload, signal, symbol, interval, mode, direction, confidence, frame, idx, max_hold_bars, capital, risk_pct)
                        with perf.measure("trade_settlement", detail={"symbol": symbol, "interval": interval, "mode": mode, "timestamp": timestamp}):
                            settled = self._settle_position(position, frame, idx + 1, step_bars=time_forward_step_bars, fee_bps=fee_bps, slippage_bps=slippage_bps)
                        blocked_until[open_key] = int((settled.get("details") or {}).get("close_index") or idx)
                        trades.append(settled)
                        if progress_callback is not None:
                            progress_callback({
                                "event_type": "trade_settled",
                                "progress_pct": round((completed_tasks / max(1, total_tasks)) * 100),
                                "current_sim_date": _iso(candle["open_time"]),
                                "trade_count": len(trades),
                                "closed_trade_count": len(trades),
                                "open_trade_count": 0,
                                "symbol": symbol,
                                "interval": interval,
                                "mode": mode,
                                "direction": direction,
                                "trade": settled.get("details") or settled,
                            })
                        equity_points.append(equity_points[-1] + float(settled.get("pnl") or 0.0))
                        bucket = per_mode[mode]
                        bucket["pnl"] += float(settled.get("pnl") or 0.0)
                        bucket["trades"] += 1
                        if float(settled.get("pnl") or 0.0) > 0:
                            bucket["wins"] += 1
                    completed_tasks += 1
                    if progress_callback is not None:
                        progress_callback({
                            "event_type": "task_completed",
                            "progress_pct": round((completed_tasks / max(1, total_tasks)) * 100),
                            "current_sim_date": _iso(frame.iloc[min(len(frame) - 1, idx)]["open_time"]),
                            "trade_count": len(trades),
                            "closed_trade_count": len(trades),
                            "open_trade_count": 0,
                            "stages": stages,
                        })

        stages[1] = _stage("scan_replay", "Historical scan replay", "DONE", f"{completed_tasks} replay tasks complete")
        stages[2] = _stage("trade_calc", "Time-forward trade calc", "DONE", f"{len(trades)} trades settled")
        stages[3] = _stage("pnl_attr", "P&L attribution", "DONE", "complete")
        return self._finalize(payload, capital, equity_points, trades, per_mode, skip_counts, skip_samples, stages, "COMPLETED", completed_tasks, total_tasks, start, end, htf_metrics, perf)

    def _run_parallel(
        self,
        payload: dict[str, Any],
        *,
        symbols: list[str],
        intervals: list[str],
        modes: list[str],
        capital: float,
        stop_checker: Callable[[], bool] | None,
        progress_callback: Callable[[dict[str, Any]], None] | None,
        trace_callback: Callable[[dict[str, Any]], None] | None,
        requested_workers: int,
        effective_workers: int,
        start: datetime,
        end: datetime,
        perf: SimulationPerf,
    ) -> dict[str, Any]:
        tasks = [(symbol, interval, mode) for symbol in symbols for interval in intervals for mode in modes]
        total_tasks = max(1, len(tasks))
        completed_tasks = 0
        cancelled_tasks = 0
        worker_errors: list[dict[str, Any]] = []
        traces: list[dict[str, Any]] = []
        trades: list[dict[str, Any]] = []
        skip_counts: Counter[str] = Counter()
        skip_samples: list[dict[str, Any]] = []
        htf_metrics: dict[str, Any] = {"requested": 0, "available": 0, "missing": 0, "missing_by_symbol": Counter(), "missing_by_interval": Counter()}
        stages = [
            _stage("data_load", "Historical candle load", "DONE", "parallel workers loading historical candles"),
            _stage("scan_replay", "Historical scan replay", "ACTIVE", f"{effective_workers} workers replaying {len(tasks)} tasks"),
            _stage("trade_calc", "Time-forward trade calc", "PENDING", "pending"),
            _stage("pnl_attr", "P&L attribution", "PENDING", "pending"),
        ]

        def run_task(symbol: str, interval: str, mode: str) -> dict[str, Any]:
            local_payload = {**payload, "symbols": [symbol], "intervals": [interval], "modes": [mode], "scan_workers": 1}
            local_traces: list[dict[str, Any]] = []
            worker = HistoricalSimulationEngine(
                candle_loader=self.candle_loader,
                analyzer=None if self.analyzer is None else self.analyzer,
                snapshot_builder=self.snapshot_builder,
            )
            worker_start = perf_counter()
            output = worker.run(local_payload, stop_checker=stop_checker, trace_callback=local_traces.append)
            worker_elapsed = perf_counter() - worker_start
            return {"symbol": symbol, "interval": interval, "mode": mode, "output": output, "traces": local_traces, "worker_elapsed_seconds": worker_elapsed}

        with perf.measure("parallel_executor_wall"):
            with ThreadPoolExecutor(max_workers=effective_workers, thread_name_prefix="sim-replay") as executor:
                with perf.measure("parallel_submit_tasks"):
                    future_map = {executor.submit(run_task, symbol, interval, mode): (symbol, interval, mode) for symbol, interval, mode in tasks}
                for future in as_completed(future_map):
                    symbol, interval, mode = future_map[future]
                    if stop_checker and stop_checker():
                        for pending in future_map:
                            if not pending.done() and pending.cancel():
                                cancelled_tasks += 1
                        break
                    try:
                        result = future.result()
                    except Exception as exc:
                        worker_errors.append({"symbol": symbol, "interval": interval, "mode": mode, "error": str(exc)})
                        skip_counts["worker_error"] += 1
                        self._record_skip_sample(skip_samples, reason="worker_error", symbol=symbol, interval=interval, mode=mode, timestamp=start.isoformat(), message=str(exc))
                        if progress_callback is not None:
                            progress_callback({"event_type": "worker_error", "symbol": symbol, "interval": interval, "mode": mode, "message": str(exc), "progress_pct": round((completed_tasks / total_tasks) * 100)})
                        completed_tasks += 1
                        continue
                    perf.add("worker_task_wall", float(result.get("worker_elapsed_seconds") or 0.0), detail={"symbol": symbol, "interval": interval, "mode": mode})
                    output = dict(result.get("output") or {})
                    metrics = dict(output.get("metrics") or {})
                    child_perf = metrics.get("performance_diagnostics") if isinstance(metrics.get("performance_diagnostics"), dict) else {}
                    for bucket in child_perf.get("buckets") or []:
                        perf.add(f"worker:{bucket.get('key')}", float(bucket.get("seconds") or 0.0))
                    completed_tasks += 1
                    trades.extend(output.get("results") or [])
                    traces.extend(result.get("traces") or [])
                    for row in metrics.get("skip_breakdown") or []:
                        skip_counts[str(row.get("key") or "other")] += int(row.get("count") or 0)
                    for sample in metrics.get("skip_samples") or []:
                        if len(skip_samples) < 75:
                            skip_samples.append(sample)
                    htf_metrics["requested"] += int(metrics.get("htf_context_requested_count") or 0)
                    htf_metrics["available"] += int(metrics.get("htf_context_available_count") or 0)
                    htf_metrics["missing"] += int(metrics.get("htf_context_missing_count") or 0)
                    htf_metrics["missing_by_symbol"].update(metrics.get("htf_context_missing_by_symbol") or {})
                    htf_metrics["missing_by_interval"].update(metrics.get("htf_context_missing_by_interval") or {})
                    if progress_callback is not None:
                        progress_callback({"event_type": "task_completed", "progress_pct": round((completed_tasks / total_tasks) * 100), "symbol": symbol, "interval": interval, "mode": mode, "trade_count": len(trades), "closed_trade_count": len(trades), "open_trade_count": 0, "stages": stages})

        with perf.measure("trace_sort"):
            traces = sorted(traces, key=lambda row: (str(row.get("timestamp") or ""), str(row.get("symbol") or ""), str(row.get("interval") or ""), str(row.get("mode") or ""), str(row.get("trace_id") or "")))
        with perf.measure("trace_emit", detail={"trace_count": len(traces)}):
            for trace in traces:
                self._emit_trace(trace_callback, trace)
        with perf.measure("trade_sort"):
            trades = sorted(trades, key=lambda row: (str((row.get("details") or {}).get("opened_at") or ""), str(row.get("symbol") or ""), str(row.get("interval") or ""), str(row.get("mode") or ""), str((row.get("details") or {}).get("trade_id") or "")))
        equity_points = [capital]
        per_mode: dict[str, dict[str, float]] = defaultdict(lambda: {"pnl": 0.0, "trades": 0.0, "wins": 0.0})
        for trade in trades:
            pnl = float((trade.get("details") or {}).get("pnl") or trade.get("pnl") or 0.0)
            equity_points.append(equity_points[-1] + pnl)
            bucket = per_mode[str(trade.get("mode") or "UNKNOWN")]
            bucket["pnl"] += pnl
            bucket["trades"] += 1
            if pnl > 0:
                bucket["wins"] += 1
        status = "STOPPED" if stop_checker and stop_checker() else "COMPLETED"
        stages[1] = _stage("scan_replay", "Historical scan replay", "DONE" if status == "COMPLETED" else "STOPPED", f"{completed_tasks} replay tasks complete")
        stages[2] = _stage("trade_calc", "Time-forward trade calc", "DONE", f"{len(trades)} trades settled")
        stages[3] = _stage("pnl_attr", "P&L attribution", "DONE", "complete")
        output = self._finalize(payload, capital, equity_points, trades, per_mode, skip_counts, skip_samples, stages, status, completed_tasks, total_tasks, start, end, htf_metrics, perf)
        metrics = dict(output.get("metrics") or {})
        metrics.update({
            "worker_count_requested": requested_workers,
            "worker_count_effective": effective_workers,
            "tasks_submitted": len(tasks),
            "tasks_completed": completed_tasks,
            "tasks_cancelled": cancelled_tasks,
            "worker_errors": worker_errors,
            "parallel_execution_enabled": True,
        })
        if worker_errors:
            metrics.setdefault("alerts", []).append({"tone": "warning", "title": "Simulation worker errors", "message": f"{len(worker_errors)} replay worker(s) failed."})
        output["metrics"] = metrics
        return output

    def _get_analyzer(self):
        if self.analyzer is None:
            from runtime.services.analyzer_engine_adapter import AnalyzerEngineAdapter

            self.analyzer = AnalyzerEngineAdapter()
        return self.analyzer

    def _analyze_window(self, *, symbol: str, interval: str, mode: str, frame: pd.DataFrame, window: pd.DataFrame | None = None, idx: int, htf_interval: str | None = None, htf_window: pd.DataFrame | None = None) -> dict[str, Any]:
        candle = frame.iloc[idx]
        timestamp = _iso(candle.get("close_time") or candle.get("open_time"))
        # Use precomputed indicator snapshot when available (~18x faster)
        if self._indicator_frame is not None:
            snapshot = extract_snapshot(self._indicator_frame, idx)
        else:
            snapshot = dict(self.snapshot_builder(window or frame.iloc[:idx + 1]))
        if self.unified_snapshot_builder is None:
            return self._get_analyzer().analyze(
                symbol=symbol,
                interval=interval,
                mode=mode,
                snapshot=snapshot,
                runtime_context={"kind": "historical_simulation", "timestamp": timestamp},
                timestamp=timestamp,
            )

        raw_candles = self._raw_candles(window or frame.iloc[:idx + 1])
        raw_htf_candles = {htf_interval: self._raw_candles(htf_window)} if htf_interval and htf_window is not None and not htf_window.empty else {}
        snapshot_artifact = self.unified_snapshot_builder.build(
            symbol=symbol,
            interval=interval,
            timestamp_utc=timestamp,
            request_kind=RequestKind.REPLAY_EVAL,
            raw_candles=raw_candles,
            raw_htf_candles=raw_htf_candles,
            engine_mode="PAPER",
            runtime_context_hints={"mode": mode, "requested_by": "historical_simulation"},
            data_source="historical_replay",
            mode=SnapshotMode.REPLAY_STATE,
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
                source_context="historical_simulation",
                requested_by="simulation",
                paper_or_live_mode=mode,
                engine_budget_hint="normal",
                runtime_phase="replay",
            ),
            trade_mode=mode,
            request_kind=RequestKind.REPLAY_EVAL,
            run_id="historical-simulation",
        )
        legacy_request = to_v5_request(analysis_request)
        # Use extract_snapshot result (already computed above) — avoid dict() copy
        legacy_snapshot = {**legacy_request.get("snapshot", {}), **snapshot}
        legacy_snapshot["candles"] = list(legacy_snapshot.get("candles") or raw_candles)
        legacy_snapshot.setdefault("strategy_version", snapshot.get("strategy_version"))
        legacy_request["snapshot"] = legacy_snapshot
        legacy_request["mode"] = mode
        return self._get_analyzer().analyze(
            symbol=symbol,
            interval=interval,
            mode=mode,
            snapshot=legacy_snapshot,
            market_context=legacy_request.get("market_context"),
            runtime_context=legacy_request.get("runtime_context"),
            request_id=analysis_request.identity.request_id,
            timestamp=analysis_request.identity.timestamp_utc,
        )

    @staticmethod
    def _emit_trace(trace_callback: Callable[[dict[str, Any]], None] | None, trace: dict[str, Any]) -> None:
        if trace_callback is not None:
            trace_callback(trace)

    def _build_decision_trace(
        self,
        *,
        symbol: str,
        interval: str,
        mode: str,
        timestamp: str,
        analysis: dict[str, Any],
        signal: dict[str, Any],
        runtime_filter_reason: str | None,
        skip_family: str,
        htf_status: dict[str, Any] | None = None,
        analysis_error: str | None = None,
    ) -> dict[str, Any]:
        analysis = dict(analysis or {})
        signal = dict(signal or {})
        advanced = signal.get("advanced_analysis") if isinstance(signal.get("advanced_analysis"), dict) else {}
        decision_path = advanced.get("decision_path") if isinstance(advanced, dict) else {}
        if not isinstance(decision_path, dict):
            decision_path = {}
        probability_model = advanced.get("probability_model") if isinstance(advanced, dict) else {}
        if not isinstance(probability_model, dict):
            probability_model = {}
        scores = analysis.get("scores") if isinstance(analysis.get("scores"), dict) else {}
        direction = str(signal.get("direction") or analysis.get("direction") or "NEUTRAL").upper()
        confidence = _num(signal.get("confidence", analysis.get("confidence")), None)
        no_trade_reason = signal.get("no_trade_reason") or analysis.get("fallback_reason") or runtime_filter_reason
        fallback_reason = analysis.get("fallback_reason") or signal.get("fallback_reason") or (no_trade_reason if analysis.get("fallback_used") else None)
        htf_status = dict(htf_status or {})
        return {
            "trace_id": f"sim-trace-{uuid.uuid4().hex}",
            "symbol": symbol,
            "interval": interval,
            "mode": mode,
            "timestamp": timestamp,
            "direction": direction,
            "confidence": confidence,
            "signal_status": analysis.get("signal_status") or signal.get("signal_status"),
            "selected_action": analysis.get("selected_action") or signal.get("selected_action") or decision_path.get("selected_action") if isinstance(decision_path, dict) else None,
            "selected_head": analysis.get("selected_head") or signal.get("selected_head") or decision_path.get("selected_head") if isinstance(decision_path, dict) else None,
            "runtime_filter_reason": runtime_filter_reason,
            "no_trade_reason": no_trade_reason,
            "skip_family": skip_family,
            "fallback_used": bool(analysis.get("fallback_used") or str(runtime_filter_reason or "").startswith("analysis_fallback")),
            "fallback_reason": fallback_reason,
            "analysis_error": analysis_error,
            "data_error": None,
            "insufficient_history": False,
            "confidence_raw": _num(signal.get("confidence_raw") or analysis.get("confidence_raw"), None),
            "confidence_final": _num(signal.get("confidence_final") or analysis.get("confidence_final") or confidence, None),
            "probability_long_raw": self._probability_value(probability_model, scores, "long", "raw"),
            "probability_short_raw": self._probability_value(probability_model, scores, "short", "raw"),
            "probability_no_trade_raw": self._probability_value(probability_model, scores, "no_trade", "raw"),
            "probability_long_final": self._probability_value(probability_model, scores, "long", "final"),
            "probability_short_final": self._probability_value(probability_model, scores, "short", "final"),
            "probability_no_trade_final": self._probability_value(probability_model, scores, "no_trade", "final"),
            "entry_price": _num(signal.get("entry_price") or analysis.get("entry_price"), None),
            "stop_loss": _num(signal.get("stop_loss") or analysis.get("stop_loss"), None),
            "take_profit": _num(signal.get("take_profit") or analysis.get("take_profit"), None),
            "summary": signal.get("summary") or analysis.get("summary") or analysis_error or "",
            "analyzer_metadata": {
                "engine_name": analysis.get("engine_name"),
                "engine_version": analysis.get("engine_version"),
                "schema_version": analysis.get("schema_version"),
                "analysis_latency_ms": analysis.get("analysis_latency_ms"),
                "warnings": analysis.get("warnings") or [],
            },
            "runtime_context": {
                "source_context": "historical_simulation",
                "runtime_phase": "replay",
                "runtime_filter_reason": runtime_filter_reason,
            },
            "snapshot_metadata": {
                "htf_interval": htf_status.get("htf_interval"),
                "htf_available": bool(htf_status.get("available")),
                "htf_missing_reason": htf_status.get("missing_reason"),
            },
        }

    @staticmethod
    def _probability_value(probability_model: dict[str, Any], scores: dict[str, Any], head: str, stage: str) -> float | None:
        candidates = (
            probability_model.get(f"probability_{head}_{stage}"),
            probability_model.get(f"{head}_{stage}"),
            probability_model.get(head) if stage == "final" else None,
            scores.get(f"{head}_score") if stage == "final" else None,
        )
        for candidate in candidates:
            value = _num(candidate, None)
            if value is not None:
                return value
        return None

    @staticmethod
    def _record_skip_sample(
        samples: list[dict[str, Any]],
        *,
        reason: str,
        symbol: str,
        interval: str,
        mode: str,
        timestamp: str,
        analysis: dict[str, Any] | None = None,
        signal: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> None:
        if len(samples) >= 75:
            return
        analysis = dict(analysis or {})
        signal = dict(signal or {})
        samples.append({
            "reason": reason,
            "symbol": symbol,
            "interval": interval,
            "mode": mode,
            "timestamp": timestamp,
            "direction": str(signal.get("direction") or analysis.get("direction") or "NEUTRAL").upper(),
            "confidence": _num(signal.get("confidence", analysis.get("confidence")), None),
            "signal_status": analysis.get("signal_status"),
            "fallback_reason": analysis.get("fallback_reason") or signal.get("no_trade_reason"),
            "summary": signal.get("summary") or analysis.get("summary") or message or "",
            "no_trade_reason": signal.get("no_trade_reason") or analysis.get("fallback_reason") or message or "",
        })

    @staticmethod
    def _setting(payload: dict[str, Any], execution_settings: dict[str, Any], keys: list[str], default: Any = None) -> Any:
        for key in keys:
            payload_value = payload.get(key)
            if payload_value is not None and payload_value != "":
                return payload_value
            setting_value = execution_settings.get(key)
            if setting_value is not None and setting_value != "":
                return setting_value
        return default

    @classmethod
    def _number_setting(cls, payload: dict[str, Any], execution_settings: dict[str, Any], keys: list[str], default: float | None = None) -> float | None:
        return _num(cls._setting(payload, execution_settings, keys, default), default)

    @staticmethod
    def _bool_setting(value: Any, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _mark_htf_missing(htf_metrics: dict[str, Any], symbol: str, htf_interval: str) -> None:
        htf_metrics["missing"] += 1
        htf_metrics["missing_by_symbol"][symbol] += 1
        htf_metrics["missing_by_interval"][htf_interval] += 1

    @staticmethod
    def _htf_window(htf_frame: pd.DataFrame | None, timestamp: str) -> pd.DataFrame | None:
        if htf_frame is None or htf_frame.empty:
            return None
        close_times = pd.to_datetime(htf_frame.get("close_time", htf_frame.get("open_time")))
        cutoff = pd.Timestamp(timestamp)
        if cutoff.tzinfo is None:
            cutoff = cutoff.tz_localize(timezone.utc)
        aligned = htf_frame.loc[close_times <= cutoff].copy()
        if aligned.empty:
            return None
        return aligned.reset_index(drop=True)

    @staticmethod
    def _raw_candles(frame: pd.DataFrame) -> list[dict[str, Any]]:
        candles: list[dict[str, Any]] = []
        for row in frame.to_dict(orient="records"):
            candles.append({
                "open_time_utc": _iso(row.get("open_time")),
                "close_time_utc": _iso(row.get("close_time") or row.get("open_time")),
                "open": float(row.get("open") or 0.0),
                "high": float(row.get("high") or 0.0),
                "low": float(row.get("low") or 0.0),
                "close": float(row.get("close") or 0.0),
                "volume": float(row.get("volume") or 0.0),
            })
        return candles

    def _open_position(self, payload: dict[str, Any], signal: dict[str, Any], symbol: str, interval: str, mode: str, direction: str, confidence: float, frame: pd.DataFrame, idx: int, max_hold_bars: int, capital: float, risk_pct: float) -> SimPosition:
        candle = frame.iloc[idx]
        entry = float(_num(signal.get("entry_price"), float(candle["close"])) or float(candle["close"]))
        fallback_risk = entry * (0.01 if "SCALP" in mode else 0.025)
        if direction == "BUY":
            stop = float(_num(signal.get("stop_loss"), entry - fallback_risk) or (entry - fallback_risk))
            take = float(_num(signal.get("take_profit"), entry + abs(entry - stop) * 2.0) or (entry + abs(entry - stop) * 2.0))
            if stop >= entry:
                stop = entry - fallback_risk
            if take <= entry:
                take = entry + abs(entry - stop) * 2.0
        else:
            stop = float(_num(signal.get("stop_loss"), entry + fallback_risk) or (entry + fallback_risk))
            take = float(_num(signal.get("take_profit"), entry - abs(stop - entry) * 2.0) or (entry - abs(stop - entry) * 2.0))
            if stop <= entry:
                stop = entry + fallback_risk
            if take >= entry:
                take = entry - abs(stop - entry) * 2.0
        risk_amount = capital * (risk_pct / 100.0)
        risk_per_unit = max(1e-12, abs(entry - stop))
        qty = risk_amount / risk_per_unit
        max_exit_index = min(len(frame) - 1, idx + max(1, max_hold_bars))
        return SimPosition(
            trade_id=f"sim-{symbol}-{interval}-{mode}-{_iso(candle['open_time']).replace(':', '').replace('-', '')}",
            symbol=symbol,
            interval=interval,
            mode=mode,
            direction=direction,
            confidence=confidence,
            entry_price=entry,
            stop_loss=stop,
            take_profit=take,
            quantity=qty,
            notional=qty * entry,
            risk_amount=risk_amount,
            opened_at=candle["open_time"],
            max_exit_index=max_exit_index,
            engine_summary=str(signal.get("summary") or "engine signal"),
        )

    def _settle_position(self, pos: SimPosition, frame: pd.DataFrame, start_idx: int, *, step_bars: int = 1, fee_bps: float = 0.0, slippage_bps: float = 0.0) -> dict[str, Any]:
        exit_price = float(frame.iloc[pos.max_exit_index]["close"])
        exit_at = frame.iloc[pos.max_exit_index]["close_time"]
        exit_reason = "time_stop"
        status = "CLOSED"
        close_index = pos.max_exit_index
        for idx in range(start_idx, pos.max_exit_index + 1, max(1, step_bars)):
            row = frame.iloc[idx]
            high = float(row["high"])
            low = float(row["low"])
            if pos.direction == "BUY":
                if low <= pos.stop_loss:
                    exit_price = pos.stop_loss
                    exit_at = row["close_time"]
                    exit_reason = "stop_loss"
                    status = "STOPPED_OUT"
                    close_index = idx
                    break
                if high >= pos.take_profit:
                    exit_price = pos.take_profit
                    exit_at = row["close_time"]
                    exit_reason = "take_profit"
                    close_index = idx
                    break
            else:
                if high >= pos.stop_loss:
                    exit_price = pos.stop_loss
                    exit_at = row["close_time"]
                    exit_reason = "stop_loss"
                    status = "STOPPED_OUT"
                    close_index = idx
                    break
                if low <= pos.take_profit:
                    exit_price = pos.take_profit
                    exit_at = row["close_time"]
                    exit_reason = "take_profit"
                    close_index = idx
                    break
        slip = slippage_bps / 10_000.0
        effective_entry = pos.entry_price * (1.0 + slip if pos.direction == "BUY" else 1.0 - slip)
        effective_exit = exit_price * (1.0 - slip if pos.direction == "BUY" else 1.0 + slip)
        gross_pnl = (effective_exit - effective_entry) * pos.quantity if pos.direction == "BUY" else (effective_entry - effective_exit) * pos.quantity
        fees = (abs(effective_entry * pos.quantity) + abs(effective_exit * pos.quantity)) * (fee_bps / 10_000.0)
        pnl = gross_pnl - fees
        pnl_pct = (pnl / max(1e-12, abs(effective_entry * pos.quantity))) * 100.0
        return {
            "symbol": pos.symbol,
            "interval": pos.interval,
            "mode": pos.mode,
            "direction": pos.direction,
            "confidence": pos.confidence,
            "outcome": "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAKEVEN",
            "realized_r": pnl / pos.risk_amount if pos.risk_amount else None,
            "details": {
                "trade_id": pos.trade_id,
                "symbol": pos.symbol,
                "direction": pos.direction,
                "mode": pos.mode,
                "interval": pos.interval,
                "entry_price": pos.entry_price,
                "exit_price": exit_price,
                "effective_entry_price": effective_entry,
                "effective_exit_price": effective_exit,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "confidence": pos.confidence,
                "hold_time_hours": _hours_between(pos.opened_at, exit_at),
                "status": status,
                "opened_at": _iso(pos.opened_at),
                "closed_at": _iso(exit_at),
                "stop_reason": exit_reason if status == "STOPPED_OUT" else None,
                "entry_reason": "engine_signal",
                "exit_reason": exit_reason,
                "risk_amount": pos.risk_amount,
                "notional": pos.notional,
                "fees": fees,
                "fee_bps": fee_bps,
                "slippage_bps": slippage_bps,
                "time_forward_step_bars": step_bars,
                "engine_summary": pos.engine_summary,
                "close_index": close_index,
            },
        }

    def _finalize(self, payload: dict[str, Any], capital: float, equity_points: list[float], trades: list[dict[str, Any]], per_mode: dict[str, dict[str, float]], skip_counts: Counter[str], skip_samples: list[dict[str, Any]], stages: list[dict[str, str]], status: str, completed_tasks: int, total_tasks: int, start: datetime, end: datetime, htf_metrics: dict[str, Any] | None = None, perf: SimulationPerf | None = None) -> dict[str, Any]:
        closed = len(trades)
        wins = sum(1 for trade in trades if float((trade.get("details") or {}).get("pnl") or 0.0) > 0)
        total_pnl = sum(float((trade.get("details") or {}).get("pnl") or 0.0) for trade in trades)
        returns = [((equity_points[i] - equity_points[i - 1]) / max(1.0, equity_points[i - 1])) for i in range(1, len(equity_points))]
        avg = sum(returns) / len(returns) if returns else 0.0
        variance = sum((r - avg) ** 2 for r in returns) / len(returns) if returns else 0.0
        sharpe = (avg / math.sqrt(variance) * math.sqrt(len(returns))) if variance > 0 else None
        max_dd = self._max_drawdown_pct(equity_points)
        total_skips = sum(skip_counts.values()) or 1
        execution_settings = dict(payload.get("execution_settings") or {})
        resolved_time_forward_step_bars = max(1, int(self._number_setting(payload, execution_settings, ["time_forward_step_bars", "SIMULATION_TIME_FORWARD_STEP_BARS", "TIME_FORWARD_STEP_BARS"], 1) or 1))
        htf_metrics = dict(htf_metrics or {})
        htf_missing_by_symbol = dict(htf_metrics.get("missing_by_symbol") or {})
        htf_missing_by_interval = dict(htf_metrics.get("missing_by_interval") or {})
        reproducibility = dict(payload.get("reproducibility") or {})
        reproducibility.update({
            "candle_source_summary": {
                "symbols": payload.get("symbols") or [],
                "intervals": payload.get("intervals") or [],
                "period_start": start.date().isoformat(),
                "period_end": end.date().isoformat(),
                "source": "historical_loader_binance_or_cache",
            },
            "htf_context_summary": {
                "requested": int(htf_metrics.get("requested") or 0),
                "available": int(htf_metrics.get("available") or 0),
                "missing": int(htf_metrics.get("missing") or 0),
                "missing_by_symbol": htf_missing_by_symbol,
                "missing_by_interval": htf_missing_by_interval,
            },
        })
        perf_payload = perf.payload() if perf is not None else {}
        metrics = {
            "period_start": start.date().isoformat(),
            "period_end": end.date().isoformat(),
            "symbol_count": len(payload.get("symbols") or []),
            "symbols": payload.get("symbols") or [],
            "intervals": payload.get("intervals") or [],
            "modes": payload.get("modes") or [],
            "capital": capital,
            "scan_workers": int(payload.get("scan_workers") or 4),
            "worker_count_requested": int(self._number_setting(payload, execution_settings, ["scan_workers", "AUTONOMOUS_SCAN_WORKERS", "SCAN_WORKERS"], 1) or 1),
            "worker_count_effective": 1,
            "tasks_submitted": total_tasks,
            "tasks_completed": completed_tasks,
            "tasks_cancelled": 0,
            "worker_errors": [],
            "parallel_execution_enabled": False,
            "time_forward_step_bars": resolved_time_forward_step_bars,
            "simulation_profile_id": payload.get("simulation_profile_id"),
            "simulation_profile": payload.get("simulation_profile") or {},
            "execution_settings": execution_settings,
            "performance_diagnostics": perf_payload,
            "reproducibility": reproducibility,
            "htf_context_requested_count": int(htf_metrics.get("requested") or 0),
            "htf_context_available_count": int(htf_metrics.get("available") or 0),
            "htf_context_missing_count": int(htf_metrics.get("missing") or 0),
            "htf_context_missing_by_symbol": htf_missing_by_symbol,
            "htf_context_missing_by_interval": htf_missing_by_interval,
            "progress_pct": 100 if status in {"COMPLETED", "STOPPED"} else round((completed_tasks / max(1, total_tasks)) * 100),
            "current_sim_date": None,
            "time_elapsed_h": round(_hours_between(start, end), 2),
            "time_remaining_h": 0,
            "total_pnl": total_pnl,
            "total_pnl_pct": (total_pnl / capital * 100.0) if capital else None,
            "win_rate": (wins / closed * 100.0) if closed else 0.0,
            "trade_count": closed,
            "open_trade_count": 0,
            "closed_trade_count": closed,
            "max_drawdown_pct": max_dd,
            "sharpe_ratio": sharpe,
            "avg_hold_time_h": (sum(float((t.get("details") or {}).get("hold_time_hours") or 0.0) for t in trades) / closed) if closed else None,
            "stages": stages,
            "skip_breakdown": [{"key": k, "count": v, "pct": round(v / total_skips * 100)} for k, v in skip_counts.items()],
            "skip_samples": skip_samples,
            "equity_curve": self._normalize_curve(equity_points),
            "per_mode": [
                {"mode": mode, "pnl": row["pnl"], "trades": int(row["trades"]), "winRate": round((row["wins"] / row["trades"] * 100.0) if row["trades"] else 0.0, 1)}
                for mode, row in per_mode.items()
            ],
            "alerts": [] if status == "COMPLETED" else [{"tone": "warning", "title": "Simulation stopped", "message": "The run was stopped before completion."}],
        }
        return {"status": status, "metrics": metrics, "results": trades}

    @staticmethod
    def _default_hold_bars(interval: str, mode: str) -> int:
        mode = mode.upper()
        if "SCALP" in mode:
            return 8
        if mode == "SWING":
            return 12
        return 10

    @staticmethod
    def _max_drawdown_pct(points: list[float]) -> float | None:
        if not points:
            return None
        peak = points[0]
        max_dd = 0.0
        for point in points:
            peak = max(peak, point)
            if peak > 0:
                max_dd = min(max_dd, (point - peak) / peak * 100.0)
        return max_dd

    @staticmethod
    def _normalize_curve(points: list[float], count: int = 20) -> list[float]:
        if not points:
            return [50.0] * count
        if len(points) == 1:
            return [50.0] * count
        min_v = min(points)
        max_v = max(points)
        span = max(max_v - min_v, 1e-9)
        sampled = []
        for i in range(count):
            idx = round(i * (len(points) - 1) / max(1, count - 1))
            sampled.append(round(40.0 + ((points[idx] - min_v) / span) * 60.0, 2))
        return sampled
