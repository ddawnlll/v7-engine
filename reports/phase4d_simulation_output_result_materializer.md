# Phase 4d — SimulationOutputResultMaterializer Implementation Report

## Result

**PASS**

`SimulationOutputResultMaterializer` was implemented in isolation.

- No orchestrator changes
- No `simulation_service.py` integration changes
- No simulation truth changes

## Files Changed

- `runtime/services/simulation_output_result_materializer.py`
- `runtime/tests/test_simulation_output_result_materializer.py`

## Implementation Summary

Implemented `SimulationOutputResultMaterializer.to_runtime_result(...)` per the Phase 4b design:

- selected runtime direction -> selected comparative `ActionOutcome`
- legacy runtime row projection for `direction`, `outcome`, `realized_r`, and legacy `details` fields
- `STOP_HIT` / `TARGET_HIT` / `TIME_EXIT` normalization at the runtime presentation layer
- comparative LONG/SHORT/NO_TRADE evidence preserved under `details.comparative_outcomes`
- `resolution_status`, `invalidity_reason`, and `adapter_kind=REPLAY` preserved in stored metadata

## Isolated Materializer Test

Test command:

```bash
PYTHONPATH=. python3 -m pytest runtime/tests/test_simulation_output_result_materializer.py -q
```

Observed result:

```text
3 passed, 1 warning in 0.04s
```

## Field-by-Field Comparison Table — LONG Selected

Representative runtime context was materialized and compared against a manually constructed expected runtime result dict.

| Field | Materializer output | Manual expected | Result |
|---|---|---|---|
| `direction` | `BUY` | `BUY` | PASS |
| `outcome` | `WIN` | `WIN` | PASS |
| `realized_r` | `1.1` | `1.1` | PASS |
| `details.exit_reason` | `take_profit` | `take_profit` | PASS |
| `details.pnl` | `110.0` | `110.0` | PASS |
| `details.fees` | `5.0` | `5.0` | PASS |
| `details.notional` | `400.0` | `400.0` | PASS |
| `details.resolution_status` | `COMPLETE` | `COMPLETE` | PASS |
| `details.adapter_kind` | `REPLAY` | `REPLAY` | PASS |
| `details.comparative_outcomes.long.realized_r_net` | `1.1` | `1.1` | PASS |
| `details.comparative_outcomes.short.realized_r_net` | `-0.82` | `-0.82` | PASS |
| `details.comparative_outcomes.no_trade.no_trade_quality` | `AMBIGUOUS_NO_TRADE` | `AMBIGUOUS_NO_TRADE` | PASS |

## Field-by-Field Comparison Table — SHORT Selected

| Field | Materializer output | Manual expected | Result |
|---|---|---|---|
| `direction` | `SELL` | `SELL` | PASS |
| `outcome` | `LOSS` | `LOSS` | PASS |
| `realized_r` | `-0.82` | `-0.82` | PASS |
| `details.exit_reason` | `stop_loss` | `stop_loss` | PASS |
| `details.status` | `STOPPED_OUT` | `STOPPED_OUT` | PASS |
| `details.pnl` | `-123.0` | `-123.0` | PASS |
| `details.selected_action` | `SHORT_NOW` | `SHORT_NOW` | PASS |
| `details.selected_same_candle_ambiguity` | `True` | `True` | PASS |
| `details.comparative_outcomes.long.realized_r_net` | `1.1` | `1.1` | PASS |

## Field-by-Field Comparison Table — NO_TRADE Selected

| Field | Materializer output | Manual expected | Result |
|---|---|---|---|
| `direction` | `NO_TRADE` | `NO_TRADE` | PASS |
| `outcome` | `AMBIGUOUS_NO_TRADE` | `AMBIGUOUS_NO_TRADE` | PASS |
| `realized_r` | `0.0` | `0.0` | PASS |
| `details.status` | `SKIPPED` | `SKIPPED` | PASS |
| `details.exit_reason` | `no_trade` | `no_trade` | PASS |
| `details.selected_action` | `NO_TRADE` | `NO_TRADE` | PASS |
| `details.comparative_outcomes.no_trade.saved_loss_r` | `0.82` | `0.82` | PASS |

## Known Limitations

- Materializer is not yet wired into `ReplayBackedSimulationOrchestrator`
- Runtime-side monetary fields are projections from selected-direction R and provided sizing context; end-to-end parity still depends on orchestrator/integration work
- Existing diagnostics continue to read the legacy result shape; no schema or repository changes were made here
