#!/usr/bin/env python3
"""v0.34A — Cross-Sectional Momentum Strategy Runner.

Loads 20 symbols aligned by timestamp, runs the cross-sectional
momentum strategy, reports performance.

Usage:
    PYTHONPATH=alphaforge/src:. python3 scripts/strategy_v034a.py
"""
import sys, json, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "alphaforge" / "src"))
sys.path.insert(0, str(REPO))

import numpy as np
from alphaforge.strategy.cross_sectional import (
    backtest_cross_sectional_momentum,
    DEFAULT_CONFIG,
)

SYMBOLS = DEFAULT_CONFIG["symbols"]
DATA_DIR = REPO / "data_lake" / "raw" / "binance" / "um" / "klines"

def load_aligned_data() -> tuple[dict[str, np.ndarray], np.ndarray, dict[str, np.ndarray]]:
    """Load all 20 symbols aligned by timestamp."""
    import pyarrow.parquet as pq

    # Load all parquet files for each symbol
    raw_data: dict[str, list] = {sym: [] for sym in SYMBOLS}
    timestamps_set = set()

    for sym in SYMBOLS:
        sym_dir = DATA_DIR / sym / "1h"
        if not sym_dir.exists():
            print(f"  [WARN] No data for {sym}")
            continue
        rows = []
        for year_dir in sorted(sym_dir.iterdir()):
            if not year_dir.is_dir(): continue
            for pf in sorted(year_dir.iterdir()):
                if pf.suffix != ".parquet": continue
                try:
                    df = pq.read_table(str(pf)).to_pandas()
                    for _, r in df.iterrows():
                        ts_col = "timestamp" if "timestamp" in df.columns else "open_time"
                        rows.append((int(r[ts_col]), float(r["close"])))
                except Exception:
                    pass
        rows.sort(key=lambda x: x[0])
        raw_data[sym] = rows
        timestamps_set.update(r[0] for r in rows)

    # Find common timestamps (all symbols have data at this timestamp)
    common_ts = sorted(timestamps_set)

    # Build aligned arrays
    close_data: dict[str, np.ndarray] = {}
    timestamps_arr = np.array(common_ts, dtype=np.int64)
    n = len(common_ts)

    for sym in SYMBOLS:
        arr = np.full(n, np.nan, dtype=np.float64)
        sym_dict = {r[0]: r[1] for r in raw_data.get(sym, [])}
        for i, ts in enumerate(common_ts):
            if ts in sym_dict:
                arr[i] = sym_dict[ts]
        # Forward-fill NaN
        last = np.nan
        for i in range(n):
            if np.isnan(arr[i]):
                arr[i] = last
            else:
                last = arr[i]
        close_data[sym] = arr

    print(f"  Symbols: {len(close_data)}")
    print(f"  Bars:    {n}")
    print(f"  Range:   {common_ts[0]} to {common_ts[-1]}")

    return close_data, timestamps_arr, close_data


def main():
    print("=" * 70)
    print("  v0.34A — Cross-Sectional Momentum Profit Baseline")
    print("=" * 70)

    # Load data
    print("\n[1/3] Loading 20-symbol aligned data...")
    t0 = time.time()
    close_data, timestamps, prices = load_aligned_data()
    print(f"  Done in {time.time()-t0:.1f}s")

    # Run strategy
    print("\n[2/3] Running cross-sectional momentum backtest...")
    t0 = time.time()
    result = backtest_cross_sectional_momentum(
        close_data, timestamps, prices,
        config={
            "symbols": SYMBOLS,
            "momentum_windows": [1, 4, 12, 24],
            "long_pct": 0.20,
            "short_pct": 0.20,
            "max_symbols_per_side": 4,
            "max_exposure_pct": 0.40,
            "rebalance_hours": 4,
            "taker_fee": 0.00045,
            "slippage": 0.0005,
        },
    )
    print(f"  Done in {time.time()-t0:.1f}s")

    # Print results
    print(f"\n{'='*70}")
    print(f"  RESULTS")
    print(f"{'='*70}")
    print(f"  Total Return:       {result.gross_return:.4f} ({result.gross_return*100:.1f}%)")
    print(f"  Net Return:         {result.net_return:.4f}")
    print(f"  Max Drawdown:       {result.max_drawdown:.4f}")
    print(f"  Profit Factor:      {result.profit_factor:.4f}")
    print(f"  Sharpe (annual):    {result.sharpe:.4f}")
    print(f"  Trades:             {result.n_trades}")
    print(f"  LONG/SHORT:         {result.n_long}/{result.n_short}")
    print(f"  Exposure:           {result.exposure_pct:.1f}%")
    print(f"  Gated by costs:     {result.n_trades_gated}")
    print(f"  Executed:           {result.n_trades_executed}")
    print(f"  Beats no-trade:     {result.beat_no_trade}")

    # Save
    out = REPO / "data" / "diagnostics" / "strategy_v034a_result.json"
    out.write_text(json.dumps({
        "strategy": "cross_sectional_momentum",
        "config": DEFAULT_CONFIG,
        "return_pct": round(result.gross_return * 100, 4),
        "net_return_pct": round(result.net_return * 100, 4),
        "max_drawdown": result.max_drawdown,
        "profit_factor": result.profit_factor,
        "sharpe": result.sharpe,
        "n_trades": result.n_trades,
        "n_long": result.n_long,
        "n_short": result.n_short,
        "exposure_pct": result.exposure_pct,
        "trades_gated": result.n_trades_gated,
        "trades_executed": result.n_trades_executed,
        "beat_no_trade": result.beat_no_trade,
    }, indent=2))
    print(f"\n  Results saved: {out}")


if __name__ == "__main__":
    main()
