"""
V7 Mode-Specific Thresholds.

Each mode has its own threshold dataclass defining the boundary between
acceptable and rejected trade candidates. Thresholds are LOCKED_INITIAL_BASELINE
for SWING and SCALP — recalibrate after first empirical WFV.

Domain authority:
  - Owns mode-specific threshold definitions
  - Does NOT own the policy evaluation logic (policy.py owns that)
  - Does NOT own promotion gates (gates/evaluator.py owns G0-G10)
"""

from v7.thresholds.scalp import SCALP_THRESHOLDS, ScalpThresholds, validate_scalp

__all__ = [
    "ScalpThresholds",
    "SCALP_THRESHOLDS",
    "validate_scalp",
]
