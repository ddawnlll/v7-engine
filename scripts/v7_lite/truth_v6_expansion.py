"""
Truth V6 Expansion + Robustness Validation

Runs Truth V6 on wider symbol universe and multiple configurations
to test scalability and reconcile with the original 870-trade result.

Usage:
    PYTHONPATH=alphaforge/src:v7/src:. python3 scripts/v7_lite/truth_v6_expansion.py
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "alphaforge/src"))
sys.path.insert(0, str(REPO_ROOT / "v7/src"))
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "reports/v7_lite/truth_v6_validation"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(OUTPUT_DIR / "expansion" / "truth_v6_expansion.log", mode="w"),
    ],
)
logger = logging.getLogger("truth_v6_expansion")


def run_single_config(
    symbols: tuple[str, ...],
    mode: str = "SCALP",
    confidence_threshold: float = 0.55,
    folds: int = 6,
    execution_mode: str = "TAKER",
    label: str = "",
) -> dict | None:
    """Run one configuration and return metrics."""
    from alphaforge.discovery.backtest import backtest_signals
    from alphaforge.discovery.signal_generator import (
        generate_trade_signals,
        filter_overlapping_signals,
    )
    from alphaforge.train import (
        MODE_CONFIG,
        build_aligned_training_frame,
        walk_forward_validate,
        _load_panel_data,
        cross_sectional_rank_normalize,
    )

    t0 = time.time()
    cfg = MODE_CONFIG[mode]
    panel_cache = str(REPO_ROOT / "cache/factor_sprint")

    logger.info("Config: %s | Mode=%s | Syms=%d | Th=%.2f | Folds=%d",
                label, mode, len(symbols), confidence_threshold, folds)

    # Load data
    ohlcv = _load_panel_data(panel_cache, list(symbols))
    if ohlcv is None:
        logger.error("  Panel cache not found")
        return None

    # Build frame
    training_frame = build_aligned_training_frame(ohlcv, mode)
    X = training_frame["X"]
    y_int = training_frame["y_int"]
    label_net_r = training_frame["label_net_r"]
    action_net_r = training_frame["action_net_r"]
    timestamps = training_frame["timestamps"]
    symbols_arr = training_frame["symbols"]
    close_arr_raw = training_frame.get("close_prices", None)

    # Clean
    X_clean = np.nan_to_num(X, nan=0.0)
    if len(np.unique(timestamps)) < len(timestamps):
        X_clean = cross_sectional_rank_normalize(X_clean, timestamps)

    # WFV
    wfv_results, fold_preds, fold_y_class, fold_y_val = walk_forward_validate(
        X_clean, y_int.copy(), label_net_r.copy(), mode,
        min_folds=folds,
        action_net_r=action_net_r.copy(),
        return_raw_preds=True,
    )

    # Signals
    signals = generate_trade_signals(
        fold_results=wfv_results,
        fold_preds=fold_preds,
        fold_y_class=fold_y_class,
        ohlcv=ohlcv,
        mode_cfg=cfg,
        timestamps=timestamps.copy(),
        symbols=symbols_arr.copy(),
        close_arr=close_arr_raw,
        confidence_threshold=confidence_threshold,
    )
    signals = filter_overlapping_signals(signals)

    if not signals:
        logger.warning("  No signals generated")
        return None

    # Backtest
    trades = backtest_signals(
        signals=signals,
        ohlcv=ohlcv,
        mode=mode,
        execution_mode=execution_mode,
    )

    if not trades:
        logger.warning("  No trades produced")
        return None

    # Compute metrics
    net_r = np.array([t.realized_r_net for t in trades])
    fee_r = np.array([t.fee_cost_r for t in trades])
    slippage_r = np.array([t.slippage_cost_r for t in trades])
    cost_per_trade = float(np.mean(fee_r + slippage_r))

    # Symbol breakdown
    sym_counts = {}
    sym_net_r = {}
    for t in trades:
        s = t.signal.symbol
        sym_counts[s] = sym_counts.get(s, 0) + 1
        sym_net_r[s] = sym_net_r.get(s, 0.0) + t.realized_r_net

    top_sym = max(sym_counts, key=sym_counts.get)
    top_share = sym_counts[top_sym] / len(trades)

    # Direction breakdown
    long_r = [t.realized_r_net for t in trades if t.signal.side == "LONG"]
    short_r = [t.realized_r_net for t in trades if t.signal.side == "SHORT"]

    elapsed = time.time() - t0

    result = {
        "label": label,
        "symbols": list(symbols),
        "mode": mode,
        "confidence_threshold": confidence_threshold,
        "folds": folds,
        "trade_count": len(trades),
        "signal_count": len(signals),
        "raw_mean_R": round(float(np.mean(net_r)), 6),
        "median_R": round(float(np.median(net_r)), 6),
        "std_R": round(float(np.std(net_r)), 6),
        "gross_mean_R": round(float(np.mean([t.realized_r_gross for t in trades])), 6),
        "cost_per_trade_R": round(cost_per_trade, 6),
        "cost_adjusted_R": round(float(np.mean(net_r)) - cost_per_trade, 6),
        "2x_cost_R": round(float(np.mean(net_r)) - 2 * cost_per_trade, 6),
        "5x_cost_R": round(float(np.mean(net_r)) - 5 * cost_per_trade, 6),
        "win_rate": round(float(np.mean(net_r > 0)), 4),
        "symbol_breakdown": sym_counts,
        "symbol_R_breakdown": {k: round(v, 6) for k, v in sym_net_r.items()},
        "top_symbol": top_sym,
        "top_symbol_share": round(top_share, 4),
        "top_symbol_R": round(sym_net_r[top_sym] / sym_counts[top_sym], 6),
        "non_top_symbol_R": round(
            np.mean([sym_net_r[s] / sym_counts[s] for s in sym_counts if s != top_sym]),
            6
        ) if len(sym_counts) > 1 else 0.0,
        "positive_symbol_count": sum(1 for s in sym_net_r if sym_net_r[s] / sym_counts[s] > 0),
        "negative_symbol_count": sum(1 for s in sym_net_r if sym_net_r[s] / sym_counts[s] <= 0),
        "long_count": len(long_r),
        "short_count": len(short_r),
        "long_mean_R": round(float(np.mean(long_r)), 6) if long_r else 0.0,
        "short_mean_R": round(float(np.mean(short_r)), 6) if short_r else 0.0,
        "elapsed_seconds": round(elapsed, 2),
    }

    logger.info("  Trades=%d, R=%.6f, cost_adj=%.6f, top_sym=%s(%.1f%%), pos_syms=%d",
                result["trade_count"], result["raw_mean_R"], result["cost_adjusted_R"],
                top_sym, top_share * 100, result["positive_symbol_count"])

    return result


def export_trade_log(trades, output_path: str):
    """Export per-trade results to CSV."""
    fieldnames = [
        "trade_id", "alpha_id", "symbol", "direction", "entry_time",
        "exit_time", "entry_price", "exit_price", "exit_reason",
        "atr", "stop_price", "target_price", "initial_risk",
        "gross_R", "fee_R", "slippage_R", "funding_R", "net_R",
        "hold_bars", "confidence", "model_score", "path_quality",
    ]
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, t in enumerate(trades):
            sig = t.signal
            writer.writerow({
                "trade_id": i + 1,
                "alpha_id": "discovery_pipeline_v6_expanded",
                "symbol": sig.symbol,
                "direction": sig.side,
                "entry_time": sig.timestamp,
                "exit_time": "",
                "entry_price": sig.entry_price,
                "exit_price": t.exit_price,
                "exit_reason": t.exit_reason,
                "atr": sig.atr,
                "stop_price": sig.stop_price,
                "target_price": sig.target_price,
                "initial_risk": sig.initial_risk,
                "gross_R": round(t.realized_r_gross, 6),
                "fee_R": round(t.fee_cost_r, 6),
                "slippage_R": round(t.slippage_cost_r, 6),
                "funding_R": round(t.funding_cost_r, 6),
                "net_R": round(t.realized_r_net, 6),
                "hold_bars": t.hold_bars,
                "confidence": sig.confidence,
                "model_score": sig.model_score,
                "path_quality": round(t.path_quality_score, 4),
            })


def run_expansion_with_trades(
    symbols: tuple[str, ...],
    mode: str = "SCALP",
    confidence_threshold: float = 0.55,
    folds: int = 6,
    execution_mode: str = "TAKER",
    output_csv: str = "",
) -> dict | None:
    """Run expansion and also export the full trade log."""
    from alphaforge.discovery.backtest import backtest_signals
    from alphaforge.discovery.signal_generator import (
        generate_trade_signals,
        filter_overlapping_signals,
    )
    from alphaforge.train import (
        MODE_CONFIG,
        build_aligned_training_frame,
        walk_forward_validate,
        _load_panel_data,
        cross_sectional_rank_normalize,
    )

    t0 = time.time()
    cfg = MODE_CONFIG[mode]
    panel_cache = str(REPO_ROOT / "cache/factor_sprint")

    ohlcv = _load_panel_data(panel_cache, list(symbols))
    if ohlcv is None:
        return None

    training_frame = build_aligned_training_frame(ohlcv, mode)
    X = training_frame["X"]
    y_int = training_frame["y_int"]
    label_net_r = training_frame["label_net_r"]
    action_net_r = training_frame["action_net_r"]
    timestamps = training_frame["timestamps"]
    symbols_arr = training_frame["symbols"]
    close_arr_raw = training_frame.get("close_prices", None)

    X_clean = np.nan_to_num(X, nan=0.0)
    if len(np.unique(timestamps)) < len(timestamps):
        X_clean = cross_sectional_rank_normalize(X_clean, timestamps)

    wfv_results, fold_preds, fold_y_class, fold_y_val = walk_forward_validate(
        X_clean, y_int.copy(), label_net_r.copy(), mode,
        min_folds=folds,
        action_net_r=action_net_r.copy(),
        return_raw_preds=True,
    )

    signals = generate_trade_signals(
        fold_results=wfv_results,
        fold_preds=fold_preds,
        fold_y_class=fold_y_class,
        ohlcv=ohlcv,
        mode_cfg=cfg,
        timestamps=timestamps.copy(),
        symbols=symbols_arr.copy(),
        close_arr=close_arr_raw,
        confidence_threshold=confidence_threshold,
    )
    signals = filter_overlapping_signals(signals)

    if not signals:
        return None

    trades = backtest_signals(
        signals=signals,
        ohlcv=ohlcv,
        mode=mode,
        execution_mode=execution_mode,
    )

    if not trades:
        return None

    # Export trade log
    if output_csv:
        export_trade_log(trades, output_csv)
        logger.info("  Exported %d trades to %s", len(trades), output_csv)

    # Compute metrics
    net_r = np.array([t.realized_r_net for t in trades])
    fee_r = np.array([t.fee_cost_r for t in trades])
    slippage_r = np.array([t.slippage_cost_r for t in trades])
    cost_per_trade = float(np.mean(fee_r + slippage_r))

    sym_counts = {}
    sym_net_r = {}
    for t in trades:
        s = t.signal.symbol
        sym_counts[s] = sym_counts.get(s, 0) + 1
        sym_net_r[s] = sym_net_r.get(s, 0.0) + t.realized_r_net

    top_sym = max(sym_counts, key=sym_counts.get)
    top_share = sym_counts[top_sym] / len(trades)

    long_r = [t.realized_r_net for t in trades if t.signal.side == "LONG"]
    short_r = [t.realized_r_net for t in trades if t.signal.side == "SHORT"]

    # Time split (first half vs second half by timestamp)
    all_ts = np.array([t.signal.timestamp for t in trades])
    mid_ts = np.median(all_ts)
    first_half = [t for t in trades if t.signal.timestamp <= mid_ts]
    second_half = [t for t in trades if t.signal.timestamp > mid_ts]
    first_half_r = float(np.mean([t.realized_r_net for t in first_half])) if first_half else 0.0
    second_half_r = float(np.mean([t.realized_r_net for t in second_half])) if second_half else 0.0

    elapsed = time.time() - t0

    result = {
        "symbols": list(symbols),
        "mode": mode,
        "confidence_threshold": confidence_threshold,
        "folds": folds,
        "trade_count": len(trades),
        "signal_count": len(signals),
        "raw_mean_R": round(float(np.mean(net_r)), 6),
        "median_R": round(float(np.median(net_r)), 6),
        "std_R": round(float(np.std(net_r)), 6),
        "cost_per_trade_R": round(cost_per_trade, 6),
        "cost_adjusted_R": round(float(np.mean(net_r)) - cost_per_trade, 6),
        "2x_cost_R": round(float(np.mean(net_r)) - 2 * cost_per_trade, 6),
        "5x_cost_R": round(float(np.mean(net_r)) - 5 * cost_per_trade, 6),
        "win_rate": round(float(np.mean(net_r > 0)), 4),
        "symbol_breakdown": sym_counts,
        "symbol_R_breakdown": {k: round(v, 6) for k, v in sym_net_r.items()},
        "top_symbol": top_sym,
        "top_symbol_share": round(top_share, 4),
        "positive_symbol_count": sum(1 for s in sym_net_r if sym_net_r[s] / sym_counts[s] > 0),
        "negative_symbol_count": sum(1 for s in sym_net_r if sym_net_r[s] / sym_counts[s] <= 0),
        "long_count": len(long_r),
        "short_count": len(short_r),
        "long_mean_R": round(float(np.mean(long_r)), 6) if long_r else 0.0,
        "short_mean_R": round(float(np.mean(short_r)), 6) if short_r else 0.0,
        "first_half_R": round(first_half_r, 6),
        "second_half_R": round(second_half_r, 6),
        "first_half_count": len(first_half),
        "second_half_count": len(second_half),
        "elapsed_seconds": round(elapsed, 2),
    }

    return result


def main():
    parser = argparse.ArgumentParser(description="Truth V6 Expansion Validation")
    parser.add_argument("--symbols", nargs="+", default=None,
                        help="Symbols to use (default: all 20 in panel cache)")
    parser.add_argument("--max-symbols", type=int, default=None,
                        help="Max symbols to use (picks top N by bar count)")
    parser.add_argument("--mode", default="SCALP", choices=["SCALP", "SWING", "AGGRESSIVE_SCALP"])
    parser.add_argument("--threshold", type=float, default=0.55)
    parser.add_argument("--folds", type=int, default=6)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR / "expansion"))
    parser.add_argument("--write-trades", action="store_true", default=True)
    args = parser.parse_args()

    expansion_dir = Path(args.output_dir)
    expansion_dir.mkdir(parents=True, exist_ok=True)

    # Get available symbols
    import pandas as pd
    close = pd.read_parquet(REPO_ROOT / "cache/factor_sprint/panel_d8c8d55e3b8b107e_close.parquet")
    all_symbols = [c for c in close.columns if c != "__index_level_0__"]

    if args.symbols:
        symbols = tuple(args.symbols)
    elif args.max_symbols:
        # Pick top N by bar count
        sym_bars = [(s, close[s].notna().sum()) for s in all_symbols]
        sym_bars.sort(key=lambda x: -x[1])
        symbols = tuple(s for s, _ in sym_bars[:args.max_symbols])
    else:
        # Default: all symbols with >= 20K bars
        sym_bars = [(s, close[s].notna().sum()) for s in all_symbols]
        symbols = tuple(s for s, b in sym_bars if b >= 20000)

    logger.info("=" * 60)
    logger.info("Truth V6 Expansion Validation")
    logger.info("Symbols: %s (%d)", symbols, len(symbols))
    logger.info("=" * 60)

    # ── Run 1: Reconciliation — same 4 symbols, multiple configs ───────
    logger.info("\n=== RECONCILIATION: Testing configs to match 870 trades ===")
    recon_configs = [
        {"folds": 6, "threshold": 0.55, "label": "P0_baseline"},
        {"folds": 4, "threshold": 0.55, "label": "4_folds"},
        {"folds": 8, "threshold": 0.55, "label": "8_folds"},
        {"folds": 6, "threshold": 0.50, "label": "th_0.50"},
        {"folds": 6, "threshold": 0.45, "label": "th_0.45"},
        {"folds": 4, "threshold": 0.50, "label": "4f_th_0.50"},
    ]
    base_symbols = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT")
    recon_results = []
    for cfg in recon_configs:
        r = run_single_config(
            symbols=base_symbols,
            confidence_threshold=cfg["threshold"],
            folds=cfg["folds"],
            label=cfg["label"],
        )
        if r:
            recon_results.append(r)

    # ── Run 2: Expanded universe — 12 symbols ─────────────────────────
    logger.info("\n=== EXPANSION: 12-symbol universe ===")
    expanded_12 = run_expansion_with_trades(
        symbols=symbols[:12] if len(symbols) >= 12 else symbols,
        confidence_threshold=args.threshold,
        folds=args.folds,
        output_csv=str(expansion_dir / "truth_v6_expanded_trade_log.csv") if args.write_trades else "",
    )

    # ── Run 3: Full universe — all available ───────────────────────────
    logger.info("\n=== EXPANSION: Full symbol universe ===")
    expanded_full = run_expansion_with_trades(
        symbols=symbols,
        confidence_threshold=args.threshold,
        folds=args.folds,
        output_csv=str(expansion_dir / "truth_v6_expanded_full_trade_log.csv") if args.write_trades else "",
    )

    # ── Write reconciliation results ──────────────────────────────────
    recon_path = expansion_dir / "reconciliation_configs.json"
    with open(recon_path, "w") as f:
        json.dump(recon_results, f, indent=2)
    logger.info("Wrote reconciliation configs to %s", recon_path)

    # ── Write expansion summary ────────────────────────────────────────
    summary = {
        "run_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "reconciliation": recon_results,
        "expanded_12": expanded_12,
        "expanded_full": expanded_full,
    }
    summary_path = expansion_dir / "truth_v6_expanded_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    logger.info("Wrote summary to %s", summary_path)

    # ── Write expansion report ─────────────────────────────────────────
    md_path = expansion_dir / "TRUTH_V6_EXPANSION_RUN.md"
    with open(md_path, "w") as f:
        f.write("# Truth V6 Expansion Run\n\n")
        f.write(f"**Generated:** {summary['run_timestamp']}\n\n")

        f.write("## Reconciliation (4-symbol, multiple configs)\n\n")
        f.write("| Config | Folds | Threshold | Trades | Raw R | Cost-Adj R |\n")
        f.write("|--------|-------|-----------|--------|-------|------------|\n")
        for r in recon_results:
            f.write(f"| {r['label']} | {r['folds']} | {r['confidence_threshold']} | "
                    f"{r['trade_count']} | {r['raw_mean_R']:.6f} | {r['cost_adjusted_R']:.6f} |\n")

        if expanded_12:
            f.write("\n## 12-Symbol Expansion\n\n")
            f.write(f"- Trade count: {expanded_12['trade_count']}\n")
            f.write(f"- Raw R: {expanded_12['raw_mean_R']:.6f}\n")
            f.write(f"- Cost-adjusted R: {expanded_12['cost_adjusted_R']:.6f}\n")
            f.write(f"- Top symbol: {expanded_12['top_symbol']} ({expanded_12['top_symbol_share']:.1%})\n")
            f.write(f"- Positive symbols: {expanded_12['positive_symbol_count']}\n")

        if expanded_full:
            f.write("\n## Full Universe Expansion\n\n")
            f.write(f"- Symbols: {len(expanded_full['symbols'])}\n")
            f.write(f"- Trade count: {expanded_full['trade_count']}\n")
            f.write(f"- Raw R: {expanded_full['raw_mean_R']:.6f}\n")
            f.write(f"- Cost-adjusted R: {expanded_full['cost_adjusted_R']:.6f}\n")
            f.write(f"- Top symbol: {expanded_full['top_symbol']} ({expanded_full['top_symbol_share']:.1%})\n")
            f.write(f"- Positive symbols: {expanded_full['positive_symbol_count']}\n")

    logger.info("Wrote expansion report to %s", md_path)
    logger.info("=" * 60)
    logger.info("EXPANSION COMPLETE")
    logger.info("=" * 60)

    return summary


if __name__ == "__main__":
    try:
        result = main()
        if result is None:
            logger.error("FAILED")
            sys.exit(1)
    except Exception as e:
        logger.exception("FAILED_WITH_TRACEBACK")
        sys.exit(1)
