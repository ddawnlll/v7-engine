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

Feature design should assume:
- primary decision interval: **4h**
- higher-timeframe context: **1d**
- optional future refinement: **1h**, not first-phase authority
- shared centralized multi-symbol model family
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
- interval identity features where approved

---

## Recommended Feature Groups

First-phase grouping should be explicit:

- price geometry
- momentum
- volatility
- structure
- higher-timeframe alignment
- time/session features
- symbol metadata
- quality/degradation flags

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

### 6. Shared model bias
Features should support a shared model family, not per-symbol handcrafted pipelines.

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
