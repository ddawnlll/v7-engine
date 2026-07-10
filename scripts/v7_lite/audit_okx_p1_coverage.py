#!/usr/bin/env python3
"""P1 Coverage Audit — V2 OKX P2 Scale Build.

Inspects P1 outputs to determine whether P1 was a real build or tiny sample.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
P1_ROOT = REPO_ROOT / "cache" / "v7_lite_scalp_dataset_v2_okx_p1"
REPORTS_DIR = REPO_ROOT / "reports" / "v7_lite" / "dataset_v2_okx_p2"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def audit():
    report_lines = ["# P1 Coverage Audit\n", f"Generated: {datetime.now(timezone.utc).isoformat()}\n"]
    all_rows = []
    all_ts = []

    # Check OKX features
    for tf in ["5m", "15m", "1h"]:
        d = P1_ROOT / f"microstructure/okx_trades_features_{tf}"
        files = list(d.glob("*.parquet")) if d.exists() else []
        total_rows = 0
        for f in files:
            df = pd.read_parquet(f)
            total_rows += len(df)
            all_ts.extend([df["ts"].min(), df["ts"].max()])
            all_rows.append({"timeframe": tf, "symbol": f.stem.split("_")[0], "rows": len(df),
                             "ts_min": int(df["ts"].min()), "ts_max": int(df["ts"].max())})
        report_lines.append(f"## OKX {tf}\n- symbols: {len(files)}\n- total rows: {total_rows}\n")

    # Joined panel
    panel_f = P1_ROOT / "joined/scalp_1h_panel/version=p1/panel.parquet"
    if panel_f.exists():
        df = pd.read_parquet(panel_f)
        report_lines.append(f"## Joined 1h Panel\n- rows: {len(df)}\n- symbols: {df['symbol'].nunique()}\n")

    # Date range
    if all_ts:
        min_ts = min(t for t in all_ts if t > 0)
        max_ts = max(t for t in all_ts if t > 0)
        min_dt = pd.to_datetime(min_ts, unit="ms", utc=True)
        max_dt = pd.to_datetime(max_ts, unit="ms", utc=True)
        days = (max_dt - min_dt).days
        report_lines.insert(2, f"## Actual Date Range\n- start: {min_dt}\n- end: {max_dt}\n- days: {days}\n")

    # Storage
    perm = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(P1_ROOT) for f in fs)
    report_lines.append(f"## Storage\n- permanent: {perm / 1e6:.2f} MB\n")

    # Verdict
    report_lines.append("## Conclusion\n")
    if all_rows and max(r["rows"] for r in all_rows) <= 2:
        report_lines.append("P1 was a **tiny recent sample** (~1 hour of OKX trades per symbol), NOT a 3-6 month build. "
                            "P2 must download substantially more OKX data to be useful for specialist discovery.\n")
    else:
        report_lines.append("P1 had meaningful coverage.\n")

    report = "\n".join(report_lines)
    out = REPORTS_DIR / "P1_COVERAGE_AUDIT.md"
    with open(out, "w") as f:
        f.write(report)
    print(report)
    return {"rows": all_rows, "storage_mb": perm / 1e6}


if __name__ == "__main__":
    audit()
