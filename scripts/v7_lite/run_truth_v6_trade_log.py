"""
P0.1 — Truth V6 Trade-Log Rerun/Export

Re-runs the discovery pipeline on real panel cache data and exports
per-trade results to CSV. This produces the missing Truth V6 trade-level
log that was never persisted from the original run.

Usage:
    PYTHONPATH=alphaforge/src:v7/src:. python3 scripts/v7_lite/run_truth_v6_trade_log.py

Output:
    reports/v7_lite/p0_primitives/truth_v6/truth_v6_trade_log.csv
    reports/v7_lite/p0_primitives/truth_v6/truth_v6_rerun_summary.json
"""

from __future__ import annotations

import csv
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "alphaforge/src"))
sys.path.insert(0, str(REPO_ROOT / "v7/src"))
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "reports/v7_lite/p0_primitives/truth_v6"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(OUTPUT_DIR / "truth_v6_rerun.log", mode="w"),
    ],
)
logger = logging.getLogger("truth_v6_rerun")


def run_truth_v6_trade_log():
    """Run the discovery pipeline on real data and export per-trade CSV."""
    from alphaforge.discovery import DiscoveryConfig
    from alphaforge.discovery.pipeline import run_discovery
    from alphaforge.discovery.backtest import backtest_signals, _build_profile
    from alphaforge.discovery.signal_generator import (
        generate_trade_signals,
        filter_overlapping_signals,
    )
    from alphaforge.train import (
        MODE_CONFIG,
        build_aligned_training_frame,
        load_cached_data,
        walk_forward_validate,
        _load_panel_data,
        collect_metrics,
        cross_sectional_rank_normalize,
    )

    t0 = time.time()

    # ── Configuration ──────────────────────────────────────────────────
    mode = "SCALP"
    symbols = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT")
    panel_cache = str(REPO_ROOT / "cache/factor_sprint")
    confidence_threshold = 0.55
    folds = 6
    execution_mode = "TAKER"

    cfg = MODE_CONFIG[mode]
    logger.info("Truth V6 Trade-Log Rerun")
    logger.info("Mode=%s, Symbols=%s, Threshold=%.2f, Folds=%d",
                mode, symbols, confidence_threshold, folds)

    # ── Step 1: Load OHLCV data from panel cache ──────────────────────
    logger.info("[1/8] Loading OHLCV data from panel cache...")
    ohlcv = _load_panel_data(panel_cache, list(symbols))
    if ohlcv is None:
        logger.error("Panel cache not found at %s", panel_cache)
        return None

    n_bars = len(ohlcv.get("close", []))
    logger.info("  Loaded %d bars", n_bars)

    # ── Step 2: Build aligned training frame ──────────────────────────
    logger.info("[2/8] Building aligned feature + label frame...")
    training_frame = build_aligned_training_frame(ohlcv, mode)
    X = training_frame["X"]
    y_int = training_frame["y_int"]
    label_net_r = training_frame["label_net_r"]
    action_net_r = training_frame["action_net_r"]
    timestamps = training_frame["timestamps"]
    symbols_arr = training_frame["symbols"]
    feat_names = training_frame["feature_names"]
    close_arr_raw = training_frame.get("close_prices", None)

    logger.info("  Frame: %d samples, %d features", len(X), len(feat_names))

    # ── Step 3: NaN→0 fill + rank normalization ───────────────────────
    logger.info("[3/8] NaN→0 fill + rank normalization...")
    X_clean = np.nan_to_num(X, nan=0.0)
    if len(np.unique(timestamps)) < len(timestamps):
        X_clean = cross_sectional_rank_normalize(X_clean, timestamps)
    y_clean = y_int.copy()
    label_net_clean = label_net_r.copy()
    action_net_clean = action_net_r.copy()
    ts_clean = timestamps.copy()
    sym_clean = symbols_arr.copy()

    # ── Step 4: Walk-forward validation ───────────────────────────────
    logger.info("[4/8] Walk-forward validation (%d folds)...", folds)
    t_wfv = time.time()
    wfv_results, fold_preds, fold_y_class, fold_y_val = walk_forward_validate(
        X_clean, y_clean, label_net_clean, mode,
        min_folds=folds,
        action_net_r=action_net_clean,
        return_raw_preds=True,
    )
    logger.info("  WFV done in %.1fs, %d folds", time.time() - t_wfv, len(wfv_results))

    # ── Step 5: Generate trade signals ────────────────────────────────
    logger.info("[5/8] Generating trade signals (threshold=%.2f)...", confidence_threshold)
    signals = generate_trade_signals(
        fold_results=wfv_results,
        fold_preds=fold_preds,
        fold_y_class=fold_y_class,
        ohlcv=ohlcv,
        mode_cfg=cfg,
        timestamps=ts_clean,
        symbols=sym_clean,
        close_arr=close_arr_raw,
        confidence_threshold=confidence_threshold,
    )
    signals = filter_overlapping_signals(signals)
    logger.info("  %d signals after overlap filtering", len(signals))

    if not signals:
        logger.error("No trade signals generated")
        return None

    # ── Step 6: Backtest signals → per-trade results ──────────────────
    logger.info("[6/8] Backtesting %d signals...", len(signals))
    t_bt = time.time()
    trades = backtest_signals(
        signals=signals,
        ohlcv=ohlcv,
        mode=mode,
        execution_mode=execution_mode,
    )
    logger.info("  %d trades in %.1fs", len(trades), time.time() - t_bt)

    if not trades:
        logger.error("No trades produced")
        return None

    # ── Step 7: Export per-trade CSV ──────────────────────────────────
    logger.info("[7/8] Exporting trade log to CSV...")
    csv_path = OUTPUT_DIR / "truth_v6_trade_log.csv"
    fieldnames = [
        "trade_id", "alpha_id", "symbol", "direction", "entry_time",
        "exit_time", "entry_price", "exit_price", "exit_reason",
        "atr", "stop_price", "target_price", "initial_risk",
        "gross_R", "fee_R", "slippage_R", "funding_R", "net_R",
        "hold_bars", "confidence", "model_score", "path_quality",
    ]

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, t in enumerate(trades):
            sig = t.signal
            writer.writerow({
                "trade_id": i + 1,
                "alpha_id": "discovery_pipeline_v6",
                "symbol": sig.symbol,
                "direction": sig.side,
                "entry_time": sig.timestamp,
                "exit_time": "",  # not directly available from BacktestTradeResult
                "entry_price": sig.entry_price,
                "exit_price": t.exit_price,
                "exit_reason": t.exit_reason,
                "atr": sig.atr,
                "stop_price": sig.stop_price,
                "target_price": sig.target_price,
                "initial_risk": sig.initial_risk,
                "gross_R": round(t.realized_r_gross, 6),
                "fee_R": round(t.fee_cost_r, 6),
                "slippage_R": round(t.slippage_cost_r, 6),
                "funding_R": round(t.funding_cost_r, 6),
                "net_R": round(t.realized_r_net, 6),
                "hold_bars": t.hold_bars,
                "confidence": sig.confidence,
                "model_score": sig.model_score,
                "path_quality": round(t.path_quality_score, 4),
            })

    logger.info("  Wrote %d trades to %s", len(trades), csv_path)

    # ── Step 8: Compute and export summary metrics ────────────────────
    logger.info("[8/8] Computing summary metrics...")

    net_r_arr = np.array([t.realized_r_net for t in trades])
    gross_r_arr = np.array([t.realized_r_gross for t in trades])
    fee_r_arr = np.array([t.fee_cost_r for t in trades])
    slippage_r_arr = np.array([t.slippage_cost_r for t in trades])

    # Cost estimates
    fee_per_trade = float(np.mean(fee_r_arr)) if len(fee_r_arr) > 0 else 0.0
    slippage_per_trade = float(np.mean(slippage_r_arr)) if len(slippage_r_arr) > 0 else 0.0
    estimated_cost_per_trade = fee_per_trade + slippage_per_trade

    # BTCUSDT_SHORT breakdown
    btc_short = [t for t in trades if t.signal.symbol == "BTCUSDT" and t.signal.side == "SHORT"]
    btc_short_net_r = np.mean([t.realized_r_net for t in btc_short]) if btc_short else 0.0
    btc_short_cost_adj = btc_short_net_r - estimated_cost_per_trade if btc_short else 0.0

    # Symbol breakdown
    sym_counts = {}
    for t in trades:
        sym_counts[t.signal.symbol] = sym_counts.get(t.signal.symbol, 0) + 1

    # Direction breakdown
    long_count = sum(1 for t in trades if t.signal.side == "LONG")
    short_count = sum(1 for t in trades if t.signal.side == "SHORT")

    # Cost-adjusted R
    cost_adjusted_r = float(np.mean(net_r_arr)) - estimated_cost_per_trade

    summary = {
        "run_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": mode,
        "symbols": list(symbols),
        "confidence_threshold": confidence_threshold,
        "folds": folds,
        "execution_mode": execution_mode,
        "panel_cache": panel_cache,
        "trade_count": len(trades),
        "raw_mean_R": round(float(np.mean(net_r_arr)), 6),
        "median_R": round(float(np.median(net_r_arr)), 6),
        "std_R": round(float(np.std(net_r_arr)), 6),
        "raw_total_R": round(float(np.sum(net_r_arr)), 6),
        "gross_mean_R": round(float(np.mean(gross_r_arr)), 6),
        "estimated_cost_per_trade_R": round(estimated_cost_per_trade, 6),
        "fee_per_trade_R": round(fee_per_trade, 6),
        "slippage_per_trade_R": round(slippage_per_trade, 6),
        "cost_adjusted_R": round(cost_adjusted_r, 6),
        "2x_cost_R": round(float(np.mean(net_r_arr)) - 2 * estimated_cost_per_trade, 6),
        "5x_cost_R": round(float(np.mean(net_r_arr)) - 5 * estimated_cost_per_trade, 6),
        "symbol_count": len(sym_counts),
        "symbol_breakdown": sym_counts,
        "direction_count": {"LONG": long_count, "SHORT": short_count},
        "BTCUSDT_SHORT_trade_count": len(btc_short),
        "BTCUSDT_SHORT_raw_R": round(float(btc_short_net_r), 6),
        "BTCUSDT_SHORT_cost_adjusted_R": round(float(btc_short_cost_adj), 6),
        "win_rate": round(float(np.mean(net_r_arr > 0)), 4),
        "signal_count": len(signals),
        "elapsed_seconds": round(time.time() - t0, 2),
    }

    # Write summary JSON
    summary_path = OUTPUT_DIR / "truth_v6_rerun_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info("  Wrote summary to %s", summary_path)

    # Write results markdown
    md_path = OUTPUT_DIR / "TRUTH_V6_TRADE_LOG_RERUN_RESULTS.md"
    with open(md_path, "w") as f:
        f.write(f"# Truth V6 Trade-Log Rerun Results\n\n")
        f.write(f"**Generated:** {summary['run_timestamp']}\n\n")
        f.write(f"## Configuration\n\n")
        f.write(f"- Mode: {mode}\n")
        f.write(f"- Symbols: {', '.join(symbols)}\n")
        f.write(f"- Confidence threshold: {confidence_threshold}\n")
        f.write(f"- Walk-forward folds: {folds}\n")
        f.write(f"- Execution mode: {execution_mode}\n\n")
        f.write(f"## Results\n\n")
        f.write(f"| Metric | Value |\n")
        f.write(f"|--------|-------|\n")
        f.write(f"| Trade count | {summary['trade_count']} |\n")
        f.write(f"| Raw mean R | {summary['raw_mean_R']:.6f} |\n")
        f.write(f"| Median R | {summary['median_R']:.6f} |\n")
        f.write(f"| Raw total R | {summary['raw_total_R']:.4f} |\n")
        f.write(f"| Estimated cost/trade | {summary['estimated_cost_per_trade_R']:.6f} |\n")
        f.write(f"| Cost-adjusted R | {summary['cost_adjusted_R']:.6f} |\n")
        f.write(f"| 2x cost R | {summary['2x_cost_R']:.6f} |\n")
        f.write(f"| 5x cost R | {summary['5x_cost_R']:.6f} |\n")
        f.write(f"| Win rate | {summary['win_rate']:.2%} |\n")
        f.write(f"| BTCUSDT SHORT trades | {summary['BTCUSDT_SHORT_trade_count']} |\n")
        f.write(f"| BTCUSDT SHORT raw R | {summary['BTCUSDT_SHORT_raw_R']:.6f} |\n")
        f.write(f"| BTCUSDT SHORT cost-adj R | {summary['BTCUSDT_SHORT_cost_adjusted_R']:.6f} |\n\n")
        f.write(f"## Symbol Breakdown\n\n")
        for sym, cnt in sorted(sym_counts.items()):
            f.write(f"- {sym}: {cnt} trades\n")
        f.write(f"\n## Direction Breakdown\n\n")
        f.write(f"- LONG: {long_count}\n")
        f.write(f"- SHORT: {short_count}\n\n")
        f.write(f"## Verdict\n\n")
        if summary['cost_adjusted_R'] > 0:
            f.write("**TRADE_LOG_CREATED_REAL_DATA** — cost-adjusted R is positive.\n")
        elif summary['raw_mean_R'] > 0:
            f.write("**TRADE_LOG_CREATED_PARTIAL** — raw R positive but cost-adjusted negative.\n")
        else:
            f.write("**TRADE_LOG_CREATED_PARTIAL** — trade log created but raw R negative.\n")
    logger.info("  Wrote results to %s", md_path)

    logger.info("=" * 60)
    logger.info("Truth V6 Trade-Log Rerun COMPLETE")
    logger.info("  Trades: %d", len(trades))
    logger.info("  Raw R: %+.6f", summary['raw_mean_R'])
    logger.info("  Cost-adj R: %+.6f", summary['cost_adjusted_R'])
    logger.info("  CSV: %s", csv_path)
    logger.info("=" * 60)

    return summary


if __name__ == "__main__":
    try:
        result = run_truth_v6_trade_log()
        if result is None:
            logger.error("FAILED: No result produced")
            sys.exit(1)
    except Exception as e:
        logger.exception("FAILED_WITH_TRACEBACK")
        sys.exit(1)
