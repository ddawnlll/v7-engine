
# Phase 3 — Labels & Outcome Semantics (Planned)

**Status:** Planned
**Owner:** Labels / lifecycle track
**Last updated:** 2026-04-24
**Delivery status:** Not started

---

## 1. Purpose

This phase converts runtime simulation outputs into label logic and aligns that same simulated truth with `TradeOutcome` semantics.

It solves the problem of having simulation outputs without a normalized supervised target family or lifecycle-consistent consequence language.

---

## 2. What Carried Over / What Must Stay Stable

The following are already implemented / must remain stable:

- [x] contracts are typed and validated
- [x] runtime simulation engine and side-effect-free training/replay adapter outputs exist from Phase 2
- [x] no-trade is already first-class

This phase builds on top of these. Do not regress them.

---

## 3. Background & Motivation

Without this phase, V7 can consume runtime simulation outputs but still fail to answer:
- what should the model learn?
- when is no-trade correct?
- when is a state ambiguous?
- how do labels relate to later outcomes?

This phase makes those answers explicit.

---

## 4. Current Failure State / Known Blockers

The current state has the following known issues:

- `best_action_label` = not yet derived as stable code
- `ambiguity` = may not yet produce explicit ambiguous label states
- `path_quality_bucket` = may not yet be produced from path metrics
- `TradeOutcome interpretation` = may not yet align with simulation family

---

## 5. Workstream A — Label Builder Core

**Status:** New

### Problem / Goal

Convert comparative runtime simulation outputs into compact supervised labels without creating a label-only simulator.

### Implementation Tasks

- [ ] Implement best-action label derivation
- [ ] Implement second-best action derivation
- [ ] Implement regret outputs
- [ ] Implement no-trade correctness outputs
- [ ] Preserve simulation profile/version and adapter lineage on label records
- [ ] Optionally consume Monte Carlo robustness evidence for label confidence when configured

### Acceptance Criteria

- [ ] best-action label family exists
- [ ] regret outputs exist
- [ ] no-trade correctness is explicit

---

## 6. Workstream B — Ambiguity & Path Quality

**Status:** New

### Problem / Goal

Handle cases where forced winners would be misleading and expose path-quality buckets.

### Default ambiguity and quality values

First implementation defaults:
- `ambiguity_gap_r_threshold = 0.15`
- `path_quality_high_threshold = 0.70`
- `path_quality_medium_threshold = 0.40`
- `min_acceptable_directional_realized_r = 0.25`

These are config defaults, not eternal constants.

### Implementation Tasks

- [ ] Implement ambiguity-threshold behavior
- [ ] Emit `AMBIGUOUS_STATE` where appropriate
- [ ] Implement path-quality bucket mapping
- [ ] Implement `skip_was_correct` logic

### `skip_was_correct` rule

Default first implementation:
`skip_was_correct = true` when any of the following are true:
- no-trade is the best comparative action
- both directional actions fail to exceed `min_acceptable_directional_realized_r`
- the saved-loss score exceeds the configured saved-loss threshold and no-trade remains preferred

### Acceptance Criteria

- [ ] ambiguity can emit explicit ambiguous states
- [ ] path-quality bucket mapping is deterministic
- [ ] `skip_was_correct` follows configured semantics

---

## 7. Workstream C — TradeOutcome Alignment

**Status:** New

### Problem / Goal

Ensure lifecycle outcomes can carry the same truth family without semantic drift.

### Dependency note
Workstream C depends on Workstream A’s label vocabulary.
Do not finalize outcome interpretation helpers before label names and label-validity states are stable.

#### 7.1 Outcome normalization helpers

```python
# examples
outcome_label
is_good_decision
is_good_no_trade
```

**Rationale:**
- outcomes are larger than labels
- but label truth and outcome interpretation must not conflict

#### 7.2 Timing echo alignment

```python
# examples
decision_confidence_seen
entry_readiness_seen
entry_valid_for_bars_seen
```

### Acceptance Criteria

- [ ] trade-outcome normalization helpers exist
- [ ] outcome semantics do not contradict label semantics
- [ ] timing echo surfaces can be preserved consistently

---

## 8. Workstream D — Test Coverage

**Status:** New
**Required before:** Phase 4 features/dataset

### 8.1 Label tests

- [ ] best-action label assignment test
- [ ] no-trade correctness test
- [ ] ambiguity threshold test

### 8.2 Path-quality tests

- [ ] path-quality bucket mapping test
- [ ] `skip_was_correct` test
- [ ] regret consistency test

### 8.3 Outcome interpretation tests

- [ ] `TradeOutcome` interpretation helpers align with simulation outputs
- [ ] unresolved/invalid outputs do not become valid final labels
- [ ] if best-second-best gap < ambiguity threshold, no forced directional winner is emitted

---

## 9. Workstream E — Pre-Run Audit Checklist

**Status:** New
**Must complete before:** dataset assembly

### 9.1 Label audit

- [ ] verify no unresolved simulation becomes valid training label
- [ ] verify ambiguous states are not silently forced into directional labels
- [ ] verify labels consume runtime simulation adapter outputs only
- [ ] verify no label-only simulator exists
- [ ] verify Monte Carlo evidence, if used, remains config-driven and distributional

### 9.2 Outcome audit

- [ ] verify outcome interpretation remains consistent with label semantics
- [ ] verify no label/output path duplicates a second truth family

### 9.3 Timing audit

- [ ] verify timing extension stays advisory and not a first-phase learned primary target

---

## 10. Combined Implementation Order

1. Complete Workstream A — Label Builder Core
2. Implement Workstream B — Ambiguity & Path Quality
3. Apply Workstream C — TradeOutcome Alignment
4. Run Workstream E — Pre-Run Audit
5. Implement Workstream D — Test Coverage
6. Execute label/outcome semantic suite
7. Evaluate results against acceptance criteria

### Acceptance Criteria for First Combined Run

- [ ] best-action / regret / no-trade outputs are produced correctly
- [ ] ambiguous states are preserved explicitly
- [ ] path-quality buckets are stable
- [ ] outcome interpretation aligns with label truth

---

## 11. Definition of Done

### 11.1 Label layer

- [x] label semantics are documented
- [x] ambiguity handling is specified
- [ ] label builder exists
- [ ] regret/no-trade outputs exist

### 11.2 Outcome layer

- [ ] outcome interpretation helpers exist
- [ ] lifecycle semantics align with label truth
- [ ] timing echo compatibility is preserved

### 11.3 Candidate health

- [ ] no hidden forced-winner logic remains
- [ ] no unresolved states enter strict label flow
- [ ] ambiguity defaults are config-backed and test-covered

### 11.4 Test layer

- [ ] label tests pass
- [ ] ambiguity tests pass
- [ ] outcome alignment tests pass

---

## 12. What Phase 4 Inherits

### 12.1 Capability expansion themes

- supervised label family
- explicit ambiguity handling
- outcome-compatible truth language

### 12.2 Phase Boundary

- Phase 4 is features and dataset work.
- Phase 3 is the prerequisite.
- Do not start Phase 4 work until Phase 3 definition of done is fully satisfied.

---

## 13. Compact Mental Model

### 13.1 Phase Relationships

- Phase 2: truth became real
- Phase 3: labels and outcomes become coherent
- Phase 4: feature and dataset rows become valid
- Phase 5: first model is trained

### 13.2 Key Takeaway

This phase answers what the model is actually supposed to learn.
Without it, later training quality is guesswork disguised as progress.
