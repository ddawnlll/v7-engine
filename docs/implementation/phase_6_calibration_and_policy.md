
# Phase 6 — Calibration & Policy (Planned)

**Status:** Planned
**Owner:** Decision-surface track
**Last updated:** 2026-04-24
**Delivery status:** Not started

---

## 1. Purpose

This phase turns raw model outputs into calibrated, policy-shaped decision surfaces that match `AnalysisResult`.

It exists because runtime should not consume raw model scores directly as if they were final economic decisions.

---

## 2. What Carried Over / What Must Stay Stable

The following are already implemented / must remain stable:

- [x] one baseline candidate model exists from Phase 5
- [x] confidence and expected-R surfaces are already core V7 semantics
- [x] no-trade must remain first-class
- [x] timing extension remains advisory-first in first phase

This phase builds on top of these. Do not regress them.

---

## 3. Background & Motivation

Without this phase:
- confidence remains uncalibrated
- raw scores leak into runtime
- no-trade semantics become weak fallback
- timing fields remain undefined in production flow

This phase creates the compact decision layer V7 actually wants.

---

## 4. Current Failure State / Known Blockers

The current state has the following known issues:

- `calibration artifact` = may not yet exist
- `confidence_kind` = may not yet be operationally truthful
- `policy selection` = may not yet choose long/short/no-trade explicitly
- `entry_readiness` = may not yet be computed anywhere

---

## 5. Workstream A — Calibration Artifact

**Status:** New

### Problem / Goal

Produce calibration artifacts per `model_scope` that map scope-compatible model outputs into safer confidence surfaces.

### Calibration-slice rule

Default fold usage:
- training window: model fit
- first half of validation window: early stopping / model selection
- second half of validation window: calibration fit
- optional holdout tail: untouched for later evaluation

Do not fit calibration on the same rows used to fit the model core.

### Recalibration rule

Recalibration is required when:
- model artifact family changes
- calibration config changes materially
- Phase 8 monitoring shows calibration drift beyond threshold

### Implementation Tasks

- [ ] Implement calibration training flow
- [ ] Implement calibration artifact loading
- [ ] Preserve calibration lineage
- [ ] Support raw-confidence fallback visibility

### Acceptance Criteria

- [ ] calibration artifact exists for the baseline candidate
- [ ] raw vs calibrated confidence remains explicit
- [ ] stale/missing calibration can be detected
- [ ] calibration artifact is scope-compatible and rejected on `scope_mismatch`

---

## 6. Workstream B — Decision Policy Core

**Status:** New

### Problem / Goal

Turn calibrated surfaces into normalized decisions.

### Conflict rule

First implementation rule:
- a directional trade is actionable only if **both**
  - confidence gate passes
  - expected-R gate passes
- if confidence passes but expected-R fails, select `NO_TRADE`
- if expected-R passes but confidence fails, select `NO_TRADE`
- review-only downgrade is allowed only if explicitly configured

### Implementation Tasks

- [ ] Implement long/short/no-trade selection
- [ ] Implement confidence gate
- [ ] Implement expected-R gate
- [ ] Implement tie-break/no-trade margin rules

### Acceptance Criteria

- [ ] `recommended_action` is explicit
- [ ] `NO_TRADE` is selected positively, not by accident
- [ ] confidence-only cannot override failed economic gate
- [ ] policy thresholds are selected per `model_scope` and no averaged scope outputs are used

---

## 7. Workstream C — Timing Advisory Surface

**Status:** New

### Problem / Goal

Compute the first-phase advisory timing fields without turning policy into a timing planner.

#### 7.1 Timing outputs

```python
entry_readiness
entry_valid_for_bars
```

**Rationale:**
- runtime and review need timing visibility
- first phase should keep timing bounded and advisory

#### 7.2 Timing derivation rule

Default bounded heuristic:
- `READY_NOW` if current price is inside entry zone and time sensitivity is not expiring-critical
- `WAIT` if current price is near but not yet inside preferred zone and `CAN_WAIT` is allowed
- `CHASING` if price has moved beyond the favorable side of the entry zone by configured chase distance
- `EXPIRING` if still near entry but `EXPIRING_SOON`
- `MISSED` if price is materially outside acceptable entry bounds or expected validity has collapsed
- `entry_valid_for_bars` uses bounded integer range `0–5`

### Acceptance Criteria

- [ ] `entry_readiness` can be emitted
- [ ] `entry_valid_for_bars` is bounded and valid
- [ ] timing outputs remain advisory-first

---

## 8. Workstream D — Test Coverage

**Status:** New
**Required before:** Phase 7 runtime integration

### 8.1 Calibration tests

- [ ] calibration artifact load test
- [ ] raw vs calibrated distinction test
- [ ] fallback visibility test

### 8.2 Policy tests

- [ ] long vs short vs no-trade selection test
- [ ] expected-R gate test
- [ ] confidence vs expected-R conflict test

### 8.3 Timing tests

- [ ] `entry_readiness` legality test
- [ ] `entry_valid_for_bars` bound test
- [ ] advisory-first behavior test

---

## 9. Workstream E — Pre-Run Audit Checklist

**Status:** New
**Must complete before:** runtime integration

### 9.1 Calibration audit

- [ ] verify calibration used a separate calibration-eligible slice
- [ ] verify calibration artifact is tied to the correct model family

### 9.2 Policy audit

- [ ] verify no-trade is explicitly selectable
- [ ] verify confidence vs expected-R conflict rule is documented in code/tests

### 9.3 Timing audit

- [ ] verify timing outputs are not treated as mandatory learned targets
- [ ] verify gating on timing is still disabled by default

---

## 10. Combined Implementation Order

1. Complete Workstream A — Calibration Artifact
2. Implement Workstream B — Decision Policy Core
3. Apply Workstream C — Timing Advisory Surface
4. Run Workstream E — Pre-Run Audit
5. Implement Workstream D — Test Coverage
6. Execute calibration/policy test suite
7. Evaluate results against acceptance criteria

### Acceptance Criteria for First Combined Run

- [ ] calibrated confidence surface exists
- [ ] policy emits valid long/short/no-trade decisions
- [ ] timing fields are present and bounded where applicable
- [ ] raw confidence is never silently mislabeled as calibrated

---

## 11. Definition of Done

### 11.1 Calibration layer

- [x] calibration semantics are documented
- [ ] calibration artifact exists
- [ ] calibration lineage exists

### 11.2 Policy layer

- [ ] explicit decision selection exists
- [ ] no-trade is explicit
- [ ] confidence + expected-R gating exists

### 11.3 Candidate health

- [ ] timing advisory surface exists without hard gating by default
- [ ] `AnalysisResult`-compatible surface can be produced
- [ ] calibration split and recalibration triggers are implemented

### 11.4 Test layer

- [ ] calibration tests pass
- [ ] policy tests pass
- [ ] timing tests pass

---

## 12. What Phase 7 Inherits

### 12.1 Capability expansion themes

- calibrated confidence
- normalized engine decision surface
- advisory timing fields
- policy-ready `AnalysisResult` semantics

### 12.2 Phase Boundary

- Phase 7 is portfolio/risk/runtime integration work.
- Phase 6 is the prerequisite.
- Do not start Phase 7 work until Phase 6 definition of done is fully satisfied.

---

## 13. Compact Mental Model

### 13.1 Phase Relationships

- Phase 5: candidate model exists
- Phase 6: scores become decisions
- Phase 7: runtime consumes decisions
- Phase 8: quality and drift are proven

### 13.2 Key Takeaway

This phase is where model outputs stop being “interesting numbers” and become actual decision surfaces the rest of V7 can consume.
