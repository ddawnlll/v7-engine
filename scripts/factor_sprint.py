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
# Add the internal src directory to PYTHONPATH so that 'alphaforge' package resolves correctly
ALPHAFORGE_SRC = str(Path(PROJECT_ROOT, "alphaforge", "src").resolve())
sys.path.insert(0, ALPHAFORGE_SRC)

# ----------------------------------------------------------------------
# Imports – all of these live in alphaforge/factors/
# ----------------------------------------------------------------------
from alphaforge.factors.loader import (
    load_1h_ohlcv,
    load_1h_ohlcv_gpu,
    load_or_build_aligned_panel,
    load_or_build_aligned_panel_gpu,
    load_funding_rates,
    build_funding_panel,
)
from alphaforge.factors.factors import FACTOR_REGISTRY, compute_all_factors
from alphaforge.factors.leaderboard import write_alpha_leaderboard
from alphaforge.factors.evaluation import (
    compute_forward_returns,
    evaluate_factor,
)

# Guardrail – max seconds a single factor evaluation may take
EVAL_TIMEOUT = 30


def evaluate_factor_with_timeout(factor_name, scores, fwd_returns, direction):
    """Run evaluate_factor in a separate process with a timeout.
    Returns an empty list on timeout, printing a warning.
    """
    import concurrent.futures
    # Use a single-worker ProcessPoolExecutor for isolation
    with concurrent.futures.ProcessPoolExecutor(max_workers=1) as executor:
        future = executor.submit(evaluate_factor, factor_name, scores, fwd_returns, direction)
        try:
            return future.result(timeout=EVAL_TIMEOUT)
        except concurrent.futures.TimeoutError:
            print(f"  {factor_name}: evaluation timed out after {EVAL_TIMEOUT}s")
            return []



import psutil
import os
from tqdm import tqdm

import pandas as pd

# ----------------------------------------------------------------------
# Command‑line flags
# ----------------------------------------------------------------------
parser = argparse.ArgumentParser(description="FACTOR SPRINT – deterministic alpha evaluation")
parser.add_argument("--gpu", action="store_true", help="Use ROCm GPU (cuDF) for data loading (fallback to CPU if cuDF unavailable)")
parser.add_argument("--parallel", action="store_true", help="Evaluate factors in parallel using threads")
parser.add_argument("--test", action="store_true", help="Run in test mode with limited symbols and one‑year data")
args = parser.parse_args()
# When GPU flag is set, we no longer enforce test mode automatically.
# Users can combine --gpu with --test explicitly if they want a quick test run.
# The script will now run on the full dataset when --gpu is provided without --test.


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
    print("\n[1/6] Loading 1h OHLCV from data lake...")
    loader_start = time.time()
    if args.gpu:
        data_1h = load_1h_ohlcv_gpu()
    else:
        data_1h = load_1h_ohlcv()
    loader_time = time.time() - loader_start
    loaded = {s: df for s, df in data_1h.items() if not df.empty}
    if args.test:
        # Limit to first 2 symbols for quick test
        loaded = dict(list(loaded.items())[:2])
        print(f"  TEST MODE: restricting to {len(loaded)} symbols")
        # Slice each symbol's DataFrame to most recent year
        for sym, df in loaded.items():
            max_date = df.index.max()
            start_date = max_date - pd.Timedelta(days=365)
            loaded[sym] = df.loc[start_date:max_date]
        print(f"  TEST MODE: data limited to one year per symbol")
    print(f"  Loaded {len(loaded)}/{len(data_1h)} symbols in {loader_time:.2f}s")
    # Show a quick progress bar for the symbols that were actually loaded
    with tqdm(total=len(loaded), desc="Loaded symbols") as pbar:
        for _ in loaded:
            pbar.update(1)

    if len(loaded) < 5 and not args.test:
        print("  FATAL: Fewer than 5 symbols loaded. Aborting.")
        sys.exit(1)

    # ── STEP 2: Build aligned panels ───────────────────────────────
    print("\n[2/6] Building aligned panels...")
    t0 = time.time()
    if args.gpu:
        panels_1h = load_or_build_aligned_panel_gpu(loaded)
        # Convert cuDF frames to pandas for downstream evaluation (handle fallback)
        if panels_1h and not isinstance(next(iter(panels_1h.values())), pd.DataFrame):
            panels_1h = {k: v.to_pandas() if hasattr(v, 'to_pandas') else v for k, v in panels_1h.items()}
    else:
        panels_1h = load_or_build_aligned_panel(loaded)

    if args.test:
        # Restrict data to the most recent year
        max_date = panels_1h['close'].index.max()
        start_date = max_date - pd.Timedelta(days=365)
        panels_1h = {k: v.loc[start_date:max_date] if isinstance(v, pd.DataFrame) else v for k, v in panels_1h.items()}
        print(f"  TEST MODE: data limited to one year from {start_date.date()} to {max_date.date()}")
    print(f"  Panel columns: {list(panels_1h.keys())}")
    print(f"  Built in {time.time()-t0:.1f}s")
    if "close" in panels_1h:
        print(f"  Timestamps: {len(panels_1h['close'])}")
        print(f"  Symbols: {len(panels_1h['close'].columns)}")
        print(
            f"  Date range: {panels_1h['close'].index.min()} to {panels_1h['close'].index.max()}"
        )

    # ── STEP 3: Load funding rates ─────────────────────────────────
    print("\n[3/6] Loading funding rates...")
    fr_load_start = time.time()
    syms = list(loaded.keys())
    funding_data = load_funding_rates(symbols=syms)
    funding_loaded = {s: df for s, df in funding_data.items() if not df.empty}
    print(f"  Loaded funding rates for {len(funding_loaded)}/{len(syms)} symbols in {time.time()-fr_load_start:.2f}s")
    if funding_loaded:
        sample_sym = list(funding_loaded.keys())[0]
        print(f"  Sample ({sample_sym}): {len(funding_loaded[sample_sym])} records, "
              f"range: {funding_loaded[sample_sym].index.min()} to {funding_loaded[sample_sym].index.max()}")

    # Build funding panel aligned to OHLCV index
    if funding_loaded and "close" in panels_1h:
        funding_panel = build_funding_panel(funding_data, panels_1h["close"].index)
        panels_1h["funding_rate"] = funding_panel
        print(f"  Funding panel: {funding_panel.shape[0]} timestamps × {funding_panel.shape[1]} symbols")
    else:
        print("  WARNING: No funding rate data available, funding factors will be skipped")

    # ── STEP 4: Compute forward returns ────────────────────────────
    print("\n[4/6] Computing forward returns...")
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
    print("\n[5/6] Computing alpha factors...")
    factor_scores = compute_all_factors(panels_1h)
    print(f"  Computed {len(factor_scores)} factors: {list(factor_scores.keys())}")

    for name, scores in factor_scores.items():
        valid = scores.notna().sum().sum()
        total = scores.shape[0] * scores.shape[1]
        print(f"  {name}: {valid}/{total} valid values ({100*valid/total:.1f}%)")

    # ── STEP 5: Evaluate all factors ───────────────────────────────
    print("\n[6/6] Evaluating factors across horizons...")
    all_results = []

    if args.parallel:
        # Parallel evaluation using separate processes
        from concurrent.futures import ProcessPoolExecutor, as_completed
        max_workers = os.cpu_count() or 1
        futures = {}
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            for factor_name, scores in factor_scores.items():
                if factor_name not in FACTOR_REGISTRY:
                    continue
                direction, _ = FACTOR_REGISTRY[factor_name]
                futures[executor.submit(evaluate_factor, factor_name, scores, fwd_returns, direction)] = factor_name
            for future in as_completed(futures):
                factor_name = futures[future]
                try:
                    results = future.result()
                except Exception as exc:
                    print(f"  {factor_name}: evaluation error {exc}")
                    results = []
                all_results.extend(results)
                pass_count = sum(1 for r in results if r["pass_fail"] == "PASS")
                watch_count = sum(1 for r in results if r["pass_fail"] == "WATCH")
                fail_count = sum(1 for r in results if r["pass_fail"] == "FAIL")
                print(f"  {factor_name}: PASS={pass_count} WATCH={watch_count} FAIL={fail_count}")
    else:
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
