#!/usr/bin/env python3
"""OKX Historical Mini Build — builds features from downloaded historical data.
Calls extract_okx_historical_trade_features.py then verifies output.
"""
import json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts" / "v7_lite"))

from extract_okx_historical_trade_features import main as extract_main


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def main():
    log("=" * 60)
    log("OKX Historical Mini Build")
    log("=" * 60)

    # Run extraction
    log("Running feature extraction...")
    extract_result = extract_main()

    # Verify output
    feat_dir = REPO / "cache" / "v7_lite_okx_historical_resolution" / "samples" / "features"
    parquets = sorted(feat_dir.glob("*.parquet"))
    total_rows = 0
    total_mb = 0

    for f in parquets:
        import pandas as pd
        df = pd.read_parquet(f)
        total_rows += len(df)
        total_mb += f.stat().st_size / 1e6
        log(f"  {f.name}: {len(df)} rows, {f.stat().st_size / 1e6:.2f} MB")

    log(f"\nTotal: {len(parquets)} files, {total_rows} rows, {total_mb:.2f} MB")
    return {"status": "PASS" if parquets else "FAIL", "files": len(parquets),
            "rows": total_rows, "mb": round(total_mb, 2)}


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
