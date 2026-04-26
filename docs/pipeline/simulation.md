# Pipeline Simulation

**Intended path:** `docs/v7/pipeline/simulation.md`

## Purpose

Defines the single authoritative simulation truth layer for V7.

It answers:

> Given one decision-time state and a future price path, how should V7 compute long, short, and no-trade consequences under one consistent economic model?

This document is the base authority for:
- labeling
- evaluation
- replay projection
- `TradeOutcome` normalization

---

## In Scope

- long / short / no-trade comparative simulation
- stop, target, and time-exit semantics
- fee and slippage application
- path-aware metrics
- unresolved / invalid outcome handling
- simulation-family versioning

---

## Out of Scope

- feature generation
- dataset splitting
- model architecture
- broker order logic
- runtime execution plumbing

---

## First-Phase Scope

- target universe: **60 symbols**
- initial rollout may use a smaller approved subset
- primary decision interval: **4h**
- higher-timeframe context: **1d**
- first-phase refinement/timing context: **1h**

---

## Core Decision

V7 uses **one simulation truth layer** across:
- labels
- out-of-sample forward evaluation
- runtime paper trading (which is forward simulation)
- historical replay (using a replay driver around the same engine)
- production-side outcome normalization

This simulation core is a shared engine module consumed by runtime; runtime does not own simulation truth. The simulation core should be profile/adaptor-friendly to accept both V6 and V7 inputs.
There must not be one cost model for labels and another for evaluation.

---

## Inputs

Minimum inputs:
- decision timestamp
- symbol
- primary interval
- future candle path
- configured horizon family
- configured stop / target / time-exit rules
- configured cost assumptions

Optional inputs:
- execution assumption family
- entry timing annotation
- replay mode metadata

---

## Entry Timing Annotation Rule

If an entry timing annotation exists, first-phase simulation treats it as **metadata only**.

That means:
- it may be preserved for audit and comparative studies
- it does **not** change the canonical simulated entry rule in first phase
- it does **not** silently shift entry price by itself

If later simulation families support timing-aware alternative entries, that must be introduced as a new comparative family version, not hidden inside the same family.

---

## Outputs

Simulation should produce one normalized comparative output family containing:

- long outcome
- short outcome
- no-trade outcome
- chosen exit reason
- realized R
- MFE / MAE
- path quality signals
- counterfactual comparison signals
- resolution status

---

## Rules

### 1. Market-first truth
Simulation evaluates the market path, not legacy runtime actions, as the source of truth.

### 2. Comparative truth
Long, short, and no-trade must be evaluated under the same simulation family.

### 3. Cost-aware truth
Fees and slippage are mandatory parts of simulated quality.

### 4. Path-aware truth
Terminal return alone is not enough.
Simulation must preserve path quality metrics.

### 5. Pending is legal
If the future window is incomplete, the simulation result must remain unresolved rather than pretending to be final.

### 6. Version everything that changes meaning
Meaningful changes to stop/target/cost/horizon semantics must bump simulation-family versions.

---

## Canonical Exit Families

The first-phase simulation layer should support:

- `STOP_HIT`
- `TARGET_HIT`
- `TIME_EXIT`
- `HORIZON_END`
- `UNRESOLVED`
- `INVALIDATED`

Do not introduce many specialized exit families in first phase.

---

## Unresolved vs Invalidated

First-phase rule:

- use `UNRESOLVED` when the approved future window is not yet fully available but may still become available
- use `INVALIDATED` when the required window cannot be completed safely or consistently

### Default invalidation convention
Unless a family-specific config overrides it:
- an unresolved simulation may remain unresolved until the horizon family completes
- if required future data is still incomplete after **2 × the configured horizon length**, mark `INVALIDATED`
- immediately invalidate if the required future data is known to be irrecoverable or corrupted

This rule must remain config-driven through the unified config system.

---

## Cost Model Rules

First-phase simulation must include:

- taker fee assumption
- slippage assumption
- net realized R after costs

Recommended versioned surfaces:
- `cost_model_version`
- `fee_model_version`
- `slippage_model_version`

---

## No-Trade Rules

No-trade is first-class.
It must not be treated as “absence of simulation.”

At minimum, simulation must support:
- correct no-trade
- missed opportunity
- saved loss
- ambiguous no-trade

This is required for later calibration and evaluation quality.

---

## Failure / Fallback

If simulation cannot be resolved:
- mark unresolved
- preserve invalidity reason if applicable
- do not silently emit final labels
- do not silently train on unresolved states

---

## Config Surface

Key config families:
- horizon family
- stop family
- target family
- time-exit family
- fee model
- slippage model
- validity window rules

All of these must use the unified config system described in `docs/v7/configuration.md`.

---

## Interfaces

Upstream:
- `contracts/analysis_request.md`
- `contracts/decision_event.md`

Downstream:
- `pipeline/labels.md`
- `pipeline/evaluation.md`
- `contracts/trade_outcome.md`

---

## Test Requirements

Minimum simulation tests:
- stop hit first
- target hit first
- time exit
- fee/slippage reduces R correctly
- long vs short vs no-trade comparative parity
- unresolved window stays unresolved
- invalidation after irrecoverable missing data
- entry timing annotation does not silently change canonical entry in first phase

---

## Final Position

Simulation is the economic truth core of V7.
If this layer is inconsistent, every downstream layer becomes untrustworthy.
