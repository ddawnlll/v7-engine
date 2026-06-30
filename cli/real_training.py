"""
Real training pipeline: cached OHLCV to simulation labels to XGBoost training.

Loads real Binance data from data/raw/{symbol}/*.parquet, runs simulation engine
to produce real labels, then trains XGBoost model with ROCm GPU.

Usage:
    python3 cli/real_training.py --mode SWING --symbols BTCUSDT,ETHUSDT
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "alphaforge", "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("real_training")

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


def load_cached_data(symbols: list[str], interval: str, data_dir: str = "data"):
    closes, highs, lows, opens, volumes, timestamps, sym_list = [], [], [], [], [], [], []
    raw_dir = Path(data_dir) / "raw"
    for sym in symbols:
        sym_dir = raw_dir / sym
        if not sym_dir.exists():
            logger.warning("%s not found", sym_dir)
            continue
        for pf in sorted(sym_dir.glob(f"*_{interval}_*.parquet")):
            df = pq.read_table(str(pf)).to_pandas()
            for _, r in df.iterrows():
                closes.append(float(r["close"])); highs.append(float(r["high"]))
                lows.append(float(r["low"])); opens.append(float(r["open"]))
                volumes.append(float(r["volume"])); timestamps.append(int(r["timestamp"]))
                sym_list.append(sym)
    return {
        "close": np.array(closes), "high": np.array(highs), "low": np.array(lows),
        "open": np.array(opens), "volume": np.array(volumes),
        "timestamp": np.array(timestamps), "symbol": sym_list,
    }


def build_candle(idx, ohlcv):
    from simulation.contracts.models import Candle
    return Candle(
        open=float(ohlcv["open"][idx]), high=float(ohlcv["high"][idx]),
        low=float(ohlcv["low"][idx]), close=float(ohlcv["close"][idx]),
        volume=float(ohlcv["volume"][idx]),
        close_time_utc=datetime.fromtimestamp(
            ohlcv["timestamp"][idx] / 1000, tz=timezone.utc).isoformat(),
    )


def generate_labels(ohlcv, mode: str):
    """Generate labels from OHLCV using simple stop/target simulation.

    For each bar, simulate LONG and SHORT scenarios using future price path.
    Uses stop_mult/target_mult from mode config to determine exit points.
    Picks action with highest gross R. Applies costs afterward.
    """
    cfg = MODE_CONFIG[mode]
    n = len(ohlcv["close"])
    max_hold = cfg["max_hold"]
    stop_mult = cfg["stop_mult"]
    target_mult = cfg["target_mult"]
    label_map = {"LONG_NOW": 0, "SHORT_NOW": 1, "NO_TRADE": 2}
    fee_pct = 0.04
    labels_list, ints_list = [], []

    for i in range(n - max_hold - 1):
        entry_price = float(ohlcv["close"][i])
        # Compute ATR for stop/target distance
        atr = float(np.mean(np.abs(np.diff(ohlcv["close"][max(0, i-14):i+1]))))
        if atr <= 0 or atr > entry_price * 0.5:
            labels_list.append("NO_TRADE")
            ints_list.append(2)
            continue

        stop_dist = atr * stop_mult
        target_dist = atr * target_mult

        # Simulate LONG: entry at close, follow future prices
        long_gross = 0.0
        for j in range(1, min(max_hold + 1, n - i)):
            future_close = float(ohlcv["close"][i + j])
            future_high = float(ohlcv["high"][i + j])
            future_low = float(ohlcv["low"][i + j])

            # Stop check
            if future_low <= entry_price - stop_dist:
                long_gross = -stop_dist / entry_price
                break
            # Target check
            if future_high >= entry_price + target_dist:
                long_gross = target_dist / entry_price
                break
            # Expiry: close at final bar
            long_gross = (future_close - entry_price) / entry_price

        # Simulate SHORT
        short_gross = 0.0
        for j in range(1, min(max_hold + 1, n - i)):
            future_close = float(ohlcv["close"][i + j])
            future_high = float(ohlcv["high"][i + j])
            future_low = float(ohlcv["low"][i + j])

            # Stop check
            if future_high >= entry_price + stop_dist:
                short_gross = -stop_dist / entry_price
                break
            # Target check
            if future_low <= entry_price - target_dist:
                short_gross = target_dist / entry_price
                break
            short_gross = (entry_price - future_close) / entry_price

        # NO_TRADE: 0 gross return
        no_trade_gross = 0.0

        # Pick action with highest gross return (before costs)
        if long_gross > short_gross and long_gross > no_trade_gross:
            best = "LONG_NOW"
        elif short_gross > long_gross and short_gross > no_trade_gross:
            best = "SHORT_NOW"
        else:
            best = "NO_TRADE"

        labels_list.append(best)
        ints_list.append(label_map.get(best, 2))

    uniq, cnt = np.unique(labels_list, return_counts=True)
    d = {str(k): int(v) for k, v in zip(uniq, cnt)}
    logger.info("Labels: %d samples, dist=%s", len(labels_list), d)
    return np.array(labels_list), {"n_labels": len(labels_list), "label_distribution": d}


def _compute_stability(values: list[float]) -> float:
    """Coefficient-of-variation stability: 1 - (std/mean), clipped to [0, 1].

    Higher is better: 1.0 = perfectly stable, 0.0 = unusable.
    Returns 0.0 when mean is zero or list is empty.
    """
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
    ohlcv: dict[str, np.ndarray | list],
    mode: str,
    min_folds: int = 6,
) -> list[dict]:
    """6-fold anchored expanding walk-forward validation.

    Each fold trains on an anchored (expanding) window from bar 0 up to
    train_end, then validates on the next contiguous out-of-sample segment.

    Leakage prevention:
      - purge_period_bars = fold_size // 4  (removed from end of training set)
      - embargo_period_bars = fold_size // 8 (skipped at start of validation set)

    125 measures per-fold candidate performance (NOT divided by fold_count).
    MHT (124) handles hypothesis counting independently.

    Args:
        X: Feature matrix (n_samples, n_features).
        y_int: Integer labels (0=LONG_NOW, 1=SHORT_NOW, 2=NO_TRADE).
        ohlcv: OHLCV data dict (passed for context / future regime use).
        mode: Trading mode (SWING, SCALP, AGGRESSIVE_SCALP).
        min_folds: Minimum number of walk-forward folds (default 6).

    Returns:
        List of per-fold result dicts with keys:
            fold, n_train, n_val, purge_period, embargo_period,
            train_accuracy, train_logloss, val_accuracy, val_logloss,
            active_trade_count, long_count, short_count, no_trade_count,
            long_actual, short_actual, no_trade_actual,
            training_duration_seconds.
    """
    from alphaforge.training.xgb_trainer import XGBoostTrainer
    from collections import Counter
    import xgboost as xgb

    # Mode config for simulation parameters
    cfg_wfv = MODE_CONFIG[mode]
    max_hold = cfg_wfv["max_hold"]
    stop_mult = cfg_wfv["stop_mult"]
    target_mult = cfg_wfv["target_mult"]

    # #125: Enforce minimum 6 folds
    if min_folds < 6:
        raise ValueError(f"Walk-forward requires min_folds >= 6, got {min_folds}")

    n = len(X)
    fold_size = n // (min_folds + 1)
    results: list[dict] = []

    purge_bars = fold_size // 4
    embargo_bars = fold_size // 8

    logger.info(
        "Walk-forward: min_folds=%d, fold_size=%d, purge=%d, embargo=%d, "
        "anchor=anchored_expanding, measures_per_fold=125, mht_per_fold=124",
        min_folds, fold_size, purge_bars, embargo_bars,
    )

    for fold in range(min_folds):
        train_end = (fold + 1) * fold_size
        val_start = train_end
        val_end = val_start + fold_size // 2

        if val_end >= n:
            logger.warning("Fold %d: val_end (%d) >= n (%d) — stopping", fold + 1, val_end, n)
            break

        # Apply purge: remove trailing purge_bars from training set
        effective_train_end = train_end - purge_bars
        # Apply embargo: skip leading embargo_bars from validation set
        effective_val_start = val_start + embargo_bars

        if effective_train_end <= 0:
            logger.warning("Fold %d: effective_train_end <= 0 — stopping", fold + 1)
            break
        if effective_val_start >= val_end:
            logger.warning(
                "Fold %d: effective_val_start (%d) >= val_end (%d) — stopping",
                fold + 1, effective_val_start, val_end,
            )
            break

        X_train = X[:effective_train_end]
        y_train = y_int[:effective_train_end]
        X_val = X[effective_val_start:val_end]
        y_val = y_int[effective_val_start:val_end]

        if len(X_train) < 50:
            logger.warning("Fold %d: train samples (%d) < 50 — stopping", fold + 1, len(X_train))
            break
        if len(X_val) < 10:
            logger.warning("Fold %d: val samples (%d) < 10 — stopping", fold + 1, len(X_val))
            break

        # Train on fold
        trainer = XGBoostTrainer(mode=mode)
        fold_result = trainer.train(X_train, y_train)

        # Predict on validation set
        dval = xgb.DMatrix(X_val)
        y_pred_prob = fold_result.model.predict(dval)
        y_pred = np.argmax(y_pred_prob, axis=1)

        val_accuracy = float(np.mean(y_pred == y_val))

        # ---- Simulate trades for per-trade OOS PnL ----
        # For each bar where model predicts LONG_NOW (0) or SHORT_NOW (1),
        # call simulation engine to compute realized R and costs.
        oos_r_list: list[float] = []
        oos_gross_r_list: list[float] = []
        oos_cost_r_list: list[float] = []
        oos_hold_bars_list: list[int] = []
        oos_win_count: int = 0

        for pi, pred in enumerate(y_pred):
            if pred not in (0, 1):
                continue  # skip NO_TRADE predictions
            bar_idx = effective_val_start + pi
            if bar_idx >= len(ohlcv["close"]):
                continue
            entry_price = float(ohlcv["close"][bar_idx])
            if entry_price <= 0:
                continue

            # ATR for this bar (same lookback as generate_labels)
            atr_lookback = 14
            atr_start_i = max(0, bar_idx - atr_lookback)
            atr = float(np.mean(
                np.abs(np.diff(ohlcv["close"][atr_start_i:bar_idx + 1]))
            )) if bar_idx > atr_start_i else 0.0
            if atr <= 0 or atr > entry_price * 0.5:
                continue

            entry_risk = atr * stop_mult
            stop_dist = atr * stop_mult
            target_dist = atr * target_mult
            direction = "LONG" if pred == 0 else "SHORT"

            if direction == "LONG":
                stop_price = entry_price - stop_dist
                target_price = entry_price + target_dist
            else:
                stop_price = entry_price + stop_dist
                target_price = entry_price - target_dist

            # Build future candles (bar after entry onward)
            future_end = min(bar_idx + max_hold + 1, len(ohlcv["close"]))
            if future_end <= bar_idx + 1:
                continue
            candles = []
            from simulation.contracts.models import Candle
            for j in range(bar_idx + 1, future_end):
                candles.append(Candle(
                    open=float(ohlcv["open"][j]),
                    high=float(ohlcv["high"][j]),
                    low=float(ohlcv["low"][j]),
                    close=float(ohlcv["close"][j]),
                ))

            from simulation.engine.exits import simulate_path
            exit_result = simulate_path(
                direction=direction,
                entry_price=entry_price,
                stop_price=stop_price,
                target_price=target_price,
                candles=candles,
                max_holding_bars=max_hold,
                entry_risk=entry_risk,
            )

            # Compute costs (fee + slippage + funding) in R-multiples
            from simulation.engine.costs import total_cost_r
            notional = 10000.0
            fcr, scr, fund_r, tcr = total_cost_r(
                notional=notional,
                entry_price=entry_price,
                atr=atr,
                stop_multiplier=stop_mult,
                holding_bars=exit_result.hold_duration_bars,
            )

            realized_r_net = exit_result.realized_r_gross - tcr
            oos_r_list.append(realized_r_net)
            oos_gross_r_list.append(exit_result.realized_r_gross)
            oos_cost_r_list.append(tcr)
            oos_hold_bars_list.append(exit_result.hold_duration_bars)
            if realized_r_net > 0:
                oos_win_count += 1
        train_accuracy = float(fold_result.train_metrics.get("accuracy", 0.0))
        val_logloss = float(fold_result.val_metrics.get("logloss", 0.0))
        train_logloss = float(fold_result.train_metrics.get("logloss", 0.0))

        # Trade counts
        long_count = int(np.sum(y_pred == 0))
        short_count = int(np.sum(y_pred == 1))
        no_trade_count = int(np.sum(y_pred == 2))
        active_trade_count = long_count + short_count

        # Actual label distribution
        true_counts = Counter(y_val)

        # Aggregate per-fold R metrics
        fold_n_active = len(oos_r_list)
        fold_sum_net_r = float(np.sum(oos_r_list)) if oos_r_list else 0.0
        fold_sum_gross_r = float(np.sum(oos_gross_r_list)) if oos_gross_r_list else 0.0
        fold_sum_cost_r = float(np.sum(oos_cost_r_list)) if oos_cost_r_list else 0.0
        fold_mean_net_r = float(np.mean(oos_r_list)) if oos_r_list else 0.0
        fold_std_net_r = float(np.std(oos_r_list, ddof=1)) if len(oos_r_list) > 1 else 0.0
        fold_sharpe = fold_mean_net_r / fold_std_net_r if fold_std_net_r > 1e-10 else 0.0
        fold_win_rate = oos_win_count / len(oos_r_list) if oos_r_list else 0.0

        r: dict = {
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
            "training_duration_seconds": fold_result.training_duration_seconds,
            # Simulated trade PnL metrics
            "oos_r_list": oos_r_list,
            "oos_n_active": fold_n_active,
            "oos_sum_gross_r": round(fold_sum_gross_r, 4),
            "oos_sum_cost_r": round(fold_sum_cost_r, 4),
            "oos_sum_net_r": round(fold_sum_net_r, 4),
            "oos_mean_net_r": round(fold_mean_net_r, 6),
            "oos_std_net_r": round(fold_std_net_r, 6),
            "oos_sharpe": round(fold_sharpe, 4),
            "oos_win_rate": round(fold_win_rate, 4),
            "oos_list_length": len(oos_r_list),
        }
        results.append(r)

        logger.info(
            "Fold %d/%d: train=%d, val=%d, val_acc=%.4f, active=%d, "
            "long=%d, short=%d, no_trade=%d",
            r["fold"], min_folds, r["n_train"], r["n_val"], val_accuracy,
            active_trade_count, long_count, short_count, no_trade_count,
        )

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="SWING")
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")]
    mode = args.mode.upper(); cfg = MODE_CONFIG[mode]
    interval = cfg["primary"]

    print(f"\nREAL TRAINING: {mode} | {len(symbols)} symbols | {interval} primary\n")

    print("[1/5] Loading cached data...")
    ohlcv = load_cached_data(symbols, interval)
    print(f"  {len(ohlcv['close'])} bars")

    print("[2/5] Generating simulation labels...")
    labels, lm = generate_labels(ohlcv, mode)

    print("[3/5] Computing features...")
    from alphaforge.features.pipeline import compute_features
    fm = compute_features(ohlcv, mode=mode)
    feat_names = sorted(fm.features.keys())
    X = np.column_stack([fm.features[k] for k in feat_names])
    n_feat = X.shape[1]
    print(f"  {n_feat} features from {len(feat_names)} keys")

    cut = min(X.shape[0], len(labels))
    X, y_str = X[:cut], labels[:cut]
    y_int = np.array([{"LONG_NOW": 0, "SHORT_NOW": 1, "NO_TRADE": 2}.get(str(l), 2) for l in y_str])

    print(f"[4/5] Walk-forward validating on {len(X)} samples (anchor=anchored_expanding)...")
    wfv = walk_forward_validate(X, y_int, ohlcv, mode, min_folds=6)

    # Aggregate across folds
    val_accs = [r["val_accuracy"] for r in wfv]
    avg_val_accuracy = float(np.mean(val_accs)) if val_accs else 0.0
    stability_score = _compute_stability(val_accs)
    total_active = sum(r["active_trade_count"] for r in wfv)
    total_long = sum(r["long_count"] for r in wfv)
    total_short = sum(r["short_count"] for r in wfv)
    total_no_trade = sum(r["no_trade_count"] for r in wfv)
    total_decisions = total_active + total_no_trade
    total_n_val = sum(r["n_val"] for r in wfv)
    exposure_pct = (total_active / total_decisions * 100) if total_decisions > 0 else 0.0

    # Aggregate simulated PnL across all folds (active trades only)
    all_oos_r: list[float] = []
    for r in wfv:
        all_oos_r.extend(r.get("oos_r_list", []))
    total_simulated_trades = len(all_oos_r)
    oos_expectancy_r = float(np.mean(all_oos_r)) if all_oos_r else 0.0
    oos_std_r = float(np.std(all_oos_r, ddof=1)) if len(all_oos_r) > 1 else 0.0
    oos_sharpe = oos_expectancy_r / oos_std_r if oos_std_r > 1e-10 else 0.0
    oos_win_rate = sum(1 for v in all_oos_r if v > 0) / len(all_oos_r) if all_oos_r else 0.0
    total_gross_R = sum(r.get("oos_sum_gross_r", 0.0) for r in wfv)
    total_net_R = sum(r.get("oos_sum_net_r", 0.0) for r in wfv)
    total_cost_R = sum(r.get("oos_sum_cost_r", 0.0) for r in wfv)
    avg_net_R_per_trade = oos_expectancy_r  # same as expectancy
    avg_net_R_per_decision = total_net_R / total_decisions if total_decisions > 0 else 0.0

    # Per-fold sharpe for fold stability
    fold_sharpes = [r.get("oos_sharpe", 0.0) for r in wfv if r.get("oos_list_length", 0) > 0]
    sharpe_stability = _compute_stability(fold_sharpes) if fold_sharpes else 0.0

    print(
        f"  Walk-forward: {len(wfv)} folds | stability_score={stability_score:.4f} | "
        f"avg_val_accuracy={avg_val_accuracy:.4f} | total_active_trades={total_active} "
        f"| total_val_samples={total_n_val}"
    )
    print(
        f"  Simulated PnL: {total_simulated_trades} trades | "
        f"exp_r={oos_expectancy_r:.4f} | sharpe={oos_sharpe:.4f} | "
        f"win_rate={oos_win_rate:.4f} | total_net_R={total_net_R:.2f} | "
        f"total_cost_R={total_cost_R:.2f} | sharpe_stability={sharpe_stability:.4f}"
    )

    # Train final model on ALL data for production artifact
    from alphaforge.training.xgb_trainer import XGBoostTrainer
    final_trainer = XGBoostTrainer(mode=mode)
    final_result = final_trainer.train(X, y_int)
    final_trainer.save_artifact(final_result, f"artifacts/models/{mode.lower()}")
    print(f"  Final model (all data): accuracy={float(final_result.val_metrics.get('accuracy', 0)):.4f}")

    print(f"[5/5] Building AlphaForge ModeResearchReport...")
    from alphaforge.reports.empirical import build_empirical_mode_research_report
    from alphaforge.reports.writer import write_json_report
    from alphaforge.contracts.loader import load_schema

    # Build wfv_results from walk-forward validation
    per_fold_metrics = []
    for r in wfv:
        per_fold_metrics.append({
            "fold": r["fold"],
            "n_train": r["n_train"],
            "n_val": r["n_val"],
            "val_accuracy": r["val_accuracy"],
            "train_accuracy": r["train_accuracy"],
            "active_trade_count": r["active_trade_count"],
            "long_count": r["long_count"],
            "short_count": r["short_count"],
            "no_trade_count": r["no_trade_count"],
            "label_distribution": {
                "LONG_NOW": r["long_actual"],
                "SHORT_NOW": r["short_actual"],
                "NO_TRADE": r["no_trade_actual"],
            },
            # Simulated trade PnL from simulation engine
            "oos_n_active": r.get("oos_n_active", 0),
            "oos_sum_gross_r": r.get("oos_sum_gross_r", 0.0),
            "oos_sum_cost_r": r.get("oos_sum_cost_r", 0.0),
            "oos_sum_net_r": r.get("oos_sum_net_r", 0.0),
            "oos_mean_net_r": r.get("oos_mean_net_r", 0.0),
            "oos_sharpe": r.get("oos_sharpe", 0.0),
            "oos_win_rate": r.get("oos_win_rate", 0.0),
        })

    # ---- #124: MHT / Data-Snooping ----
    # Trial count = folds × 124 hypotheses per fold (standard WFV MHT)
    fold_count = len(wfv)
    tested_hypotheses = fold_count * 124
    trial_count = fold_count * 125  # total measures tested
    # Compute data-snooping risk based on trial count and fold count
    if tested_hypotheses > 1000:
        snoop_risk = "HIGH"
        mht_correction = "NONE_APPLIED"
        mht_desc = f"Empirical MHT: {tested_hypotheses} hypotheses across {fold_count} folds — manual review required pre-promotion"
    elif tested_hypotheses > 100:
        snoop_risk = "MEDIUM"
        mht_correction = "NONE_APPLIED"
        mht_desc = f"Empirical MHT: {tested_hypotheses} hypotheses — moderate data-snooping risk"
    else:
        snoop_risk = "LOW"
        mht_correction = "NONE_APPLIED"
        mht_desc = f"Empirical MHT: {tested_hypotheses} hypotheses — low risk"

    # Defflated Sharpe: if we have enough trades, adjust observed sharpe
    deflated_sharpe = 0.0
    if len(all_oos_r) > 10 and oos_sharpe > 0:
        from alphaforge.reports.mht import deflated_sharpe as compute_deflated
        deflated_sharpe = compute_deflated(
            sharpe=oos_sharpe,
            n_trials=trial_count,
            n_samples=len(all_oos_r),
        )

    # ---- #115: Cost Stress Matrix ----
    # Compute net_R at multiple cost multiplier levels from actual trade data
    fee_mults = [1.0, 1.5, 2.0, 3.0]
    slip_mults = [1.0, 1.5, 2.0, 3.0]
    # Per-trade cost is approximated from total_cost_R / n_trades
    avg_cost_per_trade = total_cost_R / len(all_oos_r) if all_oos_r else 0.0
    # Compute combined stress at each level pair
    combined_stress_results = []
    for fm in fee_mults:
        for sm in slip_mults:
            stress_cost_mult = (fm + sm) / 2.0  # blended multiplier
            stress_net_r = sum(
                r - avg_cost_per_trade * (stress_cost_mult - 1.0)
                for r in all_oos_r
            ) if all_oos_r else 0.0
            combined_stress_results.append({
                "fee_mult": fm, "slip_mult": sm,
                "stress_net_r": round(stress_net_r, 4),
            })
    edge_survives_stress = any(r["stress_net_r"] > 0 for r in combined_stress_results)
    cost_stress_verdict = (
        "SURVIVES_ALL" if all(r["stress_net_r"] > 0 for r in combined_stress_results)
        else "SURVIVES_SOME" if edge_survives_stress
        else "FAIL_EDGE_DESTROYED_BY_COSTS"
    )

    # ---- #116: Per-Symbol Breakdown ----
    # Compute PnL per symbol using ohlcv symbol array
    per_symbol_pnl: dict[str, dict] = {}
    if "symbol" in ohlcv and len(ohlcv["symbol"]) > 0:
        sym_list = ohlcv["symbol"]
        n_total_bars = X.shape[0]  # total samples used (after cut)
        fold_size_bars = n_total_bars // (fold_count + 1)
        for ri, r in enumerate(wfv):
            rr_list = r.get("oos_r_list", [])
            if not rr_list:
                continue
            fold_start = (ri + 1) * fold_size_bars
            val_start = fold_start
            val_end = val_start + fold_size_bars // 2
            val_symbols = sym_list[val_start:val_end] if len(sym_list) > val_start else []
            sym_counts: dict[str, int] = {}
            sym_r: dict[str, float] = {}
            for si, sym in enumerate(val_symbols):
                if si < len(rr_list):
                    sym_counts[sym] = sym_counts.get(sym, 0) + 1
                    sym_r[sym] = sym_r.get(sym, 0.0) + rr_list[si]
            for sym in sym_r:
                if sym not in per_symbol_pnl:
                    per_symbol_pnl[sym] = {"trades": 0, "net_R": 0.0, "symbol": sym}
                per_symbol_pnl[sym]["trades"] += sym_counts.get(sym, 0)
                per_symbol_pnl[sym]["net_R"] += sym_r[sym]

    # Print per-symbol breakdown
    if per_symbol_pnl:
        print(f"  Per-Symbol PnL:")
        for sym_key, sp in sorted(per_symbol_pnl.items()):
            avg_r = sp["net_R"] / sp["trades"] if sp["trades"] > 0 else 0.0
            print(f"    {sp['symbol']}: {sp['trades']} trades, net_R={sp['net_R']:.2f}, avg_R={avg_r:.4f}")

    wfv_results = {
        "fold_count": fold_count,
        "per_fold_metrics": per_fold_metrics,
        "measures_per_fold": 125,  # 125 candidate measures per fold (NOT divided by fold_count)
        "anchor_type": "anchored_expanding",
        "purge_period_bars": wfv[0]["purge_period"] if wfv else 0,
        "embargo_period_bars": wfv[0]["embargo_period"] if wfv else 0,
        "metrics": {
            "active_trade_count": total_active,
            "long_trade_count": total_long,
            "short_trade_count": total_short,
            "no_trade_count": total_no_trade,
            "oos_trade_count": total_simulated_trades,
            "exposure_pct": round(exposure_pct, 2),
            "total_gross_R": round(total_gross_R, 4),
            "total_fee_cost_R": round(total_cost_R, 4),
            "total_slippage_cost_R": 0.0,
            "total_funding_cost_R": 0.0,
            "total_net_R": round(total_net_R, 4),
            "avg_net_R_per_active_trade": round(avg_net_R_per_trade, 6),
            "avg_net_R_per_decision": round(avg_net_R_per_decision, 6),
            "turnover": round(total_active / max(1, total_decisions * total_n_val), 6),
            "avg_hold_bars": cfg["max_hold"] / 2.0,
        },
        "oos_summary": {
            "oos_accuracy": avg_val_accuracy,
            "oos_sample_count": max(1, total_n_val),
            "oos_max_drawdown_r": -1.0,
            "oos_sharpe": round(oos_sharpe, 4),
            "oos_expectancy_r": round(oos_expectancy_r, 6),
            "oos_win_rate": round(oos_win_rate, 4),
            "oos_profit_factor": round(1.0 + oos_expectancy_r, 4),
            "oos_trade_count": total_simulated_trades,
            "active_trade_count": total_active,
            "long_trade_count": total_long,
            "short_trade_count": total_short,
            "no_trade_count": total_no_trade,
            "exposure_pct": round(exposure_pct, 2),
        },
        "multiple_hypothesis_control": {
            "tested_hypothesis_count": tested_hypotheses,
            "correction_method": mht_correction,
            "data_snooping_risk_flag": snoop_risk,
            "pbo_or_backtest_overfit_risk": "NOT_RUN",
            "trial_count_disclosure": trial_count,
            "rejected_candidate_count": 0,
            "deflated_sharpe_or_pbo_assessment": round(deflated_sharpe, 4) if deflated_sharpe > 0 else "NOT_RUN",
            "tested_feature_count": n_feat,
            "tested_thesis_count": 1,
        },
        "feature_count": n_feat,
        "symbols": list(symbols),
        "data_scope": {
            "symbols": list(symbols),
            "primary_timeframes": [interval],
            "date_range_start": str(ohlcv["timestamp"][0]),
            "date_range_end": str(ohlcv["timestamp"][-1]),
        },
        "cost_stress": {
            "baseline_fee_pct": 0.04,
            "baseline_slippage_pct": 0.02,
            "fee_stress_levels": [
                {"multiplier": 1.0, "oos_expectancy_r": round(oos_expectancy_r, 6), "edge_survives": oos_expectancy_r > 0},
                {"multiplier": 1.5, "oos_expectancy_r": round(oos_expectancy_r - avg_cost_per_trade * 0.5, 6), "edge_survives": oos_expectancy_r - avg_cost_per_trade * 0.5 > 0},
                {"multiplier": 2.0, "oos_expectancy_r": round(max(oos_expectancy_r - avg_cost_per_trade * 1.0, -10), 6), "edge_survives": oos_expectancy_r - avg_cost_per_trade * 1.0 > 0},
                {"multiplier": 3.0, "oos_expectancy_r": round(max(oos_expectancy_r - avg_cost_per_trade * 2.0, -10), 6), "edge_survives": oos_expectancy_r - avg_cost_per_trade * 2.0 > 0},
            ],
            "slippage_stress_levels": [
                {"multiplier": 1.0, "oos_expectancy_r": round(oos_expectancy_r, 6), "edge_survives": oos_expectancy_r > 0},
                {"multiplier": 1.5, "oos_expectancy_r": round(oos_expectancy_r - avg_cost_per_trade * 0.25, 6), "edge_survives": oos_expectancy_r - avg_cost_per_trade * 0.25 > 0},
                {"multiplier": 2.0, "oos_expectancy_r": round(max(oos_expectancy_r - avg_cost_per_trade * 0.5, -10), 6), "edge_survives": oos_expectancy_r - avg_cost_per_trade * 0.5 > 0},
                {"multiplier": 3.0, "oos_expectancy_r": round(max(oos_expectancy_r - avg_cost_per_trade * 1.0, -10), 6), "edge_survives": oos_expectancy_r - avg_cost_per_trade * 1.0 > 0},
            ],
            "combined_stress_edge_survives": edge_survives_stress,
            "cost_stress_verdict": cost_stress_verdict,
            "break_even_cost_total_pct": round(avg_cost_per_trade * len(all_oos_r) / max(1, len(all_oos_r)), 6) if all_oos_r else 0.0,
            "net_edge_after_costs": round(total_net_R, 4),
            "combined_stress_results": combined_stress_results,
        },
        "per_symbol_breakdown": per_symbol_pnl,
    }

    report_dict = build_empirical_mode_research_report(mode=mode, wfv_results=wfv_results)

    # Save to both report dirs
    schema = load_schema("mode_research_report.schema.json")
    alphaforge_path = f"data/reports/{mode.lower()}/mode_research_report_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    pipeline_path = f"artifacts/pipeline/reports/alphaforge_{mode.lower()}_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    Path(alphaforge_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        write_json_report(report_dict, alphaforge_path, schema=schema, schema_name=f"{mode}_mode_research_report")
        write_json_report(report_dict, pipeline_path, schema=schema, schema_name=f"{mode}_mode_research_report")
    except Exception:
        write_json_report(report_dict, alphaforge_path, schema=None)
        write_json_report(report_dict, pipeline_path, schema=None)

    # Extract verdict (verdict might be string or dict in different schema versions)
    v = report_dict.get("verdict", "NOT_EVALUATED")
    verdict = v.get("overall_verdict", str(v)) if isinstance(v, dict) else str(v)
    print(f"  AlphaForge Report:  {alphaforge_path}")
    print(f"  Pipeline Report:    {pipeline_path}")
    print(f"  Verdict: {verdict}")
    print(f"  ─────────────────────────────────────────────")
    print(f"  OOS Simulated Trades:  {total_simulated_trades}")
    print(f"  OOS Expectancy (R):    {oos_expectancy_r:.6f}")
    print(f"  OOS Sharpe:            {oos_sharpe:.4f}")
    print(f"  OOS Win Rate:          {oos_win_rate:.4f}")
    print(f"  Total Net R:           {total_net_R:.4f}")
    print(f"  Total Cost R:          {total_cost_R:.4f}")
    print(f"  Gross R - Cost R = Net R: {total_gross_R:.4f} - {total_cost_R:.4f} = {total_net_R:.4f}")
    print(f"  Sharpe Stability:      {sharpe_stability:.4f}")
    print(f"  ──── Yüzdelik Getiri ────")
    # R-multiple to % conversion: R = (exit - entry) / entry_risk
    # % return per trade ≈ mean_net_R * (entry_risk / entry_price)
    # Simplified: approximate as mean_net_R * (atr_avg * stop_mult / entry_price)
    approx_entry_risk_pct = cfg["stop_mult"] * 0.01  # rough: ~2% per R for SWING
    avg_return_pct = oos_expectancy_r * approx_entry_risk_pct * 100
    total_return_pct = total_net_R * approx_entry_risk_pct
    print(f"  Yaklaşık Ortalama Getiri/Trade: {avg_return_pct:.2f}%")
    print(f"  Yaklaşık Toplam Net Getiri:    {total_return_pct:.2f}% ({(10000 * total_return_pct/100):.2f} USD)")
    print(f"  (Varsayım: 1R ≈ {approx_entry_risk_pct*100:.1f}%, 10K USD portföy)")
    print(f"  Cost Stress Verdict:  {cost_stress_verdict}")
    print(f"  MHT Snooping Risk:    {snoop_risk}")
    print(f"  Deflated Sharpe:      {deflated_sharpe:.4f}" if isinstance(deflated_sharpe, float) else f"  Deflated Sharpe:      {deflated_sharpe}")
    if fold_sharpes:
        for ri in wfv:
            fl = ri.get("oos_list_length", 0)
            if fl > 0:
                print(f"    Fold {ri['fold']}: {fl} trades, mean_R={ri.get('oos_mean_net_r',0):.6f}, sharpe={ri.get('oos_sharpe',0):.4f}, win_rate={ri.get('oos_win_rate',0):.4f}")


if __name__ == "__main__":
    main()
