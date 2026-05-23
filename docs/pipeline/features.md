# Pipeline Features

**Intended path:** `docs/v7/pipeline/features.md`

## Purpose

Defines how V7 transforms canonical state into model-ready features.

It answers:

> Given one valid canonical market state, what stable, leak-free feature schema should V7 produce for the hybrid model?

---

## Core Decision

V7 features are produced from canonical state only.

The same feature row feeds both:

- classification heads
- regression heads

Do not create separate feature pipelines for action classification and economic regression in first phase unless a later authority doc explicitly approves it.

---

## First-Phase Scope

Feature design assumes:

- primary decision interval: 4h
- higher-timeframe context: 1d
- refinement/timing context: 1h
- shared centralized multi-symbol model family
- target universe up to 60 symbols

---

## Inputs

- canonical state
- 4h primary state view
- 1d higher-timeframe state view
- 1h refinement/timing state view
- feature config
- feature schema version

---

## Outputs

A feature row includes:

- numeric feature values
- categorical/identity feature values where approved
- feature schema version
- missing/degraded flags
- symbol identity features
- interval/view availability flags
- normalization lineage

---

## Recommended Feature Groups

### 4h primary decision features

- returns
- candle geometry
- range structure
- volatility
- momentum
- trend/range state
- local support/resistance distance where available

### 1d higher-timeframe context

- HTF trend alignment
- HTF volatility regime
- HTF range compression/expansion
- HTF structure quality

### 1h refinement/timing context

- local momentum pressure
- entry-zone distance
- short-term volatility pressure
- entry readiness indicators
- local invalidation pressure

1h features are refinement/context features. They do not create a separate first-phase primary 1h model universe.

### Global context

- symbol identity
- session/time features
- data-quality flags
- missingness flags
- regime metadata

---

## Rules

1. Canonical-state only.
2. No future bars, future labels, or outcome echoes.
3. Stable naming and grouping.
4. Missingness is explicit.
5. First phase stays boring and interpretable.
6. Features support shared multi-symbol modeling.
7. Feature semantics are identical for training, replay, and live inference.

---

## Normalization Family

First-phase normalization:

- fit on training split only
- global across approved training universe
- robust centering/scaling for continuous features where needed
- no per-symbol normalization in first phase unless explicitly versioned later

Tree models may not require aggressive scaling, but normalization lineage must still be explicit when applied.

---

## Missing Context Rules

If higher-timeframe context is unavailable:

- emit fallback numeric values only to preserve schema stability
- emit explicit missing flags
- keep degradation visible downstream

If 1h refinement context is unavailable:

- preserve primary 4h decision features
- emit 1h-missing flags
- policy/runtime may degrade timing guidance or actionability based on config

---

## Symbol Identity Encoding

First phase uses compact one-hot encoding over the approved symbol universe.

If the approved universe changes materially, bump the feature schema or symbol-encoding family version.

---

## Config Surface

Key config families:

- feature schema version
- enabled feature groups
- normalization family
- symbol-encoding family
- missingness handling rules
- feature clipping/winsorization rules
- approved symbol metadata

---

## Interfaces

Upstream:

- canonical state
- `contracts/analysis_request.md`

Downstream:

- `pipeline/dataset.md`
- `pipeline/model.md`
- `pipeline/monitoring.md`

---

## Test Requirements

Minimum tests:

- deterministic transform for same input
- no future leakage
- schema stability
- missing-context flags work
- HTF fallback + flags work
- 1h refinement absence is visible
- symbol one-hot stability
- training-only normalization statistics

---

## Final Position

Features are the stable interface between canonical state and learned behavior. In V7, the same leak-free feature row must support both action classification and economic regression.
