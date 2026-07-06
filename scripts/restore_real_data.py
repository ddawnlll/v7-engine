#!/usr/bin/env python3
"""Copy data_lake from worktree to data/raw/ format for load_cached_data().

Handles schema differences across years (open_time vs timestamp, uneven cols).
"""

from __future__ import annotations
import sys
from pathlib import Path
import pyarrow.parquet as pq
import pyarrow as pa
import numpy as np

REPO = Path(__file__).resolve().parent.parent
WT_ROOT = REPO / ".claude" / "worktrees" / "wf_af3f20e1-0b2-11"
SRC = WT_ROOT / "data_lake" / "raw" / "binance" / "um" / "klines"
DST = REPO / "data" / "raw"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
INTERVAL = "1h"


def load_monthly(path: Path) -> dict:
    """Load a monthly parquet, return {col: np.array} with unified column names."""
    t = pq.read_table(str(path))
    names = t.column_names
    out = {}
    for col in names:
        arr = t.column(col).to_numpy()
        out[col] = arr
    # Rename: open_time -> timestamp
    if "open_time" in out and "timestamp" not in out:
        out["timestamp"] = out.pop("open_time").astype(np.int64)
    # Fill trade_count if only trades exists
    if "trade_count" not in out and "trades" in out:
        out["trade_count"] = out.pop("trades")
    return out


def convert():
    print(f"Source: {SRC}")
    print(f"Dest:   {DST}")
    print()

    for sym in SYMBOLS:
        sym_dir = SRC / sym / INTERVAL
        if not sym_dir.exists():
            print(f"  SKIP {sym}: not found")
            continue

        # Collect monthly files
        months = sorted(sym_dir.rglob("*.parquet"))
        if not months:
            print(f"  SKIP {sym}: no parquet files")
            continue

        print(f"  {sym}: {len(months)} files")

        all_ts, all_open, all_high, all_low, all_close, all_vol = [], [], [], [], [], []
        total = 0
        for mf in months:
            d = load_monthly(mf)
            n = len(d["open"])
            # Filter away rows with 0 volume (uninit/partial bars)
            vol = d.get("volume", np.zeros(n))
            all_ts.append(d["timestamp"])
            all_open.append(d["open"])
            all_high.append(d["high"])
            all_low.append(d["low"])
            all_close.append(d["close"])
            all_vol.append(vol)
            total += n

        # Concatenate
        ts = np.concatenate(all_ts).astype(np.int64)
        open_a = np.concatenate(all_open).astype(np.float64)
        high_a = np.concatenate(all_high).astype(np.float64)
        low_a = np.concatenate(all_low).astype(np.float64)
        close_a = np.concatenate(all_close).astype(np.float64)
        vol_a = np.concatenate(all_vol).astype(np.float64)

        # Sort by timestamp
        order = np.argsort(ts)
        ts = ts[order]
        open_a = open_a[order]
        high_a = high_a[order]
        low_a = low_a[order]
        close_a = close_a[order]
        vol_a = vol_a[order]

        # Write single parquet
        table = pa.table({
            "timestamp": pa.array(ts, type=pa.int64()),
            "open": pa.array(open_a, type=pa.float64()),
            "high": pa.array(high_a, type=pa.float64()),
            "low": pa.array(low_a, type=pa.float64()),
            "close": pa.array(close_a, type=pa.float64()),
            "volume": pa.array(vol_a, type=pa.float64()),
        })

        out_dir = DST / sym
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{sym}_{INTERVAL}_full.parquet"
        pq.write_table(table, str(out_path))

        # Summary
        ts_min = np.datetime64(int(ts.min()), "s") if ts.dtype.kind == "i" else ts.min()
        ts_max = np.datetime64(int(ts.max()), "s") if ts.dtype.kind == "i" else ts.max()
        print(f"    -> {out_path}")
        print(f"       {total} rows, {ts_min} to {ts_max}")
        print(f"       {out_path.stat().st_size / 1024:.0f} KB")

    print("\nDone. 4 symbols restored.")


if __name__ == "__main__":
    convert()
