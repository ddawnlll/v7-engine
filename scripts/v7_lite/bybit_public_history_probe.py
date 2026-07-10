#!/usr/bin/env python3
"""Bybit Public Historical Data Probe."""
import json
from datetime import datetime, timezone
from pathlib import Path
import requests

REPO = Path(__file__).resolve().parent.parent.parent
CACHE = REPO / "cache" / "v7_lite_free_data_source_audit"
DL = CACHE / "staging" / "bybit"
DL.mkdir(parents=True, exist_ok=True)
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
PROBES = []


def log(m):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {m}")
    with open(CACHE / "logs" / "download.log", "a") as f:
        f.write(f"[{ts}] {m}\n")


def p(url, label):
    r = {"url": url, "label": label}
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r["status"] = resp.status_code
        r["reachable"] = resp.status_code == 200
        log(f"  {'✅' if r['reachable'] else '❌'} {label} ({resp.status_code})")
        if r["reachable"]:
            r["size"] = len(resp.content)
            r["preview"] = resp.text[:200]
    except Exception as e:
        r["status"] = 0
        r["error"] = str(e)
        r["reachable"] = False
        log(f"  ❌ {label} {e}")
    PROBES.append(r)


def probe():
    log("=" * 60 + "\nBYBIT PUBLIC HISTORICAL DATA PROBE\n" + "=" * 60)
    p("https://api.bybit.com/v5/market/kline?category=linear&symbol=BTCUSDT&interval=60&limit=10", "kline 1h BTC")
    p("https://api.bybit.com/v5/market/recent-trade?category=linear&symbol=BTCUSDT&limit=50", "recent trades BTC")
    p("https://public.bybit.com/trading/BTCUSDT/", "public trading BTC dir")
    p("https://public.bybit.com/trading/ETHUSDT/", "public trading ETH dir")
    p("https://public.bybit.com/trading/BTCUSDT/BTCUSDT2024-01-01.csv.gz", "BTC 2024-01-01 csv.gz")
    p("https://public.bybit.com/trading/BTCUSDT/BTCUSDT2025-01-01.csv.gz", "BTC 2025-01-01 csv.gz")
    p("https://public.bybit.com/trading/", "public trading root")

    ok = sum(1 for r in PROBES if r.get("reachable"))
    log(f"\nProbes: {len(PROBES)} total, {ok} reachable")

    # Download tiny sample if CSV found
    for r in PROBES:
        if r.get("reachable") and ".csv" in r["url"]:
            log(f"\nDownloading: {r['url']}")
            try:
                resp = requests.get(r["url"], timeout=60, stream=True)
                if resp.status_code == 200:
                    data = resp.content[:262144]
                    fname = r["url"].split("/")[-1]
                    (DL / fname).write_bytes(data)
                    log(f"  {len(data)} bytes -> {fname}")
                    import gzip
                    try:
                        dec = gzip.decompress(data[:10000])
                        log(f"  Preview: {dec[:300].decode(errors='replace')}")
                    except:
                        log(f"  Binary data")
            except Exception as e:
                log(f"  Error: {e}")
            break

    return {"probes": len(PROBES), "reachable": ok}


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2))
