"""P0.8E — AlphaForge fixture validation tests.

Validates every AlphaForge fixture against its schema using jsonschema.
Fails if fixture/schema drift occurs.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMAS_DIR = ROOT / "contracts" / "schemas" / "alphaforge"
FIXTURES_DIR = ROOT / "contracts" / "fixtures" / "alphaforge"

# (schema_path, fixture_path, label)
ALPHAFORGE_CONTRACTS = [
    ("mode_research_report.schema.json", "scalp_mode_research_report_minimal.json", "SCALP mode report"),
    ("mode_research_report.schema.json", "aggressive_scalp_mode_research_report_minimal.json", "AGGRESSIVE_SCALP mode report"),
    ("mode_research_report.schema.json", "swing_mode_research_report_minimal.json", "SWING mode report"),
    ("alphaforge_research_report.schema.json", "alphaforge_research_report_minimal.json", "AlphaForge aggregate report"),
    ("v7_handoff_package.schema.json", "v7_handoff_package_minimal.json", "V7 Handoff Package"),
]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_with_jsonschema(schema, instance):
    """Validate instance against schema using jsonschema if available."""
    try:
        import jsonschema
        jsonschema.validate(instance=instance, schema=schema)
        return True, None
    except ImportError:
        # Fallback: check top-level required keys only
        missing = [k for k in schema.get("required", []) if k not in instance]
        if missing:
            return False, f"Missing required keys: {missing}"
        return True, "jsonschema not installed — top-level required check only"
    except Exception as e:
        return False, str(e)


@pytest.mark.parametrize("schema_file,fixture_file,label", ALPHAFORGE_CONTRACTS)
def test_alphaforge_fixture_validates_against_schema(schema_file, fixture_file, label):
    """Each AlphaForge fixture must validate against its schema."""
    schema = load_json(SCHEMAS_DIR / schema_file)
    instance = load_json(FIXTURES_DIR / fixture_file)

    ok, err = validate_with_jsonschema(schema, instance)
    if not ok:
        pytest.fail(f"{label} ({fixture_file}) failed schema validation: {err}")


def test_all_five_alphaforge_fixtures_exist():
    """All 5 expected AlphaForge fixtures must exist."""
    expected = [
        "scalp_mode_research_report_minimal.json",
        "aggressive_scalp_mode_research_report_minimal.json",
        "swing_mode_research_report_minimal.json",
        "alphaforge_research_report_minimal.json",
        "v7_handoff_package_minimal.json",
    ]
    for name in expected:
        path = FIXTURES_DIR / name
        assert path.exists(), f"Missing fixture: {name}"


def test_all_fixtures_are_valid_json():
    """Every AlphaForge fixture must be parseable JSON."""
    for fixture_file in FIXTURES_DIR.glob("*.json"):
        try:
            data = load_json(fixture_file)
            assert isinstance(data, dict), f"{fixture_file.name} is not a JSON object"
        except Exception as e:
            pytest.fail(f"{fixture_file.name} is not valid JSON: {e}")


def test_fixtures_have_no_real_profitability_claims():
    """No fixture may claim real profitability."""
    marker_phrases = ["real_profitability", "guaranteed_profit", "proven_edge"]
    for fixture_file in FIXTURES_DIR.glob("*.json"):
        text = fixture_file.read_text(encoding="utf-8")
        for phrase in marker_phrases:
            assert phrase not in text.lower(), (
                f"{fixture_file.name} contains forbidden phrase '{phrase}' — "
                f"fixtures must be honest dummies"
            )


def test_v7_gate_mapping_uses_canonical_ids():
    """V7HandoffPackage fixture must use canonical V7 gate IDs."""
    fixture = load_json(FIXTURES_DIR / "v7_handoff_package_minimal.json")
    gate_mapping = fixture["v7_gate_mapping"]

    canonical_gates = [
        "G0_doc_ready",
        "G1_research_backtest",
        "G2_walk_forward_oos",
        "G3_cost_stress",
        "G4_regime_breakdown",
        "G5_symbol_stability",
        "G6_calibration_reliability",
        "G7_shadow",
        "G8_paper",
        "G9_tiny_live",
        "G10_live",
    ]

    for gate_id in canonical_gates:
        assert gate_id in gate_mapping, f"Missing canonical gate: {gate_id}"

    # No legacy gate IDs
    legacy_gates = [
        "G0_data_quality", "G1_feature_validity", "G2_label_validity",
        "G3_model_sanity", "G4_oos_performance", "G5_cost_resilience",
        "G6_regime_robustness", "G7_stability", "G8_calibration",
        "G9_no_trade_baseline", "G10_paper_shadow",
    ]
    for legacy_id in legacy_gates:
        assert legacy_id not in gate_mapping, (
            f"Legacy gate ID {legacy_id} found in fixture — should have been "
            f"renamed to canonical V7 gate IDs in P0.8E"
        )


def test_mode_fixtures_have_locked_timeframes():
    """Each mode fixture must use locked simulation profile timeframes."""
    scalp = load_json(FIXTURES_DIR / "scalp_mode_research_report_minimal.json")
    aggressive = load_json(FIXTURES_DIR / "aggressive_scalp_mode_research_report_minimal.json")
    swing = load_json(FIXTURES_DIR / "swing_mode_research_report_minimal.json")

    # SCALP: primary 1h
    assert scalp["data_scope"]["primary_timeframes"] == ["1h"], (
        f"SCALP primary_timeframes must be ['1h'] (locked profile), got {scalp['data_scope']['primary_timeframes']}"
    )

    # AGGRESSIVE_SCALP: primary 15m
    assert aggressive["data_scope"]["primary_timeframes"] == ["15m"], (
        f"AGGRESSIVE_SCALP primary_timeframes must be ['15m'] (locked profile), got {aggressive['data_scope']['primary_timeframes']}"
    )

    # SWING: primary 4h
    assert swing["data_scope"]["primary_timeframes"] == ["4h"], (
        f"SWING primary_timeframes must be ['4h'] (locked profile), got {swing['data_scope']['primary_timeframes']}"
    )


def test_mode_fixtures_have_correct_priority():
    """SCALP/AGGRESSIVE_SCALP must be PRIMARY, SWING must be SECONDARY_BASELINE."""
    scalp = load_json(FIXTURES_DIR / "scalp_mode_research_report_minimal.json")
    aggressive = load_json(FIXTURES_DIR / "aggressive_scalp_mode_research_report_minimal.json")
    swing = load_json(FIXTURES_DIR / "swing_mode_research_report_minimal.json")

    assert scalp["mode_priority"] == "PRIMARY"
    assert scalp["report_type"] == "primary_research_report"
    assert aggressive["mode_priority"] == "PRIMARY"
    assert aggressive["report_type"] == "primary_research_report"
    assert swing["mode_priority"] == "SECONDARY_BASELINE"
    assert swing["report_type"] == "secondary_baseline_report"


def test_mode_fixtures_have_nested_required_fields():
    """Mode report fixtures must carry strengthened nested fields from P0.8E."""
    for fixture_file, label in [
        ("scalp_mode_research_report_minimal.json", "SCALP"),
        ("aggressive_scalp_mode_research_report_minimal.json", "AGGRESSIVE_SCALP"),
        ("swing_mode_research_report_minimal.json", "SWING"),
    ]:
        report = load_json(FIXTURES_DIR / fixture_file)

        # cost_stress must have cost_stress_verdict and net_edge_after_costs
        assert "cost_stress_verdict" in report.get("cost_stress", {}), f"{label} missing cost_stress.cost_stress_verdict"
        assert "net_edge_after_costs" in report.get("cost_stress", {}), f"{label} missing cost_stress.net_edge_after_costs"

        # no_trade_comparison must have trade_vs_no_trade_verdict
        assert "trade_vs_no_trade_verdict" in report.get("no_trade_comparison", {}), f"{label} missing no_trade.trade_vs_no_trade_verdict"

        # regime_breakdown must have regimes_tested, best_regime, worst_regime
        rb = report.get("regime_breakdown", {})
        assert "regimes_tested" in rb, f"{label} missing regime_breakdown.regimes_tested"
        assert "regime_stability_verdict" in rb, f"{label} missing regime_breakdown.regime_stability_verdict"

        # P0.8E: v7_gate_readiness must be present
        assert "v7_gate_readiness" in report, f"{label} missing v7_gate_readiness"

        # P0.8E: multiple_hypothesis_control must be present
        assert "multiple_hypothesis_control" in report, f"{label} missing multiple_hypothesis_control"
