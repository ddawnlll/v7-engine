#!/usr/bin/env python3
"""OKX Historical Source Probe — searches for real historical trade data."""
import json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent.parent
CACHE = REPO / "cache" / "v7_lite_okx_historical_resolution"
LOG_DIR = CACHE / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

CANDIDATES = []

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")
    with open(LOG_DIR / "okx_source_probe.log", "a") as f:
        f.write(f"[{ts}] {msg}\n")

def probe(name, url, params=None, method="GET", expect_historical=False, headers=None):
    """Probe a source URL and record result."""
    log(f"  probing: {url}")
    result = {
        "source_name": name, "url": url, "params": params,
        "status_code": None, "error": None, "is_historical": False,
        "content_preview": None, "data_types": [],
    }
    try:
        if method == "GET":
            resp = requests.get(url, params=params, timeout=15, headers=headers)
        else:
            resp = requests.post(url, json=params, timeout=15)
        result["status_code"] = resp.status_code
        result["response_size_bytes"] = len(resp.content)
        if resp.status_code == 200:
            try:
                body = resp.json()
                if isinstance(body, dict):
                    result["content_preview"] = str(list(body.keys())[:4])
                    if body.get("code") == "0":
                        result["is_historical"] = True
                        result["data_types"].append("trades" if "trades" in name.lower() else "unknown")
                elif isinstance(body, list):
                    result["content_preview"] = f"list[{len(body)}]"
                    if len(body) > 0:
                        result["is_historical"] = True
            except:
                result["content_preview"] = resp.text[:200]
        else:
            error = resp.text[:500]
            result["error"] = error
    except Exception as e:
        result["error"] = str(e)
    CANDIDATES.append(result)
    return result

def main():
    log("=" * 60)
    log("OKX Historical Source Probe")
    log("=" * 60)

    # 1. OKX public trades endpoint — test deep pagination
    log("\n--- 1. OKX trades API (deep pagination test) ---")
    probe("OKX Trades API (BTC, 5 pages)", 
          "https://www.okx.com/api/v5/market/trades",
          {"instId": "BTC-USDT-SWAP", "limit": "100"})
    
    # Try with 'before' parameter for historical
    probe("OKX Trades API (BTC, 'before' param test)",
          "https://www.okx.com/api/v5/market/trades",
          {"instId": "BTC-USDT-SWAP", "limit": "100", "before": "1700000000000"})
    
    # 2. OKX history candles / klines — may support parameters
    log("\n--- 2. OKX candles/klines API ---")
    probe("OKX History Candles (1h, BTC, limit 100)",
          "https://www.okx.com/api/v5/market/history-candles",
          {"instId": "BTC-USDT-SWAP", "bar": "1H", "limit": "100"})
    
    # Try with 'after' for historical
    probe("OKX History Candles (1h, with 'after' back to 2023)",
          "https://www.okx.com/api/v5/market/history-candles",
          {"instId": "BTC-USDT-SWAP", "bar": "1H", "limit": "100", "after": "1672531200000"})
    
    # 3. OKX funding rate history — this IS historical
    log("\n--- 3. OKX funding rate history ---")
    result = probe("OKX Funding Rate History",
                   "https://www.okx.com/api/v5/public/funding-rate",
                   {"instId": "BTC-USDT-SWAP"})
    probe("OKX Funding Rate History (with 'after')",
          "https://www.okx.com/api/v5/public/funding-rate",
          {"instId": "BTC-USDT-SWAP", "after": "1672531200000"})
    
    # 4. OKX public data / static archive URLs
    log("\n--- 4. OKX static/downloadable archives ---")
    for url in [
        "https://static.okx.com/cdn/okex/traderecords/trades/",
        "https://www.okx.com/static/okex/traderecords/trades/BTC-USDT-SWAP/2026-07/",
        "https://okx.com/static/okex/traderecords/",
        "https://archive.okx.com/",
    ]:
        probe("OKX Static Archive", url)

    # 5. OKX public market data page
    log("\n--- 5. OKX market data page ---")
    probe("OKX Market Data Page", "https://www.okx.com/market-data/instruments")

    # 6. OKX public REST for index/tickers (test auth bypasses)
    log("\n--- 6. OKX index/ticker endpoint ---")
    probe("OKX Index Candles (BTC-USDT, 1H, historical)",
          "https://www.okx.com/api/v5/market/index-candles",
          {"instId": "BTC-USDT", "bar": "1H", "limit": "100", "after": "1672531200000"})

    # 7. Check Bybit historical trades as potential fallback
    log("\n--- 7. Bybit historical public endpoints ---")
    probe("Bybit History Candles (1h, BTC back to 2023)",
          "https://api.bybit.com/v5/market/kline",
          {"category": "linear", "symbol": "BTCUSDT", "interval": "60", "limit": "200", "start": 1672531200000})

    # 8. Check Kraken/Coinbase/CryptoCompare for potential fallback
    log("\n--- 8. CryptoCompare (free historical trades) ---")
    probe("CryptoCompare Trades (BTC, 2 days back)",
          "https://min-api.cryptocompare.com/data/v2/trade",
          {"fsym": "BTC", "tsym": "USDT", "toTs": datetime.now().timestamp() - 172800})

    # Save results
    out = CACHE / "manifest" / "source_candidates.json"
    with open(out, "w") as f:
        json.dump({"probed_at": datetime.now(timezone.utc).isoformat(), "candidates": CANDIDATES}, f, indent=2)
    log(f"\nSaved {len(CANDIDATES)} candidate probes to {out}")

    # Summary
    reachable = [c for c in CANDIDATES if c["status_code"] == 200]
    historical = [c for c in CANDIDATES if c["is_historical"]]
    log(f"Total probes: {len(CANDIDATES)}")
    log(f"Reachable (200): {len(reachable)}")
    log(f"Historical data found: {len(historical)}")
    return {"total": len(CANDIDATES), "reachable": len(reachable), "historical": len(historical)}

if __name__ == "__main__":
    r = main()
    print(json.dumps(r, indent=2))
