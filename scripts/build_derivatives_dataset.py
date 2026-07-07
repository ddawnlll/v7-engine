"""
Build a combined training dataset: OHLCV + Funding Rate + OI + Premium Index.
Downloads derivatives from KEDevO HuggingFace, joins with local data lake,
saves as a unified parquet for training.
"""
import io, json, logging, os, sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HF_BASE = "https://huggingface.co/datasets/KEDevO/crypto-market-datasets/resolve/main"
DATA_LAKE = Path("data_lake/raw/binance/um/klines")
OUTPUT_DIR = Path("data/raw")

def download_parquet(url: str) -> pd.DataFrame:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return pq.read_table(io.BytesIO(r.content)).to_pandas()

def get_hf_siblings() -> list:
    r = requests.get("https://huggingface.co/api/datasets/KEDevO/crypto-market-datasets", timeout=30)
    return r.json()["siblings"]

def load_derivatives(siblings: list, data_type: str, symbol: str) -> pd.DataFrame:
    """Load and resample derivatives data from KEDevO."""
    files = [s["rfilename"] for s in siblings if data_type in s["rfilename"] and symbol in s["rfilename"]]
    logger.info(f"{data_type}: found {len(files)} files")
    
    all_dfs = []
    for fpath in sorted(files):
        url = f"{HF_BASE}/{fpath}"
        try:
            df = download_parquet(url)
            all_dfs.append(df)
        except Exception as e:
            logger.warning(f"  skip {fpath}: {e}")
    
    if not all_dfs:
        return pd.DataFrame()
    
    result = pd.concat(all_dfs, ignore_index=True)
    
    # Handle different schemas
    if data_type == "funding_rates":
        result = result.rename(columns={"funding_rate": "value"})
        result["timestamp"] = result["timestamp"] // 3_600_000 * 3_600_000
    elif data_type == "open_interest":
        result = result.rename(columns={"open_interest": "value"})
        result["timestamp"] = result["timestamp"] // 3_600_000 * 3_600_000
    elif data_type == "premium_index":
        if "open_time" in result.columns:
            result["timestamp"] = result["open_time"]
        result = result.rename(columns={"close": "value"})
        result["timestamp"] = result["timestamp"] // 3_600_000 * 3_600_000
    
    # Aggregate to 1h
    result = result.groupby("timestamp")["value"].last().reset_index()
    result = result.sort_values("timestamp").drop_duplicates(subset=["timestamp"])
    logger.info(f"  -> {len(result)} hourly records: {result.timestamp.min()} -> {result.timestamp.max()}")
    return result

def build_dataset(symbol: str = "BTCUSDT", interval: str = "1h"):
    logger.info(f"Building {symbol} {interval} dataset with derivatives...")
    
    # 1. Load OHLCV from data lake
    ohlcv_path = DATA_LAKE / symbol / f"{symbol}_{interval}_combined.parquet"
    if ohlcv_path.exists():
        ohlcv = pd.read_parquet(ohlcv_path)
        logger.info(f"OHLCV: {len(ohlcv)} rows")
    else:
        # Try monthly directory
        monthly_dir = DATA_LAKE / symbol / interval
        if monthly_dir.exists():
            dfs = []
            for f in sorted(monthly_dir.glob("*.parquet")):
                dfs.append(pd.read_parquet(f))
            ohlcv = pd.concat(dfs, ignore_index=True)
            logger.info(f"OHLCV (monthly): {len(ohlcv)} rows")
        else:
            logger.error(f"No OHLCV data for {symbol}")
            return
    
    ohlcv = ohlcv.sort_values("timestamp").reset_index(drop=True)
    
    # 2. Load derivatives from KEDevO
    siblings = get_hf_siblings()
    funding = load_derivatives(siblings, "funding_rates", symbol)
    oi = load_derivatives(siblings, "open_interest", symbol)
    premium = load_derivatives(siblings, "premium_index", symbol)
    
    # 3. Merge: forward-fill derivatives onto OHLCV timestamps
    merged = ohlcv[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    
    for name, df in [("funding_rate", funding), ("open_interest", oi), ("premium_index", premium)]:
        merged[name] = np.nan
        if len(df) == 0:
            continue
        ts_arr = df["timestamp"].values
        val_arr = df["value"].values
        for i, ts in enumerate(merged["timestamp"].values):
            idx = np.searchsorted(ts_arr, ts, side="right") - 1
            if idx >= 0 and abs(ts - ts_arr[idx]) < 7200000:  # within 2h
                merged.loc[i, name] = val_arr[idx]
        coverage = merged[name].notna().sum()
        logger.info(f"  {name}: {coverage}/{len(merged)} bars covered ({100*coverage/len(merged):.0f}%)")
    
    # 4. Fill remaining NaN with 0 so features always compute
    for col in ["funding_rate", "open_interest", "premium_index"]:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0.0)
    
    # 5. Save as parquet with symbol column
    merged["symbol"] = symbol
    merged["timestamp"] = merged["timestamp"].astype(np.int64)
    
    output_dir = OUTPUT_DIR / symbol
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{symbol}_{interval}_with_derivatives.parquet"
    
    table = pa.Table.from_pandas(merged)
    pq.write_table(table, str(output_path), compression="ZSTD")
    logger.info(f"Saved {len(merged)} rows to {output_path}")
    
    # Also create symlink for training
    print(f"\nDataset ready: {output_path}")
    print(f"  Columns: {list(merged.columns)}")
    print(f"  Time range: {merged.timestamp.min()} -> {merged.timestamp.max()}")
    print(f"  Funding rate coverage: {merged.funding_rate.notna().sum()} bars")
    print(f"  OI coverage: {merged.open_interest.notna().sum()} bars")
    print(f"  Premium index coverage: {merged.premium_index.notna().sum()} bars")

if __name__ == "__main__":
    build_dataset("BTCUSDT", "1h")
