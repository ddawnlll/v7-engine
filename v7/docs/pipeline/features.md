# Pipeline Features — Mode-Centric (Shared)

**Intended path:** `docs/v7/pipeline/features.md`

## Purpose

Defines how V7 transforms canonical state into model-ready features — **shared across all trading modes**.

It answers:

> Given one valid canonical market state, what stable, leak-free feature schema should V7 produce for all mode-specific hybrid models?

---

## Core Decision

V7 features are produced from canonical state only.

The same feature row feeds both:

- classification heads (per mode)
- regression heads (per mode)

Do not create separate feature pipelines for different modes or for action classification and economic regression in first phase unless a later authority doc explicitly approves it.

---

## First-Phase Scope

Feature design supports **all three modes** through shared canonical state:

- **SWING:** primary 4h, context 1d, refinement 1h
- **SCALP:** primary 1h, context 4h, refinement 15m
- **AGGRESSIVE_SCALP:** primary 15m, context 1h, refinement 5m
- shared centralized multi-symbol model family **per mode**
- target universe up to 60 symbols

Features are built once from canonical state and consumed by all three mode pipelines.

---

## Inputs

- canonical state (multiple interval views)
- primary state view per mode
- higher-timeframe context views
- refinement/timing state views
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

### Primary decision features (per mode interval)

Features are computed at the primary interval of each mode (4h, 1h, 15m) but share the same feature logic:

- returns
- candle geometry
- range structure
- volatility
- momentum
- trend/range state
- local support/resistance distance where available

### Higher-timeframe context (per mode)

- HTF trend alignment
- HTF volatility regime
- HTF range compression/expansion
- HTF structure quality

### Refinement/timing context (per mode)

- local momentum pressure
- entry-zone distance
- short-term volatility pressure
- entry readiness indicators
- local invalidation pressure

Refinement features are context features. They do not create separate first-phase primary model universes.

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
6. Features support shared multi-symbol modeling **per mode**.
7. Feature semantics are identical for training, replay, and live inference.
8. **Features are shared across modes** — labels are mode-specific.

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

If a mode's higher-timeframe context is unavailable:

- emit fallback numeric values only to preserve schema stability
- emit explicit missing flags
- keep degradation visible downstream

If a mode's refinement context is unavailable:

- preserve primary decision features
- emit refinement-missing flags
- policy/runtime may degrade timing guidance or actionability based on config

---

## Symbol Identity Encoding

First phase uses compact one-hot encoding over the approved symbol universe.

If the approved universe changes materially, bump the feature schema or symbol-encoding family version.

---

## Config Surface

Key config families:

- feature schema version
- enabled feature groups (shared)
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
- `pipeline/model.md` (per mode)
- `pipeline/monitoring.md`

---

## Test Requirements

Minimum tests:

- deterministic transform for same input
- no future leakage
- schema stability
- missing-context flags work
- HTF fallback + flags work
- refinement absence is visible
- symbol one-hot stability
- training-only normalization statistics
- same feature row feeds all modes correctly

---

## Final Position

Features are the stable interface between canonical state and learned behavior. In V7, the same leak-free feature row must support both action classification and economic regression — across all three mode scopes.
