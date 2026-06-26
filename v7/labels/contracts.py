"""
LabelSpec — Mode-specific label configuration contracts.

Defines the label window, primary interval, edge thresholds, and
per-mode success criteria for converting SimulationOutput into
supervised learning targets.

Design authority: v7/docs/pipeline/labels.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Final


@dataclass(frozen=True)
class LabelSpec:
    """Mode-specific label generation configuration.

    Each mode has its own label window, primary interval, edge threshold,
    and success criteria reflecting the different time horizons and
    noise characteristics of SWING (slower, wider), SCALP (faster, tighter),
    and AGGRESSIVE_SCALP (very fast, micro-structure driven).
    """

    mode: str
    primary_interval: str
    label_window_bars: int
    min_edge_r: float
    min_net_r_for_success: float
    max_mae_r_for_success: float
    min_mfe_r_for_good_exit: float
    max_time_to_mfe_bars: int
    allow_no_trade_on_ambiguity: bool
    no_trade_default: bool

    def validate_edge_threshold(self) -> bool:
        """The min_edge_r must be strictly positive.

        A non-positive edge threshold would admit negative-expectancy
        trades, which defeats the purpose of a minimum edge gate.
        """
        return self.min_edge_r > 0.0

    def validate_label_window(self) -> bool:
        """The label window must be at least 1 bar.

        A zero-bar window has no forward information for labelling.
        """
        return self.label_window_bars >= 1


SUPPORTED_MODES: Final = ("SWING", "SCALP", "AGGRESSIVE_SCALP")

LABEL_SPECS: Final[Dict[str, LabelSpec]] = {
    "SWING": LabelSpec(
        mode="SWING",
        primary_interval="4h",
        label_window_bars=24,        # 4 days at 4h
        min_edge_r=0.25,
        min_net_r_for_success=0.75,
        max_mae_r_for_success=-0.60,
        min_mfe_r_for_good_exit=1.0,
        max_time_to_mfe_bars=48,
        allow_no_trade_on_ambiguity=False,
        no_trade_default=False,
    ),
    "SCALP": LabelSpec(
        mode="SCALP",
        primary_interval="1h",
        label_window_bars=48,        # 2 days at 1h
        min_edge_r=0.15,
        min_net_r_for_success=0.20,
        max_mae_r_for_success=-0.25,
        min_mfe_r_for_good_exit=0.60,
        max_time_to_mfe_bars=12,
        allow_no_trade_on_ambiguity=True,
        no_trade_default=False,
    ),
    "AGGRESSIVE_SCALP": LabelSpec(
        mode="AGGRESSIVE_SCALP",
        primary_interval="15m",
        label_window_bars=96,        # 24 hours at 15m
        min_edge_r=0.10,
        min_net_r_for_success=0.10,
        max_mae_r_for_success=-0.10,
        min_mfe_r_for_good_exit=0.30,
        max_time_to_mfe_bars=3,
        allow_no_trade_on_ambiguity=True,
        no_trade_default=True,
    ),
}


def get_label_spec(mode: str) -> LabelSpec:
    """Return the LabelSpec for a given mode.

    Args:
        mode: One of "SWING", "SCALP", "AGGRESSIVE_SCALP".

    Returns:
        The frozen LabelSpec for the mode.

    Raises:
        KeyError: If the mode is not in SUPPORTED_MODES.
    """
    if mode not in LABEL_SPECS:
        raise KeyError(
            f"Unknown mode '{mode}'. Supported modes: {SUPPORTED_MODES}"
        )
    return LABEL_SPECS[mode]
