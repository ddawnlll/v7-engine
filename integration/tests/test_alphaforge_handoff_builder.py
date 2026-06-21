"""P0.9A — AlphaForge V7 handoff builder tests.

Verifies V7HandoffPackage builder produces schema-valid review-only
handoffs with canonical V7 gate mapping.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
AF_SRC = REPO / "alphaforge" / "src"
if str(AF_SRC) not in sys.path:
    sys.path.insert(0, str(AF_SRC))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import pytest
from alphaforge.handoff.builders import (
    build_v7_handoff_package,
    build_all_handoffs,
)
from alphaforge.constants import (
    CANONICAL_V7_GATES,
    HANDOFF_REVIEW_REQUIRED,
)
from alphaforge.contracts.loader import load_schema
from alphaforge.contracts.validator import validate_payload
from alphaforge.errors import ModeError


def test_build_handoff_validates():
    """Single-mode handoff must validate against schema."""
    handoff = build_v7_handoff_package("SWING")
    schema = load_schema("v7_handoff_package.schema.json")
    result = validate_payload(schema, handoff, "swing_handoff")
    assert result.valid, f"Handoff validation failed: {result.errors}"


def test_build_all_handoffs():
    """All three modes must produce valid handoffs."""
    all_h = build_all_handoffs()
    assert set(all_h.keys()) == {"SCALP", "AGGRESSIVE_SCALP", "SWING"}
    schema = load_schema("v7_handoff_package.schema.json")
    for mode, handoff in all_h.items():
        result = validate_payload(schema, handoff, f"handoff_{mode}")
        assert result.valid, f"{mode} handoff failed: {result.errors}"


def test_handoff_uses_canonical_gate_ids():
    """Handoff gate mapping must use canonical V7 gate IDs from P0.8E."""
    handoff = build_v7_handoff_package("SWING")
    gate_mapping = handoff["v7_gate_mapping"]

    for gate_id in CANONICAL_V7_GATES:
        assert gate_id in gate_mapping, f"Missing canonical gate: {gate_id}"
        assert "evidence_ref" in gate_mapping[gate_id]
        assert "status" in gate_mapping[gate_id]

    # Legacy gate IDs must NOT appear
    legacy = [
        "G0_data_quality", "G1_feature_validity", "G2_label_validity",
        "G3_model_sanity", "G4_oos_performance", "G5_cost_resilience",
        "G6_regime_robustness", "G7_stability", "G8_calibration",
        "G9_no_trade_baseline", "G10_paper_shadow",
    ]
    for lid in legacy:
        assert lid not in gate_mapping, f"Legacy gate ID {lid} found in handoff"


def test_handoff_recommended_status_review_only():
    """Scaffold handoff must default to REVIEW_REQUIRED, not SHADOW_READY or PROMOTION_CANDIDATE."""
    handoff = build_v7_handoff_package("SCALP")
    assert handoff["recommended_status"] == HANDOFF_REVIEW_REQUIRED


def test_handoff_blocked_scopes_include_holds():
    """Handoff must mention relevant holds in blocked_scopes."""
    for mode in ["SCALP", "AGGRESSIVE_SCALP", "SWING"]:
        handoff = build_v7_handoff_package(mode)
        scopes_text = " ".join(handoff["blocked_scopes"]).lower()
        assert "deferred" in scopes_text, f"{mode} handoff missing DEFERRED in blocked_scopes"


def test_handoff_v7_final_authority_preserved():
    """Handoff must not override V7 final authority."""
    handoff = build_v7_handoff_package("SWING")
    # recommended_status must be non-binding
    assert handoff["recommended_status"] != "PROMOTION_CANDIDATE"
    # limitations must mention V7 independence
    limits_text = " ".join(handoff["limitations"]).lower()
    assert "verify" in limits_text or "v7" in limits_text


def test_build_handoff_unknown_mode_raises():
    with pytest.raises(ModeError):
        build_v7_handoff_package("INVALID")


def test_handoff_gate_status_all_not_evaluated():
    """All gate statuses must be NOT_EVALUATED in scaffold (no fake readiness)."""
    handoff = build_v7_handoff_package("SWING")
    for gate_id, entry in handoff["v7_gate_mapping"].items():
        assert entry["status"] == "NOT_EVALUATED", (
            f"Gate {gate_id} status is '{entry['status']}', expected NOT_EVALUATED"
        )
