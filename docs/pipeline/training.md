# Pipeline Training

**Intended path:** `docs/v7/pipeline/training.md`

## Purpose

Defines the first-phase training flow for the V7 hybrid supervised model.

It answers:

> Given valid temporal datasets, how should V7 train classification and regression heads without leakage or promotion shortcuts?

---

## Core Decision

V7 training is **hybrid supervised training**.

It trains:

- classification heads for action selection
- regression heads for economic quality
- calibration artifacts for runtime-facing confidence

Training does not decide live execution eligibility. It produces candidate artifacts for evaluation.

---

## Training Diagram

```text
Canonical Market State
      ↓
Feature Engineering
      ↓
Simulation Truth
      ↓
Hybrid Labels
      ├── Classification labels
      └── Regression labels
      ↓
Temporal Dataset / Walk-Forward Folds
      ↓
XGBoost Hybrid Training
      ├── Classifier heads
      │   ├── P(LONG_NOW)
      │   ├── P(SHORT_NOW)
      │   └── P(NO_TRADE)
      └── Regressor heads
          ├── E[R | LONG_NOW]
          ├── E[R | SHORT_NOW]
          ├── expected adverse pressure
          └── cost-adjusted expectancy
      ↓
Calibration Fit
      ↓
Policy Evaluation
      ↓
Candidate Artifact
      ↓
Walk-Forward / Economic Evaluation
      ↓
Promotion Review
```

---

## Training Inputs

- train split
- validation split
- optional holdout/test tail
- feature schema version
- classification targets
- regression targets
- sample weights
- training config

---

## Training Outputs

- model artifact
- classification head metrics
- regression head metrics
- calibration artifact or calibration requirement record
- feature importance summaries
- target coverage summaries
- training lineage record
- candidate publish status

---

## Rules

1. Training rows must be temporally valid.
2. Calibration rows must not be the same rows used for core model fitting.
3. Classification and regression heads may use different valid row subsets.
4. Sample weighting must be explicit and reproducible.
5. Early stopping is default.
6. No unresolved or invalid labels in strict training.
7. No candidate promotion during training.
8. Failed target heads degrade explicitly; they are not silently omitted.

---

## Objective Families

### Classification objectives

- action multi-class objective, or
- separate binary objectives for long, short, and no-trade

The chosen family must be config-declared and reflected in artifact metadata.

### Regression objectives

Approved first-phase regression objectives include:

- squared error for expected R
- absolute error for robust expected R variants
- quantile-style objectives where supported and explicitly versioned

Target clipping or transformation must be versioned.

---

## Validation During Training

Training should track:

- classification log loss / AUC / precision by action
- no-trade classification quality
- regression MAE/RMSE by target
- expected-R sign quality
- economic monotonicity checks by predicted bucket
- symbol/regime coverage

Training metrics are not promotion evidence by themselves. They are candidate-quality diagnostics.

---

## Config Surface

Key config families:

- model family
- target head enablement
- objectives
- hyperparameters
- early stopping
- sample weights
- target clipping/transformation
- calibration split
- artifact publishing rules

---

## Interfaces

Upstream:

- `pipeline/dataset.md`
- `pipeline/model.md`

Downstream:

- `pipeline/calibration.md`
- `pipeline/evaluation.md`

---

## Test Requirements

Minimum tests:

- train classifier heads
- train regression heads
- head-specific row filtering works
- early stopping works
- calibration split is separate
- artifact metadata includes all target heads
- failed head handling is explicit

---

## Final Position

V7 training should be simple, temporal, and evidence-generating. It trains the hybrid model; it does not prove profitability by itself.
