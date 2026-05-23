# Pipeline Simulation — Mode-Centric

**Intended path:** `docs/v7/pipeline/simulation.md`

## Purpose

Defines the authoritative economic simulation truth layer for V7 — **configured per trading mode**.

It answers:

> Given one decision-time state and a future price path, how should V7 compute long, short, and no-trade consequences under one consistent economic model, parameterized by mode?

Simulation is the base authority for labels, evaluation, replay projection, and `TradeOutcome` normalization.

---

## Core Decision

V7 uses **one simulation engine, configured per mode** across:

- label generation
- out-of-sample evaluation
- runtime paper trading
- historical replay
- production-side outcome normalization

There must not be one cost model for labels and a different cost model for evaluation.

---

## First-Phase Scope

- target universe: up to 60 symbols
- **SWING mode:** primary 4h, context 1d, refinement 1h
- **SCALP mode:** primary 1h, context 4h, refinement 15m
- **AGGRESSIVE_SCALP mode:** primary 15m, context 1h, refinement 5m
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

## Mode-Specific Simulation Configuration

Each mode has its own simulation config. The same simulation engine is used, parameterized by mode.

### Configuration Table

| Parameter | SWING | SCALP | AGGRESSIVE_SCALP |
|-----------|-------|-------|------------------|
| Primary interval | 4h | 30m/1h | 15m |
| Context interval | 1d | 4h | 1h |
| Refinement interval | 1h | 15m | 5m |
| Max holding bars | 12-30 | 3-12 | 1-5 |
| Stop multiplier (ATR) | 2.0-2.5 | 1.5-2.0 | 1.0-1.5 |
| Target multiplier (ATR) | 2.0-3.0 | 1.5-2.0 | 1.0-1.5 |
| Ambiguity margin (R) | 0.20 | 0.10 | 0.05 |
| Min action edge (R) | 0.35 | 0.15 | 0.08 |
| MAE penalty weight | MEDIUM | HIGH | VERY_HIGH |
| Cost penalty weight | MEDIUM | HIGH | VERY_HIGH |
| NO_TRADE tendency | LOW | MEDIUM | HIGH (default) |

### Mode-Specific Stop/Target Behavior

```yaml
simulation_configs:
  swing:
    primary_interval: "4h"
    context_intervals: ["1d", "1h"]
    max_holding_bars: 30
    stop_method: "atr_wide"
    target_method: "atr_wide"
    ambiguity_margin_r: 0.20
    min_action_edge_r: 0.35

  scalp:
    primary_interval: "1h"
    context_intervals: ["4h", "15m"]
    max_holding_bars: 12
    stop_method: "atr_medium"
    target_method: "atr_medium"
    ambiguity_margin_r: 0.10
    min_action_edge_r: 0.15

  aggressive_scalp:
    primary_interval: "15m"
    context_intervals: ["1h", "5m"]
    max_holding_bars: 5
    stop_method: "atr_tight"
    target_method: "atr_tight"
    ambiguity_margin_r: 0.05
    min_action_edge_r: 0.08
    no_trade_default: true
```

### Regime-Aware Stop Multipliers

Stop multipliers adapt to detected market regime (see mode-centric doc section 5.4):

- In `TRANSITION` regime: use 99.0 multiplier (forces no-trade instead of wide stop)
- In trend regimes: use base multipliers (2.0)
- In `RANGE`: use tighter multipliers (1.5)

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
