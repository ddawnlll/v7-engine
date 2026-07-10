# Simulation Entry Point Discovery

**Generated:** 2026-07-08T08:45:00+00:00

---

## Entry Points Found

### 1. Central Simulation Engine (single-event)

| Field | Value |
|-------|-------|
| **File** | `simulation/engine/engine.py` |
| **Function** | `simulate(input: SimulationInput) -> SimulationOutput` |
| **Adapter** | `simulation/adapters/training_adapter.py::TrainingAdapter.run()` |
| **Input** | `SimulationInput(symbol, decision_timestamp, mode, entry_price, atr, future_path, profile)` |
| **Output** | `SimulationOutput(long_outcome, short_outcome, best_action, ...)` |
| **Cost model** | Full: `simulation/engine/costs.py` + `simulation/authority.py` (10bps round trip) |
| **Can run now?** | ✅ **YES** — tested with real BTCUSDT event |
| **Blocker** | Requires pre-built FuturePath from OHLCV data |

### 2. Batch Simulator (hardware-accelerated)

| Field | Value |
|-------|-------|
| **File** | `simulation/engine/batch.py` |
| **Class** | `BatchSimulator` |
| **Input** | Array-based (not SimulationInput) — for GPU/CPU-parallel kernel |
| **Cost model** | Uses same authority but different format |
| **Can run now?** | ✅ YES — but uses different input format from signal events |
| **Blocker** | Requires conversion from signal events → batch arrays |

### 3. Fast Simulator (used for factor sprint proxy R)

| Field | Value |
|-------|-------|
| **File** | `alphaforge/src/alphaforge/factors/fast_simulator.py` |
| **Cost model** | `TOTAL_COST_RATE = 0.0010` (10bps) from authority |
| **Exit logic** | Simplified stop/target/max-hold |
| **Status** | Used for current PROXY_R_LEADERBOARD_V2.csv |
| **Can run now?** | ✅ YES — but results are PROXY, not official |

### 4. Discovery Pipeline (Truth V6-style)

| Field | Value |
|-------|-------|
| **File** | `alphaforge/src/alphaforge/discover.py` (CLI: `python -m alphaforge.discover`) |
| **Pipeline** | `alphaforge/src/alphaforge/discovery/pipeline.py::run_discovery()` |
| **Backtest** | `alphaforge/src/alphaforge/discovery/backtest.py::backtest_signals()` |
| **Tested** | ✅ YES — synthetic test produced 51 trades through central sim |
| **Can run now?** | ✅ YES — with `--synthetic` or `--panel-cache` |

## Entry Point Summary

| Entry Point | Purpose | Status | Ready for Factor Signals? |
|-------------|---------|--------|--------------------------|
| `engine.simulate()` | Single-event central sim | ✅ Ready | No — requires individual calls |
| `TrainingAdapter.run()` | Single-event with validation | ✅ Ready | No — same |
| `BatchSimulator` | Hardware-accelerated batch | ✅ Ready | Partial — array format needed |
| `fast_simulator.py` | Quick proxy sim | ✅ Ready | ✅ YES (used for current proxy R) |
| `discovery pipeline` | Full alpha discover+backtest | ✅ Ready | No — designed for XGBoost models |
| `cli simulate` | CLI command | ❌ **STUB** | No — `Not yet implemented` |

## Comparison: Fast Simulator vs Central Engine

| Feature | Fast Simulator | Central Engine |
|---------|---------------|----------------|
| **Cost rate** | 0.0010 (10bps) | 0.0010 (10bps, same authority) |
| **Exit logic** | Simplified stop/target | Full stop/target + same-candle ambiguity |
| **Path metrics** | Not computed | MFE/MAE computed |
| **Funding cost** | Not modeled | Modeled |
| **Input** | Row-by-row in factor sprint loop | SimulationInput objects |
| **Official status** | PROXY only | **AUTHORITATIVE** |
| **Speed** | Fast (numba JIT) | Moderate (single-event, validated) |
| **Batch support** | Built-in loop | Requires batch wrapper |

## Key Findings

1. **No FACTOR_SIGNAL_EVENTS.csv exists** — only the generation script
2. `scripts/factor_signal_events.py` imports from `lib.data_lake.gateway` (not implemented)
3. **Central engine works** with proper SimulationInput objects
4. **Panel cache** has 20 symbols × 29,928 bars of real OHLCV data
5. **Discovery pipeline** works end-to-end and includes central sim backtest
6. **cli simulate** is a stub — no actual implementation
