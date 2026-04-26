
# Phase 7 — Portfolio, Risk & Runtime Integration (Planned)

**Status:** Planned
**Owner:** Runtime / controls track
**Last updated:** 2026-04-24
**Delivery status:** Not started

---

## 1. Purpose

This phase integrates policy outputs into the runtime lifecycle, adds portfolio and risk interpretation, and materializes `DecisionEvent` and `TradeOutcome` in actual flows.

It solves the problem that a valid `AnalysisResult` still does not mean the runtime can safely execute or even persist it correctly.

---

## 2. What Carried Over / What Must Stay Stable

The following are already implemented / must remain stable:

- [x] calibrated policy outputs exist from Phase 6
- [x] runtime vs engine ownership is already defined
- [x] event/outcome are runtime-owned lifecycle objects
- [x] portfolio and risk are separate documented stages
- [x] runtime authority doc exists at `runtime/runtime_integration.md`

This phase builds on top of these. Do not regress them.

---

## 3. Background & Motivation

Without this phase:
- results stay detached from runtime behavior
- portfolio suppression stays theoretical
- risk blocks stay theoretical
- events/outcomes stay docs only

This phase is where V7 stops being a pure training design and becomes a runtime-capable system slice.

---

## 4. Current Failure State / Known Blockers

The current state has the following known issues:

- `request builder` = may not yet emit V7 `AnalysisRequest`
- `result validator` = may not yet gate runtime consumption
- `DecisionEvent` = may not yet be materialized
- `TradeOutcome` = may not yet be created/updated in runtime lifecycle
- `portfolio_blocked` / `risk_blocked` = may not yet be explicit in live flow

---

## 5. Workstream A — Portfolio & Risk Controls

**Status:** New

### Problem / Goal

Implement lightweight portfolio interpretation and explicit risk hard/soft guards.

### Cluster grouping default

First implementation default:
- use explicit config-defined cluster groups
- do not derive ad hoc runtime correlation clusters in first phase
- optional offline correlation-based grouping may replace manual groups only with a versioned cluster-family update

### Combined block rule

If both portfolio and risk would block:
- set both `portfolio_blocked = true` and `risk_blocked = true`
- set the primary suppression reason to the risk block
- preserve the portfolio block as secondary context

### Implementation Tasks

- [ ] Implement portfolio pass / suppress / down-rank behavior
- [ ] Implement cluster/concentration rules using config-defined cluster groups
- [ ] Implement risk hard-block rules
- [ ] Preserve portfolio-before-risk ordering

### Acceptance Criteria

- [ ] portfolio suppression is explicit
- [ ] risk blocks are explicit
- [ ] portfolio and risk outputs can coexist without ambiguity

---

## 6. Workstream B — Runtime Request/Result Flow

**Status:** New

### Problem / Goal

Make runtime emit valid requests and consume only valid results.

### Authority note

Primary behavioral authority for this workstream:
- `runtime/runtime_integration.md`
- contract family docs
- fallback and deployment-safety docs where relevant

### Implementation Tasks

- [ ] Implement V7 request builder
- [ ] Implement result validator
- [ ] Consume shared simulation core for paper trading (forward simulation) and replay
- [ ] Enforce actionability vs execution-eligibility split
- [ ] Preserve fallback visibility in runtime interpretation

### Acceptance Criteria

- [ ] runtime can build valid `AnalysisRequest`
- [ ] runtime rejects invalid `AnalysisResult`
- [ ] actionability and execution eligibility are distinct in flow

---

## 7. Workstream C — Event & Outcome Lifecycle

**Status:** New

### Problem / Goal

Materialize runtime-owned lifecycle records.

### Outcome update triggers

Default first implementation triggers:
- create `TradeOutcome` after `DecisionEvent` exists and the decision enters tracked lifecycle
- update outcome on fill/open confirmation when relevant
- update outcome on close/exit confirmation when relevant
- update outcome on replay horizon completion
- update outcome on asynchronous outcome resolver completion
- allow `PENDING → RESOLVED | PARTIALLY_RESOLVED | INVALIDATED | UNAVAILABLE`

#### 7.1 Event creation

```python
DecisionEvent
```

**Rationale:**
- the model does not emit events
- runtime needs a normalized decision record before outcome is known

#### 7.2 Outcome creation / update

```python
TradeOutcome
```

### Acceptance Criteria

- [ ] `DecisionEvent` is created after valid normalized result
- [ ] `TradeOutcome` can be created as pending and updated later
- [ ] fallback / suppression signals survive into lifecycle objects

---

## 8. Workstream D — Test Coverage

**Status:** New
**Required before:** evaluation and paper-flow validation

### 8.1 Portfolio / risk tests

- [ ] portfolio suppression test
- [ ] risk block test
- [ ] portfolio-before-risk ordering test
- [ ] dual portfolio+risk block propagation test

### 8.2 Runtime flow tests

- [ ] request builder test
- [ ] result validator rejection test
- [ ] actionability vs execution-eligibility split test

### 8.3 Lifecycle tests

- [ ] decision event materialization test
- [ ] trade outcome pending → updated flow test
- [ ] fallback/suppression propagation matrix test

---

## 9. Workstream E — Pre-Run / Pre-Deploy Audit Checklist

**Status:** New
**Must complete before:** Phase 8 evaluation/monitoring integration

### 9.1 Runtime audit

- [ ] verify runtime does not silently bypass result validation
- [ ] verify fallback signals are visible in event creation

### 9.2 Control audit

- [ ] verify portfolio and risk blocks can be distinguished downstream
- [ ] verify timing extension remains advisory by default

### 9.3 Lifecycle audit

- [ ] verify event creation is not deferred until trade outcome exists
- [ ] verify pending outcomes are legal and explicit
- [ ] verify outcome update triggers are implemented explicitly

---

## 10. Combined Implementation Order

1. Complete Workstream A — Portfolio & Risk Controls
2. Implement Workstream B — Runtime Request/Result Flow
3. Apply Workstream C — Event & Outcome Lifecycle
4. Run Workstream E — Pre-Run Audit
5. Implement Workstream D — Test Coverage
6. Execute runtime-integration suite
7. Evaluate results against acceptance criteria

### Acceptance Criteria for First Combined Run

- [ ] runtime builds valid requests
- [ ] runtime validates and consumes valid results only
- [ ] portfolio/risk controls are explicit
- [ ] event/outcome lifecycle is materialized correctly

---

## 11. Definition of Done

### 11.1 Control layer

- [x] portfolio/risk semantics are documented
- [ ] portfolio interpretation exists
- [ ] risk interpretation exists

### 11.2 Runtime / interface layer

- [ ] request builder exists
- [ ] result validator exists
- [ ] actionability vs execution-eligibility split is enforced

### 11.3 Lifecycle layer

- [ ] decision events are created
- [ ] trade outcomes are created and updateable
- [ ] fallback lineage is preserved
- [ ] outcome trigger rules are implemented

### 11.4 Test layer

- [ ] control tests pass
- [ ] runtime flow tests pass
- [ ] lifecycle tests pass

---

## 12. What Phase 8 Inherits

### 12.1 Capability expansion themes

- runtime-consumable decisions
- explicit portfolio/risk controls
- real lifecycle records
- paper/replay-capable flow

### 12.2 Phase Boundary

- Phase 8 is evaluation and monitoring work.
- Phase 7 is the prerequisite.
- Do not start Phase 8 work until Phase 7 definition of done is fully satisfied.

---

## 13. Compact Mental Model

### 13.1 Phase Relationships

- Phase 6: decisions became operational surfaces
- Phase 7: runtime begins consuming them correctly
- Phase 8: system quality becomes measurable
- Phase 9: release safety becomes enforceable

### 13.2 Key Takeaway

This phase makes V7 behave like a system, not just a pipeline.
It is where lifecycle truth and execution safety finally meet.
