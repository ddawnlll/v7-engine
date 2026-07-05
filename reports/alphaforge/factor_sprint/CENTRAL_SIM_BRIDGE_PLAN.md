# Central Simulation Bridge Plan

**Generated:** Factor Sprint 001.5, Phase D
**Status:** INVESTIGATION COMPLETE

---

## 1. Can Central Simulation Currently Consume Factor Signal Events?

**Partially yes, but not directly as a batch event stream.**

The central simulation engine (`simulation/engine/engine.py`) accepts `SimulationInput` objects, each representing a single decision point for a single symbol. The `simulation_adapter.py` in `alphaforge/factors/` already bridges factor scores to `SimulationInput`, but it operates bar-by-bar in a loop — not as a batch consumer of pre-generated signal events.

### Current Path (what `factor_r_sprint.py` uses):

```
factor scores → fast_simulator.py (standalone numba kernel) → trade records
```

This **bypasses** the central simulation engine entirely. The fast simulator has its own:
- Cost model (TOTAL_COST_RATE = 0.0012)
- Exit logic (stop/target/time-exit)
- No same-candle ambiguity handling
- No funding cost
- No path metrics

### Desired Path:

```
factor scores → signal events CSV → adapter → SimulationInput → central engine → SimulationOutput
```

## 2. Exact Command to Run (if available)

The central simulation can be invoked via `TrainingAdapter`:

```python
from simulation.adapters.training_adapter import TrainingAdapter
from simulation.contracts.models import (
    SimulationInput, FuturePath, Candle, SimulationProfile, TradingMode
)

adapter = TrainingAdapter()
sim_input = SimulationInput(
    symbol="BTCUSDT",
    decision_timestamp="2024-01-15T12:00:00Z",
    mode=TradingMode.SCALP,
    primary_interval="1h",
    entry_price=42000.0,
    atr=500.0,
    future_path=FuturePath(candles=[...], completeness_status="COMPLETE", expected_bars=8),
    profile=profile,
)
output = adapter.run(sim_input)
# output.long_outcome.realized_r_net, output.short_outcome.realized_r_net, etc.
```

There is **no existing CLI** that accepts a batch of signal events and runs them through the central engine. The `simulation/run_simulation.py` is a synthetic data generator, not a real simulation runner.

## 3. Minimal Adapter Needed

To bridge factor signal events to the central simulation, the following adapter is needed:

### 3.1 Signal Event → SimulationInput Converter

```python
def signal_event_to_sim_input(
    event: dict,          # row from FACTOR_SIGNAL_EVENTS.csv
    ohlcv_panels: dict,   # aligned OHLCV panels
    atr_panel: pd.DataFrame,
    profile: SimulationProfile,
) -> SimulationInput:
    """Convert a signal event dict to a SimulationInput for the central engine."""
    # Extract timestamp, symbol, entry price from event
    # Build FuturePath from OHLCV data after entry timestamp
    # Set ATR from pre-computed panel
    # Return SimulationInput
```

### 3.2 Batch Simulation Runner

```python
def run_batch_simulation(
    events_path: str,           # FACTOR_SIGNAL_EVENTS.csv
    ohlcv_panels: dict,         # aligned panels
    atr_panel: pd.DataFrame,
    profile: SimulationProfile,
) -> pd.DataFrame:
    """Run all signal events through the central engine. Returns results DataFrame."""
    events = pd.read_csv(events_path)
    results = []
    adapter = TrainingAdapter()
    for _, event in events.iterrows():
        sim_input = signal_event_to_sim_input(event, ohlcv_panels, atr_panel, profile)
        output = adapter.run(sim_input)
        results.append(extract_result(event, output))
    return pd.DataFrame(results)
```

### 3.3 Files to Create

| File | Purpose |
|------|---------|
| `alphaforge/src/alphaforge/factors/central_sim_bridge.py` | Signal event → SimulationInput converter + batch runner |
| `scripts/factor_central_sim.py` | CLI entry point: reads events CSV, runs central sim, writes results |

### 3.4 Files to Change

| File | Change |
|------|--------|
| `scripts/factor_r_sprint.py` | Add `--use-central-sim` flag to route through central engine instead of fast_simulator |
| `alphaforge/src/alphaforge/factors/leaderboard.py` | Add `write_central_sim_results()` function |

## 4. What Output Should Become Official

Once the central simulation bridge is running, these metrics become official V7 R:

| Metric | Source | Status |
|--------|--------|--------|
| `central_net_R` | `SimulationOutput.long_outcome.realized_r_net` | **OFFICIAL** |
| `central_expectancy_R` | Mean of `realized_r_net` across trades | **OFFICIAL** |
| `central_profit_factor` | Gross profit / gross loss from `realized_r_net` | **OFFICIAL** |
| `central_max_drawdown_R` | Max drawdown of cumulative `realized_r_net` | **OFFICIAL** |

## 5. What Must Remain Proxy Only

| Output | Reason |
|--------|--------|
| `ALPHA_R_LEADERBOARD.csv` (fast_simulator) | Uses standalone cost model, no same-candle ambiguity, no funding |
| `ALPHA_LEADERBOARD.csv` (IC analysis) | Statistical signal only, no trade simulation |
| `FACTOR_SIGNAL_EVENTS.csv` | Intent stream only, no trade outcome claimed |

---

## Implementation Priority

1. **Phase 1 (this sprint):** Mark standalone R as proxy (DONE via PROXY_R_LEADERBOARD_V2.csv)
2. **Phase 2 (next sprint):** Implement `central_sim_bridge.py` adapter
3. **Phase 3 (next sprint):** Run central simulation on signal events, produce `CENTRAL_SIM_RESULTS.csv`
4. **Phase 4 (future):** Only then can any candidate be promoted to V7

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Central engine may not handle batch well | Adapter runs one event at a time (sequential, safe) |
| FuturePath construction may fail for edge cases | Graceful skip with logging |
| Performance: central engine is slower than fast_simulator | Acceptable for accuracy; fast_simulator remains for screening |
| Cost model differences may change rankings | Expected — that's why we need central sim for official R |
