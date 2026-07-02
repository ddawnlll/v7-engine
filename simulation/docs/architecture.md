# Simulation Architecture — Component Design & Data Flow

## Purpose

This document defines the technical architecture of `/simulation`. It answers:

- What components exist
- How data flows through simulation
- What contracts define boundaries
- What import rules apply
- How the engine evaluates comparative outcomes

## High-Level Flow

```
Raw / canonical future path
        │
        ▼
SimulationInput
        │
        ├── mode profile resolver
        ├── cost model resolver
        ├── horizon resolver
        ├── stop / target resolver
        ├── time-exit resolver
        └── validation / lineage check
        │
        ▼
Comparative Simulation Engine
        │
        ├── simulate LONG_NOW
        ├── simulate SHORT_NOW
        └── simulate NO_TRADE
        │
        ▼
Path Metrics
        │
        ├── MFE / MAE
        ├── time_to_mfe / time_to_mae
        ├── path_quality_score
        ├── saved_loss_score
        └── missed_opportunity_score
        │
        ▼
SimulationOutput
        │
        ├── AlphaForge labels/evaluation
        ├── V7 replay/paper/live outcome normalization
        └── monitoring / promotion / rollback evidence
```

## Components

### 1. SimulationInput Contract

The entry boundary. Carries canonical state, future path, mode, profile references, and lineage.

### 2. Mode Profile Resolver

Resolves the mode-specific simulation profile from configuration:

- Primary interval
- Context/refinement intervals
- Stop method and multiplier
- Target method and multiplier
- Max holding bars
- Ambiguity margin
- Min action edge

### 3. Cost Model Resolver

Resolves the cost profile:

- Fee model (maker/taker percentages)
- Slippage model (basis points, volatility-adjusted)
- Versioned cost profile reference

### 4. Horizon Resolver

Determines the forward window:

- Max holding bars
- Horizon end bar index
- Time-exit bar count

### 5. Stop/Target Resolver

Resolves stop and target levels per mode:

- ATR-based stop calculation
- ATR-based target calculation
- Stop-before-target, target-before-stop precedence rules
- Same-candle ambiguity handling

### 6. Time-Exit Resolver

Determines exit timing:

- Max holding bars threshold
- Time-exit bar index
- Horizon-end bar index

### 7. Validation / Lineage Check

Validates inputs before simulation:

- Profile version compatibility
- Cost model version compatibility
- Future path completeness check
- Data corruption detection

### 8. Comparative Simulation Engine

The core engine that simulates all three actions simultaneously:

- **LONG_NOW** path: enters long at canonical entry price, applies stop/target/time-exit
- **SHORT_NOW** path: enters short at canonical entry price, applies stop/target/time-exit
- **NO_TRADE** path: no entry, used for saved-loss and missed-opportunity computation

Each action path computes:

- Exit price and exit reason
- Gross R (raw return normalised to entry risk)
- Fee cost and slippage cost
- Net R (gross R minus costs)
- Resolution status (COMPLETE, UNRESOLVED, INVALIDATED)

### 9. Path Metrics

Computed for each directional action path:

- **MFE** (Maximum Favourable Excursion): best unrealized gain during the trade
- **MAE** (Maximum Adverse Excursion): worst unrealized loss during the trade
- **time_to_mfe**: bars from entry to MFE peak
- **time_to_mae**: bars from entry to MAE trough
- **path_quality_score**: composite 0–1 score based on MFE/MAE ratio and smoothness
- **saved_loss_score**: for NO_TRADE, how much loss was avoided
- **missed_opportunity_score**: for NO_TRADE, how much gain was missed

### 10. Comparative Action Selection

After all three paths are simulated:

- **best_action**: action with highest net economic utility
- **second_best_action**: second-best action
- **action_gap_R**: utility difference between best and second-best
- **regret_R**: difference between actual action and best action (for downstream use)
- **ambiguity flag**: true if action_gap_R < mode-specific ambiguity_margin

### 11. SimulationOutput Contract

The exit boundary. Contains all comparative outcomes, path metrics, resolution status, and lineage.

### 12. Adapter Layer

Side-effect-free adapters consumed by downstream systems:

- **Training replay adapter**: used by alphaforge for label generation
- **Evaluation replay adapter**: used by alphaforge for walk-forward evaluation
- **Historical replay driver**: used by v7 for historical replay
- **Paper forward driver**: used by v7 for paper trading
- **Monte Carlo driver**: used for robustness diagnostics

All adapters are deterministic for identical inputs. Training/evaluation adapters have no live execution side effects.

## Dependency Rules

```
simulation may import from lib:
  lib/indicators (ATR, returns, volatility)
  lib/costs (basic fee %, slippage estimation)
  lib/time (interval conversion, fold generation)

simulation MUST NOT import:
  v7/**          (policy, risk, runtime internals, orchestration)
  alphaforge/**  (labels, models, datasets, evaluation, calibration)

lib MUST NOT import:
  simulation/**
  v7/**
  alphaforge/**

v7 MAY import:
  simulation/**  (through stable contract surfaces only)

alphaforge MAY import:
  simulation/**  (through side-effect-free adapters only)
```

## Module Structure

```
simulation/
├── contracts/             # SimulationInput, SimulationOutput, ActionOutcome types
│   └── models.py          # All contract types (enums, value objects, input/output)
├── engine/                # Core simulation engine
│   ├── engine.py          # Main simulation loop (LONG_NOW, SHORT_NOW, NO_TRADE)
│   ├── batch.py           # Batch simulation orchestration
│   ├── costs.py           # Fee, slippage, and funding cost calculation
│   ├── exits.py           # Exit reason determination
│   ├── funding.py         # Funding rate cost model
│   └── writer.py          # Simulation output writer
├── adapters/              # Side-effect-free adapters for consumers
│   └── market_data_adapter.py  # Converts KlineRecords to SimulationInput
├── docs/                  # Authority documentation
│   └── phases/            # Phase implementation plans
├── tests/                 # Unit, golden, integration tests
│   ├── golden/
│   │   └── test_swing_golden.py
│   ├── test_batch_simulation.py
│   ├── test_funding_costs.py
│   ├── test_import_boundary.py
│   ├── test_market_data_adapter.py
│   └── test_simulation_writer.py
└── __init__.py
```

## Data Lineage

Every `SimulationOutput` carries full lineage:

```text
simulation_run_id          ← unique per simulation invocation
simulation_family_version  ← engine semantic version
simulation_profile_version ← profile semantic version
cost_model_version         ← cost model semantic version
fee_model_version          ← fee model semantic version
slippage_model_version     ← slippage model semantic version
horizon_family             ← horizon family identifier
stop_family                ← stop logic family identifier
target_family              ← target logic family identifier
time_exit_family           ← time-exit logic family identifier
adapter_kind               ← TRAINING | EVALUATION | REPLAY | PAPER | LIVE_OUTCOME
```

This lineage is preserved through the entire downstream pipeline: labels, datasets, models, evaluation, and monitoring.

## Error Semantics

| Error Condition | Behavior |
|---|---|
| Missing future path data | Output `resolution_status = UNRESOLVED` |
| Corrupted future path data | Output `resolution_status = INVALIDATED` with `invalidity_reason` |
| Profile version mismatch | Raise explicit version error |
| Cost model version mismatch | Raise explicit version error |
| Symbol missing from profile | Return error with explicit reason |
| Invalid mode | Return error with supported mode list |
| Import boundary violation | Hard stop (tests enforce this) |

## Testing Layers

| Layer | What It Tests |
|---|---|
| Unit tests | Individual path simulations, resolvers, exits, metrics |
| Golden tests | Known input/output pairs to catch drift |
| Integration tests | Full SimulationInput → SimulationOutput pipeline |
| Import boundary tests | simulation does not import v7/ or alphaforge/ |
| Parity tests | Same semantics across training/eval/replay/paper adapters |
| Monte Carlo tests | MC outputs distinguishable from realized truth |

---

## Document Authority

**Canonical hub:** [ai_summary.md](ai_summary.md) — read this first for the full system synthesis and table of contents.

**Related docs for this topic:**

| [contracts.md](contracts.md) | SimulationInput/Output contract schemas |
| [profiles.md](profiles.md) | Mode-specific parameterization |
| [cost_model.md](cost_model.md) | Fee and slippage semantics |
| [exits_and_horizons.md](exits_and_horizons.md) | Stop/target/time-exit logic |
| [replay_paper_and_runtime_hosting.md](replay_paper_and_runtime_hosting.md) | Adapter and V7 hosting model |
    
**Parent:** [../README.md](../README.md) — authority overview and ownership diagram.

**For implementation:** See [phases/](phases/) for v4.1.1 phase plans S0–S6.

**For validation:** See [validation.md](validation.md) for required test gates.

