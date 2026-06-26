"""
V7 Thresholds — mode-specific decision gates.

Each mode has its own threshold profile defining the promotion
and execution guardrails for policy acceptance.

Lock semantics:
  - LOCKED_INITIAL_BASELINE: safe starting point; recalibrate after first evidence
  - HOLD: empirical evidence required before lock
  - LOCKED: authoritative, do not change without explicit contradiction evidence

Thresholds are consumed by the policy acceptance layer (v7/policy.py)
and validated against evaluation evidence before promotion.
"""

from v7.thresholds.aggressive_scalp import AGGRESSIVE_SCALP_THRESHOLDS

__all__ = ["AGGRESSIVE_SCALP_THRESHOLDS"]
