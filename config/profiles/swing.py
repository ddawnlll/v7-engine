"""
SWING profile — default SimulationProfile for swing trading mode.

Baseline control profile used to validate the simulation architecture.
Conservative stop/target multipliers for 4h candles.

References: simulation/docs/profiles.md
"""

from simulation.contracts.models import SimulationProfile, TradingMode


def swing_profile() -> SimulationProfile:
    """Return the default SWING profile."""
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
