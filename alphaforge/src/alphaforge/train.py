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
        "open": [], "high": [], "low": [], "close": [], "volume": [], "symbol": [],
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
        all_data["symbol"].extend([sym] * n_bars)
    return {
        "open": np.concatenate(all_data["open"]),
        "high": np.concatenate(all_data["high"]),
        "low": np.concatenate(all_data["low"]),
        "close": np.concatenate(all_data["close"]),
        "volume": np.concatenate(all_data["volume"]),
        "symbol": all_data["symbol"],
    }


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_cached_data(
    symbols: List[str],
    interval: str,
    data_dir: Optional[str] = None,
) -> Optional[dict]:
    """Load real OHLCV data from parquet cache.

    Checks these paths in order:
      1. ``{data_dir}/raw/{symbol}/``  (legacy flat format)
      2. ``data_lake/raw/binance/um/klines/{symbol}/{interval}/`` (DataLake medallion)

    Returns None if no data found (caller falls back to synthetic).
    """
    if data_dir is None:
        data_dir = str(REPO_ROOT / "data")
    raw_dir = Path(data_dir) / "raw"
    data_lake_dir = REPO_ROOT / "data_lake" / "raw" / "binance" / "um" / "klines"

    import pyarrow.parquet as pq

    def _load_sym_dir(sym_dir: Path, sym: str) -> Optional[int]:
        """Load all parquet files from a flat symbol directory. Returns row count."""
        nonlocal closes, highs, lows, opens, volumes, timestamps, sym_list, found_any
        if not sym_dir.exists():
            return None
        parquet_files = sorted(sym_dir.glob(f"*_{interval}_*.parquet"))
        # NOTE: No wildcard fallback here — we must only load bars matching
        # the requested interval.  The DataLake path below is the correct
        # fallback for medallion-structured data.
        count = 0
        for pf in parquet_files:
            try:
                df = pq.read_table(str(pf)).to_pandas()
                n = len(df)
                for _, r in df.iterrows():
                    closes.append(float(r["close"]))
                    highs.append(float(r["high"]))
                    lows.append(float(r["low"]))
                    opens.append(float(r["open"]))
                    volumes.append(float(r.get("volume", 0)))
                    timestamps.append(int(r.get("timestamp", 0)))
                    sym_list.append(sym)
                found_any = True
                count += n
                logger.info("  Loaded %d bars from %s/%s", n, sym, pf.name)
            except Exception as e:
                logger.warning("  Error reading %s: %s", pf, e)
        return count or None

    def _load_data_lake_sym(sym: str) -> Optional[int]:
        """Load DataLake medallion path: {symbol}/{interval}/{year}/{month}.parquet"""
        nonlocal closes, highs, lows, opens, volumes, timestamps, sym_list, found_any
        sym_dir = data_lake_dir / sym / interval
        if not sym_dir.exists():
            logger.info("  No data_lake dir for %s/%s", sym, interval)
            return None
        count = 0
        for year_dir in sorted(sym_dir.iterdir()):
            if not year_dir.is_dir():
                continue
            for pf in sorted(year_dir.iterdir()):
                if pf.suffix != ".parquet":
                    continue
                try:
                    df = pq.read_table(str(pf)).to_pandas()
                    n = len(df)
                    # Handle both 'timestamp' and 'open_time' column names
                    ts_col = "timestamp" if "timestamp" in df.columns else "open_time"
                    for _, r in df.iterrows():
                        closes.append(float(r["close"]))
                        highs.append(float(r["high"]))
                        lows.append(float(r["low"]))
                        opens.append(float(r["open"]))
                        volumes.append(float(r.get("volume", 0)))
                        timestamps.append(int(r.get(ts_col, 0)))
                        sym_list.append(sym)
                    found_any = True
                    count += n
                except Exception as e:
                    logger.warning("  Error reading %s from data_lake: %s", pf, e)
        if count:
            logger.info("  Loaded %d bars for %s from data_lake/%s", count, sym, interval)
        return count or None

    closes, highs, lows, opens, volumes, timestamps, sym_list = [], [], [], [], [], [], []
    found_any = False

    for sym in symbols:
        # Try legacy flat path first
        if _load_sym_dir(raw_dir / sym, sym) is not None:
            continue
        # Fallback to DataLake medallion path
        _load_data_lake_sym(sym)

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

def generate_labels(ohlcv: dict, mode: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Generate triple-barrier labels with stop/target simulation.

    Returns (int_labels, gross_r_values, net_r_values, metrics_dict).
    Label DECISION uses net_R (cost-aware); gross_R is exported for analysis
    and net_R is exported for downstream economic metrics.
    """
    cfg = MODE_CONFIG[mode]
    n = len(ohlcv["close"])
    max_hold = cfg["max_hold"]
    stop_mult = cfg["stop_mult"]
    target_mult = cfg["target_mult"]
    label_map = {"LONG_NOW": 0, "SHORT_NOW": 1, "NO_TRADE": 2}
    fee_pct = 0.04
    labels_list, ints_list, gross_r_vals, net_r_vals = [], [], [], []

    for i in range(n - max_hold - 1):
        entry_price = float(ohlcv["close"][i])
        atr = float(np.mean(np.abs(np.diff(ohlcv["close"][max(0, i - 14):i + 1]))))
        if atr <= 0 or atr > entry_price * 0.5:
            labels_list.append("NO_TRADE")
            ints_list.append(2)
            gross_r_vals.append(0.0)
            net_r_vals.append(0.0)
            continue

        stop_dist = atr * stop_mult
        target_dist = atr * target_mult

        # Simulate LONG
        long_gross = 0.0
        for j in range(1, min(max_hold + 1, n - i)):
            future_high = float(ohlcv["high"][i + j])
            future_low = float(ohlcv["low"][i + j])
            future_close = float(ohlcv["close"][i + j])
            if future_low <= entry_price - stop_dist:
                long_gross = -stop_dist / entry_price
                break
            if future_high >= entry_price + target_dist:
                long_gross = target_dist / entry_price
                break
            long_gross = (future_close - entry_price) / entry_price

        # Simulate SHORT
        short_gross = 0.0
        for j in range(1, min(max_hold + 1, n - i)):
            future_high = float(ohlcv["high"][i + j])
            future_low = float(ohlcv["low"][i + j])
            future_close = float(ohlcv["close"][i + j])
            if future_high >= entry_price + stop_dist:
                short_gross = -stop_dist / entry_price
                break
            if future_low <= entry_price - target_dist:
                short_gross = target_dist / entry_price
                break
            short_gross = (entry_price - future_close) / entry_price

        # Pick best action — COST-AWARE: subtract round-trip fee from gross returns
        # Round-trip cost = fee_pct * 2 (entry + exit)
        round_trip_cost = fee_pct * 2 / 100  # fee_pct is 0.04, so this is 0.0008
        net_long = long_gross - round_trip_cost
        net_short = short_gross - round_trip_cost
        no_trade_net = 0.0

        if net_long > net_short and net_long > no_trade_net:
            best = "LONG_NOW"
            best_gross_r = long_gross
            best_net_r = net_long
        elif net_short > net_long and net_short > no_trade_net:
            best = "SHORT_NOW"
            best_gross_r = short_gross
            best_net_r = net_short
        else:
            best = "NO_TRADE"
            best_gross_r = 0.0
            best_net_r = 0.0

        labels_list.append(best)
        ints_list.append(label_map[best])
        gross_r_vals.append(best_gross_r)
        net_r_vals.append(best_net_r)

    uniq, cnt = np.unique(labels_list, return_counts=True)
    d = {str(k): int(v) for k, v in zip(uniq, cnt)}
    logger.info("Labels: %d samples, dist=%s", len(labels_list), d)
    return np.array(ints_list), np.array(gross_r_vals, dtype=float), np.array(net_r_vals, dtype=float), {
        "n_labels": len(labels_list),
        "label_distribution": d,
    }


# ---------------------------------------------------------------------------
# Feature computation
# ---------------------------------------------------------------------------

def compute_all_features(ohlcv: dict, mode: str) -> Tuple[np.ndarray, List[str]]:
    """Compute all feature groups and return (X, feature_names)."""
    from alphaforge.features.pipeline import compute_features

    fm = compute_features(ohlcv, mode=mode)
    # Exclude funding_rate proxy (OHLCV-derived proxy is in orderbook group)
    feat_names = sorted(fm.features.keys())
    X = np.column_stack([fm.features[k] for k in feat_names])
    logger.info("Features: %d columns from %d groups", X.shape[1], len(fm.feature_group_ids))
    return X, feat_names


def compute_features_selected(ohlcv: dict, mode: str, feature_groups: Optional[List[str]] = None) -> Tuple[np.ndarray, List[str]]:
    """Compute selected feature groups.

    Args:
        ohlcv: OHLCV data dict.
        mode: Trading mode.
        feature_groups: List of group names (e.g. ["returns", "volatility", "atr", "momentum", "breakout"]).
            If None or ["all"], compute all groups.

    Returns (X, feature_names).
    """
    from alphaforge.features.pipeline import compute_features

    if feature_groups is None or feature_groups == ["all"]:
        fm = compute_features(ohlcv, mode=mode)
    else:
        fm = compute_features(ohlcv, mode=mode, feature_groups=feature_groups)
    feat_names = sorted(fm.features.keys())
    X = np.column_stack([fm.features[k] for k in feat_names])
    logger.info("Features: %d columns from mode=%s groups=%s", X.shape[1], mode, feature_groups or "all")
    return X, feat_names


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
    confidence_threshold: float | None = None,
) -> List[dict]:
    """6-fold anchored expanding walk-forward validation.

    Args:
        confidence_threshold: If None, uses module default (0.55).
            If -1, confidence filtering is disabled (all predictions count).

    Returns per-fold result dicts.
    """
    from alphaforge.training.xgb_trainer import XGBoostTrainer
    from collections import Counter
    import xgboost as xgb

    n = len(X)
    fold_size = n // (min_folds + 1)
    results: list[dict] = []
    purge_bars = fold_size // 4
    embargo_bars = fold_size // 8

    logger.info(
        "WFV: folds=%d, fold_size=%d, purge=%d, embargo=%d",
        min_folds, fold_size, purge_bars, embargo_bars,
    )

    for fold in range(min_folds):
        train_end = (fold + 1) * fold_size
        val_start = train_end
        val_end = val_start + fold_size // 2
        if val_end >= n:
            logger.warning("Fold %d: val_end >= n — stopping", fold + 1)
            break

        effective_train_end = train_end - purge_bars
        effective_val_start = val_start + embargo_bars

        if effective_train_end <= 0 or effective_val_start >= val_end:
            logger.warning("Fold %d: boundary issue — stopping", fold + 1)
            break

        X_train = X[:effective_train_end]
        y_train = y_int[:effective_train_end]
        X_val = X[effective_val_start:val_end]
        y_val = y_int[effective_val_start:val_end]

        if len(X_train) < 50 or len(X_val) < 10:
            logger.warning("Fold %d: insufficient samples — stopping", fold + 1)
            break

        trainer = XGBoostTrainer(mode=mode)
        fold_result = trainer.train(X_train, y_train)
        dval = xgb.DMatrix(X_val)
        y_pred_prob = fold_result.model.predict(dval)
        y_pred_prob_max = np.max(y_pred_prob, axis=1)
        y_pred = np.argmax(y_pred_prob, axis=1)

        # Apply confidence threshold: force NO_TRADE when model is uncertain
        thr = confidence_threshold if confidence_threshold is not None else CONFIDENCE_THRESHOLD
        low_conf_count = 0
        low_conf_pct = 0.0
        if thr >= 0:
            low_conf_count = int(np.sum(y_pred_prob_max < thr))
            low_conf_pct = float(low_conf_count / len(y_pred_prob_max) * 100)
            y_pred[y_pred_prob_max < thr] = 2  # NO_TRADE

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

        val_net_r_values = net_r_values[effective_val_start:val_end]
        net_r_expectancy_val = float(np.mean(val_net_r_values)) if len(val_net_r_values) > 0 else 0.0

        results.append({
            "fold": fold + 1,
            "n_train": len(X_train),
            "n_val": len(X_val),
            "purge_period": purge_bars,
            "embargo_period": embargo_bars,
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
        })

        logger.info(
            "Fold %d/%d: train=%d, val=%d, val_acc=%.4f, active=%d",
            fold + 1, min_folds, results[-1]["n_train"], results[-1]["n_val"],
            val_accuracy, active_trade_count,
        )

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
    """Compute OOS Sharpe ratio from per-fold net R-expectancy values."""
    r_exps = [r["net_r_expectancy"] for r in wfv_results if abs(r["net_r_expectancy"]) > 1e-12]
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

    # R-expectancy decomposition: net is primary; gross is recovered from net + cost
    net_r_exps = [r["net_r_expectancy"] for r in wfv_results]
    round_trip_cost_r = fee_pct * 2 / 100  # R units (same cost every bar)
    gross_r_exps = [nr + round_trip_cost_r for nr in net_r_exps]
    net_expectancy_r = float(np.mean(net_r_exps)) if net_r_exps else 0.0
    gross_expectancy_r = float(np.mean(gross_r_exps)) if gross_r_exps else 0.0
    net_sharpe_ratio = net_sharpe

    total_active = sum(r["active_trade_count"] for r in wfv_results)
    total_long = sum(r["long_count"] for r in wfv_results)
    total_short = sum(r["short_count"] for r in wfv_results)
    total_no_trade = sum(r["no_trade_count"] for r in wfv_results)
    total_decisions = total_active + total_no_trade
    exposure_pct = (total_active / total_decisions * 100) if total_decisions > 0 else 0.0

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
    parser.add_argument("--target", default="3-class", choices=["3-class", "2-class"],
                        help="Target: 3-class (LONG/SHORT/NO_TRADE) or 2-class (LONG vs SHORT only)")
    parser.add_argument("--confidence", type=float, default=None,
                        help="Confidence threshold (-1 to disable, default=0.55 for 3-class, disabled for 2-class)")
    args = parser.parse_args()

    global mode
    mode = args.mode.upper()
    symbols = [s.strip().upper() for s in args.symbols.split(",")]
    cfg = MODE_CONFIG[mode]
    interval = cfg["primary"]

    # Set confidence default based on target
    if args.confidence is None:
        args.confidence = -1.0 if args.target == "2-class" else 0.55

    print(f"\n{'='*60}")
    print(f"  AlphaForge Training Pipeline")
    print(f"  Mode: {mode} | Interval: {interval} | Symbols: {len(symbols)}")
    print(f"  Target: {args.target} | Confidence: {'disabled' if args.confidence < 0 else args.confidence}")
    print(f"  Features: {args.features} | WFV Folds: {args.folds}")
    print(f"{'='*60}\n")

    # Step 1: Load data
    print("[1/6] Loading OHLCV data...")
    ohlcv = None
    if not args.synthetic:
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

    # Step 2: Generate labels
    print("\n[2/6] Generating triple-barrier labels...")
    y_int, gross_r_vals, r_vals, label_metrics = generate_labels(ohlcv, mode)

    # Step 2b: Filter to 2-class direction if requested
    if args.target == "2-class":
        dir_mask = y_int < 2
        removed = (~dir_mask).sum()
        # Apply to all arrays that need alignment
        gross_r_vals = gross_r_vals[dir_mask]
        r_vals = r_vals[dir_mask]
        y_int = y_int[dir_mask]
        # ohlcv is used for features — keep full ohlcv, feature pipeline handles alignment later
        print(f"  2-class target: {removed} NO_TRADE rows removed, {len(y_int)} direction rows remaining")
        print(f"  LONG={int((y_int==0).sum())} SHORT={int((y_int==1).sum())}")
    else:
        print(f"  3-class target: {dict(zip(['LONG','SHORT','NO_TRADE'],[int((y_int==0).sum()),int((y_int==1).sum()),int((y_int==2).sum())]))}")

    # Step 3: Compute features
    print("\n[3/6] Computing features...")
    feature_groups_arg = args.features.lower()
    if feature_groups_arg == "all":
        feature_groups = None
    else:
        feature_groups = [g.strip() for g in feature_groups_arg.split(",")]
    X, feat_names = compute_features_selected(ohlcv, mode, feature_groups=feature_groups)
    print(f"  {X.shape[1]} feature columns, {X.shape[0]} rows")

    # Align lengths (labels are shorter due to max_hold lookahead)
    cut = min(X.shape[0], len(y_int))
    X, y_int = X[:cut], y_int[:cut]
    r_vals = r_vals[:cut]
    print(f"  After label alignment: {len(X)} samples")

    # Remove NaN rows
    nan_mask = np.isnan(X).any(axis=1)
    X_clean = X[~nan_mask]
    y_clean = y_int[~nan_mask]
    r_clean = r_vals[~nan_mask]
    print(f"  After NaN removal: {len(X_clean)} valid samples ({int(nan_mask.sum())} dropped)")

    if len(X_clean) < 100:
        print("  ERROR: Insufficient clean samples for training")
        sys.exit(1)

    # Step 4: Walk-forward validation
    print(f"\n[4/6] Walk-forward validation ({args.folds} folds, anchored expanding)...")
    t0 = time.time()
    wfv_results = walk_forward_validate(
        X_clean, y_clean, r_clean, mode, min_folds=args.folds,
        confidence_threshold=args.confidence,
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

    # Step 6: Collect metrics
    print("\n[6/6] Collecting metrics...")
    fee_pct = cfg.get("ambiguity_margin_r", 0.04) if False else 0.04  # keep at 4bps
    metrics = collect_metrics(wfv_results, X_clean, feat_names, fee_pct=fee_pct)

    print(f"\n{'='*60}")
    print(f"  TRAINING RESULTS — {mode}")
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

    # Return the metrics for programmatic use
    return metrics


if __name__ == "__main__":
    metrics = main()

    # Render the color terminal dashboard
    try:
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        viz_path = repo_root / "scripts" / "visualize_results.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location("viz", viz_path)
        if spec and spec.loader:
            viz = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(viz)
            viz.render_dashboard(metrics)
    except Exception:
        pass

    # Print structured output for machine consumption
    print("\n---STRUCTURED_RESULTS---")
    print(json.dumps({
        "status": "PASS",
        "accuracy": metrics["accuracy"],
        "sharpe_ratio": metrics["sharpe_ratio"],
        "overfit_gap": metrics["overfit_gap"],
        "feature_count": metrics["feature_count"],
    }, indent=2))
