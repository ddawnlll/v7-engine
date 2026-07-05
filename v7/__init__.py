"""
V7 Policy Acceptance Engine.

Domain authority:
  - Owns final trade decisions (policy acceptance)
  - Does NOT invent alpha (AlphaForge owns discovery)
  - Does NOT own economic truth (Simulation owns cost/horizon/exit semantics)
  - Observes contracts defined in contracts/schemas/

Modes (priority order per v7/docs/v7_mode_centric_architecture.md):
  - SCALP:           PRIMARY business/research, HOLD (empirical evidence required)
  - AGGRESSIVE_SCALP: PRIMARY business/research, LOCKED_INITIAL_BASELINE (Issue #36)
  - SWING:           SECONDARY_BASELINE, LOCKED_INITIAL_BASELINE

Architecture:
  AnalysisRequest -> builder -> router -> policy -> portfolio -> risk -> DecisionEvent
"""

__version__ = "0.2.0"

from v7.portfolio import PortfolioManager, PortfolioResult
from v7.risk import RiskManager, RiskResult

__all__ = [
    "PortfolioManager",
    "PortfolioResult",
    "RiskManager",
    "RiskResult",
]
