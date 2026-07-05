"""Alpha thesis lifecycle — state machine, transition rules, rejection tracking.

The lifecycle governs how an alpha thesis moves from proposal through research,
validation, and ultimately becomes a V7 candidate or is rejected.

Authority: AlphaForge owns the alpha thesis lifecycle.
See alphaforge/docs/alpha_thesis_lifecycle.md for the authoritative spec.
"""

from alphaforge.lifecycle.state_machine import (
    PROPOSED,
    DATA_READY,
    FEATURED,
    SIMULATED,
    TRAINED,
    VALIDATED,
    V7_CANDIDATE,
    REJECTED,
    ARCHIVED,
    CONTINUE_RESEARCH,
    TERMINAL_STATES,
    TRANSITIONS,
    ALL_STATES,
    VALID_V7_CANDIDATE_VERDICTS,
    AlphaThesisState,
    RejectionRecord,
    StateTransitionError,
    ThesisStateMachine,
)

__all__ = [
    "PROPOSED",
    "DATA_READY",
    "FEATURED",
    "SIMULATED",
    "TRAINED",
    "VALIDATED",
    "V7_CANDIDATE",
    "REJECTED",
    "ARCHIVED",
    "CONTINUE_RESEARCH",
    "TERMINAL_STATES",
    "TRANSITIONS",
    "ALL_STATES",
    "VALID_V7_CANDIDATE_VERDICTS",
    "AlphaThesisState",
    "RejectionRecord",
    "StateTransitionError",
    "ThesisStateMachine",
]
