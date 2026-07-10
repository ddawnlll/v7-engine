#!/usr/bin/env python3
"""Tardis Free Sample Probe."""
import json, gzip
from datetime import datetime, timezone
from pathlib import Path
import requests

REPO = Path(__file__).resolve().parent.parent.parent
CACHE = REPO / "cache" / "v7_lite_free_data_source_audit"
DL = CACHE / "staging" / "tardis"
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
        log(f"  {'✅' if r['reachable'] else '❌'} {label} ({resp.status_code}, {len(resp.content)}b)")
    except Exception as e:
        r["status"] = 0
        r["error"] = str(e)
        r["reachable"] = False
        log(f"  ❌ {label} {e}")
    PROBES.append(r)


def probe():
    log("=" * 60 + "\nTARDIS FREE SAMPLE PROBE\n" + "=" * 60)
    p("https://tardis.dev/", "homepage")
    p("https://tardis.dev/data-samples", "data samples page")
    p("https://public.tardis.dev/samples/binance-trades-sample.csv.gz", "binance trades sample")
    p("https://public.tardis.dev/samples/bybit-trades-sample.csv.gz", "bybit trades sample")
    p("https://public.tardis.dev/samples/okx-trades-sample.csv.gz", "okx trades sample")
    p("https://public.tardis.dev/", "public root dir")

    ok = sum(1 for r in PROBES if r.get("reachable"))
    log(f"\nProbes: {len(PROBES)} total, {ok} reachable")

    # Download binance trades sample
    for r in PROBES:
        if r.get("reachable") and "trades-sample" in r["url"]:
            log(f"\nDownloading: {r['url']}")
            try:
                resp = requests.get(r["url"], timeout=60, stream=True)
                if resp.status_code == 200:
                    data = b""
                    for chunk in resp.iter_content(2097152):
                        data += chunk
                        if len(data) >= 2097152:
                            break
                    fname = r["url"].split("/")[-1]
                    (DL / fname).write_bytes(data)
                    log(f"  {len(data)} bytes -> {fname}")
                    try:
                        dec = gzip.decompress(data[:10000])
                        log(f"  Preview: {dec[:400].decode(errors='replace')}")
                    except:
                        log(f"  Binary data")
            except Exception as e:
                log(f"  Error: {e}")
            break

    return {"probes": len(PROBES), "reachable": ok}


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2))
