#!/usr/bin/env python3
"""Factor Sprint — deterministic alpha evaluation.

Loads real 1h OHLCV, computes 12 alpha factors, evaluates cross-sectional
Rank‑IC and top‑bottom spread, writes ALPHA_LEADERBOARD.csv.

Usage:
    PYTHONPATH=. .venv/bin/python3 scripts/factor_sprint.py [--gpu]
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

# ----------------------------------------------------------------------
# Project setup – make sure the repo root is on sys.path
# ----------------------------------------------------------------------
PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_ROOT)

# ----------------------------------------------------------------------
# Imports – all of these live in alphaforge/factors/
# ----------------------------------------------------------------------
from alphaforge.factors.loader import (
    load_1h_ohlcv,
    load_1h_ohlcv_gpu,
    load_or_build_aligned_panel,
    load_or_build_aligned_panel_gpu,
)
from alphaforge.factors.factors import FACTOR_REGISTRY, compute_all_factors
from alphaforge.factors.leaderboard import write_alpha_leaderboard
from alphaforge.factors.evaluation import (
    compute_forward_returns,
    evaluate_factor,
)
import signal

# ----------------------------------------------------------------------
# Timeout helper for factor evaluation – prevents a single factor from
# hanging the whole run.  Uses the POSIX alarm signal (works on Linux).
# ----------------------------------------------------------------------
class TimeoutException(Exception):
    pass

def _handle_timeout(signum, frame):
    raise TimeoutException()

# Guardrail – max seconds a single factor evaluation may take
EVAL_TIMEOUT = 5


def evaluate_factor_with_timeout(factor_name, scores, fwd_returns, direction):
    """Wrap evaluate_factor with a POSIX alarm timeout.
    Returns an empty list on timeout, printing a warning.
    """
    def _handler(signum, frame):
        raise TimeoutException()
    signal.signal(signal.SIGALRM, _handler)
    signal.alarm(EVAL_TIMEOUT)
    try:
        return evaluate_factor(factor_name, scores, fwd_returns, direction)
    except TimeoutException:
        print(f"  {factor_name}: evaluation timed out after {EVAL_TIMEOUT}s")
        return []
    finally:
        signal.alarm(0)


import psutil
import os
from tqdm import tqdm

import pandas as pd

# ----------------------------------------------------------------------
# Command‑line flags
# ----------------------------------------------------------------------
parser = argparse.ArgumentParser(description="FACTOR SPRINT – deterministic alpha evaluation")
parser.add_argument("--gpu", action="store_true", help="Use ROCm GPU (cuDF) for data loading")
args = parser.parse_args()

# ----------------------------------------------------------------------
# Main routine – largely identical to the original script but with a GPU
# branch for the heavy I/O section.  All downstream evaluation remains
# CPU‑only; if you want a full GPU pipeline you’ll need to port the
# evaluation logic (see README.md for guidance).
# ----------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("FACTOR SPRINT — Deterministic Alpha Evaluation")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)
    run_start = time.time()

    # ── STEP 1: Load data ──────────────────────────────────────────
    print("\n[1/5] Loading 1h OHLCV from data lake...")
    loader_start = time.time()
    if args.gpu:
        data_1h = load_1h_ohlcv_gpu()
    else:
        data_1h = load_1h_ohlcv()
    loader_time = time.time() - loader_start
    loaded = {s: df for s, df in data_1h.items() if not df.empty}
    print(f"  Loaded {len(loaded)}/{len(data_1h)} symbols in {loader_time:.2f}s")
    # Show a quick progress bar for the symbols that were actually loaded
    with tqdm(total=len(loaded), desc="Loaded symbols") as pbar:
        for _ in loaded:
            pbar.update(1)


    if len(loaded) < 5:
        print("  FATAL: Fewer than 5 symbols loaded. Aborting.")
        sys.exit(1)

    # ── STEP 2: Build aligned panels ───────────────────────────────
    print("\n[2/5] Building aligned panels...")
    t0 = time.time()
    if args.gpu:
        panels_1h = load_or_build_aligned_panel_gpu(loaded)
        # Convert cuDF frames to pandas for downstream evaluation
        panels_1h = {k: v.to_pandas() for k, v in panels_1h.items()}
    else:
        panels_1h = load_or_build_aligned_panel(loaded)

    print(f"  Panel columns: {list(panels_1h.keys())}")
    print(f"  Built in {time.time()-t0:.1f}s")
    if "close" in panels_1h:
        print(f"  Timestamps: {len(panels_1h['close'])}")
        print(f"  Symbols: {len(panels_1h['close'].columns)}")
        print(
            f"  Date range: {panels_1h['close'].index.min()} to {panels_1h['close'].index.max()}"
        )

    # ── STEP 3: Compute forward returns ────────────────────────────
    print("\n[3/5] Computing forward returns...")
    fr_start = time.time()
    close = panels_1h.get("close")
    if close is None or close.empty:
        print("  FATAL: No close price panel. Aborting.")
        sys.exit(1)
    fwd_returns = compute_forward_returns(close, horizons=[1, 4, 12, 24])
    fr_time = time.time() - fr_start
    for h, fr in fwd_returns.items():
        valid_count = fr.notna().sum().sum()
        print(f"  Horizon {h}h: {valid_count} valid forward returns")
    print(f"  Forward return computation took {fr_time:.2f}s")

    # ── STEP 4: Compute factors ────────────────────────────────────
    print("\n[4/5] Computing 12 alpha factors...")
    factor_scores = compute_all_factors(panels_1h)
    print(f"  Computed {len(factor_scores)} factors: {list(factor_scores.keys())}")

    for name, scores in factor_scores.items():
        valid = scores.notna().sum().sum()
        total = scores.shape[0] * scores.shape[1]
        print(f"  {name}: {valid}/{total} valid values ({100*valid/total:.1f}%)")

    # ── STEP 5: Evaluate all factors ───────────────────────────────
    print("\n[5/5] Evaluating factors across horizons...")
    all_results = []

    for factor_name, scores in tqdm(factor_scores.items(), desc="Evaluating factors"):

        if factor_name not in FACTOR_REGISTRY:
            continue
        direction, _ = FACTOR_REGISTRY[factor_name]
        results = evaluate_factor_with_timeout(factor_name, scores, fwd_returns, direction)
        all_results.extend(results)
        # Print summary
        pass_count = sum(1 for r in results if r["pass_fail"] == "PASS")
        watch_count = sum(1 for r in results if r["pass_fail"] == "WATCH")
        fail_count = sum(1 for r in results if r["pass_fail"] == "FAIL")
        print(f"  {factor_name}: PASS={pass_count} WATCH={watch_count} FAIL={fail_count}")

    # ── WRITE OUTPUT ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("WRITING ALPHA_LEADERBOARD.csv")
    print("=" * 60)

    output_path = write_alpha_leaderboard(all_results)
    print(f"\nDone. Output: {output_path}")
    print(f"Total evaluation rows: {len(all_results)}")

    # Print top results
    pass_results = [r for r in all_results if r["pass_fail"] == "PASS"]
    watch_results = [r for r in all_results if r["pass_fail"] == "WATCH"]

    if pass_results:
        print("\n--- PASS candidates ---")
        for r in sorted(pass_results, key=lambda x: abs(x.get("mean_rank_ic", 0)), reverse=True)[:5]:
            print(f"  {r['factor_name']} ({r['horizon']}h): IC={r['mean_rank_ic']:.4f}, IC_IR={r['ic_ir']:.4f}")

    if watch_results:
        print("\n--- WATCH candidates ---")
        for r in sorted(watch_results, key=lambda x: abs(x.get("mean_rank_ic", 0)), reverse=True)[:5]:
            print(f"  {r['factor_name']} ({r['horizon']}h): IC={r['mean_rank_ic']:.4f}, IC_IR={r['ic_ir']:.4f}")

    print(f"\nCompleted: {datetime.now().isoformat()}")
    # ------------------------------------------------------------------
    # Performance diagnostics
    # ------------------------------------------------------------------
    total_time = time.time() - run_start
    proc = psutil.Process(os.getpid())
    mem_mb = proc.memory_info().rss / (1024 * 1024)
    cpu_pct = psutil.cpu_percent(interval=0.1)
    print("\n=== PERFORMANCE DIAGNOSTICS ===")
    print(f"Total wall‑clock time: {total_time:.2f}s")
    print(f"Peak RAM usage: {mem_mb:.1f} MiB")
    print(f"CPU % (instant): {cpu_pct:.1f}%")



if __name__ == "__main__":
    main()
