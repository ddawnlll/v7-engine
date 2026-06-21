"""P0.9A — AlphaForge contract loader tests."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
AF_SRC = REPO / "alphaforge" / "src"
if str(AF_SRC) not in sys.path:
    sys.path.insert(0, str(AF_SRC))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import pytest
from alphaforge.contracts.loader import (
    load_schema,
    load_fixture,
    load_registry,
    load_compatibility,
    load_mapping,
    list_schemas,
    list_fixtures,
    SCHEMA_FIXTURE_MAP,
    load_all_fixtures_for_schema,
)
from alphaforge.contracts.validator import (
    validate_payload,
    validate_fixture,
    validate_all_known_fixtures,
    is_fixture_valid,
    ValidationResult,
)
from alphaforge.contracts.registry import (
    get_alphaforge_contracts,
    check_required_contracts_registered,
    validate_registry,
    get_contract_by_name,
    REQUIRED_ALPHAFORGE_CONTRACTS,
)
from alphaforge.errors import ContractLoadError


# ── Schema loading ──────────────────────────────────────────────────────

def test_all_required_schemas_load():
    """All 10 AlphaForge schemas must be loadable."""
    schemas = list_schemas()
    assert len(schemas) >= 10, f"Expected >= 10 schemas, got {len(schemas)}: {schemas}"
    for name in schemas:
        schema = load_schema(name)
        assert isinstance(schema, dict)
        assert "$schema" in schema or "title" in schema


def test_missing_schema_raises():
    """Loading a nonexistent schema must raise ContractLoadError."""
    with pytest.raises(ContractLoadError):
        load_schema("nonexistent.schema.json")


def test_invalid_json_raises():
    """Loading invalid JSON must raise ContractLoadError."""
    # Create a temp file with invalid JSON
    import tempfile
    import os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("not valid json {{{")
        tmp = f.name
    try:
        from alphaforge.contracts.loader import _load_json
        with pytest.raises(ContractLoadError):
            _load_json(Path(tmp))
    finally:
        os.unlink(tmp)


# ── Fixture loading ─────────────────────────────────────────────────────

def test_all_required_fixtures_load():
    """All 5 AlphaForge fixtures must be loadable."""
    fixtures = list_fixtures()
    assert len(fixtures) >= 5, f"Expected >= 5 fixtures, got {len(fixtures)}: {fixtures}"
    for name in fixtures:
        fixture = load_fixture(name)
        assert isinstance(fixture, dict)


def test_load_all_fixtures_for_schema():
    """load_all_fixtures_for_schema returns fixtures for known schemas."""
    fixtures = load_all_fixtures_for_schema("mode_research_report.schema.json")
    assert len(fixtures) == 3  # SCALP, AGGRESSIVE_SCALP, SWING


# ── Registry ────────────────────────────────────────────────────────────

def test_registry_loads():
    """Registry must be loadable."""
    registry = load_registry()
    assert "contracts" in registry


def test_all_alphaforge_contracts_registered():
    """All required AlphaForge contracts must be in the registry."""
    missing = validate_registry()
    assert not missing, f"Registry validation errors: {missing}"


def test_check_required_contracts():
    """check_required_contracts_registered returns True for all required."""
    check = check_required_contracts_registered()
    for name, present in check.items():
        assert present, f"Required contract {name} not in registry"


def test_get_contract_by_name():
    """Can look up individual contracts."""
    c = get_contract_by_name("V7HandoffPackage")
    assert c is not None
    assert c["owner_domain"] == "alphaforge"


# ── Validation ──────────────────────────────────────────────────────────

def test_validate_all_known_fixtures_pass():
    """All known fixtures must validate against their schemas."""
    results = validate_all_known_fixtures()
    for schema_name, schema_results in results.items():
        for i, result in enumerate(schema_results):
            assert result.valid, (
                f"Fixture {i+1} for {schema_name} failed: {result.errors}"
            )


def test_validate_fixture_specific():
    """Validate specific schema-fixture pairs."""
    assert is_fixture_valid(
        "mode_research_report.schema.json",
        "scalp_mode_research_report_minimal.json",
    )
    assert is_fixture_valid(
        "v7_handoff_package.schema.json",
        "v7_handoff_package_minimal.json",
    )


def test_validation_result_bool():
    """ValidationResult is truthy/falsy correctly."""
    ok = ValidationResult(True, [])
    fail = ValidationResult(False, ["error"])
    assert ok
    assert not fail


def test_missing_required_field_detected():
    """Basic validation must detect missing required fields."""
    schema = {"type": "object", "required": ["foo"], "properties": {"foo": {"type": "string"}}}
    result = validate_payload(schema, {}, "test")
    assert not result.valid
    assert any("foo" in e for e in result.errors)


# ── Compatibility ───────────────────────────────────────────────────────

def test_compatibility_loads():
    """Compatibility file must be loadable."""
    compat = load_compatibility()
    assert isinstance(compat, dict)


# ── Mapping docs ────────────────────────────────────────────────────────

def test_alphaforge_to_v7_mapping_loads():
    """AlphaForge→V7 mapping doc must be readable."""
    text = load_mapping("alphaforge_to_v7.md")
    assert "G0_doc_ready" in text or "G0" in text
    assert "DOC_READY" in text
    # Legacy gate names must NOT appear
    assert "G0_data_quality" not in text
    assert "G10_paper_shadow" not in text
