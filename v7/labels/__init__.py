"""
V7 Labels — Mode-specific label semantics.

Converts SimulationOutput into supervised targets (classification + regression)
parameterized per trading mode (SWING | SCALP | AGGRESSIVE_SCALP).

Design authority: v7/docs/pipeline/labels.md
"""

from v7.labels.contracts import (
    LabelSpec,
    LABEL_SPECS,
    get_label_spec,
    SUPPORTED_MODES,
)

__all__ = [
    "LabelSpec",
    "LABEL_SPECS",
    "get_label_spec",
    "SUPPORTED_MODES",
]
