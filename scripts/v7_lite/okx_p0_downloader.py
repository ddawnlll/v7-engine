#!/usr/bin/env python3
"""OKX P0 Smoke Downloader — Exchange-Agnostic Microstructure V2.

Downloads OKX tick trades, funding rates for BTC-USDT-SWAP, ETH-USDT-SWAP, SOL-USDT-SWAP.
Uses public REST endpoints for a tiny recent window.
No API key required for public market data.
"""

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SMOKE_ROOT = REPO_ROOT / "cache" / "v7_lite_scalp_dataset_v2_p0_smoke"
STAGING = SMOKE_ROOT / "staging" / "okx"
LOG_DIR = SMOKE_ROOT / "logs"

STAGING.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# OKX instruments for P0 smoke
SYMBOLS = {
    "BTC-USDT-SWAP": "BTCUSDT",
    "ETH-USDT-SWAP": "ETHUSDT",
    "SOL-USDT-SWAP": "SOLUSDT",
}

# OKX public endpoints
OKX_TRADES_URL = "https://www.okx.com/api/v5/market/trades"
OKX_FUNDING_URL = "https://www.okx.com/api/v5/public/funding-rate"
OKX_TICKER_URL = "https://www.okx.com/api/v5/market/ticker"

# Rate limiting
REQUEST_DELAY = 0.2  # seconds between requests


def log_message(msg: str, log_file: Optional[Path] = None):
    """Log message to stdout and optional file."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if log_file:
        with open(log_file, "a") as f:
            f.write(line + "\n")


def compute_sha256(filepath: Path) -> str:
    """Compute SHA256 hash of file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def test_okx_reachability() -> dict:
    """Test OKX API reachability."""
    log_file = LOG_DIR / "okx_download.log"
    log_message("Testing OKX reachability...", log_file)
    
    result = {
        "reachable": False,
        "ticker_status": None,
        "trades_status": None,
        "funding_status": None,
        "error": None,
        "latency_ms": None,
    }
    
    try:
        # Test ticker endpoint
        start = time.time()
        resp = requests.get(OKX_TICKER_URL, params={"instId": "BTC-USDT-SWAP"}, timeout=10)
        latency = (time.time() - start) * 1000
        result["latency_ms"] = round(latency, 2)
        result["ticker_status"] = resp.status_code
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == "0" and data.get("data"):
                result["reachable"] = True
                log_message(f"OKX reachable. Latency: {latency:.0f}ms", log_file)
            else:
                result["error"] = f"API error: {data.get('msg', 'unknown')}"
                log_message(f"OKX API error: {data.get('msg')}", log_file)
        else:
            result["error"] = f"HTTP {resp.status_code}"
            log_message(f"OKX HTTP error: {resp.status_code}", log_file)
            
    except Exception as e:
        result["error"] = str(e)
        log_message(f"OKX reachability failed: {e}", log_file)
    
    return result


def download_okx_trades(inst_id: str, max_trades: int = 500) -> dict:
    """Download recent OKX tick trades."""
    log_file = LOG_DIR / "okx_download.log"
    log_message(f"Downloading OKX trades for {inst_id}...", log_file)
    
    result = {
        "status": "BLOCKED",
        "rows": 0,
        "file": None,
        "checksum": None,
        "error": None,
    }
    
    try:
        all_trades = []
        after = ""
        
        for page in range(5):  # Max 5 pages
            params = {"instId": inst_id, "limit": str(min(max_trades - len(all_trades), 100))}
            if after:
                params["after"] = after
            
            resp = requests.get(OKX_TRADES_URL, params=params, timeout=10)
            time.sleep(REQUEST_DELAY)
            
            if resp.status_code != 200:
                result["error"] = f"HTTP {resp.status_code}"
                log_message(f"OKX trades HTTP error: {resp.status_code}", log_file)
                break
            
            data = resp.json()
            if data.get("code") != "0":
                result["error"] = f"API error: {data.get('msg')}"
                break
            
            trades = data.get("data", [])
            if not trades:
                break
            
            all_trades.extend(trades)
            after = trades[-1].get("ts", "")
            
            if len(all_trades) >= max_trades:
                break
        
        if all_trades:
            # Convert to DataFrame
            df = pd.DataFrame(all_trades)
            
            # Rename columns to standard format
            col_map = {
                "ts": "timestamp",
                "px": "price",
                "sz": "size",
                "side": "side",
                "instId": "inst_id",
            }
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
            
            # Save to staging
            symbol = SYMBOLS.get(inst_id, inst_id.replace("-", "_"))
            output_file = STAGING / f"{symbol}_trades_raw.json"
            df.to_json(output_file, orient="records", indent=2)
            
            result["status"] = "PASS"
            result["rows"] = len(df)
            result["file"] = str(output_file)
            result["checksum"] = compute_sha256(output_file)
            
            log_message(f"OKX trades saved: {len(df)} rows to {output_file.name}", log_file)
        else:
            result["error"] = "No trades returned"
            log_message(f"OKX trades: no data returned for {inst_id}", log_file)
            
    except Exception as e:
        result["error"] = str(e)
        log_message(f"OKX trades download failed: {e}", log_file)
    
    return result


def download_okx_funding(inst_id: str) -> dict:
    """Download OKX funding rate history."""
    log_file = LOG_DIR / "okx_download.log"
    log_message(f"Downloading OKX funding for {inst_id}...", log_file)
    
    result = {
        "status": "BLOCKED",
        "rows": 0,
        "file": None,
        "checksum": None,
        "error": None,
    }
    
    try:
        all_funding = []
        
        for page in range(3):  # Max 3 pages
            params = {"instId": inst_id, "limit": "100"}
            if all_funding:
                params["after"] = all_funding[-1].get("fundingTime", "")
            
            resp = requests.get(OKX_FUNDING_URL, params=params, timeout=10)
            time.sleep(REQUEST_DELAY)
            
            if resp.status_code != 200:
                result["error"] = f"HTTP {resp.status_code}"
                break
            
            data = resp.json()
            if data.get("code") != "0":
                result["error"] = f"API error: {data.get('msg')}"
                break
            
            funding = data.get("data", [])
            if not funding:
                break
            
            all_funding.extend(funding)
        
        if all_funding:
            df = pd.DataFrame(all_funding)
            
            # Rename columns
            col_map = {
                "fundingTime": "timestamp",
                "fundingRate": "funding_rate",
                "instId": "inst_id",
            }
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
            
            # Save to staging
            symbol = SYMBOLS.get(inst_id, inst_id.replace("-", "_"))
            output_file = STAGING / f"{symbol}_funding_raw.json"
            df.to_json(output_file, orient="records", indent=2)
            
            result["status"] = "PASS"
            result["rows"] = len(df)
            result["file"] = str(output_file)
            result["checksum"] = compute_sha256(output_file)
            
            log_message(f"OKX funding saved: {len(df)} rows to {output_file.name}", log_file)
        else:
            result["error"] = "No funding data returned"
            log_message(f"OKX funding: no data returned for {inst_id}", log_file)
            
    except Exception as e:
        result["error"] = str(e)
        log_message(f"OKX funding download failed: {e}", log_file)
    
    return result


def main():
    """Main OKX download orchestrator."""
    started_at = datetime.now(timezone.utc).isoformat()
    log_file = LOG_DIR / "okx_download.log"
    
    log_message("=" * 60, log_file)
    log_message("OKX P0 Smoke Download — Exchange-Agnostic Microstructure V2", log_file)
    log_message(f"Started: {started_at}", log_file)
    log_message("=" * 60, log_file)
    
    # Test reachability
    reachability = test_okx_reachability()
    
    results = {
        "started_at": started_at,
        "ended_at": None,
        "reachability": reachability,
        "trades": {},
        "funding": {},
    }
    
    if not reachability["reachable"]:
        log_message(f"OKX NOT REACHABLE: {reachability['error']}", log_file)
        results["status"] = "BLOCKED_OKX_UNREACHABLE"
    else:
        # Download for each symbol
        for inst_id, symbol in SYMBOLS.items():
            log_message(f"\n--- {symbol} ({inst_id}) ---", log_file)
            
            # Trades
            trade_result = download_okx_trades(inst_id, max_trades=500)
            results["trades"][symbol] = trade_result
            
            # Funding
            funding_result = download_okx_funding(inst_id)
            results["funding"][symbol] = funding_result
            
            time.sleep(REQUEST_DELAY)
        
        # Determine overall status
        any_trade_pass = any(r["status"] == "PASS" for r in results["trades"].values())
        any_funding_pass = any(r["status"] == "PASS" for r in results["funding"].values())
        
        if any_trade_pass or any_funding_pass:
            results["status"] = "PARTIAL_WITH_DATA" if not all([any_trade_pass, any_funding_pass]) else "PASS"
        else:
            results["status"] = "FAIL"
    
    results["ended_at"] = datetime.now(timezone.utc).isoformat()
    
    # Save results
    output_file = SMOKE_ROOT / "manifest" / "okx_download_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    log_message(f"\nResults saved to {output_file}", log_file)
    log_message(f"Status: {results['status']}", log_file)
    
    return results


if __name__ == "__main__":
    results = main()
    print(json.dumps(results, indent=2))
