"""AlphaForge path resolution.

Locates repo root and resolves paths to AlphaForge contracts,
schemas, fixtures, and mappings relative to the repo root.
"""
from pathlib import Path


def _find_repo_root() -> Path:
    """Walk upward from this file's directory to find the repo root.

    The repo root is identified by the presence of a top-level
    contracts/ directory and the lack of a parent with the same.
    """
    current = Path(__file__).resolve().parent
    # alphaforge/src/alphaforge/paths.py → go up 3 levels to repo root
    candidate = current.parent.parent.parent
    # Verify: contracts/ should exist at candidate
    if (candidate / "contracts").is_dir():
        return candidate
    # Fallback: walk up until we find contracts/
    for _ in range(10):
        if (candidate / "contracts").is_dir():
            return candidate
        candidate = candidate.parent
    raise FileNotFoundError("Cannot locate repo root — no contracts/ found in ancestor chain")


_REPO_ROOT: Path | None = None


def repo_root() -> Path:
    """Return the repository root directory."""
    global _REPO_ROOT
    if _REPO_ROOT is None:
        _REPO_ROOT = _find_repo_root()
    return _REPO_ROOT


def contracts_dir() -> Path:
    """Return contracts/ directory."""
    return repo_root() / "contracts"


def schemas_dir() -> Path:
    """Return contracts/schemas/alphaforge/ directory."""
    return contracts_dir() / "schemas" / "alphaforge"


def fixtures_dir() -> Path:
    """Return contracts/fixtures/alphaforge/ directory."""
    return contracts_dir() / "fixtures" / "alphaforge"


def mappings_dir() -> Path:
    """Return contracts/mappings/ directory."""
    return contracts_dir() / "mappings"


def registry_path() -> Path:
    """Return contracts/registry.json path."""
    return contracts_dir() / "registry.json"


def compatibility_path() -> Path:
    """Return contracts/compatibility.json path."""
    return contracts_dir() / "compatibility.json"


def alphaforge_docs_dir() -> Path:
    """Return alphaforge/docs/ directory."""
    return repo_root() / "alphaforge" / "docs"
