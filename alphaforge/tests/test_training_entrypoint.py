"""Import-boundary test: verify training entrypoint centralization.

Ensures that only the alphaforge training domain imports xgboost.
Any file outside alphaforge/ that imports xgboost is a violation
(bypasses the centralized training entrypoint).

Pattern: follows lib/tests/test_import_boundary.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ── Blessed paths that MAY import xgboost ───────────────────────────
# These are submodules of the centralized training entrypoint.
BLESSED_PATH_PREFIXES: set[str] = {
    # AlphaForge = the training/research domain — xgboost is its primary tool
    "alphaforge/src/alphaforge",
    # Test files in alphaforge
    "alphaforge/tests",
    # Legacy real_training entrypoint (deprecated, consolidated onto centralized
    # entrypoint in issue #319; still alive while users migrate)
    "cli/real_training.py",
}

# Additional files allowed to import xgboost (user scripts, diagnostics, etc.
# that are NOT production training paths)
EXEMPTED_PATHS: set[str] = {
    # User-run scripts (not part of production training)
    "scripts/ab_comparison.py",
    "scripts/candidate_v031d.py",
    "scripts/candidate_v031e.py",
    "scripts/candidate_v031e_verified.py",
    "scripts/diagnostic_v031.py",
    "scripts/experiment_v031b.py",
    "scripts/iso_alpha1.py",
    "scripts/phase_reality_complete.py",
    # Profile scripts (measurement tools, not production)
    "alphaforge/scripts",
    # Run/experiment scripts
    "alphaforge/runs",
}

# Files/dirs to skip (worktrees, caches, venvs)
SKIP_PREFIXES: set[str] = {
    ".worktrees",
    ".venv",
    "__pycache__",
    ".git",
}


def _is_allowed(rel_path: str) -> bool:
    """Check if a file is in a blessed path or explicitly exempted."""
    for prefix in BLESSED_PATH_PREFIXES:
        if rel_path.startswith(prefix):
            return True
    for prefix in EXEMPTED_PATHS:
        if rel_path.startswith(prefix):
            return True
    return False


def _should_skip(rel_path: str) -> bool:
    """Check if a file should be skipped."""
    for prefix in SKIP_PREFIXES:
        if prefix in rel_path:
            return True
    return False


def _find_xgboost_files() -> list[Path]:
    """Find all .py files that import xgboost outside allowed paths."""
    results: list[Path] = []
    for pyfile in REPO_ROOT.rglob("*.py"):
        rel = str(pyfile.relative_to(REPO_ROOT)).replace("\\", "/")
        if _should_skip(rel):
            continue
        if _is_allowed(rel):
            continue
        try:
            content = pyfile.read_text(encoding="utf-8", errors="replace")
            if "import xgboost" in content or "from xgboost" in content:
                results.append(pyfile)
        except Exception:
            pass
    return results


def test_no_unauthorized_xgboost_imports():
    """Fail if any non-blessed file imports xgboost.

    Files inside ``alphaforge/src/alphaforge/`` are the training domain
    (blessed).  Files outside that domain (cli/, scripts/, etc.) that
    import xgboost are bypassing the centralized entrypoint.
    """
    violators: list[str] = []
    for path in _find_xgboost_files():
        rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        violators.append(rel)

    assert not violators, (
        f"The following {len(violators)} file(s) import xgboost outside the "
        f"blessed training domain (alphaforge/src/alphaforge/):\n"
        + "\n".join(f"  - {v}" for v in violators)
        + "\n\nEither move the import behind the blessed entrypoint, or add "
        "the file to BLESSED_PATH_PREFIXES in this test."
    )


def test_training_config_loader_imports():
    """Verify the centralized config loader can be imported."""
    from lib.config_training import (
        TrainingConfig,
        load_training_config,
        resolve_training_scope,
    )

    assert TrainingConfig is not None
    assert load_training_config is not None
    assert resolve_training_scope is not None
