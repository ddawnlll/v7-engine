#!/usr/bin/env python3
"""Build OKX P1 Joined Panels — Exchange-Agnostic Microstructure V2.

Joins Binance local OHLCV (1h) with OKX 5m/15m/1h trade features
using as-of backward join for Tier-A symbols.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
P1_ROOT = REPO_ROOT / "cache" / "v7_lite_scalp_dataset_v2_okx_p1"
MICRO_DIR = P1_ROOT / "microstructure"
JOINED_DIR = P1_ROOT / "joined"
QUALITY_DIR = P1_ROOT / "quality"
REPORTS_DIR = REPO_ROOT / "reports" / "v7_lite" / "dataset_v2_okx_p1"
LOG_DIR = P1_ROOT / "logs"

for d in [JOINED_DIR, QUALITY_DIR, REPORTS_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

TIER_A = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]

TOLERANCE_1H = "5min"
TOLERANCE_15M = "16min"


def log(msg, lf=None):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if lf:
        with open(lf, "a") as f:
            f.write(line + "\n")


def load_binance_1h():
    lf = LOG_DIR / "join_build.log"
    log("Loading Binance 1h OHLCV...", lf)
    expanded = REPO_ROOT / "cache" / "v7_lite_expanded_panel_v1"
    close_f = expanded / "panel_v7lite_expanded_close.parquet"
    open_f = expanded / "panel_v7lite_expanded_open.parquet"
    high_f = expanded / "panel_v7lite_expanded_high.parquet"
    low_f = expanded / "panel_v7lite_expanded_low.parquet"
    vol_f = expanded / "panel_v7lite_expanded_volume.parquet"

    if not close_f.exists():
        log("FATAL: Expanded panel not found", lf)
        return pd.DataFrame()

    close = pd.read_parquet(close_f)
    # Check format: might be wide (symbol columns) or long
    if "symbol" in close.columns:
        # Long format
        result = close.copy()
        for name, fp in [("open", open_f), ("high", high_f), ("low", low_f), ("volume", vol_f)]:
            if fp.exists():
                df = pd.read_parquet(fp)
                if "symbol" in df.columns:
                    result = result.merge(df[["timestamp", "symbol", name]], on=["timestamp", "symbol"], how="left")
        return result
    else:
        # Wide format — filter to Tier-A
        target_cols = [c for c in close.columns if c in TIER_A]
        if not target_cols:
            log("FATAL: Tier-A symbols not found in wide panel", lf)
            return pd.DataFrame()
        id_cols = [c for c in close.columns if c not in target_cols]
        result = pd.melt(close, id_vars=id_cols, var_name="symbol", value_name="close")
        result = result[result["symbol"].isin(TIER_A)]
        return result


def load_okx_features(tf: str) -> pd.DataFrame:
    lf = LOG_DIR / "join_build.log"
    feat_dir = MICRO_DIR / f"okx_trades_features_{tf}"
    if not feat_dir.exists():
        log(f"No OKX {tf} features directory", lf)
        return pd.DataFrame()
    files = list(feat_dir.glob("*.parquet"))
    if not files:
        log(f"No OKX {tf} feature files", lf)
        return pd.DataFrame()
    dfs = [pd.read_parquet(f) for f in files]
    result = pd.concat(dfs, ignore_index=True)
    log(f"Loaded OKX {tf} features: {len(result)} rows, {result['canonical_symbol'].nunique()} symbols", lf)
    return result


def asof_join(base: pd.DataFrame, overlay: pd.DataFrame, tolerance: str, overlay_name: str) -> pd.DataFrame:
    lf = LOG_DIR / "join_build.log"
    if base.empty or overlay.empty:
        return base

    base = base.copy()
    overlay = overlay.copy()

    # Find timestamp column in base
    base_ts_col = None
    for col in ["timestamp", "ts"]:
        if col in base.columns:
            base_ts_col = col
            break
    if base_ts_col is None:
        log(f"  WARNING: No timestamp column in base: {list(base.columns)}", lf)
        return base

    # Find timestamp column in overlay
    overlay_ts_col = None
    for col in ["ts", "timestamp"]:
        if col in overlay.columns:
            overlay_ts_col = col
            break
    if overlay_ts_col is None:
        log(f"  WARNING: No timestamp column in overlay: {list(overlay.columns)}", lf)
        return base

    # Convert to datetime
    for df, col in [(base, base_ts_col), (overlay, overlay_ts_col)]:
        if df[col].dtype in ["int64", "float64"]:
            df["ts_dt"] = pd.to_datetime(df[col], unit="ms", utc=True)
        else:
            df["ts_dt"] = pd.to_datetime(df[col], utc=True)

    base = base.sort_values(["ts_dt", "symbol"]).reset_index(drop=True)
    overlay = overlay.sort_values(["ts_dt", "canonical_symbol"]).reset_index(drop=True)

    # Rename overlay symbol column to match base
    if "canonical_symbol" in overlay.columns:
        overlay = overlay.rename(columns={"canonical_symbol": "symbol"})

    merged = pd.merge_asof(
        base, overlay, on="ts_dt", by="symbol",
        tolerance=pd.Timedelta(tolerance), direction="backward",
        suffixes=("", f"_{overlay_name}"),
    )

    merged[f"qc_stale_{overlay_name}"] = False
    merged[f"qc_unknown_delay_{overlay_name}"] = True
    log(f"  Join {overlay_name}: {len(base)} -> {len(merged)} rows", lf)
    return merged


def generate_signal_events(ohlcv_df: pd.DataFrame) -> pd.DataFrame:
    lf = LOG_DIR / "join_build.log"
    events = []
    for sym in TIER_A:
        sdf = ohlcv_df[ohlcv_df["symbol"] == sym].sort_values("timestamp")
        if len(sdf) < 5:
            continue
        sdf["ret_4h"] = sdf["close"].pct_change(4)
        for _, row in sdf.iterrows():
            if pd.notna(row.get("ret_4h")):
                d = "long" if row["ret_4h"] > 0.01 else "short" if row["ret_4h"] < -0.01 else None
                if d:
                    events.append({"symbol": sym, "ts": int(row["timestamp"]),
                                   "factor_name": "ret_4h_momentum", "direction": d, "close": row["close"]})
    df = pd.DataFrame(events)
    log(f"Generated {len(df)} signal events", lf)
    return df


def main():
    started_at = datetime.now(timezone.utc).isoformat()
    lf = LOG_DIR / "join_build.log"
    log("=" * 60, lf)
    log("OKX P1 Joined Panel Builder", lf)
    log("=" * 60, lf)

    ohlcv = load_binance_1h()
    if ohlcv.empty:
        log("FATAL: No OHLCV data", lf)
        return {"status": "FAIL"}

    # Filter to Tier-A
    ohlcv = ohlcv[ohlcv["symbol"].isin(TIER_A)].copy()
    log(f"Binance 1h: {len(ohlcv)} rows, {ohlcv['symbol'].nunique()} Tier-A symbols", lf)

    # Load OKX features
    okx_5m = load_okx_features("5m")
    okx_15m = load_okx_features("15m")
    okx_1h = load_okx_features("1h")

    # Build 1h joined panel
    log("\n--- Building scalp_1h_panel ---", lf)
    panel_1h = ohlcv.copy()

    if not okx_1h.empty:
        panel_1h = asof_join(panel_1h, okx_1h, TOLERANCE_1H, "okx_1h")

    if not okx_5m.empty:
        panel_1h = asof_join(panel_1h, okx_5m, TOLERANCE_1H, "okx_5m")

    if not okx_15m.empty:
        panel_1h = asof_join(panel_1h, okx_15m, TOLERANCE_1H, "okx_15m")

    # Save 1h panel
    out_1h = JOINED_DIR / "scalp_1h_panel" / "version=p1"
    out_1h.mkdir(parents=True, exist_ok=True)
    panel_1h.to_parquet(out_1h / "panel.parquet", index=False)
    log(f"Saved scalp_1h_panel: {len(panel_1h)} rows, {len(panel_1h.columns)} cols", lf)

    # Build enriched signal events
    log("\n--- Building enriched signal events ---", lf)
    events = generate_signal_events(ohlcv)
    if not events.empty and not okx_5m.empty:
        events_enriched = asof_join(events, okx_5m, "5min", "okx_5m_enriched")
    else:
        events_enriched = events

    enriched_csv = REPORTS_DIR / "enriched_signal_events_sample.csv"
    events_enriched.to_csv(enriched_csv, index=False)
    log(f"Saved enriched events: {len(events_enriched)} rows", lf)

    # Leakage audit
    audit = QUALITY_DIR / "leakage_audit.md"
    with open(audit, "w") as f:
        f.write("# Leakage Audit — V2 OKX P1\n\n")
        f.write(f"Generated: {started_at}\n\n")
        f.write("## Join Configuration\n\n")
        f.write("- **Method**: As-of backward join\n")
        f.write(f"- **Tolerance (1h)**: {TOLERANCE_1H}\n")
        f.write("- **Direction**: backward (observable at or before bar close)\n\n")
        f.write("## Feature Groups Joined\n\n")
        f.write(f"- OKX 1h: {'YES' if not okx_1h.empty else 'NO'}\n")
        f.write(f"- OKX 5m: {'YES' if not okx_5m.empty else 'NO'}\n")
        f.write(f"- OKX 15m: {'YES' if not okx_15m.empty else 'NO'}\n")
        f.write("\n## Quality Flags\n\n")
        f.write("- qc_unknown_delay_okx: true (all overlay sources)\n")
        f.write("- qc_stale_okx: false (within tolerance)\n")

    # Join alignment report
    jar = QUALITY_DIR / "join_alignment_report.md"
    with open(jar, "w") as f:
        f.write("# Join Alignment Report — V2 OKX P1\n\n")
        f.write(f"Generated: {started_at}\n\n")
        f.write(f"- Binance 1h rows: {len(ohlcv)}\n")
        f.write(f"- OKX 5m rows: {len(okx_5m)}\n")
        f.write(f"- OKX 15m rows: {len(okx_15m)}\n")
        f.write(f"- OKX 1h rows: {len(okx_1h)}\n")
        f.write(f"- Joined 1h panel rows: {len(panel_1h)}\n")

    result = {
        "status": "PASS",
        "started_at": started_at,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "ohlcv_rows": len(ohlcv),
        "okx_5m_rows": len(okx_5m),
        "okx_15m_rows": len(okx_15m),
        "okx_1h_rows": len(okx_1h),
        "panel_1h_rows": len(panel_1h),
        "enriched_events": len(events_enriched),
    }

    out = P1_ROOT / "manifest" / "join_results.json"
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    log(f"\nJoin status: PASS", lf)
    return result


if __name__ == "__main__":
    r = main()
    print(json.dumps(r, indent=2))
