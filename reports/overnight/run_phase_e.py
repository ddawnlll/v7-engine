#!/usr/bin/env python3
"""Phase E — Maker execution profile A/B (the arithmetic lever).

Runs SCALP discovery on 12 bootstrap symbols under all execution modes:
  - TAKER (baseline, default)
  - MAKER pessimistic (fill iff bar trades THROUGH price by 0.05%)
  - MAKER base (touch + 1 tick)
  - MAKER optimistic (touch only)

Reports: R/trade, n_trades (fill rate), total R, fee savings, adverse selection.

Usage:
    PYTHONPATH=alphaforge/src:simulation python3 reports/overnight/run_phase_e.py
"""

import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "alphaforge" / "src"))
sys.path.insert(0, str(Path(__file__).parents[2] / "simulation"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("phase_e")

REPO = Path(__file__).parents[2]
OVERNIGHT = REPO / "reports" / "overnight"
LEDGER = OVERNIGHT / "ledger.jsonl"

# Bootstrap symbols (shared with Phase A/B)
BOOTSTRAP_SYMBOLS = tuple(sorted([
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "LTCUSDT", "BCHUSDT",
]))


def log_ledger(entry: dict):
    entry.setdefault("ts", time.time())
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def run_scalp(execution_mode: str = "TAKER", maker_fill_assumption: str = "base",
              threshold: float = 0.50, label: str = "") -> dict:
    """Run SCALP discovery with given execution mode."""
    from alphaforge.discovery import DiscoveryConfig
    from alphaforge.discovery.pipeline import run_discovery

    config = DiscoveryConfig(
        mode="SCALP",
        symbols=BOOTSTRAP_SYMBOLS,
        folds=6,
        confidence_threshold=threshold,
        use_synthetic=False,
        create_handoff=False,
        random_seed=42,
        execution_mode=execution_mode,
        maker_fill_assumption=maker_fill_assumption,
    )
    t0 = time.time()
    try:
        result = run_discovery(config)
        elapsed = time.time() - t0
        m = result.metrics or {}
        rm = m.get("return_metrics") or {}
        risk = m.get("risk_metrics") or {}
        cd = m.get("cost_decomposition") or {}
        return {
            "label": label,
            "status": result.status,
            "trade_count": result.trade_count,
            "avg_net_R": rm.get("avg_net_R"),
            "total_net_R": rm.get("total_net_R"),
            "win_rate": risk.get("win_rate"),
            "profit_factor": risk.get("profit_factor"),
            "max_drawdown_R": risk.get("max_drawdown_R"),
            "avg_cost_per_trade_R": cd.get("avg_cost_per_trade_R"),
            "total_cost_R": cd.get("total_cost_R"),
            "duration_s": round(elapsed, 1),
            "full_metrics": m,
        }
    except Exception as e:
        import traceback
        logger.error("Run crashed: %s", e)
        return {"label": label, "status": "CRASHED", "error": str(e),
                "traceback": traceback.format_exc(), "trade_count": 0,
                "duration_s": round(time.time() - t0, 1)}


def main():
    logger.info("=== Phase E: Maker Execution Profile A/B ===")
    logger.info("12 bootstrap symbols, SCALP, threshold=0.50")

    # Run configurations
    runs = [
        ("TAKER", "base",        "E-taker-base"),        # Baseline
        ("MAKER", "pessimistic", "E-maker-pessimistic"), # Worst fill
        ("MAKER", "base",        "E-maker-base"),         # Expected fill
        ("MAKER", "optimistic",  "E-maker-optimistic"),   # Best fill
    ]

    results = []
    for exec_mode, fill_assumption, label in runs:
        logger.info("\n--- %s (fill=%s) ---", exec_mode, fill_assumption)
        r = run_scalp(exec_mode, fill_assumption, label=label)
        results.append(r)

        log_ledger({
            "id": label, "phase": "E",
            "config": {"mode": "SCALP", "symbols": len(BOOTSTRAP_SYMBOLS),
                       "folds": 6, "threshold": 0.50,
                       "execution_mode": exec_mode,
                       "maker_fill_assumption": fill_assumption},
            "sim_metrics": {
                "n_trades": r["trade_count"],
                "avg_net_R": r.get("avg_net_R"),
                "total_net_R": r.get("total_net_R"),
                "win_rate": r.get("win_rate"),
                "profit_factor": r.get("profit_factor"),
                "max_dd_R": r.get("max_drawdown_R"),
                "avg_cost_per_trade_R": r.get("avg_cost_per_trade_R"),
            },
            "duration_s": r["duration_s"],
            "verdict": r["status"],
        })

        logger.info("  trades=%d, avg_R=%s, WR=%s, PF=%s, cost/trade=%s",
                     r["trade_count"], _fmt(r.get("avg_net_R")),
                     _fmt(r.get("win_rate")), _fmt(r.get("profit_factor")),
                     _fmt(r.get("avg_cost_per_trade_R")))

    # ── Summary table ──
    logger.info("\n" + "=" * 70)
    logger.info("PHASE E — MAKER EXECUTION FRONTIER")
    logger.info("%-20s | %8s | %8s | %6s | %6s | %8s",
                "Mode", "Trades", "Avg R", "WR", "PF", "Cost/R")
    logger.info("-" * 70)
    baseline_r = results[0].get("avg_net_R") or 0
    for r in results:
        r_val = r.get("avg_net_R") or 0
        delta = r_val - baseline_r
        insuff = " ⚠️ <500" if r["trade_count"] < 500 and r["trade_count"] > 0 else ""
        logger.info("%-20s | %8d%s | %8.4f | %6.2f | %6.2f | %8.4f",
                    r["label"], r["trade_count"], insuff, r_val,
                    (r.get("win_rate") or 0) * 100,
                    r.get("profit_factor") or 0,
                    r.get("avg_cost_per_trade_R") or 0)
        if "MAKER" in r["label"]:
            logger.info("%-20s   Δ vs taker: %+.4f R/trade", "", delta)
    logger.info("=" * 70)

    # ── Adverse selection check ──
    logger.info("\nAdverse Selection Check:")
    taker_wr = results[0].get("win_rate") or 0
    for r in results[1:]:
        maker_wr = r.get("win_rate") or 0
        wr_diff = maker_wr - taker_wr
        logger.info("  %s: WR=%.2f%% vs taker WR=%.2f%% (Δ=%+.2f%%)",
                     r["label"], maker_wr * 100, taker_wr * 100, wr_diff * 100)
        if wr_diff < -0.02:
            logger.info("    ⚠️  Adverse selection detected: filled maker trades %.1f%% worse",
                        abs(wr_diff) * 100)

    # ── Pessimistic row is the citation anchor ──
    if len(results) >= 2:
        pess = results[1]  # MAKER pessimistic
        base_r = results[0].get("avg_net_R") or 0
        pess_r = pess.get("avg_net_R") or 0
        logger.info("\n★ Citation anchor (Phase E):")
        logger.info("  The pessimistic MAKER row is the valid claim for 'maker adds +X R/trade'")
        logger.info("  Pessimistic maker: avg R = %.4f (Δ vs taker = %+.4f)",
                     pess_r, pess_r - base_r)

    logger.info("\n=== Phase E complete ===")
    return 0


def _fmt(v, d=4):
    if v is None: return "?"
    if isinstance(v, str): return v
    return f"{v:.{d}f}"


if __name__ == "__main__":
    sys.exit(main())
