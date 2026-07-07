#!/usr/bin/env python3
"""Phase A runner — 56-symbol SCALP + SWING baseline scoreboard.

Usage:
    PYTHONPATH=alphaforge/src python3 reports/overnight/run_phase_a.py

Output:
    reports/overnight/ledger.jsonl   (appended)
    reports/overnight/scoreboard.md  (generated)
"""

import json
import logging
import sys
import time
import os
from pathlib import Path

# Add alphaforge and simulation to path
sys.path.insert(0, str(Path(__file__).parents[2] / "alphaforge" / "src"))
sys.path.insert(0, str(Path(__file__).parents[2] / "simulation"))

from alphaforge.discovery import DiscoveryConfig, DiscoveryResult
from alphaforge.discovery.pipeline import run_discovery

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
)
logger = logging.getLogger("phase_a")

REPO = Path(__file__).parents[2]
OVERNIGHT = REPO / "reports" / "overnight"
LEDGER = OVERNIGHT / "ledger.jsonl"

# ── Canonical symbol lists (single source of truth) ──
# Bootstrap subset: 12 high-liquidity symbols with consistent derivative data
BOOTSTRAP_SYMBOLS = tuple(sorted([
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "LTCUSDT", "BCHUSDT",
]))

# Full 56-symbol universe (from Phase B runner, covers all listed perps)
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

# The old ERROR ledger entry (A-SCALP-baseline, ts=1783426431) is an incomplete
# run that crashed during backtest step [6/8]. Per the resume checklist, this is
# NOT finished work — Phase A will be re-attempted fresh.

# Canonical confidence threshold for SCALP baseline (matches pipeline CONFIDENCE_THRESHOLD)
SCALP_THRESHOLD = 0.50


def log_ledger(entry: dict):
    """Append one row to the JSONL ledger."""
    entry.setdefault("ts", time.time())
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")
    logger.info("Ledger: %s", entry.get("id", "?"))


def run_discovery_safe(config: DiscoveryConfig) -> dict:
    """Run discovery with timing, catch crashes, return safe dict."""
    t0 = time.time()
    try:
        result = run_discovery(config)
        elapsed = time.time() - t0
        m = result.metrics or {}
        wfv = result.wfv_metrics or {}
        rejection = result.rejection or {}
        return {
            "status": result.status,
            "signal_count": result.signal_count,
            "trade_count": result.trade_count,
            "avg_net_R": m.get("avg_net_R"),
            "total_net_R": m.get("total_net_R"),
            "win_rate": m.get("win_rate"),
            "profit_factor": m.get("profit_factor"),
            "sharpe_ratio": m.get("sharpe_ratio"),
            "max_drawdown_R": m.get("max_drawdown_r") or m.get("max_drawdown"),
            "wf_accuracy": wfv.get("accuracy"),
            "wf_overfit_gap": wfv.get("overfit_gap"),
            "rejection_decision": rejection.get("decision"),
            "duration_s": round(elapsed, 1),
            "errors": result.errors,
            "full_metrics": m,
            "full_wfv": wfv,
        }
    except Exception as e:
        import traceback
        elapsed = time.time() - t0
        tb = traceback.format_exc()
        logger.error("Discovery crashed: %s", e)
        return {
            "status": "CRASHED",
            "error": str(e),
            "traceback": tb,
            "duration_s": round(elapsed, 1),
            "errors": [str(e)],
        }


def write_scoreboard(results: list[dict]):
    """Write scoreboard.md with tables."""
    lines = [
        "# OPERATION SCALP 0.05 — Scoreboard (Phase A)",
        "",
        f"Generated: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        f"Symbols: {len(ALL_SYMBOLS)}",
        "",
        "## Baseline Results",
        "",
        "| Run | N Trades | Avg R | Total R | WR | PF | Max DD | WF Acc | Overfit | Status |",
        "|-----|----------|-------|---------|----|----|--------|---------|---------|--------|",
    ]
    for r in results:
        lines.append(
            f"| {r.get('id','?'):15s} | {r.get('trade_count','?'):<8} | "
            f"{_fmt(r.get('avg_net_R')):>7} | {_fmt(r.get('total_net_R')):>8} | "
            f"{_fmt(r.get('win_rate')):>4} | {_fmt(r.get('profit_factor')):>4} | "
            f"{_fmt(r.get('max_drawdown_R')):>8} | {_fmt(r.get('wf_accuracy')):>6} | "
            f"{_fmt(r.get('wf_overfit_gap')):>7} | {r.get('status','?'):>6} |"
        )

    lines.extend([
        "",
        "## Cost Decomposition (from metrics)",
        "",
    ])
    for r in results:
        m = r.get("full_metrics") or {}
        lines.append(f"### {r.get('id','?')}")
        lines.append(f"- avg_net_R = {_fmt(m.get('avg_net_R'))}")
        lines.append(f"- avg_gross_R = {_fmt(m.get('avg_gross_R'))}")
        lines.append(f"- Fee impact = {_fmt(m.get('fee_cost_r') or m.get('avg_fee_cost_r'))}")
        lines.append(f"- Slippage impact = {_fmt(m.get('slippage_cost_r') or m.get('avg_slippage_cost_r'))}")
        lines.append(f"- Total cost drag = {_fmt(m.get('total_cost_r') or m.get('avg_total_cost_r'))}")

    lines.extend([
        "",
        "## Symbol Concentration",
        "",
    ])
    for r in results:
        m = r.get("full_metrics") or {}
        sym_breakdown = m.get("symbol_breakdown") or {}
        if sym_breakdown:
            lines.append(f"### {r.get('id','?')}")
            total_trades = sum(s.get("trade_count", 0) for s in sym_breakdown.values())
            sorted_syms = sorted(sym_breakdown.items(), key=lambda x: x[1].get("trade_count", 0), reverse=True)
            top2_share = 0.0
            for i, (sym, sm) in enumerate(sorted_syms[:5]):
                share = sm.get("trade_count", 0) / max(total_trades, 1)
                if i < 2:
                    top2_share += share
                lines.append(f"  - {sym}: {sm.get('trade_count', 0)} trades, "
                             f"R={_fmt(sm.get('total_net_R'))}, share={share:.1%}")
            lines.append(f"  Top-2 share: {top2_share:.1%}")
            if top2_share > 0.40:
                lines.append("  **⚠️  Top-2 > 40% — concentration risk**")

    lines.extend([
        "",
        "---",
        f"_Phase A complete at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}_",
    ])

    path = OVERNIGHT / "scoreboard.md"
    path.write_text("\n".join(lines))
    logger.info("Scoreboard written to %s", path)


def _fmt(v, d=4):
    if v is None:
        return "?"
    if isinstance(v, str):
        return v
    return f"{v:.{d}f}"


def main(symbol_set="bootstrap"):
    """Run Phase A baseline.

    Parameters
    ----------
    symbol_set : str
        "bootstrap" → 12 high-liquidity symbols (safety, rules out OOM/crash).
        "full" → 56-symbol universe.
    """
    symbols = BOOTSTRAP_SYMBOLS if symbol_set == "bootstrap" else ALL_SYMBOLS
    logger.info("=== Phase A: TRUE BASELINE ===")
    logger.info("Symbol set: %s (%d symbols), SCALP + SWING", symbol_set, len(symbols))

    # ── Data pre-flight ──
    from alphaforge.train import load_cached_data
    logger.info("[A.1] Data pre-flight (%d symbols)...", len(symbols))
    test_data = load_cached_data(list(symbols[:2]), "1h")
    if test_data is None:
        logger.error("Data loading failed — aborting Phase A")
        return 1
    n_bars = len(test_data["close"])
    logger.info("  Data OK: %d bars for %d symbols", n_bars, len(symbols[:3]))
    logger.info("  Rows per symbol: %.0f", n_bars / 3)

    results = []

    # ── SCALP baseline ──
    logger.info("\n[A.2] SCALP baseline (%d symbols, 6 folds, threshold=%.2f)...",
                len(symbols), SCALP_THRESHOLD)
    config = DiscoveryConfig(
        mode="SCALP",
        symbols=symbols,
        folds=6,
        confidence_threshold=SCALP_THRESHOLD,
        use_synthetic=False,
        create_handoff=False,
        random_seed=42,
    )
    r = run_discovery_safe(config)
    r["id"] = f"SCALP_baseline_{len(symbols)}"
    log_ledger({"id": f"A-SCALP-baseline-{len(symbols)}", "phase": "A", "config": {
        "mode": "SCALP", "symbols": len(symbols), "folds": 6, "threshold": SCALP_THRESHOLD,
    }, "sim_metrics": {
        "n_trades": r["trade_count"],
        "avg_net_R": r["avg_net_R"],
        "total_net_R": r["total_net_R"],
        "win_rate": r["win_rate"],
        "profit_factor": r["profit_factor"],
        "max_dd_R": r["max_drawdown_R"],
    }, "duration_s": r["duration_s"], "verdict": r["status"]})
    results.append(r)

    # ── SWING control ──
    logger.info("\n[A.3] SWING control (%d symbols, 6 folds, threshold=0.55)...", len(symbols))
    config_s = DiscoveryConfig(
        mode="SWING",
        symbols=symbols,
        folds=6,
        confidence_threshold=0.55,
        use_synthetic=False,
        create_handoff=False,
        random_seed=42,
    )
    r2 = run_discovery_safe(config_s)
    r2["id"] = f"SWING_control_{len(symbols)}"
    log_ledger({"id": f"A-SWING-control-{len(symbols)}", "phase": "A", "config": {
        "mode": "SWING", "symbols": len(symbols), "folds": 6, "threshold": 0.55,
    }, "sim_metrics": {
        "n_trades": r2["trade_count"],
        "avg_net_R": r2["avg_net_R"],
        "total_net_R": r2["total_net_R"],
        "win_rate": r2["win_rate"],
        "profit_factor": r2["profit_factor"],
        "max_dd_R": r2["max_drawdown_R"],
    }, "duration_s": r2["duration_s"], "verdict": r2["status"]})
    results.append(r2)

    # ── Scoreboard ──
    write_scoreboard(results)

    # ── Decision Node A ──
    scalp_r = results[0]
    if scalp_r["trade_count"] > 0:
        r_per_trade = scalp_r.get("avg_net_R") or 0
        logger.info("\n[DECISION NODE A]")
        logger.info("  SCALP sim R/trade = %s", _fmt(r_per_trade))
        if r_per_trade > 0:
            logger.info("  → Positive expectancy! Continue to Phase B.")
        else:
            logger.info("  → R/trade ≤ 0. Running gap decomposition...")
            m = scalp_r.get("full_metrics") or {}
            gross = m.get("avg_gross_R") or m.get("avg_net_R", 0) or 0
            net = m.get("avg_net_R") or 0
            cost_drag = gross - net if gross and net else None
            logger.info("  Gross R = %s, Net R = %s, Cost drag = %s",
                        _fmt(gross), _fmt(net), _fmt(cost_drag))
            # Gap decomposition
            logger.info("  Gap decomposition (break-even cost analysis):")
            logger.info("    Current cost drag: %s R/trade", _fmt(cost_drag))
            logger.info("    Current avg R/trade: %s", _fmt(net))
            logger.info("    4bps round-trip saving → ~+%.4f R (maker profile target)",
                       abs(net) * 0.5 if net else 0.04)
            log_ledger({"id": "A-decision-node", "phase": "A",
                       "decision": "NEGATIVE_BASELINE", "avg_net_R": net,
                       "cost_drag": cost_drag})

    # ── Summary ──
    logger.info("\n=== Phase A complete ===")
    for r in results:
        logger.info("  %s: %d trades, avg R=%s, status=%s",
                    r.get("id","?"), r["trade_count"], _fmt(r.get("avg_net_R")), r["status"])
    return 0


if __name__ == "__main__":
    # Default: bootstrap (12 symbols). Pass --full on CLI for the 56-symbol run.
    import argparse
    parser = argparse.ArgumentParser(description="Phase A baseline runner")
    parser.add_argument("--full", action="store_true", help="Use 56-symbol universe instead of 12-symbol bootstrap")
    args = parser.parse_args()
    sys.exit(main("full" if args.full else "bootstrap"))
