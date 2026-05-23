#!/usr/bin/env python3
"""Alpha Thesis Validation — Main Entry Point.

Executes the full validation plan:

  Step 0: Data verification
  Step 1: Hypothesis 1 — Altcoin Delay
  Step 2: Hypothesis 2 — Volatility Compression
  Step 3: Hypothesis 3 — Funding + Spot Divergence
  Step 4: Hypothesis 4 — Open Interest Spike
  Step 5: Hypothesis 5 — Volume Anomaly
  Step 6: Composite Signal (if 2+ hypotheses pass)
  Step 7: Summary report

Usage:
    python -m alphas.main                         # full run
    python -m alphas.main --check-data-only        # only verify data
    python -m alphas.main --hypo 1                 # run hypothesis 1 only
    python -m alphas.main --hypo 4                 # run hypothesis 4 only
    python -m alphas.main --skip-download          # use cached data only
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

from .config import (
    RAW_DATA_DIR, RESULTS_DIR, TOP_N_SYMBOLS, START_DATE, END_DATE,
    MIN_DATA_PCT, PERPETUAL_SYMBOLS,
)
from .data import (
    download_klines, download_funding_rate, get_top_symbols_by_volume,
    check_data_availability,
)
from .utils import ensure_results_dir

# Import hypotheses
from .hypothesises.altcoin_delay import run_hypothesis as run_h1
from .hypothesises.volatility_compression import run_hypothesis as run_h2
from .hypothesises.funding_divergence import run_hypothesis as run_h3, check_funding_data_available
from .hypothesises.open_interest_spike import run_hypothesis as run_h4
from .hypothesises.volume_anomaly import run_hypothesis as run_h5
from .hypothesises.composite import can_build_composite, run_composite


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def step_0_verify_data(symbols: list) -> bool:
    """Step 0: Data Verification Checklist.

    Returns True if all checks pass.
    """
    logger.info("=" * 60)
    logger.info("STEP 0: Data Verification")
    logger.info("=" * 60)

    all_ok = True

    # 1. Binance klines for 60 symbols from 2021-01-01 available
    logger.info(f"\n[1/4] Checking klines for {len(symbols)} symbols...")
    avail = check_data_availability(symbols[:TOP_N_SYMBOLS])
    ok_count = sum(1 for v in avail.values() if v["ok"])
    logger.info(f"  {ok_count}/{len(avail)} symbols pass data completeness check")

    failing = [s for s, v in avail.items() if not v["ok"]]
    if failing:
        logger.warning(f"  Symbols failing: {failing}")
        all_ok = False

    # 2. No gaps > 24h
    max_gaps = [v["gap_hours"] for v in avail.values() if v["ok"]]
    if max_gaps and max(max_gaps) > 24:
        logger.warning(f"  Max gap: {max(max_gaps):.1f}h — exceeds 24h limit")
        all_ok = False
    else:
        logger.info(f"  Max gap: {max(max_gaps):.1f}h (OK)" if max_gaps else "  No gap data")

    # 3. Funding rate history accessible
    logger.info(f"\n[3/4] Checking funding rate data...")
    funding_ok = check_funding_data_available(symbols)
    logger.info(f"  Funding data: {'AVAILABLE' if funding_ok else 'UNAVAILABLE'}")
    if not funding_ok:
        logger.warning("  Hypothesis 3 will be BLOCKED")

    # 4. Disk space
    logger.info(f"\n[4/4] Checking disk space...")
    try:
        import shutil
        total, used, free = shutil.disk_usage(RAW_DATA_DIR if os.path.exists(RAW_DATA_DIR) else ".")
        free_gb = free / (1024 ** 3)
        logger.info(f"  Free disk space: {free_gb:.1f} GB")
        if free_gb < 1:
            logger.warning("  Less than 1 GB free — may not be enough for ~500MB raw data")
            all_ok = False
        else:
            logger.info(f"  Disk space OK (need ~500MB)")
    except Exception:
        logger.warning("  Could not check disk space")

    logger.info(f"\nData verification: {'ALL CHECKS PASSED' if all_ok else 'SOME CHECKS FAILED'}")

    # Save verification report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbols_checked": len(avail),
        "symbols_ok": ok_count,
        "symbols_failing": failing,
        "funding_available": funding_ok,
        "all_checks_passed": all_ok,
    }
    with open(os.path.join(RESULTS_DIR, "data_verification_report.json"), "w") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Verification report saved to {RESULTS_DIR}/data_verification_report.json")

    return all_ok


def get_active_symbols() -> list:
    """Get the list of symbols to test on, filtered by data availability."""
    try:
        symbols = get_top_symbols_by_volume(TOP_N_SYMBOLS)
        logger.info(f"Got {len(symbols)} top symbols from Binance API")
        # Filter to only symbols with data in our range
        avail = check_data_availability(symbols[:TOP_N_SYMBOLS])
        active = [s for s, v in avail.items() if v["ok"]]
        logger.info(f"  {len(active)} symbols have complete data in {START_DATE}-{END_DATE}")
        return active if active else symbols[:TOP_N_SYMBOLS]
    except Exception as e:
        logger.warning(f"Could not get top symbols: {e}, using hardcoded list")
        return PERPETUAL_SYMBOLS[:TOP_N_SYMBOLS]


def summary_report(all_results: dict, composite_result: dict):
    """Generate and save final summary report."""
    logger.info("=" * 60)
    logger.info("FINAL SUMMARY REPORT")
    logger.info("=" * 60)

    lines = []
    lines.append("Alpha Thesis Validation — Final Report")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    lines.append("─" * 60)
    lines.append("")

    accepted_count = 0
    for name, res in all_results.items():
        lines.append(f"Hypothesis: {name}")
        if isinstance(res, dict) and res.get("status") == "BLOCKED":
            lines.append(f"  Status: BLOCKED")
            lines.append(f"  Reason: {res.get('reason', 'N/A')}")
        else:
            median_r = res.get("median_r_multiple", 0.0)
            total = res.get("total_signals", 0)
            win_rate = res.get("win_rate", 0.0)
            lines.append(f"  Median R-multiple: {median_r:.4f}")
            lines.append(f"  Total signals: {total}")
            lines.append(f"  Win rate: {win_rate:.1%}")
            regime_bd = res.get("regime_breakdown", {})
            lines.append(f"  Regimes: {list(regime_bd.keys())}")
            if median_r > 1.5:
                accepted_count += 1
                lines.append(f"  → PASSES (R > 1.5)")
            else:
                lines.append(f"  → FAILS (R <= 1.5)")
        lines.append("")

    lines.append("─" * 60)
    lines.append("")
    lines.append(f"Hypotheses passing (R > 1.5): {accepted_count}/{len(all_results)}")

    # Composite decision
    composite_status = composite_result.get("status", "NOT_BUILT")
    lines.append(f"Composite signal: {composite_status}")
    lines.append(f"Reason: {composite_result.get('reason', 'N/A')}")

    lines.append("")
    lines.append("─" * 60)
    lines.append("")

    # Gating rules
    if accepted_count >= 2:
        lines.append("→ CRITICAL GATE: 2+ hypotheses pass. Proceed to system integration plan.")
    elif accepted_count == 1:
        lines.append(
            "→ CRITICAL GATE: 1 hypothesis passes. Write it into V7 as "
            "single-point-of-failure. Continue alpha search in parallel."
        )
    else:
        lines.append(
            "→ CRITICAL GATE: NONE pass. STOP. Do not build execution pipeline "
            "on zero-expectancy strategy. Revisit alpha search."
        )

    report = "\n".join(lines)
    logger.info(f"\n{report}")

    with open(os.path.join(RESULTS_DIR, "final_summary_report.txt"), "w") as f:
        f.write(report)

    # Also save JSON version
    summary = {
        "hypotheses": {name: {
            "median_r_multiple": res.get("median_r_multiple", None) if not isinstance(res, dict) or res.get("status") != "BLOCKED" else None,
            "total_signals": res.get("total_signals", None) if not isinstance(res, dict) or res.get("status") != "BLOCKED" else None,
            "win_rate": res.get("win_rate", None) if not isinstance(res, dict) or res.get("status") != "BLOCKED" else None,
            "status": "BLOCKED" if isinstance(res, dict) and res.get("status") == "BLOCKED" else ("PASS" if res.get("median_r_multiple", 0) > 1.5 else "FAIL"),
        } for name, res in all_results.items()},
        "accepted_count": accepted_count,
        "composite_status": composite_status,
        "gate_decision": (
            "proceed_to_integration" if accepted_count >= 2
            else "write_single_to_v7" if accepted_count == 1
            else "stop_and_revisit"
        ),
    }
    with open(os.path.join(RESULTS_DIR, "final_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    logger.info(f"Final report saved to {RESULTS_DIR}/")
    return report


def main():
    parser = argparse.ArgumentParser(description="Alpha Thesis Validation")
    parser.add_argument("--check-data-only", action="store_true",
                        help="Only run data verification, skip hypothesis testing")
    parser.add_argument("--hypo", type=int, choices=[1, 2, 3, 4, 5],
                        help="Run a single hypothesis only")
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip data download, use cached data only")
    parser.add_argument("--symbols", type=str, nargs="+",
                        help="Override symbol list")
    args = parser.parse_args()

    ensure_results_dir()

    # Determine symbol universe
    if args.symbols:
        symbols = args.symbols
    else:
        symbols = get_active_symbols()

    logger.info(f"Symbol universe: {len(symbols)} symbols")
    logger.info(f"Data directory: {RAW_DATA_DIR}")
    logger.info(f"Results directory: {RESULTS_DIR}")

    # ── Step 0: Data Verification ──
    data_ok = step_0_verify_data(symbols)

    if args.check_data_only:
        logger.info("Check-data-only mode. Exiting.")
        return

    # ── Run Hypotheses ──
    all_results = {}

    hypothesis_configs = [
        (1, "altcoin_delay", run_h1, "Altcoin Delay"),
        (2, "volatility_compression", run_h2, "Volatility Compression"),
        (3, "funding_divergence", run_h3, "Funding Divergence"),
        (4, "open_interest_spike", run_h4, "Open Interest Spike"),
        (5, "volume_anomaly", run_h5, "Volume Anomaly"),
    ]

    # Filter to selected hypotheses
    to_run = [hc for hc in hypothesis_configs if args.hypo is None or args.hypo == hc[0]]
    total = len(to_run)

    import time as _time
    hypo_start = _time.monotonic()

    for idx, (hnum, hname, hfunc, hlabel) in enumerate(to_run, 1):
        logger.info("\n" + "=" * 60)
        logger.info(f"[{idx}/{total}] HYPOTHESIS {hnum}: {hlabel}")
        logger.info("=" * 60)
        try:
            t0 = _time.monotonic()
            result = hfunc(symbols)
            elapsed = _time.monotonic() - t0
            status = result.get("status", "OK") if isinstance(result, dict) else "OK"
            median_r = result.get("median_r_multiple", "N/A") if isinstance(result, dict) else "N/A"
            logger.info(f"  ✅ {hname}: {status} | median R={median_r} | {elapsed:.0f}s")
            all_results[hname] = result
        except Exception as e:
            logger.error(f"  ❌ {hname} crashed: {e}")
            all_results[hname] = {"status": "ERROR", "reason": str(e)}

        # Estimate remaining
        done_elapsed = _time.monotonic() - hypo_start
        avg_per_hypo = done_elapsed / idx
        remaining = avg_per_hypo * (total - idx)
        logger.info(f"  ⏱  Elapsed: {done_elapsed:.0f}s  |  Est. remaining: {remaining:.0f}s")

    # ── Composite Signal ──
    total_hypos = len(all_results)
    composite_result = {"status": "NOT_BUILT", "reason": f"Composite not attempted (ran {total_hypos}/5 hypos)"}

    if args.hypo is None and total_hypos >= 2:
        logger.info("\n\n")
        composite_result = run_composite({}, all_results)

    # ── Summary Report ──
    logger.info("\n\n")
    total_elapsed = _time.monotonic() - hypo_start
    logger.info(f"Total time: {total_elapsed:.0f}s ({total_elapsed/60:.1f} min)")
    summary_report(all_results, composite_result)

    logger.info("\nDone. See results/ directory for all deliverables.")


if __name__ == "__main__":
    main()
