# Pipeline Dataset

**Intended path:** `docs/v7/pipeline/dataset.md`

## Purpose

Defines how V7 assembles training and evaluation datasets from state, features, and labels.

It answers:

> Given canonical state, features, and labels, how should V7 build temporally correct datasets for training and evaluation?

---

## In Scope

- dataset row assembly
- split rules
- walk-forward families
- symbol coverage policy
- dataset lineage and versions

---

## Out of Scope

- feature engineering rules
- simulation rules
- model internals
- runtime execution rules

---

## Core Decision

Dataset rows are built from:

- canonical state lineage
- feature row
- label row
- version lineage

No row is valid without traceable upstream lineage.

Label truth comes from runtime simulation outputs through side-effect-free adapters. Dataset assembly must not call live execution, broker, exchange, or mutable account-state paths.

---

## Inputs

- feature rows
- label rows
- request/result/event/outcome lineage where relevant
- dataset config
- split config

---

## Outputs

A dataset row should minimally carry:

- feature vector
- target fields
- symbol
- `model_scope`
- `primary_interval`
- `context_intervals`
- `refinement_intervals`
- timestamp
- feature schema version
- label version / interpretation version
- `label_horizon_family`
- cost model / slippage model identifiers
- simulation family/profile version
- `simulation_run_id` / `replay_run_id` where used
- `monte_carlo_run_id` where configured
- dataset family version

---

## First-Phase Scope

- shared dataset infrastructure, separate dataset family per `model_scope`
- target universe: up to **60 symbols**
- initial rollout may subset symbols, but dataset design should not assume six-symbol-only permanence
- `SWING` dataset: `primary_interval` `4h`, `context_intervals` `1d`, `refinement_intervals` `1h`, swing `label_horizon_family`
- `SCALP` dataset: `primary_interval` `15m`, `context_intervals` `1h`, `refinement_intervals` `5m`, scalp `label_horizon_family`
- `AGGRESSIVE_SCALP` dataset: `primary_interval` `1m` or `3m`, `context_intervals` `5m` + `15m`, micro refinement where applicable, immediate-continuation / very short `label_horizon_family`
- cost and slippage model profiles are selected per scope through the unified config system

---

## Rules

### 1. Temporal correctness
No future leakage across training / validation / test splits.

### 2. Scope-family rows
Rows should support shared training infrastructure across symbols within a `model_scope`. Rows from `SWING`, `SCALP`, and `AGGRESSIVE_SCALP` must not be mixed into one supervised dataset or one universal training target.

### 3. Symbol balance matters
Do not let a few high-frequency symbols dominate silently.

### 4. Unresolved rows stay out
Unresolved or invalid labels should not silently join strict supervised training.

### 5. Split by time first
Do not random-shuffle across time in a way that breaks evaluation realism.

### 6. Preserve lineage
Every row should be traceable back to source versions.

### 7. Runtime simulation lineage
Dataset manifests must include the runtime simulation profile/version and adapter lineage used to derive labels. Replay and Monte Carlo run IDs should be preserved when used.

---

## Symbol Balancing Rule

First-phase balancing should use one of two approved mechanisms:
- inverse-frequency sample weights by symbol, or
- capped per-symbol row contribution before training export

Default first-phase preference:
- preserve full row set
- attach inverse-frequency symbol weights
- only cap rows if a symbol massively dominates the corpus

This keeps each scope-specific multi-symbol model family from letting BTC/ETH-like symbols silently own the objective.

---

## Recommended Split Strategy

First-phase walk-forward convention:
- **6 folds**
- minimum train window: **12 months**
- validation window per fold: **2 months**
- optional short holdout/test tail after validation: **1 month**
- advance window by validation length

These are first-phase defaults and may be config-overridden.

Do not default to IID-style random train/test splits.

---

## Dataset Versioning Rule

Bump `dataset_family_version` when any of the following changes materially:
- `model_scope`, `primary_interval`, or `label_horizon_family` meaning
- feature schema meaning
- label interpretation meaning
- simulation family meaning
- symbol-universe policy
- runtime simulation profile/version lineage
- replay / Monte Carlo run ID preservation where used
- split family meaning

Do not bump for cosmetic filename or storage-path changes only.

---

## Partial Row Policy

If a row is incomplete:
- mark invalid
- preserve reason
- exclude from strict supervised training by default

“Explicitly allowed” means:
- a documented config flag exists
- the downstream training mode is designed for partial rows
- the run record preserves that exception

No silent partial-row inclusion.

---

## Failure / Fallback

If a row is incomplete:
- mark invalid
- preserve reason
- exclude from strict training unless explicitly allowed

Do not silently coerce partial rows into full rows.

---

## Config Surface

Key config families:
- runtime simulation profile/version lineage
- replay / Monte Carlo run ID preservation where used
- split family
- walk-forward windows
- allowed symbol universe
- row validity rules
- minimum label completeness rules
- balancing / weighting rules
- partial-row exception policy

---

## Interfaces

Upstream:
- `pipeline/features.md`
- `pipeline/labels.md`

Downstream:
- `pipeline/model.md`
- `pipeline/evaluation.md`

---

## Test Requirements

Minimum dataset tests:
- no train/test temporal leakage
- unresolved labels excluded correctly
- row lineage preserved
- symbol weighting reproducible
- walk-forward folds reproducible
- dataset-family bump triggers behave correctly

---

## Final Position

Dataset quality is not just “enough rows.”
It is temporally valid, lineage-valid, and evaluation-valid row construction.
