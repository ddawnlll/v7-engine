"""Hypothesis 4: Open Interest Spike.

When OI suddenly spikes (≥20%) while price stays flat, it signals large
position accumulation. A breakout in either direction is imminent.
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..config import (
    OPEN_INTEREST_SPIKE_THRESHOLDS, OPEN_INTEREST_SPIKE_LOOKBACK_H,
    OPEN_INTEREST_SPIKE_PRICE_THRESHOLDS, OPEN_INTEREST_SPIKE_MAX_HOLD_H,
    STOP_LOSS_PCT, TAKE_PROFIT_PCT,
)
from ..engine import WalkForwardEngine, run_baselines
from ..utils import save_csv, save_json, save_text, label_regime_for_df
from ..data import download_klines, download_open_interest

logger = logging.getLogger(__name__)


def build_param_grid() -> List[dict]:
    grid = []
    for oi_thresh in OPEN_INTEREST_SPIKE_THRESHOLDS:
        for lookback in OPEN_INTEREST_SPIKE_LOOKBACK_H:
            for price_thresh in OPEN_INTEREST_SPIKE_PRICE_THRESHOLDS:
                grid.append({
                    "oi_spike_threshold": oi_thresh,
                    "oi_lookback_h": lookback,
                    "price_change_threshold": price_thresh,
                })
    return grid


def oi_spike_signal(
    df: pd.DataFrame,
    symbol: str,
    params: dict,
    oi_data: Optional[pd.DataFrame] = None,
) -> List[dict]:
    """Generate Open Interest spike signals.

    Conditions:
      1. OI increases by `oi_spike_threshold` (e.g., 20%) over `oi_lookback_h`.
      2. Price change over the same period is below `price_change_threshold`.
      3. When both are true → position accumulation detected → enter long.

    Future direction is assumed up (OI spike = smart money accumulating longs).
    A short signal is generated if OI drops sharply with flat price (distribution).
    """
    if oi_data is None or oi_data.empty:
        return []

    oi_thresh = params["oi_spike_threshold"]
    lookback_h = params["oi_lookback_h"]
    px_thresh = params["price_change_threshold"]
    freq_h = _infer_freq(df)
    lookback_bars = max(1, int(lookback_h / freq_h) if freq_h > 0 else 1)

    # Align OI data to kline timestamps (forward-fill)
    oi_aligned = oi_data.set_index("timestamp").reindex(
        df["timestamp"], method="ffill"
    ).reset_index()

    df = df.copy()
    df["open_interest"] = oi_aligned["open_interest"].values

    # OI change over lookback window
    df["oi_change"] = df["open_interest"].pct_change(lookback_bars)
    # Price change over same window
    df["price_change"] = df["close"].pct_change(lookback_bars)

    signals = []

    for i in range(lookback_bars, len(df)):
        oi_chg = df["oi_change"].iloc[i]
        px_chg = abs(df["price_change"].iloc[i])

        if pd.isna(oi_chg) or pd.isna(px_chg):
            continue

        # OI spike up + price flat → accumulation → long
        if oi_chg > oi_thresh and px_chg < px_thresh:
            signals.append({"entry_idx": i, "direction": 1})

        # OI spike down + price flat → distribution → short
        elif oi_chg < -oi_thresh and px_chg < px_thresh:
            signals.append({"entry_idx": i, "direction": -1})

    return signals


def _infer_freq(df: pd.DataFrame) -> float:
    if len(df) < 2:
        return 1.0
    delta = (df["timestamp"].iloc[1] - df["timestamp"].iloc[0]).total_seconds() / 3600
    return max(delta, 1.0)


def prepare_data(
    symbols: List[str],
    interval: str = "1h",
) -> Dict[str, pd.DataFrame]:
    """Download klines + OI data for all symbols."""
    logger.info(f"Downloading OI data for {len(symbols)} symbols...")
    data = {}
    for sym in symbols:
        try:
            df = download_klines(sym, interval=interval)
            if df.empty:
                continue
            oi_df = download_open_interest(sym, interval=interval)
            if oi_df.empty:
                logger.warning(f"  {sym}: no OI data, skipping")
                continue
            # Merge OI into klines
            oi_ts = oi_df.set_index("timestamp")["open_interest"]
            df = df.set_index("timestamp")
            df["open_interest"] = oi_ts.reindex(df.index, method="ffill")
            df = df.reset_index()
            data[sym] = df
        except Exception as e:
            logger.warning(f"Failed to prepare {sym}: {e}")
    return data


def run_hypothesis(
    symbols: List[str],
    interval: str = "1h",
) -> Dict:
    logger.info("=" * 60)
    logger.info("HYPOTHESIS 4: Open Interest Spike")
    logger.info("=" * 60)

    data = prepare_data(symbols, interval)
    if not data:
        logger.warning("No symbols with OI data available — skipping")
        return {"status": "BLOCKED", "reason": "No OI data available"}

    param_grid = build_param_grid()

    engine = WalkForwardEngine(
        hypothesis_name="open_interest_spike",
        signal_fn=oi_spike_signal,
        param_grid=param_grid,
        max_hold_hours=OPEN_INTEREST_SPIKE_MAX_HOLD_H,
        stop_pct=STOP_LOSS_PCT,
        tp_pct=TAKE_PROFIT_PCT,
    )

    results = engine.run(data)

    trades_df = pd.DataFrame(engine.all_trades)
    save_csv(trades_df, "results_open_interest_spike.csv")
    save_json(results, "stats_open_interest_spike.json")
    baselines = run_baselines(data, "open_interest_spike")
    save_json(baselines, "baseline_comparison_open_interest_spike.json")
    save_json(engine.fold_results, "fold_results_open_interest_spike.json")
    decision = _make_decision(results, baselines)
    save_text(decision, "rejection_decision_open_interest_spike.txt")
    logger.info(f"Decision: {decision[:100]}...")
    return results


def _make_decision(results: dict, baselines: dict) -> str:
    median_r = results.get("median_r_multiple", 0.0)
    total = results.get("total_signals", 0)
    n_folds = len(results.get("fold_results", []))
    if median_r < 1.0:
        return f"REJECTED: Median R {median_r:.3f} < 1.0 ({total} signals, {n_folds} folds)"
    regime_bd = results.get("regime_breakdown", {})
    regimes = [r for r, v in regime_bd.items() if v["count"] > 0]
    if len(regimes) < 2:
        return f"REJECTED: Only {len(regimes)} regime(s) ({regimes})"
    return f"ACCEPTED: Median R {median_r:.3f}, {total} signals, {len(regimes)} regimes, {n_folds} folds"
