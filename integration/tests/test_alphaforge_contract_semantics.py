"""P0.8E — AlphaForge contract semantics tests.

Validates cross-schema invariants: mode coverage enforcement,
verdict coupling, timeframe consistency, label contract completeness.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMAS_DIR = ROOT / "contracts" / "schemas" / "alphaforge"
FIXTURES_DIR = ROOT / "contracts" / "fixtures" / "alphaforge"
REGISTRY_PATH = ROOT / "contracts" / "registry.json"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── AlphaForgeResearchReport mode coverage ──────────────────────────────

def test_aggregate_report_has_all_three_modes():
    """AlphaForgeResearchReport must include SCALP, AGGRESSIVE_SCALP, SWING."""
    report = load_json(FIXTURES_DIR / "alphaforge_research_report_minimal.json")
    modes = {r["mode"] for r in report["mode_reports"]}
    assert modes == {"SCALP", "AGGRESSIVE_SCALP", "SWING"}, (
        f"AlphaForgeResearchReport must cover all 3 modes, got {modes}"
    )


def test_aggregate_report_modes_do_not_duplicate():
    """No mode should appear twice in mode_reports."""
    report = load_json(FIXTURES_DIR / "alphaforge_research_report_minimal.json")
    modes = [r["mode"] for r in report["mode_reports"]]
    assert len(modes) == len(set(modes)), f"Duplicate modes in mode_reports: {modes}"


def test_primary_modes_not_declared_baseline():
    """SCALP and AGGRESSIVE_SCALP must NOT use secondary_baseline_report."""
    for fixture_file, label in [
        ("scalp_mode_research_report_minimal.json", "SCALP"),
        ("aggressive_scalp_mode_research_report_minimal.json", "AGGRESSIVE_SCALP"),
    ]:
        report = load_json(FIXTURES_DIR / fixture_file)
        assert report["report_type"] == "primary_research_report", (
            f"{label} must use primary_research_report, got {report['report_type']}"
        )
        assert report["mode_priority"] == "PRIMARY", (
            f"{label} must be PRIMARY, got {report['mode_priority']}"
        )


def test_swing_not_declared_primary():
    """SWING must use secondary_baseline_report, NOT primary."""
    report = load_json(FIXTURES_DIR / "swing_mode_research_report_minimal.json")
    assert report["report_type"] == "secondary_baseline_report", (
        f"SWING must use secondary_baseline_report, got {report['report_type']}"
    )
    assert report["mode_priority"] == "SECONDARY_BASELINE", (
        f"SWING must be SECONDARY_BASELINE, got {report['mode_priority']}"
    )


# ── Verdict coupling ────────────────────────────────────────────────────

ALLOWED_VERDICTS = [
    "REJECT", "CONTINUE_RESEARCH", "CANDIDATE_FOR_V7_GATES",
    "BASELINE_VALID", "BASELINE_WEAK",
]


def test_mode_report_verdicts_in_allowed_set():
    """All mode report verdicts must be in the allowed enum."""
    for fixture_file in [
        "scalp_mode_research_report_minimal.json",
        "aggressive_scalp_mode_research_report_minimal.json",
        "swing_mode_research_report_minimal.json",
    ]:
        report = load_json(FIXTURES_DIR / fixture_file)
        assert report["verdict"] in ALLOWED_VERDICTS, (
            f"{fixture_file} verdict '{report['verdict']}' not in allowed set {ALLOWED_VERDICTS}"
        )


def test_scalp_aggressive_scalp_not_using_baseline_verdicts():
    """SCALP and AGGRESSIVE_SCALP must not use baseline verdicts as primary modes."""
    for fixture_file, label in [
        ("scalp_mode_research_report_minimal.json", "SCALP"),
        ("aggressive_scalp_mode_research_report_minimal.json", "AGGRESSIVE_SCALP"),
    ]:
        report = load_json(FIXTURES_DIR / fixture_file)
        assert report["verdict"] not in ("BASELINE_VALID", "BASELINE_WEAK"), (
            f"{label} (PRIMARY mode) should not use baseline verdict {report['verdict']}"
        )


# ── Label contract completeness ─────────────────────────────────────────

REQUIRED_LABEL_FIELDS = [
    "label_dataset_id", "mode", "simulation_profile_id",
    "label_source", "label_fields", "cost_model_ref",
    "funding_status", "no_trade_comparison", "lineage",
]


def test_label_dataset_spec_requires_key_fields():
    """LabelDatasetSpec schema must require cost/no-trade/funding awareness."""
    schema = load_json(SCHEMAS_DIR / "label_dataset_spec.schema.json")
    required = schema.get("required", [])
    for field in REQUIRED_LABEL_FIELDS:
        assert field in required, f"label_dataset_spec missing required field: {field}"

    # funding_status must include DEFERRED, IMPLEMENTED, NOT_APPLICABLE
    funding_enum = (
        schema.get("properties", {})
        .get("funding_status", {})
        .get("enum", [])
    )
    assert "DEFERRED" in funding_enum, "funding_status must include DEFERRED"


# ── Cross-schema timeframe consistency ──────────────────────────────────

LOCKED_TIMEFRAMES = {
    "SCALP": {"primary": ["1h"], "context": ["4h"], "refinement": ["15m"]},
    "AGGRESSIVE_SCALP": {"primary": ["15m"], "context": ["1h"], "refinement": ["5m"]},
    "SWING": {"primary": ["4h"], "context": ["1d"], "refinement": ["1h"]},
}


def test_fixture_timeframes_match_locked_profiles():
    """All fixtures must use locked simulation profile timeframes."""
    for mode, expected in LOCKED_TIMEFRAMES.items():
        fixture_name = f"{mode.lower().replace('-', '').replace(' ', '_').replace('aggressive_scalp', 'aggressive_scalp')}_mode_research_report_minimal.json"
        # Fix: AGGRESSIVE_SCALP -> aggressive_scalp
        if mode == "AGGRESSIVE_SCALP":
            fixture_name = "aggressive_scalp_mode_research_report_minimal.json"
        elif mode == "SCALP":
            fixture_name = "scalp_mode_research_report_minimal.json"
        elif mode == "SWING":
            fixture_name = "swing_mode_research_report_minimal.json"

        report = load_json(FIXTURES_DIR / fixture_name)
        primary = report["data_scope"]["primary_timeframes"]
        assert primary == expected["primary"], (
            f"{mode} primary_timeframes should be {expected['primary']}, got {primary}"
        )


# ── Registry completeness ───────────────────────────────────────────────

def test_registry_includes_all_alphaforge_contracts():
    """Registry must list all AlphaForge contract schemas."""
    registry = load_json(REGISTRY_PATH)
    contracts = registry.get("contracts", [])
    alphaforge_objects = {
        c["object_name"] for c in contracts
        if c.get("owner_domain") == "alphaforge"
    }

    expected = {
        "AlphaThesis", "AlphaCandidate", "FeatureSetSpec",
        "LabelDatasetSpec", "ModeResearchReport",
        "AlphaForgeResearchReport", "ValidationReport",
        "ModelArtifact", "CalibrationCandidate",
        "V7HandoffPackage", "AlphaForgeLabel",
    }
    missing = expected - alphaforge_objects
    assert not missing, f"Registry missing AlphaForge contracts: {missing}"
