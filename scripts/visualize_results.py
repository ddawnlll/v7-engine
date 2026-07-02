#!/usr/bin/env python3
"""Terminal dashboard for AlphaForge training results — standalone, no alphaforge imports.

Renders a color ANSI dashboard with quality progress bars.

Usage (as module):
    from scripts.visualize_results import render_dashboard
    render_dashboard(metrics_dict)

Usage (CLI):
    python3 scripts/visualize_results.py data/reports/train-results-SCALP.json
    cat data/reports/train-results-SCALP.json | python3 scripts/visualize_results.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict


# ── ANSI 256-color helpers ───────────────────────────────────────────────

def _c(code: int) -> str:
    return f"\x1b[38;5;{code}m"


_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = _c(245)

# Palette
NEON_GREEN = _c(82)
GREEN = _c(34)
YELLOW = _c(220)
ORANGE = _c(208)
RED = _c(196)
DIM_WHITE = _c(245)
WHITE = _c(255)
CYAN = _c(51)
BLACK = _c(16)


# ── Quality scoring ──────────────────────────────────────────────────────


def _score_accuracy(acc: float) -> float:
    """3-class baseline is 0.33; SCALP can be lower due to low exposure."""
    if acc >= 0.40:
        return 1.0
    if acc <= 0.10:
        return 0.0
    return (acc - 0.10) / 0.30


def _score_sharpe(sharpe: float) -> float:
    if sharpe >= 5.0:
        return 1.0
    if sharpe <= 0.0:
        return 0.0
    return sharpe / 5.0


def _score_overfit_gap(gap: float) -> float:
    if gap <= 0.15:
        return 1.0
    if gap >= 0.60:
        return 0.0
    return 1.0 - (gap - 0.15) / 0.45


def _score_stability(stab: float) -> float:
    if stab >= 0.85:
        return 1.0
    if stab <= 0.50:
        return 0.0
    return (stab - 0.50) / 0.35


def _score_correlation(corr: float) -> float:
    if 0.30 <= corr <= 0.85:
        return 1.0
    if corr <= 0.0 or corr >= 1.0:
        return 0.0
    if corr < 0.30:
        return corr / 0.30
    return 1.0 - (corr - 0.85) / 0.15


def _score_pbo(pbo: str) -> float:
    mapping = {"LOW": 1.0, "MODERATE": 0.5, "HIGH": 0.15, "CRITICAL": 0.0}
    return mapping.get(pbo.upper(), 0.0)


def _score_exposure(exposure_pct: float, mode: str) -> float:
    if mode == "SCALP":
        if 5.0 <= exposure_pct <= 20.0:
            return 1.0
        if exposure_pct <= 1.0:
            return 0.0
        if exposure_pct > 50.0:
            return 0.3
        if exposure_pct < 5.0:
            return exposure_pct / 5.0
        return max(0.0, 1.0 - (exposure_pct - 20.0) / 30.0)
    if 10.0 <= exposure_pct <= 40.0:
        return 1.0
    if exposure_pct <= 2.0:
        return 0.0
    if exposure_pct < 10.0:
        return exposure_pct / 10.0
    return max(0.0, 1.0 - (exposure_pct - 40.0) / 40.0)


def _score_active_trades(trades: int, mode: str) -> float:
    threshold = 200 if mode == "SCALP" else 100
    if trades >= 5000:
        return 1.0
    if trades <= threshold:
        return max(0.0, trades / threshold * 0.5)
    return 0.5 + (trades - threshold) / (5000 - threshold) * 0.5


def compute_quality(metrics: Dict[str, Any], mode: str) -> float:
    """Composite 0.0–1.0 quality score."""
    weights = {
        "sharpe": 0.30,
        "accuracy": 0.10,
        "overfit_gap": 0.20,
        "stability": 0.10,
        "correlation": 0.05,
        "pbo": 0.15,
        "exposure": 0.05,
        "active_trades": 0.05,
    }
    score = 0.0
    score += weights["sharpe"] * _score_sharpe(metrics.get("sharpe_ratio", 0))
    score += weights["accuracy"] * _score_accuracy(metrics.get("accuracy", 0))
    score += weights["overfit_gap"] * _score_overfit_gap(metrics.get("overfit_gap", 0))
    score += weights["stability"] * _score_stability(metrics.get("accuracy_stability", 0))
    score += weights["correlation"] * _score_correlation(metrics.get("train_oos_correlation", 0))
    score += weights["pbo"] * _score_pbo(metrics.get("pbo_risk", "HIGH"))
    score += weights["exposure"] * _score_exposure(metrics.get("exposure_pct", 0), mode)
    score += weights["active_trades"] * _score_active_trades(metrics.get("total_active_trades", 0), mode)
    return min(1.0, max(0.0, score))


# ── Bar rendering ────────────────────────────────────────────────────────


def _color_for_value(value: float, good: float = 0.7, warn: float = 0.4) -> str:
    if value >= good:
        return NEON_GREEN
    if value >= warn:
        return YELLOW
    return RED


def _bar(value: float, width: int = 40, filled: str = "█", empty: str = "░") -> str:
    n_filled = int(round(value * width))
    n_empty = width - n_filled
    color = _color_for_value(value)
    return f"{color}{filled * n_filled}{_DIM}{empty * n_empty}{_RESET}"


def _pbo_colored(pbo: str) -> str:
    mapping = {"LOW": NEON_GREEN, "MODERATE": YELLOW, "HIGH": RED, "CRITICAL": f"{_c(196)}{_BOLD}"}
    c = mapping.get(pbo.upper(), WHITE)
    return f"{c}{pbo}{_RESET}"


def _colored_value(value: float, good: float = 0.7, warn: float = 0.4, fmt: str = ".4f") -> str:
    if value >= good:
        c = NEON_GREEN
    elif value >= warn:
        c = YELLOW
    else:
        c = RED
    return f"{c}{value:{fmt}}{_RESET}"


# ── Dashboard ────────────────────────────────────────────────────────────


def render_dashboard(metrics: Dict[str, Any]) -> None:
    """Render full terminal training dashboard."""
    mode = metrics.get("mode", "UNKNOWN")
    quality = compute_quality(metrics, mode)
    quality_pct = quality * 100
    quality_label = (
        f"{NEON_GREEN}EXCELLENT{_RESET}" if quality >= 0.8 else
        f"{GREEN}GOOD{_RESET}" if quality >= 0.65 else
        f"{YELLOW}FAIR{_RESET}" if quality >= 0.45 else
        f"{ORANGE}POOR{_RESET}" if quality >= 0.25 else
        f"{RED}CRITICAL{_RESET}"
    )

    # ── Header ───────────────────────────────────────────────────────
    print()
    print(f"{_BOLD}{CYAN}"
          f"  ╔══════════════════════════════════════════════════════════════╗\n"
          f"  ║          ALPHAFORGE TRAINING REPORT  —  {mode:<20s}║\n"
          f"  ╚══════════════════════════════════════════════════════════════╝"
          f"{_RESET}")

    # ── Performance ──────────────────────────────────────────────────
    acc = metrics.get("accuracy", 0)
    train_acc = metrics.get("train_accuracy", 0)
    sharpe = metrics.get("sharpe_ratio", 0)
    overfit = metrics.get("overfit_gap", 0)
    stability = metrics.get("accuracy_stability", 0)
    correlation = metrics.get("train_oos_correlation", 0)
    pbo = metrics.get("pbo_risk", "HIGH")

    def row(label: str, value: str, norm: float | None = None) -> str:
        bar_part = f"  {_bar(norm)}" if norm is not None else ""
        color = _color_for_value(norm) if norm is not None else WHITE
        return f"  {_DIM}{label:<28}{_RESET}{color}{_BOLD}{value:>10}{_RESET}{bar_part}"

    print(f"\n  {_BOLD}{WHITE}PERFORMANCE{_RESET}")
    print(f"  {_DIM}────────────────────────────────────────────────────────────────{_RESET}")
    print(row("Accuracy (OOS)", f"{acc:.4f}", _score_accuracy(acc)))
    print(row("Train Accuracy", f"{train_acc:.4f}", _score_accuracy(train_acc)))
    print(row("Accuracy Stability", f"{stability:.4f}", _score_stability(stability)))
    print(row("Sharpe Ratio (OOS)", f"{sharpe:.4f}", _score_sharpe(sharpe)))
    print(f"  {_DIM}────────────────────────────────────────────────────────────────{_RESET}")

    # ── Overfit ──────────────────────────────────────────────────────
    print(f"\n  {_BOLD}{WHITE}OVERFIT ANALYSIS{_RESET}")
    print(f"  {_DIM}────────────────────────────────────────────────────────────────{_RESET}")
    print(row("Overfit Gap", f"{overfit:.4f}", _score_overfit_gap(overfit)))
    print(row("Train-OOS Correlation", f"{correlation:.4f}", _score_correlation(correlation)))
    print(f"  {_DIM}PBO Risk:               {_RESET}{_pbo_colored(pbo)}  {_bar(_score_pbo(pbo), width=30)}")
    print(f"  {_DIM}────────────────────────────────────────────────────────────────{_RESET}")

    # ── Trades ───────────────────────────────────────────────────────
    active = metrics.get("total_active_trades", 0)
    long_trades = metrics.get("total_long", 0)
    short_trades = metrics.get("total_short", 0)
    no_trade = metrics.get("total_no_trade", 0)
    exposure = metrics.get("exposure_pct", 0)
    n_samples = metrics.get("n_samples", 0)
    n_folds = metrics.get("n_folds", 0)
    n_features = metrics.get("feature_count", 0)
    low_conf = metrics.get("low_conf_rate_pct", 0)
    net_r = metrics.get("net_expectancy_r", 0)
    gross_r = metrics.get("gross_expectancy_r", 0)

    long_pct = (long_trades / active * 100) if active > 0 else 0
    short_pct = (short_trades / active * 100) if active > 0 else 0
    exp_score = _score_exposure(exposure, mode)

    print(f"\n  {_BOLD}{WHITE}TRADE STATISTICS{_RESET}")
    print(f"  {_DIM}────────────────────────────────────────────────────────────────{_RESET}")
    print(f"  {_DIM}Active Trades:            {_RESET}{WHITE}{active:>10,}{_RESET}        {_DIM}{n_folds} walk-forward folds{_RESET}")
    print(f"  {_DIM}Direction:               {_RESET}{NEON_GREEN}LONG {long_trades:>5}{_RESET}  {RED}SHORT {short_trades:>5}{_RESET}  {_DIM}NO_TRADE {no_trade:>5}{_RESET}")
    split_bar = _bar(long_pct / 100, width=20)
    print(f"  {_DIM}Direction Split:          {_RESET}{split_bar}  {NEON_GREEN}{long_pct:.0f}% L{_RESET} / {RED}{short_pct:.0f}% S{_RESET}")
    print(f"  {_DIM}Exposure:                 {_RESET}{_colored_value(exposure, 15, 5, '.1f')}%{_RESET}  {_bar(exp_score, width=30)}")
    print(f"  {_DIM}Low-Confidence Rate:      {_RESET}{_colored_value(100 - low_conf, 30, 15, '.1f')}% confident{_RESET}  ({low_conf:.0f}% low-conf)")
    print(f"  {_DIM}Net Expectancy R:         {_RESET}{_colored_value(net_r, 0.01, 0.0, '.6f')}{_RESET}")
    print(f"  {_DIM}Gross Expectancy R:       {_RESET}{_colored_value(gross_r, 0.015, 0.0, '.6f')}{_RESET}")

    # ── Dataset ──────────────────────────────────────────────────────
    cd = metrics.get("cost_decomposition", {})
    fee = cd.get("fee_pct", 0)
    rt_cost = cd.get("round_trip_cost_bps", 0)
    features = metrics.get("features", [])

    print(f"\n  {_BOLD}{WHITE}DATASET{_RESET}")
    print(f"  {_DIM}────────────────────────────────────────────────────────────────{_RESET}")
    print(f"  {_DIM}Samples:                  {_RESET}{WHITE}{n_samples:>10,}{_RESET}")
    print(f"  {_DIM}Features:                 {_RESET}{WHITE}{n_features:>10}{_RESET}  {_DIM}{', '.join(features[:4])}{_RESET}")
    if len(features) > 4:
        print(f"  {_DIM}                          {_RESET}{_DIM}+{len(features) - 4} more{_RESET}")
    print(f"  {_DIM}Fee:                      {_RESET}{WHITE}{fee}%{_RESET}  {_DIM}({rt_cost} bps round-trip){_RESET}")

    # ── Overall Quality Bar ─────────────────────────────────────────
    pbo_ok = _score_pbo(pbo) >= 0.5
    overfit_ok = _score_overfit_gap(overfit) >= 0.5

    warnings = []
    if not pbo_ok:
        warnings.append(f"{_BOLD}{RED}PBO RISK{_RESET}")
    if not overfit_ok:
        warnings.append(f"{_BOLD}{YELLOW}OVERFIT{_RESET}")
    if low_conf > 80:
        warnings.append(f"{_BOLD}{YELLOW}LOW CONFIDENCE{_RESET}")

    bar_width = 52
    print()
    print(f"  {_BOLD}{WHITE}╔{'═' * 54}╗{_RESET}")
    print(f"  {_BOLD}{WHITE}║{_RESET}           {_BOLD}OVERALL MODEL QUALITY:  {quality_label:<14s}{_BOLD}{WHITE}         ║{_RESET}")
    print(f"  {_BOLD}{WHITE}║{_RESET}              {_bar(quality, bar_width, filled='━', empty='─')}    {_color_for_value(quality, 0.65, 0.45)}{quality_pct:>5.1f}%{_RESET}{_BOLD}{WHITE}   ║{_RESET}")
    print(f"  {_BOLD}{WHITE}║{_RESET}                          {_DIM}sharpe={sharpe:.1f}  acc={acc:.3f}{_RESET}                 {_BOLD}{WHITE}║{_RESET}")

    if warnings:
        warn_str = "  ⚠  " + "  ".join(warnings)
        pad = 54 - len(warn_str) + 16
        print(f"  {_BOLD}{WHITE}║{_RESET}  {warn_str}{' ' * max(0, pad)}{_BOLD}{WHITE}║{_RESET}")

    print(f"  {_BOLD}{WHITE}╚{'═' * 54}╝{_RESET}")
    print()


# ── CLI ──────────────────────────────────────────────────────────────────


def main():
    if not sys.stdin.isatty() and len(sys.argv) <= 1:
        data = json.load(sys.stdin)
    elif len(sys.argv) > 1:
        path = Path(sys.argv[1])
        if not path.exists():
            print(f"Error: file not found: {path}", file=sys.stderr)
            sys.exit(1)
        with open(path) as f:
            data = json.load(f)
    else:
        print("Usage: python3 scripts/visualize_results.py <report.json>", file=sys.stderr)
        print("   or: cat report.json | python3 scripts/visualize_results.py", file=sys.stderr)
        sys.exit(1)
    render_dashboard(data)


if __name__ == "__main__":
    main()
