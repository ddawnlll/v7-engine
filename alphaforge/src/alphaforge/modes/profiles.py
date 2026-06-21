"""Canonical mode profiles — LOCKED.

Source of truth: simulation/docs/profiles.md and v7/docs/pipeline/evaluation.md.
P0.8E aligned timeframes to locked simulation profiles.

Do NOT change these values without an authority lock re-audit.
"""
from dataclasses import dataclass, field

from alphaforge.constants import (
    CANONICAL_MODES,
    MODE_PRIORITY_PRIMARY,
    MODE_PRIORITY_SECONDARY_BASELINE,
    REPORT_TYPE_PRIMARY,
    REPORT_TYPE_SECONDARY_BASELINE,
    PROMOTION_HOLD,
    PROMOTION_LOCKED_BASELINE,
)
from alphaforge.errors import ModeError


@dataclass(frozen=True)
class ModeProfile:
    """Immutable canonical mode profile.

    All fields are frozen — profiles cannot be mutated at runtime.
    """
    mode: str
    priority: str
    report_type: str
    primary_timeframe: str
    context_timeframe: str
    refinement_timeframe: str
    promotion_status: str
    description: str = ""

    @property
    def timeframe_stack(self) -> dict[str, str]:
        return {
            "primary": self.primary_timeframe,
            "context": self.context_timeframe,
            "refinement": self.refinement_timeframe,
        }

    @property
    def is_primary(self) -> bool:
        return self.priority == MODE_PRIORITY_PRIMARY

    @property
    def is_baseline(self) -> bool:
        return self.priority == MODE_PRIORITY_SECONDARY_BASELINE


# ── Locked profiles ─────────────────────────────────────────────────────
# P0.8E: timeframe stacks aligned to simulation/docs/profiles.md

_SCALP_PROFILE = ModeProfile(
    mode="SCALP",
    priority=MODE_PRIORITY_PRIMARY,
    report_type=REPORT_TYPE_PRIMARY,
    primary_timeframe="1h",
    context_timeframe="4h",
    refinement_timeframe="15m",
    promotion_status=PROMOTION_HOLD,
    description="SCALP — PRIMARY mode. 1h primary. HOLD until empirical evidence.",
)

_AGGRESSIVE_SCALP_PROFILE = ModeProfile(
    mode="AGGRESSIVE_SCALP",
    priority=MODE_PRIORITY_PRIMARY,
    report_type=REPORT_TYPE_PRIMARY,
    primary_timeframe="15m",
    context_timeframe="1h",
    refinement_timeframe="5m",
    promotion_status=PROMOTION_HOLD,
    description="AGGRESSIVE_SCALP — PRIMARY mode. 15m primary. HOLD until empirical evidence.",
)

_SWING_PROFILE = ModeProfile(
    mode="SWING",
    priority=MODE_PRIORITY_SECONDARY_BASELINE,
    report_type=REPORT_TYPE_SECONDARY_BASELINE,
    primary_timeframe="4h",
    context_timeframe="1d",
    refinement_timeframe="1h",
    promotion_status=PROMOTION_LOCKED_BASELINE,
    description="SWING — SECONDARY_BASELINE mode. 4h primary. LOCKED_INITIAL_BASELINE with recalibration pending.",
)

# Frozen lookup
_PROFILES: dict[str, ModeProfile] = {
    "SCALP": _SCALP_PROFILE,
    "AGGRESSIVE_SCALP": _AGGRESSIVE_SCALP_PROFILE,
    "SWING": _SWING_PROFILE,
}


def get_mode_profile(mode: str) -> ModeProfile:
    """Return the canonical ModeProfile for a mode.

    Args:
        mode: One of 'SCALP', 'AGGRESSIVE_SCALP', 'SWING'.

    Returns:
        Frozen ModeProfile.

    Raises:
        ModeError: Unknown mode.
    """
    if mode not in _PROFILES:
        raise ModeError(f"Unknown mode: '{mode}'. Valid modes: {sorted(_PROFILES.keys())}")
    return _PROFILES[mode]


def validate_mode(mode: str) -> bool:
    """Check if a mode string is a valid canonical mode.

    Returns:
        True if valid, False otherwise.
    """
    return mode in CANONICAL_MODES


def all_profiles() -> dict[str, ModeProfile]:
    """Return all canonical mode profiles.

    Returns:
        Dict of mode → ModeProfile (frozen).
    """
    return dict(_PROFILES)


def primary_modes() -> list[str]:
    """Return list of PRIMARY mode identifiers."""
    return [
        mode for mode, profile in _PROFILES.items()
        if profile.priority == MODE_PRIORITY_PRIMARY
    ]


def baseline_modes() -> list[str]:
    """Return list of SECONDARY_BASELINE mode identifiers."""
    return [
        mode for mode, profile in _PROFILES.items()
        if profile.priority == MODE_PRIORITY_SECONDARY_BASELINE
    ]
