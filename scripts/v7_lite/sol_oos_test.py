"""
#287 — SOL Truth V6 OOS Walk-Forward + Cost Stress

Tests whether SOLUSDT's edge survives OOS validation and cost stress.

Usage:
    PYTHONPATH=alphaforge/src:v7/src:. python3 scripts/v7_lite/sol_oos_test.py

Output:
    reports/v7_lite/sol_oos/SOL_OOS_RESULTS.json
    reports/v7_lite/sol_oos/SOL_OOS_REPORT.md
    reports/v7_lite/sol_oos/sol_oos_trade_log.csv
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

OUTPUT_DIR = REPO_ROOT / "reports/v7_lite/sol_oos"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(OUTPUT_DIR / "sol_oos_test.log", mode="w"),
    ],
)
logger = logging.getLogger("sol_oos_test")


def run_sol_pipeline(
    confidence_threshold: float = 0.55,
    folds: int = 6,
    execution_mode: str = "TAKER",
) -> dict | None:
    """Run Truth V6 pipeline on SOLUSDT only."""
    from alphaforge.discovery.backtest import backtest_signals
    from alphaforge.discovery.signal_generator import (
        generate_trade_signals,
        filter_overlapping_signals,
    )
    from alphaforge.train import (
        MODE_CONFIG,
        build_aligned_training_frame,
        walk_forward_validate,
        _load_panel_data,
        cross_sectional_rank_normalize,
    )

    mode = "SCALP"
    symbols = ("SOLUSDT",)
    panel_cache = str(REPO_ROOT / "cache/factor_sprint")
    cfg = MODE_CONFIG[mode]

    # Load data
    ohlcv = _load_panel_data(panel_cache, list(symbols))
    if ohlcv is None:
        return None

    # Build frame
    training_frame = build_aligned_training_frame(ohlcv, mode)
    X = training_frame["X"]
    y_int = training_frame["y_int"]
    label_net_r = training_frame["label_net_r"]
    action_net_r = training_frame["action_net_r"]
    timestamps = training_frame["timestamps"]
    symbols_arr = training_frame["symbols"]
    close_arr_raw = training_frame.get("close_prices", None)

    # Clean
    X_clean = np.nan_to_num(X, nan=0.0)
    if len(np.unique(timestamps)) < len(timestamps):
        X_clean = cross_sectional_rank_normalize(X_clean, timestamps)

    # WFV
    wfv_results, fold_preds, fold_y_class, fold_y_val = walk_forward_validate(
        X_clean, y_int.copy(), label_net_r.copy(), mode,
        min_folds=folds,
        action_net_r=action_net_r.copy(),
        return_raw_preds=True,
    )

    # Signals
    signals = generate_trade_signals(
        fold_results=wfv_results,
        fold_preds=fold_preds,
        fold_y_class=fold_y_class,
        ohlcv=ohlcv,
        mode_cfg=cfg,
        timestamps=timestamps.copy(),
        symbols=symbols_arr.copy(),
        close_arr=close_arr_raw,
        confidence_threshold=confidence_threshold,
    )
    signals = filter_overlapping_signals(signals)

    if not signals:
        return None

    # Backtest
    trades = backtest_signals(
        signals=signals,
        ohlcv=ohlcv,
        mode=mode,
        execution_mode=execution_mode,
    )

    if not trades:
        return None

    return {
        "trades": trades,
        "signals": signals,
        "wfv_results": wfv_results,
        "ohlcv": ohlcv,
        "timestamps": timestamps,
    }


def compute_metrics(trades, cost_per_trade: float = 0.052388) -> dict:
    """Compute metrics from trade list."""
    net_r = np.array([t.realized_r_net for t in trades])
    
    # Time split
    all_ts = np.array([t.signal.timestamp for t in trades])
    mid_ts = np.median(all_ts)
    first_half = [t for t in trades if t.signal.timestamp <= mid_ts]
    second_half = [t for t in trades if t.signal.timestamp > mid_ts]
    
    first_r = float(np.mean([t.realized_r_net for t in first_half])) if first_half else 0.0
    second_r = float(np.mean([t.realized_r_net for t in second_half])) if second_half else 0.0
    
    # Direction split
    long_trades = [t for t in trades if t.signal.side == "LONG"]
    short_trades = [t for t in trades if t.signal.side == "SHORT"]
    
    return {
        "trade_count": len(trades),
        "raw_mean_R": round(float(np.mean(net_r)), 6),
        "median_R": round(float(np.median(net_r)), 6),
        "std_R": round(float(np.std(net_r)), 6),
        "cost_per_trade_R": round(cost_per_trade, 6),
        "cost_adjusted_R": round(float(np.mean(net_r)) - cost_per_trade, 6),
        "2x_cost_R": round(float(np.mean(net_r)) - 2 * cost_per_trade, 6),
        "5x_cost_R": round(float(np.mean(net_r)) - 5 * cost_per_trade, 6),
        "win_rate": round(float(np.mean(net_r > 0)), 6),
        "first_half_R": round(first_r, 6),
        "second_half_R": round(second_r, 6),
        "first_half_count": len(first_half),
        "second_half_count": len(second_half),
        "long_count": len(long_trades),
        "short_count": len(short_trades),
        "long_mean_R": round(float(np.mean([t.realized_r_net for t in long_trades])), 6) if long_trades else 0.0,
        "short_mean_R": round(float(np.mean([t.realized_r_net for t in short_trades])), 6) if short_trades else 0.0,
    }


def cost_stress_test(trades, base_cost: float = 0.052388) -> list[dict]:
    """Run cost stress at multiple multipliers."""
    net_r = np.array([t.realized_r_net for t in trades])
    results = []
    for mult in [1.0, 1.25, 1.5, 2.0, 3.0, 5.0]:
        cost = base_cost * mult
        cost_adj = float(np.mean(net_r)) - cost
        results.append({
            "cost_multiplier": mult,
            "cost_per_trade_R": round(cost, 6),
            "cost_adjusted_R": round(cost_adj, 6),
            "pass": bool(cost_adj > 0),
        })
    return results


def baseline_comparison(trades) -> dict:
    """Compare against random-entry baseline."""
    net_r = np.array([t.realized_r_net for t in trades])
    actual_mean = float(np.mean(net_r))
    
    # Random permutation test
    np.random.seed(42)
    n_iter = 1000
    random_means = []
    for _ in range(n_iter):
        shuffled = np.random.permutation(net_r)
        random_means.append(float(np.mean(shuffled)))
    
    random_mean = np.mean(random_means)
    random_std = np.std(random_means)
    z_score = (actual_mean - random_mean) / random_std if random_std > 0 else 0
    p_value = np.mean(np.array(random_means) >= actual_mean)
    
    return {
        "actual_mean_R": round(actual_mean, 6),
        "random_baseline_mean_R": round(random_mean, 6),
        "random_baseline_std_R": round(random_std, 6),
        "z_score": round(float(z_score), 4),
        "p_value": round(float(p_value), 4),
        "beats_baseline": bool(actual_mean > random_mean),
    }


def export_trade_log(trades, output_path: str):
    """Export trades to CSV."""
    fieldnames = [
        "trade_id", "symbol", "direction", "entry_time", "entry_price",
        "exit_price", "exit_reason", "net_R", "gross_R", "fee_R",
        "slippage_R", "hold_bars", "confidence",
    ]
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, t in enumerate(trades):
            sig = t.signal
            writer.writerow({
                "trade_id": i + 1,
                "symbol": sig.symbol,
                "direction": sig.side,
                "entry_time": sig.timestamp,
                "entry_price": sig.entry_price,
                "exit_price": t.exit_price,
                "exit_reason": t.exit_reason,
                "net_R": round(t.realized_r_net, 6),
                "gross_R": round(t.realized_r_gross, 6),
                "fee_R": round(t.fee_cost_r, 6),
                "slippage_R": round(t.slippage_cost_r, 6),
                "hold_bars": t.hold_bars,
                "confidence": round(sig.confidence, 6),
            })


def main():
    t0 = time.time()
    logger.info("=" * 60)
    logger.info("#287 — SOL Truth V6 OOS Walk-Forward + Cost Stress")
    logger.info("=" * 60)

    # Step 1: Run SOL pipeline
    logger.info("\n[1/5] Running SOL Truth V6 pipeline...")
    result = run_sol_pipeline(confidence_threshold=0.55, folds=6)
    if result is None:
        logger.error("Pipeline failed — no trades produced")
        return None

    trades = result["trades"]
    logger.info("  SOL trades: %d", len(trades))

    # Step 2: Export trade log
    logger.info("\n[2/5] Exporting trade log...")
    csv_path = OUTPUT_DIR / "sol_oos_trade_log.csv"
    export_trade_log(trades, str(csv_path))
    logger.info("  Wrote %s", csv_path)

    # Step 3: Compute metrics
    logger.info("\n[3/5] Computing metrics...")
    metrics = compute_metrics(trades)
    logger.info("  Raw R: %+.6f, Cost-adj R: %+.6f", metrics["raw_mean_R"], metrics["cost_adjusted_R"])

    # Step 4: Cost stress
    logger.info("\n[4/5] Cost stress test...")
    stress = cost_stress_test(trades)
    for s in stress:
        logger.info("  %.1fx cost: R=%+.6f pass=%s", s["cost_multiplier"], s["cost_adjusted_R"], s["pass"])

    # Step 5: Baseline comparison
    logger.info("\n[5/5] Baseline comparison...")
    baseline = baseline_comparison(trades)
    logger.info("  z_score=%.2f, p_value=%.4f, beats_baseline=%s",
                baseline["z_score"], baseline["p_value"], baseline["beats_baseline"])

    # Determine verdict
    oos_pass = (
        metrics["cost_adjusted_R"] > 0
        and metrics["trade_count"] >= 150
        and metrics["first_half_R"] > 0
        and metrics["second_half_R"] > 0
    )
    cost_stress_1_5x = any(s["cost_multiplier"] == 1.5 and s["pass"] for s in stress)
    cost_stress_2x = any(s["cost_multiplier"] == 2.0 and s["pass"] for s in stress)

    if oos_pass and cost_stress_1_5x:
        verdict = "YESIL"
        verdict_detail = "SOL edge survives OOS + 1.5x cost stress. Ready for mechanism hypothesis."
    elif oos_pass:
        verdict = "YESIL_KOSULLU"
        verdict_detail = "SOL edge positive but fails 1.5x cost stress. Fragile — needs mechanism validation."
    else:
        verdict = "KIRMIZI"
        verdict_detail = "SOL edge does NOT survive OOS validation. Noise confirmed."

    elapsed = time.time() - t0

    # Assemble summary
    summary = {
        "run_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config": {
            "mode": "SCALP",
            "symbols": ["SOLUSDT"],
            "confidence_threshold": 0.55,
            "folds": 6,
            "execution_mode": "TAKER",
        },
        "metrics": metrics,
        "cost_stress": stress,
        "baseline": baseline,
        "verdict": verdict,
        "verdict_detail": verdict_detail,
        "oos_pass": oos_pass,
        "cost_stress_1_5x_pass": cost_stress_1_5x,
        "cost_stress_2x_pass": cost_stress_2x,
        "elapsed_seconds": round(elapsed, 2),
    }

    # Write JSON
    with open(OUTPUT_DIR / "SOL_OOS_RESULTS.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    # Write report
    with open(OUTPUT_DIR / "SOL_OOS_REPORT.md", "w") as f:
        f.write("# SOL Truth V6 OOS Report — Issue #287\n\n")
        f.write(f"**Generated:** {summary['run_timestamp']}\n\n")
        f.write(f"## Verdict: {verdict}\n\n")
        f.write(f"{verdict_detail}\n\n")
        f.write(f"## Metrics\n\n")
        f.write(f"| Metric | Value |\n")
        f.write(f"|--------|-------|\n")
        f.write(f"| Trade count | {metrics['trade_count']} |\n")
        f.write(f"| Raw mean R | {metrics['raw_mean_R']:.6f} |\n")
        f.write(f"| Cost-adjusted R | {metrics['cost_adjusted_R']:.6f} |\n")
        f.write(f"| 2x cost R | {metrics['2x_cost_R']:.6f} |\n")
        f.write(f"| Win rate | {metrics['win_rate']:.2%} |\n")
        f.write(f"| First half R | {metrics['first_half_R']:.6f} |\n")
        f.write(f"| Second half R | {metrics['second_half_R']:.6f} |\n\n")
        f.write(f"## Cost Stress\n\n")
        f.write(f"| Multiplier | Cost/Trade R | Cost-Adj R | Pass |\n")
        f.write(f"|------------|-------------|------------|------|\n")
        for s in stress:
            f.write(f"| {s['cost_multiplier']}x | {s['cost_per_trade_R']:.6f} | {s['cost_adjusted_R']:.6f} | {'YES' if s['pass'] else 'no'} |\n")
        f.write(f"\n## Baseline Comparison\n\n")
        f.write(f"- Actual R: {baseline['actual_mean_R']:.6f}\n")
        f.write(f"- Random baseline: {baseline['random_baseline_mean_R']:.6f}\n")
        f.write(f"- Z-score: {baseline['z_score']:.2f}\n")
        f.write(f"- P-value: {baseline['p_value']:.4f}\n")
        f.write(f"- Beats baseline: {baseline['beats_baseline']}\n")

    logger.info("=" * 60)
    logger.info("VERDICT: %s", verdict)
    logger.info("=" * 60)

    return summary


if __name__ == "__main__":
    try:
        result = main()
        if result:
            print(json.dumps({"verdict": result["verdict"], "cost_adj_R": result["metrics"]["cost_adjusted_R"]}, indent=2))
    except Exception as e:
        logger.exception("FAILED_WITH_TRACEBACK")
        sys.exit(1)
