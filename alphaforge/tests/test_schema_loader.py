"""Test all expected AlphaForge schemas load, including AlphaForgeLabel."""

from alphaforge.src.alphaforge.schema_loader import (
    load_schema, load_all_alphaforge_schemas, list_schema_files,
    validate_schema_is_loadable, has_jsonschema,
)


def test_all_expected_schemas_loadable():
    expected = [
        "AlphaForgeLabel", "AlphaThesis", "AlphaCandidate",
        "FeatureSetSpec", "LabelDatasetSpec", "ModeResearchReport",
        "AlphaForgeResearchReport", "ValidationReport",
        "ModelArtifact", "CalibrationCandidate", "V7HandoffPackage",
    ]
    for name in expected:
        assert validate_schema_is_loadable(name), f"Schema {name} not loadable"


def test_alphaforge_label_schema_loads():
    schema = load_schema("AlphaForgeLabel")
    assert schema["title"] == "AlphaForgeLabel"
    props = schema["properties"]
    assert "long_R_gross" in props
    assert "short_R_gross" in props
    assert "no_trade_quality" in props
    assert "funding_status" in props
    assert "simulation_profile_id" in schema["required"]


def test_v7_handoff_package_gates_canonical():
    schema = load_schema("V7HandoffPackage")
    gate_props = schema["properties"]["v7_gate_mapping"]["properties"]
    assert "G0_doc_ready" in gate_props
    assert "G3_cost_stress" in gate_props
    assert "G10_live" in gate_props
    assert "G3_model_sanity" not in gate_props
    assert "G10_paper_shadow" not in gate_props


def test_all_alphaforge_schemas_load():
    schemas = load_all_alphaforge_schemas()
    assert len(schemas) >= 11


def test_list_schema_files():
    files = list_schema_files()
    assert len(files) >= 8


def test_has_jsonschema_info():
    assert isinstance(has_jsonschema(), bool)
