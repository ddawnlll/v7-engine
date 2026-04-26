
# Phase 5 — Model Baseline (Planned)

**Status:** Planned
**Owner:** Model training track
**Last updated:** 2026-04-24
**Delivery status:** Not started

---

## 1. Purpose

This phase trains the first shared V7 baseline model family and produces candidate artifacts.

It exists to prove that the V7 dataset can support a stable, shared, multi-symbol decision model before calibration and policy logic are layered on top.

---

## 2. What Carried Over / What Must Stay Stable

The following are already implemented / must remain stable:

- [x] dataset rows are intended to be leakage-safe
- [x] first-phase model family is documented as XGBoost-first
- [x] no-trade remains first-class in outputs

This phase builds on top of these. Do not regress them.

---

## 3. Background & Motivation

Starting with a simple shared baseline is deliberate.

The prior risk would be:
- deep architecture expansion too early
- per-symbol model fragmentation
- no candidate artifact discipline

The correct first approach is one boring shared baseline.

---

## 4. Current Failure State / Known Blockers

The current state has the following known issues:

- `baseline model family` = documented, not implemented
- `candidate artifact` = may not yet exist as a stable publishable state
- `training reproducibility` = may not yet be enforced
- `early stopping behavior` = may not yet be implemented

---

## 5. Workstream A — Baseline Trainer

**Status:** New

### Problem / Goal

Train one shared first-phase XGBoost-family baseline.

### Multi-output strategy

First implementation default:
- one **multiclass classifier** for `LONG_NOW`, `SHORT_NOW`, `NO_TRADE`
- one **scalar regressor** for `expected_r`

The classifier owns action probabilities.
The regressor owns expected-R estimation.
Do not start with three unrelated binary classifiers in the first baseline.

### Implementation Tasks

- [ ] Implement baseline trainer entrypoint
- [ ] Support one shared interval-aware, multi-view model family (4h + 1d + 1h fused, not averaged independently)
- [ ] Support multiclass action training
- [ ] Support expected-R regression training
- [ ] Emit stable model artifact metadata

### Acceptance Criteria

- [ ] first candidate model trains successfully
- [ ] output artifact loads for inference
- [ ] artifact metadata preserves lineage

---

## 6. Workstream B — Reproducibility & Early Stopping

**Status:** New

### Problem / Goal

Prevent unstable training behavior and unbounded overfitting.

### Early stopping defaults

First implementation default:
- classifier early stopping metric: `mlogloss`
- expected-R regressor early stopping metric: `rmse`

These may be config-overridden later, but phase-one implementation should not leave them undefined.

### Implementation Tasks

- [ ] Wire explicit seed / reproducibility controls
- [ ] Implement validation-based early stopping
- [ ] Wire the minimum hyperparameter surface
- [ ] Preserve training-run record for each attempt

### Acceptance Criteria

- [ ] early stopping works on validation slice
- [ ] hyperparameters are config-driven
- [ ] training runs are traceable and reproducible enough for review

---

## 7. Workstream C — Candidate Artifact Publishing

**Status:** New

### Problem / Goal

Separate successful training from promotable release authority.

#### 7.1 Candidate publishing

```python
status = "candidate"
```

**Rationale:**
- training success is not the same as live eligibility
- later phases need artifacts to calibrate/evaluate

#### 7.2 Promotion ownership

```python
promotable = False
```

The ownership rule is:
- Phase 5 produces **candidate** artifacts only
- Phase 8 may mark a candidate **evaluation-promotable**
- Phase 9 may mark an evaluation-promotable candidate **live-eligible**

### Acceptance Criteria

- [ ] successful training creates candidate artifacts only
- [ ] failed runs do not publish promotable artifacts
- [ ] publish vs promote is visible in run metadata

---

## 8. Workstream D — Test Coverage

**Status:** New
**Required before:** Phase 6 calibration

### 8.1 Training smoke tests

- [ ] small training run completes
- [ ] trained artifact can be loaded
- [ ] inference over sample rows works

### 8.2 Reproducibility tests

- [ ] fixed-seed repeatability sanity test
- [ ] early stopping path test
- [ ] hyperparameter config path test

### 8.3 Output validation

- [ ] multiclass action outputs exist
- [ ] expected-R regressor output exists
- [ ] candidate artifact metadata is preserved
- [ ] failed run does not publish promotable state

---

## 9. Workstream E — Pre-Run Audit Checklist

**Status:** New
**Must complete before:** first real candidate training run

### 9.1 Dataset audit

- [ ] verify training input dataset family version is recorded
- [ ] verify unresolved/invalid rows were excluded correctly

### 9.2 Hyperparameter audit

- [ ] verify config contains required hyperparameter surface
- [ ] verify early stopping metrics and rounds are set

### 9.3 Latency audit

- [ ] verify atomic inference target is recorded with a first implementation default (recommended p95 <= 50 ms on target serving worker)
- [ ] verify batch scan target is recorded with a first implementation default (recommended p95 <= 5 s for 60-symbol scan on target worker)

---

## 10. Combined Implementation Order

1. Complete Workstream A — Baseline Trainer
2. Implement Workstream B — Reproducibility & Early Stopping
3. Apply Workstream C — Candidate Artifact Publishing
4. Run Workstream E — Pre-Run Audit
5. Implement Workstream D — Test Coverage
6. Execute first candidate training run
7. Evaluate results against acceptance criteria

### Acceptance Criteria for First Combined Run

- [ ] one shared baseline candidate is trained
- [ ] artifact can load for inference
- [ ] early stopping and seed handling work
- [ ] candidate artifact lineage is visible

---

## 11. Definition of Done

### 11.1 Model layer

- [x] first-phase model family choice is documented
- [ ] baseline trainer exists
- [ ] candidate artifact emission exists

### 11.2 Artifact layer

- [ ] artifact metadata is preserved
- [ ] publish vs promote distinction exists
- [ ] failed runs do not create promotable state

### 11.3 Candidate health

- [ ] one baseline candidate trains successfully
- [ ] outputs are stable enough for calibration input
- [ ] multiclass + expected-R strategy is implemented explicitly

### 11.4 Test layer

- [ ] smoke tests pass
- [ ] reproducibility tests pass
- [ ] output validation tests pass

---

## 12. What Phase 6 Inherits

### 12.1 Capability expansion themes

- one trained baseline candidate
- reproducible training surface
- candidate artifact lineage
- explicit model-output strategy

### 12.2 Phase Boundary

- Phase 6 is calibration and policy work.
- Phase 5 is the prerequisite.
- Do not start Phase 6 work until Phase 5 definition of done is fully satisfied.

---

## 13. Compact Mental Model

### 13.1 Phase Relationships

- Phase 4: rows became valid
- Phase 5: baseline model is trained
- Phase 6: outputs become calibrated decisions
- Phase 7: runtime consumes them safely

### 13.2 Key Takeaway

Phase 5 is not about proving V7 is finished.
It is about proving the first shared model family can exist as a serious candidate.
