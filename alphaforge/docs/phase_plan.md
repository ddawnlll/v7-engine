# AlphaForge Phase Plan

**Purpose:** Define the implementation phases for AlphaForge from authority lock through V7 handoff.

**Authority:** This is the canonical implementation roadmap. LOCKED for phases defined here.

---

## Phase Overview

| Phase | ID | Title | Status |
|-------|----|-------|--------|
| P0.8B | Complete | Authority Lock + Docs + Contracts | DONE |
| P0.8C | Complete | Re-Audit After Authority Lock | DONE |
| P0.8D | Complete | Profitability/Efficiency Squeeze Audit | DONE |
| P0.8E | Complete | Contract/Docs Profitability Patch | DONE |
| P0.9A | Next | Implementation Scaffold | REDESIGN_IN_PROGRESS |
| P0.9A-FREEZE | Current | Freeze + Metric Ownership Redesign | IN_PROGRESS |
| XSMOM | Complete | Cross-Sectional Momentum Baseline | DONE |
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

## P0.8C — Re-Audit (Complete)

**What:** Re-audit AlphaForge readiness after P0.8B docs and contracts are locked.

**Output:**
- Re-audit ACCP-YAML report
- Combined completion report
- Updated authority verdict
- Verification that all tests pass

---

## P0.8D — Profitability/Efficiency Squeeze Audit (Complete)

**What:** Audit AlphaForge profitability thesis and efficiency surface. Identified critical contract/doc drift that must be fixed before P0.9A scaffold.

**Output:**
- Profitability/efficiency squeeze audit ACCP-YAML report
- Identified gate mapping drift, timeframe drift, label schema gaps, validation contract misalignment
- Recommended P0.8E targeted patch before P0.9A

---

## P0.8E — Contract/Docs Profitability Patch (Complete)

**What:** Targeted contract, schema, fixture, and documentation patch to fix critical drift identified by P0.8D audit. Repaired the contract/documentation foundation so P0.9A can safely build on correct contracts.

**Status: DONE (2026-06-23).** All 8 objectives completed. 295 tests pass with 0 failures. See `reports/p0_8e_alphaforge_profitability_contract_patch.accp.yaml` for completion report.

**Scope:**
- Fix gate mapping to V7 canonical G0-G10
- Reconcile timeframe stacks to locked simulation profiles
- Complete AlphaForgeLabel schema (gross/net cost, NO_TRADE quality, lineage)
- Align validation contract to V7 gates (6-fold minimum, canonical regimes, MHT)
- Add MHT/data-snooping controls
- Tighten schema strictness (nested required fields)
- Mark legacy docs as superseded
- Gate P0.9A on P0.8E PASS
- Add/update fixture validation, contract semantics, and schema strictness tests

**Prerequisites:** P0.8B + P0.8C + P0.8D PASS

**Exit condition:** All 5 validation commands pass. P0.9A unblocked.

---

## P0.9A — Implementation Scaffold (REDESIGN_IN_PROGRESS)

**What:** Create minimal AlphaForge package structure without full model training.

**Scope:**
- Package structure under `alphaforge/src/`
- Contract reader utilities (schema loading, validation)
- Report writer interfaces
- Fixture validation tests
- CI integration (basic)
- No actual training, no data pipeline yet

**Prerequisites:** P0.8B + P0.8C + P0.8D + P0.8E PASS

---

## P0.9A-FREEZE — Freeze + Metric Ownership Redesign (IN_PROGRESS)

**What:** Pause the original P0.9A scaffold implementation. Redesign to account for layer metric ownership (Metric Philosophy) discovered during v0.25 diagnostics repair and v0.30 metric plumbing audit.

**Scope:**
- Freeze P0.9A scaffold source tree
- Document layer metric ownership in discovery_authority.md
- Redesign scaffold to respect metric layer boundaries

**Prerequisites:** P0.8B + P0.8C + P0.8D + P0.8E PASS

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

## XSMOM — Cross-Sectional Momentum Baseline (DONE)

**Issue:** #v034 — Cross-sectional momentum (XSMOM) baseline for all 16 symbols.

**What:** Research and implement cross-sectional momentum alpha discovery. Rank symbols by trailing returns, go long top quantile, short bottom quantile. Baseline validated for 16 Binance USDT perpetual symbols.

**Output:**
- XSMOM baseline implementation
- 16-symbol ranking and scoring
- Cross-sectional momentum research report

**Lock status:** LOCKED_INITIAL_BASELINE. Recalibrate after first walk-forward on real data.

**Evidence:** Committed as v0.34A.

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
