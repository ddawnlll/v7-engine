"""
V7 Feature Specification — mode-specific feature window parameters.

Domain authority:
  - Defines FeatureSpec per mode (SWING, SCALP, AGGRESSIVE_SCALP)
  - Does NOT compute features (that is the canonical-state pipeline)
  - Feature windows match locked timeframe stacks per mode
  - Features are shared across modes; labels are mode-specific

See v7/docs/pipeline/features.md for the full design doc.
"""

from v7.features.spec import (
    FeatureGroup,
    FeatureSpec,
    MODE_FEATURE_SPECS,
    get_feature_spec,
    list_modes,
)

__all__ = [
    "FeatureGroup",
    "FeatureSpec",
    "MODE_FEATURE_SPECS",
    "get_feature_spec",
    "list_modes",
]
