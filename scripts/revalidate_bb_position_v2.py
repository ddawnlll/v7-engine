#!/usr/bin/env python3
"""
BB Position v2 Revalidation — REAL DATA RUN (Issue #312)

Two data sources:
  1. Canonical raw: data/raw/{SYMBOL}/*.parquet (10 sym, 90 days 1h)
  2. Cache panel: cache/factor_sprint/panel_*.parquet (20 sym, 3.5y 1h)

Usage:
  PYTHONPATH=alphaforge/src:simulation/src:. python3 scripts/revalidate_bb_position_v2.py
"""

import json, logging, sys, time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "alphaforge/src"))
sys.path.insert(0, str(REPO_ROOT / "simulation/src"))
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("bb_reval")

MODE = "SCALP"
FOLDS = 6
SYMBOLS_RAW = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
               "ADAUSDT", "AVAXUSDT", "DOGEUSDT", "DOTUSDT",
               "LINKUSDT", "XRPUSDT"]


def load_data_real(symbols):
    from alphaforge.train import load_cached_data
    ohlcv = load_cached_data(symbols, "1h")
    if ohlcv is None:
        return None
    n = len(ohlcv["close"])
    syms = len(set(str(s) for s in ohlcv.get("symbol", [])))
    if n < 5000 or syms < 2:
        logger.warning("Raw data too small (%d bars, %d syms)", n, syms)
        return None
    logger.info("Loaded %d bars, %d symbols from canonical raw", n, syms)
    return ohlcv


def load_data_panel(symbols, panel_cache):
    from alphaforge.train import _load_panel_data
    ohlcv = _load_panel_data(panel_cache, symbols)
    if ohlcv is None:
        return None
    n = len(ohlcv["close"])
    syms = len(set(str(s) for s in ohlcv.get("symbol", [])))
    logger.info("Loaded %d bars, %d symbols from panel cache", n, syms)
    return ohlcv


def run_pipeline(ohlcv, data_label, features="all"):
    from alphaforge.train import build_aligned_training_frame, walk_forward_validate, collect_metrics, cross_sectional_rank_normalize
    from alphaforge.reports.cost_stress_check import compute_cost_stress_for_wfv

    fg = None if features == "all" else [g.strip() for g in features.split(",")]
    print(f"\n{'='*65}")
    print(f"  RUN: {data_label} | features={features} | WFV={FOLDS}")
    print(f"{'='*65}")

    t0 = time.time()
    frame = build_aligned_training_frame(ohlcv, MODE, feature_groups=fg)
    feat_names = frame.get("feature_names", [])
    print(f"  Frame: {frame['X'].shape} in {time.time()-t0:.1f}s  feat={len(feat_names)}")

    X = np.nan_to_num(frame["X"].copy(), nan=0.0)
    ts = frame.get("timestamps", np.array([]))
    syms_arr = frame.get("symbols", np.array([]))
    if len(syms_arr) > 0 and len(ts) > 0 and len(np.unique(ts)) < len(ts):
        X = cross_sectional_rank_normalize(X, ts)

    y = frame["y_int"]
    net_r = frame["label_net_r"]
    action_net = frame["action_net_r"]
    print(f"  Clean: X={X.shape}  y_dist=({int(np.sum(y==0))}L/{int(np.sum(y==1))}S/{int(np.sum(y==2))}N)")

    t0 = time.time()
    wfv = walk_forward_validate(X, y, net_r, MODE, min_folds=FOLDS, action_net_r=action_net)
    print(f"  WFV: {len(wfv)}/{FOLDS} folds in {time.time()-t0:.1f}s")

    if "bb_position" in feat_names:
        bbidx = feat_names.index("bb_position")
        print(f"  bb_position idx={bbidx}/{len(feat_names)}")

    for r in wfv:
        am = r.get("active_metrics", {}) or {}
        ne = am.get("avg_net_R_per_active_trade", r.get("net_r_expectancy", 0))
        print(f"  Fold {r['fold']}: train={r['n_train']} val={r['n_val']} "
              f"trades={r['active_trade_count']} long={r['long_count']} short={r['short_count']} "
              f"netR={float(ne):.6f} acc={r['val_accuracy']:.4f} "
              f"lowconf={r.get('low_conf_pct',0):.1f}%")

    # collect_metrics returns flat dict, not nested
    m = collect_metrics(wfv, X, feat_names, mode=MODE)
    # m has keys: accuracy, net_expectancy_r, total_active_trades, etc. — flat

    net_r_val = float(m.get("net_expectancy_r", 0))
    cost_stress = compute_cost_stress_for_wfv(net_r_val, MODE)

    null_baseline = -0.1675
    z = (net_r_val - null_baseline) / 0.017 if null_baseline != 0 else 0

    print(f"\n  Aggregate   netR={net_r_val:.6f}  acc={m.get('accuracy',0):.4f}  "
          f"train_acc={m.get('train_accuracy',0):.4f}  "
          f"gap={m.get('overfit_gap',0):.4f}  trades={m.get('total_active_trades',0)}  "
          f"exposure={m.get('exposure_pct',0):.1f}%  pbo={m.get('pbo_risk','?')}")
    print(f"  Cost 1.0x: r={net_r_val:.6f}  1.5x: {cost_stress['fee_stress_levels'][1]['oos_expectancy_r']:.6f}  "
          f"BE={cost_stress.get('break_even_cost_total_pct',0):.2f}x  "
          f"Survive: {cost_stress.get('combined_stress_edge_survives',False)}")
    print(f"  Null: z={z:.2f}  edge={net_r_val:.6f} vs baseline={null_baseline}")

    if net_r_val <= 0 or not cost_stress.get("combined_stress_edge_survives", False):
        verdict, label = "REJECT", "KIRMIZI"
        reason = f"edge={net_r_val:.6f} destroyed by costs" if net_r_val > 0 else f"edge={net_r_val:.6f} <= 0"
    elif net_r_val >= 0.10 and z > 3:
        verdict, label = "BASELINE_VALID", "YESIL"
        reason = "strong edge"
    elif net_r_val >= 0.05:
        verdict, label = "CONTINUE_RESEARCH", "SARI"
        reason = f"weak edge={net_r_val:.6f}"
    else:
        verdict, label = "REJECT", "KIRMIZI"
        reason = f"net_r={net_r_val:.6f} insufficient"
    print(f"  VERDICT: {verdict} ({label}) — {reason}")

    return {
        "data_label": data_label, "features": features,
        "n_folds": len(wfv),
        "per_fold": [dict(fold=r["fold"], n_train=r["n_train"], n_val=r["n_val"],
                          active=r["active_trade_count"], long=r["long_count"],
                          short=r["short_count"],
                          net_r=float((r.get("active_metrics",{}) or {}).get(
                              "avg_net_R_per_active_trade", r.get("net_r_expectancy",0))),
                          val_acc=r["val_accuracy"],
                          low_conf_pct=r.get("low_conf_pct",0))
                     for r in wfv],
        "aggregate": {"net_expectancy_r": net_r_val,
                      "accuracy": m.get("accuracy",0),
                      "train_accuracy": m.get("train_accuracy",0),
                      "overfit_gap": m.get("overfit_gap",0),
                      "total_active_trades": m.get("total_active_trades",0),
                      "exposure_pct": m.get("exposure_pct",0),
                      "pbo_risk": m.get("pbo_risk","?"),
                      "n_samples": m.get("n_samples",0),
                      "n_features": m.get("feature_count",0)},
        "cost_stress": {"fee_stress_levels": cost_stress.get("fee_stress_levels", []),
                        "combined_stress_edge_survives": cost_stress.get("combined_stress_edge_survives", False),
                        "break_even": cost_stress.get("break_even_cost_total_pct", 0),
                        "cost_stress_verdict": cost_stress.get("cost_stress_verdict", "?")},
        "null_comparison": {"z_score": round(float(z), 2), "our_edge": net_r_val,
                            "baseline": null_baseline},
        "verdict": verdict, "verdict_label": label, "reason": reason,
    }


def main():
    results = []
    panel_cache = str(REPO_ROOT / "cache/factor_sprint")

    # --- RUN 1: Canonical raw, 10 symbols, ALL features ---
    print("=" * 65)
    print("  RUN 1: CANONICAL RAW — 10 symbols, ALL features")
    print("=" * 65)
    ohlcv_raw = load_data_real(SYMBOLS_RAW)
    if ohlcv_raw:
        results.append(run_pipeline(ohlcv_raw, "CANONICAL_RAW_10SYM", "all"))

    # --- RUN 2: Cache panel, 4 pre-registered symbols, breakout only (baseline) ---
    print(f"\n{'='*65}")
    print("  RUN 2: CACHE PANEL — 4 symbols, breakout ONLY (baseline)")
    print(f"{'='*65}")
    ohlcv_pc = load_data_panel(["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"], panel_cache)
    if ohlcv_pc:
        results.append(run_pipeline(ohlcv_pc, "CACHE_PANEL_4SYM_BREAKOUT", "breakout"))

    # --- Summary ---
    print(f"\n{'='*65}")
    print("  SUMMARY")
    print(f"{'='*65}")
    for r in results:
        a = r["aggregate"]
        print(f"  {r['data_label']:>35s} | {r['features']:>12s} | "
              f"N={a['n_samples']:>6d} | "
              f"netR={a['net_expectancy_r']:+.6f} | "
              f"acc={a['accuracy']:.3f} | "
              f"trades={a['total_active_trades']:>5d} | "
              f"survive={str(r['cost_stress']['combined_stress_edge_survives']):>5s} | "
              f"{r['verdict_label']:>7s}")

    out = REPO_ROOT / "reports" / "v7_lite" / "mechanism" / "bb_position_v2_result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump({"runs": results, "generated_at": datetime.now(timezone.utc).isoformat(),
                    "config": {"mode": MODE, "folds": FOLDS}}, f, indent=2, default=str)
    print(f"\n  Saved: {out}")


if __name__ == "__main__":
    main()
