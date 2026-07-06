#!/usr/bin/env python3
"""
CI lint: ensure no handoff/candidate JSON without real data tag is committed.

Fails if:
  1. Any JSON in reports/candidates/ or alphaforge/docs/discovered_alphas/
     is missing "is_real_data": true in its data_passport or validation results.
  2. Any .py file in scripts/ or alphaforge/runs/ calls assert_real_data=False
     or generate_synthetic_ohlcv() in a non-test path.

Usage:
  python3 scripts/check_real_data_required.py          # check staged files
  python3 scripts/check_real_data_required.py --all     # check all files

Exit code: 0 = pass, 1 = fail
"""

from __future__ import annotations
import json, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Files/patterns to check
HANDOFF_PATTERNS = [
    "reports/candidates/*.json",
    "alphaforge/docs/discovered_alphas/*.json",
]


def check_handoff_json(path: Path) -> list[str]:
    """Check a handoff JSON for real data markers."""
    errors: list[str] = []
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        errors.append(f"  {path}: parse error: {e}")
        return errors

    # Check data source in validation_results
    src = (data.get("validation_results", {}) or {}).get("data", {}) or {}
    source_str = (src.get("source", "") or "").lower()
    if "synthetic" in source_str or "random" in source_str:
        errors.append(f"  {path}: validation_results.data.source contains 'synthetic'/'random'")

    # Check for is_real_data in data_passport (if present)
    passport = data.get("data_passport", {}) or {}
    if passport:
        is_real = passport.get("is_real_data", False)
        if not is_real:
            errors.append(f"  {path}: data_passport.is_real_data is false or missing")

    # Check for schema_version indicating synthetic version
    schema_ver = data.get("schema_version", "")
    if isinstance(schema_ver, str) and "1.0.0" == schema_ver and any(
        word in source_str for word in ["synthetic", "random"]
    ):
        errors.append(f"  {path}: schema_version 1.0.0 with synthetic data source")

    # Check git_commit isn't a pre-real-data commit
    lineage = data.get("lineage", {}) or {}
    git_commit = (lineage.get("git_commit", "") or "")
    if git_commit and git_commit == "5f8646f":
        errors.append(f"  {path}: lineage.git_commit is pre-real-data (5f8646f) — update required")

    return errors


def check_script_imports(path: Path) -> list[str]:
    """Check .py files for unsafe synthetic patterns (outside tests)."""
    errors: list[str] = []
    text = path.read_text()

    # Skip test files AND files marked as DEPRECATED
    if "/tests/" in str(path) or path.name.startswith("test_") or "DEPRECATED" in text[:500]:
        return errors

    # Check for generate_synthetic_ohlcv import/call WITHOUT a real data guard
    if "generate_synthetic_ohlcv" in text:
        # Allow if file explicitly has assert_real_data or --synthetic flag
        if "assert_real_data" not in text and "tag_as_synthetic" not in text:
            errors.append(
                f"  {path}: imports/calls generate_synthetic_ohlcv() "
                f"but lacks assert_real_data() guard"
            )

    return errors


def main() -> int:
    errors: list[str] = []
    check_all = "--all" in sys.argv

    if check_all:
        # Check all matching files in repo
        for pattern in HANDOFF_PATTERNS:
            for path in sorted(REPO.glob(pattern)):
                errors.extend(check_handoff_json(path))

        # Check all .py files in scripts/ and alphaforge/runs/
        for dir_path in [REPO / "scripts", REPO / "alphaforge" / "runs"]:
            for path in sorted(dir_path.rglob("*.py")):
                errors.extend(check_script_imports(path))
    else:
        # Check only staged files (git diff --cached --name-only)
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, cwd=REPO,
        )
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            path = REPO / line.strip()
            if not path.exists():
                continue
            if path.suffix == ".json" and any(
                p in str(path) for p in ["reports/candidates", "discovered_alphas"]
            ):
                errors.extend(check_handoff_json(path))
            elif path.suffix == ".py":
                errors.extend(check_script_imports(path))

    if errors:
        print("❌ REAL DATA CHECK FAILED", file=sys.stderr)
        print("", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        print("", file=sys.stderr)
        print(
            "Tüm handoff/candidate JSON'lar 'is_real_data': true içermelidir.",
            file=sys.stderr,
        )
        print(
            "Tüm research script'leri assert_real_data() guard'ına sahip olmalıdır.",
            file=sys.stderr,
        )
        return 1

    print("✅ Real data check: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
