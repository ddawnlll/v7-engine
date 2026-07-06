# Phase 4G — simulation_service.py Integration

## Summary

Swapped `SimulationService` default engine from `HistoricalSimulationEngine` to `ReplayBackedSimulationOrchestrator`.

## Changes

- `runtime/services/simulation_service.py`: Added import for `ReplayBackedSimulationOrchestrator`; changed default engine from `HistoricalSimulationEngine()` to `ReplayBackedSimulationOrchestrator()`.
- `runtime/services/historical_simulation_engine.py`: Added `import warnings` and deprecation warning at the start of `__init__`.

## Design Decisions

- `HistoricalSimulationEngine` import retained in `simulation_service.py` for backward compatibility (constructor `engine` parameter accepts it).
- `HistoricalSimulationEngine` file preserved (not deleted).
- No changes to `SimulationRepository`, API routes, `contracts/registry.json`, or any files under `alphaforge/`, `simulation/`, or `lib/`.

## Lock Status

LOCKED — 459/459 runtime tests pass after swap.
