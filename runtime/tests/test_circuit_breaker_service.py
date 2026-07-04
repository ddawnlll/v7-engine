"""Tests for runtime/services/circuit_breaker_service.py.

Pure logic (no DB): _rules_from_settings, _state_payload, _failure_breakdown
Session-dependent: _evaluate_with_session via mocked query/execute
Full flow: evaluate_circuit_state via mocked repos
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from runtime.services.circuit_breaker_service import (
    CircuitBreakerService,
    CircuitRules,
    _parse_iso,
    _utc_now,
)
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID


# ── Test helpers ─────────────────────────────────────────────────────

def _make_service(settings_repo=None, repo=None):
    service = CircuitBreakerService(
        settings_repo=settings_repo or MagicMock(),
        repo=repo or MagicMock(),
    )
    return service


@dataclass
class FakeOrder:
    """Minimal Order stub for _failure_breakdown / _evaluate_with_session."""
    payload_json: str = "{}"
    closed_at_utc: str = ""
    profile_id: str = PAPER_PROFILE_ID
    status: str = "CLOSED"
    symbol: str = "BTCUSDT"
    signal_id: str = ""


@dataclass
class FakeTradeFailure:
    severity_score: int = 0
    profile_id: str = PAPER_PROFILE_ID
    created_at_utc: str = ""


def fake_json(payload: dict) -> str:
    import json
    return json.dumps(payload)


# ── _rules_from_settings ─────────────────────────────────────────────

class TestRulesFromSettings:
    def test_defaults_when_empty(self):
        service = _make_service()
        rules = service._rules_from_settings({}, lookback_window=None)
        assert rules.enabled is True
        assert rules.manual_mode == "AUTO"
        assert rules.lookback_window == 10
        assert rules.max_consecutive_losses == 5
        assert rules.max_failure_rate_pct == 70.0
        assert rules.max_severity_avg == 4.0
        assert rules.cooldown_minutes == 60
        assert rules.degraded_multiplier == 0.7

    def test_custom_values(self):
        service = _make_service()
        rules = service._rules_from_settings({
            "CIRCUIT_BREAKER_ENABLED": "false",
            "CIRCUIT_BREAKER_MANUAL_MODE": "force_open",
            "CIRCUIT_BREAKER_LOOKBACK_TRADES": "20",
            "CIRCUIT_BREAKER_MAX_CONSECUTIVE_LOSSES": "3",
            "CIRCUIT_BREAKER_MAX_FAILURE_RATE_PCT": "50.0",
            "CIRCUIT_BREAKER_MAX_SEVERITY_AVG": "3.0",
            "CIRCUIT_BREAKER_COOLDOWN_MINUTES": "120",
            "CIRCUIT_BREAKER_DEGRADED_MULTIPLIER": "0.5",
        }, lookback_window=None)
        assert rules.enabled is False
        assert rules.manual_mode == "FORCE_OPEN"
        assert rules.lookback_window == 20
        assert rules.max_consecutive_losses == 3
        assert rules.max_failure_rate_pct == 50.0
        assert rules.max_severity_avg == 3.0
        assert rules.cooldown_minutes == 120
        assert rules.degraded_multiplier == 0.5

    def test_explicit_lookback_overrides_settings(self):
        service = _make_service()
        rules = service._rules_from_settings(
            {"CIRCUIT_BREAKER_LOOKBACK_TRADES": "20"},
            lookback_window=5,
        )
        assert rules.lookback_window == 5

    def test_truthy_enabled_values(self):
        service = _make_service()
        for val in ("1", "true", "yes", "on"):
            rules = service._rules_from_settings({"CIRCUIT_BREAKER_ENABLED": val}, lookback_window=None)
            assert rules.enabled is True

    def test_falsy_enabled_values(self):
        service = _make_service()
        for val in ("0", "false", "no", "off", ""):
            rules = service._rules_from_settings({"CIRCUIT_BREAKER_ENABLED": val}, lookback_window=None)
            assert rules.enabled is False


# ── _state_payload ──────────────────────────────────────────────────

class TestStatePayload:
    def test_closed_normal(self):
        service = _make_service()
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = service._state_payload(
            status="CLOSED",
            reason="All good.",
            triggered_at=now,
            failure_rate=0.0,
            consecutive_losses=0,
            active_rules=[],
            rules=CircuitRules(),
            active_event=None,
            profile_id=PAPER_PROFILE_ID,
        )
        assert result["status"] == "CLOSED"
        assert result["auto_resume_at"] is None
        assert result["failure_rate"] == 0.0

    def test_open_sets_auto_resume(self):
        service = _make_service()
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        rules = CircuitRules(cooldown_minutes=60)
        result = service._state_payload(
            status="OPEN",
            reason="Too many losses.",
            triggered_at=now,
            failure_rate=50.0,
            consecutive_losses=5,
            active_rules=["max_consecutive_losses"],
            rules=rules,
            active_event=None,
            profile_id=PAPER_PROFILE_ID,
        )
        assert result["status"] == "OPEN"
        assert result["auto_resume_at"] is not None
        auto_resume = datetime.fromisoformat(result["auto_resume_at"])
        assert auto_resume == now + timedelta(minutes=60)

    def test_force_open_no_auto_resume(self):
        service = _make_service()
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        rules = CircuitRules(manual_mode="FORCE_OPEN")
        result = service._state_payload(
            status="OPEN",
            reason="Forced open.",
            triggered_at=now,
            failure_rate=0.0,
            consecutive_losses=0,
            active_rules=["manual_force_open"],
            rules=rules,
            active_event=None,
            auto_resume_at=None,
            profile_id=PAPER_PROFILE_ID,
        )
        assert result["auto_resume_at"] is None

    def test_uses_active_event_auto_resume(self):
        service = _make_service()
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = service._state_payload(
            status="CLOSED",
            reason="Resolved.",
            triggered_at=now,
            failure_rate=0.0,
            consecutive_losses=0,
            active_rules=[],
            rules=CircuitRules(),
            active_event={"status": "OPEN", "auto_resume_at_utc": "2026-06-01T13:00:00+00:00"},
            profile_id=PAPER_PROFILE_ID,
        )
        # auto_resume_at preserves active event's value when present
        assert result["auto_resume_at"] is not None


# ── _failure_breakdown ──────────────────────────────────────────────

class TestFailureBreakdown:
    def test_no_losses_returns_empty(self):
        service = _make_service()
        rows = [
            FakeOrder(payload_json=fake_json({"realized_r": 0.5})),
            FakeOrder(payload_json=fake_json({"realized_r": 1.0})),
        ]
        assert service._failure_breakdown(rows, key="session_label") == {}

    def test_session_label_breakdown(self):
        service = _make_service()
        rows = [
            FakeOrder(payload_json=fake_json({"realized_r": -0.5, "signal": {"advanced_analysis": {"session_label": "LONDON"}}})),
            FakeOrder(payload_json=fake_json({"realized_r": -1.0, "signal": {"advanced_analysis": {"session_label": "LONDON"}}})),
            FakeOrder(payload_json=fake_json({"realized_r": -0.3, "signal": {"advanced_analysis": {"session_label": "NEW_YORK"}}})),
        ]
        result = service._failure_breakdown(rows, key="session_label")
        assert result == {"LONDON": 66.67, "NEW_YORK": 33.33}

    def test_hour_bucket_breakdown(self):
        service = _make_service()
        rows = [
            FakeOrder(payload_json=fake_json({"realized_r": -1.0}), closed_at_utc="2026-06-01T10:30:00+00:00"),
            FakeOrder(payload_json=fake_json({"realized_r": -0.5}), closed_at_utc="2026-06-01T10:45:00+00:00"),
        ]
        result = service._failure_breakdown(rows, key="hour_bucket")
        assert result == {"10:00": 100.0}


# ── _evaluate_with_session (state machine) ──────────────────────────

class TestEvaluateWithSession:
    def _make_session_mock(self, *, orders=None, failures=None, decision_rows=None):
        """Create a mock DB session that returns controlled data.

        Order query: .filter(A).filter(B).order_by().limit().all()
        TradeFailure query: .filter(A).order_by().limit().all()
        Different mock chains → set both paths.
        """
        session = MagicMock()
        # Chain for Order (two .filter() calls)
        session.query.return_value.filter.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = orders or []
        # Chain for TradeFailure (one .filter() call)
        session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = failures or []
        # Decision events
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = decision_rows or []
        session.execute.return_value = result_mock
        return session

    def test_disabled_returns_closed(self):
        service = _make_service()
        session = self._make_session_mock()
        rules = CircuitRules(enabled=False)
        result = service._evaluate_with_session(session, rules)
        assert result["status"] == "CLOSED"
        assert "disabled" in result["active_rules"]

    def test_force_open(self):
        service = _make_service()
        session = self._make_session_mock()
        rules = CircuitRules(manual_mode="FORCE_OPEN")
        result = service._evaluate_with_session(session, rules)
        assert result["status"] == "OPEN"
        assert "manual_force_open" in result["active_rules"]

    def test_force_closed(self):
        service = _make_service()
        session = self._make_session_mock()
        rules = CircuitRules(manual_mode="FORCE_CLOSED")
        result = service._evaluate_with_session(session, rules)
        assert result["status"] == "CLOSED"
        assert "manual_force_closed" in result["active_rules"]

    def test_consecutive_losses_trips_open(self):
        service = _make_service()
        losing_order = FakeOrder(payload_json=fake_json({"realized_r": -1.0}))
        # 5 consecutive losses, threshold is 5
        orders = [losing_order] * 7
        session = self._make_session_mock(orders=orders)
        rules = CircuitRules(max_consecutive_losses=5)
        result = service._evaluate_with_session(session, rules)
        assert result["status"] == "OPEN"
        assert "max_consecutive_losses" in result["active_rules"]

    def test_within_consecutive_losses_stays_closed(self):
        service = _make_service()
        # 2 consecutive losses, threshold is 5 → stays CLOSED
        # Keep failure rate low (2/5 = 40%, threshold 70%)
        orders = [
            FakeOrder(payload_json=fake_json({"realized_r": -0.5})),
            FakeOrder(payload_json=fake_json({"realized_r": -0.3})),
            FakeOrder(payload_json=fake_json({"realized_r": 1.0})),
            FakeOrder(payload_json=fake_json({"realized_r": 0.8})),
            FakeOrder(payload_json=fake_json({"realized_r": 0.6})),
        ]
        session = self._make_session_mock(orders=orders)
        rules = CircuitRules(max_consecutive_losses=5, max_failure_rate_pct=70.0)
        result = service._evaluate_with_session(session, rules)
        assert result["status"] == "CLOSED"

    def test_failure_rate_trips_open(self):
        service = _make_service()
        # 4 out of 5 losing = 80% > 70% threshold
        orders = [
            FakeOrder(payload_json=fake_json({"realized_r": -1.0})),
            FakeOrder(payload_json=fake_json({"realized_r": -0.5})),
            FakeOrder(payload_json=fake_json({"realized_r": 1.0})),
            FakeOrder(payload_json=fake_json({"realized_r": -2.0})),
            FakeOrder(payload_json=fake_json({"realized_r": -0.3})),
        ]
        session = self._make_session_mock(orders=orders)
        rules = CircuitRules(lookback_window=5, max_failure_rate_pct=70.0)
        result = service._evaluate_with_session(session, rules)
        assert result["status"] == "OPEN"
        assert "max_failure_rate_pct" in result["active_rules"]

    def test_high_severity_trips_open(self):
        service = _make_service()
        failures = [
            FakeTradeFailure(severity_score=5),
            FakeTradeFailure(severity_score=5),
            FakeTradeFailure(severity_score=5),
        ]
        session = self._make_session_mock(failures=failures)
        rules = CircuitRules(max_severity_avg=4.0)
        result = service._evaluate_with_session(session, rules)
        assert result["status"] == "OPEN"
        assert "max_severity_avg" in result["active_rules"]

    def test_approaching_thresholds_triggers_degraded(self):
        service = _make_service()
        # 4 losses out of 6 = 66.67% failure rate
        # max_failure_rate_pct = 70 → near threshold = max(56, 60) = 60
        # 66.67 >= 60 → near_failure = True → DEGRADED
        orders = [
            FakeOrder(payload_json=fake_json({"realized_r": -1.0})),
            FakeOrder(payload_json=fake_json({"realized_r": -0.5})),
            FakeOrder(payload_json=fake_json({"realized_r": 1.0})),
            FakeOrder(payload_json=fake_json({"realized_r": -2.0})),
            FakeOrder(payload_json=fake_json({"realized_r": 0.5})),
            FakeOrder(payload_json=fake_json({"realized_r": -0.3})),
        ]
        session = self._make_session_mock(orders=orders)
        rules = CircuitRules(lookback_window=6, max_failure_rate_pct=70.0, max_consecutive_losses=10, max_severity_avg=10.0)
        result = service._evaluate_with_session(session, rules)
        assert result["status"] == "DEGRADED"
        assert "near_failure_rate" in result["active_rules"]
        assert "near_failure_rate" in result["active_rules"]

    def test_cooldown_keeps_open(self):
        service = _make_service()
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        session = self._make_session_mock()
        # Mock repo.get_current_state to return an active_event that is still in cooldown
        service.repo.get_current_state.return_value = {
            "status": "OPEN",
            "auto_resume_at_utc": future,
            "id": 1,
        }
        rules = CircuitRules()
        result = service._evaluate_with_session(session, rules)
        assert result["status"] == "OPEN"
        assert "cooldown" in result["active_rules"]

    def test_timeout_streak_trips_open(self):
        service = _make_service()
        session = self._make_session_mock(decision_rows=[
            {"degraded_reason": "TIMEOUT", "symbol": "BTCUSDT", "fallback_used": True, "deterministic_block": False},
            {"degraded_reason": "TIMEOUT", "symbol": "BTCUSDT", "fallback_used": True, "deterministic_block": False},
            {"degraded_reason": "TIMEOUT", "symbol": "BTCUSDT", "fallback_used": True, "deterministic_block": False},
        ])
        rules = CircuitRules()
        result = service._evaluate_with_session(session, rules)
        assert result["status"] == "OPEN"
        assert "v6_timeout_trip" in result["active_rules"]

    def test_hard_block_trips_open(self):
        service = _make_service()
        session = self._make_session_mock(decision_rows=[
            {"deterministic_block": True, "symbol": "BTCUSDT", "degraded_reason": "", "fallback_used": False},
            {"deterministic_block": True, "symbol": "BTCUSDT", "degraded_reason": "", "fallback_used": False},
            {"deterministic_block": True, "symbol": "BTCUSDT", "degraded_reason": "", "fallback_used": False},
            {"deterministic_block": True, "symbol": "BTCUSDT", "degraded_reason": "", "fallback_used": False},
            {"deterministic_block": True, "symbol": "BTCUSDT", "degraded_reason": "", "fallback_used": False},
        ])
        rules = CircuitRules()
        result = service._evaluate_with_session(session, rules)
        assert result["status"] == "OPEN"
        assert "v6_hard_block_trip" in result["active_rules"]

    def test_healthy_state(self):
        """No issues at all → CLOSED."""
        service = _make_service()
        orders = [
            FakeOrder(payload_json=fake_json({"realized_r": 0.5})),
            FakeOrder(payload_json=fake_json({"realized_r": 1.0})),
            FakeOrder(payload_json=fake_json({"realized_r": 0.3})),
        ]
        session = self._make_session_mock(orders=orders)
        rules = CircuitRules()
        result = service._evaluate_with_session(session, rules)
        assert result["status"] == "CLOSED"
        assert result["failure_rate"] == 0.0


# ── _persist_transition ─────────────────────────────────────────────

class TestPersistTransition:
    def test_same_status_skips(self):
        service = _make_service()
        session = MagicMock()
        service.repo.get_current_state.return_value = {"status": "CLOSED", "id": 1}
        state = {"status": "CLOSED", "triggered_at": datetime.now(timezone.utc).isoformat()}
        service._persist_transition(session, state)
        service.repo.resolve_event.assert_not_called()
        service.repo.save_event.assert_not_called()

    def test_open_transition_saves(self):
        service = _make_service()
        session = MagicMock()
        service.repo.get_current_state.return_value = {"status": "CLOSED", "id": 1}
        state = {"status": "OPEN", "triggered_at": datetime.now(timezone.utc).isoformat()}
        service._persist_transition(session, state)
        service.repo.resolve_event.assert_not_called()
        service.repo.save_event.assert_called_once()


# ── reset / update_settings / list_events ───────────────────────────

class TestApiMethods:
    def test_reset_clears_cache(self):
        service = _make_service()
        session = MagicMock()
        service.repo.get_current_state.return_value = None
        service.repo.normalize_payload.side_effect = lambda x: x
        service.repo.save_event.return_value = {"status": "CLOSED"}
        with patch("runtime.services.circuit_breaker_service.session_scope") as mock_scope:
            mock_scope.return_value.__enter__.return_value = session
            result = service.reset()
            assert result["status"] == "CLOSED"

    def test_update_settings_only_allowed_keys(self):
        service = _make_service()
        service.settings_repo.save_many.return_value = {
            "CIRCUIT_BREAKER_ENABLED": "false",
        }
        with patch("runtime.services.circuit_breaker_service.session_scope") as mock_scope:
            mock_scope.return_value.__enter__.return_value = MagicMock()
            result = service.update_settings({
                "CIRCUIT_BREAKER_ENABLED": "false",
                "INVALID_KEY": "should_be_ignored",
            })
            assert "CIRCUIT_BREAKER_ENABLED" in result
            assert "INVALID_KEY" not in result


# ── _parse_iso ──────────────────────────────────────────────────────

class TestParseIso:
    def test_none(self):
        assert _parse_iso(None) is None

    def test_empty(self):
        assert _parse_iso("") is None

    def test_valid_iso(self):
        result = _parse_iso("2026-06-01T12:00:00+00:00")
        assert result is not None
        assert result.hour == 12

    def test_z_suffix(self):
        result = _parse_iso("2026-06-01T12:00:00Z")
        assert result is not None
        assert result.hour == 12

    def test_invalid(self):
        assert _parse_iso("not-a-date") is None
