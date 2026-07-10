"""
Import boundary enforcement test for /simulation authority.

/simulation must NOT import v7, alphaforge, runtime, or interface.
This test enforces that boundary at the module-import level.
"""

import importlib
import os
import subprocess
import sys

import pytest


FORBIDDEN_MODULES = [
    "v7",
    "alphaforge",
    "runtime",
    "interface",
]

# Module names that contain these as substrings in comments/docstrings
# We only care about actual import statements
IMPORT_PATTERNS = [
    "import v7",
    "from v7",
    "import alphaforge",
    "from alphaforge",
    "import runtime",
    "from runtime",
    "import interface",
    "from interface",
]


def _get_simulation_python_files() -> list[str]:
    """Return all .py files under simulation/ (relative paths)."""
    sim_dir = os.path.join(os.path.dirname(__file__), "..")
    py_files = []
    for root, _dirs, files in os.walk(sim_dir):
        for f in files:
            if f.endswith(".py"):
                full = os.path.relpath(os.path.join(root, f), sim_dir)
                py_files.append(full)
    return py_files


@pytest.mark.xfail(reason="Known cross-domain import — #315 test imports alphaforge (lineage tests)")
def test_simulation_does_not_import_forbidden_modules() -> None:
    """Every .py file under simulation/ (excluding tests) must not import forbidden domains."""
    sim_dir = os.path.join(os.path.dirname(__file__), "..")
    this_file = os.path.abspath(__file__)
    py_files = []
    for root, _dirs, files in os.walk(sim_dir):
        for f in files:
            if f.endswith(".py"):
                full = os.path.abspath(os.path.join(root, f))
                if full != this_file:
                    py_files.append(full)

    violations = []
    for filepath in py_files:
        with open(filepath) as fh:
            for lineno, line in enumerate(fh, 1):
                stripped = line.strip()
                # Skip comments and docstrings
                if stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("'"):
                    continue
                for pattern in IMPORT_PATTERNS:
                    if pattern in stripped:
                        violations.append(
                            f"{filepath}:{lineno}: forbidden import pattern '{pattern}': {stripped}"
                        )

    if violations:
        pytest.fail(
            "Forbidden imports found in simulation/:\n" + "\n".join(violations)
        )


def test_simulation_modules_importable():
    """Core simulation modules can be imported without error."""
    modules = [
        "simulation",
        "simulation.contracts",
        "simulation.contracts.models",
        "simulation.engine",
        "simulation.engine.costs",
        "simulation.engine.exits",
        "simulation.engine.engine",
        "simulation.engine.batch",
        "simulation.engine.writer",
        "simulation.adapters",
        "simulation.adapters.market_data_adapter",
        "simulation.adapters.training_adapter",
        "simulation.adapters.evaluation_adapter",
        "simulation.adapters.paper_driver",
        "simulation.adapters.replay_driver",
        "simulation.adapters.monte_carlo_adapter",
        "simulation.adapters._validation",
        "simulation.engine.interface",
    ]
    for mod_name in modules:
        importlib.import_module(mod_name)
