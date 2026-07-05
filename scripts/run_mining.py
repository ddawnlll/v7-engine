#!/usr/bin/env python3
"""Run AlphaForge mining pipeline on real Binance data.

Pipeline: parquet load → KlineRecord → simulation (triple-barrier) → CandidateOutcomeDataset → mining

Usage:
    PYTHONPATH=alphaforge/src:. .venv/bin/python3 scripts/run_mining.py --mode SCALP --symbols BTCUSDT,ETHUSDT,SOLUSDT --intervals 1h
    PYTHONPATH=alphaforge/src:. .venv/bin/python3 scripts/run_mining.py --mode SCALP --full --levels 1,2
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import math
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

try:
    from numba import njit
except ImportError:
    njit = lambda f: f

# Ensure repo root is on path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "alphaforge" / "src"))

from lib.market_data.contracts import KlineRecord
from simulation.contracts.models import (
    ActionOutcome,
    NoTradeOutcome,
    PathMetrics,
    SimulationLineage,
    SimulationOutput,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_mining")

# ---------------------------------------------------------------------------
# SCALP mode config
# ---------------------------------------------------------------------------

MODE_CONFIG = {
    "SWING": {
        "primary": "4h", "max_hold": 30, "stop_mult": 2.0, "target_mult": 3.0,
        "context": "1d", "refinement": "1h",
    },
    "SCALP": {
        "primary": "1h", "max_hold": 12, "stop_mult": 1.5, "target_mult": 2.0,
        "context": "4h", "refinement": "15m",
    },
    "AGGRESSIVE_SCALP": {
        "primary": "15m", "max_hold": 5, "stop_mult": 1.5, "target_mult": 2.0,
        "context": "1h", "refinement": "5m",
    },
}

# Full 20-symbol universe
FULL_UNIVERSE = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "SOLUSDT", "DOTUSDT", "MATICUSDT", "AVAXUSDT", "UNIUSDT",
    "LINKUSDT", "ATOMUSDT", "LTCUSDT", "DOGEUSDT",
    "FILUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT", "NEARUSDT",
]

# Symbols we have 15m data for (SCALP uses 15m refinement)
SCALP_SYMBOLS_15M = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "SOLUSDT", "DOTUSDT", "MATICUSDT", "AVAXUSDT", "UNIUSDT",
    "LINKUSDT", "ATOMUSDT", "LTCUSDT", "DOGEUSDT",
    "APTUSDT", "ARBUSDT", "OPUSDT", "NEARUSDT",
]


# ---------------------------------------------------------------------------
# Data loading from parquet
# ---------------------------------------------------------------------------

def load_symbol_data(
    symbol: str, interval: str, data_dir: str = "data_lake"
) -> List[KlineRecord]:
    """Load all parquet data for a symbol/interval into KlineRecords."""
    raw_dir = Path(data_dir) / "raw" / "binance" / "um" / "klines" / symbol / interval
    if not raw_dir.exists():
        logger.warning("No data for %s/%s at %s", symbol, interval, raw_dir)
        return []

    records: List[KlineRecord] = []
    for year_dir in sorted(raw_dir.iterdir()):
        if not year_dir.is_dir():
            continue
        for pq_file in sorted(year_dir.glob("*.parquet")):
            try:
                table = pq.read_table(str(pq_file))
                n = table.num_rows
                cols = set(table.column_names)

                # Schema-adaptive: handle two column naming conventions
                ts_col = "timestamp" if "timestamp" in cols else "open_time"
                trade_col = "trade_count" if "trade_count" in cols else "trades"
                taker_vol_col = "taker_buy_base_volume" if "taker_buy_base_volume" in cols else "taker_buy_volume"

                open_times = table.column(ts_col).to_pylist()
                opens = table.column("open").to_pylist()
                highs = table.column("high").to_pylist()
                lows = table.column("low").to_pylist()
                closes = table.column("close").to_pylist()
                volumes = table.column("volume").to_pylist()
                quote_volumes = table.column("quote_volume").to_pylist()
                trade_counts = table.column(trade_col).to_pylist() if trade_col in cols else [0] * n
                taker_buy_vols = table.column(taker_vol_col).to_pylist() if taker_vol_col in cols else [0.0] * n
                taker_buy_qvols = table.column("taker_buy_quote_volume").to_pylist() if "taker_buy_quote_volume" in cols else [0.0] * n

                for i in range(n):
                    records.append(KlineRecord(
                        symbol=symbol,
                        timestamp=int(open_times[i]),
                        open=float(opens[i]),
                        high=float(highs[i]),
                        low=float(lows[i]),
                        close=float(closes[i]),
                        volume=float(volumes[i]),
                        quote_volume=float(quote_volumes[i]),
                        trade_count=int(trade_counts[i]),
                        taker_buy_volume=float(taker_buy_vols[i]),
                        taker_buy_quote_volume=float(taker_buy_qvols[i]),
                        interval=interval,
                        source="binance",
                        is_closed=True,
                    ))
            except Exception as e:
                logger.warning("Error reading %s: %s", pq_file, e)

    records.sort(key=lambda r: r.timestamp)
    logger.info("Loaded %d bars for %s/%s", len(records), symbol, interval)
    return records


# ---------------------------------------------------------------------------
# Triple-barrier simulation (per-symbol, per-interval)
# ---------------------------------------------------------------------------

def _default_lineage() -> SimulationLineage:
    """Return a default SimulationLineage for mining-originated outputs."""
    return SimulationLineage(
        simulation_family_version="mining-v1.0",
        simulation_profile_version="mining",
        cost_model_version="mining-v1.0",
        fee_model_version="mining-v1.0",
        slippage_model_version="mining-v1.0",
        funding_model_version="mining-v1.0",
        horizon_family="triple_barrier",
        stop_family="atr_multiplicative",
        target_family="atr_multiplicative",
        time_exit_family="max_hold",
        adapter_kind="mining",
    )


def _build_outcome(
    gross_r: float, entry_price: float, stop_dist: float,
    target_dist: float, max_hold: int, mode: str,
    path_highs: np.ndarray, path_lows: np.ndarray,
    exit_reason: str, hold_bars: int,
) -> ActionOutcome:
    """Build an ActionOutcome dataclass from simulation results."""
    cost_r = gross_r * 0.08 if gross_r != 0.0 else 0.0  # approximate fee
    net_r = gross_r - cost_r

    mfe = float(np.max(path_highs) - entry_price) if len(path_highs) > 0 else 0.0
    mae = float(entry_price - np.min(path_lows)) if len(path_lows) > 0 else 0.0
    mfe_r = mfe / entry_price if entry_price > 0 else 0.0
    mae_r = mae / entry_price if entry_price > 0 else 0.0

    path_metrics = PathMetrics(
        mfe=mfe, mae=mae,
        mfe_r=mfe_r, mae_r=mae_r,
        time_to_mfe=0, time_to_mae=0,
        path_quality_score=0.0,
        path_quality_bucket="unknown",
    )

    return ActionOutcome(
        action="LONG" if gross_r > 0 else "SHORT",
        realized_r_gross=gross_r,
        realized_r_net=net_r,
        fee_cost_r=cost_r,
        slippage_cost_r=0.0,
        funding_cost_r=0.0,
        total_cost_r=cost_r,
        exit_reason=exit_reason,
        exit_price=entry_price + gross_r * entry_price,
        exit_bar_index=hold_bars,
        hold_duration_bars=hold_bars,
        action_utility=net_r,
        path_metrics=path_metrics,
        same_candle_ambiguity=False,
    )


def _build_no_trade_outcome() -> NoTradeOutcome:
    """Build a NoTradeOutcome (zero utility)."""
    return NoTradeOutcome(
        saved_loss_r=0.0,
        saved_loss_score=0.0,
        missed_opportunity_r=0.0,
        missed_opportunity_score=0.0,
        no_trade_quality="neutral",
        was_correct_skip=True,
    )


# ---------------------------------------------------------------------------
# Pure-numpy vectorized indicator helpers (no lib.indicators dependency)
# ---------------------------------------------------------------------------

@njit
def _np_rolling_max(arr, w):
    n = len(arr)
    out = np.empty(n)
    out[:w-1] = np.nan
    for i in range(w - 1, n):
        mx = arr[i - w + 1]
        for j in range(i - w + 2, i + 1):
            if arr[j] > mx:
                mx = arr[j]
        out[i] = mx
    return out


@njit
def _np_rolling_min(arr, w):
    n = len(arr)
    out = np.empty(n)
    out[:w-1] = np.nan
    for i in range(w - 1, n):
        mn = arr[i - w + 1]
        for j in range(i - w + 2, i + 1):
            if arr[j] < mn:
                mn = arr[j]
        out[i] = mn
    return out


@njit
def _compute_vol_pct(atr_pct, window):
    n = len(atr_pct)
    out = np.full(n, 50.0)
    for i in range(window, n):
        count = 0
        less = 0
        for j in range(i - window + 1, i + 1):
            if not np.isnan(atr_pct[j]):
                count += 1
                if atr_pct[j] <= atr_pct[i]:
                    less += 1
        if count >= 5 and not np.isnan(atr_pct[i]):
            out[i] = less / count * 100.0
    return out


@njit
def _compute_mom_rank(mom_raw, volatility_window, momentum_period):
    n = len(mom_raw)
    out = np.full(n, 0.5)
    start = momentum_period + volatility_window
    for i in range(start, n):
        count = 0
        mn = 1e18
        mx = -1e18
        for j in range(i - volatility_window + 1, i + 1):
            if not np.isnan(mom_raw[j]):
                count += 1
                if mom_raw[j] < mn:
                    mn = mom_raw[j]
                if mom_raw[j] > mx:
                    mx = mom_raw[j]
        if count >= 3 and mx > mn:
            out[i] = (mom_raw[i] - mn) / (mx - mn)
    return out


@njit
def _compute_vol_z(volumes, window):
    n = len(volumes)
    out = np.zeros(n)
    for i in range(window, n):
        s = 0.0
        for j in range(i - window + 1, i + 1):
            s += volumes[j]
        mean = s / window
        var = 0.0
        for j in range(i - window + 1, i + 1):
            var += (volumes[j] - mean) ** 2
        std = np.sqrt(var / window)
        if std > 1e-14:
            out[i] = (volumes[i] - mean) / std
    return out


@njit
def _compute_slope(closes, lookback):
    n = len(closes)
    out = np.full(n, np.nan)
    x = np.arange(lookback, dtype=np.float64)
    xm = np.mean(x)
    xc = x - xm
    den = np.sum(xc ** 2)
    if den > 0:
        for i in range(lookback - 1, n):
            y = closes[i - lookback + 1: i + 1]
            ym = np.mean(y)
            out[i] = np.sum((y - ym) * xc) / den
    return out


@njit
def _compute_pullback_dist(closes, rolling_high_closes, rolling_high_highs, rolling_low_lows, atr_raw, window):
    n = len(closes)
    pullback = np.zeros(n)
    dist_range = np.full(n, 0.5)
    for i in range(window, n):
        if not np.isnan(atr_raw[i]) and atr_raw[i] > 0 and not np.isnan(rolling_high_closes[i]):
            if rolling_high_closes[i] > closes[i]:
                pullback[i] = (rolling_high_closes[i] - closes[i]) / atr_raw[i]
        if not np.isnan(rolling_high_highs[i]) and not np.isnan(rolling_low_lows[i]):
            if rolling_high_highs[i] > rolling_low_lows[i]:
                dist_range[i] = (closes[i] - rolling_low_lows[i]) / (rolling_high_highs[i] - rolling_low_lows[i])
    return pullback, dist_range


def _np_sma(arr: np.ndarray, period: int) -> np.ndarray:
    """Vectorized SMA using cumulative sum."""
    n = len(arr)
    out = np.full(n, np.nan)
    cs = np.cumsum(arr)
    out[period - 1:] = (cs[period - 1:] - np.concatenate([[0.0], cs[:n - period]])) / period
    return out


def _np_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    """Vectorized ATR with exponential smoothing."""
    n = len(closes)
    tr = np.zeros(n)
    tr[0] = highs[0] - lows[0]
    tr[1:] = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])),
    )
    atr = np.full(n, np.nan)
    if n >= period:
        atr[period - 1] = np.mean(tr[:period])
        for i in range(period, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def _np_momentum(closes: np.ndarray, period: int = 10) -> np.ndarray:
    """Vectorized momentum = (close - close[n]) / close[n]."""
    n = len(closes)
    mom = np.full(n, np.nan)
    valid = closes[period:] > 0
    mom[period:][valid] = (closes[period:][valid] - closes[:n - period][valid]) / closes[:n - period][valid]
    return mom


def simulate_trades(
    records: List[KlineRecord], mode: str
) -> List[SimulationOutput]:
    """Run triple-barrier simulation on raw kline data.

    Precomputes all features once per symbol, then generates candidates.
    Subsamples every 4th bar to keep dataset manageable (~7K per symbol).
    """
    cfg = MODE_CONFIG[mode]
    max_hold = cfg["max_hold"]
    stop_mult = cfg["stop_mult"]
    target_mult = cfg["target_mult"]

    n = len(records)
    if n < 60:
        return []

    fee_pct = 0.04
    round_trip_cost_r = fee_pct * 2 / 100.0

    closes = np.array([r.close for r in records], dtype=np.float64)
    highs = np.array([r.high for r in records], dtype=np.float64)
    lows = np.array([r.low for r in records], dtype=np.float64)
    volumes = np.array([r.volume for r in records], dtype=np.float64)

    # Vectorized ATR for stop/target sizing
    atr_raw = np.full(n, np.nan, dtype=np.float64)
    tr = np.maximum(highs[1:] - lows[1:], np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])))
    atr_raw[1:] = np.convolve(tr, np.ones(14)/14, mode='full')[:n-1]

    sim_outputs = []
    lookback = 50
    lineage = _default_lineage()
    step = 4  # subsample: every 4th bar
    candidate_count = len(range(lookback, n - max_hold - 1, step))
    logger.info("  simulate_trades: %d candidate bars (n=%d, step=%d)", candidate_count, n, step)
    processed = 0
    last_log = time.time()

    for i in range(lookback, n - max_hold - 1, step):
        if np.isnan(atr_raw[i]) or atr_raw[i] <= 0 or atr_raw[i] > closes[i] * 0.5:
            continue

        entry_price = closes[i]
        stop_dist = atr_raw[i] * stop_mult
        target_dist = atr_raw[i] * target_mult

        # Simulate LONG
        long_gross = 0.0
        long_exit = "TIMEOUT"
        long_hold = max_hold
        for j in range(1, min(max_hold + 1, n - i)):
            if lows[i + j] <= entry_price - stop_dist:
                long_gross = -stop_dist / entry_price
                long_exit = "STOP_HIT"
                long_hold = j
                break
            if highs[i + j] >= entry_price + target_dist:
                long_gross = target_dist / entry_price
                long_exit = "TARGET_HIT"
                long_hold = j
                break
            long_gross = (closes[i + j] - entry_price) / entry_price

        # Simulate SHORT
        short_gross = 0.0
        short_exit = "TIMEOUT"
        short_hold = max_hold
        for j in range(1, min(max_hold + 1, n - i)):
            if highs[i + j] >= entry_price + stop_dist:
                short_gross = -stop_dist / entry_price
                short_exit = "STOP_HIT"
                short_hold = j
                break
            if lows[i + j] <= entry_price - target_dist:
                short_gross = target_dist / entry_price
                short_exit = "TARGET_HIT"
                short_hold = j
                break
            short_gross = (entry_price - closes[i + j]) / entry_price

        net_long = long_gross - round_trip_cost_r
        net_short = short_gross - round_trip_cost_r

        # Always pick the best direction, even if both are negative.
        # Losing trades provide the negative examples needed for realistic mining.
        if net_long > net_short:
            best_action = "LONG_NOW"
        elif net_short > net_long:
            best_action = "SHORT_NOW"
        else:
            best_action = "NO_TRADE"

        long_path_highs = highs[i + 1: i + 1 + long_hold]
        long_path_lows = lows[i + 1: i + 1 + long_hold]
        short_path_highs = highs[i + 1: i + 1 + short_hold]
        short_path_lows = lows[i + 1: i + 1 + short_hold]

        long_outcome = _build_outcome(
            long_gross, entry_price, stop_dist, target_dist, max_hold, mode,
            long_path_highs, long_path_lows, long_exit, long_hold,
        )
        short_outcome = _build_outcome(
            short_gross, entry_price, stop_dist, target_dist, max_hold, mode,
            short_path_highs, short_path_lows, short_exit, short_hold,
        )

        from datetime import datetime, timezone
        ts_ms = records[i].timestamp
        ts_iso = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()

        sim_outputs.append(SimulationOutput(
            simulation_run_id=f"mining_{records[i].symbol}_{mode}",
            symbol=records[i].symbol,
            decision_timestamp=ts_iso,
            mode=mode,
            primary_interval=records[i].interval,
            resolution_status="RESOLVED",
            long_outcome=long_outcome,
            short_outcome=short_outcome,
            no_trade_outcome=_build_no_trade_outcome(),
            best_action=best_action,
            action_gap_r=abs(net_long - net_short),
            regret_r=0.0,
            is_ambiguous=(best_action == "NO_TRADE"),
            lineage=lineage,
            second_best_action="SHORT_NOW" if best_action == "LONG_NOW" else "LONG_NOW",
            invalidity_reason="",
            monte_carlo_run_id="",
            monte_carlo_family_version="",
        ))

        processed += 1
        now = time.time()
        if processed % 500 == 0 or (now - last_log) > 30.0:
            logger.info("  simulate_trades: %d/%d candidates processed, %d outputs so far",
                        processed, candidate_count, len(sim_outputs))
            last_log = now

    logger.info("  simulate_trades done: %d candidates processed → %d outputs", processed, len(sim_outputs))
    return sim_outputs


def _simulate_symbol_worker(task: tuple) -> Tuple[str, str, int, List[SimulationOutput]]:
    """Module-level worker for ProcessPoolExecutor: run simulate_trades on one task.

    Task tuple: (symbol, interval, records, mode, idx, total_syms)
    Returns: (symbol, interval, output_count, simulation_outputs)
    """
    sym, interval, records, mode, sym_idx, total_syms = task
    logger.info("  [%d/%d] Simulating %s/%s (%d bars)...",
                sym_idx + 1, total_syms, sym, interval, len(records))
    sim_outs = simulate_trades(records, mode)
    return sym, interval, len(sim_outs), sim_outs


# ---------------------------------------------------------------------------
# Build CandidateOutcomeDataset
# ---------------------------------------------------------------------------

def build_candidate_dataset(
    sim_outputs: List[SimulationOutput],
    market_data_map: Dict[str, List[KlineRecord]],
    btc_market_data: Optional[List[KlineRecord]] = None,
    lookback_bars: int = 50,
    watchdog: Optional["_WatchdogTimer"] = None,
) -> pa.Table:
    """Build a CandidateOutcomeDataset by precomputing features per symbol.

    Uses pure-numpy vectorized helpers — no lib.indicators.rolling dependency.
    Precomputes features once per symbol, then indexes at each candidate point.

    Args:
        watchdog: Optional watchdog timer to feed during long loops.
    """
    def _wd_feed() -> None:
        if watchdog is not None:
            watchdog.feed()
    SMA_PERIOD = 50
    ATR_PERIOD = 14
    MOMENTUM_PERIOD = 10
    VOLUME_WINDOW = 20
    VOLATILITY_WINDOW = 20
    RANGE_WINDOW = 20
    SLOPE_LOOKBACK = 10

    # Precompute features per symbol
    symbol_features: Dict[str, Dict[str, np.ndarray]] = {}
    symbol_ts: Dict[str, np.ndarray] = {}
    total_syms = len(market_data_map)

    for sym_idx, (sym, records) in enumerate(market_data_map.items(), 1):
        logger.info("  Precomputing features for %s (%d/%d), %d bars...",
                    sym, sym_idx, total_syms, len(records))
        _wd_feed()
        if len(records) < lookback_bars:
            logger.info("    Skipped: %d bars < lookback_bars=%d", len(records), lookback_bars)
            continue
        n = len(records)
        closes = np.array([r.close for r in records], dtype=np.float64)
        highs = np.array([r.high for r in records], dtype=np.float64)
        lows = np.array([r.low for r in records], dtype=np.float64)
        volumes = np.array([r.volume for r in records], dtype=np.float64)
        timestamps = np.array([r.timestamp for r in records], dtype=np.int64)

        # ATR — pure numpy
        atr_raw = _np_atr(highs, lows, closes, ATR_PERIOD)
        atr_pct = np.where((~np.isnan(atr_raw)) & (closes > 0), atr_raw / closes * 100.0, np.nan)

        # SMA50 — vectorized cumulative sum
        sma50 = _np_sma(closes, SMA_PERIOD)

        # Linear slope (10-bar) — numba vectorized
        slope = _compute_slope(closes, SLOPE_LOOKBACK)
        _wd_feed()

        # Regime — vectorized masks
        regime = np.full(n, "range", dtype="U10")
        mask_up = (~np.isnan(sma50)) & (~np.isnan(slope)) & (closes > sma50 * 1.005) & (slope > 0)
        mask_down = (~np.isnan(sma50)) & (~np.isnan(slope)) & (closes < sma50 * 0.995) & (slope < 0)
        regime[mask_up] = "up"
        regime[mask_down] = "down"

        # Volatility percentile — numba vectorized
        vol_pct = _compute_vol_pct(atr_pct, VOLATILITY_WINDOW)

        # Momentum rank — numba vectorized
        mom_raw = _np_momentum(closes, MOMENTUM_PERIOD)
        mom_rank = _compute_mom_rank(mom_raw, VOLATILITY_WINDOW, MOMENTUM_PERIOD)

        # Volume zscore — numba vectorized
        vol_z = _compute_vol_z(volumes, VOLUME_WINDOW)

        # Pullback ATR + distance to range high — numba vectorized
        rolling_high_closes = _np_rolling_max(closes, RANGE_WINDOW)
        rolling_high_highs = _np_rolling_max(highs, RANGE_WINDOW)
        rolling_low_lows = _np_rolling_min(lows, RANGE_WINDOW)
        pullback, dist_range = _compute_pullback_dist(
            closes, rolling_high_closes, rolling_high_highs, rolling_low_lows, atr_raw, RANGE_WINDOW
        )

        btc_regime = np.full(n, "range", dtype="U10")

        # Returns (1-bar forward) for BTC-relative and cross-sectional features
        returns_1 = np.full(n, np.nan)
        returns_1[:-1] = (closes[1:] - closes[:-1]) / closes[:-1]

        symbol_features[sym] = {
            "regime_trend": regime,
            "volatility_percentile": vol_pct,
            "momentum_rank": mom_rank,
            "volume_zscore": vol_z,
            "atr_pct": atr_pct,
            "pullback_atr": pullback,
            "distance_to_range_high": dist_range,
            "spread_proxy": np.zeros(n),
            "funding_context": np.zeros(n),
            "returns_1": returns_1,
        }
        symbol_ts[sym] = timestamps
        logger.info("    %s features done (%d bars)", sym, n)
        _wd_feed()

    # ------------------------------------------------------------------
    # Cross-sectional features: rank each symbol vs peers at same timestamp
    # ------------------------------------------------------------------
    logger.info("  Computing cross-sectional features...")
    cs_features: Dict[str, np.ndarray] = {}  # cs_momentum, cs_volume, cs_atr
    for sym in symbol_features:
        n_sym = len(symbol_features[sym]["momentum_rank"])
        cs_features[sym] = {}
        for cs_name in ["cs_momentum", "cs_volume", "cs_atr"]:
            cs_features[sym][cs_name] = np.full(n_sym, 0.5)
    symbol_features_by_sym = {sym: feats for sym, feats in symbol_features.items()}
    symbol_ts_by_sym = {sym: ts for sym, ts in symbol_ts.items()}
    _wd_feed()

    # Collect all (timestamp, sym, index) tuples for alignment
    ts_sym_idx = []
    for sym in symbol_features:
        ts_arr = symbol_ts[sym]
        for i in range(len(ts_arr)):
            ts_sym_idx.append((ts_arr[i], sym, i))
    ts_sym_idx.sort(key=lambda x: x[0])

    # For each timestamp, compute cross-sectional ranks
    # Group by timestamp in a single pass
    cs_sources = {
        "cs_momentum": "momentum_rank",
        "cs_volume": "volume_zscore",
        "cs_atr": "atr_pct",
    }
    i = 0
    total_ts = len(ts_sym_idx)
    while i < total_ts:
        ts = ts_sym_idx[i][0]
        # Collect all symbols at this timestamp
        group = []
        while i < total_ts and ts_sym_idx[i][0] == ts:
            group.append(ts_sym_idx[i])
            i += 1
        if len(group) < 3:
            continue  # need multiple symbols for cross-sectional comparison
        for cs_name, src_name in cs_sources.items():
            vals = []
            members = []
            for _, sym, idx in group:
                feats = symbol_features_by_sym.get(sym)
                if feats is None:
                    continue
                v = feats[src_name][idx]
                if not np.isnan(v):
                    vals.append(v)
                    members.append((sym, idx))
            if len(vals) < 3:
                continue
            vals_arr = np.array(vals)
            # Percentile rank within this timestamp group
            ranks = np.searchsorted(np.sort(vals_arr), vals_arr) / len(vals_arr)
            for rank_val, (sym, idx) in zip(ranks, members):
                cs_features[sym][cs_name][idx] = float(rank_val)
        _wd_feed()

    # Attach cross-sectional features to symbol_features
    for sym in symbol_features:
        for cs_name in ["cs_momentum", "cs_volume", "cs_atr"]:
            symbol_features[sym][cs_name] = cs_features[sym][cs_name]
    logger.info("  Cross-sectional features computed")
    _wd_feed()

    # Compute BTC regime across all symbols
    logger.info("  Computing BTC regime mapping for %d symbols...", len(symbol_features))
    if btc_market_data and len(btc_market_data) > SMA_PERIOD:
        btc_n = len(btc_market_data)
        btc_closes = np.array([r.close for r in btc_market_data], dtype=np.float64)
        btc_sma = _np_sma(btc_closes, SMA_PERIOD)
        btc_sl = np.full(btc_n, np.nan)
        x = np.arange(SLOPE_LOOKBACK, dtype=np.float64); xm = np.mean(x); xc = x - xm; den = np.sum(xc**2)
        if den > 0:
            for i in range(SLOPE_LOOKBACK - 1, btc_n):
                y = btc_closes[i - SLOPE_LOOKBACK + 1: i + 1]
                btc_sl[i] = np.sum((y - np.mean(y)) * xc) / den
        btc_regime_arr = np.full(btc_n, "range", dtype="U10")
        btc_mask_up = (~np.isnan(btc_sma)) & (~np.isnan(btc_sl)) & (btc_closes > btc_sma * 1.005) & (btc_sl > 0)
        btc_mask_down = (~np.isnan(btc_sma)) & (~np.isnan(btc_sl)) & (btc_closes < btc_sma * 0.995) & (btc_sl < 0)
        btc_regime_arr[btc_mask_up] = "up"
        btc_regime_arr[btc_mask_down] = "down"
        btc_ts = np.array([r.timestamp for r in btc_market_data], dtype=np.int64)
        for sym in symbol_features:
            sym_ts = symbol_ts[sym]
            btc_r = np.full(len(sym_ts), "range", dtype="U10")
            for idx, ts in enumerate(sym_ts):
                pos = np.searchsorted(btc_ts, ts)
                if pos < btc_n:
                    btc_r[idx] = btc_regime_arr[pos]
            symbol_features[sym]["btc_regime"] = btc_r
    else:
        for sym in symbol_features:
            symbol_features[sym]["btc_regime"] = np.full(len(symbol_ts[sym]), "range", dtype="U10")

    # Build rows from sim_outputs
    logger.info("  Building rows from %d simulation outputs...", len(sim_outputs))
    rows = []
    _last_row_log = time.time()
    for _row_idx, sim in enumerate(sim_outputs):
        sym = sim.symbol
        if sym not in symbol_features:
            continue
        feats = symbol_features[sym]
        ts_arr = symbol_ts[sym]

        # Find index by binary search
        ts_ms = int(sim.decision_timestamp[:19].replace("-", "").replace("T", "").replace(":", ""))  # hack
        # Use timestamp from simulation_run_id to find the bar
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(sim.decision_timestamp)
        ts_target = int(dt.timestamp() * 1000)
        pos = np.searchsorted(ts_arr, ts_target)
        if pos >= len(ts_arr) or pos < lookback_bars:
            continue

        if sim.best_action == "NO_TRADE":
            continue  # skip NO_TRADE for mining -- no actionable trade signal
        outcome = sim.long_outcome if sim.best_action == "LONG_NOW" else sim.short_outcome
        # Now includes losing trades (negative net_R) since best_action picks best of
        # LONG/SHORT even when both are negative -- needed for realistic win_rate.

        side = "LONG" if sim.best_action == "LONG_NOW" else "SHORT"

        # Feature interactions
        regime_dir = 1.0 if str(feats["regime_trend"][pos]) == "up" else (-1.0 if str(feats["regime_trend"][pos]) == "down" else 0.0)
        atr_val = float(feats["atr_pct"][pos]) if not np.isnan(feats["atr_pct"][pos]) else 0.0
        mom_val = float(feats["momentum_rank"][pos])
        pb_val = float(feats["pullback_atr"][pos])

        rows.append({
            "symbol": sym,
            "timestamp": int(ts_arr[pos]),
            "side": side,
            "mode": sim.mode,
            "timeframe": sim.primary_interval,
            "regime_trend": str(feats["regime_trend"][pos]),
            "volatility_percentile": float(feats["volatility_percentile"][pos]),
            "momentum_rank": mom_val,
            "volume_zscore": float(feats["volume_zscore"][pos]),
            "atr_pct": atr_val,
            "btc_regime": str(feats["btc_regime"][pos]),
            "pullback_atr": pb_val,
            "distance_to_range_high": float(feats["distance_to_range_high"][pos]),
            "spread_proxy": float(feats["spread_proxy"][pos]),
            "funding_context": float(feats["funding_context"][pos]),
            # Cross-sectional features (symbol rank vs peers at same timestamp)
            "cs_momentum": float(feats.get("cs_momentum", np.full(1, 0.5))[pos]),
            "cs_volume": float(feats.get("cs_volume", np.full(1, 0.5))[pos]),
            "cs_atr": float(feats.get("cs_atr", np.full(1, 0.5))[pos]),
            # Feature interactions (capture non-linear regime effects)
            "atr_x_regime": atr_val * regime_dir,
            "mom_x_pullback": mom_val * pb_val,
            "net_R": float(outcome.realized_r_net),
            "gross_R": float(outcome.realized_r_gross),
            "cost_R": float(outcome.total_cost_r),
            "mfe_R": float(outcome.path_metrics.mfe_r),
            "mae_R": float(outcome.path_metrics.mae_r),
            "exit_reason": str(outcome.exit_reason),
            "hold_duration": int(outcome.hold_duration_bars),
            "simulation_run_id": str(sim.simulation_run_id),
            "candidate_id": f"{sim.simulation_run_id}_{sym}_{pos}",
        })

        if (_row_idx + 1) % 1000 == 0:
            _now = time.time()
            logger.info("  Row building: %d/%d processed, %d rows kept (%.1fs since last)",
                        _row_idx + 1, len(sim_outputs), len(rows), _now - _last_row_log)
            _last_row_log = _now

    logger.info("  Row building done: %d sim outputs → %d rows", len(sim_outputs), len(rows))

    if not rows:
        logger.warning("No valid rows produced from %d sim outputs", len(sim_outputs))
        return pa.Table.from_pydict({k: [] for k in [
            "symbol", "timestamp", "side", "mode", "timeframe",
            "regime_trend", "volatility_percentile", "momentum_rank", "volume_zscore",
            "atr_pct", "btc_regime", "pullback_atr", "distance_to_range_high",
            "spread_proxy", "funding_context",
            "cs_momentum", "cs_volume", "cs_atr",
            "atr_x_regime", "mom_x_pullback",
            "net_R", "gross_R", "cost_R", "mfe_R", "mae_R",
            "exit_reason", "hold_duration", "simulation_run_id", "candidate_id",
        ]})

    schema = pa.schema([
        pa.field("symbol", pa.string()), pa.field("timestamp", pa.int64()),
        pa.field("side", pa.string()), pa.field("mode", pa.string()),
        pa.field("timeframe", pa.string()),
        pa.field("regime_trend", pa.string()), pa.field("volatility_percentile", pa.float64()),
        pa.field("momentum_rank", pa.float64()), pa.field("volume_zscore", pa.float64()),
        pa.field("atr_pct", pa.float64()), pa.field("btc_regime", pa.string()),
        pa.field("pullback_atr", pa.float64()), pa.field("distance_to_range_high", pa.float64()),
        pa.field("spread_proxy", pa.float64()), pa.field("funding_context", pa.float64()),
        pa.field("cs_momentum", pa.float64()), pa.field("cs_volume", pa.float64()),
        pa.field("cs_atr", pa.float64()),
        pa.field("atr_x_regime", pa.float64()), pa.field("mom_x_pullback", pa.float64()),
        pa.field("net_R", pa.float64()), pa.field("gross_R", pa.float64()),
        pa.field("cost_R", pa.float64()), pa.field("mfe_R", pa.float64()),
        pa.field("mae_R", pa.float64()), pa.field("exit_reason", pa.string()),
        pa.field("hold_duration", pa.int64()),
        pa.field("simulation_run_id", pa.string()), pa.field("candidate_id", pa.string()),
    ])

    table = pa.Table.from_pylist(rows, schema=schema)
    return table.cast(schema)


# ---------------------------------------------------------------------------
# Mining pipeline
# ---------------------------------------------------------------------------

def run_mining_pipeline(
    table: "pa.Table",
    output_dir: str,
    levels: List[int] = [1, 2],
    min_support: int = 50,
    top_k: int = 200,
) -> Dict[str, Any]:
    """Run the full mining pipeline on a CandidateOutcomeDataset."""
    from alphaforge.mine.bucketizer import FeatureBucketizer
    from alphaforge.mine.bitset_engine import BitsetEngine
    from alphaforge.mine.rule_scorer import RuleScorer
    from alphaforge.mine.multi_testing import MultiTestingCorrector
    from alphaforge.mine.oos_validator import OOSValidator

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    start = time.time()
    summary = {
        "status": "running",
        "total_candidates": table.num_rows,
        "levels": levels,
        "min_support": min_support,
        "steps_completed": [],
        "results": {},
    }

    # Step 1: Bucketize features
    logger.info("Step 1: Bucketizing features...")
    feature_cols = [
        "volatility_percentile", "momentum_rank", "volume_zscore",
        "atr_pct", "pullback_atr", "distance_to_range_high",
        "cs_momentum", "cs_volume", "cs_atr",
        "atr_x_regime", "mom_x_pullback",
    ]
    bucketizer = FeatureBucketizer()
    bucketizer.fit(table, feature_cols)
    masks = bucketizer.transform(table)
    condition_registry = [
        c for c in bucketizer.get_condition_registry()
        if c.get("support_count", 0) >= min_support
    ]
    summary["total_conditions"] = len(condition_registry)
    summary["steps_completed"].append("bucketize")
    logger.info("  Conditions: %d (min_support=%d)", len(condition_registry), min_support)

    # Step 2: Extract target
    target = table.column("net_R").to_numpy().astype("float64")

    # Step 3: Mine rules
    engine = BitsetEngine(min_support=min_support / max(1, len(target)))
    level1 = []
    level2 = []

    if 1 in levels:
        logger.info("Step 2: Level 1 — single condition scan...")
        level1 = engine.level1_scan(masks, target)
        level1 = sorted(level1, key=lambda r: r.get("mean_net_R", 0), reverse=True)[:top_k]
        summary["results"]["level1_count"] = len(level1)
        summary["steps_completed"].append("level1")
        logger.info("  Level 1: %d rules", len(level1))

    if 2 in levels:
        logger.info("Step 3: Level 2 — pair condition scan...")
        level2 = engine.level2_scan(masks, target, top_n=top_k)
        summary["results"]["level2_count"] = len(level2)
        summary["steps_completed"].append("level2")
        logger.info("  Level 2: %d rules", len(level2))

    # Combine rules
    all_rules = level1 + level2
    # Deduplicate
    seen = set()
    unique_rules = []
    for r in all_rules:
        sig = str(sorted(r.get("conditions", [])))
        if sig not in seen:
            seen.add(sig)
            unique_rules.append(r)
    all_rules = unique_rules
    summary["total_rules_discovered"] = len(all_rules)
    logger.info("  Unique rules: %d", len(all_rules))

    if not all_rules:
        summary["status"] = "no_rules_found"
        summary["elapsed_seconds"] = round(time.time() - start, 2)
        return summary

    # Step 4: Score rules
    logger.info("Step 4: Scoring %d rules...", len(all_rules))
    scorer = RuleScorer()
    symbol_map = table.column("symbol").to_numpy() if "symbol" in table.column_names else None
    regime_map = table.column("regime_trend").to_numpy() if "regime_trend" in table.column_names else None
    if symbol_map is not None:
        symbol_map = symbol_map.astype(str)
    if regime_map is not None:
        regime_map = regime_map.astype(str)
    # Build per-rule boolean masks from bucketizer masks (AND conditions)
    per_rule_masks = []
    for rule in all_rules:
        conds = rule.get("conditions", [])
        combined = None
        for c in conds:
            if c in masks and len(masks[c]) == len(target):
                combined = masks[c] if combined is None else (combined & masks[c])
        if combined is not None:
            per_rule_masks.append({"combined": combined})
        else:
            per_rule_masks.append(masks)  # fallback to full set
    scored_rules = scorer.score_batch(all_rules, per_rule_masks, target, symbol_map, regime_map)
    # Re-attach conditions from original rules (scorer drops them)
    for i, sr in enumerate(scored_rules):
        if i < len(all_rules):
            sr["conditions"] = all_rules[i].get("conditions", [])
            sr["support"] = all_rules[i].get("support", 0)
            sr["lift"] = all_rules[i].get("lift", 0.0)
    # Add p_value from Sharpe ratio via t-distribution
    try:
        from scipy import stats as sp_stats
        _has_scipy = True
    except ImportError:
        _has_scipy = False
    for r in scored_rules:
        sharpe = r.get("sharpe", 0.0)
        n_obs = r.get("n_observations", r.get("support", 1))
        if n_obs > 2:
            t_stat = sharpe * math.sqrt(n_obs)
            if _has_scipy:
                r["p_value"] = float(sp_stats.t.sf(abs(t_stat), df=n_obs - 1) * 2)
            else:
                r["p_value"] = max(0.0, min(1.0, 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t_stat) / math.sqrt(2))))))
        else:
            r["p_value"] = 1.0
    summary["steps_completed"].append("score")
    logger.info("  Scored %d rules", len(scored_rules))

    # Step 5: Multi-testing correction
    logger.info("Step 5: Multi-testing correction (FDR)...")
    corrector = MultiTestingCorrector()
    corrected_rules = corrector.correct(scored_rules, method="fdr")
    passes = [r for r in corrected_rules if r.get("passes_correction", True)]
    summary["results"]["passes_correction"] = len(passes)
    summary["results"]["fails_correction"] = len(corrected_rules) - len(passes)
    summary["steps_completed"].append("mtc")
    logger.info("  Passes MTC: %d / %d", len(passes), len(corrected_rules))

    # Step 6: Temporal consistency check (bucket-condition rules)
    logger.info("Step 6: Temporal consistency check...")
    try:
        # Build rule masks for OOS
        n_total = len(target)
        n_disc = int(n_total * 0.6)
        n_valid = int(n_total * 0.2)
        disc_idx = slice(0, n_disc)
        valid_idx = slice(n_disc, n_disc + n_valid)
        hold_idx = slice(n_disc + n_valid, n_total)

        oos_ratios = []
        val_survived = 0
        hold_survived = 0
        for rule in passes:
            conds = rule.get("conditions", [])
            combined = None
            for c in conds:
                if c in masks and len(masks[c]) == n_total:
                    combined = masks[c] if combined is None else (combined & masks[c])
            if combined is None or len(combined) != n_total:
                continue
            # Slice BOTH target and mask together to avoid dimension mismatch
            is_mean = float(np.nanmean(target[disc_idx][combined[disc_idx]]))
            val_mean = float(np.nanmean(target[valid_idx][combined[valid_idx]]))
            hold_mean = float(np.nanmean(target[hold_idx][combined[hold_idx]]))
            if is_mean > 0 and val_mean > 0.0:
                val_ratio = val_mean / is_mean
                oos_ratios.append(val_ratio)
                if val_ratio >= 0.5:
                    val_survived += 1
                    if hold_mean > 0.0 and hold_mean / is_mean >= 0.5:
                        hold_survived += 1
        cs = float(np.min(oos_ratios)) if oos_ratios else 0.0
        summary["results"]["oos"] = {
            "consistency_score": round(cs, 4),
            "survived_validation": val_survived,
            "survived_holdout": hold_survived,
            "overfit_warning": f"Consistency score {cs:.4f} is below threshold 0.5. OOS substantially lags IS." if cs < 0.5 else None,
        }
        logger.info("  OOS: consistency=%.4f, survived_val=%d/%d, survived_hold=%d/%d",
                      cs, val_survived, len(passes), hold_survived, len(passes))
    except Exception as e:
        logger.warning("Temporal consistency check failed: %s", e)
        summary["results"]["oos"] = {"error": str(e)}
    summary["steps_completed"].append("oos")

    # Export top rules as JSON
    logger.info("Step 7: Exporting top rules...")
    export_path = output_path / "top_rules.json"
    top_rules = passes[:min(50, len(passes))]
    with open(export_path, "w") as f:
        json.dump(top_rules, f, indent=2, default=str)
    summary["results"]["exported_specs"] = len(top_rules)
    summary["steps_completed"].append("export")
    logger.info("  Exported %d rules to %s", len(top_rules), export_path)

    # Write summary
    elapsed = time.time() - start
    summary["elapsed_seconds"] = round(elapsed, 2)
    summary["status"] = "complete"
    summary["output_dir"] = str(output_path)

    summary_path = output_path / "mining_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)

    logger.info("Pipeline complete in %.1f seconds — %d rules discovered", elapsed, len(all_rules))

    return summary


# ---------------------------------------------------------------------------
# Watchdog timer — aborts if no output for too long
# ---------------------------------------------------------------------------

class _WatchdogTimer:
    """Watchdog: fires a callback if no heartbeat for `timeout` seconds.

    Call ``feed()`` after every meaningful progress event.  If the main
    thread stops calling ``feed()`` for longer than ``timeout`` seconds,
    the callback is invoked (typically ``sys.exit(1)``).

    Usage::

        wd = _WatchdogTimer(timeout=120, label="Phase 3")
        wd.start()
        for item in items:
            process(item)
            wd.feed()          # reset the countdown
        wd.stop()
    """

    def __init__(self, timeout: float = 120.0, label: str = "") -> None:
        self._timeout = timeout
        self._label = label
        self._last_feed = 0.0
        self._timer: Optional[threading.Timer] = None
        self._stopped = False

    # -- lifecycle --

    def start(self) -> None:
        self._last_feed = time.time()
        self._stopped = False
        self._schedule()

    def stop(self) -> None:
        self._stopped = True
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def feed(self) -> None:
        """Reset the countdown."""
        self._last_feed = time.time()

    # -- internal --

    def _schedule(self) -> None:
        if self._stopped:
            return
        self._timer = threading.Timer(self._timeout, self._check)
        self._timer.daemon = True
        self._timer.start()

    def _check(self) -> None:
        if self._stopped:
            return
        elapsed = time.time() - self._last_feed
        if elapsed >= self._timeout:
            logger.error(
                "⏰ TIMEOUT after %.0fs with no progress in %s — aborting.",
                elapsed, self._label or "(unlabeled)",
            )
            logger.error("   To increase timeout, pass --watchdog-timeout SECONDS.")
            os._exit(1)  # hard exit — cleanup may be stuck
        else:
            self._schedule()


# ---------------------------------------------------------------------------
# Top rules report
# ---------------------------------------------------------------------------

def print_top_rules(rules: list, n: int = 20):
    """Print the top N rules by mean_net_R."""
    print(f"\n{'='*80}")
    print(f"TOP {min(n, len(rules))} RULES BY MEAN NET_R")
    print(f"{'='*80}")
    for i, r in enumerate(rules[:n]):
        conds = r.get("conditions", [])
        cond_str = " AND ".join(str(c) for c in conds) if conds else "no conditions"
        print(f"\n  [{i+1}] mean_net_R={r.get('mean_net_R', 0):.4f}  "
              f"win_rate={r.get('win_rate', 0):.1%}  "
              f"support={r.get('support', 0)}  "
              f"lift={r.get('lift', 0):.2f}")
        print(f"      Conditions: {cond_str}")
        if "sharpe" in r:
            print(f"      Sharpe={r.get('sharpe', 0):.2f}  "
                  f"profit_factor={r.get('profit_factor', 0):.2f}  "
                  f"median_net_R={r.get('median_net_R', 0):.4f}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run AlphaForge mining on real data")
    parser.add_argument("--mode", default="SCALP", choices=["SCALP", "SWING", "AGGRESSIVE_SCALP"])
    parser.add_argument("--symbols", default=None, help="Comma-separated symbols (default: full universe)")
    parser.add_argument("--intervals", default=None, help="Comma-separated intervals (default: mode primary)")
    parser.add_argument("--data-dir", default="data_lake")
    parser.add_argument("--output", default="reports/alphaforge/mining")
    parser.add_argument("--levels", default="1,2", help="Mining levels (1,2,3)")
    parser.add_argument("--min-support", type=int, default=50)
    parser.add_argument("--top-k", type=int, default=200)
    parser.add_argument("--full", action="store_true", help="Use full 20-symbol universe")
    parser.add_argument("--smoke", action="store_true", help="Quick smoke test (3 symbols, 1 interval)")
    parser.add_argument("--watchdog-timeout", type=int, default=120,
                        help="Seconds of silence before abort (default: 120)")
    args = parser.parse_args()

    cfg = MODE_CONFIG[args.mode]
    levels = [int(l) for l in args.levels.split(",")]

    # Select symbols
    if args.smoke:
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        intervals = [cfg["primary"]]
    elif args.full:
        symbols = FULL_UNIVERSE
        intervals = [cfg["primary"]]
    elif args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",")]
        intervals = [i.strip() for i in args.intervals.split(",")] if args.intervals else [cfg["primary"]]
    else:
        symbols = FULL_UNIVERSE
        intervals = [cfg["primary"]]

    print(f"\n{'='*60}")
    print(f"ALPHAFORGE MINING — {args.mode}")
    print(f"{'='*60}")
    print(f"  Symbols:   {len(symbols)} ({', '.join(symbols[:5])}{'...' if len(symbols) > 5 else ''})")
    print(f"  Intervals: {intervals}")
    print(f"  Levels:    {levels}")
    print(f"  Min support: {args.min_support}")
    print(f"  Output:    {args.output}")
    print()

    # Phase 1: Load data
    logger.info("=== Phase 1: Loading market data ===")
    t0 = time.time()
    all_records: Dict[str, List[KlineRecord]] = {}
    btc_records: Optional[List[KlineRecord]] = None
    wd = _WatchdogTimer(timeout=args.watchdog_timeout, label="Phase 1: Load")
    wd.start()

    for sym_idx, sym in enumerate(symbols):
        for interval in intervals:
            records = load_symbol_data(sym, interval, args.data_dir)
            if records:
                all_records[f"{sym}_{interval}"] = records
                if sym == "BTCUSDT" and interval == cfg["primary"]:
                    btc_records = records
            wd.feed()
        logger.info("  Loaded %d symbols so far...", sym_idx + 1)

    wd.stop()
    total_bars = sum(len(r) for r in all_records.values())
    logger.info("Loaded %d total bars across %d symbol/interval combos in %.1fs",
                total_bars, len(all_records), time.time() - t0)

    if total_bars == 0:
        logger.error("No data loaded — aborting")
        return 1

    # Phase 2: Run simulations (parallel per symbol/interval)
    logger.info("\n=== Phase 2: Running triple-barrier simulations ===")
    t0 = time.time()
    all_sim_outputs = []
    market_data_map: Dict[str, List[KlineRecord]] = {}
    wd = _WatchdogTimer(timeout=args.watchdog_timeout, label="Phase 2: Simulate")
    wd.start()

    # Collect independent simulation tasks
    sim_tasks = []
    for sym_idx, sym in enumerate(symbols):
        for interval in intervals:
            key = f"{sym}_{interval}"
            records = all_records.get(key, [])
            if not records:
                continue
            if interval == cfg["primary"]:
                market_data_map[sym] = records
            wd.feed()
            sim_tasks.append((sym, interval, records, args.mode, sym_idx, len(symbols)))

    total_tasks = len(sim_tasks)
    logger.info("  Queued %d simulation tasks across %d symbols", total_tasks, len(symbols))

    max_workers = min(os.cpu_count() or 4, total_tasks)
    logger.info("  Using %d workers for %d tasks", max_workers, total_tasks)

    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_simulate_symbol_worker, t): t for t in sim_tasks}
        for future in concurrent.futures.as_completed(futures):
            wd.feed()
            sym, interval, count, sim_outs = future.result()
            all_sim_outputs.extend(sim_outs)
            logger.info("  Completed %s/%s: %d outputs (%.1fs elapsed)",
                        sym, interval, count, time.time() - t0)

    wd.stop()
    logger.info("Total simulation outputs: %d (in %.1fs)", len(all_sim_outputs), time.time() - t0)

    if not all_sim_outputs:
        logger.error("No simulation outputs — aborting")
        return 1

    # Phase 3: Build CandidateOutcomeDataset
    logger.info("\n=== Phase 3: Building CandidateOutcomeDataset ===")
    t0 = time.time()
    wd = _WatchdogTimer(timeout=args.watchdog_timeout, label="Phase 3: Build Dataset")
    wd.start()
    wd.feed()  # initial heartbeat
    table = build_candidate_dataset(
        all_sim_outputs,
        market_data_map,
        btc_market_data=btc_records,
        lookback_bars=50,
        watchdog=wd,
    )
    wd.feed()  # heartbeat after completion
    wd.stop()
    logger.info("Candidate dataset: %d rows, %d columns (in %.1fs)",
                table.num_rows, len(table.column_names), time.time() - t0)

    if table.num_rows == 0:
        logger.error("Empty candidate dataset — aborting")
        return 1

    # Save the dataset
    ds_path = Path(args.output) / "candidate_dataset.parquet"
    ds_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, str(ds_path))
    logger.info("Saved candidate dataset to %s", ds_path)

    # Phase 4: Run mining
    logger.info("\n=== Phase 4: Running mining pipeline ===")
    summary = run_mining_pipeline(
        table,
        output_dir=args.output,
        levels=levels,
        min_support=args.min_support,
        top_k=args.top_k,
    )

    # Print results
    print(f"\n{'='*60}")
    print(f"MINING RESULTS — {args.mode}")
    print(f"{'='*60}")
    print(f"  Status:     {summary['status']}")
    print(f"  Candidates: {summary['total_candidates']}")
    print(f"  Conditions: {summary.get('total_conditions', 0)}")
    print(f"  Rules:      {summary.get('total_rules_discovered', 0)}")
    if "results" in summary:
        for k, v in summary["results"].items():
            if isinstance(v, dict):
                print(f"  {k}: {json.dumps(v, indent=4)}")
            else:
                print(f"  {k}: {v}")
    print(f"  Elapsed:    {summary.get('elapsed_seconds', 0):.1f}s")
    print(f"  Output:     {summary.get('output_dir', 'N/A')}")

    if summary["status"] == "complete":
        print(f"\n✅ Mining complete!")
    elif summary["status"] == "no_rules_found":
        print(f"\n⚠️  No rules met minimum criteria")
    else:
        print(f"\n❌ Mining failed")

    return 0 if summary["status"] in ("complete", "no_rules_found") else 1


if __name__ == "__main__":
    sys.exit(main())
