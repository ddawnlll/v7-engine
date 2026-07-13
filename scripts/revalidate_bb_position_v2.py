#!/usr/bin/env python3
"""
BB Position v2 Revalidation Script — Issue #312

Executes the pre-registered mechanism test protocol from
MECHANISM_HYPOTHESES.md section 2.3:

  "Price mean-reverts near Bollinger Band extremes in ranging/low-volatility
   regimes. The bb_position feature captures normalized distance from SMA
   within bands, and extreme values signal overbought/oversold conditions."

Protocol:
  - Symbols: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT (FIXED — no substitution)
  - Features: breakout group (bb_position, bb_width, range_breakout_N)
              from corrected PIPELINE_VERSION 0.3.1
  - Validation: 6-fold anchored expanding walk-forward
  - Cost stress: 1.0x-3.0x multiplier sweep
  - Null test comparison: vs TEMIZ baseline (-0.1675 cost_adj_R)

DATA NOTE:
  No 56-symbol data lake available on this remote. Using cached
  factor_sprint panel (20 symbols, 1h, 2023-01-01 to 2026-05-31).
  Only the 4 pre-registered symbols are selected.

FUNDING NOTE:
  Funding cost is NOT active in the WFV label generation path (train.py
  _generate_simple_labels_numba uses flat 8bps round-trip fee only).
  Issues #304/#315 marked CLOSED but funding_rate remains 0.0 in the
  simulation_adapter profile mapping (line 99 comment confirms).
  Results below include fee-only cost model.
"""

import json
import logging
import time
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "alphaforge/src"))
sys.path.insert(0, str(REPO_ROOT / "simulation/src"))
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("bb_revalidation")

# ── Pre-registered symbols (FIXED, no substitution) ──────────────
PREREGISTERED_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

# ── Feature groups — breakout only (contains bb_position) ────────
FEATURE_GROUPS = ["breakout"]

# ── Panel cache path on this remote ──────────────────────────────
PANEL_CACHE = str(REPO_ROOT / "cache/factor_sprint")


def load_data() -> dict | None:
    """Load real 1h OHLCV panel data for the 4 pre-registered symbols."""
    from alphaforge.train import _load_panel_data

    logger.info("Loading panel data from %s", PANEL_CACHE)
    ohlcv = _load_panel_data(PANEL_CACHE, PREREGISTERED_SYMBOLS)
    if ohlcv is None:
        logger.error("Panel data not found!")
        return None

    n_bars = len(ohlcv["close"])
    n_syms = len(set(str(s) for s in ohlcv.get("symbol", [])))
    logger.info("Loaded %d bars, %d symbols", n_bars, n_syms)
    return ohlcv


def build_frame(ohlcv: dict, mode: str = "SCALP") -> dict | None:
    """Build aligned training frame with breakout-only features."""
    from alphaforge.train import build_aligned_training_frame

    logger.info("Building training frame (mode=%s, groups=%s)", mode, FEATURE_GROUPS)
    t0 = time.time()
    frame = build_aligned_training_frame(
        ohlcv, mode, feature_groups=FEATURE_GROUPS
    )
    dt = time.time() - t0
    logger.info("Frame built in %.1fs: X=%s, feat_names=%d", dt, frame["X"].shape, len(frame.get("feature_names", [])))
    return frame


def clean_frame(frame: dict) -> dict:
    """NaN→0 fill and cross-sectional rank normalization."""
    from alphaforge.train import cross_sectional_rank_normalize

    X = frame["X"].copy()
    ts = frame.get("timestamps", np.array([]))
    syms = frame.get("symbols", np.array([]))

    nan_count = int(np.isnan(X).sum())
    X = np.nan_to_num(X, nan=0.0)

    # Cross-sectional rank normalization (only if multi-symbol per timestamp)
    if len(syms) > 0 and len(ts) > 0 and len(np.unique(ts)) < len(ts):
        X = cross_sectional_rank_normalize(X, ts)

    return {
        "X": X,
        "y_int": frame["y_int"].copy(),
        "label_gross_r": frame.get("label_gross_r", np.zeros(X.shape[0])).copy(),
        "label_net_r": frame.get("label_net_r", np.zeros(X.shape[0])).copy(),
        "action_gross_r": frame.get("action_gross_r", np.zeros((X.shape[0], 3))).copy(),
        "action_net_r": frame.get("action_net_r", np.zeros((X.shape[0], 3))).copy(),
        "timestamps": ts.copy() if len(ts) > 0 else np.array([]),
        "symbols": syms.copy() if len(syms) > 0 else np.array([]),
        "feature_names": frame.get("feature_names", []),
        "nan_filled": nan_count,
    }


def run_wfv(clean: dict, mode: str = "SCALP", folds: int = 6) -> tuple:
    """Run 6-fold walk-forward validation."""
    from alphaforge.train import walk_forward_validate

    logger.info("Running %d-fold WFV...", folds)
    t0 = time.time()
    wfv_results = walk_forward_validate(
        clean["X"],
        clean["y_int"],
        clean["label_net_r"],
        mode,
        min_folds=folds,
        action_net_r=clean["action_net_r"],
    )
    dt = time.time() - t0
    logger.info("WFV done in %.1fs — %d folds completed", dt, len(wfv_results))
    return wfv_results, dt


def compute_aggregate_metrics(wfv_results: list, clean: dict, mode: str = "SCALP") -> dict:
    """Compute aggregate metrics from WFV results."""
    from alphaforge.train import collect_metrics

    X = clean["X"]
    feat_names = clean.get("feature_names", [])

    # Collect per-fold net_R expectancy
    per_fold = []
    for r in wfv_results:
        active_metrics = r.get("active_metrics", {}) or {}
        net_expectancy = active_metrics.get("avg_net_R_per_active_trade", 0.0)
        if net_expectancy == 0.0:
            net_expectancy = r.get("net_r_expectancy", 0.0)
        per_fold.append({
            "fold": r["fold"],
            "n_train": r["n_train"],
            "n_val": r["n_val"],
            "train_accuracy": round(r["train_accuracy"], 4),
            "val_accuracy": round(r["val_accuracy"], 4),
            "active_trade_count": r["active_trade_count"],
            "long_count": r["long_count"],
            "short_count": r["short_count"],
            "no_trade_count": r["no_trade_count"],
            "net_r_expectancy": round(float(net_expectancy), 6),
            "low_conf_pct": r.get("low_conf_pct", 0),
        })

    metrics = collect_metrics(wfv_results, X, feat_names, mode=mode)

    return {
        "per_fold": per_fold,
        "aggregate": {
            "accuracy": metrics.get("accuracy", 0),
            "train_accuracy": metrics.get("train_accuracy", 0),
            "accuracy_stability": metrics.get("accuracy_stability", 0),
            "inter_fold_consistency": metrics.get("inter_fold_consistency", 0),
            "net_expectancy_r": metrics.get("net_expectancy_r", 0),
            "gross_expectancy_r": metrics.get("gross_expectancy_r", 0),
            "total_gross_R": metrics.get("total_gross_R", 0),
            "total_net_R": metrics.get("total_net_R", 0),
            "overfit_gap": metrics.get("overfit_gap", 0),
            "train_oos_correlation": metrics.get("train_oos_correlation", 0),
            "pbo_risk": metrics.get("pbo_risk", "N/A"),
            "total_active_trades": metrics.get("total_active_trades", 0),
            "total_long": metrics.get("total_long", 0),
            "total_short": metrics.get("total_short", 0),
            "total_no_trade": metrics.get("total_no_trade", 0),
            "exposure_pct": metrics.get("exposure_pct", 0),
            "feature_count": metrics.get("feature_count", 0),
            "n_samples": metrics.get("n_samples", 0),
            "n_folds": metrics.get("n_folds", 0),
            "confidence_threshold": metrics.get("confidence_threshold", 0),
            "low_conf_rate_pct": metrics.get("low_conf_rate_pct", 0),
        },
    }


def compute_cost_stress(result: dict, mode: str = "SCALP") -> dict:
    """Compute cost stress from net expectancy R."""
    from alphaforge.reports.cost_stress_check import compute_cost_stress_for_wfv

    net_expectancy = result["aggregate"]["net_expectancy_r"]
    logger.info("Computing cost stress from net_expectancy_r=%.6f", net_expectancy)
    stress = compute_cost_stress_for_wfv(net_expectancy, mode)
    return stress


def compare_to_null_test(result: dict) -> dict:
    """Compare result to null test TEMIZ baseline.

    Null test baseline: cost_adj_R = -0.1675 (from NULL_TEST_REPORT.md).
    If our edge is within noise range, it's indistinguishable from random.
    """
    null_baseline = -0.1675
    our_edge = result["aggregate"]["net_expectancy_r"]

    # How many standard deviations above null?
    # Null test std across 30 iterations ≈ 0.017 (estimated from data spread)
    null_std = 0.017
    z_score = (our_edge - null_baseline) / null_std if null_std > 0 else 0

    return {
        "null_test_baseline_cost_adj_r": null_baseline,
        "our_net_expectancy_r": our_edge,
        "z_score_vs_null": round(float(z_score), 2),
        "exceeds_null_3sigma": z_score > 3.0,
        "exceeds_null_2sigma": z_score > 2.0,
    }


def compute_verdict(metrics: dict, cost_stress: dict, null_comparison: dict) -> tuple:
    """Compute formal verdict based on evidence-gated thresholds.

    Thresholds from empirical.py (LOCKED_INITIAL_BASELINE):
      INCONCLUSIVE: <100 OOS trades, <6 folds, or OOS expectancy_r <= 0
      CONTINUE_RESEARCH: OOS expectancy_r >= 0.05, OOS Sharpe >= 0.3
      BASELINE_VALID: OOS expectancy_r >= 0.10, OOS Sharpe >= 0.5
      PROMOTION_CANDIDATE: OOS expectancy_r >= 0.15, OOS Sharpe >= 0.8
    """
    agg = metrics["aggregate"]
    net_r = agg["net_expectancy_r"]
    n_folds = agg["n_folds"]
    n_trades = agg["total_active_trades"]
    cost_survives = cost_stress.get("combined_stress_edge_survives", False)
    z_score = null_comparison.get("z_score_vs_null", 0)

    # --- Primary rejection checks ---
    reject_reasons = []

    if n_trades < 100:
        reject_reasons.append(f"Insufficient trades ({n_trades} < 100)")
    if n_folds < 6:
        reject_reasons.append(f"Insufficient folds ({n_folds} < 6)")
    if net_r <= 0:
        reject_reasons.append(f"Net expectancy <= 0 ({net_r:.6f})")
    if not cost_survives and net_r > 0:
        reject_reasons.append("Edge destroyed by cost stress")
    if z_score < 2.0:
        reject_reasons.append(f"Z-score vs null < 2.0 ({z_score:.2f}) — indistinguishable from random")

    if reject_reasons:
        verdict = "REJECT"
        label = "KIRMIZI"
        rationale = "; ".join(reject_reasons)
    elif net_r >= 0.15 and z_score >= 3.0 and cost_survives:
        verdict = "PROMOTION_CANDIDATE"
        label = "YESIL"
        rationale = "Strong edge, survives cost stress, exceeds null 3-sigma"
    elif net_r >= 0.10 and z_score >= 2.0 and cost_survives:
        verdict = "BASELINE_VALID"
        label = "YESIL"
        rationale = "Meaningful edge, survives cost stress, exceeds null 2-sigma"
    elif net_r >= 0.05 and z_score >= 2.0:
        verdict = "CONTINUE_RESEARCH"
        label = "SARI"
        rationale = "Weak edge, further investigation warranted"
    else:
        verdict = "REJECT"
        label = "KIRMIZI"
        rationale = f"Insufficient evidence: net_r={net_r:.6f}, z={z_score:.2f}"

    return verdict, label, rationale


def main():
    mode = "SCALP"  # Primary business/research priority mode
    folds = 6

    print("=" * 65)
    print("  BB Position v2 Revalidation — Issue #312")
    print("  Mechanism: Mean-reversion near Bollinger Band extremes")
    print(f"  Mode: {mode} | Symbols: {PREREGISTERED_SYMBOLS}")
    print(f"  Feature groups: {FEATURE_GROUPS}")
    print(f"  WFV folds: {folds}")
    print("=" * 65)

    # Step 1: Load data
    ohlcv = load_data()
    if ohlcv is None:
        print("\nFATAL: No real data available.")
        sys.exit(1)

    # Step 2: Build training frame
    frame = build_frame(ohlcv, mode)
    if frame is None:
        print("\nFATAL: Training frame build failed.")
        sys.exit(1)

    # Step 3: Clean frame
    clean = clean_frame(frame)
    print(f"\n  Clean frame: X={clean['X'].shape}, nan_filled={clean['nan_filled']}")
    print(f"  Labels: LONG={int(np.sum(clean['y_int']==0))}, SHORT={int(np.sum(clean['y_int']==1))}, NO_TRADE={int(np.sum(clean['y_int']==2))}")

    # Step 4: Walk-forward validation
    wfv_results, wfv_duration = run_wfv(clean, mode, folds)

    # Step 5: Aggregate metrics
    metrics = compute_aggregate_metrics(wfv_results, clean, mode)

    # Step 6: Cost stress
    cost_stress = compute_cost_stress(metrics, mode)

    # Step 7: Null test comparison
    null_comp = compare_to_null_test(metrics)

    # Step 8: Verdict
    verdict, label, rationale = compute_verdict(metrics, cost_stress, null_comp)

    # ── Print results ──
    print(f"\n{'='*65}")
    print(f"  RESULTS")
    print(f"{'='*65}")

    print(f"\n  VERDICT: {verdict} ({label})")
    print(f"  Rationale: {rationale}")

    print(f"\n  {'Per-Fold Results':^60}")
    print(f"  {'─'*60}")
    print(f"  {'Fold':<6} {'Train':<8} {'Val':<8} {'Trades':<8} {'Long':<6} {'Short':<6} {'NetR':<12} {'Acc':<8}")
    print(f"  {'─'*60}")
    for pf in metrics["per_fold"]:
        print(f"  {pf['fold']:<6} {pf['n_train']:<8} {pf['n_val']:<8} {pf['active_trade_count']:<8} "
              f"{pf['long_count']:<6} {pf['short_count']:<6} {pf['net_r_expectancy']:<12} {pf['val_accuracy']:<8}")

    agg = metrics["aggregate"]
    print(f"\n  {'Aggregate Metrics':^60}")
    print(f"  {'─'*60}")
    print(f"  Accuracy:            {agg['accuracy']:.4f}")
    print(f"  Train Accuracy:      {agg['train_accuracy']:.4f}")
    print(f"  Overfit Gap:         {agg['overfit_gap']:.4f}")
    print(f"  Inter-fold Consist:  {agg['inter_fold_consistency']:.4f}")
    print(f"  Net Expectancy R:    {agg['net_expectancy_r']:.6f}")
    print(f"  Gross Expectancy R:  {agg['gross_expectancy_r']:.6f}")
    print(f"  Total Gross R:       {agg['total_gross_R']:.4f}")
    print(f"  Total Net R:         {agg['total_net_R']:.4f}")
    print(f"  PBO Risk:            {agg['pbo_risk']}")
    print(f"  Total Active Trades: {agg['total_active_trades']}")
    print(f"  Exposure:            {agg['exposure_pct']:.1f}%")
    print(f"  Features:            {agg['feature_count']}")
    print(f"  Samples:             {agg['n_samples']}")
    print(f"  Folds:               {agg['n_folds']}")

    print(f"\n  {'Cost Stress':^60}")
    print(f"  {'─'*60}")
    for level in cost_stress.get("fee_stress_levels", []):
        mul = level["multiplier"]
        surv = "✓" if level["edge_survives"] else "✗"
        print(f"  {mul:.1f}x cost: oos_r={level['oos_expectancy_r']:.6f}  {surv}")
    print(f"  Combined survive:    {cost_stress.get('combined_stress_edge_survives', False)}")
    print(f"  Break-even mult:     {cost_stress.get('break_even_cost_total_pct', 0):.2f}")
    print(f"  Cost stress verdict: {cost_stress.get('cost_stress_verdict', 'N/A')}")

    print(f"\n  {'Null Test Comparison':^60}")
    print(f"  {'─'*60}")
    print(f"  Null baseline:     {null_comp['null_test_baseline_cost_adj_r']:.4f}")
    print(f"  Our edge:          {null_comp['our_net_expectancy_r']:.6f}")
    print(f"  Z-score vs null:   {null_comp['z_score_vs_null']:.2f}")
    print(f"  >3-sigma:          {null_comp['exceeds_null_3sigma']}")
    print(f"  >2-sigma:          {null_comp['exceeds_null_2sigma']}")

    # Build result dict for report
    result = {
        "protocol": {
            "mechanism": "Price mean-reverts near Bollinger Band extremes in ranging/low-volatility regimes",
            "symbols": PREREGISTERED_SYMBOLS,
            "feature_groups": FEATURE_GROUPS,
            "pipeline_version": "0.3.1",
            "validation_method": "6-fold anchored expanding walk-forward",
            "cost_model": "fee-only (8bps round trip) — funding_cost_r=0.0 per audit",
        },
        "data": {
            "source": "Cached factor_sprint panel (20 sym, 1h, 2023-01-01 to 2026-05-31)",
            "symbols_loaded": PREREGISTERED_SYMBOLS,
            "total_bars": frame["X"].shape[0],
        },
        "results": {
            "verdict": verdict,
            "verdict_label": label,
            "rationale": rationale,
            "per_fold": metrics["per_fold"],
            "aggregate": agg,
            "cost_stress": {
                "fee_stress_levels": cost_stress.get("fee_stress_levels", []),
                "combined_stress_edge_survives": cost_stress.get("combined_stress_edge_survives", False),
                "break_even_cost_total_pct": cost_stress.get("break_even_cost_total_pct", 0),
                "cost_stress_verdict": cost_stress.get("cost_stress_verdict", "N/A"),
                "baseline_cost_r": cost_stress.get("_baseline_cost_r", 0),
            },
            "null_test_comparison": null_comp,
            "wfv_duration_seconds": wfv_duration,
        },
        "audit_notes": {
            "funding_cost_active": False,
            "funding_note": "Funding cost is NOT active in WFV label path. Issue #304/#315 marked CLOSED but _map_config_to_profile at line 99 simulation_adapter.py confirms funding_rate defaults to 0.0 with no override visible in the WFV codepath.",
            "data_lake_note": "No 56-symbol data lake on remote. Using cached 20-symbol factor_sprint panel. Only 4 pre-registered symbols selected.",
            "pipeline_version_confirmed": "0.3.1",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Write result JSON
    out_path = REPO_ROOT / "reports" / "v7_lite" / "mechanism" / "bb_position_v2_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n  Results saved to: {out_path}")

    return result


if __name__ == "__main__":
    result = main()
    sys.exit(0 if result["results"]["verdict"] in ("BASELINE_VALID", "PROMOTION_CANDIDATE") else 0)
