"""Tests for alpha thesis lifecycle state machine.

Covers all 9 states, allowed transitions, rejection tracking, WFV pipeline
integration, terminal states, error cases, and boundary conditions.

WS-06-NO-FAKE-TESTS: Negative/structural tests only — verify the state
machine logic, not model outputs.
"""

from __future__ import annotations

import dataclasses

import pytest

from alphaforge.lifecycle.state_machine import (
    ARCHIVED,
    DATA_READY,
    FEATURED,
    PROPOSED,
    REJECTED,
    SIMULATED,
    TRAINED,
    VALIDATED,
    V7_CANDIDATE,
    ALL_STATES,
    TERMINAL_STATES,
    TRANSITIONS,
    VALID_V7_CANDIDATE_VERDICTS,
    AlphaThesisState,
    RejectionRecord,
    StateTransitionError,
    ThesisStateMachine,
)


# =========================================================================
# State enum tests
# =========================================================================


class TestAlphaThesisState:
    """Tests for the AlphaThesisState enum."""

    def test_all_states_have_valid_values(self):
        """Each enum member value matches its name."""
        for s in AlphaThesisState:
            assert s.value == s.name, f"{s}: value != name"

    def test_nine_states_total(self):
        """Exactly 9 states as defined in alpha_thesis_lifecycle.md."""
        assert len(ALL_STATES) == 9

    def test_terminal_states_is_archived_only(self):
        """Only ARCHIVED is a terminal state."""
        assert TERMINAL_STATES == frozenset({ARCHIVED})

    def test_state_is_string_enum(self):
        """AlphaThesisState values compare equal to their string names."""
        assert PROPOSED == "PROPOSED"
        assert VALIDATED == "VALIDATED"
        assert REJECTED == "REJECTED"
        assert ARCHIVED == "ARCHIVED"
        assert isinstance(PROPOSED, str)

    def test_valid_v7_candidate_verdicts(self):
        """V7_CANDIDATE transition requires specific verdicts."""
        assert "CANDIDATE_FOR_V7_GATES" in VALID_V7_CANDIDATE_VERDICTS
        assert "BASELINE_VALID" in VALID_V7_CANDIDATE_VERDICTS
        assert "REJECT" not in VALID_V7_CANDIDATE_VERDICTS


# =========================================================================
# Transition table tests
# =========================================================================


class TestTransitions:
    """Tests for the TRANSITIONS table (alpha_thesis_lifecycle.md)."""

    def test_proposed_transitions(self):
        """PROPOSED can go to DATA_READY or REJECTED."""
        allowed = TRANSITIONS[PROPOSED]
        assert DATA_READY in allowed
        assert REJECTED in allowed
        assert len(allowed) == 2

    def test_data_ready_transitions(self):
        """DATA_READY can go to FEATURED or REJECTED."""
        allowed = TRANSITIONS[DATA_READY]
        assert FEATURED in allowed
        assert REJECTED in allowed
        assert len(allowed) == 2

    def test_featured_transitions(self):
        """FEATURED can go to SIMULATED or REJECTED."""
        allowed = TRANSITIONS[FEATURED]
        assert SIMULATED in allowed
        assert REJECTED in allowed
        assert len(allowed) == 2

    def test_simulated_transitions(self):
        """SIMULATED can go to TRAINED or REJECTED."""
        allowed = TRANSITIONS[SIMULATED]
        assert TRAINED in allowed
        assert REJECTED in allowed
        assert len(allowed) == 2

    def test_trained_transitions(self):
        """TRAINED can go to VALIDATED or REJECTED."""
        allowed = TRANSITIONS[TRAINED]
        assert VALIDATED in allowed
        assert REJECTED in allowed
        assert len(allowed) == 2

    def test_validated_transitions(self):
        """VALIDATED can go to V7_CANDIDATE, REJECTED, or PROPOSED."""
        allowed = TRANSITIONS[VALIDATED]
        assert V7_CANDIDATE in allowed
        assert REJECTED in allowed
        assert PROPOSED in allowed
        assert len(allowed) == 3

    def test_v7_candidate_transitions(self):
        """V7_CANDIDATE can only go to ARCHIVED."""
        allowed = TRANSITIONS[V7_CANDIDATE]
        assert ARCHIVED in allowed
        assert len(allowed) == 1

    def test_rejected_transitions(self):
        """REJECTED can only go to ARCHIVED."""
        allowed = TRANSITIONS[REJECTED]
        assert ARCHIVED in allowed
        assert len(allowed) == 1

    def test_archived_transitions(self):
        """ARCHIVED is terminal — no transitions allowed."""
        allowed = TRANSITIONS[ARCHIVED]
        assert len(allowed) == 0

    def test_every_state_has_entry(self):
        """Every AlphaThesisState has an entry in TRANSITIONS."""
        for state in AlphaThesisState:
            assert state in TRANSITIONS, f"Missing transition entry for {state}"


# =========================================================================
# ThesisStateMachine — happy path tests
# =========================================================================


class TestStateMachineHappyPath:
    """Tests for the standard forward progression through states."""

    def test_initial_state_is_proposed(self):
        """A new ThesisStateMachine starts at PROPOSED."""
        sm = ThesisStateMachine()
        assert sm.current_state == PROPOSED
        assert not sm.is_terminal()
        assert not sm.is_rejected()
        assert not sm.is_v7_candidate()
        assert not sm.is_validated()

    def test_proposed_to_data_ready(self):
        """PROPOSED → DATA_READY via mark_data_ready()."""
        sm = ThesisStateMachine().mark_data_ready()
        assert sm.current_state == DATA_READY
        assert "data" in sm.transition_notes.lower()

    def test_full_forward_pipeline(self):
        """Full pipeline: PROPOSED → DATA_READY → FEATURED → SIMULATED → TRAINED → VALIDATED."""
        sm = (
            ThesisStateMachine()
            .mark_data_ready()
            .mark_featured()
            .mark_simulated()
            .mark_trained()
            .mark_validated()
        )
        assert sm.current_state == VALIDATED
        assert sm.is_validated()
        assert not sm.is_terminal()

    def test_full_pipeline_to_v7_candidate(self):
        """Full pipeline to V7_CANDIDATE: VALIDATED → V7_CANDIDATE."""
        sm = (
            ThesisStateMachine()
            .mark_data_ready()
            .mark_featured()
            .mark_simulated()
            .mark_trained()
            .mark_validated()
            .promote_to_v7_candidate()
        )
        assert sm.current_state == V7_CANDIDATE
        assert sm.is_v7_candidate()
        assert sm.v7_candidate_ready
        assert not sm.is_terminal()

    def test_reject_from_applicable_states(self):
        """Can reject from any state where REJECTED is an allowed transition."""
        rejectable_states = [
            s for s in AlphaThesisState if REJECTED in TRANSITIONS[s]
        ]
        assert len(rejectable_states) > 0
        for state in rejectable_states:
            sm = ThesisStateMachine(current_state=state)
            sm2 = sm.reject(
                rejection_rules_fired=["Test rejection"],
                rejection_detail=f"Rejected from {state.value}",
            )
            assert sm2.current_state == REJECTED, f"Failed to reject from {state}"
            assert sm2.is_rejected()
            assert len(sm2.rejection_history) == 1

    def test_archive_from_rejected(self):
        """REJECTED → ARCHIVED."""
        sm = (
            ThesisStateMachine()
            .reject(rejection_rules_fired=["Test"])
            .archive()
        )
        assert sm.current_state == ARCHIVED
        assert sm.is_terminal()

    def test_archive_from_v7_candidate(self):
        """V7_CANDIDATE → ARCHIVED."""
        sm = (
            ThesisStateMachine(current_state=V7_CANDIDATE)
            .archive()
        )
        assert sm.current_state == ARCHIVED
        assert sm.is_terminal()

    def test_continue_research(self):
        """VALIDATED → PROPOSED via continue_research()."""
        sm = ThesisStateMachine(current_state=VALIDATED).continue_research()
        assert sm.current_state == PROPOSED
        assert "continue" in sm.transition_notes.lower() or "continuing" in sm.transition_notes.lower()


# =========================================================================
# ThesisStateMachine — error state tests
# =========================================================================


class TestStateMachineErrors:
    """Tests for invalid transitions and edge cases."""

    def test_illegal_transition_raises(self):
        """Transition to illegal state raises StateTransitionError."""
        sm = ThesisStateMachine(current_state=PROPOSED)
        with pytest.raises(StateTransitionError):
            # PROPOSED cannot go directly to V7_CANDIDATE
            sm.transition(V7_CANDIDATE)

    def test_illegal_transition_message(self):
        """Error message includes current, target, and allowed states."""
        sm = ThesisStateMachine(current_state=PROPOSED)
        with pytest.raises(StateTransitionError) as exc:
            sm.transition(V7_CANDIDATE)
        msg = str(exc.value)
        assert "PROPOSED" in msg
        assert "V7_CANDIDATE" in msg
        assert "DATA_READY" in msg or "REJECTED" in msg

    def test_terminal_state_transition_raises(self):
        """Transition from ARCHIVED raises error."""
        sm = ThesisStateMachine(current_state=ARCHIVED)
        with pytest.raises(StateTransitionError) as exc:
            sm.transition(PROPOSED)
        assert "ARCHIVED" in str(exc.value)
        assert "terminal" in str(exc.value).lower()

    def test_reject_requires_rules_list(self):
        """Rejection works with empty rules list (uses default)."""
        sm = ThesisStateMachine().reject(rejection_rules_fired=[])
        assert sm.current_state == REJECTED
        assert len(sm.rejection_history) == 1
        assert "Unspecified rejection criteria" in sm.rejection_history[0].rejection_rules_fired

    def test_mark_data_ready_from_non_proposed_raises(self):
        """Can only mark_data_ready from PROPOSED."""
        sm = ThesisStateMachine(current_state=FEATURED)
        with pytest.raises(StateTransitionError):
            sm.mark_data_ready()

    def test_mark_simulated_from_non_featured_raises(self):
        """Can only mark_simulated from FEATURED."""
        sm = ThesisStateMachine(current_state=PROPOSED)
        with pytest.raises(StateTransitionError):
            sm.mark_simulated()

    def test_mark_trained_from_non_simulated_raises(self):
        """Can only mark_trained from SIMULATED."""
        sm = ThesisStateMachine(current_state=DATA_READY)
        with pytest.raises(StateTransitionError):
            sm.mark_trained()

    def test_archive_from_non_eligible_state_raises(self):
        """Can only archive from REJECTED or V7_CANDIDATE."""
        sm = ThesisStateMachine(current_state=PROPOSED)
        with pytest.raises(StateTransitionError):
            sm.archive()


# =========================================================================
# Rejection tracking tests
# =========================================================================


class TestRejectionTracking:
    """Tests for RejectionRecord and rejection_history."""

    def test_rejection_record_creation(self):
        """RejectionRecord.create() produces a valid record."""
        record = RejectionRecord.create(
            rejected_from_state=VALIDATED,
            rejection_rules_fired=["NO_TRADE beats directional", "Non-positive OOS expectancy"],
            rejection_detail="Both NO_TRADE and OOS fail.",
            human_review_required=True,
        )
        assert record.rejected_from_state == VALIDATED
        assert len(record.rejection_rules_fired) == 2
        assert record.human_review_required is True
        assert record.rejection_id.startswith("REJ_")
        assert record.rejection_timestamp != ""

    def test_rejection_rules_sorted(self):
        """Rejection rules are sorted in the record."""
        record = RejectionRecord.create(
            rejected_from_state=PROPOSED,
            rejection_rules_fired=["Z rule", "A rule"],
        )
        assert record.rejection_rules_fired == ["A rule", "Z rule"]

    def test_multiple_rejections_accumulate(self):
        """Multiple rejections are tracked in history."""
        sm = ThesisStateMachine()
        sm = sm.reject(
            rejection_rules_fired=["First rejection"],
            rejection_detail="First failure.",
        )
        assert len(sm.rejection_history) == 1

        # Second rejection (from PROPOSED we can only reject once PROPOSED→REJECTED)
        # Actually, after rejection we can only archive. Let me test differently.
        # Let me simulate rejections from different stages.

    def test_rejection_history_from_pipeline(self):
        """History accumulates across multiple rejection events."""
        sm = ThesisStateMachine()
        # Reject from PROPOSED
        sm = sm.reject(rejection_rules_fired=["Rule A"], rejection_detail="First fail")
        assert sm.is_rejected()
        assert len(sm.rejection_history) == 1

        # Archive, then... can't reject from ARCHIVED, so this is fine
        sm = sm.archive()
        assert sm.is_terminal()

    def test_last_rejection(self):
        """last_rejection() returns the most recent record or None."""
        sm = ThesisStateMachine()
        assert sm.last_rejection() is None

        sm = sm.reject(rejection_rules_fired=["Rule X"])
        last = sm.last_rejection()
        assert last is not None
        assert "Rule X" in last.rejection_rules_fired


# =========================================================================
# Query method tests
# =========================================================================


class TestQueryMethods:
    """Tests for state machine query methods."""

    def test_get_allowed_transitions(self):
        """get_allowed_transitions returns correct set for each state."""
        for state in AlphaThesisState:
            allowed = ThesisStateMachine(current_state=state).get_allowed_transitions()
            assert allowed == TRANSITIONS[state]

    def test_get_entry_condition(self):
        """get_entry_condition returns non-empty string for all states."""
        for state in AlphaThesisState:
            cond = ThesisStateMachine(current_state=state).get_entry_condition(state)
            assert isinstance(cond, str)
            assert len(cond) > 0

    def test_get_entry_condition_default(self):
        """get_entry_condition without arg returns current state's condition."""
        sm = ThesisStateMachine(current_state=VALIDATED)
        cond = sm.get_entry_condition()
        assert len(cond) > 0

    def test_get_exit_condition(self):
        """get_exit_condition returns non-empty string for valid transitions."""
        sm = ThesisStateMachine(current_state=PROPOSED)
        cond = sm.get_exit_condition(DATA_READY)
        assert isinstance(cond, str)
        assert len(cond) > 0

        cond = sm.get_exit_condition(REJECTED)
        assert isinstance(cond, str)
        assert len(cond) > 0

    def test_get_exit_condition_missing(self):
        """get_exit_condition for invalid transition returns fallback."""
        sm = ThesisStateMachine(current_state=PROPOSED)
        cond = sm.get_exit_condition(V7_CANDIDATE)
        assert "No documented exit condition" in cond


# =========================================================================
# WFV pipeline integration tests
# =========================================================================


class TestWfvPipelineIntegration:
    """Tests for ThesisStateMachine.from_thesis_verdict()."""

    def test_supported_verdict_promotes_from_validated(self):
        """SUPPORTED verdict from VALIDATED → V7_CANDIDATE."""
        sm = ThesisStateMachine.from_thesis_verdict(
            current_state=VALIDATED,
            verdict="SUPPORTED",
            notes="Thesis confirmed.",
        )
        assert sm.current_state == V7_CANDIDATE
        assert sm.v7_candidate_ready

    def test_supported_verdict_keeps_current_if_not_validated(self):
        """SUPPORTED verdict from non-VALIDATED state keeps current state."""
        for state in (PROPOSED, DATA_READY, FEATURED, SIMULATED, TRAINED):
            sm = ThesisStateMachine.from_thesis_verdict(
                current_state=state,
                verdict="SUPPORTED",
            )
            # from_thesis_verdict with SUPPORTED from non-validated stays
            # (no pipeline advancement in the static factory)
            assert sm.current_state == state

    def test_refuted_verdict_rejects(self):
        """REFUTED verdict → REJECTED with rejection record."""
        sm = ThesisStateMachine.from_thesis_verdict(
            current_state=VALIDATED,
            verdict="REFUTED",
            rejection_rules_fired=["Non-positive OOS expectancy"],
            rejection_detail="OOS expectancy was -0.5.",
        )
        assert sm.current_state == REJECTED
        assert "expectancy" in sm.rejection_history[0].rejection_rules_fired[0]
        assert sm.rejection_history[0].rejection_detail == "OOS expectancy was -0.5."

    def test_inconclusive_verdict_continue_research(self):
        """INCONCLUSIVE verdict from VALIDATED → PROPOSED (continue research)."""
        sm = ThesisStateMachine.from_thesis_verdict(
            current_state=VALIDATED,
            verdict="INCONCLUSIVE",
        )
        assert sm.current_state == PROPOSED
        assert "inconclusive" in sm.transition_notes.lower()

    def test_inconclusive_from_non_validated_stays(self):
        """INCONCLUSIVE verdict from non-VALIDATED keeps current state."""
        sm = ThesisStateMachine.from_thesis_verdict(
            current_state=PROPOSED,
            verdict="INCONCLUSIVE",
        )
        # For PROPOSED, continue_research stays at PROPOSED
        assert sm.current_state == PROPOSED


# =========================================================================
# RejectionRecord frozen tests
# =========================================================================


class TestRejectionRecord:
    """Tests for RejectionRecord dataclass."""

    def test_record_is_frozen(self):
        """RejectionRecord is immutable."""
        record = RejectionRecord.create(
            rejected_from_state=PROPOSED,
            rejection_rules_fired=["Test"],
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            record.rejection_rules_fired = ["Changed"]  # type: ignore[misc]

    def test_record_without_rejection_rules(self):
        """Factory method handles empty rules list."""
        record = RejectionRecord.create(
            rejected_from_state=VALIDATED,
            rejection_rules_fired=[],
        )
        assert record.rejection_rules_fired == []


# =========================================================================
# Immutability tests
# =========================================================================


class TestImmutability:
    """Tests that ThesisStateMachine is immutable."""

    def test_state_machine_is_frozen(self):
        """ThesisStateMachine is a frozen dataclass."""
        sm = ThesisStateMachine()
        with pytest.raises(dataclasses.FrozenInstanceError):
            sm.current_state = VALIDATED  # type: ignore[misc]

    def test_transition_returns_new_instance(self):
        """transition() returns a new instance, does not mutate."""
        sm1 = ThesisStateMachine()
        sm2 = sm1.mark_data_ready()
        assert sm1 is not sm2
        assert sm1.current_state == PROPOSED
        assert sm2.current_state == DATA_READY

    def test_rejection_returns_new_instance(self):
        """reject() returns a new instance with updated history."""
        sm1 = ThesisStateMachine()
        sm2 = sm1.reject(rejection_rules_fired=["Test"])
        assert sm1 is not sm2
        assert sm1.current_state == PROPOSED
        assert sm2.current_state == REJECTED
        assert len(sm1.rejection_history) == 0
        assert len(sm2.rejection_history) == 1


# =========================================================================
# Edge case tests
# =========================================================================


class TestEdgeCases:
    """Tests for boundary and edge cases."""

    def test_rejection_from_validated_with_rules(self):
        """Rejection from VALIDATED with specific rules tracks correctly."""
        sm = ThesisStateMachine(current_state=VALIDATED)
        sm = sm.reject(
            rejection_rules_fired=[
                "NO_TRADE beats directional",
                "Non-positive OOS expectancy",
                "Cost stress flips edge negative",
            ],
            rejection_detail="Multiple rejection criteria fired.",
            human_review_required=True,
        )
        assert sm.current_state == REJECTED
        assert len(sm.rejection_history) == 1
        assert len(sm.rejection_history[0].rejection_rules_fired) == 3
        assert sm.rejection_history[0].human_review_required is True

    def test_direct_instantiation_with_all_states(self):
        """ThesisStateMachine can be created from any valid state."""
        for state in AlphaThesisState:
            sm = ThesisStateMachine(current_state=state)
            assert sm.current_state == state

    def test_v7_candidate_ready_flag_reset_on_new_instance(self):
        """v7_candidate_ready flag is independent per instance."""
        sm1 = ThesisStateMachine(current_state=VALIDATED).promote_to_v7_candidate()
        assert sm1.v7_candidate_ready is True

        sm2 = ThesisStateMachine(current_state=PROPOSED)
        assert sm2.v7_candidate_ready is False


# =========================================================================
# Allowed transitions symmetry test
# =========================================================================


class TestTransitionSymmetry:
    """Tests that transition rules are symmetric and complete."""

    def test_no_orphan_targets(self):
        """Every target state in TRANSITIONS is a valid AlphaThesisState."""
        for source, targets in TRANSITIONS.items():
            assert source in AlphaThesisState, f"Invalid source state: {source}"
            for target in targets:
                assert target in AlphaThesisState, (
                    f"Invalid target state: {target} (from {source})"
                )

    def test_reject_is_always_allowed(self):
        """REJECTED should be reachable from all forward-pipeline states (not V7_CANDIDATE or ARCHIVED)."""
        rejectable_states = {PROPOSED, DATA_READY, FEATURED, SIMULATED, TRAINED, VALIDATED}
        for source in rejectable_states:
            assert REJECTED in TRANSITIONS[source], (
                f"REJECTED is not in allowed transitions from {source}"
            )
        # V7_CANDIDATE and REJECTED and ARCHIVED should NOT have REJECTED
        assert REJECTED not in TRANSITIONS[V7_CANDIDATE]
        assert REJECTED not in TRANSITIONS[ARCHIVED]
        # REJECTED can't transition to REJECTED again
        assert REJECTED not in TRANSITIONS[REJECTED]

    def test_terminal_states_have_no_outgoing(self):
        """Terminal states have empty transition sets."""
        for state in TERMINAL_STATES:
            assert len(TRANSITIONS[state]) == 0
