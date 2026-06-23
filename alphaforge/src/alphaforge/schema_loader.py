"""Load JSON schemas from contracts/schemas/alphaforge and top-level AlphaForgeLabel.

Uses jsonschema if available; falls back to structural-only validation.
"""

from pathlib import Path
from typing import Dict, Any, List

from .contracts import (
    ALPHAFORGE_SCHEMAS,
    ALPHAFORGE_SCHEMAS_DIR,
    load_json,
)
from .errors import SchemaLoadError

# Try jsonschema — preferred validator.
# Fallback: structural-only validation in validator.py.
try:
    import jsonschema  # noqa: F401
    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False


def has_jsonschema() -> bool:
    """Return True if jsonschema library is available."""
    return _HAS_JSONSCHEMA


def load_schema(name: str) -> Dict[str, Any]:
    """Load a named AlphaForge schema from the canonical inventory.

    Args:
        name: Schema name (e.g. 'AlphaForgeLabel', 'V7HandoffPackage').

    Raises:
        SchemaLoadError: If schema file cannot be found or parsed.
    """
    from .contracts import get_schema_path
    path = get_schema_path(name)
    return load_json(path)


def load_all_alphaforge_schemas() -> Dict[str, Dict[str, Any]]:
    """Load all AlphaForge schemas. Skips missing files."""
    schemas: Dict[str, Dict[str, Any]] = {}
    for name, path in ALPHAFORGE_SCHEMAS.items():
        try:
            schemas[name] = load_json(path)
        except SchemaLoadError:
            pass
    return schemas


def load_schema_from_path(path: Path) -> Dict[str, Any]:
    """Load a JSON schema from an arbitrary path."""
    return load_json(path)


def list_schema_files() -> List[Path]:
    """List all .schema.json files in the alphaforge schemas directory."""
    if not ALPHAFORGE_SCHEMAS_DIR.exists():
        return []
    return sorted(ALPHAFORGE_SCHEMAS_DIR.glob("*.schema.json"))


def validate_schema_is_loadable(name: str) -> bool:
    """Return True if the named schema can be loaded without error."""
    try:
        load_schema(name)
        return True
    except Exception:
        return False
