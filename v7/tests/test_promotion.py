"""Tests for v7.promotion — V7PromotionEngine and promotion pipeline."""

import json
from pathlib import Path

import pytest

from v7.promotion import (
    POST_ACCEPTANCE_GATES,
    PRE_ACCEPTANCE_GATES,
    PromotionResult,
    V7PromotionEngine,
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


def _strong_context() -> dict:
    """Return gate evaluation context that passes all pre-acceptance gates."""
    return {
        "expectancy_r": 1.2,       # G2: SWING threshold is 0.35
        "expected_r_net": 0.90,     # G3: must be > 0
        "ece": 0.03,                # G6: threshold is 0.10
        "g1_research_backtest_pass": True,
    }


def _promotable_package() -> dict:
    """Return a fixture with enriched context to pass pre-acceptance gates."""
    pkg = _load_fixture()
    pkg["handoff_package_id"] = "v7hp-promotable-001"
    pkg["mode"] = "SWING"
    return pkg


def _weak_package() -> dict:
    """Return a fixture that will fail G2 (low expectancy R)."""
    pkg = _load_fixture()
    pkg["handoff_package_id"] = "v7hp-weak-001"
    pkg["mode"] = "SWING"
    return pkg


class TestV7PromotionEngine:
    """Test V7PromotionEngine — full promotion pipeline."""

    # ── promote_from_alphaforge ────────────────────────────────────────────

    def test_promote_from_alphaforge_returns_promotion_result(self):
        """promote_from_alphaforge should return a PromotionResult."""
        engine = V7PromotionEngine()
        package = _promotable_package()
        result = engine.promote_from_alphaforge(package, context=_strong_context())
        assert isinstance(result, PromotionResult)

    def test_promote_passes_all_applicable_gates(self):
        """A valid SWING package with strong evidence should pass all gates."""
        engine = V7PromotionEngine()
        package = _promotable_package()
        result = engine.promote_from_alphaforge(package, context=_strong_context())

        # Schema valid -> no schema errors
        assert "schema_errors" not in result.gates_summary

        # Pre-acceptance gates (G0-G4) should all pass
        pre_gates = result.pre_acceptance.get("gates", {})
        for gid in PRE_ACCEPTANCE_GATES:
            assert gid in pre_gates, f"Missing pre gate {gid}"
            assert pre_gates[gid]["status"] != "FAIL", (
                f"Pre-acceptance gate {gid} failed: {pre_gates[gid].get('detail')}"
            )

        # Post-acceptance gates (G5-G6 pass, G7-G10 NA)
        post_gates = result.post_acceptance.get("gates", {})
        assert post_gates["G5"]["status"] == "PASS"
        assert post_gates["G6"]["status"] == "PASS"
        assert post_gates["G7"]["status"] == "NOT_APPLICABLE"
        assert post_gates["G8"]["status"] == "NOT_APPLICABLE"
        assert post_gates["G9"]["status"] == "NOT_APPLICABLE"
        assert post_gates["G10"]["status"] == "NOT_APPLICABLE"

    def test_promote_successful_result_fields(self):
        """A successful promotion should have all expected fields."""
        engine = V7PromotionEngine()
        package = _promotable_package()
        result = engine.promote_from_alphaforge(package, context=_strong_context())

        assert result.promoted is True
        assert result.artifact_id != ""
        assert result.handoff_package_id == package["handoff_package_id"]
        assert result.mode == package["mode"]
        assert result.acceptance_id != ""

        # Next steps should include promotion-complete message
        next_steps_text = " ".join(result.next_steps).lower()
        assert "promotion complete" in next_steps_text

    # ── Schema validation failure ──────────────────────────────────────────

    def test_rejects_invalid_schema(self):
        """An invalid package should be rejected at schema validation."""
        engine = V7PromotionEngine()
        package = _promotable_package()
        del package["mode"]

        result = engine.promote_from_alphaforge(package)

        assert result.promoted is False
        assert result.artifact_id == ""
        assert "schema_errors" in result.gates_summary
        assert len(result.gates_summary["schema_errors"]) > 0
        assert "schema" in " ".join(result.next_steps).lower()

    def test_rejects_empty_package(self):
        """An empty package should be rejected at schema validation."""
        engine = V7PromotionEngine()
        result = engine.promote_from_alphaforge({})

        assert result.promoted is False
        assert result.artifact_id == ""

    # ── G2 failure (weak candidate) ────────────────────────────────────────

    def test_rejects_weak_candidate_at_pre_acceptance(self):
        """A weak candidate should fail G2 and be rejected pre-acceptance."""
        engine = V7PromotionEngine()
        package = _weak_package()
        result = engine.promote_from_alphaforge(package)

        assert result.promoted is False
        # Pre-acceptance gates should report the failure
        pre_summary = result.pre_acceptance.get("summary", {})
        failed_gates = pre_summary.get("failed_gates", [])
        assert len(failed_gates) > 0

    def test_weak_candidate_no_post_gates_run(self):
        """When pre-acceptance fails, post-acceptance gates should not run."""
        engine = V7PromotionEngine()
        package = _weak_package()
        result = engine.promote_from_alphaforge(package)

        assert result.post_acceptance == {}
        assert result.artifact_id == ""

    def test_weak_candidate_has_next_steps(self):
        """A rejected candidate should have diagnostic next steps."""
        engine = V7PromotionEngine()
        package = _weak_package()
        result = engine.promote_from_alphaforge(package)

        assert len(result.next_steps) > 0
        # Should mention addressing failed gates
        next_text = " ".join(result.next_steps).lower()
        assert "gate" in next_text or "fail" in next_text

    # ── run_pre_acceptance_gates ───────────────────────────────────────────

    def test_pre_acceptance_gates_are_g0_to_g4(self):
        """Pre-acceptance gates should be exactly G0-G4."""
        engine = V7PromotionEngine()
        package = _promotable_package()
        result = engine.run_pre_acceptance_gates(package)

        gates = result["gates"]
        assert len(gates) == 5
        for gid in PRE_ACCEPTANCE_GATES:
            assert gid in gates, f"Missing pre gate {gid}"

    def test_pre_acceptance_does_not_include_g5(self):
        """G5 should not appear in pre-acceptance gates."""
        engine = V7PromotionEngine()
        package = _promotable_package()
        result = engine.run_pre_acceptance_gates(package)
        assert "G5" not in result["gates"]

    def test_pre_acceptance_summary(self):
        """Pre-acceptance should include a valid summary."""
        engine = V7PromotionEngine()
        package = _promotable_package()
        result = engine.run_pre_acceptance_gates(package)

        summary = result["summary"]
        assert "passed" in summary
        assert "overall_score" in summary
        assert "passed_gates" in summary
        assert "failed_gates" in summary
        assert "na_gates" in summary
        assert "recommendation" in summary

    # ── run_post_acceptance_gates ──────────────────────────────────────────

    def test_post_acceptance_gates_are_g5_to_g10(self):
        """Post-acceptance gates should be exactly G5-G10."""
        engine = V7PromotionEngine()
        package = _promotable_package()
        result = engine.run_post_acceptance_gates(package)

        gates = result["gates"]
        assert len(gates) == 6
        for gid in POST_ACCEPTANCE_GATES:
            assert gid in gates, f"Missing post gate {gid}"

    def test_post_acceptance_does_not_include_g0(self):
        """G0 should not appear in post-acceptance gates."""
        engine = V7PromotionEngine()
        package = _promotable_package()
        result = engine.run_post_acceptance_gates(package)
        assert "G0" not in result["gates"]

    def test_post_acceptance_g5_g6_pass_g7_g10_na(self):
        """G5-G6 should PASS, G7-G10 should be NOT_APPLICABLE."""
        engine = V7PromotionEngine()
        package = _promotable_package()
        result = engine.run_post_acceptance_gates(package)

        gates = result["gates"]
        assert gates["G5"]["status"] == "PASS"
        assert gates["G6"]["status"] == "PASS"
        assert gates["G7"]["status"] == "NOT_APPLICABLE"
        assert gates["G8"]["status"] == "NOT_APPLICABLE"
        assert gates["G9"]["status"] == "NOT_APPLICABLE"
        assert gates["G10"]["status"] == "NOT_APPLICABLE"

    # ── register_artifact ──────────────────────────────────────────────────

    def test_register_artifact_returns_non_empty_string(self):
        """register_artifact should return a non-empty string."""
        engine = V7PromotionEngine()
        artifact_id = engine.register_artifact({"dummy": "artifact"})
        assert isinstance(artifact_id, str)
        assert len(artifact_id) > 0

    def test_register_artifact_unique_ids(self):
        """Each registration should produce a unique artifact ID."""
        engine = V7PromotionEngine()
        id1 = engine.register_artifact({})
        id2 = engine.register_artifact({})
        assert id1 != id2

    def test_register_artifact_starts_with_v7art(self):
        """Artifact IDs should start with 'v7art-'."""
        engine = V7PromotionEngine()
        artifact_id = engine.register_artifact({})
        assert artifact_id.startswith("v7art-")

    # ── Gate constant integrity ────────────────────────────────────────────

    def test_pre_acceptance_gates_are_5(self):
        """There should be exactly 5 pre-acceptance gates (G0-G4)."""
        assert len(PRE_ACCEPTANCE_GATES) == 5
        assert PRE_ACCEPTANCE_GATES == ["G0", "G1", "G2", "G3", "G4"]

    def test_post_acceptance_gates_are_6(self):
        """There should be exactly 6 post-acceptance gates (G5-G10)."""
        assert len(POST_ACCEPTANCE_GATES) == 6
        assert POST_ACCEPTANCE_GATES == ["G5", "G6", "G7", "G8", "G9", "G10"]


class TestPromotionResult:
    """Test PromotionResult dataclass."""

    def test_immutable(self):
        """PromotionResult should be immutable."""
        result = PromotionResult(
            promoted=True,
            artifact_id="v7art-test-001",
            gates_summary={"passed": True},
            next_steps=["Promotion complete"],
        )
        with pytest.raises(Exception):
            result.promoted = False  # type: ignore[misc]

    def test_defaults(self):
        """Default fields should be empty where expected."""
        result = PromotionResult(
            promoted=False,
            artifact_id="",
            gates_summary={},
            next_steps=[],
        )
        assert result.pre_acceptance == {}
        assert result.post_acceptance == {}
        assert result.handoff_package_id == ""
        assert result.mode == ""
        assert result.acceptance_id == ""
