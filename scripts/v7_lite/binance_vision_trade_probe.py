#!/usr/bin/env python3
"""Binance Vision probe — free historical aggTrades."""
import json, gzip, zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
import requests

REPO = Path(__file__).resolve().parent.parent.parent
CACHE = REPO / "cache" / "v7_lite_free_data_source_audit"
DL = CACHE / "staging" / "binance_vision"
DL.mkdir(parents=True, exist_ok=True)
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
BASE = "https://data.binance.vision"
RESULTS = []


def log(m):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {m}")
    with open(CACHE / "logs" / "download.log", "a") as f:
        f.write(f"[{ts}] {m}\n")


def probe_url(url, label):
    r = {"url": url, "label": label}
    try:
        resp = requests.head(url, timeout=15, allow_redirects=True)
        r["status"] = resp.status_code
        r["reachable"] = resp.status_code == 200
        if resp.status_code == 200:
            log(f"  ✅ {label}")
        else:
            log(f"  ❌ {label} HTTP {resp.status_code}")
    except Exception as e:
        r["status"] = 0
        r["error"] = str(e)
        r["reachable"] = False
        log(f"  ❌ {label} {e}")
    RESULTS.append(r)


def dl_sample(url, name):
    try:
        r = requests.get(url, timeout=60, stream=True)
        if r.status_code != 200:
            return None
        data = b""
        for chunk in r.iter_content(1048576):
            data += chunk
            if len(data) >= 1048576:
                break
        p = DL / name
        p.write_bytes(data)
        log(f"  Downloaded {len(data)} bytes -> {name}")
        return p
    except Exception as e:
        log(f"  Download fail: {e}")
        return None


def probe():
    log("=" * 60 + "\nBINANCE VISION PROBE\n" + "=" * 60)

    # Root
    probe_url(f"{BASE}/data/spot/daily/aggTrades/", "root spot daily aggTrades dir")

    # Directory listing for each symbol
    for sym in SYMS:
        probe_url(f"{BASE}/data/spot/daily/aggTrades/{sym}/", f"spot daily {sym}")
        probe_url(f"{BASE}/data/spot/monthly/aggTrades/{sym}/", f"spot monthly {sym}")
        probe_url(f"{BASE}/data/futures/um/daily/aggTrades/{sym}/", f"futures daily {sym}")
        probe_url(f"{BASE}/data/futures/um/monthly/aggTrades/{sym}/", f"futures monthly {sym}")

    # Specific daily files — 2 days ago
    d = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d")
    for sym in SYMS:
        probe_url(f"{BASE}/data/spot/daily/aggTrades/{sym}/{sym}-aggTrades-{d}.zip", f"{sym} spot daily {d}")

    # Monthly file — known good month
    for sym in SYMS:
        probe_url(f"{BASE}/data/spot/monthly/aggTrades/{sym}/{sym}-aggTrades-2025-01.zip", f"{sym} spot monthly 2025-01")

    # Download 1 sample if possible
    sample = None
    for r in RESULTS:
        if r.get("reachable") and "BTCUSDT" in r["url"]:
            sample = r["url"]
            break
    if sample:
        log(f"\nDownloading: {sample}")
        fp = dl_sample(sample, "BTCUSDT_aggTrades_sample.zip")
        if fp:
            try:
                with zipfile.ZipFile(fp) as zf:
                    for n in zf.namelist():
                        log(f"  ZIP: {n} ({zf.getinfo(n).file_size} bytes)")
                        if n.endswith(".csv"):
                            with zf.open(n) as csvf:
                                h = csvf.read(2000).decode()
                                log(f"  CSV preview: {h[:200]}")
            except Exception as e:
                log(f"  ZIP error: {e}")

    ok = sum(1 for r in RESULTS if r.get("reachable"))
    log(f"\nProbes: {len(RESULTS)} total, {ok} reachable")
    return {"probes": len(RESULTS), "reachable": ok}


if __name__ == "__main__":
    r = probe()
    print(json.dumps(r, indent=2))
