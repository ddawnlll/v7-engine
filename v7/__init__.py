"""
V7 Policy Acceptance Engine.

Domain authority:
  - Owns final trade decisions (policy acceptance)
  - Does NOT invent alpha (AlphaForge owns discovery)
  - Does NOT own economic truth (Simulation owns cost/horizon/exit semantics)
  - Observes contracts defined in contracts/schemas/

Modes (priority order per v7/docs/v7_mode_centric_architecture.md):
  - SCALP:           PRIMARY business/research, LOCKED_INITIAL_BASELINE thresholds
  - AGGRESSIVE_SCALP: PRIMARY business/research, HOLD (empirical evidence required)
  - SWING:           SECONDARY_BASELINE, LOCKED_INITIAL_BASELINE

Subpackages:
  - thresholds/:    Mode-specific threshold dataclasses and validation
  - gates/:         G0-G10 promotion gate evaluators
  - policy_critic/: Offline IQL critic, replay buffer, regret/return composites

Architecture:
  AnalysisRequest -> builder -> router -> policy -> DecisionEvent
"""

from v7 import labels

__version__ = "0.1.0"
