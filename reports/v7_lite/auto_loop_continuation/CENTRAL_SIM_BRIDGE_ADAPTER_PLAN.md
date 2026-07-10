# Central Simulation Bridge — Adapter Plan

**Generated:** 2026-07-08T08:43:00+00:00

---

## Architecture

```
FACTOR_SIGNAL_EVENTS.csv
    │  columns: timestamp, symbol, factor_name, score, direction, entry_price, atr
    ▼
[central_sim_bridge_p0.py]
    │  1. load_signal_events()
    │  2. load_ohlcv_panels()
    │  3. build_future_path()
    │  4. signal_event_to_sim_input()
    ▼
TrainingAdapter.run(SimulationInput)
    │  Central simulation engine (simulation/engine/engine.py)
    │  Full cost model (simulation/engine/costs.py)
    ▼
SimulationOutput → CENTRAL_SIM_RESULTS.csv
    columns: timestamp, symbol, factor_name, direction, entry_price, atr,
             central_long_r_net, central_short_r_net, central_best_action,
             central_action_gap_r
```

## P0 Adapter Details

| Component | File | Lines | Status |
|-----------|------|-------|--------|
| Event loader | `central_sim_bridge_p0.py` | ~50 | ✅ Tested |
| OHLCV panel loader | `central_sim_bridge_p0.py` | ~40 | ✅ Tested |
| FuturePath builder | `central_sim_bridge_p0.py` | ~25 | ✅ Tested |
| Signal→SimInput converter | `central_sim_bridge_p0.py` | ~40 | ✅ Tested |
| Batch runner | `central_sim_bridge_p0.py` | ~50 | ✅ Tested |
| CLI | `central_sim_bridge_p0.py` | ~40 | ✅ Tested |

## Proxy Entry → Central Sim Field Mapping

| Proxy Field | Central Sim Field | Required? | Notes |
|-------------|-------------------|-----------|-------|
| `factor_name` | Lineage metadata | Yes | Used for result grouping |
| `direction` | `SimulationInput` entry direction | Yes | Determines which ActionOutcome to use |
| `entry_price` | `SimulationInput.entry_price` | Yes | From OHLCV close at signal time |
| `atr` | `SimulationInput.atr` | Yes | From feature computation |
| `timestamp` | `SimulationInput.decision_timestamp` | Yes | Used for FuturePath alignment |
| `symbol` | `SimulationInput.symbol` | Yes | Symbol universe |
| n/a | `SimulationInput.future_path` | Yes | Constructed from OHLCV panels |
| n/a | `SimulationInput.profile` | Yes | Default SCALP profile provided |
| n/a | `ExecutionMode` | Yes | Default TAKER, configurable to MAKER |

## Missing Fields

The following fields are NOT in the proxy R leaderboard but ARE required for central simulation:

| Missing Field | Source | How to Fill |
|--------------|--------|-------------|
| `timestamp` per entry | FACTOR_SIGNAL_EVENTS.csv | Need to generate signal events |
| `entry_price` per entry | OHLCV close at signal time | From panel cache |
| `atr` per entry | Feature pipeline | From panel cache (or compute from OHLCV) |
| `future_path` candles | OHLCV data after entry | From panel cache (available) |

## Proxy R Leaderboard → Central Sim: Estimated vs Actual

For proxy entries WITHOUT signal events data, central sim R can be estimated:

```python
# Estimate from proxy R: central sim R ≈ proxy R ± 10% (exit logic uncertainty)
# Plus: central sim includes same-candle ambiguity handling
# Plus: central sim uses full cost model (same as fast_sim for 10bps)
```

**Confidence: LOW** — actual re-simulation is required for official V7 R.

## P1 Improvements (Future)

1. Generate FACTOR_SIGNAL_EVENTS.csv from factor sprint data (requires `lib.data_lake.gateway`)
2. Add `--execution-mode MAKER` for cost-reduced scenarios
3. Add per-symbol ATR percentile filter for regime-gated simulation
4. Add batch validation of 33 proxy entries vs central sim
