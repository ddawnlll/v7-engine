#!/usr/bin/env python3
"""Data health check for factor sprint — inspects the data lake and reports readiness.

Usage:
    PYTHONPATH=. .venv/bin/python3 scripts/check_factor_data.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# Ensure project root on path
PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_ROOT)

import pandas as pd

from alphaforge.factors.loader import DEFAULT_SYMBOLS, load_1h_ohlcv

REPORTS_DIR = Path("reports/alphaforge/factor_sprint")


def check_data_health() -> str:
    """Run data health checks and return markdown report."""
    lines = [
        "# Data Health Report — Factor Sprint 001",
        "",
        f"Generated: {datetime.now().isoformat()}",
        "",
    ]

    # Load data
    print("[data_health] Loading 1h OHLCV from data lake...")
    data = load_1h_ohlcv()

    # Summary
    total_symbols = len(DEFAULT_SYMBOLS)
    loaded = sum(1 for df in data.values() if not df.empty)
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total symbols requested:** {total_symbols}")
    lines.append(f"- **Symbols loaded:** {loaded}")
    lines.append(f"- **Symbols missing/empty:** {total_symbols - loaded}")
    lines.append("")

    # Per-symbol details
    lines.append("## Per-Symbol Details")
    lines.append("")
    lines.append("| Symbol | Rows | Start | End | Missing est. | Duplicates | OK |")
    lines.append("|--------|------|-------|-----|--------------|------------|----|")

    all_empty = True
    for sym in DEFAULT_SYMBOLS:
        df = data.get(sym, pd.DataFrame())
        if df.empty:
            lines.append(f"| {sym} | 0 | - | - | - | - | NO |")
            continue

        all_empty = False
        n_rows = len(df)
        start = str(df.index.min())
        end = str(df.index.max())

        # Check for duplicates
        dupes = df.index.duplicated().sum()

        # Estimate missing timestamps (1h bars)
        expected_hours = int((df.index.max() - df.index.min()).total_seconds() / 3600)
        missing_est = max(0, expected_hours - n_rows)

        ok = "YES" if n_rows > 100 and dupes == 0 else "WARN"
        lines.append(f"| {sym} | {n_rows} | {start} | {end} | {missing_est} | {dupes} | {ok} |")

    lines.append("")

    # Interval check
    lines.append("## Interval Check")
    lines.append("")
    lines.append("- 1h: **AVAILABLE** (all data lake data)")
    lines.append("- 4h: **DERIVABLE** (resample from 1h)")
    lines.append("- 15m: **NOT AVAILABLE** (not downloaded)")
    lines.append("- 1d: **NOT REQUIRED** for this sprint")
    lines.append("")

    # BTC check
    btc = data.get("BTCUSDT", pd.DataFrame())
    lines.append("## BTCUSDT Check")
    lines.append("")
    if btc.empty:
        lines.append("- **BTCUSDT: MISSING** — critical symbol not loaded")
    else:
        lines.append(f"- **BTCUSDT: PRESENT** — {len(btc)} rows, {btc.index.min()} to {btc.index.max()}")
    lines.append("")

    # 4h resample test
    lines.append("## 4h Resample Test")
    lines.append("")
    if btc.empty:
        lines.append("- Cannot test (BTCUSDT missing)")
    else:
        from alphaforge.factors.loader import resample_to_4h
        btc_4h = resample_to_4h({"BTCUSDT": btc}).get("BTCUSDT", pd.DataFrame())
        if btc_4h.empty:
            lines.append("- 4h resample: **FAILED** (empty output)")
        else:
            lines.append(f"- 4h resample: **OK** — {len(btc_4h)} bars from {len(btc)} 1h bars")
    lines.append("")

    # Column check
    lines.append("## Column Check")
    lines.append("")
    required_cols = ["open", "high", "low", "close", "volume"]
    for sym, df in data.items():
        if df.empty:
            continue
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            lines.append(f"- {sym}: **MISSING** {missing_cols}")
        else:
            lines.append(f"- {sym}: all required columns present")
            break  # only show first valid symbol
    lines.append("")

    # Overall verdict
    lines.append("## Verdict")
    lines.append("")
    if all_empty:
        lines.append("❌ **BLOCKED** — No symbol data loaded. Check data lake paths.")
    elif loaded < 10:
        lines.append("⚠️ **WARNING** — Fewer than 10 symbols loaded. Factor evaluation may be limited.")
    else:
        lines.append(f"✅ **READY** — {loaded}/{total_symbols} symbols loaded with 1h OHLCV.")

    content = "\n".join(lines) + "\n"

    # Write report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "DATA_HEALTH.md"
    report_path.write_text(content)
    print(f"[data_health] Wrote {report_path}")

    # Print to stdout
    print(content)
    return content


if __name__ == "__main__":
    check_data_health()
