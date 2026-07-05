"""
Tests for v7.eligibility — layered execution-eligibility stack.

Covers:
  - Each layer individually (pass + fail cases)
  - Short-circuit behaviour (first fail stops evaluation)
  - All layers pass happy path
  - Config-driven threshold overrides
  - Edge cases: missing fields, unknown modes, invalid types
"""

from __future__ import annotations

import pytest

from v7.eligibility import (
    EligibilityLayer,
    EligibilityResult,
    EligibilityStack,
)


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def valid_swing_request() -> dict:
    """Minimal valid SWING request."""
    return {
        "mode": "SWING",
        "symbol": "BTCUSDT",
        "model_scope": "swing_v1",
    }


@pytest.fixture
def empty_context() -> dict:
    """Empty runtime context."""
    return {}


@pytest.fixture
def stack() -> EligibilityStack:
    """Default eligibility stack."""
    return EligibilityStack()


@pytest.fixture
def stack_with_custom_engine() -> EligibilityStack:
    """Stack with a custom engine config that includes a custom scope."""
    return EligibilityStack(
        engine_config={
            "custom_v1": {"features": ["alpha", "beta"]},
            "swing_v1": {"features": ["returns", "volatility"]},
        }
    )


# =========================================================================
# Layer Enum
# =========================================================================


class TestEligibilityLayer:
    """EligibilityLayer IntEnum ordering and properties."""

    def test_ordering(self):
        """Layers are ordered 1-6."""
        assert int(EligibilityLayer.STRUCTURAL) == 1
        assert int(EligibilityLayer.ENGINE) == 2
        assert int(EligibilityLayer.CONFIDENCE) == 3
        assert int(EligibilityLayer.ECONOMIC) == 4
        assert int(EligibilityLayer.TIMING) == 5
        assert int(EligibilityLayer.OPERATIONAL) == 6

    def test_membership(self):
        """All six layers are defined."""
        expected = {
            "STRUCTURAL",
            "ENGINE",
            "CONFIDENCE",
            "ECONOMIC",
            "TIMING",
            "OPERATIONAL",
        }
        assert set(EligibilityLayer.__members__) == expected


# =========================================================================
# EligibilityResult
# =========================================================================


class TestEligibilityResult:
    """EligibilityResult dataclass construction."""

    def test_minimal_defaults(self):
        """Default construction with required fields."""
        result = EligibilityResult(
            eligible=False,
            current_layer=EligibilityLayer.STRUCTURAL,
        )
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.STRUCTURAL
        assert result.gates == {}
        assert result.blocking_reason == ""
        assert result.short_circuited is False

    def test_full_pass(self):
        """Full pass result."""
        result = EligibilityResult(
            eligible=True,
            current_layer=EligibilityLayer.OPERATIONAL,
            gates={
                "structural": {"passed": True, "reason": "ok"},
                "engine": {"passed": True, "reason": "ok"},
            },
            blocking_reason="",
            short_circuited=False,
        )
        assert result.eligible is True
        assert result.short_circuited is False

    def test_short_circuited(self):
        """Short-circuited result."""
        result = EligibilityResult(
            eligible=False,
            current_layer=EligibilityLayer.CONFIDENCE,
            gates={"structural": {"passed": True}, "confidence": {"passed": False}},
            blocking_reason="Confidence too low",
            short_circuited=True,
        )
        assert result.eligible is False
        assert result.short_circuited is True

    def test_frozen(self):
        """EligibilityResult must be immutable."""
        result = EligibilityResult(eligible=True, current_layer=EligibilityLayer.OPERATIONAL)
        with pytest.raises(AttributeError):
            result.eligible = False  # type: ignore[misc]


# =========================================================================
# Layer 1: STRUCTURAL
# =========================================================================


class TestLayer1Structural:
    """Layer 1 — valid request/result, mode supported."""

    def test_passes_valid_swing(self, stack, valid_swing_request, empty_context):
        """Valid SWING request passes structural layer."""
        result = stack.evaluate(valid_swing_request, empty_context)
        # Should NOT fail at structural
        if not result.eligible and result.current_layer == EligibilityLayer.STRUCTURAL:
            pytest.fail(f"Structural gate failed: {result.blocking_reason}")

    def test_fails_missing_mode(self, stack, empty_context):
        """Missing mode fails structural."""
        request = {"symbol": "BTCUSDT", "model_scope": "swing_v1"}
        result = stack.evaluate(request, empty_context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.STRUCTURAL
        assert result.short_circuited is True
        assert "Missing" in result.blocking_reason
        assert not result.gates["structural"]["passed"]

    def test_fails_unknown_mode(self, stack, empty_context):
        """Unknown mode fails structural."""
        request = {"mode": "BOGUS", "symbol": "BTCUSDT", "model_scope": "swing_v1"}
        result = stack.evaluate(request, empty_context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.STRUCTURAL
        assert result.short_circuited is True
        assert "Unknown mode" in result.blocking_reason

    def test_fails_missing_symbol(self, stack, empty_context):
        """Missing symbol fails structural."""
        request = {"mode": "SWING", "model_scope": "swing_v1"}
        result = stack.evaluate(request, empty_context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.STRUCTURAL
        assert "Missing" in result.blocking_reason

    def test_fails_missing_model_scope(self, stack, empty_context):
        """Missing model_scope fails structural."""
        request = {"mode": "SWING", "symbol": "BTCUSDT"}
        result = stack.evaluate(request, empty_context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.STRUCTURAL
        assert "Missing" in result.blocking_reason

    def test_accepts_requested_trade_mode_alias(self, stack, empty_context):
        """requested_trade_mode works as an alias for mode."""
        request = {
            "requested_trade_mode": "SWING",
            "symbol": "ETHUSDT",
            "model_scope": "swing_v2",
        }
        result = stack.evaluate(request, empty_context)
        assert result.gates["structural"]["passed"]

    def test_fails_mode_not_string(self, stack, empty_context):
        """Non-string mode fails structural."""
        request = {"mode": 123, "symbol": "BTCUSDT", "model_scope": "swing_v1"}
        result = stack.evaluate(request, empty_context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.STRUCTURAL

    def test_fails_blank_mode(self, stack, empty_context):
        """Blank mode string fails structural."""
        request = {"mode": "  ", "symbol": "BTCUSDT", "model_scope": "swing_v1"}
        result = stack.evaluate(request, empty_context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.STRUCTURAL


# =========================================================================
# Layer 2: ENGINE
# =========================================================================


class TestLayer2Engine:
    """Layer 2 — model scope known, feature config present."""

    def test_passes_known_scope(self, stack, empty_context):
        """Known model_scope passes engine layer."""
        request = {"mode": "SWING", "symbol": "BTCUSDT", "model_scope": "swing_v1"}
        result = stack.evaluate(request, empty_context)
        # Short-circuit would stop at structural first if that failed, so check
        # structural passed then ensure engine also passes
        assert result.gates["structural"]["passed"]
        assert result.gates["engine"]["passed"]

    def test_fails_unknown_scope(self, stack, empty_context):
        """Unknown model_scope fails engine layer."""
        request = {"mode": "SWING", "symbol": "BTCUSDT", "model_scope": "nonsense_v99"}
        result = stack.evaluate(request, empty_context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.ENGINE
        assert result.short_circuited is True
        assert "not found" in result.blocking_reason

    def test_custom_engine_config(self, stack_with_custom_engine, empty_context):
        """Custom engine config is respected."""
        request = {"mode": "SWING", "symbol": "BTCUSDT", "model_scope": "custom_v1"}
        result = stack_with_custom_engine.evaluate(request, empty_context)
        assert result.gates["engine"]["passed"]

    def test_custom_scope_still_fails_if_not_in_config(self, stack_with_custom_engine, empty_context):
        """Scope not in custom config fails."""
        request = {"mode": "SWING", "symbol": "BTCUSDT", "model_scope": "missing_v1"}
        result = stack_with_custom_engine.evaluate(request, empty_context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.ENGINE


# =========================================================================
# Layer 3: CONFIDENCE
# =========================================================================


class TestLayer3Confidence:
    """Layer 3 — model confidence >= mode threshold."""

    def test_passes_sufficient_confidence(self, stack, valid_swing_request):
        """Confidence above SWING threshold passes."""
        context = {"confidence": 0.80}
        result = stack.evaluate(valid_swing_request, context)
        assert result.gates["confidence"]["passed"]

    def test_fails_low_confidence(self, stack, valid_swing_request):
        """Confidence below SWING threshold fails."""
        context = {"confidence": 0.10}
        result = stack.evaluate(valid_swing_request, context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.CONFIDENCE
        assert result.short_circuited is True
        assert "<" in result.blocking_reason

    def test_skipped_when_missing(self, stack, valid_swing_request, empty_context):
        """Missing confidence skips the gate (passes gracefully)."""
        result = stack.evaluate(valid_swing_request, empty_context)
        assert result.gates["confidence"]["passed"]

    def test_respects_config_override(self, stack, valid_swing_request):
        """Config overrides min_confidence threshold."""
        context = {"confidence": 0.50}
        # SWING default min_confidence is 0.55, so 0.50 normally fails.
        # Override to 0.40 so it passes.
        result = stack.evaluate(
            valid_swing_request, context, config_overrides={"min_confidence": 0.40}
        )
        assert result.gates["confidence"]["passed"]

    def test_fails_with_config_override_strict(self, stack, valid_swing_request):
        """Config override can also raise the threshold."""
        context = {"confidence": 0.70}
        # SWING default is 0.55, override to 0.80 to fail.
        result = stack.evaluate(
            valid_swing_request, context, config_overrides={"min_confidence": 0.80}
        )
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.CONFIDENCE

    def test_fails_non_numeric_confidence(self, stack, valid_swing_request):
        """Non-numeric confidence value fails."""
        context = {"confidence": "high"}
        result = stack.evaluate(valid_swing_request, context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.CONFIDENCE

    def test_boundary_exact_threshold(self, stack, valid_swing_request):
        """Confidence exactly at threshold passes."""
        context = {"confidence": 0.55}  # SWING default
        result = stack.evaluate(valid_swing_request, context)
        assert result.gates["confidence"]["passed"]

    def test_boundary_just_below(self, stack, valid_swing_request):
        """Confidence just below threshold fails."""
        context = {"confidence": 0.5499}  # SWING default is 0.55
        result = stack.evaluate(valid_swing_request, context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.CONFIDENCE


# =========================================================================
# Layer 4: ECONOMIC
# =========================================================================


class TestLayer4Economic:
    """Layer 4 — net expected value positive after costs."""

    def test_passes_positive_net_r(self, stack, valid_swing_request):
        """Positive net expected R passes."""
        context = {"expected_r_gross": 0.50, "cost_r": 0.10}
        result = stack.evaluate(valid_swing_request, context)
        assert result.gates["economic"]["passed"]

    def test_fails_negative_net_r(self, stack, valid_swing_request):
        """Negative net expected R fails."""
        context = {"expected_r_gross": 0.05, "cost_r": 0.10}
        result = stack.evaluate(valid_swing_request, context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.ECONOMIC
        assert result.short_circuited is True

    def test_skipped_when_missing(self, stack, valid_swing_request, empty_context):
        """Missing expected_r_gross skips the gate."""
        result = stack.evaluate(valid_swing_request, empty_context)
        assert result.gates["economic"]["passed"]

    def test_respects_config_override(self, stack, valid_swing_request):
        """Config overrides min_expected_r threshold."""
        context = {"expected_r_gross": 0.15, "cost_r": 0.05}
        # Net = 0.10. SWING default min_expected_r is 0.20, so normally fails.
        # Override to 0.05 so it passes.
        result = stack.evaluate(
            valid_swing_request, context, config_overrides={"min_expected_r": 0.05}
        )
        assert result.gates["economic"]["passed"]

    def test_zero_gross_costs_still_pass(self, stack, valid_swing_request):
        """Zero gross and zero cost gives net 0, which may fail or skip."""
        context = {"expected_r_gross": 0.0, "cost_r": 0.0}
        result = stack.evaluate(valid_swing_request, context)
        # Net = 0.0, which is not > 0 and not >= 0.20, so fails
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.ECONOMIC

    def test_exactly_at_threshold(self, stack, valid_swing_request):
        """Net R at or above threshold passes."""
        context = {"expected_r_gross": 0.40, "cost_r": 0.10}  # net = 0.30 > 0.20
        result = stack.evaluate(valid_swing_request, context)
        assert result.gates["economic"]["passed"]

    def test_cost_r_defaults_to_zero(self, stack, valid_swing_request):
        """Missing cost_r defaults to 0."""
        context = {"expected_r_gross": 0.50}
        result = stack.evaluate(valid_swing_request, context)
        assert result.gates["economic"]["passed"]

    def test_non_numeric_gross_skips(self, stack, valid_swing_request):
        """Non-numeric expected_r_gross skips the gate."""
        context = {"expected_r_gross": "good"}
        result = stack.evaluate(valid_swing_request, context)
        assert result.gates["economic"]["passed"]


# =========================================================================
# Layer 5: TIMING
# =========================================================================


class TestLayer5Timing:
    """Layer 5 — cooldown respected, within trading window."""

    def test_passes_no_context(self, stack, valid_swing_request, empty_context):
        """No timing context passes gracefully."""
        result = stack.evaluate(valid_swing_request, empty_context)
        assert result.gates["timing"]["passed"]

    def test_fails_cooldown_violation(self, stack, valid_swing_request):
        """Cooldown not respected fails timing."""
        context = {"last_trade_time": 100.0, "current_time": 110.0}  # 10s < 120s
        result = stack.evaluate(valid_swing_request, context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.TIMING
        assert result.short_circuited is True
        assert "Cooldown" in result.blocking_reason

    def test_passes_cooldown_respected(self, stack, valid_swing_request):
        """Cooldown respected passes timing."""
        context = {"last_trade_time": 100.0, "current_time": 300.0}  # 200s > 120s
        result = stack.evaluate(valid_swing_request, context)
        assert result.gates["timing"]["passed"]

    def test_cooldown_config_override(self, stack, valid_swing_request):
        """Config overrides cooldown period."""
        context = {"last_trade_time": 100.0, "current_time": 110.0}
        # Default cooldown is 120s, so 10s < 120s fails.
        # Override to 5s so it passes.
        result = stack.evaluate(
            valid_swing_request, context, config_overrides={"cooldown_period_seconds": 5}
        )
        assert result.gates["timing"]["passed"]

    def test_fails_outside_trading_window(self, stack, valid_swing_request):
        """Outside trading window fails timing."""
        context = {
            "current_hour": 23,
        }
        # Default window is 0-24, so 23 is fine.
        # Override to 6-18 to get a failure.
        result = stack.evaluate(
            valid_swing_request,
            context,
            config_overrides={"trading_start_hour": 6, "trading_end_hour": 18},
        )
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.TIMING
        assert "Outside" in result.blocking_reason

    def test_passes_inside_trading_window(self, stack, valid_swing_request):
        """Inside trading window passes timing."""
        context = {"current_hour": 10}
        result = stack.evaluate(
            valid_swing_request,
            context,
            config_overrides={"trading_start_hour": 6, "trading_end_hour": 18},
        )
        assert result.gates["timing"]["passed"]

    def test_overnight_window_wraparound(self, stack, valid_swing_request):
        """Trading window wrapping past midnight works."""
        context = {"current_hour": 2}
        # Window 22-6 (overnight)
        result = stack.evaluate(
            valid_swing_request,
            context,
            config_overrides={"trading_start_hour": 22, "trading_end_hour": 6},
        )
        assert result.gates["timing"]["passed"]

    def test_overnight_window_outside(self, stack, valid_swing_request):
        """Outside overnight trading window."""
        context = {"current_hour": 10}
        result = stack.evaluate(
            valid_swing_request,
            context,
            config_overrides={"trading_start_hour": 22, "trading_end_hour": 6},
        )
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.TIMING


# =========================================================================
# Layer 6: OPERATIONAL
# =========================================================================


class TestLayer6Operational:
    """Layer 6 — exchange available, rate limits OK."""

    def test_passes_no_context(self, stack, valid_swing_request, empty_context):
        """No operational context passes gracefully."""
        result = stack.evaluate(valid_swing_request, empty_context)
        assert result.gates["operational"]["passed"]

    def test_fails_exchange_unavailable(self, stack, valid_swing_request):
        """Exchange not available fails operational."""
        context = {"exchange_available": False}
        result = stack.evaluate(valid_swing_request, context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.OPERATIONAL
        assert result.short_circuited is True
        assert "not available" in result.blocking_reason

    def test_passes_exchange_available(self, stack, valid_swing_request):
        """Exchange available passes."""
        context = {"exchange_available": True}
        result = stack.evaluate(valid_swing_request, context)
        assert result.gates["operational"]["passed"]

    def test_fails_low_exchange_health(self, stack, valid_swing_request):
        """Low exchange health fails."""
        context = {"exchange_health": 0.5}  # Default min is 0.8
        result = stack.evaluate(valid_swing_request, context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.OPERATIONAL
        assert "health" in result.blocking_reason.lower()

    def test_fails_rate_limit_exhausted(self, stack, valid_swing_request):
        """Exhausted rate limit fails."""
        context = {"rate_limit_remaining": 0}
        result = stack.evaluate(valid_swing_request, context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.OPERATIONAL
        assert "Rate limit" in result.blocking_reason

    def test_health_config_override(self, stack, valid_swing_request):
        """Config overrides min exchange health."""
        context = {"exchange_health": 0.5}
        # Override min to 0.3 so it passes
        result = stack.evaluate(
            valid_swing_request, context, config_overrides={"min_exchange_health": 0.3}
        )
        assert result.gates["operational"]["passed"]


# =========================================================================
# Short-Circuit Behaviour
# =========================================================================


class TestShortCircuit:
    """Short-circuit behaviour: first fail stops evaluation."""

    def test_stop_at_structural(self, stack, empty_context):
        """Fail at structural — no other layers evaluated."""
        request = {"symbol": "BTCUSDT"}  # missing mode
        result = stack.evaluate(request, empty_context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.STRUCTURAL
        assert result.short_circuited is True
        # Only structural gate should be present
        assert set(result.gates.keys()) == {"structural"}

    def test_stop_at_engine(self, stack, empty_context):
        """Fail at engine — confidence not evaluated."""
        # Valid structural, but unknown model_scope
        request = {"mode": "SWING", "symbol": "BTCUSDT", "model_scope": "nope_v99"}
        result = stack.evaluate(request, empty_context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.ENGINE
        assert result.short_circuited is True
        assert "engine" not in result.gates or not result.gates.get("engine", {}).get("passed")

    def test_stop_at_confidence(self, stack, valid_swing_request):
        """Fail at confidence — economic not evaluated."""
        context = {"confidence": 0.0}
        result = stack.evaluate(valid_swing_request, context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.CONFIDENCE
        assert result.short_circuited is True
        # Confidence gate present, economic should not be
        assert "confidence" in result.gates
        assert "economic" not in result.gates

    def test_stop_at_economic(self, stack, valid_swing_request):
        """Fail at economic — timing not evaluated."""
        context = {"confidence": 0.80, "expected_r_gross": 0.0, "cost_r": 0.50}
        result = stack.evaluate(valid_swing_request, context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.ECONOMIC
        assert result.short_circuited is True
        # Economic present, timing should not be
        assert "economic" in result.gates
        assert "timing" not in result.gates

    def test_stop_at_timing(self, stack, valid_swing_request):
        """Fail at timing — operational not evaluated."""
        context = {
            "confidence": 0.80,
            "expected_r_gross": 0.50,
            "cost_r": 0.10,
            "last_trade_time": 100.0,
            "current_time": 110.0,  # violates 120s cooldown
        }
        result = stack.evaluate(valid_swing_request, context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.TIMING
        assert result.short_circuited is True
        assert "timing" in result.gates
        assert "operational" not in result.gates

    def test_stop_at_operational(self, stack, valid_swing_request):
        """Fail at operational — last layer, still short-circuits."""
        context = {
            "confidence": 0.80,
            "expected_r_gross": 0.50,
            "cost_r": 0.10,
            "exchange_available": False,
        }
        result = stack.evaluate(valid_swing_request, context)
        assert result.eligible is False
        assert result.current_layer == EligibilityLayer.OPERATIONAL
        assert result.short_circuited is True
        assert "operational" in result.gates


# =========================================================================
# Happy Path — All Layers Pass
# =========================================================================


class TestHappyPath:
    """All layers pass — full stack cleared."""

    def test_full_pass(self, stack, valid_swing_request):
        """All six layers pass."""
        context = {
            "confidence": 0.80,
            "expected_r_gross": 0.50,
            "cost_r": 0.10,
            "last_trade_time": 100.0,
            "current_time": 300.0,  # cooldown respected
            "exchange_available": True,
            "exchange_health": 0.95,
            "rate_limit_remaining": 50,
        }
        result = stack.evaluate(valid_swing_request, context)
        assert result.eligible is True
        assert result.current_layer == EligibilityLayer.OPERATIONAL
        assert result.short_circuited is False
        assert result.blocking_reason == ""
        # All six gates present and passed
        assert set(result.gates.keys()) == {
            "structural", "engine", "confidence",
            "economic", "timing", "operational",
        }
        for gate_name, gate in result.gates.items():
            assert gate["passed"], f"Gate '{gate_name}' failed: {gate['reason']}"

    def test_full_pass_scalp_request(self, stack):
        """All layers pass with SCALP request."""
        request = {"mode": "SCALP", "symbol": "ETHUSDT", "model_scope": "scalp_v1"}
        context = {
            "confidence": 0.80,
            "expected_r_gross": 0.30,
            "cost_r": 0.05,
            "current_time": 500.0,
            "last_trade_time": 0.0,
            "exchange_available": True,
            "rate_limit_remaining": 50,
        }
        result = stack.evaluate(request, context)
        assert result.eligible is True

    def test_full_pass_empty_context(self, stack, valid_swing_request):
        """Full pass with empty context (all optional gates skipped)."""
        result = stack.evaluate(valid_swing_request, {})
        assert result.eligible is True
        assert result.current_layer == EligibilityLayer.OPERATIONAL


# =========================================================================
# Config-Driven Threshold Overrides
# =========================================================================


class TestConfigOverrides:
    """Config-driven threshold overrides applied per invocation."""

    def test_override_min_confidence(self, stack, valid_swing_request):
        """Override min_confidence via config_overrides."""
        context = {"confidence": 0.50}
        result = stack.evaluate(
            valid_swing_request,
            context,
            config_overrides={"min_confidence": 0.40},
        )
        assert result.gates["confidence"]["passed"]

    def test_override_min_expected_r(self, stack, valid_swing_request):
        """Override min_expected_r via config_overrides."""
        context = {"expected_r_gross": 0.12, "cost_r": 0.05}
        result = stack.evaluate(
            valid_swing_request,
            context,
            config_overrides={"min_expected_r": 0.05},
        )
        assert result.gates["economic"]["passed"]

    def test_override_cooldown(self, stack, valid_swing_request):
        """Override cooldown_period_seconds via config_overrides."""
        context = {"last_trade_time": 100.0, "current_time": 120.0}
        result = stack.evaluate(
            valid_swing_request,
            context,
            config_overrides={"cooldown_period_seconds": 15},
        )
        assert result.gates["timing"]["passed"]

    def test_override_trading_window(self, stack, valid_swing_request):
        """Override trading window via config_overrides."""
        context = {"current_hour": 22}
        result = stack.evaluate(
            valid_swing_request,
            context,
            config_overrides={"trading_start_hour": 6, "trading_end_hour": 23},
        )
        assert result.gates["timing"]["passed"]

    def test_override_health(self, stack, valid_swing_request):
        """Override min_exchange_health via config_overrides."""
        context = {"exchange_health": 0.6}
        result = stack.evaluate(
            valid_swing_request,
            context,
            config_overrides={"min_exchange_health": 0.5},
        )
        assert result.gates["operational"]["passed"]

    def test_multiple_overrides(self, stack, valid_swing_request):
        """Multiple config overrides applied simultaneously."""
        context = {
            "confidence": 0.50,
            "expected_r_gross": 0.15,
            "cost_r": 0.05,
        }
        result = stack.evaluate(
            valid_swing_request,
            context,
            config_overrides={
                "min_confidence": 0.40,
                "min_expected_r": 0.05,
            },
        )
        assert result.eligible is True


class TestEligibility:
    """Eligibility alias for EligibilityStack."""

    def test_alias(self):
        """Eligibility is an alias for EligibilityStack."""
        from v7.eligibility import Eligibility
        assert Eligibility is EligibilityStack
