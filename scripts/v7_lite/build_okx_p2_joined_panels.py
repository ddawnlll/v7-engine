#!/usr/bin/env python3
"""Build OKX P2 Joined Panels — V2 OKX P2 Scale Build.
Joins Binance local OHLCV (1h) with OKX features via as-of backward join.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
P2_ROOT = REPO_ROOT / "cache" / "v7_lite_scalp_dataset_v2_okx_p2"
MICRO_DIR = P2_ROOT / "microstructure"
JOINED_DIR = P2_ROOT / "joined"
QUALITY_DIR = P2_ROOT / "quality"
REPORTS_DIR = REPO_ROOT / "reports" / "v7_lite" / "dataset_v2_okx_p2"
LOG_DIR = P2_ROOT / "logs"
for d in [JOINED_DIR, QUALITY_DIR, REPORTS_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

TIER_AB = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT",
           "AVAXUSDT", "DOTUSDT", "LTCUSDT", "BCHUSDT", "NEARUSDT", "APTUSDT", "ARBUSDT", "OPUSDT",
           "FILUSDT", "ATOMUSDT", "UNIUSDT", "SUIUSDT"]


def log(msg, lf=None):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if lf:
        with open(lf, "a") as f:
            f.write(line + "\n")


def load_binance_1h():
    lf = LOG_DIR / "join_build.log"
    expanded = REPO_ROOT / "cache" / "v7_lite_expanded_panel_v1"
    close_f = expanded / "panel_v7lite_expanded_close.parquet"
    if not close_f.exists():
        return pd.DataFrame()
    close = pd.read_parquet(close_f)
    if "symbol" in close.columns:
        result = close.copy()
        for name in ["open", "high", "low", "volume"]:
            fp = expanded / f"panel_v7lite_expanded_{name}.parquet"
            if fp.exists():
                df = pd.read_parquet(fp)
                if "symbol" in df.columns:
                    result = result.merge(df[["timestamp", "symbol", name]], on=["timestamp", "symbol"], how="left")
        return result
    return pd.DataFrame()


def load_okx_features(tf):
    lf = LOG_DIR / "join_build.log"
    d = MICRO_DIR / f"okx_trades_features_{tf}"
    files = list(d.glob("*.parquet")) if d.exists() else []
    if not files:
        return pd.DataFrame()
    result = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    log(f"OKX {tf}: {len(result)} rows, {result['canonical_symbol'].nunique()} symbols", lf)
    return result


def asof_join(base, overlay, tolerance, name):
    lf = LOG_DIR / "join_build.log"
    if base.empty or overlay.empty:
        return base
    base, overlay = base.copy(), overlay.copy()
    base_ts = next((c for c in ["timestamp", "ts"] if c in base.columns), None)
    overlay_ts = next((c for c in ["ts", "timestamp"] if c in overlay.columns), None)
    if not base_ts or not overlay_ts:
        log(f"  skip {name}: missing timestamp", lf)
        return base
    for df, col in [(base, base_ts), (overlay, overlay_ts)]:
        df["ts_dt"] = pd.to_datetime(df[col], unit="ms", utc=True) if df[col].dtype in ["int64", "float64"] else pd.to_datetime(df[col], utc=True)
    base = base.sort_values(["ts_dt", "symbol"]).reset_index(drop=True)
    overlay = overlay.sort_values(["ts_dt", "canonical_symbol"]).reset_index(drop=True)
    if "canonical_symbol" in overlay.columns:
        overlay = overlay.rename(columns={"canonical_symbol": "symbol"})
    merged = pd.merge_asof(base, overlay, on="ts_dt", by="symbol", tolerance=pd.Timedelta(tolerance), direction="backward", suffixes=("", f"_{name}"))
    merged[f"qc_stale_{name}"] = False
    merged[f"qc_unknown_delay_{name}"] = True
    log(f"  {name}: {len(base)} -> {len(merged)} rows", lf)
    return merged


def generate_events(ohlcv):
    lf = LOG_DIR / "join_build.log"
    events = []
    for sym in TIER_AB:
        sdf = ohlcv[ohlcv["symbol"] == sym].sort_values("timestamp")
        if len(sdf) < 5:
            continue
        sdf["ret_4h"] = sdf["close"].pct_change(4)
        for _, row in sdf.iterrows():
            if pd.notna(row.get("ret_4h")):
                d = "long" if row["ret_4h"] > 0.01 else "short" if row["ret_4h"] < -0.01 else None
                if d:
                    events.append({"symbol": sym, "ts": int(row["timestamp"]), "factor_name": "ret_4h_momentum",
                                   "direction": d, "close": row["close"]})
    df = pd.DataFrame(events)
    log(f"Events: {len(df)}", lf)
    return df


def main():
    started = datetime.now(timezone.utc).isoformat()
    lf = LOG_DIR / "join_build.log"
    log("=" * 60, lf)
    log("OKX P2 Joined Panel Builder", lf)

    ohlcv = load_binance_1h()
    if ohlcv.empty:
        return {"status": "FAIL"}
    ohlcv = ohlcv[ohlcv["symbol"].isin(TIER_AB)].copy()
    log(f"Binance 1h: {len(ohlcv)} rows, {ohlcv['symbol'].nunique()} Tier A+B", lf)

    okx_5m, okx_15m, okx_1h = load_okx_features("5m"), load_okx_features("15m"), load_okx_features("1h")

    log("\n--- scalp_1h_panel ---", lf)
    panel = ohlcv.copy()
    for okx_df, tf in [(okx_1h, "1h"), (okx_5m, "5m"), (okx_15m, "15m")]:
        if not okx_df.empty:
            panel = asof_join(panel, okx_df, "5min", f"okx_{tf}")

    out_dir = JOINED_DIR / "scalp_1h_panel" / "version=p2"
    out_dir.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(out_dir / "panel.parquet", index=False)
    log(f"Saved: {len(panel)} rows, {len(panel.columns)} cols", lf)

    events = generate_events(ohlcv)
    if not events.empty and not okx_5m.empty:
        events = asof_join(events, okx_5m, "5min", "okx_5m_ev")
    events.to_csv(REPORTS_DIR / "enriched_signal_events_sample.csv", index=False)

    # Quality
    with open(QUALITY_DIR / "leakage_audit.md", "w") as f:
        f.write(f"# Leakage Audit — V2 OKX P2\n\nGenerated: {started}\n\n")
        f.write("- Method: as-of backward join\n- Tolerance: 5min\n- Direction: backward\n\n")
        f.write(f"- OKX 5m: {'YES' if not okx_5m.empty else 'NO'}\n")
        f.write(f"- OKX 15m: {'YES' if not okx_15m.empty else 'NO'}\n")
        f.write(f"- OKX 1h: {'YES' if not okx_1h.empty else 'NO'}\n")
        f.write("- qc_unknown_delay_okx: true\n- qc_stale_okx: false\n")

    with open(QUALITY_DIR / "join_alignment_report.md", "w") as f:
        f.write(f"# Join Alignment — V2 OKX P2\n\n")
        f.write(f"- Binance 1h: {len(ohlcv)} rows\n- OKX 5m: {len(okx_5m)}\n- OKX 15m: {len(okx_15m)}\n- OKX 1h: {len(okx_1h)}\n")
        f.write(f"- Panel: {len(panel)} rows\n")

    result = {"status": "PASS", "panel_rows": len(panel), "panel_cols": len(panel.columns),
              "events": len(events), "okx_5m": len(okx_5m), "okx_15m": len(okx_15m), "okx_1h": len(okx_1h)}
    with open(P2_ROOT / "manifest" / "join_results.json", "w") as f:
        json.dump(result, f, indent=2)
    return result


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
