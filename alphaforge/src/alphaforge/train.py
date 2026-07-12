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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
try:
    from numba import njit
except ImportError:
    njit = lambda x: x

from lib.data_lake.guard import tag_as_real, assert_real_data

# Cost authority — SINGLE source of truth
from simulation.authority import get_cost_constants

_AUTHORITY = get_cost_constants()
# fee_pct in FRACTIONAL RETURN space (not R-multiples):
#   taker_fee_bps = 4.0 → 0.0004 per side → 0.0008 round trip
_FEE_FRACTIONAL = _AUTHORITY["taker_fee_bps"] / 10000.0  # 0.0004
_ROUND_TRIP_COST_FRACTIONAL = _FEE_FRACTIONAL * 2  # 0.0008

# Centralized training config loader — single source of truth
# Replaces the old MODE_CONFIG dict which was hardcoded and drifted from simulation registry.
from lib.config_training import load_training_config, TrainingConfig

_training_config_cache: dict[str, TrainingConfig] = {}


def _get_training_config(mode: str) -> TrainingConfig:
    """Get cached training config for mode.

    Loads from simulation profile registry + configs/training.yaml.
    Replaces old MODE_CONFIG lookups.
    """
    mode_upper = mode.upper()
    if mode_upper not in _training_config_cache:
        _training_config_cache[mode_upper] = load_training_config(mode_upper)
    return _training_config_cache[mode_upper]


# ── Backward-compatible MODE_CONFIG dict ────────────────────────────
# Old code (scripts/v7_lite/*.py, tests) imports MODE_CONFIG from
# alphaforge.train.  Build it from the canonical registry so existing
# imports keep working with correct values (Issue #319).
MODE_CONFIG: dict[str, dict] = {}
for _m in ["SWING", "SCALP", "AGGRESSIVE_SCALP"]:
    _c = _get_training_config(_m)
    MODE_CONFIG[_m] = {
        "primary": _c.primary_interval,
        "max_hold": _c.max_holding_bars,
        "stop_mult": _c.stop_multiplier,
        "target_mult": _c.target_multiplier,
        "ambiguity_margin_r": _c.ambiguity_margin_r,
        "min_edge_r": _c.min_action_edge_r,
        "label_horizon": _c.label_horizon,
        "label_threshold": _c.label_threshold,
    }


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
)
logger = logging.getLogger("alphaforge.train")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


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
        "open": [], "high": [], "low": [], "close": [], "volume": [],
        "timestamp": [], "symbol": [],
        "funding_rate": [], "open_interest": [], "premium_index": [],
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
        # Synthetic derivatives data fills so feature pipeline activates
        all_data["funding_rate"].append(rng.randn(n_bars) * 0.001)
        all_data["open_interest"].append(1000.0 + rng.randn(n_bars) * 100.0)
        all_data["premium_index"].append(rng.randn(n_bars) * 0.5)
    return {
        "open": np.concatenate(all_data["open"]),
        "high": np.concatenate(all_data["high"]),
        "low": np.concatenate(all_data["low"]),
        "close": np.concatenate(all_data["close"]),
        "volume": np.concatenate(all_data["volume"]),
        "timestamp": np.array(all_data["timestamp"], dtype=np.int64),
        "symbol": all_data["symbol"],
        "funding_rate": np.concatenate(all_data["funding_rate"]),
        "open_interest": np.concatenate(all_data["open_interest"]),
        "premium_index": np.concatenate(all_data["premium_index"]),
    }


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_panel_data(cache_dir: str, symbols: list[str]) -> dict | None:
    """Load OHLCV data from factor_sprint panel cache, per-symbol valid ranges.

    Unlike the previous all-symbol intersection approach, each symbol contributes
    its full available history. A symbol that started trading later or was
    delisted early does NOT truncate other symbols' data.

    This increases usable samples dramatically (20-symbol panel: 29,928 rows/symbol
    instead of 7,594 rows from the old intersection). The downstream pipeline
    handles variable-length symbols naturally: per-symbol feature/label computation
    processes each symbol independently, and cross-sectional rank normalization
    groups by timestamp (tolerating varying symbol counts).
    """
    import pandas as pd
    cache = Path(cache_dir)
    close_path = sorted(cache.glob("panel_*_close.parquet"))
    if not close_path:
        logger.error("No panel cache found in %s", cache_dir)
        return None
    prefix = close_path[0].stem.rsplit("_", 1)[0]
    symbol_set = set(s.upper() for s in symbols)

    # Load all OHLCV DataFrames once
    dfs: dict[str, pd.DataFrame] = {}
    for key in ["close", "high", "low", "open", "volume"]:
        dfs[key] = pd.read_parquet(cache / f"{prefix}_{key}.parquet")

    avail = [c for c in dfs["close"].columns if c.upper() in symbol_set]
    if not avail:
        logger.error("No requested symbols found in panel cache")
        return None

    closes, highs, lows, opens, volumes = [], [], [], [], []
    timestamps_out: list = []
    symbols_out: list = []
    total_bars = 0
    min_bars = 0
    max_bars = 0

    for col in avail:
        sym_start = dfs["close"][col].first_valid_index()
        sym_end = dfs["close"][col].last_valid_index()
        if sym_start is None:
            continue  # No data for this symbol at all

        # Slice each OHLCV series to this symbol's valid range
        sym_close = dfs["close"].loc[sym_start:sym_end, col].ffill().values.astype(np.float64)
        sym_high = dfs["high"].loc[sym_start:sym_end, col].ffill().values.astype(np.float64)
        sym_low = dfs["low"].loc[sym_start:sym_end, col].ffill().values.astype(np.float64)
        sym_open = dfs["open"].loc[sym_start:sym_end, col].ffill().values.astype(np.float64)
        sym_volume = dfs["volume"].loc[sym_start:sym_end, col].ffill().values.astype(np.float64)
        sym_ts = dfs["close"].loc[sym_start:sym_end].index.to_numpy()

        n = len(sym_close)
        closes.append(sym_close)
        highs.append(sym_high)
        lows.append(sym_low)
        opens.append(sym_open)
        volumes.append(sym_volume)
        # Convert timestamps to int64 (nanoseconds since epoch)
        # pd.DatetimeIndex with timezone yields object arrays of Timestamps
        if sym_ts.dtype.kind == "M":
            _ts_int = sym_ts.astype(np.int64)
        else:
            _ts_int = np.array([t.value for t in sym_ts], dtype=np.int64)
        timestamps_out.extend(_ts_int)
        symbols_out.extend([col] * n)
        total_bars += n
        if min_bars == 0 or n < min_bars:
            min_bars = n
        if n > max_bars:
            max_bars = n

    n_syms = len(closes)
    logger.info(
        "  Panel: %d symbols, %d total bars, %d–%d bars/symbol, range=%s to %s",
        n_syms, total_bars, min_bars, max_bars,
        pd.Timestamp(timestamps_out[0]).strftime("%Y-%m-%d") if timestamps_out else "?",
        pd.Timestamp(timestamps_out[-1]).strftime("%Y-%m-%d") if timestamps_out else "?",
    )

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
    extra_cols: dict[str, list] = {}

    import pyarrow.parquet as pq

    found_any = False
    for sym in symbols:
        sym_dir = raw_dir / sym
        if not sym_dir.exists():
            logger.info("  No data dir for %s at %s", sym, sym_dir)
            continue
        # Prefer combined derivatives file, fall back to regular parquet
        # Always use "1h" glob since all data is 1h regardless of mode interval
        deriv_files = sorted(sym_dir.glob("*_1h_with_derivatives.parquet"))
        if deriv_files:
            parquet_files = deriv_files[:1]  # Only load 1 file!
            logger.info("  Using derivatives-enhanced file: %s", deriv_files[0].name)
        else:
            one_h_files = sorted(sym_dir.glob("*_1h.parquet"))
            if one_h_files:
                parquet_files = one_h_files[:1]  # Only load 1 file!
            else:
                parquet_files = sorted(sym_dir.glob("*.parquet"))[:1]  # Only load 1 file!
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
                # If derivatives file, also load extra columns
                if "with_derivatives" in pf.name:
                    for col_name in ["funding_rate", "open_interest", "premium_index"]:
                        if col_name in table.column_names:
                            col_data = table.column(col_name).to_numpy()
                            extra_cols.setdefault(col_name, []).extend(col_data.tolist())
                            logger.info("    Loaded extra column: %s", col_name)
            except Exception as e:
                logger.warning("  Error reading %s: %s", pf, e)

    if not found_any:
        return None

    result = {
        "close": np.array(closes, dtype=np.float64),
        "high": np.array(highs, dtype=np.float64),
        "low": np.array(lows, dtype=np.float64),
        "open": np.array(opens, dtype=np.float64),
        "volume": np.array(volumes, dtype=np.float64),
        "timestamp": np.array(timestamps),
        "symbol": sym_list,
    }
    for col_name, col_list in extra_cols.items():
        if len(col_list) == len(closes):
            result[col_name] = np.array(col_list, dtype=np.float64)
            logger.info("  Added extra column to output: %s (%d values)", col_name, len(col_list))
    return tag_as_real(result)


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

    fee_pct = _FEE_FRACTIONAL  # authority: 4 bps taker
    round_trip_cost_r = _ROUND_TRIP_COST_FRACTIONAL  # authority: 8 bps round trip

    for i in range(n - max_hold - 1):
        entry_price = close[i]
        atr_sum = 0.0
        atr_count = 0
        start = max(0, i - 14)
        for k in range(start + 1, i + 1):
            # True Range: max(high-low, |high-prev_close|, |low-prev_close|)
            prev_close = close[k - 1]
            hl = high[k] - low[k]
            hc = abs(high[k] - prev_close)
            lc = abs(low[k] - prev_close)
            tr = max(hl, hc, lc)
            atr_sum += tr
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


@njit
def _generate_simple_labels_numba(close, high, low, label_horizon, label_threshold, cost, n,
                                   min_edge_r=0.15, ambiguity_margin_r=0.10):
    """Forward-return label generation — mode-aware horizon and threshold.

    Parameters come from MODE_CONFIG (label_horizon, label_threshold) and
    simulation authority constants (cost = round_trip_cost_r).

    Label decision uses net return (cost-aware). Forward return exceeding
    +threshold → LONG, below -threshold → SHORT, else NO_TRADE.

    Previously hardcoded horizon=12, threshold=0.003, cost=0.0008 which meant
    SWING/SCALP/AGGRESSIVE_SCALP all produced IDENTICAL labels despite
    operating at different timeframes. This was bug B1.
    """
    ints_list = np.empty(n - label_horizon - 1, dtype=np.int32)
    long_gross_vals = np.empty(n - label_horizon - 1, dtype=np.float64)
    short_gross_vals = np.empty(n - label_horizon - 1, dtype=np.float64)
    long_net_vals = np.empty(n - label_horizon - 1, dtype=np.float64)
    short_net_vals = np.empty(n - label_horizon - 1, dtype=np.float64)
    gross_r_vals = np.empty(n - label_horizon - 1, dtype=np.float64)
    net_r_vals = np.empty(n - label_horizon - 1, dtype=np.float64)

    for i in range(n - label_horizon - 1):
        fwd_ret = (close[i + label_horizon] / close[i] - 1.0)

        long_gross = max(fwd_ret, 0.0)
        short_gross = max(-fwd_ret, 0.0)
        long_net = long_gross - cost
        short_net = short_gross - cost

        long_gross_vals[i] = long_gross
        short_gross_vals[i] = short_gross
        long_net_vals[i] = long_net
        short_net_vals[i] = short_net

        if fwd_ret > label_threshold:
            ints_list[i] = 0  # LONG
            gross_r_vals[i] = long_gross
            net_r_vals[i] = long_net
        elif fwd_ret < -label_threshold:
            ints_list[i] = 1  # SHORT
            gross_r_vals[i] = short_gross
            net_r_vals[i] = short_net
        else:
            ints_list[i] = 2  # NO_TRADE
            gross_r_vals[i] = 0.0
            net_r_vals[i] = 0.0

    return ints_list, gross_r_vals, net_r_vals, long_gross_vals, short_gross_vals, long_net_vals, short_net_vals


def generate_labels(ohlcv: dict, mode: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Generate mode-aware forward-return labels.

    Uses label_horizon and label_threshold from MODE_CONFIG per mode,
    so SWING/SCALP/AGGRESSIVE_SCALP produce DIFFERENT label distributions.

    Returns (int_labels, gross_r_values, net_r_values, metrics_dict).
    Label DECISION uses net_R (cost-aware); gross_R is exported for analysis
    and net_R is exported for downstream economic metrics.
    """
    cfg = _get_training_config(mode)
    label_horizon = cfg.label_horizon
    label_threshold = cfg.label_threshold
    min_edge_r = cfg.min_action_edge_r
    ambiguity_margin_r = cfg.ambiguity_margin_r

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
        if n_sym <= label_horizon + 1:
            continue
        ints_s, gross_s, net_s, _, _, _, _ = _generate_simple_labels_numba(
            sym_close, sym_high, sym_low,
            label_horizon, label_threshold, _ROUND_TRIP_COST_FRACTIONAL, n_sym,
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


def _compute_single_symbol_frame(
    sym: str,
    sym_close: np.ndarray,
    sym_high: np.ndarray,
    sym_low: np.ndarray,
    sym_open: np.ndarray,
    sym_volume: np.ndarray,
    sym_ts: np.ndarray,
    mode: str,
    label_horizon: int,
    label_threshold: float,
    min_edge_r: float,
    ambiguity_margin_r: float,
    symbol_order: int,
    feature_groups: Optional[list[str]],
    precomputed_features: Optional[dict[str, tuple[np.ndarray, list[str]]]],
    funding_rate: Optional[np.ndarray] = None,
    open_interest: Optional[np.ndarray] = None,
    premium_index: Optional[np.ndarray] = None,
) -> Optional[dict]:
    """Compute features + labels for a single symbol.

    Returns a dict of arrays keyed by part name, or None if the symbol has
    too few bars. Designed to be called from ``joblib.Parallel`` workers.

    Extra columns (funding_rate, open_interest, premium_index) are passed
    as per-symbol masked arrays to maintain correct length alignment with
    OHLCV arrays.
    """
    from alphaforge.features.pipeline import cached_compute_features, CACHE_DIR_DEFAULT
    from alphaforge.train import _ROUND_TRIP_COST_FRACTIONAL

    n_sym = len(sym_close)
    if n_sym <= label_horizon + 1:
        return None

    if precomputed_features is not None and sym in precomputed_features:
        Xs, fn = precomputed_features[sym]
    else:
        ohlcv_input = {
            "close": sym_close,
            "high": sym_high,
            "low": sym_low,
            "open": sym_open,
            "volume": sym_volume,
            "symbol": sym,
            "timestamp": sym_ts,  # S3 time features need this
        }
        if funding_rate is not None:
            ohlcv_input["funding_rate"] = funding_rate
        if open_interest is not None:
            ohlcv_input["open_interest"] = open_interest
        if premium_index is not None:
            ohlcv_input["premium_index"] = premium_index
        _cfg = _get_training_config(mode)
        _interval = _cfg.primary_interval
        fm = cached_compute_features(
            ohlcv_input, mode=mode, interval=_interval,
            feature_groups=feature_groups,
            cache_dir=CACHE_DIR_DEFAULT,
        )
        fn = sorted(fm.features.keys())
        Xs = np.column_stack([fm.features[k] for k in fn]).astype(np.float64)

        ints_s, gross_s, net_s, long_gross_s, short_gross_s, long_net_s, short_net_s = _generate_simple_labels_numba(
            sym_close, sym_high, sym_low,
            label_horizon, label_threshold, _ROUND_TRIP_COST_FRACTIONAL, n_sym,
            min_edge_r, ambiguity_margin_r,
        )

    label_len = len(ints_s)
    if label_len == 0:
        return None

    return {
        "sym_order": symbol_order,
        "X": Xs[:label_len],
        "y": ints_s[:label_len],
        "label_gross": gross_s[:label_len],
        "label_net": net_s[:label_len],
        "action_gross": np.column_stack([
            long_gross_s[:label_len],
            short_gross_s[:label_len],
            np.zeros(label_len, dtype=np.float64),
        ]),
        "action_net": np.column_stack([
            long_net_s[:label_len],
            short_net_s[:label_len],
            np.zeros(label_len, dtype=np.float64),
        ]),
        "ts": sym_ts[:label_len],
        "close_prices": sym_close[:label_len],
        "feat_names": fn,
    }


def compute_all_features(ohlcv: dict, mode: str) -> Tuple[np.ndarray, List[str]]:
    """Compute all feature groups per-symbol to avoid cross-symbol contamination."""
    return compute_features_selected(ohlcv, mode)


def _compute_one_symbol(
    sym: str,
    ohlcv: dict,
    symbols_array: np.ndarray,
    mode: str,
    feature_groups: Optional[List[str]],
) -> Tuple[str, np.ndarray, List[str]]:
    """Compute features for a single symbol.

    Imports compute_features inside the function body so it can be pickled
    across process boundaries by ProcessPoolExecutor.
    """
    from alphaforge.features.pipeline import compute_features

    mask = symbols_array == sym
    sym_ohlcv = {
        "close": ohlcv["close"][mask],
        "high": ohlcv["high"][mask],
        "low": ohlcv["low"][mask],
        "open": ohlcv["open"][mask],
        "volume": ohlcv["volume"][mask],
    }
    if "funding_rate" in ohlcv:
        sym_ohlcv["funding_rate"] = ohlcv["funding_rate"][mask]
    if "open_interest" in ohlcv:
        sym_ohlcv["open_interest"] = ohlcv["open_interest"][mask]
    if "premium_index" in ohlcv:
        sym_ohlcv["premium_index"] = ohlcv["premium_index"][mask]
    if feature_groups is None or feature_groups == ["all"]:
        fm = compute_features(sym_ohlcv, mode=mode)
    else:
        fm = compute_features(sym_ohlcv, mode=mode, feature_groups=feature_groups)
    fn = sorted(fm.features.keys())
    Xs = np.column_stack([fm.features[k] for k in fn])
    return sym, Xs, fn


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

    if len(unique_syms) == 1:
        # Single symbol — skip multiprocessing overhead
        _, Xs, fn = _compute_one_symbol(unique_syms[0], ohlcv, symbols, mode, feature_groups)
        feat_names = fn
        all_X.append(Xs)
    else:
        max_workers = min(os.cpu_count() or 4, len(unique_syms))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            fut_map = {
                executor.submit(_compute_one_symbol, sym, ohlcv, symbols, mode, feature_groups): i
                for i, sym in enumerate(unique_syms)
            }
            ordered = [None] * len(unique_syms)
            for fut, i in fut_map.items():
                _, Xs, fn = fut.result()
                ordered[i] = (Xs, fn)
            for Xs, fn in ordered:
                if feat_names is None:
                    feat_names = fn
                all_X.append(Xs)

    X = np.vstack(all_X) if all_X else np.empty((0, len(feat_names or [])))
    X = X.astype(np.float32)
    logger.info("Features: %d columns from mode=%s groups=%s (per-symbol)", X.shape[1], mode, feature_groups or "all")
    return X, feat_names or []


def build_aligned_training_frame(
    ohlcv: dict,
    mode: str,
    feature_groups: Optional[List[str]] = None,
    precomputed_features: Optional[dict[str, np.ndarray]] = None,
) -> dict:
    """Build a timestamp-aligned training frame.

    Rows are aligned per symbol first, then merged into a timestamp-major
    order so walk-forward validation can operate on chronological windows
    instead of flattened symbol blocks.

    Args:
        ohlcv: dict with OHLCV data arrays and 'symbol' list.
        mode: Trading mode string.
        feature_groups: Optional list of feature groups to compute.
        precomputed_features: Optional dict mapping symbol -> (feature_matrix, feature_names).
            When provided, skips feature re-computation (avoids double compute).
    """
    from alphaforge.features.pipeline import cached_compute_features, CACHE_DIR_DEFAULT

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

    _cfg_t = _get_training_config(mode)
    min_edge_r = _cfg_t.min_action_edge_r
    ambiguity_margin_r = _cfg_t.ambiguity_margin_r

    # Build per-symbol extra column dicts (masked per symbol)
    sym_extras: dict[str, dict[str, np.ndarray]] = {}
    for sym in unique_syms:
        mask = symbols == sym
        extra = {}
        for key in ("funding_rate", "open_interest", "premium_index"):
            if key in ohlcv:
                extra[key] = ohlcv[key][mask]
        if extra:
            sym_extras[sym] = extra

    # Parallel per-symbol computation
    from joblib import Parallel, delayed
    n_jobs = min(len(unique_syms), os.cpu_count() or 1)
    symbol_results = Parallel(n_jobs=n_jobs, prefer="threads")(
        delayed(_compute_single_symbol_frame)(
            sym=sym,
            sym_close=close_arr[symbols == sym],
            sym_high=high_arr[symbols == sym],
            sym_low=low_arr[symbols == sym],
            sym_open=open_arr[symbols == sym],
            sym_volume=volume_arr[symbols == sym],
            sym_ts=timestamps[symbols == sym],
            mode=mode,
            label_horizon=_cfg_t.label_horizon,
            label_threshold=_cfg_t.label_threshold,
            min_edge_r=min_edge_r,
            ambiguity_margin_r=ambiguity_margin_r,
            symbol_order=symbol_order[sym],
            feature_groups=feature_groups,
            precomputed_features=precomputed_features,
            **sym_extras.get(sym, {}),
        )
        for sym in unique_syms
    )

    # Collect and order results
    target_n_cols = 0
    full_feat_names: list[str] | None = None
    for res in symbol_results:
        if res is None:
            continue
        n_cols = res["X"].shape[1]
        if n_cols > target_n_cols:
            target_n_cols = n_cols
            full_feat_names = res["feat_names"]

    # Pad x_parts to uniform feature dimension across symbols
    # (derivatives-enhanced symbols produce extra features from funding/OI/premium groups)
    for res in symbol_results:
        if res is None:
            continue
        if res["X"].shape[1] < target_n_cols:
            pad_width = target_n_cols - res["X"].shape[1]
            res["X"] = np.column_stack([
                res["X"],
                np.full((res["X"].shape[0], pad_width), np.nan, dtype=np.float64),
            ])
        x_parts.append(res["X"])
        y_parts.append(res["y"])
        label_gross_parts.append(res["label_gross"])
        label_net_parts.append(res["label_net"])
        action_gross_parts.append(res["action_gross"])
        action_net_parts.append(res["action_net"])
        ts_parts.append(res["ts"])
        sym_rank_parts.append(np.full(len(res["y"]), res["sym_order"], dtype=np.int32))
        close_price_parts.append(res["close_prices"])
    feat_names = full_feat_names  # Use fullest feature name set (from symbols with derivative data)

    # ------------------------------------------------------------------
    # Phase 2: Cross-sectional features (residual momentum, lead-lag)
    # Computed once over the full multi-symbol panel, then joined per-symbol.
    # ------------------------------------------------------------------
    if len(unique_syms) >= 2:
        try:
            from alphaforge.features.residual_momentum import compute_residual_momentum_group
            # Check all symbols have the same length before building multi_ohlcv
            sym_lengths = {}
            for sym in unique_syms:
                sym_lengths[sym] = len(close_arr[symbols == sym])
            if len(set(sym_lengths.values())) > 1:
                logger.warning(
                    "Phase 2 (residual momentum) skipped: symbols have different lengths %s. "
                    "Load panel data with consistent per-symbol ranges.",
                    sym_lengths,
                )
            else:
                # Build multi-symbol OHLCV dict from the original input
                multi_ohlcv: dict[str, dict[str, np.ndarray]] = {}
                for sym in unique_syms:
                    mask = symbols == sym
                    sym_data = {
                        "close": close_arr[mask],
                        "high": high_arr[mask],
                        "low": low_arr[mask],
                        "open": open_arr[mask],
                        "volume": volume_arr[mask],
                    }
                    if "funding_rate" in ohlcv:
                        sym_data["funding_rate"] = ohlcv["funding_rate"][mask]
                    if "open_interest" in ohlcv:
                        sym_data["open_interest"] = ohlcv["open_interest"][mask]
                    if "premium_index" in ohlcv:
                        sym_data["premium_index"] = ohlcv["premium_index"][mask]
                    multi_ohlcv[sym] = sym_data

                cs_features = compute_residual_momentum_group(
                    multi_ohlcv=multi_ohlcv, btc_symbol="BTCUSDT",
                )

                # cs_features values are (n_others, n_bars) — map to x_parts
                _other_symbols = [s for s in unique_syms if s != "BTCUSDT"]
                _cs_feat_names = sorted(cs_features.keys())
                for idx, sym in enumerate(_other_symbols):
                    if sym not in symbol_order:
                        continue
                    sym_pos = symbol_order[sym]
                    if sym_pos >= len(x_parts):
                        continue
                    for feat_name in _cs_feat_names:
                        feat_arr = cs_features[feat_name][idx]
                        _x_len = len(x_parts[sym_pos])
                        if len(feat_arr) >= _x_len:
                            x_parts[sym_pos] = np.column_stack([
                                x_parts[sym_pos], feat_arr[:_x_len]
                            ])
                        else:
                            padded = np.full(_x_len, np.nan)
                            padded[:len(feat_arr)] = feat_arr
                            x_parts[sym_pos] = np.column_stack([x_parts[sym_pos], padded])

                # Pad BTC with NaN columns for shape alignment
                if "BTCUSDT" in symbol_order and _cs_feat_names:
                    btc_pos = symbol_order["BTCUSDT"]
                    n_cols = len(_cs_feat_names)
                    x_parts[btc_pos] = np.column_stack([
                        x_parts[btc_pos],
                        np.full((len(x_parts[btc_pos]), n_cols), np.nan),
                    ])

                for feat_name in _cs_feat_names:
                    feat_names.append(f"cs_{feat_name}")

                if _cs_feat_names:
                    logger.info(
                        "Phase 2: %d cross-sectional features (%s) added to %d symbols",
                        len(_cs_feat_names), ",".join(_cs_feat_names), len(_other_symbols),
                   )
        except ImportError as e:
            logger.warning("Phase 2 features unavailable: %s", e)
        except Exception as e:
            logger.warning("Phase 2 features failed (non-fatal): %s", e)

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
    X = X.astype(np.float32)
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
# Cross-sectional rank normalization (vectorized)
# ---------------------------------------------------------------------------


def cross_sectional_rank_normalize(X: np.ndarray, ts: np.ndarray) -> np.ndarray:
    """Rank-normalize each feature column cross-sectionally per timestamp group.

    Converts raw feature values to percentile ranks [0, 1] across all symbols
    within each unique timestamp. Rows are assumed to be sorted by timestamp
    (contiguous groups — matching the output of build_aligned_training_frame).

    Timestamps with fewer than 3 symbols are left unchanged (not enough for
    meaningful cross-sectional ranking).

    Uses a grouped 2D argsort.argsort to avoid O(F) inner loops per group.
    """
    X_ranked = X.copy()
    _unique_ts, _counts = np.unique(ts, return_counts=True)
    _boundaries = np.cumsum(_counts[:-1])
    _groups = np.split(np.arange(len(ts), dtype=np.intp), _boundaries)

    _ranked_count = 0
    for _g in _groups:
        _n = len(_g)
        if _n >= 3:
            _sub = X[_g, :]  # (n_symbols, n_features) — vectorized 2D slice
            # Column-wise double argsort gives rank positions per feature
            _ranks = np.argsort(np.argsort(_sub, axis=0), axis=0).astype(np.float64)
            X_ranked[_g, :] = (_ranks + 0.5) / _n
            _ranked_count += 1

    logger.info(
        "Cross-sectional rank normalization: applied to %d/%d timestamp groups",
        _ranked_count, len(_unique_ts),
    )
    return X_ranked


# ---------------------------------------------------------------------------
# Walk-forward validation
# ---------------------------------------------------------------------------

def _select_nested_thresholds(
    fold_preds: list[np.ndarray],
    fold_y_class: list[np.ndarray],
    fold_y_val: list[np.ndarray],
    wfv_results: list[dict],
    action_net: np.ndarray,
    thresholds: list[float],
) -> tuple[list[float], float, list[dict]]:
    """Nested (leakage-free) per-fold threshold selection.

    For each fold k, selects threshold using only folds 0..k-1 data,
    evaluated by net expectancy R (not accuracy). Fold 0 gets the
    most conservative (highest) threshold.

    Returns:
        per_fold_choices: threshold selected per fold.
        final_threshold: median of per_fold_choices.
        per_fold_eval: list of per-fold evaluation dicts.
    """
    from alphaforge.reports.metrics import compute_oos_metrics

    per_fold_choices: list[float] = []
    per_fold_eval: list[dict] = []

    for k in range(len(fold_preds)):
        fr = wfv_results[k]
        fold_prob = fold_preds[k]
        fold_yc = fold_y_class[k]
        fold_yv = fold_y_val[k]
        vs = fr["effective_val_start"]
        ve = fr["val_end"]
        fold_anet = action_net[vs:ve]

        # Select threshold using prior folds only
        if k == 0:
            sel_thresh = thresholds[-1]  # Most conservative
        else:
            prior_probs = np.concatenate(fold_preds[:k])
            prior_yc = np.concatenate(fold_y_class[:k])
            prior_parts = [
                action_net[wfv_results[j]["effective_val_start"]:wfv_results[j]["val_end"]]
                for j in range(k)
            ]
            prior_anet = np.concatenate(prior_parts, axis=0)

            best_r, best_t = -999.0, thresholds[-1]
            for th in thresholds:
                y_adj = prior_yc.copy()
                lc = prior_probs < th
                y_adj[lc] = 2
                active = (~lc).sum()
                if active == 0:
                    continue
                adj_labels = np.array(
                    ["LONG_NOW" if p == 0 else "SHORT_NOW" if p == 1 else "NO_TRADE" for p in y_adj],
                    dtype=object,
                )
                adj_r = prior_anet[np.arange(len(y_adj)), y_adj]
                m = compute_oos_metrics(adj_labels.tolist(), adj_r.tolist(), fee_pct=0.0)
                nr = float(m.get("avg_net_R_per_active_trade", -999.0))
                if nr > best_r:
                    best_r, best_t = nr, th
            sel_thresh = best_t

        per_fold_choices.append(sel_thresh)

        # Evaluate on fold k
        y_eval = fold_yc.copy()
        lc_eval = fold_prob < sel_thresh
        y_eval[lc_eval] = 2
        active_count = int((~lc_eval).sum())
        no_trade_count = int(lc_eval.sum())
        total = len(y_eval)
        exposure = 100.0 * active_count / total if total else 0.0
        acc = float(np.mean(y_eval == fold_yv)) if total else 0.0

        eval_labels = np.array(
            ["LONG_NOW" if p == 0 else "SHORT_NOW" if p == 1 else "NO_TRADE" for p in y_eval],
            dtype=object,
        )
        eval_r = fold_anet[np.arange(len(y_eval)), y_eval]
        eval_metrics = compute_oos_metrics(eval_labels.tolist(), eval_r.tolist(), fee_pct=0.0)
        fold_net_r = float(eval_metrics.get("avg_net_R_per_active_trade", 0.0))

        per_fold_eval.append({
            "fold": k + 1,
            "threshold": sel_thresh,
            "accuracy": round(acc, 4),
            "net_expectancy_r": round(fold_net_r, 6),
            "active_trades": active_count,
            "no_trade_count": no_trade_count,
            "exposure_pct": round(exposure, 2),
        })

    final_threshold = float(np.median(per_fold_choices)) if per_fold_choices else thresholds[0]
    return per_fold_choices, final_threshold, per_fold_eval


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
    enable_debias: bool = False,
) -> List[dict] | tuple[list[dict], list[np.ndarray], list[np.ndarray], list[np.ndarray]]:
    """6-fold anchored expanding walk-forward validation.

    Args:
        X: Feature matrix.
        y_int: Integer labels (0=LONG, 1=SHORT, 2=NO_TRADE).
        net_r_values: Net R values per sample.
        mode: Trading mode.
        min_folds: Minimum number of folds (default 6).
        dump_softmax_path: Optional path to dump softmax probabilities.
        threshold: Confidence threshold for NO_TRADE filtering.
        action_net_r: Action-aligned net R (n_samples, 3).
        return_raw_preds: If True, return raw fold predictions for post-hoc analysis.
        enable_debias: If True, apply in-fold direction debias correction.
            Default False — the debias is statistically contaminated (it adapts
            to OOS data in-sample) and should only be enabled for retrospective
            analysis of its impact.

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
    # P0.9F: purge/embargo tied to label_horizon (the actual forward lookahead
    # of the label function — was previously bound to max_hold, which was wrong
    # because max_hold is the position-sizing horizon, not the label horizon).
    _wfv_cfg = _get_training_config(mode)
    label_horizon = _wfv_cfg.label_horizon
    k = 2  # HOLD: multiplier requires empirical calibration
    purge_bars = max(fold_size // 4, k * label_horizon)
    embargo_bars = max(fold_size // 8, k * label_horizon)

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

        assert effective_train_end <= train_end - label_horizon, (
            f"purge_bars={purge_bars} insufficient: train_end={train_end}, "
            f"effective_train_end={effective_train_end}, label_horizon={label_horizon}"
        )

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
        y_pred_prob = fold_result.model.inplace_predict(X_val)
        y_pred_prob_max = np.max(y_pred_prob, axis=1)
        y_pred = np.argmax(y_pred_prob, axis=1)

        # Direction debias: if model heavily over-predicts one direction,
        # apply a gentle correction. This fixes systematic bias from
        # imbalanced market regimes (e.g. too SHORT-biased in bull market).
        # NOTE: This is statistically contaminated — it uses the VAL fold's
        # own prediction distribution. Default OFF (enable_debias=False).
        if enable_debias:
            _long_pct = np.mean(y_pred == 0)
            _short_pct = np.mean(y_pred == 1)
            _bias = _long_pct - _short_pct
            if abs(_bias) > 0.20 and _long_pct + _short_pct > 0.10:
                _shift = -_bias * 0.15  # neutralize 15% of bias
                y_pred_prob[:, 0] += _shift
                y_pred_prob[:, 1] -= _shift
                y_pred_prob = np.clip(y_pred_prob, 0, 1)
                y_pred_prob /= y_pred_prob.sum(axis=1, keepdims=True)
                y_pred = np.argmax(y_pred_prob, axis=1)
                y_pred_prob_max = np.max(y_pred_prob, axis=1)
                logger.info(
                    "  Debias: LONG=%.0f%% SHORT=%.0f%% (shift=%.3f) -> LONG=%.0f%% SHORT=%.0f%%",
                    _long_pct * 100, _short_pct * 100, _shift,
                    np.mean(y_pred == 0) * 100, np.mean(y_pred == 1) * 100,
                )

        # Save raw preds for post-hoc threshold sweep (before threshold applied)
        if return_raw_preds:
            walk_forward_validate._fold_preds.append(y_pred_prob_max.copy())
            walk_forward_validate._fold_y_class.append(y_pred.copy())
            walk_forward_validate._fold_y_val.append(y_val.copy())

        # Apply confidence threshold: force NO_TRADE when model is uncertain
        _default_threshold = _get_training_config(mode).confidence_threshold
        _threshold = threshold if threshold is not None else float(_default_threshold)
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
        # pred_gross_r is ALREADY net of cost (deducted in label generator).
        # fee_pct=0.0 avoids double-counting.
        pred_metrics = compute_oos_metrics(pred_labels.tolist(), pred_gross_r.tolist(), fee_pct=0.0)

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
        oracle_metrics = compute_oos_metrics(true_labels.tolist(), true_gross_r.tolist(), fee_pct=0.0)
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
# Inter-fold consistency (n-fold avg_net_R consistency, NOT per-trade Sharpe)
# ---------------------------------------------------------------------------

def compute_inter_fold_consistency(wfv_results: List[dict]) -> float:
    """Compute inter-fold consistency from per-fold active-trade net R values.
    
    This is NOT a Sharpe ratio. It measures how consistent the per-fold
    average net R is across folds: mean(fold_avg_R) / std(fold_avg_R) * sqrt(n).
    A high value means all folds produced similar average R.
    A low value means fold outcomes were inconsistent.
    
    For real risk-adjusted return metrics, compute per-trade Sharpe from
    the trade-level R series instead.
    """
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
    consistency = mean_r / std_r * np.sqrt(len(r_exps))
    return round(float(consistency), 4)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def collect_metrics(
    wfv_results: List[dict],
    X: np.ndarray,
    feature_names: List[str],
    fee_pct: float = 0.0,
    route_cost_bps: float = 8.0,
    mode: str = "SCALP",
) -> dict:
    """Collect and aggregate training metrics."""
    val_accs = [r["val_accuracy"] for r in wfv_results]
    train_accs = [r["train_accuracy"] for r in wfv_results]

    accuracy = float(np.mean(val_accs)) if val_accs else 0.0
    train_accuracy = float(np.mean(train_accs)) if train_accs else 0.0
    stability = _compute_stability(val_accs)

    overfit = compute_overfit_gap(wfv_results)
    inter_fold_consistency = compute_inter_fold_consistency(wfv_results)
    round_trip_cost_r = 0.0  # fees already deducted in decision_gross_r

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
        _profit_factor = float(trade_metrics.get("profit_factor", 0.0))
        _min_trade_count = float(trade_metrics.get("min_trade_count", 0))
        _drawdown_guard = float(trade_metrics.get("max_drawdown_r", 0.0))
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
        _profit_factor = 0.0
        _min_trade_count = 0
        _drawdown_guard = 0.0

    # Confidence threshold metrics
    low_conf_counts = [r.get("low_conf_count", 0) for r in wfv_results]
    total_low_conf = sum(low_conf_counts)
    total_val_samples = sum(r["n_val"] for r in wfv_results)
    low_conf_rate = float(total_low_conf / total_val_samples * 100) if total_val_samples > 0 else 0.0

    # Cost decomposition
    round_trip_cost_bps = _AUTHORITY["round_trip_taker_fee_bps"]  # 8.0 bps

    return {
        "mode": mode.upper(),
        "accuracy": round(accuracy, 4),
        "train_accuracy": round(train_accuracy, 4),
        "accuracy_stability": round(stability, 4),
        "inter_fold_consistency": inter_fold_consistency,
        "net_expectancy_r": round(net_expectancy_r, 6),
        "gross_expectancy_r": round(gross_expectancy_r, 6),
        "total_gross_R": round(total_gross_r, 6),
        "total_net_R": round(total_net_r, 6),
        "profit_factor": _profit_factor,
        "min_trade_count": _min_trade_count,
        "drawdown_guard": _drawdown_guard,
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
        "confidence_threshold": _get_training_config(mode).confidence_threshold,
        "low_conf_rate_pct": round(low_conf_rate, 2),
        "cost_decomposition": {
            "fee_pct (already in decision_gross_r)": 0.0,
            "authority_round_trip_cost_bps": _AUTHORITY["round_trip_taker_fee_bps"],
            "round_trip_cost_r (in values)": 0.0,
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
    holdout_cutoff: str | None = None,
    precomputed_frame: dict | None = None,
    precomputed_wfv: tuple | None = None,
) -> None:
    """Run the discovery pipeline after training completes.

    Called when ``--discovery`` flag is set in the training CLI.
    When ``precomputed_frame`` and ``precomputed_wfv`` are provided (from
    the main training pipeline), discovery skips data loading, frame
    construction, NaN cleaning, and walk-forward validation — using the
    training pipeline's precomputed results instead.

    The precomputed frame is the RAW training frame (pre-rank-normalization,
    pre-NaN-fill) so that discovery's NaN-drop semantics are preserved.
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
        holdout_cutoff=holdout_cutoff,
    )

    result = run_discovery(
        config,
        precomputed_frame=precomputed_frame,
        precomputed_wfv=precomputed_wfv,
        ohlcv=ohlcv,
    )

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
    parser.add_argument("--holdout-cutoff", default=None,
                        help="ISO date (e.g. '2026-04-07') for 3-month holdout reservation. "
                             "Data AFTER this date is held out — model evaluated once, no retuning.")
    parser.add_argument("--prune-features", type=float, default=0.0,
                        help="Feature importance pruning threshold (0=disabled). "
                             "Features with gain below threshold are dropped before final training.")
    parser.add_argument("--passport", default=None,
                        help="Output path for EvidencePassport JSON (V7 handoff package).")
    parser.add_argument("--discovery", action="store_true",
                        help="Run full discovery pipeline after training (signal generation, "
                             "simulation backtest, profitability analysis, rejection evaluation)")
    parser.add_argument("--regression-objective", action="store_true",
                        help="Use reg:squarederror objective instead of multi:softprob. "
                             "Trains a regression model on net R instead of classification.")
    parser.add_argument("--discovery-confidence-threshold", type=float, default=0.55,
                        help="Confidence threshold for discovery signal generation (default: 0.55)")
    parser.add_argument("--discovery-output", default=None,
                        help="Output path for discovery pipeline results (default: auto-generated)")
    args = parser.parse_args()

    global mode
    mode = args.mode.upper()
    symbols = [s.strip().upper() for s in args.symbols.split(",")]
    _main_cfg = _get_training_config(mode)
    interval = _main_cfg.primary_interval

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
    if not args.synthetic:
        n_bars = len(ohlcv["close"])
        n_syms = len(set(str(s) for s in ohlcv.get("symbol", [])))
        if n_bars < 1000 or n_syms < 1:
            print(f"  ERROR: Real data too small ({n_bars} bars, {n_syms} symbols)")
            sys.exit(1)
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

    # Fill NaN with 0 — XGBoost treats 0 as a split value and also handles
    # missing via sparsity-aware algorithm. For financial features (z-scores,
    # ratios, returns), 0 means "neutral/no signal" which is a reasonable
    # default for NaN (insufficient lookback).
    nan_count = int(np.isnan(X).sum())
    X = np.nan_to_num(X, nan=0.0)
    print(f"  Filled {nan_count} NaN values with 0 — kept all {len(X)} rows")
    X_clean = X
    y_clean = y_int
    label_gross_clean = label_gross_r
    label_net_clean = label_net_r
    action_gross_clean = action_gross_r
    action_net_clean = action_net_r
    ts_clean = sample_timestamps
    sym_clean = sample_symbols

    # Cross-sectional rank normalization: convert each feature to percentile
    # ranks per timestamp across all symbols. Research shows +35% IC improvement.
    if len(sym_clean) > 0 and len(ts_clean) > 0:
        _unique_ts = np.unique(ts_clean)
        if len(_unique_ts) < len(ts_clean):  # multiple symbols per timestamp
            X_clean = cross_sectional_rank_normalize(X_clean, ts_clean)


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
        # Nested Threshold Sweep (leakage-free per-fold)
        thresholds = [float(t.strip()) for t in args.threshold_sweep.split(",")]
        thresholds = sorted(set(thresholds))
        print(f"\n{'='*70}")
        print(f"  NESTED THRESHOLD SWEEP — {len(thresholds)} thresholds")
        print(f"{'='*70}")

        wfv_results, fold_preds, fold_y_class, fold_y_val = walk_forward_validate(
            X_clean, y_clean, label_net_clean, mode, min_folds=args.folds,
            action_net_r=action_net_clean,
            return_raw_preds=True,
        )

        per_fold_choices, final_threshold, per_fold_eval = _select_nested_thresholds(
            fold_preds, fold_y_class, fold_y_val, wfv_results,
            action_net_clean, thresholds,
        )

        print("{:<6s}  {:<10s}  {:<10s}  {:<12s}  {:<8s}  {:<10s}".format(
            "Fold", "Threshold", "Fold Acc", "Fold NetR", "Active", "Exposure"
        ))
        print(f"{'-'*70}")
        for ev in per_fold_eval:
            print(f"{ev['fold']:<6d}  {ev['threshold']:<10.2f}  {ev['accuracy']:<10.4f}  "
                  f"{ev['net_expectancy_r']:<12.6f}  {ev['active_trades']:<8d}  {ev['exposure_pct']:<9.2f}%")
        print(f"{'-'*70}")
        print(f"  Per-fold thresholds: {[f'{t:.2f}' for t in per_fold_choices]}")
        print(f"  Final threshold (median): {final_threshold:.2f}")
        print(f"  NOTE: k=2 purge/embargo multiplier is HOLD — empirical calibration pending.")
        print(f"{'='*70}\n")
    else:
        print(f"\n[4/6] Walk-forward validation ({args.folds} folds, anchored expanding)...")
        t0 = time.time()
        _need_raw_preds = args.discovery
        if _need_raw_preds:
            wfv_results, fold_preds, fold_y_class, fold_y_val = walk_forward_validate(
                X_clean, y_clean, label_net_clean, mode, min_folds=args.folds,
                action_net_r=action_net_clean,
                return_raw_preds=True,
            )
        else:
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

    _obj = "reg:squarederror" if args.regression_objective else "multi:softprob"
    final_trainer = XGBoostTrainer(mode=mode, objective=_obj)
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

    # Feature importance pruning (Issue #268)
    _pruned = False
    if args.prune_features > 0 and feat_names and imp:
        _keep = [n for n, v in imp.items() if v >= args.prune_features]
        _drop = len(feat_names) - len(_keep)
        if _drop > 0 and _keep:
            _keep_set = set(_keep)
            _keep_idx = [i for i, n in enumerate(feat_names) if n in _keep_set]
            X_clean = X_clean[:, _keep_idx]
            feat_names = [feat_names[i] for i in _keep_idx]
            print(f"  Feature pruning (threshold={args.prune_features}): "
                  f"dropped {_drop}/{len(imp)}, kept {len(_keep)}")
            # Retrain with pruned features
            _obj = "reg:squarederror" if args.regression_objective else "multi:softprob"
            final_trainer = XGBoostTrainer(mode=mode, objective=_obj)
            final_result = final_trainer.train(X_clean, y_clean)
            final_acc = float(final_result.val_metrics.get("accuracy", 0))
            print(f"  Retrained (pruned) model accuracy: {final_acc:.4f}")
            _pruned = True
        elif _drop == 0:
            print(f"  Feature pruning: all {len(feat_names)} features above threshold "
                  f"{args.prune_features} — no pruning needed")
    elif args.prune_features > 0 and not imp:
        print(f"  Feature pruning requested but no importance values available — skipping")

    # Step 6: Collect metrics
    print("\n[6/6] Collecting metrics...")
    metrics = collect_metrics(wfv_results, X_clean, feat_names)

    print(f"\n{'='*60}")
    print(f"  TRAINING RESULTS â€” {mode}")
    print(f"{'='*60}")
    print(f"  Accuracy (OOS):              {metrics['accuracy']:.4f}")
    print(f"  Train Accuracy:              {metrics['train_accuracy']:.4f}")
    print(f"  Accuracy Stability:          {metrics['accuracy_stability']:.4f}")
    print(f"  Inter-fold consistency:    {metrics['inter_fold_consistency']:.4f}")
    print(f"  Overfit Gap:                 {metrics['overfit_gap']:.4f}")
    print(f"  Train-OOS Correlation:       {metrics['train_oos_correlation']:.4f}")
    print(f"  PBO Risk:                    {metrics['pbo_risk']}")
    print(f"  Net Expectancy R (per active trade): {metrics['net_expectancy_r']:.6f}")
    print(f"  Feature Count:               {metrics['feature_count']}")
    print(f"  Total Samples:               {metrics['n_samples']}")
    print(f"  Walk-Forward Folds:          {metrics['n_folds']}")
    print(f"  Active Trades:               {metrics['total_active_trades']}")
    print(f"  LONG / SHORT / NO_TRADE:     {metrics['total_long']} / {metrics['total_short']} / {metrics['total_no_trade']}")
    print(f"  Exposure %:                  {metrics['exposure_pct']:.1f}%")
    print(f"  Confidence Threshold:        {metrics['confidence_threshold']}")
    print(f"  Low Confidence Rate:         {metrics['low_conf_rate_pct']:.1f}%")
    cd = metrics['cost_decomposition']
    print(f"  Authority round-trip cost: {cd['authority_round_trip_cost_bps']:.0f} bps (already in decision_gross_r)")
    print(f"{'='*60}\n")

    # Build EvidencePassport if requested (Issue #183)
    if args.passport:
        try:
            from dataclasses import asdict
            from alphaforge.evidence_adapter import build_alphaforge_passport
            _labels_list = y_clean.tolist() if isinstance(y_clean, np.ndarray) else list(y_clean)
            _gross_list = (label_gross_clean.tolist() if isinstance(label_gross_clean, np.ndarray)
                           else list(label_gross_clean))
            wfv_data = {
                "metrics": metrics,
                "per_fold_results": wfv_results,
                "candidate_id": f"{mode.lower()}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
                "labels": _labels_list,
                "gross_r": _gross_list,
                "fee_pct": _ROUND_TRIP_COST_FRACTIONAL,
                "feature_names": feat_names,
            }
            passport = build_alphaforge_passport(wfv_data, mode)
            pp_path = Path(args.passport)
            pp_path.parent.mkdir(parents=True, exist_ok=True)
            with open(pp_path, "w") as f:
                json.dump(asdict(passport), f, indent=2, default=str)
            print(f"  EvidencePassport saved: {pp_path.resolve()}")
        except (ImportError, AttributeError, TypeError, OSError, json.JSONDecodeError) as e:
            logger.warning("Could not build EvidencePassport: %s", e)

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
        _wfv_tuple = None
        if _need_raw_preds:
            _wfv_tuple = (wfv_results, fold_preds, fold_y_class, fold_y_val)
        _run_discovery_after_training(
            mode=mode,
            ohlcv=ohlcv,
            feature_groups=feature_groups,
            folds=args.folds,
            confidence_threshold=args.discovery_confidence_threshold,
            output=args.discovery_output,
            holdout_cutoff=args.holdout_cutoff,
            precomputed_frame=training_frame,
            precomputed_wfv=_wfv_tuple,
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
        "inter_fold_consistency": metrics["inter_fold_consistency"],
        "overfit_gap": metrics["overfit_gap"],
        "feature_count": metrics["feature_count"],
    }, indent=2))

