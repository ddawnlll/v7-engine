#!/usr/bin/env python3
"""Phase B runner — selectivity frontier from SCALP OOS predictions.

Requires Phase A scoreboard and ledger to exist.
Runs confidence thresholds: 0.50, 0.55, 0.60, 0.65, 0.70, 0.75
on the 56-symbol SCALP model to build the selectivity frontier.

Usage:
    PYTHONPATH=... python3 reports/overnight/run_phase_b.py

Output:
    reports/overnight/ledger.jsonl  (appended)
    reports/overnight/scoreboard.md (updated with frontier)
"""

import json
import logging
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "alphaforge" / "src"))
sys.path.insert(0, str(Path(__file__).parents[2] / "simulation"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("phase_b")

REPO = Path(__file__).parents[2]
OVERNIGHT = REPO / "reports" / "overnight"
LEDGER = OVERNIGHT / "ledger.jsonl"
SCOREBOARD = OVERNIGHT / "scoreboard.md"

# ── Canonical symbol lists (shared with run_phase_a.py) ──
BOOTSTRAP_SYMBOLS = tuple(sorted([
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "LTCUSDT", "BCHUSDT",
]))

ALL_SYMBOLS = tuple(sorted([
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "AAVEUSDT", "ALGOUSDT",
    "APEUSDT", "APTUSDT", "ARBUSDT", "ATOMUSDT", "AXSUSDT", "BCHUSDT",
    "COMPUSDT", "CRVUSDT", "EOSUSDT", "ETCUSDT", "FILUSDT", "FTMUSDT",
    "GALAUSDT", "GRTUSDT", "HBARUSDT", "ICPUSDT", "IMXUSDT", "INJUSDT",
    "KAVAUSDT", "KSMUSDT", "LDOUSDT", "LTCUSDT", "MANAUSDT", "MKRUSDT",
    "NEARUSDT", "OPUSDT", "QNTUSDT", "RUNEUSDT", "SANDUSDT", "SNXUSDT",
    "STXUSDT", "SUIUSDT", "THETAUSDT", "TIAUSDT", "TRXUSDT", "UNIUSDT",
    "VETUSDT", "WIFUSDT", "XLMUSDT", "XMRUSDT", "YFIUSDT", "ZECUSDT",
    "ZILUSDT", "ZRXUSDT",
]))


def log_ledger(entry: dict):
    entry.setdefault("ts", time.time())
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def run_scalp_discovery(threshold: float, label: str, symbols) -> dict:
    """Run SCALP discovery at given threshold, return results dict."""
    logger.info("Running SCALP discovery @ threshold=%.2f (%s)", threshold, label)
    from alphaforge.discovery import DiscoveryConfig
    from alphaforge.discovery.pipeline import run_discovery

    config = DiscoveryConfig(
        mode="SCALP",
        symbols=symbols,
        folds=6,
        confidence_threshold=threshold,
        use_synthetic=False,
        create_handoff=False,
        random_seed=42,
    )
    t0 = time.time()
    try:
        result = run_discovery(config)
        elapsed = time.time() - t0
        m = result.metrics or {}
        rm = m.get("return_metrics") or {}
        risk = m.get("risk_metrics") or {}
        return {
            "label": label,
            "threshold": threshold,
            "status": result.status,
            "signal_count": result.signal_count,
            "trade_count": result.trade_count,
            "avg_net_R": rm.get("avg_net_R"),
            "total_net_R": rm.get("total_net_R"),
            "win_rate": risk.get("win_rate"),
            "profit_factor": risk.get("profit_factor"),
            "sharpe_ratio": risk.get("sharpe"),
            "max_drawdown_R": risk.get("max_drawdown_R"),
            "duration_s": round(elapsed, 1),
            "errors": result.errors,
            "full_metrics": m,
        }
    except Exception as e:
        import traceback
        elapsed = time.time() - t0
        logger.error("Discovery crashed at threshold=%.2f: %s", threshold, e)
        return {
            "label": label,
            "threshold": threshold,
            "status": "CRASHED",
            "error": str(e),
            "traceback": traceback.format_exc(),
            "trade_count": 0,
            "duration_s": round(elapsed, 1),
        }


def append_frontier_to_scoreboard(results: list[dict]):
    """Append the threshold frontier table to scoreboard.md."""
    lines = [
        "",
        "## Phase B — Selectivity Frontier",
        "",
        "| Threshold | N Trades | Avg R | Total R | WR | PF | Max DD | Status | Duration |",
        "|-----------|----------|-------|---------|----|----|--------|--------|----------|",
    ]
    for r in results:
        tc = r.get("trade_count", 0)
        insuff = " ⚠️ <500" if tc and tc < 500 else ""
        lines.append(
            f"| {r.get('threshold','?'):<9.2f} | {r.get('trade_count','?'):<8}{insuff} | "
            f"{_fmt(r.get('avg_net_R')):>6} | {_fmt(r.get('total_net_R')):>8} | "
            f"{_fmt(r.get('win_rate')):>3} | {_fmt(r.get('profit_factor')):>4} | "
            f"{_fmt(r.get('max_drawdown_R')):>7} | {r.get('status','?'):>6} | "
            f"{r.get('duration_s','?'):>5}s |"
        )
    lines.extend([
        "",
        "### Decision Node B",
    ])

    # Find top decile vs average
    if results:
        best_result = max(results, key=lambda r: r.get("avg_net_R") or -999)
        best_thresh = best_result.get("threshold", "?")
        best_r = best_result.get("avg_net_R")
        # Compare vs baseline average (first result, usually lowest threshold)
        baseline = results[0] if results else {}
        baseline_r = baseline.get("avg_net_R")
        if best_r and baseline_r and best_r > baseline_r:
            lines.append(f"Top decile ({best_thresh}) = {_fmt(best_r)} > overall average ({_fmt(baseline_r)}) → RANKING=YES")
        elif best_r and baseline_r:
            lines.append(f"Top decile ({best_thresh}) = {_fmt(best_r)} ≤ overall average ({_fmt(baseline_r)}) → RANKING=NONE")
        else:
            lines.append("Unable to determine ranking — insufficient data")

    # Append
    current = SCOREBOARD.read_text() if SCOREBOARD.exists() else ""
    SCOREBOARD.write_text(current + "\n".join(lines))
    logger.info("Frontier appended to scoreboard.md")


def _fmt(v, d=4):
    if v is None:
        return "?"
    if isinstance(v, str):
        return v
    return f"{v:.{d}f}"


def main(symbol_set="bootstrap"):
    """Run Phase B selectivity frontier.

    Parameters
    ----------
    symbol_set : str
        "bootstrap" → 12 high-liquidity symbols (fast).
        "full" → 56-symbol universe (slow — backtest is CPU-bound).
    """
    symbols = BOOTSTRAP_SYMBOLS if symbol_set == "bootstrap" else ALL_SYMBOLS
    logger.info("=== Phase B: RANKING POWER — Selectivity Frontier ===")
    logger.info("Symbol set: %s (%d symbols)", symbol_set, len(symbols))

    thresholds = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75]
    results = []

    for thresh in thresholds:
        label = f"thresh_{thresh:.2f}"
        r = run_scalp_discovery(thresh, label, symbols)
        results.append(r)

        log_ledger({
            "id": f"B-{label}",
            "phase": "B",
            "config": {
                "mode": "SCALP",
                "symbols": len(symbols),
                "folds": 6,
                "threshold": thresh,
            },
            "sim_metrics": {
                "n_trades": r["trade_count"],
                "avg_net_R": r.get("avg_net_R"),
                "total_net_R": r.get("total_net_R"),
                "win_rate": r.get("win_rate"),
                "profit_factor": r.get("profit_factor"),
                "max_dd_R": r.get("max_drawdown_R"),
            },
            "duration_s": r["duration_s"],
            "verdict": r["status"],
        })

        logger.info("  thresh=%.2f: %d trades, avg_R=%s, WR=%s, status=%s",
                     thresh, r["trade_count"], _fmt(r.get("avg_net_R")),
                     _fmt(r.get("win_rate")), r["status"])

    append_frontier_to_scoreboard(results)

    # Decision Node B
    valid_results = [r for r in results if r["status"] != "CRASHED" and r.get("avg_net_R") is not None]
    if valid_results:
        best = max(valid_results, key=lambda r: r["avg_net_R"])
        baseline = valid_results[0]  # lowest threshold = most trades
        logger.info("\n[DECISION NODE B]")
        logger.info("  Best threshold: %.2f → avg R=%.4f, %d trades",
                     best["threshold"], best["avg_net_R"], best["trade_count"])
        logger.info("  Baseline (%.2f): avg R=%.4f, %d trades",
                     baseline["threshold"], baseline["avg_net_R"], baseline["trade_count"])
        if best["avg_net_R"] > baseline["avg_net_R"]:
            logger.info("  → RANKING=YES — selectivity adds value. Proceed to Phase C.")
        else:
            logger.info("  → RANKING=NONE — selectivity not additive. Skip Phase C, reallocate time.")

    logger.info("\n=== Phase B complete ===")
    return 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Phase B selectivity frontier")
    parser.add_argument("--full", action="store_true", help="Use 56-symbol universe instead of 12-symbol bootstrap")
    args = parser.parse_args()
    sys.exit(main("full" if args.full else "bootstrap"))
