#!/usr/bin/env python3
"""OKX Tier-A P1 Downloader — Exchange-Agnostic Microstructure V2.

Downloads OKX tick trades and funding for 8 Tier-A symbols.
Uses public REST endpoints with pagination for deeper history.
"""

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
P1_ROOT = REPO_ROOT / "cache" / "v7_lite_scalp_dataset_v2_okx_p1"
STAGING = P1_ROOT / "staging" / "okx"
LOG_DIR = P1_ROOT / "logs"

STAGING.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

TIER_A_SYMBOLS = {
    "BTC-USDT-SWAP": "BTCUSDT",
    "ETH-USDT-SWAP": "ETHUSDT",
    "SOL-USDT-SWAP": "SOLUSDT",
    "BNB-USDT-SWAP": "BNBUSDT",
    "XRP-USDT-SWAP": "XRPUSDT",
    "DOGE-USDT-SWAP": "DOGEUSDT",
    "ADA-USDT-SWAP": "ADAUSDT",
    "LINK-USDT-SWAP": "LINKUSDT",
}

OKX_TRADES_URL = "https://www.okx.com/api/v5/market/trades"
OKX_FUNDING_URL = "https://www.okx.com/api/v5/public/funding-rate"
OKX_TICKER_URL = "https://www.okx.com/api/v5/market/ticker"
REQUEST_DELAY = 0.25


def log(msg: str, log_file=None):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if log_file:
        with open(log_file, "a") as f:
            f.write(line + "\n")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def test_reachability():
    lf = LOG_DIR / "okx_download.log"
    log("Testing OKX reachability...", lf)
    try:
        start = time.time()
        resp = requests.get(OKX_TICKER_URL, params={"instId": "BTC-USDT-SWAP"}, timeout=10)
        latency = (time.time() - start) * 1000
        if resp.status_code == 200 and resp.json().get("code") == "0":
            log(f"OKX reachable. Latency: {latency:.0f}ms", lf)
            return {"reachable": True, "latency_ms": round(latency, 2), "error": None}
        return {"reachable": False, "error": f"HTTP {resp.status_code}", "latency_ms": round(latency, 2)}
    except Exception as e:
        return {"reachable": False, "error": str(e), "latency_ms": None}


def download_trades(inst_id: str, max_trades: int = 3000) -> dict:
    lf = LOG_DIR / "okx_download.log"
    log(f"Downloading OKX trades for {inst_id} (target: {max_trades})...", lf)
    result = {"status": "BLOCKED", "rows": 0, "file": None, "checksum": None, "error": None}
    try:
        all_trades = []
        after = ""
        for page in range(30):
            params = {"instId": inst_id, "limit": str(min(max_trades - len(all_trades), 100))}
            if after:
                params["after"] = after
            resp = requests.get(OKX_TRADES_URL, params=params, timeout=15)
            time.sleep(REQUEST_DELAY)
            if resp.status_code != 200:
                result["error"] = f"HTTP {resp.status_code}"
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
            if page % 5 == 4:
                log(f"  ...{len(all_trades)} trades so far", lf)
        if all_trades:
            df = pd.DataFrame(all_trades)
            df = df.rename(columns={"ts": "timestamp", "px": "price", "sz": "size", "instId": "inst_id"})
            symbol = TIER_A_SYMBOLS.get(inst_id, inst_id.replace("-", "_"))
            out = STAGING / f"{symbol}_trades_raw.json"
            df.to_json(out, orient="records", indent=2)
            result.update(status="PASS", rows=len(df), file=str(out), checksum=sha256(out))
            log(f"  Saved {len(df)} trades to {out.name}", lf)
        else:
            result["error"] = "No trades returned"
    except Exception as e:
        result["error"] = str(e)
    return result


def download_funding(inst_id: str, max_rows: int = 300) -> dict:
    lf = LOG_DIR / "okx_download.log"
    log(f"Downloading OKX funding for {inst_id}...", lf)
    result = {"status": "BLOCKED", "rows": 0, "file": None, "checksum": None, "error": None}
    try:
        all_funding = []
        after = ""
        for page in range(5):
            params = {"instId": inst_id, "limit": "100"}
            if after:
                params["after"] = after
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
            after = funding[-1].get("fundingTime", "")
            if len(all_funding) >= max_rows:
                break
        if all_funding:
            df = pd.DataFrame(all_funding)
            df = df.rename(columns={"fundingTime": "funding_ts", "fundingRate": "funding_rate", "instId": "inst_id"})
            symbol = TIER_A_SYMBOLS.get(inst_id, inst_id.replace("-", "_"))
            out = STAGING / f"{symbol}_funding_raw.json"
            df.to_json(out, orient="records", indent=2)
            result.update(status="PASS", rows=len(df), file=str(out), checksum=sha256(out))
            log(f"  Saved {len(df)} funding rows to {out.name}", lf)
        else:
            result["error"] = "No funding data"
    except Exception as e:
        result["error"] = str(e)
    return result


def main():
    started_at = datetime.now(timezone.utc).isoformat()
    lf = LOG_DIR / "okx_download.log"
    log("=" * 60, lf)
    log("OKX P1 Tier-A Downloader", lf)
    log(f"Started: {started_at}", lf)
    log("=" * 60, lf)

    reachability = test_reachability()
    results = {"started_at": started_at, "ended_at": None, "reachability": reachability, "trades": {}, "funding": {}}

    if not reachability["reachable"]:
        results["status"] = "BLOCKED_OKX_UNREACHABLE"
        log(f"OKX NOT REACHABLE: {reachability['error']}", lf)
    else:
        for inst_id, symbol in TIER_A_SYMBOLS.items():
            log(f"\n--- {symbol} ({inst_id}) ---", lf)
            results["trades"][symbol] = download_trades(inst_id, max_trades=3000)
            results["funding"][symbol] = download_funding(inst_id)
            time.sleep(REQUEST_DELAY)

        trade_pass = [s for s, r in results["trades"].items() if r["status"] == "PASS"]
        results["status"] = "PASS" if len(trade_pass) >= 3 else "FAIL"
        results["symbols_with_trades"] = trade_pass

    results["ended_at"] = datetime.now(timezone.utc).isoformat()
    out = P1_ROOT / "manifest" / "okx_download_results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    log(f"\nStatus: {results['status']}", lf)
    return results


if __name__ == "__main__":
    r = main()
    print(json.dumps(r, indent=2))
