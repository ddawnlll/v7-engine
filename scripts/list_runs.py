#!/usr/bin/env python3
"""List recent AlphaForge training runs and their stats.

Scans three sources:
  1. data/reports/train-results-*.json     — direct ``python3 -m alphaforge.train`` runs
  2. data/reports/{mode}/*.json             — pipeline ModeResearchReport runs
  3. alphaforge_report/research_run_index.json — canonical run index

Usage:
    python3 scripts/list_runs.py
    python3 scripts/list_runs.py --limit 5
    python3 scripts/list_runs.py --mode SCALP
"""

from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent

# ── ANSI 256-color helpers ───────────────────────────────────────────────

_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = "\x1b[38;5;245m"
NEON_GREEN = "\x1b[38;5;82m"
GREEN = "\x1b[38;5;34m"
YELLOW = "\x1b[38;5;220m"
ORANGE = "\x1b[38;5;208m"
RED = "\x1b[38;5;196m"
CYAN = "\x1b[38;5;51m"
WHITE = "\x1b[38;5;255m"
MAGENTA = "\x1b[38;5;200m"
BLUE = "\x1b[38;5;75m"
PURPLE = "\x1b[38;5;99m"


def _c(v: float, good: float = 0.7, warn: float = 0.4) -> str:
    return NEON_GREEN if v >= good else YELLOW if v >= warn else RED


def _sharpe_color(s: float) -> str:
    return NEON_GREEN if s >= 3.0 else GREEN if s >= 1.0 else YELLOW if s >= 0 else RED


def _acc_color(a: float) -> str:
    return NEON_GREEN if a >= 0.40 else GREEN if a >= 0.30 else YELLOW if a >= 0.20 else RED


def _pbo_color(p: str) -> str:
    return {"LOW": NEON_GREEN, "MODERATE": YELLOW, "HIGH": RED, "CRITICAL": f"{_BOLD}{RED}"}.get(p.upper(), _DIM)


def _verdict_color(v: str) -> str:
    if "REJECT" in v:
        return RED
    if "WEAK" in v:
        return YELLOW
    if "VALID" in v or "CANDIDATE" in v:
        return NEON_GREEN
    if "PASS" in v:
        return GREEN
    return _DIM


# ── Sources ──────────────────────────────────────────────────────────────


def _scan_train_results() -> List[Dict[str, Any]]:
    """Read data/reports/train-results-*.json files."""
    runs = []
    for path in sorted(glob.glob(str(REPO_ROOT / "data/reports/train-results-*.json"))):
        try:
            with open(path) as f:
                d = json.load(f)
            ts_str = os.path.basename(path).replace("train-results-", "").replace(".json", "")
            runs.append({
                "source": "TRAIN",
                "run_id": os.path.basename(path),
                "mode": d.get("mode", "?"),
                "timestamp": _parse_timestamp_from_name(path, ts_str),
                "accuracy": d.get("accuracy", 0),
                "train_accuracy": d.get("train_accuracy", 0),
                "sharpe": d.get("sharpe_ratio", 0),
                "overfit_gap": d.get("overfit_gap", 0),
                "pbo": d.get("pbo_risk", "?"),
                "stability": d.get("accuracy_stability", 0),
                "n_samples": d.get("n_samples", 0),
                "n_folds": d.get("n_folds", 0),
                "active_trades": d.get("total_active_trades", 0),
                "long": d.get("total_long", 0),
                "short": d.get("total_short", 0),
                "exposure": d.get("exposure_pct", 0),
                "n_features": d.get("feature_count", 0),
                "net_expectancy_r": d.get("net_expectancy_r", 0),
                "verdict": "PASS",
                "path": path,
            })
        except Exception as e:
            runs.append({"source": "TRAIN", "run_id": os.path.basename(path), "mode": "?", "error": str(e), "path": path})
    return runs


def _scan_pipeline_reports() -> List[Dict[str, Any]]:
    """Scan data/reports/{mode}/*.json for ModeResearchReport runs."""
    known_modes = {"swing", "scalp", "aggressive_scalp"}
    runs = []
    for mode_dir in sorted(glob.glob(str(REPO_ROOT / "data/reports/[a-z]*/"))):
        mode_name = os.path.basename(os.path.normpath(mode_dir)).lower()
        if mode_name not in known_modes:
            continue
        mode_map = {"swing": "SWING", "scalp": "SCALP", "aggressive_scalp": "AGGRESSIVE_SCALP"}
        mode = mode_map.get(mode_name, mode_name.upper())
        for path in sorted(glob.glob(os.path.join(mode_dir, "*.json"))):
            try:
                with open(path) as f:
                    d = json.load(f)
                m = d.get("metrics", {})
                sharpe_val = m.get("oos_sharpe", {})
                sharpe = sharpe_val.get("value", 0) if isinstance(sharpe_val, dict) else 0
                winrate_val = m.get("oos_win_rate", {})
                winrate = winrate_val.get("value", 0) if isinstance(winrate_val, dict) else 0
                trades = m.get("oos_trade_count", m.get("active_trade_count", 0))
                exposure = m.get("exposure_pct", 0)
                verdict = d.get("verdict", "?")
                if isinstance(verdict, dict):
                    verdict = verdict.get("overall_verdict", str(verdict))
                runs.append({
                    "source": "PIPELINE",
                    "run_id": os.path.basename(path),
                    "mode": mode,
                    "timestamp": _parse_timestamp_from_name(path, os.path.basename(path)),
                    "accuracy": winrate,
                    "sharpe": sharpe,
                    "active_trades": trades,
                    "exposure": exposure,
                    "verdict": verdict,
                    "n_folds": d.get("validation_summary", {}).get("fold_count", d.get("fold_count", 0)),
                    "path": path,
                })
            except Exception:
                pass
    return runs


def _scan_run_index() -> List[Dict[str, Any]]:
    """Read the canonical run index."""
    idx_path = REPO_ROOT / "alphaforge_report" / "research_run_index.json"
    if not idx_path.exists():
        return []
    try:
        with open(idx_path) as f:
            data = json.load(f)
        return [
            {
                "source": "INDEX",
                "run_id": r.get("run_id", "?"),
                "mode": r.get("mode", "?"),
                "timestamp": r.get("timestamp", "?"),
                "verdict": r.get("verdict", "?"),
                "status": r.get("status", "?"),
                "path": r.get("canonical_report_path", ""),
            }
            for r in data.get("runs", [])
        ]
    except Exception:
        return []


def _parse_timestamp_from_name(path: str, name: str) -> str:
    """Extract a human-readable timestamp from various report filename formats."""
    import re

    # Try ISO-like patterns: 20260701T085239
    m = re.search(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})", name)
    if m:
        try:
            dt = datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5]), int(m[6]))
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass
    # Try file modification time as fallback
    try:
        mtime = os.path.getmtime(path)
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return name[:16]


# ── Display ──────────────────────────────────────────────────────────────


def _fmt(v: Any, width: int = 10) -> str:
    s = str(v) if v is not None else ""
    return s[:width].rjust(width)


def _mode_box(mode: str) -> str:
    colors = {"SCALP": CYAN, "AGGRESSIVE_SCALP": MAGENTA, "SWING": BLUE}
    c = colors.get(mode, WHITE)
    return f"{c}{mode:<16s}{_RESET}"


def render_run_table(runs: List[Dict[str, Any]], limit: int = 20) -> None:
    """Render a terminal table of recent runs."""
    if not runs:
        print(f"\n  {_DIM}No runs found.{_RESET}")
        return

    # Sort by timestamp descending
    def _sort_key(r):
        ts = r.get("timestamp", "")
        if isinstance(ts, str):
            return ts
        return str(ts)

    runs = sorted(runs, key=_sort_key, reverse=True)[:limit]

    # Column widths
    col_run = 30
    col_mode = 16
    col_ts = 16
    col_acc = 8
    col_sharpe = 8
    col_gap = 8
    col_trades = 8
    col_exp = 7
    col_verdict = 18

    sep = f"  {_DIM}{'─' * (col_run + col_mode + col_ts + col_acc + col_sharpe + col_gap + col_trades + col_exp + col_verdict + 8)}{_RESET}"

    # Header
    print(f"\n  {_BOLD}{WHITE}RECENT ALPHAFORGE RUNS{_RESET}")
    print(sep)
    hdr = (
        f"  {_BOLD}{_DIM}{'RUN':<{col_run}}{'MODE':<{col_mode}}{'DATE':<{col_ts}}"
        f"{'ACC':>{col_acc}}{'SHARPE':>{col_sharpe}}{'GAP':>{col_gap}}"
        f"{'TRADES':>{col_trades}}{'EXP%':>{col_exp}}{'VERDICT':<{col_verdict}}{_RESET}"
    )
    print(hdr)
    print(sep)

    for r in runs:
        mode = r.get("mode", "?")
        source = r.get("source", "?")

        # Format based on available fields
        if "error" in r:
            print(f"  {_DIM}{r['run_id'][:col_run]:<{col_run}}{_RESET}  {RED}ERROR: {r['error']}{_RESET}")
            continue

        run_id = r.get("run_id", "?")[:col_run]
        ts = str(r.get("timestamp", "?"))[:col_ts]

        has_metrics = "accuracy" in r
        if has_metrics and r.get("accuracy") is not None:
            acc = r["accuracy"]
            sharpe = r.get("sharpe", 0)
            gap = r.get("overfit_gap", 0)
            trades = r.get("active_trades", 0)
            exp = r.get("exposure", 0)
            verdict = r.get("verdict", "?")[:col_verdict]

            acc_str = f"{_c(acc, 0.40, 0.20)}{acc:.4f}{_RESET}"
            sharpe_str = f"{_sharpe_color(sharpe)}{sharpe:.2f}{_RESET}"
            gap_str = f"{_c(1 - gap, 0.85, 0.60)}{gap:.4f}{_RESET}"  # inverted: lower gap is better
            trades_str = f"{WHITE}{trades:>6}{_RESET}" if trades > 0 else f"{_DIM}{'0':>6}{_RESET}"
            exp_str = f"{YELLOW}{exp:>5.1f}{_RESET}" if exp > 0 else f"{_DIM}{'0':>5}{_RESET}"
            verdict_str = f"{_verdict_color(verdict)}{verdict:<{col_verdict}}{_RESET}"

            # Source indicator
            src_tag = f"{CYAN}T{_RESET}" if source == "TRAIN" else f"{PURPLE}P{_RESET}" if source == "PIPELINE" else f"{_DIM}I{_RESET}"

            print(
                f"  {src_tag} {run_id:<{col_run-2}}"
                f"{_mode_box(mode)}"
                f"{_DIM}{ts:<{col_ts}}{_RESET}"
                f"{acc_str:>{col_acc+9}}"
                f"{sharpe_str:>{col_sharpe+9}}"
                f"{gap_str:>{col_gap+9}}"
                f"{trades_str:>{col_trades+9}}"
                f"{exp_str:>{col_exp+9}}"
                f"  {verdict_str}"
            )
        else:
            # Minimal row (from run index)
            verdict = r.get("verdict", "?")[:col_verdict]
            verdict_str = f"{_verdict_color(verdict)}{verdict:<{col_verdict}}{_RESET}"
            status = r.get("status", "")
            status_tag = f" [{_DIM}{status}{_RESET}]" if status else ""

            print(
                f"  {_DIM}I{_RESET} {run_id:<{col_run-2}}"
                f"{_mode_box(mode)}"
                f"{_DIM}{ts:<{col_ts}}{_RESET}"
                f"{_DIM}{'─':>{col_acc+9}}{_RESET}"
                f"{_DIM}{'─':>{col_sharpe+9}}{_RESET}"
                f"{_DIM}{'─':>{col_gap+9}}{_RESET}"
                f"{_DIM}{'─':>{col_trades+9}}{_RESET}"
                f"{_DIM}{'─':>{col_exp+9}}{_RESET}"
                f"  {verdict_str}{status_tag}"
            )

    print(sep)
    print(f"  {_DIM}{_DIM}T{_RESET}{_DIM}=alphaforge.train  {PURPLE}P{_RESET}{_DIM}=pipeline  {_DIM}I{_RESET}{_DIM}=run index{_RESET}")
    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="List recent AlphaForge training runs")
    parser.add_argument("--limit", type=int, default=20, help="Max runs to show")
    parser.add_argument("--mode", type=lambda s: s.upper(), default=None, help="Filter by mode (SCALP, SWING, AGGRESSIVE_SCALP)")
    args = parser.parse_args()

    runs = []
    runs.extend(_scan_train_results())
    runs.extend(_scan_pipeline_reports())
    runs.extend(_scan_run_index())

    if args.mode:
        runs = [r for r in runs if r.get("mode", "").upper() == args.mode]

    render_run_table(runs, limit=args.limit)


if __name__ == "__main__":
    main()
