"""Shared scan control state for pause, resume, and stop."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from runtime.db.repos.state_repo import StateRepository
from runtime.db.session import session_scope


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ScanControlService:
    """Persisted control state for the active scan runtime.

    The control surface is intentionally small:
    - desired_state: RUNNING or PAUSED
    - stop_requested: one-shot stop signal for the active run
    - active_* fields: current run metadata for the interface
    """

    STATE_KEY = "scan_control"

    def __init__(self, state_repo: StateRepository | None = None) -> None:
        self.state_repo = state_repo or StateRepository()

    def get_state(self, *, profile_id: str = "paper-main") -> dict[str, Any]:
        with session_scope() as session:
            stored = self.state_repo.get(session, self.STATE_KEY, default=None, profile_id=profile_id)
        if isinstance(stored, dict):
            return {**self.default_state(profile_id=profile_id), **stored, "profile_id": str(profile_id or 'paper-main')}
        return self.default_state(profile_id=profile_id)

    def default_state(self, *, profile_id: str = "paper-main") -> dict[str, Any]:
        return {
            "profile_id": str(profile_id or "paper-main"),
            "desired_state": "RUNNING",
            "stop_requested": False,
            "stop_requested_by": None,
            "force_stop_requested": False,
            "force_stop_requested_by": None,
            "pause_requested_by": None,
            "resume_requested_by": None,
            "active_run_id": None,
            "active_requested_by": None,
            "active_status": "IDLE",
            "current_task": None,
            "progress_updated_at_utc": None,
            "last_progress_completed_tasks": 0,
            "updated_at_utc": utc_now_iso(),
            "last_run_id": None,
            "last_action": None,
            "last_finished_status": None,
        }

    def save_state(self, payload: dict[str, Any], *, profile_id: str = "paper-main") -> dict[str, Any]:
        resolved_profile_id = str(profile_id or "paper-main")
        next_state = {**self.default_state(profile_id=resolved_profile_id), **payload, "profile_id": resolved_profile_id, "updated_at_utc": utc_now_iso()}
        with session_scope() as session:
            self.state_repo.set(session, self.STATE_KEY, next_state, profile_id=resolved_profile_id)
        return next_state

    def update(self, *, profile_id: str = "paper-main", **updates: Any) -> dict[str, Any]:
        state = self.get_state(profile_id=profile_id)
        state.update(updates)
        return self.save_state(state, profile_id=profile_id)

    def pause(self, requested_by: str | None = None, *, profile_id: str = "paper-main") -> dict[str, Any]:
        return self.update(
            profile_id=profile_id,
            desired_state="PAUSED",
            pause_requested_by=requested_by or "unknown",
            last_action="pause",
        )

    def resume(self, requested_by: str | None = None, *, profile_id: str = "paper-main") -> dict[str, Any]:
        state = self.update(
            profile_id=profile_id,
            desired_state="RUNNING",
            stop_requested=False,
            stop_requested_by=None,
            force_stop_requested=False,
            force_stop_requested_by=None,
            resume_requested_by=requested_by or "unknown",
            last_action="resume",
        )
        if not state.get("active_run_id"):
            return self.update(profile_id=profile_id, active_status="IDLE", current_task=None)
        return state

    def request_stop(self, requested_by: str | None = None, *, profile_id: str = "paper-main") -> dict[str, Any]:
        state = self.get_state(profile_id=profile_id)
        next_status = "STOPPING" if state.get("active_run_id") else "IDLE"
        return self.update(
            profile_id=profile_id,
            stop_requested=True,
            stop_requested_by=requested_by or "unknown",
            force_stop_requested=False,
            force_stop_requested_by=None,
            active_status=next_status,
            last_action="stop",
        )

    def request_force_stop(self, requested_by: str | None = None, *, profile_id: str = "paper-main") -> dict[str, Any]:
        state = self.get_state(profile_id=profile_id)
        next_status = "STOPPING" if state.get("active_run_id") else "IDLE"
        return self.update(
            profile_id=profile_id,
            stop_requested=True,
            stop_requested_by=requested_by or "unknown",
            force_stop_requested=True,
            force_stop_requested_by=requested_by or "unknown",
            active_status=next_status,
            last_action="force_stop",
        )

    def activate_run(self, run_id: str, requested_by: str, *, profile_id: str = "paper-main") -> dict[str, Any]:
        return self.update(
            profile_id=profile_id,
            force_stop_requested=False,
            force_stop_requested_by=None,
            active_run_id=run_id,
            active_requested_by=requested_by,
            active_status="PAUSED" if self.get_state(profile_id=profile_id).get("desired_state") == "PAUSED" else "RUNNING",
            current_task=None,
            progress_updated_at_utc=utc_now_iso(),
            last_progress_completed_tasks=0,
            last_run_id=run_id,
            last_finished_status=None,
        )

    def mark_running(self, run_id: str, current_task: dict[str, Any] | None, *, completed_tasks: int | None = None, profile_id: str = "paper-main") -> dict[str, Any]:
        return self.update(
            profile_id=profile_id,
            active_run_id=run_id,
            active_status="RUNNING",
            current_task=current_task,
            progress_updated_at_utc=utc_now_iso(),
            last_progress_completed_tasks=completed_tasks if completed_tasks is not None else self.get_state(profile_id=profile_id).get("last_progress_completed_tasks", 0),
        )

    def mark_paused(self, run_id: str, current_task: dict[str, Any] | None, *, completed_tasks: int | None = None, profile_id: str = "paper-main") -> dict[str, Any]:
        return self.update(
            profile_id=profile_id,
            active_run_id=run_id,
            active_status="PAUSED",
            current_task=current_task,
            progress_updated_at_utc=utc_now_iso(),
            last_progress_completed_tasks=completed_tasks if completed_tasks is not None else self.get_state(profile_id=profile_id).get("last_progress_completed_tasks", 0),
        )

    def mark_stopping(self, run_id: str, current_task: dict[str, Any] | None, *, completed_tasks: int | None = None, profile_id: str = "paper-main") -> dict[str, Any]:
        return self.update(
            profile_id=profile_id,
            active_run_id=run_id,
            active_status="STOPPING",
            current_task=current_task,
            progress_updated_at_utc=utc_now_iso(),
            last_progress_completed_tasks=completed_tasks if completed_tasks is not None else self.get_state(profile_id=profile_id).get("last_progress_completed_tasks", 0),
        )

    def finish_run(self, run_id: str, final_status: str, *, profile_id: str = "paper-main") -> dict[str, Any]:
        state = self.get_state(profile_id=profile_id)
        desired_state = "RUNNING" if final_status == "STOPPED" else state.get("desired_state", "RUNNING")
        next_status = "PAUSED" if desired_state == "PAUSED" else "IDLE"
        return self.save_state(
            {
                **state,
                "desired_state": desired_state,
                "stop_requested": False,
                "stop_requested_by": None,
                "force_stop_requested": False,
                "force_stop_requested_by": None,
                "active_run_id": None,
                "active_requested_by": None,
                "active_status": next_status,
                "current_task": None,
                "last_run_id": run_id,
                "last_finished_status": final_status,
            },
            profile_id=profile_id,
        )
