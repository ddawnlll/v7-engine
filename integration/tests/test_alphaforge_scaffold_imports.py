"""P0.9A — AlphaForge scaffold import tests.

Verifies the alphaforge package imports correctly.
"""
import sys
from pathlib import Path

# Ensure alphaforge/src is on PYTHONPATH for tests
REPO = Path(__file__).resolve().parent.parent.parent
AF_SRC = REPO / "alphaforge" / "src"
if str(AF_SRC) not in sys.path:
    sys.path.insert(0, str(AF_SRC))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_alphaforge_package_imports():
    """AlphaForge top-level package imports successfully."""
    import alphaforge
    assert alphaforge.__version__ == "0.1.0"
    assert alphaforge.__authority__ == "alphaforge"
    assert alphaforge.__domain__ == "alpha_discovery_and_research"


def test_alphaforge_errors_import():
    """All error classes import and inherit correctly."""
    from alphaforge.errors import (
        AlphaForgeError,
        ContractError,
        ContractLoadError,
        ContractValidationError,
        ModeError,
        ReportBuildError,
        HandoffBuildError,
        RegistryError,
    )
    assert issubclass(ContractError, AlphaForgeError)
    assert issubclass(ModeError, AlphaForgeError)
    assert issubclass(ReportBuildError, AlphaForgeError)


def test_alphaforge_paths_import_and_resolve():
    """Paths module resolves repo root correctly."""
    from alphaforge.paths import repo_root, schemas_dir, fixtures_dir, registry_path

    root = repo_root()
    assert root.is_dir()
    assert (root / "contracts").is_dir()

    sd = schemas_dir()
    assert sd.is_dir()
    assert (sd / "v7_handoff_package.schema.json").exists()

    fd = fixtures_dir()
    assert fd.is_dir()
    assert (fd / "swing_mode_research_report_minimal.json").exists()

    rp = registry_path()
    assert rp.exists()


def test_alphaforge_constants():
    """Constants module exposes locked canonical values."""
    from alphaforge.constants import (
        CANONICAL_MODES,
        CANONICAL_V7_GATES,
        MODE_PRIORITY_PRIMARY,
        MODE_PRIORITY_SECONDARY_BASELINE,
    )

    assert "SCALP" in CANONICAL_MODES
    assert "AGGRESSIVE_SCALP" in CANONICAL_MODES
    assert "SWING" in CANONICAL_MODES
    assert len(CANONICAL_MODES) == 3

    assert CANONICAL_V7_GATES[0] == "G0_doc_ready"
    assert CANONICAL_V7_GATES[-1] == "G10_live"
    assert len(CANONICAL_V7_GATES) == 11

    assert MODE_PRIORITY_PRIMARY == "PRIMARY"
    assert MODE_PRIORITY_SECONDARY_BASELINE == "SECONDARY_BASELINE"


def test_alphaforge_imports_no_forbidden_domains():
    """AlphaForge package must not import from forbidden domains."""
    import alphaforge

    # Check that alphaforge module tree has no references to v7, runtime, interface
    import ast
    import inspect

    def check_module(mod):
        try:
            source = inspect.getsource(mod)
        except (TypeError, OSError):
            return
        # Parse to find imports
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module_name = ""
                if isinstance(node, ast.ImportFrom) and node.module:
                    module_name = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        module_name = alias.name
                # Forbidden import domains
                forbidden = ["v7.", "runtime.", "interface."]
                for fb in forbidden:
                    assert not module_name.startswith(fb), (
                        f"{mod.__name__} imports forbidden domain: {module_name}"
                    )

    import alphaforge.paths
    import alphaforge.constants
    import alphaforge.errors
    import alphaforge.modes.profiles
    import alphaforge.contracts.loader
    import alphaforge.contracts.validator
    import alphaforge.contracts.registry
    import alphaforge.reports.builders
    import alphaforge.reports.writer
    import alphaforge.handoff.builders

    for m in [
        alphaforge.paths, alphaforge.constants, alphaforge.errors,
        alphaforge.modes.profiles, alphaforge.contracts.loader,
        alphaforge.contracts.validator, alphaforge.contracts.registry,
        alphaforge.reports.builders, alphaforge.reports.writer,
        alphaforge.handoff.builders,
    ]:
        check_module(m)
