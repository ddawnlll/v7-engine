"""
Mode dispatch router for V7 policy acceptance.

Routes AnalysisRequests to mode-appropriate processing pipelines.

Mode status per v7/docs/v7_mode_centric_architecture.md:
  - SWING:           LOCKED_INITIAL_BASELINE — fully dispatched
  - SCALP:           HOLD — blocked until empirical evidence gates pass
  - AGGRESSIVE_SCALP: HOLD — blocked until empirical evidence gates pass

HOLD modes return a HOLD decision with NO_TRADE recommendation and a
diagnostic reason explaining which evidence gates are pending.

SWING mode configuration (LOCKED_INITIAL_BASELINE):
  - primary_interval: 4h
  - context_intervals: [1d, 1h]
  - min_confidence: 0.55
  - min_expected_r: 0.20
  - max_position_size_pct: 10.0
  - stop_multiplier: 2.0 (ATR)
  - target_multiplier: 2.5 (ATR)
  - ambiguity_margin_r: 0.20
  - min_action_edge_r: 0.35

Scope/model_scope compatibility rules per v7/docs/contracts/analysis_request.md:
  - SWING             model_scope must start with 'swing_'
  - SCALP             model_scope must start with 'scalp_'
  - AGGRESSIVE_SCALP  model_scope must start with 'aggressive_scalp_'

A request with requested_trade_mode='SCALP' and model_scope='swing_v1' is a
scope_mismatch and must not be routed silently to either artifact family.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Mode lock status
LOCKED_INITIAL_BASELINE = "LOCKED_INITIAL_BASELINE"
HOLD = "HOLD"

# Valid model_scope prefixes per mode
_MODEL_SCOPE_PREFIXES: dict[str, str] = {
    "SWING": "swing_",
    "SCALP": "scalp_",
    "AGGRESSIVE_SCALP": "aggressive_scalp_",
}

# Mode configuration profiles (matches v7_mode_centric_architecture.md table)
MODE_PROFILES: dict[str, dict[str, Any]] = {
    "SWING": {
        "status": LOCKED_INITIAL_BASELINE,
        "primary_interval": "4h",
        "context_intervals": ["1d", "1h"],
        "min_confidence": 0.55,
        "min_expected_r": 0.20,
        "max_position_size_pct": 10.0,
        "stop_multiplier": 2.0,
        "target_multiplier": 2.5,
        "ambiguity_margin_r": 0.20,
        "min_action_edge_r": 0.35,
        "max_holding_bars": 30,
        "mae_penalty_weight": "medium",
        "cost_penalty_weight": "medium",
        "min_shadow_duration_days": 28,
        "min_shadow_trades": 20,
        "min_paper_duration_days": 28,
        "min_paper_trades": 50,
        "max_tiny_live_risk_per_trade_pct": 0.5,
        "max_tiny_live_daily_loss_pct": 5.0,
        "max_tiny_live_cumulative_loss_pct": 10.0,
    },
    "SCALP": {
        "status": LOCKED_INITIAL_BASELINE,  # Updated 2026-07-15
        "primary_interval": "1h",
        "context_intervals": ["4h", "15m"],
        "min_confidence": 0.60,
        "min_expected_r": 0.10,
        "max_position_size_pct": 5.0,
        "stop_multiplier": 1.5,
        "target_multiplier": 1.5,
        "ambiguity_margin_r": 0.10,
        "min_action_edge_r": 0.15,
        "max_holding_bars": 12,
        "mae_penalty_weight": "high",
        "cost_penalty_weight": "very_high",
        "min_shadow_duration_days": 21,
        "min_shadow_trades": 50,
        "min_paper_duration_days": 28,
        "min_paper_trades": 100,
        "max_tiny_live_risk_per_trade_pct": 0.25,
        "max_tiny_live_daily_loss_pct": 3.0,
        "max_tiny_live_cumulative_loss_pct": 7.0,
        "hold_reason": "2026-07-15: promote to LOCKED_INITIAL_BASELINE — empirical evidence: 56-symbol WFV, th=0.70, 94.5% winrate, 1.4/day, +0.08R, cost stress 3.0x",
    },
    "AGGRESSIVE_SCALP": {
        "status": LOCKED_INITIAL_BASELINE,  # Updated 2026-07-15
        "primary_interval": "15m",
        "context_intervals": ["1h", "5m"],
        "min_confidence": 0.70,
        "min_expected_r": 0.05,
        "max_position_size_pct": 3.0,
        "stop_multiplier": 1.0,
        "target_multiplier": 1.0,
        "ambiguity_margin_r": 0.05,
        "min_action_edge_r": 0.08,
        "max_holding_bars": 5,
        "mae_penalty_weight": "very_high",
        "cost_penalty_weight": "very_high",
        "min_shadow_duration_days": 14,
        "min_shadow_trades": 100,
        "min_paper_duration_days": 21,
        "min_paper_trades": 200,
        "max_tiny_live_risk_per_trade_pct": 0.1,
        "max_tiny_live_daily_loss_pct": 2.0,
        "max_tiny_live_cumulative_loss_pct": 5.0,
        "hold_reason": (
            "AGGRESSIVE_SCALP mode requires empirical evidence: "
            "cost-adjusted expectancy positive after realistic fees/slippage, "
            "latency impact measured, data quality verified at 15m/5m, "
            "order-book analysis ready (Phase 3), no-trade default verified."
        ),
    },
}


@dataclass(frozen=True)
class RouteResult:
    """Result of mode routing an AnalysisRequest.

    Attributes:
        allowed: Whether the mode is allowed to proceed (True for SWING,
                 False for HOLD modes).
        mode: The requested trading mode.
        profile: The mode-specific configuration dict.
        block_reason: Human-readable reason if blocked (empty if allowed).
    """

    allowed: bool
    mode: str
    profile: dict[str, Any] = field(default_factory=dict)
    block_reason: str = ""


def validate_model_scope(model_scope: str, mode: str) -> str | None:
    """Validate that model_scope prefix matches the given trading mode.

    Args:
        model_scope: The model scope identifier, e.g. 'swing_v1'.
        mode: The trading mode, e.g. 'SWING'.

    Returns:
        An error message string if invalid, or None if valid.
    """
    mode = mode.upper()
    if mode not in _MODEL_SCOPE_PREFIXES:
        return f"Unknown mode '{mode}' for model_scope validation"

    expected_prefix = _MODEL_SCOPE_PREFIXES[mode]
    if not model_scope or not isinstance(model_scope, str):
        return "model_scope must be a non-empty string"

    if not model_scope.startswith(expected_prefix):
        return (
            f"model_scope '{model_scope}' does not match mode '{mode}': "
            f"expected prefix '{expected_prefix}', "
            f"e.g. '{expected_prefix}v1'"
        )
    return None


def validate_scope_compatibility(
    requested_trade_mode: str,
    model_scope: str,
) -> str | None:
    """Validate that a requested_trade_mode and model_scope are compatible.

    Per the V7 contract authority docs:
    "A request with requested_trade_mode='SCALP' and model_scope='swing_v1'
     is a scope_mismatch and must not be routed silently."

    Args:
        requested_trade_mode: The trade mode, e.g. 'SWING'.
        model_scope: The model scope identifier, e.g. 'swing_v1'.

    Returns:
        An error message string if scope mismatch, or None if compatible.
    """
    mode = requested_trade_mode.upper()

    if mode not in _MODEL_SCOPE_PREFIXES:
        return f"Unknown requested_trade_mode '{requested_trade_mode}'"

    return validate_model_scope(model_scope, mode)


def get_artifact_scope_tag(mode: str) -> str:
    """Return the artifact scope tag for a given trading mode.

    The artifact scope tag is used to identify which model artifacts
    are applicable to a given mode, e.g. 'swing' -> 'v7_swing'.

    Args:
        mode: The trading mode, e.g. 'SWING', 'SCALP', 'AGGRESSIVE_SCALP'.

    Returns:
        Artifact scope tag string, e.g. 'v7_swing'.

    Raises:
        ValueError: If the mode is not recognized.
    """
    mode = mode.upper()
    if mode not in _MODEL_SCOPE_PREFIXES:
        raise ValueError(
            f"Unknown mode '{mode}'. Valid modes: {sorted(_MODEL_SCOPE_PREFIXES.keys())}"
        )
    prefix = _MODEL_SCOPE_PREFIXES[mode]
    # Strip trailing underscore for artifact tag
    scope_name = prefix.rstrip("_")
    return f"v7_{scope_name}"


def route_request(
    request: dict[str, Any],
    validate_scope: bool = False,
) -> RouteResult:
    """Route an AnalysisRequest to its mode pipeline.

    Args:
        request: The AnalysisRequest dict to route.
        validate_scope: If True, also validate model_scope compatibility
                        with requested_trade_mode. Raises ValueError on
                        scope mismatch.

    Returns a RouteResult indicating whether the mode is allowed and its
    configuration profile.

    SWING (LOCKED_INITIAL_BASELINE) always returns allowed=True.
    SCALP/AGGRESSIVE_SCALP (HOLD) always return allowed=False with a
    diagnostic block_reason.

    Raises:
        ValueError: If the request mode is not recognized, or if
                    validate_scope=True and scope compatibility fails.
    """
    mode = request.get("mode") or request.get("requested_trade_mode") or request.get("scope", {}).get("requested_trade_mode", "")
    if not mode:
        raise ValueError("AnalysisRequest is missing 'mode' field")

    mode = mode.upper()
    profile = MODE_PROFILES.get(mode)
    if profile is None:
        raise ValueError(
            f"Unknown mode '{mode}'. Valid modes: {sorted(MODE_PROFILES.keys())}"
        )

    # Optional scope compatibility validation
    if validate_scope:
        model_scope = request.get("model_scope", request.get("scope", {}).get("model_scope", ""))
        if model_scope:
            err = validate_scope_compatibility(mode, model_scope)
            if err is not None:
                raise ValueError(f"Scope mismatch: {err}")

    status = profile.get("status", HOLD)
    if status == LOCKED_INITIAL_BASELINE:
        return RouteResult(allowed=True, mode=mode, profile=profile)
    else:
        return RouteResult(
            allowed=False,
            mode=mode,
            profile=profile,
            block_reason=profile.get("hold_reason", f"Mode '{mode}' is on HOLD"),
        )


def get_mode_profile(mode: str) -> dict[str, Any]:
    """Return the profile dict for a given mode (no routing logic)."""
    mode = mode.upper()
    profile = MODE_PROFILES.get(mode)
    if profile is None:
        raise ValueError(
            f"Unknown mode '{mode}'. Valid modes: {sorted(MODE_PROFILES.keys())}"
        )
    return dict(profile)


def get_available_modes() -> dict[str, str]:
    """Return {mode: status} for all known modes."""
    return {mode: profile["status"] for mode, profile in MODE_PROFILES.items()}
