
# Phase 8 — Evaluation & Monitoring (Planned)

**Status:** Planned
**Owner:** Evaluation / observability track
**Last updated:** 2026-04-24
**Delivery status:** Not started

---

## 1. Purpose

This phase proves whether V7 is actually good, stable, and observable enough to promote further.

It solves the problem that a system can now run, but still may not be economically good, calibration-safe, or operationally trustworthy.

---

## 2. What Carried Over / What Must Stay Stable

The following are already implemented / must remain stable:

- [x] simulation truth exists
- [x] baseline candidate exists
- [x] calibration/policy surfaces exist
- [x] runtime lifecycle objects are created
- [x] evaluation and monitoring docs already define the quality families

This phase builds on top of these. Do not regress them.

---

## 3. Background & Motivation

Without this phase:
- promotion becomes subjective
- timing extension usefulness stays unknown
- drift remains invisible
- no-trade quality remains unproven
- baseline comparisons remain weak

This phase turns V7 into an evidence-driven system.

---

## 4. Current Failure State / Known Blockers

The current state has the following known issues:

- `walk-forward evaluation outputs` = may not yet exist
- `baseline comparison` = may not yet exist
- `calibration quality monitoring` = may not yet be live
- `feature drift monitoring` = may not yet exist
- `timing extension usefulness evidence` = may not yet exist

---

## 5. Workstream A — Evaluation Core

**Status:** New

### Problem / Goal

Implement walk-forward and comparative evaluation around the baseline candidate and later candidates.

### Default promotion thresholds

First implementation defaults:
- candidate mean realized-R must improve over baseline by at least `+0.10`
- candidate calibration error must not worsen by more than `0.01`
- candidate no-trade correctness must not degrade by more than `1.0%`
- no critical safety regression is allowed

These are starting config defaults, not final permanent policy.

### Implementation Tasks

- [ ] Implement walk-forward evaluation run flow
- [ ] Implement baseline vs candidate comparison
- [ ] Implement interval-view ablation (e.g., 4h-only vs 4h+1d vs 4h+1d+1h)
- [ ] Implement symbol/regime slice reporting
- [ ] Implement no-trade quality reporting

### Acceptance Criteria

- [ ] candidate vs baseline comparison exists
- [ ] 1h refinement value can be proved via ablation
- [ ] no-trade quality is measurable
- [ ] symbol/regime slices are available

---

## 6. Workstream B — Monitoring Core

**Status:** New

### Problem / Goal

Measure post-run and post-deployment lifecycle quality.

### Baseline ownership rule

Monitoring baselines are updated when a candidate becomes **evaluation-promotable**.
Retain:
- current promoted baseline
- immediately previous promoted baseline

Default retention:
- at least one full evaluation cycle
- recommended minimum 30 days of retained comparability metadata

### Implementation Tasks

- [ ] Implement confidence / expected-R distribution monitoring
- [ ] Implement fallback/degraded-rate monitoring
- [ ] Implement actionability vs execution-eligibility gap monitoring
- [ ] Implement outcome finality lag monitoring

### Acceptance Criteria

- [ ] lifecycle health signals exist
- [ ] fallback/degradation are measurable
- [ ] outcome lag is measurable

---

## 7. Workstream C — Drift & Timing Evidence

**Status:** New

### Problem / Goal

Measure whether feature drift and timing extension signals are operationally meaningful.

#### 7.1 Feature drift defaults

```python
continuous_feature_drift = "PSI"
missingness_shift = "absolute_rate_delta"
symbol_mix_shift = "total_variation_distance"
```

**Rationale:**
- shared multi-symbol model quality can decay invisibly without drift measurement

#### 7.2 Timing usefulness rule

```python
min_windows = 3
min_samples_per_state = 500
required_realized_r_gap = 0.25
```

A move from advisory-only to timing hard-gate is allowed only if:
- at least 3 consecutive evaluation windows agree
- each relevant timing state has enough samples
- `CHASING` or `MISSED` underperform `READY_NOW` by at least `0.25R` on average
- coverage loss stays within configured tolerance

### Acceptance Criteria

- [ ] feature drift metrics exist
- [ ] timing usefulness metrics exist
- [ ] timing gating can remain off or be justified by evidence later

---

## 8. Workstream D — Test Coverage

**Status:** New
**Required before:** release-readiness assessment

### 8.1 Evaluation tests

- [ ] walk-forward integrity test
- [ ] baseline comparison test
- [ ] no-trade metric test

### 8.2 Monitoring tests

- [ ] fallback/degradation aggregation test
- [ ] actionability vs execution-eligibility gap test
- [ ] outcome lag metric test

### 8.3 Drift / timing tests

- [ ] PSI-style feature drift aggregation test
- [ ] timing usefulness aggregation test
- [ ] baseline update logic test

---

## 9. Workstream E — Pre-Run / Pre-Deploy Audit Checklist

**Status:** New
**Must complete before:** Phase 9 deployment safety/release

### 9.1 Baseline audit

- [ ] verify promoted baseline reference exists
- [ ] verify previous baseline retention works

### 9.2 Evaluation audit

- [ ] verify promotion gate metrics are computed from real outputs
- [ ] verify incomplete slices do not masquerade as healthy evidence

### 9.3 Monitoring audit

- [ ] verify timing-extension evidence is visible
- [ ] verify feature drift evidence is visible
- [ ] verify kill-switch readiness metrics can be consumed later

---

## 10. Combined Implementation Order

1. Complete Workstream A — Evaluation Core
2. Implement Workstream B — Monitoring Core
3. Apply Workstream C — Drift & Timing Evidence
4. Run Workstream E — Pre-Run Audit
5. Implement Workstream D — Test Coverage
6. Execute evaluation/monitoring suite
7. Evaluate results against acceptance criteria

### Acceptance Criteria for First Combined Run

- [ ] candidate vs baseline evaluation works
- [ ] no-trade, calibration, and slice metrics are present
- [ ] lifecycle monitoring signals are present
- [ ] timing usefulness can be assessed empirically

---

## 11. Definition of Done

### 11.1 Evaluation layer

- [x] evaluation semantics are documented
- [ ] walk-forward evaluation exists
- [ ] baseline comparison exists
- [ ] no-trade quality reporting exists

### 11.2 Monitoring layer

- [ ] lifecycle health signals exist
- [ ] fallback/degradation signals exist
- [ ] outcome lag monitoring exists

### 11.3 Candidate health

- [ ] feature drift is measurable
- [ ] timing usefulness is measurable
- [ ] promotion evidence is no longer subjective
- [ ] baseline update logic is explicit

### 11.4 Test layer

- [ ] evaluation tests pass
- [ ] monitoring tests pass
- [ ] drift/timing tests pass

---

## 12. What Phase 9 Inherits

### 12.1 Capability expansion themes

- candidate vs baseline evidence
- lifecycle monitoring
- timing usefulness evidence
- drift visibility
- promotion inputs

### 12.2 Phase Boundary

- Phase 9 is deployment safety and release-readiness work.
- Phase 8 is the prerequisite.
- Do not start Phase 9 work until Phase 8 definition of done is fully satisfied.

---

## 13. Compact Mental Model

### 13.1 Phase Relationships

- Phase 7: runtime flow became real
- Phase 8: quality and drift become measurable
- Phase 9: release safety becomes enforceable
- Post-Phase 9: broader iteration and optimization begin

### 13.2 Key Takeaway

A working system is not yet a trustworthy system.
This phase is where V7 earns evidence, not just functionality.
