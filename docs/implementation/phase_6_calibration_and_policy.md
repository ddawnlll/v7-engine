# Phase 6 — Calibration, Expected-R Reliability & Policy (Planned)

**Status:** Planned  
**Owner:** Decision-surface track  
**Last updated:** 2026-05-23  
**Delivery status:** Not started

---

## 1. Purpose

Turn raw hybrid model outputs into calibrated, policy-shaped decision surfaces that match `AnalysisResult`.

Runtime must not consume raw classifier probabilities or raw expected-R values as final decisions.

---

## 2. Stable Rules

- Confidence must be calibrated or explicitly downgraded.
- Expected-R estimates must be reliability-reviewed before policy uses them aggressively.
- No-trade remains explicit.
- A directional trade needs both probability support and economic support.
- Timing extension remains advisory-first.

---

## 3. Workstream A — Classification Calibration Artifact

Produce calibration artifacts per `model_scope` for the action classifier.

Calibration-slice default:

- training window: model fit
- first half of validation window: early stopping / model selection
- second half of validation window: calibration fit
- optional holdout tail: untouched for evaluation

Calibration outputs:

- calibrated action probabilities
- calibrated confidence
- `confidence_kind`
- reliability metrics
- calibration lineage

### Acceptance Criteria

- [ ] calibration artifact exists.
- [ ] raw vs calibrated confidence is explicit.
- [ ] stale/missing calibration is detectable.
- [ ] calibration artifact is scope-compatible.

---

## 4. Workstream B — Expected-R Reliability Review

Expected-R regressors do not need probability calibration, but they do need reliability evidence.

Minimum review metrics:

- MAE / RMSE by fold
- signed bias by fold
- rank correlation between predicted expected-R and realized R
- bucketed realized-R by predicted-R bucket
- long/short separate quality
- symbol/regime slices

Reliability outputs:

- `expected_r_kind`
- `expected_r_reliability_grade`
- per-head error summaries
- fallback/downgrade reason if unreliable

### Acceptance Criteria

- [ ] expected-R reliability summary exists.
- [ ] unreliable expected-R can be downgraded visibly.
- [ ] policy can distinguish trusted vs degraded expected-R.

---

## 5. Workstream C — Decision Policy Core

Policy consumes:

- calibrated action probabilities
- confidence
- decision margin
- expected-R by action
- expected-R reliability state
- expected drawdown/adverse estimates where available
- policy config

First implementation rule:

A directional action is actionable only if:

- confidence gate passes
- action probability beats no-trade by configured margin
- expected-R gate passes
- drawdown/adverse gate passes if enabled
- expected-R surface is not degraded beyond configured tolerance

If confidence passes but expected-R fails: select `NO_TRADE`.

If expected-R passes but confidence fails: select `NO_TRADE`.

If long/short are too close: select `NO_TRADE`.

### Acceptance Criteria

- [ ] `recommended_action` is explicit.
- [ ] confidence-only cannot override failed economic gate.
- [ ] expected-R-only cannot override failed confidence gate.
- [ ] `NO_TRADE` is selected positively.

---

## 6. Workstream D — Timing Advisory Surface

Compute advisory fields:

```python
entry_readiness
entry_valid_for_bars
```

First phase bounded enum:

- `READY_NOW`
- `WAIT`
- `CHASING`
- `EXPIRING`
- `MISSED`

`entry_valid_for_bars` range: `0–5`.

Timing is policy-derived from score surfaces, entry-zone geometry, and simple bounded heuristics. It is not a first-phase learned primary target.

### Acceptance Criteria

- [ ] timing fields are emitted where applicable.
- [ ] values are bounded and legal.
- [ ] timing hard-gating remains disabled by default.

---

## 7. Workstream E — Test Coverage

Minimum tests:

- calibration artifact load
- raw vs calibrated confidence distinction
- missing/stale calibration fallback visibility
- expected-R reliability metrics
- expected-R degraded policy behavior
- long/short/no-trade selection
- confidence vs expected-R conflict
- no-trade positive selection
- timing legality and bounds

---

## 8. Pre-Run Audit

Before Phase 7:

- [ ] calibration used separate calibration-eligible rows
- [ ] expected-R reliability summary exists
- [ ] no-trade is explicitly selectable
- [ ] confidence vs expected-R conflict rules are test-covered
- [ ] raw expected-R cannot be treated as trusted when degraded
- [ ] timing hard gate is disabled by default

---

## 9. Definition of Done

- [ ] classifier confidence is calibrated or visibly downgraded.
- [ ] expected-R reliability is measured.
- [ ] policy uses probability + expected-R + risk gates.
- [ ] `AnalysisResult`-compatible output exists.
- [ ] tests pass.

---

## 10. What Phase 7 Inherits

Phase 7 inherits a normalized hybrid decision surface that runtime can validate, persist, suppress, and convert into lifecycle records.
