# simulation/ — Single Economic Simulation Truth Authority

## What `/simulation` Is

`simulation/` is the **single economic truth authority** for the V7 Engine monorepo. It owns the semantics, contracts, and implementation of the unified forward-simulation engine that evaluates `LONG_NOW`, `SHORT_NOW`, and `NO_TRADE` outcomes under one configurable cost/horizon/exit model.

## What `/simulation` Owns

- Economic simulation truth logic definition and implementation
- Simulation contracts (`SimulationInput`, `SimulationOutput`, `ActionOutcome`, etc.)
- Simulation input/output schemas
- Action family semantics (`LONG_NOW`, `SHORT_NOW`, `NO_TRADE`)
- Comparative action selection and gap/regret semantics
- Mode-specific simulation profiles (`SWING`, `SCALP`, `AGGRESSIVE_SCALP`)
- Stop / target / horizon / time-exit semantics
- Fee / slippage / cost model versioning
- Unresolved / invalidated semantics
- Path metrics: MFE, MAE, path quality, saved loss, missed opportunity
- Replay/paper adapter semantics
- Monte Carlo robustness semantics
- Golden tests and parity requirements
- Lineage and version rules
- Import boundary enforcement

## What `/simulation` Does NOT Own

- Runtime orchestration, persistence, or lifecycle (belongs to `v7/`)
- Policy/risk interpretation of simulation evidence (belongs to `v7/`)
- TradeOutcome normalization (belongs to `v7/` contracts)
- DecisionEvent/review surfaces (belongs to `v7/`)
- Live/paper/replay operational control (belongs to `v7/`)
- Training/research pipeline (belongs to `alphaforge/`)
- Dataset assembly (belongs to `alphaforge/`)
- Feature generation (belongs to `alphaforge/`)
- Model training, calibration, evaluation (belongs to `alphaforge/`)
- Raw market data storage (belongs to `data/`)
- Primitive helpers (belongs to `lib/`)

## Relationship to Other Authorities

```
                         ┌────────────────────────────┐
                         │        lib/ primitives      │
                         │ market data / indicators    │
                         │ primitive costs / time       │
                         └─────────────┬──────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────┐
│                        simulation/ authority                    │
│                                                                │
│  One economic truth engine                                      │
│  - LONG_NOW                                                     │
│  - SHORT_NOW                                                    │
│  - NO_TRADE                                                     │
│                                                                │
│  Produces:                                                      │
│  - realized R net/gross                                         │
│  - fees/slippage                                                │
│  - exit reason                                                  │
│  - MFE/MAE                                                      │
│  - saved-loss / missed-opportunity                              │
│  - best_action / second_best_action / action_gap_R              │
│  - resolution status                                            │
│  - lineage/version metadata                                     │
└───────────────┬────────────────────────────────────┬───────────┘
                │                                    │
                ▼                                    ▼
┌──────────────────────────────┐       ┌──────────────────────────────┐
│          v7 runtime           │       │         alphaforge            │
│                              │       │                              │
│ hosts simulation execution   │       │ consumes simulation outputs   │
│ paper/replay/live outcome    │       │ builds labels/datasets/eval   │
│ policy/risk uses evidence    │       │ trains/calibrates models      │
└───────────────┬──────────────┘       └──────────────┬───────────────┘
                │                                     │
                ▼                                     ▼
        TradeOutcome / policy               R labels / predictions
        DecisionEvent / review              walk-forward evaluation
```

## Key Design Rules

### One Engine, Mode Configured

There is one simulation engine, configured per trading mode. It is used across:

- Label generation (alphaforge consumes through adapters)
- Out-of-sample evaluation (alphaforge consumes through adapters)
- Runtime paper trading (v7 hosts)
- Historical replay (v7 hosts)
- Production-side outcome normalization (v7 hosts)

There must not be one cost model for labels and a different cost model for evaluation.

### No Label-Only Simulator

AlphaForge must not contain a separate simulation truth implementation buried inside labels. All R-multiple computation, cost application, stop/target exit logic, and path metrics flow through `/simulation` adapters.

### No Backtest-Only Simulator

Backtesting is the same simulation engine run in replay mode. There is no separate backtest simulation code path.

### No Hidden Deterministic Veto

Regime/policy may force or recommend no-trade at the policy layer, but simulation must still expose comparative `LONG_NOW`, `SHORT_NOW`, and `NO_TRADE` economic outcomes unless data is invalid. Deterministic regime logic must not silently overwrite simulated truth.

## Cross-Domain Contract Governance

Simulation economic truth contracts are now centralized in the **root contract authority**.

| What | Where |
|---|---|
| **Canonical cross-domain contract list** | `contracts/registry.json` |
| **SimulationOutput JSON Schema** | `contracts/schemas/simulation_output.schema.json` |
| **SimulationProfile JSON Schema** | `contracts/schemas/simulation_profile.schema.json` |
| **Field mappings to consuming domains** | `contracts/mappings/` (simulation_to_alphaforge.json, simulation_to_v7.json) |
| **Version compatibility rules** | `contracts/compatibility.json` |
| **Minimal fixture examples** | `contracts/fixtures/` (simulation_output_minimal.json) |
| **Root cross-domain governance** | `docs/architecture/governance.md` |
| **Adapter stubs (future boundary)** | `integration/adapters/` (simulation_adapter.py, alphaforge_adapter.py, v7_adapter.py) |
| **System-level tests** | `integration/tests/` (registry, schema parity, boundary, smoke) |

Simulation's own detailed contract docs (`simulation/docs/contracts.md`) remain the local authority for simulation-internal semantics. The root `contracts/` schemas are derived from these local docs and are the canonical cross-domain representations.

### Dependency Rules

```
simulation may import primitive helpers from lib (if needed).
simulation must not import alphaforge.
simulation must not import v7 policy/risk/runtime internals.
simulation must not import contracts/ (contracts/ contains no Python code).
v7 may import/host simulation through stable contracts.
alphaforge may consume simulation through side-effect-free adapters.
lib must not import simulation, v7, or alphaforge.
integration/adapters must not import simulation, alphaforge, or v7 internals.
```

### Validation Gates

Before simulation implementation begins, these gates must pass:

```bash
make check-contracts   # validates registry, schemas, mappings, fixtures
make check-boundaries  # validates import boundaries across all domains
make test-system       # runs all system-level tests
make test-all          # runs all lib + system tests
```

## Where to Read

**Start here:** [`docs/ai_summary.md`](docs/ai_summary.md) — the root hub with a complete table of contents, reading order, and dense machine-readable synthesis of every doc.

| Document | Answers |
|---|---|
| **[`docs/ai_summary.md`](docs/ai_summary.md)** | **→ START HERE.** Root hub, full TOC, reading order, dense synthesis |
| `docs/vision.md` | What simulation is, why it exists, what success means |
| `docs/architecture.md` | Component design, dependency rules, data flow |
| `docs/contracts.md` | SimulationInput, SimulationOutput, ActionOutcome schemas |
| `docs/profiles.md` | Mode-specific simulation profiles (SWING/SCALP/AGGRESSIVE_SCALP) |
| `docs/cost_model.md` | Fee, slippage, net/gross R semantics |
| `docs/exits_and_horizons.md` | Stop, target, time exit, unresolved, invalidated |
| `docs/no_trade_quality.md` | No-trade classification and quality metrics |
| `docs/lineage_and_versioning.md` | All version surfaces and bump rules |
| `docs/replay_paper_and_runtime_hosting.md` | V7 hosting, adapters, side-effect isolation |
| `docs/monte_carlo.md` | Diagnostic distributional simulation |
| `docs/validation.md` | Required test gates and import-boundary checks |
| `docs/migration_from_v7.md` | How V7 simulation docs migrate to /simulation |
| `docs/phases/S0–S6` | Implementation phase plans |

Every authority doc links back to `ai_summary.md` via its **Document Authority** footer.

## Current Status

**Phase:** Pre-implementation — documentation authority extraction
**Simulation engine:** Not yet implemented under `/simulation`
**V7 simulation docs:** Being migrated (see `docs/migration_from_v7.md`)
**AlphaForge integration:** Phase P2 references being updated
