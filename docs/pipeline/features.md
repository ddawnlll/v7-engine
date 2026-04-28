# Pipeline Features

**Intended path:** `docs/v7/pipeline/features.md`

## Purpose

Defines how V7 transforms canonical state into model-ready features.

It answers:

> Given one valid canonical market state, what stable, leak-free feature schema should V7 produce?

---

## In Scope

- state-to-feature transformation
- feature grouping
- feature versioning
- missing/degraded feature handling
- normalization
- feature drift ownership

---

## Out of Scope

- simulation truth
- label generation
- dataset splitting
- model training logic
- runtime execution logic

---

## Core Decision

V7 features are produced from **canonical state only**.

That means:
- no future leakage
- no hidden runtime-only side channels
- same feature meaning across live, replay, and training

---

## First-Phase Scope

Feature design should assume shared feature infrastructure with schema variants where needed by `model_scope`:
- `SWING`: `primary_interval` `4h`, `context_intervals` `1d`, `refinement_intervals` `1h`
- `SCALP`: `primary_interval` `15m`, `context_intervals` `1h`, `refinement_intervals` `5m`
- `AGGRESSIVE_SCALP`: `primary_interval` `1m` or `3m`, `context_intervals` `5m` + `15m`, micro refinement where applicable
- target universe up to **60 symbols**

---

## Inputs

- `canonical_state`
- `state_views`
- feature config
- feature schema version

---

## Outputs

A feature row should include:

- feature values
- feature schema version
- missing/degraded flags
- symbol identity features where approved
- `model_scope` / interval identity features where approved

---

## Recommended Feature Groups

First-phase grouping should be explicit:

- **Scope primary decision features**: price geometry, momentum, volatility, structure on the scope `primary_interval`
- **Context interval features**: HTF alignment, regime, structure for the scope `context_intervals`
- **Refinement interval features**: timing pressure, local momentum, and entry-readiness support for the scope `refinement_intervals`
- **Global context**: time/session features, symbol metadata, quality/degradation flags

For example, `SWING` uses 4h + 1d + 1h, `SCALP` uses 15m + 1h + 5m, and `AGGRESSIVE_SCALP` uses 1m/3m + 5m/15m context. These views are context within one selected scope, not independently averaged interval predictors.

Do not create one giant anonymous feature blob.

---

## Rules

### 1. Canonical-state only
If a value is not present or derivable from the approved state surface, it is not a valid feature.

### 2. Leak-free only
No future bars, future labels, outcome echoes, or hidden evaluation data.

### 3. Stable naming
Feature names should remain stable and grouped.

### 4. Missingness is explicit
Missing or degraded context should surface as flags, not as silent zeros.

### 5. Keep first phase boring
Prefer explicit, interpretable features over complex opaque constructions.

### 6. Scope-compatible schemas
Features should support shared infrastructure and multi-symbol learning within a `model_scope`, not per-symbol handcrafted pipelines. Feature schemas may vary by `model_scope` where needed, and features do not decide the scope; runtime `scope_router` and config choose the scope before inference.

---

## Normalization Family

First-phase normalization family:
- fit on the training split only
- global across the approved training universe unless explicitly versioned otherwise
- use robust centering/scaling for continuous features
- do not use per-symbol normalization in first phase

This keeps the shared multi-symbol model interpretable and prevents hidden symbol-local semantics.

---

## Missing HTF Context Rule

If higher-timeframe context is unavailable:
- emit the normalized fallback value `0.0` for affected HTF numeric features
- emit explicit HTF-missing flags alongside them

The flag is authoritative.
The fallback value exists only to preserve numeric schema stability.

---

## Symbol Identity Encoding

First-phase symbol identity encoding:
- compact one-hot encoding over the approved symbol universe

Do not use opaque embedding systems in first phase authority.
If the approved universe changes materially, bump the feature schema or symbol-encoding family version.

---

## Feature Drift Ownership

Feature drift monitoring belongs to `pipeline/monitoring.md`.

Minimum drift families to monitor:
- distribution shift in continuous feature groups
- missingness-rate shift
- symbol-coverage shift
- HTF-availability shift

This document owns feature meaning.
Monitoring owns feature-drift observation.

---

## Failure / Fallback

If feature generation degrades:
- emit degradation flags
- preserve schema compatibility where possible
- do not silently drop critical features without visibility

---

## Config Surface

Key config families:
- feature schema version
- enabled feature groups
- normalization families
- allowed symbol metadata
- missingness handling rules
- symbol-encoding family

---

## Interfaces

Upstream:
- `contracts/analysis_request.md`

Downstream:
- `pipeline/dataset.md`
- `pipeline/model.md`
- `pipeline/monitoring.md`

---

## Test Requirements

Minimum feature tests:
- deterministic transform for same input
- no future leakage
- schema stability
- missing-context flags work
- HTF fallback + missing flags work
- symbol one-hot encoding is stable
- normalization uses training-only statistics

---

## Final Position

Features are the stable interface between canonical state and learned model behavior.
If feature meaning drifts, model quality becomes hard to trust.
