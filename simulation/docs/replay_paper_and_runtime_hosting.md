# Replay, Paper & Runtime Hosting — Adapter & Integration Model

## Purpose

This document defines how the `/simulation` engine is hosted, executed, and consumed by `v7/` runtime and `alphaforge/` pipelines. It establishes the adapter model, side-effect isolation guarantees, and integration contracts.

## Core Principle

```
/simulation owns economic truth semantics and contracts.
V7 runtime hosts/executes simulation operationally through stable contracts.
AlphaForge consumes simulation through deterministic, side-effect-free adapters.
```

Runtime hosting does NOT mean V7 owns simulation truth semantics. Hosting is operational, not semantic.

## Operating Modes

### 1. Paper Forward Simulation

**Owner:** V7 runtime
**Consumer:** V7 paper trading
**Purpose:** Project forward outcomes for paper trades without live execution

```
V7 runtime:
  1. Assembles SimulationInput from live market state + decision
  2. Calls simulation engine with PAPER adapter kind
  3. Receives SimulationOutput
  4. Materializes DecisionEvent / TradeOutcome with paper=true
  5. No live order submission; no broker interaction
```

Paper forward uses the same simulation engine as training and evaluation. There is no separate "paper simulator."

### 2. Historical Replay Driver

**Owner:** V7 runtime
**Consumer:** V7 replay, alphaforge evaluation
**Purpose:** Replay historical decisions through the simulation engine

```
V7 runtime:
  1. Loads historical canonical state and future candle paths
  2. Calls simulation engine with REPLAY adapter kind
  3. Receives SimulationOutput for each historical decision point
  4. Outputs are used by: alphaforge evaluation, V7 replay review, promotion evidence
```

The historical replay driver:
- Uses the same runtime simulation engine
- Must NOT call live exchange, broker, or mutable account-state paths
- Must use replay-safe inputs (historical data only)

### 3. Training Replay Adapter

**Owner:** AlphaForge (consumes /simulation adapter)
**Consumer:** AlphaForge label generation
**Purpose:** Produce simulation outputs for label generation during training

```
AlphaForge:
  1. Constructs SimulationInput from canonical historical state + known future path
  2. Calls simulation adapter with TRAINING adapter kind
  3. Receives SimulationOutput
  4. Converts simulation output into classification/regression labels
```

The training replay adapter:
- Is deterministic and side-effect-free
- Has no live execution side effects
- Must not call any live exchange, broker, or mutable state
- Builds simulation inputs from canonical historical state and future windows
- Emits versioned simulation outputs for label and dataset lineage

### 4. Evaluation Replay Adapter

**Owner:** AlphaForge (consumes /simulation adapter)
**Consumer:** AlphaForge walk-forward evaluation
**Purpose:** Produce simulation outputs for out-of-sample evaluation

```
AlphaForge:
  1. Constructs SimulationInput for each walk-forward fold
  2. Calls simulation adapter with EVALUATION adapter kind
  3. Receives SimulationOutput
  4. Compares predicted R against simulated realized R
```

The evaluation replay adapter:
- Uses the same simulation engine as training
- Is deterministic and side-effect-free
- Preserves replay run IDs and simulation profile/version lineage
- Must not produce different results than the training adapter for identical inputs

### 5. Monte Carlo Robustness Mode

**Owner:** V7 runtime / AlphaForge (both can invoke)
**Consumer:** Evaluation, promotion evidence
**Purpose:** Generate distributional robustness evidence

```
Consumer:
  1. Calls simulation engine with Monte Carlo perturbation parameters
  2. Engine generates N perturbed future paths
  3. Runs simulation on each perturbed path
  4. Aggregates into MonteCarloOutput
  5. MC output carries separate lineage (monte_carlo_run_id)
```

Monte Carlo:
- Is diagnostic/distributional evidence
- Does NOT replace realized simulation truth
- Outputs must carry separate lineage (monte_carlo_run_id)
- Must be distinguishable from realized simulation outputs

## Adapter Model

```
┌─────────────────────────────────────────────────────────────┐
│                    /simulation engine                        │
│                                                             │
│  Pure function: SimulationInput → SimulationOutput           │
│  No side effects. No live data. No mutable state.           │
└─────────────────────────────────────────────────────────────┘
        ▲                    ▲                    ▲
        │                    │                    │
┌───────┴───────┐   ┌───────┴───────┐   ┌───────┴───────┐
│  Training     │   │  Evaluation   │   │  Replay/Paper │
│  Adapter      │   │  Adapter      │   │  Driver       │
│  (alphaforge) │   │  (alphaforge) │   │  (v7 runtime) │
└───────────────┘   └───────────────┘   └───────────────┘
```

All adapters construct `SimulationInput` from their domain context, call the same engine, and receive `SimulationOutput`. The engine itself has no knowledge of which adapter called it.

## Side-Effect-Free Guarantee

Training and evaluation adapters:

| Allowed | Forbidden |
|---|---|
| Read historical data from `data/` | Call live exchange APIs |
| Construct SimulationInput | Submit orders |
| Call simulation engine | Write to broker state |
| Convert SimulationOutput to labels | Mutate live account state |
| Write labels to dataset files | Open network connections |
| Emit versioned lineage metadata | Read future data beyond the fold boundary |

## V7 Runtime Hosting Contract

V7 runtime hosts simulation as an operational service, not as a semantic owner:

```
V7 runtime responsibilities:
  - Load simulation engine (import from /simulation)
  - Provide execution environment (process, sandboxing if needed)
  - Route SimulationInput → engine → SimulationOutput
  - Materialize TradeOutcome records from SimulationOutput
  - Handle lifecycle (start, stop, error recovery)
  - Select profile based on mode (mode router)
  - Validate output consistency

V7 runtime must NOT:
  - Modify simulation engine logic
  - Override simulation outputs with policy/runtime decisions
  - Create hidden alternative simulation paths
  - Silence or hide simulation evidence
```

## Paper and Replay Parity

The same simulation engine must produce the same `SimulationOutput` for identical `SimulationInput` regardless of operating mode. This means:

```
Given:
  identical future_path
  identical entry_price
  identical profile references
  identical cost model references

Then:
  TRAINING adapter output == EVALUATION adapter output == REPLAY driver output == PAPER driver output
```

This is testable. Golden tests must verify parity across adapters.

## Regime Constraint Visibility

When V7 policy/regime constraints override simulation evidence:

```
Simulation evaluates all actions purely economically.
Policy records constraints separately:
  - constraint_level: ADVISORY | SOFT_BLOCK | HARD_BLOCK
  - reason_code: regime_gate_forced_no_trade | regime_blocked_direction
  - override_time: utc_timestamp

The DecisionEvent and TradeOutcome preserve both:
  - simulation output (what the market truth says)
  - policy override (what the system decided to do)
```

Simulation must never be the hidden mechanism for regime-based suppression. Regime constraints belong to the policy layer.

## Testing

- Training adapter has no live execution side effects
- Evaluation adapter has no live execution side effects
- Paper and replay produce identical outputs for identical inputs
- V7 runtime hosts simulation through stable contracts
- AlphaForge consumes simulation through side-effect-free adapters
- No label-only simulator exists
- No backtest-only simulator exists
- Monte Carlo output is distinguishable from realized truth
- Regime constraints are visible and do not hide simulation evidence

---

## Document Authority

**Canonical hub:** [ai_summary.md](ai_summary.md) — read this first for the full system synthesis and table of contents.

**Related docs for this topic:**

| [architecture.md](architecture.md) | Adapter layer in component design |
| [contracts.md](contracts.md) | adapter_kind in SimulationInput |
| [validation.md](validation.md) | Parity tests and side-effect isolation tests |
| [migration_from_v7.md](migration_from_v7.md) | How V7 hosting wording changed |
    
**Parent:** [../README.md](../README.md) — authority overview and ownership diagram.

**For implementation:** See [phases/](phases/) for v4.1.1 phase plans S0–S6.

**For validation:** See [validation.md](validation.md) for required test gates.

