#!/usr/bin/env python3
"""V7 Engine — Main Menu (TUI)

Centralized terminal UI for all V7 Engine operations.
Use:  python3 -m cli.menu  or  make menu

Çat Kapı — her şey buradan yönetilir.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# ── ANSI colors (zero dependencies) ────────────────────────────────

class Style:
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[97m"
    BG_BLUE = "\033[44m"
    BG_GREEN = "\033[42m"
    BG_DARK = "\033[40m"
    CLEAR = "\033[2J\033[H"
    BOLD_OFF = "\033[22m"

# ── Menu tree ──────────────────────────────────────────────────────

Item = dict[str, Any]

def _cmd(cmd: str) -> Item:
    return {"type": "cmd", "run": cmd}

def _submenu(title: str, items: list[Item]) -> Item:
    return {"type": "submenu", "title": title, "items": items}

def _sep() -> Item:
    return {"type": "sep"}

# ── Action implementations ────────────────────────────────────────

PYTHONPATH_VAR = "alphaforge/src:."


ENV = os.environ.copy()
ENV["PYTHONPATH"] = PYTHONPATH_VAR


def _run(args: list[str], display: str = "") -> None:
    """Run a command safely with env vars (no shell=True)."""
    show = display or " ".join(args)
    print(f"\n  {Style.DIM}$ {show}{Style.RESET}\n")
    ret = subprocess.call(args, env=ENV)
    if ret != 0:
        print(f"\n  {Style.RED}⚠  Exit code: {ret}{Style.RESET}")
    else:
        print(f"\n  {Style.GREEN}✓ OK{Style.RESET}")
    _press_enter()


def _run_make(target: str, extra: str = "") -> None:
    """Run a make target."""
    full = f"make {target} {extra}".strip()
    print(f"\n  {Style.DIM}$ {full}{Style.RESET}\n")
    args = ["make", target] + (extra.split() if extra else [])
    ret = subprocess.call(args, env=ENV)
    if ret != 0:
        print(f"\n  {Style.RED}⚠  Exit code: {ret}{Style.RESET}")
    else:
        print(f"\n  {Style.GREEN}✓ OK{Style.RESET}")
    _press_enter()


def _run_python(module: str, args: str = "") -> None:
    """Run a python module."""
    cmd = f"python3 -m {module} {args}"
    print(f"\n  {Style.DIM}$ {cmd}{Style.RESET}\n")
    full_args = ["python3", "-m", module] + (args.split() if args else [])
    ret = subprocess.call(full_args, env=ENV)
    if ret != 0:
        print(f"\n  {Style.RED}⚠  Exit code: {ret}{Style.RESET}")
    else:
        print(f"\n  {Style.GREEN}✓ OK{Style.RESET}")
    _press_enter()


def _press_enter() -> None:
    try:
        input(f"\n  {Style.DIM}Press Enter to continue...{Style.RESET}")
    except (EOFError, KeyboardInterrupt):
        pass


def _select_mode() -> str:
    """Let user pick a trading mode interactively."""
    modes = ["SWING", "SCALP", "AGGRESSIVE_SCALP"]
    print(f"\n  {Style.BOLD}Select mode:{Style.RESET}")
    for i, m in enumerate(modes, 1):
        print(f"    [{i}] {m}")
    try:
        c = input(f"  Choice [1-3, default=1]: ").strip()
        if c:
            idx = int(c) - 1
            if 0 <= idx < len(modes):
                return modes[idx]
    except (ValueError, IndexError, EOFError):
        pass
    return "SWING"


def _yes_no(prompt: str, default: bool = True) -> bool:
    """Simple yes/no prompt."""
    hint = "Y/n" if default else "y/N"
    try:
        c = input(f"  {prompt} [{hint}]: ").strip().lower()
        if c in ("y", "yes"):
            return True
        if c in ("n", "no"):
            return False
    except (EOFError, KeyboardInterrupt):
        pass
    return default


# ── Foundation actions ────────────────────────────────────────────

def action_setup() -> None:
    _run_make("setup")

def action_install() -> None:
    _run_make("install")

def action_clean() -> None:
    if _yes_no("Remove all caches and build artifacts?"):
        _run_make("clean")

def action_lint() -> None:
    _run_make("lint")

def action_typecheck() -> None:
    _run_make("typecheck")

def action_test() -> None:
    print(f"\n  {Style.BOLD}Select test scope:{Style.RESET}")
    print(f"    [1] lib/ tests only")
    print(f"    [2] System tests (contracts + boundaries + smoke)")
    print(f"    [3] All tests")
    print(f"    [4] Specific file")
    try:
        c = input(f"  Choice [1-4]: ").strip()
        if c == "2":
            _run_make("test-system")
        elif c == "3":
            _run_make("test-all")
        elif c == "4":
            f = input("  File path: ").strip()
            _run_python("pytest", f"alphaforge/tests/{f} -v")
        else:
            _run_make("test")
    except (EOFError, KeyboardInterrupt):
        pass

def action_check_contracts() -> None:
    _run_make("check-contracts")

def action_check_boundaries() -> None:
    _run_make("check-boundaries")


# ── Pipeline actions ──────────────────────────────────────────────

def action_validate() -> None:
    _run_make("validate")

def action_backfill() -> None:
    mode = _select_mode()
    _run_make("backfill", f"MODE={mode}")

def action_simulate() -> None:
    mode = _select_mode()
    _run_make("simulate", f"MODE={mode}")

def action_build_dataset() -> None:
    mode = _select_mode()
    _run_make("build-dataset", f"MODE={mode}")

def action_train() -> None:
    mode = _select_mode()
    if _yes_no(f"Train {mode} model? (requires --force to bypass gates)", default=False):
        _run_make("train", f"MODE={mode}")

def action_wfv() -> None:
    mode = _select_mode()
    _run_make("wfv", f"MODE={mode}")

def action_pipeline_report() -> None:
    mode = _select_mode()
    _run_make("report", f"MODE={mode}")

def action_pipeline_e2e() -> None:
    mode = _select_mode()
    if _yes_no(f"Run end-to-end pipeline for {mode}? This may take a while.", default=False):
        _run_make("pipeline", f"MODE={mode}")

def action_pipeline_v02() -> None:
    mode = _select_mode()
    if _yes_no(f"Run v0.2 pipeline for {mode}? (profitability evidence)", default=False):
        _run_make("pipeline-v0.2", f"MODE={mode}")

def action_pipeline_wizard() -> None:
    """Guided pipeline wizard — asks all questions, then runs end-to-end."""
    print(f"\n  {Style.BOLD}{Style.BG_BLUE}{Style.WHITE}  ⚡ Pipeline Wizard — guided end-to-end pipeline  {Style.RESET}")
    print()

    # Step 1: Mode
    mode = _select_mode()
    print(f"  Mode: {Style.BOLD}{mode}{Style.RESET}")

    # Step 2: Pipeline type
    print(f"\n  {Style.BOLD}Pipeline type:{Style.RESET}")
    print(f"    [1] Full pipeline (validate → backfill → simulate → build-dataset → train → wfv → report)")
    print(f"    [2] v0.2 profitability evidence pipeline")
    print(f"    [3] Custom steps (choose which steps to run)")
    try:
        c = input(f"  Choice [1-3, default=1]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("  Cancelled.")
        return

    # Step 3: Data source
    if c in ("", "1", "2"):
        print(f"\n  {Style.BOLD}Data source:{Style.RESET}")
        print(f"    [1] Auto-detect (cached Binance data, fall back synthetic)")
        print(f"    [2] Force synthetic data")
        print(f"    [3] Real data (requires downloaded Binance data)")
        try:
            ds = input(f"  Choice [1-3, default=1]: ").strip()
        except (EOFError, KeyboardInterrupt):
            ds = ""

    # Step 4: Force flag
    print()
    force = _yes_no("Bypass safety gates (--force)?", default=False)

    # Step 5: Summary and confirm
    pipeline_name = {"1": "full", "2": "v0.2", "3": "custom"}.get(c or "1", "full")
    data_source = {"1": "auto", "2": "synthetic", "3": "real"}.get(ds or "1", "auto")

    mode_upper = mode.upper()
    print(f"\n  {Style.BOLD}╔══ Pipeline Summary ═══════════════════════{Style.RESET}")
    print(f"  {Style.BOLD}║{Style.RESET}  Type:       {pipeline_name}")
    print(f"  {Style.BOLD}║{Style.RESET}  Mode:       {mode_upper}")
    print(f"  {Style.BOLD}║{Style.RESET}  Data:       {data_source}")
    print(f"  {Style.BOLD}║{Style.RESET}  Force:      {'yes' if force else 'no'}")
    print(f"  {Style.BOLD}╚═══════════════════════════════════════════{Style.RESET}")

    if not _yes_no("\nRun this pipeline?", default=False):
        print("  Cancelled.")
        return

    # Execute
    if c == "2":
        # v0.2 pipeline
        opts = f"MODE={mode_upper}"
        if force:
            opts += " ARGS=--force"
        _run_make("pipeline-v0.2", opts)
    elif c == "3":
        # Custom steps
        print(f"\n  Available steps: validate, backfill, simulate, build-dataset, train, wfv, report")
        try:
            steps = input(f"  Enter steps (comma-separated, default=all): ").strip()
        except (EOFError, KeyboardInterrupt):
            steps = ""
        if steps:
            extra = f"MODE={mode_upper} ARGS='--steps {steps}'"
            if force:
                extra += " --force"
            _run_make("pipeline", extra)
        else:
            _run_make("pipeline", f"MODE={mode_upper}")
    else:
        # Full pipeline
        opts = f"MODE={mode_upper}"
        if force:
            opts += " ARGS=--force"
        _run_make("pipeline", opts)


def action_pipeline_v02_wizard() -> None:
    """Quick wizard for v0.2 profitability pipeline."""
    print(f"\n  {Style.BOLD}{Style.BG_GREEN}{Style.WHITE}  ⚡ v0.2 Pipeline — Profitability Evidence  {Style.RESET}")
    print()

    mode = _select_mode()
    print(f"\n  {Style.BOLD}Options for v0.2 pipeline:{Style.RESET}")
    print(f"    [1] Synthetic data (quick, always works)")
    print(f"    [2] Real data (requires cached Binance data)")
    print(f"    [3] Both (synthetic + real comparison)")
    try:
        c = input(f"  Choice [1-3, default=1]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("  Cancelled.")
        return

    if not _yes_no(f"\nRun v0.2 pipeline for {mode}?", default=False):
        return

    if c == "2":
        _run_make("pipeline-v0.2", f"MODE={mode.upper()} ARGS=--real --no-synthetic")
    elif c == "3":
        _run_make("pipeline-v0.2", f"MODE={mode.upper()} ARGS=--real")
    else:
        _run_make("pipeline-v0.2", f"MODE={mode.upper()} ARGS=--synthetic")


# ── Data actions ──────────────────────────────────────────────────

def action_data_health() -> None:
    mode = _select_mode()
    _run_make("data-health", f"MODE={mode}")

def action_download() -> None:
    if _yes_no("Download Binance Vision data (BTC/ETH/SOL/BNB, 1h/4h, 2023-2026)?", default=False):
        _run_make("download")

def action_test_training() -> None:
    mode = _select_mode()
    _run_make("test-training", f"MODE={mode}")

def action_test_training_full() -> None:
    mode = _select_mode()
    if _yes_no(f"Full training + Optuna for {mode}? (takes longer)", default=False):
        _run_make("test-training-full", f"MODE={mode}")

def action_candidate() -> None:
    _run_make("candidate")

def action_candidate_lightgbm() -> None:
    _run_make("candidate-lightgbm")


# ── AlphaForge actions ────────────────────────────────────────────

def action_af_status() -> None:
    _run_python("cli.alphaforge", "status")

def action_af_discover() -> None:
    mode = _select_mode()
    if _yes_no(f"Run discovery for {mode}?", default=False):
        _run_python("cli.alphaforge", f"discover --mode {mode} --real")

def action_af_simulate() -> None:
    _run_python("cli.alphaforge", "simulate --all --real")

def action_af_report_list() -> None:
    _run_python("cli.alphaforge", "report list")

def action_af_report_status() -> None:
    _run_python("cli.alphaforge", "report status")

def action_af_report_menu() -> None:
    _run_python("cli.alphaforge", "report menu")

def action_af_report_generate() -> None:
    """Interactive report generator wrapper."""
    types = [
        ("minimal-mode", "Placeholder ModeResearchReport"),
        ("minimal-validation", "Placeholder ValidationReport"),
        ("minimal-handoff", "Placeholder V7HandoffPackage"),
        ("scaffold", "Schema-valid scaffold report"),
        ("alphaforge-research", "Cross-mode aggregate report"),
        ("stability", "Symbol/regime stability"),
        ("collapse", "No-trade collapse detection"),
    ]
    print(f"\n  {Style.BOLD}Select report type:{Style.RESET}")
    for i, (t, d) in enumerate(types, 1):
        print(f"    [{i}] {t:<22} {d}")
    print(f"    [{len(types)+1}] ic-metrics (programmatic only)")
    try:
        c = input(f"  Choice [1-{len(types)+1}]: ").strip()
        idx = int(c) - 1
        if 0 <= idx < len(types):
            rtype = types[idx][0]
            extra = ""
            if types[idx][0] in ("minimal-mode", "minimal-validation", "scaffold", "stability", "collapse"):
                mode = _select_mode()
                extra = f"--mode {mode}"
            _run_python("cli.alphaforge", f"report generate {rtype} {extra}")
    except (ValueError, IndexError, EOFError):
        pass


# ── Menu tree definition ──────────────────────────────────────────

MAIN_MENU: list[Item] = [
    _submenu("⚙  Foundation", [
        _cmd("setup            Setup environment (venv + deps + verify)"),
        _cmd("install          Install Python dependencies"),
        _cmd("test             Run tests (lib / system / all)"),
        _cmd("check-contracts  Validate contract registry + schema parity"),
        _cmd("check-boundaries Verify import domain boundaries"),
        _cmd("lint             Run ruff linting"),
        _cmd("typecheck        Run mypy type checking"),
        _cmd("clean            Remove caches and build artifacts"),
    ]),
    _submenu("▶  AUTO PIPELINE", [
        _cmd("pipeline-wizard    Guided pipeline (asks mode, data, steps)"),
        _cmd("pipeline-v02-wizard  Guided v0.2 profitability pipeline"),
    ]),
    _submenu("▤  Pipeline (step-by-step)", [
        _cmd("validate         Run contract + boundary + test suite"),
        _cmd("backfill         Download backfill market data"),
        _cmd("simulate         Run simulation with cost model"),
        _cmd("build-dataset    Build training dataset"),
        _cmd("train            Train model (gated — requires force)"),
        _cmd("wfv              Walk-forward validation"),
        _cmd("report           Generate pipeline report"),
        _cmd("pipeline         End-to-end pipeline (all steps)"),
        _cmd("pipeline-v0.2    v0.2 profitability evidence pipeline"),
    ]),
    _submenu("◐  Data", [
        _cmd("data-health      Verify + auto-repair downloaded data"),
        _cmd("download         Download Binance Vision data"),
        _cmd("test-training    Health check > train > verify"),
        _cmd("test-training-full  + Optuna hyperparameter search"),
        _sep(),
        _cmd("candidate        Directional candidate v0.2"),
        _cmd("candidate-lightgbm  LightGBM candidate v0.1"),
    ]),
    _submenu("α  AlphaForge", [
        _cmd("af-status         Show alpha dashboard"),
        _cmd("af-discover       Run discovery pipelines (--real)"),
        _cmd("af-simulate       Run simulation on all alphas"),
    ]),
    _submenu("📊  Reports", [
        _cmd("report-list        List available report types"),
        _cmd("report-status      Show generated reports in data/reports/"),
        _cmd("report-generate    Generate a report (interactive)"),
        _cmd("report-menu        Interactive report builder (full)"),
    ]),
    _sep(),
    _cmd("exit"),
]


# ── Menu actions (index → handler) ─────────────────────────────────

ACTION_MAP: dict[str, tuple[str, Any]] = {
    # Foundation
    "setup": ("make setup", action_setup),
    "install": ("make install", action_install),
    "test": ("make test", action_test),
    "check-contracts": ("make check-contracts", action_check_contracts),
    "check-boundaries": ("make check-boundaries", action_check_boundaries),
    "lint": ("make lint", action_lint),
    "typecheck": ("make typecheck", action_typecheck),
    "clean": ("make clean", action_clean),
    # Pipeline
    "validate": ("make validate", action_validate),
    "backfill": ("make backfill", action_backfill),
    "simulate": ("make simulate", action_simulate),
    "build-dataset": ("make build-dataset", action_build_dataset),
    "train": ("make train", action_train),
    "wfv": ("make wfv", action_wfv),
    "report": ("make report", action_pipeline_report),
    "pipeline": ("make pipeline", action_pipeline_e2e),
    "pipeline-v0.2": ("make pipeline-v0.2", action_pipeline_v02),
    "pipeline-wizard": ("pipeline wizard", action_pipeline_wizard),
    "pipeline-v02-wizard": ("pipeline v0.2 wizard", action_pipeline_v02_wizard),
    # Data
    "data-health": ("make data-health", action_data_health),
    "download": ("make download", action_download),
    "test-training": ("make test-training", action_test_training),
    "test-training-full": ("make test-training-full", action_test_training_full),
    "candidate": ("make candidate", action_candidate),
    "candidate-lightgbm": ("make candidate-lightgbm", action_candidate_lightgbm),
    # AlphaForge
    "af-status": ("python3 -m cli.alphaforge status", action_af_status),
    "af-discover": ("python3 -m cli.alphaforge discover", action_af_discover),
    "af-simulate": ("python3 -m cli.alphaforge simulate", action_af_simulate),
    # Reports
    "report-list": ("report list", action_af_report_list),
    "report-status": ("report status", action_af_report_status),
    "report-generate": ("report generate", action_af_report_generate),
    "report-menu": ("report menu", action_af_report_menu),
}


# ── Render helpers ─────────────────────────────────────────────────

def _color_item(key: str) -> str:
    """Determine color for a menu item by category."""
    if key in ("setup", "install", "lint", "typecheck", "clean", "test"):
        return Style.CYAN
    if "pipeline" in key:
        return Style.GREEN
    if key in ("download", "data-health", "test-training", "test-training-full",
               "candidate", "candidate-lightgbm"):
        return Style.YELLOW
    if key.startswith("af-") or key.startswith("report-"):
        return Style.MAGENTA
    return Style.WHITE


def _draw_header() -> None:
    print(f"{Style.CLEAR}", end="")
    print(f"  {Style.BG_BLUE}{Style.WHITE}{Style.BOLD}  ⚡ V7 ENGINE — MAIN MENU                                   {Style.RESET}")
    print(f"  {Style.BG_DARK}{Style.WHITE}  {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC"
          f"  │  PYTHONPATH={PYTHONPATH_VAR:<16}{Style.RESET}")
    print()


def _draw_menu(title: str, items: list[Item], start_num: int = 1) -> int:
    """Draw a menu section. Returns the next number."""
    box_w = 68
    print(f"  {Style.BOLD}┌─ {title} {'─' * (box_w - 4 - len(title))}{Style.RESET}")
    num = start_num
    key_map = {}

    for item in items:
        if item["type"] == "sep":
            print(f"  {Style.DIM}│{'·' * (box_w - 2)}{Style.RESET}")
            continue
        if item["type"] == "submenu":
            # Submenu items rendered flat
            for sub in item["items"]:
                label = sub["run"]
                color = _color_item(label.split()[0] if " " in label else label)
                print(f"  │  {Style.BOLD}{num:>2}.{Style.RESET} {color}{label:<55}{Style.RESET} │")
                key_map[str(num)] = label.split()[0] if " " in label else label
                num += 1
            continue

    print(f"  {Style.BOLD}└{'─' * (box_w - 1)}{Style.RESET}")
    return key_map


def _render_menu() -> tuple[list[Item], dict[str, str]]:
    """Render the full main menu and return items + key map."""
    _draw_header()

    all_items: list[Item] = []
    key_map: dict[str, str] = {}
    num = 1

    for section in MAIN_MENU:
        if section["type"] == "sep":
            continue
        if section["type"] == "submenu":
            title = section["title"]
            items = section["items"]
            box_w = 68
            print(f"  {Style.BOLD}┌─ {title} {'─' * (box_w - 4 - len(title))}{Style.RESET}")

            for item in items:
                if item["type"] == "sep":
                    print(f"  {Style.DIM}│{'·' * (box_w - 2)}{Style.RESET}")
                    continue
                run_str = item.get("run", "")
                parts = run_str.split(None, 1)
                cmd_key = parts[0]
                desc = parts[1] if len(parts) > 1 else ""
                color = _color_item(cmd_key)
                line = f"{Style.BOLD}{num:>2}.{Style.RESET} {color}{cmd_key:<20}{Style.RESET} {Style.DIM}{desc}{Style.RESET}"
                print(f"  │  {line:<{box_w - 6}}{Style.RESET} │")
                key_map[str(num)] = cmd_key
                num += 1

            print(f"  │{Style.RESET}")
            all_items.extend(items)

    # Exit option
    print(f"  {Style.BOLD}┌─ {'─' * (box_w - 3)}{Style.RESET}")
    print(f"  │  {Style.BOLD} 0.{Style.RESET} {Style.RED}exit{Style.RESET}{' ' * (box_w - 14)}│")
    print(f"  {Style.BOLD}└{'─' * (box_w - 1)}{Style.RESET}")
    key_map["0"] = "exit"
    print()

    return all_items, key_map


def _sub_header(title: str) -> None:
    print(f"  {Style.CLEAR}", end="")
    print(f"  {Style.BG_GREEN}{Style.WHITE}{Style.BOLD}  {title}{Style.RESET}")
    print()


def _run_section_interactive(title: str, items: list[Item]) -> None:
    """Render a section and let user pick items from it."""
    print(f"{Style.CLEAR}", end="")
    _sub_header(title)
    box_w = 66

    # Collect flat items
    flat: list[tuple[str, str]] = []
    for item in items:
        if item["type"] == "sep":
            continue
        if item["type"] == "submenu":
            for sub in item["items"]:
                label = sub["cmd"]
                parts = label.split(None, 1)
                cmd = parts[0]
                desc = parts[1] if len(parts) > 1 else ""
                flat.append((cmd, desc))
            continue
        run_str = item.get("run", "")
        parts = run_str.split(None, 1)
        cmd = parts[0]
        desc = parts[1] if len(parts) > 1 else ""
        flat.append((cmd, desc))

    print(f"  {Style.BOLD}┌─ {title} {'─' * (box_w - 4 - len(title))}{Style.RESET}")
    for i, (cmd, desc) in enumerate(flat, 1):
        color = _color_item(cmd)
        print(f"  │  {Style.BOLD}{i:>2}.{Style.RESET} {color}{cmd:<20}{Style.RESET} {Style.DIM}{desc}{Style.RESET}")
    print(f"  │")
    print(f"  │  {Style.BOLD} 0.{Style.RESET} {Style.RED}back{Style.RESET}")
    print(f"  └{'─' * (box_w - 1)}")
    print()

    try:
        c = input(f"  {Style.BOLD}Selection:{Style.RESET} ").strip()
        if not c or c == "0":
            return
        idx = int(c) - 1
        if 0 <= idx < len(flat):
            cmd_key = flat[idx][0]
            _dispatch(cmd_key)
    except (ValueError, IndexError, EOFError):
        pass


def _dispatch(cmd_key: str) -> None:
    """Dispatch a command key to its handler."""
    entry = ACTION_MAP.get(cmd_key)
    if entry is None:
        print(f"\n  {Style.RED}Unknown command: {cmd_key}{Style.RESET}")
        _press_enter()
        return
    _, handler = entry
    try:
        handler()
    except (KeyboardInterrupt, EOFError):
        pass
    except Exception as e:
        print(f"\n  {Style.RED}Error: {e}{Style.RESET}")
        _press_enter()


# ── Main menu loop ────────────────────────────────────────────────

def main() -> int:
    """Main menu entry point."""
    try:
        while True:
            all_items, key_map = _render_menu()
            try:
                c = input(f"  {Style.BOLD}Selection:{Style.RESET} ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not c:
                continue

            if c == "0":
                print(f"\n  {Style.GREEN}Güle güle!{Style.RESET}")
                break

            cmd_key = key_map.get(c)
            if cmd_key is None:
                # Try direct command name
                cmd_key = c

            _dispatch(cmd_key)

    except KeyboardInterrupt:
        print(f"\n  {Style.GREEN}Güle güle!{Style.RESET}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
