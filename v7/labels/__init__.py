"""
V7 Label Module — Mode-Specific Label Semantics.

Labels consume simulation truth (SimulationOutput) and produce
mode-specific supervised targets for classification and regression.

Exports:
    LabelSpec      — Frozen dataclass per mode.
    LABEL_SPECS    — Registry dict mapping TradingMode -> LabelSpec.
    TradingMode    — Re-exported from simulation.contracts.models.
"""

from v7.labels.contracts import LABEL_SPECS, LabelSpec
from simulation.contracts.models import TradingMode

__all__ = [
    "LABEL_SPECS",
    "LabelSpec",
    "TradingMode",
]
