"""
Profile resolver — maps TradingMode to a SimulationProfile instance.

Extracted from engine.py (Sim T4). Provides profile lookup by mode,
allowing the simulation engine to resolve the correct profile without
knowing about profile definitions directly.
"""

from __future__ import annotations

from simulation.contracts.models import SimulationProfile, TradingMode

# Import profile factory functions
from config.profiles.aggressive_scalp import aggressive_scalp_profile
from config.profiles.scalp import scalp_profile
from config.profiles.swing import swing_profile

# Mode-to-profile factory mapping
_PROFILE_FACTORIES: dict[TradingMode, callable] = {
    TradingMode.SWING: swing_profile,
    TradingMode.SCALP: scalp_profile,
    TradingMode.AGGRESSIVE_SCALP: aggressive_scalp_profile,
}


def resolve_profile(mode: TradingMode) -> SimulationProfile:
    """Return the default SimulationProfile for the given trading mode.

    Args:
        mode: TradingMode enum value.

    Returns:
        SimulationProfile configured for the mode.

    Raises:
        ValueError: If mode is unknown or unsupported.
    """
    factory = _PROFILE_FACTORIES.get(mode)
    if factory is None:
        raise ValueError(f"Unknown or unsupported trading mode: {mode}")
    return factory()
