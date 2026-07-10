#!/usr/bin/env python3
"""OKX Tier A+B Downloader — V2 OKX P2 Scale Build.

Downloads OKX tick trades for 20 Tier A+B symbols.
Targets 3000+ trades per symbol (~1+ hour of recent high-liquidity data).
OKX public trades API only returns recent history, not months.
"""
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
P2_ROOT = REPO_ROOT / "cache" / "v7_lite_scalp_dataset_v2_okx_p2"
STAGING = P2_ROOT / "staging" / "okx"
LOG_DIR = P2_ROOT / "logs"
STAGING.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

TIER_AB = {
    # Tier A
    "BTC-USDT-SWAP": "BTCUSDT", "ETH-USDT-SWAP": "ETHUSDT", "SOL-USDT-SWAP": "SOLUSDT",
    "BNB-USDT-SWAP": "BNBUSDT", "XRP-USDT-SWAP": "XRPUSDT", "DOGE-USDT-SWAP": "DOGEUSDT",
    "ADA-USDT-SWAP": "ADAUSDT", "LINK-USDT-SWAP": "LINKUSDT",
    # Tier B
    "AVAX-USDT-SWAP": "AVAXUSDT", "DOT-USDT-SWAP": "DOTUSDT", "LTC-USDT-SWAP": "LTCUSDT",
    "BCH-USDT-SWAP": "BCHUSDT", "NEAR-USDT-SWAP": "NEARUSDT", "APT-USDT-SWAP": "APTUSDT",
    "ARB-USDT-SWAP": "ARBUSDT", "OP-USDT-SWAP": "OPUSDT", "FIL-USDT-SWAP": "FILUSDT",
    "ATOM-USDT-SWAP": "ATOMUSDT", "UNI-USDT-SWAP": "UNIUSDT", "SUI-USDT-SWAP": "SUIUSDT",
}

TRADES_URL = "https://www.okx.com/api/v5/market/trades"
FUNDING_URL = "https://www.okx.com/api/v5/public/funding-rate"
TICKER_URL = "https://www.okx.com/api/v5/market/ticker"
DELAY = 0.25


def log(msg, lf=None):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if lf:
        with open(lf, "a") as f:
            f.write(line + "\n")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def test_reachability():
    lf = LOG_DIR / "okx_download.log"
    try:
        start = time.time()
        resp = requests.get(TICKER_URL, params={"instId": "BTC-USDT-SWAP"}, timeout=10)
        lat = (time.time() - start) * 1000
        ok = resp.status_code == 200 and resp.json().get("code") == "0"
        log(f"OKX {'reachable' if ok else 'unreachable'} ({lat:.0f}ms)", lf)
        return {"reachable": ok, "latency_ms": round(lat, 2), "error": None if ok else f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"reachable": False, "error": str(e), "latency_ms": None}


def download_trades(inst_id, max_trades=5000):
    lf = LOG_DIR / "okx_download.log"
    log(f"  trades {inst_id} (target {max_trades})...", lf)
    try:
        all_trades, after = [], ""
        for page in range(50):
            params = {"instId": inst_id, "limit": str(min(max_trades - len(all_trades), 100))}
            if after:
                params["after"] = after
            resp = requests.get(TRADES_URL, params=params, timeout=15)
            time.sleep(DELAY)
            if resp.status_code != 200:
                return {"status": "FAIL", "rows": 0, "error": f"HTTP {resp.status_code}", "file": None, "checksum": None}
            data = resp.json()
            if data.get("code") != "0":
                return {"status": "FAIL", "rows": 0, "error": data.get("msg"), "file": None, "checksum": None}
            trades = data.get("data", [])
            if not trades:
                break
            all_trades.extend(trades)
            after = trades[-1].get("ts", "")
            if len(all_trades) >= max_trades:
                break
        if all_trades:
            df = pd.DataFrame(all_trades)
            df = df.rename(columns={"ts": "timestamp", "px": "price", "sz": "size", "instId": "inst_id"})
            sym = TIER_AB[inst_id]
            out = STAGING / f"{sym}_trades_raw.json"
            df.to_json(out, orient="records", indent=2)
            log(f"  saved {len(df)} trades -> {out.name}", lf)
            return {"status": "PASS", "rows": len(df), "file": str(out), "checksum": sha256(out), "error": None}
        return {"status": "FAIL", "rows": 0, "error": "no data", "file": None, "checksum": None}
    except Exception as e:
        return {"status": "FAIL", "rows": 0, "error": str(e), "file": None, "checksum": None}


def download_funding(inst_id, max_rows=300):
    lf = LOG_DIR / "okx_download.log"
    try:
        all_funding, after = [], ""
        for _ in range(5):
            params = {"instId": inst_id, "limit": "100"}
            if after:
                params["after"] = after
            resp = requests.get(FUNDING_URL, params=params, timeout=10)
            time.sleep(DELAY)
            if resp.status_code != 200:
                return {"status": "FAIL", "rows": 0, "error": f"HTTP {resp.status_code}", "file": None, "checksum": None}
            data = resp.json()
            if data.get("code") != "0":
                return {"status": "FAIL", "rows": 0, "error": data.get("msg"), "file": None, "checksum": None}
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
            sym = TIER_AB[inst_id]
            out = STAGING / f"{sym}_funding_raw.json"
            df.to_json(out, orient="records", indent=2)
            log(f"  saved {len(df)} funding -> {out.name}", lf)
            return {"status": "PASS", "rows": len(df), "file": str(out), "checksum": sha256(out), "error": None}
        return {"status": "FAIL", "rows": 0, "error": "no data", "file": None, "checksum": None}
    except Exception as e:
        return {"status": "FAIL", "rows": 0, "error": str(e), "file": None, "checksum": None}


def main():
    started = datetime.now(timezone.utc).isoformat()
    lf = LOG_DIR / "okx_download.log"
    log("=" * 60, lf)
    log("OKX P2 Tier A+B Downloader (20 symbols)", lf)
    log("=" * 60, lf)

    reach = test_reachability()
    results = {"started_at": started, "reachability": reach, "trades": {}, "funding": {}, "symbols_with_trades": []}

    if not reach["reachable"]:
        results["status"] = "BLOCKED_OKX_UNREACHABLE"
    else:
        for inst_id, sym in TIER_AB.items():
            log(f"\n--- {sym} ({inst_id}) ---", lf)
            results["trades"][sym] = download_trades(inst_id, max_trades=5000)
            results["funding"][sym] = download_funding(inst_id)
            time.sleep(DELAY)

        results["symbols_with_trades"] = [s for s, r in results["trades"].items() if r["status"] == "PASS"]
        results["status"] = "PASS" if len(results["symbols_with_trades"]) >= 12 else "FAIL"

    results["ended_at"] = datetime.now(timezone.utc).isoformat()
    out = P2_ROOT / "manifest" / "okx_download_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    log(f"\nStatus: {results['status']}, symbols: {len(results['symbols_with_trades'])}", lf)
    return results


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
