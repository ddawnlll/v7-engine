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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Mode lock status
LOCKED_INITIAL_BASELINE = "LOCKED_INITIAL_BASELINE"
HOLD = "HOLD"

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
    },
    "SCALP": {
        "status": HOLD,
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
        "hold_reason": (
            "SCALP mode requires empirical evidence: "
            "walk-forward OOS expectancy R > 0, fee/slippage/latency stress "
            "tests passing, funding cost model validated, no-trade quality "
            "acceptable across all market regimes."
        ),
    },
    "AGGRESSIVE_SCALP": {
        "status": HOLD,
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


def route_request(request: dict[str, Any]) -> RouteResult:
    """Route an AnalysisRequest to its mode pipeline.

    Returns a RouteResult indicating whether the mode is allowed and its
    configuration profile.

    SWING (LOCKED_INITIAL_BASELINE) always returns allowed=True.
    SCALP/AGGRESSIVE_SCALP (HOLD) always return allowed=False with a
    diagnostic block_reason.

    Raises:
        ValueError: If the request mode is not recognized.
    """
    mode = request.get("mode", request.get("requested_trade_mode", ""))
    if not mode:
        raise ValueError("AnalysisRequest is missing 'mode' field")

    mode = mode.upper()
    profile = MODE_PROFILES.get(mode)
    if profile is None:
        raise ValueError(
            f"Unknown mode '{mode}'. Valid modes: {sorted(MODE_PROFILES.keys())}"
        )

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
