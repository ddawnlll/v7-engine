"""
Mode-specific simulation profile definitions.

Each module exports a factory function that returns a fully-configured
SimulationProfile for the given trading mode.

Usage:
    from config.profiles.swing import swing_profile
    profile = swing_profile()

See simulation/docs/profiles.md for parameter documentation.
"""

from config.profiles.aggressive_scalp import aggressive_scalp_profile
from config.profiles.scalp import scalp_profile
from config.profiles.swing import swing_profile

__all__ = [
    "aggressive_scalp_profile",
    "scalp_profile",
    "swing_profile",
]
