# Pipeline Calibration

**Intended path:** `docs/v7/pipeline/calibration.md`

## Purpose

Defines how V7 turns raw model outputs into calibrated runtime-facing decision surfaces.

It answers:

> Given raw classification and economic model outputs, how should V7 produce confidence and score surfaces that policy can use safely?

---

## Core Decision

Calibration is a first-class stage.

Raw model scores are not enough because runtime and policy may gate on confidence and actionability.

---

## First-Phase Scope

- global calibration first
- no per-symbol calibration family in first phase
- no per-regime calibration family in first phase
- symbol/regime breakdowns are evaluated, not automatically split into calibration families

---

## Inputs

- raw classification outputs
- raw regression outputs where relevant
- validation/calibration-eligible data
- calibration config
- calibration family version

---

## Outputs

Calibration artifacts should support:

- calibrated action probabilities
- calibrated confidence
- confidence kind
- reliability metrics
- calibration lineage
- mapped score surfaces where approved

---

## Classification Calibration

Primary calibration applies to:

- `p_long_now`
- `p_short_now`
- `p_no_trade`
- decision confidence
- action margin confidence

Runtime-facing confidence must clearly identify whether it is:

- raw
- calibrated
- degraded
- unavailable

---

## Regression Reliability

Regression heads are not calibrated in the same way as probabilities, but their reliability must be measured.

First-phase regression reliability checks include:

- predicted expected-R bucket vs realized average R
- sign correctness by bucket
- error distribution by symbol/regime
- adverse-pressure prediction quality
- cost-adjusted expectancy bucket quality

If regression reliability is weak, policy must be able to degrade or ignore the affected economic gate explicitly.

---

## Calibration Split Rule

Calibration must use a calibration-eligible validation slice distinct from core model fitting rows.

It may share the same walk-forward family as evaluation, but:

- it must not be fit on the same rows used for model fitting
- it must remain traceable as a separate calibration slice

---

## Recalibration Policy

Produce a new calibration artifact when:

- a new candidate model family is intended for evaluation
- calibration config changes materially
- monitoring detects calibration drift beyond configured limit
- classification output semantics change

Do not silently keep stale calibration after a model-family change.

---

## Rules

1. Runtime confidence matters.
2. Raw scores are not calibrated confidence.
3. Global first.
4. Reliability is measured before trusted.
5. Calibration meaning changes are versioned.
6. Regression reliability issues degrade economic gates explicitly.

---

## Config Surface

Key config families:

- calibration family
- calibration split rules
- fallback behavior
- classification calibration method
- regression reliability thresholds
- publishing rules
- recalibration thresholds

---

## Interfaces

Upstream:

- `pipeline/model.md`
- `pipeline/training.md`

Downstream:

- `pipeline/policy.md`
- `pipeline/evaluation.md`
- `contracts/analysis_result.md`

---

## Test Requirements

Minimum tests:

- raw vs calibrated distinction preserved
- calibration artifact load test
- reliability metric computation
- confidence kind surfaced correctly
- fallback visibility when calibration missing
- stale calibration rejected or visibly downgraded
- regression reliability degradation is visible

---

## Final Position

Calibration makes confidence safer to operationalize. In V7, it must cover action probabilities directly and economic regression reliability indirectly through measured bucket behavior.
