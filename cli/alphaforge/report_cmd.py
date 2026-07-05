"""AlphaForge Report CLI — centralized report command and control.

Usage:
    python3 -m cli.alphaforge report list
    python3 -m cli.alphaforge report generate <type> [options]
    python3 -m cli.alphaforge report status
    python3 -m cli.alphaforge report menu

Available report types:
    minimal-mode         build_minimal_mode_research_report — placeholder
    minimal-validation   build_minimal_validation_report — placeholder
    minimal-handoff      build_minimal_handoff_package — placeholder
    scaffold             build_mode_research_report — schema-valid scaffold
    empirical            build_empirical_mode_research_report — from WFV results
    alphaforge-research  build_alphaforge_research_report — cross-mode aggregate
    stability            build_stability_section — symbol/regime stability
    ic-metrics           compute_ic / rank_ic / ic_ir / calibration
    collapse             build_collapse_report — no-trade collapse detection
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("alphaforge.report_cli")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ── Report type registry ──────────────────────────────────────────────

REPORT_TYPES: dict[str, dict[str, Any]] = {
    "minimal-mode": {
        "description": "Minimal placeholder ModeResearchReport",
        "builder": "build_minimal_mode_research_report",
        "module": "alphaforge.reports._minimal",
        "requires_mode": True,
        "output_pattern": "data/reports/{mode}/mrr-minimal-{mode}.json",
    },
    "minimal-validation": {
        "description": "Minimal placeholder ValidationReport",
        "builder": "build_minimal_validation_report",
        "module": "alphaforge.reports._minimal",
        "requires_mode": True,
        "output_pattern": "data/reports/{mode}/vr-minimal-{mode}.json",
    },
    "minimal-handoff": {
        "description": "Minimal placeholder V7HandoffPackage",
        "builder": "build_minimal_handoff_package",
        "module": "alphaforge.reports._minimal",
        "requires_mode": False,
        "output_pattern": "data/reports/v7hp-minimal.json",
    },
    "scaffold": {
        "description": "Schema-valid scaffold ModeResearchReport (dummy data)",
        "builder": "build_mode_research_report",
        "module": "alphaforge.reports.builders",
        "requires_mode": True,
        "output_pattern": "data/reports/{mode}/mrr-scaffold-{mode}.json",
    },
    "empirical": {
        "description": "Empirical ModeResearchReport from WFV results",
        "builder": "build_empirical_mode_research_report",
        "module": "alphaforge.reports.empirical",
        "requires_mode": True,
        "requires_wfv": True,
        "output_pattern": "data/reports/{mode}/mrr-empirical-{mode}.json",
    },
    "alphaforge-research": {
        "description": "Cross-mode aggregate AlphaForgeResearchReport",
        "builder": "build_alphaforge_research_report",
        "module": "alphaforge.reports.builders",
        "requires_mode": False,
        "output_pattern": "data/reports/alphaforge-research-report.json",
    },
    "stability": {
        "description": "Symbol/regime stability analysis",
        "builder": "build_stability_section",
        "module": "alphaforge.reports.stability",
        "requires_mode": True,
        "output_pattern": "data/reports/{mode}/stability-{mode}.json",
    },
    "ic-metrics": {
        "description": "IC, Rank IC, IC IR, calibration error",
        "builder": None,  # multiple functions
        "module": "alphaforge.reports.ic_metrics",
        "requires_mode": False,
        "output_pattern": None,
    },
    "collapse": {
        "description": "No-trade collapse detection and root cause analysis",
        "builder": "build_collapse_report",
        "module": "alphaforge.reports.collapse_detector",
        "requires_mode": True,
        "output_pattern": "data/reports/{mode}/collapse-{mode}.json",
    },
}

SUPPORTED_MODES = ("SWING", "SCALP", "AGGRESSIVE_SCALP")

# ── Helpers ───────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_output_dir(path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _validate_mode(mode: str) -> str:
    m = mode.upper()
    if m not in SUPPORTED_MODES:
        print(f"  ERROR: Unknown mode '{mode}'. Supported: {', '.join(SUPPORTED_MODES)}")
        sys.exit(1)
    return m


def _load_json(path: str | Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _find_wfv_results(mode: str) -> dict | None:
    """Look for WFV results in standard locations."""
    candidates = [
        Path(f"data/reports/{mode.lower()}/wfv_report_*.json"),
        Path(f"data/reports/{mode.lower()}/wfv_results.json"),
        Path(f"artifacts/pipeline/reports/{mode.lower()}/wfv_*.json"),
    ]
    for pattern in candidates:
        if "*" in str(pattern):
            matches = sorted(Path(".").glob(str(pattern)))
            if matches:
                try:
                    return _load_json(matches[-1])
                except (json.JSONDecodeError, OSError):
                    continue
        elif pattern.exists():
            try:
                return _load_json(pattern)
            except (json.JSONDecodeError, OSError):
                continue
    return None


def _lookup_builder(module_path: str, func_name: str) -> Any:
    """Dynamically import and return a builder function."""
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, func_name)


def _generate_report(report_type: str, mode: str | None = None,
                     wfv_path: str | None = None,
                     output_path: str | None = None) -> Path:
    """Generate a report by type, returning the output path."""
    info = REPORT_TYPES.get(report_type)
    if info is None:
        print(f"  ERROR: Unknown report type '{report_type}'")
        print(f"  Use 'python3 -m cli.alphaforge report list' to see available types")
        sys.exit(1)

    # Resolve mode
    resolved_mode = mode.upper() if mode else "SWING"
    if info["requires_mode"]:
        resolved_mode = _validate_mode(resolved_mode)
    else:
        resolved_mode = mode.upper() if mode else "SWING"

    # Resolve output path
    if output_path:
        out = Path(output_path)
    else:
        pattern = info["output_pattern"]
        if pattern and "{mode}" in pattern:
            pattern = pattern.replace("{mode}", resolved_mode.lower())
        out = Path(pattern) if pattern else Path(f"data/reports/{report_type}_{_now_iso()}.json")

    print(f"\n  Report type: {report_type}")
    print(f"  Description: {info['description']}")
    if info["requires_mode"]:
        print(f"  Mode:        {resolved_mode}")
    print(f"  Output:      {out}")

    # ── Route to builder ──────────────────────────────────────────
    if report_type == "minimal-mode":
        from alphaforge.reports._minimal import build_minimal_mode_research_report
        payload = build_minimal_mode_research_report(mode=resolved_mode)

    elif report_type == "minimal-validation":
        from alphaforge.reports._minimal import build_minimal_validation_report
        payload = build_minimal_validation_report(mode=resolved_mode)

    elif report_type == "minimal-handoff":
        from alphaforge.reports._minimal import build_minimal_handoff_package
        payload = build_minimal_handoff_package(mode=resolved_mode)

    elif report_type == "scaffold":
        from alphaforge.reports.builders import build_mode_research_report
        payload = build_mode_research_report(mode=resolved_mode)

    elif report_type == "empirical":
        from alphaforge.reports.empirical import build_empirical_mode_research_report
        if wfv_path:
            wfv_data = _load_json(wfv_path)
        else:
            wfv_data = _find_wfv_results(resolved_mode)
        if wfv_data is None:
            print(f"  ERROR: No WFV results found for {resolved_mode}.")
            print(f"  Provide a WFV results file with --wfv <path>")
            print(f"  Or run the pipeline first: python3 -m cli wfv")
            return None
            out  # type: ignore
        payload = build_empirical_mode_research_report(mode=resolved_mode, wfv_results=wfv_data)

    elif report_type == "alphaforge-research":
        from alphaforge.reports.builders import build_alphaforge_research_report
        payload = build_alphaforge_research_report()

    elif report_type == "stability":
        from alphaforge.reports.stability import build_stability_section
        # Build a minimal WFV results dict for stability analysis
        wfv_for_stability = {
            "per_symbol_oos": {},
            "oos_summary": {
                "oos_sharpe": 0.0,
                "oos_expectancy_r": 0.0,
                "oos_win_rate": 0.5,
                "oos_trade_count": 0,
                "oos_ic": 0.0,
                "oos_rank_ic": 0.0,
            },
            "data_scope": {"symbols": [f"{resolved_mode}_DEFAULT"], "primary_timeframes": ["?"]},
            "regime_breakdown": {"regimes": []},
        }
        stability_section = build_stability_section(wfv_for_stability)
        payload = {
            "schema_version": "1.0.0",
            "report_type": "stability",
            "mode": resolved_mode,
            "created_at": _now_iso(),
            "stability": stability_section,
        }

    elif report_type == "ic-metrics":
        print("  NOTE: IC metrics are pure computation functions.")
        print("  They require predicted_R and realized_R arrays as input.")
        print("  Use them programmatically from alphaforge.reports.ic_metrics")
        print()
        print("  Available functions:")
        print("    compute_ic(predicted_R, realized_R) -> float")
        print("    compute_rank_ic(predicted_R, realized_R) -> float")
        print("    compute_ic_ir(ic_series) -> float")
        print("    compute_calibration_error(probabilities, outcomes, n_bins=10) -> dict")
        print("    compute_expected_r_from_probabilities(probs, r_multiples) -> float")
        print()
        print("  Example:")
        print("    python3 -c \"from alphaforge.reports.ic_metrics import compute_ic; ...\"")
        return Path("(programmatic use only)")

    elif report_type == "collapse":
        from alphaforge.reports.collapse_detector import build_collapse_report
        # Build with mock labels and mode
        payload = build_collapse_report(
            labels=[],
            mode=resolved_mode,
        )

    else:
        print(f"  ERROR: Unhandled report type '{report_type}'")
        return None  # type: ignore

    # ── Write output ──────────────────────────────────────────────
    from alphaforge.reports.writer import write_json_report
    write_json_report(payload, out)
    print(f"  [OK] Report written to {out.resolve()}")
    return out


# ── Subcommand handlers ──────────────────────────────────────────────


def cmd_report_list(args: argparse.Namespace) -> int:
    """List all available report types with descriptions."""
    print()
    print("=" * 72)
    print("  AlphaForge — Available Report Types")
    print("=" * 72)
    print()
    print(f"  {'TYPE':<22} {'MODE':<6} {'DESCRIPTION'}")
    print(f"  {'─'*22} {'─'*6} {'─'*40}")
    for rtype, info in REPORT_TYPES.items():
        mode_req = "yes" if info["requires_mode"] else "no"
        desc = info["description"]
        print(f"  {rtype:<22} {mode_req:<6} {desc}")
    print()
    print("  Usage: python3 -m cli.alphaforge report generate <type> [options]")
    print()
    return 0


def cmd_report_generate(args: argparse.Namespace) -> int:
    """Generate a specific report."""
    report_type = args.report_type
    mode = args.mode
    wfv_path = args.wfv
    output = args.output

    if report_type not in REPORT_TYPES:
        print(f"\n  ERROR: Unknown report type '{report_type}'")
        print(f"  Use 'report list' to see available types\n")
        return 1

    result = _generate_report(report_type, mode=mode, wfv_path=wfv_path,
                               output_path=output)
    if result is None:
        return 1
    return 0


def cmd_report_status(args: argparse.Namespace) -> int:
    """Show existing reports in data/reports/."""
    reports_dir = Path("data/reports")
    if not reports_dir.is_dir():
        print("\n  No reports directory found (data/reports/).\n")
        return 0

    print()
    print("=" * 72)
    print("  AlphaForge — Generated Reports")
    print("=" * 72)
    print()

    # Collect stats per mode directory
    mode_dirs = {}
    for d in sorted(reports_dir.iterdir()):
        if d.is_dir():
            json_files = sorted(d.rglob("*.json"))
            if json_files:
                mode_dirs[d.name] = json_files
        elif d.suffix == ".json":
            mode_dirs.setdefault("(root)", []).append(d)

    total_files = 0
    for dirname, files in sorted(mode_dirs.items()):
        print(f"  [{dirname}/]")
        for f in files[-8:]:  # last 8 files per directory
            size = f.stat().st_size
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            date_str = mtime.strftime("%Y-%m-%d %H:%M")
            print(f"    {f.name:<50} {size:>8,d}b  {date_str}")
        if len(files) > 8:
            print(f"    ... and {len(files) - 8} more")
        total_files += len(files)
        print()

    print(f"  Total: {total_files} report files across {len(mode_dirs)} directories")
    print()
    return 0


def cmd_report_menu(args: argparse.Namespace) -> int:
    """Interactive terminal menu for report generation."""
    print()
    print("=" * 72)
    print("  AlphaForge Report Generator — Interactive Menu")
    print("=" * 72)
    print()

    # Step 1: Pick report type
    types_list = list(REPORT_TYPES.keys())
    print("  Available report types:")
    for i, rtype in enumerate(types_list, 1):
        info = REPORT_TYPES[rtype]
        print(f"    [{i}] {rtype:<22} — {info['description']}")
    print()

    try:
        choice = input("  Select report type [1-{}]: ".format(len(types_list))).strip()
        idx = int(choice) - 1
        if idx < 0 or idx >= len(types_list):
            print("  Invalid selection.")
            return 1
        selected_type = types_list[idx]
    except (ValueError, IndexError, EOFError):
        print("  Cancelled.")
        return 1

    info = REPORT_TYPES[selected_type]

    # Step 2: Pick mode if required
    mode = "SWING"
    if info["requires_mode"]:
        print()
        print("  Modes:")
        for i, m in enumerate(SUPPORTED_MODES, 1):
            print(f"    [{i}] {m}")
        try:
            m_choice = input("  Select mode [1-3, default=1]: ").strip()
            if m_choice:
                m_idx = int(m_choice) - 1
                if 0 <= m_idx < len(SUPPORTED_MODES):
                    mode = SUPPORTED_MODES[m_idx]
        except (ValueError, IndexError, EOFError):
            mode = "SWING"

    # Step 3: WFV path for empirical reports
    wfv_path = None
    if selected_type == "empirical":
        auto_found = _find_wfv_results(mode)
        print()
        if auto_found:
            print(f"  Auto-detected WFV results: {auto_found}")
            yn = input("  Use this file? [Y/n]: ").strip().lower()
            if yn not in ("n", "no"):
                wfv_path = str(auto_found)
        if wfv_path is None:
            wfv_path = input("  Path to WFV results JSON (or empty to skip): ").strip()
            if not wfv_path:
                print("  No WFV results — cannot generate empirical report.")
                return 1

    # Step 4: Output path
    default_out = info["output_pattern"]
    if default_out and "{mode}" in default_out:
        default_out = default_out.replace("{mode}", mode.lower())
    print()
    out_path = input(f"  Output path [default: {default_out}]: ").strip()
    if not out_path:
        out_path = default_out

    # Generate
    print()
    result = _generate_report(selected_type, mode=mode, wfv_path=wfv_path,
                               output_path=out_path)
    if result is None:
        return 1
    print()
    print("  Done. Use 'report status' to see all generated reports.")
    print()
    return 0


# ── Parser ────────────────────────────────────────────────────────────


def build_report_parser(sub: argparse.ArgumentParser) -> None:
    """Add report subcommands to the given subparser."""
    report_sub = sub.add_subparsers(dest="report_command", required=True)

    # list
    report_sub.add_parser("list", help="List all available report types")

    # generate
    gen_p = report_sub.add_parser("generate", help="Generate a specific report")
    gen_p.add_argument("report_type", choices=list(REPORT_TYPES.keys()),
                        help="Type of report to generate")
    gen_p.add_argument("--mode", default=None,
                        help="Trading mode (SWING, SCALP, AGGRESSIVE_SCALP)")
    gen_p.add_argument("--wfv", default=None,
                        help="Path to WFV results JSON (required for empirical)")
    gen_p.add_argument("--output", "-o", default=None,
                        help="Output file path")

    # status
    report_sub.add_parser("status", help="Show existing reports in data/reports/")

    # menu
    report_sub.add_parser("menu", help="Interactive terminal menu")


# ── Main dispatcher ──────────────────────────────────────────────────


def cmd_report(args: argparse.Namespace) -> int:
    """Main dispatcher for report subcommands."""
    handlers = {
        "list": cmd_report_list,
        "generate": cmd_report_generate,
        "status": cmd_report_status,
        "menu": cmd_report_menu,
    }
    handler = handlers.get(args.report_command)
    if handler is None:
        print("  Unknown report command. Available: list, generate, status, menu")
        return 1
    return handler(args)


# ── End of report_cmd.py ────────────────────────────────────────────
