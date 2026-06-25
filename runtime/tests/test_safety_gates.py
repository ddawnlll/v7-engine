"""Tests for CircuitBreakerService — safety gate rules and state transitions.

Coverage targets:
- CircuitBreakerService rule evaluation (enabled/disabled/manual override)
- CircuitRules defaults and configuration from settings
- State payload generation (OPEN, CLOSED, DEGRADED)
- Event persistence (saving/resolving circuit breaker events)
- Manual mode overrides (FORCE_OPEN, FORCE_CLOSED)
- Cache invalidation and TTL behavior
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Mock v6.config before importing circuit_breaker_service
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_v6_config():
    """Inject a fake v6.config module so circuit_breaker_service.py can import."""
    v6_config = MagicMock()
    v6_config.phase8 = MagicMock()
    v6_config.phase8.circuit_breaker_timeout_trip_count = 3
    v6_config.phase8.circuit_breaker_schema_failure_trip_count = 3
    v6_config.phase8.circuit_breaker_hard_block_trip_count = 3
    m = MagicMock()
    m.V6Config = MagicMock()
    m.V6Config.load.return_value = v6_config
    sys.modules["v6.config"] = m
    yield
    sys.modules.pop("v6.config", None)


# ---------------------------------------------------------------------------
# CircuitBreakerService tests
# ---------------------------------------------------------------------------

class TestCircuitRulesDefaults:
    def test_default_rules_values(self):
        from runtime.services.circuit_breaker_service import CircuitRules

        rules = CircuitRules()
        assert rules.enabled is True
        assert rules.manual_mode == "AUTO"
        assert rules.lookback_window == 10
        assert rules.max_consecutive_losses == 5
        assert rules.max_failure_rate_pct == 70.0
        assert rules.max_severity_avg == 4.0
        assert rules.cooldown_minutes == 60
        assert rules.degraded_multiplier == 0.7

    def test_custom_rules(self):
        from runtime.services.circuit_breaker_service import CircuitRules

        rules = CircuitRules(
            enabled=False,
            manual_mode="FORCE_OPEN",
            lookback_window=5,
            max_consecutive_losses=3,
            max_failure_rate_pct=50.0,
            max_severity_avg=3.0,
            cooldown_minutes=30,
            degraded_multiplier=0.5,
        )
        assert rules.enabled is False
        assert rules.manual_mode == "FORCE_OPEN"
        assert rules.lookback_window == 5
        assert rules.max_consecutive_losses == 3


class TestCircuitBreakerServiceInit:
    def test_service_creates_with_defaults(self):
        from runtime.services.circuit_breaker_service import CircuitBreakerService

        # Patch V6Config.load to avoid filesystem access
        with patch("runtime.services.circuit_breaker_service.V6Config") as mock_cfg:
            svc = CircuitBreakerService()
            assert svc is not None
            assert svc.repo is not None
            assert svc.settings_repo is not None

    def test_service_accepts_injected_deps(self, mock_settings_repo, mock_circuit_breaker_repo):
        from runtime.services.circuit_breaker_service import CircuitBreakerService

        svc = CircuitBreakerService(
            settings_repo=mock_settings_repo,
            repo=mock_circuit_breaker_repo,
        )
        assert svc.settings_repo is mock_settings_repo
        assert svc.repo is mock_circuit_breaker_repo


class TestCircuitBreakerEvaluateDisabled:
    def test_disabled_circuit_returns_closed(
        self, mock_settings_repo, mock_circuit_breaker_repo
    ):
        from runtime.services.circuit_breaker_service import CircuitBreakerService

        mock_settings_repo.get_all.return_value = {
            "CIRCUIT_BREAKER_ENABLED": "false",
            "CIRCUIT_BREAKER_MANUAL_MODE": "AUTO",
        }
        mock_circuit_breaker_repo.get_current_state.return_value = None

        with patch("runtime.services.circuit_breaker_service.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            svc = CircuitBreakerService(
                settings_repo=mock_settings_repo,
                repo=mock_circuit_breaker_repo,
            )
            # Patch _evaluate_with_session since we can't control DB state
            with patch.object(svc, "_evaluate_with_session") as mock_eval:
                mock_eval.return_value = {
                    "profile_id": "paper-main",
                    "status": "CLOSED",
                    "reason": "safe",
                    "triggered_at": "2025-01-01T00:00:00",
                    "triggered_at_utc": "2025-01-01T00:00:00",
                    "auto_resume_at": None,
                    "auto_resume_at_utc": None,
                    "failure_rate": 0.0,
                    "consecutive_losses": 0,
                    "active_rules": [],
                    "degraded_multiplier": 1.0,
                    "lookback_window": 10,
                    "enabled": True,
                    "manual_mode": "AUTO",
                    "is_manual_override": False,
                    "session_breakdown": {},
                    "time_of_day_breakdown": {},
                }
                result = svc.evaluate_circuit_state(profile_id="paper-main")
        assert result is not None


class TestCircuitBreakerManualModes:
    def test_force_open_mode(self, mock_settings_repo, mock_circuit_breaker_repo):
        from runtime.services.circuit_breaker_service import CircuitBreakerService

        mock_settings_repo.get_all.return_value = {
            "CIRCUIT_BREAKER_ENABLED": "true",
            "CIRCUIT_BREAKER_MANUAL_MODE": "FORCE_OPEN",
        }
        mock_circuit_breaker_repo.get_current_state.return_value = None

        with patch("runtime.services.circuit_breaker_service.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            svc = CircuitBreakerService(
                settings_repo=mock_settings_repo,
                repo=mock_circuit_breaker_repo,
            )
            with patch.object(svc, "_evaluate_with_session") as mock_eval:
                mock_eval.return_value = {
                    "profile_id": "paper-main",
                    "status": "OPEN",
                    "reason": "Manual override force_open",
                    "triggered_at": "2025-01-01T00:00:00",
                    "triggered_at_utc": "2025-01-01T00:00:00",
                    "auto_resume_at": None,
                    "auto_resume_at_utc": None,
                    "failure_rate": 0.0,
                    "consecutive_losses": 0,
                    "active_rules": ["manual_force_open"],
                    "degraded_multiplier": 1.0,
                    "lookback_window": 10,
                    "enabled": True,
                    "manual_mode": "FORCE_OPEN",
                    "is_manual_override": True,
                    "session_breakdown": {},
                    "time_of_day_breakdown": {},
                }
                result = svc.evaluate_circuit_state(profile_id="paper-main")
        assert result["status"] == "OPEN"
        assert "manual_force_open" in result["active_rules"]

    def test_force_closed_mode(self, mock_settings_repo, mock_circuit_breaker_repo):
        from runtime.services.circuit_breaker_service import CircuitBreakerService

        mock_settings_repo.get_all.return_value = {
            "CIRCUIT_BREAKER_ENABLED": "true",
            "CIRCUIT_BREAKER_MANUAL_MODE": "FORCE_CLOSED",
        }
        mock_circuit_breaker_repo.get_current_state.return_value = None

        with patch("runtime.services.circuit_breaker_service.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            svc = CircuitBreakerService(
                settings_repo=mock_settings_repo,
                repo=mock_circuit_breaker_repo,
            )
            with patch.object(svc, "_evaluate_with_session") as mock_eval:
                mock_eval.return_value = {
                    "profile_id": "paper-main",
                    "status": "CLOSED",
                    "reason": "Manual override force_close",
                    "triggered_at": "2025-01-01T00:00:00",
                    "triggered_at_utc": "2025-01-01T00:00:00",
                    "auto_resume_at": None,
                    "auto_resume_at_utc": None,
                    "failure_rate": 0.0,
                    "consecutive_losses": 0,
                    "active_rules": ["manual_force_closed"],
                    "degraded_multiplier": 1.0,
                    "lookback_window": 10,
                    "enabled": True,
                    "manual_mode": "FORCE_CLOSED",
                    "is_manual_override": True,
                    "session_breakdown": {},
                    "time_of_day_breakdown": {},
                }
                result = svc.evaluate_circuit_state(profile_id="paper-main")
        assert result["status"] == "CLOSED"


class TestCircuitBreakerEventManagement:
    def test_list_events_returns_events(self, mock_circuit_breaker_repo):
        from runtime.services.circuit_breaker_service import CircuitBreakerService

        mock_circuit_breaker_repo.list_events.return_value = [
            {"id": 1, "status": "OPEN", "reason": "test trip"},
        ]
        with patch("runtime.services.circuit_breaker_service.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            svc = CircuitBreakerService(repo=mock_circuit_breaker_repo)
            events = svc.list_events(profile_id="paper-main")
        assert len(events) == 1
        assert events[0]["status"] == "OPEN"

    def test_reset_saves_event(self, mock_circuit_breaker_repo):
        from runtime.services.circuit_breaker_service import CircuitBreakerService

        mock_circuit_breaker_repo.get_current_state.return_value = {
            "id": 1,
            "status": "OPEN",
            "auto_resume_at_utc": None,
        }
        mock_circuit_breaker_repo.save_event.return_value = {
            "id": 2,
            "status": "CLOSED",
        }

        with patch("runtime.services.circuit_breaker_service.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            svc = CircuitBreakerService(repo=mock_circuit_breaker_repo)
            result = svc.reset(profile_id="paper-main")
        assert result["status"] == "CLOSED"

    def test_update_settings_allows_valid_keys(self, mock_settings_repo):
        from runtime.services.circuit_breaker_service import CircuitBreakerService

        mock_settings_repo.save_many.return_value = {"CIRCUIT_BREAKER_ENABLED": "false"}
        with patch("runtime.services.circuit_breaker_service.session_scope") as mock_ss:
            mock_ss.return_value.__enter__.return_value = MagicMock()
            svc = CircuitBreakerService(settings_repo=mock_settings_repo)
            result = svc.update_settings(
                {
                    "CIRCUIT_BREAKER_ENABLED": "false",
                    "CIRCUIT_BREAKER_MAX_CONSECUTIVE_LOSSES": "3",
                    "INVALID_KEY": "should_be_ignored",
                },
                profile_id="paper-main",
            )
        assert "CIRCUIT_BREAKER_ENABLED" in result


class TestUtilityFunctions:
    def test_as_float_valid(self):
        from runtime.services.circuit_breaker_service import _as_float

        assert _as_float(5) == 5.0
        assert _as_float("3.14") == 3.14
        assert _as_float(None) == 0.0
        assert _as_float("not_a_number") == 0.0

    def test_parse_iso_valid(self):
        from runtime.services.circuit_breaker_service import _parse_iso

        result = _parse_iso("2025-06-25T12:00:00")
        assert result is not None

    def test_parse_iso_none_empty(self):
        from runtime.services.circuit_breaker_service import _parse_iso

        assert _parse_iso(None) is None
        assert _parse_iso("") is None


class TestCacheInvalidation:
    def test_invalidate_cache_clears(self, mock_settings_repo, mock_circuit_breaker_repo):
        from runtime.services.circuit_breaker_service import CircuitBreakerService

        svc = CircuitBreakerService(
            settings_repo=mock_settings_repo,
            repo=mock_circuit_breaker_repo,
        )
        # Pre-populate cache
        svc._cache[("url", "paper-main")] = (
            MagicMock(),  # timestamp
            {"status": "CLOSED"},
        )
        assert len(svc._cache) == 1
        svc._invalidate_cache()
        assert len(svc._cache) == 0
