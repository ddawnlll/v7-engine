"""Tests for simulation.lineage — version registry and LineageBuilder."""

from __future__ import annotations

import pytest

from simulation.contracts.models import (
    FuturePath,
    SimulationInput,
    SimulationLineage,
    SimulationProfile,
    TradingMode,
)
from simulation.lineage import LineageBuilder
from simulation.lineage.version_registry import (
    ADAPTER_KIND,
    COST_MODEL_VERSION,
    FEE_MODEL_VERSION,
    FUNDING_MODEL_VERSION,
    HORIZON_FAMILY_SUFFIX,
    SIMULATION_FAMILY_VERSION,
    SLIPPAGE_MODEL_VERSION,
    TIME_EXIT_FAMILY,
    VERSION,
)


# ---------------------------------------------------------------------------
# Version registry tests
# ---------------------------------------------------------------------------


class TestVersionRegistry:
    def test_shared_version_component(self) -> None:
        assert VERSION == "1.0.0"

    def test_family_version_strings(self) -> None:
        """SIMULATION_FAMILY_VERSION and COST_MODEL_VERSION compose from VERSION."""
        assert SIMULATION_FAMILY_VERSION == "simfam-1.0.0"
        assert COST_MODEL_VERSION == "cost-1.0.0"

    def test_standalone_version_strings(self) -> None:
        assert FEE_MODEL_VERSION == "fee-1.0.0"
        assert SLIPPAGE_MODEL_VERSION == "slippage-1.0.0"
        assert FUNDING_MODEL_VERSION == "funding-1.0.0"

    def test_horizon_family_suffix(self) -> None:
        assert HORIZON_FAMILY_SUFFIX == "_horizon"

    def test_static_families(self) -> None:
        assert TIME_EXIT_FAMILY == "hold_then_exit"
        assert ADAPTER_KIND == "TRAINING"


# ---------------------------------------------------------------------------
# LineageBuilder tests
# ---------------------------------------------------------------------------


@pytest.fixture
def swing_profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="1.0.0",
        mode=TradingMode.SWING,
        primary_interval="4h",
        max_holding_bars=24,
        stop_multiplier=2.0,
        target_multiplier=3.0,
        ambiguity_margin_r=0.1,
        min_action_edge_r=0.05,
        no_trade_default=False,
    )


@pytest.fixture
def scalp_profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="1.0.0",
        mode=TradingMode.SCALP,
        primary_interval="1m",
        max_holding_bars=6,
        stop_multiplier=1.5,
        target_multiplier=2.0,
        ambiguity_margin_r=0.05,
        min_action_edge_r=0.03,
        no_trade_default=False,
    )


@pytest.fixture
def sim_input() -> SimulationInput:
    return SimulationInput(
        symbol="BTCUSDT",
        decision_timestamp="2025-01-01T00:00:00Z",
        mode=TradingMode.SWING,
        primary_interval="4h",
        entry_price=50000.0,
        atr=1000.0,
        future_path=FuturePath(candles=[]),
        profile=SimulationProfile(
            profile_version="1.0.0",
            mode=TradingMode.SWING,
            primary_interval="4h",
            max_holding_bars=24,
            stop_multiplier=2.0,
            target_multiplier=3.0,
            ambiguity_margin_r=0.1,
            min_action_edge_r=0.05,
            no_trade_default=False,
        ),
    )


class TestLineageBuilder:
    def test_build_returns_lineage_instance(self, sim_input: SimulationInput, swing_profile: SimulationProfile) -> None:
        lineage = LineageBuilder(input=sim_input, profile=swing_profile).build()
        assert isinstance(lineage, SimulationLineage)

    def test_build_default_values(self, sim_input: SimulationInput, swing_profile: SimulationProfile) -> None:
        """All hardcoded version strings match the registry constants."""
        lineage = LineageBuilder(input=sim_input, profile=swing_profile).build()

        assert lineage.simulation_family_version == SIMULATION_FAMILY_VERSION
        assert lineage.simulation_profile_version == swing_profile.profile_version
        assert lineage.cost_model_version == COST_MODEL_VERSION
        assert lineage.fee_model_version == FEE_MODEL_VERSION
        assert lineage.slippage_model_version == SLIPPAGE_MODEL_VERSION
        assert lineage.funding_model_version == FUNDING_MODEL_VERSION
        assert lineage.time_exit_family == TIME_EXIT_FAMILY
        assert lineage.adapter_kind == ADAPTER_KIND

    def test_horizon_family_swing(self, sim_input: SimulationInput, swing_profile: SimulationProfile) -> None:
        lineage = LineageBuilder(input=sim_input, profile=swing_profile).build()
        assert lineage.horizon_family == "swing_horizon"

    def test_horizon_family_scalp(self, sim_input: SimulationInput, scalp_profile: SimulationProfile) -> None:
        lineage = LineageBuilder(input=sim_input, profile=scalp_profile).build()
        assert lineage.horizon_family == "scalp_horizon"

    def test_build_values_match_old_inline_construction(
        self, sim_input: SimulationInput, swing_profile: SimulationProfile
    ) -> None:
        """LineageBuilder produces the same values as the previous inline code."""
        builder_lineage = LineageBuilder(input=sim_input, profile=swing_profile).build()

        # Exactly replicate the old inline construction (engine.py lines 263-275)
        inline_lineage = SimulationLineage(
            simulation_family_version=sim_input.simulation_family_version,
            simulation_profile_version=swing_profile.profile_version,
            cost_model_version=sim_input.cost_model_version,
            fee_model_version="fee-1.0.0",
            slippage_model_version="slippage-1.0.0",
            funding_model_version="funding-1.0.0",
            horizon_family=f"{swing_profile.mode.value.lower()}_horizon",
            stop_family=swing_profile.stop_method,
            target_family=swing_profile.target_method,
            time_exit_family="hold_then_exit",
            adapter_kind="TRAINING",
        )

        assert builder_lineage == inline_lineage
