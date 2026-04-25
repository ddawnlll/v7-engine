
# Phase 0 — Repo Alignment & Foundations (Planned)

**Status:** Planned
**Owner:** Foundation / platform track
**Last updated:** 2026-04-24
**Delivery status:** Not started

---

## 1. Purpose

This phase creates the minimal repository structure, typed foundations, config surfaces, and test scaffolding needed to implement V7 safely.

This phase is not about business logic correctness yet.
It is about making the repo analyzable and implementation-ready.

---

## 2. What Carried Over / What Must Stay Stable

The following are already implemented / must remain stable:

- [x] V7 documentation authority exists
- [x] Contract family naming and semantics are already defined
- [x] One unified config direction is already mandated
- [x] Repo should remain LLM-readable and low-sprawl

This phase builds on top of these.
Do not regress them.

---

## 3. Background & Motivation

A large share of later implementation risk comes from starting logic work inside a repo that has:
- no stable module map
- no typed contract home
- no central config surface
- no test skeleton

The correct approach is to create the minimal boring skeleton first.

---

## 4. Current Failure State / Known Blockers

The current state has the following known issues:

- `src/v7/` = missing or partial — implementation home may not exist yet
- `tests/` = incomplete for V7-specific boundaries
- `config surface` = may exist in legacy form only
- `contract types` = may not exist as typed Python surfaces
- `task runner / lint / typing flow` = may not yet align with V7 rules

---

## 5. Workstream A — Repository Skeleton

**Status:** New

### Problem / Goal

Create the primary V7 module layout so later phases do not invent structure ad hoc.

### Implementation Tasks

- [ ] Create `src/v7/` module tree aligned with docs
- [ ] Create top-level subpackages for contracts, simulation, features, dataset, model, calibration, policy, portfolio, risk, runtime, evaluation, monitoring
- [ ] Create placeholder `__init__` surfaces only where needed
- [ ] Avoid adding business logic beyond scaffolding

### Acceptance Criteria

- [ ] `src/v7/` exists with stable top-level concern folders
- [ ] module tree matches V7 docs closely enough to begin implementation
- [ ] no duplicate parallel V7 package trees exist

---

## 6. Workstream B — Config Foundations

**Status:** New

### Problem / Goal

Establish the central config entrypoint and resolved-config pattern required by later phases.

### Implementation Tasks

- [ ] Identify current config mechanism in repo
- [ ] Create or align one V7 config module family
- [ ] Define base config object pattern for later thresholds/toggles
- [ ] Add defaults location and merge / resolution strategy

### Default merge / resolution strategy

1. checked-in defaults
2. environment-specific config file overlay
3. local developer override file if explicitly enabled
4. environment variables
5. explicit CLI/runtime override arguments

Higher layers override lower layers.
Silent unknown-key merges are forbidden.

### Acceptance Criteria

- [ ] V7 has one identifiable config surface
- [ ] defaults are centralized
- [ ] later phases can add settings without hardcoding values in random modules
- [ ] merge / resolution order is implemented and test-covered

---

## 7. Workstream C — Typed Foundations

**Status:** New

### Problem / Goal

Create minimal typed base structures needed by contracts and lifecycle objects.

### Root Cause

Phase 1 cannot be consistent if every contract chooses its own typing and validation style.

### Implementation choice

First-phase default:
- use `dataclasses` or equivalent lightweight typed classes for core objects
- use explicit validators rather than framework magic as the primary validation layer

If the repo already has a dominant validated-model standard, use the closest compatible existing standard and report the substitution.
Do not introduce heavy framework dependency only for V7 if the repo does not already rely on it.

#### 7.1 Base typing surface

```python
class ValidationError(Exception): ...
class ConfigError(Exception): ...
```

**Rationale:**
- domain errors improve boundary clarity
- later phases need typed exceptions and shared utility surfaces

#### 7.2 Serialization / validation helpers

```python
def to_dict(...) -> dict: ...
def from_dict(...) -> object: ...
```

### Acceptance Criteria

- [ ] minimal domain error family exists
- [ ] typed serialization / validation helpers have a stable home
- [ ] helpers are small and reusable, not framework-heavy
- [ ] typed object strategy is explicit and consistent for later phases

---

## 8. Workstream D — Test Coverage

**Status:** New
**Required before:** Phase 1 contract implementation

### 8.1 Bootstrap tests

- [ ] repo imports do not crash
- [ ] base config loads
- [ ] package tree import smoke tests pass

### 8.2 Tooling tests

- [ ] `pytest` command wiring exists
- [ ] `ruff` lint/format-check wiring exists
- [ ] `mypy` typing command wiring exists

### 8.3 Boundary tests

- [ ] config error paths raise clearly
- [ ] invalid import cycles are avoided in core modules

---

## 9. Workstream E — Pre-Run Audit Checklist

**Status:** New
**Must complete before:** starting Phase 1

### 9.1 Repo audit

- [ ] confirm target V7 package tree exists only once
- [ ] search for duplicate V7 roots such as `src/v7`, `app/v7`, `lib/v7`, or legacy duplicate contract trees
- [ ] search for duplicate contract names such as `AnalysisRequest`, `AnalysisResult`, `DecisionEvent`, `TradeOutcome`

### 9.2 Config audit

- [ ] confirm where defaults live
- [ ] confirm later phases can add settings without parallel config systems

### 9.3 Test audit

- [ ] confirm test directories for unit/integration/regression exist or are planned concretely
- [ ] confirm `pytest`, `ruff`, and `mypy` are either already standard or can be introduced without conflict

---

## 10. Combined Implementation Order

1. Complete Workstream A — Repository Skeleton
2. Implement Workstream B — Config Foundations
3. Apply Workstream C — Typed Foundations
4. Run Workstream E — Pre-Run Audit
5. Implement Workstream D — Test Coverage
6. Execute first bootstrap import/lint/type run
7. Evaluate results against acceptance criteria

### Acceptance Criteria for First Combined Run

- [ ] package imports complete without bootstrap errors
- [ ] base config can load successfully
- [ ] lint/type/test smoke commands are runnable
- [ ] repo structure is ready for contract implementation

---

## 11. Definition of Done

### 11.1 Bootstrap layer

- [x] V7 docs exist
- [x] V7 package target structure is known
- [ ] `src/v7/` aligned skeleton exists
- [ ] one central config surface exists

### 11.2 Interface layer

- [ ] base typed helper surfaces exist
- [ ] domain errors exist
- [ ] serialization / validation helpers have a stable home
- [ ] typed object strategy is chosen explicitly

### 11.3 Platform coverage

- [ ] no duplicate V7 structure ambiguity remains
- [ ] later phases can locate config, modules, and tests unambiguously

### 11.4 Test layer

- [ ] bootstrap smoke tests exist
- [ ] pytest/ruff/mypy commands are wired
- [ ] config load test exists

---

## 12. What Phase 1 Inherits

### 12.1 Capability expansion themes

- one repo location for V7 code
- one config home
- one base testing surface
- one typed implementation style

### 12.2 Phase Boundary

- Phase 1 is contract implementation work.
- Phase 0 is the prerequisite.
- Do not start Phase 1 work until Phase 0 definition of done is fully satisfied.

---

## 13. Compact Mental Model

### 13.1 Phase Relationships

- Phase -1: docs were written
- Phase 0: repo becomes safe to build in
- Phase 1: contracts become real
- Phase 2: simulation becomes real

### 13.2 Key Takeaway

If Phase 0 is skipped, every later phase invents its own structure.
That produces exactly the kind of repo sprawl V7 is trying to prevent.
