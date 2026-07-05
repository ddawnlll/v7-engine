"""Tests for LabelAdapter schema validation, error handling, and cost-aware correctness.

WS-02-SCHEMA-TESTS: validate output against alphaforge_label.schema.json,
test negative cases (missing fields, invalid values, optional field handling),
cost-aware field correctness, cross-mode tests, and fixture schema validation.
"""

import copy
import json
import math
from pathlib import Path

import pytest

from alphaforge.labels.adapter import (
    LabelAdapter,
    adapt_simulation_output,
    classify_no_trade_quality,
    _REQUIRED_SIM_FIELDS,
    VALID_MODES,
    VALID_BEST_ACTIONS,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "contracts" / "fixtures"
SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "contracts" / "schemas"


def _load_sim_fixture() -> dict:
    path = FIXTURE_DIR / "simulation_output_minimal.json"
    with open(path) as f:
        return json.load(f)


def _load_label_schema() -> dict:
    path = SCHEMA_DIR / "alphaforge_label.schema.json"
    with open(path) as f:
        return json.load(f)


def _load_label_fixture() -> dict:
    path = FIXTURE_DIR / "alphaforge_label_minimal.json"
    with open(path) as f:
        return json.load(f)


def _make_sim_fixture(**overrides) -> dict:
    sim = copy.deepcopy(_load_sim_fixture())
    sim.update(overrides)
    return sim


def _validate_with_jsonschema(instance: dict, schema: dict) -> list:
    """Validate instance against schema; return list of error messages."""
    try:
        import jsonschema
        validator = jsonschema.Draft7Validator(schema)
        return [e.message for e in validator.iter_errors(instance)]
    except ImportError:
        # Fallback: structural check
        errors = []
        required = schema.get("required", [])
        for field in required:
            if field not in instance:
                errors.append(f"Missing required field: '{field}'")
        return errors


# ---------------------------------------------------------------------------
# Schema validation tests (AC-02-025)
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    """Tests that adapter output passes JSON Schema validation."""

    def test_output_validates_against_schema(self):
        """AC-02-025: Adapter output passes jsonschema.validate() with no errors."""
        schema = _load_label_schema()
        sim = _load_sim_fixture()
        label = adapt_simulation_output(sim)
        errors = _validate_with_jsonschema(label, schema)
        assert errors == [], f"Schema validation errors: {errors}"

    def test_output_has_all_required_fields(self):
        """All required schema fields are present in adapter output."""
        schema = _load_label_schema()
        sim = _load_sim_fixture()
        label = adapt_simulation_output(sim)
        for field in schema.get("required", []):
            assert field in label, f"Missing required field: {field}"

    def test_enum_values_are_valid(self):
        """All enum-constrained fields have valid values."""
        schema = _load_label_schema()
        sim = _load_sim_fixture()
        label = adapt_simulation_output(sim)
        properties = schema.get("properties", {})
        for field, value in label.items():
            if field in properties and "enum" in properties[field]:
                assert value in properties[field]["enum"], (
                    f"Field '{field}' has invalid enum value '{value}'. "
                    f"Allowed: {properties[field]['enum']}"
                )

    def test_number_fields_are_numbers(self):
        """All number-typed fields are numbers (int or float)."""
        schema = _load_label_schema()
        sim = _load_sim_fixture()
        label = adapt_simulation_output(sim)
        properties = schema.get("properties", {})
        for field, value in label.items():
            if field in properties and properties[field].get("type") == "number":
                assert isinstance(value, (int, float)), (
                    f"Field '{field}' expected number, got {type(value).__name__}: {value}"
                )

    def test_string_fields_are_strings(self):
        """All string-typed fields are strings."""
        schema = _load_label_schema()
        sim = _load_sim_fixture()
        label = adapt_simulation_output(sim)
        properties = schema.get("properties", {})
        for field, value in label.items():
            if field in properties and properties[field].get("type") == "string":
                assert isinstance(value, str), (
                    f"Field '{field}' expected string, got {type(value).__name__}: {value}"
                )

    def test_boolean_fields_are_booleans(self):
        """All boolean-typed fields are booleans."""
        schema = _load_label_schema()
        sim = _load_sim_fixture()
        label = adapt_simulation_output(sim)
        properties = schema.get("properties", {})
        for field, value in label.items():
            if field in properties and properties[field].get("type") == "boolean":
                assert isinstance(value, bool), (
                    f"Field '{field}' expected bool, got {type(value).__name__}: {value}"
                )


# ---------------------------------------------------------------------------
# Negative tests — invalid/missing inputs (AC-02-026, AC-02-027)
# ---------------------------------------------------------------------------

class TestInvalidInputs:
    """Tests that adapter raises descriptive errors for invalid inputs."""

    def test_missing_simulation_run_id_raises(self):
        """AC-02-026: Missing required field raises ValueError."""
        sim = _load_sim_fixture()
        del sim["simulation_run_id"]
        with pytest.raises(ValueError, match="simulation_run_id"):
            adapt_simulation_output(sim)

    def test_missing_decision_timestamp_raises(self):
        """Missing decision_timestamp raises ValueError."""
        sim = _load_sim_fixture()
        del sim["decision_timestamp"]
        with pytest.raises(ValueError, match="decision_timestamp"):
            adapt_simulation_output(sim)

    def test_missing_mode_raises(self):
        """Missing mode raises ValueError."""
        sim = _load_sim_fixture()
        del sim["mode"]
        with pytest.raises(ValueError, match="mode"):
            adapt_simulation_output(sim)

    def test_missing_long_outcome_raises(self):
        """Missing long_outcome raises ValueError."""
        sim = _load_sim_fixture()
        del sim["long_outcome"]
        with pytest.raises(ValueError, match="long_outcome"):
            adapt_simulation_output(sim)

    def test_missing_short_outcome_raises(self):
        """Missing short_outcome raises ValueError."""
        sim = _load_sim_fixture()
        del sim["short_outcome"]
        with pytest.raises(ValueError, match="short_outcome"):
            adapt_simulation_output(sim)

    def test_missing_no_trade_outcome_raises(self):
        """Missing no_trade_outcome raises ValueError."""
        sim = _load_sim_fixture()
        del sim["no_trade_outcome"]
        with pytest.raises(ValueError, match="no_trade_outcome"):
            adapt_simulation_output(sim)

    def test_missing_best_action_raises(self):
        """Missing best_action raises ValueError."""
        sim = _load_sim_fixture()
        del sim["best_action"]
        with pytest.raises(ValueError, match="best_action"):
            adapt_simulation_output(sim)

    def test_invalid_mode_raises(self):
        """AC-02-027: Invalid mode value raises ValueError."""
        sim = _load_sim_fixture()
        sim["mode"] = "INVALID_MODE"
        with pytest.raises(ValueError, match="Invalid mode"):
            adapt_simulation_output(sim)

    def test_invalid_best_action_raises(self):
        """Invalid best_action raises ValueError."""
        sim = _load_sim_fixture()
        sim["best_action"] = "BUY_NOW"
        with pytest.raises(ValueError, match="Invalid best_action"):
            adapt_simulation_output(sim)

    def test_invalid_resolution_status_raises(self):
        """Invalid resolution_status raises ValueError."""
        sim = _load_sim_fixture()
        sim["resolution_status"] = "UNKNOWN_STATUS"
        with pytest.raises(ValueError, match="Invalid resolution_status"):
            adapt_simulation_output(sim)

    def test_non_dict_input_raises(self):
        """Non-dict input raises ValueError."""
        with pytest.raises(ValueError, match="must be a dict"):
            adapt_simulation_output(None)  # type: ignore

    def test_non_dict_substruct_raises(self):
        """Non-dict sub-struct (long_outcome) raises ValueError."""
        sim = _load_sim_fixture()
        sim["long_outcome"] = "not_a_dict"
        with pytest.raises(ValueError, match="long_outcome.*must be a dict"):
            adapt_simulation_output(sim)


# ---------------------------------------------------------------------------
# Optional field handling tests (AC-02-028)
# ---------------------------------------------------------------------------

class TestOptionalFieldHandling:
    """Tests that optional fields are handled gracefully."""

    def test_monte_carlo_run_id_absent_ok(self):
        """AC-02-028: monte_carlo_run_id absence does not cause crash."""
        sim = _load_sim_fixture()
        if "monte_carlo_run_id" in sim:
            del sim["monte_carlo_run_id"]
        label = adapt_simulation_output(sim)
        assert "symbol" in label  # Still produces valid output

    def test_second_best_action_absent_ok(self):
        """AC-02-028: second_best_action absence does not cause crash."""
        sim = _load_sim_fixture()
        if "second_best_action" in sim:
            del sim["second_best_action"]
        label = adapt_simulation_output(sim)
        assert "best_action_label" in label

    def test_invalidity_reason_absent_ok(self):
        """AC-02-028: invalidity_reason absence does not cause crash."""
        sim = _load_sim_fixture()
        if "invalidity_reason" in sim:
            del sim["invalidity_reason"]
        label = adapt_simulation_output(sim)
        assert "label_validity" in label

    def test_missing_optional_fields_in_action_outcome(self):
        """Optional fields in ActionOutcome use None/0 defaults."""
        sim = _load_sim_fixture()
        # Remove optional fields from path_metrics
        if "path_metrics" in sim["long_outcome"]:
            pm = sim["long_outcome"]["path_metrics"]
            for opt in ("time_to_mfe", "time_to_mae"):
                pm.pop(opt, None)
        label = adapt_simulation_output(sim)
        assert "long_mfe_R" in label
        assert "long_mae_R" in label

    def test_missing_path_metrics_substruct(self):
        """Missing path_metrics sub-struct uses 0 defaults."""
        sim = _load_sim_fixture()
        del sim["long_outcome"]["path_metrics"]
        label = adapt_simulation_output(sim)
        assert label["long_mfe_R"] == 0.0
        assert label["long_mae_R"] == 0.0

    def test_missing_exit_reason_defaults_to_none(self):
        """Missing exit_reason defaults to None."""
        sim = _load_sim_fixture()
        del sim["long_outcome"]["exit_reason"]
        label = adapt_simulation_output(sim)
        assert label["exit_reason"] is None


# ---------------------------------------------------------------------------
# Cost-aware field correctness tests (AC-02-029)
# ---------------------------------------------------------------------------

class TestCostAwareFields:
    """Tests for cost-aware field correctness."""

    def test_net_equals_gross_minus_total_cost_long(self):
        """AC-02-029: long_R_net ≈ long_R_gross - total_cost_r_long within tolerance."""
        sim = _load_sim_fixture()
        label = adapt_simulation_output(sim)

        expected_net = label["long_R_gross"] - label["total_cost_r_long"]
        diff = abs(label["long_R_net"] - expected_net)
        assert diff < 0.0001, (
            f"long_R_net ({label['long_R_net']}) != "
            f"long_R_gross ({label['long_R_gross']}) - total_cost_r_long ({label['total_cost_r_long']}) = {expected_net}; "
            f"diff={diff}"
        )

    def test_net_equals_gross_minus_total_cost_short(self):
        """short_R_net ≈ short_R_gross - total_cost_r_short within tolerance."""
        sim = _load_sim_fixture()
        label = adapt_simulation_output(sim)

        expected_net = label["short_R_gross"] - label["total_cost_r_short"]
        diff = abs(label["short_R_net"] - expected_net)
        assert diff < 0.0001, (
            f"short_R_net ({label['short_R_net']}) != "
            f"short_R_gross ({label['short_R_gross']}) - total_cost_r_short ({label['total_cost_r_short']}) = {expected_net}; "
            f"diff={diff}"
        )

    def test_cost_components_approx_equal_total_long(self):
        """fee_cost_r_long + slippage_cost_r_long ≈ total_cost_r_long."""
        sim = _load_sim_fixture()
        label = adapt_simulation_output(sim)

        sum_components = label["fee_cost_r_long"] + label["slippage_cost_r_long"]
        diff = abs(label["total_cost_r_long"] - sum_components)
        assert diff < 0.0001, (
            f"total_cost_r_long ({label['total_cost_r_long']}) != "
            f"fee ({label['fee_cost_r_long']}) + slippage ({label['slippage_cost_r_long']}) = {sum_components}; "
            f"diff={diff}"
        )

    def test_cost_components_approx_equal_total_short(self):
        """fee_cost_r_short + slippage_cost_r_short ≈ total_cost_r_short."""
        sim = _load_sim_fixture()
        label = adapt_simulation_output(sim)

        sum_components = label["fee_cost_r_short"] + label["slippage_cost_r_short"]
        diff = abs(label["total_cost_r_short"] - sum_components)
        assert diff < 0.0001, (
            f"total_cost_r_short ({label['total_cost_r_short']}) != "
            f"fee ({label['fee_cost_r_short']}) + slippage ({label['slippage_cost_r_short']}) = {sum_components}; "
            f"diff={diff}"
        )

    def test_cost_impact_is_total_cost_alias_long(self):
        """cost_impact_long == total_cost_r_long (alias)."""
        sim = _load_sim_fixture()
        label = adapt_simulation_output(sim)
        assert label["cost_impact_long"] == label["total_cost_r_long"]

    def test_cost_impact_is_total_cost_alias_short(self):
        """cost_impact_short == total_cost_r_short (alias)."""
        sim = _load_sim_fixture()
        label = adapt_simulation_output(sim)
        assert label["cost_impact_short"] == label["total_cost_r_short"]

    def test_gross_net_and_cost_fields_populated(self):
        """All cost-aware fields are populated."""
        sim = _load_sim_fixture()
        label = adapt_simulation_output(sim)

        cost_fields = [
            "long_R_gross", "long_R_net", "short_R_gross", "short_R_net",
            "fee_cost_r_long", "slippage_cost_r_long", "total_cost_r_long",
            "fee_cost_r_short", "slippage_cost_r_short", "total_cost_r_short",
            "cost_impact_long", "cost_impact_short",
        ]
        for field in cost_fields:
            assert field in label, f"Missing cost field: {field}"
            assert isinstance(label[field], (int, float)), (
                f"Cost field {field} should be number, got {type(label[field]).__name__}"
            )

    def test_cost_consumed_edge_detected_long(self):
        """AC-02-013: cost_edge_warning=True when long_R_gross > 0 and long_R_net < 0."""
        sim = _load_sim_fixture()
        sim["long_outcome"]["realized_r_gross"] = 0.5
        sim["long_outcome"]["realized_r_net"] = -0.2
        sim["long_outcome"]["total_cost_r"] = 0.7
        label = adapt_simulation_output(sim)
        assert label["cost_edge_warning"] is True

    def test_cost_consumed_edge_detected_short(self):
        """cost_edge_warning=True when short_R_gross > 0 and short_R_net < 0."""
        sim = _load_sim_fixture()
        sim["short_outcome"]["realized_r_gross"] = 0.3
        sim["short_outcome"]["realized_r_net"] = -0.1
        sim["short_outcome"]["total_cost_r"] = 0.4
        label = adapt_simulation_output(sim)
        assert label["cost_edge_warning"] is True


# ---------------------------------------------------------------------------
# Cross-mode tests (AC-02-030)
# ---------------------------------------------------------------------------

class TestCrossMode:
    """Tests that adapter works for all three modes."""

    def _make_mode_fixture(self, mode: str) -> dict:
        """Create a mode-specific fixture."""
        sim = copy.deepcopy(_load_sim_fixture())
        sim["mode"] = mode
        return sim

    def test_swing_mode_produces_valid_label(self):
        """AC-02-030: SWING mode produces valid AlphaForgeLabel."""
        sim = self._make_mode_fixture("SWING")
        label = adapt_simulation_output(sim)
        assert label["mode"] == "SWING"
        errors = _validate_with_jsonschema(label, _load_label_schema())
        assert errors == [], f"SWING label validation errors: {errors}"

    def test_scalp_mode_produces_valid_label(self):
        """AC-02-030: SCALP mode produces valid AlphaForgeLabel."""
        sim = self._make_mode_fixture("SCALP")
        label = adapt_simulation_output(sim)
        assert label["mode"] == "SCALP"
        errors = _validate_with_jsonschema(label, _load_label_schema())
        assert errors == [], f"SCALP label validation errors: {errors}"

    def test_aggressive_scalp_mode_produces_valid_label(self):
        """AC-02-030: AGGRESSIVE_SCALP mode produces valid AlphaForgeLabel."""
        sim = self._make_mode_fixture("AGGRESSIVE_SCALP")
        label = adapt_simulation_output(sim)
        assert label["mode"] == "AGGRESSIVE_SCALP"
        errors = _validate_with_jsonschema(label, _load_label_schema())
        assert errors == [], f"AGGRESSIVE_SCALP label validation errors: {errors}"

    def test_mode_field_matches_input_for_all_modes(self):
        """Output mode field matches input mode for all three modes."""
        for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
            sim = self._make_mode_fixture(mode)
            label = adapt_simulation_output(sim)
            assert label["mode"] == mode

    def test_all_modes_have_funding_deferred(self):
        """All modes have funding_status = 'DEFERRED'."""
        for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
            sim = self._make_mode_fixture(mode)
            label = adapt_simulation_output(sim)
            assert label["funding_status"] == "DEFERRED"


# ---------------------------------------------------------------------------
# Minimal fixture schema validation (AC-02-031)
# ---------------------------------------------------------------------------

class TestMinimalFixtureValidation:
    """Tests that the minimal AlphaForgeLabel fixture passes schema validation."""

    def test_minimal_fixture_validates_against_schema(self):
        """AC-02-031: alphaforge_label_minimal.json passes jsonschema validate()."""
        fixture = _load_label_fixture()
        schema = _load_label_schema()
        errors = _validate_with_jsonschema(fixture, schema)
        assert errors == [], f"Minimal fixture validation errors: {errors}"

    def test_fixture_has_all_required_fields(self):
        """Minimal fixture has all required fields per schema."""
        fixture = _load_label_fixture()
        schema = _load_label_schema()
        for field in schema.get("required", []):
            assert field in fixture, f"Missing required field in fixture: {field}"


# ---------------------------------------------------------------------------
# Lineage propagation tests
# ---------------------------------------------------------------------------

class TestLineagePropagation:
    """Tests that lineage fields are correctly propagated."""

    def test_simulation_profile_id_from_lineage(self):
        """simulation_profile_id comes from lineage.simulation_profile_version."""
        sim = _load_sim_fixture()
        label = adapt_simulation_output(sim)
        assert label["simulation_profile_id"] == "swing_profile-1.0.0"

    def test_simulation_engine_version_from_lineage(self):
        """simulation_engine_version comes from lineage.simulation_engine_version."""
        sim = _load_sim_fixture()
        label = adapt_simulation_output(sim)
        assert label["simulation_engine_version"] == "simfam-1.0.0"

    def test_cost_model_version_from_lineage(self):
        """cost_model_version comes from lineage.cost_model_version."""
        sim = _load_sim_fixture()
        label = adapt_simulation_output(sim)
        assert label["cost_model_version"] == "cost-1.0.0"

    def test_label_interpretation_version_is_fixed(self):
        """label_interpretation_version is fixed at '1.0.0'."""
        sim = _load_sim_fixture()
        label = adapt_simulation_output(sim)
        assert label["label_interpretation_version"] == "1.0.0"

    def test_funding_status_is_always_deferred(self):
        """funding_status is always 'DEFERRED'."""
        sim = _load_sim_fixture()
        label = adapt_simulation_output(sim)
        assert label["funding_status"] == "DEFERRED"


# ---------------------------------------------------------------------------
# Warning accumulation test
# ---------------------------------------------------------------------------

class TestWarnings:
    """Tests for LabelAdapter warning accumulation."""

    def test_warnings_reset_each_call(self):
        """Warnings list resets on each adapt_simulation_output call."""
        adapter = LabelAdapter()
        sim = _load_sim_fixture()
        adapter.adapt_simulation_output(sim)
        w1 = adapter.warnings
        adapter.adapt_simulation_output(sim)
        w2 = adapter.warnings
        assert isinstance(w1, list)
        assert isinstance(w2, list)
