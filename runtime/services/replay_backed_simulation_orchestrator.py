"""Runtime-side replay orchestration with simulation-owned settlement truth."""

from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter
from typing import Any, Callable

import pandas as pd

from runtime.services.historical_simulation_engine import (
    HistoricalSimulationEngine,
    SimPosition,
    SimulationPerf,
    _iso,
    _num,
    _parse_dt,
    _stage,
)
from runtime.services.runtime_replay_input_mapper import RuntimeReplayInputMapper
from runtime.services.simulation_output_result_materializer import (
    SimulationOutputResultMaterializer,
)
from simulation.adapters.replay_driver import ReplayDriver


class ReplayBackedSimulationOrchestrator(HistoricalSimulationEngine):
    """Historical replay orchestration that delegates settlement to ReplayDriver."""

    def __init__(
        self,
        candle_loader=None,
        analyzer: Any | None = None,
        snapshot_builder=None,
        replay_driver: ReplayDriver | None = None,
        input_mapper: RuntimeReplayInputMapper | None = None,
        result_materializer: SimulationOutputResultMaterializer | None = None,
    ) -> None:
        super().__init__(
            candle_loader=candle_loader,
            analyzer=analyzer,
            snapshot_builder=snapshot_builder,
        )
        self.replay_driver = replay_driver or ReplayDriver()
        self.input_mapper = input_mapper or RuntimeReplayInputMapper()
        self.result_materializer = result_materializer or SimulationOutputResultMaterializer()

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
        min_confidence = self._number_setting(
            payload,
            execution_settings,
            ["min_confidence", "AUTONOMOUS_MIN_CONFIDENCE", "MIN_CONFIDENCE"],
            55.0,
        ) or 55.0
        scan_step_bars = max(
            1,
            int(
                self._number_setting(
                    payload,
                    execution_settings,
                    ["scan_step_bars", "SIMULATION_SCAN_STEP_BARS", "SCAN_STEP_BARS"],
                    1,
                )
                or 1
            ),
        )
        max_hold_bars_payload = self._setting(
            payload,
            execution_settings,
            ["max_hold_bars", "SIMULATION_MAX_HOLD_BARS", "MAX_HOLD_BARS"],
            None,
        )
        record_htf_availability = self._bool_setting(
            self._setting(
                payload,
                execution_settings,
                ["record_htf_availability", "SIMULATION_RECORD_HTF_AVAILABILITY"],
                True,
            ),
            True,
        )
        require_htf_context = self._bool_setting(
            self._setting(
                payload,
                execution_settings,
                ["require_htf_context", "SIMULATION_REQUIRE_HTF_CONTEXT"],
                False,
            ),
            False,
        )
        perf = SimulationPerf()
        requested_workers = max(
            1,
            int(
                self._number_setting(
                    payload,
                    execution_settings,
                    ["scan_workers", "AUTONOMOUS_SCAN_WORKERS", "SCAN_WORKERS"],
                    1,
                )
                or 1
            ),
        )
        max_workers = max(
            1,
            int(
                self._number_setting(
                    payload,
                    execution_settings,
                    ["max_scan_workers", "SIMULATION_MAX_SCAN_WORKERS", "MAX_SCAN_WORKERS"],
                    4,
                )
                or 4
            ),
        )
        effective_workers = min(
            requested_workers,
            max_workers,
            max(1, len(symbols) * len(intervals) * len(modes)),
        )
        if effective_workers > 1:
            return self._run_parallel_replay(
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

        from runtime.runtime.htf import resolve_htf_interval
        from runtime.services.incremental_indicators import extract_snapshot, precompute_all_indicators

        for symbol in symbols:
            for interval in intervals:
                try:
                    with perf.measure("candle_load", detail={"symbol": symbol, "interval": interval}):
                        frame = self.candle_loader.load(symbol, interval, start, end)
                except Exception as exc:
                    skip_counts["data_error"] += len(modes)
                    for mode in modes:
                        self._record_skip_sample(
                            skip_samples,
                            reason="data_error",
                            symbol=symbol,
                            interval=interval,
                            mode=mode,
                            timestamp=start.isoformat(),
                            message=str(exc),
                        )
                    if progress_callback is not None:
                        progress_callback(
                            {
                                "event_type": "data_error",
                                "progress_pct": round((completed_tasks / max(1, total_tasks)) * 100),
                                "symbol": symbol,
                                "interval": interval,
                                "message": str(exc),
                                "skip_breakdown": [{"key": k, "count": v} for k, v in skip_counts.items()],
                            }
                        )
                    continue
                if len(frame) < 8:
                    skip_counts["insufficient_history"] += len(modes)
                    for mode in modes:
                        self._record_skip_sample(
                            skip_samples,
                            reason="insufficient_history",
                            symbol=symbol,
                            interval=interval,
                            mode=mode,
                            timestamp=start.isoformat(),
                            message=f"Only {len(frame)} candles available",
                        )
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
                with perf.measure("precompute_indicators"):
                    self._indicator_frame = precompute_all_indicators(frame)
                for mode in modes:
                    if stop_checker and stop_checker():
                        return self._finalize(
                            payload,
                            capital,
                            equity_points,
                            trades,
                            per_mode,
                            skip_counts,
                            skip_samples,
                            stages,
                            "STOPPED",
                            completed_tasks,
                            total_tasks,
                            start,
                            end,
                            htf_metrics,
                            perf,
                        )
                    default_hold = self._default_hold_bars(interval, mode)
                    max_hold_bars = int(max_hold_bars_payload or default_hold)
                    for idx in range(warmup, len(frame) - 1, scan_step_bars):
                        if stop_checker and stop_checker():
                            return self._finalize(
                                payload,
                                capital,
                                equity_points,
                                trades,
                                per_mode,
                                skip_counts,
                                skip_samples,
                                stages,
                                "STOPPED",
                                completed_tasks,
                                total_tasks,
                                start,
                                end,
                                htf_metrics,
                                perf,
                            )
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
                                    self._record_skip_sample(
                                        skip_samples,
                                        reason="htf_data_error",
                                        symbol=symbol,
                                        interval=interval,
                                        mode=mode,
                                        timestamp=timestamp,
                                        message=htf_load_error,
                                    )
                                    continue
                            else:
                                with perf.measure("htf_window_align"):
                                    htf_window = self._htf_window(htf_frame, timestamp)
                                if htf_window is None or htf_window.empty:
                                    self._mark_htf_missing(htf_metrics, symbol, htf_interval)
                                    htf_status["missing_reason"] = "insufficient_htf_history"
                                    if require_htf_context:
                                        skip_counts["insufficient_htf_history"] += 1
                                        self._record_skip_sample(
                                            skip_samples,
                                            reason="insufficient_htf_history",
                                            symbol=symbol,
                                            interval=interval,
                                            mode=mode,
                                            timestamp=timestamp,
                                            message=f"No aligned {htf_interval} candles available",
                                        )
                                        continue
                                else:
                                    htf_metrics["available"] += 1
                                    htf_status["available"] = True
                        try:
                            with perf.measure(
                                "analyzer",
                                detail={"symbol": symbol, "interval": interval, "mode": mode, "timestamp": timestamp},
                            ):
                                analysis = self._analyze_window(
                                    symbol=symbol,
                                    interval=interval,
                                    mode=mode,
                                    frame=frame,
                                    idx=idx,
                                    htf_interval=htf_interval,
                                    htf_window=htf_window,
                                )
                        except Exception as exc:
                            skip_counts["analysis_error"] += 1
                            self._record_skip_sample(
                                skip_samples,
                                reason="analysis_error",
                                symbol=symbol,
                                interval=interval,
                                mode=mode,
                                timestamp=timestamp,
                                message=str(exc),
                            )
                            self._emit_trace(
                                trace_callback,
                                self._build_decision_trace(
                                    symbol=symbol,
                                    interval=interval,
                                    mode=mode,
                                    timestamp=timestamp,
                                    analysis={},
                                    signal={},
                                    runtime_filter_reason="analysis_error",
                                    skip_family="error",
                                    analysis_error=str(exc),
                                    htf_status=htf_status,
                                ),
                            )
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
                        snapshot = extract_snapshot(self._indicator_frame, idx)
                        future_frame = frame.iloc[idx + 1 : idx + 1 + max_hold_bars].reset_index(drop=True)
                        position = self._open_position(payload, signal, symbol, interval, mode, direction, confidence, frame, idx, max_hold_bars, capital, risk_pct)
                        with perf.measure("trade_settlement", detail={"symbol": symbol, "interval": interval, "mode": mode, "timestamp": timestamp}):
                            settled = self._simulate_actionable_decision(
                                payload=payload,
                                signal=signal,
                                snapshot=snapshot,
                                position=position,
                                symbol=symbol,
                                interval=interval,
                                mode=mode,
                                timestamp=timestamp,
                                future_frame=future_frame,
                                execution_settings=execution_settings,
                            )
                        relative_close_index = settled.get("details", {}).get("close_index")
                        if isinstance(relative_close_index, int):
                            blocked_until[open_key] = idx + 1 + relative_close_index
                        else:
                            blocked_until[open_key] = idx
                        trades.append(settled)
                        if progress_callback is not None:
                            progress_callback(
                                {
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
                                }
                            )
                        equity_points.append(equity_points[-1] + float(settled.get("details", {}).get("pnl") or settled.get("pnl") or 0.0))
                        bucket = per_mode[mode]
                        bucket["pnl"] += float(settled.get("details", {}).get("pnl") or settled.get("pnl") or 0.0)
                        bucket["trades"] += 1
                        if float(settled.get("details", {}).get("pnl") or settled.get("pnl") or 0.0) > 0:
                            bucket["wins"] += 1
                    completed_tasks += 1
                    if progress_callback is not None:
                        progress_callback(
                            {
                                "event_type": "task_completed",
                                "progress_pct": round((completed_tasks / max(1, total_tasks)) * 100),
                                "current_sim_date": _iso(frame.iloc[min(len(frame) - 1, idx)]["open_time"]),
                                "trade_count": len(trades),
                                "closed_trade_count": len(trades),
                                "open_trade_count": 0,
                                "stages": stages,
                            }
                        )

        stages[1] = _stage("scan_replay", "Historical scan replay", "DONE", f"{completed_tasks} replay tasks complete")
        stages[2] = _stage("trade_calc", "Time-forward trade calc", "DONE", f"{len(trades)} trades settled")
        stages[3] = _stage("pnl_attr", "P&L attribution", "DONE", "complete")
        return self._finalize(payload, capital, equity_points, trades, per_mode, skip_counts, skip_samples, stages, "COMPLETED", completed_tasks, total_tasks, start, end, htf_metrics, perf)

    def _run_parallel_replay(
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
        start,
        end,
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
            worker = ReplayBackedSimulationOrchestrator(
                candle_loader=self.candle_loader,
                analyzer=None if self.analyzer is None else self.analyzer,
                snapshot_builder=self.snapshot_builder,
                replay_driver=self.replay_driver,
                input_mapper=self.input_mapper,
                result_materializer=self.result_materializer,
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
            trades = sorted(trades, key=lambda row: (str((row.get("details") or {}).get("opened_at") or ""), str(row.get("symbol") or ""), str(row.get("interval") or ""), str(row.get("mode") or ""), str((row.get("details") or {}).get("simulation_run_id") or "")))
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

    def _simulate_actionable_decision(
        self,
        *,
        payload: dict[str, Any],
        signal: dict[str, Any],
        snapshot: dict[str, Any],
        position: SimPosition,
        symbol: str,
        interval: str,
        mode: str,
        timestamp: str,
        future_frame: pd.DataFrame,
        execution_settings: dict[str, Any],
    ) -> dict[str, Any]:
        sim_input = self.input_mapper.build_input(
            symbol=symbol,
            interval=interval,
            mode=mode,
            timestamp=timestamp,
            signal=signal,
            snapshot=snapshot,
            future_frame=future_frame,
            simulation_profile=dict(payload.get("simulation_profile") or {}),
            execution_settings=execution_settings,
        )
        sim_output = self.replay_driver.run(sim_input)
        closed_at = timestamp
        relative_close_index = None
        if position.direction == "BUY":
            relative_close_index = sim_output.long_outcome.exit_bar_index
        elif position.direction == "SELL":
            relative_close_index = sim_output.short_outcome.exit_bar_index
        if isinstance(relative_close_index, int) and 0 <= relative_close_index < len(sim_input.future_path.candles):
            closed_at = sim_input.future_path.candles[relative_close_index].close_time_utc
        return self.result_materializer.to_runtime_result(
            sim_output=sim_output,
            selected_direction=position.direction,
            quantity_context={
                "risk_amount": position.risk_amount,
                "quantity": position.quantity,
                "entry_price": position.entry_price,
                "notional": position.notional,
                "stop_loss": position.stop_loss,
                "take_profit": position.take_profit,
            },
            run_context={
                "symbol": symbol,
                "interval": interval,
                "mode": mode,
                "confidence": position.confidence,
                "opened_at": _iso(position.opened_at),
                "closed_at": closed_at,
                "created_at_utc": closed_at,
                "entry_reason": "engine_signal",
                "engine_summary": position.engine_summary,
                "fee_bps": self._number_setting(payload, execution_settings, ["fee_bps", "SIMULATION_FEE_BPS", "FEE_BPS"], 4.0) or 4.0,
                "slippage_bps": self._number_setting(payload, execution_settings, ["slippage_bps", "SIMULATION_SLIPPAGE_BPS", "SLIPPAGE_BPS"], 1.0) or 1.0,
                "time_forward_step_bars": self._number_setting(payload, execution_settings, ["time_forward_step_bars", "SIMULATION_TIME_FORWARD_STEP_BARS", "TIME_FORWARD_STEP_BARS"], 1) or 1,
                "entry_price": position.entry_price,
            },
        )
