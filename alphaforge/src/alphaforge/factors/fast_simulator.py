"""Numba-accelerated R-based trade simulation kernel.

POSITION MANAGEMENT authority — bar-by-bar entry/exit tracking.
Cost parameters sourced from ``simulation.engine.costs`` (economic truth authority).

**Architecture (Authority Map Aşama 2):**
- ``fast_simulate_factor`` (this module) = bar-by-bar position tracking engine.
  Owns: entry timing, exit decisions (stop/target/max_hold), per-bar state.
- ``simulation/engine/costs.py`` = cost formula authority.
  Owns: fee, slippage, funding cost rates.
- ``simulation/engine/engine.py::simulate()`` = single-decision-point R computation.
  NOT used for bar-by-bar position management (it's not designed for that).

This module keeps the correct position management logic but uses authority-aligned
cost rates imported from ``simulation.engine.costs`` instead of hardcoded constants.

Perf note: numba JIT provides ~155x speedup over pure Python on the hot kernel.
Without numba, this module falls back to pure Python — functional but extremely slow.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    from numba import njit
except ImportError:
    def njit(f=None, **kwargs):
        if f is not None:
            return f
        return lambda g: g
    _NUMBA_AVAILABLE = False
else:
    _NUMBA_AVAILABLE = True

# Warn once on first import if numba is missing or disabled
if not _NUMBA_AVAILABLE:
    logger.warning(
        "numba not installed — simulation kernels will run 50-150x slower. "
        "Install it: pip install numba"
    )
elif os.environ.get("NUMBA_DISABLE_JIT", "0") == "1":
    logger.warning(
        "NUMBA_DISABLE_JIT=1 — simulation kernels will run in pure-Python mode "
        "(50-150x slower). Unset for full performance."
    )


# ---------------------------------------------------------------------------
# Cost model constant — sourced from simulation.authority (canonical)
# ---------------------------------------------------------------------------
# Authority: simulation.authority.get_cost_constants() defines:
#   taker_fee_bps = 4.0     → 4bps entry + 4bps exit = 8bps
#   slippage_bps  = 1.0     → 1bp entry + 1bp exit = 2bps
# Total round trip = 10bps = 0.0010 as fraction of notional.
# This replaces the old hardcoded 0.0012 (12bps) which did not match the engine.
from simulation.authority import get_cost_constants

_COST_AUTH = get_cost_constants()
TOTAL_COST_RATE: float = _COST_AUTH["total_round_trip_cost_bps"] / 10_000  # 0.0010 (10bps)
assert abs(TOTAL_COST_RATE - 0.0010) < 1e-10, f"TOTAL_COST_RATE={TOTAL_COST_RATE} != 0.0010"



# ---------------------------------------------------------------------------
# 1. Numba ATR kernel — Wilder EMA
# ---------------------------------------------------------------------------

@njit(cache=True)
def fast_compute_atr(
    highs: np.ndarray,   # (n_timestamps,) float64
    lows: np.ndarray,    # (n_timestamps,) float64
    closes: np.ndarray,  # (n_timestamps,) float64
    period: int,
) -> np.ndarray:
    """Compute ATR using Wilder's exponential moving average.

    True Range = max(high - low, |high - prev_close|, |low - prev_close|)
    ATR is seeded with SMA of the first ``period`` TR values, then updated via:
        ATR[i] = (ATR[i-1] * (period - 1) + TR[i]) / period

    Returns:
        Array of same length as inputs.  First ``period`` values are the
        SMA-seeded ATR; values before that are 0.0.
    """
    n = len(highs)
    atr = np.empty(n, dtype=np.float64)

    # True Range
    tr = np.empty(n, dtype=np.float64)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, max(hc, lc))

    # Seed with SMA
    for i in range(n):
        atr[i] = 0.0

    if n < period:
        return atr

    s = 0.0
    for i in range(period):
        s += tr[i]
    atr[period - 1] = s / period

    # Wilder EMA
    for i in range(period, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    return atr


# ---------------------------------------------------------------------------
# 2. Numba simulation kernel — all symbols at once
# ---------------------------------------------------------------------------

@njit(cache=True)
def fast_simulate_factor(
    scores_matrix: np.ndarray,   # (n_timestamps, n_symbols) float64 — NaN where missing
    close_matrix: np.ndarray,    # (n_timestamps, n_symbols) float64
    high_matrix: np.ndarray,     # (n_timestamps, n_symbols) float64
    low_matrix: np.ndarray,      # (n_timestamps, n_symbols) float64
    atr_matrix: np.ndarray,      # (n_timestamps, n_symbols) float64 — precomputed ATR
    config_stop_mult: float,     # ATR multiplier for stop
    config_target_mult: float,   # ATR multiplier for target
    config_max_hold: int,        # max bars to hold a position
    direction_int: int,          # 1 = long, -1 = short, 0 = agnostic
    min_quantile: float,         # e.g. 0.80 — top quantile triggers long entry
    max_quantile: float,         # e.g. 0.20 — bottom quantile triggers short entry
    warmup: int = 15,            # bars to skip before entries (was hardcoded; now aligns w/ atr_period + 1)
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray,
           np.ndarray, np.ndarray, np.ndarray, np.ndarray,
           np.ndarray, np.ndarray, np.ndarray]:
    """Bar-by-bar simulation for all symbols simultaneously.

    Tracks at most one active position per symbol.  For each bar:

    1. Close any open position that hits stop, target, or max-hold.
    2. If no position is open for a symbol, evaluate the score against
       quantile thresholds to decide whether to open a new position.

    Args:
        warmup: Number of initial bars to skip before opening positions.
            Should be at least ``atr_period + 1`` to ensure ATR is seeded.

    Returns a tuple of 1-D arrays (one element per completed trade):
        entry_idx,    exit_idx,     symbol_idx,  side,
        entry_price,  exit_price,   stop_price,  target_price,
        initial_risk, pnl,          R
    """
    n_ts, n_sym = scores_matrix.shape

    # --- pre-compute quantile thresholds per bar ---------------------------
    high_thresh = np.empty(n_ts, dtype=np.float64)
    low_thresh = np.empty(n_ts, dtype=np.float64)
    valid_count = np.empty(n_ts, dtype=np.int64)

    for t in range(n_ts):
        # Count valid (non-NaN) scores this bar
        count = 0
        for s in range(n_sym):
            v = scores_matrix[t, s]
            if v == v:  # not NaN
                count += 1
        valid_count[t] = count

        if count < 5:
            high_thresh[t] = np.nan
            low_thresh[t] = np.nan
            continue

        # Collect valid scores into a temp buffer and sort for quantile
        buf = np.empty(count, dtype=np.float64)
        idx = 0
        for s in range(n_sym):
            v = scores_matrix[t, s]
            if v == v:
                buf[idx] = v
                idx += 1

        # Simple insertion sort — fine for typical n_symbols (50-200)
        for i in range(1, count):
            key = buf[i]
            j = i - 1
            while j >= 0 and buf[j] > key:
                buf[j + 1] = buf[j]
                j -= 1
            buf[j + 1] = key

        # Quantile via linear interpolation
        def _quantile(sorted_arr: np.ndarray, q: float) -> float:
            n = len(sorted_arr)
            pos = q * (n - 1)
            lo = int(pos)
            hi = lo + 1
            if hi >= n:
                return sorted_arr[n - 1]
            frac = pos - lo
            return sorted_arr[lo] * (1.0 - frac) + sorted_arr[hi] * frac

        high_thresh[t] = _quantile(buf, min_quantile)
        low_thresh[t] = _quantile(buf, max_quantile)

    # --- per-symbol position tracking arrays --------------------------------
    #   0 = flat,  1 = long,  -1 = short
    active_side = np.zeros(n_sym, dtype=np.int64)
    active_entry_idx = np.full(n_sym, -1, dtype=np.int64)
    active_entry_price = np.zeros(n_sym, dtype=np.float64)
    active_stop = np.zeros(n_sym, dtype=np.float64)
    active_target = np.zeros(n_sym, dtype=np.float64)
    active_initial_risk = np.zeros(n_sym, dtype=np.float64)

    # --- output buffers (will be trimmed at the end) -----------------------
    max_trades = n_ts * n_sym  # upper bound
    out_entry_idx = np.empty(max_trades, dtype=np.int64)
    out_exit_idx = np.empty(max_trades, dtype=np.int64)
    out_symbol_idx = np.empty(max_trades, dtype=np.int64)
    out_side = np.empty(max_trades, dtype=np.int64)
    out_entry_price = np.empty(max_trades, dtype=np.float64)
    out_exit_price = np.empty(max_trades, dtype=np.float64)
    out_stop_price = np.empty(max_trades, dtype=np.float64)
    out_target_price = np.empty(max_trades, dtype=np.float64)
    out_initial_risk = np.empty(max_trades, dtype=np.float64)
    out_pnl = np.empty(max_trades, dtype=np.float64)
    out_R = np.empty(max_trades, dtype=np.float64)
    trade_count = 0

    # --- main bar loop -----------------------------------------------------
    for t in range(n_ts):
        for s in range(n_sym):
            # Skip symbols with no valid price data this bar
            cls = close_matrix[t, s]
            if cls != cls:  # NaN check
                continue

            # ---- Phase 1: check active position for exits -----------------
            if active_side[s] != 0:
                bar_high = high_matrix[t, s]
                bar_low = low_matrix[t, s]
                if bar_high != bar_high or bar_low != bar_low:
                    continue

                entry_p = active_entry_price[s]
                init_risk = active_initial_risk[s]
                stop_p = active_stop[s]
                target_p = active_target[s]
                bars_held = t - active_entry_idx[s]
                exited = False
                exit_p = 0.0
                exit_reason = 0  # 0=none, 1=stop, 2=target, 3=max_hold

                if active_side[s] == 1:
                    # LONG — check stop first (conservative same-bar rule)
                    if bar_low <= stop_p:
                        exit_p = stop_p
                        exit_reason = 1
                    elif bar_high >= target_p:
                        exit_p = target_p
                        exit_reason = 2
                    elif bars_held >= config_max_hold:
                        exit_p = cls
                        exit_reason = 3

                    if exit_reason != 0:
                        cost = (entry_p + exit_p) * TOTAL_COST_RATE
                        pnl = (exit_p - entry_p) - cost
                        R = pnl / init_risk if init_risk > 0.0 else 0.0
                        exited = True

                else:
                    # SHORT — check stop first (conservative same-bar rule)
                    if bar_high >= stop_p:
                        exit_p = stop_p
                        exit_reason = 1
                    elif bar_low <= target_p:
                        exit_p = target_p
                        exit_reason = 2
                    elif bars_held >= config_max_hold:
                        exit_p = cls
                        exit_reason = 3

                    if exit_reason != 0:
                        cost = (entry_p + exit_p) * TOTAL_COST_RATE
                        pnl = (entry_p - exit_p) - cost
                        R = pnl / init_risk if init_risk > 0.0 else 0.0
                        exited = True

                if exited:
                    out_entry_idx[trade_count] = active_entry_idx[s]
                    out_exit_idx[trade_count] = t
                    out_symbol_idx[trade_count] = s
                    out_side[trade_count] = active_side[s]
                    out_entry_price[trade_count] = entry_p
                    out_exit_price[trade_count] = exit_p
                    out_stop_price[trade_count] = stop_p
                    out_target_price[trade_count] = target_p
                    out_initial_risk[trade_count] = init_risk
                    out_pnl[trade_count] = pnl
                    out_R[trade_count] = R
                    trade_count += 1

                    active_side[s] = 0
                    active_entry_idx[s] = -1

                # If still in position, do NOT open a new one this bar
                if active_side[s] != 0:
                    continue

            # ---- Phase 2: open new position --------------------------------
            # Skip warmup bars
            if t < warmup:
                continue

            # Need valid ATR
            cur_atr = atr_matrix[t, s]
            if cur_atr != cur_atr or cur_atr <= 0.0:
                continue

            score = scores_matrix[t, s]
            if score != score:  # NaN
                continue

            ht = high_thresh[t]
            lt = low_thresh[t]
            if ht != ht or lt != lt:  # not enough valid scores
                continue

            opened = False
            side = 0

            if direction_int == 1:
                # long direction: high score -> long, low score -> short
                if score >= ht:
                    side = 1
                elif score <= lt:
                    side = -1
            elif direction_int == -1:
                # short direction: low score -> long, high score -> short
                if score <= lt:
                    side = 1
                elif score >= ht:
                    side = -1
            else:
                # agnostic: high score -> long, low score -> short
                if score >= ht:
                    side = 1
                elif score <= lt:
                    side = -1

            if side == 0:
                continue

            entry_p = cls

            if side == 1:
                stop_p = entry_p - cur_atr * config_stop_mult
                target_p = entry_p + cur_atr * config_target_mult
                init_risk = entry_p - stop_p
            else:
                stop_p = entry_p + cur_atr * config_stop_mult
                target_p = entry_p - cur_atr * config_target_mult
                init_risk = stop_p - entry_p

            if init_risk > 0.0:
                active_side[s] = side
                active_entry_idx[s] = t
                active_entry_price[s] = entry_p
                active_stop[s] = stop_p
                active_target[s] = target_p
                active_initial_risk[s] = init_risk
                opened = True

    # --- flush remaining open positions at last bar ------------------------
    last_bar = n_ts - 1
    for s in range(n_sym):
        if active_side[s] == 0:
            continue

        last_close = close_matrix[last_bar, s]
        if last_close != last_close:  # NaN
            continue

        entry_p = active_entry_price[s]
        init_risk = active_initial_risk[s]
        stop_p = active_stop[s]
        target_p = active_target[s]
        cost = (entry_p + last_close) * TOTAL_COST_RATE

        if active_side[s] == 1:
            pnl = (last_close - entry_p) - cost
        else:
            pnl = (entry_p - last_close) - cost

        R = pnl / init_risk if init_risk > 0.0 else 0.0

        out_entry_idx[trade_count] = active_entry_idx[s]
        out_exit_idx[trade_count] = last_bar
        out_symbol_idx[trade_count] = s
        out_side[trade_count] = active_side[s]
        out_entry_price[trade_count] = entry_p
        out_exit_price[trade_count] = last_close
        out_stop_price[trade_count] = stop_p
        out_target_price[trade_count] = target_p
        out_initial_risk[trade_count] = init_risk
        out_pnl[trade_count] = pnl
        out_R[trade_count] = R
        trade_count += 1

    # --- trim outputs to actual trade count ---------------------------------
    if trade_count == 0:
        empty = np.empty(0, dtype=np.float64)
        empty_i = np.empty(0, dtype=np.int64)
        return (empty_i, empty_i, empty_i, empty_i,
                empty, empty, empty, empty,
                empty, empty, empty)

    return (
        out_entry_idx[:trade_count],
        out_exit_idx[:trade_count],
        out_symbol_idx[:trade_count],
        out_side[:trade_count],
        out_entry_price[:trade_count],
        out_exit_price[:trade_count],
        out_stop_price[:trade_count],
        out_target_price[:trade_count],
        out_initial_risk[:trade_count],
        out_pnl[:trade_count],
        out_R[:trade_count],
    )


# ---------------------------------------------------------------------------
# 3. Python wrapper — pandas in, list[dict] out
# ---------------------------------------------------------------------------

def simulate_factor_fast(
    factor_scores: pd.DataFrame,
    close: pd.DataFrame,
    high: pd.DataFrame,
    low: pd.DataFrame,
    config_stop_mult: float,
    config_target_mult: float,
    config_max_hold: int,
    direction: str,
    min_score_quantile: float = 0.80,
    max_score_quantile: float = 0.20,
    atr_panel: pd.DataFrame | None = None,
    atr_period: int = 14,
) -> list[dict[str, Any]]:
    """Run the fast numba simulation kernel and return a list of trade dicts.

    Args:
        factor_scores: DataFrame[timestamps x symbols] of factor scores.
        close, high, low: Aligned OHLCV DataFrames.
        config_stop_mult: ATR multiplier for stop-loss.
        config_target_mult: ATR multiplier for take-profit.
        config_max_hold: Maximum bars to hold a position.
        direction: "long", "short", or "agnostic".
        min_score_quantile: Top quantile threshold (default 0.80).
        max_score_quantile: Bottom quantile threshold (default 0.20).
        atr_panel: Pre-computed ATR DataFrame (optional, computed if None).
        atr_period: ATR lookback period (default 14).

    Returns:
        List of dicts, one per trade, with keys matching TradeRecord fields.
    """
    # Align to common index
    common_idx = factor_scores.index.intersection(close.index)
    common_idx = common_idx.intersection(high.index).intersection(low.index)
    common_idx = common_idx.sort_values()

    common_cols = factor_scores.columns.intersection(close.columns)
    common_cols = common_cols.intersection(high.columns).intersection(low.columns)
    common_cols = common_cols.sort_values()

    if len(common_idx) == 0 or len(common_cols) == 0:
        return []

    # Convert to numpy
    scores_np = factor_scores.loc[common_idx, common_cols].to_numpy(dtype=np.float64)
    close_np = close.loc[common_idx, common_cols].to_numpy(dtype=np.float64)
    high_np = high.loc[common_idx, common_cols].to_numpy(dtype=np.float64)
    low_np = low.loc[common_idx, common_cols].to_numpy(dtype=np.float64)

    # Compute or align ATR
    if atr_panel is not None and not atr_panel.empty:
        atr_aligned = atr_panel.reindex(index=common_idx, columns=common_cols)
        atr_np = atr_aligned.to_numpy(dtype=np.float64)
    else:
        atr_np = np.full_like(close_np, np.nan, dtype=np.float64)
        for col_idx, col_name in enumerate(common_cols):
            h = high[col_name].reindex(common_idx).to_numpy(dtype=np.float64)
            l = low[col_name].reindex(common_idx).to_numpy(dtype=np.float64)
            c = close[col_name].reindex(common_idx).to_numpy(dtype=np.float64)
            # Drop leading NaNs
            valid = ~(np.isnan(h) | np.isnan(l) | np.isnan(c))
            if valid.sum() < atr_period + 1:
                continue
            first_valid = int(np.argmax(valid))
            h_clean = h[first_valid:]
            l_clean = l[first_valid:]
            c_clean = c[first_valid:]
            atr_vals = fast_compute_atr(h_clean, l_clean, c_clean, atr_period)
            atr_col = np.full(len(common_idx), np.nan, dtype=np.float64)
            atr_col[first_valid:] = atr_vals
            atr_np[:, col_idx] = atr_col

    # Direction int mapping
    direction_map = {"long": 1, "short": -1, "agnostic": 0}
    direction_int = direction_map.get(direction.lower(), 0)

    # Run the kernel
    (entry_idx, exit_idx, symbol_idx, side,
     entry_price, exit_price, stop_price, target_price,
     initial_risk, pnl, R) = fast_simulate_factor(
        scores_np, close_np, high_np, low_np, atr_np,
        config_stop_mult, config_target_mult, config_max_hold,
        direction_int, min_score_quantile, max_score_quantile,
        warmup=atr_period + 1,
    )

    if len(entry_idx) == 0:
        return []

    # Convert back to list of dicts
    symbols_list = list(common_cols)
    timestamps = common_idx
    direction_label = direction.lower()

    trades: list[dict[str, Any]] = []
    for i in range(len(entry_idx)):
        ei = int(entry_idx[i])
        xi = int(exit_idx[i])
        si = int(symbol_idx[i])

        side_int = int(side[i])
        side_str = "LONG" if side_int == 1 else "SHORT"

        # Determine exit reason
        entry_p = float(entry_price[i])
        exit_p = float(exit_price[i])
        stop_p = float(stop_price[i])
        target_p = float(target_price[i])
        init_risk = float(initial_risk[i])
        hold_bars = xi - ei

        if side_int == 1:
            if exit_p == stop_p:
                exit_reason = "STOP"
            elif exit_p == target_p:
                exit_reason = "TARGET"
            else:
                exit_reason = "MAX_HOLD" if hold_bars >= config_max_hold else "END_OF_DATA"
        else:
            if exit_p == stop_p:
                exit_reason = "STOP"
            elif exit_p == target_p:
                exit_reason = "TARGET"
            else:
                exit_reason = "MAX_HOLD" if hold_bars >= config_max_hold else "END_OF_DATA"

        cost = (entry_p + exit_p) * TOTAL_COST_RATE

        trades.append({
            "symbol": symbols_list[si],
            "side": side_str,
            "entry_ts": timestamps[ei],
            "exit_ts": timestamps[xi],
            "entry_price": entry_p,
            "exit_price": exit_p,
            "stop_price": stop_p,
            "target_price": target_p,
            "initial_risk": init_risk,
            "pnl": float(pnl[i]),
            "R": float(R[i]),
            "exit_reason": exit_reason,
            "hold_bars": hold_bars,
            "cost": cost,
            "direction_mode": direction_label,
        })

    return trades


# ---------------------------------------------------------------------------
# 4. Vectorized aggregation over numpy arrays
# ---------------------------------------------------------------------------

def aggregate_trades_fast(
    trades: list[dict[str, Any]],
    alpha_name: str,
    config_name: str,
    direction: str,
) -> dict[str, Any]:
    """Aggregate trade dicts into summary statistics for the R leaderboard.

    Operates on numpy arrays extracted from the trade dicts for speed.
    Returns a dict matching ALPHA_R_LEADERBOARD.csv columns.
    """
    n_trades = len(trades)

    if n_trades == 0:
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

    # Extract arrays in one pass
    R_arr = np.empty(n_trades, dtype=np.float64)
    cost_arr = np.empty(n_trades, dtype=np.float64)
    hold_arr = np.empty(n_trades, dtype=np.float64)
    initial_risk_arr = np.empty(n_trades, dtype=np.float64)
    symbols = [t["symbol"] for t in trades]

    for i, t in enumerate(trades):
        R_arr[i] = t["R"]
        cost_arr[i] = t["cost"]
        hold_arr[i] = t["hold_bars"]
        initial_risk_arr[i] = t["initial_risk"]

    total_R = float(R_arr.sum())
    avg_R = float(R_arr.mean())
    median_R = float(np.median(R_arr))
    expectancy_R = avg_R

    # Profit factor
    gross_profit = float(R_arr[R_arr > 0].sum()) if (R_arr > 0).any() else 0.0
    gross_loss = float(np.abs(R_arr[R_arr < 0]).sum()) if (R_arr < 0).any() else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    win_rate = float((R_arr > 0).sum()) / n_trades

    # Max drawdown in R
    cum_R = np.cumsum(R_arr)
    peak = np.maximum.accumulate(cum_R)
    drawdowns = cum_R - peak
    max_drawdown_R = float(drawdowns.min())

    # Fee drag
    mean_risk = float(initial_risk_arr.mean()) if initial_risk_arr.mean() > 0 else 1.0
    fee_drag_R = float(cost_arr.sum() / mean_risk)

    # Per-symbol aggregation (vectorized via numpy unique)
    sym_arr = np.array(symbols)
    unique_syms, sym_inverse = np.unique(sym_arr, return_inverse=True)
    n_unique = len(unique_syms)

    sym_R_totals = np.zeros(n_unique, dtype=np.float64)
    for i in range(n_trades):
        sym_R_totals[sym_inverse[i]] += R_arr[i]

    best_idx = int(np.argmax(sym_R_totals))
    worst_idx = int(np.argmin(sym_R_totals))
    best_sym = str(unique_syms[best_idx])
    worst_sym = str(unique_syms[worst_idx])

    total_abs = float(np.abs(sym_R_totals).sum())
    dominant_share = float(np.abs(sym_R_totals[best_idx]) / total_abs) if total_abs > 0 else 0.0

    # Pass/fail logic (from r_simulator.py)
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
        "avg_hold_bars": round(float(hold_arr.mean()), 2),
        "turnover": np.nan,
        "best_symbol": best_sym,
        "worst_symbol": worst_sym,
        "dominant_symbol_share": round(dominant_share, 4),
        "start_ts": str(trades[0]["entry_ts"]),
        "end_ts": str(trades[-1]["exit_ts"]),
        "pass_fail": pf,
        "notes": notes,
    }
