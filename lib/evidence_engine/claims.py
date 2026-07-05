from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ClaimType(str, Enum):
    """Standard claim types shared by AlphaForge and V7."""

    ALPHA_HAS_EDGE = "ALPHA_HAS_EDGE"
    MODEL_BEATS_BASELINES = "MODEL_BEATS_BASELINES"
    FEATURE_FAMILY_HAS_SIGNAL = "FEATURE_FAMILY_HAS_SIGNAL"
    COST_AWARE_FILTER_IMPROVES_NET_R = "COST_AWARE_FILTER_IMPROVES_NET_R"
    TRAINING_CHANGE_ALLOWED = "TRAINING_CHANGE_ALLOWED"
    V7_RESEARCH_BACKTEST_READY = "V7_RESEARCH_BACKTEST_READY"
    V7_COST_STRESS_READY = "V7_COST_STRESS_READY"
    V7_SHADOW_READY = "V7_SHADOW_READY"
    V7_PAPER_READY = "V7_PAPER_READY"


class ClaimStatus(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"
    PASSED = "PASSED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"  # missing prerequisite evidence


@dataclass
class Claim:
    """A single evaluable claim that evidence can support or refute."""

    claim_id: str
    claim_type: ClaimType
    candidate_id: str
    mode: str
    status: ClaimStatus = ClaimStatus.NOT_EVALUATED
    evidence_refs: list[str] = field(default_factory=list)
    blocked_reason: str | None = None
