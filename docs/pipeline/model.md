# Pipeline Model

**Intended path:** `docs/v7/pipeline/model.md`

## Purpose

Defines the first-phase V7 model family and output surface.

It answers:

> Given a valid V7 dataset, what learned model family should V7 train first, and what outputs should it produce?

---

## Core Decision

First-phase V7 is an **XGBoost-first hybrid supervised decision model**.

This means:

- XGBoost remains the default first model family
- action selection is classification-first
- economic quality is regression-first
- both outputs are exposed as first-class decision surfaces
- runtime ownership stays outside the model

---

## Why Hybrid

Trading needs two questions answered at the same time:

1. **Classification:** Which action is most appropriate?
2. **Regression:** Is the action economically worth taking?

A high probability trade with poor expected R should be filtered.
A moderate probability trade with strong positive expected R may be valuable.

V7 therefore does not use pure classification or pure regression as the full decision engine.

---

## First-Phase Scope

- one shared multi-symbol model family
- no per-symbol model families in first phase
- primary decision interval: 4h
- higher-timeframe context: 1d
- refinement/timing context: 1h
- target universe up to 60 symbols
- one fused decision surface per atomic request

---

## Inputs

- dataset rows from `pipeline/dataset.md`
- shared feature matrix
- classification targets
- regression targets
- feature schema version
- label interpretation version
- training config

---

## Output Surface

The model artifact should expose:

### Classification outputs

- `p_long_now`
- `p_short_now`
- `p_no_trade`
- `classification_margin`
- optional per-action raw scores

### Regression outputs

- `expected_r_long`
- `expected_r_short`
- `expected_drawdown_long` or `expected_mae_long`
- `expected_drawdown_short` or `expected_mae_short`
- `expected_cost_adjusted_r_long`
- `expected_cost_adjusted_r_short`
- optional path-quality estimates

### Metadata outputs

- feature schema version
- label version
- model family version
- target family version
- training dataset version
- calibration requirement flag

---

## Recommended Implementation Shape

First phase may use separate XGBoost models per target head:

```text
classification:
  action_classifier or binary heads:
    LONG_NOW / SHORT_NOW / NO_TRADE

regression:
  long_expected_r_regressor
  short_expected_r_regressor
  long_adverse_pressure_regressor
  short_adverse_pressure_regressor
  optional cost_adjusted_expectancy_regressors
```

This keeps training, debugging, and evaluation simple.

Do not require a complex deep multi-task architecture in first phase.

---

## Rules

1. Shared model first: no per-symbol families in first phase.
2. Hybrid output first: classification and regression surfaces are both first-class.
3. Compact artifact surface: outputs must stay calibratable and policy-wrappable.
4. Stable lineage: every artifact is versioned and traceable.
5. No hidden runtime semantics: the model recommends; runtime decides execution eligibility.
6. No regression-only decisioning: regression supports economic gates; policy still compares calibrated action evidence.
7. No raw-score trust: calibration must distinguish raw and calibrated surfaces.

---

## XGBoost Clarification

XGBoost is not a regression-only algorithm.

V7 may use:

- `XGBClassifier` for action and success probabilities
- `XGBRegressor` for expected R, drawdown, and economic targets

The term **XGBoost-first** means model-family preference, not target-type restriction.

---

## Early Stopping Policy

First-phase training should use:

- explicit validation folds from dataset split family
- early stopping enabled by default
- monitored validation objective per target head
- separate monitored metrics for classification and regression

Do not train to exhaustion by default.

---

## Hyperparameter Surface

Config should include at minimum:

- `max_depth`
- `n_estimators`
- `learning_rate`
- `min_child_weight`
- `subsample`
- `colsample_bytree`
- `reg_alpha`
- `reg_lambda`
- `early_stopping_rounds`
- target-specific objectives
- target-specific sample weighting

---

## Artifact Publishing Flow

Training may produce:

- candidate artifacts
- rejected artifacts
- promotable artifacts

Successful training may publish a candidate artifact.
Promotion is controlled by evaluation and release policy.

Failed or invalid runs must not publish promotable artifacts.

---

## Interfaces

Upstream:

- `pipeline/dataset.md`
- `pipeline/training.md`

Downstream:

- `pipeline/calibration.md`
- `pipeline/policy.md`
- `pipeline/evaluation.md`
- `contracts/analysis_result.md`

---

## Test Requirements

Minimum tests:

- training smoke test
- inference schema parity
- artifact load test
- classification output exists and is stable
- regression output exists and is stable
- no-trade output exists
- early stopping path works
- candidate vs promotable states stay distinct
- missing regression head degrades explicitly

---

## Final Position

The first V7 model should be boring, shared, measurable, and hybrid. Its job is not architecture novelty. Its job is to produce reliable action probabilities and economic-quality estimates for policy to evaluate.
