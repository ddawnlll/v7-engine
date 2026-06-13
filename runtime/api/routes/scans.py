"""Scan routes for v4."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from runtime.db.repos._helpers import dumps_json
from runtime.db.repos.state_repo import StateRepository
from runtime.db.repos.settings_repo import SettingsRepository, resolve_mode_intervals
from runtime.db.repos.scan_repo import ScanRepository
from runtime.db.repos.signal_repo import SignalRepository
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.db.session import session_scope
from runtime.runtime.autonomous_runtime import get_autonomous_loop
from runtime.runtime.scan_control import ScanControlService
from runtime.runtime.scan_runtime import ScanRuntime

router = APIRouter(tags=["scans"])
scan_runtime: ScanRuntime | None = None
scan_repo = ScanRepository()
signal_repo = SignalRepository()
scan_control = ScanControlService()
settings_repo = SettingsRepository()
state_repo = StateRepository()
ACTIVE_SCAN_STATUSES = {"RUNNING", "PAUSED", "STOPPING"}
STALE_SCAN_TIMEOUT_SECONDS = 300


def _mark_runs_force_stopped(rows: list[dict], *, requested_by: str) -> list[str]:
    affected: list[str] = []
    timestamp = datetime.now(timezone.utc).isoformat()
    with session_scope() as session:
        for row in rows:
            run_id = str(row.get("run_id") or "").strip()
            if not run_id:
                continue
            result = dict(row.get("result") or {})
            result["force_stopped"] = True
            result["force_stopped_at_utc"] = timestamp
            result["stop_cause"] = "force_stop_requested"
            result["stop_requested_by"] = requested_by
            progress = dict(result.get("progress") or {})
            progress["current_task"] = None
            result["progress"] = progress
            scan_repo.save_run(session, {
                "run_id": run_id,
                "profile_id": row.get("profile_id") or PAPER_PROFILE_ID,
                "requested_by": row.get("requested_by"),
                "status": "STOPPED",
                "symbols_csv": ",".join(row.get("symbols") or []),
                "intervals_csv": ",".join(row.get("intervals") or []),
                "modes_csv": ",".join(row.get("modes") or []),
                "signal_count": row.get("signal_count") or 0,
                "summary": row.get("summary") or "Force-stopped by operator.",
                "error_text": row.get("error_text") or "Force-stopped by operator.",
                "created_at_utc": row.get("created_at_utc"),
                "started_at_utc": row.get("started_at_utc"),
                "finished_at_utc": timestamp,
                "payload_json": dumps_json(row.get("payload") or {}),
                "result_json": dumps_json(result),
            })
            affected.append(run_id)
    return affected


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _synthesize_active_run(state: dict, *, profile_id: str = PAPER_PROFILE_ID) -> dict | None:
    run_id = str(state.get("active_run_id") or "").strip()
    if not run_id:
        return None
    status = str(state.get("active_status") or "").upper()
    if status not in ACTIVE_SCAN_STATUSES:
        return None
    current_task = dict(state.get("current_task") or {})
    symbol = str(current_task.get("symbol") or "").strip()
    interval = str(current_task.get("interval") or "").strip()
    mode = str(current_task.get("mode") or current_task.get("phase") or "").strip()
    progress_updated_at = str(state.get("progress_updated_at_utc") or state.get("updated_at_utc") or datetime.now(timezone.utc).isoformat())
    completed_tasks = int(state.get("last_progress_completed_tasks") or 0)
    with session_scope() as session:
        last_trigger = state_repo.get(session, "last_scan_trigger", default=None, profile_id=profile_id)
    requested_by = str(state.get("active_requested_by") or (last_trigger or {}).get("reason") or "system")
    progress = {
        "total_tasks": max(0, completed_tasks),
        "completed_tasks": completed_tasks,
        "remaining_tasks": 0,
        "percent_complete": 100.0 if completed_tasks > 0 else 0.0,
        "current_task": current_task or None,
    }
    payload = {
        "symbols": [symbol] if symbol else [],
        "intervals": [interval] if interval else [],
        "modes": [mode] if mode else [],
        "synthetic": True,
        "synthetic_reason": "scan_control_only",
    }
    result = {
        "progress": progress,
        "signals": [],
        "errors": [],
        "synthetic": True,
        "synthetic_reason": "scan_control_only",
    }
    return {
        "id": None,
        "run_id": run_id,
        "profile_id": profile_id,
        "requested_by": requested_by,
        "status": status,
        "symbols": payload["symbols"],
        "intervals": payload["intervals"],
        "modes": payload["modes"],
        "signal_count": 0,
        "summary": f"Synthetic {status.lower()} run from scan control state",
        "error_text": None,
        "created_at_utc": progress_updated_at,
        "started_at_utc": progress_updated_at,
        "finished_at_utc": None,
        "payload": payload,
        "result": result,
    }


def _reconcile_scan_state(limit: int = 250, *, profile_id: str = PAPER_PROFILE_ID) -> tuple[list[dict], dict]:
    resolved_profile_id = str(profile_id or PAPER_PROFILE_ID)
    with session_scope() as session:
        items = scan_repo.list_runs(session, limit=max(limit, 250), profile_id=resolved_profile_id)
        state = scan_control.get_state(profile_id=resolved_profile_id)
        active_run_id = str(state.get("active_run_id") or "").strip()
        active_run = next((row for row in items if str(row.get("run_id")) == active_run_id), None) if active_run_id else None
        if active_run is None and not items:
            synthetic_active_run = _synthesize_active_run(state, profile_id=resolved_profile_id)
            if synthetic_active_run is not None:
                items = [synthetic_active_run, *items]
                active_run = synthetic_active_run
        if active_run is None:
            active_run = next((row for row in items if str(row.get("status") or "").upper() in ACTIVE_SCAN_STATUSES), None)
            if active_run is not None:
                state = scan_control.update(
                    profile_id=resolved_profile_id,
                    active_run_id=active_run.get("run_id"),
                    active_requested_by=active_run.get("requested_by"),
                    active_status=str(active_run.get("status") or "RUNNING").upper(),
                    current_task=((active_run.get("result") or {}).get("progress") or {}).get("current_task"),
                    progress_updated_at_utc=state.get("progress_updated_at_utc") or active_run.get("started_at_utc") or active_run.get("created_at_utc"),
                )

        active_status = str(state.get("active_status") or "").upper()
        progress_at = _parse_time(state.get("progress_updated_at_utc")) or _parse_time(state.get("updated_at_utc"))
        is_stale = (
            active_run is not None
            and active_status in {"RUNNING", "STOPPING"}
            and progress_at is not None
            and (datetime.now(timezone.utc) - progress_at).total_seconds() >= STALE_SCAN_TIMEOUT_SECONDS
        )
        if is_stale:
            try:
                get_scan_runtime().force_stop_active_run(requested_by="stale_reconcile", profile_id=resolved_profile_id)
            except Exception:
                pass
            progress = dict(((active_run.get("result") or {}).get("progress") or {}))
            debug = dict(((active_run.get("result") or {}).get("debug") or {}))
            completed_tasks = int(progress.get("completed_tasks") or 0)
            total_tasks = int(progress.get("total_tasks") or 0)
            result = dict(active_run.get("result") or {})
            result["stale_cancelled"] = True
            result["stale_cancelled_at_utc"] = datetime.now(timezone.utc).isoformat()
            progress["current_task"] = state.get("current_task") or progress.get("current_task")
            result["progress"] = progress
            result["debug"] = {
                **debug,
                "stale_cancelled_by_reconcile": True,
                "stale_control_state": state,
                "stale_progress_snapshot": progress,
            }
            current_task = progress.get("current_task") or {}
            task_summary = " · ".join(
                part
                for part in [
                    str(current_task.get("symbol") or "").strip(),
                    str(current_task.get("interval") or "").strip(),
                    str(current_task.get("mode") or current_task.get("phase") or "").strip(),
                ]
                if part
            )
            summary = f"Cancelled after no progress for 5m at {completed_tasks}/{total_tasks} scans"
            if task_summary:
                summary = f"{summary} · stuck on {task_summary}"
            scan_repo.save_run(session, {
                "run_id": active_run["run_id"],
                "profile_id": active_run.get("profile_id") or PAPER_PROFILE_ID,
                "requested_by": active_run["requested_by"],
                "status": "STOPPED",
                "symbols_csv": ",".join(active_run.get("symbols") or []),
                "intervals_csv": ",".join(active_run.get("intervals") or []),
                "modes_csv": ",".join(active_run.get("modes") or []),
                "signal_count": active_run.get("signal_count") or 0,
                "summary": summary,
                "error_text": active_run.get("error_text") or "Cancelled after no progress for 5 minutes.",
                "created_at_utc": active_run.get("created_at_utc"),
                "started_at_utc": active_run.get("started_at_utc"),
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "payload_json": dumps_json(active_run.get("payload") or {}),
                "result_json": dumps_json(result),
            })
            state = scan_control.finish_run(str(active_run["run_id"]), "STOPPED", profile_id=resolved_profile_id)
            state = scan_control.update(profile_id=resolved_profile_id, last_action="stale_cancel")
            items = scan_repo.list_runs(session, limit=max(limit, 250), profile_id=resolved_profile_id)
    return items[:limit], state


def get_scan_runtime() -> ScanRuntime:
    global scan_runtime
    if scan_runtime is None:
        scan_runtime = ScanRuntime()
    return scan_runtime


def _load_runtime_settings(profile_id: str = PAPER_PROFILE_ID) -> dict[str, str]:
    with session_scope() as session:
        return settings_repo.get_all(session, profile_id=profile_id)


class ScanRequest(BaseModel):
    symbols: List[str] = Field(default_factory=list)
    intervals: List[str] = Field(default_factory=list)
    modes: List[str] = Field(default_factory=list)
    scan_workers: int | None = None
    requested_by: str = "api"
    profile_id: str = PAPER_PROFILE_ID


class ScanControlResponse(BaseModel):
    ok: bool = True
    state: dict


class ScanTriggerResponse(BaseModel):
    ok: bool = True
    state: dict
    trigger: dict


class ScanStopAllResponse(BaseModel):
    ok: bool = True
    state: dict
    affected_run_ids: list[str] = Field(default_factory=list)
    aborted: bool = False


@router.get("/api/v3/scans")
@router.get("/api/admin/jobs")
def list_scans(limit: int = Query(default=250, ge=1, le=1000), profile_id: str = Query(default=PAPER_PROFILE_ID)):
    items, control_state = _reconcile_scan_state(limit, profile_id=profile_id)
    running_count = sum(1 for row in items if row["status"] == "RUNNING")
    completed_count = sum(1 for row in items if row["status"] == "COMPLETED")
    paused_count = sum(1 for row in items if row["status"] == "PAUSED")
    stopped_count = sum(1 for row in items if row["status"] == "STOPPED")
    failed_count = sum(1 for row in items if row["status"] in {"FAILED", "DEAD_LETTER", "DEGRADED"})
    return {
        "items": [
            {
                "id": row["run_id"],
                "job_type": "SCAN_RUN",
                "status": row["status"],
                "requested_by": row["requested_by"],
                "profile_id": row.get("profile_id") or PAPER_PROFILE_ID,
                "worker_id": "python-v4",
                "run_id": row["run_id"],
                "payload": row["payload"],
                "result": row["result"],
                "error_text": row["error_text"],
                "created_at": row["created_at_utc"],
                "started_at": row["started_at_utc"],
                "finished_at": row["finished_at_utc"],
            }
            for row in items
        ],
        "summary": {
            "pending": 0,
            "running": running_count,
            "completed": completed_count,
            "paused": paused_count,
            "stopped": stopped_count,
            "failed": failed_count,
        },
        "pending": 0,
        "running": running_count,
        "completed": completed_count,
        "paused": paused_count,
        "stopped": stopped_count,
        "failed": failed_count,
        "control": control_state,
    }


@router.post("/api/v3/scans")
@router.post("/api/admin/jobs/scan")
def create_scan(payload: ScanRequest):
    settings = _load_runtime_settings(profile_id=payload.profile_id)
    mode_intervals = resolve_mode_intervals(settings, payload.modes, payload.intervals)
    result = get_scan_runtime().run_scan(
        payload.symbols,
        payload.intervals,
        payload.modes,
        requested_by=payload.requested_by,
        scan_workers=payload.scan_workers,
        mode_intervals=mode_intervals,
        profile_id=payload.profile_id,
    )
    return {
        "ok": True,
        "run_id": result["run"]["run_id"],
        "job": {"id": result["run"]["run_id"]},
        "run": result["run"],
    }


@router.get("/api/v3/scans/control", response_model=ScanControlResponse)
@router.get("/api/admin/jobs/control", response_model=ScanControlResponse)
def get_scan_control_state(profile_id: str = Query(default=PAPER_PROFILE_ID)):
    _, control_state = _reconcile_scan_state(profile_id=profile_id)
    return ScanControlResponse(state=control_state)


@router.post("/api/v3/scans/control/pause", response_model=ScanControlResponse)
@router.post("/api/admin/jobs/pause", response_model=ScanControlResponse)
def pause_scans(requested_by: str = Query(default="interface"), profile_id: str = Query(default=PAPER_PROFILE_ID)):
    return ScanControlResponse(state=scan_control.pause(requested_by=requested_by, profile_id=profile_id))


@router.post("/api/v3/scans/control/resume", response_model=ScanControlResponse)
@router.post("/api/admin/jobs/resume", response_model=ScanControlResponse)
def resume_scans(requested_by: str = Query(default="interface"), profile_id: str = Query(default=PAPER_PROFILE_ID)):
    return ScanControlResponse(state=scan_control.resume(requested_by=requested_by, profile_id=profile_id))


@router.post("/api/v3/scans/control/stop", response_model=ScanControlResponse)
@router.post("/api/admin/jobs/stop", response_model=ScanControlResponse)
def stop_scans(requested_by: str = Query(default="interface"), profile_id: str = Query(default=PAPER_PROFILE_ID)):
    items, state = _reconcile_scan_state(profile_id=profile_id)
    if not state.get("active_run_id"):
        active_run = next((row for row in items if str(row.get("status") or "").upper() in ACTIVE_SCAN_STATUSES), None)
        if active_run is not None:
            scan_control.update(
                profile_id=profile_id,
                active_run_id=active_run.get("run_id"),
                active_requested_by=active_run.get("requested_by"),
                active_status=str(active_run.get("status") or "RUNNING").upper(),
                current_task=((active_run.get("result") or {}).get("progress") or {}).get("current_task"),
            )
    return ScanControlResponse(state=scan_control.request_stop(requested_by=requested_by, profile_id=profile_id))


@router.post("/api/v3/scans/control/stop-all", response_model=ScanStopAllResponse)
@router.post("/api/admin/jobs/stop-all", response_model=ScanStopAllResponse)
def stop_all_scans(requested_by: str = Query(default="interface"), profile_id: str = Query(default=PAPER_PROFILE_ID)):
    items, state = _reconcile_scan_state(profile_id=profile_id)
    active_rows = [
        row for row in items
        if str(row.get("status") or "").upper() in ACTIVE_SCAN_STATUSES
    ]
    if not state.get("active_run_id") and active_rows:
        active_run = active_rows[0]
        scan_control.update(
            profile_id=profile_id,
            active_run_id=active_run.get("run_id"),
            active_requested_by=active_run.get("requested_by"),
            active_status=str(active_run.get("status") or "RUNNING").upper(),
            current_task=((active_run.get("result") or {}).get("progress") or {}).get("current_task"),
        )
    scan_control.pause(requested_by=requested_by, profile_id=profile_id)
    state = scan_control.request_stop(requested_by=requested_by, profile_id=profile_id)
    return ScanStopAllResponse(
        state=state,
        affected_run_ids=[str(row.get("run_id") or "") for row in active_rows if str(row.get("run_id") or "").strip()],
    )


@router.post("/api/v3/scans/control/force-stop-all", response_model=ScanStopAllResponse)
@router.post("/api/admin/jobs/force-stop-all", response_model=ScanStopAllResponse)
def force_stop_all_scans(requested_by: str = Query(default="interface"), profile_id: str = Query(default=PAPER_PROFILE_ID)):
    items, state = _reconcile_scan_state(profile_id=profile_id)
    active_rows = [
        row for row in items
        if str(row.get("status") or "").upper() in ACTIVE_SCAN_STATUSES
    ]
    if not state.get("active_run_id") and active_rows:
        active_run = active_rows[0]
        scan_control.update(
            profile_id=profile_id,
            active_run_id=active_run.get("run_id"),
            active_requested_by=active_run.get("requested_by"),
            active_status=str(active_run.get("status") or "RUNNING").upper(),
            current_task=((active_run.get("result") or {}).get("progress") or {}).get("current_task"),
        )
    outcome = get_scan_runtime().force_stop_active_run(requested_by=requested_by, profile_id=profile_id)
    affected_run_ids = [
        *([str(outcome.get("affected_run_id"))] if str(outcome.get("affected_run_id") or "").strip() else []),
        *[
            str(row.get("run_id") or "")
            for row in active_rows
            if str(row.get("run_id") or "").strip() and str(row.get("run_id") or "") != str(outcome.get("affected_run_id") or "")
        ],
    ]
    if not outcome.get("aborted") and active_rows:
        force_stopped = _mark_runs_force_stopped(active_rows, requested_by=requested_by)
        if force_stopped:
            state = scan_control.finish_run(force_stopped[0], "STOPPED", profile_id=profile_id)
        else:
            state = dict(outcome.get("state") or {})
        affected_run_ids = list(dict.fromkeys(force_stopped))
        aborted = True
    else:
        state = dict(outcome.get("state") or {})
        aborted = bool(outcome.get("aborted"))
    return ScanStopAllResponse(
        state=state,
        affected_run_ids=affected_run_ids,
        aborted=aborted,
    )


@router.post("/api/v3/scans/control/trigger", response_model=ScanTriggerResponse)
@router.post("/api/admin/jobs/trigger", response_model=ScanTriggerResponse)
def trigger_scan_now(profile_id: str = Query(default=PAPER_PROFILE_ID)):
    _, state = _reconcile_scan_state(profile_id=profile_id)
    resumed = False
    if str(state.get("desired_state") or "").upper() == "PAUSED":
        scan_control.resume(requested_by="interface", profile_id=profile_id)
        resumed = True
    loop = get_autonomous_loop(profile_id)
    if hasattr(loop, "resume"):
        loop.resume()
    trigger = loop.trigger_scan_now()
    trigger = {**trigger, "resumed_from_pause": resumed}
    _, refreshed_state = _reconcile_scan_state(profile_id=profile_id)
    return ScanTriggerResponse(state=refreshed_state or state, trigger=trigger)


@router.get("/api/v3/scans/{run_id}")
def get_scan(run_id: str, profile_id: str = Query(default=PAPER_PROFILE_ID)):
    with session_scope() as session:
        run = scan_repo.get_run(session, run_id, profile_id=profile_id)
        signals = signal_repo.list_signals(session, run_id=run_id, limit=1000)
    if run is None:
        return {"ok": False, "run": None, "signals": []}
    return {"ok": True, "run": run, "signals": signals}


@router.post("/api/v3/jobs/retry")
@router.post("/api/admin/jobs/retry-failed")
def retry_scan_jobs(limit: int = Query(default=25, ge=1, le=100), profile_id: str = Query(default=PAPER_PROFILE_ID)):
    with session_scope() as session:
        candidates = scan_repo.list_runs(session, limit=500, profile_id=profile_id)
    settings = _load_runtime_settings(profile_id=profile_id)

    retried_runs: list[str] = []
    for row in candidates:
        status = str(row.get("status") or "").upper()
        if status not in {"FAILED", "DEGRADED"}:
            continue
        payload = dict(row.get("payload") or {})
        symbols = list(payload.get("symbols") or row.get("symbols") or [])
        intervals = list(payload.get("intervals") or row.get("intervals") or [])
        modes = list(payload.get("modes") or row.get("modes") or [])
        mode_intervals = resolve_mode_intervals(settings, modes, intervals)
        result = get_scan_runtime().run_scan(
            symbols,
            intervals,
            modes,
            requested_by="retry",
            scan_workers=payload.get("scan_workers"),
            mode_intervals=mode_intervals,
            profile_id=profile_id,
        )
        retried_runs.append(str(result["run"]["run_id"]))
        if len(retried_runs) >= limit:
            break

    return {"ok": True, "retried": len(retried_runs), "job_ids": retried_runs}
