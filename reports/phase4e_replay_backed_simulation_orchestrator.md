# Phase 4e — ReplayBackedSimulationOrchestrator Implementation Report

## Result

**PASS**

`ReplayBackedSimulationOrchestrator` was implemented in isolation.

- No `simulation_service.py` swap yet
- No repository schema changes
- No simulation truth changes

## Files Changed

- `runtime/services/replay_backed_simulation_orchestrator.py`
- `runtime/tests/test_replay_backed_simulation_orchestrator.py`
- `runtime/services/historical_simulation_engine.py`
- `runtime/services/indicator_snapshot.py`

## Implementation Summary

Implemented `ReplayBackedSimulationOrchestrator.run(...)` per the Phase 4b design:

- reuses runtime-owned candle loading, HTF alignment, analyzer replay, skip accounting, progress events, and trace emission flow
- replaces only the economic settlement step with `RuntimeReplayInputMapper -> ReplayDriver -> SimulationOutputResultMaterializer`
- preserves the external `run(payload, callbacks)` return shape expected by `SimulationService`
- keeps parallel worker fan-out behavior by instantiating replay-backed worker instances per task

The supporting compatibility patches were minimal:

- `historical_simulation_engine.py` now lazy-imports `v6` request-assembly modules so replay-oriented tests do not fail during module import when the `v6` package is absent
- `indicator_snapshot.py` now uses `timezone.utc` instead of `datetime.UTC`, restoring Python 3.10 compatibility

## Acceptance Test

Test command:

```bash
PYTHONPATH=. python3 -m pytest runtime/tests/test_replay_backed_simulation_orchestrator.py -q
```

Observed result:

```text
1 passed, 1 warning in 0.55s
```

## Focused Parity Harness

The orchestrator test runs one full replay window and compares four stages for the same actionable decision point:

1. runtime-selected direction (`BUY`)
2. mapped `SimulationInput`
3. resulting `SimulationOutput` from `ReplayDriver`
4. final materialized runtime result row returned by the orchestrator

Verified parity points:

| Check | Result |
|---|---|
| one actionable replay decision materialized from a full historical window | PASS |
| orchestrator result row equals independently mapped/materialized expected row | PASS |
| comparative outcomes preserved in runtime `details` | PASS |
| runtime metrics still count one closed trade | PASS |

## Known Limitations

- `simulation_service.py` still instantiates `HistoricalSimulationEngine`
- end-to-end side-by-side diff against the legacy engine is still pending the integration issue
- roadmap update for this checkpoint remains in the working tree because `v7/docs/roadmap.md` already contained unrelated uncommitted edits outside this issue scope
