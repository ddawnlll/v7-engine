"""Alpha rejection engine — evaluates alphas against configurable criteria.

Produces structured rejection reasons for weak/noisy alphas and clear
promotion signalling for profitable ones.

Decision levels:
  REJECT   — Alpha fails critical thresholds, is not viable.
  WATCH    — Alpha passes critical thresholds but has secondary concerns.
             Should not be promoted but may improve with tuning.
  PROMOTE  — All criteria met.  Alpha is ready for V7 handoff evaluation.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("alphaforge.discovery.rejection")


# ---------------------------------------------------------------------------
# Default thresholds
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS: dict[str, dict] = {
    "MIN_TRADES": {
        "threshold": 30,
        "critical": True,
        "description": "At least 30 active trades for statistical significance",
    },
    "PROFIT_FACTOR": {
        "threshold": 1.2,
        "critical": True,
        "description": "Profit factor >= 1.2 beats random",
    },
    "EXPECTANCY_R": {
        "threshold": 0.10,
        "critical": True,
        "description": "Positive edge per trade after costs (E[R] >= 0.10R)",
    },
    "SHARPE": {
        "threshold": 0.5,
        "critical": True,
        "description": "Risk-adjusted return (Sharpe >= 0.5)",
    },
    "MAX_DRAWDOWN": {
        "threshold": -5.0,
        "critical": True,
        "description": "Max drawdown >= -5.0R (stop catastrophic loss)",
    },
    "WIN_RATE": {
        "threshold": 0.35,
        "critical": False,
        "description": "Win rate >= 0.35 (not entirely lucky)",
    },
    "COST_DRAG": {
        "threshold": 50.0,
        "critical": False,
        "description": "Cost drag <= 50% of gross return (edge not eaten by costs)",
    },
    "SYMBOL_DIVERSITY": {
        "threshold": 0.50,
        "critical": False,
        "description": "No single symbol > 50% of total edge",
    },
}

# Disqualifying thresholds — alpha is REJECTED if ANY of these fail
CRITICAL_RULES = {
    name for name, cfg in DEFAULT_THRESHOLDS.items() if cfg["critical"]
}


def evaluate_alpha(
    metrics: dict,
    thresholds: dict | None = None,
    mode: str = "",
) -> dict:
    """Evaluate alpha candidate against rejection criteria.

    Parameters
    ----------
    metrics:
        Profitability metrics dict from ``analyze_profitability()``.
    thresholds:
        Optional dict of threshold overrides (same structure as
        ``DEFAULT_THRESHOLDS``).  Per-key overrides merge with defaults.
    mode:
        Trading mode label (included in output for traceability).

    Returns
    -------
    dict with keys:

    - ``decision`` — ``'PROMOTE'`` / ``'WATCH'`` / ``'REJECT'``
    - ``reasons`` — list of per-rule evaluation dicts
    - ``summary`` — human-readable summary string
    """
    cfg = {**DEFAULT_THRESHOLDS}
    if thresholds:
        for k, v in thresholds.items():
            if k in cfg:
                cfg[k].update(v)

    meta = metrics.get("metadata", {})
    ret = metrics.get("return_metrics", {})
    risk = metrics.get("risk_metrics", {})
    cost = metrics.get("cost_decomposition", {})
    sym = metrics.get("symbol_breakdown", {})

    n_trades = meta.get("total_trades", 0)
    expectancy_r = ret.get("expectancy_R", 0.0)
    sharpe = risk.get("sharpe_ratio", 0.0)
    profit_factor = risk.get("profit_factor", 0.0)
    max_dd = risk.get("max_drawdown_R", 0.0)
    win_rate = risk.get("win_rate", 0.0)
    cost_drag = cost.get("cost_drag_pct", 0.0)
    dominant_share = sym.get("dominant_share", 0.0)

    reasons: list[dict] = []

    # ── Rule evaluations ──

    # 1. MIN_TRADES
    t = cfg["MIN_TRADES"]["threshold"]
    passed = n_trades >= t
    reasons.append({
        "rule": "MIN_TRADES",
        "passed": passed,
        "critical": cfg["MIN_TRADES"]["critical"],
        "detail": f"{n_trades} trades {'>=' if passed else '<'} {t}",
    })

    # 2. PROFIT_FACTOR
    t = cfg["PROFIT_FACTOR"]["threshold"]
    passed = profit_factor >= t
    reasons.append({
        "rule": "PROFIT_FACTOR",
        "passed": passed,
        "critical": cfg["PROFIT_FACTOR"]["critical"],
        "detail": f"PF={profit_factor:.2f} {'>=' if passed else '<'} {t}",
    })

    # 3. EXPECTANCY_R
    t = cfg["EXPECTANCY_R"]["threshold"]
    passed = expectancy_r >= t
    reasons.append({
        "rule": "EXPECTANCY_R",
        "passed": passed,
        "critical": cfg["EXPECTANCY_R"]["critical"],
        "detail": f"E[R]={expectancy_r:.4f}R {'>=' if passed else '<'} {t}R",
    })

    # 4. SHARPE
    t = cfg["SHARPE"]["threshold"]
    passed = sharpe >= t
    reasons.append({
        "rule": "SHARPE",
        "passed": passed,
        "critical": cfg["SHARPE"]["critical"],
        "detail": f"Sharpe={sharpe:.4f} {'>=' if passed else '<'} {t}",
    })

    # 5. MAX_DRAWDOWN
    t = cfg["MAX_DRAWDOWN"]["threshold"]
    passed = max_dd >= t
    reasons.append({
        "rule": "MAX_DRAWDOWN",
        "passed": passed,
        "critical": cfg["MAX_DRAWDOWN"]["critical"],
        "detail": f"Max DD={max_dd:.2f}R {'>=' if passed else '<'} {t}R",
    })

    # 6. WIN_RATE
    t = cfg["WIN_RATE"]["threshold"]
    passed = win_rate >= t
    reasons.append({
        "rule": "WIN_RATE",
        "passed": passed,
        "critical": cfg["WIN_RATE"]["critical"],
        "detail": f"Win rate={win_rate:.2%} {'>=' if passed else '<'} {t:.0%}",
    })

    # 7. COST_DRAG
    t = cfg["COST_DRAG"]["threshold"]
    passed = cost_drag <= t
    reasons.append({
        "rule": "COST_DRAG",
        "passed": passed,
        "critical": cfg["COST_DRAG"]["critical"],
        "detail": f"Cost drag={cost_drag:.1f}% {'<=' if passed else '>'} {t:.0f}%",
    })

    # 8. SYMBOL_DIVERSITY
    t = cfg["SYMBOL_DIVERSITY"]["threshold"]
    passed = dominant_share <= t
    reasons.append({
        "rule": "SYMBOL_DIVERSITY",
        "passed": passed,
        "critical": cfg["SYMBOL_DIVERSITY"]["critical"],
        "detail": f"Dominant share={dominant_share:.1%} {'<=' if passed else '>'} {t:.0%}",
    })

    # ── Decision logic ──
    critical_failures = [r for r in reasons if r["critical"] and not r["passed"]]
    non_critical_failures = [r for r in reasons if not r["critical"] and not r["passed"]]

    if critical_failures:
        decision = "REJECT"
        failed_rules = [r["rule"] for r in critical_failures]
        summary = (
            f"REJECTED: {len(critical_failures)} critical rule(s) failed: "
            f"{', '.join(failed_rules)}. "
            f"E[R]={expectancy_r:.4f}R, PF={profit_factor:.2f}, "
            f"Sharpe={sharpe:.2f}, Trades={n_trades}"
        )
    elif non_critical_failures:
        decision = "WATCH"
        failed_rules = [r["rule"] for r in non_critical_failures]
        summary = (
            f"WATCH: {len(non_critical_failures)} non-critical rule(s) failed: "
            f"{', '.join(failed_rules)}. "
            f"E[R]={expectancy_r:.4f}R, PF={profit_factor:.2f}"
        )
    else:
        decision = "PROMOTE"
        summary = (
            f"PROMOTE: All {len(reasons)} rules passed. "
            f"E[R]={expectancy_r:.4f}R, PF={profit_factor:.2f}, "
            f"Sharpe={sharpe:.2f}, Trades={n_trades}"
        )

    logger.info("Alpha %s (%s)", decision, mode)

    return {
        "decision": decision,
        "reasons": reasons,
        "summary": summary,
        "mode": mode,
    }


def rejection_to_verdict(rejection_decision: str) -> str:
    """Map rejection engine decision to empirical report verdict string."""
    mapping = {
        "REJECT": "REJECT",
        "WATCH": "CONTINUE_RESEARCH",
        "PROMOTE": "CANDIDATE_FOR_V7_GATES",
    }
    return mapping.get(rejection_decision, "CONTINUE_RESEARCH")
