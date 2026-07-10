#!/usr/bin/env python3
"""Extract OKX Tier A+B Trade Features — V2 OKX P2 Scale Build.
Extracts 5m, 15m, 1h bar features from OKX tick trades.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
P2_ROOT = REPO_ROOT / "cache" / "v7_lite_scalp_dataset_v2_okx_p2"
STAGING = P2_ROOT / "staging" / "okx"
LOG_DIR = P2_ROOT / "logs"
MICRO_DIR = P2_ROOT / "microstructure"
LOG_DIR.mkdir(parents=True, exist_ok=True)
MICRO_DIR.mkdir(parents=True, exist_ok=True)

SYMBOLS = {
    "BTCUSDT": "BTC-USDT-SWAP", "ETHUSDT": "ETH-USDT-SWAP", "SOLUSDT": "SOL-USDT-SWAP",
    "BNBUSDT": "BNB-USDT-SWAP", "XRPUSDT": "XRP-USDT-SWAP", "DOGEUSDT": "DOGE-USDT-SWAP",
    "ADAUSDT": "ADA-USDT-SWAP", "LINKUSDT": "LINK-USDT-SWAP", "AVAXUSDT": "AVAX-USDT-SWAP",
    "DOTUSDT": "DOT-USDT-SWAP", "LTCUSDT": "LTC-USDT-SWAP", "BCHUSDT": "BCH-USDT-SWAP",
    "NEARUSDT": "NEAR-USDT-SWAP", "APTUSDT": "APT-USDT-SWAP", "ARBUSDT": "ARB-USDT-SWAP",
    "OPUSDT": "OP-USDT-SWAP", "FILUSDT": "FIL-USDT-SWAP", "ATOMUSDT": "ATOM-USDT-SWAP",
    "UNIUSDT": "UNI-USDT-SWAP", "SUIUSDT": "SUI-USDT-SWAP",
}
TF = {"5m": "5min", "15m": "15min", "1h": "1h"}


def log(msg, lf=None):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if lf:
        with open(lf, "a") as f:
            f.write(line + "\n")


def extract(trades_df, symbol, okx_symbol, resample):
    if trades_df.empty:
        return pd.DataFrame()
    df = trades_df.copy()
    for c in ["timestamp", "price", "size"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["timestamp", "price", "size"])
    if df.empty:
        return pd.DataFrame()
    df["ts_dt"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["bucket"] = df["ts_dt"].dt.floor(resample)
    df["quote_volume"] = df["price"] * df["size"]

    feats = []
    for bucket, g in df.groupby("bucket"):
        n = len(g)
        vol = g["size"].sum()
        qvol = g["quote_volume"].sum()
        has_side = "side" in g.columns and g["side"].notna().any()
        buy_vol = g.loc[g["side"].str.lower() == "buy", "size"].sum() if has_side else np.nan
        sell_vol = g.loc[g["side"].str.lower() != "buy", "size"].sum() if has_side else np.nan
        imb = (buy_vol - sell_vol) / (buy_vol + sell_vol) if has_side and (buy_vol + sell_vol) > 0 else np.nan
        med = g["size"].median()
        large = g[g["size"] > 2 * med]
        vwap = qvol / vol if vol > 0 else np.nan
        fp = g["price"].iloc[0]
        vdev = (vwap - fp) / fp if pd.notna(vwap) and fp > 0 else np.nan
        rets = g["price"].pct_change().dropna()
        feats.append({
            "canonical_symbol": symbol, "okx_symbol": okx_symbol,
            "ts": int(bucket.timestamp() * 1000), "bucket": bucket.isoformat(),
            "okx_trade_count": n, "okx_total_volume": float(vol), "okx_quote_volume": float(qvol),
            "okx_buy_volume": float(buy_vol) if has_side else np.nan,
            "okx_sell_volume": float(sell_vol) if has_side else np.nan,
            "okx_trade_imbalance": float(imb) if has_side else np.nan,
            "okx_large_trade_count": int(len(large)), "okx_large_trade_volume": float(large["size"].sum()),
            "okx_large_trade_ratio": len(large) / n if n > 0 else np.nan,
            "okx_vwap": float(vwap) if pd.notna(vwap) else np.nan,
            "okx_vwap_deviation": float(vdev) if pd.notna(vdev) else np.nan,
            "okx_micro_return": float(rets.iloc[-1]) if len(rets) > 0 else np.nan,
            "okx_realized_vol": float(rets.std()) if len(rets) > 1 else np.nan,
            "okx_volume_burst": float(vol),
            "source_start": int(g["timestamp"].min()), "source_end": int(g["timestamp"].max()),
            "qc_aggressor_side_available": has_side, "qc_partial_window": False,
        })
    return pd.DataFrame(feats)


def process_symbol(symbol, okx_symbol):
    lf = LOG_DIR / "feature_extract.log"
    raw = STAGING / f"{symbol}_trades_raw.json"
    if not raw.exists():
        return {"symbol": symbol, "status": "BLOCKED", "timeframes": {}}
    try:
        trades = pd.read_json(raw)
        log(f"  {symbol}: {len(trades)} trades", lf)
        result = {"symbol": symbol, "status": "PASS", "timeframes": {}}
        for tf_name, resample in TF.items():
            out_dir = MICRO_DIR / f"okx_trades_features_{tf_name}"
            out_dir.mkdir(parents=True, exist_ok=True)
            feats = extract(trades, symbol, okx_symbol, resample)
            out_file = out_dir / f"{symbol}_okx_trades_{tf_name}.parquet"
            if not feats.empty:
                feats.to_parquet(out_file, index=False)
                result["timeframes"][tf_name] = {"status": "PASS", "rows": len(feats)}
                log(f"    {tf_name}: {len(feats)} rows", lf)
            else:
                result["timeframes"][tf_name] = {"status": "EMPTY", "rows": 0}
        return result
    except Exception as e:
        return {"symbol": symbol, "status": "FAIL", "error": str(e), "timeframes": {}}


def main():
    started = datetime.now(timezone.utc).isoformat()
    lf = LOG_DIR / "feature_extract.log"
    log("=" * 60, lf)
    log("OKX P2 Tier A+B Feature Extraction", lf)
    results = {}
    for sym, okx in SYMBOLS.items():
        results[sym] = process_symbol(sym, okx)
    summary = {"started_at": started, "ended_at": datetime.now(timezone.utc).isoformat(),
               "symbols": results, "pass_count": sum(1 for r in results.values() if r["status"] == "PASS")}
    out = P2_ROOT / "manifest" / "okx_feature_extraction_results.json"
    with open(out, "w") as f:
        json.dump(summary, f, indent=2)
    log(f"Pass: {summary['pass_count']}/{len(SYMBOLS)}", lf)
    return summary


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
