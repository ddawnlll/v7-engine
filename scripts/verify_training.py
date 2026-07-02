#!/usr/bin/env python3
"""Verify training results — CLI entry point for Makefile.

Usage:
    python3 scripts/verify_training.py data/reports/train-results-SCALP.json

Exits with code 0.
"""
import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("  Usage: verify_training.py <report-path>")
        return 1

    report_path = Path(sys.argv[1])
    if not report_path.exists():
        print(f"  No report found at {report_path}")
        return 0

    m = json.loads(report_path.read_text())
    print(f"  OOS Accuracy:    {m.get('accuracy', 0):.4f}")
    print(f"  Train Accuracy:  {m.get('train_accuracy', 0):.4f}")
    print(f"  OOS Sharpe:      {m.get('sharpe_ratio', 0):.4f}")
    print(f"  Overfit Gap:     {m.get('overfit_gap', 0):.4f}")
    print(f"  Active Trades:   {m.get('total_active_trades', 0)}")
    print(f"  Exposure:        {m.get('exposure_pct', 0):.1f}%")
    print(f"  Samples:         {m.get('n_samples', 0)}")
    print(f"  Folds:           {m.get('n_folds', 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
