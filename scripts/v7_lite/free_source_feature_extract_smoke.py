#!/usr/bin/env python3
"""Free Source Feature Extract Smoke — tiny demo from any free source."""
import json, gzip, zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
CACHE = REPO / "cache" / "v7_lite_free_data_source_audit"
STAGING = CACHE / "staging"
FEAT_DIR = CACHE / "samples" / "features"
LOG_DIR = CACHE / "logs"
FEAT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
TF = {"5m": "5min", "15m": "15min", "1h": "1h"}


def log(m):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {m}")
    with open(LOG_DIR / "feature_extract.log", "a") as f:
        f.write(f"[{ts}] {m}\n")


def extract_from_agg_trades(csv_path: Path, symbol: str, source_label: str):
    """Extract features from Binance aggTrade CSV."""
    log(f"Reading aggTrades: {csv_path}")
    try:
        df = pd.read_csv(csv_path)
    except:
        df = pd.read_csv(csv_path, compression="gzip")
    log(f"  Columns: {list(df.columns)}")
    log(f"  Rows: {len(df)}")

    # Binance aggTrade schema: A=aggTradeId, p=price, q=qty, f=firstTradeId, l=lastTradeId, T=time, m=buyerMaker, M=bestMatch
    # Map columns
    col_map = {}
    for expected, alternatives in [("A", ["Aggregate trade ID", "agg_trade_id"]),
                                   ("p", ["Price", "price"]),
                                   ("q", ["Quantity", "qty"]),
                                   ("T", ["Trade time", "timestamp"]),
                                   ("m", ["Is buyer maker", "buyer_maker"]),
                                   ("M", ["Best match", "best_match"])]:
        for c in alternatives:
            if c in df.columns:
                col_map[expected] = c
                break
        if expected not in col_map and expected in df.columns:
            col_map[expected] = expected

    log(f"  Mapped columns: {col_map}")

    df = df.rename(columns={col_map.get("p", "p"): "price",
                            col_map.get("q", "q"): "size",
                            col_map.get("T", "T"): "ts",
                            col_map.get("m", "m"): "buyer_maker"})
    for c in ["price", "size", "ts"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["ts", "price", "size"])
    df["ts_dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df["qv"] = df["price"] * df["size"]
    has_side = "buyer_maker" in df.columns
    log(f"  Aggressor side (buyer_maker): {has_side}")

    for tf_name, resample in TF.items():
        df["bucket"] = df["ts_dt"].dt.floor(resample)
        feats = []
        for bucket, g in df.groupby("bucket"):
            n = len(g)
            vol = g["size"].sum()
            qvol = g["qv"].sum()
            if has_side:
                buy_vol = g.loc[~g["buyer_maker"].astype(bool), "size"].sum() if "buyer_maker" in g.columns else np.nan
                sell_vol = g.loc[g["buyer_maker"].astype(bool), "size"].sum() if "buyer_maker" in g.columns else np.nan
                imb = (buy_vol - sell_vol) / (buy_vol + sell_vol) if (buy_vol + sell_vol) > 0 else np.nan
            else:
                buy_vol = sell_vol = imb = np.nan
            med = g["size"].median()
            large = g[g["size"] > 2 * med]
            vwap = qvol / vol if vol > 0 else np.nan
            fp = g["price"].iloc[0]
            vdev = (vwap - fp) / fp if pd.notna(vwap) and fp > 0 else np.nan
            ret = g["price"].pct_change().dropna()
            feats.append({
                "source": source_label, "exchange": "binance", "canonical_symbol": symbol,
                "provider_symbol": symbol, "ts": int(bucket.timestamp() * 1000), "bucket": bucket.isoformat(),
                "trade_count": n, "total_volume": float(vol), "quote_volume": float(qvol),
                "buy_volume": float(buy_vol) if has_side else np.nan,
                "sell_volume": float(sell_vol) if has_side else np.nan,
                "trade_imbalance": float(imb) if has_side else np.nan,
                "large_trade_count": int(len(large)), "large_trade_volume": float(large["size"].sum()),
                "large_trade_ratio": len(large) / n if n > 0 else np.nan,
                "vwap": float(vwap) if pd.notna(vwap) else np.nan,
                "micro_return": float(ret.iloc[-1]) if len(ret) > 0 else np.nan,
                "realized_vol": float(ret.std()) if len(ret) > 1 else np.nan,
                "volume_burst": float(vol),
                "source_start": int(g["ts"].min()), "source_end": int(g["ts"].max()),
                "qc_aggressor_side_available": has_side, "qc_partial_window": False,
            })
        result = pd.DataFrame(feats)
        out = FEAT_DIR / f"free_source_trade_features_{tf_name}.parquet"
        result.to_parquet(out, index=False)
        log(f"  {tf_name}: {len(result)} rows -> {out.name}")


def extract_from_csv(csv_path: Path, symbol: str, source_label: str):
    """Extract features from a generic trade CSV."""
    log(f"Reading CSV: {csv_path}")
    try:
        df = pd.read_csv(csv_path)
    except:
        df = pd.read_csv(csv_path, compression="gzip")
    log(f"  Columns: {list(df.columns)}")
    log(f"  Rows: {len(df)}")

    # Auto-detect columns
    ts_col = next((c for c in df.columns if c in ["timestamp", "ts", "time", "Trade time", "T"]), None)
    price_col = next((c for c in df.columns if c in ["price", "Price", "px", "p"]), None)
    size_col = next((c for c in df.columns if c in ["size", "Size", "qty", "q", "Quantity", "volume", "sz"]), None)
    side_col = next((c for c in df.columns if c in ["side", "Side", "is_buyer_maker", "m", "buyer_maker"]), None)

    if not all([ts_col, price_col, size_col]):
        log(f"  Cannot detect required columns. ts={ts_col} price={price_col} size={size_col}")
        return

    log(f"  Auto-detect: ts={ts_col} price={price_col} size={size_col} side={side_col}")

    df = df.rename(columns={ts_col: "ts_raw", price_col: "price", size_col: "size"})
    if side_col:
        df["buyer_maker"] = df[side_col]
        has_side = True
    else:
        has_side = False

    df["ts"] = pd.to_numeric(df["ts_raw"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["size"] = pd.to_numeric(df["size"], errors="coerce")
    df = df.dropna(subset=["ts", "price", "size"])
    df = df[df["ts"] > 1e12].copy()  # Filter ms timestamps
    df["ts_dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df["qv"] = df["price"] * df["size"]

    for tf_name, resample in TF.items():
        df["bucket"] = df["ts_dt"].dt.floor(resample)
        feats = []
        for bucket, g in df.groupby("bucket"):
            n = len(g); vol = g["size"].sum(); qvol = g["qv"].sum()
            buy_vol = sell_vol = imb = np.nan
            if has_side:
                buy_vol = g.loc[g["buyer_maker"] == 0, "size"].sum() if 0 in g["buyer_maker"].values else g.loc[~g["buyer_maker"].astype(bool), "size"].sum()
                sell_vol = vol - buy_vol
                imb = (buy_vol - sell_vol) / (buy_vol + sell_vol) if (buy_vol + sell_vol) > 0 else np.nan
            med = g["size"].median(); large = g[g["size"] > 2 * med]
            vwap = qvol / vol if vol > 0 else np.nan
            fp = g["price"].iloc[0]; vdev = (vwap - fp) / fp if pd.notna(vwap) and fp > 0 else np.nan
            ret = g["price"].pct_change().dropna()
            feats.append({"source": source_label, "exchange": "binance", "canonical_symbol": symbol,
                          "provider_symbol": symbol, "ts": int(bucket.timestamp() * 1000),
                          "trade_count": n, "total_volume": float(vol), "quote_volume": float(qvol),
                          "buy_volume": float(buy_vol) if has_side else np.nan,
                          "sell_volume": float(sell_vol) if has_side else np.nan,
                          "trade_imbalance": float(imb) if has_side else np.nan,
                          "large_trade_count": int(len(large)), "large_trade_volume": float(large["size"].sum()),
                          "large_trade_ratio": len(large) / n if n > 0 else np.nan,
                          "vwap": float(vwap) if pd.notna(vwap) else np.nan,
                          "micro_return": float(ret.iloc[-1]) if len(ret) > 0 else np.nan,
                          "realized_vol": float(ret.std()) if len(ret) > 1 else np.nan,
                          "volume_burst": float(vol),
                          "source_start": int(g["ts"].min()), "source_end": int(g["ts"].max()),
                          "qc_aggressor_side_available": has_side, "qc_partial_window": False})
        result_df = pd.DataFrame(feats)
        out = FEAT_DIR / f"free_source_trade_features_{tf_name}.parquet"
        result_df.to_parquet(out, index=False)
        log(f"  {tf_name}: {len(result_df)} rows -> {out.name}")


def main():
    log("=" * 60 + "\nFREE SOURCE FEATURE EXTRACT SMOKE\n" + "=" * 60)

    # Search for any downloaded trade CSV/zip
    candidates = []
    for d in [STAGING / "tardis", STAGING / "binance_vision", STAGING / "bybit", STAGING / "okx"]:
        if d.exists():
            for f in d.iterdir():
                if f.suffix in [".csv", ".gz", ".zip"] and not f.name.startswith("."):
                    candidates.append(f)
    log(f"Found {len(candidates)} candidate files")
    for f in candidates:
        log(f"  {f.name} ({f.stat().st_size} bytes)")

    # Try Binance aggTrades ZIP first
    for f in candidates:
        if "aggTrade" in f.name or (f.suffix == ".zip" and "BTCUSDT" in f.name):
            log(f"\nTrying: {f}")
            if f.suffix == ".zip":
                import zipfile
                try:
                    with zipfile.ZipFile(f) as zf:
                        for name in zf.namelist():
                            if name.endswith(".csv"):
                                with zf.open(name) as csvf:
                                    extract_from_agg_trades(csvf, "BTCUSDT", "binance_vision")
                                break
                except Exception as e:
                    log(f"  ZIP error: {e}")
            break
    else:
        # Try Tardis CSV
        for f in candidates:
            if "trades" in f.name or "binance" in f.name:
                log(f"\nTrying: {f}")
                try:
                    extract_from_csv(f, "BTCUSDT", "tardis_sample")
                except Exception as e:
                    log(f"  Error: {e}")
                break
        else:
            log("\nNo usable trade files found to extract features from.")

    feats = list(FEAT_DIR.glob("*.parquet"))
    total_rows = sum(pd.read_parquet(f).shape[0] for f in feats) if feats else 0
    log(f"\nFeature files: {len(feats)}, total rows: {total_rows}")
    return {"files": len(feats), "rows": total_rows}


if __name__ == "__main__":
    r = main()
    print(json.dumps(r, indent=2))
