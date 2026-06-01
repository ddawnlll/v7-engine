# feature_workflow.md — End-to-End Feature Workflow

## Purpose

This document describes the **contract-first workflow** for adding or changing
features in the V7 Engine monorepo. It explains how data flows from raw
market data through simulation to training labels and runtime outcomes.

## Intended Flow (ASCII Diagram)

```
                         ┌──────────────────────┐
                         │     data/             │
                         │  raw/ processed/      │
                         │  cache/ models/       │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │     lib/             │
                         │  market_data (Binance)│
                         │  indicators (ATR, etc)│
                         │  costs (fees, slip)  │
                         │  time (folds)        │
                         └──────────┬───────────┘
                                    │ primitives
                                    ▼
               ┌──────────────────────────────────────┐
               │         simulation/                  │
               │                                     │
               │  simulation/docs/contracts.md        │
               │  → SimulationInput                  │
               │  → SimulationOutput                 │
               │  → ActionOutcome                    │
               │  → NoTradeOutcome                   │
               │  → PathMetrics                      │
               │                                     │
               │  Phases S0–S6 (planned)             │
               └──────────┬──────────────┬───────────┘
                          │              │
              via adapters│              │via adapters
                          ▼              ▼
          ┌──────────────────────┐  ┌──────────────────────┐
          │    alphaforge/       │  │       v7/            │
          │                      │  │                      │
          │  integration/adapters│  │  integration/adapters│
          │  AlphaForgeAdapter   │  │  V7Adapter           │
          │                      │  │                      │
          │  Phase P2: R-labels  │  │  Phase 2: normalize  │
          │  Phase P4: datasets  │  │  TradeOutcome        │
          │  Phase P5: XGBoost   │  │                      │
          │                      │  │                      │
          │  → AlphaForgeLabel   │  │  → TradeOutcome      │
          │  → Predictions       │  │  → DecisionEvent     │
          └──────────────────────┘  └──────────────────────┘

CONTRACTS LAYER (passive, read-only)

  contracts/
  ├── registry.json         ← enumerates all contract objects
  ├── compatibility.json    ← version compatibility rules
  ├── schemas/              ← JSON Schema definitions
  ├── mappings/             ← field-level cross-domain mappings
  └── fixtures/             ← minimal valid examples

INTEGRATION LAYER (active but minimal)

  integration/
  ├── adapters/             ← stub interfaces between domains
  └── tests/                ← boundary, contract, schema, smoke tests
```

## Contract-First Workflow

Every feature that crosses domain boundaries must follow this workflow:

### Step 1: Define Contracts

Before writing implementation code, define the contract surface:

1. Identify which existing contract objects are affected.
2. Identify if a new contract object is needed.
3. Update the relevant JSON schema in `contracts/schemas/`.
4. Update `contracts/registry.json` if adding a new contract.
5. Update `contracts/compatibility.json` for new version pairings.
6. Update `contracts/mappings/` if field mapping changes.
7. Update `contracts/fixtures/` with minimal examples.

### Step 2: Validate Contracts

Run contract validation before any implementation:

```bash
make check-contracts
```

This ensures all schemas are valid, all fixtures match their schemas,
all registry entries reference existing files, and all field mappings resolve.

### Step 3: Implement with Boundary Discipline

- Implement domain logic in the owning domain only.
- Never import a disallowed domain (see governance.md).
- Adapters go in the owning domain's src/, not in integration/.
- integration/adapters/ stubs remain as interface documentation only.

### Step 4: Update Tests

- Add unit tests in the domain's test directory.
- Add or update boundary tests if new import relationships exist.
- Add or update schema parity tests if new field mappings exist.
- Run `make test-all` before considering the feature complete.

## Fixture Update Workflow

When contract schemas change, fixtures must be updated:

1. Update the schema in `contracts/schemas/`.
2. Update `contracts/fixtures/` to include all new required fields.
3. Run `make check-contracts` to verify fixtures match schemas.
4. Run `make test-all` to verify no downstream breakage.

## Schema Parity Workflow

When a field is added or changed in a source contract (e.g., SimulationOutput),
validate that all consumer mappings are updated:

1. Update `contracts/mappings/simulation_to_alphaforge.json`.
2. Update `contracts/mappings/simulation_to_v7.json`.
3. Run `make check-contracts` — test_schema_parity must pass.
4. If mappings reference fields not in target schemas, update target schemas
   or remove the mapping.

## Boundary Test Workflow

Boundary tests run on every `make check-boundaries`:

1. They scan all Python files in each domain's src/ directory.
2. They detect `import` and `from ... import` statements via AST.
3. Any import of a forbidden domain is a hard failure.
4. Domains without src/ or without Python files are skipped (clean).

## Simulation → AlphaForge → V7 Relationship

```
simulation/ produces SimulationOutput (economic truth)
    │
    ├──→ alphaforge/ consumes SimulationOutput via adapters
    │      produces AlphaForgeLabel (training targets)
    │      produces features, datasets, trained models
    │      produces predictions (probability, expected R, confidence)
    │
    └──→ v7/ hosts simulation execution
           consumes SimulationOutput via adapters
           produces TradeOutcome (lifecycle consequence record)
           produces DecisionEvent (normalized lifecycle record)
           uses alphaforge predictions for policy decisions
```

Key rules:

- Simulation is the single economic truth authority.
- AlphaForge consumes simulation outputs through side-effect-free adapters.
- V7 hosts simulation execution but does not duplicate simulation semantics.
- Mappings in `contracts/mappings/` define the exact field correspondence.
- Schema parity tests enforce that mappings stay consistent.

## Adding a New Cross-Domain Feature

Example: Adding a new metric field to SimulationOutput.

1. Add the field to `contracts/schemas/simulation_output.schema.json`.
2. Add a mapping entry in `contracts/mappings/simulation_to_alphaforge.json`.
3. Add a mapping entry in `contracts/mappings/simulation_to_v7.json`.
4. Update `contracts/fixtures/simulation_output_minimal.json`.
5. Run `make check-contracts` (parity tests must pass).
6. Run `make check-boundaries` (no new violations).
7. Run `make test-all` (all tests pass).
8. Implement the metric in simulation/src/ (future phase).
9. Implement consumers in alphaforge/src/ and v7/src/ (future phases).
