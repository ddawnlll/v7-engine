"""Hypothesis 2: Volatility Compression.

After 72h of compressed volatility (< 50% of 30-day avg ATR), 
price breakout in either direction has momentum.
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..config import (
    VOLATILITY_COMPRESSION_THRESHOLDS, VOLATILITY_COMPRESSION_DURATIONS_H,
    VOLATILITY_COMPRESSION_ATR_PERIODS, VOLATILITY_COMPRESSION_MAX_HOLD_H, STOP_LOSS_PCT, TAKE_PROFIT_PCT,
)
from ..engine import WalkForwardEngine, run_baselines
from ..utils import compute_atr, save_csv, save_json, save_text
from ..data import download_klines

logger = logging.getLogger(__name__)


def build_param_grid() -> List[dict]:
    """Build parameter grid for Hypothesis 2 optimization."""
    grid = []
    for comp_thresh in VOLATILITY_COMPRESSION_THRESHOLDS:
        for comp_dur in VOLATILITY_COMPRESSION_DURATIONS_H:
            for atr_period in VOLATILITY_COMPRESSION_ATR_PERIODS:
                grid.append({
                    "compression_threshold": comp_thresh,
                    "compression_duration_h": comp_dur,
                    "atr_period": atr_period,
                })
    return grid


def volatility_compression_signal(
    df: pd.DataFrame,
    symbol: str,
    params: dict,
) -> List[dict]:
    """Generate volatility compression breakout signals with DIRECTION PREDICTION.

    Improvements over the original:
      - Tracks "compression slope" to predict breakout direction BEFORE it happens.
      - Enters when the breakout confirms the predicted direction, not just on any breakout.
      - Uses position-within-range (% of compression range) as directional bias.

    Theory: during compression, if price is biased toward the top of the range,
    an upside breakout is more likely (and vice versa).
    """
    comp_thresh = params["compression_threshold"]
    comp_dur_h = params["compression_duration_h"]
    atr_period = params["atr_period"]
    freq_h = _infer_freq(df)

    df = df.copy()

    # ── ATR & compression detection ──
    df["atr"] = compute_atr(df, atr_period)
    df["atr_30d_avg"] = df["atr"].rolling(30).mean()
    df["compression"] = df["atr"] < (df["atr_30d_avg"] * comp_thresh)

    comp_bars = max(1, int(comp_dur_h / freq_h) if freq_h > 0 else 1)
    df["compression_streak"] = df["compression"].astype(int).rolling(comp_bars).sum()
    df["in_compression"] = df["compression_streak"] >= comp_bars

    # ── Track compression period range ──
    df["comp_high"] = np.nan
    df["comp_low"] = np.nan
    df["comp_start_idx"] = np.nan

    in_period = False
    period_start = None
    for i in range(len(df)):
        if df["in_compression"].iloc[i] and not in_period:
            in_period = True
            period_start = i
            df.loc[df.index[i], "comp_high"] = df["high"].iloc[i]
            df.loc[df.index[i], "comp_low"] = df["low"].iloc[i]
            df.loc[df.index[i], "comp_start_idx"] = i
        elif df["in_compression"].iloc[i] and in_period:
            df.loc[df.index[i], "comp_high"] = df["high"].iloc[period_start:i+1].max()
            df.loc[df.index[i], "comp_low"] = df["low"].iloc[period_start:i+1].min()
            df.loc[df.index[i], "comp_start_idx"] = period_start
        elif not df["in_compression"].iloc[i] and in_period:
            in_period = False

    # ── Compression slope: where is price within the range? ──
    # ratio 0..1: 0 = at bottom, 1 = at top
    df["comp_position_ratio"] = np.where(
        (df["comp_high"] - df["comp_low"]) > 0,
        (df["close"] - df["comp_low"]) / (df["comp_high"] - df["comp_low"]),
        0.5,
    )

    signals = []

    for i in range(comp_bars + atr_period + 5, len(df)):
        if not df["in_compression"].iloc[i]:
            continue

        comp_high = df["comp_high"].iloc[i]
        comp_low = df["comp_low"].iloc[i]
        pos_ratio = df["comp_position_ratio"].iloc[i]

        if pd.isna(comp_high) or pd.isna(comp_low):
            continue

        # ── Directional prediction from compression bias ──
        # If price is in upper 40% of range → expect upside breakout
        # If price is in lower 40% of range → expect downside breakout
        # If in middle 20% → no directional bias, skip
        if pos_ratio > 0.6:
            predicted_dir = 1  # expect up
        elif pos_ratio < 0.4:
            predicted_dir = -1  # expect down
        else:
            continue  # no clear directional bias

        # ── Confirm with actual breakout ──
        current_high = df["high"].iloc[i]
        current_low = df["low"].iloc[i]
        prev_close = df["close"].iloc[i - 1]

        breakout_up = current_high > comp_high and current_high > prev_close
        breakout_down = current_low < comp_low and current_low < prev_close

        if predicted_dir == 1 and breakout_up:
            if not _recent_signal(signals, i, int(freq_h * 4)):
                signals.append({"entry_idx": i, "direction": 1})
        elif predicted_dir == -1 and breakout_down:
            if not _recent_signal(signals, i, int(freq_h * 4)):
                signals.append({"entry_idx": i, "direction": -1})

    return signals


def _recent_signal(signals: List[dict], current_idx: int, min_gap_bars: int) -> bool:
    """Check if a signal was emitted within the last min_gap_bars."""
    for s in signals:
        if current_idx - s["entry_idx"] < min_gap_bars:
            return True
    return False


def _infer_freq(df: pd.DataFrame) -> float:
    if len(df) < 2:
        return 1.0
    delta = (df["timestamp"].iloc[1] - df["timestamp"].iloc[0]).total_seconds() / 3600
    return max(delta, 1.0)


def prepare_data(
    symbols: List[str],
    interval: str = "1h",
) -> Dict[str, pd.DataFrame]:
    """Download and prepare data for Hypothesis 2."""
    logger.info(f"Downloading volatility data for {len(symbols)} symbols ({interval})...")

    data = {}
    for sym in symbols:
        try:
            df = download_klines(sym, interval=interval)
            if not df.empty:
                data[sym] = df
        except Exception as e:
            logger.warning(f"Failed to download {sym}: {e}")

    return data


def run_hypothesis(
    symbols: List[str],
    interval: str = "1h",
) -> Dict:
    """Run full Hypothesis 2 validation."""
    logger.info("=" * 60)
    logger.info("HYPOTHESIS 2: Volatility Compression")
    logger.info("=" * 60)

    data = prepare_data(symbols, interval)
    param_grid = build_param_grid()

    engine = WalkForwardEngine(
        hypothesis_name="volatility_compression",
        signal_fn=volatility_compression_signal,
        param_grid=param_grid,
        max_hold_hours=VOLATILITY_COMPRESSION_MAX_HOLD_H,
        stop_pct=STOP_LOSS_PCT,
        tp_pct=TAKE_PROFIT_PCT,
    )

    results = engine.run(data)

    # ── Save deliverables ──
    trades_df = pd.DataFrame(engine.all_trades)
    save_csv(trades_df, "results_volatility_compression.csv")

    save_json(results, "stats_volatility_compression.json")

    baselines = run_baselines(data, "volatility_compression")
    save_json(baselines, "baseline_comparison_volatility_compression.json")

    save_json(engine.fold_results, "fold_results_volatility_compression.json")

    decision = _make_decision(results, baselines)
    save_text(decision, "rejection_decision_volatility_compression.txt")
    logger.info(f"Decision: {decision[:100]}...")

    return results


def _make_decision(results: dict, baselines: dict) -> str:
    """Formulate rejection decision."""
    median_r = results.get("median_r_multiple", 0.0)
    total = results.get("total_signals", 0)

    # Check success rate: % of trades with R > 0 (winning)
    win_rate = results.get("win_rate", 0.0)

    if win_rate < 0.40:
        return (
            f"REJECTED: Breakout success rate (win rate) {win_rate:.1%} < 40% "
            f"({total} signals)"
        )

    # Check vs random direction after compression (placeholder)
    hyp_r = baselines.get("hypothesis_r", median_r)
    rand_r = baselines.get("random_baseline_r", 0.0)
    if hyp_r <= rand_r and median_r < 1.0:
        return (
            f"REJECTED: Hypothesis R {hyp_r:.3f} <= Random baseline R {rand_r:.3f} "
            f"and median R {median_r:.3f} < 1.0"
        )

    regime_bd = results.get("regime_breakdown", {})
    regimes_with_trades = [r for r, v in regime_bd.items() if v["count"] > 0]

    return (
        f"ACCEPTED: Win rate {win_rate:.1%}, median R-multiple {median_r:.3f}, "
        f"{len(regimes_with_trades)} regimes, {total} signals"
    )
