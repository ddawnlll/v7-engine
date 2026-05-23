# Phase 0 — Repo Alignment & Hybrid Foundations (Planned)

**Status:** Planned  
**Owner:** Foundation / platform track  
**Last updated:** 2026-05-23  
**Delivery status:** Not started

---

## 1. Purpose

Create the repository structure, config surfaces, typed foundations, and test scaffolding needed to implement V7 as a hybrid supervised system.

This phase is not about business logic yet. It makes the repo safe to build in.

---

## 2. What Must Stay Stable

- One V7 implementation home.
- One central config root.
- One typed contract family.
- One simulation truth layer.
- One XGBoost-first hybrid model framework.
- No duplicate hidden config or orchestration surfaces.

---

## 3. Workstream A — Repository Skeleton

Create `src/v7/` with concern-focused subpackages:

- `contracts`
- `config`
- `simulation`
- `labels`
- `features`
- `dataset`
- `model`
- `calibration`
- `policy`
- `portfolio`
- `risk`
- `runtime`
- `evaluation`
- `monitoring`

### Hybrid-specific package expectations

The model package should be ready for:

- action classifier artifacts
- action-conditioned expected-R regressor artifacts
- model-suite bundle metadata
- scope-compatible artifact loading

The contract package should be ready for:

- action probabilities
- expected-R-by-action fields
- risk/economic estimates
- confidence kind and calibration lineage

### Acceptance Criteria

- [ ] `src/v7/` exists with stable concern folders.
- [ ] no duplicate V7 package roots exist.
- [ ] package imports succeed.

---

## 4. Workstream B — Config Foundations

Establish one V7 config family.

Minimum config groups:

- `system`
- `symbols`
- `model_scope`
- `simulation`
- `labels`
- `features`
- `dataset`
- `model`
- `calibration`
- `policy`
- `portfolio`
- `risk`
- `evaluation`
- `deployment`

### Hybrid config requirements (mode-centric)

The config must be able to express:

- enabled `model_scope` values (SWING, SCALP, AGGRESSIVE_SCALP)
- **mode-specific simulation configurations** (primary interval, stop/target multipliers, holding horizon)
- **mode-specific label thresholds**
- action-classification target family
- regression target family
- XGBoost classifier hyperparameters
- XGBoost regressor hyperparameters
- per-surface early stopping metrics
- calibration method for classifier confidence
- expected-R reliability review settings
- policy gates for confidence, expected-R, drawdown, and no-trade margin
- **regime detection config per mode**
- **regime policy modifiers**
- **correlation group definitions** for portfolio

### Merge order

1. checked-in defaults
2. environment config overlay
3. local developer override, if explicitly enabled
4. environment variables
5. explicit CLI/runtime overrides

Unknown keys fail by default.

### Acceptance Criteria

- [ ] one config loader exists.
- [ ] hybrid model fields are first-class config entries.
- [ ] unknown config keys fail visibly.

---

## 5. Workstream C — Typed Foundations

Use lightweight typed objects unless the repo already has a dominant validated-model standard.

Minimum foundation surfaces:

```python
class ValidationError(Exception): ...
class ConfigError(Exception): ...
class ArtifactCompatibilityError(Exception): ...
```

Reusable helpers:

```python
to_dict(obj) -> dict
from_dict(payload) -> object
validate_or_raise(obj) -> None
```

### Acceptance Criteria

- [ ] domain errors exist.
- [ ] typed serialization helpers exist.
- [ ] validator helpers have one stable home.

---

## 6. Workstream D — Test Scaffolding

Minimum tests before Phase 1:

- package import smoke tests
- config load tests
- unknown config key failure tests
- typed helper round-trip tests
- bootstrap `pytest` path
- lint/type command wiring if used by repo standards

---

## 7. Pre-Run Audit

Before Phase 1:

- [ ] confirm only one V7 package root exists
- [ ] confirm central config can express hybrid output settings
- [ ] confirm no separate hidden config controls model outputs
- [ ] confirm tests can be run locally

---

## 8. Definition of Done

- [ ] V7 skeleton exists.
- [ ] central config exists.
- [ ] hybrid config keys are available.
- [ ] base typing and validation helpers exist.
- [ ] bootstrap tests pass.

---

## 9. What Phase 1 Inherits

Phase 1 inherits one repo home, one config system, and a typed implementation style for hybrid contracts.
