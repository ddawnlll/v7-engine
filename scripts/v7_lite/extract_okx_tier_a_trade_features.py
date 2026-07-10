#!/usr/bin/env python3
"""Extract OKX Tier-A Trade Features — Exchange-Agnostic Microstructure V2.

Extracts 5m, 15m, and 1h bar features from OKX tick trades for Tier-A symbols.
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
STAGING = P1_ROOT / "staging" / "okx"
LOG_DIR = P1_ROOT / "logs"
MICRO_DIR = P1_ROOT / "microstructure"

LOG_DIR.mkdir(parents=True, exist_ok=True)
MICRO_DIR.mkdir(parents=True, exist_ok=True)

TIER_A_SYMBOLS = {
    "BTCUSDT": "BTC-USDT-SWAP",
    "ETHUSDT": "ETH-USDT-SWAP",
    "SOLUSDT": "SOL-USDT-SWAP",
    "BNBUSDT": "BNB-USDT-SWAP",
    "XRPUSDT": "XRP-USDT-SWAP",
    "DOGEUSDT": "DOGE-USDT-SWAP",
    "ADAUSDT": "ADA-USDT-SWAP",
    "LINKUSDT": "LINK-USDT-SWAP",
}

TIMEFRAMES = {"5m": "5min", "15m": "15min", "1h": "1h"}


def log(msg, lf=None):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if lf:
        with open(lf, "a") as f:
            f.write(line + "\n")


def extract_features(trades_df: pd.DataFrame, symbol: str, okx_symbol: str, tf: str, resample: str) -> pd.DataFrame:
    if trades_df.empty:
        return pd.DataFrame()

    trades_df = trades_df.copy()
    trades_df["timestamp"] = pd.to_numeric(trades_df["timestamp"], errors="coerce")
    trades_df["price"] = pd.to_numeric(trades_df["price"], errors="coerce")
    trades_df["size"] = pd.to_numeric(trades_df["size"], errors="coerce")
    trades_df = trades_df.dropna(subset=["timestamp", "price", "size"])
    if trades_df.empty:
        return pd.DataFrame()

    trades_df["ts_dt"] = pd.to_datetime(trades_df["timestamp"], unit="ms", utc=True)
    trades_df["bucket"] = trades_df["ts_dt"].dt.floor(resample)

    # Compute quote volume (price * size)
    trades_df["quote_volume"] = trades_df["price"] * trades_df["size"]

    features = []
    for bucket, grp in trades_df.groupby("bucket"):
        n = len(grp)
        total_vol = grp["size"].sum()
        quote_vol = grp["quote_volume"].sum()

        buy_mask = grp["side"].str.lower() == "buy" if "side" in grp.columns else pd.Series(False, index=grp.index)
        buy_vol = grp.loc[buy_mask, "size"].sum()
        sell_vol = grp.loc[~buy_mask, "size"].sum() if "side" in grp.columns else np.nan
        imbalance = (buy_vol - sell_vol) / (buy_vol + sell_vol) if (buy_vol + sell_vol) > 0 else np.nan
        has_side = bool("side" in grp.columns and grp["side"].notna().any())

        median_sz = grp["size"].median()
        large_mask = grp["size"] > 2 * median_sz
        large_count = int(large_mask.sum())
        large_vol = grp.loc[large_mask, "size"].sum()
        large_ratio = large_count / n if n > 0 else np.nan

        vwap = quote_vol / total_vol if total_vol > 0 else np.nan
        first_price = grp["price"].iloc[0]
        vwap_dev = (vwap - first_price) / first_price if pd.notna(vwap) and first_price > 0 else np.nan

        returns = grp["price"].pct_change().dropna()
        micro_ret = float(returns.iloc[-1]) if len(returns) > 0 else np.nan
        realized_vol = float(returns.std()) if len(returns) > 1 else np.nan

        # Volume burst: total_vol / rolling median (approximate with single bucket)
        vol_burst = total_vol  # Placeholder — real burst needs multi-bucket context

        features.append({
            "canonical_symbol": symbol,
            "okx_symbol": okx_symbol,
            "ts": int(bucket.timestamp() * 1000),
            "bucket": bucket.isoformat(),
            "okx_trade_count": n,
            "okx_total_volume": float(total_vol),
            "okx_quote_volume": float(quote_vol),
            "okx_buy_volume": float(buy_vol) if has_side else np.nan,
            "okx_sell_volume": float(sell_vol) if has_side else np.nan,
            "okx_trade_imbalance": float(imbalance) if has_side else np.nan,
            "okx_large_trade_count": large_count,
            "okx_large_trade_volume": float(large_vol),
            "okx_large_trade_ratio": float(large_ratio),
            "okx_vwap": float(vwap) if pd.notna(vwap) else np.nan,
            "okx_vwap_deviation": float(vwap_dev) if pd.notna(vwap_dev) else np.nan,
            "okx_micro_return": micro_ret,
            "okx_realized_vol": realized_vol,
            "okx_volume_burst": float(vol_burst),
            "source_start": int(grp["timestamp"].min()),
            "source_end": int(grp["timestamp"].max()),
            "qc_aggressor_side_available": has_side,
            "qc_partial_window": False,
        })

    return pd.DataFrame(features)


def process_symbol(symbol: str, okx_symbol: str) -> dict:
    lf = LOG_DIR / "feature_extract.log"
    log(f"Processing {symbol}...", lf)
    result = {"symbol": symbol, "status": "BLOCKED", "total_input_rows": 0, "timeframes": {}, "error": None}

    raw_file = STAGING / f"{symbol}_trades_raw.json"
    if not raw_file.exists():
        result["error"] = f"Raw file not found: {raw_file.name}"
        return result

    try:
        trades_df = pd.read_json(raw_file)
        result["total_input_rows"] = len(trades_df)
        log(f"  Loaded {len(trades_df)} trades", lf)

        for tf, resample in TIMEFRAMES.items():
            out_dir = MICRO_DIR / f"okx_trades_features_{tf}"
            out_dir.mkdir(parents=True, exist_ok=True)
            features_df = extract_features(trades_df, symbol, okx_symbol, tf, resample)
            out_file = out_dir / f"{symbol}_okx_trades_{tf}.parquet"
            if not features_df.empty:
                features_df.to_parquet(out_file, index=False)
                result["timeframes"][tf] = {"status": "PASS", "rows": len(features_df), "file": str(out_file)}
                log(f"  {tf}: {len(features_df)} rows -> {out_file.name}", lf)
            else:
                result["timeframes"][tf] = {"status": "EMPTY", "rows": 0}
                log(f"  {tf}: no features", lf)

        any_pass = any(r.get("status") == "PASS" for r in result["timeframes"].values())
        result["status"] = "PASS" if any_pass else "EMPTY"
    except Exception as e:
        result["error"] = str(e)
        log(f"  ERROR: {e}", lf)

    return result


def main():
    started_at = datetime.now(timezone.utc).isoformat()
    lf = LOG_DIR / "feature_extract.log"
    log("=" * 60, lf)
    log("OKX Tier-A Feature Extraction (5m/15m/1h)", lf)
    log("=" * 60, lf)

    results = {}
    for symbol, okx_symbol in TIER_A_SYMBOLS.items():
        results[symbol] = process_symbol(symbol, okx_symbol)

    summary = {
        "started_at": started_at,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "symbols": results,
        "pass_count": sum(1 for r in results.values() if r["status"] == "PASS"),
        "total_input": sum(r["total_input_rows"] for r in results.values()),
    }

    out = P1_ROOT / "manifest" / "okx_feature_extraction_results.json"
    with open(out, "w") as f:
        json.dump(summary, f, indent=2)

    log(f"\nPass: {summary['pass_count']}/{len(TIER_A_SYMBOLS)}", lf)
    return summary


if __name__ == "__main__":
    r = main()
    print(json.dumps(r, indent=2))
