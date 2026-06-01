# Migration from V7 — Extracting Simulation Into Its Own Authority

## Purpose

This document explains the migration of simulation truth documentation and authority from `v7/docs/` to the new top-level `/simulation` directory. It maps old locations to new locations and describes what changed and what did not.

## Current State (Before Migration)

Before this migration, simulation truth was documented within V7:

| Old Location | Content |
|---|---|
| `v7/docs/pipeline/simulation.md` | Simulation engine semantics, mode profiles, contracts |
| `v7/docs/implementation/phase_2_simulation_truth_layer.md` | Implementation phase for simulation |
| `v7/docs/runtime/simulation_engine.md` | Runtime hosting and simulation ownership |
| `v7/docs/vision.md` | "Runtime-hosted simulation truth layer" |
| `v7/docs/architecture.md` | "Runtime simulation engine" layer descriptions |
| `v7/docs/ai_summary.md` | Simulation as V7-owned layer |
| `v7/docs/contracts/trade_outcome.md` | TradeOutcome references simulation |
| `v7/docs/pipeline/labels.md` | Labels derived from simulation truth |
| `alphaforge/docs/phase_plans/P2__*.md` | "calls V7 simulation API" wording |

The previous phrasing in V7 docs was:

> "V7 owns the simulation truth layer."
> "Runtime owns simulation execution."
> "AlphaForge calls V7 simulation API."

## New State (After Migration)

| New Location | Content |
|---|---|
| `simulation/README.md` | Authority overview, ownership, relationship map |
| `simulation/docs/vision.md` | What simulation is, success definition, principles |
| `simulation/docs/architecture.md` | Component design, data flow, module structure, dependency rules |
| `simulation/docs/contracts.md` | SimulationInput, SimulationOutput, ActionOutcome, etc. |
| `simulation/docs/profiles.md` | Mode-specific profiles (SWING, SCALP, AGGRESSIVE_SCALP) |
| `simulation/docs/cost_model.md` | Fee, slippage, net R semantics |
| `simulation/docs/exits_and_horizons.md` | Stop, target, time exit, unresolved, invalidated |
| `simulation/docs/no_trade_quality.md` | No-trade classification and metrics |
| `simulation/docs/lineage_and_versioning.md` | All version surfaces and bump rules |
| `simulation/docs/replay_paper_and_runtime_hosting.md` | V7 hosting, adapters, side-effect isolation |
| `simulation/docs/monte_carlo.md` | Diagnostic distributional simulation |
| `simulation/docs/validation.md` | Test gates and import-boundary requirements |
| `simulation/docs/migration_from_v7.md` | This document |
| `simulation/docs/ai_summary.md` | Dense machine-readable synthesis |
| `simulation/docs/phases/S0–S6` | Implementation phase plans |

The new phrasing is:

> "`/simulation` owns economic truth semantics and contracts."
> "V7 runtime hosts/executes simulation operationally through stable contracts."
> "AlphaForge consumes `/simulation` authority outputs through deterministic side-effect-free adapters."

## What Changed

1. **Ownership boundary**: Simulation truth is now a first-class top-level authority (`/simulation`), not buried inside V7 docs.
2. **V7 role clarified**: V7 runtime is the operational **host** and **executor**, not the **semantic owner** of simulation truth.
3. **AlphaForge role clarified**: AlphaForge is a **consumer** of simulation outputs, not a caller of "V7 simulation API." It calls `/simulation` adapters.
4. **lib boundary**: Simulation is explicitly NOT in `lib/`. `lib/` stays primitive.
5. **Dependency rules made explicit**: simulation must not import v7 policy/risk/runtime, alphaforge must not import simulation internals beyond adapters.

## What Did NOT Change

1. **Simulation semantics themselves**: The same stop/target/cost/horizon/MFE/MAE/regret semantics from V7 docs are preserved and migrated.
2. **Mode profiles**: SWING (4h), SCALP (1h), AGGRESSIVE_SCALP (15m) profiles are identical.
3. **Contract shapes**: SimulationInput and SimulationOutput are formalized but semantically identical to what V7 docs described.
4. **Exit families**: STOP_HIT, TARGET_HIT, TIME_EXIT, HORIZON_END, UNRESOLVED, INVALIDATED are preserved.
5. **Cost model**: Fee + slippage → net R formula is identical.
6. **No-trade first-class**: NO_TRADE remains a first-class action.
7. **Versioning**: All version surfaces are preserved and documented more explicitly.
8. **Monte Carlo**: Monte Carlo is still diagnostic/distributional, not realized truth.

## How V7 References Should Change

### Old Wording → New Wording

| Old | New |
|---|---|
| "V7 owns the simulation truth layer" | "`/simulation` owns economic truth semantics and contracts. V7 runtime hosts/executes simulation operationally." |
| "V7 runtime simulation engine" | "`/simulation` engine, hosted by V7 runtime" |
| "Runtime owns simulation execution" | "V7 runtime hosts/executes the `/simulation` engine operationally" |
| "The runtime-hosted simulation engine" | "The `/simulation` engine (hosted by V7 runtime)" |
| "Pipeline consumes runtime simulation outputs" | "AlphaForge consumes `/simulation` outputs through adapters" |
| "Simulation runs in runtime" | "Simulation is owned by `/simulation`, executed by V7 runtime" |

### V7 Docs That Need Updates

| Doc | Update |
|---|---|
| `v7/docs/vision.md` | Update simulation references to point to `/simulation` |
| `v7/docs/architecture.md` | Update simulation layer description |
| `v7/docs/ai_summary.md` | Update simulation ownership and relationship map |
| `v7/docs/pipeline/simulation.md` | Replace with pointer to `/simulation/docs/` |
| `v7/docs/runtime/simulation_engine.md` | Replace with pointer, keep runtime hosting section |
| `v7/docs/implementation/phase_2_*.md` | Reference `/simulation` phases S0–S6 |
| `v7/docs/README.md` | Add `/simulation` to reading order |

## How AlphaForge References Should Change

| Doc | Update |
|---|---|
| `alphaforge/docs/phase_plans/P2__*.md` | Change "calls V7 simulation API" to "consumes /simulation outputs through adapters" |
| `alphaforge/docs/ai_summary__v7_alphaforge_xgb.md` | Add `/simulation` as external authority |
| `alphaforge/docs/phase_plans/P4__*.md` | Reference `/simulation` for evaluation truth |
| `alphaforge/docs/phase_plans/P8__*.md` | Reference `/simulation` for paper/shadow validation parity |

## How lib References Should Change

| Doc | Update |
|---|---|
| `lib/docs/README.md` | Add explicit rule: `simulation/` is NOT in `lib/`. Cost primitives are basic only. |

## Migration Steps

```txt
[ ] 1. Create /simulation directory with all docs and phase plans
[ ] 2. Migrate V7 simulation truth content into /simulation/docs/
[ ] 3. Update V7 docs to point to /simulation (pointer docs, not deletion)
[ ] 4. Update AlphaForge P2 and downstream docs
[ ] 5. Update root README with /simulation in the tree
[ ] 6. Update ai_summary files
[ ] 7. Search for stale "V7 owns simulation truth" wording
[ ] 8. Search for hidden simulator references
[ ] 9. Add import-boundary tests for simulation/
[ ] 10. Run validation gates
```

## Risks

| Risk | Mitigation |
|---|---|
| V7 docs lose simulation content during pointer migration | Preserve existing docs as-is; add pointer at top; do not delete |
| AlphaForge references break | Update P2 phase plan explicitly; all downstream phases inherit |
| Someone adds simulation to lib/ | Import boundary tests catch this |
| Someone adds hidden simulator to alphaforge | Audit-based test catches this |
| V7 runtime silently takes over simulation semantics | Code review + architecture doc clarifies hosting vs owning |

## Rollback

If this migration needs to be rolled back:

1. Restore V7 docs from git history (they are preserved, not deleted)
2. Remove `/simulation` directory
3. Revert AlphaForge doc changes
4. Revert README changes

---

## Document Authority

**Canonical hub:** [ai_summary.md](ai_summary.md) — read this first for the full system synthesis and table of contents.

**Related docs for this topic:**

| [vision.md](vision.md) | What migrated (authority vision) |
| [architecture.md](architecture.md) | What migrated (component design) |
| [contracts.md](contracts.md) | What migrated (contract surfaces) |
| All other docs in this directory | Content migrated from v7/docs/ |
    
**Parent:** [../README.md](../README.md) — authority overview and ownership diagram.

**For implementation:** See [phases/](phases/) for v4.1.1 phase plans S0–S6.

**For validation:** See [validation.md](validation.md) for required test gates.

