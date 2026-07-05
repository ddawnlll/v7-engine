#!/usr/bin/env python3
"""Factor Direction Audit — sign/direction integrity check for all factor/horizon pairs.

Computes raw and inverted IC for every factor/horizon pair, checks sign
consistency between IC, IC_IR, top/bottom returns, and declared direction.
Produces ALPHA_DIRECTION_AUDIT.csv and ALPHA_LEADERBOARD_V2.csv.

Usage:
    PYTHONPATH=. .venv/bin/python3 scripts/factor_direction_audit.py
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_ROOT)

import numpy as np
import pandas as pd

from alphaforge.factors.evaluation import (
    compute_forward_returns,
    compute_cross_sectional_ic,
    compute_top_bottom_spread,
    compute_turnover,
)
from alphaforge.factors.factors import FACTOR_REGISTRY, compute_all_factors
from alphaforge.factors.loader import build_aligned_panel, load_1h_ohlcv

REPORTS_DIR = Path("reports/alphaforge/factor_sprint")


# ── HELPERS ──────────────────────────────────────────────────────────


def _compute_long_short_bucket_returns(
    factor_scores: pd.DataFrame,
    forward_returns: pd.DataFrame,
    top_pct: float = 0.20,
    bottom_pct: float = 0.20,
) -> tuple[float, float, float, float]:
    """Compute mean forward returns for long and short buckets.

    Long bucket = symbols with highest factor scores (top_pct).
    Short bucket = symbols with lowest factor scores (bottom_pct).

    Returns:
        (long_bucket_mean_return, short_bucket_mean_return,
         long_cumulative_return, short_cumulative_return)
    """
    common_idx = factor_scores.index.intersection(forward_returns.index)
    common_cols = factor_scores.columns.intersection(forward_returns.columns)

    if len(common_idx) == 0 or len(common_cols) < 5:
        return np.nan, np.nan, np.nan, np.nan

    fs = factor_scores.loc[common_idx, common_cols]
    fr = forward_returns.loc[common_idx, common_cols]

    ranks = fs.rank(axis=1, pct=True)
    n_sym = len(common_cols)
    n_top = max(1, int(n_sym * top_pct))
    n_bottom = max(1, int(n_sym * bottom_pct))

    top_threshold = 1.0 - (n_top / n_sym)
    bottom_threshold = n_bottom / n_sym

    top_mask = ranks >= top_threshold
    bottom_mask = ranks <= bottom_threshold

    top_mean = fr.where(top_mask).mean(axis=1)
    bottom_mean = fr.where(bottom_mask).mean(axis=1)

    return (
        float(top_mean.mean()),
        float(bottom_mean.mean()),
        float(top_mean.sum()),
        float(bottom_mean.sum()),
    )


def audit_factor_pair(
    factor_name: str,
    factor_scores: pd.DataFrame,
    forward_returns: dict[int, pd.DataFrame],
    declared_direction: str,
) -> list[dict]:
    """Audit a single factor across all horizons.

    Returns list of dicts with full sign/direction audit.
    """
    results = []

    for horizon, fwd_ret in forward_returns.items():
        # Raw IC (no direction adjustment)
        raw_ic_series = compute_cross_sectional_ic(factor_scores, fwd_ret)
        raw_spread_series = compute_top_bottom_spread(factor_scores, fwd_ret)
        turnover_series = compute_turnover(factor_scores)

        valid_ic = raw_ic_series.dropna()
        valid_spread = raw_spread_series.dropna()
        valid_turnover = turnover_series.dropna()

        n_timestamps = len(valid_ic)
        n_symbols = len(factor_scores.columns)

        if n_timestamps == 0:
            results.append(_empty_audit_row(factor_name, horizon, declared_direction))
            continue

        raw_mean_ic = float(valid_ic.mean())
        raw_std_ic = float(valid_ic.std())
        raw_ic_ir = raw_mean_ic / raw_std_ic if raw_std_ic > 0 else 0.0

        # Inverted IC (flip sign)
        inv_mean_ic = -raw_mean_ic
        inv_ic_ir = -raw_ic_ir

        # Long/short bucket returns
        long_mean_ret, short_mean_ret, long_cum_ret, short_cum_ret = (
            _compute_long_short_bucket_returns(factor_scores, fwd_ret)
        )

        # Top-bottom raw (long bucket - short bucket)
        raw_tob = float(valid_spread.sum()) if len(valid_spread) > 0 else np.nan

        # Direction-adjusted top-bottom
        if declared_direction == "short":
            dir_adj_tob = -raw_tob
        else:
            dir_adj_tob = raw_tob

        # Net return (currently just direction-adjusted spread in V1 code)
        net_return = dir_adj_tob

        # Determine best orientation
        # "best" = which raw IC sign aligns with declared direction
        if declared_direction == "long":
            # For long: positive raw IC = correct direction
            raw_aligned = raw_mean_ic > 0
        elif declared_direction == "short":
            # For short: negative raw IC = correct direction (high score → low return)
            raw_aligned = raw_mean_ic < 0
        else:
            raw_aligned = abs(raw_mean_ic) > 0.001

        if raw_aligned:
            best_orientation = "raw"
            orientation_status = "ALIGNED"
        else:
            best_orientation = "inverted"
            orientation_status = "MISALIGNED"

        # Bug detection
        bug_notes = []

        # Bug 1: IC_IR sign mismatch between column and notes
        # In V1: ic_ir column is negated for short, but notes show raw ic_ir
        # Check if |ic_ir| in column != |raw_ic_ir| (should always match)
        # This is actually fine since the column negates for display.
        # The real bug is that notes field says "IC_IR=X" where X is the
        # RAW ic_ir (possibly negative), while column shows negated value.

        # Bug 2: top_bottom_net_return sign
        # For short factors: net = -gross, which looks like "negating" the return
        # This is direction-correct but confusing naming

        # Bug 3: direction mismatch not caught in pass/fail
        if declared_direction == "short" and raw_mean_ic > 0:
            bug_notes.append("short factor has positive raw IC — direction mismatch")
        elif declared_direction == "long" and raw_mean_ic < 0:
            bug_notes.append("long factor has negative raw IC — direction mismatch")

        # Bug 4: IC_IR sign inconsistency in V1 notes
        # The notes field in V1 shows raw ic_ir value which can be negative
        # while the ic_ir column shows the negated value for short factors
        if declared_direction == "short":
            bug_notes.append(
                f"V1 bug: ic_ir column={raw_ic_ir * -1:.4f} but notes showed ic_ir={raw_ic_ir:.4f}"
            )

        mean_turnover = float(valid_turnover.mean()) if len(valid_turnover) > 0 else np.nan

        results.append({
            "factor_name": factor_name,
            "horizon": horizon,
            "declared_direction": declared_direction,
            "raw_mean_rank_ic": round(raw_mean_ic, 6),
            "inverted_mean_rank_ic": round(inv_mean_ic, 6),
            "raw_ic_ir": round(raw_ic_ir, 4),
            "inverted_ic_ir": round(inv_ic_ir, 4),
            "long_bucket_return": round(long_cum_ret, 6),
            "short_bucket_return": round(short_cum_ret, 6),
            "top_bottom_raw": round(raw_tob, 6),
            "top_bottom_direction_adjusted": round(dir_adj_tob, 6),
            "top_bottom_net_after_cost": round(net_return, 6),
            "best_orientation": best_orientation,
            "orientation_status": orientation_status,
            "bug_status": "; ".join(bug_notes) if bug_notes else "CLEAN",
            "turnover": round(mean_turnover, 4),
            "n_timestamps": n_timestamps,
            "n_symbols": n_symbols,
            "start_ts": str(valid_ic.index[0]),
            "end_ts": str(valid_ic.index[-1]),
        })

    return results


def _empty_audit_row(
    factor_name: str, horizon: int, direction: str
) -> dict:
    return {
        "factor_name": factor_name,
        "horizon": horizon,
        "declared_direction": direction,
        "raw_mean_rank_ic": np.nan,
        "inverted_mean_rank_ic": np.nan,
        "raw_ic_ir": np.nan,
        "inverted_ic_ir": np.nan,
        "long_bucket_return": np.nan,
        "short_bucket_return": np.nan,
        "top_bottom_raw": np.nan,
        "top_bottom_direction_adjusted": np.nan,
        "top_bottom_net_after_cost": np.nan,
        "best_orientation": "unknown",
        "orientation_status": "NO_DATA",
        "bug_status": "no valid IC samples",
        "turnover": np.nan,
        "n_timestamps": 0,
        "n_symbols": len(FACTOR_REGISTRY),
        "start_ts": "",
        "end_ts": "",
    }


def build_v2_leaderboard(audit_rows: list[dict]) -> list[dict]:
    """Build corrected V2 leaderboard from audit data.

    Uses raw IC (not direction-negated) for IC columns.
    Uses direction-adjusted top-bottom for spread.
    Fixes IC_IR sign to match raw IC.
    """
    v2_rows = []
    for row in audit_rows:
        if row["n_timestamps"] == 0:
            continue

        raw_ic = row["raw_mean_rank_ic"]
        raw_ic_ir = row["raw_ic_ir"]
        direction = row["declared_direction"]

        # Determine display values — use orientation that matches declared direction
        if row["best_orientation"] == "raw":
            display_ic = raw_ic
            display_ic_ir = raw_ic_ir
        else:
            display_ic = row["inverted_mean_rank_ic"]
            display_ic_ir = row["inverted_ic_ir"]

        # Pass/fail logic (same thresholds as V1 but using corrected values)
        n_ts = row["n_timestamps"]
        n_sym = row["n_symbols"]

        abs_ic = abs(display_ic)
        abs_ic_ir = abs(display_ic_ir)

        if n_ts < 50:
            pf = "FAIL"
            notes = "insufficient sample"
        elif n_sym < 10:
            pf = "FAIL"
            notes = "too few symbols"
        elif not np.isfinite(display_ic):
            pf = "FAIL"
            notes = "non-finite IC"
        elif not np.isfinite(row["top_bottom_direction_adjusted"]):
            pf = "FAIL"
            notes = "non-finite spread"
        elif abs_ic > 0.02 and abs_ic_ir > 0.3:
            pf = "PASS"
            notes = f"strong signal, IC_IR={abs_ic_ir:.2f}"
        elif abs_ic > 0.01 and abs_ic_ir > 0.15:
            pf = "WATCH"
            notes = f"moderate signal, IC_IR={abs_ic_ir:.2f}"
        elif abs_ic < 0.005:
            pf = "FAIL"
            notes = "near-zero IC"
        else:
            pf = "WATCH"
            notes = f"weak signal, IC_IR={abs_ic_ir:.2f}"

        # Direction mismatch check
        if direction == "short" and raw_ic > 0 and pf == "PASS":
            pf = "WATCH"
            notes += " (direction mismatch)"
        elif direction == "long" and raw_ic < 0 and pf == "PASS":
            pf = "WATCH"
            notes += " (direction mismatch)"

        if row["orientation_status"] == "MISALIGNED":
            notes += f" [orientation flipped: {row['best_orientation']}]"

        v2_rows.append({
            "factor_name": row["factor_name"],
            "horizon": row["horizon"],
            "direction": direction,
            "mean_rank_ic": round(display_ic, 6),
            "median_rank_ic": np.nan,  # not computed in audit
            "ic_ir": round(display_ic_ir, 4),
            "top_bottom_gross_return": row["top_bottom_raw"],
            "top_bottom_net_return": row["top_bottom_direction_adjusted"],
            "turnover": row["turnover"],
            "n_timestamps": row["n_timestamps"],
            "n_symbols": row["n_symbols"],
            "start_ts": row["start_ts"],
            "end_ts": row["end_ts"],
            "pass_fail": pf,
            "notes": notes,
        })

    # Sort: PASS first, then WATCH, then FAIL; within each by |mean_rank_ic| desc
    sort_order = {"PASS": 0, "WATCH": 1, "FAIL": 2}
    df = pd.DataFrame(v2_rows)
    df["_sort_pf"] = df["pass_fail"].map(sort_order).fillna(3)
    df["_sort_ic"] = df["mean_rank_ic"].abs().fillna(0)
    df = df.sort_values(["_sort_pf", "_sort_ic"], ascending=[True, False])
    df = df.drop(columns=["_sort_pf", "_sort_ic"])
    df.insert(0, "rank", range(1, len(df) + 1))

    return df.to_dict("records")


# ── MAIN ─────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 70)
    print("FACTOR DIRECTION AUDIT — Sign/Direction Integrity Check")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 70)

    # ── STEP 1: Load data ──────────────────────────────────────────
    print("\n[1/4] Loading 1h OHLCV from data lake...")
    t0 = time.time()
    data_1h = load_1h_ohlcv()
    loaded = {s: df for s, df in data_1h.items() if not df.empty}
    print(f"  Loaded {len(loaded)}/{len(data_1h)} symbols in {time.time()-t0:.1f}s")

    if len(loaded) < 5:
        print("  FATAL: Fewer than 5 symbols loaded. Aborting.")
        sys.exit(1)

    # ── STEP 2: Build panels + compute factors + forward returns ────
    print("\n[2/4] Building panels, computing factors & forward returns...")
    t1 = time.time()
    panels_1h = build_aligned_panel(loaded)
    close = panels_1h.get("close")
    if close is None or close.empty:
        print("  FATAL: No close price panel. Aborting.")
        sys.exit(1)

    fwd_returns = compute_forward_returns(close, horizons=[1, 4, 12, 24])
    factor_scores = compute_all_factors(panels_1h)
    print(f"  {len(factor_scores)} factors, {len(fwd_returns)} horizons, {time.time()-t1:.1f}s")

    # ── STEP 3: Audit every factor/horizon pair ────────────────────
    print("\n[3/4] Running direction audit...")
    t2 = time.time()
    all_audit = []

    for factor_name, scores in factor_scores.items():
        if factor_name not in FACTOR_REGISTRY:
            continue
        direction, _ = FACTOR_REGISTRY[factor_name]
        audit_rows = audit_factor_pair(factor_name, scores, fwd_returns, direction)
        all_audit.extend(audit_rows)

        aligned = sum(1 for r in audit_rows if r["orientation_status"] == "ALIGNED")
        misaligned = sum(1 for r in audit_rows if r["orientation_status"] == "MISALIGNED")
        bugs = sum(1 for r in audit_rows if r["bug_status"] != "CLEAN")
        print(f"  {factor_name}: aligned={aligned} misaligned={misaligned} bugs={bugs}")

    print(f"\n  Total audit rows: {len(all_audit)} in {time.time()-t2:.1f}s")

    # ── STEP 4: Write outputs ──────────────────────────────────────
    print("\n[4/4] Writing outputs...")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # ALPHA_DIRECTION_AUDIT.csv
    audit_df = pd.DataFrame(all_audit)
    audit_path = REPORTS_DIR / "ALPHA_DIRECTION_AUDIT.csv"
    audit_df.to_csv(audit_path, index=False)
    print(f"  Wrote {audit_path}: {len(audit_df)} rows")

    # ALPHA_LEADERBOARD_V2.csv
    v2_rows = build_v2_leaderboard(all_audit)
    v2_df = pd.DataFrame(v2_rows)
    v2_path = REPORTS_DIR / "ALPHA_LEADERBOARD_V2.csv"
    v2_df.to_csv(v2_path, index=False)
    print(f"  Wrote {v2_path}: {len(v2_df)} rows")

    # ── SUMMARY ────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("DIRECTION AUDIT SUMMARY")
    print("=" * 70)

    n_total = len(all_audit)
    n_aligned = sum(1 for r in all_audit if r["orientation_status"] == "ALIGNED")
    n_misaligned = sum(1 for r in all_audit if r["orientation_status"] == "MISALIGNED")
    n_bugs = sum(1 for r in all_audit if r["bug_status"] != "CLEAN")

    print(f"  Total factor/horizon pairs: {n_total}")
    print(f"  Aligned with declared direction: {n_aligned}")
    print(f"  Misaligned: {n_misaligned}")
    print(f"  With V1 bugs noted: {n_bugs}")

    # Suspicious factors
    suspicious = [r for r in all_audit if r["orientation_status"] == "MISALIGNED"]
    if suspicious:
        print(f"\n  SUSPICIOUS (direction mismatch):")
        for r in suspicious:
            print(f"    {r['factor_name']} ({r['horizon']}h): "
                  f"declared={r['declared_direction']}, "
                  f"raw_ic={r['raw_mean_rank_ic']:.4f}, "
                  f"raw_ic_ir={r['raw_ic_ir']:.4f}")

    # V2 top 10
    pass_v2 = [r for r in v2_rows if r["pass_fail"] == "PASS"]
    watch_v2 = [r for r in v2_rows if r["pass_fail"] == "WATCH"]

    print(f"\n  V2 leaderboard: PASS={len(pass_v2)} WATCH={len(watch_v2)}")
    if pass_v2:
        print("\n  --- V2 PASS candidates ---")
        for r in pass_v2[:10]:
            print(f"    {r['factor_name']} ({r['horizon']}h): "
                  f"IC={r['mean_rank_ic']:.4f}, IC_IR={r['ic_ir']:.4f}, "
                  f"spread={r['top_bottom_net_return']:.4f}")

    if watch_v2:
        print("\n  --- V2 WATCH candidates (top 10) ---")
        for r in watch_v2[:10]:
            print(f"    {r['factor_name']} ({r['horizon']}h): "
                  f"IC={r['mean_rank_ic']:.4f}, IC_IR={r['ic_ir']:.4f}, "
                  f"spread={r['top_bottom_net_return']:.4f}")

    print(f"\nCompleted: {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
