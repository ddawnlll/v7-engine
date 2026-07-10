"""Build the Negative Alpha Autopsy + Rescue Matrix from the alpha inventory.

Reads ALPHA_INVENTORY_FULL.csv and alpha_ledger.json, classifies every alpha,
produces the rescue matrix CSV/JSON and all supporting reports.
"""

import csv
import json
import sys
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Load alpha inventory
# ---------------------------------------------------------------------------
def load_inventory(path) -> list[dict]:
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows

# ---------------------------------------------------------------------------
# Classification logic
# ---------------------------------------------------------------------------
def classify_alpha(row: dict) -> tuple[str, str, dict]:
    """Return (classification, rescue_action, extra_metadata)."""
    alpha_id = row.get("alpha_id", "")
    status = row.get("status", "").strip()
    raw_r_str = row.get("net_R_per_trade", "").strip()
    trade_count_str = row.get("trade_count", "").strip()
    win_rate_str = row.get("win_rate", "").strip()
    profit_factor_str = row.get("profit_factor", "").strip()
    max_dd_str = row.get("max_drawdown_R", "").strip()
    sharpe_str = row.get("sharpe", "").strip()
    oos_rank_ic_str = row.get("oos_rank_ic", "").strip()
    holdout_tested = row.get("holdout_tested", "").strip()
    cost_stress = row.get("cost_stress_survived", "").strip()
    notes = row.get("notes", "").strip()
    tags = row.get("tags", "").strip()
    source = row.get("source", "").strip()
    name = row.get("name", "").strip()

    # Parse numeric fields
    raw_r = try_float(raw_r_str)
    trade_count = try_int(trade_count_str)
    win_rate = try_float(win_rate_str)
    profit_factor = try_float(profit_factor_str)
    max_dd = try_float(max_dd_str)
    sharpe = try_float(sharpe_str)
    oos_rank_ic = try_float(oos_rank_ic_str)

    # Metadata
    meta = {
        "alpha_id": alpha_id,
        "alpha_name": name,
        "source_file": "reports/ALPHA_INVENTORY_FULL.csv",
        "mode": row.get("mode", ""),
        "family_or_cluster": "",
        "status": status,
        "raw_net_R": raw_r,
        "cost_adjusted_R": None,
        "estimated_cost_R": 0.062,
        "trade_count": trade_count,
        "winrate": win_rate,
        "ic_score": oos_rank_ic,
        "oos_R": None,
        "walk_forward_status": "UNKNOWN",
        "holdout_status": "NOT_RUN" if holdout_tested.lower() == "false" else "UNKNOWN",
        "contaminated": "contaminated" in tags.lower() or "leakage" in tags.lower(),
        "failure_reason": notes,
        "primary_loss_bucket": "",
        "symbol_concentration": "UNKNOWN",
        "regime_available": False,
        "session_available": False,
        "spread_available": False,
        "volume_available": False,
        "baseline_compared": False,
        "baseline_dominance_status": "UNKNOWN",
        "classification": "",
        "rescue_action": "",
        "inversion_priority": 0,
        "segment_rescue_priority": 0,
        "cost_rescue_priority": 0,
        "retest_priority": 0,
        "recommended_next_experiment": "",
        "confidence": "LOW",
        "notes": notes,
    }

    # ---- FAMILY / CLUSTER ----
    family = assign_family(alpha_id, name)
    meta["family_or_cluster"] = family

    # ---- CLASSIFICATION ----
    # Special cases first
    if meta["contaminated"]:
        meta["classification"] = "CONTAMINATED_REJECT"
        meta["rescue_action"] = "Do not use. Check if corrected v2 exists."
        meta["confidence"] = "HIGH"
        return meta["classification"], meta["rescue_action"], meta

    if raw_r is None and status in ("HOLD", "WATCH"):
        meta["classification"] = "RETEST_REQUIRED"
        meta["rescue_action"] = "Re-run with completed simulation pipeline"
        meta["retest_priority"] = 3
        meta["confidence"] = "LOW"
        return meta["classification"], meta["rescue_action"], meta

    # Discovery Pipeline V6 — special treatment (best alpha)
    if "discovery_pipeline_v6" in alpha_id:
        meta["classification"] = "PROMISING_RAW_POSITIVE"
        meta["rescue_action"] = "Cost rescue: regime/symbol filters needed"
        meta["cost_rescue_priority"] = 5
        meta["confidence"] = "HIGH"
        return meta["classification"], meta["rescue_action"], meta

    # SCALP 1h Direction v01 (+0.0076R) — weak positive
    if "scalp_1h_direction_v01" in alpha_id:
        meta["classification"] = "PROMISING_RAW_POSITIVE"
        meta["rescue_action"] = "Needs cost survival. Test confidence threshold filter."
        meta["cost_rescue_priority"] = 3
        meta["confidence"] = "MEDIUM"
        return meta["classification"], meta["rescue_action"], meta

    # BB Position v1 — contaminated but has green v2
    if "bb_position" in alpha_id:
        if "v1" in alpha_id and "v2" not in alpha_id:
            meta["classification"] = "CONTAMINATED_REJECT"
            meta["rescue_action"] = "Use v2 (corrected). v1 is unrecoverable."
            meta["confidence"] = "HIGH"
            return meta["classification"], meta["rescue_action"], meta
        elif "v2" in alpha_id:
            meta["classification"] = "RETEST_REQUIRED"
            meta["rescue_action"] = "Run v2 on corrected features"
            meta["retest_priority"] = 5
            meta["confidence"] = "MEDIUM"
            return meta["classification"], meta["rescue_action"], meta

    # Factor sprint alphas with IC scores
    if source.strip() in ("factor_sprint_ic_leaderboard",):
        ic_ir_abs = abs(oos_rank_ic) if oos_rank_ic else 0
        if raw_r is None:
            if ic_ir_abs < 0.01:
                meta["classification"] = "NOISE_NEAR_ZERO"
                meta["rescue_action"] = "Not useful. Drop from active research."
                meta["confidence"] = "HIGH"
            elif ic_ir_abs < 0.04:
                meta["classification"] = "FEATURE_ONLY"
                meta["rescue_action"] = "Keep as feature/filter. Not a trade signal."
                meta["confidence"] = "MEDIUM"
            else:
                # Check if this is an inversion candidate (MISALIGNED)
                if status == "WATCH" and ic_ir_abs >= 0.1:
                    meta["classification"] = "INVERSION_CANDIDATE"
                    meta["rescue_action"] = "Invert declared direction. Test with corrected sign."
                    meta["inversion_priority"] = min(int(ic_ir_abs * 20), 5)
                    meta["confidence"] = "MEDIUM"
                else:
                    meta["classification"] = "FEATURE_ONLY"
                    meta["rescue_action"] = "Marginal IC. Use as feature if implemented."
            return meta["classification"], meta["rescue_action"], meta

    # Factor sprint R-leaderboard / Proxy — group by CONCEPT not by mode variant
    # The same concept appears 3 times (SWING_PROXY_1H, SCALP_1H_SLOW, SCALP_1H_FAST).
    # Only the BEST variant matters for classification.
    is_fs_r = source.strip() in ("factor_sprint_r_leaderboard",)
    is_fs_proxy = source.strip() in ("factor_sprint_proxy",)
    
    if is_fs_r or is_fs_proxy:
        if raw_r is not None and raw_r < 0:
            abs_r = abs(raw_r)
            # Extract core concept from name
            concept = name.split("(")[0].strip() if "(" in name else name
            
            # Known baseline concepts that are well-documented market phenomena
            baseline_concepts = {
                "range_zscore": "ATR/volatility baseline",
                "volume_zscore": "Volume baseline", 
                "session_volatility": "Volatility regime baseline",
                "compression_expansion": "BB width baseline",
            }
            is_known_baseline = any(k in alpha_id.lower() for k in baseline_concepts)
            
            if is_fs_proxy:
                meta["classification"] = "RETEST_REQUIRED"
                meta["rescue_action"] = f"Proxy sim only ({concept}). Run on central simulation."
                meta["retest_priority"] = 2
                meta["confidence"] = "LOW"
            elif is_known_baseline:
                meta["classification"] = "BASELINE_DUPLICATE"
                meta["rescue_action"] = f"Baseline concept ({concept}). Keep for benchmark, not alpha."
                meta["confidence"] = "HIGH"
            elif abs_r > 0.2 and trade_count and trade_count > 10000:
                meta["classification"] = "INVERSION_CANDIDATE"
                meta["rescue_action"] = f"Consistently {abs_r:.2f}R negative across {trade_count} trades. Invert signal."
                meta["inversion_priority"] = 4
                meta["confidence"] = "MEDIUM"
            elif abs_r > 0.05:
                meta["classification"] = "FEATURE_ONLY"
                meta["rescue_action"] = f"Weak signal ({raw_r:.4f}R). Use as feature/filter."
                meta["confidence"] = "LOW"
            else:
                meta["classification"] = "NOISE_NEAR_ZERO"
                meta["rescue_action"] = f"Near zero ({raw_r:.4f}R). Drop from active research."
                meta["confidence"] = "MEDIUM"
            return meta["classification"], meta["rescue_action"], meta

    # Operation SCALP 0.05 results
    if "op005" in alpha_id or "op_scalp" in alpha_id or "operation" in alpha_id:
        meta["classification"] = "COST_RESCUE_CANDIDATE"
        meta["rescue_action"] = "Raw edge is weak. Test maker execution + symbol filter."
        meta["cost_rescue_priority"] = 2
        meta["confidence"] = "HIGH"
        if raw_r and raw_r < -0.08:
            meta["classification"] = "SEGMENT_RESCUE_CANDIDATE"
            meta["rescue_action"] = "Test regime/symbol filtering. May have segments."
            meta["segment_rescue_priority"] = 3
        return meta["classification"], meta["rescue_action"], meta

    # SWING control
    if "swing_control" in alpha_id:
        meta["classification"] = "REJECT_FOREVER"
        meta["rescue_action"] = "Control baseline. Strongly negative. No rescue path."
        meta["confidence"] = "HIGH"
        return meta["classification"], meta["rescue_action"], meta

    # BTC-dependent alphas
    if "btc_" in alpha_id.lower():
        if raw_r and raw_r < -0.3:
            meta["classification"] = "REJECT_FOREVER"
            meta["rescue_action"] = "Strongly negative across BTC regime. Not rescuable."
            meta["confidence"] = "HIGH"
        else:
            meta["classification"] = "REGIME_SPECIALIST_CANDIDATE"
            meta["rescue_action"] = "BTC-corr alphas may work in specific BTC regimes."
            meta["confidence"] = "LOW"
        return meta["classification"], meta["rescue_action"], meta

    # Fallback for any remaining entries with negative R that aren't from factor sprint / proxy
    # These should only be ledger entries not caught above
    if raw_r is not None and raw_r < 0 and source.strip() in ("ledger",):
        abs_r = abs(raw_r)
        if abs_r > 0.3:
            meta["classification"] = "REJECT_FOREVER"
            meta["rescue_action"] = f"Strongly negative ({raw_r:.4f}R). No rescue mechanism known."
            meta["confidence"] = "HIGH"
        elif abs_r > 0.1:
            meta["classification"] = "SEGMENT_RESCUE_CANDIDATE"
            meta["rescue_action"] = "Moderately negative. Try regime/symbol splitting."
            meta["segment_rescue_priority"] = 2
            meta["confidence"] = "LOW"
        else:
            meta["classification"] = "NOISE_NEAR_ZERO"
            meta["rescue_action"] = f"Near zero ({raw_r:.4f}R). Not actionable."
            meta["confidence"] = "MEDIUM"
        return meta["classification"], meta["rescue_action"], meta

    # Default for unclassified
    meta["classification"] = "RETEST_REQUIRED"
    meta["rescue_action"] = "Insufficient data to classify. Re-run for completeness."
    meta["retest_priority"] = 1
    meta["confidence"] = "LOW"
    return meta["classification"], meta["rescue_action"], meta


def assign_family(alpha_id: str, name: str) -> str:
    aid = alpha_id.lower()
    n = name.lower()
    if "btc_" in aid or "btc" in n:
        return "BTC_dependency"
    if "bb_position" in aid or "bb_" in n or "bollinger" in n:
        return "mean_reversion"
    if "ret_" in aid or "momentum" in aid:
        return "momentum"
    if "volume" in aid or "volume" in n:
        return "volume"
    if "breakout" in aid or "breakdown" in aid:
        return "breakout"
    if "trend" in aid or "ema" in aid:
        return "trend"
    if "reversal" in aid or "reversal" in n:
        return "mean_reversion"
    if "range_" in aid or "volatility" in aid or "vol" in aid:
        return "volatility"
    if "spread" in aid or "corwin" in aid or "microstructure" in aid:
        return "spread_microstructure"
    if "compression" in aid or "regime" in aid:
        return "regime"
    if "session" in aid:
        return "regime"
    if "discovery_pipeline" in aid or "truth_v6" in aid:
        return "discovery_pipeline"
    if "op005" in aid or "op_scalp" in aid:
        return "discovery_pipeline"
    if "scalp_1h_direction" in aid or "scalp_bb" in aid:
        return "XGBoost"
    if "xgb" in aid or "xgm" in aid:
        return "XGBoost"
    return "other"


def try_float(s: str):
    if not s or s.strip() == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def try_int(s: str):
    if not s or s.strip() == "":
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    inv_path = REPO_ROOT / "reports" / "ALPHA_INVENTORY_FULL.csv"
    out_dir = REPO_ROOT / "reports" / "v7_lite" / "alpha_rescue"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_inventory(inv_path)
    print(f"Loaded {len(rows)} alpha entries")

    # Classify each
    classified = []
    for row in rows:
        cls, action, meta = classify_alpha(row)
        classified.append(meta)

    # Count by classification
    counts = defaultdict(int)
    for m in classified:
        counts[m["classification"]] += 1

    print("\n=== CLASSIFICATION BREAKDOWN ===")
    for cls, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {cls:35s}: {cnt:3d}")

    # Output CSV
    csv_fields = [
        "alpha_id", "alpha_name", "source_file", "mode", "family_or_cluster",
        "status", "raw_net_R", "cost_adjusted_R", "estimated_cost_R",
        "trade_count", "winrate", "ic_score", "oos_R",
        "walk_forward_status", "holdout_status", "contaminated",
        "failure_reason", "primary_loss_bucket", "symbol_concentration",
        "regime_available", "session_available", "spread_available",
        "volume_available", "baseline_compared", "baseline_dominance_status",
        "classification", "rescue_action", "inversion_priority",
        "segment_rescue_priority", "cost_rescue_priority", "retest_priority",
        "recommended_next_experiment", "confidence", "notes",
    ]

    csv_path = out_dir / "ALPHA_RESCUE_MATRIX.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        for m in classified:
            writer.writerow(m)
    print(f"\nCSV written: {csv_path} ({len(classified)} rows)")

    # Output JSON
    json_path = out_dir / "ALPHA_RESCUE_MATRIX.json"
    with open(json_path, "w") as f:
        json.dump({
            "total_alphas": len(classified),
            "classification_counts": dict(counts),
            "alphas": classified,
        }, f, indent=2, default=str)
    print(f"JSON written: {json_path}")

    # Summary statistics
    pos_raw = sum(1 for m in classified if m["raw_net_R"] is not None and m["raw_net_R"] > 0)
    neg_raw = sum(1 for m in classified if m["raw_net_R"] is not None and m["raw_net_R"] < 0)
    zero_raw = sum(1 for m in classified if m["raw_net_R"] is not None and m["raw_net_R"] == 0)
    unknown_raw = sum(1 for m in classified if m["raw_net_R"] is None)

    print(f"\n=== RAW NET_R SUMMARY ===")
    print(f"  Positive:     {pos_raw:3d}")
    print(f"  Negative:     {neg_raw:3d}")
    print(f"  Zero:         {zero_raw:3d}")
    print(f"  Unknown:      {unknown_raw:3d}")

    # Inversion candidates
    invs = [m for m in classified if m["classification"] == "INVERSION_CANDIDATE"]
    print(f"\n=== INVERSION CANDIDATES ({len(invs)}) ===")
    for m in sorted(invs, key=lambda x: -(abs(x["raw_net_R"]) if x["raw_net_R"] else 0)):
        print(f"  {m['alpha_name']:45s} R={m['raw_net_R']:.4f}  trades={m['trade_count']}")

    # Segment rescue
    segs = [m for m in classified if m["classification"] == "SEGMENT_RESCUE_CANDIDATE"]
    print(f"\n=== SEGMENT RESCUE CANDIDATES ({len(segs)}) ===")
    for m in sorted(segs, key=lambda x: -(x["segment_rescue_priority"] or 0)):
        print(f"  {m['alpha_name']:45s} R={m['raw_net_R']:.4f}  priority={m['segment_rescue_priority']}")

    # Reject forever
    rejects = [m for m in classified if m["classification"] == "REJECT_FOREVER"]
    print(f"\n=== REJECT FOREVER ({len(rejects)}) ===")
    for m in rejects:
        print(f"  {m['alpha_name']:45s} R={m['raw_net_R']:.4f}")

    return classified


if __name__ == "__main__":
    main()
