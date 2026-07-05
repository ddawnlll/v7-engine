"""Tests for v7.router — mode dispatch routing."""

import pytest

from v7.router import (
    HOLD,
    LOCKED_INITIAL_BASELINE,
    MODE_PROFILES,
    RouteResult,
    get_artifact_scope_tag,
    get_available_modes,
    get_mode_profile,
    route_request,
    validate_model_scope,
    validate_scope_compatibility,
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


class TestValidateModelScope:
    """Test model_scope validation."""

    def test_swing_valid(self):
        """swing_v1 should be valid for SWING."""
        assert validate_model_scope("swing_v1", "SWING") is None

    def test_scalp_valid(self):
        """scalp_v1 should be valid for SCALP."""
        assert validate_model_scope("scalp_v1", "SCALP") is None

    def test_aggressive_scalp_valid(self):
        """aggressive_scalp_v1 should be valid for AGGRESSIVE_SCALP."""
        assert validate_model_scope("aggressive_scalp_v1", "AGGRESSIVE_SCALP") is None

    def test_swing_with_scalp_mode_rejected(self):
        """swing_v1 should be rejected for SCALP mode."""
        err = validate_model_scope("swing_v1", "SCALP")
        assert err is not None
        assert "swing_" in err

    def test_scalp_with_swing_mode_rejected(self):
        """scalp_v1 should be rejected for SWING mode."""
        err = validate_model_scope("scalp_v1", "SWING")
        assert err is not None
        assert "scalp_" in err

    def test_aggressive_scalp_with_swing_rejected(self):
        """aggressive_scalp_v1 should be rejected for SWING mode."""
        err = validate_model_scope("aggressive_scalp_v1", "SWING")
        assert err is not None
        assert "aggressive_scalp_" in err

    def test_empty_scope_rejected(self):
        """Empty model_scope should be rejected."""
        err = validate_model_scope("", "SWING")
        assert err is not None

    def test_unknown_mode(self):
        """Unknown mode should return error message."""
        err = validate_model_scope("swing_v1", "DAY_TRADING")
        assert err is not None
        assert "Unknown mode" in err


class TestValidateScopeCompatibility:
    """Test scope compatibility validation."""

    def test_swing_compatible(self):
        """SWING + swing_v1 should be compatible."""
        assert validate_scope_compatibility("SWING", "swing_v1") is None

    def test_scalp_compatible(self):
        """SCALP + scalp_v1 should be compatible."""
        assert validate_scope_compatibility("SCALP", "scalp_v1") is None

    def test_aggressive_scalp_compatible(self):
        """AGGRESSIVE_SCALP + aggressive_scalp_v1 should be compatible."""
        assert validate_scope_compatibility("AGGRESSIVE_SCALP", "aggressive_scalp_v1") is None

    def test_scope_mismatch(self):
        """SCALP mode with swing_v1 should be a mismatch."""
        err = validate_scope_compatibility("SCALP", "swing_v1")
        assert err is not None

    def test_unknown_mode(self):
        """Unknown mode should return error."""
        err = validate_scope_compatibility("INVALID", "swing_v1")
        assert err is not None

    def test_lowercase_mode_accepted(self):
        """Lowercase mode should be case-insensitive."""
        assert validate_scope_compatibility("scalp", "scalp_v1") is None


class TestGetArtifactScopeTag:
    """Test artifact scope tagging."""

    def test_swing_tag(self):
        """SWING should produce 'v7_swing' tag."""
        assert get_artifact_scope_tag("SWING") == "v7_swing"

    def test_scalp_tag(self):
        """SCALP should produce 'v7_scalp' tag."""
        assert get_artifact_scope_tag("SCALP") == "v7_scalp"

    def test_aggressive_scalp_tag(self):
        """AGGRESSIVE_SCALP should produce 'v7_aggressive_scalp' tag."""
        assert get_artifact_scope_tag("AGGRESSIVE_SCALP") == "v7_aggressive_scalp"

    def test_lowercase_accepted(self):
        """Lowercase mode should be accepted."""
        assert get_artifact_scope_tag("swing") == "v7_swing"

    def test_unknown_mode_raises(self):
        """Unknown mode should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown mode"):
            get_artifact_scope_tag("INVALID")


class TestRouteRequestWithScopeValidation:
    """Test route_request with scope validation enabled."""

    def test_swing_scope_valid(self):
        """SWING with valid model_scope should pass scope check."""
        request = {
            "request_id": "req_001",
            "mode": "SWING",
            "symbol": "BTCUSDT",
            "scope": {
                "model_scope": "swing_v1",
            },
        }
        result = route_request(request, validate_scope=True)
        assert result.allowed is True
        assert result.mode == "SWING"

    def test_scalp_scope_mismatch_raises(self):
        """SCALP with swing_v1 scope should raise ValueError."""
        request = {
            "request_id": "req_002",
            "mode": "SCALP",
            "symbol": "ETHUSDT",
            "scope": {
                "model_scope": "swing_v1",
            },
        }
        with pytest.raises(ValueError, match="Scope mismatch"):
            route_request(request, validate_scope=True)

    def test_scope_validation_off_by_default(self):
        """Default route_request should not validate scope."""
        request = {
            "request_id": "req_003",
            "mode": "SCALP",
            "symbol": "ETHUSDT",
            "scope": {
                "model_scope": "swing_v1",
            },
        }
        # Should not raise even with mismatched scope
        result = route_request(request, validate_scope=False)
        assert result.allowed is False  # SCALP is HOLD

    def test_scope_from_top_level_model_scope(self):
        """route_request should read model_scope from top-level field."""
        request = {
            "request_id": "req_004",
            "mode": "SWING",
            "symbol": "BTCUSDT",
            "model_scope": "swing_v1",
        }
        result = route_request(request, validate_scope=True)
        assert result.allowed is True

    def test_aggressive_scalp_scope_mismatch_raises(self):
        """AGGRESSIVE_SCALP with scalp_v1 scope should raise."""
        request = {
            "request_id": "req_005",
            "mode": "AGGRESSIVE_SCALP",
            "symbol": "BTCUSDT",
            "scope": {
                "model_scope": "scalp_v1",
            },
        }
        with pytest.raises(ValueError, match="Scope mismatch"):
            route_request(request, validate_scope=True)

    def test_missing_model_scope_with_validation(self):
        """Missing model_scope with validate_scope=True should not error."""
        request = {
            "request_id": "req_006",
            "mode": "SWING",
            "symbol": "BTCUSDT",
        }
        result = route_request(request, validate_scope=True)
        assert result.allowed is True
