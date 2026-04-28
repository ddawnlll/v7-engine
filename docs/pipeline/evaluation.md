# Pipeline Evaluation

**Intended path:** `docs/v7/pipeline/evaluation.md`

## Purpose

Defines how V7 measures model and system quality.

It answers:

> Given models, calibrated outputs, policies, and outcomes, how should V7 decide whether quality is improving or regressing?

---

## In Scope

- walk-forward evaluation
- forward simulation evaluation
- symbol/regime breakdowns
- calibration quality
- no-trade quality
- promotion criteria
- baseline policy

---

## Out of Scope

- training implementation details
- broker execution plumbing
- dashboard implementation
- monitoring alert transport

---

## Core Decision

V7 evaluation is **economic-quality-first**.

That means the system is not judged only by:
- accuracy
- confidence
- hit rate

It must also be judged by:
- expectancy / realized R
- no-trade quality
- calibration quality
- path quality
- regret-aware comparative behavior

Evaluation is per `model_scope`. `SWING`, `SCALP`, and `AGGRESSIVE_SCALP` each require separate evaluation reports, configured metrics/gates, and promotion evidence. Do not promote one scope because another scope passed evaluation.

---

## Inputs

- trained artifacts
- calibration artifacts
- policy behavior
- replay outcomes
- live/paper outcomes where available
- evaluation config

---

## Outputs

Evaluation should produce:

- global quality metrics
- walk-forward summaries
- symbol breakdowns
- regime breakdowns
- no-trade quality metrics
- calibration metrics
- promotion / non-promotion decision support

---

## Walk-Forward Family

Evaluation uses the same first-phase walk-forward defaults as dataset construction:
- **6 folds**
- minimum train window: **12 months**
- validation window: **2 months**
- optional holdout tail: **1 month**

Dataset owns fold construction.
Evaluation owns fold consumption and interpretation.

---

## Rules

### 1. Forward realism first
Prefer walk-forward and forward-style evaluation over IID shortcuts.

### 2. No-trade is part of quality
A model that forces too many bad trades is not good just because directional hit rate looks fine.

### 3. Calibration is measured, not assumed
Confidence without reliability evidence is not enough.

### 4. Symbol/regime breakdowns are mandatory
A global metric can hide severe concentration of failure.

### 5. Replay and live should stay comparable
Do not create incompatible evaluation languages.

---

## Recommended Metric Families

Minimum first-phase families by `model_scope`:
- net expectancy / realized R after cost by scope
- stop-first rate by scope
- short-side expectancy by scope
- average and distributional regret
- no-trade correctness / no-trade quality by scope
- calibration error
- confidence bucket quality
- path quality summaries
- suppression / skip quality
- symbol-side harmful cohort by scope
- symbol and regime slices

### Ablation / Measurement Guidance

First-phase evaluation should include interval-view ablation within each scope to justify complexity, for example:
- `SWING`: compare **4h-only** vs **4h + 1d** vs **4h + 1d + 1h**
- `SCALP`: compare **15m-only** vs **15m + 1h** vs **15m + 1h + 5m**
- `AGGRESSIVE_SCALP`: compare the configured micro primary view against 5m/15m context variants

A refinement interval must prove its value via evaluation, not assumption.

---

## Promotion Gate

Promotion should never rely on a single scalar.

Minimum promotion gate should be config-driven and include:
- realized-R quality threshold
- no-trade quality threshold
- calibration quality threshold
- symbol/regime stability threshold
- no critical safety regression

Threshold values live in config, not hardcoded in this document.

---

## Baseline Policy

Evaluation compares candidates against:
1. the current promoted baseline model family for the same `model_scope`
2. the last accepted evaluation baseline for the same scope and evaluation family

When a candidate is promoted:
- it becomes the new promoted baseline
- the previous promoted baseline remains retained for historical comparison according to artifact retention policy

This keeps baseline transitions explicit.

---

## Replay vs Live Evidence Rule

Replay-only evidence may justify:
- candidate continuation
- deeper review
- paper deployment

Promotion to live-eligible authority should not rely on replay alone when live or paper evidence is part of the release policy.
The exact release gate remains config-driven, but replay-only promotion should not be assumed sufficient by default.

---

## Failure / Fallback

If an evaluation slice is incomplete:
- mark incomplete
- preserve reason
- do not treat it as normal evidence

---

## Config Surface

Key config families:
- evaluation family
- walk-forward windows
- promotion thresholds
- minimum coverage rules
- slice breakdown rules
- baseline retention rules
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

Minimum evaluation tests:
- walk-forward split integrity
- calibration metric correctness
- no-trade metric correctness
- symbol/regime slicing reproducibility
- incomplete slice handling
- baseline replacement logic works

---

## Final Position

Evaluation is where V7 proves that its economic claims are real.
If evaluation is weak, promotion becomes storytelling instead of evidence.
