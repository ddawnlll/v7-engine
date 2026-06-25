"""Tests for ScanControlService — lifecycle: start, pause, resume, stop.

Coverage targets:
- Default state structure
- Pause / resume transitions
- Stop / force_stop transitions
- Run lifecycle (activate, mark_running, mark_paused, mark_stopping, finish)
- State persistence edge cases (nonexistent state, partial state)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from runtime.runtime.scan_control import ScanControlService


# ---------------------------------------------------------------------------
# Default state
# ---------------------------------------------------------------------------

class TestDefaultState:
    def test_default_state_structure(self, scan_control_service: ScanControlService):
        state = scan_control_service.default_state(profile_id="paper-main")
        assert state["profile_id"] == "paper-main"
        assert state["desired_state"] == "RUNNING"
        assert state["stop_requested"] is False
        assert state["active_status"] == "IDLE"
        assert state["last_progress_completed_tasks"] == 0
        assert "updated_at_utc" in state

    def test_default_state_different_profile(self, scan_control_service: ScanControlService):
        state = scan_control_service.default_state(profile_id="custom-profile")
        assert state["profile_id"] == "custom-profile"

    def test_default_state_empty_profile_falls_back(self, scan_control_service: ScanControlService):
        state = scan_control_service.default_state(profile_id="")
        assert state["profile_id"] == "paper-main"


# ---------------------------------------------------------------------------
# Get state (DB interaction)
# ---------------------------------------------------------------------------

class TestGetState:
    def test_returns_default_when_nothing_stored(
        self, scan_control_service: ScanControlService, mock_state_repo: MagicMock
    ):
        mock_state_repo.get.return_value = None
        with patch("runtime.runtime.scan_control.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            state = scan_control_service.get_state(profile_id="paper-main")
        assert state["desired_state"] == "RUNNING"
        assert state["profile_id"] == "paper-main"

    def test_merges_stored_over_defaults(
        self, scan_control_service: ScanControlService, mock_state_repo: MagicMock
    ):
        mock_state_repo.get.return_value = {
            "desired_state": "PAUSED",
            "stop_requested": False,
        }
        with patch("runtime.runtime.scan_control.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            state = scan_control_service.get_state(profile_id="paper-main")
        assert state["desired_state"] == "PAUSED"
        assert state["profile_id"] == "paper-main"


# ---------------------------------------------------------------------------
# Lifecycle: pause / resume / stop
# ---------------------------------------------------------------------------

class TestPauseResume:
    def test_pause_sets_desired_state(
        self, scan_control_service: ScanControlService, mock_state_repo: MagicMock
    ):
        # Simulate current RUNNING state
        mock_state_repo.get.return_value = {
            **scan_control_service.default_state(profile_id="paper-main"),
            "desired_state": "RUNNING",
        }
        with patch("runtime.runtime.scan_control.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            result = scan_control_service.pause(requested_by="operator", profile_id="paper-main")
        assert result["desired_state"] == "PAUSED"
        assert result["pause_requested_by"] == "operator"
        assert result["last_action"] == "pause"

    def test_pause_unknown_requestor(self, scan_control_service: ScanControlService):
        with patch("runtime.runtime.scan_control.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            result = scan_control_service.pause(profile_id="paper-main")
        assert result["desired_state"] == "PAUSED"
        assert result["pause_requested_by"] == "unknown"

    def test_resume_clears_stop_flags(
        self, scan_control_service: ScanControlService, mock_state_repo: MagicMock
    ):
        mock_state_repo.get.return_value = {
            **scan_control_service.default_state(profile_id="paper-main"),
            "desired_state": "RUNNING",
            "active_run_id": "run-abc",
        }
        with patch("runtime.runtime.scan_control.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            result = scan_control_service.resume(requested_by="admin", profile_id="paper-main")
        assert result["desired_state"] == "RUNNING"
        assert result["stop_requested"] is False
        assert result["stop_requested_by"] is None
        assert result["force_stop_requested"] is False
        assert result["resume_requested_by"] == "admin"

    def test_resume_without_active_run_sets_idle(
        self, scan_control_service: ScanControlService, mock_state_repo: MagicMock
    ):
        mock_state_repo.get.return_value = {
            **scan_control_service.default_state(profile_id="paper-main"),
            "desired_state": "PAUSED",
            "active_run_id": None,
            "active_status": "IDLE",
        }
        with patch("runtime.runtime.scan_control.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            result = scan_control_service.resume(profile_id="paper-main")
        assert result["active_status"] == "IDLE"
        assert result["current_task"] is None


class TestStop:
    def test_request_stop_no_active_run(
        self, scan_control_service: ScanControlService, mock_state_repo: MagicMock
    ):
        mock_state_repo.get.return_value = {
            **scan_control_service.default_state(profile_id="paper-main"),
            "active_run_id": None,
        }
        with patch("runtime.runtime.scan_control.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            result = scan_control_service.request_stop(requested_by="system", profile_id="paper-main")
        assert result["stop_requested"] is True
        assert result["active_status"] == "IDLE"
        assert result["last_action"] == "stop"

    def test_request_stop_with_active_run_sets_stopping(
        self, scan_control_service: ScanControlService, mock_state_repo: MagicMock
    ):
        mock_state_repo.get.return_value = {
            **scan_control_service.default_state(profile_id="paper-main"),
            "active_run_id": "run-123",
        }
        with patch("runtime.runtime.scan_control.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            result = scan_control_service.request_stop(requested_by="operator", profile_id="paper-main")
        assert result["active_status"] == "STOPPING"

    def test_force_stop_sets_flags(
        self, scan_control_service: ScanControlService, mock_state_repo: MagicMock
    ):
        mock_state_repo.get.return_value = {
            **scan_control_service.default_state(profile_id="paper-main"),
            "active_run_id": "run-456",
        }
        with patch("runtime.runtime.scan_control.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            result = scan_control_service.request_force_stop(requested_by="admin", profile_id="paper-main")
        assert result["stop_requested"] is True
        assert result["force_stop_requested"] is True
        assert result["force_stop_requested_by"] == "admin"
        assert result["active_status"] == "STOPPING"
        assert result["last_action"] == "force_stop"

    def test_force_stop_unknown_requestor(
        self, scan_control_service: ScanControlService, mock_state_repo: MagicMock
    ):
        mock_state_repo.get.return_value = {
            **scan_control_service.default_state(profile_id="paper-main"),
            "active_run_id": None,
        }
        with patch("runtime.runtime.scan_control.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            result = scan_control_service.request_force_stop(profile_id="paper-main")
        assert result["force_stop_requested_by"] == "unknown"


# ---------------------------------------------------------------------------
# Run lifecycle
# ---------------------------------------------------------------------------

class TestRunLifecycle:
    def test_activate_run_when_running(
        self, scan_control_service: ScanControlService, mock_state_repo: MagicMock
    ):
        mock_state_repo.get.return_value = {
            **scan_control_service.default_state(profile_id="paper-main"),
            "desired_state": "RUNNING",
        }
        with patch("runtime.runtime.scan_control.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            result = scan_control_service.activate_run(
                "run-001", "orchestrator", profile_id="paper-main"
            )
        assert result["active_run_id"] == "run-001"
        assert result["active_status"] == "RUNNING"
        assert result["active_requested_by"] == "orchestrator"

    def test_activate_run_when_paused(
        self, scan_control_service: ScanControlService, mock_state_repo: MagicMock
    ):
        mock_state_repo.get.return_value = {
            **scan_control_service.default_state(profile_id="paper-main"),
            "desired_state": "PAUSED",
        }
        with patch("runtime.runtime.scan_control.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            result = scan_control_service.activate_run(
                "run-002", "orchestrator", profile_id="paper-main"
            )
        assert result["active_status"] == "PAUSED"
        assert result["last_run_id"] == "run-002"

    def test_activate_run_clears_force_stop(self, scan_control_service: ScanControlService, mock_state_repo: MagicMock):
        mock_state_repo.get.return_value = {
            **scan_control_service.default_state(profile_id="paper-main"),
            "force_stop_requested": True,
            "force_stop_requested_by": "previous",
        }
        with patch("runtime.runtime.scan_control.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            result = scan_control_service.activate_run("run-003", "orchestrator", profile_id="paper-main")
        assert result["force_stop_requested"] is False
        assert result["force_stop_requested_by"] is None

    def test_mark_running_updates_progress(
        self, scan_control_service: ScanControlService, mock_state_repo: MagicMock
    ):
        mock_state_repo.get.return_value = {
            **scan_control_service.default_state(profile_id="paper-main"),
            "last_progress_completed_tasks": 0,
        }
        with patch("runtime.runtime.scan_control.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            result = scan_control_service.mark_running(
                "run-004",
                current_task={"symbol": "BTCUSDT", "interval": "4h"},
                completed_tasks=5,
                profile_id="paper-main",
            )
        assert result["active_status"] == "RUNNING"
        assert result["current_task"] == {"symbol": "BTCUSDT", "interval": "4h"}
        assert result["last_progress_completed_tasks"] == 5

    def test_mark_paused_updates_state(
        self, scan_control_service: ScanControlService, mock_state_repo: MagicMock
    ):
        mock_state_repo.get.return_value = {
            **scan_control_service.default_state(profile_id="paper-main"),
            "last_progress_completed_tasks": 2,
        }
        with patch("runtime.runtime.scan_control.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            result = scan_control_service.mark_paused(
                "run-005",
                current_task=None,
                profile_id="paper-main",
            )
        assert result["active_status"] == "PAUSED"

    def test_mark_stopping(
        self, scan_control_service: ScanControlService, mock_state_repo: MagicMock
    ):
        mock_state_repo.get.return_value = {
            **scan_control_service.default_state(profile_id="paper-main"),
            "last_progress_completed_tasks": 10,
        }
        with patch("runtime.runtime.scan_control.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            result = scan_control_service.mark_stopping(
                "run-006",
                current_task={"symbol": "ETHUSDT", "interval": "1h"},
                completed_tasks=8,
                profile_id="paper-main",
            )
        assert result["active_status"] == "STOPPING"
        assert result["last_progress_completed_tasks"] == 8

    def test_finish_run_stopped_clears_state(
        self, scan_control_service: ScanControlService, mock_state_repo: MagicMock
    ):
        mock_state_repo.get.return_value = {
            **scan_control_service.default_state(profile_id="paper-main"),
            "active_run_id": "run-007",
            "active_status": "RUNNING",
            "stop_requested": True,
        }
        with patch("runtime.runtime.scan_control.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            result = scan_control_service.finish_run(
                "run-007", "STOPPED", profile_id="paper-main"
            )
        assert result["active_run_id"] is None
        assert result["active_status"] == "IDLE"
        assert result["last_run_id"] == "run-007"
        assert result["last_finished_status"] == "STOPPED"
        assert result["stop_requested"] is False

    def test_finish_run_completed_respects_paused_desired(
        self, scan_control_service: ScanControlService, mock_state_repo: MagicMock
    ):
        mock_state_repo.get.return_value = {
            **scan_control_service.default_state(profile_id="paper-main"),
            "active_run_id": "run-008",
            "active_status": "RUNNING",
            "desired_state": "PAUSED",
        }
        with patch("runtime.runtime.scan_control.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            result = scan_control_service.finish_run(
                "run-008", "COMPLETED", profile_id="paper-main"
            )
        assert result["active_status"] == "PAUSED"
        assert result["desired_state"] == "RUNNING"  # unwinds to RUNNING after stop

    def test_finish_run_succeeded_goes_idle(
        self, scan_control_service: ScanControlService, mock_state_repo: MagicMock
    ):
        mock_state_repo.get.return_value = {
            **scan_control_service.default_state(profile_id="paper-main"),
            "active_run_id": "run-009",
            "active_status": "RUNNING",
            "desired_state": "RUNNING",
        }
        with patch("runtime.runtime.scan_control.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            result = scan_control_service.finish_run(
                "run-009", "SUCCEEDED", profile_id="paper-main"
            )
        assert result["active_status"] == "IDLE"


# ---------------------------------------------------------------------------
# State key constant
# ---------------------------------------------------------------------------

class TestStateKeyConstant:
    def test_state_key_is_constant(self):
        assert ScanControlService.STATE_KEY == "scan_control"
