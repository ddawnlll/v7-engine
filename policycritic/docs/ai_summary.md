# V7 Policy Critic — AI Summary

> Last updated: 2026-06-23
> Adapted from: `~/src/trading-bot-pr/policycritic/docs/ai_summary.md`
> Canonical authority: `v7/docs/policy_critic/ai_summary.md`
> For: Claude and other AI agents working in this repo

## One-Line Context

The Policy Critic is a **docs/design-only** advisory safety layer. No RL implementation exists. No runtime behavior has been changed. The critic reviews proposed actions, scores risk, adjusts confidence, and recommends NO_TRADE — all under deterministic gates that retain hard veto.

## V7 Authority Boundary

This is the verified authority hierarchy per `CLAUDE.md` domain boundaries and the existing codebase:

```
Runtime Risk Gate (hard: max daily loss, max drawdown, circuit breaker) → VETO
    ↑
Final Operational Gate (execution eligibility, cooldown, exposure) → VETO
    ↑
V7 Policy Gates (confidence, expected-R, regime, degradation, portfolio, risk) → VETO
    ↑
Policy Critic (advisory: risk score, confidence downweight, NO_TRADE rec) → ADVISORY ← NOT IMPLEMENTED
    ↑
AlphaForge Scorer — XGBoost (LONG/SHORT/NO_TRADE alpha scores) → PROPOSES ← NOT IMPLEMENTED
    ↑
V6 Inference Engine (sibling repo: current live decision path) → PROPOSES ← IMPLEMENTED
    ↑
Execution Layer — ExecutionOrchestrator (only executes gate-cleared actions)
```

**Shield principle**: Layers marked VETO are deterministic, rule-based, and verified. The Policy Critic (when implemented) sits UNDER shields. The critic advises; the gate decides.

## Existing Repo Facts (Verified in v7-engine)

### What Exists Today

| Component | File | Status |
|---|---|---|
| Shadow decision persistence | `runtime/db/repos/shadow_policy_repo.py` | IMPLEMENTED |
| Policy dataset persistence | `runtime/db/repos/policy_dataset_repo.py` | IMPLEMENTED |
| Scan runtime loop | `runtime/runtime/scan_runtime.py` | IMPLEMENTED |
| Execution orchestrator | `runtime/runtime/execution_orchestrator.py` | IMPLEMENTED |
| Simulation engine (economic truth) | `simulation/engine/engine.py` | IMPLEMENTED |
| Simulation cost model | `simulation/engine/costs.py` | IMPLEMENTED (funding DEFERRED) |
| Contract registry (15 contracts) | `contracts/registry.json` | IMPLEMENTED |
| Policy Critic design (canonical) | `v7/docs/policy_critic/design.md` | DOCS_COMPLETE |
| Policy Critic codebase maps (4 maps) | `v7/docs/policy_critic/codebase_maps/` | DOCS_COMPLETE |
| Policy Critic research (4 files) | `v7/docs/policy_critic/research/` | DOCS_COMPLETE |
| AlphaForge scorer design | `alphaforge/docs/ai_summary__v7_alphaforge_xgb.md` | SPEC_ONLY |
| AlphaForge prediction schema | `alphaforge/docs/schemas/prediction_schema_v1.json` | SPEC_ONLY |

### What Does NOT Exist (Blocker List)

- ❌ Replay buffer (no (s,a,r,s',terminal) tuple store)
- ❌ Reward shaper (no unified reward computation pipeline)
- ❌ Event bus (all execution is synchronous/poll-based)
- ❌ Online learning (retraining is batch-only via SQL)
- ❌ Off-policy evaluation (no FQE, no OPE protocol)
- ❌ Trained RL model (no RL training infrastructure)
- ❌ PolicyCriticReview contract (not yet registered in contracts/registry.json)
- ❌ AlphaForge scorer/runtime code (alphaforge/src/ contains only .gitkeep)
- ❌ V7-native policy bridge code (v7/src/ contains only .gitkeep)
- ❌ Per-decision portfolio drawdown (only aggregate run-level drawdown exists)
- ❌ Per-direction expected_R in production (only in AlphaForge prediction_schema_v1.json)

### V6 Backend Facts (old_repo_context_unverified)

The old docs claimed CatBoost is the primary V6 backend with XGBoost as challenger. **This claim cannot be verified in v7-engine** — the V6 inference engine lives in a sibling repo (`/home/erfolg/src/trading-bot/v6/`). The v7-engine AlphaForge design (`ai_summary__v7_alphaforge_xgb.md`) specifies **XGBoost** as the primary model class for the V7-native scorer. This doc set uses "XGBoost" throughout when referring to the planned V7-native scorer, consistent with the AlphaForge design.

**Verification note**: The AlphaForge design explicitly specifies XGBoost as the model class (sections 7.5, 11-13 of `ai_summary__v7_alphaforge_xgb.md`). The claim that "CatBoost is primary" originates from the old trading-bot-pr repo and is marked `old_repo_context_unverified`.

### Architecture Readiness

- Overall V7 implementation readiness: **early design/spec phase** (v7/src/ is greenfield)
- RL readiness: **0/10** — no RL infrastructure exists
- Reward infrastructure: **partial** — simulation engine produces authoritative reward surface; no tuple emitter
- Event-driven architecture: **0/10** — synchronous scan loop only
- Online learning: **0/10** — batch retraining only via SQL

## Current Holds

These are the active blocker conditions. Do NOT propose removing them.

| Hold | Condition | Rationale |
|---|---|---|
| HOLD-REPLAY | No replay buffer | Prerequisite for all offline learning |
| HOLD-RL | No RL implementation | No (s,a,r,s',terminal) tuples, no OPE, no training harness |
| HOLD-CRITIC | No critic implementation | Advisory only; gates retain hard veto |
| HOLD-SCALP | SCALP/AGGRESSIVE modes | Locked thresholds require empirical evidence |
| HOLD-FUNDING | Funding cost model DEFERRED | Perp trades blocked at G3; spot-only valid |
| HOLD-V7-SRC | v7/src/ greenfield | AlphaForge P5/P6/P9 phases not started |
| HOLD-LIVE | No live trading | Extensive shadow evidence required before any live authority |

## Next Steps (In Order)

1. **Docs complete** (this task — ACCP v7 policy critic docs port)
2. **PolicyCriticReview contract** — define the audit record schema, register in contracts/registry.json
3. **Replay buffer emitter** — start recording (state, action, realized_r_net, mae_r, next_state) tuples from simulation engine
4. **V1 shadow rule-based critic** — heuristic risk scoring, shadow-only, zero live influence
5. **V2 supervised critic** — XGBoost model predicting realized_r
6. **Off-policy evaluation** — FQE, DSR, PBO validation
7. **V3 offline IQL critic** — IQL-trained Q-function for risk scoring (distributional + conformal)
8. **V4 constrained optimizer** — sizing/exit proposals within shield limits

**Each transition requires evidence, not ambition.** Gates: DSR p<0.05, PBO<0.10, walk-forward ≥4/5 folds, champion anti-regression, shadow burn-in, human approval.

## Files NOT To Modify

When working on Policy Critic tasks, never modify:

- `runtime/runtime/scan_runtime.py` (scan loop orchestration)
- `runtime/runtime/execution_orchestrator.py` (operational hard gate)
- `runtime/services/analyzer_engine_adapter.py` (V6 adapter bridge)
- `simulation/engine/engine.py` (economic truth)
- `simulation/engine/costs.py` (cost model)
- `runtime/db/models.py` (existing DB models)
- `runtime/db/repos/shadow_policy_repo.py` (existing shadow repo)
- `runtime/db/repos/policy_dataset_repo.py` (existing policy dataset repo)
- `contracts/registry.json` (only append new contracts, never modify existing)
- Any file outside `policycritic/docs/` and `reports/accp/`

## Related Documents

- [[README.md]] — Folder overview
- [[policy_critic_design.md]] — Full architecture
- [[rl_intro_for_v7.md]] — RL teaching doc
- [[pipeline.md]] — Versioned pipeline plan
- [[authority_and_boundaries.md]] — Boundary specification
- [[replay_buffer_design.md]] — Replay buffer technical spec
- [[rollout_plan.md]] — Staged rollout plan
- [[source_inventory.md]] — Curated bibliography
- `v7/docs/policy_critic/ai_summary.md` — Canonical critic ai_summary
- `v7/docs/policy_critic/design.md` — Canonical design recommendation
- `v7/docs/policy_critic/codebase_maps/` — Codebase grounding maps (4 files)
