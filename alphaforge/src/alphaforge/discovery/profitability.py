"""Profitability analysis — computes trade metrics from simulation engine outputs.

Takes ``BacktestTradeResult`` objects (produced by Phase 3) and computes
canonical profitability metrics: return profile, risk metrics, cost
decomposition, exit breakdown, and per-symbol/side analysis.

All metrics are computed from the simulation engine's authoritative
``realized_r_net`` values — NOT label approximations.  This is the
economic truth assessment for alpha rejection/acceptance decisions.

Metric ownership (per discovery_authority.md):
  AlphaForge computes trade-level metrics INTERNALLY for rejection decisions.
  The empirical report (Phase 6) correctly attributes metric ownership per
  the V7 domain boundaries.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from alphaforge.discovery import BacktestTradeResult

logger = logging.getLogger("alphaforge.discovery.profitability")


def analyze_profitability(
    trades: list[BacktestTradeResult],
    mode: str = "",
) -> dict:
    """Compute full profitability metrics from simulation backtest results.

    Parameters
    ----------
    trades:
        List of ``BacktestTradeResult`` from ``backtest_signals()``.
        May be empty (all values are zero-safe).
    mode:
        Trading mode label (included in output metadata).

    Returns
    -------
    dict with sections:

    - ``trade_counts`` — total, long, short counts
    - ``return_metrics`` — total/avg/median net R, expectancy_R
    - ``risk_metrics`` — profit_factor, sharpe, max_drawdown_R, win_rate
    - ``exit_breakdown`` — stop/target/time-exit frequencies
    - ``cost_decomposition`` — total fee/slippage/funding cost in R
    - ``symbol_breakdown`` — per-symbol expectancy and concentration
    - ``side_breakdown`` — long vs short metrics
    - ``metadata`` — trade count, duration range
    """
    n = len(trades)

    # ------------------------------------------------------------------
    # Extract arrays
    # ------------------------------------------------------------------
    net_r = np.array([t.realized_r_net for t in trades], dtype=np.float64)
    gross_r = np.array([t.realized_r_gross for t in trades], dtype=np.float64)
    fee_r = np.array([t.fee_cost_r for t in trades], dtype=np.float64)
    slippage_r = np.array([t.slippage_cost_r for t in trades], dtype=np.float64)
    funding_r = np.array([t.funding_cost_r for t in trades], dtype=np.float64)
    hold_bars = np.array([t.hold_bars for t in trades], dtype=np.float64)
    path_q = np.array([t.path_quality_score for t in trades], dtype=np.float64)
    sides = [t.signal.side for t in trades]
    symbols = [t.signal.symbol for t in trades]
    exits = [t.exit_reason for t in trades]

    # ------------------------------------------------------------------
    # Trade counts
    # ------------------------------------------------------------------
    long_count = int(sum(1 for s in sides if s == "LONG"))
    short_count = int(sum(1 for s in sides if s == "SHORT"))
    total_active = n

    # ------------------------------------------------------------------
    # Return metrics
    # ------------------------------------------------------------------
    total_net_R = float(np.sum(net_r)) if n > 0 else 0.0
    total_gross_R = float(np.sum(gross_r)) if n > 0 else 0.0
    avg_net_R = float(np.mean(net_r)) if n > 0 else 0.0
    median_net_R = float(np.median(net_r)) if n > 0 else 0.0
    expectancy_R = avg_net_R  # expectancy = mean R per trade

    # ------------------------------------------------------------------
    # Risk metrics
    # ------------------------------------------------------------------
    # Profit factor
    gross_profit = float(np.sum(net_r[net_r > 0])) if n > 0 and any(net_r > 0) else 0.0
    gross_loss = float(np.abs(np.sum(net_r[net_r < 0]))) if n > 0 and any(net_r < 0) else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

    # Win rate
    win_count = int(np.sum(net_r > 0)) if n > 0 else 0
    win_rate = win_count / n if n > 0 else 0.0

    # Max drawdown (peak-to-trough of cumulative net R)
    if n > 0:
        cum_R = np.cumsum(net_r)
        peak = np.maximum.accumulate(cum_R)
        drawdowns = cum_R - peak
        max_drawdown_R = float(np.min(drawdowns))
    else:
        max_drawdown_R = 0.0

    # Sharpe ratio (of trade-level net R values)
    if n > 1:
        std_r = float(np.std(net_r, ddof=1))
        sharpe = (avg_net_R / std_r * np.sqrt(252)) if std_r > 1e-12 else 0.0
    else:
        sharpe = 0.0

    # Calmar-like: return / |max_drawdown|
    calmar_ratio = avg_net_R / abs(max_drawdown_R) if abs(max_drawdown_R) > 1e-12 else 0.0

    # ------------------------------------------------------------------
    # Exit breakdown
    # ------------------------------------------------------------------
    stop_count = int(sum(1 for e in exits if "STOP" in e.upper()))
    target_count = int(sum(1 for e in exits if "TARGET" in e.upper()))
    time_exit_count = int(sum(1 for e in exits if "TIME" in e.upper() or "HORIZON" in e.upper()))
    other_exit_count = n - stop_count - target_count - time_exit_count

    # ------------------------------------------------------------------
    # Cost decomposition
    # ------------------------------------------------------------------
    total_fee_R = float(np.sum(fee_r)) if n > 0 else 0.0
    total_slippage_R = float(np.sum(slippage_r)) if n > 0 else 0.0
    total_funding_R = float(np.sum(funding_r)) if n > 0 else 0.0
    total_cost_R = total_fee_R + total_slippage_R + total_funding_R

    avg_hold = float(np.mean(hold_bars)) if n > 0 else 0.0
    avg_path_q = float(np.mean(path_q)) if n > 0 else 0.0

    # ------------------------------------------------------------------
    # Symbol breakdown
    # ------------------------------------------------------------------
    sym_net_r: dict[str, float] = {}
    sym_count: dict[str, int] = {}
    for t in trades:
        sym = t.signal.symbol
        sym_net_r[sym] = sym_net_r.get(sym, 0.0) + t.realized_r_net
        sym_count[sym] = sym_count.get(sym, 0) + 1

    symbol_metrics = {}
    for sym in sorted(sym_net_r.keys()):
        symbol_metrics[sym] = {
            "total_net_R": round(sym_net_r[sym], 6),
            "trade_count": sym_count[sym],
            "avg_net_R": round(sym_net_r[sym] / sym_count[sym], 6) if sym_count[sym] > 0 else 0.0,
        }

    # Concentration
    total_abs_r = sum(abs(v) for v in sym_net_r.values())
    if total_abs_r > 0 and sym_net_r:
        best_sym = max(sym_net_r, key=lambda k: abs(sym_net_r[k]))
        dominant_share = abs(sym_net_r[best_sym]) / total_abs_r
    else:
        best_sym = ""
        dominant_share = 0.0

    # ------------------------------------------------------------------
    # Side breakdown
    # ------------------------------------------------------------------
    long_r = [t.realized_r_net for t in trades if t.signal.side == "LONG"]
    short_r = [t.realized_r_net for t in trades if t.signal.side == "SHORT"]
    side_metrics = {
        "long": {
            "count": len(long_r),
            "total_net_R": round(sum(long_r), 6) if long_r else 0.0,
            "avg_net_R": round(float(np.mean(long_r)), 6) if long_r else 0.0,
            "win_rate": round(float(np.mean([r > 0 for r in long_r])), 4) if long_r else 0.0,
        },
        "short": {
            "count": len(short_r),
            "total_net_R": round(sum(short_r), 6) if short_r else 0.0,
            "avg_net_R": round(float(np.mean(short_r)), 6) if short_r else 0.0,
            "win_rate": round(float(np.mean([r > 0 for r in short_r])), 4) if short_r else 0.0,
        },
    }

    # ------------------------------------------------------------------
    # Assemble result
    # ------------------------------------------------------------------
    result = {
        "metadata": {
            "mode": mode,
            "total_trades": n,
            "long_trades": long_count,
            "short_trades": short_count,
        },
        "return_metrics": {
            "total_gross_R": round(total_gross_R, 6),
            "total_net_R": round(total_net_R, 6),
            "avg_net_R": round(avg_net_R, 6),
            "median_net_R": round(median_net_R, 6),
            "expectancy_R": round(expectancy_R, 6),
        },
        "risk_metrics": {
            "profit_factor": round(profit_factor, 4),
            "sharpe_ratio": round(sharpe, 4),
            "max_drawdown_R": round(max_drawdown_R, 4),
            "calmar_ratio": round(calmar_ratio, 4),
            "win_rate": round(win_rate, 4),
            "avg_hold_bars": round(avg_hold, 2),
            "avg_path_quality": round(avg_path_q, 4),
        },
        "exit_breakdown": {
            "stop_hit": stop_count,
            "target_hit": target_count,
            "time_exit": time_exit_count,
            "other": other_exit_count,
            "stop_pct": round(stop_count / n * 100, 1) if n > 0 else 0.0,
            "target_pct": round(target_count / n * 100, 1) if n > 0 else 0.0,
            "time_exit_pct": round(time_exit_count / n * 100, 1) if n > 0 else 0.0,
        },
        "cost_decomposition": {
            "total_fee_cost_R": round(total_fee_R, 6),
            "total_slippage_cost_R": round(total_slippage_R, 6),
            "total_funding_cost_R": round(total_funding_R, 6),
            "total_cost_R": round(total_cost_R, 6),
            "avg_cost_per_trade_R": round(total_cost_R / n, 6) if n > 0 else 0.0,
            "cost_drag_pct": round(total_cost_R / abs(total_gross_R) * 100, 2) if abs(total_gross_R) > 1e-12 else 0.0,
        },
        "symbol_breakdown": {
            "symbols": symbol_metrics,
            "best_symbol": best_sym,
            "dominant_share": round(dominant_share, 4),
        },
        "side_breakdown": side_metrics,
    }

    return result
