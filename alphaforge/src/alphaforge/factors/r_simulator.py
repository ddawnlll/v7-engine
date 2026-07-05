"""Deterministic R-based trade simulator. DEPRECATED — USE simulation_adapter.py

⚠️ DEPRECATED: This module is deprecated and will be removed in a future version.
Use `alphaforge.factors.simulation_adapter` instead, which uses the centralized
simulation engine (`simulation/`) for proper cost models, exit logic, and path metrics.

This standalone simulator was kept for backward compatibility but should not be
used for new factor evaluations.

---

Converts factor signals into trade entries and measures R-multiple outcomes.
Each trade's result is expressed in terms of initial risk (R).

Conservative bar rule: if stop and target are both hit in the same bar,
assume stop was hit first.

Cost model: Conservative assumption
- Taker fee: 0.04% per side (0.08% round trip)
- Slippage: 0.02% per side (0.04% round trip)
- Total round-trip cost: 0.12% of notional
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


# ── COST MODEL ────────────────────────────────────────────────────

TAKER_FEE_RATE = 0.0004   # 0.04% per side
SLIPPAGE_RATE = 0.0002    # 0.02% per side
TOTAL_COST_RATE = 2 * (TAKER_FEE_RATE + SLIPPAGE_RATE)  # 0.12% round trip


@dataclass(frozen=True)
class TradeConfig:
    """Configuration for R simulation."""
    name: str
    timeframe: str  # "1h" or "4h"
    stop_mult: float  # ATR multiplier for stop
    target_mult: float  # ATR multiplier for target
    max_hold_bars: int  # maximum bars to hold position


# Pre-defined configs
CONFIGS = {
    "SCALP_1H_FAST": TradeConfig("SCALP_1H_FAST", "1h", 1.5, 2.0, 4),
    "SCALP_1H_SLOW": TradeConfig("SCALP_1H_SLOW", "1h", 1.5, 2.0, 8),
    "SWING_PROXY_1H": TradeConfig("SWING_PROXY_1H", "1h", 2.0, 3.0, 12),
}


# ── SIMPLE ATR ────────────────────────────────────────────────────

def compute_atr(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Compute ATR (Average True Range) from aligned panel data.

    True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
    ATR = rolling mean of True Range.
    """
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=0).max(level=0) if False else tr1  # simplified
    # Actually, we need element-wise max across the three
    tr = pd.DataFrame(
        np.maximum(np.maximum(tr1.values, tr2.values), tr3.values),
        index=high.index,
        columns=high.columns,
    )
    atr = tr.rolling(period, min_periods=max(1, period // 2)).mean()
    return atr


# ── TRADE RECORD ──────────────────────────────────────────────────

@dataclass
class TradeRecord:
    """Record of a single R-simulated trade."""
    symbol: str
    side: str  # "LONG" or "SHORT"
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float
    initial_risk: float
    pnl: float
    R: float
    exit_reason: str  # "TARGET", "STOP", "MAX_HOLD"
    hold_bars: int
    cost: float


# ── R SIMULATOR ───────────────────────────────────────────────────

def simulate_trades_for_factor(
    factor_scores: pd.DataFrame,
    close: pd.DataFrame,
    high: pd.DataFrame,
    low: pd.DataFrame,
    config: TradeConfig,
    direction: str,
    min_score_quantile: float = 0.80,
    max_score_quantile: float = 0.20,
) -> list[TradeRecord]:
    """Simulate R-based trades for a factor and config.

    For each timestamp:
    - Top factor scores (>= 80th percentile) → LONG entry
    - Bottom factor scores (<= 20th percentile) → SHORT entry
    - Middle scores → NO TRADE

    For "short" direction factors, flip: low scores → LONG, high scores → SHORT.

    Args:
        factor_scores: DataFrame[timestamps × symbols] of factor scores.
        close/high/low: Aligned OHLCV panels.
        config: Trade configuration.
        direction: "long", "short", or "agnostic".
        min_score_quantile: Top quantile threshold for long entries.
        max_score_quantile: Bottom quantile threshold for short entries.

    Returns:
        List of TradeRecord objects.
    """
    atr_period = 14
    atr = compute_atr(high, low, close, period=atr_period)

    trades: list[TradeRecord] = []

    # Track active positions: dict[(symbol, side)] → entry info
    active: dict[tuple[str, str], dict] = {}

    timestamps = factor_scores.index
    symbols = factor_scores.columns

    for i, ts in enumerate(timestamps):
        if i < atr_period + 1:
            continue  # wait for ATR to warm up

        scores = factor_scores.loc[ts].dropna()
        if len(scores) < 5:
            continue

        # Determine entry thresholds
        high_thresh = scores.quantile(min_score_quantile)
        low_thresh = scores.quantile(max_score_quantile)

        for sym in symbols:
            if sym not in scores.index:
                continue
            if sym not in close.columns or sym not in atr.columns:
                continue

            score = scores[sym]
            current_close = close[sym].get(ts, np.nan)
            current_atr = atr[sym].get(ts, np.nan)

            if not np.isfinite(current_close) or not np.isfinite(current_atr) or current_atr <= 0:
                continue

            key_long = (sym, "LONG")
            key_short = (sym, "SHORT")

            # Check if we need to close existing positions
            for key in [key_long, key_short]:
                if key in active:
                    pos = active[key]
                    bars_held = len(timestamps[pos["entry_idx"]:i+1]) - 1

                    # Check exit conditions using the current bar's high/low
                    bar_high = high[sym].get(ts, np.nan)
                    bar_low = low[sym].get(ts, np.nan)
                    if not np.isfinite(bar_high) or not np.isfinite(bar_low):
                        continue

                    if pos["side"] == "LONG":
                        # Check stop first (conservative: same bar = stop first)
                        if bar_low <= pos["stop"]:
                            exit_price = pos["stop"]
                            exit_reason = "STOP"
                        elif bar_high >= pos["target"]:
                            exit_price = pos["target"]
                            exit_reason = "TARGET"
                        elif bars_held >= config.max_hold_bars:
                            exit_price = current_close
                            exit_reason = "MAX_HOLD"
                        else:
                            continue
                    else:  # SHORT
                        if bar_high >= pos["stop"]:
                            exit_price = pos["stop"]
                            exit_reason = "STOP"
                        elif bar_low <= pos["target"]:
                            exit_price = pos["target"]
                            exit_reason = "TARGET"
                        elif bars_held >= config.max_hold_bars:
                            exit_price = current_close
                            exit_reason = "MAX_HOLD"
                        else:
                            continue

                    # Compute R
                    entry = pos["entry"]
                    initial_risk = pos["initial_risk"]
                    cost = entry * TOTAL_COST_RATE + exit_price * TOTAL_COST_RATE

                    if pos["side"] == "LONG":
                        pnl = (exit_price - entry) - cost
                    else:
                        pnl = (entry - exit_price) - cost

                    R = pnl / initial_risk if initial_risk > 0 else 0.0

                    trades.append(TradeRecord(
                        symbol=sym,
                        side=pos["side"],
                        entry_ts=pos["entry_ts"],
                        exit_ts=ts,
                        entry_price=entry,
                        exit_price=exit_price,
                        stop_price=pos["stop"],
                        target_price=pos["target"],
                        initial_risk=initial_risk,
                        pnl=pnl,
                        R=R,
                        exit_reason=exit_reason,
                        hold_bars=bars_held,
                        cost=cost,
                    ))
                    del active[key]

            # Open new positions (only if no active position for this symbol)
            if key_long not in active and key_short not in active:
                if direction == "short":
                    # For short factors: low score = LONG, high score = SHORT
                    if score <= low_thresh:
                        # LONG entry
                        entry = current_close
                        stop = entry - current_atr * config.stop_mult
                        target = entry + current_atr * config.target_mult
                        initial_risk = entry - stop
                        if initial_risk > 0:
                            active[key_long] = {
                                "side": "LONG", "entry": entry, "stop": stop,
                                "target": target, "initial_risk": initial_risk,
                                "entry_ts": ts, "entry_idx": i,
                            }
                    elif score >= high_thresh:
                        # SHORT entry
                        entry = current_close
                        stop = entry + current_atr * config.stop_mult
                        target = entry - current_atr * config.target_mult
                        initial_risk = stop - entry
                        if initial_risk > 0:
                            active[key_short] = {
                                "side": "SHORT", "entry": entry, "stop": stop,
                                "target": target, "initial_risk": initial_risk,
                                "entry_ts": ts, "entry_idx": i,
                            }
                elif direction == "long":
                    # For long factors: high score = LONG, low score = SHORT
                    if score >= high_thresh:
                        entry = current_close
                        stop = entry - current_atr * config.stop_mult
                        target = entry + current_atr * config.target_mult
                        initial_risk = entry - stop
                        if initial_risk > 0:
                            active[key_long] = {
                                "side": "LONG", "entry": entry, "stop": stop,
                                "target": target, "initial_risk": initial_risk,
                                "entry_ts": ts, "entry_idx": i,
                            }
                    elif score <= low_thresh:
                        entry = current_close
                        stop = entry + current_atr * config.stop_mult
                        target = entry - current_atr * config.target_mult
                        initial_risk = stop - entry
                        if initial_risk > 0:
                            active[key_short] = {
                                "side": "SHORT", "entry": entry, "stop": stop,
                                "target": target, "initial_risk": initial_risk,
                                "entry_ts": ts, "entry_idx": i,
                            }
                else:
                    # agnostic: only long top, short bottom
                    if score >= high_thresh:
                        entry = current_close
                        stop = entry - current_atr * config.stop_mult
                        target = entry + current_atr * config.target_mult
                        initial_risk = entry - stop
                        if initial_risk > 0:
                            active[key_long] = {
                                "side": "LONG", "entry": entry, "stop": stop,
                                "target": target, "initial_risk": initial_risk,
                                "entry_ts": ts, "entry_idx": i,
                            }
                    elif score <= low_thresh:
                        entry = current_close
                        stop = entry + current_atr * config.stop_mult
                        target = entry - current_atr * config.target_mult
                        initial_risk = stop - entry
                        if initial_risk > 0:
                            active[key_short] = {
                                "side": "SHORT", "entry": entry, "stop": stop,
                                "target": target, "initial_risk": initial_risk,
                                "entry_ts": ts, "entry_idx": i,
                            }

    # Close any remaining active positions at last available price
    for key, pos in active.items():
        sym = key[0]
        last_ts = timestamps[-1]
        last_close = close[sym].get(last_ts, np.nan)
        if not np.isfinite(last_close):
            continue

        entry = pos["entry"]
        initial_risk = pos["initial_risk"]
        cost = entry * TOTAL_COST_RATE + last_close * TOTAL_COST_RATE

        if pos["side"] == "LONG":
            pnl = (last_close - entry) - cost
        else:
            pnl = (entry - last_close) - cost

        R = pnl / initial_risk if initial_risk > 0 else 0.0

        trades.append(TradeRecord(
            symbol=sym,
            side=pos["side"],
            entry_ts=pos["entry_ts"],
            exit_ts=last_ts,
            entry_price=entry,
            exit_price=last_close,
            stop_price=pos["stop"],
            target_price=pos["target"],
            initial_risk=initial_risk,
            pnl=pnl,
            R=R,
            exit_reason="END_OF_DATA",
            hold_bars=0,
            cost=cost,
        ))

    return trades


def aggregate_trades(
    trades: list[TradeRecord],
    alpha_name: str,
    config_name: str,
    direction: str,
) -> dict:
    """Aggregate trade records into summary statistics for the R leaderboard.

    Returns a dict matching ALPHA_R_LEADERBOARD.csv columns.
    """
    if not trades:
        return {
            "alpha_name": alpha_name,
            "config_name": config_name,
            "side_mode": direction,
            "trades": 0,
            "avg_R": np.nan,
            "median_R": np.nan,
            "total_R": np.nan,
            "expectancy_R": np.nan,
            "profit_factor": np.nan,
            "win_rate": np.nan,
            "max_drawdown_R": np.nan,
            "fee_drag_R": np.nan,
            "avg_hold_bars": np.nan,
            "turnover": np.nan,
            "best_symbol": "",
            "worst_symbol": "",
            "dominant_symbol_share": np.nan,
            "start_ts": "",
            "end_ts": "",
            "pass_fail": "FAIL",
            "notes": "no trades",
        }

    R_values = np.array([t.R for t in trades])
    costs = np.array([t.cost for t in trades])
    hold_bars = np.array([t.hold_bars for t in trades])

    n_trades = len(trades)
    total_R = float(R_values.sum())
    avg_R = float(R_values.mean())
    median_R = float(np.median(R_values))
    expectancy_R = avg_R

    # Profit factor
    gross_profit = float(R_values[R_values > 0].sum()) if (R_values > 0).any() else 0.0
    gross_loss = float(abs(R_values[R_values < 0].sum())) if (R_values < 0).any() else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    win_rate = float((R_values > 0).sum()) / n_trades if n_trades > 0 else 0.0

    # Max drawdown in R units
    cum_R = np.cumsum(R_values)
    peak = np.maximum.accumulate(cum_R)
    drawdowns = cum_R - peak
    max_drawdown_R = float(drawdowns.min())

    # Fee drag
    fee_drag_R = float(costs.sum() / np.mean([t.initial_risk for t in trades])) if trades else 0.0

    # Per-symbol stats
    sym_R: dict[str, list[float]] = {}
    for t in trades:
        sym_R.setdefault(t.symbol, []).append(t.R)

    sym_totals = {s: sum(rs) for s, rs in sym_R.items()}
    if sym_totals:
        best_sym = max(sym_totals, key=sym_totals.get)  # type: ignore
        worst_sym = min(sym_totals, key=sym_totals.get)  # type: ignore
        # Dominant symbol share
        total_abs = sum(abs(v) for v in sym_totals.values())
        dominant_share = max(abs(v) for v in sym_totals.values()) / total_abs if total_abs > 0 else 0.0
    else:
        best_sym = ""
        worst_sym = ""
        dominant_share = 0.0

    # Pass/fail
    if total_R < 0:
        pf = "REJECT"
        notes = f"negative total R ({total_R:.2f})"
    elif expectancy_R <= 0:
        pf = "REJECT"
        notes = f"non-positive expectancy ({expectancy_R:.4f})"
    elif profit_factor < 1.0:
        pf = "REJECT"
        notes = f"PF < 1.0 ({profit_factor:.2f})"
    elif profit_factor < 1.05:
        pf = "WATCH"
        notes = f"marginal PF ({profit_factor:.2f})"
    elif dominant_share > 0.50:
        pf = "WATCH"
        notes = f"dominated by {best_sym} ({dominant_share:.0%})"
    elif n_trades < 30:
        pf = "WATCH"
        notes = f"small sample ({n_trades} trades)"
    else:
        pf = "PROMOTE_TO_MINI_V7"
        notes = f"PF={profit_factor:.2f}, E[R]={expectancy_R:.4f}"

    return {
        "alpha_name": alpha_name,
        "config_name": config_name,
        "side_mode": direction,
        "trades": n_trades,
        "avg_R": round(avg_R, 6),
        "median_R": round(median_R, 6),
        "total_R": round(total_R, 4),
        "expectancy_R": round(expectancy_R, 6),
        "profit_factor": round(profit_factor, 4),
        "win_rate": round(win_rate, 4),
        "max_drawdown_R": round(max_drawdown_R, 4),
        "fee_drag_R": round(fee_drag_R, 6),
        "avg_hold_bars": round(float(hold_bars.mean()), 2),
        "turnover": np.nan,  # computed separately if needed
        "best_symbol": best_sym,
        "worst_symbol": worst_sym,
        "dominant_symbol_share": round(dominant_share, 4),
        "start_ts": str(trades[0].entry_ts),
        "end_ts": str(trades[-1].exit_ts),
        "pass_fail": pf,
        "notes": notes,
    }
