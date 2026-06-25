"""
test_cross_domain_boundaries.py — Enforce import boundaries across all domains.

Checks:
- lib must not import simulation, alphaforge, or v7.
- simulation must not import alphaforge or v7.
- alphaforge must not import simulation or v7.
- v7 must not import simulation or alphaforge.
- integration/adapters must not import simulation, alphaforge, or v7.
- contracts/ must contain no Python files.

If a domain's src/ directory does not exist or has no Python files,
that domain is treated as clean (skip with info).
"""

import ast
import os
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Domain definitions: domain_name -> { src_dir, forbidden_import_prefixes }
DOMAINS = {
    "lib": {
        "src_dir": os.path.join(REPO_ROOT, "lib"),
        "forbidden": ["simulation", "alphaforge", "v7"],
    },
    "simulation": {
        "src_dir": os.path.join(REPO_ROOT, "simulation"),
        "forbidden": ["alphaforge", "v7"],
    },
    "alphaforge": {
        "src_dir": os.path.join(REPO_ROOT, "alphaforge", "src"),
        "forbidden": ["simulation", "v7"],
    },
    "v7": {
        "src_dir": os.path.join(REPO_ROOT, "v7", "src"),
        "forbidden": ["simulation", "alphaforge"],
    },
    "integration": {
        "src_dir": os.path.join(REPO_ROOT, "integration", "adapters"),
        "forbidden": ["simulation", "alphaforge", "v7"],
    },
}


def _collect_py_files(directory: str) -> list[str]:
    """Collect all .py files under a directory, skipping __pycache__."""
    if not os.path.isdir(directory):
        return []
    py_files = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))
    return py_files


def _find_imports_in_file(filepath: str) -> list[str]:
    """Extract module-level import statements from a Python file using AST."""
    with open(filepath, "r") as f:
        source = f.read()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


class TestCrossDomainBoundaries:
    """Enforce import boundaries across all domains."""

    def test_lib_boundary(self):
        """lib must not import simulation, alphaforge, or v7."""
        py_files = _collect_py_files(DOMAINS["lib"]["src_dir"])
        assert py_files, "lib must have Python files to test"
        violations = []
        for f in py_files:
            for imp in _find_imports_in_file(f):
                for forbidden in DOMAINS["lib"]["forbidden"]:
                    if imp == forbidden or imp.startswith(f"{forbidden}."):
                        violations.append(f"  {f}: imports {imp}")
        assert not violations, (
            f"LIB IMPORT BOUNDARY VIOLATION:\n" + "\n".join(violations)
        )

    def test_simulation_boundary(self):
        """simulation must not import alphaforge or v7."""
        src_dir = DOMAINS["simulation"]["src_dir"]
        if not os.path.isdir(src_dir) or not _collect_py_files(src_dir):
            pytest.skip("simulation/src/ does not exist or has no Python files (clean)")
        violations = []
        for f in _collect_py_files(src_dir):
            for imp in _find_imports_in_file(f):
                for forbidden in DOMAINS["simulation"]["forbidden"]:
                    if imp == forbidden or imp.startswith(f"{forbidden}."):
                        violations.append(f"  {f}: imports {imp}")
        assert not violations, (
            f"SIMULATION IMPORT BOUNDARY VIOLATION:\n" + "\n".join(violations)
        )

    def test_alphaforge_boundary(self):
        """alphaforge must not import simulation or v7."""
        src_dir = DOMAINS["alphaforge"]["src_dir"]
        if not os.path.isdir(src_dir) or not _collect_py_files(src_dir):
            pytest.skip("alphaforge/src/ has no Python files (clean)")
        violations = []
        for f in _collect_py_files(src_dir):
            for imp in _find_imports_in_file(f):
                for forbidden in DOMAINS["alphaforge"]["forbidden"]:
                    if imp == forbidden or imp.startswith(f"{forbidden}."):
                        violations.append(f"  {f}: imports {imp}")
        assert not violations, (
            f"ALPHAFORGE IMPORT BOUNDARY VIOLATION:\n" + "\n".join(violations)
        )

    def test_v7_boundary(self):
        """v7 must not import simulation or alphaforge."""
        src_dir = DOMAINS["v7"]["src_dir"]
        if not os.path.isdir(src_dir) or not _collect_py_files(src_dir):
            pytest.skip("v7/src/ has no Python files (clean)")
        violations = []
        for f in _collect_py_files(src_dir):
            for imp in _find_imports_in_file(f):
                for forbidden in DOMAINS["v7"]["forbidden"]:
                    if imp == forbidden or imp.startswith(f"{forbidden}."):
                        violations.append(f"  {f}: imports {imp}")
        assert not violations, (
            f"V7 IMPORT BOUNDARY VIOLATION:\n" + "\n".join(violations)
        )

    def test_integration_boundary(self):
        """integration/adapters must not import simulation, alphaforge, or v7."""
        src_dir = DOMAINS["integration"]["src_dir"]
        py_files = _collect_py_files(src_dir)
        assert py_files, "integration/adapters must have Python files to test"
        violations = []
        for f in py_files:
            for imp in _find_imports_in_file(f):
                for forbidden in DOMAINS["integration"]["forbidden"]:
                    if imp == forbidden or imp.startswith(f"{forbidden}."):
                        violations.append(f"  {f}: imports {imp}")
        assert not violations, (
            f"INTEGRATION IMPORT BOUNDARY VIOLATION:\n" + "\n".join(violations)
        )

    def test_contracts_has_no_python_files(self):
        """contracts/ must contain no Python files."""
        contracts_dir = os.path.join(REPO_ROOT, "contracts")
        py_files = _collect_py_files(contracts_dir)
        assert not py_files, (
            f"contracts/ must not contain Python files (passive authority). Found: {py_files}"
        )
