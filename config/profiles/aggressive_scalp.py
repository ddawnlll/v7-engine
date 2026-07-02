"""
AGGRESSIVE_SCALP profile — default SimulationProfile for aggressive scalping mode.

Very tight stops/targets, very high sensitivity to costs, MAE, and time.
Defaults to NO_TRADE when ambiguous — trades only with strong signals.

References: simulation/docs/profiles.md
"""

from simulation.contracts.models import SimulationProfile, TradingMode


def aggressive_scalp_profile() -> SimulationProfile:
    """Return the default AGGRESSIVE_SCALP profile."""
    return SimulationProfile(
        profile_version="aggressive_scalp_profile-1.0.0",
        mode=TradingMode.AGGRESSIVE_SCALP,
        primary_interval="15m",
        max_holding_bars=5,
        stop_multiplier=1.25,
        target_multiplier=1.25,
        ambiguity_margin_r=0.05,
        min_action_edge_r=0.08,
        no_trade_default=True,
        context_intervals=["1h", "5m"],
        refinement_intervals=["5m"],
        stop_method="atr_tight",
        target_method="atr_tight",
        mae_penalty_weight=3.0,
        cost_penalty_weight=3.0,
        time_penalty_weight=2.5,
    )
