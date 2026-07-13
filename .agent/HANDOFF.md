# Agent Handoff — V7-Lite Leverage-Native P0 Economic Parity (2026-07-13)

## Current state

P0 economic-R parity foundation is IMPLEMENTED and VERIFIED:
- 58 new tests pass locally (macOS, Python 3.14) and remotely (vast.ai, Python 3.12.3)
- Deterministic 13-action parity fixture produces correct invariants
- base_net_R does not inflate with leverage
- Cost scenarios stress correctly

## Completed in P0

### Scope 1: AlphaForge R semantics
- Added F-019 docstring warning in `alphaforge/src/alphaforge/train.py:generate_labels()`
- Clarified that `gross_r_values`/`net_r_values` are **net forward returns**, not risk-normalized R
- New simulation fields `base_net_R_long`/`base_net_R_short` available via `LeverageOutcome`

### Scope 2: Isolated-margin contract
- `simulation/contracts/models.py`: added `PositionMargin`, `CostScenario`, `LeverageOutcome`,
  `BinanceBracketSnapshot`, `MarginType`, `LeverageTier`
- `simulation/engine/margin.py`: `compute_isolated_margin()` with Binance USDⓈ-M formulas
- V2 action space mapping (13 actions, backward-compatible with v1 IDs 0-8)

### Scope 3: Extended action space
- `contracts/schemas/action_space.schema.json`: v2 with 13 actions (NO_TRADE + LONG/SHORT at 1x/2x/3x/5x/7x/10x)
- `contracts/registry.json`: ActionSpace bumped to v2.0.0
- Backward compatible: v1 IDs 0-8 preserved, v2 adds IDs 9-12

### Scope 4+5: Parity fixture + cost scenarios
- `simulation/engine/leverage_fixture.py`: `generate_leverage_fixture()` — deterministic fixture
- 8 immutable `CostScenario` instances: baseline, fee 1.5x/2.0x/3.0x, slippage 1.5x/2.0x, combined 2.0x/3.0x
- No monkey-patching for new code paths

### Scope 6: Tests
- `simulation/tests/test_leverage_parity.py`: 58 tests, all passing
- Covers: forward return vs true R, fixture determinism, base_net_R invariance,
  13-action contract, isolated-only margin, liquidation behavior, cost scenarios,
  simulation parity, backward compatibility

## Verification

### Local (macOS, Python 3.14):
```
PYTHONPATH=. .venv/bin/python -m pytest simulation/tests/test_leverage_parity.py -v
→ 58 passed

PYTHONPATH=. .venv/bin/python -m pytest simulation/tests/unit/test_costs.py simulation/tests/unit/test_engine.py simulation/tests/test_engine_interface.py simulation/tests/test_exits.py simulation/tests/test_cost_stress.py -q
→ 111 passed

PYTHONPATH=. .venv/bin/python -m pytest integration/tests/test_contract_registry.py integration/tests/test_schema_parity.py -q
→ 20 passed

PYTHONPATH=. .venv/bin/python -m pytest alphaforge/tests/test_wfv.py alphaforge/tests/test_wfv_timestamp_boundaries.py -q
→ 49 passed
```

### Remote (vast.ai, RTX 3060, Python 3.12.3, CUDA 13.0):
```
ssh -p 33346 root@1.208.108.242 'cd /root/v7-engine && PYTHONPATH=. python3 -m pytest simulation/tests/test_leverage_parity.py -v'
→ 58 passed

Parity fixture output:
  LONG_1X  base_R=0.812400  equity_R=0.812400  liq_price=None
  LONG_2X  base_R=0.812400  equity_R=1.624800  liq_price=25200.0
  LONG_10X base_R=0.812400  equity_R=8.124000  liq_price=45200.0
  SHORT_1X base_R=-0.854267  equity_R=-0.854267  liq_price=None
  Base net R invariant: True
  Cost scenarios: baseline→fee_2.0x fee_R doubles, equity drops correctly
```

## Files changed

### New files:
- `simulation/engine/margin.py` — isolated margin computation, v2 action space mapping
- `simulation/engine/leverage_fixture.py` — parity fixture generator, cost scenarios
- `simulation/tests/test_leverage_parity.py` — 58 P0 parity tests

### Modified files:
- `simulation/contracts/models.py` — added MarginType, LeverageTier, PositionMargin,
  CostScenario, BinanceBracketSnapshot, LeverageOutcome
- `contracts/schemas/action_space.schema.json` — v2 with 13 actions
- `contracts/registry.json` — ActionSpace v2.0.0
- `alphaforge/src/alphaforge/train.py` — F-019 docstring warning
- `docs/audits/FINDINGS_LEDGER.md` — F-020, F-019 update
- `docs/audits/OPEN_QUESTIONS.md` — Q-013 update

## Current task / next action

P0 is complete. Next: P1 (contracts + P2 isolated-margin simulator from
the master todo). See `.agent/CURRENT_TASK.md` for updated scope.

The frozen post-cutoff volume candidate remains G0–G6 HOLD.
No Binance testnet/shadow reconciliation has been attempted —
the parity fixture uses deterministic synthetic candles only.
