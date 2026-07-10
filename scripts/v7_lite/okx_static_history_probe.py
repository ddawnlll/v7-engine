#!/usr/bin/env python3
"""OKX Static Download / Historical Page Probe."""
import json
from datetime import datetime, timezone
from pathlib import Path
import requests

REPO = Path(__file__).resolve().parent.parent.parent
CACHE = REPO / "cache" / "v7_lite_free_data_source_audit"
DL = CACHE / "staging" / "okx"
DL.mkdir(parents=True, exist_ok=True)
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
    except Exception as e:
        r["status"] = 0
        r["error"] = str(e)
        r["reachable"] = False
        log(f"  ❌ {label} {e}")
    PROBES.append(r)


def probe():
    log("=" * 60 + "\nOKX STATIC DOWNLOAD PROBE\n" + "=" * 60)
    p("https://www.okx.com/market-data/history-data", "history data page")
    p("https://static.okx.com/cdn/okex/traderecords/trades/", "static trades dir")
    p("https://static.okx.com/cdn/okex/traderecords/trades/BTC-USDT-SWAP/2025-01/", "static BTC 2025-01")
    p("https://static.okx.com/cdn/okex/traderecords/trades/BTC-USDT-SWAP/2024-06/", "static BTC 2024-06")
    p("https://okx-public-cdn.okx.com/data/", "public cdn data dir")
    p("https://www.okx.com/api/v5/market/history-trades?instId=BTC-USDT-SWAP&limit=5", "API history-trades")

    ok = sum(1 for r in PROBES if r.get("reachable"))
    log(f"\nProbes: {len(PROBES)} total, {ok} reachable")
    return {"probes": len(PROBES), "reachable": ok}


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2))
