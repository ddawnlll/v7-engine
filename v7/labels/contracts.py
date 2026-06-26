"""
Mode-specific label semantics contracts.

Each trading mode defines a LabelSpec that governs how simulation
outputs are converted into supervised targets — windows, edge
thresholds, and success criteria are all mode-parameterised.

Domain authority:
  - Labels consume SimulationOutput (simulation owns economic truth).
  - Labels produce mode-specific targets for AlphaForge model training.

Per-mode defaults are LOCKED_INITIAL_BASELINE — safe starting points
that will be recalibrated after first empirical evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

from simulation.contracts.models import TradingMode


@dataclass(frozen=True)
class LabelSpec:
    """Mode-specific label generation specification.

    Attributes:
        mode:           Trading mode this spec applies to.
        primary_interval:   Candle interval used as the label resolution.
        label_window:       Number of primary-interval bars the label
                            evaluates across (lookahead window).
        min_edge_r:         Minimum edge ratio (net R / gross R) required
                            for a directional action to be considered viable.
        min_net_r_for_success: Minimum net realized R for a trade to be
                            labelled a success.
        max_mae_r_for_success: Maximum adverse excursion (as a negative R)
                            allowed while still being labelled a success.
        ambiguity_margin_r: Gap in utility between best and second-best
                            action below which the label is ambiguous.
    """
    mode: TradingMode
    primary_interval: str
    label_window: int
    min_edge_r: float
    min_net_r_for_success: float
    max_mae_r_for_success: float
    ambiguity_margin_r: float


# ── Mode-Specific Label Specifications ──────────────────────────────────
#
# These are LOCKED_INITIAL_BASELINE per the project governance:
# safe starting points that will be recalibrated when empirical
# label-evaluation data becomes available.

LABEL_SPECS: dict[TradingMode, LabelSpec] = {
    TradingMode.SWING: LabelSpec(
        mode=TradingMode.SWING,
        primary_interval="4h",
        label_window=24,
        min_edge_r=0.25,
        min_net_r_for_success=0.75,
        max_mae_r_for_success=-0.60,
        ambiguity_margin_r=0.25,
    ),
    TradingMode.SCALP: LabelSpec(
        mode=TradingMode.SCALP,
        primary_interval="1h",
        label_window=48,
        min_edge_r=0.15,
        min_net_r_for_success=0.20,
        max_mae_r_for_success=-0.25,
        ambiguity_margin_r=0.10,
    ),
    TradingMode.AGGRESSIVE_SCALP: LabelSpec(
        mode=TradingMode.AGGRESSIVE_SCALP,
        primary_interval="15m",
        label_window=96,
        min_edge_r=0.10,
        min_net_r_for_success=0.10,
        max_mae_r_for_success=-0.10,
        ambiguity_margin_r=0.05,
    ),
}
