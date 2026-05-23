# Pipeline Model — Mode-Centric

**Intended path:** `docs/v7/pipeline/model.md`

## Purpose

Defines the first-phase V7 model family and output surface — **per mode scope**.

It answers:

> Given a valid V7 dataset for a specific mode, what learned model family should V7 train first, and what outputs should it produce?

---

## Core Decision

First-phase V7 is an **XGBoost-first hybrid supervised decision model per mode scope**.

This means:

- XGBoost remains the default first model family (trained independently per mode)
- action selection is classification-first
- economic quality is regression-first
- both outputs are exposed as first-class decision surfaces
- runtime ownership stays outside the model
- **do not train one artifact across incompatible modes**

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

- **one artifact bundle per mode scope** (SWING, SCALP, AGGRESSIVE_SCALP)
- shared multi-symbol model family within each mode
- no per-symbol model families in first phase
- **SWING mode:** primary 4h, context 1d, refinement 1h
- **SCALP mode:** primary 1h, context 4h, refinement 15m
- **AGGRESSIVE_SCALP mode:** primary 15m, context 1h, refinement 5m
- target universe up to 60 symbols
- one fused decision surface per atomic request

---

## Inputs

- dataset rows from `pipeline/dataset.md` (mode-scoped)
- shared feature matrix
- mode-specific classification targets
- mode-specific regression targets
- feature schema version
- mode-specific label interpretation version
- training config

---

## Output Surface (Per Mode)

Each mode's model artifact should expose:

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

- `model_scope` (SWING | SCALP | AGGRESSIVE_SCALP)
- feature schema version
- label version (mode-specific)
- model family version
- target family version
- training dataset version
- calibration requirement flag

---

## Recommended Implementation Shape

First phase may use separate XGBoost models per target head, **per mode**:

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

1. **Mode-specific models:** each mode trains its own artifact bundle. Do not train one artifact across incompatible scopes.
2. Shared features within mode: no per-symbol families in first phase.
3. Hybrid output first: classification and regression surfaces are both first-class.
4. Compact artifact surface: outputs must stay calibratable and policy-wrappable.
5. Stable lineage: every artifact is versioned and traceable.
6. No hidden runtime semantics: the model recommends; runtime decides execution eligibility.
7. No regression-only decisioning: regression supports economic gates; policy still compares calibrated action evidence.
8. No raw-score trust: calibration must distinguish raw and calibrated surfaces.

---

## XGBoost Clarification

XGBoost is not a regression-only algorithm.

V7 may use:

- `XGBClassifier` for action and success probabilities
- `XGBRegressor` for expected R, drawdown, and economic targets

The term **XGBoost-first** means model-family preference, not target-type restriction.

---

## Early Stopping Policy

First-phase training should use (per mode):

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

## Artifact Publishing Flow (Per Mode)

Training may produce (per mode scope):

- candidate artifacts
- rejected artifacts
- promotable artifacts

Successful training may publish a candidate artifact.
Promotion is controlled by evaluation and release policy per mode.

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

- training smoke test (per mode)
- inference schema parity
- artifact load test
- classification output exists and is stable
- regression output exists and is stable
- no-trade output exists
- early stopping path works
- candidate vs promotable states stay distinct
- missing regression head degrades explicitly
- scope mismatch cannot load incompatible artifact

---

## Final Position

The first V7 model should be boring, shared (within mode), measurable, and hybrid. Its job is not architecture novelty. Its job is to produce reliable action probabilities and economic-quality estimates for policy to evaluate — independently for each mode scope.
