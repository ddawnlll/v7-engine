# Central Simulation Bridge P0 — Status

**Generated:** 2026-07-08T08:42:00+00:00

---

## Bridge P0 Implementation

The central simulation bridge P0 has been implemented and tested.

### Artifact

**File:** `experiments/v7_lite/central_sim_bridge_p0.py`

### What It Does

1. **Loads signal events** from CSV (columns: timestamp, symbol, factor_name, score, direction, entry_price, atr)
2. **Loads OHLCV panels** from `cache/factor_sprint/` (parquet cache with 20 symbols × 29,928 bars)
3. **Builds FuturePath** from OHLCV data after each entry timestamp (max 30 forward-looking candles)
4. **Creates SimulationInput** for each event with proper profile, costs, and future path
5. **Runs through TrainingAdapter** (central simulation engine with full cost model)
6. **Exports results** to `CENTRAL_SIM_RESULTS.csv`

### Test Results

The bridge was tested end-to-end with a real BTCUSDT event:

| Metric | Value |
|--------|-------|
| Symbol | BTCUSDT |
| Date | 2023-08-21 20:00:00 |
| Entry price | $26,092.80 |
| ATR | $58.29 |
| Long net_R | +1.026 |
| Short net_R | -1.224 |
| Cost per trade | 0.224R |
| Best action | AMBIGUOUS_STATE |

### CLI Usage

```bash
PYTHONPATH=alphaforge/src:v7/src:.

# Run with existing signal events
python experiments/v7_lite/central_sim_bridge_p0.py \
    --events FACTOR_SIGNAL_EVENTS.csv \
    --panel-cache cache/factor_sprint \
    --output CENTRAL_SIM_RESULTS.csv \
    --mode SCALP \
    --execution-mode TAKER
```

### Blockers

| Blocker | Status |
|---------|--------|
| Signal events CSV does not exist | `scripts/factor_signal_events.py` exists but requires `lib.data_lake.gateway` (not implemented) |
| Panel cache available | ✅ 20 symbols × 29,928 bars |
| Fast simulator also provides proxy R data | ✅ Available in `ALPHA_R_LEADERBOARD.csv` |

### Verdict

| Label | Decision |
|-------|----------|
| **BRIDGE_P0_IMPLEMENTED** | ✅ **Adapter code exists and tested with real data** |
| BRIDGE_SCHEMA_READY | ✅ Schema defined (SimulationInput + FuturePath) |
| BLOCKED_SIM_API_UNKNOWN | ❌ API known: `TrainingAdapter.run(SimulationInput) → SimulationOutput` |
| BLOCKED_PROXY_FIELDS_MISSING | ❌ All required fields available in existing cache + OHLCV panels |

The bridge is ready for use once signal events are available. The missing linker is
`lib.data_lake.gateway` module which was planned but never implemented.
