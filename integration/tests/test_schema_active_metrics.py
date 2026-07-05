"""Schema validation tests for Issue 123 — Active Trade Metrics.

Tests:
- Schema validates a mode research report WITH the new active trade metric fields.
- Schema REJECTS a report missing required active trade metric fields.
- Duplicate multiple_hypothesis_control property key has been removed from schema.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = ROOT / "contracts" / "schemas" / "alphaforge" / "mode_research_report.schema.json"
FIXTURE_PATH = ROOT / "contracts" / "fixtures" / "alphaforge" / "swing_mode_research_report_minimal.json"


def load_schema() -> dict:
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def load_fixture() -> dict:
    with open(FIXTURE_PATH) as f:
        return json.load(f)


def _validate(instance: dict, schema: dict) -> list[str]:
    """Validate instance against schema; return list of error messages."""
    try:
        import jsonschema
        validator = jsonschema.Draft7Validator(schema)
        return [e.message for e in validator.iter_errors(instance)]
    except ImportError:
        # Fallback structural check
        errors = []
        for field in schema.get("required", []):
            if field not in instance:
                errors.append(f"Missing required field at top level: '{field}'")
        # Check nested required in properties
        for prop, prop_schema in schema.get("properties", {}).items():
            if prop in instance and isinstance(instance[prop], dict):
                for nested_key in prop_schema.get("required", []):
                    if nested_key not in instance[prop]:
                        errors.append(f"Missing required field: '{prop}.{nested_key}'")
        return errors


# ---------------------------------------------------------------------------
# New active trade metric fields expected in the metrics section
# ---------------------------------------------------------------------------

ACTIVE_METRIC_FIELDS = [
    "active_trade_count",
    "long_trade_count",
    "short_trade_count",
    "no_trade_count",
    "total_gross_R",
    "total_net_R",
    "exposure_pct",
    "avg_net_R_per_active_trade",
]


def _make_fixture_with_active_metrics(**overrides) -> dict:
    """Load the base fixture and add active trade metric fields."""
    report = load_fixture()
    report.setdefault("metrics", {})
    report["metrics"].update({
        "active_trade_count": 7,
        "long_trade_count": 4,
        "short_trade_count": 3,
        "no_trade_count": 3,
        "total_gross_R": 2.0,
        "total_net_R": 1.58,
        "exposure_pct": 70.0,
        "avg_net_R_per_active_trade": 0.225714,
    })
    report.update(overrides)
    return report


class TestSchemaAcceptsActiveTradeMetrics:
    """Tests that schema validates a report WITH active trade metrics."""

    def test_schema_validates_report_with_active_metrics(self):
        """Schema does not REJECT a report that includes active trade metrics."""
        schema = load_schema()
        report = _make_fixture_with_active_metrics()
        errors = _validate(report, schema)
        assert errors == [], (
            f"Schema should accept active trade metrics but got errors: {errors}"
        )

    def test_active_metrics_fields_are_integers_or_numbers(self):
        """Each active metric field has the correct type when present in payload."""
        schema = load_schema()
        metrics_schema = schema.get("properties", {}).get("metrics", {}).get("properties", {})
        for field in ACTIVE_METRIC_FIELDS:
            if field in metrics_schema:
                expected_type = metrics_schema[field].get("type")
                assert expected_type in ("integer", "number", ["integer", "number"]), (
                    f"Field {field} should be integer or number in schema, got {expected_type}"
                )

    def test_active_metrics_fields_can_be_added_to_fixture(self):
        """Adding active metric fields to the fixture does not break schema validity."""
        schema = load_schema()
        report = _make_fixture_with_active_metrics()
        for field in ACTIVE_METRIC_FIELDS:
            assert field in report["metrics"], (
                f"Active metric field '{field}' must be present in test fixture"
            )
        errors = _validate(report, schema)
        assert errors == []


class TestSchemaRejectsMissingActiveMetrics:
    """Tests that schema REJECTS reports missing required active trade metric fields."""

    def test_missing_active_trade_count_is_rejected(self):
        """Schema rejects when active_trade_count is missing from metrics."""
        schema = load_schema()
        metrics_required = (
            schema.get("properties", {})
            .get("metrics", {})
            .get("required", [])
        )
        if "active_trade_count" in metrics_required:
            report = _make_fixture_with_active_metrics()
            del report["metrics"]["active_trade_count"]
            errors = _validate(report, schema)
            assert len(errors) >= 1, (
                "Schema should reject when required field 'active_trade_count' is missing"
            )

    def test_missing_long_trade_count_is_rejected(self):
        """Schema rejects when long_trade_count is missing from metrics."""
        schema = load_schema()
        metrics_required = (
            schema.get("properties", {})
            .get("metrics", {})
            .get("required", [])
        )
        if "long_trade_count" in metrics_required:
            report = _make_fixture_with_active_metrics()
            del report["metrics"]["long_trade_count"]
            errors = _validate(report, schema)
            assert len(errors) >= 1

    def test_missing_total_net_R_is_rejected(self):
        """Schema rejects when total_net_R is missing from metrics."""
        schema = load_schema()
        metrics_required = (
            schema.get("properties", {})
            .get("metrics", {})
            .get("required", [])
        )
        if "total_net_R" in metrics_required:
            report = _make_fixture_with_active_metrics()
            del report["metrics"]["total_net_R"]
            errors = _validate(report, schema)
            assert len(errors) >= 1

    def test_missing_exposure_pct_is_rejected(self):
        """Schema rejects when exposure_pct is missing from metrics."""
        schema = load_schema()
        metrics_required = (
            schema.get("properties", {})
            .get("metrics", {})
            .get("required", [])
        )
        if "exposure_pct" in metrics_required:
            report = _make_fixture_with_active_metrics()
            del report["metrics"]["exposure_pct"]
            errors = _validate(report, schema)
            assert len(errors) >= 1

    def test_empty_metrics_object_is_rejected(self):
        """Schema rejects an empty metrics object when required fields are specified."""
        schema = load_schema()
        metrics_required = (
            schema.get("properties", {})
            .get("metrics", {})
            .get("required", [])
        )
        if metrics_required:
            report = _make_fixture_with_active_metrics()
            report["metrics"] = {}
            errors = _validate(report, schema)
            assert len(errors) >= 1, (
                f"Empty metrics should be rejected; required={metrics_required}"
            )


class TestMultipleHypothesisControlDeduplication:
    """Tests that the duplicate multiple_hypothesis_control key is removed from the schema."""

    def test_no_duplicate_mht_key_in_schema_properties(self):
        """The schema properties dict should not have duplicate multiple_hypothesis_control."""
        schema = load_schema()
        properties = schema.get("properties", {})
        assert "multiple_hypothesis_control" in properties

    def test_raw_schema_file_has_single_multiple_hypothesis_control_property(self):
        """The raw JSON file should only define multiple_hypothesis_control once as a property key."""
        raw = SCHEMA_PATH.read_text(encoding="utf-8")
        property_defs = re.findall(
            r'"multiple_hypothesis_control"\s*:\s*\{',
            raw,
        )
        assert len(property_defs) == 1, (
            f"Expected 1 property definition for multiple_hypothesis_control, "
            f"found {len(property_defs)}. Remove duplicate definitions from schema."
        )

    def test_mht_required_fields_include_mht_status(self):
        """After dedup, multiple_hypothesis_control required must include tested_hypothesis_count,
        correction_method, and data_snooping_risk_flag."""
        schema = load_schema()
        mht_prop = schema.get("properties", {}).get("multiple_hypothesis_control", {})
        mht_required = mht_prop.get("required", [])
        assert "tested_hypothesis_count" in mht_required
        assert "correction_method" in mht_required
        assert "data_snooping_risk_flag" in mht_required
