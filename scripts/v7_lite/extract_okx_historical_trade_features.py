#!/usr/bin/env python3
"""OKX Historical Mini Build — extracts features from downloaded historical data."""
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
CACHE = REPO / "cache" / "v7_lite_okx_historical_resolution"
STAGING = CACHE / "staging" / "okx"
SAMPLES = CACHE / "samples"
LOG_DIR = CACHE / "logs"
OUT_DIR = SAMPLES / "features"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SYMBOLS = {"BTCUSDT": "BTC-USDT-SWAP", "ETHUSDT": "ETH-USDT-SWAP", "SOLUSDT": "SOL-USDT-SWAP"}
TF = {"5m": "5min", "15m": "15min", "1h": "1h"}


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")
    with open(LOG_DIR / "feature_extract.log", "a") as f:
        f.write(f"[{ts}] {msg}\n")


def extract_trade_features(trades, symbol, okx_sym, tf, resample):
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame(trades)
    for c in ["ts", "px", "sz"]:
        if c not in df.columns:
            return pd.DataFrame()
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["ts", "px", "sz"])
    if df.empty:
        return pd.DataFrame()
    df["ts_dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df["bucket"] = df["ts_dt"].dt.floor(resample)
    df["qv"] = df["px"] * df["sz"]

    feats = []
    for bucket, g in df.groupby("bucket"):
        n = len(g)
        vol = g["sz"].sum()
        qvol = g["qv"].sum()
        has_side = "side" in g.columns and g["side"].notna().any()
        bw = g.loc[g["side"].str.lower() == "buy", "sz"].sum() if has_side else np.nan
        sw = g.loc[g["side"].str.lower() != "buy", "sz"].sum() if has_side else np.nan
        imb = (bw - sw) / (bw + sw) if has_side and (bw + sw) > 0 else np.nan
        med = g["sz"].median()
        lm = g[g["sz"] > 2 * med]
        vw = qvol / vol if vol > 0 else np.nan
        fp = g["px"].iloc[0]
        vd = (vw - fp) / fp if pd.notna(vw) and fp > 0 else np.nan
        ret = g["px"].pct_change().dropna()
        feats.append({
            "canonical_symbol": symbol, "okx_symbol": okx_sym,
            "ts": int(bucket.timestamp() * 1000), "bucket": bucket.isoformat(),
            "okx_trade_count": n, "okx_total_volume": float(vol), "okx_quote_volume": float(qvol),
            "okx_buy_volume": float(bw) if has_side else np.nan,
            "okx_sell_volume": float(sw) if has_side else np.nan,
            "okx_trade_imbalance": float(imb) if has_side else np.nan,
            "okx_large_trade_count": int(len(lm)), "okx_large_trade_volume": float(lm["sz"].sum()),
            "okx_large_trade_ratio": len(lm) / n if n > 0 else np.nan,
            "okx_vwap": float(vw) if pd.notna(vw) else np.nan,
            "okx_vwap_deviation": float(vd) if pd.notna(vd) else np.nan,
            "okx_micro_return": float(ret.iloc[-1]) if len(ret) > 0 else np.nan,
            "okx_realized_vol": float(ret.std()) if len(ret) > 1 else np.nan,
            "okx_volume_burst": float(vol),
            "source_start": int(g["ts"].min()), "source_end": int(g["ts"].max()),
            "qc_aggressor_side_available": has_side, "qc_partial_window": False,
            "source_type": "okx_historical",
        })
    return pd.DataFrame(feats)


def extract_candle_features(candles, symbol, okx_sym, tf, resample):
    """Extract candle-based features as alternative to trade features."""
    if not candles:
        return pd.DataFrame()
    df = pd.DataFrame(candles)
    # Format from history-candles: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
    cols = ["ts", "open", "high", "low", "close", "vol", "volCcy", "volCcyQuote", "confirm"]
    present = [c for c in cols if c in df.columns]
    if len(present) < 5:
        # Ok data maybe came as list of lists
        try:
            df = pd.DataFrame(candles, columns=cols)
        except:
            return pd.DataFrame()
    for c in ["ts", "open", "high", "low", "close", "vol"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["ts", "close"])
    df["ts_dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df  # Return raw candles — they're already aggregated


def build_historical_funding_features(symbol, okx_sym):
    """Build funding features from historical funding data."""
    lf = LOG_DIR / "feature_extract.log"
    funding_file = STAGING / f"{symbol}_funding_historical.json"
    if not funding_file.exists():
        return None
    with open(funding_file) as f:
        funding = json.load(f)
    if not funding:
        return None
    df = pd.DataFrame(funding)
    for c in ["fundingTime", "fundingRate"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["fundingTime", "fundingRate"])
    df["ts"] = df["fundingTime"]
    df["symbol"] = symbol
    log(f"  {symbol} funding: {len(df)} rows")
    return df


def main():
    log("=" * 60)
    log("OKX Historical Mini Build")
    log("=" * 60)

    results = {"funding_features": {}, "status": "PARTIAL"}

    # Try to build funding features (we know funding-rate-history works historically)
    log("\n--- Historical Funding Features ---")
    for sym, okx in SYMBOLS.items():
        fd = build_historical_funding_features(sym, okx)
        if fd is not None and not fd.empty:
            out = OUT_DIR / f"{sym}_funding_historical.parquet"
            fd.to_parquet(out, index=False)
            results["funding_features"][sym] = {"rows": len(fd), "file": str(out)}
            log(f"  Saved {len(fd)} funding features -> {out.name}")

    # Try to build trade features from history-trades if data exists
    log("\n--- History Trades (attempting to load) ---")
    for tf_name, resample in TF.items():
        trade_file = STAGING / f"BTCUSDT_trades_historical.json"
        if trade_file.exists():
            with open(trade_file) as f:
                trades = json.load(f)
            if trades:
                feats = extract_trade_features(trades, "BTCUSDT", "BTC-USDT-SWAP", tf_name, resample)
                if not feats.empty:
                    out = OUT_DIR / f"okx_historical_trade_features_{tf_name}.parquet"
                    feats.to_parquet(out, index=False)
                    log(f"  {tf_name}: {len(feats)} rows -> {out.name}")

    # Check if any features were produced
    feature_files = list(OUT_DIR.glob("*.parquet"))
    if feature_files:
        results["status"] = "PASS"
        results["files"] = [str(f) for f in feature_files]
        total_mb = sum(f.stat().st_size for f in feature_files) / 1e6
        results["total_mb"] = round(total_mb, 2)
        log(f"\nCreated {len(feature_files)} feature files ({total_mb:.2f} MB)")

    log(f"\nStatus: {results['status']}")
    return results


if __name__ == "__main__":
    r = main()
    print(json.dumps(r, indent=2))
