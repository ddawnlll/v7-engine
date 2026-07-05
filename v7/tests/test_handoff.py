"""Tests for v7.handoff — HandoffAcceptor and handoff acceptance workflow."""

import json
from pathlib import Path

import pytest

from v7.handoff import (
    HANDOFF_REJECTION_RULES,
    HandoffAcceptanceRecord,
    HandoffAcceptor,
)

# ── Helpers ─────────────────────────────────────────────────────────────────────

_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "contracts"
    / "fixtures"
    / "alphaforge"
    / "v7_handoff_package_minimal.json"
)


def _load_fixture() -> dict:
    with open(_FIXTURE_PATH) as fh:
        return json.load(fh)


class TestHandoffAcceptor:
    """Test HandoffAcceptor — validation, gating, acceptance, rejection."""

    # ── validate_contract ──────────────────────────────────────────────────

    def test_validate_contract_valid_fixture(self):
        """A valid handoff package fixture should pass schema validation."""
        acceptor = HandoffAcceptor()
        package = _load_fixture()
        errors = acceptor.validate_contract(package)
        assert errors == [], f"Schema validation failed: {errors}"

    def test_validate_contract_missing_required_field(self):
        """A package missing a required field should produce validation errors."""
        acceptor = HandoffAcceptor()
        package = _load_fixture()
        del package["mode"]
        errors = acceptor.validate_contract(package)
        assert len(errors) > 0

    def test_validate_contract_invalid_mode(self):
        """A package with an invalid mode enum should fail validation."""
        acceptor = HandoffAcceptor()
        package = _load_fixture()
        package["mode"] = "INVALID_MODE"
        errors = acceptor.validate_contract(package)
        assert len(errors) > 0

    def test_validate_contract_invalid_recommended_status(self):
        """A package with an invalid recommended_status enum should fail."""
        acceptor = HandoffAcceptor()
        package = _load_fixture()
        package["recommended_status"] = "INVALID_STATUS"
        errors = acceptor.validate_contract(package)
        assert len(errors) > 0

    def test_validate_contract_empty_package(self):
        """An empty package should produce validation errors."""
        acceptor = HandoffAcceptor()
        errors = acceptor.validate_contract({})
        assert len(errors) > 0

    def test_validate_contract_schema_cached(self):
        """The schema should be cached after first load."""
        acceptor = HandoffAcceptor()
        assert acceptor._schema is None
        _ = acceptor.validate_contract(_load_fixture())
        assert acceptor._schema is not None

    # ── run_gates ──────────────────────────────────────────────────────────

    def test_run_gates_returns_g0_g6(self):
        """run_gates should return G0-G6 gate results."""
        acceptor = HandoffAcceptor()
        package = _load_fixture()
        result = acceptor.run_gates(package)

        assert "gates" in result
        assert "summary" in result

        gates = result["gates"]
        # G0-G6 should be present
        for gid in [f"G{i}" for i in range(7)]:
            assert gid in gates, f"Missing gate {gid}"
        # G7-G10 should also be present (evaluate_candidate runs all)
        assert "G7" in gates
        assert "G8" in gates
        assert "G9" in gates
        assert "G10" in gates

    def test_run_gates_summary_shape(self):
        """run_gates summary should have expected keys."""
        acceptor = HandoffAcceptor()
        package = _load_fixture()
        result = acceptor.run_gates(package)

        summary = result["summary"]
        assert "passed" in summary
        assert "overall_score" in summary
        assert "passed_gates" in summary
        assert "failed_gates" in summary
        assert "na_gates" in summary
        assert "recommendation" in summary

    def test_run_gates_each_gate_result_shape(self):
        """Each gate result should have the expected fields."""
        acceptor = HandoffAcceptor()
        package = _load_fixture()
        result = acceptor.run_gates(package)

        for gid, gate_dict in result["gates"].items():
            assert "gate_id" in gate_dict
            assert "name" in gate_dict
            assert "status" in gate_dict
            assert "score" in gate_dict
            assert "threshold" in gate_dict
            assert "detail" in gate_dict
            assert gate_dict["gate_id"] == gid

    def test_run_gates_swing_minimal_passes_g0(self):
        """G0 DOC_READY should pass for a valid SWING fixture."""
        acceptor = HandoffAcceptor()
        package = _load_fixture()
        # The candidate extraction now uses "MULTI" as symbol for handoff
        # packages, and handoff_package_id satisfies request_id.
        result = acceptor.run_gates(package)
        assert result["gates"]["G0"]["status"] == "PASS", (
            f"G0 detail: {result['gates']['G0']['detail']}"
        )

    def test_run_gates_fails_on_missing_request_id(self):
        """G0 should fail if request_id (handoff_package_id) is empty."""
        acceptor = HandoffAcceptor()
        package = _load_fixture()
        # Empty handoff_package_id -> empty request_id -> G0 FAIL
        package["handoff_package_id"] = ""
        result = acceptor.run_gates(package)
        assert result["gates"]["G0"]["status"] == "FAIL", (
            f"Expected G0 FAIL for empty handoff_package_id, got: "
            f"{result['gates']['G0']['status']}: {result['gates']['G0']['detail']}"
        )

    # ── accept_candidate ──────────────────────────────────────────────────

    def test_accept_candidate_returns_accepted_true(self):
        """accept_candidate should return a record with accepted=True."""
        acceptor = HandoffAcceptor()
        package = _load_fixture()
        gates = acceptor.run_gates(package)
        record = acceptor.accept_candidate(package, gates)

        assert record.accepted is True
        assert record.handoff_package_id == package["handoff_package_id"]
        assert record.mode == package["mode"]
        assert record.acceptance_id != ""
        assert record.accepted_at != ""

    def test_accept_candidate_rejection_fields_empty(self):
        """accept_candidate should have empty rejection fields."""
        acceptor = HandoffAcceptor()
        package = _load_fixture()
        gates = acceptor.run_gates(package)
        record = acceptor.accept_candidate(package, gates)

        assert record.rejection_rules_triggered == []
        assert record.rejection_reason == ""

    def test_accept_candidate_gates_summary(self):
        """accept_candidate should carry the gate summary."""
        acceptor = HandoffAcceptor()
        package = _load_fixture()
        gates = acceptor.run_gates(package)
        record = acceptor.accept_candidate(package, gates)

        assert record.gates_summary is not None
        assert "passed" in record.gates_summary
        assert "recommendation" in record.gates_summary

    def test_accept_candidate_creates_unique_ids(self):
        """Each acceptance should produce a unique acceptance_id."""
        acceptor = HandoffAcceptor()
        package = _load_fixture()
        gates = acceptor.run_gates(package)

        r1 = acceptor.accept_candidate(package, gates)
        r2 = acceptor.accept_candidate(package, gates)
        assert r1.acceptance_id != r2.acceptance_id

    # ── reject_candidate ──────────────────────────────────────────────────

    def test_reject_candidate_returns_accepted_false(self):
        """reject_candidate should return a record with accepted=False."""
        acceptor = HandoffAcceptor()
        package = _load_fixture()
        gates = acceptor.run_gates(package)
        record = acceptor.reject_candidate(package, gates, "Test rejection")

        assert record.accepted is False
        assert record.acceptance_id == ""
        assert record.accepted_at == ""

    def test_reject_candidate_has_reason(self):
        """reject_candidate should include the rejection reason."""
        acceptor = HandoffAcceptor()
        package = _load_fixture()
        gates = acceptor.run_gates(package)
        reason = "Edge destroyed under realistic cost assumptions"
        record = acceptor.reject_candidate(package, gates, reason)

        assert reason in record.rejection_reason
        assert reason in record.rejection_rules_triggered

    def test_reject_candidate_multiple_calls(self):
        """Multiple rejections should each produce separate records."""
        acceptor = HandoffAcceptor()
        package = _load_fixture()
        gates = acceptor.run_gates(package)

        r1 = acceptor.reject_candidate(package, gates, "reason_a")
        r2 = acceptor.reject_candidate(package, gates, "reason_b")
        assert r1.rejection_reason == "reason_a"
        assert r2.rejection_reason == "reason_b"

    # ── HandoffAcceptanceRecord ────────────────────────────────────────────

    def test_acceptance_record_is_immutable(self):
        """HandoffAcceptanceRecord should be immutable."""
        package = _load_fixture()
        record = HandoffAcceptanceRecord(
            accepted=True,
            handoff_package_id=package["handoff_package_id"],
            mode=package["mode"],
        )
        with pytest.raises(Exception):
            record.accepted = False  # type: ignore[misc]

    # ── Rejection rules constant ───────────────────────────────────────────

    def test_handoff_rejection_rules(self):
        """HANDOFF_REJECTION_RULES must contain the 12 canonical rules."""
        expected = [
            "missing_evidence",
            "incomplete_gate_mapping",
            "lineage_break",
            "checksum_mismatch",
            "validation_failure",
            "cost_vulnerability",
            "overfit_detected",
            "single_symbol_overfitting",
            "calibration_unusable",
            "funding_unknown",
            "blocked_scope_violation",
            "policy_conflict",
        ]
        assert HANDOFF_REJECTION_RULES == expected
        assert len(HANDOFF_REJECTION_RULES) == 12
