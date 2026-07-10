#!/usr/bin/env python3
"""Phase G — THE HOLDOUT, exactly once.

Uses the frozen candidate config from Phase F.1:
  - SCALP, 12 bootstrap symbols, threshold=0.50
  - MAKER execution, pessimistic fill assumption
  - holdout_cutoff = 3 months before today

NO RETRY. NO TWEAK. Report verbatim, good or bad.

Usage:
    PYTHONPATH=alphaforge/src:simulation python3 reports/overnight/run_phase_g.py
"""

import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "alphaforge" / "src"))
sys.path.insert(0, str(Path(__file__).parents[2] / "simulation"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("phase_g")

REPO = Path(__file__).parents[2]
OVERNIGHT = REPO / "reports" / "overnight"
LEDGER = OVERNIGHT / "ledger.jsonl"

BOOTSTRAP_SYMBOLS = tuple(sorted([
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "LTCUSDT", "BCHUSDT",
]))

# 3-month holdout cutoff (data before this is training, after is holdout)
HOLDOUT_CUTOFF = "2026-04-07"  # 3 months before 2026-07-07


def log_ledger(entry: dict):
    entry.setdefault("ts", time.time())
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def main():
    logger.info("╔══════════════════════════════════════╗")
    logger.info("║   PHASE G — THE HOLDOUT              ║")
    logger.info("║   Exactly one evaluation. No retry.  ║")
    logger.info("╚══════════════════════════════════════╝")
    logger.info("Candidate config: SCALP, 12 bootstrap symbols")
    logger.info("  threshold=0.50, MAKER+pessimistic")
    logger.info("  holdout_cutoff=%s (3-month reservation)", HOLDOUT_CUTOFF)

    from alphaforge.discovery import DiscoveryConfig
    from alphaforge.discovery.pipeline import run_discovery

    config = DiscoveryConfig(
        mode="SCALP",
        symbols=BOOTSTRAP_SYMBOLS,
        folds=6,
        confidence_threshold=0.50,
        use_synthetic=False,
        create_handoff=False,
        random_seed=42,
        execution_mode="MAKER",
        maker_fill_assumption="pessimistic",
        holdout_cutoff=HOLDOUT_CUTOFF,
    )

    t0 = time.time()
    result = run_discovery(config)
    elapsed = time.time() - t0

    m = result.metrics or {}
    rm = m.get("return_metrics") or {}
    risk = m.get("risk_metrics") or {}
    cd = m.get("cost_decomposition") or {}
    holdout_m = m.get("holdout") if isinstance(m, dict) else None
    holdout_rm = holdout_m.get("return_metrics", {}) if holdout_m else {}
    holdout_risk = holdout_m.get("risk_metrics", {}) if holdout_m else {}

    # Ledger entry
    log_ledger({
        "id": "G-holdout", "phase": "G",
        "config": {
            "mode": "SCALP", "symbols": len(BOOTSTRAP_SYMBOLS),
            "folds": 6, "threshold": 0.50,
            "execution_mode": "MAKER", "maker_fill_assumption": "pessimistic",
            "holdout_cutoff": HOLDOUT_CUTOFF,
        },
        "pre_holdout_metrics": {
            "n_trades": result.trade_count,
            "avg_net_R": rm.get("avg_net_R"),
            "total_net_R": rm.get("total_net_R"),
            "win_rate": risk.get("win_rate"),
            "profit_factor": risk.get("profit_factor"),
        },
        "holdout_metrics": {
            "n_trades": holdout_m.get("metadata", {}).get("total_trades") if holdout_m else None,
            "avg_net_R": holdout_rm.get("avg_net_R"),
            "total_net_R": holdout_rm.get("total_net_R"),
            "win_rate": holdout_risk.get("win_rate"),
            "profit_factor": holdout_risk.get("profit_factor"),
        } if holdout_m else None,
        "duration_s": round(elapsed, 1),
        "verdict": result.status,
    })

    # Report
    logger.info("\n" + "=" * 60)
    logger.info("PHASE G — HOLDOUT REPORT")
    logger.info("=" * 60)
    logger.info("Pre-holdout (WFV on training data):")
    logger.info("  Trades=%d, E[R]=%.4fR, PF=%.2f, WR=%.2f%%",
                 result.trade_count, rm.get("avg_net_R", 0) or 0,
                 risk.get("profit_factor", 0) or 0,
                 (risk.get("win_rate", 0) or 0) * 100)

    if holdout_m:
        logger.info("Holdout (3-month window, MAKER pessimistic):")
        logger.info("  Trades=%d, E[R]=%.4fR, PF=%.2f, WR=%.2f%%",
                     holdout_m.get("metadata", {}).get("total_trades", 0),
                     holdout_rm.get("avg_net_R", 0) or 0,
                     holdout_risk.get("profit_factor", 0) or 0,
                     (holdout_risk.get("win_rate", 0) or 0) * 100)
        logger.info("  ★ HOLDOUT VERDICT: NO RETRY, NO TWEAK — this is the ONE evaluation.")
    else:
        logger.info("Holdout: no trade signals or evaluation errored")

    # MHT statement
    logger.info("\nMultiple Testing Statement:")
    try:
        with open(LEDGER) as f:
            n_rows = sum(1 for _ in f)
        logger.info("  Total experiments this campaign: %d", n_rows)
        logger.info("  MHT exposure = %d independent evaluations", n_rows)
        logger.info("  Overfit gap on training data: %.4f" % (
            (result.wfv_metrics or {}).get("overfit_gap", 0)))
    except Exception:
        logger.info("  MHT count unavailable — read ledger manually")

    logger.info("\n=== Phase G complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
