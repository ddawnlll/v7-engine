"""Test registry contains AlphaForge contracts and compatibility mapping."""

from alphaforge.registry import (
    load_registry, get_alphaforge_contracts, get_alphaforge_contract_names,
    get_contract_by_name, alphaforge_schemas_in_registry, alphaforge_consumers,
    load_compatibility,
)


def test_registry_loads():
    registry = load_registry()
    assert "contracts" in registry


def test_alphaforge_contracts_present():
    contracts = get_alphaforge_contracts()
    names = {c["object_name"] for c in contracts}
    expected = {
        "AlphaForgeLabel", "V7HandoffPackage", "ValidationReport",
        "ModeResearchReport", "AlphaForgeResearchReport",
        "AlphaThesis", "AlphaCandidate", "FeatureSetSpec",
        "LabelDatasetSpec", "ModelArtifact", "CalibrationCandidate",
    }
    assert expected.issubset(names)


def test_get_alphaforge_contract_names():
    names = get_alphaforge_contract_names()
    assert "AlphaForgeLabel" in names
    assert "V7HandoffPackage" in names
    assert len(names) >= 11


def test_get_contract_by_name():
    c = get_contract_by_name("AlphaForgeLabel")
    assert c is not None
    assert c["owner_domain"] == "alphaforge"
    assert c["schema_file"] == "contracts/schemas/alphaforge_label.schema.json"


def test_alphaforge_schemas_in_registry():
    schemas = alphaforge_schemas_in_registry()
    assert "AlphaForgeLabel" in schemas


def test_alphaforge_consumers_v7():
    consumers = alphaforge_consumers()
    assert "V7HandoffPackage" in consumers
    assert "v7" in consumers["V7HandoffPackage"]


def test_compatibility_loads():
    compat = load_compatibility()
    assert isinstance(compat, dict)
