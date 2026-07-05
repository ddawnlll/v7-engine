#!/usr/bin/env python3
"""V7 Engine — guided terminal menu.

A small, workflow-first TUI for common V7 operations.  The menu avoids a
flat list of dozens of commands and asks for mode, symbol universe, date
range, intervals, and dry-run/execute at the point where those choices matter.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any


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


PYTHONPATH_VAR = "alphaforge/src:."
ENV = os.environ.copy()
ENV["PYTHONPATH"] = PYTHONPATH_VAR
ENV.setdefault("PYTHON", sys.executable)

CORE_SYMBOLS = "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT"
FULL_UNIVERSE = ",".join([
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "SOLUSDT", "DOTUSDT", "MATICUSDT", "AVAXUSDT", "UNIUSDT",
    "LINKUSDT", "ATOMUSDT", "LTCUSDT", "BCHUSDT", "DOGEUSDT",
    "FILUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT",
])


def _press_enter() -> None:
    try:
        input(f"\n  {Style.DIM}Press Enter to continue...{Style.RESET}")
    except (EOFError, KeyboardInterrupt):
        pass


def _choice(title: str, options: list[tuple[str, str]], default: int = 1) -> str:
    print(f"\n  {Style.BOLD}{title}{Style.RESET}")
    for idx, (_, label) in enumerate(options, 1):
        suffix = "  (default)" if idx == default else ""
        print(f"    [{idx}] {label}{Style.DIM}{suffix}{Style.RESET}")
    try:
        raw = input(f"  Choice [1-{len(options)}]: ").strip()
        if not raw:
            return options[default - 1][0]
        idx = int(raw) - 1
        if 0 <= idx < len(options):
            return options[idx][0]
    except (ValueError, EOFError, KeyboardInterrupt):
        pass
    return options[default - 1][0]


def _text(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        value = input(f"  {prompt}{suffix}: ").strip()
        return value or default
    except (EOFError, KeyboardInterrupt):
        return default


def _yes_no(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    try:
        value = input(f"  {prompt} [{hint}]: ").strip().lower()
        if value in ("y", "yes"):
            return True
        if value in ("n", "no"):
            return False
    except (EOFError, KeyboardInterrupt):
        pass
    return default


def _run(args: list[str], display: str | None = None, pause: bool = True) -> int:
    show = display or " ".join(shlex.quote(a) for a in args)
    print(f"\n  {Style.DIM}$ {show}{Style.RESET}\n")
    ret = subprocess.call(args, env=ENV)
    if ret == 0:
        print(f"\n  {Style.GREEN}✓ OK{Style.RESET}")
    else:
        print(f"\n  {Style.RED}⚠ Exit code: {ret}{Style.RESET}")
    if pause:
        _press_enter()
    return ret


def _run_make(target: str, vars: dict[str, str] | None = None, pause: bool = True) -> int:
    args = ["make", target]
    for key, value in (vars or {}).items():
        if value != "":
            args.append(f"{key}={value}")
    return _run(args, pause=pause)


def _run_python(module: str, args_text: str = "", pause: bool = True) -> int:
    args = [sys.executable, "-m", module] + shlex.split(args_text)
    return _run(args, pause=pause)


def _select_mode(default: str = "SCALP") -> str:
    modes = [("SCALP", "SCALP — primary"), ("AGGRESSIVE_SCALP", "AGGRESSIVE_SCALP — primary/high frequency"), ("SWING", "SWING — baseline/control")]
    default_idx = next((i + 1 for i, (m, _) in enumerate(modes) if m == default), 1)
    return _choice("Trading mode", modes, default_idx)


def _select_symbols() -> str:
    selected = _choice(
        "Symbol universe",
        [
            (CORE_SYMBOLS, "Core 4: BTC, ETH, SOL, BNB"),
            ("BTCUSDT", "BTC only — smoke/test"),
            (FULL_UNIVERSE, "Full 20-symbol universe"),
            ("custom", "Custom comma-separated list"),
        ],
        default=1,
    )
    if selected == "custom":
        return _text("Symbols", CORE_SYMBOLS).upper().replace(" ", "")
    return selected


def _select_range() -> tuple[str, str]:
    preset = _choice(
        "Data range",
        [
            ("smoke", "Smoke: 2024-01-01 → 2024-01-31 (1 month)"),
            ("h1", "Half-year: 2024-01-01 → 2024-06-30"),
            ("y2024", "Year 2024"),
            ("prod", "Production baseline: 2023-01-01 → 2026-12-31"),
            ("custom", "Custom dates"),
        ],
        default=1,
    )
    if preset == "smoke":
        return "2024-01-01", "2024-01-31"
    if preset == "h1":
        return "2024-01-01", "2024-06-30"
    if preset == "y2024":
        return "2024-01-01", "2024-12-31"
    if preset == "prod":
        return "2023-01-01", "2026-12-31"
    return _text("Start date YYYY-MM-DD", "2024-01-01"), _text("End date YYYY-MM-DD", "2024-01-31")


def _default_intervals(mode: str) -> str:
    if mode == "AGGRESSIVE_SCALP":
        return "5m,15m,1h"
    if mode == "SWING":
        return "1h,4h"
    return "15m,1h,4h"


def _select_intervals(mode: str) -> str:
    default = _default_intervals(mode)
    selected = _choice(
        "Intervals",
        [
            (default, f"Mode default: {default}"),
            ("1h", "1h only — fastest smoke"),
            ("15m,1h", "15m + 1h"),
            ("custom", "Custom comma-separated intervals"),
        ],
        default=1,
    )
    if selected == "custom":
        return _text("Intervals", default).replace(" ", "")
    return selected


def _data_options(default_mode: str = "SCALP") -> dict[str, str]:
    mode = _select_mode(default_mode)
    symbols = _select_symbols()
    start, end = _select_range()
    intervals = _select_intervals(mode)
    data_dir = _text("Data directory", "data_lake")
    return {"MODE": mode, "SYMBOLS": symbols, "DATA_DIR": data_dir, "ARGS": f"--intervals {intervals} --start {start} --end {end}"}


def _header() -> None:
    print(f"{Style.CLEAR}", end="")
    print(f"  {Style.BG_BLUE}{Style.WHITE}{Style.BOLD}  V7 ENGINE — guided menu  {Style.RESET}")
    print(f"  {Style.BG_DARK}{Style.WHITE}  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} │ python={sys.executable}{Style.RESET}")
    print()


def action_quick_start() -> None:
    print(f"\n  {Style.BOLD}Quick Start{Style.RESET}")
    action = _choice(
        "What do you want to do?",
        [
            ("synthetic", "Run v0.2 synthetic pipeline smoke (safe, no download)"),
            ("download", "Download data with guided symbols/range"),
            ("health", "Check data health with guided symbols/range"),
            ("tests", "Run local tests"),
        ],
        default=1,
    )
    if action == "synthetic":
        mode = _select_mode()
        _run_make("pipeline-v0.2", {"MODE": mode, "ARGS": "--real --synthetic --steps-v02 validate,backfill,labels,features,report"})
    elif action == "download":
        action_data_download()
    elif action == "health":
        action_data_health()
    else:
        _run_make("test-all")


def action_data_download() -> None:
    opts = _data_options()
    opts["DRY_RUN"] = "1"
    print(f"\n  {Style.BOLD}Preview download command{Style.RESET}")
    _run_make("backfill", opts, pause=False)
    opts.pop("DRY_RUN", None)
    if _yes_no("Execute this download?", default=False):
        _run_make("backfill", opts)
    else:
        _press_enter()


def action_data_health() -> None:
    opts = _data_options()
    no_repair = not _yes_no("Allow auto-repair/backfill if data is missing?", default=False)
    if no_repair:
        opts["ARGS"] = f"{opts['ARGS']} --no-auto-repair"
    _run_make("data-health", opts)


def action_pipeline() -> None:
    mode = _select_mode()
    pipeline = _choice(
        "Pipeline",
        [
            ("v02_synthetic", "v0.2 synthetic smoke"),
            ("v02_real", "v0.2 real/cached data pipeline"),
            ("legacy_dry", "Legacy command dry-run preview"),
            ("report", "Generate empirical report only"),
        ],
        default=1,
    )
    if pipeline == "v02_synthetic":
        steps = _text("Steps", "validate,backfill,labels,features,train,wfv,report")
        force = " --force" if _yes_no("Bypass training gates?", default=False) else ""
        _run_make("pipeline-v0.2", {"MODE": mode, "ARGS": f"--real --synthetic --steps-v02 {steps}{force}"})
    elif pipeline == "v02_real":
        symbols = _select_symbols()
        start, end = _select_range()
        steps = _text("Steps", "validate,backfill,labels,features,train,wfv,report")
        force = " --force" if _yes_no("Bypass training gates?", default=False) else ""
        _run_make("pipeline-v0.2", {"MODE": mode, "ARGS": f"--real --no-synthetic --symbols-v02 {symbols} --start {start} --end {end} --steps-v02 {steps}{force}"})
    elif pipeline == "report":
        _run_make("report", {"MODE": mode})
    else:
        _run_make("pipeline", {"MODE": mode, "DRY_RUN": "1"})


def action_tests() -> None:
    scope = _choice(
        "Tests and checks",
        [
            ("test", "Lib tests"),
            ("system", "System tests (integration)"),
            ("all", "All local tests (lib + integration + simulation)"),
            ("contracts", "Contract checks"),
            ("boundaries", "Boundary checks"),
            ("validate", "Validate target (contracts + boundaries + system)"),
        ],
        default=3,
    )
    target = {"test": "test", "system": "test-system", "all": "test-all", "contracts": "check-contracts", "boundaries": "check-boundaries", "validate": "validate"}[scope]
    _run_make(target)


def action_reports() -> None:
    action = _choice(
        "Reports",
        [
            ("list", "List report types"),
            ("status", "Report status"),
            ("empirical", "Generate empirical ModeResearchReport"),
            ("menu", "Open AlphaForge report sub-menu"),
        ],
        default=1,
    )
    if action == "list":
        _run_make("af-report", {"ARGS": "list"})
    elif action == "status":
        _run_make("af-report", {"ARGS": "status"})
    elif action == "empirical":
        mode = _select_mode()
        _run_make("af-report", {"ARGS": f"generate empirical --mode {mode}"})
    else:
        _run_make("af-report", {"ARGS": "menu"})


def action_maintenance() -> None:
    action = _choice(
        "Maintenance / advanced",
        [
            ("install", "Install/update dependencies"),
            ("clean", "Clean caches/build artifacts"),
            ("lint", "Ruff lint"),
            ("typecheck", "Mypy typecheck"),
            ("candidate", "Candidate dry-run preview"),
            ("download-default", "Default download dry-run preview"),
        ],
        default=1,
    )
    if action == "clean" and not _yes_no("Remove caches/build artifacts?", default=False):
        return
    target_map = {
        "install": ("install", {}),
        "clean": ("clean", {}),
        "lint": ("lint", {}),
        "typecheck": ("typecheck", {}),
        "candidate": ("candidate", {"DRY_RUN": "1"}),
        "download-default": ("download", {"DRY_RUN": "1"}),
    }
    target, vars = target_map[action]
    _run_make(target, vars)


ACTIONS: list[tuple[str, str, Any]] = [
    ("quick", "Quick start / recommended workflows", action_quick_start),
    ("data", "Data download + health wizard", lambda: _data_submenu()),
    ("pipeline", "Pipeline runner", action_pipeline),
    ("tests", "Tests and validation", action_tests),
    ("reports", "Reports", action_reports),
    ("advanced", "Maintenance / advanced", action_maintenance),
]


def _data_submenu() -> None:
    action = _choice(
        "Data",
        [("download", "Download/backfill data"), ("health", "Check data health")],
        default=1,
    )
    if action == "download":
        action_data_download()
    else:
        action_data_health()


def _dispatch(key: str) -> None:
    for action_key, _, handler in ACTIONS:
        if key == action_key:
            handler()
            return
    # Direct command escape hatch for power users.
    direct = {
        "install": lambda: _run_make("install"),
        "test": lambda: _run_make("test"),
        "test-all": lambda: _run_make("test-all"),
        "backfill": action_data_download,
        "data-health": action_data_health,
        "report": action_reports,
    }
    if key in direct:
        direct[key]()
        return
    print(f"\n  {Style.RED}Unknown command: {key}{Style.RESET}")
    _press_enter()


def main() -> int:
    while True:
        _header()
        print(f"  {Style.BOLD}Choose a workflow:{Style.RESET}\n")
        key_map: dict[str, str] = {}
        for idx, (key, label, _) in enumerate(ACTIONS, 1):
            key_map[str(idx)] = key
            print(f"    {Style.BOLD}[{idx}]{Style.RESET} {Style.CYAN}{label}{Style.RESET}")
        print(f"    {Style.BOLD}[0]{Style.RESET} {Style.RED}Exit{Style.RESET}")
        print(f"\n  {Style.DIM}Tip: type a command directly, e.g. test-all, backfill, data-health.{Style.RESET}")
        try:
            raw = input(f"\n  {Style.BOLD}Selection:{Style.RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if raw in ("0", "exit", "quit"):
            print(f"\n  {Style.GREEN}Güle güle!{Style.RESET}")
            return 0
        if not raw:
            continue
        _dispatch(key_map.get(raw, raw))


if __name__ == "__main__":
    sys.exit(main())
