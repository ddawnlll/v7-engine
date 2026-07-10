# V7 Engine — AI Meta Hub

## META

This is the **repo-root entry point** for any AI agent or LLM code agent loading into `/home/erfolg/src/v7-engine/`. It is NOT a dense synthesis. It is a **thin map** that tells you which subsystem's `ai_summary.md` to read for your task, and provides cross-domain rules that span all subsystems.

**Reading order for an AI:**
1. Read `CLAUDE.md` for working instructions (design lock semantics, task completion protocol, forbidden actions, domain boundaries).
2. Read this file to orient yourself.
3. Then read the ai_summary.md for the subsystem(s) you are working on.
4. Return here for cross-domain conflict resolution.

**If you read only one doc, read `CLAUDE.md`.** It encodes how to work safely in this repo. If this doc conflicts with a subsystem authority doc, the subsystem authority doc wins.

---

## Repo Layout

```
/                              (this hub)
  ai_summary.md                ← you are here
  contracts/                   cross-domain contract schemas & registry
  docs/                        cross-domain governance & runbook
  v7/                          V7 pipeline docs, sources, ai_summary
  runtime/                     operational Python backend, scan loop, analyzer, learning, schema, API
  interface/                   React + TypeScript + Vite operator UI
  simulation/                  simulation truth layer (stop/target/horizon/fee/slippage semantics)
  alphaforge/                  alphaforge subsystem
  data/                        generated data artifacts
  lib/                         shared library code
  configs/                     centralized training config, profiles, gates, data scope
  scripts/                     operational scripts
  test.sh                      top-level test runner
```

---

## Subsystem Authority Map

| Subsystem | ai_summary.md | Scope | Read This When... |
|---|---|---|---|
| **V7 Pipeline** | `v7/docs/ai_summary.md` | Mode-centric pipeline (simulation → labels → features → model → calibration → policy → portfolio → risk → evaluation → monitoring), contracts (AnalysisRequest, AnalysisResult, DecisionEvent, TradeOutcome), config surface, invariants, test requirements, implementation phases | You need contract semantics, pipeline rules, mode-specific config, invariants, or V7-internal lifecycle details. |
| **Runtime** | `runtime/docs/ai_summary.md` | Python backend: architecture, scan loop, analyzer pipeline, learning layer, self-learning, PostgreSQL schema, FastAPI route groups, API architecture rules, runbook, diagnostic snapshots | You need API routes, schema tables, analyzer behavior, runtime flow, circuit breaker rules, or operational runbooks. |
| **Interface** | `interface/docs/ai_summary.md` | React UI: workspace structure, page ownership, component architecture, migration plan, data freshness, current-state report | You need UI routing rules, page responsibilities, data freshness cadence, or the interface rework plan. |
| **Simulation** | `simulation/docs/ai_summary.md` | Simulation truth engine: stop/target multipliers, fee/slippage, R computation, MFE/MAE, path quality, monte carlo | You need simulation output semantics, profile schema, or simulation-to-v7 field mappings. |
| **Contract schemas** | *(no ai_summary — use `contracts/registry.json` + schema files)* | Cross-domain contract schemas, version compatibility, field mapping | You need canonical TradeOutcome or SimulationOutput schema definitions. |
| **AlphaForge** | `alphaforge/docs/ai_summary.md` | Alpha discovery authority, label engine, validation, V7 handoff | You work on alpha discovery, label contracts, feature research, validation, or handoff packages. |
|| **Policy Critic** | `v7/docs/policy_critic/ai_summary.md` (canonical) + `policycritic/docs/README.md` (supplementary) | Advisory offline-RL component: research, design, business plan | You need critic design, RL research, phase plans, or business case. |
|| **Training Config** | **`configs/training.yaml`** + **`configs/profiles/`** | Centralized training profiles: research/full scope, simulation profile references, Makefile defaults | You need to change training scope, symbols, intervals, or simulation profile parameters. |

---

## Quick-Start Decision Tree

| Your Task | Read First |
|---|---|
| How does the V7 pipeline work end-to-end? | `v7/docs/ai_summary.md` (all 42 sections) |
| What API routes exist and what do they return? | `runtime/docs/ai_summary.md` → R.7 API Surface |
| How does the analyzer make trading decisions? | `runtime/docs/ai_summary.md` → R.3 Analyzer |
| What tables are in the operational database? | `runtime/docs/ai_summary.md` → R.6 Operational Schema |
| How does the learning layer adjust behavior? | `runtime/docs/ai_summary.md` → R.4 Learning Layer |
| What does the UI look like and how is it organized? | `interface/docs/ai_summary.md` → I.2–I.5 |
| I need to add a new page to the UI. Where does it go? | `interface/docs/ai_summary.md` → I.3 Target Info Architecture |
| How do simulation semantics affect labels/policy? | `simulation/docs/ai_summary.md` then `v7/docs/ai_summary.md` → sections 12–21 |
| What contracts exist and what validation rules apply? | `v7/docs/ai_summary.md` → sections 4–7 (contract summaries) + `contracts/schemas/` |
| Where are the implementation phases documented? | `v7/docs/ai_summary.md` → section 26 |
| What config keys control the system? | `v7/docs/ai_summary.md` → section 28 |
| What invariants must never be violated? | `v7/docs/ai_summary.md` → section 29 |
| I'm seeing an error — where's the exception reference? | `v7/docs/ai_summary.md` → section 35 |

---

## Cross-Domain Authority & Governance

### Root Authorities
- **Contract schemas:** `contracts/registry.json`, `contracts/schemas/*.schema.json`
- **Governance:** `docs/architecture/governance.md`
- **Simulation truth semantics:** `/simulation/`
- **V7-local pipeline:** `v7/docs/`
- **Runtime operational engine:** `runtime/docs/`
- **Interface operator UI:** `interface/`

### Truth Hierarchy (when subsystems disagree)
1. Simulation truth (simulation output semantics)
2. Realized market outcome truth (actual exchange fills)
3. Contract truth (schema validation rules)
4. Runtime interpretation truth (operational lifecycle)
5. Model explanation (ML model outputs)

### Cross-Domain Rules
- V7 pipeline consumes simulation outputs through stable contracts; it does NOT reimplement simulation
- Runtime hosts simulation but does NOT define simulation semantics
- Interface consumes runtime API; it does NOT reconstruct engine state
- Contract schemas live in `contracts/` (not in any subsystem)
- Governance across subsystem boundaries lives in `docs/architecture/governance.md`
- For cross-domain conflicts, `docs/architecture/governance.md` wins

### Integration Flow (high-level)
```
Exchange Data → Runtime Market Ingestion → Canonical State
  → V7 Pipeline (features → model → policy → portfolio → risk)
    → AnalysisRequest/Result contracts
      → Runtime lifecycle (DecisionEvent → Execution/TradeOutcome)
        → Interface (operator visualization)
```

### V4→V7 Migration Status
- `runtime/` and `interface/` have been promoted from V4 into the V7 authority tree
- Cross-doc links within those trees still reference legacy V4 paths (e.g. `/Users/hootie/src/trading-bot/v4/...`); these are legacy anchors awaiting path normalization
- Operational semantics from these trees supersede the V4 originals for V7-internal work
- `/simulation/` was previously under V7 runtime docs and has been promoted to a top-level authority

---

## Key Contacts by Area

| Area | Primary Authority | Fallback |
|---|---|---|
| Pipeline semantics (labels, features, model, calibration, policy, portfolio, risk, evaluation, monitoring) | `v7/docs/ai_summary.md` | Original doc in `v7/docs/pipeline/` |
| Contracts (AnalysisRequest, AnalysisResult, DecisionEvent, TradeOutcome) | `v7/docs/ai_summary.md` sections 4–7 | Original doc in `v7/docs/contracts/` + `contracts/schemas/` |
| Simulation truth | `simulation/docs/ai_summary.md` | `contracts/schemas/simulation_output.schema.json` |
| Runtime engineering (API, analyzer, scan loop, schema, learning) | `runtime/docs/ai_summary.md` | Original doc in `runtime/docs/` |
| Interface engineering (routing, pages, components, data freshness) | `interface/docs/ai_summary.md` | Original doc in `interface/` |
| Implementation phases | `v7/docs/ai_summary.md` section 26 | `v7/docs/implementation/` |
| Executor support | `v7/docs/ai_summary.md` section 27 | `v7/docs/v7_executor_support_pack/` |
| File & naming conventions | `v7/docs/ai_summary.md` section 40 | `v7/docs/v7_llm_rules.md` |

---

## END OF AI META HUB

This document is the top-level entry point for the V7 Engine repository. For detailed synthesis, consult each subsystem's `ai_summary.md` as indicated in the table above.
