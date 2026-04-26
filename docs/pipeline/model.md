# Pipeline Model

**Intended path:** `docs/v7/pipeline/model.md`

## Purpose

Defines the first-phase V7 model family and training authority.

It answers:

> Given a valid V7 dataset, what learned model family should V7 train first, and what outputs should it produce?

---

## In Scope

- first-phase model family choice
- artifact outputs
- training target family
- shared-model policy
- model lineage requirements
- overfitting control
- publishing flow

---

## Out of Scope

- calibration rules
- decision policy rules
- portfolio/risk gates
- runtime orchestration
- broker execution logic

---

## Core Decision

First-phase V7 is **XGBoost-first**.

That means:
- start with compact, explicit, tabular-friendly learning
- do not begin with large deep architectures
- do not create per-symbol model families in first phase

---

## First-Phase Scope

- one shared interval-aware multi-view model family (not separate per-interval primary model families)
- primary decision interval: **4h**
- higher-timeframe context: **1d**
- first-phase refinement/timing context: **1h**
- 1h, 4h, and 1d are fused inside one model input or one shared model family, not treated as three independently averaged predictors
- target universe up to **60 symbols**

---

## Inputs

- dataset rows from `pipeline/dataset.md`
- feature schema version
- label interpretation version
- training config

---

## Outputs

The trained model family should expose a stable artifact surface for:
- long score
- short score
- no-trade score
- confidence-supporting surfaces
- expected-R-supporting surfaces where approved

The external contract is the result surface, not internal training details.

---

## Rules

### 1. Shared model first
Do not create one model per symbol in first phase.

### 2. Shared decision interval first
Do not create a separate primary model family per interval in first phase.

### 3. Stable artifact lineage
Every trained artifact must be versioned and traceable.

### 4. Compact output surface
Model output should remain small enough to calibrate, policy-wrap, and explain.

### 5. No hidden runtime semantics
The model may support runtime decisions, but runtime still owns execution.

---

## Early Stopping Policy

First-phase training should use:
- explicit validation folds from the dataset split family
- early stopping enabled by default
- monitored validation objective chosen per target family and documented in config

Do not train to exhaustion by default.

---

## Hyperparameter Surface

First-phase config should explicitly include at minimum:
- `max_depth`
- `n_estimators`
- `learning_rate`
- `min_child_weight`
- `subsample`
- `colsample_bytree`
- `reg_alpha`
- `reg_lambda`
- `early_stopping_rounds`

This document does not hardcode final values, but these parameters must be first-class config entries.

---

## Inference Latency Target

First-phase target:
- atomic inference should remain compatible with low-latency runtime use
- batch inference over the approved scan family should complete within the configured runtime SLO

Model training decisions must not ignore runtime latency requirements.

Latency SLO values belong in config, not hardcoded in the model document.

---

## Publishing Flow

Training may produce:
- candidate artifacts
- rejected artifacts
- promotable artifacts

Default rule:
- successful training may publish a **candidate** artifact
- promotion to runtime-eligible artifact is controlled by evaluation and release policy
- failed or invalid runs must not publish promotable artifacts

This keeps publish vs promote separate.

---

## Failure / Fallback

If a training run is invalid:
- do not publish a promotable artifact
- preserve the run record
- mark failure reason explicitly

No silent partial promotion.

---

## Config Surface

Key config families:
- model family
- hyperparameters
- training seed / reproducibility
- target family
- artifact publishing rules
- latency SLO references

---

## Interfaces

Upstream:
- `pipeline/dataset.md`

Downstream:
- `pipeline/calibration.md`
- `pipeline/evaluation.md`
- `contracts/analysis_result.md`

---

## Test Requirements

Minimum model tests:
- training smoke test
- inference schema parity
- artifact loading test
- deterministic run under fixed seed where applicable
- no-trade output exists and is stable
- early stopping path works
- candidate vs promotable publish states stay distinct

---

## Final Position

The first V7 model should be boring, shared, and measurable.
The job of phase one is not architecture novelty.
It is reliable economic decision surfaces.
