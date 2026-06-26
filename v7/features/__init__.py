"""
V7 Feature Specification — mode-specific feature window parameters.

Features are produced from canonical state only. The same feature row feeds both
classification and regression heads across all modes.

Modes:
  SWING:            primary 4h, context 1d, refinement 1h
  SCALP:            primary 1h, context 4h, refinement 15m
  AGGRESSIVE_SCALP: primary 15m, context 1h, refinement 5m

Feature groups:
  returns, volatility, atr, momentum, volume, breakout
"""

from v7.features.spec import FeatureSpec, FeatureSpecPerMode, get_feature_spec

__all__ = ["FeatureSpec", "FeatureSpecPerMode", "get_feature_spec"]
