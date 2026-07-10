#!/usr/bin/env python3
"""
Prepare config for Google Colab.

Usage:
    python3 scripts/colab/prepare.py                      # Default config
    python3 scripts/colab/prepare.py --symbols BTCUSDT    # Override symbols
    python3 scripts/colab/prepare.py --mode SWING          # Override mode

Output:
    dist/colab-config.json    → Notebook config (consumed by colab notebook)
"""

import argparse
import json
import os
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DIST_DIR = REPO_ROOT / "dist"

DEFAULT_CONFIG = {
    "symbols": "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT",
    "mode": "SCALP",
    "intervals": "1h,4h",
    "branch": "main",
    "repo_url": "https://github.com/ddawnlll/v7-engine",
    "data_years": "2023-2026",
    "folds": 6,
}


def parse_args():
    parser = argparse.ArgumentParser(description="Prepare Colab config")
    parser.add_argument("--symbols", default=DEFAULT_CONFIG["symbols"],
                        help="Symbols for data/training")
    parser.add_argument("--mode", default=DEFAULT_CONFIG["mode"],
                        choices=["SCALP", "SWING", "AGGRESSIVE_SCALP"],
                        help="Trading mode")
    return parser.parse_args()


def save_config(config: dict, config_path: Path) -> None:
    """Save Colab config as JSON."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2))
    print(f"  Config → {config_path}")
    print(f"  Mode:   {config['mode']}")
    print(f"  Symbols: {config['symbols']}")


def print_instructions(config: dict) -> None:
    """Print step-by-step Colab setup instructions."""
    print()
    print("=" * 55)
    print("  GOOGLE COLAB — SETUP INSTRUCTIONS")
    print("=" * 55)
    print()
    print("  1. https://colab.research.google.com/")
    print("  2. File > Upload notebook → scripts/colab/af_leverage_train.ipynb")
    print("  3. Runtime > Change runtime type > T4 GPU")
    print("  4. Run cells sırayla:")
    print()
    print("     Cell 1: GPU check")
    print("     Cell 2: Clone repo (GitHub'dan direkt çeker)")
    print("     Cell 3: pip install dependencies")
    print("     Cell 4: GPU smoke test")
    print("     Cell 5: Binance data download")
    print("     Cell 6: Simulation")
    print("     Cell 7: XGBoost training")
    print()
    print(f"  Config: mode={config['mode']}, symbols={config['symbols']}")
    print()
    print("  NOT: Kod GitHub'dan clone'lanır. Değişiklik varsa")
    print("  önce push et, sonra Colab'da Cell 2'yi tekrar çalıştır.")
    print("  Lokal değişiklikleri Colab'a taşımak için git push yap.")
    print()


def main():
    args = parse_args()
    config = {**DEFAULT_CONFIG, "symbols": args.symbols, "mode": args.mode}
    config_path = DIST_DIR / "colab-config.json"

    save_config(config, config_path)
    print_instructions(config)
    return 0


if __name__ == "__main__":
    main()
