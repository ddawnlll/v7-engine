from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from runtime.runtime.scan_event_bus import get_scan_event_bus


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class InferenceJobOutcome:
    payload: dict[str, Any]
    status: str = "COMPLETED"
    error_text: str | None = None


class InferenceJobError(RuntimeError):
    def __init__(self, message: str, job: dict[str, Any], *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.job = dict(job)
        if cause is not None:
            self.__cause__ = cause


class InferenceJobRejectedError(InferenceJobError):
    pass


class InferenceJobFailedError(InferenceJobError):
    pass


class InferenceJobTimedOutError(InferenceJobError):
    pass


@dataclass
class _QueuedInferenceJob:
    job_id: str
    execute: Callable[[], InferenceJobOutcome]
    done: threading.Event
    payload: dict[str, Any] | None = None
    failure: Exception | None = None


class InferenceBus:
    def __init__(self, *, max_workers: int = 0, max_queue_size: int = 64, event_publisher: Callable[[dict[str, Any]], Any] | None = None) -> None:
        self._lock = threading.Lock()
        self._queue: queue.Queue[_QueuedInferenceJob] = queue.Queue(maxsize=max(1, int(max_queue_size)))
        self._workers: list[threading.Thread] = []
        self._worker_capacity = 0
        self._running_jobs = 0
        self._jobs: dict[str, dict[str, Any]] = {}
        self._stats = {
            "submitted": 0,
            "completed": 0,
            "failed": 0,
            "timed_out": 0,
            "rejected": 0,
            "max_queue_depth": 0,
            "max_running": 0,
        }
        self.event_publisher = event_publisher or get_scan_event_bus().publish
        self.configure(max_workers=max_workers, max_queue_size=max_queue_size)

    def configure(self, *, max_workers: int | None = None, max_queue_size: int | None = None) -> None:
        with self._lock:
            if max_queue_size is not None and self._worker_capacity == 0:
                self._queue = queue.Queue(maxsize=max(1, int(max_queue_size)))
            desired_workers = max(0, int(max_workers if max_workers is not None else self._worker_capacity))
            while self._worker_capacity < desired_workers:
                worker = threading.Thread(
                    target=self._worker_loop,
                    name=f"runtime-inference-bus-{self._worker_capacity + 1}",
                    daemon=True,
                )
                self._workers.append(worker)
                self._worker_capacity += 1
                worker.start()

    def submit(
        self,
        *,
        profile_id: str,
        run_id: str,
        symbol: str,
        interval: str,
        mode: str,
        requested_by: str,
        execute: Callable[[], InferenceJobOutcome],
    ) -> dict[str, Any]:
        queued = _QueuedInferenceJob(
            job_id=f"infjob-{uuid.uuid4().hex[:12]}",
            execute=execute,
            done=threading.Event(),
        )
        with self._lock:
            queue_depth = self._queue.qsize()
            job = {
                "job_id": queued.job_id,
                "profile_id": str(profile_id or "paper-main"),
                "run_id": str(run_id or ""),
                "symbol": str(symbol or "").upper(),
                "interval": str(interval or ""),
                "mode": str(mode or "").upper(),
                "requested_by": str(requested_by or "SCAN"),
                "status": "QUEUED",
                "submitted_at_utc": _utc_now_iso(),
                "started_at_utc": None,
                "_submitted_monotonic": time.perf_counter(),
                "completed_at_utc": None,
                "queue_depth_at_submit": queue_depth,
                "queue_limit": int(self._queue.maxsize),
                "worker_capacity": int(self._worker_capacity),
                "queue_wait_ms": None,
                "error_text": None,
            }
            self._jobs[queued.job_id] = job
            self._stats["submitted"] += 1
            self._stats["max_queue_depth"] = max(int(self._stats.get("max_queue_depth") or 0), queue_depth + 1)
        self._emit_job_event("INFERENCE_JOB_QUEUED", job)
        if self._worker_capacity <= 0:
            failed = self._set_terminal_state(queued.job_id, status="FAILED", error_text="Inference bus has no active workers.")
            with self._lock:
                self._stats["failed"] += 1
            self._emit_job_event("INFERENCE_JOB_FAILED", failed)
            raise InferenceJobFailedError(
                f"Inference bus is unavailable for {failed['profile_id']}:{failed['run_id']}:{failed['symbol']}:{failed['interval']}",
                failed,
            )

        try:
            self._queue.put_nowait(queued)
        except queue.Full as exc:
            rejected = self._set_terminal_state(queued.job_id, status="REJECTED", error_text="Inference queue saturated.")
            with self._lock:
                self._stats["rejected"] += 1
            self._emit_job_event("INFERENCE_JOB_REJECTED", rejected)
            raise InferenceJobRejectedError(
                f"Inference queue rejected job for {rejected['profile_id']}:{rejected['run_id']}:{rejected['symbol']}:{rejected['interval']}",
                rejected,
                cause=exc,
            ) from exc

        queued.done.wait()
        if queued.failure is not None:
            raise queued.failure
        return {
            "job": self.get_job(queued.job_id),
            "payload": dict(queued.payload or {}),
        }

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._jobs.get(job_id) or {})

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "worker_capacity": int(self._worker_capacity),
                "queue_limit": int(self._queue.maxsize),
                "queue_depth": int(self._queue.qsize()),
                "running_jobs": int(self._running_jobs),
                **dict(self._stats),
            }

    def _worker_loop(self) -> None:
        while True:
            queued = self._queue.get()
            job = self._set_running_state(queued.job_id)
            self._emit_job_event("INFERENCE_JOB_RUNNING", job)
            try:
                outcome = queued.execute()
                queued.payload = dict(outcome.payload or {})
                terminal = self._set_terminal_state(
                    queued.job_id,
                    status=str(outcome.status or "COMPLETED").upper(),
                    error_text=outcome.error_text,
                )
                with self._lock:
                    if terminal["status"] == "TIMED_OUT":
                        self._stats["timed_out"] += 1
                    else:
                        self._stats["completed"] += 1
                self._emit_job_event("INFERENCE_JOB_TIMED_OUT" if terminal["status"] == "TIMED_OUT" else "INFERENCE_JOB_COMPLETED", terminal)
                if terminal["status"] == "TIMED_OUT":
                    queued.failure = InferenceJobTimedOutError(
                        f"Inference job timed out for {terminal['profile_id']}:{terminal['run_id']}:{terminal['symbol']}:{terminal['interval']}",
                        terminal,
                    )
            except Exception as exc:
                failed = self._set_terminal_state(queued.job_id, status="FAILED", error_text=str(exc))
                with self._lock:
                    self._stats["failed"] += 1
                self._emit_job_event("INFERENCE_JOB_FAILED", failed)
                queued.failure = InferenceJobFailedError(
                    f"Inference job failed for {failed['profile_id']}:{failed['run_id']}:{failed['symbol']}:{failed['interval']}: {exc}",
                    failed,
                    cause=exc,
                )
            finally:
                queued.done.set()
                self._queue.task_done()

    def _emit_job_event(self, event_type: str, job: dict[str, Any]) -> None:
        try:
            payload = {
                "type": event_type,
                "timestamp": _utc_now_iso(),
                "profile_id": job.get("profile_id"),
                "run_id": job.get("run_id"),
                "symbol": job.get("symbol"),
                "interval": job.get("interval"),
                "mode": job.get("mode"),
                "job_id": job.get("job_id"),
                "message": job.get("error_text"),
                "queue_depth": self._queue.qsize(),
                "queue_limit": int(self._queue.maxsize),
                "worker_capacity": int(self._worker_capacity),
                "running_jobs": int(self._running_jobs),
                "queue_wait_ms": job.get("queue_wait_ms"),
                "status": job.get("status"),
            }
            self.event_publisher(payload)
        except Exception:
            return

    def _set_running_state(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            self._running_jobs += 1
            self._stats["max_running"] = max(int(self._stats.get("max_running") or 0), self._running_jobs)
            job = dict(self._jobs.get(job_id) or {})
            job["status"] = "RUNNING"
            job["started_at_utc"] = _utc_now_iso()
            started_monotonic = time.perf_counter()
            submitted_monotonic = job.get("_submitted_monotonic")
            if submitted_monotonic is not None:
                job["queue_wait_ms"] = round((started_monotonic - float(submitted_monotonic)) * 1000.0, 4)
            job["_started_monotonic"] = started_monotonic
            self._jobs[job_id] = job
            return job

    def _set_terminal_state(self, job_id: str, *, status: str, error_text: str | None) -> dict[str, Any]:
        with self._lock:
            job = dict(self._jobs.get(job_id) or {})
            started_monotonic = job.get("_started_monotonic")
            submitted_monotonic = job.get("_submitted_monotonic")
            finished_monotonic = time.perf_counter()
            if job.get("started_at_utc") is None:
                job["started_at_utc"] = _utc_now_iso()
                started_monotonic = finished_monotonic
            if submitted_monotonic is not None and job.get("queue_wait_ms") is None:
                job["queue_wait_ms"] = round((float(started_monotonic or finished_monotonic) - float(submitted_monotonic)) * 1000.0, 4)
            job["status"] = str(status or "COMPLETED").upper()
            job["completed_at_utc"] = _utc_now_iso()
            job["error_text"] = error_text
            job["total_elapsed_ms"] = round((finished_monotonic - float(submitted_monotonic or finished_monotonic)) * 1000.0, 4)
            job.pop("_started_monotonic", None)
            job.pop("_submitted_monotonic", None)
            if self._running_jobs > 0 and started_monotonic is not None:
                self._running_jobs -= 1
            self._jobs[job_id] = job
            return job


_SHARED_BUS: InferenceBus | None = None
_SHARED_BUS_LOCK = threading.Lock()


def get_shared_inference_bus(*, max_workers: int = 0, max_queue_size: int = 64) -> InferenceBus:
    global _SHARED_BUS
    with _SHARED_BUS_LOCK:
        if _SHARED_BUS is None:
            _SHARED_BUS = InferenceBus(max_workers=max_workers, max_queue_size=max_queue_size)
        else:
            _SHARED_BUS.configure(max_workers=max_workers, max_queue_size=max_queue_size)
        return _SHARED_BUS
