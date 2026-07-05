"""
AlphaForge Full Training Pipeline.

Usage:
    PYTHONPATH=alphaforge/src python3 -m alphaforge.train --mode SWING --features all

Loads real OHLCV data (falls back to synthetic), generates triple-barrier labels,
computes all feature groups, runs walk-forward validation, trains a final model,
and reports accuracy / Sharpe / overfit gap / feature count.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
try:
    from numba import njit
except ImportError:
    njit = lambda x: x

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
)
logger = logging.getLogger("alphaforge.train")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

MODE_CONFIG = {
    "SWING": {
        "primary": "4h", "max_hold": 30, "stop_mult": 2.0, "target_mult": 3.0,
        "ambiguity_margin_r": 0.15, "min_edge_r": 0.25,
    },
    "SCALP": {
        "primary": "1h", "max_hold": 12, "stop_mult": 1.5, "target_mult": 2.0,
        "ambiguity_margin_r": 0.10, "min_edge_r": 0.15,
    },
    "AGGRESSIVE_SCALP": {
        "primary": "15m", "max_hold": 5, "stop_mult": 1.5, "target_mult": 2.0,
        "ambiguity_margin_r": 0.05, "min_edge_r": 0.10,
    },
}

# Confidence threshold for trade filtering: if max softprob < this, force NO_TRADE
CONFIDENCE_THRESHOLD = 0.55


# ---------------------------------------------------------------------------
# Synthetic data generator (fallback when no real data)
# ---------------------------------------------------------------------------

def generate_synthetic_ohlcv(
    n_bars: int = 2000,
    symbols: Tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"),
    random_seed: int = 42,
) -> dict:
    """Generate synthetic multi-symbol OHLCV data."""
    rng = np.random.RandomState(random_seed)
    all_data = {
        "open": [], "high": [], "low": [], "close": [], "volume": [], "timestamp": [], "symbol": [],
    }
    for sym in symbols:
        returns = rng.randn(n_bars) * 0.02
        close = 100.0 * np.exp(np.cumsum(returns))
        close = np.maximum(close, 0.01)
        noise = rng.randn(n_bars) * 0.005
        open_arr = close * (1.0 + noise * 0.3)
        high_noise = rng.uniform(0.0, 0.015, n_bars)
        low_noise = rng.uniform(0.0, 0.015, n_bars)
        high = np.maximum(open_arr, close) * (1.0 + high_noise)
        low = np.minimum(open_arr, close) * (1.0 - low_noise)
        low = np.minimum(low, np.minimum(open_arr, close))
        high = np.maximum(high, np.maximum(open_arr, close))
        volume = rng.lognormal(mean=10.0, sigma=1.0, size=n_bars)
        all_data["open"].append(open_arr)
        all_data["high"].append(high)
        all_data["low"].append(low)
        all_data["close"].append(close)
        all_data["volume"].append(volume)
        all_data["timestamp"].extend(np.arange(n_bars, dtype=np.int64))
        all_data["symbol"].extend([sym] * n_bars)
    return {
        "open": np.concatenate(all_data["open"]),
        "high": np.concatenate(all_data["high"]),
        "low": np.concatenate(all_data["low"]),
        "close": np.concatenate(all_data["close"]),
        "volume": np.concatenate(all_data["volume"]),
        "timestamp": np.array(all_data["timestamp"], dtype=np.int64),
        "symbol": all_data["symbol"],
    }


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_panel_data(cache_dir: str, symbols: list[str]) -> dict | None:
    """Load OHLCV data from factor_sprint panel cache, aligned to common date range."""
    import pandas as pd
    cache = Path(cache_dir)
    close_path = sorted(cache.glob("panel_*_close.parquet"))
    if not close_path:
        logger.error("No panel cache found in %s", cache_dir)
        return None
    prefix = close_path[0].stem.rsplit("_", 1)[0]
    symbol_set = set(s.upper() for s in symbols)
    # Load close to find common range
    close_df = pd.read_parquet(cache / f"{prefix}_close.parquet")
    avail = [c for c in close_df.columns if c.upper() in symbol_set]
    if not avail:
        logger.error("No requested symbols found in panel cache")
        return None
    # Find common non-NaN range across all selected symbols
    valid_idx = close_df[avail].notna().all(axis=1)
    if not valid_idx.any():
        logger.error("No overlapping date range for requested symbols")
        return None
    # Find first/last contiguous valid block
    valid_starts = valid_idx[valid_idx].index
    first_valid = valid_starts[0]
    last_valid = valid_starts[-1]
    logger.info("  Panel date range: %s to %s (%d rows)", first_valid, last_valid, len(close_df.loc[first_valid:last_valid]))
    # Slice all OHLCV to common range and ffill any remaining gaps
    dfs = {}
    for key in ["close", "high", "low", "open", "volume"]:
        df = pd.read_parquet(cache / f"{prefix}_{key}.parquet")
        df = df.loc[first_valid:last_valid, avail].ffill().bfill()
        dfs[key] = df
    closes, highs, lows, opens, volumes, timestamps_out, symbols_out = [], [], [], [], [], [], []
    for col in avail:
        n = len(dfs["close"])
        closes.append(dfs["close"][col].values.astype(np.float64))
        highs.append(dfs["high"][col].values.astype(np.float64))
        lows.append(dfs["low"][col].values.astype(np.float64))
        opens.append(dfs["open"][col].values.astype(np.float64))
        volumes.append(dfs["volume"][col].values.astype(np.float64))
        timestamps_out.extend(dfs["close"].index.to_numpy())
        symbols_out.extend([col] * n)
    return {
        "close": np.concatenate(closes),
        "high": np.concatenate(highs),
        "low": np.concatenate(lows),
        "open": np.concatenate(opens),
        "volume": np.concatenate(volumes),
        "timestamp": np.array(timestamps_out),
        "symbol": symbols_out,
    }


def load_cached_data(
    symbols: List[str],
    interval: str,
    data_dir: Optional[str] = None,
) -> Optional[dict]:
    """Load real OHLCV data from parquet cache.

    Returns None if no data found (caller falls back to synthetic).
    """
    if data_dir is None:
        data_dir = str(REPO_ROOT / "data")
    raw_dir = Path(data_dir) / "raw"
    closes, highs, lows, opens, volumes, timestamps, sym_list = [], [], [], [], [], [], []

    import pyarrow.parquet as pq

    found_any = False
    for sym in symbols:
        sym_dir = raw_dir / sym
        if not sym_dir.exists():
            logger.info("  No data dir for %s at %s", sym, sym_dir)
            continue
        parquet_files = sorted(sym_dir.glob(f"*_{interval}_*.parquet"))
        # Fallback to any parquet file
        if not parquet_files:
            parquet_files = sorted(sym_dir.glob("*.parquet"))
        for pf in parquet_files:
            try:
                table = pq.read_table(str(pf))
                n = len(table)
                close_col = table.column('close').to_numpy()
                high_col = table.column('high').to_numpy()
                low_col = table.column('low').to_numpy()
                open_col = table.column('open').to_numpy()
                vol_col = table.column('volume') if 'volume' in table.column_names else None
                ts_col = table.column('timestamp') if 'timestamp' in table.column_names else None
                closes.extend(close_col)
                highs.extend(high_col)
                lows.extend(low_col)
                opens.extend(open_col)
                volumes.extend(np.zeros(n) if vol_col is None else vol_col.to_numpy())
                timestamps.extend(np.zeros(n, dtype=np.int64) if ts_col is None else ts_col.to_numpy())
                sym_list.extend([sym] * n)
                found_any = True
                logger.info("  Loaded %d bars from %s/%s", n, sym, pf.name)
            except Exception as e:
                logger.warning("  Error reading %s: %s", pf, e)

    if not found_any:
        return None

    return {
        "close": np.array(closes, dtype=np.float64),
        "high": np.array(highs, dtype=np.float64),
        "low": np.array(lows, dtype=np.float64),
        "open": np.array(opens, dtype=np.float64),
        "volume": np.array(volumes, dtype=np.float64),
        "timestamp": np.array(timestamps),
        "symbol": sym_list,
    }


# ---------------------------------------------------------------------------
# Label generation (triple-barrier)
# ---------------------------------------------------------------------------


@njit
def _generate_labels_numba(close, high, low, max_hold, stop_mult, target_mult, n,
                            min_edge_r=0.15, ambiguity_margin_r=0.10):
    """Numba-accelerated triple-barrier label generation.

    Uses min_edge_r to filter out economically insignificant edges.
    Uses ambiguity_margin_r to force NO_TRADE when LONG vs SHORT is within margin.
    """
    ints_list = np.empty(n - max_hold - 1, dtype=np.int32)
    long_gross_vals = np.empty(n - max_hold - 1, dtype=np.float64)
    short_gross_vals = np.empty(n - max_hold - 1, dtype=np.float64)
    long_net_vals = np.empty(n - max_hold - 1, dtype=np.float64)
    short_net_vals = np.empty(n - max_hold - 1, dtype=np.float64)
    gross_r_vals = np.empty(n - max_hold - 1, dtype=np.float64)
    net_r_vals = np.empty(n - max_hold - 1, dtype=np.float64)

    fee_pct = 0.04
    round_trip_cost_r = fee_pct * 2 / 100.0

    for i in range(n - max_hold - 1):
        entry_price = close[i]
        atr_sum = 0.0
        atr_count = 0
        start = max(0, i - 14)
        for k in range(start + 1, i + 1):
            atr_sum += abs(close[k] - close[k - 1])
            atr_count += 1
        atr = atr_sum / max(atr_count, 1)

        if atr <= 0 or atr > entry_price * 0.5:
            ints_list[i] = 2
            long_gross_vals[i] = 0.0
            short_gross_vals[i] = 0.0
            long_net_vals[i] = 0.0
            short_net_vals[i] = 0.0
            gross_r_vals[i] = 0.0
            net_r_vals[i] = 0.0
            continue

        stop_dist = atr * stop_mult
        target_dist = atr * target_mult

        # LONG simulation
        long_gross = 0.0
        for j in range(1, min(max_hold + 1, n - i)):
            future_high = high[i + j]
            future_low = low[i + j]
            future_close = close[i + j]
            if future_low <= entry_price - stop_dist:
                long_gross = -stop_dist / entry_price
                break
            if future_high >= entry_price + target_dist:
                long_gross = target_dist / entry_price
                break
            long_gross = (future_close - entry_price) / entry_price

        # SHORT simulation
        short_gross = 0.0
        for j in range(1, min(max_hold + 1, n - i)):
            future_high = high[i + j]
            future_low = low[i + j]
            future_close = close[i + j]
            if future_high >= entry_price + stop_dist:
                short_gross = -stop_dist / entry_price
                break
            if future_low <= entry_price - target_dist:
                short_gross = target_dist / entry_price
                break
            short_gross = (entry_price - future_close) / entry_price

        net_long = long_gross - round_trip_cost_r
        net_short = short_gross - round_trip_cost_r
        long_gross_vals[i] = long_gross
        short_gross_vals[i] = short_gross
        long_net_vals[i] = net_long
        short_net_vals[i] = net_short

        # Convert to R-multiple: net_return / risk_amount
        risk_r = stop_dist / entry_price  # fraction of entry price at risk
        if risk_r > 1e-12:
            long_r_mult = net_long / risk_r
            short_r_mult = net_short / risk_r
        else:
            long_r_mult = 0.0
            short_r_mult = 0.0

        # Ambiguity check: if both sides are within margin, it's NO_TRADE
        if abs(long_r_mult - short_r_mult) <= ambiguity_margin_r:
            ints_list[i] = 2
            long_gross_vals[i] = long_gross
            short_gross_vals[i] = short_gross
            long_net_vals[i] = net_long
            short_net_vals[i] = net_short
            gross_r_vals[i] = 0.0
            net_r_vals[i] = 0.0
        elif long_r_mult > short_r_mult and long_r_mult > min_edge_r:
            ints_list[i] = 0
            gross_r_vals[i] = long_gross
            net_r_vals[i] = net_long
        elif short_r_mult > long_r_mult and short_r_mult > min_edge_r:
            ints_list[i] = 1
            gross_r_vals[i] = short_gross
            net_r_vals[i] = net_short
        else:
            ints_list[i] = 2
            gross_r_vals[i] = 0.0
            net_r_vals[i] = 0.0

    return ints_list, gross_r_vals, net_r_vals, long_gross_vals, short_gross_vals, long_net_vals, short_net_vals


def generate_labels(ohlcv: dict, mode: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Generate triple-barrier labels with stop/target simulation.

    Returns (int_labels, gross_r_values, net_r_values, metrics_dict).
    Label DECISION uses net_R (cost-aware); gross_R is exported for analysis
    and net_R is exported for downstream economic metrics.
    """
    cfg = MODE_CONFIG[mode]
    max_hold = cfg["max_hold"]
    stop_mult = cfg["stop_mult"]
    target_mult = cfg["target_mult"]
    min_edge_r = cfg.get("min_edge_r", 0.15)
    ambiguity_margin_r = cfg.get("ambiguity_margin_r", 0.10)

    # Split by symbol to prevent cross-symbol contamination
    close_arr = ohlcv["close"].astype(np.float64)
    high_arr = ohlcv["high"].astype(np.float64)
    low_arr = ohlcv["low"].astype(np.float64)
    symbols = np.array(ohlcv.get("symbol", ["" for _ in range(len(close_arr))]))
    unique_syms = np.unique(symbols)

    all_ints, all_gross, all_net = [], [], []
    for sym in unique_syms:
        mask = symbols == sym
        sym_close = close_arr[mask]
        sym_high = high_arr[mask]
        sym_low = low_arr[mask]
        n_sym = len(sym_close)
        if n_sym <= max_hold + 1:
            continue
        ints_s, gross_s, net_s, _, _, _, _ = _generate_labels_numba(
            sym_close, sym_high, sym_low,
            max_hold, stop_mult, target_mult, n_sym,
            min_edge_r, ambiguity_margin_r,
        )
        all_ints.append(ints_s)
        all_gross.append(gross_s)
        all_net.append(net_s)

    ints_arr = np.concatenate(all_ints) if all_ints else np.array([], dtype=np.int32)
    gross_r_arr = np.concatenate(all_gross) if all_gross else np.array([], dtype=np.float64)
    net_r_arr = np.concatenate(all_net) if all_net else np.array([], dtype=np.float64)

    rev_label_map = {0: "LONG_NOW", 1: "SHORT_NOW", 2: "NO_TRADE"}
    labels_list = [rev_label_map[i] for i in ints_arr.tolist()]

    uniq, cnt = np.unique(labels_list, return_counts=True)
    d = {str(k): int(v) for k, v in zip(uniq, cnt)}
    logger.info("Labels: %d samples, dist=%s", len(labels_list), d)
    return ints_arr, net_r_arr, {
        "n_labels": len(labels_list),
        "label_distribution": d,
    }


# ---------------------------------------------------------------------------
# Feature computation
# ---------------------------------------------------------------------------

def compute_all_features(ohlcv: dict, mode: str) -> Tuple[np.ndarray, List[str]]:
    """Compute all feature groups per-symbol to avoid cross-symbol contamination."""
    return compute_features_selected(ohlcv, mode)


def compute_features_selected(ohlcv: dict, mode: str, feature_groups: Optional[List[str]] = None) -> Tuple[np.ndarray, List[str]]:
    """Compute selected feature groups, per-symbol to avoid cross-symbol contamination."""
    from alphaforge.features.pipeline import compute_features

    symbols = np.array(ohlcv.get("symbol", ["" for _ in range(len(ohlcv["close"]))]))
    unique_syms = []
    seen = set()
    for s in symbols:
        if s not in seen:
            seen.add(s)
            unique_syms.append(s)

    all_X, feat_names = [], None
    for sym in unique_syms:
        mask = symbols == sym
        sym_ohlcv = {
            "close": ohlcv["close"][mask],
            "high": ohlcv["high"][mask],
            "low": ohlcv["low"][mask],
            "open": ohlcv["open"][mask],
            "volume": ohlcv["volume"][mask],
        }
        if feature_groups is None or feature_groups == ["all"]:
            fm = compute_features(sym_ohlcv, mode=mode)
        else:
            fm = compute_features(sym_ohlcv, mode=mode, feature_groups=feature_groups)
        fn = sorted(fm.features.keys())
        if feat_names is None:
            feat_names = fn
        Xs = np.column_stack([fm.features[k] for k in fn])
        all_X.append(Xs)

    X = np.vstack(all_X) if all_X else np.empty((0, len(feat_names or [])))
    logger.info("Features: %d columns from mode=%s groups=%s (per-symbol)", X.shape[1], mode, feature_groups or "all")
    return X, feat_names or []


def build_aligned_training_frame(
    ohlcv: dict,
    mode: str,
    feature_groups: Optional[List[str]] = None,
) -> dict:
    """Build a timestamp-aligned training frame.

    Rows are aligned per symbol first, then merged into a timestamp-major
    order so walk-forward validation can operate on chronological windows
    instead of flattened symbol blocks.
    """
    from alphaforge.features.pipeline import compute_features

    close_arr = ohlcv["close"].astype(np.float64)
    high_arr = ohlcv["high"].astype(np.float64)
    low_arr = ohlcv["low"].astype(np.float64)
    open_arr = ohlcv["open"].astype(np.float64)
    volume_arr = ohlcv["volume"].astype(np.float64)
    symbols = np.asarray(ohlcv.get("symbol", ["" for _ in range(len(close_arr))]))
    timestamps = np.asarray(ohlcv.get("timestamp", np.arange(len(close_arr), dtype=np.int64)))

    unique_syms: list[str] = []
    symbol_order: dict[str, int] = {}
    for s in symbols:
        if s not in symbol_order:
            symbol_order[s] = len(unique_syms)
            unique_syms.append(str(s))

    x_parts: list[np.ndarray] = []
    y_parts: list[np.ndarray] = []
    label_gross_parts: list[np.ndarray] = []
    label_net_parts: list[np.ndarray] = []
    action_gross_parts: list[np.ndarray] = []
    action_net_parts: list[np.ndarray] = []
    ts_parts: list[np.ndarray] = []
    sym_rank_parts: list[np.ndarray] = []
    close_price_parts: list[np.ndarray] = []
    feat_names: list[str] | None = None

    cfg = MODE_CONFIG[mode]
    max_hold = cfg["max_hold"]
    stop_mult = cfg["stop_mult"]
    target_mult = cfg["target_mult"]
    min_edge_r = cfg.get("min_edge_r", 0.15)
    ambiguity_margin_r = cfg.get("ambiguity_margin_r", 0.10)

    for sym in unique_syms:
        mask = symbols == sym
        sym_close = close_arr[mask]
        sym_high = high_arr[mask]
        sym_low = low_arr[mask]
        sym_open = open_arr[mask]
        sym_volume = volume_arr[mask]
        sym_ts = timestamps[mask]
        n_sym = len(sym_close)
        if n_sym <= max_hold + 1:
            continue

        fm = compute_features(
            {
                "close": sym_close,
                "high": sym_high,
                "low": sym_low,
                "open": sym_open,
                "volume": sym_volume,
                "symbol": sym,
            },
            mode=mode,
            feature_groups=feature_groups,
        )
        fn = sorted(fm.features.keys())
        if feat_names is None:
            feat_names = fn
        Xs = np.column_stack([fm.features[k] for k in fn]).astype(np.float64)

        ints_s, gross_s, net_s, long_gross_s, short_gross_s, long_net_s, short_net_s = _generate_labels_numba(
            sym_close, sym_high, sym_low,
            max_hold, stop_mult, target_mult, n_sym,
            min_edge_r, ambiguity_margin_r,
        )

        label_len = len(ints_s)
        if label_len == 0:
            continue

        x_parts.append(Xs[:label_len])
        y_parts.append(ints_s[:label_len])
        label_gross_parts.append(gross_s[:label_len])
        label_net_parts.append(net_s[:label_len])
        action_gross_parts.append(
            np.column_stack([
                long_gross_s[:label_len],
                short_gross_s[:label_len],
                np.zeros(label_len, dtype=np.float64),
            ])
        )
        action_net_parts.append(
            np.column_stack([
                long_net_s[:label_len],
                short_net_s[:label_len],
                np.zeros(label_len, dtype=np.float64),
            ])
        )
        ts_parts.append(sym_ts[:label_len])
        sym_rank_parts.append(np.full(label_len, symbol_order[sym], dtype=np.int32))
        close_price_parts.append(sym_close[:label_len])

    if not x_parts:
        return {
            "X": np.empty((0, 0), dtype=np.float64),
            "y_int": np.empty((0,), dtype=np.int32),
            "label_gross_r": np.empty((0,), dtype=np.float64),
            "label_net_r": np.empty((0,), dtype=np.float64),
            "action_gross_r": np.empty((0, 3), dtype=np.float64),
            "action_net_r": np.empty((0, 3), dtype=np.float64),
            "timestamps": np.empty((0,), dtype=timestamps.dtype),
            "symbols": np.empty((0,), dtype=object),
            "close_prices": np.empty((0,), dtype=np.float64),
            "feature_names": feat_names or [],
        }

    X = np.vstack(x_parts)
    y_int = np.concatenate(y_parts)
    label_gross_r = np.concatenate(label_gross_parts)
    label_net_r = np.concatenate(label_net_parts)
    action_gross_r = np.vstack(action_gross_parts)
    action_net_r = np.vstack(action_net_parts)
    ts = np.concatenate(ts_parts)
    sym_rank = np.concatenate(sym_rank_parts)
    close_prices = np.concatenate(close_price_parts) if close_price_parts else np.array([], dtype=np.float64)
    if np.issubdtype(ts.dtype, np.datetime64):
        ts_sort = ts.astype("datetime64[ns]").astype(np.int64)
    elif ts.dtype.kind in {"i", "u"}:
        ts_sort = ts.astype(np.int64, copy=False)
    else:
        import pandas as pd
        ts_sort = pd.to_datetime(ts).view("int64")

    sort_idx = np.lexsort((sym_rank, ts_sort))
    symbols_arr = np.asarray([unique_syms[int(i)] for i in sym_rank], dtype=object)

    return {
        "X": X[sort_idx],
        "y_int": y_int[sort_idx],
        "label_gross_r": label_gross_r[sort_idx],
        "label_net_r": label_net_r[sort_idx],
        "action_gross_r": action_gross_r[sort_idx],
        "action_net_r": action_net_r[sort_idx],
        "timestamps": ts[sort_idx],
        "symbols": symbols_arr[sort_idx],
        "close_prices": close_prices[sort_idx] if len(close_prices) == len(ts) else close_prices,
        "feature_names": feat_names or [],
    }


# ---------------------------------------------------------------------------
# Walk-forward validation
# ---------------------------------------------------------------------------

def _compute_stability(values: list[float]) -> float:
    if not values:
        return 0.0
    arr = np.array(values, dtype=float)
    mean_v = float(np.mean(arr))
    if abs(mean_v) < 1e-10:
        return 0.0
    std_v = float(np.std(arr, ddof=1))
    cv = std_v / abs(mean_v)
    return max(0.0, min(1.0, 1.0 - cv))


def walk_forward_validate(
    X: np.ndarray,
    y_int: np.ndarray,
    net_r_values: np.ndarray,
    mode: str,
    min_folds: int = 6,
    dump_softmax_path: str | None = None,
    threshold: float | None = None,
    action_net_r: np.ndarray | None = None,
    return_raw_preds: bool = False,
) -> List[dict] | tuple[list[dict], list[np.ndarray], list[np.ndarray], list[np.ndarray]]:
    """6-fold anchored expanding walk-forward validation.

    Returns per-fold result dicts.
    """
    from alphaforge.training.xgb_trainer import XGBoostTrainer
    from alphaforge.reports.metrics import compute_oos_metrics
    from collections import Counter
    import xgboost as xgb

    n = len(X)
    if action_net_r is None:
        action_net_r = np.column_stack([
            net_r_values,
            net_r_values,
            np.zeros(n, dtype=np.float64),
        ]) if n > 0 else np.empty((0, 3), dtype=np.float64)
    fold_size = n // (min_folds + 1)
    results: list[dict] = []
    purge_bars = fold_size // 4
    embargo_bars = fold_size // 8

    logger.info(
        "WFV: folds=%d, fold_size=%d, purge=%d, embargo=%d",
        min_folds, fold_size, purge_bars, embargo_bars,
    )

    # Init raw preds storage if needed
    if return_raw_preds:
        walk_forward_validate._fold_preds = []
        walk_forward_validate._fold_y_class = []
        walk_forward_validate._fold_y_val = []

    for fold in range(min_folds):
        train_end = (fold + 1) * fold_size
        val_start = train_end
        val_end = val_start + fold_size // 2
        if val_end >= n:
            logger.warning("Fold %d: val_end >= n â€” stopping", fold + 1)
            break

        effective_train_end = train_end - purge_bars
        effective_val_start = val_start + embargo_bars

        if effective_train_end <= 0 or effective_val_start >= val_end:
            logger.warning("Fold %d: boundary issue â€” stopping", fold + 1)
            break

        X_train = X[:effective_train_end]
        y_train = y_int[:effective_train_end]
        X_val = X[effective_val_start:val_end]
        y_val = y_int[effective_val_start:val_end]
        val_action_net = action_net_r[effective_val_start:val_end]

        if len(X_train) < 50 or len(X_val) < 10:
            logger.warning("Fold %d: insufficient samples â€” stopping", fold + 1)
            break

        trainer = XGBoostTrainer(mode=mode)
        fold_result = trainer.train(X_train, y_train)
        dval = xgb.DMatrix(X_val)
        y_pred_prob = fold_result.model.predict(dval)
        y_pred_prob_max = np.max(y_pred_prob, axis=1)
        y_pred = np.argmax(y_pred_prob, axis=1)

        # Save raw preds for post-hoc threshold sweep (before threshold applied)
        if return_raw_preds:
            walk_forward_validate._fold_preds.append(y_pred_prob_max.copy())
            walk_forward_validate._fold_y_class.append(y_pred.copy())
            walk_forward_validate._fold_y_val.append(y_val.copy())

        # Apply confidence threshold: force NO_TRADE when model is uncertain
        _threshold = threshold if threshold is not None else float(CONFIDENCE_THRESHOLD)
        low_conf_count = int(np.sum(y_pred_prob_max < _threshold))
        low_conf_pct = float(low_conf_count / len(y_pred_prob_max) * 100)
        y_pred[y_pred_prob_max < _threshold] = 2  # NO_TRADE

        # Accumulate softmax probs for distribution dump
        if dump_softmax_path:
            if not hasattr(walk_forward_validate, '_softmax_bins'):
                walk_forward_validate._softmax_bins = []
            walk_forward_validate._softmax_bins.append(y_pred_prob_max)

        pred_labels = np.array(["LONG_NOW" if p == 0 else "SHORT_NOW" if p == 1 else "NO_TRADE" for p in y_pred], dtype=object)
        pred_gross_r = val_action_net[np.arange(len(y_pred)), y_pred]
        pred_metrics = compute_oos_metrics(pred_labels.tolist(), pred_gross_r.tolist(), fee_pct=0.04)

        val_accuracy = float(np.mean(y_pred == y_val))
        train_accuracy = float(fold_result.train_metrics.get("accuracy", 0.0))
        val_logloss = float(fold_result.val_metrics.get("logloss", 0.0))
        train_logloss = float(fold_result.train_metrics.get("logloss", 0.0))

        long_count = int(np.sum(y_pred == 0))
        short_count = int(np.sum(y_pred == 1))
        no_trade_count = int(np.sum(y_pred == 2))
        active_trade_count = long_count + short_count
        true_counts = Counter(y_val)

        cm = np.zeros((3, 3), dtype=int)
        for t, p in zip(y_val, y_pred):
            cm[t, p] += 1

        true_labels = np.array(["LONG_NOW" if t == 0 else "SHORT_NOW" if t == 1 else "NO_TRADE" for t in y_val], dtype=object)
        true_gross_r = val_action_net[np.arange(len(y_val)), y_val]
        oracle_metrics = compute_oos_metrics(true_labels.tolist(), true_gross_r.tolist(), fee_pct=0.04)
        net_r_expectancy_val = float(pred_metrics.get("avg_net_R_per_active_trade", 0.0))

        results.append({
            "fold": fold + 1,
            "n_train": len(X_train),
            "n_val": len(X_val),
            "purge_period": purge_bars,
            "embargo_period": embargo_bars,
            "val_start": val_start,
            "val_end": val_end,
            "effective_val_start": effective_val_start,
            "train_accuracy": train_accuracy,
            "train_logloss": train_logloss,
            "val_accuracy": val_accuracy,
            "val_logloss": val_logloss,
            "active_trade_count": active_trade_count,
            "long_count": long_count,
            "short_count": short_count,
            "no_trade_count": no_trade_count,
            "long_actual": int(true_counts.get(0, 0)),
            "short_actual": int(true_counts.get(1, 0)),
            "no_trade_actual": int(true_counts.get(2, 0)),
            "confusion_matrix": cm.tolist(),
            "net_r_expectancy": net_r_expectancy_val,
            "low_conf_count": low_conf_count,
            "low_conf_pct": round(low_conf_pct, 2),
            "training_duration_seconds": fold_result.training_duration_seconds,
            "decision_labels": pred_labels.tolist(),
            "decision_gross_r": pred_gross_r.tolist(),
            "active_metrics": pred_metrics,
            "oracle_metrics": oracle_metrics,
        })

        logger.info(
            "Fold %d/%d: train=%d, val=%d, val_acc=%.4f, active=%d",
            fold + 1, min_folds, results[-1]["n_train"], results[-1]["n_val"],
            val_accuracy, active_trade_count,
        )

    # Save softmax distribution dump if requested
    if dump_softmax_path and hasattr(walk_forward_validate, '_softmax_bins'):
        all_probs = np.concatenate(walk_forward_validate._softmax_bins)
        np.save(dump_softmax_path, all_probs)
        logger.info("Saved %d softmax probs to %s", len(all_probs), dump_softmax_path)
        del walk_forward_validate._softmax_bins

    if return_raw_preds:
        return results, walk_forward_validate._fold_preds, walk_forward_validate._fold_y_class, walk_forward_validate._fold_y_val

    return results


# ---------------------------------------------------------------------------
# Overfit detection (MHT + PBO)
# ---------------------------------------------------------------------------

def compute_overfit_gap(wfv_results: List[dict]) -> dict:
    """Compute overfit indicators from walk-forward results.

    Returns dict with:
      - overfit_gap: mean(train_accuracy) - mean(val_accuracy)
      - train_oos_correlation: correlation of train vs val acc across folds
      - pbo_risk: qualitative PBO risk assessment
    """
    train_accs = [r["train_accuracy"] for r in wfv_results]
    val_accs = [r["val_accuracy"] for r in wfv_results]

    overfit_gap = float(np.mean(train_accs) - np.mean(val_accs))

    # Train-OOS correlation (low = overfit)
    if len(train_accs) >= 3:
        corr = float(np.corrcoef(train_accs, val_accs)[0, 1])
    else:
        corr = 0.0

    # PBO risk (simplified: high when gap > 0.1 or correlation < 0)
    if overfit_gap > 0.10 or corr < -0.3:
        pbo_risk = "HIGH"
    elif overfit_gap > 0.05 or corr < 0.0:
        pbo_risk = "MODERATE"
    else:
        pbo_risk = "LOW"

    return {
        "overfit_gap": round(overfit_gap, 4),
        "train_oos_correlation": round(corr, 4),
        "pbo_risk": pbo_risk,
    }


# ---------------------------------------------------------------------------
# Sharpe ratio (simplified OOS R-expectancy Sharpe)
# ---------------------------------------------------------------------------

def compute_oos_sharpe(wfv_results: List[dict]) -> float:
    """Compute OOS Sharpe ratio from per-fold active-trade net R values."""
    r_exps = []
    for r in wfv_results:
        active_metrics = r.get("active_metrics") or {}
        value = active_metrics.get("avg_net_R_per_active_trade")
        if value is None:
            value = r.get("net_r_expectancy", 0.0)
        if abs(float(value)) > 1e-12:
            r_exps.append(float(value))
    if len(r_exps) < 2:
        return 0.0
    mean_r = float(np.mean(r_exps))
    std_r = float(np.std(r_exps, ddof=1))
    if std_r < 1e-12:
        return 0.0
    sharpe = mean_r / std_r * np.sqrt(len(r_exps))
    return round(float(sharpe), 4)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def collect_metrics(
    wfv_results: List[dict],
    X: np.ndarray,
    feature_names: List[str],
    fee_pct: float = 0.04,
) -> dict:
    """Collect and aggregate training metrics."""
    val_accs = [r["val_accuracy"] for r in wfv_results]
    train_accs = [r["train_accuracy"] for r in wfv_results]

    accuracy = float(np.mean(val_accs)) if val_accs else 0.0
    train_accuracy = float(np.mean(train_accs)) if train_accs else 0.0
    stability = _compute_stability(val_accs)

    overfit = compute_overfit_gap(wfv_results)
    net_sharpe = compute_oos_sharpe(wfv_results)
    round_trip_cost_r = fee_pct * 2 / 100

    from alphaforge.reports.metrics import compute_oos_metrics

    decision_labels: list[str] = []
    decision_gross_r: list[float] = []
    for r in wfv_results:
        decision_labels.extend(r.get("decision_labels", []))
        decision_gross_r.extend(r.get("decision_gross_r", []))

    if decision_labels and len(decision_labels) == len(decision_gross_r):
        trade_metrics = compute_oos_metrics(decision_labels, decision_gross_r, fee_pct=fee_pct)
        total_active = trade_metrics["active_trade_count"]
        total_long = trade_metrics["long_trade_count"]
        total_short = trade_metrics["short_trade_count"]
        total_no_trade = trade_metrics["no_trade_count"]
        exposure_pct = trade_metrics["exposure_pct"]
        net_expectancy_r = float(trade_metrics["avg_net_R_per_active_trade"])
        gross_expectancy_r = (
            float(trade_metrics["total_gross_R"] / total_active)
            if total_active > 0 else 0.0
        )
        total_gross_r = float(trade_metrics["total_gross_R"])
        total_net_r = float(trade_metrics["total_net_R"])
        total_decisions = len(decision_labels)
    else:
        net_r_exps = [r.get("net_r_expectancy", 0.0) for r in wfv_results]
        gross_r_exps = [nr + round_trip_cost_r for nr in net_r_exps]
        net_expectancy_r = float(np.mean(net_r_exps)) if net_r_exps else 0.0
        gross_expectancy_r = float(np.mean(gross_r_exps)) if gross_r_exps else 0.0
        total_active = sum(r["active_trade_count"] for r in wfv_results)
        total_long = sum(r["long_count"] for r in wfv_results)
        total_short = sum(r["short_count"] for r in wfv_results)
        total_no_trade = sum(r["no_trade_count"] for r in wfv_results)
        total_decisions = total_active + total_no_trade
        exposure_pct = (total_active / total_decisions * 100) if total_decisions > 0 else 0.0
        total_gross_r = sum((r.get("active_metrics", {}) or {}).get("total_gross_R", 0.0) for r in wfv_results)
        total_net_r = sum((r.get("active_metrics", {}) or {}).get("total_net_R", 0.0) for r in wfv_results)
    net_sharpe_ratio = net_sharpe

    # Confidence threshold metrics
    low_conf_counts = [r.get("low_conf_count", 0) for r in wfv_results]
    total_low_conf = sum(low_conf_counts)
    total_val_samples = sum(r["n_val"] for r in wfv_results)
    low_conf_rate = float(total_low_conf / total_val_samples * 100) if total_val_samples > 0 else 0.0

    # Cost decomposition
    round_trip_cost_bps = fee_pct * 2  # bps

    return {
        "mode": mode.upper(),
        "accuracy": round(accuracy, 4),
        "train_accuracy": round(train_accuracy, 4),
        "accuracy_stability": round(stability, 4),
        "sharpe_ratio": net_sharpe_ratio,
        "net_sharpe_ratio": net_sharpe_ratio,
        "net_expectancy_r": round(net_expectancy_r, 6),
        "gross_expectancy_r": round(gross_expectancy_r, 6),
        "total_gross_R": round(total_gross_r, 6),
        "total_net_R": round(total_net_r, 6),
        "overfit_gap": overfit["overfit_gap"],
        "train_oos_correlation": overfit["train_oos_correlation"],
        "pbo_risk": overfit["pbo_risk"],
        "feature_count": X.shape[1],
        "n_samples": len(X),
        "n_folds": len(wfv_results),
        "total_active_trades": total_active,
        "total_long": total_long,
        "total_short": total_short,
        "total_no_trade": total_no_trade,
        "exposure_pct": round(exposure_pct, 2),
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "low_conf_rate_pct": round(low_conf_rate, 2),
        "cost_decomposition": {
            "fee_pct": fee_pct,
            "round_trip_cost_bps": round_trip_cost_bps,
            "round_trip_cost_r": round_trip_cost_r,
        },
        "features": feature_names,
    }


# ---------------------------------------------------------------------------
# Discovery pipeline integration
# ---------------------------------------------------------------------------


def _run_discovery_after_training(
    mode: str,
    ohlcv: dict,
    feature_groups: list[str] | None = None,
    folds: int = 6,
    confidence_threshold: float = 0.55,
    output: str | None = None,
) -> None:
    """Run the discovery pipeline after training completes.

    Called when ``--discovery`` flag is set in the training CLI.
    """
    from alphaforge.discovery import DiscoveryConfig
    from alphaforge.discovery.pipeline import run_discovery

    symbols = list(set(str(s) for s in ohlcv.get("symbol", [])))
    feat_str = ",".join(feature_groups) if feature_groups else "all"

    config = DiscoveryConfig(
        mode=mode,
        symbols=tuple(symbols),
        features=feat_str,
        folds=folds,
        confidence_threshold=confidence_threshold,
        use_synthetic=False,
        output_dir=str(Path(output).parent) if output else "artifacts/discovery",
        create_handoff=True,
    )

    result = run_discovery(config)

    print(f"\n  Discovery result: {result.status}")
    if result.rejection:
        print(f"  Decision: {result.rejection.get('decision', '?')}")
        print(f"  Summary: {result.rejection.get('summary', 'N/A')}")
    print(f"  Trades: {result.trade_count} | Duration: {result.duration_seconds:.1f}s")

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        import json as _json
        out_path.write_text(_json.dumps({
            "status": result.status,
            "rejection": result.rejection,
            "metrics": result.metrics,
            "trade_count": result.trade_count,
            "signal_count": result.signal_count,
            "duration_seconds": result.duration_seconds,
            "handoff": result.handoff,
        }, indent=2, default=str))
        print(f"  Discovery report saved: {out_path.resolve()}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="AlphaForge Full Training Pipeline")
    parser.add_argument("--mode", default="SWING", choices=["SWING", "SCALP", "AGGRESSIVE_SCALP"])
    parser.add_argument("--features", default="all", help="Feature groups: comma-separated (returns,volatility,atr,momentum,volume,breakout,orderbook,regime,candle_pattern) or 'all'")
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT", help="Comma-separated symbols")
    parser.add_argument("--synthetic", action="store_true", help="Force synthetic data")
    parser.add_argument("--folds", type=int, default=6, help="WFV folds")
    parser.add_argument("--output", default=None, help="Output report path")
    parser.add_argument("--dump-softmax", default=None, help="Dump softmax probs to .npy")
    parser.add_argument("--panel-cache", default=None, help="Path to factor_sprint panel cache directory")
    parser.add_argument("--dump-features", default=None, help="Dump X_clean + feat_names to .npy/.txt")
    parser.add_argument("--positive-control", action="store_true", help="Replace labels with synthetic feature-based signal for pipeline validation")
    parser.add_argument("--threshold-sweep", default=None,
                        help="Comma-separated threshold values to sweep (e.g., '0.1,0.3,0.45,0.55,0.7'). "
                             "Reports accuracy-exposure tradeoff for each.")
    parser.add_argument("--discovery", action="store_true",
                        help="Run full discovery pipeline after training (signal generation, "
                             "simulation backtest, profitability analysis, rejection evaluation)")
    parser.add_argument("--discovery-confidence-threshold", type=float, default=0.55,
                        help="Confidence threshold for discovery signal generation (default: 0.55)")
    parser.add_argument("--discovery-output", default=None,
                        help="Output path for discovery pipeline results (default: auto-generated)")
    args = parser.parse_args()

    global mode
    mode = args.mode.upper()
    symbols = [s.strip().upper() for s in args.symbols.split(",")]
    cfg = MODE_CONFIG[mode]
    interval = cfg["primary"]

    print(f"\n{'='*60}")
    print(f"  AlphaForge Training Pipeline")
    print(f"  Mode: {mode} | Interval: {interval} | Symbols: {len(symbols)}")
    print(f"  Features: {args.features} | WFV Folds: {args.folds}")
    print(f"{'='*60}\n")

    # Step 1: Load data
    print("[1/6] Loading OHLCV data...")
    ohlcv = None
    if args.panel_cache:
        ohlcv = _load_panel_data(args.panel_cache, symbols)
    elif not args.synthetic:
        ohlcv = load_cached_data(symbols, interval)
    if ohlcv is None:
        logger.info("Falling back to synthetic data")
        ohlcv = generate_synthetic_ohlcv(
            n_bars=3000,
            symbols=tuple(symbols),
            random_seed=42,
        )
    n_bars_total = len(ohlcv["close"])
    print(f"  {n_bars_total} total bars, {len(symbols)} symbols")

    feature_groups_arg = args.features.lower()
    if feature_groups_arg == "all":
        feature_groups = None
    else:
        feature_groups = [g.strip() for g in feature_groups_arg.split(",")]
    # Step 2/3: Build aligned dataset
    print("\n[2/6] Building aligned label + feature frame...")
    training_frame = build_aligned_training_frame(ohlcv, mode, feature_groups=feature_groups)
    X = training_frame["X"]
    feat_names = training_frame["feature_names"]
    y_int = training_frame["y_int"]
    label_gross_r = training_frame["label_gross_r"]
    label_net_r = training_frame["label_net_r"]
    action_gross_r = training_frame["action_gross_r"]
    action_net_r = training_frame["action_net_r"]
    sample_timestamps = training_frame["timestamps"]
    sample_symbols = training_frame["symbols"]

    print("\n[3/6] Aligning samples and cleaning NaNs...")
    print(f"  {X.shape[1]} feature columns, {X.shape[0]} aligned rows")

    nan_mask = np.isnan(X).any(axis=1)
    X_clean = X[~nan_mask]
    y_clean = y_int[~nan_mask]
    label_gross_clean = label_gross_r[~nan_mask]
    label_net_clean = label_net_r[~nan_mask]
    action_gross_clean = action_gross_r[~nan_mask]
    action_net_clean = action_net_r[~nan_mask]
    ts_clean = sample_timestamps[~nan_mask]
    sym_clean = sample_symbols[~nan_mask]
    print(f"  After NaN removal: {len(X_clean)} valid samples ({int(nan_mask.sum())} dropped)")
    
    # Feature dump for correlation analysis
    if args.dump_features:
        np.save(args.dump_features, X_clean)
        with open(args.dump_features.replace('.npy', '_names.txt'), 'w') as f:
            for name in feat_names:
                f.write(name + '\n')
        print(f"  Feature matrix saved: {X_clean.shape}")

    # Positive control: replace labels with synthetic feature-based signal
    if args.positive_control:
        rng = np.random.RandomState(42)
        feat_idx = 22  # log_return_1 â€” non-duplicate feature
        feat_vals = X_clean[:, feat_idx].copy()
        feat_norm = (feat_vals - np.mean(feat_vals)) / max(np.std(feat_vals), 1e-12)
        noise_std = 0.35
        signal = feat_norm + rng.normal(0, noise_std, size=len(feat_norm))
        y_new = np.full(len(signal), 2, dtype=np.int32)
        y_new[signal > 0.15] = 0   # LONG
        y_new[signal < -0.15] = 1  # SHORT
        long_c = int(np.sum(y_new == 0))
        short_c = int(np.sum(y_new == 1))
        notrade_c = int(np.sum(y_new == 2))
        print(f"\n  {'='*50}")
        print(f"  POSITIVE CONTROL TEST")
        print(f"  Feature: {feat_names[feat_idx]} (idx={feat_idx})")
        print(f"  Noise: N(0,{noise_std}) â€” label = sign(feature[t] + noise)")
        print(f"  Dist: LONG={long_c}, SHORT={short_c}, NO_TRADE={notrade_c}")
        print(f"  Baseline (NO_TRADE-guess): {max(notrade_c,long_c,short_c)/len(y_new):.3f}")
        y_clean = y_new
        label_gross_clean = np.where(y_new == 0, 0.02, np.where(y_new == 1, 0.02, 0.0)).astype(np.float64)
        label_net_clean = label_gross_clean.copy()
        action_gross_clean = np.column_stack([
            np.where(y_new == 0, 0.02, 0.0),
            np.where(y_new == 1, 0.02, 0.0),
            np.zeros(len(y_new), dtype=np.float64),
        ])
        action_net_clean = action_gross_clean.copy()

    if len(X_clean) < 100:
        print("  ERROR: Insufficient clean samples for training")
        sys.exit(1)

    # Step 4: Walk-forward validation
    if args.threshold_sweep:
        # â”€â”€ Threshold Sweep (train once, sweep thresholds on saved preds) â”€â”€
        thresholds = [float(t.strip()) for t in args.threshold_sweep.split(",")]
        thresholds = sorted(set(thresholds))
        print(f"\n{'='*60}")
        print(f"  THRESHOLD SWEEP â€” {len(thresholds)} thresholds")
        print(f"{'='*60}")

        wfv_results, fold_preds, fold_y_class, fold_y_val = walk_forward_validate(
            X_clean, y_clean, label_net_clean, mode, min_folds=args.folds,
            action_net_r=action_net_clean,
            return_raw_preds=True,
        )

        all_probs = np.concatenate(fold_preds)
        all_y_class = np.concatenate(fold_y_class)
        all_y_val = np.concatenate(fold_y_val)

        print("{:<10s}  {:<8s}  {:<10s}  {:<10s}  {:<10s}".format(
            "Threshold", "OOS Acc", "Trades", "Exposure", "No-trade"
        ))
        print(f"{'-'*50}")

        sweep_results = []
        for thresh in thresholds:
            y_pred_adj = all_y_class.copy()
            low_conf = all_probs < thresh
            y_pred_adj[low_conf] = 2

            active_count = int((~low_conf).sum())
            no_trade_count = int(low_conf.sum())
            total = len(y_pred_adj)
            exposure = 100.0 * active_count / total if total else 0.0
            acc = float(np.mean(y_pred_adj == all_y_val)) if total else 0.0

            print(f"{thresh:<8.2f}  {acc:<8.4f}  {active_count:<10d}  {exposure:<9.2f}%  {no_trade_count:<10d}")
            sweep_results.append({
                "threshold": thresh,
                "oos_accuracy": round(acc, 4),
                "active_trades": active_count,
                "exposure_pct": round(exposure, 2),
                "no_trade_count": no_trade_count,
            })

        print(f"{'-'*50}")
        viable = [r for r in sweep_results if r["exposure_pct"] > 10.0]
        if viable:
            best = max(viable, key=lambda r: r["oos_accuracy"])
            print(f"  Suggested threshold: {best['threshold']:.2f} "
                  f"(acc={best['oos_accuracy']:.4f}, "
                  f"exposure={best['exposure_pct']:.1f}%)")
        else:
            print(f"  No threshold achieves >10% exposure")
        print(f"{'='*60}\n")
    else:
        print(f"\n[4/6] Walk-forward validation ({args.folds} folds, anchored expanding)...")
        t0 = time.time()
        wfv_results = walk_forward_validate(
            X_clean, y_clean, label_net_clean, mode, min_folds=args.folds,
            action_net_r=action_net_clean,
            dump_softmax_path=args.dump_softmax,
        )
        wfv_duration = time.time() - t0
        print(f"  {len(wfv_results)} folds completed in {wfv_duration:.1f}s")

    # Step 5: Train final model
    print("\n[5/6] Training final model on all data...")
    from alphaforge.training.xgb_trainer import XGBoostTrainer

    final_trainer = XGBoostTrainer(mode=mode)
    final_result = final_trainer.train(X_clean, y_clean)
    final_acc = float(final_result.val_metrics.get("accuracy", 0))
    print(f"  Final model accuracy: {final_acc:.4f}")
    
    # Feature importance
    try:
        bst = final_result.model
        if hasattr(bst, 'get_score'):
            imp = bst.get_score(importance_type='gain')
        elif hasattr(bst, 'feature_importances_'):
            imp = dict(zip(feat_names, bst.feature_importances_))
        else:
            imp = {}
        if imp:
            sorted_imp = sorted(imp.items(), key=lambda x: -x[1])
            print(f"\n  Top-10 Feature Importance (gain):")
            for name, val in sorted_imp[:10]:
                print(f"    {name:40s} {val:.4f}")
            if len(sorted_imp) > 10:
                others = sum(v for _, v in sorted_imp[10:])
                print(f"    {'(remaining ' + str(len(sorted_imp)-10) + ' features)':40s} {others:.4f}")
    except Exception as e:
        logger.warning("Could not extract feature importance: %s", e)

    # Step 6: Collect metrics
    print("\n[6/6] Collecting metrics...")
    fee_pct = cfg.get("ambiguity_margin_r", 0.04) if False else 0.04  # keep at 4bps
    metrics = collect_metrics(wfv_results, X_clean, feat_names, fee_pct=fee_pct)

    print(f"\n{'='*60}")
    print(f"  TRAINING RESULTS â€” {mode}")
    print(f"{'='*60}")
    print(f"  Accuracy (OOS):              {metrics['accuracy']:.4f}")
    print(f"  Train Accuracy:              {metrics['train_accuracy']:.4f}")
    print(f"  Accuracy Stability:          {metrics['accuracy_stability']:.4f}")
    print(f"  Sharpe Ratio (OOS R-exp):    {metrics['sharpe_ratio']:.4f}")
    print(f"  Overfit Gap:                 {metrics['overfit_gap']:.4f}")
    print(f"  Train-OOS Correlation:       {metrics['train_oos_correlation']:.4f}")
    print(f"  PBO Risk:                    {metrics['pbo_risk']}")
    print(f"  Feature Count:               {metrics['feature_count']}")
    print(f"  Total Samples:               {metrics['n_samples']}")
    print(f"  Walk-Forward Folds:          {metrics['n_folds']}")
    print(f"  Active Trades:               {metrics['total_active_trades']}")
    print(f"  LONG / SHORT / NO_TRADE:     {metrics['total_long']} / {metrics['total_short']} / {metrics['total_no_trade']}")
    print(f"  Exposure %:                  {metrics['exposure_pct']:.1f}%")
    print(f"  Confidence Threshold:        {metrics['confidence_threshold']}")
    print(f"  Low Confidence Rate:         {metrics['low_conf_rate_pct']:.1f}%")
    cd = metrics['cost_decomposition']
    print(f"  Fee (bps):                   {cd['fee_pct']} ({cd['round_trip_cost_bps']} bps round-trip)")
    print(f"{'='*60}\n")

    # Save report if requested
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(metrics, f, indent=2, default=str)
        print(f"  Report saved: {output_path.resolve()}")

    # Run discovery pipeline if requested
    if args.discovery:
        print(f"\n{'='*60}")
        print(f"  DISCOVERY PIPELINE")
        print(f"{'='*60}")
        _run_discovery_after_training(
            mode=mode,
            ohlcv=ohlcv,
            feature_groups=feature_groups,
            folds=args.folds,
            confidence_threshold=args.discovery_confidence_threshold,
            output=args.discovery_output,
        )

    # Return the metrics for programmatic use
    return metrics


if __name__ == "__main__":
    metrics = main()
    # Print structured output for machine consumption
    print("\n---STRUCTURED_RESULTS---")
    print(json.dumps({
        "status": "PASS",
        "accuracy": metrics["accuracy"],
        "sharpe_ratio": metrics["sharpe_ratio"],
        "overfit_gap": metrics["overfit_gap"],
        "feature_count": metrics["feature_count"],
    }, indent=2))

