#!/usr/bin/env python3
"""Bybit P0 Smoke Downloader — Exchange-Agnostic Microstructure V2.

Downloads Bybit open interest and funding rates for BTCUSDT, ETHUSDT, SOLUSDT.
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
STAGING = SMOKE_ROOT / "staging" / "bybit"
LOG_DIR = SMOKE_ROOT / "logs"

STAGING.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Bybit instruments for P0 smoke
SYMBOLS = {
    "BTCUSDT": "BTCUSDT",
    "ETHUSDT": "ETHUSDT",
    "SOLUSDT": "SOLUSDT",
}

# Bybit public endpoints (v5)
BYBIT_OI_URL = "https://api.bybit.com/v5/market/open-interest"
BYBIT_FUNDING_URL = "https://api.bybit.com/v5/market/funding/history"
BYBIT_TICKER_URL = "https://api.bybit.com/v5/market/tickers"

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


def test_bybit_reachability() -> dict:
    """Test Bybit API reachability."""
    log_file = LOG_DIR / "bybit_download.log"
    log_message("Testing Bybit reachability...", log_file)
    
    result = {
        "reachable": False,
        "ticker_status": None,
        "oi_status": None,
        "funding_status": None,
        "error": None,
        "latency_ms": None,
    }
    
    try:
        # Test ticker endpoint
        start = time.time()
        resp = requests.get(BYBIT_TICKER_URL, params={"category": "linear", "symbol": "BTCUSDT"}, timeout=10)
        latency = (time.time() - start) * 1000
        result["latency_ms"] = round(latency, 2)
        result["ticker_status"] = resp.status_code
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get("retCode") == 0 and data.get("result", {}).get("list"):
                result["reachable"] = True
                log_message(f"Bybit reachable. Latency: {latency:.0f}ms", log_file)
            else:
                result["error"] = f"API error: {data.get('retMsg', 'unknown')}"
                log_message(f"Bybit API error: {data.get('retMsg')}", log_file)
        else:
            result["error"] = f"HTTP {resp.status_code}"
            log_message(f"Bybit HTTP error: {resp.status_code}", log_file)
            
    except Exception as e:
        result["error"] = str(e)
        log_message(f"Bybit reachability failed: {e}", log_file)
    
    return result


def download_bybit_oi(symbol: str, category: str = "linear") -> dict:
    """Download Bybit open interest history."""
    log_file = LOG_DIR / "bybit_download.log"
    log_message(f"Downloading Bybit OI for {symbol}...", log_file)
    
    result = {
        "status": "BLOCKED",
        "rows": 0,
        "file": None,
        "checksum": None,
        "error": None,
    }
    
    try:
        all_oi = []
        
        for page in range(3):  # Max 3 pages
            params = {
                "category": category,
                "symbol": symbol,
                "intervalTime": "1h",
                "limit": "100",
            }
            if all_oi:
                params["endTime"] = all_oi[-1].get("timestamp", "")
            
            resp = requests.get(BYBIT_OI_URL, params=params, timeout=10)
            time.sleep(REQUEST_DELAY)
            
            if resp.status_code != 200:
                result["error"] = f"HTTP {resp.status_code}"
                break
            
            data = resp.json()
            if data.get("retCode") != 0:
                result["error"] = f"API error: {data.get('retMsg')}"
                break
            
            oi_data = data.get("result", {}).get("list", [])
            if not oi_data:
                break
            
            all_oi.extend(oi_data)
        
        if all_oi:
            df = pd.DataFrame(all_oi)
            
            # Rename columns
            col_map = {
                "timestamp": "timestamp",
                "openInterest": "open_interest",
                "symbol": "inst_id",
            }
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
            
            # Save to staging
            output_file = STAGING / f"{symbol}_oi_raw.json"
            df.to_json(output_file, orient="records", indent=2)
            
            result["status"] = "PASS"
            result["rows"] = len(df)
            result["file"] = str(output_file)
            result["checksum"] = compute_sha256(output_file)
            
            log_message(f"Bybit OI saved: {len(df)} rows to {output_file.name}", log_file)
        else:
            result["error"] = "No OI data returned"
            log_message(f"Bybit OI: no data returned for {symbol}", log_file)
            
    except Exception as e:
        result["error"] = str(e)
        log_message(f"Bybit OI download failed: {e}", log_file)
    
    return result


def download_bybit_funding(symbol: str, category: str = "linear") -> dict:
    """Download Bybit funding rate history."""
    log_file = LOG_DIR / "bybit_download.log"
    log_message(f"Downloading Bybit funding for {symbol}...", log_file)
    
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
            params = {
                "category": category,
                "symbol": symbol,
                "limit": "100",
            }
            if all_funding:
                params["endTime"] = all_funding[-1].get("fundingRateTimestamp", "")
            
            resp = requests.get(BYBIT_FUNDING_URL, params=params, timeout=10)
            time.sleep(REQUEST_DELAY)
            
            if resp.status_code != 200:
                result["error"] = f"HTTP {resp.status_code}"
                break
            
            data = resp.json()
            if data.get("retCode") != 0:
                result["error"] = f"API error: {data.get('retMsg')}"
                break
            
            funding = data.get("result", {}).get("list", [])
            if not funding:
                break
            
            all_funding.extend(funding)
        
        if all_funding:
            df = pd.DataFrame(all_funding)
            
            # Rename columns
            col_map = {
                "fundingRateTimestamp": "timestamp",
                "fundingRate": "funding_rate",
                "symbol": "inst_id",
            }
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
            
            # Save to staging
            output_file = STAGING / f"{symbol}_funding_raw.json"
            df.to_json(output_file, orient="records", indent=2)
            
            result["status"] = "PASS"
            result["rows"] = len(df)
            result["file"] = str(output_file)
            result["checksum"] = compute_sha256(output_file)
            
            log_message(f"Bybit funding saved: {len(df)} rows to {output_file.name}", log_file)
        else:
            result["error"] = "No funding data returned"
            log_message(f"Bybit funding: no data returned for {symbol}", log_file)
            
    except Exception as e:
        result["error"] = str(e)
        log_message(f"Bybit funding download failed: {e}", log_file)
    
    return result


def main():
    """Main Bybit download orchestrator."""
    started_at = datetime.now(timezone.utc).isoformat()
    log_file = LOG_DIR / "bybit_download.log"
    
    log_message("=" * 60, log_file)
    log_message("Bybit P0 Smoke Download — Exchange-Agnostic Microstructure V2", log_file)
    log_message(f"Started: {started_at}", log_file)
    log_message("=" * 60, log_file)
    
    # Test reachability
    reachability = test_bybit_reachability()
    
    results = {
        "started_at": started_at,
        "ended_at": None,
        "reachability": reachability,
        "oi": {},
        "funding": {},
    }
    
    if not reachability["reachable"]:
        log_message(f"Bybit NOT REACHABLE: {reachability['error']}", log_file)
        results["status"] = "BLOCKED_BYBIT_UNREACHABLE"
    else:
        # Download for each symbol
        for symbol in SYMBOLS:
            log_message(f"\n--- {symbol} ---", log_file)
            
            # Open Interest
            oi_result = download_bybit_oi(symbol)
            results["oi"][symbol] = oi_result
            
            # Funding
            funding_result = download_bybit_funding(symbol)
            results["funding"][symbol] = funding_result
            
            time.sleep(REQUEST_DELAY)
        
        # Determine overall status
        any_oi_pass = any(r["status"] == "PASS" for r in results["oi"].values())
        any_funding_pass = any(r["status"] == "PASS" for r in results["funding"].values())
        
        if any_oi_pass or any_funding_pass:
            results["status"] = "PARTIAL_WITH_DATA" if not all([any_oi_pass, any_funding_pass]) else "PASS"
        else:
            results["status"] = "FAIL"
    
    results["ended_at"] = datetime.now(timezone.utc).isoformat()
    
    # Save results
    output_file = SMOKE_ROOT / "manifest" / "bybit_download_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    log_message(f"\nResults saved to {output_file}", log_file)
    log_message(f"Status: {results['status']}", log_file)
    
    return results


if __name__ == "__main__":
    results = main()
    print(json.dumps(results, indent=2))
