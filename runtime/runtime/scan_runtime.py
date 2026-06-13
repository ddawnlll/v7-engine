"""Manual and autonomous scan runtime for v4."""

from __future__ import annotations

import time
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from threading import Event, Lock
from typing import Any

from runtime.db.repos._helpers import dumps_json, dumps_list
from runtime.db.repos.order_repo import OrderRepository
from runtime.db.repos.scan_repo import ScanRepository
from runtime.db.repos.settings_repo import DEFAULT_RUNTIME_SETTINGS, SettingsRepository
from runtime.db.repos.signal_repo import SignalRepository
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.db.session import session_scope
from runtime.runtime.execution_orchestrator import (
    ExecutionOrchestrator,
    ExecutionPolicyViolationError,
    PaperExecutionAdapter,
    UnsupportedExecutionProfileError,
)
from runtime.runtime.inference_bus import (
    InferenceBus,
    InferenceJobFailedError,
    InferenceJobOutcome,
    InferenceJobRejectedError,
    InferenceJobTimedOutError,
    get_shared_inference_bus,
)
from runtime.runtime.scan_control import ScanControlService
from runtime.runtime.scan_event_bus import get_scan_event_bus
from runtime.runtime.market_data import MarketDataRuntime
from runtime.runtime.paper_execution import PaperExecutionService
from runtime.services.analyzer_engine_adapter import AnalyzerEngineAdapter
from runtime.services.audit_service import AuditService
from runtime.services.binance_client import BinanceBadSymbolError
from runtime.services.decision_attribution_service import DecisionAttributionService
from runtime.services.engine_manifest_service import EngineManifestService
from runtime.services.binance_usdm_manual_live_service import BinanceUsdmManualLiveError
from runtime.services.improvement_registry_service import ImprovementRegistryService
from runtime.services.performance_service import PerformanceService
from runtime.services.signal_features import build_signal_feature_vector
from runtime.services.trace_service import TraceService
from runtime.services.trend_service import determine_trend
from runtime.services.universe_filter_service import UniverseFilterService
from runtime.services.runtime_profile_service import RuntimeProfileAccessError, RuntimeProfileConnectivityError
from runtime.runtime.htf import HTF_MAP
from v6.contracts.analysis_request import ExecutionContextSection, RuntimeContextSection
from v6.contracts.analysis_result import AnalysisResult as V6AnalysisResult
from v6.contracts.compat import to_v5_request
from v6.contracts.enums import EngineMode, RequestKind
from v6.runtime.fallback_handler import FallbackHandler
from v6.runtime.request_assembler import build_analysis_request
from v6.snapshot.builder import UnifiedSnapshotBuilder
from v6.snapshot.modes import SnapshotMode

DEGRADED_ERROR_RATE_THRESHOLD = 0.70
WAIT_DEBUG_HEARTBEAT_SECONDS = 5.0


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ScanRuntime:
    def __init__(
        self,
        market_data: MarketDataRuntime | None = None,
        scan_repo: ScanRepository | None = None,
        signal_repo: SignalRepository | None = None,
        settings_repo: SettingsRepository | None = None,
        order_repo: OrderRepository | None = None,
        paper_execution: PaperExecutionService | None = None,
        execution_orchestrator: ExecutionOrchestrator | None = None,
        scan_control: ScanControlService | None = None,
        inference_bus: InferenceBus | None = None,
        scan_event_publisher=None,
    ) -> None:
        self.market_data = market_data or MarketDataRuntime()
        self.scan_repo = scan_repo or ScanRepository()
        self.signal_repo = signal_repo or SignalRepository()
        self.settings_repo = settings_repo or SettingsRepository()
        self.order_repo = order_repo or OrderRepository()
        self.scan_control = scan_control or ScanControlService()
        resolved_paper_execution = paper_execution or PaperExecutionService(
            order_repo=self.order_repo,
            signal_repo=self.signal_repo,
        )
        self.execution_orchestrator = execution_orchestrator or ExecutionOrchestrator(
            paper_adapter=PaperExecutionAdapter(resolved_paper_execution),
            order_repo=self.order_repo,
        )
        self.paper_execution = self.execution_orchestrator.paper_execution
        self.engine_adapter = AnalyzerEngineAdapter()
        self.snapshot_builder = UnifiedSnapshotBuilder()
        self.fallback_handler = FallbackHandler()
        self.trace_service = TraceService()
        self.performance_service = PerformanceService(order_repo=self.order_repo)
        self.audit_service = AuditService()
        self.registry_service = ImprovementRegistryService()
        self.inference_bus = inference_bus or get_shared_inference_bus(
            max_queue_size=int(DEFAULT_RUNTIME_SETTINGS.get("AUTONOMOUS_INFERENCE_QUEUE_SIZE", "64")),
        )
        self.scan_event_publisher = scan_event_publisher or get_scan_event_bus().publish
        self.manifest_service = EngineManifestService(self.registry_service)
        self.attribution_service = DecisionAttributionService(self.registry_service)
        self.universe_filter_service = UniverseFilterService(self.settings_repo)
        self._active_universe_filters: dict[str, dict[str, Any]] = {}
        self._active_run_contexts: dict[str, dict[str, Any]] = {}
        self._active_run_context_lock = Lock()

    def _emit_scan_event(self, event_type: str, *, profile_id: str, run_id: str, **payload: Any) -> None:
        try:
            lightweight = {
                "type": event_type,
                "timestamp": utc_now_iso(),
                "profile_id": profile_id,
                "run_id": run_id,
                **{key: value for key, value in payload.items() if value is not None},
            }
            self.scan_event_publisher(lightweight)
        except Exception:
            return

    def force_stop_active_run(self, requested_by: str = "interface", *, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any]:
        resolved_profile_id = str(profile_id or PAPER_PROFILE_ID)
        state = self.scan_control.request_force_stop(requested_by=requested_by, profile_id=resolved_profile_id)
        context: dict[str, Any] | None = None
        with self._active_run_context_lock:
            active_context = self._active_run_contexts.get(resolved_profile_id)
            if active_context is not None:
                context = dict(active_context)
                force_stop_event = context.get("force_stop_event")
                if isinstance(force_stop_event, Event):
                    force_stop_event.set()
                active_context["force_stop_requested_by"] = requested_by

        affected_run_id = str(state.get("active_run_id") or "").strip()
        if context is not None:
            for future in list(context.get("fetch_futures") or []):
                try:
                    future.cancel()
                except Exception:
                    pass
            for future in list(context.get("analysis_futures") or []):
                try:
                    future.cancel()
                except Exception:
                    pass
            for executor in (context.get("fetch_executor"), context.get("analysis_executor")):
                try:
                    if executor is not None:
                        executor.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass
            context_run_id = str(context.get("run_id") or "").strip()
            if context_run_id:
                affected_run_id = context_run_id
        return {
            "state": state,
            "affected_run_id": affected_run_id or None,
            "aborted": context is not None,
            "profile_id": resolved_profile_id,
        }

    def run_scan(
        self,
        symbols: list[str],
        intervals: list[str],
        modes: list[str],
        requested_by: str = "api",
        *,
        scan_workers: int | None = None,
        mode_intervals: dict[str, list[str]] | None = None,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict[str, Any]:
        created_at = utc_now_iso()
        run_id = f"scan-{uuid.uuid4().hex[:10]}"
        profile_id = str(profile_id or PAPER_PROFILE_ID)
        settings_resolution = self._load_settings_resolution(profile_id=profile_id)
        settings = dict(settings_resolution.get("settings") or {})
        resolved_config_hash = str(settings_resolution.get("resolved_config_hash") or "")
        resolved_workers = self._resolve_scan_workers(scan_workers, settings)
        self.inference_bus.configure(
            max_workers=self._resolve_inference_workers(settings),
            max_queue_size=self._resolve_inference_queue_size(settings),
        )
        min_confidence, confidence_policy = self._resolve_runtime_min_confidence(settings, profile_id=profile_id)
        allowed_trade_directions = self._resolve_allowed_trade_directions(settings)
        post_scan_confidence_ranked_entry_enabled = self._is_post_scan_confidence_ranked_entry_enabled(settings)
        max_trades_per_day = max(1, int(self._resolve_float(settings.get("MAX_TRADES_PER_DAY"), 5)))
        fetch_timeout_seconds = max(
            1.0,
            float(self._resolve_float(settings.get("SCAN_FETCH_TIMEOUT_SECONDS"), float(DEFAULT_RUNTIME_SETTINGS["SCAN_FETCH_TIMEOUT_SECONDS"]))),
        )
        universe_filter = self.universe_filter_service.evaluate(symbols, profile_id=profile_id)
        throttled_symbols = {
            str(item.get("symbol") or "").upper()
            for item in universe_filter.get("throttled_symbols") or []
            if item.get("throttled")
        }
        original_symbol_count = len(symbols)
        original_interval_count = len(intervals)
        original_mode_count = len(modes)
        unique_symbols = list(dict.fromkeys(symbols))
        unique_intervals = list(dict.fromkeys(intervals))
        unique_modes = list(dict.fromkeys(modes))
        symbols = unique_symbols
        intervals = unique_intervals
        modes = unique_modes
        active_symbols = [symbol for symbol in symbols if str(symbol).upper() not in throttled_symbols]
        daily_trades = self._count_daily_trades(profile_id=profile_id)
        mode_interval_sets = self._normalize_mode_intervals(intervals, modes, mode_intervals)
        allowed_mode_pairs = [
            (interval, mode)
            for interval in intervals
            for mode in modes
            if interval in mode_interval_sets.get(str(mode).upper(), set())
        ]
        total_tasks = len(symbols) * len(allowed_mode_pairs)
        throttled_task_count = (len(symbols) - len(active_symbols)) * len(allowed_mode_pairs)
        completed_tasks = throttled_task_count
        skipped = {
            "neutral": 0,
            "low_confidence": 0,
            "missing_levels": 0,
            "long_disabled_by_runtime": 0,
            "short_disabled_by_runtime": 0,
            "duplicate_open": 0,
            "insufficient_balance": 0,
            "auto_order_rejected": 0,
            "market_unavailable": 0,
            "daily_cap_reached": 0,
            "symbol_throttled": throttled_task_count,
            "errors": 0,
        }
        skip_stage_counts: dict[str, int] = {}
        if throttled_task_count > 0:
            skip_stage_counts["UNIVERSE_FILTER"] = throttled_task_count
        created_orders = 0
        order_queue_state = {"submitted": 0, "pending": 0, "verified": 0, "pending_verification": 0}
        cap_reached = False
        scanned = total_tasks
        signals: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        stale_tasks = 0
        final_status = "COMPLETED"
        analysis_durations_ms: list[float] = []
        fetch_durations_ms: list[float] = []
        post_scan_entry_candidates: list[dict[str, Any]] = []
        debug_state: dict[str, Any] = {
            "last_progress_reason": "symbols_throttled" if throttled_task_count > 0 else "scan_started",
            "last_progress_at_utc": created_at,
            "last_completed_task": None,
            "pending_fetch_count": 0,
            "pending_fetch_tasks": [],
            "oldest_pending_fetch_age_seconds": 0.0,
            "timed_out_fetch_tasks": [],
            "wait_heartbeats": 0,
            "fetch_timeout_seconds": fetch_timeout_seconds,
            "confidence_policy": dict(confidence_policy),
        }
        stage_metrics = self._new_stage_metrics()
        self._active_universe_filters[profile_id] = {
            **dict(universe_filter or {}),
            "requested_symbols": list(symbols),
            "active_symbols": list(active_symbols),
        }
        scope_diagnostics = {
            "requested_tasks_before_pruning": len(symbols) * len(intervals) * len(modes),
            "requested_symbols": len(symbols),
            "active_symbols": len(active_symbols),
            "throttled_symbols": len(throttled_symbols),
            "requested_intervals": len(intervals),
            "requested_modes": len(modes),
            "effective_intervals": 0,
            "allowed_mode_pairs": len(allowed_mode_pairs),
            "total_tasks": total_tasks,
            "effective_tasks": len(active_symbols) * len(allowed_mode_pairs),
            "fetch_tasks": 0,
            "estimated_bundle_requests_without_cache": 0,
            "estimated_unique_bundle_requests_with_cache": 0,
            "pruned_tasks": throttled_task_count,
            "pruned_by": {
                "universe_filter": throttled_task_count,
                "mode_interval_policy": max(0, (len(symbols) * len(intervals) * len(modes)) - total_tasks),
                "deduplicated_symbols": max(0, original_symbol_count - len(symbols)),
                "deduplicated_intervals": max(0, original_interval_count - len(intervals)),
                "deduplicated_modes": max(0, original_mode_count - len(modes)),
            },
        }

        with session_scope() as session:
            self.scan_repo.save_run(session, {
                "run_id": run_id,
                "profile_id": profile_id,
                "requested_by": requested_by,
                "status": "RUNNING",
                "symbols_csv": ",".join(symbols),
                "intervals_csv": ",".join(intervals),
                "modes_csv": ",".join(modes),
                "signal_count": 0,
                "summary": "Scan started",
                "error_text": None,
                "created_at_utc": created_at,
                "started_at_utc": created_at,
                "finished_at_utc": None,
                "payload_json": dumps_json({
                    "symbols": symbols,
                    "active_symbols": active_symbols,
                    "intervals": intervals,
                    "modes": modes,
                    "scan_workers": resolved_workers,
                }),
                "result_json": dumps_json(self._build_progress_payload(
                    profile_id=profile_id,
                    total_tasks=total_tasks,
                    completed_tasks=completed_tasks,
                    created_orders=created_orders,
                    daily_trades=daily_trades,
                    cap_reached=cap_reached,
                    scan_workers=resolved_workers,
                    skipped=skipped,
                    skip_stage_counts=skip_stage_counts,
                    signals=signals,
                    errors=errors,
                    stale_tasks=stale_tasks,
                    current_task=None,
                    analysis_durations_ms=analysis_durations_ms,
                    fetch_durations_ms=fetch_durations_ms,
                    debug=debug_state,
                    stage_metrics=stage_metrics,
                    scope_diagnostics=scope_diagnostics,
                )),
                "resolved_config_hash": resolved_config_hash,
            })
        self.manifest_service.create_run_manifest(
            run_id,
            engine_version="v4-phase23",
            enabled_components=self.registry_service.enabled_component_ids(),
            param_snapshot=self._manifest_param_snapshot(settings),
            feature_flags={
                "mode_interval_policy": {mode: sorted(values) for mode, values in mode_interval_sets.items()},
                "learning_enabled": True,
                "circuit_breaker_enabled": True,
                "symbol_throttle_enabled": bool(universe_filter.get("enabled")),
                "throttled_symbols": sorted(throttled_symbols),
                "self_learning_shadow_registered": "self_learning_shadow" in self.registry_service.enabled_component_ids(),
                "post_scan_confidence_ranked_entry_enabled": post_scan_confidence_ranked_entry_enabled,
            },
            runtime_mode=str(requested_by or "SCAN").upper(),
            symbol_scope=symbols,
            interval_scope=intervals,
            profile_id=profile_id,
            resolved_config_hash=resolved_config_hash,
        )
        self.scan_control.activate_run(run_id, requested_by, profile_id=profile_id)
        self.trace_service.log_event(
            "SCAN_STARTED",
            run_id=run_id,
            source=requested_by,
            status="RUNNING",
            decision="SCAN",
            reason_text="Scan started",
            details={"symbols": symbols, "intervals": intervals, "modes": modes, "scan_workers": resolved_workers},
            profile_id=profile_id,
        )
        self._emit_scan_event(
            "SCAN_STARTED",
            profile_id=profile_id,
            run_id=run_id,
            stage="STARTED",
            mode=requested_by,
            message="Scan started",
            total_tasks=total_tasks,
            completed_tasks=completed_tasks,
            queue_metrics=self.inference_bus.snapshot(),
        )
        for throttled in universe_filter.get("throttled_symbols") or []:
            self.trace_service.log_event(
                "SCAN_SKIPPED",
                run_id=run_id,
                source="SCAN",
                status="SKIPPED",
                decision="SKIP",
                reason_code="SYMBOL_THROTTLED",
                reason_text=str(throttled.get("reason") or "Symbol throttled by universe filter."),
                details=throttled,
                profile_id=profile_id,
            )
            self._emit_scan_event(
                "SCAN_SKIPPED",
                profile_id=profile_id,
                run_id=run_id,
                symbol=str(throttled.get("symbol") or "").upper(),
                stage="UNIVERSE_FILTER",
                reason_code="SYMBOL_THROTTLED",
                message=str(throttled.get("reason") or "Symbol throttled by universe filter."),
            )

        if self.scan_control.get_state(profile_id=profile_id).get("stop_requested"):
            self.scan_control.mark_stopping(run_id, None, completed_tasks=0, profile_id=profile_id)
            completed_at = utc_now_iso()
            summary = "Stopped before work began"
            result = {
                **self._build_progress_payload(
                    total_tasks=total_tasks,
                    completed_tasks=0,
                    created_orders=0,
                    daily_trades=daily_trades,
                    cap_reached=False,
                    scan_workers=resolved_workers,
                    skipped=skipped,
                    skip_stage_counts=skip_stage_counts,
                    signals=signals,
                    errors=errors,
                    stale_tasks=0,
                    current_task=None,
                    analysis_durations_ms=analysis_durations_ms,
                    fetch_durations_ms=fetch_durations_ms,
                    debug=debug_state,
                    stage_metrics=stage_metrics,
                    scope_diagnostics=scope_diagnostics,
                ),
                "scanned": scanned,
                "stopped": True,
            }
            return self._finalize_run(
                run_id,
                requested_by,
                symbols,
                intervals,
                modes,
                created_at=created_at,
                completed_at=completed_at,
                signal_count=len(signals),
                scan_workers=resolved_workers,
                summary=summary,
                result=result,
                errors=errors,
                final_status="STOPPED",
                trace_event="SCAN_STOPPED",
                profile_id=profile_id,
                resolved_config_hash=resolved_config_hash,
            )

        effective_intervals = [interval for interval in intervals if any(interval in mode_interval_sets.get(str(mode).upper(), set()) for mode in modes)]
        scope_diagnostics["effective_intervals"] = len(effective_intervals)
        interval_tasks = [(symbol, interval) for symbol in active_symbols for interval in effective_intervals]
        estimated_bundles = set(interval_tasks)
        estimated_total_bundle_requests = len(interval_tasks)
        for symbol, interval in interval_tasks:
            htf_interval = HTF_MAP.get(interval)
            if not htf_interval:
                continue
            estimated_total_bundle_requests += 1
            estimated_bundles.add((symbol, htf_interval))
        scope_diagnostics["fetch_tasks"] = len(interval_tasks)
        scope_diagnostics["estimated_bundle_requests_without_cache"] = estimated_total_bundle_requests
        scope_diagnostics["estimated_unique_bundle_requests_with_cache"] = len(estimated_bundles)
        max_fetch_workers = max(1, min(resolved_workers, len(interval_tasks) or 1))
        analysis_workers = self._resolve_analysis_workers(resolved_workers, settings)
        inference_snapshot = self.inference_bus.snapshot()
        stage_metrics["fetch_worker_capacity"] = max_fetch_workers
        stage_metrics["analysis_worker_capacity"] = analysis_workers
        stage_metrics["inference_worker_capacity"] = int(inference_snapshot.get("worker_capacity") or 1)
        stage_metrics["inference_queue_limit"] = int(inference_snapshot.get("queue_limit") or 0)
        market_bundle_cache: dict[tuple[str, str], dict[str, Any]] = {}
        market_bundle_inflight: dict[tuple[str, str], Event] = {}
        htf_trend_cache: dict[tuple[str, str], str | None] = {}
        cache_lock = Lock()
        analysis_inputs: list[dict[str, Any]] = []
        force_stop_event = Event()

        def force_stop_requested() -> bool:
            if force_stop_event.is_set():
                return True
            return bool(self.scan_control.get_state(profile_id=profile_id).get("force_stop_requested"))

        with self._active_run_context_lock:
            self._active_run_contexts[profile_id] = {
                "run_id": run_id,
                "force_stop_event": force_stop_event,
                "fetch_executor": None,
                "analysis_executor": None,
                "fetch_futures": set(),
                "analysis_futures": set(),
                "force_stop_requested_by": None,
            }

        initial_control_signal = self._honor_scan_control(
            run_id,
            requested_by,
            symbols,
            intervals,
            modes,
            profile_id=profile_id,
            total_tasks=total_tasks,
            completed_tasks=completed_tasks,
            created_orders=created_orders,
            daily_trades=daily_trades,
            cap_reached=cap_reached,
            scan_workers=resolved_workers,
            skipped=skipped,
            skip_stage_counts=skip_stage_counts,
            signals=signals,
            errors=errors,
            stale_tasks=stale_tasks,
            current_task=None,
            analysis_durations_ms=analysis_durations_ms,
            fetch_durations_ms=fetch_durations_ms,
            stage_metrics=stage_metrics,
            scope_diagnostics=scope_diagnostics,
        )
        if initial_control_signal == "stop":
            final_status = "STOPPED"
            completed_at = utc_now_iso()
            summary = f"Stopped before work began"
            result = {
                **self._build_progress_payload(
                    total_tasks=total_tasks,
                    completed_tasks=completed_tasks,
                    created_orders=created_orders,
                    daily_trades=daily_trades,
                    cap_reached=cap_reached,
                    scan_workers=resolved_workers,
                    skipped=skipped,
                    skip_stage_counts=skip_stage_counts,
                    signals=signals,
                    errors=errors,
                    stale_tasks=stale_tasks,
                    current_task=None,
                    analysis_durations_ms=analysis_durations_ms,
                    fetch_durations_ms=fetch_durations_ms,
                    debug=debug_state,
                    stage_metrics=stage_metrics,
                    scope_diagnostics=scope_diagnostics,
                ),
                "scanned": scanned,
                "stopped": True,
            }
            return self._finalize_run(
                run_id,
                requested_by,
                symbols,
                intervals,
                modes,
                created_at=created_at,
                completed_at=completed_at,
                signal_count=len(signals),
                scan_workers=resolved_workers,
                summary=summary,
                result=result,
                errors=errors,
                final_status=final_status,
                trace_event="SCAN_STOPPED",
                profile_id=profile_id,
                resolved_config_hash=resolved_config_hash,
            )

        executor = ThreadPoolExecutor(max_workers=max_fetch_workers, thread_name_prefix="scan-fetch")
        with self._active_run_context_lock:
            active_context = self._active_run_contexts.get(profile_id)
            if active_context and active_context.get("run_id") == run_id:
                active_context["fetch_executor"] = executor
        try:
            pending: dict[Future, dict[str, Any]] = {}
            task_index = 0
            last_debug_flush = time.monotonic()

            while task_index < len(interval_tasks) or pending:
                if force_stop_requested():
                    for future in pending:
                        future.cancel()
                    final_status = "STOPPED"
                    completed_at = utc_now_iso()
                    summary = f"Force-stopped after {completed_tasks}/{total_tasks} tasks"
                    result = {
                        **self._build_progress_payload(
                            total_tasks=total_tasks,
                            completed_tasks=completed_tasks,
                            created_orders=created_orders,
                            daily_trades=daily_trades,
                            cap_reached=cap_reached,
                            scan_workers=resolved_workers,
                            skipped=skipped,
                            skip_stage_counts=skip_stage_counts,
                            signals=signals,
                            errors=errors,
                            stale_tasks=stale_tasks,
                            current_task=None,
                            analysis_durations_ms=analysis_durations_ms,
                            fetch_durations_ms=fetch_durations_ms,
                            debug=debug_state,
                            stage_metrics=stage_metrics,
                            scope_diagnostics=scope_diagnostics,
                        ),
                        "scanned": scanned,
                        "stopped": True,
                        "force_stopped": True,
                    }
                    return self._finalize_run(
                        run_id,
                        requested_by,
                        symbols,
                        intervals,
                        modes,
                        created_at=created_at,
                        completed_at=completed_at,
                        signal_count=len(signals),
                        scan_workers=resolved_workers,
                        summary=summary,
                        result=result,
                        errors=errors,
                        final_status=final_status,
                        trace_event="SCAN_STOPPED",
                        profile_id=profile_id,
                        resolved_config_hash=resolved_config_hash,
                    )
                try:
                    while task_index < len(interval_tasks) and len(pending) < max_fetch_workers:
                        symbol, interval = interval_tasks[task_index]
                        interval_task = {"symbol": symbol, "interval": interval, "mode": None}
                        control_signal = self._honor_scan_control(
                            run_id,
                            requested_by,
                            symbols,
                            intervals,
                            modes,
                            profile_id=profile_id,
                            total_tasks=total_tasks,
                            completed_tasks=completed_tasks,
                            created_orders=created_orders,
                            daily_trades=daily_trades,
                            cap_reached=cap_reached,
                            scan_workers=resolved_workers,
                            skipped=skipped,
                            skip_stage_counts=skip_stage_counts,
                            signals=signals,
                            errors=errors,
                            stale_tasks=stale_tasks,
                            current_task=interval_task,
                            analysis_durations_ms=analysis_durations_ms,
                            fetch_durations_ms=fetch_durations_ms,
                            stage_metrics=stage_metrics,
                            scope_diagnostics=scope_diagnostics,
                        )
                        if control_signal == "stop":
                            for future in pending:
                                future.cancel()
                            final_status = "STOPPED"
                            completed_at = utc_now_iso()
                            summary = f"Stopped after {completed_tasks}/{total_tasks} tasks"
                            result = {
                                **self._build_progress_payload(
                                    total_tasks=total_tasks,
                                    completed_tasks=completed_tasks,
                                    created_orders=created_orders,
                                    daily_trades=daily_trades,
                                    cap_reached=cap_reached,
                                    scan_workers=resolved_workers,
                                    skipped=skipped,
                                    skip_stage_counts=skip_stage_counts,
                                    signals=signals,
                                    errors=errors,
                                    stale_tasks=stale_tasks,
                                    current_task=None,
                                    analysis_durations_ms=analysis_durations_ms,
                                    fetch_durations_ms=fetch_durations_ms,
                                    stage_metrics=stage_metrics,
                                    scope_diagnostics=scope_diagnostics,
                                ),
                                "scanned": scanned,
                                "stopped": True,
                            }
                            return self._finalize_run(
                                run_id,
                                requested_by,
                                symbols,
                                intervals,
                                modes,
                                created_at=created_at,
                                completed_at=completed_at,
                                signal_count=len(signals),
                                scan_workers=resolved_workers,
                                summary=summary,
                                result=result,
                                errors=errors,
                                final_status=final_status,
                                trace_event="SCAN_STOPPED",
                                profile_id=profile_id,
                                resolved_config_hash=resolved_config_hash,
                            )
                        future = executor.submit(self._fetch_interval_bundle, symbol, interval, market_bundle_cache, market_bundle_inflight, htf_trend_cache, cache_lock, stage_metrics)
                        pending[future] = {
                            "symbol": symbol,
                            "interval": interval,
                            "submitted_at": time.monotonic(),
                        }
                        with self._active_run_context_lock:
                            active_context = self._active_run_contexts.get(profile_id)
                            if active_context and active_context.get("run_id") == run_id:
                                active_context["fetch_futures"].add(future)
                        self._increment_stage_counter(stage_metrics, "pending_fetch_samples")
                        self._increment_stage_counter(stage_metrics, "pending_fetch_sum", len(pending))
                        stage_metrics["max_concurrent_fetches"] = max(int(stage_metrics.get("max_concurrent_fetches") or 0), len(pending))
                        task_index += 1

                    if not pending:
                        continue

                    now = time.monotonic()
                    next_timeout = 0.25
                    if pending:
                        earliest_deadline = min(float(meta.get("submitted_at") or now) + fetch_timeout_seconds for meta in pending.values())
                        next_timeout = max(0.0, min(0.25, earliest_deadline - now))
                    if next_timeout <= 0.0:
                        done = set()
                    else:
                        done, _ = wait(set(pending.keys()), timeout=next_timeout, return_when=FIRST_COMPLETED)
                    if not done:
                        oldest = max(
                            (
                                time.monotonic() - float(meta.get("submitted_at") or time.monotonic())
                                for meta in pending.values()
                            ),
                            default=0.0,
                        )
                        pending_tasks = [
                            {
                                "symbol": meta.get("symbol"),
                                "interval": meta.get("interval"),
                                "wait_seconds": round(time.monotonic() - float(meta.get("submitted_at") or time.monotonic()), 2),
                            }
                            for meta in sorted(pending.values(), key=lambda item: float(item.get("submitted_at") or 0.0))[:6]
                        ]
                        debug_state.update({
                            "last_progress_reason": "waiting_for_market_data",
                            "last_progress_at_utc": utc_now_iso(),
                            "pending_fetch_count": len(pending),
                            "pending_fetch_tasks": pending_tasks,
                            "oldest_pending_fetch_age_seconds": round(oldest, 2),
                            "wait_heartbeats": int(debug_state.get("wait_heartbeats") or 0) + 1,
                        })
                        current_task = pending_tasks[0] | {"mode": None, "phase": "fetch"} if pending_tasks else None
                        control_signal = self._honor_scan_control(
                            run_id,
                            requested_by,
                            symbols,
                            intervals,
                            modes,
                            profile_id=profile_id,
                            total_tasks=total_tasks,
                            completed_tasks=completed_tasks,
                            created_orders=created_orders,
                            daily_trades=daily_trades,
                            cap_reached=cap_reached,
                            scan_workers=resolved_workers,
                            skipped=skipped,
                            skip_stage_counts=skip_stage_counts,
                            signals=signals,
                            errors=errors,
                            stale_tasks=stale_tasks,
                            current_task=current_task,
                            analysis_durations_ms=analysis_durations_ms,
                            fetch_durations_ms=fetch_durations_ms,
                            stage_metrics=stage_metrics,
                            scope_diagnostics=scope_diagnostics,
                        )
                        if control_signal == "stop":
                            for pending_future in pending:
                                pending_future.cancel()
                            final_status = "STOPPED"
                            completed_at = utc_now_iso()
                            summary = f"Stopped after {completed_tasks}/{total_tasks} tasks"
                            result = {
                                **self._build_progress_payload(
                                    total_tasks=total_tasks,
                                    completed_tasks=completed_tasks,
                                    created_orders=created_orders,
                                    daily_trades=daily_trades,
                                    cap_reached=cap_reached,
                                    scan_workers=resolved_workers,
                                    skipped=skipped,
                                    skip_stage_counts=skip_stage_counts,
                                    signals=signals,
                                    errors=errors,
                                    stale_tasks=stale_tasks,
                                    current_task=None,
                                    analysis_durations_ms=analysis_durations_ms,
                                    fetch_durations_ms=fetch_durations_ms,
                                    debug=debug_state,
                                    stage_metrics=stage_metrics,
                                    scope_diagnostics=scope_diagnostics,
                                ),
                                "scanned": scanned,
                                "stopped": True,
                            }
                            return self._finalize_run(
                                run_id,
                                requested_by,
                                symbols,
                                intervals,
                                modes,
                                created_at=created_at,
                                completed_at=completed_at,
                                signal_count=len(signals),
                                scan_workers=resolved_workers,
                                summary=summary,
                                result=result,
                                errors=errors,
                                final_status=final_status,
                                trace_event="SCAN_STOPPED",
                                profile_id=profile_id,
                                resolved_config_hash=resolved_config_hash,
                            )
                        timed_out_futures = [
                            future
                            for future, meta in pending.items()
                            if time.monotonic() - float(meta.get("submitted_at") or time.monotonic()) >= fetch_timeout_seconds
                        ]
                        if timed_out_futures:
                            for future in timed_out_futures:
                                meta = pending.pop(future)
                                symbol = str(meta.get("symbol") or "")
                                interval = str(meta.get("interval") or "")
                                applicable_modes = [
                                    mode
                                    for mode in modes
                                    if interval in mode_interval_sets.get(str(mode).upper(), set())
                                ]
                                for _mode in applicable_modes:
                                    skipped["errors"] += 1
                                    completed_tasks += 1
                                timeout_error = f"Market data fetch timed out after {format(fetch_timeout_seconds, '.0f')}s"
                                errors.append({"symbol": symbol, "interval": interval, "error": timeout_error})
                                debug_state["timed_out_fetch_tasks"] = [
                                    *list(debug_state.get("timed_out_fetch_tasks") or [])[-9:],
                                    {
                                        "symbol": symbol,
                                        "interval": interval,
                                        "timed_out_after_seconds": round(fetch_timeout_seconds, 2),
                                    },
                                ]
                                self.trace_service.log_event(
                                    "SCAN_FETCH_TIMEOUT",
                                    run_id=run_id,
                                    source="SCAN",
                                    status="FAILED",
                                    decision="ERROR",
                                    reason_code="FETCH_TIMEOUT",
                                    reason_text=timeout_error,
                                    details={"symbol": symbol, "interval": interval, "modes": applicable_modes},
                                    profile_id=profile_id,
                                )
                            self._update_run_progress(
                                run_id,
                                requested_by,
                                symbols,
                                intervals,
                                modes,
                                profile_id=profile_id,
                                total_tasks=total_tasks,
                                completed_tasks=completed_tasks,
                                created_orders=created_orders,
                                daily_trades=daily_trades,
                                cap_reached=cap_reached,
                                scan_workers=resolved_workers,
                                skipped=skipped,
                                skip_stage_counts=skip_stage_counts,
                                signals=signals,
                                errors=errors,
                                stale_tasks=stale_tasks,
                                current_task=current_task,
                                analysis_durations_ms=analysis_durations_ms,
                                fetch_durations_ms=fetch_durations_ms,
                                debug=debug_state,
                                stage_metrics=stage_metrics,
                                scope_diagnostics=scope_diagnostics,
                            )
                        elif time.monotonic() - last_debug_flush >= WAIT_DEBUG_HEARTBEAT_SECONDS:
                            self._update_run_progress(
                                run_id,
                                requested_by,
                                symbols,
                                intervals,
                                modes,
                                profile_id=profile_id,
                                total_tasks=total_tasks,
                                completed_tasks=completed_tasks,
                                created_orders=created_orders,
                                daily_trades=daily_trades,
                                cap_reached=cap_reached,
                                scan_workers=resolved_workers,
                                skipped=skipped,
                                skip_stage_counts=skip_stage_counts,
                                signals=signals,
                                errors=errors,
                                stale_tasks=stale_tasks,
                                current_task=current_task,
                                analysis_durations_ms=analysis_durations_ms,
                                fetch_durations_ms=fetch_durations_ms,
                                debug=debug_state,
                                stage_metrics=stage_metrics,
                                scope_diagnostics=scope_diagnostics,
                            )
                            last_debug_flush = time.monotonic()
                        continue

                    for future in done:
                        meta = pending.pop(future)
                        with self._active_run_context_lock:
                            active_context = self._active_run_contexts.get(profile_id)
                            if active_context and active_context.get("run_id") == run_id:
                                active_context["fetch_futures"].discard(future)
                        symbol = str(meta.get("symbol") or "")
                        interval = str(meta.get("interval") or "")
                        market_bundle, fetch_ms, htf_trend = future.result()
                        fetch_durations_ms.append(fetch_ms)
                        debug_state.update({
                            "last_progress_reason": "market_data_ready",
                            "last_progress_at_utc": utc_now_iso(),
                            "pending_fetch_count": len(pending),
                            "pending_fetch_tasks": [],
                            "oldest_pending_fetch_age_seconds": 0.0,
                        })

                        snapshot = dict(market_bundle["snapshot"])
                        if market_bundle["stale"]:
                            stale_tasks += 1
                        if htf_trend:
                            snapshot["htf_trend"] = htf_trend
                        for mode in modes:
                            if interval not in mode_interval_sets.get(str(mode).upper(), set()):
                                continue
                            current_task = {"symbol": symbol, "interval": interval, "mode": mode}
                            control_signal = self._honor_scan_control(
                                run_id,
                                requested_by,
                                symbols,
                                intervals,
                                modes,
                                profile_id=profile_id,
                                total_tasks=total_tasks,
                                completed_tasks=completed_tasks,
                                created_orders=created_orders,
                                daily_trades=daily_trades,
                                cap_reached=cap_reached,
                                scan_workers=resolved_workers,
                                skipped=skipped,
                                skip_stage_counts=skip_stage_counts,
                                signals=signals,
                                errors=errors,
                                stale_tasks=stale_tasks,
                                current_task=current_task,
                                analysis_durations_ms=analysis_durations_ms,
                                fetch_durations_ms=fetch_durations_ms,
                                stage_metrics=stage_metrics,
                                scope_diagnostics=scope_diagnostics,
                            )
                            if control_signal == "stop":
                                for pending_future in pending:
                                    pending_future.cancel()
                                final_status = "STOPPED"
                                completed_at = utc_now_iso()
                                summary = f"Stopped after {completed_tasks}/{total_tasks} tasks"
                                result = {
                                    **self._build_progress_payload(
                                        total_tasks=total_tasks,
                                        completed_tasks=completed_tasks,
                                        created_orders=created_orders,
                                        daily_trades=daily_trades,
                                        cap_reached=cap_reached,
                                        scan_workers=resolved_workers,
                                        skipped=skipped,
                                        skip_stage_counts=skip_stage_counts,
                                        signals=signals,
                                        errors=errors,
                                        stale_tasks=stale_tasks,
                                        current_task=None,
                                        analysis_durations_ms=analysis_durations_ms,
                                        fetch_durations_ms=fetch_durations_ms,
                                        stage_metrics=stage_metrics,
                                        scope_diagnostics=scope_diagnostics,
                                    ),
                                    "scanned": scanned,
                                    "stopped": True,
                                }
                                return self._finalize_run(
                                    run_id,
                                    requested_by,
                                    symbols,
                                    intervals,
                                    modes,
                                    created_at=created_at,
                                    completed_at=completed_at,
                                    signal_count=len(signals),
                                    scan_workers=resolved_workers,
                                    summary=summary,
                                    result=result,
                                    errors=errors,
                                    final_status=final_status,
                                    trace_event="SCAN_STOPPED",
                                    profile_id=profile_id,
                                    resolved_config_hash=resolved_config_hash,
                                )
                            analysis_inputs.append({
                                "symbol": symbol,
                                "interval": interval,
                                "mode": mode,
                                "snapshot": dict(snapshot),
                            })
                except BinanceBadSymbolError as exc:
                    applicable_modes = [
                        mode
                        for mode in modes
                        if interval in mode_interval_sets.get(str(mode).upper(), set())
                    ]
                    for _mode in applicable_modes:
                        skipped["market_unavailable"] += 1
                        completed_tasks += 1
                    self.trace_service.log_event(
                        "SCAN_SKIPPED",
                        run_id=run_id,
                        source="SCAN",
                        status="SKIPPED",
                        decision="SKIP",
                        reason_code="MARKET_UNAVAILABLE",
                        reason_text=str(exc),
                        details={"symbol": symbol, "interval": interval},
                        profile_id=profile_id,
                    )
                    self._update_run_progress(
                        run_id,
                        requested_by,
                        symbols,
                        intervals,
                        modes,
                        total_tasks=total_tasks,
                        completed_tasks=completed_tasks,
                        created_orders=created_orders,
                        daily_trades=daily_trades,
                                cap_reached=cap_reached,
                                scan_workers=resolved_workers,
                                skipped=skipped,
                                skip_stage_counts=skip_stage_counts,
                                signals=signals,
                                errors=errors,
                                stale_tasks=stale_tasks,
                        current_task={"symbol": symbol, "interval": interval, "mode": None},
                        analysis_durations_ms=analysis_durations_ms,
                        fetch_durations_ms=fetch_durations_ms,
                        debug=debug_state,
                        stage_metrics=stage_metrics,
                        scope_diagnostics=scope_diagnostics,
                    )
                except Exception as exc:
                    applicable_modes = [
                        mode
                        for mode in modes
                        if interval in mode_interval_sets.get(str(mode).upper(), set())
                    ]
                    for _mode in applicable_modes:
                        skipped["errors"] += 1
                        completed_tasks += 1
                    self.trace_service.log_event(
                        "SCAN_ERROR",
                        run_id=run_id,
                        source="SCAN",
                        status="FAILED",
                        decision="ERROR",
                        reason_code="SCAN_ERROR",
                        reason_text=str(exc),
                        details={"symbol": symbol, "interval": interval},
                        profile_id=profile_id,
                    )
                    errors.append({"profile_id": profile_id, "run_id": run_id, "symbol": symbol, "interval": interval, "error": str(exc)})
                    self._update_run_progress(
                        run_id,
                        requested_by,
                        symbols,
                        intervals,
                        modes,
                        total_tasks=total_tasks,
                        completed_tasks=completed_tasks,
                        created_orders=created_orders,
                        daily_trades=daily_trades,
                        cap_reached=cap_reached,
                        scan_workers=resolved_workers,
                        skipped=skipped,
                        skip_stage_counts=skip_stage_counts,
                        signals=signals,
                        errors=errors,
                        stale_tasks=stale_tasks,
                        current_task={"symbol": symbol, "interval": interval, "mode": None},
                        analysis_durations_ms=analysis_durations_ms,
                        fetch_durations_ms=fetch_durations_ms,
                        debug=debug_state,
                        stage_metrics=stage_metrics,
                        scope_diagnostics=scope_diagnostics,
                    )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
            with self._active_run_context_lock:
                active_context = self._active_run_contexts.get(profile_id)
                if active_context and active_context.get("run_id") == run_id:
                    active_context["fetch_executor"] = None
                    active_context["fetch_futures"] = set()

        analysis_capacity = max(1, min(analysis_workers, len(analysis_inputs) or 1))
        analysis_executor = ThreadPoolExecutor(max_workers=analysis_capacity, thread_name_prefix="scan-analysis")
        with self._active_run_context_lock:
            active_context = self._active_run_contexts.get(profile_id)
            if active_context and active_context.get("run_id") == run_id:
                active_context["analysis_executor"] = analysis_executor
        try:
            pending_analysis: dict[Future, dict[str, Any]] = {}
            analysis_index = 0
            last_analysis_flush = time.monotonic()

            while analysis_index < len(analysis_inputs) or pending_analysis:
                if force_stop_requested():
                    for pending_future in pending_analysis:
                        pending_future.cancel()
                    final_status = "STOPPED"
                    completed_at = utc_now_iso()
                    summary = f"Force-stopped after {completed_tasks}/{total_tasks} tasks"
                    result = {
                        **self._build_progress_payload(
                            total_tasks=total_tasks,
                            completed_tasks=completed_tasks,
                            created_orders=created_orders,
                            daily_trades=daily_trades,
                            cap_reached=cap_reached,
                            scan_workers=resolved_workers,
                            skipped=skipped,
                            skip_stage_counts=skip_stage_counts,
                            signals=signals,
                            errors=errors,
                            stale_tasks=stale_tasks,
                            current_task=None,
                            analysis_durations_ms=analysis_durations_ms,
                            fetch_durations_ms=fetch_durations_ms,
                            debug=debug_state,
                            stage_metrics=stage_metrics,
                            scope_diagnostics=scope_diagnostics,
                        ),
                        "scanned": scanned,
                        "stopped": True,
                        "force_stopped": True,
                    }
                    return self._finalize_run(
                        run_id,
                        requested_by,
                        symbols,
                        intervals,
                        modes,
                        created_at=created_at,
                        completed_at=completed_at,
                        signal_count=len(signals),
                        scan_workers=resolved_workers,
                        summary=summary,
                        result=result,
                        errors=errors,
                        final_status=final_status,
                        trace_event="SCAN_STOPPED",
                        profile_id=profile_id,
                        resolved_config_hash=resolved_config_hash,
                    )
                while analysis_index < len(analysis_inputs) and len(pending_analysis) < analysis_capacity:
                    task = dict(analysis_inputs[analysis_index])
                    submitted_at = time.perf_counter()
                    future = analysis_executor.submit(
                        self._execute_analysis_task,
                        run_id=run_id,
                        profile_id=profile_id,
                        requested_by=requested_by,
                        scan_workers=resolved_workers,
                        symbol=str(task.get("symbol") or ""),
                        interval=str(task.get("interval") or ""),
                        mode=str(task.get("mode") or ""),
                        snapshot=dict(task.get("snapshot") or {}),
                        submitted_at=submitted_at,
                    )
                    pending_analysis[future] = {
                        **task,
                        "submitted_at": submitted_at,
                    }
                    with self._active_run_context_lock:
                        active_context = self._active_run_contexts.get(profile_id)
                        if active_context and active_context.get("run_id") == run_id:
                            active_context["analysis_futures"].add(future)
                    analysis_index += 1

                current_meta = next(iter(pending_analysis.values()), None)
                current_task = None
                if current_meta:
                    current_task = {
                        "symbol": current_meta.get("symbol"),
                        "interval": current_meta.get("interval"),
                        "mode": current_meta.get("mode"),
                        "phase": "analysis",
                    }
                control_signal = self._honor_scan_control(
                    run_id,
                    requested_by,
                    symbols,
                    intervals,
                    modes,
                    profile_id=profile_id,
                    total_tasks=total_tasks,
                    completed_tasks=completed_tasks,
                    created_orders=created_orders,
                    daily_trades=daily_trades,
                    cap_reached=cap_reached,
                    scan_workers=resolved_workers,
                    skipped=skipped,
                    skip_stage_counts=skip_stage_counts,
                    signals=signals,
                    errors=errors,
                    stale_tasks=stale_tasks,
                    current_task=current_task,
                    analysis_durations_ms=analysis_durations_ms,
                    fetch_durations_ms=fetch_durations_ms,
                    stage_metrics=stage_metrics,
                    scope_diagnostics=scope_diagnostics,
                )
                if control_signal == "stop":
                    for pending_future in pending_analysis:
                        pending_future.cancel()
                    final_status = "STOPPED"
                    completed_at = utc_now_iso()
                    summary = f"Stopped after {completed_tasks}/{total_tasks} tasks"
                    result = {
                        **self._build_progress_payload(
                            total_tasks=total_tasks,
                            completed_tasks=completed_tasks,
                            created_orders=created_orders,
                            daily_trades=daily_trades,
                            cap_reached=cap_reached,
                            scan_workers=resolved_workers,
                            skipped=skipped,
                            skip_stage_counts=skip_stage_counts,
                            signals=signals,
                            errors=errors,
                            stale_tasks=stale_tasks,
                            current_task=None,
                            analysis_durations_ms=analysis_durations_ms,
                            fetch_durations_ms=fetch_durations_ms,
                            debug=debug_state,
                            stage_metrics=stage_metrics,
                            scope_diagnostics=scope_diagnostics,
                        ),
                        "scanned": scanned,
                        "stopped": True,
                    }
                    return self._finalize_run(
                        run_id,
                        requested_by,
                        symbols,
                        intervals,
                        modes,
                        created_at=created_at,
                        completed_at=completed_at,
                        signal_count=len(signals),
                        scan_workers=resolved_workers,
                        summary=summary,
                        result=result,
                        errors=errors,
                        final_status=final_status,
                        trace_event="SCAN_STOPPED",
                        profile_id=profile_id,
                        resolved_config_hash=resolved_config_hash,
                    )

                done, _ = wait(set(pending_analysis.keys()), timeout=0.25, return_when=FIRST_COMPLETED) if pending_analysis else (set(), set())
                if not done:
                    debug_state.update({
                        "last_progress_reason": "waiting_for_analysis",
                        "last_progress_at_utc": utc_now_iso(),
                        "pending_analysis_count": len(pending_analysis),
                    })
                    if time.monotonic() - last_analysis_flush >= WAIT_DEBUG_HEARTBEAT_SECONDS:
                        self._update_run_progress(
                            run_id,
                            requested_by,
                            symbols,
                            intervals,
                            modes,
                            profile_id=profile_id,
                            total_tasks=total_tasks,
                            completed_tasks=completed_tasks,
                            created_orders=created_orders,
                            daily_trades=daily_trades,
                            cap_reached=cap_reached,
                            scan_workers=resolved_workers,
                            skipped=skipped,
                            skip_stage_counts=skip_stage_counts,
                            signals=signals,
                            errors=errors,
                            stale_tasks=stale_tasks,
                            current_task=current_task,
                            analysis_durations_ms=analysis_durations_ms,
                            fetch_durations_ms=fetch_durations_ms,
                            debug=debug_state,
                            stage_metrics=stage_metrics,
                            scope_diagnostics=scope_diagnostics,
                        )
                        last_analysis_flush = time.monotonic()
                    continue

                for future in done:
                    meta = pending_analysis.pop(future)
                    with self._active_run_context_lock:
                        active_context = self._active_run_contexts.get(profile_id)
                        if active_context and active_context.get("run_id") == run_id:
                            active_context["analysis_futures"].discard(future)
                    symbol = str(meta.get("symbol") or "")
                    interval = str(meta.get("interval") or "")
                    mode = str(meta.get("mode") or "")
                    current_task = {"symbol": symbol, "interval": interval, "mode": mode}
                    try:
                        analysis_result = future.result()
                    except Exception as exc:
                        skipped["errors"] += 1
                        completed_tasks += 1
                        reason_code = "ANALYSIS_ERROR"
                        details = {"symbol": symbol, "interval": interval, "mode": mode}
                        if isinstance(exc, InferenceJobRejectedError):
                            reason_code = "INFERENCE_QUEUE_REJECTED"
                            self._increment_stage_counter(stage_metrics, "inference_queue_rejections")
                            details["inference_job"] = dict(exc.job)
                        elif isinstance(exc, InferenceJobTimedOutError):
                            reason_code = "INFERENCE_TIMEOUT"
                            self._increment_stage_counter(stage_metrics, "inference_timeouts")
                            details["inference_job"] = dict(exc.job)
                        elif isinstance(exc, InferenceJobFailedError):
                            reason_code = "INFERENCE_FAILED"
                            self._increment_stage_counter(stage_metrics, "inference_failures")
                            details["inference_job"] = dict(exc.job)
                        self.trace_service.log_event(
                            "SCAN_ERROR",
                            run_id=run_id,
                            source="SCAN",
                            status="FAILED",
                            decision="ERROR",
                            reason_code=reason_code,
                            reason_text=str(exc),
                            details=details,
                            profile_id=profile_id,
                        )
                        errors.append({
                            "profile_id": profile_id,
                            "run_id": run_id,
                            "symbol": symbol,
                            "interval": interval,
                            "mode": mode,
                            "reason_code": reason_code,
                            "error": str(exc),
                            "inference_job": dict(details.get("inference_job") or {}),
                        })
                        self._update_run_progress(
                            run_id,
                            requested_by,
                            symbols,
                            intervals,
                            modes,
                            profile_id=profile_id,
                            total_tasks=total_tasks,
                            completed_tasks=completed_tasks,
                            created_orders=created_orders,
                            daily_trades=daily_trades,
                            cap_reached=cap_reached,
                            scan_workers=resolved_workers,
                            skipped=skipped,
                            skip_stage_counts=skip_stage_counts,
                            signals=signals,
                            errors=errors,
                            stale_tasks=stale_tasks,
                            current_task=current_task,
                            analysis_durations_ms=analysis_durations_ms,
                            fetch_durations_ms=fetch_durations_ms,
                            debug=debug_state,
                            stage_metrics=stage_metrics,
                            scope_diagnostics=scope_diagnostics,
                        )
                        continue

                    analysis = dict(analysis_result.get("analysis") or {})
                    snapshot = dict(analysis_result.get("snapshot") or {})
                    signal = dict(analysis.get("signal") or {})
                    analysis_ms = float(analysis_result.get("analysis_ms") or 0.0)
                    queue_wait_ms = float(analysis_result.get("queue_wait_ms") or 0.0)
                    analysis_durations_ms.append(analysis_ms)
                    self._append_stage_metric(stage_metrics, "analysis_ms", analysis_ms)
                    self._append_stage_metric(stage_metrics, "analysis_queue_wait_ms", queue_wait_ms)
                    self._increment_stage_counter(stage_metrics, "analysis_tasks")
                    prefilter = analysis_result.get("prefilter")
                    if isinstance(prefilter, dict) and prefilter:
                        skipped["neutral"] += 1
                        skip_stage = str(prefilter.get("stage") or "PREFILTER")
                        skip_reason_text = str(prefilter.get("reason") or "Prefilter rejected task before full analysis.")
                        skip_stage_counts[skip_stage] = skip_stage_counts.get(skip_stage, 0) + 1
                        self.trace_service.log_event(
                            "SCAN_SKIPPED",
                            run_id=run_id,
                            source="SCAN",
                            status="SKIPPED",
                            decision="SKIP",
                            reason_code="PREFILTER_NEUTRAL",
                            reason_text=skip_reason_text,
                            details={"symbol": symbol, "interval": interval, "mode": mode, "stage": skip_stage},
                            profile_id=profile_id,
                        )
                        completed_tasks += 1
                        debug_state.update({
                            "last_progress_reason": "prefilter_neutral",
                            "last_progress_at_utc": utc_now_iso(),
                            "last_completed_task": current_task | {"skip_stage": skip_stage},
                        })
                        self._update_run_progress(
                            run_id,
                            requested_by,
                            symbols,
                            intervals,
                            modes,
                            profile_id=profile_id,
                            total_tasks=total_tasks,
                            completed_tasks=completed_tasks,
                            created_orders=created_orders,
                            daily_trades=daily_trades,
                            cap_reached=cap_reached,
                            scan_workers=resolved_workers,
                            skipped=skipped,
                            skip_stage_counts=skip_stage_counts,
                            signals=signals,
                            errors=errors,
                            stale_tasks=stale_tasks,
                            current_task=current_task,
                            analysis_durations_ms=analysis_durations_ms,
                            fetch_durations_ms=fetch_durations_ms,
                            debug=debug_state,
                            stage_metrics=stage_metrics,
                            scope_diagnostics=scope_diagnostics,
                        )
                        continue

                    adapter_metrics = dict(analysis.get("adapter_metrics") or {})
                    decision_performance = dict((analysis.get("decision_payload") or {}).get("performance") or {})
                    self._annotate_trade_direction_policy(signal, allowed_trade_directions=allowed_trade_directions)
                    self._ensure_runtime_decision_trace(
                        signal,
                        min_confidence=min_confidence,
                        runtime_decision="PENDING_RUNTIME_FILTERS",
                        runtime_reason=None,
                        runtime_stage="POST_ANALYSIS",
                    )
                    self._append_stage_metric(stage_metrics, "adapter_total_ms", adapter_metrics.get("adapter_total_ms"))
                    self._append_stage_metric(stage_metrics, "engine_lookup_ms", adapter_metrics.get("engine_lookup_ms"))
                    self._append_stage_metric(stage_metrics, "response_validation_ms", adapter_metrics.get("response_validation_ms"))
                    self._append_stage_metric(stage_metrics, "timeout_lookup_ms", adapter_metrics.get("timeout_lookup_ms"))
                    self._append_stage_metric(stage_metrics, "analyzer_status_write_ms", adapter_metrics.get("status_persist_ms"))
                    self._append_stage_metric(stage_metrics, "engine_total_ms", decision_performance.get("engine_total_ms"))
                    self._append_stage_metric(stage_metrics, "base_analyzer_ms", decision_performance.get("base_analyzer_ms"))
                    self._append_stage_metric(stage_metrics, "self_learning_total_ms", decision_performance.get("self_learning_total_ms"))
                    self._append_stage_metric(stage_metrics, "self_learning_inference_ms", decision_performance.get("self_learning_inference_ms"))
                    self._append_stage_metric(stage_metrics, "self_learning_retrieval_ms", decision_performance.get("self_learning_retrieval_ms"))
                    if analysis.get("fallback_used"):
                        self._increment_stage_counter(stage_metrics, "analysis_fallbacks")
                    if decision_performance.get("self_learning_active"):
                        self._increment_stage_counter(stage_metrics, "self_learning_active_tasks")
                    if decision_performance.get("self_learning_bypassed"):
                        self._increment_stage_counter(stage_metrics, "self_learning_bypassed_tasks")

                    skip_reason, skip_reason_text = self._classify_skip(
                        signal,
                        min_confidence=min_confidence,
                        allowed_trade_directions=allowed_trade_directions,
                    )
                    if not post_scan_confidence_ranked_entry_enabled and daily_trades >= max_trades_per_day:
                        cap_reached = True
                        skipped["daily_cap_reached"] += 1
                        self._ensure_runtime_decision_trace(
                            signal,
                            min_confidence=min_confidence,
                            runtime_decision="REJECTED",
                            runtime_reason="DAILY_CAP_REACHED",
                            runtime_stage="DAILY_CAP",
                        )
                        self.trace_service.log_event(
                            "SCAN_SKIPPED",
                            run_id=run_id,
                            signal=signal,
                            source="SCAN",
                            status="SKIPPED",
                            decision="SKIP",
                            reason_code="DAILY_CAP_REACHED",
                            reason_text="Daily trade cap reached",
                            profile_id=profile_id,
                        )
                        completed_tasks += 1
                        debug_state.update({
                            "last_progress_reason": "daily_cap_reached",
                            "last_progress_at_utc": utc_now_iso(),
                            "last_completed_task": current_task,
                        })
                        self._update_run_progress(
                            run_id,
                            requested_by,
                            symbols,
                            intervals,
                            modes,
                            profile_id=profile_id,
                            total_tasks=total_tasks,
                            completed_tasks=completed_tasks,
                            created_orders=created_orders,
                            daily_trades=daily_trades,
                            cap_reached=cap_reached,
                            scan_workers=resolved_workers,
                            skipped=skipped,
                            skip_stage_counts=skip_stage_counts,
                            signals=signals,
                            errors=errors,
                            stale_tasks=stale_tasks,
                            current_task=current_task,
                            analysis_durations_ms=analysis_durations_ms,
                            fetch_durations_ms=fetch_durations_ms,
                            debug=debug_state,
                            stage_metrics=stage_metrics,
                            scope_diagnostics=scope_diagnostics,
                        )
                        continue
                    if skip_reason is not None:
                        skipped[skip_reason] += 1
                        skip_stage = self._resolve_skip_stage(signal)
                        runtime_stage = skip_stage or {
                            "neutral": "ENGINE_NO_TRADE",
                            "low_confidence": "RUNTIME_MIN_CONFIDENCE",
                            "missing_levels": "RUNTIME_MISSING_LEVELS",
                            "long_disabled_by_runtime": "TRADE_DIRECTION_POLICY",
                            "short_disabled_by_runtime": "TRADE_DIRECTION_POLICY",
                        }.get(skip_reason, "RUNTIME_FILTER")
                        self._ensure_runtime_decision_trace(
                            signal,
                            min_confidence=min_confidence,
                            runtime_decision="REJECTED",
                            runtime_reason=str(skip_reason).upper(),
                            runtime_stage=runtime_stage,
                        )
                        if skip_stage:
                            skip_stage_counts[skip_stage] = skip_stage_counts.get(skip_stage, 0) + 1
                        self.trace_service.log_event(
                            "SCAN_SKIPPED",
                            run_id=run_id,
                            signal=signal,
                            source="SCAN",
                            status="SKIPPED",
                            decision="SKIP",
                            reason_code=skip_reason,
                            reason_text=str(skip_reason_text or signal.get("no_trade_reason") or f"Signal skipped: {skip_reason}"),
                            profile_id=profile_id,
                        )
                        completed_tasks += 1
                        debug_state.update({
                            "last_progress_reason": f"skipped_{skip_reason}",
                            "last_progress_at_utc": utc_now_iso(),
                            "last_completed_task": current_task | {"skip_stage": skip_stage},
                        })
                        self._update_run_progress(
                            run_id,
                            requested_by,
                            symbols,
                            intervals,
                            modes,
                            profile_id=profile_id,
                            total_tasks=total_tasks,
                            completed_tasks=completed_tasks,
                            created_orders=created_orders,
                            daily_trades=daily_trades,
                            cap_reached=cap_reached,
                            scan_workers=resolved_workers,
                            skipped=skipped,
                            skip_stage_counts=skip_stage_counts,
                            signals=signals,
                            errors=errors,
                            stale_tasks=stale_tasks,
                            current_task=current_task,
                            analysis_durations_ms=analysis_durations_ms,
                            fetch_durations_ms=fetch_durations_ms,
                            debug=debug_state,
                            stage_metrics=stage_metrics,
                            scope_diagnostics=scope_diagnostics,
                        )
                        continue
                    if self._has_duplicate_open_order(signal, profile_id=profile_id):
                        skipped["duplicate_open"] += 1
                        self._ensure_runtime_decision_trace(
                            signal,
                            min_confidence=min_confidence,
                            runtime_decision="REJECTED",
                            runtime_reason="DUPLICATE_OPEN",
                            runtime_stage="DUPLICATE_OPEN_GUARD",
                        )
                        self.trace_service.log_event(
                            "SCAN_SKIPPED",
                            run_id=run_id,
                            signal=signal,
                            source="SCAN",
                            status="SKIPPED",
                            decision="SKIP",
                            reason_code="DUPLICATE_OPEN",
                            reason_text="Duplicate open order exists",
                            profile_id=profile_id,
                        )
                        completed_tasks += 1
                        debug_state.update({
                            "last_progress_reason": "duplicate_open",
                            "last_progress_at_utc": utc_now_iso(),
                            "last_completed_task": current_task,
                        })
                        self._update_run_progress(
                            run_id,
                            requested_by,
                            symbols,
                            intervals,
                            modes,
                            profile_id=profile_id,
                            total_tasks=total_tasks,
                            completed_tasks=completed_tasks,
                            created_orders=created_orders,
                            daily_trades=daily_trades,
                            cap_reached=cap_reached,
                            scan_workers=resolved_workers,
                            skipped=skipped,
                            skip_stage_counts=skip_stage_counts,
                            signals=signals,
                            errors=errors,
                            stale_tasks=stale_tasks,
                            current_task=current_task,
                            analysis_durations_ms=analysis_durations_ms,
                            fetch_durations_ms=fetch_durations_ms,
                            debug=debug_state,
                            stage_metrics=stage_metrics,
                            scope_diagnostics=scope_diagnostics,
                        )
                        continue

                    audit_started = time.perf_counter()
                    signal_audit = self.audit_service.build_audit_snapshot(signal, snapshot)
                    self._append_stage_metric(stage_metrics, "signal_audit_ms", round((time.perf_counter() - audit_started) * 1000.0, 4))
                    signal_record = self._signal_record(run_id, signal, snapshot, signal_audit, analysis, profile_id=profile_id)
                    persist_started = time.perf_counter()
                    with session_scope() as session:
                        saved_signal = self.signal_repo.save_signal(session, signal_record)
                    self._append_stage_metric(stage_metrics, "signal_persist_ms", round((time.perf_counter() - persist_started) * 1000.0, 4))
                    attribution_started = time.perf_counter()
                    self.attribution_service.capture_signal_attribution(
                        saved_signal["signal_id"],
                        run_id,
                        self._components_used_for_signal(signal),
                        list(signal.get("factors") or []),
                        self._filter_contributions(signal, signal_audit),
                        self._adjustment_contributions(signal),
                        signal={**signal, "signal_id": saved_signal["signal_id"], "audit": signal_audit, "profile_id": profile_id},
                        profile_id=profile_id,
                    )
                    self._append_stage_metric(stage_metrics, "signal_attribution_ms", round((time.perf_counter() - attribution_started) * 1000.0, 4))
                    self._ensure_runtime_decision_trace(
                        signal,
                        min_confidence=min_confidence,
                        runtime_decision="ACCEPTED",
                        runtime_reason="SIGNAL_EMITTED",
                        runtime_stage="SIGNAL_ACCEPTED",
                    )
                    signals.append(signal)
                    self._increment_stage_counter(stage_metrics, "signals_emitted")
                    self.trace_service.log_event(
                        "SIGNAL_EMITTED",
                        run_id=run_id,
                        signal={**signal, "signal_id": saved_signal["signal_id"], "profile_id": profile_id},
                        source="SCAN",
                        status="READY",
                        decision=signal.get("direction"),
                        reason_text=signal.get("summary"),
                        profile_id=profile_id,
                    )
                    if post_scan_confidence_ranked_entry_enabled:
                        post_scan_entry_candidates.append({
                            "signal": signal,
                            "signal_id": saved_signal["signal_id"],
                            "snapshot": dict(snapshot),
                        })
                        completed_tasks += 1
                        debug_state.update({
                            "last_progress_reason": "signal_buffered_for_post_scan_entry",
                            "last_progress_at_utc": utc_now_iso(),
                            "last_completed_task": current_task | {"signal_id": saved_signal["signal_id"]},
                        })
                        self._update_run_progress(
                            run_id,
                            requested_by,
                            symbols,
                            intervals,
                            modes,
                            total_tasks=total_tasks,
                            completed_tasks=completed_tasks,
                            created_orders=created_orders,
                            daily_trades=daily_trades,
                            cap_reached=cap_reached,
                            scan_workers=resolved_workers,
                            skipped=skipped,
                            skip_stage_counts=skip_stage_counts,
                            signals=signals,
                            errors=errors,
                            stale_tasks=stale_tasks,
                            current_task=current_task,
                            analysis_durations_ms=analysis_durations_ms,
                            fetch_durations_ms=fetch_durations_ms,
                            debug=debug_state,
                            stage_metrics=stage_metrics,
                            scope_diagnostics=scope_diagnostics,
                        )
                        continue
                    entry_price = self._resolve_entry_price(signal, snapshot)
                    sizing = self._compute_auto_order_sizing(entry_price, signal=signal, profile_id=profile_id)
                    if sizing is not None:
                        quantity = float(sizing.get("quantity") or 0.0)
                        if quantity <= 0:
                            available_balance = float(sizing.get("available_balance") or 0.0)
                            skipped["insufficient_balance"] += 1
                            self.trace_service.log_event(
                                "SCAN_SKIPPED",
                                run_id=run_id,
                                signal={**signal, "signal_id": saved_signal["signal_id"], "profile_id": profile_id},
                                source="SCAN",
                                status="SKIPPED",
                                decision="SKIP",
                                reason_code="INSUFFICIENT_BALANCE",
                                reason_text=(
                                    "Paper balance is insufficient for this auto order"
                                    if available_balance <= 0
                                    else "Auto order resolved to zero quantity"
                                ),
                                profile_id=profile_id,
                            )
                            completed_tasks += 1
                            self._update_run_progress(
                                run_id,
                                requested_by,
                                symbols,
                                intervals,
                                modes,
                                profile_id=profile_id,
                                total_tasks=total_tasks,
                                completed_tasks=completed_tasks,
                                created_orders=created_orders,
                                daily_trades=daily_trades,
                                cap_reached=cap_reached,
                                scan_workers=resolved_workers,
                                skipped=skipped,
                                skip_stage_counts=skip_stage_counts,
                                signals=signals,
                                errors=errors,
                                stale_tasks=stale_tasks,
                                current_task=current_task,
                                analysis_durations_ms=analysis_durations_ms,
                                fetch_durations_ms=fetch_durations_ms,
                            )
                            continue
                    execution_started = time.perf_counter()
                    order_queue_state["submitted"] += 1
                    order_queue_state["pending"] += 1
                    debug_state.update({
                        "last_progress_reason": "order_submit_requested",
                        "last_progress_at_utc": utc_now_iso(),
                        "last_completed_task": current_task | {"signal_id": saved_signal["signal_id"], "order_request_sent": True},
                    })
                    self._update_run_progress(
                        run_id,
                        requested_by,
                        symbols,
                        intervals,
                        modes,
                        total_tasks=total_tasks,
                        completed_tasks=completed_tasks,
                        created_orders=created_orders,
                        daily_trades=daily_trades,
                        cap_reached=cap_reached,
                        scan_workers=resolved_workers,
                        skipped=skipped,
                        skip_stage_counts=skip_stage_counts,
                        signals=signals,
                        errors=errors,
                        stale_tasks=stale_tasks,
                        current_task=current_task,
                        analysis_durations_ms=analysis_durations_ms,
                        fetch_durations_ms=fetch_durations_ms,
                        debug=debug_state,
                        stage_metrics=stage_metrics,
                        scope_diagnostics=scope_diagnostics,
                        order_queue_state=order_queue_state,
                    )
                    try:
                        opened = self._open_auto_order(
                            signal={
                                **signal,
                                "signal_id": saved_signal["signal_id"],
                                "run_id": run_id,
                                "entry": entry_price,
                                "profile_id": profile_id,
                                "paper_sizing": sizing or {},
                            },
                            entry_price=entry_price,
                            sizing=sizing,
                            profile_id=profile_id,
                        )
                    except (
                        BinanceUsdmManualLiveError,
                        ExecutionPolicyViolationError,
                        RuntimeProfileAccessError,
                        RuntimeProfileConnectivityError,
                        UnsupportedExecutionProfileError,
                    ) as exc:
                        order_queue_state["pending"] = max(0, int(order_queue_state.get("pending") or 0) - 1)
                        self._record_auto_order_skip(
                            run_id=run_id,
                            signal={**signal, "signal_id": saved_signal["signal_id"], "profile_id": profile_id},
                            skipped=skipped,
                            skip_stage_counts=skip_stage_counts,
                            reason_text=str(exc),
                            profile_id=profile_id,
                        )
                        completed_tasks += 1
                        self._update_run_progress(
                            run_id,
                            requested_by,
                            symbols,
                            intervals,
                            modes,
                            profile_id=profile_id,
                            total_tasks=total_tasks,
                            completed_tasks=completed_tasks,
                            created_orders=created_orders,
                            daily_trades=daily_trades,
                            cap_reached=cap_reached,
                            scan_workers=resolved_workers,
                            skipped=skipped,
                            skip_stage_counts=skip_stage_counts,
                            signals=signals,
                            errors=errors,
                            stale_tasks=stale_tasks,
                            current_task=current_task,
                            analysis_durations_ms=analysis_durations_ms,
                            fetch_durations_ms=fetch_durations_ms,
                            order_queue_state=order_queue_state,
                        )
                        continue
                    self._append_stage_metric(stage_metrics, "execution_ms", round((time.perf_counter() - execution_started) * 1000.0, 4))
                    order_queue_state["pending"] = max(0, int(order_queue_state.get("pending") or 0) - 1)
                    submission_status = str(((opened.get("submission") or {}).get("submission_status") or (opened.get("order") or {}).get("submission_status") or "")).upper()
                    if submission_status in {"SUBMITTED", "SUBMITTED_VERIFIED"}:
                        order_queue_state["verified"] += 1
                    elif submission_status:
                        order_queue_state["pending_verification"] += 1
                    created_orders += 1
                    daily_trades += 1
                    self._increment_stage_counter(stage_metrics, "orders_created")
                    signal["execution_outcome"] = opened.get("signal_outcome") or {
                        "order_id": ((opened.get("order") or {}).get("order_id")),
                        "signal_outcome": str(((opened.get("submission") or {}).get("submission_status") or (opened.get("order") or {}).get("submission_status") or "ORDER_REQUEST_SENT")).upper(),
                        "submission_status": ((opened.get("submission") or {}).get("submission_status") or (opened.get("order") or {}).get("submission_status")),
                        "order_status": ((opened.get("order") or {}).get("status")),
                        "venue_order_id": ((opened.get("order") or {}).get("venue_order_id")),
                        "client_order_id": ((opened.get("order") or {}).get("client_order_id")),
                    }
                    completed_tasks += 1
                    debug_state.update({
                        "last_progress_reason": "order_created",
                        "last_progress_at_utc": utc_now_iso(),
                        "last_completed_task": current_task | {"signal_id": saved_signal["signal_id"]},
                    })
                    self._update_run_progress(
                        run_id,
                        requested_by,
                        symbols,
                        intervals,
                        modes,
                        total_tasks=total_tasks,
                        completed_tasks=completed_tasks,
                        created_orders=created_orders,
                        daily_trades=daily_trades,
                        cap_reached=cap_reached,
                        scan_workers=resolved_workers,
                        skipped=skipped,
                        skip_stage_counts=skip_stage_counts,
                        signals=signals,
                        errors=errors,
                        stale_tasks=stale_tasks,
                        current_task=current_task,
                        analysis_durations_ms=analysis_durations_ms,
                        fetch_durations_ms=fetch_durations_ms,
                        debug=debug_state,
                        stage_metrics=stage_metrics,
                        scope_diagnostics=scope_diagnostics,
                        order_queue_state=order_queue_state,
                    )
        finally:
            analysis_executor.shutdown(wait=False, cancel_futures=True)
            with self._active_run_context_lock:
                active_context = self._active_run_contexts.get(profile_id)
                if active_context and active_context.get("run_id") == run_id:
                    active_context["analysis_executor"] = None
                    active_context["analysis_futures"] = set()

        if post_scan_confidence_ranked_entry_enabled and post_scan_entry_candidates:
            created_orders, daily_trades, cap_reached = self._execute_post_scan_ranked_entries(
                run_id=run_id,
                profile_id=profile_id,
                candidates=post_scan_entry_candidates,
                created_orders=created_orders,
                daily_trades=daily_trades,
                max_trades_per_day=max_trades_per_day,
                cap_reached=cap_reached,
                skipped=skipped,
                skip_stage_counts=skip_stage_counts,
                stage_metrics=stage_metrics,
            )
            debug_state.update({
                "last_progress_reason": "post_scan_ranked_entry_completed",
                "last_progress_at_utc": utc_now_iso(),
                "post_scan_ranked_candidates": len(post_scan_entry_candidates),
            })

        completed_at = utc_now_iso()
        summary = self._build_summary(signals, errors, stale_tasks)
        result = {
            **self._build_progress_payload(
                profile_id=profile_id,
                total_tasks=total_tasks,
                completed_tasks=completed_tasks,
                created_orders=created_orders,
                daily_trades=daily_trades,
                cap_reached=cap_reached,
                scan_workers=resolved_workers,
                skipped=skipped,
                skip_stage_counts=skip_stage_counts,
                signals=signals,
                errors=errors,
                stale_tasks=stale_tasks,
                current_task=None,
                analysis_durations_ms=analysis_durations_ms,
                fetch_durations_ms=fetch_durations_ms,
                debug=debug_state,
                stage_metrics=stage_metrics,
                scope_diagnostics=scope_diagnostics,
                order_queue_state=order_queue_state,
            ),
            "scanned": scanned,
        }
        final_status = self._resolve_final_status(total_tasks=total_tasks, errors=errors)
        return self._finalize_run(
            run_id,
            requested_by,
            symbols,
            intervals,
            modes,
            created_at=created_at,
            completed_at=completed_at,
            signal_count=len(signals),
            scan_workers=resolved_workers,
            summary=summary,
            result=result,
            errors=errors,
            final_status=final_status,
            trace_event="SCAN_COMPLETED" if final_status == "COMPLETED" else "SCAN_DEGRADED",
            profile_id=profile_id,
        )

    def _execute_post_scan_ranked_entries(
        self,
        *,
        run_id: str,
        profile_id: str,
        candidates: list[dict[str, Any]],
        created_orders: int,
        daily_trades: int,
        max_trades_per_day: int,
        cap_reached: bool,
        skipped: dict[str, int],
        skip_stage_counts: dict[str, int],
        stage_metrics: dict[str, Any],
    ) -> tuple[int, int, bool]:
        ranked_candidates = self._rank_post_scan_entry_candidates(candidates)
        total_candidates = len(ranked_candidates)
        for index, candidate in enumerate(ranked_candidates, start=1):
            signal = candidate.get("signal") or {}
            signal_id = str(candidate.get("signal_id") or "")
            snapshot = dict(candidate.get("snapshot") or {})
            symbol = str(signal.get("symbol") or "").upper()
            interval = str(signal.get("interval") or "").lower()
            mode = str(signal.get("mode") or "").upper()
            self.scan_control.mark_running(
                run_id,
                {
                    "symbol": symbol,
                    "interval": interval,
                    "mode": mode,
                    "phase": "POST_SCAN_RANKED_ENTRY",
                    "ranked_candidate_index": index,
                    "ranked_candidate_total": total_candidates,
                    "signal_id": signal_id or None,
                },
                profile_id=profile_id,
            )
            signal_payload = {**signal, "signal_id": signal_id, "profile_id": profile_id}
            if daily_trades >= max_trades_per_day:
                cap_reached = True
                skipped["daily_cap_reached"] += 1
                self.trace_service.log_event("SCAN_SKIPPED", run_id=run_id, signal=signal_payload, source="SCAN", status="SKIPPED", decision="SKIP", reason_code="DAILY_CAP_REACHED", reason_text="Daily trade cap reached", profile_id=profile_id)
                continue
            if self._has_duplicate_open_order(signal, profile_id=profile_id):
                skipped["duplicate_open"] += 1
                self.trace_service.log_event("SCAN_SKIPPED", run_id=run_id, signal=signal_payload, source="SCAN", status="SKIPPED", decision="SKIP", reason_code="DUPLICATE_OPEN", reason_text="Duplicate open order exists", profile_id=profile_id)
                continue
            entry_price = self._resolve_entry_price(signal, snapshot)
            sizing = self._compute_auto_order_sizing(entry_price, signal=signal, profile_id=profile_id)
            if sizing is not None:
                quantity = float(sizing.get("quantity") or 0.0)
                if quantity <= 0:
                    skipped["insufficient_balance"] += 1
                    available_balance = float(sizing.get("available_balance") or 0.0)
                    reason_text = "Paper balance is insufficient for this auto order" if available_balance <= 0 else "Auto order resolved to zero quantity"
                    self.trace_service.log_event("SCAN_SKIPPED", run_id=run_id, signal=signal_payload, source="SCAN", status="SKIPPED", decision="SKIP", reason_code="INSUFFICIENT_BALANCE", reason_text=reason_text, profile_id=profile_id)
                    continue
            execution_started = time.perf_counter()
            try:
                opened = self._open_auto_order(signal={**signal_payload, "run_id": run_id, "entry": entry_price, "paper_sizing": sizing or {}}, entry_price=entry_price, sizing=sizing, profile_id=profile_id)
            except (
                BinanceUsdmManualLiveError,
                ExecutionPolicyViolationError,
                RuntimeProfileAccessError,
                RuntimeProfileConnectivityError,
                UnsupportedExecutionProfileError,
            ) as exc:
                self._record_auto_order_skip(
                    run_id=run_id,
                    signal=signal_payload,
                    skipped=skipped,
                    skip_stage_counts=skip_stage_counts,
                    reason_text=str(exc),
                    profile_id=profile_id,
                )
                continue
            self._append_stage_metric(stage_metrics, "execution_ms", round((time.perf_counter() - execution_started) * 1000.0, 4))
            self._increment_stage_counter(stage_metrics, "orders_created")
            signal["execution_outcome"] = opened.get("signal_outcome") or {
                "order_id": ((opened.get("order") or {}).get("order_id")),
                "signal_outcome": str(((opened.get("submission") or {}).get("submission_status") or (opened.get("order") or {}).get("submission_status") or "ORDER_REQUEST_SENT")).upper(),
                "submission_status": ((opened.get("submission") or {}).get("submission_status") or (opened.get("order") or {}).get("submission_status")),
                "order_status": ((opened.get("order") or {}).get("status")),
                "venue_order_id": ((opened.get("order") or {}).get("venue_order_id")),
                "client_order_id": ((opened.get("order") or {}).get("client_order_id")),
            }
            created_orders += 1
            daily_trades += 1
        return created_orders, daily_trades, cap_reached

    @staticmethod
    def _rank_post_scan_entry_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            candidates,
            key=lambda item: (
                -float((item.get("signal") or {}).get("confidence") or 0.0),
                str((item.get("signal") or {}).get("symbol") or "").upper(),
                str((item.get("signal") or {}).get("interval") or "").lower(),
                str((item.get("signal") or {}).get("mode") or "").upper(),
                str((item.get("signal") or {}).get("direction") or "").upper(),
            ),
        )

    def _update_run_progress(
        self,
        run_id: str,
        requested_by: str,
        symbols: list[str],
        intervals: list[str],
        modes: list[str],
        *,
        profile_id: str = PAPER_PROFILE_ID,
        status: str = "RUNNING",
        summary_override: str | None = None,
        total_tasks: int,
        completed_tasks: int,
        created_orders: int,
        daily_trades: int,
        cap_reached: bool,
        scan_workers: int,
        skipped: dict[str, int],
        skip_stage_counts: dict[str, int],
        signals: list[dict[str, Any]],
        errors: list[dict[str, str]],
        stale_tasks: int,
        current_task: dict[str, Any] | None,
        analysis_durations_ms: list[float],
        fetch_durations_ms: list[float],
        debug: dict[str, Any] | None = None,
        stage_metrics: dict[str, Any] | None = None,
        scope_diagnostics: dict[str, Any] | None = None,
        order_queue_state: dict[str, Any] | None = None,
    ) -> None:
        with session_scope() as session:
            existing_run = self.scan_repo.get_run(session, run_id)
            resolved_profile_id = str((existing_run or {}).get("profile_id") or PAPER_PROFILE_ID)
            self.scan_repo.save_run(session, {
                "run_id": run_id,
                "profile_id": resolved_profile_id,
                "requested_by": requested_by,
                "status": status,
                "symbols_csv": ",".join(symbols),
                "intervals_csv": ",".join(intervals),
                "modes_csv": ",".join(modes),
                "signal_count": len(signals),
                "summary": summary_override or f"{completed_tasks}/{total_tasks} scans ongoing",
                "error_text": errors[-1]["error"] if errors else None,
                "created_at_utc": existing_run["created_at_utc"],
                "started_at_utc": existing_run["started_at_utc"],
                "finished_at_utc": existing_run["finished_at_utc"] if status == "STOPPED" else None,
                "payload_json": dumps_json({
                    "symbols": symbols,
                    "active_symbols": list((self._active_universe_filters.get(resolved_profile_id) or {}).get("active_symbols") or symbols),
                    "intervals": intervals,
                    "modes": modes,
                    "scan_workers": scan_workers,
                }),
                "result_json": dumps_json(self._build_progress_payload(
                    profile_id=resolved_profile_id,
                    total_tasks=total_tasks,
                    completed_tasks=completed_tasks,
                    created_orders=created_orders,
                    daily_trades=daily_trades,
                    cap_reached=cap_reached,
                    scan_workers=scan_workers,
                    skipped=skipped,
                    skip_stage_counts=skip_stage_counts,
                    signals=signals,
                    errors=errors,
                    stale_tasks=stale_tasks,
                    current_task=current_task,
                    analysis_durations_ms=analysis_durations_ms,
                    fetch_durations_ms=fetch_durations_ms,
                    debug=debug,
                    stage_metrics=stage_metrics,
                    scope_diagnostics=scope_diagnostics,
                    order_queue_state=order_queue_state,
                )),
            })
        self.scan_control.update(
            profile_id=resolved_profile_id,
            active_run_id=run_id,
            active_status=status,
            current_task=current_task,
            progress_updated_at_utc=utc_now_iso(),
            last_progress_completed_tasks=completed_tasks,
        )
        stage = str((current_task or {}).get("phase") or (current_task or {}).get("mode") or status or "RUNNING").upper()
        event_payload = {
            "stage": stage,
            "symbol": (current_task or {}).get("symbol"),
            "interval": (current_task or {}).get("interval"),
            "mode": (current_task or {}).get("mode"),
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "remaining_tasks": max(0, int(total_tasks) - int(completed_tasks)),
            "percent_complete": round((max(0, min(int(completed_tasks), int(total_tasks))) / int(total_tasks)) * 100.0, 2) if int(total_tasks) else 100.0,
            "queue_metrics": self.inference_bus.snapshot(),
        }
        self._emit_scan_event("SCAN_PROGRESS", profile_id=resolved_profile_id, run_id=run_id, **event_payload)
        if current_task:
            self._emit_scan_event("SCAN_STAGE_UPDATED", profile_id=resolved_profile_id, run_id=run_id, **event_payload)

    def _honor_scan_control(
        self,
        run_id: str,
        requested_by: str,
        symbols: list[str],
        intervals: list[str],
        modes: list[str],
        *,
        profile_id: str = PAPER_PROFILE_ID,
        total_tasks: int,
        completed_tasks: int,
        created_orders: int,
        daily_trades: int,
        cap_reached: bool,
        scan_workers: int,
        skipped: dict[str, int],
        skip_stage_counts: dict[str, int],
        signals: list[dict[str, Any]],
        errors: list[dict[str, str]],
        stale_tasks: int,
        current_task: dict[str, Any] | None,
        analysis_durations_ms: list[float],
        fetch_durations_ms: list[float],
        stage_metrics: dict[str, Any],
        scope_diagnostics: dict[str, Any],
    ) -> str:
        pause_recorded = False
        while True:
            state = self.scan_control.get_state(profile_id=profile_id)
            if state.get("stop_requested"):
                self.scan_control.mark_stopping(run_id, current_task, completed_tasks=completed_tasks, profile_id=profile_id)
                self._update_run_progress(
                    run_id,
                    requested_by,
                    symbols,
                    intervals,
                    modes,
                    status="STOPPED",
                    summary_override=f"Stopped at {completed_tasks}/{total_tasks} scans",
                    total_tasks=total_tasks,
                    completed_tasks=completed_tasks,
                    created_orders=created_orders,
                    daily_trades=daily_trades,
                    cap_reached=cap_reached,
                    scan_workers=scan_workers,
                    skipped=skipped,
                    skip_stage_counts=skip_stage_counts,
                    signals=signals,
                    errors=errors,
                    stale_tasks=stale_tasks,
                    current_task=current_task,
                    analysis_durations_ms=analysis_durations_ms,
                    fetch_durations_ms=fetch_durations_ms,
                    stage_metrics=stage_metrics,
                    scope_diagnostics=scope_diagnostics,
                )
                return "stop"
            if state.get("desired_state") == "PAUSED":
                if not pause_recorded:
                    self.scan_control.mark_paused(run_id, current_task, completed_tasks=completed_tasks, profile_id=profile_id)
                    self._update_run_progress(
                        run_id,
                        requested_by,
                        symbols,
                        intervals,
                        modes,
                        status="PAUSED",
                        summary_override=f"Paused at {completed_tasks}/{total_tasks} scans",
                        total_tasks=total_tasks,
                        completed_tasks=completed_tasks,
                        created_orders=created_orders,
                        daily_trades=daily_trades,
                        cap_reached=cap_reached,
                        scan_workers=scan_workers,
                        skipped=skipped,
                        skip_stage_counts=skip_stage_counts,
                        signals=signals,
                        errors=errors,
                        stale_tasks=stale_tasks,
                        current_task=current_task,
                        analysis_durations_ms=analysis_durations_ms,
                        fetch_durations_ms=fetch_durations_ms,
                        stage_metrics=stage_metrics,
                        scope_diagnostics=scope_diagnostics,
                    )
                    pause_recorded = True
                time.sleep(0.25)
                continue
            self.scan_control.mark_running(run_id, current_task, completed_tasks=completed_tasks, profile_id=profile_id)
            if pause_recorded:
                self._update_run_progress(
                    run_id,
                    requested_by,
                    symbols,
                    intervals,
                    modes,
                    status="RUNNING",
                    total_tasks=total_tasks,
                    completed_tasks=completed_tasks,
                    created_orders=created_orders,
                    daily_trades=daily_trades,
                    cap_reached=cap_reached,
                    scan_workers=scan_workers,
                    skipped=skipped,
                    skip_stage_counts=skip_stage_counts,
                    signals=signals,
                    errors=errors,
                    stale_tasks=stale_tasks,
                    current_task=current_task,
                    analysis_durations_ms=analysis_durations_ms,
                    fetch_durations_ms=fetch_durations_ms,
                    stage_metrics=stage_metrics,
                    scope_diagnostics=scope_diagnostics,
                )
            return "continue"

    def _finalize_run(
        self,
        run_id: str,
        requested_by: str,
        symbols: list[str],
        intervals: list[str],
        modes: list[str],
        *,
        created_at: str,
        completed_at: str,
        signal_count: int,
        scan_workers: int,
        summary: str,
        result: dict[str, Any],
        errors: list[dict[str, str]],
        final_status: str,
        trace_event: str,
        profile_id: str = PAPER_PROFILE_ID,
        resolved_config_hash: str = "",
    ) -> dict[str, Any]:
        profile_id = str(profile_id or PAPER_PROFILE_ID)
        control_state = self.scan_control.get_state(profile_id=profile_id)
        stop_meta = {}
        if final_status == "STOPPED":
            control_last_action = str(control_state.get("last_action") or "")
            stop_cause = "stopped"
            if control_last_action == "force_stop":
                stop_cause = "force_stop_requested"
            elif control_last_action == "stop":
                stop_cause = "stop_requested"
            stop_meta = {
                "stop_cause": stop_cause,
                "stop_requested_by": control_state.get("stop_requested_by"),
                "force_stop_requested_by": control_state.get("force_stop_requested_by"),
                "control_last_action": control_last_action,
            }
            result = {
                **result,
                **stop_meta,
            }
        with session_scope() as session:
            self.scan_repo.save_run(session, {
                "run_id": run_id,
                "profile_id": profile_id,
                "requested_by": requested_by,
                "status": final_status,
                "symbols_csv": ",".join(symbols),
                "intervals_csv": ",".join(intervals),
                "modes_csv": ",".join(modes),
                "signal_count": signal_count,
                "summary": summary,
                "error_text": errors[0]["error"] if errors else None,
                "created_at_utc": created_at,
                "started_at_utc": created_at,
                "finished_at_utc": completed_at,
                "payload_json": dumps_json({
                    "symbols": symbols,
                    "active_symbols": list((self._active_universe_filters.get(profile_id) or {}).get("active_symbols") or symbols),
                    "intervals": intervals,
                    "modes": modes,
                    "scan_workers": scan_workers,
                }),
                "result_json": dumps_json(result),
                "resolved_config_hash": str(resolved_config_hash or ""),
            })
            run = self.scan_repo.get_run(session, run_id)
        self.manifest_service.finalize_run_manifest(run_id, result, profile_id=profile_id)
        self.scan_control.finish_run(run_id, final_status, profile_id=profile_id)
        with self._active_run_context_lock:
            active_context = self._active_run_contexts.get(profile_id)
            if active_context and active_context.get("run_id") == run_id:
                self._active_run_contexts.pop(profile_id, None)
                self._active_universe_filters.pop(profile_id, None)
        self.trace_service.log_event(
            trace_event,
            run_id=run_id,
            source=requested_by,
            status=final_status,
            decision="SCAN",
            reason_text=summary,
            details=result,
            resolved_config_hash=resolved_config_hash,
            profile_id=profile_id,
        )
        progress = dict((result or {}).get("progress") or {})
        self._emit_scan_event(
            trace_event,
            profile_id=profile_id,
            run_id=run_id,
            stage=final_status,
            mode=requested_by,
            message=summary,
            total_tasks=progress.get("total_tasks"),
            completed_tasks=progress.get("completed_tasks"),
            queue_metrics=self.inference_bus.snapshot(),
        )
        self.performance_service.store_snapshot("scan_market")
        return {"run": run, "signals": result.get("signals", [])}

    def _build_progress_payload(
        self,
        *,
        profile_id: str = PAPER_PROFILE_ID,
        total_tasks: int,
        completed_tasks: int,
        created_orders: int,
        daily_trades: int,
        cap_reached: bool,
        scan_workers: int,
        skipped: dict[str, int],
        skip_stage_counts: dict[str, int],
        signals: list[dict[str, Any]],
        errors: list[dict[str, str]],
        stale_tasks: int,
        current_task: dict[str, Any] | None,
        analysis_durations_ms: list[float],
        fetch_durations_ms: list[float],
        debug: dict[str, Any] | None = None,
        stage_metrics: dict[str, Any] | None = None,
        scope_diagnostics: dict[str, Any] | None = None,
        order_queue_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        safe_total = max(0, int(total_tasks))
        safe_completed = max(0, min(int(completed_tasks), safe_total)) if safe_total else max(0, int(completed_tasks))
        percent_complete = round((safe_completed / safe_total) * 100.0, 2) if safe_total else 100.0
        return {
            "signals": signals,
            "errors": errors,
            "stale_tasks": stale_tasks,
            "created_orders": created_orders,
            "daily_trades": daily_trades,
            "cap_reached": cap_reached,
            "scan_workers": scan_workers,
            "skipped": skipped,
            "skip_stages": dict(skip_stage_counts),
            "timing": {
                "analysis": ScanRuntime._timing_stats(analysis_durations_ms),
                "market_fetch": ScanRuntime._timing_stats(fetch_durations_ms),
                "stages": self._stage_timing_payload(stage_metrics or {}),
            },
            "progress": {
                "total_tasks": safe_total,
                "completed_tasks": safe_completed,
                "remaining_tasks": max(0, safe_total - safe_completed),
                "percent_complete": percent_complete,
                "current_task": current_task,
            },
            "counts": {
                "total": len(signals),
                "buy": sum(1 for item in signals if item["direction"] == "BUY"),
                "sell": sum(1 for item in signals if item["direction"] == "SELL"),
                "neutral": sum(1 for item in signals if item["direction"] == "NEUTRAL"),
            },
            "debug": dict(debug or {}),
            "universe_filter": dict((self._active_universe_filters.get(profile_id) or {})),
            "scope": dict(scope_diagnostics or {}),
            "order_queue": {
                "submitted": int((order_queue_state or {}).get("submitted") or 0),
                "pending": int((order_queue_state or {}).get("pending") or 0),
                "verified": int((order_queue_state or {}).get("verified") or 0),
                "pending_verification": int((order_queue_state or {}).get("pending_verification") or 0),
            },
        }

    @staticmethod
    def _timing_stats(values: list[float]) -> dict[str, float | int | None]:
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
            "p50_ms": round(ScanRuntime._percentile(sorted_values, 50), 4),
            "p95_ms": round(ScanRuntime._percentile(sorted_values, 95), 4),
            "p99_ms": round(ScanRuntime._percentile(sorted_values, 99), 4),
            "total_ms": round(sum(values), 4),
        }

    @staticmethod
    def _percentile(sorted_values: list[float], percentile: float) -> float:
        if not sorted_values:
            return 0.0
        if len(sorted_values) == 1:
            return float(sorted_values[0])
        rank = (len(sorted_values) - 1) * (percentile / 100.0)
        lower = int(rank)
        upper = min(lower + 1, len(sorted_values) - 1)
        if lower == upper:
            return float(sorted_values[lower])
        weight = rank - lower
        return float(sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * weight)

    @staticmethod
    def _new_stage_metrics() -> dict[str, Any]:
        return {
            "analysis_ms": [],
            "analysis_queue_wait_ms": [],
            "market_fetch_total_ms": [],
            "market_fetch_live_ms": [],
            "market_fetch_cache_load_ms": [],
            "market_persist_ms": [],
            "indicator_build_ms": [],
            "htf_resolve_ms": [],
            "signal_audit_ms": [],
            "signal_persist_ms": [],
            "signal_attribution_ms": [],
            "execution_ms": [],
            "adapter_total_ms": [],
            "engine_lookup_ms": [],
            "response_validation_ms": [],
            "timeout_lookup_ms": [],
            "analyzer_status_write_ms": [],
            "engine_total_ms": [],
            "base_analyzer_ms": [],
            "self_learning_total_ms": [],
            "self_learning_inference_ms": [],
            "self_learning_retrieval_ms": [],
            "market_bundle_requests": 0,
            "market_bundle_unique_fetches": 0,
            "market_bundle_cache_hits": 0,
            "htf_trend_requests": 0,
            "htf_trend_unique_resolutions": 0,
            "htf_trend_cache_hits": 0,
            "candle_write_skips": 0,
            "rows_written": 0,
            "analysis_tasks": 0,
            "signals_emitted": 0,
            "orders_created": 0,
            "analysis_fallbacks": 0,
            "self_learning_active_tasks": 0,
            "self_learning_bypassed_tasks": 0,
            "fetch_worker_capacity": 0,
            "analysis_worker_capacity": 1,
            "inference_worker_capacity": 1,
            "inference_queue_limit": 0,
            "inference_queue_rejections": 0,
            "inference_timeouts": 0,
            "inference_failures": 0,
            "max_concurrent_fetches": 0,
            "pending_fetch_samples": 0,
            "pending_fetch_sum": 0,
        }

    @staticmethod
    def _append_stage_metric(metrics: dict[str, Any], key: str, value: float | None) -> None:
        if value is None:
            return
        metrics.setdefault(key, []).append(float(value))

    @staticmethod
    def _increment_stage_counter(metrics: dict[str, Any], key: str, delta: int = 1) -> None:
        metrics[key] = int(metrics.get(key) or 0) + int(delta)

    def _stage_timing_payload(self, metrics: dict[str, Any]) -> dict[str, Any]:
        market_bundle_requests = int(metrics.get("market_bundle_requests") or 0)
        market_bundle_unique_fetches = int(metrics.get("market_bundle_unique_fetches") or 0)
        market_bundle_cache_hits = int(metrics.get("market_bundle_cache_hits") or 0)
        htf_trend_requests = int(metrics.get("htf_trend_requests") or 0)
        htf_trend_unique_resolutions = int(metrics.get("htf_trend_unique_resolutions") or 0)
        htf_trend_cache_hits = int(metrics.get("htf_trend_cache_hits") or 0)
        pending_fetch_samples = int(metrics.get("pending_fetch_samples") or 0)
        pending_fetch_sum = int(metrics.get("pending_fetch_sum") or 0)
        return {
            "analysis": self._timing_stats(list(metrics.get("analysis_ms") or [])),
            "analysis_queue_wait": self._timing_stats(list(metrics.get("analysis_queue_wait_ms") or [])),
            "market_fetch_total": self._timing_stats(list(metrics.get("market_fetch_total_ms") or [])),
            "market_fetch_live": self._timing_stats(list(metrics.get("market_fetch_live_ms") or [])),
            "market_fetch_cache_load": self._timing_stats(list(metrics.get("market_fetch_cache_load_ms") or [])),
            "market_persist": self._timing_stats(list(metrics.get("market_persist_ms") or [])),
            "indicator_build": self._timing_stats(list(metrics.get("indicator_build_ms") or [])),
            "htf_resolve": self._timing_stats(list(metrics.get("htf_resolve_ms") or [])),
            "signal_audit": self._timing_stats(list(metrics.get("signal_audit_ms") or [])),
            "signal_persist": self._timing_stats(list(metrics.get("signal_persist_ms") or [])),
            "signal_attribution": self._timing_stats(list(metrics.get("signal_attribution_ms") or [])),
            "execution": self._timing_stats(list(metrics.get("execution_ms") or [])),
            "adapter_total": self._timing_stats(list(metrics.get("adapter_total_ms") or [])),
            "engine_lookup": self._timing_stats(list(metrics.get("engine_lookup_ms") or [])),
            "response_validation": self._timing_stats(list(metrics.get("response_validation_ms") or [])),
            "timeout_lookup": self._timing_stats(list(metrics.get("timeout_lookup_ms") or [])),
            "analyzer_status_write": self._timing_stats(list(metrics.get("analyzer_status_write_ms") or [])),
            "engine_total": self._timing_stats(list(metrics.get("engine_total_ms") or [])),
            "base_analyzer": self._timing_stats(list(metrics.get("base_analyzer_ms") or [])),
            "self_learning_total": self._timing_stats(list(metrics.get("self_learning_total_ms") or [])),
            "self_learning_inference": self._timing_stats(list(metrics.get("self_learning_inference_ms") or [])),
            "self_learning_retrieval": self._timing_stats(list(metrics.get("self_learning_retrieval_ms") or [])),
            "market_bundle_requests": market_bundle_requests,
            "market_bundle_unique_fetches": market_bundle_unique_fetches,
            "market_bundle_cache_hits": market_bundle_cache_hits,
            "market_bundle_cache_hit_rate": round((market_bundle_cache_hits / market_bundle_requests) * 100.0, 2) if market_bundle_requests else None,
            "htf_trend_requests": htf_trend_requests,
            "htf_trend_unique_resolutions": htf_trend_unique_resolutions,
            "htf_trend_cache_hits": htf_trend_cache_hits,
            "htf_trend_cache_hit_rate": round((htf_trend_cache_hits / htf_trend_requests) * 100.0, 2) if htf_trend_requests else None,
            "candle_write_skips": int(metrics.get("candle_write_skips") or 0),
            "rows_written": int(metrics.get("rows_written") or 0),
            "analysis_tasks": int(metrics.get("analysis_tasks") or 0),
            "signals_emitted": int(metrics.get("signals_emitted") or 0),
            "orders_created": int(metrics.get("orders_created") or 0),
            "analysis_fallbacks": int(metrics.get("analysis_fallbacks") or 0),
            "self_learning_active_tasks": int(metrics.get("self_learning_active_tasks") or 0),
            "self_learning_bypassed_tasks": int(metrics.get("self_learning_bypassed_tasks") or 0),
            "fetch_worker_capacity": int(metrics.get("fetch_worker_capacity") or 0),
            "analysis_worker_capacity": int(metrics.get("analysis_worker_capacity") or 1),
            "inference_worker_capacity": int(metrics.get("inference_worker_capacity") or 1),
            "inference_queue_limit": int(metrics.get("inference_queue_limit") or 0),
            "inference_queue_rejections": int(metrics.get("inference_queue_rejections") or 0),
            "inference_timeouts": int(metrics.get("inference_timeouts") or 0),
            "inference_failures": int(metrics.get("inference_failures") or 0),
            "max_concurrent_fetches": int(metrics.get("max_concurrent_fetches") or 0),
            "avg_concurrent_fetches": round((pending_fetch_sum / pending_fetch_samples), 4) if pending_fetch_samples else None,
        }

    def _resolve_htf_trend(
        self,
        symbol: str,
        interval: str,
        market_bundle_cache: dict[tuple[str, str], dict[str, Any]],
        market_bundle_inflight: dict[tuple[str, str], Event],
        htf_trend_cache: dict[tuple[str, str], str | None],
        cache_lock: Lock,
        stage_metrics: dict[str, Any],
    ) -> str | None:
        htf_interval = HTF_MAP.get(interval)
        if not htf_interval:
            return None
        self._increment_stage_counter(stage_metrics, "htf_trend_requests")
        cache_key = (symbol, htf_interval)
        with cache_lock:
            if cache_key in htf_trend_cache:
                self._increment_stage_counter(stage_metrics, "htf_trend_cache_hits")
                return htf_trend_cache[cache_key]
        try:
            started = time.perf_counter()
            market_bundle, _cache_hit = self._get_market_snapshot_cached(symbol, htf_interval, market_bundle_cache, market_bundle_inflight, cache_lock, stage_metrics)
            trend, _strength, _factors = determine_trend(market_bundle["snapshot"])
            resolved = "BUY" if trend == "BULLISH" else "SELL" if trend == "BEARISH" else "MIXED"
            self._append_stage_metric(stage_metrics, "htf_resolve_ms", round((time.perf_counter() - started) * 1000.0, 4))
            self._increment_stage_counter(stage_metrics, "htf_trend_unique_resolutions")
            with cache_lock:
                htf_trend_cache[cache_key] = resolved
            return resolved
        except Exception:
            return None

    def _get_market_snapshot_cached(
        self,
        symbol: str,
        interval: str,
        market_bundle_cache: dict[tuple[str, str], dict[str, Any]],
        market_bundle_inflight: dict[tuple[str, str], Event],
        cache_lock: Lock,
        stage_metrics: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        cache_key = (symbol, interval)
        self._increment_stage_counter(stage_metrics, "market_bundle_requests")
        while True:
            with cache_lock:
                cached = market_bundle_cache.get(cache_key)
                if cached is not None:
                    self._increment_stage_counter(stage_metrics, "market_bundle_cache_hits")
                    return cached, True
                inflight = market_bundle_inflight.get(cache_key)
                if inflight is None:
                    inflight = Event()
                    market_bundle_inflight[cache_key] = inflight
                    is_leader = True
                else:
                    is_leader = False
            if is_leader:
                break
            inflight.wait()
        self._increment_stage_counter(stage_metrics, "market_bundle_unique_fetches")
        try:
            bundle = self.market_data.get_market_snapshot(symbol, interval)
        finally:
            with cache_lock:
                waiter = market_bundle_inflight.pop(cache_key, None)
                if waiter is not None:
                    waiter.set()
        metrics = dict(bundle.get("metrics") or {})
        self._append_stage_metric(stage_metrics, "market_fetch_live_ms", metrics.get("fetch_ms"))
        self._append_stage_metric(stage_metrics, "market_fetch_cache_load_ms", metrics.get("cache_load_ms"))
        self._append_stage_metric(stage_metrics, "market_persist_ms", metrics.get("persist_ms"))
        self._append_stage_metric(stage_metrics, "indicator_build_ms", metrics.get("snapshot_build_ms"))
        self._increment_stage_counter(stage_metrics, "rows_written", int(metrics.get("rows_written") or 0))
        if metrics.get("write_skipped"):
            self._increment_stage_counter(stage_metrics, "candle_write_skips")
        with cache_lock:
            market_bundle_cache[cache_key] = bundle
        return bundle, False

    def _fetch_interval_bundle(
        self,
        symbol: str,
        interval: str,
        market_bundle_cache: dict[tuple[str, str], dict[str, Any]],
        market_bundle_inflight: dict[tuple[str, str], Event],
        htf_trend_cache: dict[tuple[str, str], str | None],
        cache_lock: Lock,
        stage_metrics: dict[str, Any],
    ) -> tuple[dict[str, Any], float, str | None]:
        started = time.perf_counter()
        bundle, _cache_hit = self._get_market_snapshot_cached(symbol, interval, market_bundle_cache, market_bundle_inflight, cache_lock, stage_metrics)
        htf_trend = self._resolve_htf_trend(symbol, interval, market_bundle_cache, market_bundle_inflight, htf_trend_cache, cache_lock, stage_metrics)
        total_ms = round((time.perf_counter() - started) * 1000.0, 4)
        self._append_stage_metric(stage_metrics, "market_fetch_total_ms", total_ms)
        return bundle, total_ms, htf_trend

    def _execute_analysis_task(
        self,
        *,
        run_id: str,
        profile_id: str,
        requested_by: str,
        scan_workers: int,
        symbol: str,
        interval: str,
        mode: str,
        snapshot: dict[str, Any],
        submitted_at: float,
    ) -> dict[str, Any]:
        prefilter = self._prefilter_snapshot(snapshot, mode)
        if prefilter is not None:
            started = time.perf_counter()
            return {
                "symbol": symbol,
                "interval": interval,
                "mode": mode,
                "snapshot": dict(snapshot),
                "analysis": None,
                "analysis_ms": round((time.perf_counter() - started) * 1000.0, 4),
                "queue_wait_ms": round((started - submitted_at) * 1000.0, 4),
                "prefilter": {
                    "stage": prefilter[0],
                    "reason": prefilter[1],
                },
            }
        local_queue_wait_ms = round((time.perf_counter() - submitted_at) * 1000.0, 4)
        bus_result = self.inference_bus.submit(
            profile_id=profile_id,
            run_id=run_id,
            symbol=symbol,
            interval=interval,
            mode=mode,
            requested_by=requested_by,
            execute=lambda: self._run_inference_job(
                run_id=run_id,
                profile_id=profile_id,
                requested_by=requested_by,
                symbol=symbol,
                interval=interval,
                mode=mode,
                snapshot=snapshot,
            ),
        )
        job = dict(bus_result.get("job") or {})
        payload = dict(bus_result.get("payload") or {})
        payload["queue_wait_ms"] = round(local_queue_wait_ms + float(job.get("queue_wait_ms") or 0.0), 4)
        payload["inference_job"] = job
        return payload

    def _run_inference_job(
        self,
        *,
        run_id: str,
        profile_id: str,
        requested_by: str,
        symbol: str,
        interval: str,
        mode: str,
        snapshot: dict[str, Any],
    ) -> InferenceJobOutcome:
        started = time.perf_counter()
        legacy_snapshot = dict(snapshot)
        timestamp_utc = str(legacy_snapshot.get("timestamp") or legacy_snapshot.get("close_time_utc") or utc_now_iso())
        raw_candles = list(legacy_snapshot.get("candles") or [])
        if not raw_candles:
            synthetic_close = str(legacy_snapshot.get("close_time_utc") or timestamp_utc)
            price = float(legacy_snapshot.get("price") or legacy_snapshot.get("close") or 0.0)
            raw_candles = [{
                "open": float(legacy_snapshot.get("open") or price),
                "high": float(legacy_snapshot.get("high") or price),
                "low": float(legacy_snapshot.get("low") or price),
                "close": price,
                "volume": float(legacy_snapshot.get("volume") or 0.0),
                "close_time_utc": synthetic_close,
            }]
        raw_htf_candles = {}
        htf_interval = HTF_MAP.get(interval)
        if htf_interval and isinstance(legacy_snapshot.get("htf_candles"), list):
            raw_htf_candles[htf_interval] = list(legacy_snapshot.get("htf_candles") or [])
        try:
            snapshot_artifact = self.snapshot_builder.build(
                symbol=symbol,
                interval=interval,
                timestamp_utc=timestamp_utc,
                request_kind=RequestKind.LIVE_SCAN,
                raw_candles=raw_candles,
                raw_htf_candles=raw_htf_candles,
                engine_mode="LIVE",
                runtime_context_hints={"mode": mode, "requested_by": requested_by, "profile_id": profile_id},
                data_source="live",
                mode=SnapshotMode.LIVE_RUNTIME,
            )
            runtime_context = RuntimeContextSection(
                source_context="live_scan",
                requested_by=requested_by,
                paper_or_live_mode=mode,
                engine_budget_hint="normal",
                runtime_phase="scan",
            )
            execution_context = ExecutionContextSection(
                position_exists=False,
                position_direction="NONE",
                position_size_fraction=0.0,
                symbol_exposure_fraction=0.0,
            )
            analysis_request = build_analysis_request(
                snapshot=snapshot_artifact,
                execution_context=execution_context,
                runtime_context=runtime_context,
                trade_mode=mode,
                request_kind=RequestKind.LIVE_SCAN,
                run_id=run_id,
            )
        except Exception as exc:
            fallback = self.fallback_handler.handle_invalid_request(
                legacy_snapshot,
                str(exc),
                engine_name="runtime",
                request_id=f"invalid-{symbol.lower()}-{interval}-{mode.lower()}",
            )
            analysis = {
                "signal_status": fallback.status.signal_status.value,
                "direction": fallback.decision.direction.value,
                "confidence": fallback.scores.confidence,
                "probability": fallback.scores.probability,
                "entry_price": fallback.execution_guidance.entry_price,
                "stop_loss": fallback.execution_guidance.stop_loss,
                "take_profit": fallback.execution_guidance.take_profit,
                "risk_reward": fallback.scores.risk_reward_estimate,
                "summary": fallback.decision.decision_summary or fallback.observability.reason_summary or "",
                "engine_name": fallback.identity.engine_name,
                "engine_version": fallback.identity.engine_version,
                "schema_version": fallback.contract.response_schema_version,
                "analysis_latency_ms": fallback.observability.analysis_latency_ms or 0.0,
                "fallback_used": True,
                "fallback_reason": fallback.fallback_degradation.fallback_reason,
                "warnings": list(fallback.observability.warnings),
                "decision_payload": {"signal": {"direction": "NEUTRAL"}},
                "signal": {
                    "symbol": symbol,
                    "interval": interval,
                    "mode": mode,
                    "direction": "NEUTRAL",
                    "confidence": 0.0,
                    "probability": 0.0,
                    "entry_price": None,
                    "stop_loss": None,
                    "take_profit": None,
                    "risk_reward": None,
                    "summary": fallback.decision.decision_summary or fallback.observability.reason_summary or "",
                    "regime": "DEGRADED",
                    "trend": "UNKNOWN",
                    "trend_strength": 0.0,
                    "no_trade_reason": fallback.fallback_degradation.fallback_reason,
                    "advanced_analysis": {},
                    "adaptive_context": {},
                    "factors": [],
                },
                "v6_result": fallback.to_dict(),
            }
            finished = time.perf_counter()
            return InferenceJobOutcome(payload={
                "symbol": symbol,
                "interval": interval,
                "mode": mode,
                "snapshot": dict(legacy_snapshot),
                "analysis": analysis,
                "analysis_ms": round((finished - started) * 1000.0, 4),
                "queue_wait_ms": 0.0,
                "prefilter": None,
            })

        legacy_request = to_v5_request(analysis_request)
        legacy_request["mode"] = mode
        legacy_request["snapshot"] = {**legacy_request["snapshot"], **legacy_snapshot}
        legacy_request["snapshot"]["candles"] = list(legacy_request["snapshot"].get("candles") or raw_candles)
        legacy_request["snapshot"].setdefault("htf_trend", legacy_snapshot.get("htf_trend"))
        legacy_request["snapshot"].setdefault("session_label", legacy_snapshot.get("session_label"))
        legacy_request["snapshot"].setdefault("strategy_version", legacy_snapshot.get("strategy_version"))
        analysis = self.engine_adapter.analyze(
            symbol=symbol,
            interval=interval,
            mode=mode,
            snapshot=legacy_request["snapshot"],
            market_context=legacy_request.get("market_context"),
            runtime_context=legacy_request.get("runtime_context"),
            request_id=analysis_request.identity.request_id,
            timestamp=analysis_request.identity.timestamp_utc,
        )
        try:
            normalized_result = V6AnalysisResult.from_dict(dict(analysis.get("v6_result") or {})).validate()
            analysis["v6_result"] = normalized_result.to_dict()
        except Exception:
            normalized_result = self.fallback_handler.handle_invalid_result(
                analysis_request,
                analysis,
                engine_name=str(analysis.get("engine_name") or "unknown"),
            )
            analysis["v6_result"] = normalized_result.to_dict()
            analysis["signal_status"] = normalized_result.status.signal_status.value
            analysis["direction"] = normalized_result.decision.direction.value
            analysis["confidence"] = normalized_result.scores.confidence
            analysis["probability"] = normalized_result.scores.probability
            analysis["fallback_used"] = True
            analysis["fallback_reason"] = normalized_result.fallback_degradation.fallback_reason
            signal = dict(analysis.get("signal") or {})
            signal.update({
                "direction": "NEUTRAL",
                "confidence": 0.0,
                "probability": 0.0,
                "summary": normalized_result.decision.decision_summary or normalized_result.observability.reason_summary or "",
                "no_trade_reason": normalized_result.fallback_degradation.fallback_reason,
            })
            analysis["signal"] = signal

        finished = time.perf_counter()
        status = "TIMED_OUT" if str(analysis.get("fallback_reason") or "").upper() == "ENGINE_TIMEOUT" else "COMPLETED"
        return InferenceJobOutcome(
            payload={
                "symbol": symbol,
                "interval": interval,
                "mode": mode,
                "snapshot": dict(legacy_snapshot),
                "analysis": analysis,
                "analysis_ms": round((finished - started) * 1000.0, 4),
                "queue_wait_ms": 0.0,
                "prefilter": None,
            },
            status=status,
            error_text=str(analysis.get("fallback_reason") or "") if status == "TIMED_OUT" else None,
        )

    def _signal_record(self, run_id: str, signal: dict[str, Any], snapshot: dict[str, Any], signal_audit: dict[str, Any], analysis: dict[str, Any], *, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any]:
        return {
            "signal_id": f"sig-{uuid.uuid4().hex}",
            "profile_id": str(signal.get("profile_id") or profile_id or PAPER_PROFILE_ID),
            "run_id": run_id,
            "symbol": signal["symbol"],
            "interval": signal["interval"],
            "mode": signal["mode"],
            "direction": signal["direction"],
            "confidence": float(signal["confidence"] or 0.0),
            "regime": signal["regime"],
            "trend": signal["trend"],
            "trend_strength": float(signal["trend_strength"] or 0.0),
            "summary": signal["summary"],
            "no_trade_reason": signal.get("no_trade_reason"),
            "strategy_version": str(signal.get("adaptive_context", {}).get("strategy_version") or "v3-enhanced-v1"),
            "engine_name": str(analysis.get("engine_name") or "v4_default"),
            "engine_version": str(analysis.get("engine_version") or "v4-phase25"),
            "engine_schema_version": str(analysis.get("schema_version") or "analysis_result.v1"),
            "engine_fallback_used": bool(analysis.get("fallback_used")),
            "snapshot_json": dumps_json(snapshot),
            "features_json": dumps_json(build_signal_feature_vector(signal, snapshot)),
            "factors_json": dumps_list(signal.get("factors", [])),
            "audit_json": dumps_json(signal_audit),
            "created_at_utc": utc_now_iso(),
        }

    @staticmethod
    def _manifest_param_snapshot(settings: dict[str, str]) -> dict[str, Any]:
        keys = [
            "AUTONOMOUS_ENABLED",
            "AUTONOMOUS_MODES",
            "AUTONOMOUS_INTERVALS",
            "AUTONOMOUS_MIN_CONFIDENCE",
            "AUTONOMOUS_ALLOWED_TRADE_DIRECTIONS",
            "MAX_TRADES_PER_DAY",
            "POST_SCAN_CONFIDENCE_RANKED_ENTRY_ENABLED",
            "SCAN_WORKERS",
            "AUTONOMOUS_INFERENCE_WORKERS",
            "AUTONOMOUS_INFERENCE_QUEUE_SIZE",
            "SYMBOL_THROTTLE_ENABLED",
            "SYMBOL_THROTTLE_LOOKBACK_TRADES",
            "SYMBOL_THROTTLE_MAX_CONSECUTIVE_STOP_HITS",
            "SYMBOL_THROTTLE_MAX_STOP_HIT_RATE_PCT",
            "SYMBOL_THROTTLE_COOLDOWN_MINUTES",
        ]
        return {key: settings.get(key) for key in keys if key in settings}

    @staticmethod
    def _is_post_scan_confidence_ranked_entry_enabled(settings: dict[str, str]) -> bool:
        return str(settings.get("POST_SCAN_CONFIDENCE_RANKED_ENTRY_ENABLED", "false")).lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _risk_adjustment_factor(signal: dict[str, Any]) -> float:
        advanced = dict(signal.get("advanced_analysis") or {})
        stop_model = dict(advanced.get("stop_model") or {})
        stop_distance_atr = float(stop_model.get("stop_distance_atr") or 1.0)
        if stop_distance_atr <= 1.5:
            return 1.0
        return max(0.45, min(1.0, 1.5 / stop_distance_atr))

    @staticmethod
    def _components_used_for_signal(signal: dict[str, Any]) -> list[str]:
        components = {
            "regime_detector",
            "trend_detector",
            "structure_filter",
            "oscillator_gate",
            "probability_model",
            "audit_snapshot",
        }
        advanced = dict(signal.get("advanced_analysis") or {})
        learning = dict(advanced.get("learning_adjustments") or {})
        circuit = dict(advanced.get("circuit_breaker") or {})
        if advanced.get("session_label"):
            components.add("session_context")
        if signal.get("adaptive_context"):
            components.add("htf_alignment")
        if learning.get("learning_active"):
            components.add("learning_calibration")
        if float(learning.get("entry_penalty") or 0.0) > 0.0:
            components.add("entry_timing_penalty")
        if float(learning.get("component_penalty") or 0.0) > 0.0:
            components.add("component_penalty")
        if float(learning.get("execution_penalty") or 0.0) > 0.0:
            components.add("execution_penalty")
        if float(learning.get("stop_loss_multiplier") or 1.0) > 1.0:
            components.add("adaptive_stop")
        if circuit:
            components.add("circuit_breaker")
        probability_model = dict((((advanced.get("probability_model") or {}) if isinstance(advanced.get("probability_model"), dict) else {})))
        if probability_model:
            components.add("volume_context")
        return sorted(components)

    @staticmethod
    def _filter_contributions(signal: dict[str, Any], signal_audit: dict[str, Any]) -> list[dict[str, Any]]:
        advanced = dict(signal.get("advanced_analysis") or {})
        threshold_checks = list((signal_audit or {}).get("threshold_checks") or [])
        filters = []
        for item in threshold_checks:
            filters.append({
                "component_id": "structure_filter" if "rr" in str(item.get("name") or "").lower() else "probability_model",
                "name": item.get("name"),
                "threshold": item.get("threshold"),
                "value": item.get("value"),
                "passed": item.get("passed"),
                "reason": item.get("reason"),
            })
        circuit = dict(advanced.get("circuit_breaker") or {})
        if circuit:
            filters.append({
                "component_id": "circuit_breaker",
                "name": "circuit_breaker_state",
                "value": circuit.get("status"),
                "passed": str(circuit.get("status") or "CLOSED") != "OPEN",
                "reason": circuit.get("reason"),
            })
        return filters

    @staticmethod
    def _adjustment_contributions(signal: dict[str, Any]) -> list[dict[str, Any]]:
        advanced = dict(signal.get("advanced_analysis") or {})
        learning = dict(advanced.get("learning_adjustments") or {})
        items = []
        if learning:
            items.append({
                "component_id": "learning_calibration",
                "multiplier": learning.get("calibration_multiplier"),
                "reason": "Confidence calibration from realized outcomes.",
            })
        if float(learning.get("entry_penalty") or 0.0) > 0.0:
            items.append({
                "component_id": "entry_timing_penalty",
                "multiplier": round(1.0 - float(learning.get("entry_penalty") or 0.0), 4),
                "reason": "; ".join(learning.get("reasons") or []),
            })
        if float(learning.get("component_penalty") or 0.0) > 0.0:
            items.append({
                "component_id": "component_penalty",
                "multiplier": round(1.0 - float(learning.get("component_penalty") or 0.0), 4),
                "reason": ", ".join(learning.get("applied_components") or []),
            })
        if float(learning.get("execution_penalty") or 0.0) > 0.0:
            items.append({
                "component_id": "execution_penalty",
                "multiplier": round(1.0 - float(learning.get("execution_penalty") or 0.0), 4),
                "reason": "; ".join(learning.get("reasons") or []),
            })
        if float(learning.get("stop_loss_multiplier") or 1.0) > 1.0:
            items.append({
                "component_id": "adaptive_stop",
                "multiplier": learning.get("stop_loss_multiplier"),
                "reason": "Adaptive stop multiplier active.",
            })
        return items

    @staticmethod
    def _build_summary(signals: list[dict[str, Any]], errors: list[dict[str, str]], stale_tasks: int) -> str:
        buys = sum(1 for item in signals if item["direction"] == "BUY")
        sells = sum(1 for item in signals if item["direction"] == "SELL")
        neutrals = sum(1 for item in signals if item["direction"] == "NEUTRAL")
        parts = [f"{len(signals)} signals", f"{buys} buy", f"{sells} sell", f"{neutrals} neutral"]
        if stale_tasks:
            parts.append(f"{stale_tasks} stale")
        if errors:
            parts.append(f"{len(errors)} errors")
        return " · ".join(parts)

    @staticmethod
    def _resolve_final_status(*, total_tasks: int, errors: list[dict[str, str]]) -> str:
        if not errors:
            return "COMPLETED"
        safe_total = max(1, int(total_tasks))
        error_rate = len(errors) / safe_total
        return "DEGRADED" if error_rate >= DEGRADED_ERROR_RATE_THRESHOLD else "COMPLETED"

    def _load_settings_resolution(self, *, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any]:
        with session_scope() as session:
            return self.settings_repo.get_resolution(session, profile_id=profile_id)

    def _load_settings(self, *, profile_id: str = PAPER_PROFILE_ID) -> dict[str, str]:
        return dict(self._load_settings_resolution(profile_id=profile_id).get("settings") or {})

    @staticmethod
    def _resolve_allowed_trade_directions(settings: dict[str, str]) -> str:
        value = str(settings.get("AUTONOMOUS_ALLOWED_TRADE_DIRECTIONS") or DEFAULT_RUNTIME_SETTINGS["AUTONOMOUS_ALLOWED_TRADE_DIRECTIONS"] or "BOTH")
        normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
        if normalized in {"LONG", "BUY", "BUY_ONLY"}:
            return "LONG_ONLY"
        if normalized in {"SHORT", "SELL", "SELL_ONLY"}:
            return "SHORT_ONLY"
        if normalized in {"LONG_ONLY", "SHORT_ONLY", "BOTH"}:
            return normalized
        return "BOTH"

    @staticmethod
    def _resolve_float(value: object, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _resolve_scan_workers(explicit_value: int | None, settings: dict[str, str]) -> int:
        if explicit_value is not None:
            return max(1, int(explicit_value))
        try:
            return max(1, int(float(settings.get("AUTONOMOUS_SCAN_WORKERS", "4"))))
        except (TypeError, ValueError):
            return 4

    @staticmethod
    def _resolve_analysis_workers(scan_workers: int, settings: dict[str, str]) -> int:
        try:
            configured = int(float(settings.get("AUTONOMOUS_ANALYSIS_WORKERS", str(min(max(1, scan_workers), 8)))))
        except (TypeError, ValueError):
            configured = min(max(1, scan_workers), 8)
        return max(1, configured)

    @staticmethod
    def _resolve_inference_workers(settings: dict[str, str]) -> int:
        try:
            configured = int(float(settings.get("AUTONOMOUS_INFERENCE_WORKERS", DEFAULT_RUNTIME_SETTINGS["AUTONOMOUS_INFERENCE_WORKERS"])))
        except (TypeError, ValueError):
            configured = int(DEFAULT_RUNTIME_SETTINGS["AUTONOMOUS_INFERENCE_WORKERS"])
        return max(1, configured)

    @staticmethod
    def _resolve_inference_queue_size(settings: dict[str, str]) -> int:
        try:
            configured = int(float(settings.get("AUTONOMOUS_INFERENCE_QUEUE_SIZE", DEFAULT_RUNTIME_SETTINGS["AUTONOMOUS_INFERENCE_QUEUE_SIZE"])))
        except (TypeError, ValueError):
            configured = int(DEFAULT_RUNTIME_SETTINGS["AUTONOMOUS_INFERENCE_QUEUE_SIZE"])
        return max(1, configured)

    def _resolve_runtime_min_confidence(self, settings: dict[str, str], *, profile_id: str = PAPER_PROFILE_ID) -> tuple[float, dict[str, Any]]:
        fixed_threshold = self._resolve_float(settings.get("AUTONOMOUS_MIN_CONFIDENCE"), 35.0)
        policy = str(settings.get("AUTONOMOUS_CONFIDENCE_POLICY") or "FIXED").strip().upper()
        diagnostics: dict[str, Any] = {
            "policy": policy,
            "fixed_threshold": float(fixed_threshold),
            "resolved_threshold": float(fixed_threshold),
        }
        if policy != "PERCENTILE":
            return float(fixed_threshold), diagnostics
        lookback = max(25, int(self._resolve_float(settings.get("AUTONOMOUS_CONFIDENCE_LOOKBACK_TRACES"), 200.0)))
        percentile = min(0.99, max(0.5, self._resolve_float(settings.get("AUTONOMOUS_CONFIDENCE_PERCENTILE"), 0.90)))
        min_samples = max(10, int(self._resolve_float(settings.get("AUTONOMOUS_CONFIDENCE_MIN_SAMPLES"), 50.0)))
        floor = self._resolve_float(settings.get("AUTONOMOUS_CONFIDENCE_MIN_FLOOR"), 20.0)
        ceil = self._resolve_float(settings.get("AUTONOMOUS_CONFIDENCE_MAX_CEIL"), 40.0)
        confidences = self._recent_directional_runtime_confidences(limit=lookback, profile_id=profile_id)
        diagnostics.update({
            "percentile": float(percentile),
            "lookback_traces": int(lookback),
            "min_samples": int(min_samples),
            "floor": float(floor),
            "ceil": float(ceil),
            "sample_size": len(confidences),
        })
        if len(confidences) < min_samples:
            diagnostics["fallback_reason"] = "insufficient_trace_samples"
            return float(fixed_threshold), diagnostics
        percentile_value = self._percentile(sorted(confidences), percentile * 100.0)
        resolved = max(float(floor), min(float(ceil), float(percentile_value)))
        diagnostics["percentile_threshold"] = float(percentile_value)
        diagnostics["resolved_threshold"] = float(resolved)
        return float(resolved), diagnostics

    def _recent_directional_runtime_confidences(self, *, limit: int, profile_id: str = PAPER_PROFILE_ID) -> list[float]:
        snapshot = self.trace_service.get_snapshot(limit=max(1, int(limit)), profile_id=profile_id)
        values: list[float] = []
        for item in list(snapshot.get("items") or []):
            payload = item.get("signal_payload") or {}
            if not isinstance(payload, dict):
                continue
            direction = str(payload.get("direction") or "").upper()
            if direction not in {"BUY", "SELL"}:
                continue
            advanced = payload.get("advanced_analysis") or {}
            if not isinstance(advanced, dict):
                continue
            decision_path = advanced.get("decision_path") or {}
            if not isinstance(decision_path, dict):
                continue
            confidence = decision_path.get("runtime_confidence", payload.get("confidence"))
            try:
                values.append(float(confidence))
            except (TypeError, ValueError):
                continue
        return values

    @staticmethod
    def _normalize_mode_intervals(
        intervals: list[str],
        modes: list[str],
        mode_intervals: dict[str, list[str]] | None,
    ) -> dict[str, set[str]]:
        interval_set = {str(interval).strip() for interval in intervals if str(interval).strip()}
        normalized: dict[str, set[str]] = {}
        for mode in modes:
            mode_key = str(mode).upper()
            requested = [
                str(interval).strip()
                for interval in (mode_intervals or {}).get(mode_key, [])
                if str(interval).strip()
            ]
            allowed = {interval for interval in requested if interval in interval_set}
            normalized[mode_key] = allowed or set(interval_set)
        return normalized

    def _count_daily_trades(self, *, profile_id: str = PAPER_PROFILE_ID) -> int:
        today = datetime.now(timezone.utc).date()
        with session_scope() as session:
            orders = self.order_repo.list_orders(session, limit=1000, profile_id=profile_id)
        total = 0
        for order in orders:
            opened_at = order.get("opened_at_utc") or order.get("open_timestamp")
            if not opened_at:
                continue
            try:
                opened_dt = datetime.fromisoformat(str(opened_at).replace("Z", "+00:00"))
            except ValueError:
                continue
            if opened_dt.astimezone(timezone.utc).date() == today:
                total += 1
        return total

    def _has_duplicate_open_order(self, signal: dict[str, Any], *, profile_id: str = PAPER_PROFILE_ID) -> bool:
        with session_scope() as session:
            open_orders = self.order_repo.list_orders(session, status="OPEN", limit=500, profile_id=profile_id)
        for order in open_orders:
            if (
                str(order.get("symbol") or "").upper() == str(signal.get("symbol") or "").upper()
                and str(order.get("interval") or "").lower() == str(signal.get("interval") or "").lower()
                and str(order.get("mode") or "").upper() == str(signal.get("mode") or "").upper()
                and str(order.get("direction") or "").upper() == str(signal.get("direction") or "").upper()
            ):
                return True
        return False

    @staticmethod
    def _classify_auto_order_skip(reason_text: str) -> tuple[str, str]:
        lowered = str(reason_text or "").lower()
        balance_markers = (
            "available balance",
            "insufficient balance",
            "insufficient margin",
            "margin is insufficient",
            "not enough balance",
            "insufficient wallet",
        )
        if any(marker in lowered for marker in balance_markers):
            return "insufficient_balance", "INSUFFICIENT_BALANCE"
        return "auto_order_rejected", "AUTO_ORDER_REJECTED"

    def _record_auto_order_skip(
        self,
        *,
        run_id: str,
        signal: dict[str, Any],
        skipped: dict[str, int],
        skip_stage_counts: dict[str, int],
        reason_text: str,
        profile_id: str,
    ) -> None:
        bucket, reason_code = self._classify_auto_order_skip(reason_text)
        skipped[bucket] = skipped.get(bucket, 0) + 1
        skip_stage_counts["EXECUTION"] = skip_stage_counts.get("EXECUTION", 0) + 1
        self.trace_service.log_event(
            "SCAN_SKIPPED",
            run_id=run_id,
            signal=signal,
            source="SCAN",
            status="SKIPPED",
            decision="SKIP",
            reason_code=reason_code,
            reason_text=str(reason_text or "Auto order was rejected during execution."),
            profile_id=profile_id,
        )

    def _compute_auto_order_sizing(
        self,
        entry_price: float,
        *,
        signal: dict[str, Any],
        profile_id: str,
    ) -> dict[str, Any] | None:
        try:
            return self.execution_orchestrator.compute_confidence_position_size(
                entry_price,
                confidence=float(signal.get("confidence") or 0.0),
                fee=0.0,
                risk_adjustment_factor=self._risk_adjustment_factor(signal),
                profile_id=profile_id,
            )
        except UnsupportedExecutionProfileError as exc:
            if "Paper confidence sizing is not used for live Phase 5A routing." not in str(exc):
                raise
            return None

    def _open_auto_order(
        self,
        *,
        signal: dict[str, Any],
        entry_price: float,
        sizing: dict[str, Any] | None,
        profile_id: str,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "entry_price": entry_price,
            "fee": 0.0,
            "source": "AUTO",
            "profile_id": profile_id,
        }
        if sizing is not None:
            kwargs["quantity"] = float(sizing.get("quantity") or 0.0)
        return self.execution_orchestrator.open_order(signal, **kwargs)

    @staticmethod
    def _classify_skip(
        signal: dict[str, Any],
        *,
        min_confidence: float,
        allowed_trade_directions: str,
    ) -> tuple[str | None, str | None]:
        direction = str(signal.get("direction") or "").upper()
        if direction not in {"BUY", "SELL"}:
            return "neutral", str(signal.get("no_trade_reason") or "").strip() or None
        policy_reason, policy_text = ScanRuntime._direction_policy_skip_reason(
            direction,
            allowed_trade_directions=allowed_trade_directions,
        )
        if policy_reason is not None:
            signal["no_trade_reason"] = policy_text
            return policy_reason, policy_text
        if float(signal.get("confidence") or 0.0) < min_confidence:
            return "low_confidence", None
        if not all([signal.get("entry_price"), signal.get("stop_loss"), signal.get("take_profit")]):
            return "missing_levels", None
        return None, None

    @staticmethod
    def _direction_policy_skip_reason(direction: str, *, allowed_trade_directions: str) -> tuple[str | None, str | None]:
        policy = str(allowed_trade_directions or "BOTH").upper()
        side = str(direction or "").upper()
        if side == "BUY" and policy == "SHORT_ONLY":
            return "long_disabled_by_runtime", "Long signal skipped because runtime is configured for short trades only."
        if side == "SELL" and policy == "LONG_ONLY":
            return "short_disabled_by_runtime", "Short signal skipped because runtime is configured for long trades only."
        return None, None

    @staticmethod
    def _annotate_trade_direction_policy(signal: dict[str, Any], *, allowed_trade_directions: str) -> None:
        advanced = signal.get("advanced_analysis")
        if not isinstance(advanced, dict):
            advanced = {}
            signal["advanced_analysis"] = advanced
        decision_path = advanced.get("decision_path")
        if not isinstance(decision_path, dict):
            decision_path = {}
            advanced["decision_path"] = decision_path
        direction = str(signal.get("direction") or "").upper()
        decision_path["allowed_trade_directions"] = str(allowed_trade_directions)
        decision_path["runtime_direction_allowed"] = ScanRuntime._direction_policy_skip_reason(
            direction,
            allowed_trade_directions=allowed_trade_directions,
        )[0] is None

    @staticmethod
    def _ensure_runtime_decision_trace(
        signal: dict[str, Any],
        *,
        min_confidence: float,
        runtime_decision: str,
        runtime_reason: str | None,
        runtime_stage: str | None,
    ) -> None:
        advanced = signal.get("advanced_analysis")
        if not isinstance(advanced, dict):
            advanced = {}
            signal["advanced_analysis"] = advanced
        decision_path = advanced.get("decision_path")
        if not isinstance(decision_path, dict):
            decision_path = {}
            advanced["decision_path"] = decision_path
        runtime_confidence = float(signal.get("confidence") or decision_path.get("confidence_final") or 0.0)
        decision_path["runtime_min_confidence"] = float(min_confidence)
        decision_path["runtime_confidence"] = runtime_confidence
        decision_path["runtime_confidence_pass"] = runtime_confidence >= float(min_confidence)
        decision_path["runtime_decision"] = str(runtime_decision)
        if runtime_reason is not None:
            decision_path["runtime_reason"] = str(runtime_reason)
        if runtime_stage is not None:
            decision_path["runtime_stage"] = str(runtime_stage)

    @staticmethod
    def _resolve_skip_stage(signal: dict[str, Any]) -> str | None:
        advanced = signal.get("advanced_analysis") or {}
        if not isinstance(advanced, dict):
            return None
        decision_path = advanced.get("decision_path") or {}
        if not isinstance(decision_path, dict):
            return None
        stage = decision_path.get("neutral_stage")
        if not stage:
            stage = decision_path.get("stage")
        return str(stage).upper() if stage else None

    @staticmethod
    def _resolve_entry_price(signal: dict[str, Any], snapshot: dict[str, Any]) -> float:
        for key in ("entry_price", "entry", "entry_zone_low", "price"):
            value = signal.get(key)
            if value is None:
                value = snapshot.get(key)
            try:
                if value is not None:
                    return float(value)
            except (TypeError, ValueError):
                continue
        raise ValueError("Signal missing entry price.")

    @staticmethod
    def _prefilter_snapshot(snapshot: dict[str, Any], mode: str) -> tuple[str, str] | None:
        mode_key = str(mode or "").upper()
        try:
            adx = float(snapshot.get("adx") or 0.0)
        except (TypeError, ValueError):
            adx = 0.0
        try:
            rsi = float(snapshot.get("rsi") or 50.0)
        except (TypeError, ValueError):
            rsi = 50.0
        try:
            bb_width = float(snapshot.get("bb_width") or 0.0)
        except (TypeError, ValueError):
            bb_width = 0.0
        try:
            price = float(snapshot.get("price") or 0.0)
        except (TypeError, ValueError):
            price = 0.0
        try:
            ema_9 = float(snapshot.get("ema_9") or 0.0)
            ema_21 = float(snapshot.get("ema_21") or 0.0)
            ema_50 = float(snapshot.get("ema_50") or 0.0)
        except (TypeError, ValueError):
            ema_9 = ema_21 = ema_50 = 0.0

        if mode_key == "SWING":
            if adx < 15.0 and 47.0 <= rsi <= 53.0 and bb_width <= 3.0:
                return "PREFILTER_CHOP", "Low ADX, neutral RSI, and narrow bands make this swing setup structurally dead."
            if price > 0.0 and all(value > 0.0 for value in (ema_9, ema_21, ema_50)):
                ema_spread = max(abs(ema_9 - ema_21), abs(ema_21 - ema_50)) / price
                if ema_spread < 0.0025 and 46.0 <= rsi <= 54.0:
                    return "PREFILTER_MIXED", "EMA stack is too compressed for a productive swing trend."
        return None
