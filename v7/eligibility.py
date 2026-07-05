"""
V7 Layered Execution-Eligibility Stack.

Domain authority:
  - Evaluates whether a trade candidate can proceed to execution.
  - Six layers in strict order, each gating the next.
  - Short-circuits on first failure: no point checking confidence if the
    request structure is invalid, no point checking timing if the model
    features aren't loaded.

Ownership:
  - V7 owns the eligibility decision (policy acceptance authority).
  - Layer 3 (CONFIDENCE) reads thresholds from MODE_PROFILES (router).
  - Layer 4 (ECONOMIC) consumes externally computed costs and expected value.
  - Layer 6 (OPERATIONAL) delegates to runtime/exchange health signals.

Callers:
  - runtime/execution_orchestrator.py uses this stack to gate execution.
  - evaluate_policy() in v7/policy.py feeds into Layer 3 and Layer 4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from v7.router import MODE_PROFILES, get_mode_profile


# =========================================================================
# Layer Enum
# =========================================================================


class EligibilityLayer(IntEnum):
    """Execution-eligibility layers, evaluated in ascending order.

    Each layer depends on the previous:
      - If the request is structurally invalid (Layer 1), there is no point
        checking engine readiness (Layer 2).
      - If the model is not loaded (Layer 2), there is no point checking
        confidence (Layer 3).
      - If confidence is too low (Layer 3), there is no point computing
        economic value (Layer 4).
      - If expected value is negative (Layer 4), there is no point checking
        timing (Layer 5).
      - If outside the trading window (Layer 5), there is no point checking
        the exchange health (Layer 6).
    """

    STRUCTURAL = 1
    ENGINE = 2
    CONFIDENCE = 3
    ECONOMIC = 4
    TIMING = 5
    OPERATIONAL = 6


# =========================================================================
# Result Dataclass
# =========================================================================


@dataclass(frozen=True)
class EligibilityResult:
    """Result of evaluating execution eligibility.

    Attributes:
        eligible: True if ALL layers passed (full stack cleared).
        current_layer: The layer at which evaluation stopped, or None if
                       evaluation did not begin (e.g. no context provided).
                       On a full pass, this is the last layer (OPERATIONAL).
        gates: Dict mapping layer names (lowercase) to per-layer outcomes.
               Each value has: passed (bool), reason (str), evidence (dict).
        blocking_reason: Concise human-readable reason for the block.
        short_circuited: True if evaluation stopped early due to a layer
                         failure. False if all layers were evaluated or
                         no evaluation occurred.
    """

    eligible: bool
    current_layer: EligibilityLayer | None
    gates: dict[str, dict] = field(default_factory=dict)
    blocking_reason: str = ""
    short_circuited: bool = False


# =========================================================================
# Default Config
# =========================================================================

# Config-driven defaults used when the caller does not supply explicit
# overrides. These are conservative baselines — production deployments
# MUST set values appropriate to their infrastructure.

_DEFAULT_ENGINE_CONFIG: dict[str, Any] = {
    "swing_v1": {"features": ["returns", "volatility", "volume"]},
    "scalp_v1": {"features": ["returns", "volatility", "volume", "orderbook"]},
}

_DEFAULT_TIMING_CONFIG: dict[str, Any] = {
    "cooldown_period_seconds": 120,
    "trading_start_hour": 0,
    "trading_end_hour": 24,
}

_DEFAULT_OPERATIONAL_CONFIG: dict[str, Any] = {
    "min_exchange_health": 0.8,
    "rate_limit_capacity": 100,
}

# Known mode-agnostic model_scope values (scopes that are not mode-tagged)
_KNOWN_SCOPES: set[str] = {"generic_v1", "baseline_v1"}


# =========================================================================
# Layer Helpers (internal)
# =========================================================================


def _build_gate(
    passed: bool,
    reason: str,
    **evidence: Any,
) -> dict[str, Any]:
    return {
        "passed": passed,
        "reason": reason,
        "evidence": evidence,
    }


def _check_structural(request: dict[str, Any]) -> dict[str, Any]:
    """Layer 1: Structural — valid request/result, mode supported."""
    mode = request.get("mode", request.get("requested_trade_mode", ""))
    if not mode or not isinstance(mode, str) or not mode.strip():
        return _build_gate(
            False,
            "Missing or empty mode/requested_trade_mode in request",
        )

    mode = mode.upper()
    if mode not in MODE_PROFILES:
        return _build_gate(
            False,
            f"Unknown mode '{mode}'. Valid modes: {sorted(MODE_PROFILES.keys())}",
        )

    symbol = request.get("symbol", "")
    if not symbol or not isinstance(symbol, str):
        return _build_gate(
            False,
            "Missing or empty symbol in request",
        )

    model_scope = request.get("model_scope", "")
    if not model_scope or not isinstance(model_scope, str):
        return _build_gate(
            False,
            "Missing or empty model_scope in request",
        )

    return _build_gate(
        True,
        f"Request structurally valid for mode={mode}, symbol={symbol}",
        mode=mode,
        symbol=symbol,
        model_scope=model_scope,
    )


def _check_engine(
    request: dict[str, Any],
    engine_config: dict[str, Any],
) -> dict[str, Any]:
    """Layer 2: Engine — model scope known, feature config present."""
    model_scope = request.get("model_scope", "")

    # Check if scope is known in config or is a known agnostic scope
    if model_scope not in engine_config and model_scope not in _KNOWN_SCOPES:
        # Also try matching by prefix (e.g. swing_v2 could match swing_v1 config)
        matched = False
        for known_scope in engine_config:
            if model_scope.startswith(known_scope.rsplit("_", 1)[0] + "_"):
                matched = True
                break
        if not matched:
            return _build_gate(
                False,
                f"model_scope '{model_scope}' not found in engine config",
                known_scopes=sorted(engine_config.keys()),
            )

    # Check features are configured
    features_config = engine_config.get(model_scope, None)
    if features_config is None and model_scope in _KNOWN_SCOPES:
        # Known agnostic scopes are allowed without explicit feature list
        pass
    elif features_config is None:
        # Scope matched by prefix — look up the parent
        for known_scope in engine_config:
            if model_scope.startswith(known_scope.rsplit("_", 1)[0] + "_"):
                features_config = engine_config.get(known_scope, {})
                break

    if features_config is not None:
        features = features_config.get("features", [])
        if not features:
            return _build_gate(
                False,
                f"Empty features list for model_scope '{model_scope}'",
            )

    return _build_gate(
        True,
        f"Engine ready for model_scope='{model_scope}'",
        model_scope=model_scope,
    )


def _check_confidence(
    context: dict[str, Any],
    mode: str,
    config_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Layer 3: Confidence — model confidence >= mode threshold."""
    if "confidence" not in context:
        return _build_gate(
            True,
            "No confidence in context — confidence gate skipped",
        )

    confidence = context.get("confidence", 0.0)
    if not isinstance(confidence, (int, float)):
        return _build_gate(
            False,
            f"Invalid confidence type: {type(confidence).__name__}",
            confidence=confidence,
        )

    # Resolve threshold: config overrides > mode profile > hard default
    min_confidence = config_overrides.get(
        "min_confidence",
        get_mode_profile(mode).get("min_confidence", 0.55),
    )

    passed = confidence >= min_confidence
    if passed:
        return _build_gate(
            True,
            f"Confidence {confidence:.4f} >= {min_confidence}",
            confidence=confidence,
            threshold=min_confidence,
        )
    else:
        return _build_gate(
            False,
            f"Confidence {confidence:.4f} < {min_confidence}",
            confidence=confidence,
            threshold=min_confidence,
        )


def _check_economic(
    context: dict[str, Any],
    mode: str,
    config_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Layer 4: Economic — net expected value positive after costs."""
    expected_r_gross = context.get("expected_r_gross")
    if expected_r_gross is None or not isinstance(expected_r_gross, (int, float)):
        return _build_gate(
            True,
            "No expected_r_gross in context — economic gate skipped",
        )

    cost_r = context.get("cost_r", 0.0)
    if not isinstance(cost_r, (int, float)):
        cost_r = 0.0

    # Resolve threshold: config overrides > mode profile > hard default
    min_expected_r = config_overrides.get(
        "min_expected_r",
        get_mode_profile(mode).get("min_expected_r", 0.20),
    )

    net_r = float(expected_r_gross) - float(cost_r)
    passed = net_r > 0 and net_r >= min_expected_r

    if passed:
        return _build_gate(
            True,
            f"Net expected R {net_r:.4f} >= {min_expected_r} "
            f"(gross={expected_r_gross}, cost={cost_r})",
            expected_r_gross=expected_r_gross,
            cost_r=cost_r,
            net_r=net_r,
            threshold=min_expected_r,
        )
    else:
        return _build_gate(
            False,
            f"Net expected R {net_r:.4f} < {min_expected_r} "
            f"(gross={expected_r_gross}, cost={cost_r})",
            expected_r_gross=expected_r_gross,
            cost_r=cost_r,
            net_r=net_r,
            threshold=min_expected_r,
        )


def _check_timing(
    context: dict[str, Any],
    config_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Layer 5: Timing — cooldown respected, within trading window."""
    # Cooldown check
    cooldown = config_overrides.get(
        "cooldown_period_seconds",
        _DEFAULT_TIMING_CONFIG["cooldown_period_seconds"],
    )
    last_trade_time = context.get("last_trade_time")
    current_time = context.get("current_time")

    if last_trade_time is not None and current_time is not None:
        try:
            elapsed = abs(float(current_time) - float(last_trade_time))
            if elapsed < float(cooldown):
                return _build_gate(
                    False,
                    f"Cooldown not respected: {elapsed:.1f}s < {cooldown}s",
                    elapsed_seconds=elapsed,
                    cooldown_seconds=cooldown,
                )
        except (TypeError, ValueError, OverflowError):
            pass  # If timestamps are non-numeric, skip cooldown check

    # Trading window check
    trading_start = config_overrides.get(
        "trading_start_hour",
        _DEFAULT_TIMING_CONFIG["trading_start_hour"],
    )
    trading_end = config_overrides.get(
        "trading_end_hour",
        _DEFAULT_TIMING_CONFIG["trading_end_hour"],
    )

    current_hour = context.get("current_hour")
    if current_hour is not None:
        try:
            hour = int(current_hour)
            # Support wraparound (e.g. 22-6 = overnight window)
            if trading_start <= trading_end:
                in_window = trading_start <= hour < trading_end
            else:
                in_window = hour >= trading_start or hour < trading_end

            if not in_window:
                return _build_gate(
                    False,
                    f"Outside trading window: hour={hour} "
                    f"(window={trading_start}-{trading_end})",
                    current_hour=hour,
                    trading_start=trading_start,
                    trading_end=trading_end,
                )
        except (TypeError, ValueError):
            pass  # If hour is non-integer, skip window check

    return _build_gate(
        True,
        "Timing checks passed (cooldown + trading window)",
        cooldown_seconds=cooldown,
        trading_window=f"{trading_start}-{trading_end}",
    )


def _check_operational(
    context: dict[str, Any],
    config_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Layer 6: Operational — exchange available, rate limits OK."""
    min_health = config_overrides.get(
        "min_exchange_health",
        _DEFAULT_OPERATIONAL_CONFIG["min_exchange_health"],
    )
    rate_capacity = config_overrides.get(
        "rate_limit_capacity",
        _DEFAULT_OPERATIONAL_CONFIG["rate_limit_capacity"],
    )

    exchange_available = context.get("exchange_available")
    if exchange_available is not None and not exchange_available:
        return _build_gate(
            False,
            "Exchange is not available",
            exchange_available=exchange_available,
        )

    exchange_health = context.get("exchange_health")
    if exchange_health is not None:
        try:
            if float(exchange_health) < float(min_health):
                return _build_gate(
                    False,
                    f"Exchange health {exchange_health} < {min_health}",
                    exchange_health=exchange_health,
                    min_health=min_health,
                )
        except (TypeError, ValueError):
            pass

    rate_limit_remaining = context.get("rate_limit_remaining")
    if rate_limit_remaining is not None:
        try:
            if int(rate_limit_remaining) <= 0:
                return _build_gate(
                    False,
                    "Rate limit exhausted",
                    rate_limit_remaining=rate_limit_remaining,
                )
        except (TypeError, ValueError):
            pass

    return _build_gate(
        True,
        "Operational checks passed (exchange available, rate limits OK)",
        min_exchange_health=min_health,
        rate_limit_capacity=rate_capacity,
    )


# =========================================================================
# EligibilityStack
# =========================================================================


class EligibilityStack:
    """Six-layer execution-eligibility stack.

    Usage::

        stack = EligibilityStack()
        result = stack.evaluate(
            request={"mode": "SWING", "symbol": "BTCUSDT", "model_scope": "swing_v1"},
            context={},
        )
        if not result.eligible:
            print(result.blocking_reason)

    Config overrides can be passed to ``evaluate()`` to customise thresholds
    per invocation.  Defaults come from the module-level config dicts and
    ``v7.router.MODE_PROFILES``.
    """

    def __init__(self, engine_config: dict[str, Any] | None = None):
        """Initialise the eligibility stack.

        Args:
            engine_config: Override the default engine feature config.
                           If None, ``_DEFAULT_ENGINE_CONFIG`` is used.
        """
        self._engine_config: dict[str, Any] = (
            dict(engine_config) if engine_config else dict(_DEFAULT_ENGINE_CONFIG)
        )

    def evaluate(
        self,
        request: dict[str, Any],
        context: dict[str, Any],
        config_overrides: dict[str, Any] | None = None,
    ) -> EligibilityResult:
        """Evaluate execution eligibility across all six layers.

        Args:
            request: The AnalysisRequest dict.  Must contain at minimum
                     ``mode`` (or ``requested_trade_mode``), ``symbol``,
                     and ``model_scope``.
            context: Runtime context dict.  May contain ``confidence``,
                     ``expected_r_gross``, ``cost_r``, ``last_trade_time``,
                     ``current_time``, ``current_hour``,
                     ``exchange_available``, ``exchange_health``,
                     ``rate_limit_remaining``, etc.
            config_overrides: Optional dict that can override thresholds
                              for any layer.  Supported keys:
                              ``min_confidence``, ``min_expected_r``,
                              ``cooldown_period_seconds``,
                              ``trading_start_hour``, ``trading_end_hour``,
                              ``min_exchange_health``,
                              ``rate_limit_capacity``.

        Returns:
            EligibilityResult — if any layer fails, short_circuited is True
            and remaining layers are not evaluated.
        """
        raw_mode = request.get("mode", request.get("requested_trade_mode", ""))
        if not isinstance(raw_mode, str):
            # Non-string mode — let _check_structural produce a clean failure
            raw_mode = ""
        mode = raw_mode.upper()
        overrides = config_overrides or {}
        gates: dict[str, dict] = {}
        current_layer: EligibilityLayer | None = None
        blocking_reason = ""

        # ── Layer 1: STRUCTURAL ────────────────────────────────────────
        current_layer = EligibilityLayer.STRUCTURAL
        gates["structural"] = _check_structural(request)
        if not gates["structural"]["passed"]:
            return EligibilityResult(
                eligible=False,
                current_layer=current_layer,
                gates=gates,
                blocking_reason=gates["structural"]["reason"],
                short_circuited=True,
            )

        # Extract validated fields from structural gate evidence
        mode = gates["structural"]["evidence"]["mode"]
        symbol = gates["structural"]["evidence"]["symbol"]
        model_scope = gates["structural"]["evidence"]["model_scope"]

        # ── Layer 2: ENGINE ────────────────────────────────────────────
        current_layer = EligibilityLayer.ENGINE
        gates["engine"] = _check_engine(request, self._engine_config)
        if not gates["engine"]["passed"]:
            return EligibilityResult(
                eligible=False,
                current_layer=current_layer,
                gates=gates,
                blocking_reason=gates["engine"]["reason"],
                short_circuited=True,
            )

        # ── Layer 3: CONFIDENCE ────────────────────────────────────────
        current_layer = EligibilityLayer.CONFIDENCE
        gates["confidence"] = _check_confidence(context, mode, overrides)
        if not gates["confidence"]["passed"]:
            return EligibilityResult(
                eligible=False,
                current_layer=current_layer,
                gates=gates,
                blocking_reason=gates["confidence"]["reason"],
                short_circuited=True,
            )

        # ── Layer 4: ECONOMIC ──────────────────────────────────────────
        current_layer = EligibilityLayer.ECONOMIC
        gates["economic"] = _check_economic(context, mode, overrides)
        if not gates["economic"]["passed"]:
            return EligibilityResult(
                eligible=False,
                current_layer=current_layer,
                gates=gates,
                blocking_reason=gates["economic"]["reason"],
                short_circuited=True,
            )

        # ── Layer 5: TIMING ────────────────────────────────────────────
        current_layer = EligibilityLayer.TIMING
        gates["timing"] = _check_timing(context, overrides)
        if not gates["timing"]["passed"]:
            return EligibilityResult(
                eligible=False,
                current_layer=current_layer,
                gates=gates,
                blocking_reason=gates["timing"]["reason"],
                short_circuited=True,
            )

        # ── Layer 6: OPERATIONAL ───────────────────────────────────────
        current_layer = EligibilityLayer.OPERATIONAL
        gates["operational"] = _check_operational(context, overrides)
        if not gates["operational"]["passed"]:
            return EligibilityResult(
                eligible=False,
                current_layer=current_layer,
                gates=gates,
                blocking_reason=gates["operational"]["reason"],
                short_circuited=True,
            )

        # ── ALL PASSED ─────────────────────────────────────────────────
        return EligibilityResult(
            eligible=True,
            current_layer=current_layer,
            gates=gates,
            blocking_reason="",
            short_circuited=False,
        )


# Public alias
Eligibility = EligibilityStack
