"""Deterministic profile registry for simulation engine.

Usage:
    from simulation.profile_registry import get_profile, register_profile

    profile = get_profile("SCALP")
    profile = get_profile("SCALP", version="1.0.0")
"""

import hashlib
import json
from typing import Optional

from simulation.contracts.models import SimulationProfile, TradingMode


# ── In-memory registry ──────────────────────────────────────────────

_registry: dict[str, dict[str, SimulationProfile]] = {}
"""Nested dict: registry[mode][version] -> SimulationProfile."""


def _compute_profile_hash(profile: SimulationProfile) -> str:
    """Deterministic SHA-256 hash of profile fields."""
    raw = {
        "profile_version": profile.profile_version,
        "mode": profile.mode.value if hasattr(profile.mode, "value") else str(profile.mode),
        "primary_interval": profile.primary_interval,
        "max_holding_bars": profile.max_holding_bars,
        "stop_multiplier": profile.stop_multiplier,
        "target_multiplier": profile.target_multiplier,
        "ambiguity_margin_r": profile.ambiguity_margin_r,
        "min_action_edge_r": profile.min_action_edge_r,
        "no_trade_default": profile.no_trade_default,
        "context_intervals": sorted(profile.context_intervals),
        "refinement_intervals": sorted(profile.refinement_intervals),
        "stop_method": profile.stop_method,
        "target_method": profile.target_method,
        "mae_penalty_weight": profile.mae_penalty_weight,
        "cost_penalty_weight": profile.cost_penalty_weight,
        "time_penalty_weight": profile.time_penalty_weight,
        "funding_rate": profile.funding_rate,
        "execution_mode": profile.execution_mode,
        "maker_fill_probability": profile.maker_fill_probability,
    }
    digest = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()[:16]
    return digest


def register_profile(profile: SimulationProfile) -> str:
    """Register a canonical profile and return its hash.

    Args:
        profile: Fully populated SimulationProfile.

    Returns:
        16-char profile hash (first 16 hex chars of SHA-256).

    Raises:
        ValueError: If profile already registered with different params.
    """
    mode_key = profile.mode.value if hasattr(profile.mode, "value") else str(profile.mode)
    version = profile.profile_version
    profile_hash = _compute_profile_hash(profile)

    if mode_key not in _registry:
        _registry[mode_key] = {}

    if version in _registry[mode_key]:
        existing_hash = _compute_profile_hash(_registry[mode_key][version])
        if existing_hash != profile_hash:
            raise ValueError(
                f"Profile conflict: {mode_key} v{version} already registered "
                f"with different parameters (hash={existing_hash}, new={profile_hash})"
            )

    _registry[mode_key][version] = profile
    return profile_hash


def get_profile(mode: str, version: Optional[str] = None) -> SimulationProfile:
    """Look up a canonical SimulationProfile.

    Args:
        mode: Trading mode ('SWING', 'SCALP', 'AGGRESSIVE_SCALP').
        version: Profile version string. If None, returns the latest.

    Returns:
        Canonical SimulationProfile matching mode + version.

    Raises:
        ValueError: If mode is unknown or version not found.
    """
    mode_upper = mode.upper()
    if mode_upper not in _registry:
        raise ValueError(
            f"Unknown profile mode: '{mode_upper}'. "
            f"Registered modes: {sorted(_registry.keys())}"
        )

    if version is not None:
        if version not in _registry[mode_upper]:
            raise ValueError(
                f"Unknown profile version for '{mode_upper}': '{version}'. "
                f"Available: {sorted(_registry[mode_upper].keys())}"
            )
        return _registry[mode_upper][version]

    # Return latest version (semver string comparison)
    versions = sorted(_registry[mode_upper].keys(), reverse=True)
    return _registry[mode_upper][versions[0]]


def list_profiles() -> dict[str, list[str]]:
    """List all registered profiles by mode.

    Returns:
        Dict of mode -> list of version strings.
    """
    return {mode: sorted(versions.keys()) for mode, versions in _registry.items()}


def profile_exists(mode: str, version: Optional[str] = None) -> bool:
    """Check if a profile is registered."""
    mode_upper = mode.upper()
    if mode_upper not in _registry:
        return False
    if version is None:
        return True
    return version in _registry[mode_upper]


# ── Bootstrap canonical profiles ────────────────────────────────────
# These match the authoritative config in configs/profiles/*.yaml and
# simulation/docs/profiles.md. LOCKED_INITIAL_BASELINE.

_SWING_V1 = SimulationProfile(
    profile_version="1.0.0",
    mode=TradingMode.SWING,
    primary_interval="4h",
    max_holding_bars=24,
    stop_multiplier=2.0,
    target_multiplier=3.0,
    ambiguity_margin_r=0.15,
    min_action_edge_r=0.20,
    no_trade_default=False,
    context_intervals=["1d"],
    refinement_intervals=["1h"],
    stop_method="atr_wide",
    target_method="atr_wide",
    mae_penalty_weight=1.0,
    cost_penalty_weight=1.0,
    time_penalty_weight=0.3,
)

_SCALP_V1 = SimulationProfile(
    profile_version="1.0.0",
    mode=TradingMode.SCALP,
    primary_interval="1h",
    max_holding_bars=12,
    stop_multiplier=1.75,
    target_multiplier=1.75,
    ambiguity_margin_r=0.10,
    min_action_edge_r=0.15,
    no_trade_default=True,
    context_intervals=["4h", "15m"],
    refinement_intervals=["15m"],
    stop_method="atr_medium",
    target_method="atr_medium",
    mae_penalty_weight=1.0,
    cost_penalty_weight=1.0,
    time_penalty_weight=0.3,
)

_AGGRESSIVE_SCALP_V1 = SimulationProfile(
    profile_version="1.0.0",
    mode=TradingMode.AGGRESSIVE_SCALP,
    primary_interval="15m",
    max_holding_bars=5,
    stop_multiplier=1.25,
    target_multiplier=1.25,
    ambiguity_margin_r=0.08,
    min_action_edge_r=0.10,
    no_trade_default=True,
    context_intervals=["1h", "5m"],
    refinement_intervals=["5m"],
    stop_method="atr_tight",
    target_method="atr_tight",
    mae_penalty_weight=1.2,
    cost_penalty_weight=1.0,
    time_penalty_weight=0.3,
)

# Register and export hashes
SWING_V1_HASH = register_profile(_SWING_V1)
SCALP_V1_HASH = register_profile(_SCALP_V1)

# Asymmetric exit profile (Phase 1 oracle feasibility check, 2026-07-15).
# stop_multiplier=1.75 (unchanged), target_multiplier=0.60 (asymmetric).
# 0.05R expectancy requires ~76.6% win rate at this geometry.
# Oracle win rate on 5 canonical symbols: 76.6% (barely feasible at breakeven).
# EXPERIMENTAL — not locked, not canonical. Owner decision to promote.
_SCALP_ASYMMETRIC_V1 = SimulationProfile(
    profile_version="1.1.0-exp-asym-06",
    mode=TradingMode.SCALP,
    primary_interval=_SCALP_V1.primary_interval,
    max_holding_bars=_SCALP_V1.max_holding_bars,
    stop_multiplier=_SCALP_V1.stop_multiplier,      # 1.75 (unchanged)
    target_multiplier=0.60,                           # asymmetric: 1.75:0.60
    ambiguity_margin_r=_SCALP_V1.ambiguity_margin_r,
    min_action_edge_r=_SCALP_V1.min_action_edge_r,
    no_trade_default=_SCALP_V1.no_trade_default,
    context_intervals=_SCALP_V1.context_intervals,
    refinement_intervals=_SCALP_V1.refinement_intervals,
    stop_method=_SCALP_V1.stop_method,
    target_method=_SCALP_V1.target_method,
    mae_penalty_weight=_SCALP_V1.mae_penalty_weight,
    cost_penalty_weight=_SCALP_V1.cost_penalty_weight,
    time_penalty_weight=_SCALP_V1.time_penalty_weight,
)
SCALP_ASYMMETRIC_HASH = register_profile(_SCALP_ASYMMETRIC_V1)

AGGRESSIVE_SCALP_V1_HASH = register_profile(_AGGRESSIVE_SCALP_V1)
