"""AlphaForge contract loading, validation, and registry helpers.

Previously contracts.py was shadowed by contracts/ directory — content
consolidated here to resolve package-vs-module conflict (P0.9B repair).
All paths relative to repo root; use PYTHONPATH=alphaforge/src:.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
CONTRACTS_DIR = REPO_ROOT / "contracts"
SCHEMAS_DIR = CONTRACTS_DIR / "schemas"
ALPHAFORGE_SCHEMAS_DIR = SCHEMAS_DIR / "alphaforge"
MAPPINGS_DIR = CONTRACTS_DIR / "mappings"
FIXTURES_DIR = CONTRACTS_DIR / "fixtures"
ALPHAFORGE_FIXTURES_DIR = FIXTURES_DIR / "alphaforge"
REPORTS_DIR = REPO_ROOT / "reports"
ACCP_DIR = REPORTS_DIR / "accp"

ALPHAFORGE_SCHEMAS: Dict[str, Path] = {
    "AlphaForgeLabel": SCHEMAS_DIR / "alphaforge_label.schema.json",
    "AlphaThesis": ALPHAFORGE_SCHEMAS_DIR / "alpha_thesis.schema.json",
    "AlphaCandidate": ALPHAFORGE_SCHEMAS_DIR / "alpha_candidate.schema.json",
    "FeatureSetSpec": ALPHAFORGE_SCHEMAS_DIR / "feature_set_spec.schema.json",
    "LabelDatasetSpec": ALPHAFORGE_SCHEMAS_DIR / "label_dataset_spec.schema.json",
    "ModeResearchReport": ALPHAFORGE_SCHEMAS_DIR / "mode_research_report.schema.json",
    "AlphaForgeResearchReport": ALPHAFORGE_SCHEMAS_DIR / "alphaforge_research_report.schema.json",
    "ValidationReport": ALPHAFORGE_SCHEMAS_DIR / "validation_report.schema.json",
    "ModelArtifact": ALPHAFORGE_SCHEMAS_DIR / "model_artifact.schema.json",
    "CalibrationCandidate": ALPHAFORGE_SCHEMAS_DIR / "calibration_candidate.schema.json",
    "V7HandoffPackage": ALPHAFORGE_SCHEMAS_DIR / "v7_handoff_package.schema.json",
}

ALPHAFORGE_FIXTURES: Dict[str, Path] = {
    "AlphaForgeLabel": FIXTURES_DIR / "alphaforge_label_minimal.json",
    "V7HandoffPackage": ALPHAFORGE_FIXTURES_DIR / "v7_handoff_package_minimal.json",
}

MAPPINGS: Dict[str, Path] = {
    "alphaforge_to_v7": MAPPINGS_DIR / "alphaforge_to_v7.md",
    "simulation_to_alphaforge": MAPPINGS_DIR / "simulation_to_alphaforge.json",
    "simulation_to_alphaforge_md": MAPPINGS_DIR / "simulation_to_alphaforge.md",
}

from alphaforge.contracts.loader import load_schema  # noqa: E402
from alphaforge.contracts.validator import validate_payload  # noqa: E402


def load_json(path: Path) -> Dict[str, Any]:
    """Load and parse a JSON file. Raises SchemaLoadError on failure."""
    from alphaforge.errors import SchemaLoadError
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        raise SchemaLoadError(str(path), "File not found")
    except json.JSONDecodeError as e:
        raise SchemaLoadError(str(path), f"Invalid JSON: {e}")
    except Exception as e:
        raise SchemaLoadError(str(path), str(e))


def get_schema_path(name: str) -> Path:
    """Return the schema path for a named AlphaForge contract."""
    from alphaforge.errors import ConfigError
    path = ALPHAFORGE_SCHEMAS.get(name)
    if path is None:
        raise ConfigError(key="schema_name",
            detail=f"Unknown schema '{name}'. Known: {sorted(ALPHAFORGE_SCHEMAS.keys())}")
    return path


def get_fixture_path(name: str) -> Optional[Path]:
    """Return the fixture path for a named AlphaForge contract, or None."""
    return ALPHAFORGE_FIXTURES.get(name)


def schema_names() -> list:
    """Return sorted list of known AlphaForge schema names."""
    return sorted(ALPHAFORGE_SCHEMAS.keys())
