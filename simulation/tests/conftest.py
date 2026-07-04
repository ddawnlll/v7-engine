"""Shared profile fixtures for simulation tests."""

import pytest
from simulation.contracts.models import SimulationProfile, TradingMode


@pytest.fixture
def swing_profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="swing_profile-1.0.0",
        mode=TradingMode.SWING,
        primary_interval="4h",
        max_holding_bars=30,
        stop_multiplier=2.0,
        target_multiplier=2.5,
        ambiguity_margin_r=0.20,
        min_action_edge_r=0.35,
        no_trade_default=False,
        context_intervals=["1d", "1h"],
        refinement_intervals=["1h"],
        stop_method="atr_wide",
        target_method="atr_wide",
        mae_penalty_weight=1.0,
        cost_penalty_weight=1.0,
        time_penalty_weight=0.3,
    )


@pytest.fixture
def scalp_profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="scalp_profile-1.0.0",
        mode=TradingMode.SCALP,
        primary_interval="1h",
        max_holding_bars=12,
        stop_multiplier=1.5,
        target_multiplier=1.8,
        ambiguity_margin_r=0.10,
        min_action_edge_r=0.15,
        no_trade_default=False,
        context_intervals=["4h", "15m"],
        refinement_intervals=["15m"],
        stop_method="atr_wide",
        target_method="atr_wide",
        mae_penalty_weight=2.0,
        cost_penalty_weight=2.0,
        time_penalty_weight=1.5,
    )


@pytest.fixture
def aggressive_scalp_profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="aggressive_scalp_profile-1.0.0",
        mode=TradingMode.AGGRESSIVE_SCALP,
        primary_interval="15m",
        max_holding_bars=5,
        stop_multiplier=1.2,
        target_multiplier=1.2,
        ambiguity_margin_r=0.05,
        min_action_edge_r=0.08,
        no_trade_default=True,
        context_intervals=["1h", "5m"],
        refinement_intervals=["5m"],
        stop_method="atr_wide",
        target_method="atr_wide",
        mae_penalty_weight=3.0,
        cost_penalty_weight=3.0,
        time_penalty_weight=2.5,
    )
