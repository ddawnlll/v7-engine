#!/usr/bin/env python3
"""Factor Signal Events — generate neutral handoff file for central simulation.

Computes factor scores, identifies when scores enter top/bottom buckets,
applies cooldown, and writes FACTOR_SIGNAL_EVENTS.csv.

This file is an intent/event stream — it does NOT claim trade outcomes.
The central simulation engine consumes it to evaluate actual R.

Usage:
    PYTHONPATH=. .venv/bin/python3 scripts/factor_signal_events.py
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_ROOT)

import numpy as np
import pandas as pd

from alphaforge.factors.factors import FACTOR_REGISTRY, compute_all_factors
from alphaforge.factors.loader import build_aligned_panel, load_1h_ohlcv

REPORTS_DIR = Path("reports/alphaforge/factor_sprint")


# ── EVENT CONFIGS ────────────────────────────────────────────────────


@dataclass(frozen=True)
class EventConfig:
    name: str
    bucket_pct: float  # top/bottom percentile threshold
    cooldown_bars: int
    max_hold_bars: int
    stop_profile: str
    target_profile: str


EVENT_CONFIGS = {
    "EVENT_SCALP_1H_FAST": EventConfig(
        name="EVENT_SCALP_1H_FAST",
        bucket_pct=0.20,
        cooldown_bars=4,
        max_hold_bars=4,
        stop_profile="ATR_1.5",
        target_profile="ATR_2.0",
    ),
    "EVENT_SCALP_1H_SLOW": EventConfig(
        name="EVENT_SCALP_1H_SLOW",
        bucket_pct=0.20,
        cooldown_bars=8,
        max_hold_bars=8,
        stop_profile="ATR_1.5",
        target_profile="ATR_2.0",
    ),
    "EVENT_SWING_PROXY_1H": EventConfig(
        name="EVENT_SWING_PROXY_1H",
        bucket_pct=0.20,
        cooldown_bars=24,
        max_hold_bars=24,
        stop_profile="ATR_2.0",
        target_profile="ATR_3.0",
    ),
}


# ── SIGNAL GENERATION ────────────────────────────────────────────────


def generate_signal_events(
    factor_scores: pd.DataFrame,
    factor_name: str,
    direction: str,
    event_config: EventConfig,
    close: pd.DataFrame,
) -> list[dict]:
    """Generate sparse signal events for a factor and event config.

    Only emits events when a symbol's score newly enters the top/bottom bucket.
    Applies cooldown to prevent duplicate signals.

    Returns list of event dicts.
    """
    bucket_pct = event_config.bucket_pct
    cooldown = event_config.cooldown_bars

    events: list[dict] = []

    # Track last signal timestamp per symbol
    last_signal_idx: dict[str, int] = {}

    timestamps = factor_scores.index
    symbols = factor_scores.columns

    for i, ts in enumerate(timestamps):
        scores = factor_scores.loc[ts].dropna()
        if len(scores) < 5:
            continue

        # Compute thresholds
        high_thresh = scores.quantile(1.0 - bucket_pct)
        low_thresh = scores.quantile(bucket_pct)

        for sym in symbols:
            if sym not in scores.index:
                continue

            score = scores[sym]

            # Check cooldown
            if sym in last_signal_idx:
                if i - last_signal_idx[sym] < cooldown:
                    continue

            # Determine side based on score and direction
            side = None
            action_hint = "NO_TRADE"
            confidence = 0.0

            if direction == "long":
                if score >= high_thresh:
                    side = "LONG"
                    action_hint = "LONG_NOW"
                    confidence = min(1.0, (score - high_thresh) / (scores.max() - high_thresh + 1e-10))
                elif score <= low_thresh:
                    side = "SHORT"
                    action_hint = "SHORT_NOW"
                    confidence = min(1.0, (low_thresh - score) / (low_thresh - scores.min() + 1e-10))
            elif direction == "short":
                if score <= low_thresh:
                    side = "LONG"
                    action_hint = "LONG_NOW"
                    confidence = min(1.0, (low_thresh - score) / (low_thresh - scores.min() + 1e-10))
                elif score >= high_thresh:
                    side = "SHORT"
                    action_hint = "SHORT_NOW"
                    confidence = min(1.0, (score - high_thresh) / (scores.max() - high_thresh + 1e-10))
            else:  # agnostic
                if score >= high_thresh:
                    side = "LONG"
                    action_hint = "LONG_NOW"
                    confidence = min(1.0, (score - high_thresh) / (scores.max() - high_thresh + 1e-10))
                elif score <= low_thresh:
                    side = "SHORT"
                    action_hint = "SHORT_NOW"
                    confidence = min(1.0, (low_thresh - score) / (low_thresh - scores.min() + 1e-10))

            if side is None or action_hint == "NO_TRADE":
                continue

            # Compute rank_pct
            rank_pct = float(scores.rank(pct=True).get(sym, 0.5))

            # Get price for context
            current_close = close[sym].get(ts, np.nan) if sym in close.columns else np.nan

            events.append({
                "timestamp": str(ts),
                "symbol": sym,
                "alpha_name": factor_name,
                "timeframe": "1h",
                "horizon": event_config.max_hold_bars,
                "score": round(float(score), 6),
                "rank_pct": round(rank_pct, 4),
                "orientation_used": direction,
                "action_hint": action_hint,
                "side": side,
                "confidence": round(confidence, 4),
                "entry_reason": f"factor_{factor_name}_bucket_entry",
                "stop_profile": event_config.stop_profile,
                "target_profile": event_config.target_profile,
                "max_hold_bars": event_config.max_hold_bars,
                "entry_price": round(float(current_close), 4) if np.isfinite(current_close) else np.nan,
            })

            last_signal_idx[sym] = i

    return events


# ── MAIN ─────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 70)
    print("FACTOR SIGNAL EVENTS — Neutral Handoff for Central Simulation")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 70)

    # ── STEP 1: Load data ──────────────────────────────────────────
    print("\n[1/3] Loading 1h OHLCV from data lake...")
    t0 = time.time()
    data_1h = load_1h_ohlcv()
    loaded = {s: df for s, df in data_1h.items() if not df.empty}
    print(f"  Loaded {len(loaded)}/{len(data_1h)} symbols in {time.time()-t0:.1f}s")

    if len(loaded) < 5:
        print("  FATAL: Fewer than 5 symbols loaded. Aborting.")
        sys.exit(1)

    # ── STEP 2: Compute factors ────────────────────────────────────
    print("\n[2/3] Computing factors...")
    t1 = time.time()
    panels_1h = build_aligned_panel(loaded)
    close = panels_1h.get("close")
    factor_scores = compute_all_factors(panels_1h)
    print(f"  {len(factor_scores)} factors in {time.time()-t1:.1f}s")

    # ── STEP 3: Generate signal events ─────────────────────────────
    print("\n[3/3] Generating signal events...")
    t2 = time.time()
    all_events = []

    for config_name, config in EVENT_CONFIGS.items():
        config_events = []
        for factor_name, scores in factor_scores.items():
            if factor_name not in FACTOR_REGISTRY:
                continue
            direction, _ = FACTOR_REGISTRY[factor_name]

            # Skip agnostic factors for event generation
            if direction == "agnostic":
                continue

            events = generate_signal_events(scores, factor_name, direction, config, close)
            config_events.extend(events)

        print(f"  {config_name}: {len(config_events)} events")
        all_events.extend(config_events)

    print(f"\n  Total events: {len(all_events)} in {time.time()-t2:.1f}s")

    # ── WRITE OUTPUT ───────────────────────────────────────────────
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if all_events:
        events_df = pd.DataFrame(all_events)
        events_path = REPORTS_DIR / "FACTOR_SIGNAL_EVENTS.csv"
        events_df.to_csv(events_path, index=False)
        print(f"\n  Wrote {events_path}: {len(events_df)} rows")

        # Summary stats
        print(f"\n  Event distribution:")
        for config_name in EVENT_CONFIGS:
            n = sum(1 for e in all_events if e["max_hold_bars"] == EVENT_CONFIGS[config_name].max_hold_bars)
            print(f"    {config_name}: {n} events")

        print(f"\n  Alpha representation:")
        alpha_counts = {}
        for e in all_events:
            alpha_counts[e["alpha_name"]] = alpha_counts.get(e["alpha_name"], 0) + 1
        for name, count in sorted(alpha_counts.items(), key=lambda x: -x[1]):
            print(f"    {name}: {count} events")

        print(f"\n  Side distribution:")
        long_count = sum(1 for e in all_events if e["side"] == "LONG")
        short_count = sum(1 for e in all_events if e["side"] == "SHORT")
        print(f"    LONG: {long_count}, SHORT: {short_count}")
    else:
        print("\n  WARNING: No events generated!")

    print(f"\nCompleted: {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
