# Policy Critic — Folder Tree

> Last updated: 2026-06-23
> Status: Docs/Design Only

## Current Docs Layout

```
policycritic/
  docs/
    README.md                           ← Folder overview, design position, verified repo facts
    ai_summary.md                       ← Agent context, authority boundary, current holds
    folder_tree.md                      ← THIS FILE — planned docs and implementation layout
    implementation_file_map.md          ← Current + future files, ownership, connection plan
    problem_statement.md                ← Exact problem, scope, success criteria

    policy_critic_design.md             ← Full architecture, authority hierarchy, data flow, contract sketch
    rl_intro_for_v7.md                  ← RL teaching doc: fundamentals through safe RL
    pipeline.md                         ← Four-stage pipeline: V1→V4 with release gates
    authority_and_boundaries.md         ← Veto chain, gate hierarchy, governance
    replay_buffer_design.md             ← Tuple spec, storage design, prerequisites
    rollout_plan.md                     ← Staged rollout with PR sequencing
    source_inventory.md                 ← Curated bibliography with trust ratings

    phase_plans/
      README.md                         ← Phase plan overview and reading order
      phase_0_research_and_design.md    ← Current phase: docs, research, design lock
      phase_1_observability_and_schema.md  ← Contracts, schemas, audit trail
      phase_2_shadow_replay_buffer.md   ← Replay buffer emitter + storage
      phase_3_offline_training_and_evaluation.md ← Supervised + OPE/FQE + IQL training
      phase_4_shadow_critic_runtime.md  ← Shadow-only critic in scan loop
      phase_5_guarded_influence.md      ← Advisory influence with hard gate limits
      phase_6_business_validation.md    ← Profitability evidence, live readiness

    research/
      README.md                         ← Research index and reading order
      rl_basics.md                      ← MDP, Bellman, Q-learning, policy gradients
      offline_rl.md                     ← Offline RL problem, distribution shift, algorithms
      implicit_q_learning_iql.md        ← IQL deep-dive
      conservative_q_learning_cql.md    ← CQL deep-dive
      decision_transformer.md           ← DT architecture and why rejected for V7
      distributional_rl_quantile_q.md   ← QR-DQN, IQN, risk-aware gating
      conformal_calibration.md          ← Conformal prediction, exchangeability, time-series
      ope_and_fqe.md                    ← Off-policy evaluation, FQE, importance sampling
      backtest_overfitting_dsr_pbo.md   ← DSR, PBO, CSCV, walk-forward
      safe_rl_and_shielding.md          ← Shielded RL, safety architectures
      reward_hacking.md                 ← Specification gaming, trading failure modes
      financial_ml_validation.md        ← WF-CV, purging, embargo, meta-labeling
      gbdt_vs_deep_rl_for_tabular_finance.md ← Trees vs neural nets on tabular data
      trading_rl_failure_modes.md       ← OOD, regime shift, look-ahead, survivorship

    business/
      README.md                         ← Business section overview
      business_plan.md                  ← Strategic rationale, staged investment, ROI logic
      profitability_calculation.md      ← Scenario-based formulas, break-even analysis
      unit_economics.md                 ← Per-trade economics, cost structure
      risk_register.md                  ← Ranked risks with mitigations
      go_to_market_internal_strategy.md ← Internal rollout, team readiness, operational plan

    quality/
      README.md                         ← Quality section overview
      self_scorecard.md                 ← Internal self-score across 10 dimensions
      independent_ai_review_packet.md   ← Packet for external AI review
      acceptance_rubric.md              ← Partner acceptance criteria
```

## Planned Implementation Layout (Future)

When implementation is authorized, files will be created under the v7-engine repo following the existing domain boundaries:

```
v7/src/v7/alpha/policy_bridge/          ← V7-native policy bridge (greenfield today)
  __init__.py
  policy_critic/
    __init__.py
    contracts.py                         ← PolicyCriticReview dataclass
    critic_engine.py                     ← Abstract critic interface
    rule_based_critic_v1.py              ← V1: heuristic risk scorer
    supervised_critic_v2.py              ← V2: XGBoost expected-value estimator
    iql_critic_v3.py                     ← V3: distributional IQL Q-function
    critic_calibration.py                ← Conformal calibration retrofit
    critic_ensemble.py                   ← IQL/CQL cross-check

runtime/services/policy/                 ← Runtime critic services (new directory)
  __init__.py
  policy_critic_registry_service.py      ← Critic registration (mirrors AnalyzerEngineRegistryService)
  replay_buffer_emitter.py               ← Tuple emitter: state + SimulationOutput → (s,a,r,s',t)
  policy_critic_adapter.py               ← Critic integration into scan runtime

runtime/db/repos/                        ← Extended persistence (existing dir)
  replay_buffer_repo.py                  ← ReplayBufferTuple CRUD

contracts/schemas/                       ← New contract (existing dir)
  policy_critic_review.schema.json       ← PolicyCriticReview JSON Schema

contracts/fixtures/                      ← New fixture (existing dir)
  policy_critic_review_minimal.json      ← Minimal valid fixture

contracts/mappings/                      ← New mapping (existing dir)
  policy_critic_to_decision_event.json   ← Critic verdict → runtime_interpretation
```

## Files That Must NOT Be Touched (Docs-Only Phase)

```
runtime/runtime/scan_runtime.py          ← Scan loop orchestration
runtime/runtime/execution_orchestrator.py ← Operational hard gate
runtime/services/analyzer_engine_adapter.py ← V6 adapter bridge
simulation/engine/engine.py              ← Economic truth
simulation/engine/costs.py               ← Cost model
runtime/db/models.py                     ← DB models
contracts/registry.json                  ← Only append new contracts later
alphaforge/docs/                         ← AlphaForge authority docs
v7/docs/pipeline/                        ← V7 pipeline authority docs
```

## Canonical Authority Note

The authoritative Policy Critic docs live at `v7/docs/policy_critic/`. This `policycritic/docs/` tree is a supplementary, flat-navigation expansion. When conflicts arise, `v7/docs/policy_critic/` wins.
