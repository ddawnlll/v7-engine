#!/usr/bin/env python3
"""Free Data Source Probe — orchestrates probing all 4 free sources."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
CACHE = REPO / "cache" / "v7_lite_free_data_source_audit"
RPT = REPO / "reports" / "v7_lite" / "free_data_source_audit"
LOG_DIR = CACHE / "logs"
CACHE.mkdir(parents=True, exist_ok=True)
RPT.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_DIR / "probe.log", "a") as f:
        f.write(line + "\n")


def run_script(name, module):
    log(f"\n=== Running {name} ===")
    try:
        sys.path.insert(0, str(REPO / "scripts" / "v7_lite"))
        mod = __import__(module)
        result = mod.main() if hasattr(mod, "main") else mod.probe()
        log(f"{name}: done")
        return result
    except Exception as e:
        log(f"{name}: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return {"status": "FAIL", "error": str(e)}


def main():
    started = datetime.now(timezone.utc).isoformat()
    log("=" * 60)
    log("Free Historical Microstructure Data Source Audit")
    log(f"Started: {started}")

    results = {}

    results["binance_vision"] = run_script("Binance Vision Probe", "binance_vision_trade_probe")
    results["bybit"] = run_script("Bybit Public Data Probe", "bybit_public_history_probe")
    results["okx"] = run_script("OKX Static History Probe", "okx_static_history_probe")
    results["tardis"] = run_script("Tardis Free Sample Probe", "tardis_free_sample_probe")

    results["ended_at"] = datetime.now(timezone.utc).isoformat()
    out = CACHE / "manifest" / "free_source_probe_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    log(f"\nAll probes complete. Results -> {out}")
    return results


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
