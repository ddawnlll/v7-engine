"""AlphaForge contract registry helpers.

Read-only access to contracts/registry.json for AlphaForge contract entries.
"""
from alphaforge.errors import RegistryError
from alphaforge.contracts.loader import load_registry


# Required AlphaForge contracts expected in registry (P0.8E)
REQUIRED_ALPHAFORGE_CONTRACTS = [
    "AlphaThesis",
    "AlphaCandidate",
    "FeatureSetSpec",
    "LabelDatasetSpec",
    "ModeResearchReport",
    "AlphaForgeResearchReport",
    "ValidationReport",
    "ModelArtifact",
    "CalibrationCandidate",
    "V7HandoffPackage",
    "AlphaForgeLabel",
]


def get_alphaforge_contracts() -> list[dict]:
    """Return all AlphaForge contract entries from the registry.

    Returns:
        List of contract entry dicts where owner_domain == 'alphaforge'.
    """
    registry = load_registry()
    contracts = registry.get("contracts", [])
    return [c for c in contracts if c.get("owner_domain") == "alphaforge"]


def get_alphaforge_contract_names() -> list[str]:
    """Return object_names of all AlphaForge contracts."""
    return [c["object_name"] for c in get_alphaforge_contracts()]


def check_required_contracts_registered() -> dict[str, bool]:
    """Check whether all required AlphaForge contracts are registered.

    Returns:
        Dict mapping contract name → registered (True/False).
    """
    registered_names = set(get_alphaforge_contract_names())
    return {name: name in registered_names for name in REQUIRED_ALPHAFORGE_CONTRACTS}


def validate_registry() -> list[str]:
    """Validate that all required AlphaForge contracts are in the registry.

    Returns:
        List of error messages (empty if all OK).
    """
    errors = []
    check = check_required_contracts_registered()
    for name, present in check.items():
        if not present:
            errors.append(f"Missing from registry: {name}")
    if not errors:
        # Also verify registry is loadable and has expected structure
        registry = load_registry()
        contracts = registry.get("contracts")
        if contracts is None:
            errors.append("Registry missing 'contracts' key")
        elif not isinstance(contracts, list):
            errors.append(f"Registry 'contracts' must be a list, got {type(contracts).__name__}")
    return errors


def get_contract_by_name(object_name: str) -> dict | None:
    """Get a specific AlphaForge contract entry by object_name.

    Returns:
        Contract entry dict or None if not found.
    """
    for c in get_alphaforge_contracts():
        if c.get("object_name") == object_name:
            return c
    return None
