"""Read contracts/registry.json and compatibility.json; expose AlphaForge contract names."""

from typing import Dict, Any, List, Optional

from .contracts import CONTRACTS_DIR, load_json
from .errors import RegistryError


def _registry_path(self=None):
    import pathlib
    return CONTRACTS_DIR / "registry.json"


def _compatibility_path():
    import pathlib
    return CONTRACTS_DIR / "compatibility.json"


def load_registry() -> Dict[str, Any]:
    """Load and return the full contract registry.

    Raises RegistryError if not found or invalid.
    """
    path = CONTRACTS_DIR / "registry.json"
    if not path.exists():
        raise RegistryError(f"Registry file not found: {path}")
    return load_json(path)


def load_compatibility() -> Dict[str, Any]:
    """Load compatibility mapping. Returns {} if file missing (non-fatal)."""
    path = CONTRACTS_DIR / "compatibility.json"
    if not path.exists():
        return {}
    return load_json(path)


def get_alphaforge_contracts() -> List[Dict[str, Any]]:
    """Return all contracts owned by alphaforge from the registry."""
    registry = load_registry()
    contracts = registry.get("contracts", [])
    return [c for c in contracts if c.get("owner_domain") == "alphaforge"]


def get_alphaforge_contract_names() -> List[str]:
    """Return sorted list of AlphaForge contract object names."""
    contracts = get_alphaforge_contracts()
    return sorted(c["object_name"] for c in contracts)


def get_contract_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Return a single contract entry by object_name, or None."""
    for c in get_alphaforge_contracts():
        if c.get("object_name") == name:
            return c
    return None


def alphaforge_schemas_in_registry() -> Dict[str, str]:
    """Return {object_name: schema_file} for AlphaForge contracts."""
    return {
        c["object_name"]: c["schema_file"]
        for c in get_alphaforge_contracts()
        if c.get("schema_file")
    }


def alphaforge_consumers() -> Dict[str, List[str]]:
    """Return {object_name: [consumers]} for contracts consumed by V7."""
    result: Dict[str, List[str]] = {}
    for c in get_alphaforge_contracts():
        consumers = c.get("consumers", [])
        if "v7" in consumers:
            result[c["object_name"]] = consumers
    return result
