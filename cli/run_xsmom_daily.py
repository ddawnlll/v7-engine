#!/usr/bin/env python3
"""Cross-Sectional Momentum — Daily-Resample Baseline Backtest Runner.

Loads 1h klines for 20 symbols from the data lake, resamples to DAILY
bars, runs the cross-sectional momentum strategy with daily momentum
windows [1, 5, 21, 63], rebalances WEEKLY (every 5 bars), and reports
performance.

The goal: reduce cost erosion by reducing trade frequency vs the 4h
baseline (which burned 73% of gross return in fees on 15,908 trades).

Usage:
    python3 -m cli.run_xsmom_daily [--output PATH] [--synthetic]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# -- path setup -----------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in [PROJECT_ROOT, os.path.join(PROJECT_ROOT, "alphaforge", "src")]:
    if p not in sys.path:
        sys.path.insert(0, p)

# -- domain imports -------------------------------------------------------
from alphaforge.strategy.cross_sectional import (
    DEFAULT_CONFIG,
    backtest_cross_sectional_momentum,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column normalisation map  (some raw files use the old Binance schema)
# ---------------------------------------------------------------------------
COLUMN_ALIASES: dict[str, str] = {
    "open_time": "timestamp",
    "close_time": "close_timestamp",
    "trades": "trade_count",
    "taker_buy_volume": "taker_buy_base_volume",
}

REQUIRED_COLS = {"timestamp", "close"}


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise column names to canonical schema regardless of raw format."""
    for src, tgt in COLUMN_ALIASES.items():
        if src in df.columns:
            if tgt in df.columns:
                df[tgt] = df[tgt].fillna(df[src])
                df = df.drop(columns=[src])
            else:
                df = df.rename(columns={src: tgt})
    return df


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_symbol_klines(symbol: str, interval: str = "1h") -> pd.DataFrame:
    """Load all available klines for *symbol* from the raw data lake."""
    import glob as _glob

    raw_root = os.path.join(
        PROJECT_ROOT,
        "data_lake",
        "raw",
        "binance",
        "um",
        "klines",
        symbol,
        interval,
    )
    if not os.path.isdir(raw_root):
        logger.warning("Raw data directory not found for %s: %s", symbol, raw_root)
        return pd.DataFrame()

    parquet_files = sorted(
        _glob.glob(os.path.join(raw_root, "**", "*.parquet"), recursive=True)
    )
    if not parquet_files:
        logger.warning("No parquet files found for %s", symbol)
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    for fp in parquet_files:
        try:
            df_chunk = pd.read_parquet(fp)
            frames.append(df_chunk)
        except Exception as exc:
            logger.warning("Failed to read %s: %s", fp, exc)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df = _normalise_columns(df)

    if "timestamp" not in df.columns:
        logger.warning("%s has no timestamp column after normalisation", symbol)
        return pd.DataFrame()

    keep = [c for c in ["timestamp", "open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[keep]
    df = df.sort_values("timestamp").drop_duplicates(
        subset=["timestamp"], keep="last"
    ).reset_index(drop=True)

    return df


def load_all_symbols_hourly(
    symbols: list[str],
    interval: str = "1h",
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Load and align 1h klines for all *symbols*.

    Returns
    -------
    symbol_data : dict[str, np.ndarray]
        Mapping symbol -> aligned close-price array.
    common_timestamps : np.ndarray
        1-D int64 array of timestamps (ms) common to every symbol.
    """
    all_frames: dict[str, pd.DataFrame] = {}

    for sym in symbols:
        df = load_symbol_klines(sym, interval)
        if df.empty:
            logger.warning("No data for %s, skipping", sym)
            continue
        all_frames[sym] = df[["timestamp", "close"]].copy()
        logger.info(
            "Loaded %s: %d bars [%s .. %s]",
            sym,
            len(df),
            datetime.fromtimestamp(df["timestamp"].min() / 1000, tz=timezone.utc).strftime(
                "%Y-%m-%d"
            ),
            datetime.fromtimestamp(df["timestamp"].max() / 1000, tz=timezone.utc).strftime(
                "%Y-%m-%d"
            ),
        )

    if not all_frames:
        raise RuntimeError("No data loaded for any symbol.")

    # Build a set of timestamps common to all symbols
    ts_sets = [set(df["timestamp"].values) for df in all_frames.values()]
    common = sorted(set.intersection(*ts_sets))

    if len(common) < 500:
        logger.warning(
            "Only %d common timestamps across all symbols — "
            "backtest window will be narrow.",
            len(common),
        )

    common_arr = np.array(common, dtype=np.int64)
    symbol_data: dict[str, np.ndarray] = {}

    for sym in all_frames:
        ts_index = all_frames[sym].set_index("timestamp")
        aligned = ts_index.loc[common].values[:, 0].astype(np.float64)
        symbol_data[sym] = aligned

    logger.info(
        "Aligned %d symbols on %d common timestamps.",
        len(symbol_data),
        len(common_arr),
    )

    return symbol_data, common_arr


# ---------------------------------------------------------------------------
# Resampling
# ---------------------------------------------------------------------------


def resample_to_daily(
    symbol_data: dict[str, np.ndarray],
    timestamps: np.ndarray,
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Resample hourly aligned data to DAILY bars.

    Takes the last close of each calendar day as the daily close.
    Drops days where any symbol has NaN.
    """
    # Build a DataFrame with one column per symbol, indexed by datetime
    df = pd.DataFrame(
        symbol_data,
        index=pd.to_datetime(timestamps, unit="ms"),
    )
    # Resample to daily, keep the last observation of each day
    daily = df.resample("D").last()
    # Drop rows (days) that have any NaN (a symbol missing that day)
    before = len(daily)
    daily = daily.dropna()
    dropped = before - len(daily)
    if dropped:
        logger.info("Dropped %d daily bars with partial data.", dropped)

    new_timestamps = daily.index.to_numpy().astype("datetime64[ms]").astype(np.int64)
    new_symbol_data = {col: daily[col].values for col in daily.columns}

    logger.info(
        "Resampled %d hourly bars -> %d daily bars.",
        len(timestamps),
        len(new_timestamps),
    )
    return new_symbol_data, new_timestamps


# ---------------------------------------------------------------------------
# Baselines (daily-aware)
# ---------------------------------------------------------------------------


def _compute_period_returns(prices: np.ndarray) -> np.ndarray:
    """Compute per-step returns from a price array."""
    return np.diff(prices) / np.maximum(prices[:-1], 1e-10)


def _equity_curve(returns: np.ndarray) -> np.ndarray:
    """Compute equity curve from per-step returns (starting at 1.0)."""
    eq = np.empty(len(returns) + 1)
    eq[0] = 1.0
    np.cumprod(1 + returns, out=eq[1:])
    return eq


def _metrics_from_returns(
    returns: np.ndarray,
    n_per_year: float = 365,
) -> dict:
    """Compute standard performance metrics from a return series.

    Default 365 bars/year for daily data.
    """
    if len(returns) == 0:
        return {"net_return": 0.0, "sharpe": 0.0, "profit_factor": 0.0, "max_drawdown": 0.0}

    equity = _equity_curve(returns)
    net_return = float(equity[-1] - 1.0)

    if len(returns) > 1 and np.std(returns) > 0:
        sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(n_per_year))
    else:
        sharpe = 0.0

    pos = returns[returns > 0].sum()
    neg = abs(returns[returns < 0].sum())
    profit_factor = float(pos / max(neg, 1e-10)) if neg > 0 else float("inf")

    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    max_dd = float(np.min(dd))

    return {
        "net_return": round(net_return, 6),
        "sharpe": round(sharpe, 4),
        "profit_factor": round(profit_factor, 4),
        "max_drawdown": round(max_dd, 6),
    }


def baseline_buy_and_hold(btc_prices: np.ndarray) -> dict:
    """Buy and hold BTC for the entire period."""
    returns = _compute_period_returns(btc_prices)
    return _metrics_from_returns(returns)


def baseline_equal_weight(symbol_data: dict[str, np.ndarray]) -> dict:
    """Equal-weight portfolio: long every symbol with equal allocation."""
    n_sym = len(symbol_data)
    if n_sym == 0:
        return {"net_return": 0.0, "sharpe": 0.0, "profit_factor": 0.0, "max_drawdown": 0.0}

    all_returns = []
    for sym, prices in symbol_data.items():
        r = _compute_period_returns(prices)
        all_returns.append(r)

    avg_returns = np.mean(all_returns, axis=0)
    return _metrics_from_returns(avg_returns)


def baseline_random_ranking(
    symbol_data: dict[str, np.ndarray],
    timestamps: np.ndarray,
    config: dict,
    n_runs: int = 50,
    seed: int = 42,
) -> dict:
    """Random ranking baseline: randomly pick long/short at each rebalance."""
    n_sym = len(symbol_data)
    symbols = list(symbol_data.keys())
    prices = {s: symbol_data[s] for s in symbols}
    n_bars = len(timestamps)
    rebalance_every = config.get("rebalance_hours", 5)
    windows = config["momentum_windows"]
    max_w = max(windows)

    long_pct = config.get("long_pct", 0.20)
    short_pct = config.get("short_pct", 0.20)
    n_long = max(1, int(n_sym * long_pct))
    n_short = max(1, int(n_sym * short_pct))

    rng = np.random.default_rng(seed)
    all_final_metrics = []

    for _run in range(n_runs):
        equity = [1.0]
        prev_active: list[str] = []

        for bar in range(max_w, n_bars):
            if (bar - max_w) % rebalance_every != 0:
                equity.append(equity[-1])
                continue

            perm = rng.permutation(n_sym)
            long_idx = perm[:n_long]
            short_idx = perm[-n_short:]

            active = []
            for idx in long_idx:
                active.append((symbols[idx], 1))
            for idx in short_idx:
                active.append((symbols[idx], -1))

            cost_charge = config.get("taker_fee", 0.00045) + config.get("slippage", 0.0005)

            if bar + 1 < n_bars:
                period_returns = []
                for sym, direction in active:
                    ret = (prices[sym][bar + 1] - prices[sym][bar]) / max(
                        prices[sym][bar], 1e-10
                    )
                    period_returns.append(ret * direction)

                clean = [r for r in period_returns if not (np.isnan(r) or np.isinf(r))]
                avg_ret = float(np.mean(clean)) if clean else 0.0
                equity.append(equity[-1] * (1 + avg_ret - cost_charge))
            else:
                equity.append(equity[-1])

        eq_arr = np.array(equity)
        returns = np.diff(eq_arr)
        m = _metrics_from_returns(returns)
        all_final_metrics.append(m)

    return {
        "net_return_mean": round(
            np.mean([m["net_return"] for m in all_final_metrics]), 6
        ),
        "net_return_std": round(
            np.std([m["net_return"] for m in all_final_metrics]), 6
        ),
        "sharpe_mean": round(np.mean([m["sharpe"] for m in all_final_metrics]), 4),
        "sharpe_std": round(np.std([m["sharpe"] for m in all_final_metrics]), 4),
        "profit_factor_mean": round(
            np.mean([m["profit_factor"] for m in all_final_metrics]), 4
        ),
        "max_drawdown_mean": round(
            np.mean([m["max_drawdown"] for m in all_final_metrics]), 6
        ),
        "n_runs": n_runs,
    }


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def _to_native(obj: object) -> object:
    """Recursively convert numpy types in dicts/lists to native Python types."""
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_native(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def build_report(
    strategy_result,
    prices_aligned: dict[str, np.ndarray],
    timestamps: np.ndarray,
    data_source: str,
    n_symbols_loaded: int,
) -> dict:
    """Build the structured baseline report dict."""
    # BTC buy-and-hold
    btc_prices = prices_aligned.get("BTCUSDT")
    btc_bh = baseline_buy_and_hold(btc_prices) if btc_prices is not None else {}

    # Equal-weight
    eq_w = baseline_equal_weight(prices_aligned)

    # Random ranking
    random_r = baseline_random_ranking(prices_aligned, timestamps, strategy_result.config)

    # Determine if we beat no-trade
    beats_no_trade = bool(strategy_result.net_return > 0)
    beats_btc = bool(
        strategy_result.net_return > btc_bh.get("net_return", -999)
        if btc_bh
        else False
    )
    beats_equal_weight = bool(
        strategy_result.net_return > eq_w.get("net_return", -999)
    )
    beats_random = bool(
        strategy_result.net_return > random_r.get("net_return_mean", -999)
    )

    first_ts = timestamps[0]
    last_ts = timestamps[-1]
    dt_fmt = lambda ms: datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    cfg = strategy_result.config

    # Cost drag analysis (daily bars, weekly rebalance)
    n_reb = (len(timestamps) - max(cfg["momentum_windows"])) // max(cfg["rebalance_hours"], 1)
    per_rebalance_cost = cfg["taker_fee"] + cfg["slippage"]
    cost_drag_factor = (1 - per_rebalance_cost) ** n_reb

    report = {
        "report_id": "XSMOM_BASELINE_DAILY_V01",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_source": data_source,
        "data_range": {
            "start": dt_fmt(first_ts),
            "end": dt_fmt(last_ts),
            "n_bars": len(timestamps),
            "frequency": "daily",
        },
        "strategy_config": {
            "symbols": cfg["symbols"],
            "symbols_loaded": n_symbols_loaded,
            "intervals": cfg["intervals"],
            "data_frequency": cfg.get("data_frequency", "daily"),
            "momentum_windows": cfg["momentum_windows"],
            "long_pct": cfg["long_pct"],
            "short_pct": cfg["short_pct"],
            "max_exposure_pct": cfg["max_exposure_pct"],
            "max_symbols_per_side": cfg["max_symbols_per_side"],
            "rebalance_bars": cfg["rebalance_hours"],
            "fees": {
                "taker": cfg["taker_fee"],
                "maker": cfg["maker_fee"],
                "slippage": cfg["slippage"],
                "uncertainty_buffer": cfg["uncertainty_buffer"],
            },
        },
        "strategy_performance": {
            "net_return": round(float(strategy_result.net_return), 6),
            "gross_return": round(float(strategy_result.gross_return), 6),
            "total_cost": round(float(strategy_result.total_cost), 6),
            "sharpe": float(strategy_result.sharpe),
            "profit_factor": float(strategy_result.profit_factor),
            "max_drawdown": float(strategy_result.max_drawdown),
            "n_trades": int(strategy_result.n_trades),
            "n_long": int(strategy_result.n_long),
            "n_short": int(strategy_result.n_short),
            "n_rebalances": int(strategy_result.n_rebalances),
            "n_signals_generated": int(strategy_result.n_signals_generated),
            "n_trades_gated": int(strategy_result.n_trades_gated),
            "n_trades_executed": int(strategy_result.n_trades_executed),
            "exposure_pct": float(strategy_result.exposure_pct),
            "beat_no_trade": beats_no_trade,
        },
        "cost_analysis": {
            "n_rebalance_periods": n_reb,
            "per_rebalance_cost": per_rebalance_cost,
            "cost_drag_factor_naive": round(float(cost_drag_factor), 6),
            "cost_only_impact_pct": round(float((1 - cost_drag_factor) * 100), 2),
            "note": (
                "Daily resampling reduces bars and rebalance frequency. "
                "Per-rebalance cost of {:.4f} charged {} times compounds to "
                "{:.1f}% erosion in a zero-alpha scenario."
            ).format(per_rebalance_cost, n_reb, (1 - cost_drag_factor) * 100),
        },
        "baselines": {
            "buy_and_hold_btc": btc_bh,
            "equal_weight_all": eq_w,
            "random_ranking": random_r,
        },
        "comparisons": {
            "outperforms_no_trade": beats_no_trade,
            "outperforms_buy_and_hold_btc": beats_btc,
            "outperforms_equal_weight": beats_equal_weight,
            "outperforms_random_ranking": beats_random,
        },
        "verdict": "PASS" if beats_no_trade else "FAIL",
        "verdict_reason": (
            "Daily-resampled XSMOM generates positive net return."
            if beats_no_trade
            else (
                "Daily-resampled XSMOM does NOT generate positive net return. "
                "Cost erosion over {:.1f}% of portfolio value over {} periods."
            ).format((1 - cost_drag_factor) * 100, n_reb)
        ),
    }
    return _to_native(report)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cross-Sectional Momentum Daily Baseline Backtest"
    )
    parser.add_argument(
        "--output",
        default="reports/candidates/xsmom_baseline_daily.json",
        help="Path for the output report JSON (default: %(default)s)",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Force synthetic data generation even when real data exists",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    log = logging.getLogger("xsmom_daily")
    log.info("XSMOM Daily Baseline — starting")

    t0 = time.time()

    symbols = DEFAULT_CONFIG["symbols"]
    log.info("Target symbols: %s", ", ".join(symbols))

    # ------------------------------------------------------------------
    # 1. Load data (hourly, then resample to daily)
    # ------------------------------------------------------------------
    if not args.synthetic:
        try:
            hourly_data, hourly_ts = load_all_symbols_hourly(symbols, interval="1h")
            data_source = "real (data_lake/raw/binance/um/klines, resampled 1h->daily)"
            log.info(
                "Hourly data loaded for %d symbols, %d timestamps.",
                len(hourly_data),
                len(hourly_ts),
            )
            # Resample to daily
            symbol_data, timestamps = resample_to_daily(hourly_data, hourly_ts)
        except (FileNotFoundError, RuntimeError) as exc:
            log.warning("Real data load failed: %s", exc)
            log.warning("Falling back to synthetic daily data.")
            args.synthetic = True

    if args.synthetic:
        log.info("Generating synthetic DAILY data for %d symbols...", len(symbols))
        rng = np.random.default_rng(42)
        n_bars = 1500  # ~4 years of daily bars
        timestamps = np.arange(n_bars, dtype=np.int64) * 86400 * 1000 + int(
            datetime(2021, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
        )
        symbol_data = {}
        for sym in symbols:
            drift = rng.normal(0.0005, 0.001)  # daily drift/vol
            vol = rng.uniform(0.02, 0.08)
            shocks = rng.normal(drift, vol, n_bars)
            price = 100.0 * np.exp(np.cumsum(shocks))
            symbol_data[sym] = price
        data_source = "synthetic (daily Geometric Brownian Motion)"
        log.info("Synthetic data generated: %d bars x %d symbols", n_bars, len(symbols))

    # ------------------------------------------------------------------
    # 2. Run strategy with daily config
    # ------------------------------------------------------------------
    log.info("Running backtest_cross_sectional_momentum() with DAILY config...")

    daily_config = {
        "data_frequency": "daily",  # triggers daily defaults in the backtest
        "taker_fee": 0.0004,        # 4bps taker
        "slippage": 0.0001,         # 1bps slippage
    }

    result = backtest_cross_sectional_momentum(
        symbol_data=symbol_data,
        timestamps=timestamps,
        prices=symbol_data,
        config=daily_config,
    )

    log.info(
        "Backtest complete: net_return=%.4f, sharpe=%.2f, pf=%.2f, max_dd=%.4f, "
        "n_trades=%d",
        result.net_return,
        result.sharpe,
        result.profit_factor,
        result.max_drawdown,
        result.n_trades,
    )

    # ------------------------------------------------------------------
    # 3. Build & save report
    # ------------------------------------------------------------------
    report = build_report(
        strategy_result=result,
        prices_aligned=symbol_data,
        timestamps=timestamps,
        data_source=data_source,
        n_symbols_loaded=len(symbol_data),
    )

    output_path = os.path.join(PROJECT_ROOT, args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    elapsed = time.time() - t0
    log.info("Report saved to %s (%.1fs)", output_path, elapsed)

    # Print summary
    print()
    print("=" * 70)
    print("  XSMOM DAILY BASELINE REPORT")
    print("=" * 70)
    print(f"  Data source:  {data_source}")
    print(f"  Period:       {report['data_range']['start']} -> {report['data_range']['end']}")
    print(f"  Bars:         {report['data_range']['n_bars']}")
    print(f"  Symbols:      {len(symbol_data)} / {len(symbols)}")
    print(f"  Windows:      {report['strategy_config']['momentum_windows']}")
    print(f"  Rebalance:    every {report['strategy_config']['rebalance_bars']} bars")
    print()
    print(f"  Strategy:")
    print(f"    Net return:   {report['strategy_performance']['net_return']:.4f}  ({'+' if report['strategy_performance']['net_return'] >= 0 else ''}{report['strategy_performance']['net_return']*100:.2f}%)")
    print(f"    Sharpe:       {report['strategy_performance']['sharpe']:.2f}")
    print(f"    Profit factor:{report['strategy_performance']['profit_factor']:.2f}")
    print(f"    Max drawdown: {report['strategy_performance']['max_drawdown']*100:.2f}%")
    print(f"    Trades:       {report['strategy_performance']['n_trades']} ({report['strategy_performance']['n_long']}L / {report['strategy_performance']['n_short']}S)")
    print()
    beats = report["comparisons"]
    print(f"  Verdict:       {report['verdict']}")
    print(f"  Beats no-trade:     {beats['outperforms_no_trade']}")
    print(f"  Beats BTC buy-hold: {beats['outperforms_buy_and_hold_btc']}")
    print(f"  Beats equal-weight: {beats['outperforms_equal_weight']}")
    print(f"  Beats random:       {beats['outperforms_random_ranking']}")
    print(f"  Reason: {report['verdict_reason']}")
    print("=" * 70)

    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
