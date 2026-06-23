"""P0.8E — AlphaForge schema strictness tests.

Validates that schemas reject empty/insufficient evidence payloads,
enforce nested required fields, require MHT/data-snooping controls,
and use canonical V7 gate names and timeframe stacks.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMAS_DIR = ROOT / "contracts" / "schemas" / "alphaforge"
FIXTURES_DIR = ROOT / "contracts" / "fixtures" / "alphaforge"
LABEL_SCHEMA_PATH = ROOT / "contracts" / "schemas" / "alphaforge_label.schema.json"
LABEL_FIXTURE_PATH = ROOT / "contracts" / "fixtures" / "alphaforge_label_minimal.json"
MAPPING_PATH = ROOT / "contracts" / "mappings" / "simulation_to_alphaforge.json"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _reject_empty(instance, schema):
    """Run jsonschema validation. Returns (ok, error_str)."""
    try:
        import jsonschema
        jsonschema.validate(instance=instance, schema=schema)
        return True, None
    except ImportError:
        # Structural fallback: check top-level and nested required keys
        errors = []
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"Missing required key: {key}")
        # Also check nested required in properties
        for prop_name, prop_schema in schema.get("properties", {}).items():
            if prop_name in instance and isinstance(instance[prop_name], dict):
                for nested_key in prop_schema.get("required", []):
                    if nested_key not in instance[prop_name]:
                        errors.append(
                            f"Missing nested required key: {prop_name}.{nested_key}"
                        )
        if errors:
            return False, "; ".join(errors)
        return True, "jsonschema not installed — structural check only"
    except Exception as e:
        return False, str(e)


# ── ModeResearchReport nested strictness ───────────────────────────────

@pytest.mark.parametrize("mode_label", [
    ("scalp_mode_research_report_minimal.json", "SCALP"),
    ("aggressive_scalp_mode_research_report_minimal.json", "AGGRESSIVE_SCALP"),
    ("swing_mode_research_report_minimal.json", "SWING"),
])
def test_mode_report_cost_stress_not_empty(mode_label):
    """P0.8E: cost_stress must carry required fields — empty object must fail."""
    fixture_file, label = mode_label
    schema = load_json(SCHEMAS_DIR / "mode_research_report.schema.json")
    report = load_json(FIXTURES_DIR / fixture_file)

    # Real fixture should pass
    ok, err = _reject_empty(report, schema)
    assert ok, f"{label} fixture should validate: {err}"

    # Empty cost_stress should fail
    report_bad = dict(report)
    report_bad["cost_stress"] = {}
    ok_bad, _ = _reject_empty(report_bad, schema)
    assert not ok_bad, f"{label}: empty cost_stress should be rejected"


@pytest.mark.parametrize("mode_label", [
    ("scalp_mode_research_report_minimal.json", "SCALP"),
    ("aggressive_scalp_mode_research_report_minimal.json", "AGGRESSIVE_SCALP"),
    ("swing_mode_research_report_minimal.json", "SWING"),
])
def test_mode_report_no_trade_comparison_not_empty(mode_label):
    """P0.8E: no_trade_comparison must carry required fields — empty object must fail."""
    fixture_file, label = mode_label
    schema = load_json(SCHEMAS_DIR / "mode_research_report.schema.json")
    report = load_json(FIXTURES_DIR / fixture_file)

    report_bad = dict(report)
    report_bad["no_trade_comparison"] = {}
    ok_bad, _ = _reject_empty(report_bad, schema)
    assert not ok_bad, f"{label}: empty no_trade_comparison should be rejected"


@pytest.mark.parametrize("mode_label", [
    ("scalp_mode_research_report_minimal.json", "SCALP"),
    ("aggressive_scalp_mode_research_report_minimal.json", "AGGRESSIVE_SCALP"),
    ("swing_mode_research_report_minimal.json", "SWING"),
])
def test_mode_report_regime_breakdown_not_empty(mode_label):
    """P0.8E: regime_breakdown must carry required fields — empty object must fail."""
    fixture_file, label = mode_label
    schema = load_json(SCHEMAS_DIR / "mode_research_report.schema.json")
    report = load_json(FIXTURES_DIR / fixture_file)

    report_bad = dict(report)
    report_bad["regime_breakdown"] = {}
    ok_bad, _ = _reject_empty(report_bad, schema)
    assert not ok_bad, f"{label}: empty regime_breakdown should be rejected"


# ── ValidationReport MHT/data-snooping ─────────────────────────────────

def test_validation_report_schema_requires_mht():
    """P0.8E: validation_report schema must require multiple_hypothesis_control."""
    schema = load_json(SCHEMAS_DIR / "validation_report.schema.json")
    required = schema.get("required", [])
    assert "multiple_hypothesis_control" in required, (
        "validation_report must require multiple_hypothesis_control"
    )

    mht = schema["properties"]["multiple_hypothesis_control"]
    mht_required = mht.get("required", [])
    for field in ["tested_hypothesis_count", "correction_method", "data_snooping_risk_flag"]:
        assert field in mht_required, (
            f"multiple_hypothesis_control must require {field}"
        )


def test_validation_report_schema_has_canonical_regimes():
    """P0.8E: regime_breakdown items must use canonical V7 regime enum."""
    schema = load_json(SCHEMAS_DIR / "validation_report.schema.json")
    regime_items = (
        schema.get("properties", {})
        .get("regime_breakdown", {})
        .get("properties", {})
        .get("regimes", {})
        .get("items", {})
        .get("properties", {})
        .get("regime", {})
    )
    regime_enum = regime_items.get("enum", [])
    assert set(regime_enum) == {"TREND_UP", "TREND_DOWN", "RANGE", "TRANSITION"}, (
        f"Canonical regime enum mismatch: {regime_enum}"
    )

    # Legacy regime names must NOT appear
    legacy_names = ["HIGH_VOL_UP", "HIGH_VOL_DOWN", "LOW_VOL_RANGE", "LOW_VOL_TREND", "NORMAL"]
    for legacy in legacy_names:
        assert legacy not in regime_enum, f"Legacy regime name '{legacy}' must not be in enum"


def test_validation_report_schema_has_cost_stress_nested_required():
    """P0.8E: cost_stress must have nested required fields including spread and funding."""
    schema = load_json(SCHEMAS_DIR / "validation_report.schema.json")
    cost = schema["properties"]["cost_stress"]
    cost_required = cost.get("required", [])

    for field in [
        "baseline_fee_pct", "baseline_slippage_pct",
        "baseline_spread_pct", "combined_stress_edge_survives",
        "funding_deferred_block",
    ]:
        assert field in cost_required, f"cost_stress must require {field}"


def test_validation_report_schema_min_folds():
    """P0.8E: walk_forward_folds must have minimum 6 folds."""
    schema = load_json(SCHEMAS_DIR / "validation_report.schema.json")
    fold_count = (
        schema.get("properties", {})
        .get("walk_forward_folds", {})
        .get("properties", {})
        .get("fold_count", {})
    )
    assert fold_count.get("minimum") == 6, (
        f"fold_count minimum must be 6, got {fold_count.get('minimum')}"
    )


# ── V7 Handoff Package gate mapping ────────────────────────────────────

def test_v7_handoff_schema_requires_all_gates():
    """P0.8E: v7_gate_mapping must require all 11 canonical gates."""
    schema = load_json(SCHEMAS_DIR / "v7_handoff_package.schema.json")
    gate_mapping = schema["properties"]["v7_gate_mapping"]
    gate_required = gate_mapping.get("required", [])

    canonical = [
        "G0_doc_ready", "G1_research_backtest", "G2_walk_forward_oos",
        "G3_cost_stress", "G4_regime_breakdown", "G5_symbol_stability",
        "G6_calibration_reliability", "G7_shadow", "G8_paper",
        "G9_tiny_live", "G10_live",
    ]
    for gate in canonical:
        assert gate in gate_required, f"v7_gate_mapping must require {gate}"


def test_v7_handoff_schema_no_legacy_gates():
    """P0.8E: no legacy gate names in schema."""
    schema = load_json(SCHEMAS_DIR / "v7_handoff_package.schema.json")
    schema_text = json.dumps(schema)

    legacy = [
        "G0_data_quality", "G1_feature_validity", "G2_label_validity",
        "G3_model_sanity", "G4_oos_performance", "G5_cost_resilience",
        "G6_regime_robustness", "G7_stability", "G8_calibration",
        "G9_no_trade_baseline", "G10_paper_shadow",
    ]
    for legacy_id in legacy:
        assert legacy_id not in schema_text, (
            f"Legacy gate ID '{legacy_id}' found in v7_handoff_package schema"
        )


def test_handoff_fixture_gate_mapping_non_empty():
    """P0.8E: v7_gate_mapping must not be empty — each gate needs evidence_ref."""
    fixture = load_json(FIXTURES_DIR / "v7_handoff_package_minimal.json")
    gate_mapping = fixture["v7_gate_mapping"]
    assert len(gate_mapping) == 11, f"Expected 11 gates, got {len(gate_mapping)}"

    for gate_id, gate_obj in gate_mapping.items():
        assert "evidence_ref" in gate_obj, f"{gate_id} missing evidence_ref"
        assert "status" in gate_obj, f"{gate_id} missing status"
        assert gate_obj["status"] in ("PASS", "PENDING", "NOT_EVALUATED"), (
            f"{gate_id} invalid status: {gate_obj['status']}"
        )


# ── Label contract completeness ────────────────────────────────────────

def test_label_schema_requires_gross_net_cost_fields():
    """P0.8E: AlphaForgeLabel must require gross R and total cost fields for cost awareness."""
    schema = load_json(LABEL_SCHEMA_PATH)
    required = schema.get("required", [])

    for field in [
        "long_R_gross", "short_R_gross",
        "total_cost_r_long", "total_cost_r_short",
        "no_trade_quality", "resolution_status",
        "simulation_profile_id",
    ]:
        assert field in required, f"AlphaForgeLabel must require {field}"


def test_label_schema_requires_funding_status():
    """P0.8E: funding_status must include DEFERRED as explicit enum value."""
    schema = load_json(LABEL_SCHEMA_PATH)
    funding = schema["properties"]["funding_status"]
    assert "DEFERRED" in funding.get("enum", []), (
        "funding_status must include DEFERRED"
    )


def test_label_fixture_validates():
    """P0.8E: alphaforge_label_minimal fixture must validate against schema."""
    schema = load_json(LABEL_SCHEMA_PATH)
    fixture = load_json(LABEL_FIXTURE_PATH)
    ok, err = _reject_empty(fixture, schema)
    assert ok, f"AlphaForgeLabel fixture failed validation: {err}"


def test_label_fixture_has_all_required_economic_fields():
    """P0.8E: label fixture must carry gross/net, cost, no_trade_quality fields."""
    fixture = load_json(LABEL_FIXTURE_PATH)

    # Gross-vs-net distinction
    assert "long_R_gross" in fixture
    assert "long_R_net" in fixture
    assert "short_R_gross" in fixture
    assert "short_R_net" in fixture

    # Cost decomposition
    assert "total_cost_r_long" in fixture
    assert "total_cost_r_short" in fixture

    # NO_TRADE quality
    assert fixture["no_trade_quality"] in (
        "CORRECT_NO_TRADE", "SAVED_LOSS", "MISSED_OPPORTUNITY", "AMBIGUOUS_NO_TRADE"
    )

    # Funding explicitly deferred
    assert fixture["funding_status"] == "DEFERRED"


# ── Simulation-to-AlphaForge mapping completeness ──────────────────────

def test_simulation_to_alphaforge_mapping_has_p0_8e_fields():
    """P0.8E: mapping must include gross R, cost component, exit/reason fields."""
    mapping = load_json(MAPPING_PATH)
    targets = {m["target"] for m in mapping["mappings"]}

    p0_8e_fields = [
        "long_R_gross", "short_R_gross",
        "fee_cost_r_long", "slippage_cost_r_long", "total_cost_r_long",
        "fee_cost_r_short", "slippage_cost_r_short", "total_cost_r_short",
        "no_trade_quality", "was_correct_skip",
        "saved_loss_r", "missed_opportunity_r",
        "resolution_status", "exit_reason",
        "simulation_profile_id", "simulation_engine_version",
        "cost_model_version",
    ]
    missing = [f for f in p0_8e_fields if f not in targets]
    assert not missing, f"Mapping missing P0.8E fields: {missing}"


# ── AlphaForgeResearchReport mode coverage ─────────────────────────────

def test_aggregate_report_schema_requires_exactly_three_modes():
    """P0.8E: AlphaForgeResearchReport must require exactly 3 mode_reports."""
    schema = load_json(SCHEMAS_DIR / "alphaforge_research_report.schema.json")
    mode_reports = schema["properties"]["mode_reports"]
    assert mode_reports.get("minItems") == 3, "mode_reports minItems must be 3"
    assert mode_reports.get("maxItems") == 3, "mode_reports maxItems must be 3"


def test_aggregate_report_mode_items_require_priority_and_type():
    """P0.8E: each mode_report entry must require mode_priority and report_type."""
    schema = load_json(SCHEMAS_DIR / "alphaforge_research_report.schema.json")
    item_required = (
        schema.get("properties", {})
        .get("mode_reports", {})
        .get("items", {})
        .get("required", [])
    )
    for field in ["mode_priority", "report_type"]:
        assert field in item_required, (
            f"mode_reports items must require {field}"
        )


# ── V7 gate mapping canonical names across all schemas ─────────────────

CANONICAL_GATES = [
    "G0_doc_ready", "G1_research_backtest", "G2_walk_forward_oos",
    "G3_cost_stress", "G4_regime_breakdown", "G5_symbol_stability",
    "G6_calibration_reliability", "G7_shadow", "G8_paper",
    "G9_tiny_live", "G10_live",
]

FORBIDDEN_GATES = [
    "G0_data_quality", "G1_feature_validity", "G2_label_validity",
    "G3_model_sanity", "G4_oos_performance", "G5_cost_resilience",
    "G6_regime_robustness", "G7_stability", "G8_calibration",
    "G9_no_trade_baseline", "G10_paper_shadow",
]


def test_no_schema_contains_forbidden_gate_names():
    """P0.8E: no AlphaForge schema may reference legacy gate names."""
    for schema_file in SCHEMAS_DIR.glob("*.json"):
        text = schema_file.read_text(encoding="utf-8")
        for gate in FORBIDDEN_GATES:
            assert gate not in text, (
                f"{schema_file.name} contains forbidden gate: {gate}"
            )


# ── Timeframe stack validation ─────────────────────────────────────────

LOCKED_PRIMARY_TIMEFRAMES = {
    "SCALP": "1h",
    "AGGRESSIVE_SCALP": "15m",
    "SWING": "4h",
}

FORBIDDEN_PRIMARY_TIMEFRAMES = {
    "SCALP": ["1m", "5m"],
    "AGGRESSIVE_SCALP": ["1m", "3m"],
    "SWING": ["1h"],
}


def test_mode_report_fixtures_timeframe_keys_exist():
    """P0.8E: each mode fixture must have primary_timeframes in data_scope."""
    for fixture_file, mode in [
        ("scalp_mode_research_report_minimal.json", "SCALP"),
        ("aggressive_scalp_mode_research_report_minimal.json", "AGGRESSIVE_SCALP"),
        ("swing_mode_research_report_minimal.json", "SWING"),
    ]:
        report = load_json(FIXTURES_DIR / fixture_file)
        ptf = report["data_scope"].get("primary_timeframes", [])
        assert len(ptf) >= 1, f"{mode} has empty primary_timeframes"
        assert ptf[0] == LOCKED_PRIMARY_TIMEFRAMES[mode], (
            f"{mode} primary timeframe must be {LOCKED_PRIMARY_TIMEFRAMES[mode]}, "
            f"got {ptf[0]}"
        )


# ── Schema strictness: non-empty handoff evidence ──────────────────────

def test_handoff_package_empty_v7_gate_mapping_rejected():
    """P0.8E: empty v7_gate_mapping object must not validate."""
    schema = load_json(SCHEMAS_DIR / "v7_handoff_package.schema.json")
    fixture = load_json(FIXTURES_DIR / "v7_handoff_package_minimal.json")

    bad = dict(fixture)
    bad["v7_gate_mapping"] = {}
    ok, _ = _reject_empty(bad, schema)
    assert not ok, "Empty v7_gate_mapping should be rejected"


# ── Registry completeness check ────────────────────────────────────────

def test_registry_alphaforge_label_has_fixture():
    """P0.8E: AlphaForgeLabel must have a fixture file in registry."""
    registry = load_json(ROOT / "contracts" / "registry.json")
    for contract in registry["contracts"]:
        if contract["object_name"] == "AlphaForgeLabel":
            assert contract["fixture_file"] is not None, (
                "AlphaForgeLabel must have fixture_file in registry"
            )
            fixture_path = ROOT / contract["fixture_file"]
            assert fixture_path.exists(), (
                f"AlphaForgeLabel fixture missing: {contract['fixture_file']}"
            )
            break
    else:
        pytest.fail("AlphaForgeLabel not found in registry")


# ── MHT presence in mode report fixtures ───────────────────────────────

def test_all_mode_fixtures_have_mht_block():
    """P0.8E: every mode research report fixture must have multiple_hypothesis_control."""
    for fixture_file in [
        "scalp_mode_research_report_minimal.json",
        "aggressive_scalp_mode_research_report_minimal.json",
        "swing_mode_research_report_minimal.json",
    ]:
        report = load_json(FIXTURES_DIR / fixture_file)
        mht = report.get("multiple_hypothesis_control")
        assert mht is not None, f"{fixture_file} missing multiple_hypothesis_control"
        assert "tested_hypothesis_count" in mht, f"{fixture_file} MHT missing tested_hypothesis_count"
        assert "correction_method" in mht, f"{fixture_file} MHT missing correction_method"
        assert "data_snooping_risk_flag" in mht, f"{fixture_file} MHT missing data_snooping_risk_flag"


def test_mode_fixtures_have_v7_gate_readiness():
    """P0.8E: every mode report fixture must have v7_gate_readiness block."""
    for fixture_file in [
        "scalp_mode_research_report_minimal.json",
        "aggressive_scalp_mode_research_report_minimal.json",
        "swing_mode_research_report_minimal.json",
    ]:
        report = load_json(FIXTURES_DIR / fixture_file)
        assert "v7_gate_readiness" in report, f"{fixture_file} missing v7_gate_readiness"
        v7gr = report["v7_gate_readiness"]
        assert "gates_mapped" in v7gr, f"{fixture_file} v7_gate_readiness missing gates_mapped"
        assert "overall_readiness" in v7gr, f"{fixture_file} v7_gate_readiness missing overall_readiness"
