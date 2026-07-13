# Current Task

## Task ID: V7LITE-LEVERAGE-NATIVE-P1-BINANCE-EXECUTION-PARITY

**Status:** PENDING — P0 economic parity foundation is complete.
P1 (version the leverage and margin contract, extend action space v2, isolated-margin
simulator) can begin after coordinator review.

## P0 Completed (2026-07-13)

P0 economic-R parity is verified:
- True R semantics: `base_net_R` vs forward return distinguished
- V2 action space (13 actions): backward-compatible with v1
- Isolated-margin position model in Simulation
- Deterministic parity fixture with 8 cost scenarios
- 58 tests passing locally and remotely
- `base_net_R` invariant confirmed: does not inflate with leverage

See `reports/accp/v7_lite_leverage_native_p0_economic_parity_2026-07-13.accp.yaml`
for full evidence.

## P1 Scope

From `docs/research/v7_lite_leverage_native_master_todo.md`:

- Version the leverage and margin contract fully
- Extend action space through P2 isolated-margin simulator
- Update contract registry/schema compatibility tests
- Build Binance-native simulation economics (bracket snapshots, mark-price)
- Model initial margin, maintenance margin, unrealized PnL, fees, funding, liquidation
- Add quantity/tick/min-notional rounding
- Preserve conservative intrabar ordering

## Non-negotiable constraints

- No live, paper, or shadow orders
- No automatic runtime execution implementation
- No cross margin / portfolio margin (P1 remains ISOLATED only)
- No numerical promotion/drawdown/liquidation threshold locked
- Simulation remains economic truth authority

## Evidence

- `reports/accp/v7_lite_leverage_native_p0_economic_parity_2026-07-13.accp.yaml`
- F-020 in `docs/audits/FINDINGS_LEDGER.md`
- `simulation/tests/test_leverage_parity.py` (58 tests)
