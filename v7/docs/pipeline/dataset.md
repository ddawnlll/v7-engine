# Pipeline Dataset — Mode-Centric

**Intended path:** `docs/v7/pipeline/dataset.md`

## Purpose

Defines how V7 assembles training and evaluation datasets from canonical state, features, simulation outputs, and labels — **per mode scope**.

It answers:

> How should V7 build temporally correct datasets for mode-specific hybrid supervised training and economic evaluation?

---

## Core Decision

A valid V7 dataset row contains:

- canonical state lineage
- feature row (shared across modes)
- **mode identifier**
- mode-specific classification labels
- mode-specific regression labels
- simulation lineage (mode-configured)
- version lineage

No row is valid without traceable upstream lineage.

---

## First-Phase Scope

- **datasets are mode-specific** (one dataset per mode scope)
- shared multi-symbol dataset within each mode
- **SWING:** primary 4h, context 1d, refinement 1h
- **SCALP:** primary 1h, context 4h, refinement 15m
- **AGGRESSIVE_SCALP:** primary 15m, context 1h, refinement 5m
- target universe up to 60 symbols
- initial rollout may subset symbols, but dataset design must not assume six-symbol permanence

---

## Inputs

- feature rows (shared)
- mode-specific normalized label records
- mode-specific simulation outputs
- mode identifier
- request/result/event/outcome lineage where relevant
- dataset config
- split config

---

## Outputs

A dataset row should minimally carry:

- **mode** (SWING | SCALP | AGGRESSIVE_SCALP)
- feature vector (shared)
- classification target fields (mode-specific)
- regression target fields (mode-specific)
- sample weights
- symbol
- primary interval (per mode)
- timestamp
- feature schema version
- label interpretation version (mode-specific)
- simulation family version
- dataset family version
- row validity status
- exclusion reason where applicable

---

## Target Families (Per Mode)

### Classification targets

- `best_action_label`
- `long_success_label`
- `short_success_label`
- `no_trade_quality_label`

### Regression targets

- `long_realized_r_net`
- `short_realized_r_net`
- `long_mae_r`
- `short_mae_r`
- `long_mfe_r`
- `short_mfe_r`
- `regret_r`
- `saved_loss_score`
- `missed_opportunity_score`
- optional mode-specific fields (e.g., `long_time_to_mfe_bars` for SCALP)
- optional clipped/normalized target variants

Regression targets may use clipping/winsorization, but target transformation must be versioned and reversible enough for evaluation interpretation.

---

## Rules

1. **Mode-specific datasets:** do not mix modes in one dataset. Each mode has its own dataset with mode-specific labels and simulation configs.
2. Temporal correctness: no future leakage across train/validation/test.
3. Shared-family rows: support one shared model family across symbols **per mode**.
4. Symbol balance matters: no silent dominance by high-row-count symbols.
5. Unresolved rows stay out of strict supervised training by default.
6. Ambiguous rows are explicit and excluded from hard action-classification training by default.
7. Split by time first, not IID random shuffle.
8. Preserve lineage for every row.
9. Classification and regression target availability are tracked separately.

---

## Symbol Balancing Rule

Approved first-phase mechanisms:

- inverse-frequency sample weights by symbol
- capped per-symbol row contribution before export

Default preference:

- preserve full row set
- attach inverse-frequency symbol weights
- cap only when a symbol massively dominates the corpus

---

## Recommended Split Strategy

First-phase walk-forward convention (per mode):

- 6 folds
- minimum train window: 12 months
- validation window per fold: 2 months
- optional holdout/test tail after validation: 1 month
- advance window by validation length

No IID-style random split for primary evaluation.

---

## Partial Target Policy

Rows may have valid classification targets but invalid regression targets, or the opposite.

Default behavior:

- strict model training uses only rows valid for the target head being trained
- row validity is head-specific
- excluded rows preserve exclusion reason
- no silent target imputation for labels

---

## Dataset Versioning Rule

Bump `dataset_family_version` when any of the following changes materially:

- feature schema meaning
- label interpretation meaning (per mode)
- simulation family meaning (per mode)
- target transformation policy
- symbol-universe policy
- split family meaning
- row validity policy

Do not bump for cosmetic filename or storage-path changes only.

---

## Config Surface

Key config families:

- split family
- walk-forward windows
- allowed symbol universe
- row validity rules
- classification target inclusion rules
- regression target inclusion rules
- balancing/weighting rules
- target clipping/transformation rules
- partial-row exception policy

---

## Interfaces

Upstream:

- `pipeline/features.md`
- `pipeline/labels.md`

Downstream:

- `pipeline/model.md`
- `pipeline/training.md`
- `pipeline/evaluation.md`

---

## Test Requirements

Minimum tests:

- no temporal leakage
- unresolved labels excluded correctly
- ambiguous rows handled correctly
- classification/regression validity tracked separately
- row lineage preserved
- mode field populated correctly
- symbol weighting reproducible
- walk-forward folds reproducible
- dataset-family version bump triggers work

---

## Final Position

Dataset quality is not just row count. V7 requires temporally valid, lineage-valid, target-valid row construction for both classification and regression heads — independently per mode scope.
