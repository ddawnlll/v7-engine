#!/usr/bin/env python3
"""Extract OKX Trade Features — Exchange-Agnostic Microstructure V2.

Extracts 5m bar features from OKX tick trades:
- Trade count
- Total volume
- Buy/sell volume (if available)
- Trade imbalance
- Large trade ratio
- VWAP
- VWAP deviation
- Realized volatility
- Volume burst
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SMOKE_ROOT = REPO_ROOT / "cache" / "v7_lite_scalp_dataset_v2_p0_smoke"
STAGING = SMOKE_ROOT / "staging" / "okx"
LOG_DIR = SMOKE_ROOT / "logs"
OUTPUT_DIR = SMOKE_ROOT / "microstructure" / "okx_trades_features"

LOG_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def log_message(msg: str, log_file: Optional[Path] = None):
    """Log message to stdout and optional file."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if log_file:
        with open(log_file, "a") as f:
            f.write(line + "\n")


def extract_trade_features(trades_df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Extract 5m bar features from tick trades."""
    
    if trades_df.empty:
        return pd.DataFrame()
    
    # Ensure timestamp is numeric (milliseconds)
    trades_df["timestamp"] = pd.to_numeric(trades_df["timestamp"], errors="coerce")
    trades_df["price"] = pd.to_numeric(trades_df["price"], errors="coerce")
    trades_df["size"] = pd.to_numeric(trades_df["size"], errors="coerce")
    
    # Drop invalid rows
    trades_df = trades_df.dropna(subset=["timestamp", "price", "size"])
    
    if trades_df.empty:
        return pd.DataFrame()
    
    # Convert to datetime
    trades_df["ts_dt"] = pd.to_datetime(trades_df["timestamp"], unit="ms", utc=True)
    
    # Create 5m buckets
    trades_df["bucket"] = trades_df["ts_dt"].dt.floor("5min")
    
    # Group by 5m bucket
    features = []
    
    for bucket, group in trades_df.groupby("bucket"):
        bucket_ts = int(bucket.timestamp() * 1000)
        
        # Basic stats
        trade_count = len(group)
        total_volume = group["size"].sum()
        
        # Buy/sell analysis (if side column exists)
        buy_volume = np.nan
        sell_volume = np.nan
        trade_imbalance = np.nan
        large_trade_ratio = np.nan
        
        if "side" in group.columns:
            # OKX side: "buy" or "sell"
            buy_mask = group["side"].str.lower() == "buy"
            sell_mask = group["side"].str.lower() == "sell"
            
            buy_volume = group.loc[buy_mask, "size"].sum()
            sell_volume = group.loc[sell_mask, "size"].sum()
            
            if buy_volume + sell_volume > 0:
                trade_imbalance = (buy_volume - sell_volume) / (buy_volume + sell_volume)
            
            # Large trade ratio (> 2x median size)
            median_size = group["size"].median()
            large_trades = group[group["size"] > 2 * median_size]
            if trade_count > 0:
                large_trade_ratio = len(large_trades) / trade_count
        else:
            # AGGRESSOR_SIDE_UNAVAILABLE
            pass
        
        # VWAP
        if total_volume > 0:
            vwap = (group["price"] * group["size"]).sum() / total_volume
        else:
            vwap = np.nan
        
        # VWAP deviation (from first price in bucket)
        first_price = group["price"].iloc[0]
        vwap_deviation = (vwap - first_price) / first_price if pd.notna(vwap) and first_price > 0 else np.nan
        
        # Realized volatility (returns std)
        returns = group["price"].pct_change().dropna()
        realized_vol = returns.std() if len(returns) > 1 else np.nan
        
        # Volume burst (volume relative to rolling average)
        # For now, use the volume itself as a proxy
        volume_burst = total_volume  # Placeholder
        
        # Source timestamps
        source_start = int(group["timestamp"].min())
        source_end = int(group["timestamp"].max())
        
        features.append({
            "symbol": symbol,
            "exchange_symbol": f"{symbol}-USDT-SWAP",
            "ts": bucket_ts,
            "bucket": bucket.isoformat(),
            "okx_trade_count_5m": trade_count,
            "okx_total_volume_5m": total_volume,
            "okx_buy_volume_5m": buy_volume,
            "okx_sell_volume_5m": sell_volume,
            "okx_trade_imbalance_5m": trade_imbalance,
            "okx_large_trade_ratio_5m": large_trade_ratio,
            "okx_vwap_5m": vwap,
            "okx_vwap_deviation_5m": vwap_deviation,
            "okx_realized_vol_5m": realized_vol,
            "okx_volume_burst_5m": volume_burst,
            "source_start": source_start,
            "source_end": source_end,
        })
    
    return pd.DataFrame(features)


def process_symbol(symbol: str) -> dict:
    """Process OKX trades for one symbol."""
    log_file = LOG_DIR / "feature_extract.log"
    log_message(f"Processing OKX trades for {symbol}...", log_file)
    
    result = {
        "symbol": symbol,
        "status": "BLOCKED",
        "input_rows": 0,
        "output_rows": 0,
        "output_file": None,
        "error": None,
    }
    
    # Find raw trade file
    raw_file = STAGING / f"{symbol}_trades_raw.json"
    
    if not raw_file.exists():
        result["error"] = f"Raw file not found: {raw_file.name}"
        log_message(f"SKIP {symbol}: {result['error']}", log_file)
        return result
    
    try:
        # Load raw trades
        trades_df = pd.read_json(raw_file)
        result["input_rows"] = len(trades_df)
        
        log_message(f"Loaded {len(trades_df)} trades for {symbol}", log_file)
        
        # Extract features
        features_df = extract_trade_features(trades_df, symbol)
        
        if features_df.empty:
            result["error"] = "No features extracted"
            log_message(f"No features extracted for {symbol}", log_file)
            return result
        
        result["output_rows"] = len(features_df)
        
        # Save to parquet
        output_file = OUTPUT_DIR / f"{symbol}_okx_trades_5m.parquet"
        features_df.to_parquet(output_file, index=False)
        
        result["status"] = "PASS"
        result["output_file"] = str(output_file)
        
        log_message(f"OKX trade features saved: {len(features_df)} rows to {output_file.name}", log_file)
        
    except Exception as e:
        result["error"] = str(e)
        log_message(f"OKX trade feature extraction failed for {symbol}: {e}", log_file)
    
    return result


def main():
    """Main feature extraction orchestrator."""
    started_at = datetime.now(timezone.utc).isoformat()
    log_file = LOG_DIR / "feature_extract.log"
    
    log_message("=" * 60, log_file)
    log_message("OKX Trade Feature Extraction — Exchange-Agnostic Microstructure V2", log_file)
    log_message(f"Started: {started_at}", log_file)
    log_message("=" * 60, log_file)
    
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    results = {}
    
    for symbol in symbols:
        results[symbol] = process_symbol(symbol)
    
    # Summary
    total_input = sum(r["input_rows"] for r in results.values())
    total_output = sum(r["output_rows"] for r in results.values())
    pass_count = sum(1 for r in results.values() if r["status"] == "PASS")
    
    log_message(f"\n{'=' * 60}", log_file)
    log_message(f"Summary: {pass_count}/{len(symbols)} symbols processed", log_file)
    log_message(f"Total input rows: {total_input:,}", log_file)
    log_message(f"Total output rows: {total_output:,}", log_file)
    
    # Save results
    output_file = SMOKE_ROOT / "manifest" / "okx_feature_extraction_results.json"
    with open(output_file, "w") as f:
        json.dump({
            "started_at": started_at,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "symbols": results,
            "summary": {
                "total_input_rows": total_input,
                "total_output_rows": total_output,
                "pass_count": pass_count,
            }
        }, f, indent=2)
    
    log_message(f"Results saved to {output_file}", log_file)
    
    return results


if __name__ == "__main__":
    results = main()
    print(json.dumps(results, indent=2))
