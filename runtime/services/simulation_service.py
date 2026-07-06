"""Simulation CRUD service for v4."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from inspect import signature
from queue import Queue
from threading import Lock
from typing import Any

from runtime.db.repos.failure_repo import FailureRepository
from runtime.db.repos.simulation_decision_trace_repo import SimulationDecisionTraceRepository
from runtime.db.repos.simulation_repo import SimulationRepository
from runtime.db.session import session_scope
from runtime.services.historical_simulation_engine import HistoricalSimulationEngine
from runtime.services.replay_backed_simulation_orchestrator import ReplayBackedSimulationOrchestrator
from runtime.services.simulation_diagnostics_service import SimulationDiagnosticsService


class SimulationTraceHub:
    def __init__(self, *, max_recent: int = 250) -> None:
        self.max_recent = max_recent
        self._lock = Lock()
        self._subscribers: dict[int, list[Queue]] = {}
        self._recent: dict[int, list[dict[str, Any]]] = {}

    def publish(self, run_id: int, event: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **event,
        }
        with self._lock:
            recent = self._recent.setdefault(run_id, [])
            recent.append(payload)
            if len(recent) > self.max_recent:
                del recent[: len(recent) - self.max_recent]
            subscribers = list(self._subscribers.get(run_id, []))
        for queue in subscribers:
            queue.put(payload)
        return payload

    def subscribe(self, run_id: int) -> Queue:
        queue: Queue = Queue()
        with self._lock:
            self._subscribers.setdefault(run_id, []).append(queue)
            recent = list(self._recent.get(run_id, []))
        for event in recent:
            queue.put(event)
        return queue

    def unsubscribe(self, run_id: int, queue: Queue) -> None:
        with self._lock:
            subscribers = self._subscribers.get(run_id, [])
            if queue in subscribers:
                subscribers.remove(queue)
            if not subscribers and run_id in self._subscribers:
                self._subscribers.pop(run_id, None)


class SimulationService:
    def __init__(self, simulation_repo: SimulationRepository | None = None, engine: HistoricalSimulationEngine | None = None, trace_repo: SimulationDecisionTraceRepository | None = None) -> None:
        self.simulation_repo = simulation_repo or SimulationRepository()
        self.trace_repo = trace_repo or SimulationDecisionTraceRepository()
        self.diagnostics_service = SimulationDiagnosticsService(self.simulation_repo, self.trace_repo)
        self.failure_repo = FailureRepository()
        self.engine = engine or ReplayBackedSimulationOrchestrator()
        self._stop_requested: set[int] = set()
        self._stop_lock = Lock()
        self.trace_hub = SimulationTraceHub()

    def list_runs(self, *, limit: int = 50) -> dict[str, Any]:
        with session_scope() as session:
            return {
                "ok": True,
                "summary": self.simulation_repo.summary(session),
                "runs": self.simulation_repo.list_runs(session, limit=limit),
            }

    def create_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        parameters = dict(payload.get("parameters") or {})
        direct_parameters = self._historical_parameters(payload)
        if direct_parameters:
            parameters = direct_parameters
        parameters = self._attach_reproducibility_metadata(parameters)
        with session_scope() as session:
            run = self.simulation_repo.create_run(
                session,
                name=str(payload.get("name") or self._default_name(parameters) or "Simulation Run").strip(),
                parameters=parameters,
                requested_by=str(payload.get("requested_by") or parameters.get("requested_by") or "admin"),
                status=str(payload.get("status") or "PENDING").upper(),
            )
            return {"ok": True, "run": run}

    def create_and_start_run(self, payload: dict[str, Any], *, background_tasks: Any | None = None) -> dict[str, Any]:
        parameters = self._historical_parameters(payload)
        if not parameters:
            return self.create_run(payload)
        created = self.create_run({**payload, "parameters": parameters, "status": "PENDING"})
        run_id = int(created["run"]["id"])
        self.trace_hub.publish(run_id, {"type": "created", "status": "PENDING", "run": created.get("run")})
        if background_tasks is not None:
            background_tasks.add_task(self.run_historical_simulation, run_id)
        else:
            self.run_historical_simulation(run_id)
        return created

    def run_historical_simulation(self, run_id: int) -> dict[str, Any] | None:
        with session_scope() as session:
            existing = self.simulation_repo.get_run(session, run_id)
            if not existing:
                return None
            if dict(existing.get("metrics") or {}).get("force_stopped"):
                metrics = dict(existing.get("metrics") or {})
                ignored = existing
                if str(existing.get("status") or "").upper() != "STOPPED":
                    ignored = self.simulation_repo.update_run(session, run_id, status="STOPPED", metrics=metrics, finished=True)
                self.trace_hub.publish(run_id, {"type": "ignored_after_force_stop", "status": "STOPPED", "run": ignored})
                return {"ok": True, "run": ignored, "inserted": 0, "ignored_after_force_stop": True}
        with self._stop_lock:
            self._stop_requested.discard(run_id)
        with session_scope() as session:
            run = self.simulation_repo.update_run(session, run_id, status="RUNNING", started=True)
        if not run:
            return None
        self.trace_hub.publish(run_id, {"type": "started", "status": "RUNNING", "run": run})
        parameters = dict(run.get("parameters") or {})
        try:
            output = self._run_engine(
                run_id,
                parameters,
                stop_checker=lambda: self._is_stop_requested(run_id),
                progress_callback=lambda metrics: self._update_progress(run_id, metrics),
            )
            status = str(output.get("status") or "COMPLETED").upper()
            with session_scope() as session:
                current = self.simulation_repo.get_run(session, run_id)
                if (current or {}).get("metrics", {}).get("force_stopped"):
                    ignored = current
                    if str((current or {}).get("status") or "").upper() != "STOPPED":
                        ignored = self.simulation_repo.update_run(session, run_id, status="STOPPED", metrics=dict((current or {}).get("metrics") or {}), finished=True)
                    self.trace_hub.publish(run_id, {"type": "ignored_after_force_stop", "status": "STOPPED", "run": ignored})
                    return {"ok": True, "run": ignored, "inserted": 0, "ignored_after_force_stop": True}
                self.simulation_repo.delete_results_for_run(session, run_id)
                inserted = self.simulation_repo.bulk_insert_results(session, run_id, output.get("results") or [])
                updated = self.simulation_repo.update_run(session, run_id, status=status, metrics=dict(output.get("metrics") or {}), finished=True)
            self.trace_hub.publish(run_id, {"type": status.lower(), "status": status, "run": updated, "inserted": inserted})
            return {"ok": True, "run": updated, "inserted": inserted}
        except Exception as exc:
            metrics = {
                "progress_pct": 100,
                "alerts": [{"tone": "bad", "title": "Simulation failed", "message": str(exc)}],
                "stages": [{"key": "failed", "label": "Simulation failed", "status": "FAILED", "detail": str(exc)}],
            }
            with session_scope() as session:
                updated = self.simulation_repo.update_run(session, run_id, status="FAILED", metrics=metrics, finished=True)
            self.trace_hub.publish(run_id, {"type": "failed", "status": "FAILED", "run": updated, "error": str(exc)})
            return {"ok": False, "run": updated, "error": str(exc)}

    def stop_run(self, run_id: int) -> dict[str, Any] | None:
        with session_scope() as session:
            run = self.simulation_repo.get_run(session, run_id)
            if not run:
                return None
            metrics = dict(run.get("metrics") or {})
            metrics["stop_requested"] = True
            status = "STOPPED" if str(run.get("status") or "").upper() != "RUNNING" else "RUNNING"
            updated = self.simulation_repo.update_run(session, run_id, status=status, metrics=metrics, finished=status == "STOPPED")
        with self._stop_lock:
            self._stop_requested.add(run_id)
        self.trace_hub.publish(run_id, {"type": "stop_requested", "status": updated.get("status"), "run": updated})
        return {"ok": True, "run": updated}

    def force_stop_run(self, run_id: int) -> dict[str, Any] | None:
        with session_scope() as session:
            run = self.simulation_repo.get_run(session, run_id)
            if not run:
                return None
            metrics = dict(run.get("metrics") or {})
            metrics.update({
                "stop_requested": True,
                "force_stopped": True,
                "progress_pct": metrics.get("progress_pct", 100),
                "alerts": [
                    *(metrics.get("alerts") or []),
                    {"tone": "bad", "title": "Simulation force-stopped", "message": "Operator forced this simulation to STOPPED. Any still-running background worker will be ignored by status reconciliation."},
                ],
            })
            updated = self.simulation_repo.update_run(session, run_id, status="STOPPED", metrics=metrics, finished=True)
        with self._stop_lock:
            self._stop_requested.add(run_id)
        self.trace_hub.publish(run_id, {"type": "force_stopped", "status": "STOPPED", "run": updated})
        return {"ok": True, "run": updated, "force_stopped": True}

    def get_run_detail(self, run_id: int) -> dict[str, Any] | None:
        with session_scope() as session:
            run = self.simulation_repo.get_run(session, run_id)
            if not run:
                return None
            return {"ok": True, "run": run, "results": self.simulation_repo.results_for_run(session, run_id)}

    def update_run(self, run_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with session_scope() as session:
            run = self.simulation_repo.update_run(
                session,
                run_id,
                status=(str(payload["status"]).upper() if payload.get("status") else None),
                metrics=payload.get("metrics"),
                started=bool(payload.get("started")),
                finished=bool(payload.get("finished")),
            )
            if not run:
                return None
            return {"ok": True, "run": run}

    def insert_results(self, run_id: int, results: list[dict[str, Any]]) -> dict[str, Any] | None:
        with session_scope() as session:
            run = self.simulation_repo.get_run(session, run_id)
            if not run:
                return None
            inserted = self.simulation_repo.bulk_insert_results(session, run_id, results)
            return {"ok": True, "inserted": inserted}

    def get_decision_traces(self, run_id: int, **filters: Any) -> dict[str, Any] | None:
        with session_scope() as session:
            run = self.simulation_repo.get_run(session, run_id)
            if not run:
                return None
            page = self.trace_repo.list_for_run(session, run_id, **filters)
            return {"ok": True, "run_id": run_id, **page}

    def get_decision_trace_summary(self, run_id: int) -> dict[str, Any] | None:
        with session_scope() as session:
            run = self.simulation_repo.get_run(session, run_id)
            if not run:
                return None
            summary = self.trace_repo.summary(session, run_id)
            return {"ok": True, "run_id": run_id, **summary}

    def get_diagnostics(self, run_id: int) -> dict[str, Any] | None:
        return self.diagnostics_service.get_diagnostics(run_id)

    def get_confidence_histogram(self, run_id: int) -> dict[str, Any] | None:
        return self.diagnostics_service.get_confidence_histogram(run_id)

    def get_what_if(self, run_id: int, **params: Any) -> dict[str, Any] | None:
        return self.diagnostics_service.get_what_if(run_id, **params)

    def get_parity_report(self, run_id: int) -> dict[str, Any] | None:
        return self.diagnostics_service.get_parity_report(run_id)

    def export_run(self, run_id: int, **params: Any) -> dict[str, Any] | None:
        return self.diagnostics_service.export(run_id, **params)

    def analyze_failures(self, run_id: int, *, persist: bool = True, profile_id: str | None = None) -> dict[str, Any] | None:
        with session_scope() as session:
            run = self.simulation_repo.get_run(session, run_id)
            if not run:
                return None
            results = self.simulation_repo.results_for_run(session, run_id)
            target_profile = profile_id or f"simulation-{run_id}"
            rows: list[dict[str, Any]] = []
            for result in results:
                details = dict(result.get("details") or {})
                pnl = self._as_float(details.get("pnl", result.get("realized_r")))
                if pnl is None or pnl >= 0:
                    continue
                mode = str(details.get("mode") or result.get("mode") or "UNKNOWN").upper()
                direction = str(details.get("direction") or result.get("direction") or "UNKNOWN").upper()
                symbol = str(details.get("symbol") or result.get("symbol") or "UNKNOWN").upper()
                interval = str(details.get("interval") or result.get("interval") or "UNKNOWN")
                realized_r = self._as_float(result.get("realized_r"))
                if realized_r is None:
                    capital = self._as_float((parameters or {}).get("capital")) or 0.0
                    realized_r = (pnl / capital) if capital > 0 else pnl
                stop_reason = str(details.get("stop_reason") or result.get("outcome") or "LOSS").upper()
                if "STOP" in stop_reason:
                    source, component = "STOP_LOSS", "risk_management"
                elif direction == "SELL":
                    source, component = "SHORT_THESIS_FAILED", "strategy_direction"
                elif mode == "SCALP":
                    source, component = "SCALP_ENTRY_FAILED", "entry_timing"
                else:
                    source, component = "ADVERSE_PRICE_ACTION", "signal_quality"
                severity = int(min(5, max(1, round(abs(pnl) / 100) + 1)))
                confidence_raw = self._as_float(details.get("confidence", result.get("confidence"))) or 0.0
                confidence = confidence_raw / 100 if confidence_raw > 1 else confidence_raw
                row = {
                    "order_id": f"sim-{run_id}-{result.get('id') or symbol}-{mode}-{direction}",
                    "profile_id": target_profile,
                    "signal_id": f"simctx|{symbol}|{interval}|{mode}|{direction}|{realized_r}|{pnl}",
                    "failure_source": source,
                    "blamed_component": component,
                    "severity_score": severity,
                    "confidence": confidence,
                    "classification": f"SIMULATION_{source}",
                    "explanation": f"Simulation #{run_id} losing {mode} {direction} trade on {symbol}; pnl={pnl:.4f}; stop={stop_reason}.",
                    "improvement": "Review trace context, entry timing, stop distance, and mode/direction filters before live promotion.",
                    "created_at_utc": datetime.now(timezone.utc).isoformat(),
                }
                rows.append(row)
                if persist:
                    self.failure_repo.save_failure(session, row)
            summary: dict[str, Any] = {"total": len(rows), "counts_by_failure_source": {}, "counts_by_blamed_component": {}, "average_severity_score": 0, "average_confidence": 0, "top_weakness": None}
            if rows:
                for row in rows:
                    summary["counts_by_failure_source"][row["failure_source"]] = summary["counts_by_failure_source"].get(row["failure_source"], 0) + 1
                    summary["counts_by_blamed_component"][row["blamed_component"]] = summary["counts_by_blamed_component"].get(row["blamed_component"], 0) + 1
                summary["average_severity_score"] = round(sum(float(row["severity_score"]) for row in rows) / len(rows), 4)
                summary["average_confidence"] = round(sum(float(row["confidence"]) for row in rows) / len(rows), 4)
                top_source = max(summary["counts_by_failure_source"].items(), key=lambda item: item[1])
                summary["top_weakness"] = {"failure_source": top_source[0], "count": top_source[1]}
            return {"ok": True, "run_id": run_id, "profile_id": target_profile, "persisted": persist, "summary": summary, "items": rows}

    @staticmethod
    def _as_float(value: Any) -> float | None:
        try:
            parsed = float(value)
            return parsed if parsed == parsed else None
        except Exception:
            return None

    def _run_engine(self, run_id: int, parameters: dict[str, Any], *, stop_checker, progress_callback) -> dict[str, Any]:
        kwargs = {
            "stop_checker": stop_checker,
            "progress_callback": progress_callback,
        }
        try:
            accepts_trace_callback = "trace_callback" in signature(self.engine.run).parameters
        except Exception:
            accepts_trace_callback = False
        if accepts_trace_callback:
            kwargs["trace_callback"] = lambda trace: self._persist_decision_trace(run_id, trace)
        return self.engine.run(parameters, **kwargs)

    def _persist_decision_trace(self, run_id: int, trace: dict[str, Any]) -> None:
        with session_scope() as session:
            run = self.simulation_repo.get_run(session, run_id)
            if not run:
                return
            # Force-stop is authoritative for status, but partial decision traces
            # are intentionally preserved for diagnostics.
            self.trace_repo.bulk_insert(session, run_id, [trace])

    def _is_stop_requested(self, run_id: int) -> bool:
        with self._stop_lock:
            return run_id in self._stop_requested

    def _update_progress(self, run_id: int, metrics: dict[str, Any]) -> None:
        event_metrics = dict(metrics or {})
        event_type = str(event_metrics.pop("event_type", "progress") or "progress")
        with session_scope() as session:
            run = self.simulation_repo.get_run(session, run_id)
            if not run:
                return
            if dict(run.get("metrics") or {}).get("force_stopped"):
                if str(run.get("status") or "").upper() != "STOPPED":
                    self.simulation_repo.update_run(session, run_id, status="STOPPED", metrics=dict(run.get("metrics") or {}), finished=True)
                return
            merged = dict(run.get("metrics") or {})
            merged.update({k: v for k, v in event_metrics.items() if k not in {"trade", "message"}})
            updated = self.simulation_repo.update_run(session, run_id, status="RUNNING", metrics=merged)
        event_payload = {"type": event_type, "status": "RUNNING", "metrics": event_metrics, "run": updated}
        if "trade" in metrics:
            event_payload["trade"] = metrics["trade"]
        if "message" in metrics:
            event_payload["message"] = metrics["message"]
        self.trace_hub.publish(run_id, event_payload)

    def _attach_reproducibility_metadata(self, parameters: dict[str, Any]) -> dict[str, Any]:
        parameters = dict(parameters or {})
        if not parameters:
            return parameters
        canonical = {key: value for key, value in parameters.items() if key not in {"created_at", "created_at_utc", "reproducibility"}}
        execution_settings = dict(parameters.get("execution_settings") or {})
        parameters["reproducibility"] = {
            "request_payload_hash": self._stable_hash(canonical),
            "execution_settings_hash": self._stable_hash(execution_settings),
            "analyzer_engine_version": execution_settings.get("analyzer_engine_version") or parameters.get("analyzer_engine_version") or "runtime-default",
            "model_version": execution_settings.get("model_version") or parameters.get("model_version"),
            "snapshot_builder_version": "v6-unified-snapshot-replay-v1",
            "contract_version": "analysis_request_vnext",
        }
        return parameters

    @staticmethod
    def _stable_hash(value: Any) -> str:
        payload = json.dumps(value or {}, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _historical_parameters(payload: dict[str, Any]) -> dict[str, Any]:
        if not payload.get("period_start") and not payload.get("period_end"):
            return {}
        return {
            "period_start": payload.get("period_start"),
            "period_end": payload.get("period_end"),
            "symbols": list(payload.get("symbols") or []),
            "intervals": list(payload.get("intervals") or []),
            "modes": list(payload.get("modes") or []),
            "capital": payload.get("capital", 50_000),
            "risk_per_trade_pct": payload.get("risk_per_trade_pct", 1.0),
            "max_hold_bars": payload.get("max_hold_bars"),
            "min_confidence": payload.get("min_confidence"),
            "scan_step_bars": payload.get("scan_step_bars", 1),
            "scan_workers": payload.get("scan_workers", 4),
            "time_forward_step_bars": payload.get("time_forward_step_bars", 1),
            "simulation_profile_id": payload.get("simulation_profile_id"),
            "simulation_profile": dict(payload.get("simulation_profile") or {}),
            "execution_settings": dict(payload.get("execution_settings") or {}),
            "requested_by": payload.get("requested_by", "interface"),
        }

    @staticmethod
    def _default_name(parameters: dict[str, Any]) -> str:
        if not parameters:
            return "Simulation Run"
        modes = ", ".join(parameters.get("modes") or []) or "engine"
        start = parameters.get("period_start") or "start"
        end = parameters.get("period_end") or "end"
        return f"{modes} replay {start} → {end}"
