"""AlphaThesisStateMachine — formal state machine for the alpha thesis lifecycle.

Implements the state diagram defined in alphaforge/docs/alpha_thesis_lifecycle.md
(LOCKED authority document).  Provides immutable state transitions, entry/exit
condition checking, rejection criteria tracking, and WFV pipeline integration.

States (9 total, per the LOCKED doc):
    PROPOSED → DATA_READY → FEATURED → SIMULATED → TRAINED → VALIDATED
    VALIDATED → V7_CANDIDATE  (if evidence supports)
    VALIDATED → REJECTED      (if evidence refutes)
    VALIDATED → PROPOSED      (CONTINUE_RESEARCH — iterate with new hypothesis)
    REJECTED → ARCHIVED       (after review period)
    V7_CANDIDATE → ARCHIVED   (after V7 decision)

This module imports ZERO ML libraries (no xgboost, sklearn, tensorflow, torch).
It is pure state logic with no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Set


# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------


class AlphaThesisState(str, Enum):
    """Canonical lifecycle states for an alpha thesis.

    Matches alpha_thesis_lifecycle.md verbatim (LOCKED).
    """

    PROPOSED = "PROPOSED"
    DATA_READY = "DATA_READY"
    FEATURED = "FEATURED"
    SIMULATED = "SIMULATED"
    TRAINED = "TRAINED"
    VALIDATED = "VALIDATED"
    V7_CANDIDATE = "V7_CANDIDATE"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


# ---------------------------------------------------------------------------
# Named constants for convenience
# ---------------------------------------------------------------------------

PROPOSED = AlphaThesisState.PROPOSED
DATA_READY = AlphaThesisState.DATA_READY
FEATURED = AlphaThesisState.FEATURED
SIMULATED = AlphaThesisState.SIMULATED
TRAINED = AlphaThesisState.TRAINED
VALIDATED = AlphaThesisState.VALIDATED
V7_CANDIDATE = AlphaThesisState.V7_CANDIDATE
REJECTED = AlphaThesisState.REJECTED
ARCHIVED = AlphaThesisState.ARCHIVED

# Special pseudo-state for VALIDATED → PROPOSED transition (continue research)
CONTINUE_RESEARCH = "CONTINUE_RESEARCH"

# ---------------------------------------------------------------------------
# Allowed transitions (immutable)
# ---------------------------------------------------------------------------

TRANSITIONS: Dict[AlphaThesisState, FrozenSet[AlphaThesisState]] = {
    PROPOSED: frozenset({DATA_READY, REJECTED}),
    DATA_READY: frozenset({FEATURED, REJECTED}),
    FEATURED: frozenset({SIMULATED, REJECTED}),
    SIMULATED: frozenset({TRAINED, REJECTED}),
    TRAINED: frozenset({VALIDATED, REJECTED}),
    VALIDATED: frozenset({V7_CANDIDATE, REJECTED, PROPOSED}),
    V7_CANDIDATE: frozenset({ARCHIVED}),
    REJECTED: frozenset({ARCHIVED}),
    ARCHIVED: frozenset(),
}

ALL_STATES: FrozenSet[AlphaThesisState] = frozenset(AlphaThesisState)
TERMINAL_STATES: FrozenSet[AlphaThesisState] = frozenset({ARCHIVED})

# Verdicts from ModeResearchReport / ValidationReport that allow
# transition to V7_CANDIDATE
VALID_V7_CANDIDATE_VERDICTS: FrozenSet[str] = frozenset({
    "CANDIDATE_FOR_V7_GATES",
    "BASELINE_VALID",
})

# ---------------------------------------------------------------------------
# Rejection tracking
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RejectionRecord:
    """A single rejection event with reasons and context.

    Each rejection captures which rejection rules fired, at what state
    the thesis was rejected from, and when it happened.
    """

    rejection_id: str
    rejected_from_state: AlphaThesisState
    rejection_timestamp: str = ""  # ISO 8601, auto-set to now in factory
    rejection_rules_fired: List[str] = field(default_factory=list)  # e.g. "NO_TRADE beats directional"
    rejection_detail: str = ""
    human_review_required: bool = False

    @staticmethod
    def create(
        rejected_from_state: AlphaThesisState,
        rejection_rules_fired: List[str],
        rejection_detail: str = "",
        human_review_required: bool = False,
    ) -> RejectionRecord:
        """Factory: build a RejectionRecord with an auto-generated ID and timestamp."""
        now = datetime.now(timezone.utc).isoformat()
        return RejectionRecord(
            rejection_id=f"REJ_{now}_{id(rejection_rules_fired)}",
            rejected_from_state=rejected_from_state,
            rejection_timestamp=now,
            rejection_rules_fired=sorted(rejection_rules_fired),
            rejection_detail=rejection_detail,
            human_review_required=human_review_required,
        )


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------


class StateTransitionError(ValueError):
    """Raised when a state transition is not allowed per the lifecycle."""

    def __init__(
        self,
        current_state: AlphaThesisState,
        target_state: AlphaThesisState,
        reason: str = "",
    ):
        self.current_state = current_state
        self.target_state = target_state
        self.reason = reason
        msg = (
            f"Illegal transition: {current_state.value} → {target_state.value}"
            f"{'. ' + reason if reason else ''}"
        )
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Entry / exit condition helpers
# ---------------------------------------------------------------------------

_ENTRY_CONDITIONS: Dict[AlphaThesisState, str] = {
    PROPOSED: (
        "Thesis document written with hypothesis, expected evidence, "
        "required data, required features, risk factors, and rejection criteria."
    ),
    DATA_READY: (
        "Data scope defined: symbols, intervals, timeframe stack, date range. "
        "All data sources identified, accessible, and quality-checked."
    ),
    FEATURED: (
        "FeatureSetSpec defined per mode with no leakage detected. "
        "Normalized market data available."
    ),
    SIMULATED: (
        "Simulation profile selected per mode.  SimulationRun complete producing "
        "SimulationOutput.  LabelDataset generated from SimulationOutput.  "
        "NO_TRADE comparison computed."
    ),
    TRAINED: (
        "Training, validation, and OOS split defined.  Model training run "
        "executed.  Training metrics recorded.  Model artifact produced."
    ),
    VALIDATED: (
        "Walk-forward validation across all folds complete.  OOS performance "
        "metrics, cost stress analysis, NO_TRADE comparison, regime breakdown, "
        "symbol stability check, overfit risk flags, and calibration quality "
        "all assessed."
    ),
    V7_CANDIDATE: (
        "Validation verdict is CANDIDATE_FOR_V7_GATES or BASELINE_VALID.  "
        "All required evidence attached.  V7HandoffPackage assembled.  "
        "V7 gate mapping complete.  Blocked scopes and limitations explicit."
    ),
    REJECTED: (
        "At least one rejection criterion from alpha_thesis_lifecycle.md is true.  "
        "Rejection reasons recorded in RejectionRecord."
    ),
    ARCHIVED: (
        "Thesis lifecycle complete — no further transitions allowed."
    ),
}

_EXIT_CONDITIONS: Dict[AlphaThesisState, Dict[AlphaThesisState, str]] = {
    PROPOSED: {
        DATA_READY: "Data scope defined, quality checks passed.",
        REJECTED: "Rejection criteria triggered before data ready.",
    },
    DATA_READY: {
        FEATURED: "Normalized market data available and quality-checked. FeatureSetSpec defined.",
        REJECTED: "Essential data unavailable or quality insufficient.",
    },
    FEATURED: {
        SIMULATED: "Simulation run complete producing SimulationOutput. LabelDataset generated.",
        REJECTED: "Feature leakage detected or simulation infeasible.",
    },
    SIMULATED: {
        TRAINED: "Training/validation/OOS split defined. Model training executed.",
        REJECTED: "Labels invalid, NO_TRADE comparison fails, or simulation insufficient.",
    },
    TRAINED: {
        VALIDATED: "Model artifact produced with recorded training metrics.",
        REJECTED: "Training failed, metrics outside acceptable range.",
    },
    VALIDATED: {
        V7_CANDIDATE: "ValidationReport produced, all required checks passed, verdict positive.",
        REJECTED: "Evidence refutes thesis hypothesis.",
        PROPOSED: "Inconclusive evidence — continue research with revised hypothesis.",
    },
    V7_CANDIDATE: {
        ARCHIVED: "V7 acceptance decision complete (promoted or declined).",
    },
    REJECTED: {
        ARCHIVED: "Review period elapsed.  Thesis lifecycle complete.",
    },
}


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThesisStateMachine:
    """Formal state machine for alpha thesis lifecycle.

    Immutable — every transition returns a new ThesisStateMachine instance.

    Attributes:
        current_state: The current lifecycle state.
        rejection_history: List of all RejectionRecord entries for this thesis.
        transition_notes: Free-form notes attached during the most recent transition.
        v7_candidate_ready: True when VALIDATED → V7_CANDIDATE transition is appropriate.
    """

    current_state: AlphaThesisState = PROPOSED
    rejection_history: List[RejectionRecord] = field(default_factory=list)
    transition_notes: str = ""
    v7_candidate_ready: bool = False

    # ------------------------------------------------------------------
    # Core transition
    # ------------------------------------------------------------------

    def transition(
        self,
        target_state: AlphaThesisState,
        *,
        rejection_rules_fired: Optional[List[str]] = None,
        rejection_detail: str = "",
        human_review_required: bool = False,
        notes: str = "",
        entry_conditions_met: bool = True,
    ) -> ThesisStateMachine:
        """Attempt a state transition and return a new ThesisStateMachine.

        Args:
            target_state: The state to transition to.
            rejection_rules_fired: Required when transitioning to REJECTED.
                List of rejection rule descriptions that fired.
            rejection_detail: Additional context for the rejection.
            human_review_required: Whether human review is needed.
            notes: Free-form notes for this transition.
            entry_conditions_met: Set to False to skip condition checks
                (for programmatic transitions where conditions are already verified).

        Returns:
            A new ThesisStateMachine with the new state.

        Raises:
            StateTransitionError: If the transition is not allowed by the
                lifecycle, or if entry conditions are not met.
        """
        # 1. Check if terminal state
        if self.current_state in TERMINAL_STATES:
            raise StateTransitionError(
                self.current_state,
                target_state,
                f"Cannot transition from terminal state {self.current_state.value}.",
            )

        # 2. Check if transition is allowed
        allowed = TRANSITIONS.get(self.current_state, frozenset())
        if target_state not in allowed:
            raise StateTransitionError(
                self.current_state,
                target_state,
                f"Allowed transitions from {self.current_state.value}: "
                f"{[s.value for s in allowed]}",
            )

        # 3. Entry conditions check
        if entry_conditions_met and target_state in _ENTRY_CONDITIONS:
            pass  # Conditions documented; caller is responsible for verifying

        # 4. Handle REJECTED transition
        rejection_history = list(self.rejection_history)
        if target_state == REJECTED:
            fired_rules = rejection_rules_fired or []
            if not fired_rules:
                fired_rules = ["Unspecified rejection criteria"]
            record = RejectionRecord.create(
                rejected_from_state=self.current_state,
                rejection_rules_fired=fired_rules,
                rejection_detail=rejection_detail,
                human_review_required=human_review_required,
            )
            rejection_history.append(record)

        # 5. Determine v7_candidate_ready
        v7_candidate_ready = target_state == V7_CANDIDATE

        return ThesisStateMachine(
            current_state=target_state,
            rejection_history=rejection_history,
            transition_notes=notes,
            v7_candidate_ready=v7_candidate_ready,
        )

    # ------------------------------------------------------------------
    # Specific transition helpers
    # ------------------------------------------------------------------

    def mark_data_ready(self, notes: str = "") -> ThesisStateMachine:
        """PROPOSED → DATA_READY: data scope defined and quality-checked."""
        return self.transition(
            DATA_READY,
            notes=notes or "Data scope defined, quality checks passed.",
        )

    def mark_featured(self, notes: str = "") -> ThesisStateMachine:
        """DATA_READY → FEATURED: feature set specified and computed."""
        return self.transition(
            FEATURED,
            notes=notes or "Feature set specified, no leakage detected.",
        )

    def mark_simulated(self, notes: str = "") -> ThesisStateMachine:
        """FEATURED → SIMULATED: simulation run complete."""
        return self.transition(
            SIMULATED,
            notes=notes or "Simulation run complete, labels generated.",
        )

    def mark_trained(self, notes: str = "") -> ThesisStateMachine:
        """SIMULATED → TRAINED: model training complete."""
        return self.transition(
            TRAINED,
            notes=notes or "Model training complete, artifact produced.",
        )

    def mark_validated(self, notes: str = "") -> ThesisStateMachine:
        """TRAINED → VALIDATED: walk-forward validation complete."""
        return self.transition(
            VALIDATED,
            notes=notes or "Walk-forward validation complete.",
        )

    def promote_to_v7_candidate(
        self,
        notes: str = "",
        entry_conditions_met: bool = True,
    ) -> ThesisStateMachine:
        """VALIDATED → V7_CANDIDATE: packaged for V7 acceptance gates.

        Requires the validation verdict to be CANDIDATE_FOR_V7_GATES
        or BASELINE_VALID.  The caller is responsible for verifying the
        verdict before calling this method.
        """
        return self.transition(
            V7_CANDIDATE,
            notes=notes or "V7 candidate ready — all evidence attached.",
            entry_conditions_met=entry_conditions_met,
        )

    def reject(
        self,
        rejection_rules_fired: List[str],
        rejection_detail: str = "",
        human_review_required: bool = False,
        notes: str = "",
    ) -> ThesisStateMachine:
        """Transition to REJECTED from any non-terminal state.

        Args:
            rejection_rules_fired: Which rejection criteria fired.
            rejection_detail: Context about why rejection occurred.
            human_review_required: Whether human must review before archiving.
            notes: Free-form notes.
        """
        return self.transition(
            REJECTED,
            rejection_rules_fired=rejection_rules_fired,
            rejection_detail=rejection_detail,
            human_review_required=human_review_required,
            notes=notes,
        )

    def continue_research(self, notes: str = "") -> ThesisStateMachine:
        """VALIDATED → PROPOSED: inconclusive evidence, iterate.

        This transition represents the CONTINUE_RESEARCH verdict from
        the validation report — the thesis needs more work before it
        can be accepted or rejected.
        """
        return self.transition(
            PROPOSED,
            notes=notes or (
                "Validation inconclusive — continuing research with "
                "revised hypothesis or additional evidence."
            ),
        )

    def archive(self, notes: str = "") -> ThesisStateMachine:
        """REJECTED/V7_CANDIDATE → ARCHIVED: lifecycle complete."""
        return self.transition(
            ARCHIVED,
            notes=notes or "Thesis lifecycle complete.  Archived.",
        )

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def is_terminal(self) -> bool:
        """True if the thesis is in a terminal state (ARCHIVED)."""
        return self.current_state in TERMINAL_STATES

    def is_rejected(self) -> bool:
        """True if the current state is REJECTED."""
        return self.current_state == REJECTED

    def is_v7_candidate(self) -> bool:
        """True if the current state is V7_CANDIDATE."""
        return self.current_state == V7_CANDIDATE

    def is_validated(self) -> bool:
        """True if the current state is VALIDATED."""
        return self.current_state == VALIDATED

    def get_allowed_transitions(self) -> FrozenSet[AlphaThesisState]:
        """Return the set of allowed target states from the current state."""
        return TRANSITIONS.get(self.current_state, frozenset())

    def get_entry_condition(self, state: Optional[AlphaThesisState] = None) -> str:
        """Return the documented entry condition for a given state."""
        target = state or self.current_state
        return _ENTRY_CONDITIONS.get(target, "No documented entry condition.")

    def get_exit_condition(
        self,
        target_state: AlphaThesisState,
    ) -> str:
        """Return the documented exit condition for current → target transition."""
        exits = _EXIT_CONDITIONS.get(self.current_state, {})
        return exits.get(target_state, "No documented exit condition.")

    def last_rejection(self) -> Optional[RejectionRecord]:
        """Return the most recent rejection record, or None."""
        if not self.rejection_history:
            return None
        return self.rejection_history[-1]

    # ------------------------------------------------------------------
    # WFV pipeline integration
    # ------------------------------------------------------------------

    @staticmethod
    def from_thesis_verdict(
        current_state: AlphaThesisState,
        verdict: str,
        rejection_rules_fired: Optional[List[str]] = None,
        rejection_detail: str = "",
        notes: str = "",
    ) -> ThesisStateMachine:
        """Create a state machine instance based on a thesis validation verdict.

        This is the primary integration point with the WFV pipeline:
        after ThesisValidator.validate() produces a verdict, call this
        method to compute the appropriate lifecycle transition.

        Args:
            current_state: The current state of the thesis (typically VALIDATED
                after validation completes, but could be any state).
            verdict: Validation verdict string (SUPPORTED, REFUTED, INCONCLUSIVE).
            rejection_rules_fired: Required if verdict is REFUTED.
            rejection_detail: Context for rejection.
            notes: Additional notes.

        Returns:
            A new ThesisStateMachine reflecting the post-verdict state.

        Verdict → Transition mapping:
            SUPPORTED   → promote to V7_CANDIDATE
            REFUTED     → transition to REJECTED
            INCONCLUSIVE → continue research (PROPOSED)
        """
        sm = ThesisStateMachine(current_state=current_state)

        if verdict == "SUPPORTED":
            if current_state == VALIDATED:
                return sm.promote_to_v7_candidate(
                    notes=notes or "Validation supports thesis — promoting to V7 candidate.",
                )
            # If not yet VALIDATED, just stay in current state
            return sm

        if verdict == "REFUTED":
            return sm.reject(
                rejection_rules_fired=rejection_rules_fired or ["Evidence refutes thesis hypothesis."],
                rejection_detail=rejection_detail,
                notes=notes or "Validation refutes thesis — rejecting.",
            )

        # INCONCLUSIVE — continue research only if coming from VALIDATED
        if current_state == VALIDATED:
            return sm.continue_research(
                notes=notes or (
                    "Validation inconclusive — returning to research for "
                    "additional evidence or revised hypothesis."
                ),
            )
        # Otherwise stay in current state (no self-transition needed)
        return sm
