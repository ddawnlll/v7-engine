"""Test validator: valid fixtures pass, empty payloads fail, MHT blocking."""

from alphaforge.src.alphaforge.validator import (
    validate_fixture, validate_empty_payload_fails,
)


def test_valid_label_fixture_passes():
    from alphaforge.src.alphaforge.contracts import ALPHAFORGE_FIXTURES
    valid, errors = validate_fixture("AlphaForgeLabel", ALPHAFORGE_FIXTURES["AlphaForgeLabel"])
    assert valid
    assert len(errors) == 0


def test_valid_handoff_fixture_passes():
    from alphaforge.src.alphaforge.contracts import ALPHAFORGE_FIXTURES
    valid, errors = validate_fixture("V7HandoffPackage", ALPHAFORGE_FIXTURES["V7HandoffPackage"])
    assert valid
    assert len(errors) == 0


def test_empty_handoff_fails():
    assert validate_empty_payload_fails("V7HandoffPackage")


def test_empty_validation_report_fails():
    assert validate_empty_payload_fails("ValidationReport")


def test_empty_mode_research_report_fails():
    assert validate_empty_payload_fails("ModeResearchReport")


def test_empty_alphaforge_research_report_fails():
    assert validate_empty_payload_fails("AlphaForgeResearchReport")


def test_validation_report_mht_required():
    from alphaforge.src.alphaforge.schema_loader import load_schema
    schema = load_schema("ValidationReport")
    assert "multiple_hypothesis_control" in schema["required"]
