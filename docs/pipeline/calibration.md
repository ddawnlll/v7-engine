# Pipeline Calibration

**Intended path:** `docs/v7/pipeline/calibration.md`

## Purpose

Defines how V7 turns raw model outputs into calibrated runtime-facing decision surfaces.

It answers:

> Given raw model scores, how should V7 produce confidence and related calibrated outputs that runtime can trust more safely?

---

## In Scope

- calibration inputs and outputs
- calibration artifact lineage
- calibration evaluation metrics
- first-phase calibration scope
- recalibration policy

---

## Out of Scope

- model training internals
- policy thresholds
- runtime execution gates
- portfolio/risk controls

---

## Core Decision

V7 uses explicit calibration as a first-class stage.

This matters because runtime cares about:
- confidence
- actionability
- no-trade quality

Raw model scores alone are not enough.

---

## First-Phase Scope

First phase calibration policy:
- **global-within-scope calibration first**
- calibration is per `model_scope` / artifact family
- no per-symbol calibration first phase
- no per-primary-interval calibration family inside a scope first phase
- symbol/regime breakdowns may be evaluated, but not automatically turned into separate calibration families

This keeps the system compact and auditable.

---

## Inputs

- raw model outputs
- validation data
- calibration config
- calibration family version

Validation labels/outcomes used for calibration inherit runtime simulation profile/version lineage from their source datasets or evaluation adapters. Calibration does not run simulation directly except by consuming outputs produced through the approved training/evaluation adapters.

---

## Outputs

A calibration artifact family should support:
- calibrated confidence
- calibration lineage, including relevant simulation profile/version lineage
- reliability metrics
- optional mapped score surfaces

---

## Rules

### 1. Runtime confidence matters
Because runtime may gate on confidence, calibration is first-class.

### 2. Global first
Do not jump to per-symbol calibration families in phase one.

### 3. Measured before trusted
No calibration family should be considered authoritative without explicit reliability evidence.

### 4. No hidden semantic changes
If calibration changes the meaning of exposed confidence, that must be versioned.

### 5. Scope-compatible only
A `SWING` calibration artifact must not be reused for `SCALP`, and a `SCALP` calibration artifact must not be reused for `AGGRESSIVE_SCALP`. Calibration artifacts are scope-compatible only; `scope_mismatch` must fail validation or degrade explicitly to a safe result.

---

## Calibration Split Rule

Calibration must use a **calibration-eligible validation slice** that is distinct from the training fit data.

It may share the same walk-forward family as evaluation, but:
- it must not be fit on the same rows used for core model fitting
- it must remain traceable as a separate calibration slice

This reduces calibration overfit risk.

---

## Recalibration Policy

A new calibration artifact should be produced:
- after each new candidate model family intended for evaluation
- when calibration-family config changes materially
- when explicit monitoring or evaluation thresholds indicate calibration drift beyond the configured limit

Do not silently keep stale calibration artifacts after a model family change.

---

## Global Calibration Sufficiency Rule

Global calibration remains first-phase default unless review shows persistent breakdown failure.

A move away from global calibration requires:
- repeated symbol or regime breakdown underperformance
- evidence across more than one evaluation slice
- an explicit new calibration family version

No ad hoc per-symbol calibration sprawl.

---

## Calibration Artifact Lifetime

Default rule:
- a calibration artifact is valid only for the scope-compatible model artifact family it was built for
- if the model artifact changes materially, a new calibration artifact is required
- stale calibration may be used only through an explicit fallback policy and must remain visible

---

## Calibration Metrics

Minimum monitored metrics:
- reliability / calibration error
- confidence bucket behavior
- no-trade calibration quality
- symbol and regime breakdowns for review
- forward-period stability

---

## Failure / Fallback

If calibration is unavailable or invalid:
- runtime must know
- result should surface `confidence_kind` correctly
- fallback use must be explicit

Never silently pretend raw confidence is calibrated confidence.

---

## Config Surface

Key config families:
- calibration family
- calibration split rules
- fallback behavior
- calibration publishing rules
- simulation profile/version lineage requirements
- recalibration thresholds

---

## Interfaces

Upstream:
- `pipeline/model.md`

Downstream:
- `pipeline/policy.md`
- `pipeline/evaluation.md`
- `contracts/analysis_result.md`

---

## Test Requirements

Minimum calibration tests:
- raw vs calibrated distinction preserved
- artifact load test
- reliability metric computation
- fallback visibility when calibration missing
- confidence kind surfaced correctly
- stale calibration is rejected or visibly downgraded

---

## Final Position

Calibration is what makes confidence safer to operationalize.
If confidence matters in runtime, calibration cannot remain informal.
