"""AlphaForge contract schema and fixture loader.

Loads JSON schemas and fixtures from the canonical contracts/ directory.
All loads are read-only — no mutation of schemas or fixtures.
"""
import json
from pathlib import Path

from alphaforge.errors import ContractLoadError
from alphaforge.paths import schemas_dir, fixtures_dir, mappings_dir, registry_path, compatibility_path


def _load_json(path: Path) -> dict:
    """Load a single JSON file. Returns dict. Raises ContractLoadError on failure."""
    if not path.exists():
        raise ContractLoadError(f"Contract file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ContractLoadError(f"Invalid JSON in {path}: {e}")
    if not isinstance(data, dict):
        raise ContractLoadError(f"Expected JSON object in {path}, got {type(data).__name__}")
    return data


def load_schema(schema_name: str) -> dict:
    """Load a schema by filename from contracts/schemas/alphaforge/.

    Args:
        schema_name: e.g. 'mode_research_report.schema.json'

    Returns:
        Schema as dict.

    Raises:
        ContractLoadError: File not found or invalid JSON.
    """
    path = schemas_dir() / schema_name
    return _load_json(path)


def load_fixture(fixture_name: str) -> dict:
    """Load a fixture by filename from contracts/fixtures/alphaforge/.

    Args:
        fixture_name: e.g. 'scalp_mode_research_report_minimal.json'

    Returns:
        Fixture as dict.

    Raises:
        ContractLoadError: File not found or invalid JSON.
    """
    path = fixtures_dir() / fixture_name
    return _load_json(path)


def load_registry() -> dict:
    """Load contracts/registry.json."""
    return _load_json(registry_path())


def load_compatibility() -> dict:
    """Load contracts/compatibility.json."""
    return _load_json(compatibility_path())


def load_mapping(mapping_name: str) -> str:
    """Load a mapping doc as text from contracts/mappings/.

    Args:
        mapping_name: e.g. 'alphaforge_to_v7.md'

    Returns:
        Content as string (not parsed, mapping docs are markdown).
    """
    path = mappings_dir() / mapping_name
    if not path.exists():
        raise ContractLoadError(f"Mapping doc not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def list_schemas() -> list[str]:
    """List all .schema.json files in the AlphaForge schemas directory."""
    sd = schemas_dir()
    if not sd.is_dir():
        return []
    return sorted([p.name for p in sd.glob("*.schema.json")])


def list_fixtures() -> list[str]:
    """List all .json files in the AlphaForge fixtures directory."""
    fd = fixtures_dir()
    if not fd.is_dir():
        return []
    return sorted([p.name for p in fd.glob("*.json")])


# Known schema → fixture mapping (P0.8E canonical)
SCHEMA_FIXTURE_MAP = {
    "mode_research_report.schema.json": [
        "scalp_mode_research_report_minimal.json",
        "aggressive_scalp_mode_research_report_minimal.json",
        "swing_mode_research_report_minimal.json",
    ],
    "alphaforge_research_report.schema.json": [
        "alphaforge_research_report_minimal.json",
    ],
    "v7_handoff_package.schema.json": [
        "v7_handoff_package_minimal.json",
    ],
}


def load_all_fixtures_for_schema(schema_name: str) -> list[dict]:
    """Load all known fixtures for a schema.

    Returns:
        List of fixture dicts. Empty list if no fixtures mapped.
    """
    fixture_names = SCHEMA_FIXTURE_MAP.get(schema_name, [])
    return [load_fixture(name) for name in fixture_names]
