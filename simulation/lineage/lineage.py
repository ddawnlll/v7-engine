"""
LineageBuilder — constructs SimulationLineage from SimulationInput + SimulationProfile.

Replaces the inline SimulationLineage(...) construction in engine.py.
"""

from __future__ import annotations

from simulation.contracts.models import SimulationInput, SimulationLineage, SimulationProfile
from simulation.lineage.version_registry import (
    ADAPTER_KIND,
    FEE_MODEL_VERSION,
    FUNDING_MODEL_VERSION,
    HORIZON_FAMILY_SUFFIX,
    SLIPPAGE_MODEL_VERSION,
    TIME_EXIT_FAMILY,
)


class LineageBuilder:
    """Builds a SimulationLineage from simulation input and profile.

    Extracts version and family fields from the input/profile pair and
    fills in hardcoded defaults from the version registry.
    """

    def __init__(self, input: SimulationInput, profile: SimulationProfile) -> None:
        self._input = input
        self._profile = profile

    def build(self) -> SimulationLineage:
        """Construct and return a fully-populated SimulationLineage."""
        profile = self._profile
        input = self._input

        return SimulationLineage(
            simulation_family_version=input.simulation_family_version,
            simulation_profile_version=profile.profile_version,
            cost_model_version=input.cost_model_version,
            fee_model_version=FEE_MODEL_VERSION,
            slippage_model_version=SLIPPAGE_MODEL_VERSION,
            funding_model_version=FUNDING_MODEL_VERSION,
            horizon_family=f"{profile.mode.value.lower()}{HORIZON_FAMILY_SUFFIX}",
            stop_family=profile.stop_method,
            target_family=profile.target_method,
            time_exit_family=TIME_EXIT_FAMILY,
            adapter_kind=ADAPTER_KIND,
        )
