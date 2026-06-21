"""AlphaForge V7 Handoff Builder.

Builds schema-valid placeholder V7HandoffPackage payloads using canonical
V7 gate mapping from P0.8E. All handoffs are REVIEW_REQUIRED — scaffold
does not claim readiness for shadow, paper, or live.
"""
from datetime import datetime, timezone

from alphaforge.constants import (
    CANONICAL_V7_GATES,
    HANDOFF_REVIEW_REQUIRED,
    FUNDING_DEFERRED,
)
from alphaforge.modes.profiles import get_mode_profile, ModeProfile
from alphaforge.contracts.loader import load_schema
from alphaforge.contracts.validator import validate_payload
from alphaforge.errors import HandoffBuildError, ModeError


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_gate_entry(evidence_ref: str, status: str = "NOT_EVALUATED") -> dict:
    return {
        "evidence_ref": evidence_ref,
        "status": status,
    }


def build_v7_handoff_package(
    mode: str,
    handoff_package_id: str | None = None,
    alpha_candidate_id: str | None = None,
    mode_research_report_id: str | None = None,
    validation_report_id: str | None = None,
    model_artifact_id: str | None = None,
    calibration_candidate_id: str | None = None,
    recommended_status: str = HANDOFF_REVIEW_REQUIRED,
) -> dict:
    """Build a schema-valid placeholder V7HandoffPackage.

    Uses canonical V7 gate mapping (P0.8E corrected). All gates marked
    NOT_EVALUATED. Recommended status defaults to REVIEW_REQUIRED.

    Args:
        mode: 'SCALP', 'AGGRESSIVE_SCALP', or 'SWING'.
        handoff_package_id: Optional package ID override.
        alpha_candidate_id: Optional candidate ID override.
        mode_research_report_id: Optional mode report ID override.
        validation_report_id: Optional validation report ID override.
        model_artifact_id: Optional model artifact ID override.
        calibration_candidate_id: Optional calibration candidate ID override.
        recommended_status: Handoff recommendation (default: REVIEW_REQUIRED).

    Returns:
        V7HandoffPackage payload as dict.

    Raises:
        ModeError: Unknown mode.
        HandoffBuildError: Validation failed.
    """
    if mode not in ("SCALP", "AGGRESSIVE_SCALP", "SWING"):
        raise ModeError(f"Unknown mode: '{mode}'")

    profile = get_mode_profile(mode)
    mode_key = mode.lower().replace("-", "").replace(" ", "_")
    if mode == "AGGRESSIVE_SCALP":
        mode_key = "aggressive_scalp"
    elif mode == "SCALP":
        mode_key = "scalp"
    elif mode == "SWING":
        mode_key = "swing"

    pid = handoff_package_id or f"v7hp-{mode_key}-scaffold-001"
    acid = alpha_candidate_id or f"ac-{mode_key}-scaffold-001"
    mrid = mode_research_report_id or f"mrr-{mode_key}-scaffold-001"
    vrid = validation_report_id or f"vr-{mode_key}-scaffold-001"
    maid = model_artifact_id or f"ma-{mode_key}-scaffold-001"
    ccid = calibration_candidate_id or f"cc-{mode_key}-scaffold-001"

    # Canonical gate mapping — all NOT_EVALUATED in scaffold (P0.8E)
    gate_mapping = {
        "G0_doc_ready": _make_gate_entry(
            f"Authority docs for {mode} — scaffold placeholder (no real docs reviewed)"
        ),
        "G1_research_backtest": _make_gate_entry(
            f"Initial backtest metrics for {mode} — scaffold placeholder (no real data)"
        ),
        "G2_walk_forward_oos": _make_gate_entry(
            f"Walk-forward OOS evidence for {mode} — scaffold placeholder (no real data)"
        ),
        "G3_cost_stress": _make_gate_entry(
            f"Cost stress analysis for {mode} — scaffold placeholder (no real data)"
        ),
        "G4_regime_breakdown": _make_gate_entry(
            f"Regime breakdown for {mode} — scaffold placeholder (no real data)"
        ),
        "G5_symbol_stability": _make_gate_entry(
            f"Symbol stability for {mode} — scaffold placeholder (single symbol limitation)"
        ),
        "G6_calibration_reliability": _make_gate_entry(
            f"Calibration for {mode} — scaffold placeholder (no real model)"
        ),
        "G7_shadow": _make_gate_entry(
            "Shadow trading infrastructure not yet built — P0.9A+ dependency"
        ),
        "G8_paper": _make_gate_entry(
            "Paper trading infrastructure not yet built — P0.9A+ dependency"
        ),
        "G9_tiny_live": _make_gate_entry(
            "Tiny-live infrastructure not yet built — far future"
        ),
        "G10_live": _make_gate_entry(
            "Live infrastructure not yet built — far future"
        ),
    }

    payload = {
        "schema_version": "1.0.0",
        "handoff_package_id": pid,
        "mode": mode,
        "alpha_candidate_id": acid,
        "mode_research_report_id": mrid,
        "validation_report_id": vrid,
        "model_artifact_id": maid,
        "calibration_candidate_id": ccid,
        "v7_gate_mapping": gate_mapping,
        "recommended_status": recommended_status,
        "blocked_scopes": [
            f"Scaffold placeholder — no real data for {mode}",
            "No real model trained — all references are scaffold IDs",
            f"Funding model DEFERRED — blocks perpetual/live handoff for {mode}",
            f"{mode} is {profile.priority} — {profile.description}",
            "V7 has not reviewed this package — all gates are dummy mapped",
        ],
        "limitations": [
            "Scaffold placeholder for schema validation and interface testing only",
            "All referenced IDs are scaffold examples — do not expect real artifacts",
            "No real model binary exists at any URI",
            "No real validation was performed",
            "V7 gate mapping is structural — no real evidence behind gates",
            f"Recommended status {recommended_status} — V7 must independently verify",
            f"P0.8E canonical gate mapping used — all gates NOT_EVALUATED",
        ],
        "lineage": {
            "data_refs": ["raw-btcusdt-scaffold", "norm-btcusdt-scaffold"],
            "feature_set_id": f"fs-{mode_key}-scaffold-001",
            "label_dataset_id": f"lds-{mode_key}-scaffold-001",
            "simulation_profile_id": f"{mode_key}_profile-1.0.0",
            "simulation_run_ids": [f"sim-scaffold-{mode_key}-001"],
            "training_run_id": f"run-scaffold-{mode_key}-001",
            "git_commit": "0000000000000000000000000000000000000000",
            "lineage_verified": False,
        },
        "created_at": _now_iso(),
        "rejection_rules_applied": [
            "Scaffold placeholder — all dummy data, automatically REVIEW_REQUIRED",
            "No real OOS evidence — cannot pass G2-G6 without real data",
            "Funding DEFERRED — perpetual/live scope explicitly blocked",
            "Single symbol only — flagged as limitation",
        ],
    }

    # Validate against P0.8E-corrected schema
    schema = load_schema("v7_handoff_package.schema.json")
    result = validate_payload(schema, payload, f"v7_handoff_package({mode})")
    if not result.valid:
        raise HandoffBuildError(
            f"Built V7HandoffPackage for {mode} failed validation: {result.errors}"
        )

    return payload


def build_all_handoffs() -> dict[str, dict]:
    """Build scaffold handoff packages for all three modes.

    Returns:
        Dict mapping mode → V7HandoffPackage payload.
    """
    return {
        "SCALP": build_v7_handoff_package("SCALP"),
        "AGGRESSIVE_SCALP": build_v7_handoff_package("AGGRESSIVE_SCALP"),
        "SWING": build_v7_handoff_package("SWING"),
    }
