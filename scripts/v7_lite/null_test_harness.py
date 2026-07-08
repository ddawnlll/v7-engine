"""
#286 — Null Test Harness

Validates the validator by running shuffled (random) signals through
the same pipeline that evaluates real alphas. If shuffled signals
get "promoted" (positive cost-adjusted R), the validator is BROKEN.

Usage:
    PYTHONPATH=simulation/src:alphaforge/src:v7/src:. python3 scripts/v7_lite/null_test_harness.py --iterations 30

Output:
    reports/v7_lite/null_test/null_test_results.json
    reports/v7_lite/null_test/NULL_TEST_REPORT.md
    reports/v7_lite/null_test/null_test.log
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "simulation/src"))
sys.path.insert(0, str(REPO_ROOT / "alphaforge/src"))
sys.path.insert(0, str(REPO_ROOT / "v7/src"))
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "reports/v7_lite/null_test"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(OUTPUT_DIR / "null_test.log", mode="w"),
    ],
)
logger = logging.getLogger("null_test")


def load_real_signals() -> pd.DataFrame:
    """Load the real factor signal events."""
    csv_path = REPO_ROOT / "reports/v7_lite/p0_primitives/factor_events/FACTOR_SIGNAL_EVENTS.csv"
    df = pd.read_csv(csv_path)
    logger.info("Loaded %d real signal events", len(df))
    return df


def shuffle_signals(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Shuffle direction labels while preserving all other columns.
    
    This creates a null distribution: same timestamps, same symbols,
    same prices — but random directions. Any "edge" found here is false positive.
    """
    shuffled = df.copy()
    rng = np.random.RandomState(seed)
    
    # Shuffle direction column
    directions = shuffled["direction"].values.copy()
    rng.shuffle(directions)
    shuffled["direction"] = directions
    
    # Also shuffle score/signal_value to break any score-direction correlation
    scores = shuffled["score"].values.copy()
    rng.shuffle(scores)
    shuffled["score"] = scores
    shuffled["signal_value"] = scores
    
    return shuffled


def run_bridge_on_signals(
    events_df: pd.DataFrame,
    label: str = "",
) -> dict | None:
    """Run central sim bridge on a set of signal events.
    
    Returns summary metrics or None if failed.
    """
    from experiments.v7_lite.central_sim_bridge_p0 import (
        load_signal_events,
        load_ohlcv_panels,
        default_profile,
        run_batch_central_simulation,
    )
    
    panel_cache = str(REPO_ROOT / "cache/factor_sprint")
    
    # Load OHLCV panels
    try:
        ohlcv_panels = load_ohlcv_panels(panel_cache)
    except FileNotFoundError as e:
        logger.error("Panel cache not found: %s", e)
        return None
    
    # Write shuffled events to temp file
    temp_csv = OUTPUT_DIR / f"_temp_events_{label}.csv"
    events_df.to_csv(temp_csv, index=False)
    
    # Build profile
    profile = default_profile("SCALP")
    
    # Run bridge
    temp_output = OUTPUT_DIR / f"_temp_results_{label}.csv"
    try:
        run_batch_central_simulation(
            events_path=str(temp_csv),
            ohlcv_panels=ohlcv_panels,
            profile=profile,
            output_path=str(temp_output),
        )
    except Exception as e:
        logger.error("Bridge failed for %s: %s", label, e)
        return None
    
    # Read results
    if not temp_output.exists():
        logger.error("No output for %s", label)
        return None
    
    results = pd.read_csv(temp_output)
    
    # Compute metrics
    long_r = pd.to_numeric(results["central_long_r_net"], errors="coerce")
    short_r = pd.to_numeric(results["central_short_r_net"], errors="coerce")
    
    # Directional R (matching declared direction)
    dir_r = []
    for _, row in results.iterrows():
        if row["direction"] == "LONG":
            dir_r.append(row["central_long_r_net"])
        else:
            dir_r.append(row["central_short_r_net"])
    
    dir_r = pd.Series(dir_r).dropna()
    
    if len(dir_r) == 0:
        return None
    
    # Cost estimate from Truth V6 P0
    cost_per_trade = 0.052388
    
    raw_mean_R = float(dir_r.mean())
    cost_adj_R = raw_mean_R - cost_per_trade
    
    # Count promotions
    # Promotion criteria: cost_adj_R > 0 AND trade_count >= 200
    promoted = cost_adj_R > 0 and len(dir_r) >= 200
    
    # Best action distribution
    action_dist = results["central_best_action"].value_counts().to_dict()
    
    # Cleanup temp files
    temp_csv.unlink(missing_ok=True)
    temp_output.unlink(missing_ok=True)
    
    return {
        "label": label,
        "trade_count": len(dir_r),
        "raw_mean_R": round(raw_mean_R, 6),
        "cost_adjusted_R": round(cost_adj_R, 6),
        "2x_cost_R": round(raw_mean_R - 2 * cost_per_trade, 6),
        "win_rate": round(float((dir_r > 0).mean()), 4),
        "promoted": promoted,
        "best_action_distribution": action_dist,
    }


def run_real_baseline() -> dict | None:
    """Run the real (unshuffled) signals as baseline comparison."""
    logger.info("Running real signal baseline...")
    real_df = load_real_signals()
    return run_bridge_on_signals(real_df, label="real_baseline")


def run_null_test(n_iterations: int = 30) -> dict:
    """Run N shuffle iterations and collect results."""
    real_df = load_real_signals()
    
    null_results = []
    promotion_count = 0
    
    for i in range(n_iterations):
        seed = 42 + i
        shuffled = shuffle_signals(real_df, seed=seed)
        
        logger.info("Null test iteration %d/%d (seed=%d)", i + 1, n_iterations, seed)
        result = run_bridge_on_signals(shuffled, label=f"null_{i:03d}")
        
        if result:
            null_results.append(result)
            if result["promoted"]:
                promotion_count += 1
                logger.warning("  ITERATION %d: PROMOTED! cost_adj_R=%.6f", i, result["cost_adjusted_R"])
            else:
                logger.info("  not promoted: cost_adj_R=%.6f trades=%d",
                           result["cost_adjusted_R"], result["trade_count"])
    
    return {
        "n_iterations": n_iterations,
        "n_completed": len(null_results),
        "n_promoted": promotion_count,
        "false_positive_rate": promotion_count / max(len(null_results), 1),
        "null_results": null_results,
    }


def main():
    parser = argparse.ArgumentParser(description="Null Test Harness - #286")
    parser.add_argument("--iterations", type=int, default=30,
                        help="Number of shuffle iterations (default: 30)")
    args = parser.parse_args()
    
    t0 = time.time()
    logger.info("=" * 60)
    logger.info("NULL TEST HARNESS — Issue #286")
    logger.info("Iterations: %d", args.iterations)
    logger.info("=" * 60)
    
    # Step 1: Run real baseline
    logger.info("\n--- Step 1: Real signal baseline ---")
    real_baseline = run_real_baseline()
    if real_baseline:
        logger.info("  Real baseline: cost_adj_R=%.6f, trades=%d, promoted=%s",
                    real_baseline["cost_adjusted_R"], real_baseline["trade_count"],
                    real_baseline["promoted"])
    
    # Step 2: Run null test
    logger.info("\n--- Step 2: Null test (%d iterations) ---", args.iterations)
    null_test = run_null_test(args.iterations)
    
    elapsed = time.time() - t0
    
    # Step 3: Write results
    summary = {
        "run_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "iterations": args.iterations,
        "real_baseline": real_baseline,
        "null_test": {
            "n_completed": null_test["n_completed"],
            "n_promoted": null_test["n_promoted"],
            "false_positive_rate": null_test["false_positive_rate"],
        },
        "null_cost_adj_R_values": [r["cost_adjusted_R"] for r in null_test["null_results"]],
        "null_trade_counts": [r["trade_count"] for r in null_test["null_results"]],
        "elapsed_seconds": round(elapsed, 2),
    }
    
    # Determine verdict
    fpr = null_test["false_positive_rate"]
    if fpr <= 0.05:
        verdict = "TEMIZ"
        verdict_detail = f"False positive rate {fpr:.1%} is within acceptable range (<=5%). Validator is trustworthy."
    elif fpr <= 0.10:
        verdict = "TEMIZ_MARGIN"
        verdict_detail = f"False positive rate {fpr:.1%} is marginal (5-10%). Validator needs monitoring but is usable."
    else:
        verdict = "KIRLI"
        verdict_detail = f"False positive rate {fpr:.1%} is UNACCEPTABLE (>10%). Validator is BROKEN. Pipeline promotes noise."
    
    summary["verdict"] = verdict
    summary["verdict_detail"] = verdict_detail
    
    # Write JSON
    json_path = OUTPUT_DIR / "null_test_results.json"
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    
    # Write report
    md_path = OUTPUT_DIR / "NULL_TEST_REPORT.md"
    with open(md_path, "w") as f:
        f.write("# Null Test Harness Report — Issue #286\n\n")
        f.write(f"**Generated:** {summary['run_timestamp']}\n\n")
        f.write(f"## Configuration\n\n")
        f.write(f"- Iterations: {args.iterations}\n")
        f.write(f"- Real signal count: {real_baseline['trade_count'] if real_baseline else 'N/A'}\n")
        f.write(f"- Cost per trade: 0.052388R (from Truth V6 P0)\n")
        f.write(f"- Promotion criteria: cost_adj_R > 0 AND trade_count >= 200\n\n")
        
        f.write(f"## Verdict: {verdict}\n\n")
        f.write(f"{verdict_detail}\n\n")
        
        f.write(f"## Real Baseline\n\n")
        if real_baseline:
            f.write(f"- Trade count: {real_baseline['trade_count']}\n")
            f.write(f"- Raw mean R: {real_baseline['raw_mean_R']:.6f}\n")
            f.write(f"- Cost-adjusted R: {real_baseline['cost_adjusted_R']:.6f}\n")
            f.write(f"- Promoted: {real_baseline['promoted']}\n\n")
        
        f.write(f"## Null Test Results\n\n")
        f.write(f"- Completed: {null_test['n_completed']}/{args.iterations}\n")
        f.write(f"- Promoted: {null_test['n_promoted']}\n")
        f.write(f"- False positive rate: {fpr:.1%}\n\n")
        
        f.write(f"### Per-Iteration Results\n\n")
        f.write(f"| Iter | Trades | Raw R | Cost-Adj R | Promoted |\n")
        f.write(f"|------|--------|-------|------------|----------|\n")
        for i, r in enumerate(null_test["null_results"]):
            f.write(f"| {i+1} | {r['trade_count']} | {r['raw_mean_R']:.6f} | {r['cost_adjusted_R']:.6f} | {'YES' if r['promoted'] else 'no'} |\n")
        
        f.write(f"\n## Cost-Adj R Distribution (null)\n\n")
        null_r = [r["cost_adjusted_R"] for r in null_test["null_results"]]
        if null_r:
            f.write(f"- Mean: {np.mean(null_r):.6f}\n")
            f.write(f"- Std: {np.std(null_r):.6f}\n")
            f.write(f"- Min: {np.min(null_r):.6f}\n")
            f.write(f"- Max: {np.max(null_r):.6f}\n")
            f.write(f"- P(null R > 0): {np.mean(np.array(null_r) > 0):.1%}\n")
    
    logger.info("=" * 60)
    logger.info("NULL TEST COMPLETE")
    logger.info("  Verdict: %s", verdict)
    logger.info("  False positive rate: %.1f%%", fpr * 100)
    logger.info("  Real baseline cost_adj_R: %.6f",
                real_baseline["cost_adjusted_R"] if real_baseline else 0)
    logger.info("=" * 60)
    
    return summary


if __name__ == "__main__":
    try:
        result = main()
        print(json.dumps({"verdict": result["verdict"], "fpr": result["null_test"]["false_positive_rate"]}, indent=2))
    except Exception as e:
        logger.exception("FAILED_WITH_TRACEBACK")
        sys.exit(1)
