# Pipeline Evaluation — Mode-Aware, Regime-Aware

**Intended path:** `docs/v7/pipeline/evaluation.md`

## Purpose

Defines how V7 measures model and system quality — **per mode scope with regime breakdowns**.

It answers:

> Given hybrid model artifacts, calibrated outputs, policy behavior, and outcomes (per mode), how should V7 decide whether quality is improving or regressing?

---

## Core Decision

V7 evaluation is **economic-quality-first** and **mode-aware**.
The system is not judged only by:

- accuracy
- confidence
- hit rate

It is judged by:

- realized R (per mode)
- expectancy
- regret
- no-trade quality
- calibration quality
- regression reliability
- path quality
- symbol/regime stability
- safety behavior
- **mode comparison quality**

---

## Inputs

- trained model artifacts (per mode)
- calibration artifacts (per mode)
- policy behavior (per mode, including regime modifiers)
- replay outcomes
- paper/live outcomes where available
- `DecisionEvent`
- `TradeOutcome`
- evaluation config

---

## Outputs

Evaluation produces (**per mode scope**):

- global quality metrics
- walk-forward summaries
- classification metrics
- regression metrics
- economic metrics
- no-trade quality metrics
- calibration metrics
- symbol breakdowns
- regime breakdowns
- promotion/non-promotion support

---

## Walk-Forward Family

First-phase defaults (per mode):

- 6 folds
- minimum train window: 12 months
- validation window: 2 months
- optional holdout tail: 1 month

Dataset owns fold construction. Evaluation owns fold consumption and interpretation.

---

## Metric Families

### Economic metrics (per mode)

- realized R
- net expectancy
- profit factor
- max drawdown
- average trade R
- cost-adjusted R
- regret distribution
- saved-loss / missed-opportunity quality

### Classification metrics (per mode)

- action accuracy where meaningful
- precision/recall by action
- no-trade classification quality
- confusion matrix for `LONG_NOW`, `SHORT_NOW`, `NO_TRADE`
- action probability bucket quality

### Regression metrics (per mode)

- MAE/RMSE for expected R heads
- sign correctness for expected R
- predicted-R bucket vs realized-R average
- adverse-pressure error
- cost-adjusted expectancy error
- symbol/regime regression breakdowns

### Calibration metrics (per mode)

- reliability error
- confidence bucket behavior
- no-trade calibration quality
- forward-period stability

### Regime-aware metrics

- realized-R by regime bucket
- no-trade quality by regime
- action distribution by regime
- decision margin by regime
- regime stability: consistency of metrics across consecutive same-regime windows

---

## No-Trade Quality

No-trade quality must measure:

- correct skip
- saved loss
- missed opportunity
- over-suppression
- under-suppression

A model that avoids all trades may look safe but is not automatically good.

---

## Ablation Requirement

First-phase evaluation should include:

- **per-mode ablation:** SWING only, SCALP only, AGGRESSIVE_SCALP only
- interval-view ablation per mode:
  - primary only
  - primary + context
  - primary + context + refinement
- classifier-only policy vs hybrid policy (per mode)
- probability gate only vs probability + expected-R gate

Refinement intervals must prove value through evidence, not assumption.

---

## Promotion Gate (Per Mode)

Promotion must never rely on a single scalar.

Minimum gate families:

- realized-R quality threshold
- no-trade quality threshold
- calibration quality threshold
- regression reliability threshold
- symbol/regime stability threshold
- no critical safety regression
- no unacceptable portfolio/risk suppression regression

Threshold values live in config.

---

## Replay vs Live Evidence Rule

Replay-only evidence may justify:

- candidate continuation
- deeper review
- paper deployment

Live-eligible authority should not rely on replay alone when release policy requires paper/live evidence.

---

## Baseline Policy

Evaluation compares candidates against:

1. current promoted baseline model family (per mode)
2. last accepted evaluation baseline for the same evaluation family

When a candidate is promoted, it becomes the new promoted baseline and the previous baseline is retained according to artifact policy.

---

## Failure / Fallback

If a slice is incomplete:

- mark incomplete
- preserve reason
- do not treat it as normal evidence

If regression evidence is missing or unreliable:

- degrade the affected evaluation family explicitly
- do not pretend the hybrid model is fully evaluated

---

## Config Surface

Key config families:

- evaluation family
- walk-forward windows
- promotion thresholds
- regression reliability thresholds
- minimum coverage rules
- slice breakdown rules
- baseline retention
- replay vs live evidence policy

---

## Interfaces

Upstream:

- `pipeline/model.md`
- `pipeline/calibration.md`
- `pipeline/policy.md`
- `contracts/trade_outcome.md`

Downstream:

- promotion decisions
- monitoring baselines
- roadmap decisions

---

## Test Requirements

Minimum tests:

- walk-forward split integrity
- economic metric correctness
- classification metric correctness
- regression metric correctness
- calibration metric correctness
- no-trade metric correctness
- symbol/regime slicing reproducibility
- incomplete slice handling
- baseline replacement logic
- **regime-aware metric correctness**
- **per-mode metric isolation**

---

## Final Position

Evaluation is where V7 proves that its profitability claims are real. Hybrid modeling is useful only if classification, regression, calibration, regime awareness, and policy together improve economic evidence — independently per mode scope.
