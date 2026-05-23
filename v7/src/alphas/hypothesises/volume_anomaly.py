"""Hypothesis 5: Volume Anomaly.

When volume spikes to 3× the 20-bar average while price hasn't moved,
it signals smart money accumulation. Early entry before the move.
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..config import (
    VOLUME_ANOMALY_MULTIPLES, VOLUME_ANOMALY_LOOKBACK,
    VOLUME_ANOMALY_PRICE_THRESHOLDS, VOLUME_ANOMALY_MAX_HOLD_H,
    STOP_LOSS_PCT, TAKE_PROFIT_PCT,
)
from ..engine import WalkForwardEngine, run_baselines
from ..utils import save_csv, save_json, save_text
from ..data import download_klines

logger = logging.getLogger(__name__)


def build_param_grid() -> List[dict]:
    grid = []
    for mult in VOLUME_ANOMALY_MULTIPLES:
        for lookback in VOLUME_ANOMALY_LOOKBACK:
            for px_thresh in VOLUME_ANOMALY_PRICE_THRESHOLDS:
                grid.append({
                    "volume_multiple": mult,
                    "lookback_bars": lookback,
                    "price_change_threshold": px_thresh,
                })
    return grid


def volume_anomaly_signal(
    df: pd.DataFrame,
    symbol: str,
    params: dict,
) -> List[dict]:
    """Generate volume anomaly signals.

    Conditions:
      1. Current bar volume > `volume_multiple` × rolling average of last `lookback_bars`.
      2. Price change over the last `lookback_bars` is below `price_change_threshold`.
      3. Direction is determined by comparing the current close to the
         volume-weighted average price (VWAP-like) — if price is above,
         smart money is buying → long. If below, smart money is selling → short.
    """
    vol_mult = params["volume_multiple"]
    lookback = params["lookback_bars"]
    px_thresh = params["price_change_threshold"]
    freq_h = _infer_freq(df)

    df = df.copy()

    # Rolling average volume
    df["vol_avg"] = df["volume"].rolling(lookback).mean()
    df["vol_ratio"] = df["volume"] / df["vol_avg"]

    # Price change over lookback
    df["price_change"] = df["close"].pct_change(lookback)

    # Simple VWAP over lookback for direction bias
    df["vwap"] = (
        (df["volume"] * (df["high"] + df["low"] + df["close"]) / 3)
        .rolling(lookback)
        .sum() / df["volume"].rolling(lookback).sum()
    )
    df["vwap_bias"] = df["close"] > df["vwap"]  # True = above VWAP → bullish

    signals = []

    for i in range(lookback, len(df)):
        vol_r = df["vol_ratio"].iloc[i]
        px_chg = abs(df["price_change"].iloc[i])

        if pd.isna(vol_r) or pd.isna(px_chg):
            continue

        # Volume anomaly detected
        if vol_r > vol_mult and px_chg < px_thresh:
            # Direction from VWAP bias
            if df["vwap_bias"].iloc[i]:
                direction = 1  # price above VWAP during anomaly → bullish
            else:
                direction = -1  # below VWAP → bearish

            # Avoid clustering: skip if signal already fired within 4h
            if not _recent_signal(signals, i, max(1, int(4 / freq_h))):
                signals.append({"entry_idx": i, "direction": direction})

    return signals


def _recent_signal(signals: List[dict], current_idx: int, min_gap_bars: int) -> bool:
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
    """Download klines — volume is already in klines, no extra API needed."""
    logger.info(f"Downloading volume data for {len(symbols)} symbols...")
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
    logger.info("=" * 60)
    logger.info("HYPOTHESIS 5: Volume Anomaly")
    logger.info("=" * 60)

    data = prepare_data(symbols, interval)
    param_grid = build_param_grid()

    engine = WalkForwardEngine(
        hypothesis_name="volume_anomaly",
        signal_fn=volume_anomaly_signal,
        param_grid=param_grid,
        max_hold_hours=VOLUME_ANOMALY_MAX_HOLD_H,
        stop_pct=STOP_LOSS_PCT,
        tp_pct=TAKE_PROFIT_PCT,
    )

    results = engine.run(data)

    trades_df = pd.DataFrame(engine.all_trades)
    save_csv(trades_df, "results_volume_anomaly.csv")
    save_json(results, "stats_volume_anomaly.json")
    baselines = run_baselines(data, "volume_anomaly")
    save_json(baselines, "baseline_comparison_volume_anomaly.json")
    save_json(engine.fold_results, "fold_results_volume_anomaly.json")
    decision = _make_decision(results, baselines)
    save_text(decision, "rejection_decision_volume_anomaly.txt")
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
