# Simulation Entry Point Discovery

**Generated:** 2026-07-08T08:10:00+00:00

---

## Discovery Results

| File | Type | Can Run? | Notes |
|------|------|----------|-------|
| `simulation/run_simulation.py` | Script | YES | Synthetic data generator only — NOT for real factor signals |
| `simulation/engine/engine.py::simulate()` | Function | VIA CODE | Core simulation engine, single-event interface |
| `simulation/engine/batch.py::BatchSimulator` | Class | VIA CODE | Batch runner with GPU/CPU/fallback, requires prepared arrays |
| `simulation/adapter.py::TrainingAdapter` | Class | VIA CODE | Dict-based adapter, side-effect-free |
| `cli/__main__.py` | CLI | YES | `python -m cli simulate` — but `cmd_simulate` is a STUB |
| `Makefile` | `make simulate` | DRY-RUN ONLY | Invokes `cli simulate`, which is a stub |

## Conclusion: No Central Simulation CLI Exists

The central simulation engine (`engine.py`) works correctly for individual `SimulationInput`
objects, but there is NO command-line interface for batch factor signal processing.

**Actual usable entry points:**

| Entry Point | Purpose | Ready? |
|-------------|---------|--------|
| `python3 -c "from simulation.engine.engine import simulate; simulate(...)"` | Single-event sim | ✅ Code works |
| `python -m cli simulate --dry-run` | Dry run | ✅ Stub |
| `make simulate DRY_RUN=1` | Dry run | ✅ Stub |

**For batch factor signals, an adapter must be built** (see PROXY_TO_CENTRAL_SIM_BRIDGE_PLAN.md).

## Fast Simulator (Currently Used)

The existing factor sprint R values use a standalone fast_simulator:

| Property | Fast Simulator | Central Engine |
|----------|---------------|----------------|
| Cost model | TOTAL_COST_RATE = 0.0012 | Full per-trade cost model |
| Exit logic | Simple stop/target/time | Same + same-candle ambiguity |
| Funding cost | Not modeled | Modeled |
| Path metrics | Not computed | MFE/MAE computed |
| Interface | Inline in factor_sprint script | SimulationInput objects |
| CLI | `scripts/factor_r_sprint.py` | None |
