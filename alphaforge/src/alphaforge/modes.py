"""Frozen canonical mode profiles matching P0.8E timeframe alignment.

These are LOCKED — change only with explicit contradiction evidence.
"""

from dataclasses import dataclass
from typing import Dict, FrozenSet


@dataclass(frozen=True)
class ModeProfile:
    """Immutable mode profile with canonical timeframe stack."""

    name: str
    priority: str  # "PRIMARY" or "SECONDARY_BASELINE"
    primary_interval: str
    context_interval: str
    refinement_interval: str
    label_horizon_family: str
    threshold_status: str  # "HOLD" or "LOCKED_INITIAL_BASELINE"

    @property
    def timeframe_stack(self) -> Dict[str, str]:
        return {
            "primary": self.primary_interval,
            "context": self.context_interval,
            "refinement": self.refinement_interval,
        }

    def validate(self) -> None:
        """Assert this profile matches canonical expectations."""
        canonical = CANONICAL_PROFILES[self.name]
        assert self.primary_interval == canonical.primary_interval, (
            f"{self.name} primary interval mismatch: "
            f"{self.primary_interval} != {canonical.primary_interval}"
        )
        assert self.context_interval == canonical.context_interval, (
            f"{self.name} context interval mismatch"
        )
        assert self.refinement_interval == canonical.refinement_interval, (
            f"{self.name} refinement interval mismatch"
        )


SWING = ModeProfile(
    name="SWING",
    priority="SECONDARY_BASELINE",
    primary_interval="4h",
    context_interval="1d",
    refinement_interval="1h",
    label_horizon_family="swing_horizon",
    threshold_status="LOCKED_INITIAL_BASELINE",
)

SCALP = ModeProfile(
    name="SCALP",
    priority="PRIMARY",
    primary_interval="1h",
    context_interval="4h",
    refinement_interval="15m",
    label_horizon_family="scalp_horizon",
    threshold_status="HOLD",
)

AGGRESSIVE_SCALP = ModeProfile(
    name="AGGRESSIVE_SCALP",
    priority="PRIMARY",
    primary_interval="15m",
    context_interval="1h",
    refinement_interval="5m",
    label_horizon_family="aggressive_scalp_horizon",
    threshold_status="HOLD",
)

CANONICAL_PROFILES: Dict[str, ModeProfile] = {
    "SWING": SWING,
    "SCALP": SCALP,
    "AGGRESSIVE_SCALP": AGGRESSIVE_SCALP,
}

ALLOWED_MODES: FrozenSet[str] = frozenset(CANONICAL_PROFILES.keys())


def get_profile(mode: str) -> ModeProfile:
    """Return the frozen canonical profile for a mode name.

    Raises ConfigError if mode is unknown.
    """
    from .errors import ConfigError

    profile = CANONICAL_PROFILES.get(mode)
    if profile is None:
        raise ConfigError(
            key="mode",
            detail=f"Unknown mode '{mode}'. Allowed: {sorted(ALLOWED_MODES)}",
        )
    return profile


def validate_all_profiles() -> None:
    """Validate all canonical profiles against themselves."""
    for profile in CANONICAL_PROFILES.values():
        profile.validate()
