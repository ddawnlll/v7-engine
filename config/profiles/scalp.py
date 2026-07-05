"""
SCALP profile — default SimulationProfile for scalping mode.

Tighter stops/targets, higher sensitivity to costs and MAE.
Defaults to NO_TRADE when ambiguous.

References: simulation/docs/profiles.md
"""

from simulation.contracts.models import SimulationProfile, TradingMode


def scalp_profile() -> SimulationProfile:
    """Return the default SCALP profile."""
    return SimulationProfile(
        profile_version="scalp_profile-1.0.0",
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
        mae_penalty_weight=2.0,
        cost_penalty_weight=2.0,
        time_penalty_weight=1.5,
    )
