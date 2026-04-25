
# Phase 1 — Contracts & Validation (Planned)

**Status:** Planned
**Owner:** Contracts / interface track
**Last updated:** 2026-04-24
**Delivery status:** Not started

---

## 1. Purpose

This phase implements the four V7 lifecycle contracts as typed runtime surfaces and builds validation around them.

It solves the problem that V7 semantics currently exist in docs but not yet as trusted code-level boundaries.

---

## 2. What Carried Over / What Must Stay Stable

The following are already implemented / must remain stable:

- [x] Contract family semantics are documented
- [x] Atomic request/result/event/outcome boundaries are locked
- [x] Runtime vs engine ownership boundaries are already defined
- [x] Phase 0 chooses the typed-object strategy

This phase builds on top of these. Do not regress them.

---

## 3. Background & Motivation

Without real contract surfaces, later implementation will:
- pass ad hoc dicts
- hide required fields
- drift between runtime and pipeline
- lose version discipline

The correct approach is to make contracts explicit before simulation/model/runtime work deepens.

---

## 4. Current Failure State / Known Blockers

The current state has the following known issues:

- `AnalysisRequest` = documented, not guaranteed as typed object
- `AnalysisResult` = documented, not guaranteed as typed object
- `DecisionEvent` = documented, not guaranteed as typed object
- `TradeOutcome` = documented, not guaranteed as typed object
- `contract validation` = may be scattered or absent

---

## 5. Workstream A — Typed Contract Objects

**Status:** New

### Problem / Goal

Implement the four core lifecycle objects as explicit typed structures.

### Implementation tasks

- [ ] Implement `AnalysisRequest`
- [ ] Implement `AnalysisResult`
- [ ] Implement `DecisionEvent`
- [ ] Implement `TradeOutcome`

### Typed implementation rule

Default first-phase choice:
- typed dataclass-style objects
- explicit constructor or post-init validation hooks kept minimal
- validation logic lives in dedicated validators, not hidden side effects

If the repo’s existing dominant model layer is reused, the implementation must preserve:
- explicit required/optional fields
- explicit version fields
- explicit dict round-trip

### Acceptance Criteria

- [ ] all four contract types exist in code
- [ ] required vs optional fields are explicit
- [ ] version fields are represented explicitly

---

## 6. Workstream B — Contract Validation

**Status:** New

### Problem / Goal

Ensure invalid lifecycle objects fail early and clearly.

### Implementation Tasks

- [ ] Add structural validators for each contract
- [ ] Add consistency validators for request/result/event/outcome linkage
- [ ] Add enum and numeric bound validation
- [ ] Add timing-extension field validation for `AnalysisResult`

### Timing validation defaults

First-phase timing validation should enforce:
- `entry_valid_for_bars` is an integer
- default allowed range is **0–5**
- `entry_readiness` must be one of the documented legal enum values
- `entry_expiry_utc`, if present, must parse as valid UTC timestamp

### Acceptance Criteria

- [ ] invalid objects fail before downstream use
- [ ] consistency mismatches raise clear errors
- [ ] timing extension fields are bounded and legal

---

## 7. Workstream C — Serialization / Round-Trip

**Status:** New

### Problem / Goal

Enable lifecycle objects to move safely across logging, persistence, and tests.

#### 7.1 Serialization helpers

```python
obj.to_dict()
ContractType.from_dict(payload)
```

**Rationale:**
- tests need round-trip safety
- persistence should not invent a second schema

#### 7.2 Version-aware validation

```python
payload = {
  "contract_version": "v7-0.x",
  "response_schema_version": "result-0.x",
}
```

### Version compatibility rule

First-phase default:
- contract-family major mismatch fails
- same-family newer minor/patch versions may load only if all required fields for the active runtime are present
- unknown optional fields may be preserved or ignored explicitly, but never silently reinterpret meaning

### Acceptance Criteria

- [ ] contracts serialize predictably
- [ ] contracts deserialize predictably
- [ ] version mismatches fail clearly where unsupported

---

## 8. Workstream D — Test Coverage

**Status:** New
**Required before:** Phase 2 simulation implementation

### 8.1 Contract shape tests

- [ ] required-field tests for all four contracts
- [ ] optional-field omission tests
- [ ] enum legality tests

### 8.2 Consistency tests

- [ ] request/result linkage validation
- [ ] result/event linkage validation
- [ ] event/outcome linkage validation

### 8.3 Round-trip tests

- [ ] request serialization round-trip
- [ ] result serialization round-trip
- [ ] event serialization round-trip
- [ ] outcome serialization round-trip

---

## 9. Workstream E — Pre-Run Audit Checklist

**Status:** New
**Must complete before:** Phase 2

### 9.1 Contract audit

- [ ] verify contract names map directly to doc names
- [ ] verify no duplicate legacy contract variants silently remain in active path

### 9.2 Validation audit

- [ ] verify invalid objects cannot bypass validators
- [ ] verify version fields are present and test-covered

### 9.3 Boundary audit

- [ ] verify runtime-owned vs engine-owned contracts are separated in code organization
- [ ] verify timing validation upper bounds are config-aligned or explicitly fixed by this phase

---

## 10. Combined Implementation Order

1. Complete Workstream A — Typed Contract Objects
2. Implement Workstream B — Contract Validation
3. Apply Workstream C — Serialization / Round-Trip
4. Run Workstream E — Pre-Run Audit
5. Implement Workstream D — Test Coverage
6. Execute contract test suite
7. Evaluate results against acceptance criteria

### Acceptance Criteria for First Combined Run

- [ ] four contract types instantiate successfully
- [ ] invalid linkage fails correctly
- [ ] round-trip tests pass
- [ ] version fields are preserved and validated

---

## 11. Definition of Done

### 11.1 Contract layer

- [x] contract semantics are documented
- [x] required fields are known from docs
- [ ] typed request/result/event/outcome objects exist
- [ ] validators exist for all four

### 11.2 Interface layer

- [ ] serialization helpers exist
- [ ] linkage consistency checks exist
- [ ] timing extension validation exists
- [ ] version compatibility policy is implemented

### 11.3 Candidate health

- [ ] no active V7 flow depends on ad hoc unvalidated dict payloads
- [ ] versioned contract boundaries are testable

### 11.4 Test layer

- [ ] required/optional field tests pass
- [ ] linkage tests pass
- [ ] round-trip tests pass

---

## 12. What Phase 2 Inherits

### 12.1 Capability expansion themes

- trusted typed lifecycle objects
- validation before simulation use
- stable serialization surfaces
- explicit version compatibility behavior

### 12.2 Phase Boundary

- Phase 2 is simulation truth-layer work.
- Phase 1 is the prerequisite.
- Do not start Phase 2 work until Phase 1 definition of done is fully satisfied.

---

## 13. Compact Mental Model

### 13.1 Phase Relationships

- Phase 0: repo is ready
- Phase 1: contracts become real
- Phase 2: truth layer becomes real
- Phase 3: labels/outcomes become coherent

### 13.2 Key Takeaway

Simulation and runtime should not be built on untyped guesswork.
Phase 1 turns the contract docs into actual enforceable program boundaries.
