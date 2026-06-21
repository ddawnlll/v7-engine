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
- `runtime/simulation_engine.md`
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
- `profitability_thesis.md`
- `roadmap.md`

### 7. Policy Critic (advisory RL component)
- `policy_critic/ai_summary.md`
- `policy_critic/design.md`
- `policy_critic/codebase_maps/` (V7 pipeline, AlphaForge, Simulation, Contracts maps)
- `policy_critic/research/` (offline RL, calibration, reward design, finance RL literature)

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

## Cross-Domain Contract Governance

V7's cross-domain contract surface is now centralized in the **root contract authority**.

| What | Where |
|---|---|
| **Canonical cross-domain contract list** | `contracts/registry.json` |
| **TradeOutcome JSON Schema** | `contracts/schemas/trade_outcome.schema.json` |
| **SimulationOutput schema (input to V7 adapters)** | `contracts/schemas/simulation_output.schema.json` |
| **SimulationOutput → TradeOutcome field mapping** | `contracts/mappings/simulation_to_v7.json` |
| **Version compatibility rules** | `contracts/compatibility.json` |
| **Root cross-domain governance** | `docs/architecture/governance.md` |
| **V7 adapter stub (future adapter boundary)** | `integration/adapters/v7_adapter.py` |
| **System-level tests** | `integration/tests/` (registry, schema parity, boundary, smoke) |

### Key Governance Rules for V7

1. **V7 owns runtime/policy semantics** — runtime orchestration, persistence, lifecycle, DecisionEvent, TradeOutcome normalization.
2. **V7 must NOT duplicate simulation economic truth.** The `contracts/schemas/simulation_output.schema.json` is the canonical SimulationOutput; V7 consumes it via adapters.
3. **V7 must NOT import simulation or alphaforge internals.** Cross-domain communication happens through `integration/adapters/` only.
4. **TradeOutcome schema in `contracts/schemas/trade_outcome.schema.json`** is the canonical cross-domain definition. V7-local contract docs (`v7/docs/contracts/trade_outcome.md`) remain authoritative for V7-internal semantics.
5. **V7 may host simulation execution via adapters** but must not duplicate simulation's cost/horizon/exit logic.

## Core Position

V7 is not a greenfield reset.
It is a disciplined extension of the best V6 decisions:

- atomic contract family
- runtime-hosted simulation engine / one simulated-truth layer
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
- first model scopes: `SWING`, `SCALP`, and `AGGRESSIVE_SCALP` (mode-centric architecture, see `v7_mode_centric_architecture.md`)
- scope defaults:
  - `SWING`: `primary_interval` **4h**, `context_intervals` **1d**, `refinement_intervals` **1h**
  - `SCALP`: `primary_interval` **1h** (or 30m), `context_intervals` **4h**, `refinement_intervals` **15m**
  - `AGGRESSIVE_SCALP`: `primary_interval` **15m**, `context_intervals` **1h**, `refinement_intervals` **5m**
- runtime hosts the simulation engine; training/evaluation consume it through side-effect-free adapters with scope-specific profiles
- Monte Carlo robustness mode runs on top of the runtime simulation engine and is not live execution truth
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
- runtime-hosted simulation engine / one simulated-truth layer
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
