#!/usr/bin/env python3
"""OKX Historical Downloader — attempts real historical trade/funding download."""
import json, os, time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

REPO = Path(__file__).resolve().parent.parent.parent
CACHE = REPO / "cache" / "v7_lite_okx_historical_resolution"
STAGING = CACHE / "staging" / "okx"
LOG_DIR = CACHE / "logs"
STAGING.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

SYMBOLS = {"BTCUSDT": "BTC-USDT-SWAP", "ETHUSDT": "ETH-USDT-SWAP", "SOLUSDT": "SOL-USDT-SWAP"}
HISTCANDLES = "https://www.okx.com/api/v5/market/history-candles"
FUNDHIST = "https://www.okx.com/api/v5/public/funding-rate-history"
DELAY = 0.3

ATTEMPTS = []


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")
    with open(LOG_DIR / "okx_download_attempts.log", "a") as f:
        f.write(f"[{ts}] {msg}\n")


def attempt(name, url, params, expect_historical=False):
    ATTEMPTS.append({"name": name, "url": url, "params": params,
                     "status": None, "error": None, "rows": 0, "is_historical": False, "file": None})
    a = ATTEMPTS[-1]
    try:
        r = requests.get(url, params=params, timeout=15)
        a["status_code"] = r.status_code
        a["response_size"] = len(r.content)
        if r.status_code == 200:
            data = r.json()
            rows = data.get("data", [])
            a["rows"] = len(rows)
            if rows:
                a["is_historical"] = expect_historical
                log(f"  {name}: {len(rows)} rows (HTTP 200)")
                return data
            else:
                a["error"] = "empty data"
                log(f"  {name}: empty (HTTP 200)")
                return None
        else:
            a["error"] = f"HTTP {r.status_code}: {r.text[:200]}"
            log(f"  {name}: HTTP {r.status_code}")
            return None
    except Exception as e:
        a["error"] = str(e)
        log(f"  {name}: {e}")
        return None


def download_funding_history(symbol, okx_sym):
    log(f"  Funding history for {symbol}...")
    all_funding = []
    before = ""
    for page in range(5):
        params = {"instId": okx_sym, "limit": "100"}
        if before:
            params["before"] = before
        data = attempt(f"funding-{symbol}-p{page}", FUNDHIST, params, expect_historical=True)
        if not data or not data.get("data"):
            break
        rows = data["data"]
        all_funding.extend(rows)
        before = rows[-1].get("fundingTime", "")
        time.sleep(DELAY)
        if len(rows) < 100:
            break
    return all_funding


def download_history_candles(symbol, okx_sym, bar="1H", max_calls=30):
    log(f"  History candles {bar} for {symbol}...")
    all_candles = []
    after = str(int(datetime.now().timestamp() * 1000))
    for page in range(max_calls):
        params = {"instId": okx_sym, "bar": bar, "limit": "300"}
        if after:
            params["after"] = after
        data = attempt(f"candles-{symbol}-p{page}", HISTCANDLES, params, expect_historical=True)
        if not data or not data.get("data"):
            break
        rows = data["data"]
        all_candles.extend(rows)
        after = rows[-1][0]
        time.sleep(DELAY)
        if len(rows) < 300:
            break
    return all_candles


def main():
    log("=" * 60)
    log("OKX Historical Downloader")
    log("=" * 60)

    results = {"started_at": datetime.now(timezone.utc).isoformat(), "funding": {}, "candles": {}}

    # Attempt 1: Funding rate history for each symbol
    log("\n--- Funding Rate History ---")
    for sym, okx in SYMBOLS.items():
        funding = download_funding_history(sym, okx)
        if funding:
            out = STAGING / f"{sym}_funding_historical.json"
            with open(out, "w") as f:
                json.dump(funding, f, indent=2)
            ts_min = min(int(r.get("fundingTime", 0)) for r in funding if r.get("fundingTime"))
            ts_max = max(int(r.get("fundingTime", 0)) for r in funding if r.get("fundingTime"))
            results["funding"][sym] = {"rows": len(funding), "start": ts_min, "end": ts_max,
                                        "file": str(out)}
            log(f"  Saved {len(funding)} funding rows for {sym}")

    # Attempt 2: History candles (as alternative/trade proxy)
    log("\n--- History Candles (1H, 30 pages = ~1yr each) ---")
    for sym, okx in SYMBOLS.items():
        candles = download_history_candles(sym, okx, "1H", max_calls=30)
        if candles:
            out = STAGING / f"{sym}_candles_historical_1h.json"
            df = pd.DataFrame(candles, columns=["ts", "open", "high", "low", "close", "vol", "volCcy", "volCcyQuote", "confirm"])
            df.to_json(out, orient="records", indent=2)
            ts0, tsn = int(df["ts"].iloc[0]), int(df["ts"].iloc[-1])
            results["candles"][sym] = {"rows": len(df), "start": ts0, "end": tsn,
                                        "file": str(out), "days": round((ts0 - tsn)/86400000, 1)}
            log(f"  Saved {len(df)} 1h candles for {sym}: {results['candles'][sym]['days']} days")

    results["ended_at"] = datetime.now(timezone.utc).isoformat()
    results["attempts"] = ATTEMPTS

    out = CACHE / "manifest" / "coverage_probe.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    log(f"\nSaved coverage probe to {out}")
    return results


if __name__ == "__main__":
    r = main()
    print(json.dumps(r, indent=2))
