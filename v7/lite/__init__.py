"""V7-Lite deterministic candidate admission.

This package owns the narrow V7-side check that a frozen AlphaForge candidate
may enter the V7 policy path.  It does not score a model, place an order, or
replace portfolio and runtime risk gates.
"""

from v7.lite.candidate_gate import (
    CandidateAdmission,
    FrozenCandidateManifest,
    evaluate_frozen_candidate,
    load_frozen_candidate_manifest,
)
from v7.lite.portfolio_replay import (
    PortfolioReplayResult,
    ReplaySignal,
    replay_shadow_portfolio,
)
from v7.lite.preregistration import (
    FrozenHoldoutPreregistration,
    load_frozen_holdout_preregistration,
)
from v7.lite.readiness_gate import (
    DataScope,
    GateEvidence,
    GateResult,
    ReadinessScore,
    compute_readiness,
    evaluate_gate,
    write_readiness_checkpoint,
)

__all__ = [
    "CandidateAdmission",
    "FrozenCandidateManifest",
    "evaluate_frozen_candidate",
    "load_frozen_candidate_manifest",
    "PortfolioReplayResult",
    "ReplaySignal",
    "replay_shadow_portfolio",
    "FrozenHoldoutPreregistration",
    "load_frozen_holdout_preregistration",
    "DataScope",
    "GateEvidence",
    "GateResult",
    "ReadinessScore",
    "compute_readiness",
    "evaluate_gate",
    "write_readiness_checkpoint",
]
