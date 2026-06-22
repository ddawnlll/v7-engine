# policycritic/docs

> Created: 2026-06-23
> Adapted from: `~/src/trading-bot-pr/policycritic/docs/` (old repo source material)
> Target repo: `~/src/v7-engine`
> Status: **Docs/Design Only** — No production code, no runtime changes.

## What This Folder Is

This folder contains the research documentation and design specification for the **V7 Policy Critic** — a proposed advisory layer that reviews trade decisions and emits risk assessments, confidence adjustments, and NO_TRADE veto recommendations.

All content in this folder is **documentation and design only**. No runtime behavior has been changed. No production code has been written. No RL implementation exists.

This folder is a **supplementary, flat-navigation version** of the existing `v7/docs/policy_critic/` doc tree. The canonical authority remains `v7/docs/policy_critic/ai_summary.md` and `v7/docs/policy_critic/design.md`. When these docs conflict with the canonical docs, the canonical docs win.

## What Is the Policy Critic?

The Policy Critic is a planned **advisory safety layer** for V7. It sits between the hard gate (AlphaForge evidence) and the final operational gate (runtime execution eligibility). Its job:

- **Review** proposed LONG/SHORT actions from AlphaForge evidence
- **Score** risk using heuristic rules (V1) or learned value functions (V3+)
- **Reduce** confidence when risk exceeds calibrated thresholds
- **Recommend** NO_TRADE when expected value is negative
- **Produce** PolicyCriticReview audit records for shadow-mode evidence

The critic **does not** open trades, close trades, make final decisions, bypass hard gates, bypass runtime risk gates, create new action enums, or hold live veto authority.

## V7 Authority Truth Hierarchy

Per `CLAUDE.md` domain boundaries:

```
simulation > realized > contract > runtime > model
```

The Policy Critic is the **lowest authority** in this hierarchy. It can **downgrade but never upgrade** execution eligibility.

## Why V7 Needs It

The AlphaForge scorer (XGBoost-based, planned in P5-P6 phases, not yet implemented) will propose LONG/SHORT/NO_TRADE with alpha scores. The V7 policy gates will apply deterministic thresholds. But there is no learned component that can:

1. Estimate the **expected value** of a proposed action before it executes
2. Detect **regime-conditional** risk patterns the deterministic gates cannot express
3. Provide **shadow audit evidence** before granting any live influence
4. Evolve from heuristic → supervised → offline RL in a **staged, evidence-gated** manner

The Policy Critic fills this gap — but only as an advisory layer under deterministic shields.

## What It Does and Does Not Do

### What the Policy Critic CAN Do

| Capability | V1 | V2 | V3 | V4 |
|---|---|---|---|---|
| Review proposed actions | ✅ | ✅ | ✅ | ✅ |
| Score action risk (heuristic) | ✅ | ✅ | ✅ | ✅ |
| Score action risk (supervised) | — | ✅ | ✅ | ✅ |
| Score action risk (offline RL) | — | — | ✅ | ✅ |
| Reduce confidence on high risk | ✅ | ✅ | ✅ | ✅ |
| Recommend NO_TRADE veto | ✅ | ✅ | ✅ | ✅ |
| Shadow audit evidence | ✅ | ✅ | ✅ | ✅ |
| Propose sizing adjustments | — | — | — | ✅ |

### What the Policy Critic CANNOT Do (Any Version)

- ❌ Open trades (execution remains with runtime execution_orchestrator)
- ❌ Close trades (outcome resolution remains with TradeOutcome lifecycle)
- ❌ Make final decisions (authority: V7 Policy → Portfolio → Risk → Runtime)
- ❌ Bypass hard gates (deterministic V7 policy gates)
- ❌ Bypass runtime risk gates (daily loss limit, max drawdown, circuit breaker)
- ❌ Create new action enums (action space locked to LONG_NOW/SHORT_NOW/NO_TRADE)
- ❌ Bypass cost/funding/risk holds
- ❌ Hold live veto authority

## Current Status

**Docs/Design Only.** The Policy Critic exists only as:

- Design documentation in `v7/docs/policy_critic/` and this folder
- Shadow persistence infrastructure (`runtime/db/repos/shadow_policy_repo.py`)
- Policy dataset persistence (`runtime/db/repos/policy_dataset_repo.py`)
- The simulation engine (`simulation/engine/engine.py`) which produces the reward surface
- AlphaForge contract schemas defining the alpha evidence flow

No RL training has been run. No critic inference exists. No replay buffer exists. No reward shaper exists. The `v7/src/` directory is greenfield (only `.gitkeep`).

### Repo Fact Verification Note

The source material in `~/src/trading-bot-pr/policycritic/docs/` referenced several files that **do not exist** in `~/src/v7-engine`. These claims are marked `old_repo_context_unverified` throughout this doc set.

Specifically, the following old-repo paths are **not present** in v7-engine:
- `runtime/contracts/policy_contract.py` — old_repo_context_unverified
- `runtime/services/policy/policy_engine.py` — old_repo_context_unverified
- `runtime/services/policy/rule_based_policy_engine.py` — old_repo_context_unverified
- `runtime/services/policy/rl_policy_stub.py` — old_repo_context_unverified
- `docs/v7/architecture_review.md` — old_repo_context_unverified
- `docs/v6/ai_summary.md` — old_repo_context_unverified

The following paths **do exist** in v7-engine and are verified:
- `runtime/db/repos/shadow_policy_repo.py` — ShadowPolicyRepository
- `runtime/db/repos/policy_dataset_repo.py` — PolicyDatasetRepository
- `runtime/runtime/scan_runtime.py` — ScanRuntime scan loop
- `simulation/engine/engine.py` — Economic truth authority
- `v7/docs/policy_critic/ai_summary.md` — Canonical critic design
- `v7/docs/policy_critic/design.md` — Full design recommendation
- `contracts/registry.json` — 15 registered cross-domain contracts
- `alphaforge/docs/ai_summary__v7_alphaforge_xgb.md` — AlphaForge scorer design

The V6 inference engine lives in a **sibling repo** (`/home/erfolg/src/trading-bot/v6/`), not in v7-engine. The v7-engine repo imports V6 via the runtime adapter (`runtime/services/analyzer_engine_adapter.py`).

## Documents In This Folder

| Document | Purpose |
|---|---|
| [README.md](README.md) | This file — folder overview and design position |
| [ai_summary.md](ai_summary.md) | Agent context: repo facts, boundaries, current holds |
| [policy_critic_design.md](policy_critic_design.md) | Full architecture: authority hierarchy, data flow, contract sketch |
| [rl_intro_for_v7.md](rl_intro_for_v7.md) | RL teaching doc: fundamentals to safe RL for V7 engineers |
| [pipeline.md](pipeline.md) | Four-stage pipeline: V1 shadow → V2 supervised → V3 IQL → V4 optimizer |
| [authority_and_boundaries.md](authority_and_boundaries.md) | Detailed boundary spec: veto chain, gate hierarchy, governance |
| [replay_buffer_design.md](replay_buffer_design.md) | Technical spec: tuple fields, storage, lineage, prerequisites |
| [rollout_plan.md](rollout_plan.md) | Staged rollout with entry/exit criteria and PR sequencing |
| [source_inventory.md](source_inventory.md) | Curated bibliography with trust ratings and V7 applicability |

## Key Design Position

> V7 Policy Critic is an **advisory layer** that reviews proposed actions, scores risk, reduces confidence, recommends NO_TRADE veto, and produces shadow-mode audit evidence. It does not open trades, close trades, bypass gates, or hold live veto authority.

## Related Repo Files (Verified in v7-engine)

- `contracts/registry.json` — Canonical cross-domain contract registry (15 contracts)
- `v7/docs/policy_critic/ai_summary.md` — Canonical critic dense synthesis
- `v7/docs/policy_critic/design.md` — Full design recommendation
- `v7/docs/policy_critic/codebase_maps/v7_pipeline_map.md` — Decision pipeline map
- `v7/docs/policy_critic/codebase_maps/contracts_runtime_map.md` — Contracts + runtime map
- `v7/docs/policy_critic/codebase_maps/simulation_map.md` — Simulation/reward surface map
- `v7/docs/policy_critic/codebase_maps/alphaforge_map.md` — AlphaForge scorer map
- `runtime/db/repos/shadow_policy_repo.py` — ShadowDecision + ExpectancyLabelProfile persistence
- `runtime/db/repos/policy_dataset_repo.py` — PolicyExample persistence
- `simulation/engine/engine.py` — Economic truth: simulate(SimulationInput) → SimulationOutput
- `simulation/engine/costs.py` — Authoritative cost model (fee + slippage; funding DEFERRED)
- `alphaforge/docs/ai_summary__v7_alphaforge_xgb.md` — AlphaForge XGBoost scorer design
- `v7/docs/ai_summary.md` — V7 pipeline dense synthesis
- `v7/docs/pipeline/policy.md` — V7 policy gates specification
- `v7/docs/runtime/runtime_integration.md` — Per-mode readiness states, execution eligibility stack
