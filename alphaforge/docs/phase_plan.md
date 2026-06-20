# AlphaForge Phase Plan

**Purpose:** Define the implementation phases for AlphaForge from authority lock through V7 handoff.

**Authority:** This is the canonical implementation roadmap. LOCKED for phases defined here.

---

## Phase Overview

| Phase | ID | Title | Status |
|-------|----|-------|--------|
| P0.8B | Current | Authority Lock + Docs + Contracts | IN PROGRESS |
| P0.8C | Current | Re-Audit After Authority Lock | IN PROGRESS |
| P0.9A | Next | Implementation Scaffold | PENDING |
| P0.9B | Future | Data/Label/Feature Pipeline | PENDING |
| P0.9C | Future | All-Mode Research Reports | PENDING |
| P1.0 | Future | V7 Handoff Candidate | PENDING |

---

## P0.8B — Authority Lock (Current)

**What:** Lock AlphaForge authority boundaries, create all docs, schemas, fixtures, mapping docs, and update contracts registry.

**Output:**
- 13 authority docs (ai_summary, discovery_authority, alpha_thesis_lifecycle, data_contract, feature_contract, label_contract, report_contracts, validation_contract, model_artifact_contract, handoff_to_v7, storage_policy, phase_plan, decision_log)
- 10 JSON schemas under contracts/schemas/alphaforge/
- 5 minimal fixtures under contracts/fixtures/alphaforge/
- 2 mapping docs under contracts/mappings/
- Updated contracts/registry.json
- Cross-doc links in v7 docs and README

**Explicitly NOT done in this phase:**
- No AlphaForge source code
- No model training
- No data download
- No simulation changes
- No V7 source changes

---

## P0.8C — Re-Audit (Current)

**What:** Re-audit AlphaForge readiness after P0.8B docs and contracts are locked.

**Output:**
- Re-audit ACCP-YAML report
- Combined completion report
- Updated authority verdict
- Verification that all tests pass

---

## P0.9A — Implementation Scaffold (Next)

**What:** Create minimal AlphaForge package structure without full model training.

**Scope:**
- Package structure under `alphaforge/src/`
- Contract reader utilities (schema loading, validation)
- Report writer interfaces
- Fixture validation tests
- CI integration (basic)
- No actual training, no data pipeline yet

**Prerequisites:** P0.8B + P0.8C PASS

---

## P0.9B — Data/Label/Feature Pipeline

**What:** Implement the data → feature → label pipeline.

**Scope:**
- Market data loading and normalization
- Feature computation per FeatureSetSpec
- Label generation from SimulationOutput
- Data quality validation
- Storage integration (external artifact paths)
- Pipeline tests

**Prerequisites:** P0.9A complete. Simulation running.

---

## P0.9C — All-Mode Research Reports

**What:** Produce the first round of all-mode research reports.

**Scope:**
- SCALP primary research report
- AGGRESSIVE_SCALP primary research report
- SWING secondary baseline report
- Walk-forward validation per mode
- AlphaForgeResearchReport (aggregate)
- Research report tests

**Prerequisites:** P0.9B complete. Feature and label datasets available.

---

## P1.0 — V7 Handoff Candidate

**What:** Produce the first V7HandoffPackage for V7 acceptance evaluation.

**Scope:**
- First alpha candidate packaged for V7
- Full evidence package (all reports, model artifact, calibration)
- V7 gate mapping complete
- Handoff to V7 acceptance pipeline

**Prerequisites:** P0.9C complete. At least one mode has CANDIDATE_FOR_V7_GATES verdict.

---

## Implementation Rules

1. **No implementation in P0.8B or P0.8C.** These are docs + contracts only.
2. **No source code changes to lib/, simulation/, v7/, runtime/, or interface/.** AlphaForge is additive.
3. **No fake empirical results.** Research reports must be based on actual data.
4. **No premature threshold locking.** SCALP/AGGRESSIVE_SCALP thresholds stay HOLD until empirical evidence.
5. **Funding DEFERRED preserved.** Do not remove this hold without funding model implementation.

---

## Related Docs

- [ai_summary.md](ai_summary.md)
- [discovery_authority.md](discovery_authority.md)
- [decision_log.md](decision_log.md)
- [../../v7/docs/roadmap.md](../../v7/docs/roadmap.md) — overall V7 roadmap

## Related Contracts

- All schemas under [../../contracts/schemas/alphaforge/](../../contracts/schemas/alphaforge/)

## Forbidden Assumptions

- Phase completion is NOT based on time estimates; it's based on evidence.
- P0.9A-C may be adjusted based on P0.8C re-audit findings.
- SWING implementation priority does NOT exceed SCALP/AGGRESSIVE_SCALP.

## Open Holds

- All holds from [decision_log.md](decision_log.md) apply.
- Phase timelines depend on empirical research outcomes.
