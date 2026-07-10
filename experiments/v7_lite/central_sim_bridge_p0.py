"""
Central Simulation Bridge P0 — converts proxy factor signals → central simulation results.

This adapter bridges factor scores from the factor sprint into the `simulation/engine/engine.py`
central simulation engine (the economic truth authority). It replaces the standalone
fast_simulator which had its own cost model and exit logic.

Usage:
    python experiments/v7_lite/central_sim_bridge_p0.py \\
        --events <FACTOR_SIGNAL_EVENTS.csv> \\
        --panel-cache <cache/factor_sprint/> \\
        --output <CENTRAL_SIM_RESULTS.csv> \\
        --mode SCALP

Requires:
    - Pandas, NumPy (available in environment)
    - simulation/ (all imports local)
"""

from __future__ import annotations

import argparse
import csv
import sys
import json
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Simulation engine imports (all local to this repo)
# ---------------------------------------------------------------------------
from simulation.adapters.training_adapter import TrainingAdapter
from simulation.contracts.models import (
    Candle,
    FuturePath,
    SimulationInput,
    SimulationProfile,
    TradingMode,
)
from simulation.engine.costs import total_cost_r
from simulation.authority import get_cost_constants

_COST_AUTH = get_cost_constants()
TAKER_FEE_BPS = _COST_AUTH["taker_fee_bps"]
SLIPPAGE_BPS = _COST_AUTH["slippage_bps"]
ROUND_TRIP_BPS = _COST_AUTH["total_round_trip_cost_bps"]


# ---------------------------------------------------------------------------
# Default SCALP simulation profile
# ---------------------------------------------------------------------------
def default_profile(mode: str = "SCALP") -> SimulationProfile:
    """Return a default SimulationProfile for the given trading mode.

    Uses conservative (taker) execution by default. For maker scenarios,
    set execution_mode='MAKER' on the returned profile.
    """
    return SimulationProfile(
        profile_version="p0-bridge-1.0.0",
        mode=TradingMode(mode),
        primary_interval="1h",
        max_holding_bars=30,
        stop_multiplier=2.0,
        target_multiplier=2.5,
        ambiguity_margin_r=0.20,
        min_action_edge_r=0.35,
        no_trade_default=False,
        stop_method="atr_wide",
        target_method="atr_wide",
        mae_penalty_weight=1.0,
        cost_penalty_weight=1.0,
        time_penalty_weight=0.3,
        execution_mode="TAKER",  # default conservative
        maker_fill_probability=0.7,
    )


# ---------------------------------------------------------------------------
# Signal events format
# ---------------------------------------------------------------------------
SIGNAL_EVENTS_REQUIRED_COLS = [
    "timestamp",
    "symbol",
    "factor_name",
    "score",
    "direction",  # 'long' or 'short'
    "entry_price",
    "atr",
]

SIGNAL_EVENTS_OPTIONAL_COLS = [
    "stop_multiplier",
    "target_multiplier",
    "max_holding_bars",
    "execution_mode",  # TAKER / MAKER / HYBRID
]


def load_signal_events(path: str) -> pd.DataFrame:
    """Load and validate FACTOR_SIGNAL_EVENTS.csv.

    Expected columns:
        timestamp, symbol, factor_name, score, direction,
        entry_price, atr

    Returns:
        Cleaned DataFrame with required columns present.
    """
    df = pd.read_csv(path)
    missing = [c for c in SIGNAL_EVENTS_REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Missing required columns: {missing}. "
            f"Expected: {SIGNAL_EVENTS_REQUIRED_COLS}"
        )
    # Ensure numeric types
    for col in ["entry_price", "atr", "score"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    # Drop rows with missing critical fields
    before = len(df)
    df = df.dropna(subset=["entry_price", "atr"])
    after = len(df)
    if after < before:
        print(f"[bridge] Dropped {before - after} rows with missing price/ATR")
    return df


# ---------------------------------------------------------------------------
# OHLCV panel loader
# ---------------------------------------------------------------------------
def load_ohlcv_panels(panel_cache_dir: str) -> dict[str, pd.DataFrame]:
    """Load OHLCV panels from factor_sprint cache.

    The cache stores per-field parquet files like:
        panel_<hash>_close.parquet
        panel_<hash>_high.parquet
        panel_<hash>_low.parquet
        panel_<hash>_open.parquet
        panel_<hash>_volume.parquet

    Returns:
        dict mapping symbol -> DataFrame with columns [open, high, low, close, volume]
    """
    cache_path = Path(panel_cache_dir)
    if not cache_path.exists():
        raise FileNotFoundError(f"Panel cache directory not found: {panel_cache_dir}")

    # Find all parquet files and identify the hash prefix
    parquet_files = list(cache_path.glob("panel_*_close.parquet"))
    if not parquet_files:
        raise FileNotFoundError(
            f"No panel_*_close.parquet found in {panel_cache_dir}. "
            "Run factor_sprint.py first to generate cache."
        )

    # Load close panel to get symbol list
    close_panel = pd.read_parquet(parquet_files[0])
    symbols = [c for c in close_panel.columns if c != "__index_level_0__"]

    # Load all field panels
    field_map = {}
    for field in ["close", "high", "low", "open", "volume"]:
        fp = list(cache_path.glob(f"panel_*_{field}.parquet"))
        if fp:
            field_map[field] = pd.read_parquet(fp[0])

    # Build per-symbol DataFrames
    panels = {}
    for sym in symbols:
        sym_data = {}
        for field, panel in field_map.items():
            if sym in panel.columns:
                sym_data[field] = panel[sym].values
        if sym_data:
            idx = field_map.get("close", list(field_map.values())[0]).index
            panels[sym] = pd.DataFrame(sym_data, index=idx)
            # Ensure required columns exist
            for c in ["open", "high", "low", "close", "volume"]:
                if c not in panels[sym].columns:
                    panels[sym][c] = np.nan

    print(f"[bridge] Loaded {len(panels)} symbols from panel cache")
    return panels


# ---------------------------------------------------------------------------
# FuturePath builder
# ---------------------------------------------------------------------------
def build_future_path(
    ohlcv: pd.DataFrame,
    entry_idx: int,
    max_bars: int = 30,
) -> Optional[FuturePath]:
    """Build FuturePath from OHLCV data after the entry index.

    Args:
        ohlcv: DataFrame with [open, high, low, close, volume] columns.
        entry_idx: Row index of the entry decision.
        max_bars: Maximum number of forward-looking candles.

    Returns:
        FuturePath with candles after entry, or None if insufficient data.
    """
    if entry_idx < 0 or entry_idx >= len(ohlcv) - 1:
        return None

    future = ohlcv.iloc[entry_idx + 1 : entry_idx + 1 + max_bars]
    if len(future) == 0:
        return None

    candles = []
    for _, row in future.iterrows():
        candle = Candle(
            open=float(row.get("open", row.get("close", 0.0))),
            high=float(row.get("high", row.get("close", 0.0))),
            low=float(row.get("low", row.get("close", 0.0))),
            close=float(row.get("close", 0.0)),
            volume=float(row.get("volume", 0.0)),
        )
        candles.append(candle)

    return FuturePath(
        candles=candles,
        completeness_status="COMPLETE",
        expected_bars=len(candles),
    )


# ---------------------------------------------------------------------------
# Signal event to SimulationInput converter
# ---------------------------------------------------------------------------
def signal_event_to_sim_input(
    event: dict,
    ohlcv_panels: dict[str, pd.DataFrame],
    profile: SimulationProfile,
    atr_panel: Optional[pd.Series] = None,
) -> Optional[SimulationInput]:
    """Convert a single signal event to a SimulationInput.

    Args:
        event: Row from signal events DataFrame.
        ohlcv_panels: Per-symbol OHLCV DataFrames.
        profile: SimulationProfile for the simulation.
        atr_panel: Optional pre-computed ATR series per symbol.

    Returns:
        SimulationInput ready for TrainingAdapter, or None if conversion fails.
    """
    symbol = str(event.get("symbol", ""))
    entry_price = float(event.get("entry_price", 0.0))
    atr = float(event.get("atr", 0.0))
    timestamp = str(event.get("timestamp", ""))

    if symbol not in ohlcv_panels:
        print(f"[bridge] WARNING: symbol '{symbol}' not in OHLCV panels — skipping")
        return None

    ohlcv = ohlcv_panels[symbol]
    if atr <= 0:
        atr = ohlcv["close"].diff().abs().rolling(14).mean().iloc[-1]
        atr = float(atr) if not np.isnan(atr) else entry_price * 0.02

    # Find entry index by timestamp (handle timezone-aware indices)
    try:
        entry_ts = pd.Timestamp(timestamp)
        if hasattr(ohlcv.index, 'tz') and ohlcv.index.tz is not None:
            if entry_ts.tz is None:
                entry_ts = entry_ts.tz_localize(ohlcv.index.tz)
        else:
            if entry_ts.tz is not None:
                entry_ts = entry_ts.tz_localize(None)
        idx = ohlcv.index.get_indexer([entry_ts], method="nearest")[0]
    except Exception:
        idx = -1

    if idx < 0 or idx >= len(ohlcv):
        print(f"[bridge] WARNING: timestamp {timestamp} not found in {symbol} data — skipping")
        return None

    future_path = build_future_path(ohlcv, idx, max_bars=profile.max_holding_bars)
    if future_path is None:
        print(f"[bridge] WARNING: no future path for {symbol}@{timestamp} — skipping")
        return None

    return SimulationInput(
        symbol=symbol,
        decision_timestamp=timestamp,
        mode=profile.mode,
        primary_interval=profile.primary_interval,
        entry_price=entry_price,
        atr=max(atr, 0.001),  # prevent division by zero
        future_path=future_path,
        profile=profile,
    )


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------
def run_batch_central_simulation(
    events_path: str,
    ohlcv_panels: dict[str, pd.DataFrame],
    profile: SimulationProfile,
    output_path: str,
) -> int:
    """Run all signal events through the central simulation engine.

    Args:
        events_path: Path to FACTOR_SIGNAL_EVENTS.csv.
        ohlcv_panels: Per-symbol OHLCV DataFrames.
        profile: SimulationProfile.
        output_path: CSV path for results.

    Returns:
        0 on success, 1 on error.
    """
    print(f"[bridge] Loading signal events from {events_path}")
    events = load_signal_events(events_path)
    print(f"[bridge] Loaded {len(events)} events")

    adapter = TrainingAdapter()
    results = []

    for i, (_, event) in enumerate(events.iterrows()):
        if i % 100 == 0 and i > 0:
            print(f"[bridge] Processed {i}/{len(events)} events...")

        sim_input = signal_event_to_sim_input(event.to_dict(), ohlcv_panels, profile)
        if sim_input is None:
            continue

        try:
            output = adapter.run(sim_input)
        except Exception as e:
            print(f"[bridge] ERROR: event {i} failed: {e}")
            continue

        # Extract outcomes
        long_r = output.long_outcome.realized_r_net if output.long_outcome else None
        short_r = output.short_outcome.realized_r_net if output.short_outcome else None
        best_action = output.best_action
        action_gap = output.action_gap_r

        results.append({
            "timestamp": event.get("timestamp", ""),
            "symbol": event.get("symbol", ""),
            "factor_name": event.get("factor_name", ""),
            "direction": event.get("direction", ""),
            "entry_price": sim_input.entry_price,
            "atr": sim_input.atr,
            "central_long_r_net": long_r,
            "central_short_r_net": short_r,
            "central_best_action": best_action,
            "central_action_gap_r": action_gap,
            "error": "",
        })

    # Write results
    out_df = pd.DataFrame(results)
    out_df.to_csv(output_path, index=False)
    print(f"[bridge] Wrote {len(results)} results to {output_path}")
    print(f"[bridge] Success rate: {len(results)}/{len(events)} "
          f"({len(results)/len(events)*100:.1f}%)")

    # Summary stats
    if len(results) > 0:
        long_vals = [r["central_long_r_net"] for r in results if r["central_long_r_net"] is not None]
        short_vals = [r["central_short_r_net"] for r in results if r["central_short_r_net"] is not None]
        if long_vals:
            print(f"[bridge] Mean central long r_net: {np.mean(long_vals):+.6f}")
        if short_vals:
            print(f"[bridge] Mean central short r_net: {np.mean(short_vals):+.6f}")

    return 0


# ---------------------------------------------------------------------------
# Proxy-to-Central mapping
# ---------------------------------------------------------------------------
def proxy_r_to_central_estimate(
    proxy_r: float,
    trade_count: int,
    fee_drag_r: float,
) -> dict:
    """Estimate central simulation equivalent from proxy R values.

    The fast_simulator uses TOTAL_COST_RATE=0.0010 (10bps) per trade.
    The central engine uses the same cost authority rates.
    However, exit logic differs: fast_simulator uses simplified stop/target,
    while central engine uses same-candle ambiguity handling and path metrics.

    This function provides a ROUGH estimate only. Official central sim results
    require full re-simulation.

    Args:
        proxy_r: Mean R per trade from fast_simulator.
        trade_count: Number of simulated trades.
        fee_drag_r: Mean fee cost per trade from fast_simulator.

    Returns:
        Dict with estimate and confidence level.
    """
    # Both use ~10bps cost rate, so the fee_drag should be similar
    # The main difference is exit logic and same-candle handling
    # Estimate: central sim R ≈ proxy R × 0.90 to 1.10 (exit logic uncertainty)
    uncertainty_range = 0.10  # ±10%
    lower_est = proxy_r * (1 - uncertainty_range)
    upper_est = proxy_r * (1 + uncertainty_range)

    return {
        "proxy_r": proxy_r,
        "estimated_central_r_lower": lower_est,
        "estimated_central_r_upper": upper_est,
        "confidence": "LOW",
        "notes": "Rough estimate only. Fast simulator and central engine exit logic differ. "
                 "Full re-simulation required for official R.",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Central Simulation Bridge P0 — run factor signals through central engine"
    )
    parser.add_argument(
        "--events", required=True,
        help="Path to FACTOR_SIGNAL_EVENTS.csv"
    )
    parser.add_argument(
        "--panel-cache", default="cache/factor_sprint",
        help="Path to factor_sprint panel cache directory (default: cache/factor_sprint)"
    )
    parser.add_argument(
        "--output", default="reports/alphaforge/factor_sprint/CENTRAL_SIM_RESULTS.csv",
        help="Output CSV path (default: reports/alphaforge/factor_sprint/CENTRAL_SIM_RESULTS.csv)"
    )
    parser.add_argument(
        "--mode", default="SCALP", choices=["SCALP", "SWING", "AGGRESSIVE_SCALP"],
        help="Trading mode (default: SCALP)"
    )
    parser.add_argument(
        "--execution-mode", default="TAKER", choices=["TAKER", "MAKER", "HYBRID"],
        help="Execution mode for cost model (default: TAKER)"
    )
    parser.add_argument(
        "--max-events", type=int, default=None,
        help="Limit number of events to process (for testing)"
    )
    args = parser.parse_args()

    # Load OHLCV panels
    try:
        ohlcv_panels = load_ohlcv_panels(args.panel_cache)
    except FileNotFoundError as e:
        print(f"[bridge] ERROR: {e}")
        print("[bridge] Cannot run without panel cache. Run factor_sprint.py first.")
        return 1

    # Build profile
    profile = default_profile(args.mode)
    profile.execution_mode = args.execution_mode

    # Run
    return run_batch_central_simulation(
        events_path=args.events,
        ohlcv_panels=ohlcv_panels,
        profile=profile,
        output_path=args.output,
    )


if __name__ == "__main__":
    sys.exit(main())
