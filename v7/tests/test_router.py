"""Tests for v7.router — mode dispatch routing."""

import pytest

from v7.router import (
    HOLD,
    LOCKED_INITIAL_BASELINE,
    MODE_PROFILES,
    RouteResult,
    get_available_modes,
    get_mode_profile,
    route_request,
)


class TestRouteRequest:
    """Test mode routing."""

    def test_swing_allowed(self):
        """SWING mode should be routed as allowed (LOCKED_INITIAL_BASELINE)."""
        request = {
            "request_id": "req_001",
            "mode": "SWING",
            "symbol": "BTCUSDT",
            "timestamp": "2026-06-01T12:00:00Z",
            "requested_trade_mode": "SWING",
            "model_scope": "swing_v1",
            "caller": "v7_runtime",
        }
        result = route_request(request)
        assert result.allowed is True
        assert result.mode == "SWING"
        assert result.block_reason == ""
        assert result.profile["status"] == LOCKED_INITIAL_BASELINE
        assert result.profile["primary_interval"] == "4h"

    def test_scalp_blocked(self):
        """SCALP mode should be blocked (HOLD)."""
        request = {
            "request_id": "req_002",
            "mode": "SCALP",
            "symbol": "ETHUSDT",
            "timestamp": "2026-06-01T12:00:00Z",
            "requested_trade_mode": "SCALP",
            "model_scope": "scalp_v1",
            "caller": "v7_runtime",
        }
        result = route_request(request)
        assert result.allowed is False
        assert result.mode == "SCALP"
        assert result.block_reason != ""
        assert "empirical evidence" in result.block_reason.lower()
        assert result.profile["status"] == HOLD

    def test_aggressive_scalp_blocked(self):
        """AGGRESSIVE_SCALP mode should be blocked (HOLD)."""
        request = {
            "request_id": "req_003",
            "mode": "AGGRESSIVE_SCALP",
            "symbol": "BTCUSDT",
            "timestamp": "2026-06-01T12:00:00Z",
            "requested_trade_mode": "AGGRESSIVE_SCALP",
            "model_scope": "aggressive_scalp_v1",
            "caller": "v7_runtime",
        }
        result = route_request(request)
        assert result.allowed is False
        assert result.mode == "AGGRESSIVE_SCALP"
        assert result.block_reason != ""
        assert result.profile["status"] == HOLD

    def test_unknown_mode_raises(self):
        """Unknown mode should raise ValueError."""
        request = {
            "request_id": "req_004",
            "mode": "POSITION_TRADING",
            "symbol": "BTCUSDT",
            "timestamp": "2026-06-01T12:00:00Z",
            "requested_trade_mode": "POSITION_TRADING",
            "model_scope": "pos_v1",
            "caller": "v7_runtime",
        }
        with pytest.raises(ValueError, match="Unknown mode"):
            route_request(request)

    def test_missing_mode_raises(self):
        """Missing mode field should raise ValueError."""
        request = {
            "request_id": "req_005",
            "symbol": "BTCUSDT",
            "timestamp": "2026-06-01T12:00:00Z",
            "model_scope": "swing_v1",
            "caller": "v7_runtime",
        }
        with pytest.raises(ValueError, match="missing"):
            route_request(request)

    def test_uses_requested_trade_mode_fallback(self):
        """Should use requested_trade_mode if mode is missing."""
        request = {
            "request_id": "req_006",
            "symbol": "BTCUSDT",
            "timestamp": "2026-06-01T12:00:00Z",
            "requested_trade_mode": "SWING",
            "model_scope": "swing_v1",
            "caller": "v7_runtime",
        }
        result = route_request(request)
        assert result.allowed is True
        assert result.mode == "SWING"


class TestGetModeProfile:
    """Test profile retrieval."""

    def test_swing_profile(self):
        """SWING profile should have all expected fields."""
        profile = get_mode_profile("SWING")
        assert profile["status"] == LOCKED_INITIAL_BASELINE
        assert profile["primary_interval"] == "4h"
        assert "min_confidence" in profile
        assert "min_expected_r" in profile
        assert "stop_multiplier" in profile
        assert "target_multiplier" in profile

    def test_scalp_profile(self):
        """SCALP profile should exist with HOLD status."""
        profile = get_mode_profile("SCALP")
        assert profile["status"] == HOLD
        assert "hold_reason" in profile

    def test_aggressive_scalp_profile(self):
        """AGGRESSIVE_SCALP profile should exist with HOLD status."""
        profile = get_mode_profile("AGGRESSIVE_SCALP")
        assert profile["status"] == HOLD

    def test_unknown_mode_raises(self):
        """Unknown mode should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown mode"):
            get_mode_profile("INVALID")

    def test_lowercase_mode_accepted(self):
        """Mode should be case-insensitive."""
        profile = get_mode_profile("swing")
        assert profile["status"] == LOCKED_INITIAL_BASELINE


class TestGetAvailableModes:
    """Test available modes listing."""

    def test_three_modes(self):
        """Should return exactly three modes."""
        modes = get_available_modes()
        assert len(modes) == 3
        assert "SWING" in modes
        assert "SCALP" in modes
        assert "AGGRESSIVE_SCALP" in modes

    def test_swing_is_locked(self):
        """SWING should be LOCKED_INITIAL_BASELINE."""
        modes = get_available_modes()
        assert modes["SWING"] == LOCKED_INITIAL_BASELINE

    def test_scalp_is_hold(self):
        """SCALP should be HOLD."""
        modes = get_available_modes()
        assert modes["SCALP"] == HOLD

    def test_aggressive_scalp_is_hold(self):
        """AGGRESSIVE_SCALP should be HOLD."""
        modes = get_available_modes()
        assert modes["AGGRESSIVE_SCALP"] == HOLD


class TestRouteResult:
    """Test RouteResult dataclass."""

    def test_allowed_result(self):
        """Allowed RouteResult should have no block_reason."""
        result = RouteResult(
            allowed=True,
            mode="SWING",
            profile={"status": LOCKED_INITIAL_BASELINE},
        )
        assert result.allowed is True
        assert result.block_reason == ""

    def test_blocked_result(self):
        """Blocked RouteResult should have block_reason."""
        result = RouteResult(
            allowed=False,
            mode="SCALP",
            profile={"status": HOLD},
            block_reason="Empirical evidence required",
        )
        assert result.allowed is False
        assert result.block_reason != ""

    def test_immutable(self):
        """RouteResult should be immutable."""
        result = RouteResult(allowed=True, mode="SWING")
        with pytest.raises(Exception):
            result.allowed = False  # type: ignore


class TestModeProfiles:
    """Verify MODE_PROFILES configuration matches architecture docs."""

    def test_swing_thresholds(self):
        """SWING thresholds match v7_mode_centric_architecture.md."""
        sw = MODE_PROFILES["SWING"]
        assert sw["min_confidence"] == 0.55
        assert sw["min_expected_r"] == 0.20
        assert sw["ambiguity_margin_r"] == 0.20
        assert sw["min_action_edge_r"] == 0.35
        assert sw["stop_multiplier"] == 2.0
        assert sw["target_multiplier"] == 2.5
        assert sw["max_holding_bars"] == 30

    def test_scalp_thresholds(self):
        """SCALP thresholds match v7_mode_centric_architecture.md."""
        sc = MODE_PROFILES["SCALP"]
        assert sc["min_confidence"] == 0.60
        assert sc["min_expected_r"] == 0.10
        assert sc["ambiguity_margin_r"] == 0.10
        assert sc["min_action_edge_r"] == 0.15
        assert sc["stop_multiplier"] == 1.5
        assert sc["target_multiplier"] == 1.5
        assert sc["max_holding_bars"] == 12

    def test_aggressive_scalp_thresholds(self):
        """AGGRESSIVE_SCALP thresholds match v7_mode_centric_architecture.md."""
        ag = MODE_PROFILES["AGGRESSIVE_SCALP"]
        assert ag["min_confidence"] == 0.70
        assert ag["min_expected_r"] == 0.05
        assert ag["ambiguity_margin_r"] == 0.05
        assert ag["min_action_edge_r"] == 0.08
        assert ag["stop_multiplier"] == 1.0
        assert ag["target_multiplier"] == 1.0
        assert ag["max_holding_bars"] == 5
