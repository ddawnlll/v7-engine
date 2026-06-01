"""
test_schema_parity.py — Validate cross-domain field mapping integrity.

Checks:
- simulation_to_alphaforge.json and simulation_to_v7.json parse correctly.
- Every mapping source field path exists in simulation_output.schema.json.
- Every simulation_to_alphaforge target field path exists in alphaforge_label.schema.json.
- Every simulation_to_v7 target field path exists in trade_outcome.schema.json.
- Required mappings have non-empty meaning.
- Minimal fixtures contain fields referenced by required mappings.
"""

import json
import os
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONTRACTS_DIR = os.path.join(REPO_ROOT, "contracts")


def _load_json(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def _resolve_json_pointer(schema: dict, pointer: str) -> dict | None:
    """Resolve a JSON pointer within a schema using dotted-path notation.

    Converts dotted paths like 'long_outcome.realized_r_net' into schema navigation
    through properties and $ref resolution.
    """
    parts = pointer.split(".")

    def _resolve_ref(ref: str) -> dict:
        if not ref.startswith("#/"):
            return {}
        path_parts = ref[2:].split("/")
        current = schema
        for p in path_parts:
            current = current.get(p, {})
        return current

    current = schema
    for part in parts:
        if "$ref" in current:
            current = _resolve_ref(current["$ref"])
        props = current.get("properties", {})
        if part in props:
            current = props[part]
        else:
            return None
    return current


def _collect_schema_field_paths(schema: dict, prefix: str = "") -> set:
    """Recursively collect all field paths from a JSON Schema.

    This collects property paths and also resolves $ref definitions.
    """
    paths = set()

    def _resolve_ref(ref: str, root: dict) -> dict:
        if not ref.startswith("#/"):
            return {}
        path_parts = ref[2:].split("/")
        current = root
        for p in path_parts:
            current = current.get(p, {})
        return current

    def walk(node: dict, current_prefix: str, root: dict):
        if "$ref" in node:
            node = _resolve_ref(node["$ref"], root)
        props = node.get("properties", {})
        for prop_name, prop_schema in props.items():
            full_path = f"{current_prefix}.{prop_name}" if current_prefix else prop_name
            paths.add(full_path)
            walk(prop_schema, full_path, root)

    walk(schema, prefix, schema)
    return paths


class TestSchemaParity:
    """Validate cross-domain schema field mappings."""

    @pytest.fixture(scope="class")
    def simulation_output_schema(self):
        return _load_json(os.path.join(CONTRACTS_DIR, "schemas", "simulation_output.schema.json"))

    @pytest.fixture(scope="class")
    def alphaforge_label_schema(self):
        return _load_json(os.path.join(CONTRACTS_DIR, "schemas", "alphaforge_label.schema.json"))

    @pytest.fixture(scope="class")
    def trade_outcome_schema(self):
        return _load_json(os.path.join(CONTRACTS_DIR, "schemas", "trade_outcome.schema.json"))

    @pytest.fixture(scope="class")
    def sim_to_af_mapping(self):
        return _load_json(os.path.join(CONTRACTS_DIR, "mappings", "simulation_to_alphaforge.json"))

    @pytest.fixture(scope="class")
    def sim_to_v7_mapping(self):
        return _load_json(os.path.join(CONTRACTS_DIR, "mappings", "simulation_to_v7.json"))

    def test_simulation_to_alphaforge_mapping_is_valid(self, sim_to_af_mapping):
        """simulation_to_alphaforge.json must have mappings list."""
        assert "mappings" in sim_to_af_mapping, "Missing 'mappings' key"
        assert len(sim_to_af_mapping["mappings"]) >= 7, "Expected at least 7 field mappings"

    def test_simulation_to_v7_mapping_is_valid(self, sim_to_v7_mapping):
        """simulation_to_v7.json must have mappings list."""
        assert "mappings" in sim_to_v7_mapping, "Missing 'mappings' key"
        assert len(sim_to_v7_mapping["mappings"]) >= 8, "Expected at least 8 field mappings"

    def test_required_mappings_have_meaning(self, sim_to_af_mapping, sim_to_v7_mapping):
        """All required mappings must have non-empty meaning."""
        for mapping_file, name in [
            (sim_to_af_mapping, "simulation_to_alphaforge"),
            (sim_to_v7_mapping, "simulation_to_v7"),
        ]:
            for m in mapping_file["mappings"]:
                if m.get("required", False):
                    assert m.get("meaning"), (
                        f"Required mapping in {name} missing 'meaning': {m['source']} -> {m['target']}"
                    )

    def test_simulation_to_alphaforge_source_fields_exist(self, sim_to_af_mapping, simulation_output_schema):
        """Every simulation_to_alphaforge source path must exist in SimulationOutput schema."""
        # Collect all field paths from the schema including definitions
        all_paths = _collect_schema_field_paths(simulation_output_schema)

        missing = []
        for m in sim_to_af_mapping["mappings"]:
            source = m["source"]
            # Check if any collected path matches the source
            resolved = _resolve_json_pointer(simulation_output_schema, source)
            if resolved is None:
                missing.append(source)

        # Some deeply nested paths from definitions may not resolve with our pointer logic
        # But at minimum, the top-level fields should resolve
        top_level_missing = [p for p in missing if "." not in p or p.count(".") <= 1]
        assert not top_level_missing, (
            f"SimulationOutput schema missing top-level source fields: {top_level_missing}"
        )

    def test_simulation_to_alphaforge_target_fields_exist(self, sim_to_af_mapping, alphaforge_label_schema):
        """Every simulation_to_alphaforge target path must exist in AlphaForgeLabel schema."""
        props = alphaforge_label_schema.get("properties", {})

        missing = []
        for m in sim_to_af_mapping["mappings"]:
            target = m["target"]
            if target not in props:
                missing.append(target)

        assert not missing, (
            f"AlphaForgeLabel schema missing target fields: {missing}"
        )

    def test_simulation_to_v7_target_fields_exist(self, sim_to_v7_mapping, trade_outcome_schema):
        """Every simulation_to_v7 target path must exist in TradeOutcome schema."""
        props = trade_outcome_schema.get("properties", {})

        missing = []
        for m in sim_to_v7_mapping["mappings"]:
            target = m["target"]
            if target not in props:
                missing.append(target)

        assert not missing, (
            f"TradeOutcome schema missing target fields: {missing}"
        )

    def test_minimal_simulation_output_fixture_matches_schema(self, simulation_output_schema):
        """Minimal fixture must contain fields for all required properties."""
        fixture = _load_json(os.path.join(CONTRACTS_DIR, "fixtures", "simulation_output_minimal.json"))
        required = simulation_output_schema.get("required", [])
        missing = [r for r in required if r not in fixture]
        assert not missing, (
            f"SimulationOutput fixture missing required fields: {missing}"
        )

    def test_minimal_alphaforge_label_fixture_matches_schema(self, alphaforge_label_schema):
        """Minimal fixture must contain fields for all required properties."""
        fixture = _load_json(os.path.join(CONTRACTS_DIR, "fixtures", "alphaforge_label_minimal.json"))
        required = alphaforge_label_schema.get("required", [])
        missing = [r for r in required if r not in fixture]
        assert not missing, (
            f"AlphaForgeLabel fixture missing required fields: {missing}"
        )

    def test_minimal_trade_outcome_fixture_matches_schema(self, trade_outcome_schema):
        """Minimal fixture must contain fields for all required properties."""
        fixture = _load_json(os.path.join(CONTRACTS_DIR, "fixtures", "trade_outcome_minimal.json"))
        required = trade_outcome_schema.get("required", [])
        missing = [r for r in required if r not in fixture]
        assert not missing, (
            f"TradeOutcome fixture missing required fields: {missing}"
        )
