# Pipeline Simulation

**Intended path:** `docs/v7/pipeline/simulation.md`

## Purpose

Defines the single authoritative economic simulation truth layer for V7.

It answers:

> Given one decision-time state and a future price path, how should V7 compute long, short, and no-trade consequences under one consistent economic model?

Simulation is the base authority for labels, evaluation, replay projection, and `TradeOutcome` normalization.

---

## Core Decision

V7 uses one simulation truth layer across:

- label generation
- out-of-sample evaluation
- runtime paper trading
- historical replay
- production-side outcome normalization

There must not be one cost model for labels and a different cost model for evaluation.

---

## First-Phase Scope

- target universe: up to 60 symbols
- primary decision interval: 4h
- higher-timeframe context: 1d
- refinement/timing context: 1h
- action family: `LONG_NOW`, `SHORT_NOW`, `NO_TRADE`

---

## Inputs

Minimum inputs:

- decision timestamp
- symbol
- primary interval
- canonical market state lineage
- future candle path
- horizon family
- stop family
- target family
- time-exit family
- fee model
- slippage model
- simulation-family version

Optional inputs:

- execution assumption family
- entry timing annotation
- replay/paper/live mode metadata

---

## Outputs

Simulation produces one comparative output family:

- long outcome
- short outcome
- no-trade outcome
- exit reason
- realized R net of costs
- gross R before costs
- fees and slippage cost
- MFE / MAE
- path quality score
- saved-loss score
- missed-opportunity score
- regret relative to best action
- resolution status
- invalidity reason if applicable

---

## Exit Families

First-phase exit reasons:

- `STOP_HIT`
- `TARGET_HIT`
- `TIME_EXIT`
- `HORIZON_END`
- `UNRESOLVED`
- `INVALIDATED`

Do not introduce many specialized exit families in first phase.

---

## No-Trade Rules

No-trade is first-class. It is not absence of simulation.

Simulation must classify no-trade quality as:

- correct no-trade
- saved loss
- missed opportunity
- ambiguous no-trade

This is required for classification labels, regression labels, calibration, and evaluation.

---

## Entry Timing Annotation Rule

If entry timing annotation exists, first-phase simulation treats it as metadata only.

It may be preserved for audit and later analysis, but it must not silently shift canonical entry price or change the first-phase action family.

Timing-aware alternative entries require a new simulation-family version.

---

## Unresolved and Invalidated

Use `UNRESOLVED` when the future window is incomplete but may still complete.

Use `INVALIDATED` when the required future data cannot be completed safely or consistently.

Default convention:

- unresolved may remain unresolved until the horizon completes
- if required future data is still incomplete after `2 x horizon`, mark invalidated unless config overrides
- immediately invalidate known corrupted or irrecoverable future data

---

## Cost Model Rules

First-phase simulation must include:

- fee assumption
- slippage assumption
- net realized R after costs

Recommended version surfaces:

- `cost_model_version`
- `fee_model_version`
- `slippage_model_version`

---

## Rules

1. Market-first truth: evaluate the market path, not legacy runtime actions.
2. Comparative truth: long, short, and no-trade are evaluated together.
3. Cost-aware truth: fees and slippage are mandatory.
4. Path-aware truth: terminal return alone is not enough.
5. Pending is legal: incomplete windows stay unresolved.
6. Version meaning changes: stop/target/cost/horizon changes bump versions.

---

## Interfaces

Upstream:

- canonical market state
- contract lineage
- raw future candle path

Downstream:

- `pipeline/labels.md`
- `pipeline/evaluation.md`
- `contracts/trade_outcome.md`

---

## Test Requirements

Minimum tests:

- stop hit before target
- target hit before stop
- time exit
- horizon end
- fee/slippage reduces R correctly
- long/short/no-trade comparative parity
- unresolved stays unresolved
- invalidation after irrecoverable missing data
- timing annotation does not alter first-phase entry semantics

---

## Final Position

Simulation is V7's economic truth core. If simulation is inconsistent, all downstream labels, regression targets, evaluation evidence, and promotion decisions become untrustworthy.
