# Proxy → Central Simulation Bridge Plan

**Generated:** 2026-07-08T08:00:00+00:00
**Based on:** `reports/alphaforge/factor_sprint/CENTRAL_SIM_BRIDGE_PLAN.md`
**Status:** BRIDGE_NOT_BUILT

---

## Current State

The existing factor sprint R results (`ALPHA_R_LEADERBOARD.csv`, 63 entries) and proxy R results
(`PROXY_R_LEADERBOARD_V2.csv`, 33 entries) were produced by `fast_simulator.py` — a standalone
simulator with its own cost model (`TOTAL_COST_RATE = 0.0012`), exit logic, and no same-candle
ambiguity handling. These are **NOT** official V7 R values.

The central simulation engine (`simulation/engine/engine.py`) is the economic truth authority
but has **no CLI entry point** for batch factor signal processing.

---

## Proxy Entry Fields vs Central Sim Required Fields

### Proxy Entry Fields (from PROXY_R_LEADERBOARD_V2.csv)

| Field | Type | Available? |
|-------|------|-----------|
| `alpha_name` | str | ✓ |
| `config_name` | str | ✓ |
| `side_mode` | str (long/short) | ✓ |
| `trades` | int | ✓ |
| `avg_R` | float | ✓ (proxy R, not central) |
| `median_R` | float | ✓ |
| `total_R` | float | ✓ |
| `expectancy_R` | float | ✓ |
| `profit_factor` | float | ✓ |
| `win_rate` | float | ✓ |
| `max_drawdown_R` | float | ✓ |
| `fee_drag_R` | float | ✓ |
| `avg_hold_bars` | float | ✓ |
| `turnover` | float | ✓ |
| `best_symbol` | str | ✓ |
| `worst_symbol` | str | ✓ |
| `dominant_symbol_share` | float | ✓ |

### Central Sim Required Fields (from `simulation/engine/engine.py::simulate()`)

| Field | Type | Mapping | Available? |
|-------|------|---------|-----------|
| `symbol` | str | From event context | ✓ (from factor sprint) |
| `decision_timestamp` | str | Signal event timestamp | ✓ (from FACTOR_SIGNAL_EVENTS.csv) |
| `entry_price` | float | OHLCV close at timestamp | ✓ (from DataGateway) |
| `atr` | float | Pre-computed ATR | ✓ (from features pipeline) |
| `future_path` | FuturePath | Candles after entry | ✓ (from DataGateway) |
| `profile` | SimulationProfile | Mode-specific | ✓ (from mode config) |
| `direction` | str (long/short) | From factor signal | ✓ |

---

## Mapping Rules

| Proxy Field | Central Sim Field | Transformation |
|------------|-------------------|---------------|
| `avg_R` | `realized_r_net` (mean) | Requires full re-simulation |
| `fee_drag_R` | `fee_cost_r + slippage_cost_r` | Central engine computes per-trade |
| `max_drawdown_R` | Cumulative max drawdown | Requires full re-simulation |

**No direct mapping from proxy R to central sim R exists.**
All 33 proxy entries require full re-simulation through the central engine.

---

## Missing Fields

The following are needed for central simulation and are NOT available in proxy entries:

1. **Signal event timestamps** — the exact bar-by-bar entry decisions are in `FACTOR_SIGNAL_EVENTS.csv`
   (from `scripts/factor_signal_events.py`) but not in the proxy R summary
2. **OHLCV context** — the OHLCV data at each entry point needs to be loaded from the data lake
3. **FuturePath candles** — the forward-looking candles after each entry need to be constructed
4. **ATR values at entry** — need to be computed from features pipeline

---

## Unsupported Cases

The central simulation engine cannot handle:

1. **Batch signal events** — no batch interface exists (only single-event `simulate()`)
2. **Non-standard exit logic** — the central engine uses fixed stop/target/time-exit per profile
3. **Zero ATR entries** — would cause division by zero in cost model
4. **Last-bar entries** — no future path available for last N bars of data

---

## Minimal Adapter Needed

```python
# alphaforge/src/alphaforge/factors/central_sim_bridge.py
# Files to create:
#   1. central_sim_bridge.py — adapter
#   2. scripts/factor_central_sim.py — CLI entry point
```

### File 1: `alphaforge/src/alphaforge/factors/central_sim_bridge.py`

```python
"""Central Simulation Bridge — converts FACTOR_SIGNAL_EVENTS.csv → SimulationInput → SimulationOutput."""

from simulation.adapters.training_adapter import TrainingAdapter
from simulation.contracts.models import SimulationInput, FuturePath, Candle, SimulationProfile, TradingMode
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime


def load_signal_events(path: str) -> pd.DataFrame:
    """Load FACTOR_SIGNAL_EVENTS.csv (columns: timestamp, symbol, factor_name, score, direction, entry_price, atr)."""
    df = pd.read_csv(path)
    required = ["timestamp", "symbol", "factor_name", "score", "direction", "entry_price", "atr"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    return df


def build_future_path(symbol: str, entry_ts: str, ohlcv_panels: dict, max_bars: int = 30) -> FuturePath:
    """Build FuturePath from OHLCV panels after entry timestamp."""
    df = ohlcv_panels[symbol]
    entry_idx = df.index.get_loc(entry_ts) if entry_ts in df.index else -1
    if entry_idx < 0:
        return None
    future = df.iloc[entry_idx + 1 : entry_idx + 1 + max_bars]
    if len(future) == 0:
        return None
    candles = [
        Candle(open=r["open"], high=r["high"], low=r["low"], close=r["close"], volume=r["volume"])
        for _, r in future.iterrows()
    ]
    return FuturePath(candles=candles, completeness_status="COMPLETE", expected_bars=len(candles))


def signal_event_to_sim_input(
    event: dict,
    ohlcv_panels: dict,
    profile: SimulationProfile,
) -> SimulationInput:
    """Convert a signal event to a SimulationInput."""
    symbol = event["symbol"]
    entry_price = float(event["entry_price"])
    atr = float(event["atr"])
    entry_ts = str(event["timestamp"])
    
    future_path = build_future_path(symbol, entry_ts, ohlcv_panels)
    if future_path is None:
        return None
    
    return SimulationInput(
        symbol=symbol,
        decision_timestamp=entry_ts,
        mode=TradingMode.SCALP,
        primary_interval="1h",
        entry_price=entry_price,
        atr=max(atr, 0.001),  # prevent division by zero
        future_path=future_path,
        profile=profile,
    )


def run_batch_central_simulation(
    events_path: str,
    ohlcv_panels: dict,
    profile: SimulationProfile,
) -> pd.DataFrame:
    """Run all signal events through the central engine."""
    events = load_signal_events(events_path)
    adapter = TrainingAdapter()
    results = []
    
    for _, event in events.iterrows():
        sim_input = signal_event_to_sim_input(event.to_dict(), ohlcv_panels, profile)
        if sim_input is None:
            continue
        output = adapter.run(sim_input)
        results.append({
            "timestamp": event["timestamp"],
            "symbol": event["symbol"],
            "factor_name": event["factor_name"],
            "direction": event["direction"],
            "central_long_net_r": output.long_outcome.realized_r_net if output.long_outcome else None,
            "central_short_net_r": output.short_outcome.realized_r_net if output.short_outcome else None,
            "central_best_action": output.best_action,
            "central_action_gap_r": output.action_gap_r,
        })
    
    return pd.DataFrame(results)
```

### File 2: `scripts/factor_central_sim.py`

Standard CLI entry point: reads `FACTOR_SIGNAL_EVENTS.csv`, runs central simulation,
writes `CENTRAL_SIM_RESULTS.csv`.

---

## Test Fixture

A minimal test fixture should use:

1. **One factor** (e.g., `ret_1h_rank`)  
2. **One symbol** (e.g., `BTCUSDT`)
3. **One mode** (e.g., `SCALP`)
4. **~100 signal events** (from existing `FACTOR_SIGNAL_EVENTS.csv`)
5. **Verify**: output CSV has same number of rows as input events
6. **Verify**: `central_long_net_r` and `central_short_net_r` are finite floats

---

## Expected Output Format

```csv
timestamp,symbol,factor_name,direction,central_long_net_r,central_short_net_r,central_best_action,central_action_gap_r
2024-01-15T12:00:00Z,BTCUSDT,ret_1h_rank,long,0.023,-0.045,LONG_NOW,0.068
```

---

## Decision

| Item | Status |
|------|--------|
| Central sim bridge adapter | **NOT IMPLEMENTED** |
| CLI entry point | **NOT IMPLEMENTED** |
| Proxy entries needing retest | **33** |
| Can retest now? | **NO** |
| Blocker | No batch simulation CLI; no signal events → SimulationInput adapter |
| Effort to resolve | ~150-250 lines of Python (bridge adapter + CLI) |
| Can we estimate central sim from proxy? | **NO** — different cost model, exit logic, ambiguity handling |

### Mitigation for this run

Since we cannot run central simulation, we can use the proxy R data with the understanding
that proxy R values may differ significantly from central sim R values. The existing proxy
results are all negative, so even central sim would not produce positive survivors without
a fundamentally different approach.

**Next action:** Focus on non-simulation rescue strategies (BB Position v2, Truth V6 specialist).
