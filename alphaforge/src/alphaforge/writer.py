"""Write deterministic JSON/YAML reports to reports/alphaforge or reports/accp."""

import json
from pathlib import Path
from typing import Dict, Any, Optional

from .contracts import REPORTS_DIR, ACCP_DIR


def write_json_report(
    data: Dict[str, Any],
    filename: str,
    target_dir: Optional[Path] = None,
    indent: int = 2,
) -> Path:
    """Write a JSON report to disk. Creates parent directories.

    Returns path to written file.
    """
    if target_dir is None:
        target_dir = REPORTS_DIR / "alphaforge"
    target_dir.mkdir(parents=True, exist_ok=True)
    filepath = target_dir / filename
    with open(filepath, "w") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
        f.write("\n")
    return filepath


def write_accp_yaml_report(data: Dict[str, Any], filename: str) -> Path:
    """Write ACCP-YAML report to reports/accp/. Falls back to JSON-in-YAML."""
    ACCP_DIR.mkdir(parents=True, exist_ok=True)
    filepath = ACCP_DIR / filename
    try:
        import yaml
        with open(filepath, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except ImportError:
        with open(filepath, "w") as f:
            f.write("---\n")
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
    return filepath


def write_report(data: Dict[str, Any], filepath: Path, indent: int = 2) -> Path:
    """Write a report to an arbitrary path. Creates parent directories."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    if filepath.suffix in (".yaml", ".yml"):
        return write_accp_yaml_report(data, str(filepath.relative_to(ACCP_DIR)) if ACCP_DIR in filepath.parents else filepath.name)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
        f.write("\n")
    return filepath
