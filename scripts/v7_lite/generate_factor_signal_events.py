"""
P0.2 — Factor Signal Events Generator

Generates normalized signal events from factor sprint leaderboard data and
panel cache OHLCV data. These events allow factor/proxy alphas to enter
central simulation.

Usage:
    PYTHONPATH=alphaforge/src:v7/src:. python3 scripts/v7_lite/generate_factor_signal_events.py

Output:
    reports/v7_lite/p0_primitives/factor_events/FACTOR_SIGNAL_EVENTS.csv
    reports/v7_lite/p0_primitives/factor_events/FACTOR_SIGNAL_EVENTS_SCHEMA.md
    reports/v7_lite/p0_primitives/factor_events/FACTOR_SIGNAL_EVENTS_GENERATION_REPORT.md
"""

from __future__ import annotations

import csv
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "alphaforge/src"))
sys.path.insert(0, str(REPO_ROOT / "v7/src"))
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "reports/v7_lite/p0_primitives/factor_events"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(OUTPUT_DIR / "factor_signal_events.log", mode="w"),
    ],
)
logger = logging.getLogger("factor_events")


# ── Factor definitions from leaderboard analysis ─────────────────────────
# These are the factor names from ALPHA_LEADERBOARD_V2.csv with their
# entry conditions derived from the factor sprint results.

FACTOR_DEFINITIONS = [
    {
        "factor_name": "breakdown_n_low",
        "feature_name": "lowest_N",
        "direction": "short",
        "timeframe": "24h",
        "horizon": 24,
        "entry_condition": "lowest_N_rank < 0.10",
        "threshold_percentile": 0.10,
        "description": "N-period low breakdown — short when price breaks below N-period low",
    },
    {
        "factor_name": "volume_zscore",
        "feature_name": "volume_ratio_N",
        "direction": "long",
        "timeframe": "24h",
        "horizon": 24,
        "entry_condition": "volume_ratio_N > 2.0",
        "threshold_percentile": 0.90,
        "description": "Volume Z-score — long on unusual volume expansion",
    },
    {
        "factor_name": "ret_24h_rank",
        "feature_name": "momentum_N",
        "direction": "long",
        "timeframe": "24h",
        "horizon": 24,
        "entry_condition": "momentum_N_rank > 0.80",
        "threshold_percentile": 0.80,
        "description": "24h return rank — long on strong momentum",
    },
    {
        "factor_name": "ret_4h_rank",
        "feature_name": "momentum_N",
        "direction": "long",
        "timeframe": "1h",
        "horizon": 4,
        "entry_condition": "momentum_N_rank > 0.80",
        "threshold_percentile": 0.80,
        "description": "4h return rank — long on short-term momentum",
    },
    {
        "factor_name": "reversal_4h_zscore",
        "feature_name": "return_zscore_N",
        "direction": "long",
        "timeframe": "1h",
        "horizon": 4,
        "entry_condition": "return_zscore_N < -1.5",
        "threshold_percentile": 0.05,
        "description": "4h reversal Z-score — long on mean-reversion oversold",
    },
    {
        "factor_name": "trend_pullback_ema",
        "feature_name": "bb_position",
        "direction": "long",
        "timeframe": "24h",
        "horizon": 24,
        "entry_condition": "bb_position < 0.20",
        "threshold_percentile": 0.20,
        "description": "Trend pullback to EMA — long when price pulls back in uptrend",
    },
    {
        "factor_name": "ret_12h_rank",
        "feature_name": "momentum_N",
        "direction": "long",
        "timeframe": "12h",
        "horizon": 12,
        "entry_condition": "momentum_N_rank > 0.80",
        "threshold_percentile": 0.80,
        "description": "12h return rank — medium-term momentum",
    },
    {
        "factor_name": "ret_1h_rank",
        "feature_name": "log_return_1",
        "direction": "long",
        "timeframe": "1h",
        "horizon": 1,
        "entry_condition": "log_return_1_rank > 0.80",
        "threshold_percentile": 0.80,
        "description": "1h return rank — short-term momentum",
    },
    {
        "factor_name": "reversal_1h_zscore",
        "feature_name": "return_zscore_N",
        "direction": "long",
        "timeframe": "1h",
        "horizon": 1,
        "entry_condition": "return_zscore_N < -1.5",
        "threshold_percentile": 0.05,
        "description": "1h reversal Z-score — short-term mean reversion",
    },
    {
        "factor_name": "range_zscore",
        "feature_name": "high_low_range_N",
        "direction": "long",
        "timeframe": "24h",
        "horizon": 24,
        "entry_condition": "high_low_range_N > 1.5",
        "threshold_percentile": 0.85,
        "description": "Range Z-score — long on expanding range",
    },
    {
        "factor_name": "compression_breakout_regime",
        "feature_name": "bb_width",
        "direction": "long",
        "timeframe": "24h",
        "horizon": 24,
        "entry_condition": "bb_width < 0.10",
        "threshold_percentile": 0.10,
        "description": "Compression breakout — long when BB width compresses",
    },
    {
        "factor_name": "spread_contraction_signal",
        "feature_name": "spread_pct_N",
        "direction": "long",
        "timeframe": "24h",
        "horizon": 24,
        "entry_condition": "spread_pct_N < 0.05",
        "threshold_percentile": 0.10,
        "description": "Spread contraction — long on tightening spreads",
    },
]


def load_panel_data() -> dict[str, pd.DataFrame]:
    """Load OHLCV panels from factor_sprint cache."""
    cache_path = REPO_ROOT / "cache/factor_sprint"
    close_panel = pd.read_parquet(cache_path / "panel_d8c8d55e3b8b107e_close.parquet")
    high_panel = pd.read_parquet(cache_path / "panel_d8c8d55e3b8b107e_high.parquet")
    low_panel = pd.read_parquet(cache_path / "panel_d8c8d55e3b8b107e_low.parquet")
    open_panel = pd.read_parquet(cache_path / "panel_d8c8d55e3b8b107e_open.parquet")
    volume_panel = pd.read_parquet(cache_path / "panel_d8c8d55e3b8b107e_volume.parquet")

    symbols = [c for c in close_panel.columns if c != "__index_level_0__"]
    # Use only the 4 main symbols for speed
    main_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
    symbols = [s for s in main_symbols if s in symbols]
    panels = {}
    for sym in symbols:
        panels[sym] = pd.DataFrame({
            "open": open_panel[sym] if sym in open_panel.columns else np.nan,
            "high": high_panel[sym] if sym in high_panel.columns else np.nan,
            "low": low_panel[sym] if sym in low_panel.columns else np.nan,
            "close": close_panel[sym] if sym in close_panel.columns else np.nan,
            "volume": volume_panel[sym] if sym in volume_panel.columns else np.nan,
        }, index=close_panel.index)

    logger.info("Loaded %d symbols, %d bars each", len(symbols), len(close_panel))
    return panels


def compute_factor_signals(
    panels: dict[str, pd.DataFrame],
    factor_def: dict,
) -> list[dict]:
    """Generate signal events for a single factor across all symbols.

    Uses simple threshold-based entry conditions on computed features.
    """
    events = []
    feature_name = factor_def["feature_name"]
    direction = factor_def["direction"]
    threshold_pct = factor_def["threshold_percentile"]
    factor_name = factor_def["factor_name"]
    timeframe = factor_def["timeframe"]
    entry_condition = factor_def["entry_condition"]

    for sym, df in panels.items():
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # Compute feature values based on factor type
        if feature_name == "bb_position":
            # Bollinger Band position: (close - SMA20) / (2 * std20)
            sma20 = close.rolling(20).mean()
            std20 = close.rolling(20).std()
            feature_vals = (close - sma20) / (2 * std20 + 1e-10)
        elif feature_name == "bb_width":
            sma20 = close.rolling(20).mean()
            std20 = close.rolling(20).std()
            feature_vals = (4 * std20) / (sma20 + 1e-10)
        elif feature_name == "momentum_N":
            horizon = factor_def.get("horizon", 24)
            feature_vals = close.pct_change(horizon)
        elif feature_name == "log_return_1":
            feature_vals = np.log(close / close.shift(1))
        elif feature_name == "return_zscore_N":
            horizon = factor_def.get("horizon", 24)
            ret = close.pct_change(horizon)
            feature_vals = (ret - ret.rolling(100).mean()) / (ret.rolling(100).std() + 1e-10)
        elif feature_name == "volume_ratio_N":
            horizon = factor_def.get("horizon", 24)
            feature_vals = volume / (volume.rolling(horizon).mean() + 1e-10)
        elif feature_name == "high_low_range_N":
            horizon = factor_def.get("horizon", 24)
            daily_range = (high - low) / (close + 1e-10)
            feature_vals = daily_range.rolling(horizon).mean()
        elif feature_name == "lowest_N":
            horizon = factor_def.get("horizon", 24)
            rolling_low = low.rolling(horizon).min()
            feature_vals = (close - rolling_low) / (rolling_low + 1e-10)
        elif feature_name == "spread_pct_N":
            feature_vals = (high - low) / (close + 1e-10)
        else:
            # Generic fallback: use close returns
            feature_vals = close.pct_change(24)

        # Compute cross-sectional rank at each timestamp
        feature_df = pd.DataFrame({sym: feature_vals for sym, df2 in panels.items()
                                    if sym == sym})
        # For each timestamp, compute rank among all symbols
        # Simple approach: use percentile within the symbol's own history
        feature_clean = feature_vals.dropna()
        if len(feature_clean) < 100:
            continue

        # Apply threshold to find entry signals
        if direction == "long" and "rank" in entry_condition:
            # Long on high rank values
            threshold_val = feature_clean.quantile(threshold_pct)
            signal_mask = feature_vals > threshold_val
        elif direction == "short" and "rank" in entry_condition:
            # Short on low rank values
            threshold_val = feature_clean.quantile(1 - threshold_pct)
            signal_mask = feature_vals < threshold_val
        elif " < " in entry_condition:
            # Low threshold condition
            threshold_val = feature_clean.quantile(threshold_pct)
            signal_mask = feature_vals < threshold_val
        elif " > " in entry_condition:
            # High threshold condition
            threshold_val = feature_clean.quantile(threshold_pct)
            signal_mask = feature_vals > threshold_val
        else:
            threshold_val = feature_clean.quantile(threshold_pct)
            signal_mask = feature_vals > threshold_val

        # Sample entries — take every Nth signal to avoid overcrowding
        signal_timestamps = feature_vals.index[signal_mask].tolist()

        # Thin out signals: minimum 4 bars between entries for same factor/symbol
        min_gap = 12
        thinned = []
        last_ts = None
        for ts in signal_timestamps:
            if last_ts is None:
                thinned.append(ts)
                last_ts = ts
                continue
            if (ts - last_ts).total_seconds() / 3600 >= min_gap:
                thinned.append(ts)
                last_ts = ts

        for i, ts in enumerate(thinned):
            entry_price = float(close.loc[ts]) if ts in close.index else 0.0
            atr_val = float((high - low).rolling(14).mean().loc[ts]) if ts in close.index else entry_price * 0.02

            events.append({
                "event_id": f"fs_{factor_name}_{sym}_{ts.strftime('%Y%m%d%H%M')}",
                "alpha_name": f"fs_{factor_name}_{timeframe}_{direction}",
                "factor_name": factor_name,
                "symbol": sym,
                "timestamp": str(ts),
                "timeframe": timeframe,
                "direction": direction.upper(),
                "signal_value": round(float(feature_vals.loc[ts]), 6) if ts in feature_vals.index else 0.0,
                "entry_condition": entry_condition,
                "entry_price": round(entry_price, 6),
                "atr": round(atr_val, 6),
                "source_file": "generate_factor_signal_events.py",
                "source_row_id": f"{sym}_{ts.strftime('%Y%m%d')}",
            })

    return events


def main():
    """Generate factor signal events from panel cache data."""
    t0 = time.time()
    logger.info("P0.2 — Factor Signal Events Generator")

    # Load panel data
    logger.info("[1/4] Loading panel data...")
    panels = load_panel_data()

    # Generate events for each factor
    logger.info("[2/4] Generating signal events for %d factors...", len(FACTOR_DEFINITIONS))
    all_events = []
    factor_counts = {}
    for fdef in FACTOR_DEFINITIONS:
        events = compute_factor_signals(panels, fdef)
        all_events.extend(events)
        factor_counts[fdef["factor_name"]] = len(events)
        logger.info("  %s: %d events", fdef["factor_name"], len(events))

    logger.info("Total events: %d", len(all_events))

    if not all_events:
        logger.error("No events generated")
        return None

    # Write CSV
    logger.info("[3/4] Writing FACTOR_SIGNAL_EVENTS.csv...")
    csv_path = OUTPUT_DIR / "FACTOR_SIGNAL_EVENTS.csv"
    fieldnames = [
        "event_id", "alpha_name", "factor_name", "symbol", "timestamp",
        "timeframe", "direction", "signal_value", "entry_condition",
        "entry_price", "atr", "source_file", "source_row_id",
    ]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for event in all_events:
            writer.writerow({k: event.get(k, "") for k in fieldnames})

    logger.info("  Wrote %d events to %s", len(all_events), csv_path)

    # Write schema doc
    logger.info("[4/4] Writing schema and report docs...")
    schema_path = OUTPUT_DIR / "FACTOR_SIGNAL_EVENTS_SCHEMA.md"
    with open(schema_path, "w") as f:
        f.write("# FACTOR_SIGNAL_EVENTS Schema\n\n")
        f.write("**Generated:** " + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n\n")
        f.write("## Required Columns\n\n")
        f.write("| Column | Type | Description |\n")
        f.write("|--------|------|-------------|\n")
        f.write("| event_id | string | Unique event identifier |\n")
        f.write("| alpha_name | string | Alpha identifier (factor + config + side) |\n")
        f.write("| factor_name | string | Factor name from leaderboard |\n")
        f.write("| symbol | string | Trading pair (e.g. BTCUSDT) |\n")
        f.write("| timestamp | string | ISO timestamp of signal |\n")
        f.write("| timeframe | string | Signal timeframe (1h, 4h, 12h, 24h) |\n")
        f.write("| direction | string | LONG or SHORT |\n")
        f.write("| signal_value | float | Computed factor value at signal time |\n")
        f.write("| entry_condition | string | Threshold condition that triggered signal |\n")
        f.write("| entry_price | float | Close price at signal time |\n")
        f.write("| atr | float | 14-bar ATR at signal time |\n")
        f.write("| source_file | string | Generator script name |\n")
        f.write("| source_row_id | string | Source identifier for traceability |\n\n")
        f.write("## Factor Sources\n\n")
        for fdef in FACTOR_DEFINITIONS:
            f.write(f"- **{fdef['factor_name']}** ({fdef['direction']}, {fdef['timeframe']}): {fdef['description']}\n")

    # Write generation report
    report_path = OUTPUT_DIR / "FACTOR_SIGNAL_EVENTS_GENERATION_REPORT.md"
    sym_counts = {}
    for ev in all_events:
        sym_counts[ev["symbol"]] = sym_counts.get(ev["symbol"], 0) + 1

    with open(report_path, "w") as f:
        f.write("# Factor Signal Events Generation Report\n\n")
        f.write(f"**Generated:** {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n\n")
        f.write("## Summary\n\n")
        f.write(f"- Total events: {len(all_events)}\n")
        f.write(f"- Factors: {len(FACTOR_DEFINITIONS)}\n")
        f.write(f"- Symbols: {len(panels)}\n")
        f.write(f"- Elapsed: {time.time() - t0:.1f}s\n\n")
        f.write("## Events per Factor\n\n")
        for fname, cnt in sorted(factor_counts.items(), key=lambda x: -x[1]):
            f.write(f"- {fname}: {cnt}\n")
        f.write("\n## Events per Symbol\n\n")
        for sym, cnt in sorted(sym_counts.items(), key=lambda x: -x[1]):
            f.write(f"- {sym}: {cnt}\n")
        f.write("\n## Direction Breakdown\n\n")
        long_count = sum(1 for e in all_events if e["direction"] == "LONG")
        short_count = sum(1 for e in all_events if e["direction"] == "SHORT")
        f.write(f"- LONG: {long_count}\n")
        f.write(f"- SHORT: {short_count}\n\n")
        f.write("## Usage\n\n")
        f.write("Feed this CSV into the central simulation bridge:\n\n")
        f.write("```bash\n")
        f.write("PYTHONPATH=simulation/src:alphaforge/src:v7/src:. python3 experiments/v7_lite/central_sim_bridge_p0.py \\\n")
        f.write(f"    --events {csv_path} \\\n")
        f.write("    --panel-cache cache/factor_sprint/ \\\n")
        f.write("    --output reports/v7_lite/p0_primitives/central_bridge/central_sim_bridge_results.csv\n")
        f.write("```\n")

    # Summary
    elapsed = time.time() - t0
    summary = {
        "run_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_events": len(all_events),
        "factor_count": len(FACTOR_DEFINITIONS),
        "symbol_count": len(panels),
        "factor_counts": factor_counts,
        "symbol_counts": sym_counts,
        "elapsed_seconds": round(elapsed, 2),
        "csv_path": str(csv_path),
    }

    summary_path = OUTPUT_DIR / "factor_events_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    logger.info("=" * 60)
    logger.info("P0.2 Factor Signal Events Generator COMPLETE")
    logger.info("  Total events: %d", len(all_events))
    logger.info("  Factors: %d", len(FACTOR_DEFINITIONS))
    logger.info("  CSV: %s", csv_path)
    logger.info("=" * 60)

    return summary


if __name__ == "__main__":
    try:
        result = main()
        if result is None:
            logger.error("FAILED: No result produced")
            sys.exit(1)
    except Exception as e:
        logger.exception("FAILED_WITH_TRACEBACK")
        sys.exit(1)
