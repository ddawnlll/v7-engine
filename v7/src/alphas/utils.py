"""Shared utilities for alpha thesis validation."""

import json
import os
import logging
from typing import List, Tuple

import numpy as np
import pandas as pd

from .config import (
    RESULTS_DIR, CACHE_DIR, TREND_MA_PERIOD, TREND_THRESHOLD,
    MAKER_FEE, TAKER_FEE, SLIPPAGE_TIER1, SLIPPAGE_TIER2, SLIPPAGE_TIER3,
    TIER1_CUTOFF, TIER2_CUTOFF,
)
from .data import cache_get, cache_set

logger = logging.getLogger(__name__)


# ── Regime Detection ─────────────────────────────────────────────────────────

def detect_regime(price_series: pd.Series) -> str:
    """Classify current market regime based on price vs SMA.

    Returns one of: 'TRENDING', 'RANGE', 'TRANSITION'
    """
    if len(price_series) < TREND_MA_PERIOD:
        return "RANGE"
    sma = price_series.rolling(TREND_MA_PERIOD).mean().iloc[-1]
    latest = price_series.iloc[-1]
    deviation = (latest - sma) / sma

    if abs(deviation) > TREND_THRESHOLD:
        return "TRENDING"
    else:
        # Check if recently crossed the MA (transition)
        recent = price_series.iloc[-TREND_MA_PERIOD:]
        cross_count = 0
        for i in range(1, len(recent)):
            prev = recent.iloc[i - 1]
            curr = recent.iloc[i]
            sma_i = price_series.iloc[: len(price_series) - TREND_MA_PERIOD + i].mean()
            if (prev - sma_i) * (curr - sma_i) < 0:
                cross_count += 1
        return "TRANSITION" if cross_count >= 2 else "RANGE"


def label_regime_for_df(df: pd.DataFrame, price_col: str = "close") -> pd.DataFrame:
    """Add a 'regime' column to a DataFrame."""
    df = df.copy()
    df["regime"] = "RANGE"
    if len(df) >= TREND_MA_PERIOD:
        df["sma50"] = df[price_col].rolling(TREND_MA_PERIOD).mean()
        df["deviation"] = (df[price_col] - df["sma50"]) / df["sma50"]
        df.loc[df["deviation"].abs() > TREND_THRESHOLD, "regime"] = "TRENDING"
        # Mark transitions (crosses in last 50 bars)
        # Simplified: if deviation changes sign recently
        df["cross"] = df["deviation"] * df["deviation"].shift(1) < 0
        # Rolling count of crosses
        df["cross_count"] = df["cross"].rolling(TREND_MA_PERIOD).sum()
        df.loc[(df["regime"] == "RANGE") & (df["cross_count"] >= 2), "regime"] = "TRANSITION"
    return df


# ── ATR Calculation ──────────────────────────────────────────────────────────

def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute Average True Range."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return atr


# ── Transaction Costs ────────────────────────────────────────────────────────

def get_slippage(volume_rank: int) -> float:
    """Get slippage fraction based on liquidity tier."""
    if volume_rank <= TIER1_CUTOFF:
        return SLIPPAGE_TIER1
    elif volume_rank <= TIER2_CUTOFF:
        return SLIPPAGE_TIER2
    else:
        return SLIPPAGE_TIER3


def compute_entry_cost(entry_price: float, volume_rank: int = 1, is_taker: bool = True) -> float:
    """Compute total entry cost (fee + slippage) as a fraction."""
    fee = TAKER_FEE if is_taker else MAKER_FEE
    slip = get_slippage(volume_rank)
    return fee + slip


def compute_exit_cost(exit_price: float, volume_rank: int = 1, is_taker: bool = True) -> float:
    """Compute total exit cost as a fraction."""
    fee = TAKER_FEE if is_taker else MAKER_FEE
    slip = get_slippage(volume_rank)
    return fee + slip


# ── Walk-Forward Fold Generator ──────────────────────────────────────────────

def generate_folds(
    start_date: str = "2021-01-01",
    end_date: str = "2024-12-31",
    n_folds: int = 12,
    train_months: int = 6,
    oos_start: str = "2022-01-01",
) -> List[dict]:
    """Generate walk-forward fold definitions.

    Each fold has:
      - fold_id: int
      - train_start, train_end: str
      - test_start, test_end: str
    """
    all_dates = pd.date_range(start=start_date, end=end_date, freq="MS")
    folds = []

    # OOS period starts at oos_start
    oos_start_dt = pd.Timestamp(oos_start)
    train_duration = pd.DateOffset(months=train_months)

    for i in range(n_folds):
        test_start = oos_start_dt + pd.DateOffset(months=i)
        test_end = test_start + pd.DateOffset(months=1)
        if test_end > pd.Timestamp(end_date):
            break
        train_end = test_start
        train_start = train_end - train_duration

        folds.append({
            "fold_id": i + 1,
            "train_start": train_start.strftime("%Y-%m-%d"),
            "train_end": train_end.strftime("%Y-%m-%d"),
            "test_start": test_start.strftime("%Y-%m-%d"),
            "test_end": test_end.strftime("%Y-%m-%d"),
        })

    return folds


# ── R-Multiple Calculation ───────────────────────────────────────────────────

def compute_r_multiple(
    entry_price: float,
    exit_price: float,
    direction: int,  # 1 for long, -1 for short
    stop_pct: float = 0.02,
    take_profit_pct: float = 0.04,
) -> float:
    """Compute R-multiple for a trade.

    R is defined as the stop loss distance (2% by default).
    1R = stop distance. If TP is 2R = 4%, hitting TP gives +2R.
    """
    if direction == 1:  # long
        ret = (exit_price - entry_price) / entry_price
    else:  # short
        ret = (entry_price - exit_price) / entry_price

    r = ret / stop_pct
    return r


# ── Bootstrap resampling ─────────────────────────────────────────────────────

def bootstrap_r_multiples(
    r_multiples: List[float],
    n_samples: int = 100,
    random_seed: int = 42,
) -> List[float]:
    """Draw bootstrap resamples of median R-multiple."""
    rng = np.random.default_rng(random_seed)
    if len(r_multiples) == 0:
        return [0.0] * n_samples
    boot_medians = []
    for _ in range(n_samples):
        sample = rng.choice(r_multiples, size=len(r_multiples), replace=True)
        boot_medians.append(float(np.median(sample)))
    return boot_medians


# ── Output Helpers ───────────────────────────────────────────────────────────

def ensure_results_dir():
    os.makedirs(RESULTS_DIR, exist_ok=True)


def ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def save_csv(df: pd.DataFrame, name: str):
    ensure_results_dir()
    path = os.path.join(RESULTS_DIR, name)
    df.to_csv(path, index=False)
    logger.info(f"Saved {path}")


def save_json(data, name: str):
    ensure_results_dir()
    path = os.path.join(RESULTS_DIR, name)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info(f"Saved {path}")


def save_text(text: str, name: str):
    ensure_results_dir()
    path = os.path.join(RESULTS_DIR, name)
    with open(path, "w") as f:
        f.write(text)
    logger.info(f"Saved {path}")


# ── Hypothesis Results Cache ─────────────────────────────────────────────────

def load_hypothesis_results(hypothesis_name: str) -> dict | None:
    """Load pre-computed hypothesis results from pickle cache."""
    return cache_get("hypothesis_results", hypothesis_name)


def save_hypothesis_results(hypothesis_name: str, results: dict):
    """Cache hypothesis results so they can be reused without re-running."""
    cache_set("hypothesis_results", hypothesis_name, results)
    logger.info(f"📦 Cached results for {hypothesis_name}")
