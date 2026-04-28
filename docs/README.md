# V7 Documentation README

## Purpose

This is the entry document for the V7 documentation set.

It answers:

> What exists in V7, which documents are authoritative, and in what order should a human or code agent read them?

This file is a navigation and reading-order document.
It is not a second architecture spec.

---

## Read This Documentation In This Order

### 1. Direction
- `vision.md`
- `architecture.md`

### 2. Working and writing controls
- `v7_llm_rules.md`
- `v7_doc_writing_guide.md`

### 3. Contract family
- `contracts/README.md`
- `contracts/analysis_request.md`
- `contracts/analysis_result.md`
- `contracts/decision_event.md`
- `contracts/trade_outcome.md`

### 4. Runtime authority
- `runtime/runtime_integration.md`
- `runtime/fallback_policy.md`
- `runtime/deployment_safety.md`

### 5. Pipeline authority
- `pipeline/simulation.md`
- `pipeline/training.md`
- `pipeline/labels.md`
- `pipeline/features.md`
- `pipeline/dataset.md`
- `pipeline/model.md`
- `pipeline/calibration.md`
- `pipeline/policy.md`
- `pipeline/portfolio.md`
- `pipeline/risk.md`
- `pipeline/evaluation.md`
- `pipeline/monitoring.md`

### 6. Summary docs
- `ai_summary.md`
- `roadmap.md`

---

## What Each Root Doc Answers

### `vision.md`
Answers:
- what V7 is trying to become
- what V7 is trying to avoid
- what success looks like

### `architecture.md`
Answers:
- how the major system pieces fit together
- where ownership boundaries live
- how multi-symbol, contracts, and pipeline stages connect

### `v7_llm_rules.md`
Answers:
- how LLM agents should read, patch, test, and stop safely

### `v7_doc_writing_guide.md`
Answers:
- how future docs should stay compact, low-repetition, and LLM-readable

---

## Core Position

V7 is not a greenfield reset.
It is a disciplined extension of the best V6 decisions:

- atomic contract family
- one simulation truth layer
- market-first labeling
- centralized multi-symbol architecture
- compact, LLM-readable docs and modules
- explicit runtime vs engine ownership
- runtime `scope_router` selects `model_scope` before inference; no averaged scope outputs

---

## Canonical Contract Family

The V7 lifecycle contract family is:

- `AnalysisRequest`
- `AnalysisResult`
- `DecisionEvent`
- `TradeOutcome`

Ownership differs:

- request/result are engine-facing
- event/outcome are system-facing

This distinction is not optional.

---

## First-Phase Operating Assumptions

These assumptions are repeated throughout the docs and should be treated as default V7 authority:

- target universe up to **60 symbols**
- initial rollout may start with a smaller approved subset
- shared training platform, not one universal model
- first model scopes: `SWING`, `SCALP`, and `AGGRESSIVE_SCALP`
- scope defaults:
  - `SWING`: `primary_interval` **4h**, `context_intervals` **1d**, `refinement_intervals` **1h**
  - `SCALP`: `primary_interval` **15m**, `context_intervals` **1h**, `refinement_intervals` **5m**
  - `AGGRESSIVE_SCALP`: `primary_interval` **1m** or **3m**, `context_intervals` **5m + 15m**
- shared simulation core reused by runtime and replay with scope-specific profiles
- first-phase model algorithm family: **XGBoost-first** inside scope-specific artifacts
- first-phase calibration: **global within scope**
- timing extension:
  - `entry_readiness`
  - `entry_valid_for_bars`
  - advisory-first, not hard gate by default
- runtime: **incremental integration, not rewrite-first**

---

## What Is Locked vs Delegated

### Locked here
Do not casually change:
- atomic request/result/event/outcome boundaries
- one simulation truth layer
- no-trade as first-class action
- confidence + expected-R dual surface
- event/outcome lifecycle ownership
- batch/session lineage approach
- shared training platform with separate `model_scope` artifacts

### Delegated elsewhere
Do not duplicate these in README:
- detailed contract generation rules → `contracts/README.md`
- detailed runtime integration behavior → `runtime/runtime_integration.md`
- detailed pipeline semantics → `pipeline/`

This avoids semantic drift between summary docs and authority docs.

---

## Config Surface Note

This docs tree assumes one unified config system.
Where exact config semantics are not separately documented yet, the authoritative config surface remains:
- the existing repo config implementation
- the config assumptions referenced in `v7_llm_rules.md`
- the config families named in each authority document

Do not invent parallel config systems in new docs.

---

## What Is Intentionally Deferred

Not first-phase authority:
- full runtime rewrite
- advanced per-symbol model families
- per-symbol calibration by default
- heavy action-family expansion
- deep portfolio optimization
- complex timing planner
- execution microstructure optimization

---

## How To Use This Documentation

### For implementation
Read:
1. task-specific doc
2. contract docs
3. runtime or pipeline docs
4. existing repo config surface
5. tests

### For architecture review
Read:
1. `vision.md`
2. `architecture.md`
3. `contracts/README.md`
4. `runtime/runtime_integration.md`
5. relevant pipeline docs

### For LLM code agents
Use `v7_llm_rules.md` as the working-control document.

---

## Final Position

V7 documentation is designed to be:

- compact
- explicit
- authority-driven
- low repetition
- safe for LLM context windows
- strong enough to guide implementation without turning into doc hell

If a new document does not clearly own one concern, it should usually not exist.
