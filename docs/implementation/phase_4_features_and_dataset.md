
# Phase 4 — Features & Dataset (Planned)

**Status:** Planned
**Owner:** Data / training-input track
**Last updated:** 2026-04-24
**Delivery status:** Not started

---

## 1. Purpose

This phase turns canonical state and label truth into leakage-safe feature rows and walk-forward dataset families.

It solves the problem that truth and labels may exist, but training rows are not yet guaranteed to be valid, stable, or balanced.

---

## 2. What Carried Over / What Must Stay Stable

The following are already implemented / must remain stable:

- [x] contracts exist
- [x] simulation truth exists
- [x] label and outcome semantics are aligned
- [x] feature and dataset docs already define first-phase assumptions

This phase builds on top of these. Do not regress them.

---

## 3. Background & Motivation

Training rows can still fail even with good labels if:
- features leak future information
- HTF fallback is inconsistent
- symbol identity is unstable
- train/test splits are time-invalid
- symbol distribution is dominated by a few instruments

This phase prevents those failures.

---

## 4. Current Failure State / Known Blockers

The current state has the following known issues:

- `feature schema` = documented, not yet guaranteed in code
- `normalization family` = documented, not yet guaranteed in code
- `walk-forward folds` = documented, not yet guaranteed in code
- `symbol balancing` = may not yet exist
- `dataset_family_version` = may not yet be tied to actual row lineage

---

## 5. Workstream A — Feature Builder

**Status:** New

### Problem / Goal

Convert canonical state into explicit grouped model features.

### Implementation Tasks

- [ ] Implement grouped feature families
- [ ] Implement HTF context feature extraction
- [ ] Implement missing/degraded flags
- [ ] Implement symbol one-hot encoding family

### Symbol-universe evolution rule

Within one `dataset_family_version`, the approved symbol universe is fixed.
If a symbol is added or removed:
- bump the symbol-encoding family version
- bump the dataset family version
- retrain downstream model artifacts

Do not hot-swap one-hot dimensions inside the same dataset family.

### Acceptance Criteria

- [ ] grouped feature surfaces exist
- [ ] HTF missingness is explicit
- [ ] symbol encoding is stable and versioned

---

## 6. Workstream B — Normalization & Schema Stability

**Status:** New

### Problem / Goal

Keep feature values numerically stable without hiding their meaning.

### Normalization rule

Walk-forward normalization is **per fold**:
- fit normalization statistics on the training window of that fold only
- apply those same statistics to that fold’s validation/calibration/holdout rows
- do not reuse fold 1 statistics for later folds

### Implementation Tasks

- [ ] Implement training-only normalization fitting
- [ ] Implement transform-time normalization reuse
- [ ] Implement feature schema versioning
- [ ] Implement schema compatibility validation

### Acceptance Criteria

- [ ] normalization uses training-only statistics
- [ ] schema version is attached to outputs
- [ ] incompatible schemas fail clearly

---

## 7. Workstream C — Dataset Assembly

**Status:** New

### Problem / Goal

Produce walk-forward training rows with preserved lineage and symbol balancing.

#### 7.1 Row assembly

```python
row_id
symbol
primary_interval (e.g., 4h)
htf_context_interval (e.g., 1d)
refinement_interval (e.g., 1h)
state_timestamp_utc
dataset_family_version
```

**Rationale:**
- rows must be traceable
- dataset family cannot be anonymous
- single unified multi-view rows, no separate primary 1h and 4h universes

#### 7.2 Split and weighting

```python
fold_count = 6
min_train_window = "12m"
validation_window = "2m"
holdout_window = "1m"
symbol_weighting = "inverse_frequency_capped"
max_weight_ratio = 5.0
```

### Balancing default

First implementation default:
- use inverse-frequency sample weights by symbol
- cap max relative symbol weight ratio at `5.0`
- only add hard row-count caps if symbol imbalance remains pathological after weighting

### Acceptance Criteria

- [ ] walk-forward folds are reproducible
- [ ] unresolved / invalid rows are excluded by default
- [ ] symbol weighting or capping prevents silent domination

---

## 8. Workstream D — Test Coverage

**Status:** New
**Required before:** Phase 5 model training

### 8.1 Feature tests

- [ ] no future leakage test
- [ ] HTF fallback + missing-flag test
- [ ] symbol encoding stability test

### 8.2 Normalization tests

- [ ] training-only normalization-fit test
- [ ] per-fold normalization separation test
- [ ] schema mismatch test

### 8.3 Dataset tests

- [ ] walk-forward split integrity test
- [ ] unresolved row exclusion test
- [ ] symbol-weighting reproducibility test

---

## 9. Workstream E — Pre-Run Audit Checklist

**Status:** New
**Must complete before:** first model training run

### 9.1 Feature audit

- [ ] verify no feature uses future-only information
- [ ] verify grouped feature families map to docs

### 9.2 Dataset audit

- [ ] verify fold windows match documented defaults or explicit config override
- [ ] verify row lineage is preserved end to end

### 9.3 Balance audit

- [ ] verify no single symbol silently dominates row weights or row counts
- [ ] verify symbol-universe changes would bump dataset/version surfaces

---

## 10. Combined Implementation Order

1. Complete Workstream A — Feature Builder
2. Implement Workstream B — Normalization & Schema Stability
3. Apply Workstream C — Dataset Assembly
4. Run Workstream E — Pre-Run Audit
5. Implement Workstream D — Test Coverage
6. Execute feature/dataset test suite
7. Evaluate results against acceptance criteria

### Acceptance Criteria for First Combined Run

- [ ] feature rows are produced from canonical state only
- [ ] normalization is training-only and per-fold
- [ ] walk-forward datasets are reproducible
- [ ] symbol weighting/capping is explicit and testable

---

## 11. Definition of Done

### 11.1 Feature layer

- [x] feature semantics are documented
- [x] normalization direction is documented
- [ ] feature builder exists
- [ ] HTF fallback + flags exist

### 11.2 Dataset layer

- [ ] dataset row assembly exists
- [ ] walk-forward folds exist
- [ ] dataset family versioning exists

### 11.3 Candidate health

- [ ] no temporal leakage remains in row construction
- [ ] symbol dominance is controlled explicitly
- [ ] symbol-universe evolution is version-safe

### 11.4 Test layer

- [ ] feature tests pass
- [ ] normalization tests pass
- [ ] dataset tests pass

---

## 12. What Phase 5 Inherits

### 12.1 Capability expansion themes

- training-ready rows
- stable feature schema
- reproducible walk-forward splits

### 12.2 Phase Boundary

- Phase 5 is baseline model training work.
- Phase 4 is the prerequisite.
- Do not start Phase 5 work until Phase 4 definition of done is fully satisfied.

---

## 13. Compact Mental Model

### 13.1 Phase Relationships

- Phase 3: labels became coherent
- Phase 4: rows become valid
- Phase 5: baseline model is trained
- Phase 6: scores become calibrated decisions

### 13.2 Key Takeaway

A model cannot fix bad rows.
This phase is where V7 earns the right to start learning.
