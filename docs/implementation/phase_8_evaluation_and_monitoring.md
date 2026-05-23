# Phase 8 — Hybrid Evaluation & Monitoring (Planned)

**Status:** Planned  
**Owner:** Evaluation / observability track  
**Last updated:** 2026-05-23  
**Delivery status:** Not started

---

## 1. Purpose

Prove whether V7's hybrid model, calibration, policy, runtime flow, and monitoring surfaces are economically useful and operationally trustworthy.

A working system is not automatically a good system. This phase supplies evidence.

---

## 2. Stable Rules

- Evaluation is economic-quality-first.
- No-trade quality matters.
- Calibration quality matters.
- Expected-R reliability matters.
- Symbol/regime breakdowns are mandatory.
- Promotion is per `model_scope`.
- Replay/paper/live evidence must stay comparable.

---

## 3. Workstream A — Hybrid Evaluation Core

Evaluate candidates against baseline using:

### Economic metrics

- realized R
- average R
- distributional R
- profit factor
- max drawdown / adverse excursion
- regret
- no-trade correctness
- missed opportunity
- saved loss
- path quality

### Classification metrics

- action confusion matrix
- directional precision/recall where meaningful
- no-trade precision/recall
- calibrated confidence buckets
- class distribution stability

### Regression metrics

- expected-R MAE / RMSE
- signed expected-R bias
- long/short separate expected-R error
- predicted-R bucket realized-R quality
- rank correlation between predicted expected-R and realized R
- expected-R gate quality

### Ablation metrics

- 4h-only
- 4h + 1d
- 4h + 1d + 1h
- classifier-only policy vs hybrid policy
- probability gate only vs probability + expected-R gate

### Acceptance Criteria

- [ ] candidate vs baseline comparison exists.
- [ ] hybrid surface quality is measurable.
- [ ] no-trade quality is measurable.
- [ ] interval-view and hybrid-policy ablations exist.

---

## 4. Workstream B — Promotion Evidence

Default first implementation promotion thresholds:

- candidate mean realized-R improves over baseline by at least `+0.10`
- calibration error does not worsen by more than `0.01`
- no-trade correctness does not degrade by more than `1.0%`
- expected-R rank quality is non-negative and above configured minimum
- no critical safety regression

These are config defaults, not permanent policy.

Promotion should never rely on one scalar.

### Acceptance Criteria

- [ ] promotion gate uses economic, calibration, no-trade, and expected-R evidence.
- [ ] incomplete slices are marked incomplete.
- [ ] per-scope promotion is enforced.

---

## 5. Workstream C — Monitoring Core

Monitoring must aggregate by `model_scope` and track:

- confidence distribution
- expected-R distribution
- realized-R by predicted-R bucket
- fallback/degraded rate
- actionability vs execution-eligibility gap
- no-trade rate
- outcome finality lag
- feature drift
- symbol/regime coverage
- harmful symbol-side cohorts
- simulation unresolved/invalidated rate
- replay/paper divergence where measurable
- timing-extension usefulness

### Acceptance Criteria

- [ ] lifecycle health signals exist.
- [ ] fallback/degradation are measurable.
- [ ] expected-R drift or degradation is observable.
- [ ] outcome lag is measurable.

---

## 6. Workstream D — Drift & Timing Evidence

Default drift families:

```python
continuous_feature_drift = "PSI"
missingness_shift = "absolute_rate_delta"
symbol_mix_shift = "total_variation_distance"
expected_r_distribution_shift = "bucket_delta"
```

Timing gate promotion rule:

Timing remains advisory-only unless:

- at least 3 consecutive evaluation windows agree
- each relevant timing state has enough samples
- `CHASING` or `MISSED` materially underperform `READY_NOW`
- coverage loss stays within configured tolerance

### Acceptance Criteria

- [ ] feature drift metrics exist.
- [ ] expected-R drift metrics exist.
- [ ] timing usefulness can be assessed.

---

## 7. Workstream E — Test Coverage

Minimum tests:

- walk-forward integrity
- baseline comparison
- no-trade metric
- calibration metric
- expected-R metric
- predicted-R bucket aggregation
- classifier-only vs hybrid policy ablation
- fallback/degradation aggregation
- actionability/execution gap
- outcome lag metric
- feature drift aggregation
- timing usefulness aggregation
- baseline update logic

---

## 8. Pre-Deploy Audit

Before Phase 9:

- [ ] promoted baseline reference exists
- [ ] previous baseline retention works
- [ ] promotion gate metrics are computed from real outputs
- [ ] incomplete slices do not count as healthy evidence
- [ ] expected-R reliability evidence is visible
- [ ] timing-extension evidence is visible
- [ ] feature drift evidence is visible

---

## 9. Definition of Done

- [ ] walk-forward evaluation exists.
- [ ] baseline comparison exists.
- [ ] hybrid metrics exist.
- [ ] monitoring signals exist.
- [ ] promotion evidence is objective.
- [ ] tests pass.

---

## 10. What Phase 9 Inherits

Phase 9 inherits evidence about economic quality, confidence reliability, expected-R reliability, no-trade quality, drift, and runtime lifecycle health.
