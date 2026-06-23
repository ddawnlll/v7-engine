# Phase 4 — Shadow Critic Runtime

> Status: NOT STARTED
> Prerequisite: Phase 3 complete (V2 critic trained and OPE-validated)
> Duration: 2-3 weeks estimated

## Goal

Wire the trained V2 supervised critic into the scan runtime loop in **shadow-only mode**. The critic records PolicyCriticReview for every decision but has zero influence on execution. This phase proves the runtime integration without any live risk.

## Entry Criteria

- [ ] Phase 3 exit criteria met (V2 critic trained, OPE validated)
- [ ] PolicyCriticReview contract registered (Phase 1)
- [ ] Replay buffer emitting tuples (Phase 2)
- [ ] V2 model artifact available and versioned
- [ ] Critic inference latency measured and acceptable (< 10ms)

## Deliverables

1. **`v7/src/v7/alpha/policy_bridge/policy_critic/__init__.py`** — Package init
2. **`v7/src/v7/alpha/policy_bridge/policy_critic/contracts.py`** — `PolicyCriticReview` dataclass
3. **`v7/src/v7/alpha/policy_bridge/policy_critic/critic_engine.py`** — Abstract `PolicyCritic` Protocol: `review(state, proposed_action, context) → PolicyCriticReview`
4. **`v7/src/v7/alpha/policy_bridge/policy_critic/supervised_critic_v2.py`** — V2 critic implementation: loads XGBoost artifact, produces expected_value_r prediction, emits PolicyCriticReview
5. **`runtime/services/policy/policy_critic_registry_service.py`** — Critic registration service (mirrors `AnalyzerEngineRegistryService`): registers critic instances satisfying Protocol, selects active critic via `POLICY_CRITIC_ACTIVE` setting, `SHADOW_CRITIC` for shadow comparison.
6. **`runtime/services/policy/policy_critic_adapter.py`** — Integration adapter: invoked from scan runtime after engine returns AnalysisResult, before execution_orchestrator. Calls active critic, persists PolicyCriticReview via `ShadowPolicyRepository`.

## Exit Criteria

- [ ] Critic invoked for 100% of scan decisions (shadow mode)
- [ ] PolicyCriticReview persisted for every decision
- [ ] Zero live influence on execution (confirmed by audit log)
- [ ] Critic inference latency < 10ms p99
- [ ] Runtime stability: zero critic-related crashes in 7 days
- [ ] Safe degrade: critic unavailable → system continues unchanged
- [ ] Integration test: scan → critic → review → persist roundtrip

## Files Involved

**Created**: `v7/src/v7/alpha/policy_bridge/policy_critic/__init__.py`, `contracts.py`, `critic_engine.py`, `supervised_critic_v2.py`; `runtime/services/policy/policy_critic_registry_service.py`, `policy_critic_adapter.py`
**Modified**: `runtime/runtime/scan_runtime.py` (add critic invocation point — advisory only, no gate change)

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Critic inference latency slows scan loop | Low | Delayed signals | Batch inference; timeout with safe degrade |
| Model loading fails on startup | Medium | No critic available | Safe degrade: continue without critic |
| Shadow persistence overload | Low | DB bloat | Retention policy; async write |

## What Must NOT Be Implemented in This Phase

- ❌ Any confidence adjustment applied to execution (VETO not enacted)
- ❌ Any gate behavior change
- ❌ Any change to `recommended_action`
- ❌ Any live influence whatsoever
- ❌ V3 IQL critic in runtime (V2 supervised only)
- ❌ Removal of the safe degrade path

## Rollback Plan

Disable critic via `POLICY_CRITIC_ACTIVE=false`. Remove critic invocation from scan_runtime. Delete critic service files. No data loss — critic records are shadow-only.
