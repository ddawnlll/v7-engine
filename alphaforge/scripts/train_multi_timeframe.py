#!/usr/bin/env python3
"""Issue #143: Multi-Timeframe Alpha Tuning.

Runs walk-forward validation for all three canonical timeframes (SWING, SCALP,
AGGRESSIVE_SCALP) and produces a cross-timeframe edge comparison.

This script:
  1. Generates synthetic OHLCV data (multi-symbol)
  2. Runs mode-specific walk-forward validation for each mode
  3. Computes cross-timeframe edge comparison
  4. Saves individual mode reports and the comparison report

Usage:
    python alphaforge/scripts/train_multi_timeframe.py [--n-bars 2000] [--n-symbols 3]
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC_PATH = str(_REPO_ROOT / "alphaforge" / "src")
if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)


def main() -> int:
    from alphaforge.validation.walk_forward_runner import (
        WalkForwardResult,
        run_walk_forward,
        save_walk_forward_report,
    )
    from alphaforge.validation.cross_timeframe import (
        compare_timeframes,
        compare_timeframes_to_dict,
    )

    import argparse
    parser = argparse.ArgumentParser(
        description="Multi-Timeframe Alpha Tuning (Issue #143)"
    )
    parser.add_argument("--n-bars", type=int, default=2000,
                        help="Bars per symbol (default: 2000)")
    parser.add_argument("--n-symbols", type=int, default=3,
                        help="Number of symbols (default: 3)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed (default: 42)")
    parser.add_argument("--output-dir", type=str, default="artifacts/reports",
                        help="Output directory (default: artifacts/reports)")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    print("=== Multi-Timeframe Alpha Tuning (Issue #143) ===")
    print(f"Bars per symbol: {args.n_bars}")
    print(f"Symbols: {args.n_symbols}")
    print(f"Seed: {args.seed}")
    print()

    # Run walk-forward for each mode
    modes = ["SWING", "SCALP", "AGGRESSIVE_SCALP"]
    wfv_results: dict[str, WalkForwardResult] = {}

    for mode in modes:
        print(f"\n--- Running {mode} walk-forward validation ---")
        try:
            result = run_walk_forward(
                n_bars=args.n_bars,
                n_symbols=args.n_symbols,
                random_seed=args.seed,
                mode=mode,
            )
            wfv_results[mode] = result
            print(f"  Folds: {len(result.folds)}")
            print(f"  Verdict: {result.verdict}")
            print(f"  Report ID: {result.report_id}")

            # Save individual mode report
            mode_report_path = os.path.join(
                args.output_dir, f"wfv_{mode.lower()}_{ts}.json"
            )
            save_walk_forward_report(result, mode_report_path)
            print(f"  Report saved: {mode_report_path}")

        except Exception as e:
            print(f"  ERROR: {e}")
            wfv_results[mode] = WalkForwardResult()

    # Compute cross-timeframe comparison
    print("\n\n--- Cross-Timeframe Edge Comparison ---")
    comparison = compare_timeframes(wfv_results)
    print(f"Dominant timeframe: {comparison.dominant_timeframe}")
    print(f"Multi-TF confirmation: {comparison.multi_tf_confirmation}")
    print(f"Consistency score: {comparison.consistency_score}")
    print(f"Has conflict: {comparison.has_conflict}")
    print(f"Verdict: {comparison.verdict}")
    print(f"Summary: {comparison.summary}")
    print()

    # Per-timeframe edges
    for mode, edge in comparison.timeframes.items():
        print(f"  {mode}: sharpe={edge.sharpe:.4f}, "
              f"edge={edge.edge_strength}, direction={edge.direction}")

    # Save comparison report
    comparison_dict = compare_timeframes_to_dict(comparison)
    comparison_path = os.path.join(
        args.output_dir, f"cross_timeframe_comparison_{ts}.json"
    )
    with open(comparison_path, "w") as f:
        json.dump(comparison_dict, f, indent=2, default=str)
    print(f"\nComparison report saved: {comparison_path}")

    print("\n=== Multi-Timeframe Alpha Tuning COMPLETE ===")

    return 0


if __name__ == "__main__":
    sys.exit(main())
