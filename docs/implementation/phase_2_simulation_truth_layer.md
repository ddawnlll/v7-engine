
# Phase 2 — Simulation Truth Layer (Planned)

**Status:** Planned
**Owner:** Simulation / truth-layer track
**Last updated:** 2026-04-24
**Delivery status:** Not started

---

## 1. Purpose

This phase implements the single authoritative V7 simulation truth layer.

It exists because labels, evaluation, replay comparison, and outcome normalization must all agree on the same market-first economic truth.

---

## 2. What Carried Over / What Must Stay Stable

The following are already implemented / must remain stable:

- [x] typed contract family is available from Phase 1
- [x] one simulation truth layer is already the documented direction
- [x] no-trade is already first-class in docs

This phase builds on top of these. Do not regress them.

---

## 3. Background & Motivation

The old failure pattern would be:
- one cost model for labeling
- another for evaluation
- another for runtime replay reasoning

This phase prevents that by creating one shared comparative simulator.

---

## 4. Current Failure State / Known Blockers

The current state has the following known issues:

- `simulation family` = documented, not implemented
- `long/short/no-trade comparative output` = may not yet exist in shared form
- `cost model` = may be scattered or implicit
- `unresolved vs invalidated` = may not be encoded as one consistent family

---

## 5. Workstream A — Comparative Simulator Core

**Status:** New

### Problem / Goal

Implement one simulator that evaluates long, short, and no-trade under the same rule family.

### Implementation Tasks

- [ ] Implement comparative action simulation core
- [ ] Support long / short / no-trade in one output family
- [ ] Implement exit reason families
- [ ] Implement raw no-trade comparative outputs:
  - `saved_loss_score`
  - `missed_opportunity_score`
  - `no_trade_counterfactual_quality`

### Acceptance Criteria

- [ ] one simulator can evaluate all three actions
- [ ] long/short/no-trade use the same truth rules
- [ ] unresolved/invalid states are explicit
- [ ] raw no-trade comparative outputs exist for later label logic

---

## 6. Workstream B — Cost / Exit / Horizon Semantics

**Status:** New

### Problem / Goal

Make costs and exit semantics explicit and versioned.

### Implementation Tasks

- [ ] Implement fee model
- [ ] Implement slippage model
- [ ] Implement stop/target/time-exit behavior
- [ ] Implement horizon-end and invalidation rules

### Default invalidation rule

First implementation default:
- unresolved remains unresolved while the approved future window may still complete
- unresolved becomes invalidated after **2 × configured horizon length**
- immediate invalidation is allowed for explicitly irrecoverable/corrupted future data

### Configuration / Code Reference

```python
# expected config families
cost_model_version
fee_model_version
slippage_model_version
horizon_family
invalidation_multiplier = 2.0
```

### Acceptance Criteria

- [ ] realized R includes cost semantics
- [ ] stop/target/time-exit are deterministic
- [ ] unresolved → invalidated behavior follows documented rules

---

## 7. Workstream C — Path Metrics & Timing Annotation Handling

**Status:** New

### Problem / Goal

Expose path-aware quality without letting timing metadata silently rewrite truth.

#### 7.1 Core path metrics

```python
mfe_r
mae_r
time_to_mfe
time_to_mae
```

**Rationale:**
- labels and outcomes need path quality
- evaluation needs more than end-state PnL

#### 7.2 Timing annotation rule

```python
entry_timing_annotation = "metadata_only"
```

**Rationale:**
- first-phase simulation keeps canonical entry semantics fixed
- timing annotations may be preserved for audit but do not change entry price or exit rules in the same simulation family

### Acceptance Criteria

- [ ] path metrics exist in one normalized family
- [ ] metrics are deterministic for same input
- [ ] timing annotation is preserved as metadata only
- [ ] no silent entry-price mutation occurs due to timing annotation

---

## 8. Workstream D — Test Coverage

**Status:** New
**Required before:** Phase 3 labels/outcomes

### 8.1 Invariant tests

- [ ] stop hit first scenario
- [ ] target hit first scenario
- [ ] time-exit scenario
- [ ] horizon-end unresolved scenario

### 8.2 Cost and path tests

- [ ] fee/slippage reduce realized R correctly
- [ ] MFE/MAE calculations are correct
- [ ] path quality score is deterministic

### 8.3 Output validation

- [ ] comparative outputs exist for long/short/no-trade
- [ ] invalidated states preserve reason
- [ ] timing annotation does not silently change entry in first phase
- [ ] raw no-trade comparative outputs are populated

---

## 9. Workstream E — Pre-Run Audit Checklist

**Status:** New
**Must complete before:** label generation work

### 9.1 Simulation config audit

- [ ] verify cost/exit/horizon families exist in config
- [ ] verify no duplicate conflicting exit semantics are active

### 9.2 Truth audit

- [ ] verify labels and evaluation are both intended to consume this simulator
- [ ] verify no alternate simulation truth path is still considered authoritative

### 9.3 Pending/invalid audit

- [ ] verify unresolved and invalidated are distinguishable
- [ ] verify partial future windows do not become fake final labels
- [ ] verify default invalidation timeout is implemented or explicitly overridden in config

---

## 10. Combined Implementation Order

1. Complete Workstream A — Comparative Simulator Core
2. Implement Workstream B — Cost / Exit / Horizon Semantics
3. Apply Workstream C — Path Metrics & Timing Annotation Handling
4. Run Workstream E — Pre-Run Audit
5. Implement Workstream D — Test Coverage
6. Execute simulation scenario suite
7. Evaluate results against acceptance criteria

### Acceptance Criteria for First Combined Run

- [ ] long/short/no-trade outputs are produced by one simulator
- [ ] realized R includes costs
- [ ] unresolved/invalid rules work as documented
- [ ] path metrics are present and correct

---

## 11. Definition of Done

### 11.1 Truth layer

- [x] simulation semantics are documented
- [x] cost/path/horizon rules are specified
- [ ] one shared simulator exists
- [ ] shared simulator is version-aware

### 11.2 Output layer

- [ ] comparative outputs exist
- [ ] path metrics exist
- [ ] resolution status exists
- [ ] raw no-trade comparative outputs exist

### 11.3 Candidate health

- [ ] no alternate truth layer silently competes with this simulator
- [ ] labels/evaluation/outcomes can consume this family later
- [ ] timing metadata cannot silently rewrite canonical truth

### 11.4 Test layer

- [ ] scenario tests pass
- [ ] cost tests pass
- [ ] unresolved/invalid tests pass
- [ ] timing-annotation tests pass

---

## 12. What Phase 3 Inherits

### 12.1 Capability expansion themes

- one market-first truth layer
- path-aware metrics
- cost-aware comparative action outputs
- raw no-trade comparative semantics

### 12.2 Phase Boundary

- Phase 3 is label and outcome semantics work.
- Phase 2 is the prerequisite.
- Do not start Phase 3 work until Phase 2 definition of done is fully satisfied.

---

## 13. Compact Mental Model

### 13.1 Phase Relationships

- Phase 1: contracts became real
- Phase 2: truth becomes real
- Phase 3: labels and outcomes become coherent
- Phase 4: training rows become valid

### 13.2 Key Takeaway

If Phase 2 is wrong, every downstream metric lies.
This is the most important early implementation phase after contracts.
