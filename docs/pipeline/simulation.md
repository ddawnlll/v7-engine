# Pipeline Simulation

**Intended path:** `docs/v7/pipeline/simulation.md`

## Purpose

Defines the simulation semantics and output contract that the V7 pipeline consumes from the runtime-hosted simulation engine.

It answers:

> Given one decision-time state and a future price path, what normalized runtime simulation output should labels, evaluation, replay, and outcomes consume?

Runtime simulation ownership is defined in `docs/runtime/simulation_engine.md`. This document defines pipeline consumption semantics for:
- labeling
- evaluation
- replay projection
- `TradeOutcome` normalization
- Monte Carlo robustness evidence where configured

---

## In Scope

- long / short / no-trade comparative simulation outputs
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
- implementing or hosting the simulation engine

---

## First-Phase Scope

- target universe: **60 symbols**
- initial rollout may use a smaller approved subset
- one runtime-hosted simulation engine supports multiple `model_scope` profiles; it must not hardcode one horizon family for all scopes
- `SWING`: `primary_interval` `4h`, `context_intervals` `1d`, `refinement_intervals` `1h`, swing horizon profile
- `SCALP`: `primary_interval` `15m`, `context_intervals` `1h`, `refinement_intervals` `5m`, scalp horizon profile
- `AGGRESSIVE_SCALP`: `primary_interval` `1m` or `3m`, `context_intervals` `5m` + `15m`, micro refinement where applicable, immediate-continuation / very short horizon profile

---

## Core Decision

V7 uses one **runtime-hosted simulation engine** across:
- labels through a deterministic training/replay adapter
- out-of-sample forward evaluation through an evaluation replay adapter
- runtime paper trading as paper forward simulation
- historical replay through a runtime historical replay driver
- production-side outcome normalization
- Monte Carlo robustness mode when configured

Runtime owns simulation execution. The model does not own simulation, and the pipeline does not reimplement simulation. The pipeline consumes normalized runtime simulation outputs and defines how those outputs become labels, evaluation evidence, datasets, and outcome interpretations.

There must not be one cost model for labels and another for evaluation, and there must not be a label-only or backtest-only simulator.

Simulation profiles may be selected per `model_scope` / `trade_mode` through the unified config system. `SWING`, `SCALP`, and `AGGRESSIVE_SCALP` may use different horizon, stop/target, fee, cost, and slippage profiles, while still using the same runtime simulation engine with versioned `V6 simulation profile` and `V7 simulation profile` adapters where needed.

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
- `simulation_run_id` / `replay_run_id`
- `monte_carlo_run_id` when Monte Carlo robustness mode is configured

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

### 7. Runtime-hosted ownership
Pipeline code standardizes consumption of the runtime simulation engine. It must not implement a separate simulator for labels, evaluation, or models.

### 8. Side-effect-free adapters
Training/replay and evaluation adapters must be deterministic and side-effect-free. They must not call live exchange, broker, order-placement, or mutable runtime account-state paths.

### 9. Monte Carlo robustness mode
Monte Carlo robustness mode runs on top of the runtime simulation engine and produces distributional evidence. It is not live execution truth and does not replace paper forward simulation or historical replay.

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
- runtime simulation profile / adapter selection
- `V6 simulation profile` / `V7 simulation profile`
- `model_scope` / `trade_mode` simulation profile selection
- horizon family / `label_horizon_family`
- stop family
- target family
- time-exit family
- fee model
- slippage model
- validity window rules
- Monte Carlo robustness mode enablement and perturbation families, if used

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

Minimum simulation consumption tests:
- runtime simulation output schema is consumed deterministically
- training/replay adapter is side-effect-free
- stop hit first
- target hit first
- time exit
- fee/slippage reduces R correctly
- long vs short vs no-trade comparative parity
- unresolved window stays unresolved
- invalidation after irrecoverable missing data
- entry timing annotation does not silently change canonical entry in first phase
- Monte Carlo robustness output remains distributional evidence, not realized outcome truth

---

## Final Position

The runtime simulation engine is the economic simulated-truth core of V7.
This pipeline document keeps downstream consumption consistent; if consumption semantics drift, labels, evaluation, and outcomes become untrustworthy.
