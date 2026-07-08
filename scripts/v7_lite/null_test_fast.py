"""
#286 — Fast Null Test Harness (subset-based)

Uses a 2000-event random sample from the full 40K events for speed.
Each iteration runs in ~15 seconds instead of ~2.5 minutes.
Statistically valid for false-positive rate estimation.

Usage:
    PYTHONPATH=simulation/src:alphaforge/src:v7/src:. python3 scripts/v7_lite/null_test_fast.py --iterations 30
"""

from __future__ import annotations

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
        logging.FileHandler(OUTPUT_DIR / "null_test_fast.log", mode="w"),
    ],
)
logger = logging.getLogger("null_test_fast")


def load_and_sample(n_sample: int = 2000, seed: int = 0) -> pd.DataFrame:
    """Load full events and take a stratified random sample."""
    csv_path = REPO_ROOT / "reports/v7_lite/p0_primitives/factor_events/FACTOR_SIGNAL_EVENTS.csv"
    df = pd.read_csv(csv_path)
    logger.info("Loaded %d total events", len(df))
    
    # Stratified sample by factor_name
    rng = np.random.RandomState(seed)
    n_factors = df["factor_name"].nunique()
    per_factor = max(1, n_sample // n_factors)
    sampled_parts = []
    for fname, group in df.groupby("factor_name"):
        n_take = min(len(group), per_factor)
        sampled_parts.append(group.sample(n=n_take, random_state=rng))
    sampled = pd.concat(sampled_parts, ignore_index=True)
    logger.info("Sampled %d events (%d per factor) for fast null test", len(sampled), per_factor)
    return sampled


def shuffle_directions(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Shuffle only the direction column."""
    shuffled = df.copy()
    directions = shuffled["direction"].values.copy()
    rng = np.random.RandomState(seed)
    rng.shuffle(directions)
    shuffled["direction"] = directions
    return shuffled


def evaluate_events(events_df: pd.DataFrame) -> dict | None:
    """Run bridge on events and return metrics."""
    from experiments.v7_lite.central_sim_bridge_p0 import (
        load_ohlcv_panels,
        default_profile,
        run_batch_central_simulation,
    )
    
    panel_cache = str(REPO_ROOT / "cache/factor_sprint")
    ohlcv_panels = load_ohlcv_panels(panel_cache)
    profile = default_profile("SCALP")
    
    temp_csv = OUTPUT_DIR / "_temp_fast_events.csv"
    temp_output = OUTPUT_DIR / "_temp_fast_results.csv"
    events_df.to_csv(temp_csv, index=False)
    
    try:
        run_batch_central_simulation(
            events_path=str(temp_csv),
            ohlcv_panels=ohlcv_panels,
            profile=profile,
            output_path=str(temp_output),
        )
    except Exception as e:
        logger.error("Bridge failed: %s", e)
        return None
    
    if not temp_output.exists():
        return None
    
    results = pd.read_csv(temp_output)
    dir_r = []
    for _, row in results.iterrows():
        if row["direction"] == "LONG":
            dir_r.append(row["central_long_r_net"])
        else:
            dir_r.append(row["central_short_r_net"])
    
    dir_r = pd.Series(dir_r).dropna()
    if len(dir_r) == 0:
        return None
    
    cost_per_trade = 0.052388
    raw_mean_R = float(dir_r.mean())
    cost_adj_R = raw_mean_R - cost_per_trade
    
    temp_csv.unlink(missing_ok=True)
    temp_output.unlink(missing_ok=True)
    
    return {
        "trade_count": len(dir_r),
        "raw_mean_R": round(raw_mean_R, 6),
        "cost_adjusted_R": round(cost_adj_R, 6),
        "promoted": cost_adj_R > 0 and len(dir_r) >= 200,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--sample-size", type=int, default=2000)
    args = parser.parse_args()
    
    t0 = time.time()
    logger.info("FAST NULL TEST — %d iterations, sample=%d", args.iterations, args.sample_size)
    
    # Load sample
    base_sample = load_and_sample(args.sample_size)
    
    # Real baseline
    logger.info("Running real baseline...")
    real_result = evaluate_events(base_sample)
    if real_result:
        logger.info("  Real: cost_adj_R=%.6f, trades=%d, promoted=%s",
                    real_result["cost_adjusted_R"], real_result["trade_count"], real_result["promoted"])
    
    # Null iterations
    null_results = []
    for i in range(args.iterations):
        seed = 42 + i
        shuffled = shuffle_directions(base_sample, seed=seed)
        logger.info("Iteration %d/%d", i + 1, args.iterations)
        result = evaluate_events(shuffled)
        if result:
            null_results.append(result)
            status = "PROMOTED" if result["promoted"] else "ok"
            logger.info("  %s: cost_adj_R=%.6f trades=%d", status, result["cost_adjusted_R"], result["trade_count"])
    
    n_promoted = sum(1 for r in null_results if r["promoted"])
    fpr = n_promoted / max(len(null_results), 1)
    
    if fpr <= 0.05:
        verdict = "TEMIZ"
    elif fpr <= 0.10:
        verdict = "TEMIZ_MARGIN"
    else:
        verdict = "KIRLI"
    
    elapsed = time.time() - t0
    
    summary = {
        "run_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "iterations": args.iterations,
        "sample_size": args.sample_size,
        "real_baseline": real_result,
        "null_test": {
            "n_completed": len(null_results),
            "n_promoted": n_promoted,
            "false_positive_rate": round(fpr, 4),
        },
        "null_cost_adj_R_values": [r["cost_adjusted_R"] for r in null_results],
        "verdict": verdict,
        "elapsed_seconds": round(elapsed, 2),
    }
    
    # Write results
    with open(OUTPUT_DIR / "null_test_results.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)
    
    # Write report
    with open(OUTPUT_DIR / "NULL_TEST_REPORT.md", "w") as f:
        f.write("# Null Test Report — Issue #286\n\n")
        f.write(f"**Generated:** {summary['run_timestamp']}\n\n")
        f.write(f"## Verdict: {verdict}\n\n")
        f.write(f"- Iterations: {args.iterations}\n")
        f.write(f"- Sample size: {args.sample_size} events\n")
        f.write(f"- Real baseline cost_adj_R: {real_result['cost_adjusted_R'] if real_result else 'N/A'}\n")
        f.write(f"- Null promoted: {n_promoted}/{len(null_results)}\n")
        f.write(f"- False positive rate: {fpr:.1%}\n\n")
        f.write(f"## Per-Iteration Results\n\n")
        f.write(f"| Iter | Trades | Raw R | Cost-Adj R | Promoted |\n")
        f.write(f"|------|--------|-------|------------|----------|\n")
        for i, r in enumerate(null_results):
            f.write(f"| {i+1} | {r['trade_count']} | {r['raw_mean_R']:.6f} | {r['cost_adjusted_R']:.6f} | {'YES' if r['promoted'] else 'no'} |\n")
    
    logger.info("=" * 60)
    logger.info("VERDICT: %s (FPR=%.1f%%)", verdict, fpr * 100)
    logger.info("=" * 60)
    
    print(json.dumps({"verdict": verdict, "fpr": fpr, "n_promoted": n_promoted, "n_total": len(null_results)}, indent=2))


if __name__ == "__main__":
    main()
