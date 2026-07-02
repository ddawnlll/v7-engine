"""Simple synthetic simulation runner for AlphaForge diagnostics.

This script generates a set of CSV files under a user‑specified output directory.
Each CSV represents a symbol and contains the minimal columns required by the
`alphaforge.ic_diagnosis` module:
    ts, net_R, momentum_rank, trend_regime, vol_pct, rs_rank,
    btc_regime, pullback_atr, volume_zscore, spread_proxy, funding_context

The data are randomly generated but deterministic (fixed seed) so that the
diagnostic can be exercised without needing real market data.
"""

import argparse
import pathlib
import csv
import random
import pathlib

def generate_symbol_rows(symbol: str, n: int = 100):
    # Simple deterministic pseudo‑random generator based on symbol hash
    seed = hash(symbol) & 0xffffffff
    rnd = random.Random(seed)
    rows = []
    net_r = 0.0
    for i in range(n):
        ts = i
        # Add a small drift to net_R to create a weak positive correlation
        net_r += rnd.gauss(mu=0.001, sigma=0.01)
        momentum_rank = rnd.randint(0, 99)
        trend_regime = rnd.randint(0, 2)
        vol_pct = rnd.random()
        rs_rank = rnd.randint(0, 99)
        btc_regime = rnd.randint(0, 2)
        pullback_atr = rnd.random()
        volume_zscore = rnd.random()
        spread_proxy = rnd.random()
        funding_context = rnd.randint(0, 1)
        rows.append([
            ts,
            net_r,
            momentum_rank,
            trend_regime,
            vol_pct,
            rs_rank,
            btc_regime,
            pullback_atr,
            volume_zscore,
            spread_proxy,
            funding_context,
        ])
    return rows

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic SimulationOutput CSVs")
    parser.add_argument("output_dir", type=pathlib.Path, help="Directory to write CSV files")
    parser.add_argument("--symbols", nargs="+", default=["BTC", "ETH", "SOL"], help="List of symbols to generate")
    parser.add_argument("--rows", type=int, default=200, help="Number of rows per symbol")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for sym in args.symbols:
    rows = generate_symbol_rows(sym, n=args.rows)
    with open(args.output_dir / f"{sym}.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "ts",
            "net_R",
            "momentum_rank",
            "trend_regime",
            "vol_pct",
            "rs_rank",
            "btc_regime",
            "pullback_atr",
            "volume_zscore",
            "spread_proxy",
            "funding_context",
        ])
        writer.writerows(rows)
    print(f"Generated {len(args.symbols)} synthetic simulation CSVs in {args.output_dir}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
