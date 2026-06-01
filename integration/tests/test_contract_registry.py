"""
test_contract_registry.py — Validate contracts/ directory integrity.

Checks:
- registry.json is valid JSON and has expected structure.
- Every referenced schema_file exists and is valid JSON.
- Every referenced fixture_file exists (if not null).
- compatibility.json is valid JSON and references known contract IDs.
- Every schema file parses as valid JSON with $schema and type.
"""

import json
import os
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONTRACTS_DIR = os.path.join(REPO_ROOT, "contracts")
KNOWN_DOMAINS = {"lib", "simulation", "alphaforge", "v7"}


def _load_json(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def _file_exists(rel_path: str) -> bool:
    return os.path.isfile(os.path.join(REPO_ROOT, rel_path))


class TestContractRegistry:
    """Validate the root contract registry."""

    def test_registry_json_is_valid(self):
        """registry.json must be parseable JSON."""
        registry = _load_json(os.path.join(CONTRACTS_DIR, "registry.json"))
        assert "contracts" in registry, "registry.json missing 'contracts' key"
        assert isinstance(registry["contracts"], list), "registry.contracts must be a list"
        assert len(registry["contracts"]) >= 4, "Expected at least 4 contracts in registry"

    def test_registry_has_required_contracts(self):
        """Registry must include all four known contract objects."""
        registry = _load_json(os.path.join(CONTRACTS_DIR, "registry.json"))
        names = {c["object_name"] for c in registry["contracts"]}
        required = {"SimulationProfile", "SimulationOutput", "AlphaForgeLabel", "TradeOutcome"}
        missing = required - names
        assert not missing, f"Registry missing required contracts: {missing}"

    def test_every_schema_file_exists(self):
        """Every registry entry's schema_file must exist on disk."""
        registry = _load_json(os.path.join(CONTRACTS_DIR, "registry.json"))
        for contract in registry["contracts"]:
            schema_path = contract["schema_file"]
            assert _file_exists(schema_path), (
                f"Schema file missing for {contract['object_name']}: {schema_path}"
            )

    def test_every_fixture_file_exists(self):
        """Every registry entry with a fixture_file must have it on disk."""
        registry = _load_json(os.path.join(CONTRACTS_DIR, "registry.json"))
        for contract in registry["contracts"]:
            if contract.get("fixture_file") is not None:
                fixture_path = contract["fixture_file"]
                assert _file_exists(fixture_path), (
                    f"Fixture file missing for {contract['object_name']}: {fixture_path}"
                )

    def test_every_owner_domain_known(self):
        """Every contract's owner_domain must be a known domain."""
        registry = _load_json(os.path.join(CONTRACTS_DIR, "registry.json"))
        for contract in registry["contracts"]:
            owner = contract["owner_domain"]
            assert owner in KNOWN_DOMAINS, (
                f"Unknown owner_domain '{owner}' for {contract['object_name']}"
            )

    def test_every_consumer_known(self):
        """Every contract's consumers must be known domains."""
        registry = _load_json(os.path.join(CONTRACTS_DIR, "registry.json"))
        for contract in registry["contracts"]:
            for consumer in contract.get("consumers", []):
                assert consumer in KNOWN_DOMAINS, (
                    f"Unknown consumer '{consumer}' for {contract['object_name']}"
                )

    def test_every_schema_is_valid_json(self):
        """Every schema file must be parseable JSON with $schema and type."""
        registry = _load_json(os.path.join(CONTRACTS_DIR, "registry.json"))
        for contract in registry["contracts"]:
            schema_path = contract["schema_file"]
            schema = _load_json(os.path.join(REPO_ROOT, schema_path))
            assert "$schema" in schema, (
                f"Schema missing $schema: {schema_path}"
            )
            assert "type" in schema, (
                f"Schema missing type: {schema_path}"
            )


class TestCompatibilityMatrix:
    """Validate the compatibility matrix."""

    def test_compatibility_json_is_valid(self):
        """compatibility.json must be parseable JSON."""
        compat = _load_json(os.path.join(CONTRACTS_DIR, "compatibility.json"))
        assert "compatibility_rules" in compat, "compatibility.json missing 'compatibility_rules'"
        assert isinstance(compat["compatibility_rules"], list)
        assert len(compat["compatibility_rules"]) >= 3, "Expected at least 3 compatibility rules"

    def test_compatibility_references_known_contracts(self):
        """Every compatibility rule must reference known contract IDs."""
        registry = _load_json(os.path.join(CONTRACTS_DIR, "registry.json"))
        known_names = {c["object_name"] for c in registry["contracts"]}
        compat = _load_json(os.path.join(CONTRACTS_DIR, "compatibility.json"))
        for rule in compat["compatibility_rules"]:
            src = rule["source_contract"]
            tgt = rule["target_contract"]
            assert src in known_names, f"Unknown source_contract in compatibility: {src}"
            assert tgt in known_names, f"Unknown target_contract in compatibility: {tgt}"

    def test_compatibility_has_required_pairs(self):
        """Must define compatibility for the three required pairs."""
        compat = _load_json(os.path.join(CONTRACTS_DIR, "compatibility.json"))
        pairs = {(r["source_contract"], r["target_contract"]) for r in compat["compatibility_rules"]}
        required = {
            ("SimulationOutput", "AlphaForgeLabel"),
            ("SimulationOutput", "TradeOutcome"),
            ("SimulationProfile", "SimulationOutput"),
        }
        missing = required - pairs
        assert not missing, f"Compatibility missing required pairs: {missing}"

    def test_contracts_dir_has_no_python_files(self):
        """contracts/ must contain no Python source files (passive authority)."""
        py_files = []
        for root, dirs, files in os.walk(CONTRACTS_DIR):
            for f in files:
                if f.endswith(".py"):
                    py_files.append(os.path.join(root, f))
        assert not py_files, (
            f"contracts/ must contain no Python files. Found: {py_files}"
        )
