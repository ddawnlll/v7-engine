"""
Simulation adapter for alphaforge factor evaluation.

Bridges factor signals to the centralized simulation engine, replacing the
standalone R simulator with proper cost models, exit logic, and path metrics.

This adapter:
- Converts factor scores + OHLCV panels → SimulationInput entries
- Calls the centralized simulation engine via TrainingAdapter
- Collects SimulationOutput results
- Returns trade records compatible with the leaderboard format

Cost model: Uses centralized simulation engine's cost model (fee + slippage + funding).
Exit logic: Uses centralized engine's stop/target/time-exit with same-candle ambiguity.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

from simulation.contracts.models import (
    Candle,
    FuturePath,
    SimulationInput,
    SimulationOutput,
    SimulationProfile,
    TradingMode,
)
from simulation.adapters.training_adapter import TrainingAdapter


# ── Trade Record (compatible with leaderboard) ─────────────────────


@dataclass
class TradeRecord:
    """Record of a single R-simulated trade via centralized engine.

    Compatible with the leaderboard aggregation format.
    """
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
    exit_reason: str  # "TARGET", "STOP", "MAX_HOLD", "TIME_EXIT"
    hold_bars: int
    cost: float


# ── Profile Mapping ────────────────────────────────────────────────


def _map_config_to_profile(
    stop_mult: float,
    target_mult: float,
    max_hold_bars: int,
    timeframe: str,
) -> SimulationProfile:
    """Map standalone config parameters to a SimulationProfile.

    Creates a custom profile based on the config parameters, using the
    centralized engine's profile structure.
    """
    # Determine mode based on timeframe and parameters
    if timeframe == "4h":
        mode = TradingMode.SWING
    elif timeframe == "15m":
        mode = TradingMode.AGGRESSIVE_SCALP
    else:
        mode = TradingMode.SCALP

    return SimulationProfile(
        profile_version="custom-adapted-1.0.0",
        mode=mode,
        primary_interval=timeframe,
        max_holding_bars=max_hold_bars,
        stop_multiplier=stop_mult,
        target_multiplier=target_mult,
        ambiguity_margin_r=0.10,  # Default from SCALP
        min_action_edge_r=0.15,   # Default from SCALP
        no_trade_default=False,   # Factor evaluation should consider both directions
        stop_method="atr_wide",
        target_method="atr_wide",
        mae_penalty_weight=1.0,
        cost_penalty_weight=1.0,
        time_penalty_weight=0.3,
        funding_rate=0.0,
    )


def _compute_atr_from_panel(
    high: pd.DataFrame,
    low: pd.DataFrame,
    close: pd.DataFrame,
    period: int = 14,
) -> pd.DataFrame:
    """Compute ATR for all symbols in the panel.

    Uses lib.indicators.atr for each symbol, returns aligned panel.
    """
    from lib.indicators.atr import compute_atr as lib_compute_atr

    atr_data = {}
    for sym in close.columns:
        if sym not in high.columns or sym not in low.columns:
            continue

        h = high[sym].dropna().values
        l = low[sym].dropna().values
        c = close[sym].dropna().values

        if len(h) < period + 1:
            continue

        atr_values = lib_compute_atr(h, l, c, period)

        # Align with original index
        sym_index = close[sym].dropna().index
        atr_series = pd.Series(atr_values, index=sym_index)
        atr_data[sym] = atr_series

    if not atr_data:
        return pd.DataFrame()

    return pd.DataFrame(atr_data)


# ── Core Adapter ───────────────────────────────────────────────────


def simulate_trades_for_factor(
    factor_scores: pd.DataFrame,
    close: pd.DataFrame,
    high: pd.DataFrame,
    low: pd.DataFrame,
    config: object,  # TradeConfig from r_simulator
    direction: str,
    min_score_quantile: float = 0.80,
    max_score_quantile: float = 0.20,
    atr_panel: pd.DataFrame | None = None,
) -> list[TradeRecord]:
    """Simulate R-based trades for a factor using centralized simulation engine.

    This function replaces the standalone r_simulator.simulate_trades_for_factor()
    with calls to the centralized simulation engine.

    Args:
        factor_scores: DataFrame[timestamps × symbols] of factor scores.
        close/high/low: Aligned OHLCV panels.
        config: Trade configuration (must have .timeframe, .stop_mult, .target_mult, .max_hold_bars).
        direction: "long", "short", or "agnostic".
        min_score_quantile: Top quantile threshold for long entries.
        max_score_quantile: Bottom quantile threshold for short entries.

    Returns:
        List of TradeRecord objects.
    """
    # Compute ATR for all symbols
    atr_period = 14
    if atr_panel is not None and not atr_panel.empty:
        atr = atr_panel
    else:
        atr = _compute_atr_from_panel(high, low, close, period=atr_period)

    if atr.empty:
        return []

    # Create simulation profile from config
    profile = _map_config_to_profile(
        stop_mult=config.stop_mult,
        target_mult=config.target_mult,
        max_hold_bars=config.max_hold_bars,
        timeframe=config.timeframe,
    )

    # Initialize training adapter
    adapter = TrainingAdapter()

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

                    # Get future candles for simulation
                    future_end = min(i + profile.max_holding_bars + 1, len(timestamps))
                    future_candles = []

                    for j in range(i, future_end):
                        bar_ts = timestamps[j]
                        bar_high = high[sym].get(bar_ts, np.nan)
                        bar_low = low[sym].get(bar_ts, np.nan)
                        bar_close = close[sym].get(bar_ts, np.nan)

                        if np.isfinite(bar_high) and np.isfinite(bar_low) and np.isfinite(bar_close):
                            future_candles.append(Candle(
                                open=bar_close,  # Use close as open for simulation
                                high=bar_high,
                                low=bar_low,
                                close=bar_close,
                            ))

                    if not future_candles:
                        continue

                    # Create SimulationInput
                    sim_input = SimulationInput(
                        symbol=sym,
                        decision_timestamp=str(ts),
                        mode=profile.mode,
                        primary_interval=profile.primary_interval,
                        entry_price=pos["entry"],
                        atr=current_atr,
                        future_path=FuturePath(
                            candles=future_candles,
                            completeness_status="COMPLETE",
                            expected_bars=profile.max_holding_bars,
                        ),
                        profile=profile,
                    )

                    # Run centralized simulation
                    sim_output = adapter.run(sim_input)

                    # Extract outcome based on side
                    if pos["side"] == "LONG":
                        outcome = sim_output.long_outcome
                    else:
                        outcome = sim_output.short_outcome

                    # Convert to TradeRecord
                    exit_ts = timestamps[min(i + outcome.hold_duration_bars, len(timestamps) - 1)]

                    # Compute cost in price terms (not R)
                    entry_risk = pos["initial_risk"]
                    cost = outcome.total_cost_r * entry_risk if entry_risk > 0 else 0.0

                    # Compute PnL
                    if pos["side"] == "LONG":
                        pnl = (outcome.exit_price - pos["entry"]) - cost
                    else:
                        pnl = (pos["entry"] - outcome.exit_price) - cost

                    R = outcome.realized_r_net

                    # Map exit reason
                    exit_reason_map = {
                        "STOP_HIT": "STOP",
                        "TARGET_HIT": "TARGET",
                        "TIME_EXIT": "MAX_HOLD",
                        "HORIZON_END": "END_OF_DATA",
                    }
                    exit_reason = exit_reason_map.get(outcome.exit_reason, outcome.exit_reason)

                    trades.append(TradeRecord(
                        symbol=sym,
                        side=pos["side"],
                        entry_ts=pos["entry_ts"],
                        exit_ts=exit_ts,
                        entry_price=pos["entry"],
                        exit_price=outcome.exit_price,
                        stop_price=pos["stop"],
                        target_price=pos["target"],
                        initial_risk=entry_risk,
                        pnl=pnl,
                        R=R,
                        exit_reason=exit_reason,
                        hold_bars=outcome.hold_duration_bars,
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

        # Create final simulation for remaining position
        # Use last candle as the exit
        final_candle = Candle(
            open=last_close,
            high=high[sym].get(last_ts, last_close),
            low=low[sym].get(last_ts, last_close),
            close=last_close,
        )

        sim_input = SimulationInput(
            symbol=sym,
            decision_timestamp=str(last_ts),
            mode=profile.mode,
            primary_interval=profile.primary_interval,
            entry_price=entry,
            atr=current_atr if np.isfinite(current_atr) else 0.01,
            future_path=FuturePath(
                candles=[final_candle],
                completeness_status="PARTIAL",
                expected_bars=1,
            ),
            profile=profile,
        )

        sim_output = adapter.run(sim_input)

        if pos["side"] == "LONG":
            outcome = sim_output.long_outcome
        else:
            outcome = sim_output.short_outcome

        cost = outcome.total_cost_r * initial_risk if initial_risk > 0 else 0.0

        if pos["side"] == "LONG":
            pnl = (last_close - entry) - cost
        else:
            pnl = (entry - last_close) - cost

        R = outcome.realized_r_net

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
            hold_bars=1,
            cost=cost,
        ))

    return trades


# ── Fast path (numba) ──────────────────────────────────────────────


def simulate_trades_fast(
    factor_scores: pd.DataFrame,
    close: pd.DataFrame,
    high: pd.DataFrame,
    low: pd.DataFrame,
    config: object,
    direction: str,
    atr_panel: pd.DataFrame | None = None,
) -> list[dict]:
    """Simulate trades using centralized simulation engine.

    Always uses simulation.engine via TrainingAdapter. The numba fast-simulator
    fallback was removed in Aşama 1 (see authority_map.md).

    Returns list of trade dicts compatible with leaderboard format.
    """
    trades = simulate_trades_for_factor(
        factor_scores=factor_scores,
        close=close, high=high, low=low,
        config=config, direction=direction,
        atr_panel=atr_panel,
    )
    return [
        {
            "symbol": t.symbol, "side": t.side,
            "entry_ts": str(t.entry_ts), "exit_ts": str(t.exit_ts),
            "entry_price": t.entry_price, "exit_price": t.exit_price,
            "stop_price": t.stop_price, "target_price": t.target_price,
            "initial_risk": t.initial_risk, "pnl": t.pnl, "R": t.R,
            "exit_reason": t.exit_reason, "hold_bars": t.hold_bars, "cost": t.cost,
        }
        for t in trades
    ]


# ── Aggregation (moved from fast_simulator.py) ─────────────────────

def aggregate_trades_fast(
    trades: list[dict[str, Any]],
    alpha_name: str,
    config_name: str,
    direction: str,
) -> dict[str, Any]:
    """Aggregate trade dicts into summary statistics for the R leaderboard.

    Operates on numpy arrays extracted from the trade dicts for speed.
    Returns a dict matching ALPHA_R_LEADERBOARD.csv columns.

    Moved from fast_simulator.py during Aşama 1 authority cleanup.
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

    # Pass/fail logic
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
