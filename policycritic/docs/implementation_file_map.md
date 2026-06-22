# Implementation File Map

> Status: Docs/Design Only — No implementation exists
> Created: 2026-06-23

## 1. Current Repo Files Related to Policy Critic

These files exist in v7-engine today and are directly relevant to a future Policy Critic implementation.

### 1.1 Shadow + Dataset Persistence (IMPLEMENTED)

| File | What It Owns | Critic Relevance |
|------|-------------|-----------------|
| `runtime/db/repos/shadow_policy_repo.py` | `ShadowPolicyDecision` + `ExpectancyLabelProfile` CRUD | V1 critic writes PolicyCriticReview here |
| `runtime/db/repos/policy_dataset_repo.py` | `PolicyExample` CRUD with regime-action stats | Training data persistence for V2+ |
| `runtime/db/models.py` | `ShadowPolicyDecision`, `PolicyExample`, `ExpectancyLabelProfile` ORM models | Schema extended for replay buffer tuples |

### 1.2 Runtime Decision Path (IMPLEMENTED)

| File | What It Owns | Critic Relevance |
|------|-------------|-----------------|
| `runtime/runtime/scan_runtime.py` | Scan loop orchestration, per-(symbol,interval,mode) analyzer calls | Critic invoked here between analyzer and execution |
| `runtime/runtime/execution_orchestrator.py` | Operational hard gate before order placement | Critic verdict consumed; gate runs after critic |
| `runtime/services/analyzer_engine_adapter.py` | V6→runtime normalization boundary | Interim critic integration point |
| `runtime/services/analyzer_engine_registry_service.py` | Engine registration pattern (Protocol-based) | Critic registry mirrors this pattern |
| `runtime/runtime/runtime_router.py` | `TradeModeRouter`: per-mode champion selection | Critic runs after routing, before execution |

### 1.3 Economic Truth (IMPLEMENTED)

| File | What It Owns | Critic Relevance |
|------|-------------|-----------------|
| `simulation/engine/engine.py` | `simulate(SimulationInput) → SimulationOutput` | Single source of `realized_r_net` reward |
| `simulation/engine/costs.py` | `fee_cost_r`, `slippage_cost_r`, `total_cost_r` | Authoritative cost model for reward computation |
| `simulation/contracts/models.py` | `ActionOutcome`, `NoTradeOutcome`, `PathMetrics`, `SimulationOutput` | Reward surface contract types |

### 1.4 Contracts (IMPLEMENTED)

| File | What It Owns | Critic Relevance |
|------|-------------|-----------------|
| `contracts/registry.json` | 15 registered cross-domain contracts | PolicyCriticReview to be registered here |
| `contracts/compatibility.json` | Version compatibility matrix | New critic→DecisionEvent pair to be added |
| `contracts/schemas/trade_outcome.schema.json` | TradeOutcome schema with `realized_r`, `regret_r`, `mae_r` | Reward signal schema |
| `contracts/mappings/alphaforge_to_v7.md` | AlphaForge→V7 handoff bridge | Critic sits between these two layers |

### 1.5 Design Authority (DOCS)

| File | What It Owns | Critic Relevance |
|------|-------------|-----------------|
| `v7/docs/policy_critic/ai_summary.md` | Canonical critic dense synthesis | Authority for design decisions |
| `v7/docs/policy_critic/design.md` | Full design recommendation (IQL + distributional + conformal) | Primary design reference |
| `v7/docs/policy_critic/codebase_maps/v7_pipeline_map.md` | V6/V7 decision flow map with file:line refs | Critic insertion point |
| `v7/docs/policy_critic/codebase_maps/contracts_runtime_map.md` | Contract registration, runtime wiring, integration points | How critic connects |
| `v7/docs/policy_critic/codebase_maps/simulation_map.md` | Simulation reward surface, replay infrastructure | Training data source |
| `v7/docs/policy_critic/codebase_maps/alphaforge_map.md` | AlphaForge scorer, calibration, field surface | Input feature surface |
| `alphaforge/docs/ai_summary__v7_alphaforge_xgb.md` | XGBoost scorer design, alpha score formulas | Critic consumes these outputs |

---

## 2. Future Files Needed for Implementation

### 2.1 Phase 1: Contracts + Schema (Stage 1)

| Future File | What It Would Own | Why It's Needed |
|-------------|------------------|-----------------|
| `contracts/schemas/policy_critic_review.schema.json` | JSON Schema for PolicyCriticReview | Contract registry requirement |
| `contracts/fixtures/policy_critic_review_minimal.json` | Minimal valid fixture | Schema parity testing |
| `contracts/mappings/policy_critic_to_decision_event.json` | Verdict → runtime_interpretation field mapping | Runtime wiring |

### 2.2 Phase 2: Replay Buffer (Stage 2)

| Future File | What It Would Own | Why It's Needed |
|-------------|------------------|-----------------|
| `runtime/db/repos/replay_buffer_repo.py` | `ReplayBufferTuple` CRUD | Tuple persistence |
| `runtime/services/policy/replay_buffer_emitter.py` | Tuple assembler: pairs state + SimulationOutput | Training data generation |

### 2.3 Phase 3: Training (Stages 4-6)

| Future File | What It Would Own | Why It's Needed |
|-------------|------------------|-----------------|
| `alphaforge/training/critic_supervised_v2.py` | XGBoost expected-value regressor training | V2 supervised critic |
| `alphaforge/training/critic_iql_v3.py` | IQL distributional Q-function training | V3 offline RL critic |
| `alphaforge/training/off_policy_evaluation.py` | FQE, DSR, PBO evaluation harness | Evidence gates |

### 2.4 Phase 4-5: Runtime (Stages 3, 6-7)

| Future File | What It Would Own | Why It's Needed |
|-------------|------------------|-----------------|
| `v7/src/v7/alpha/policy_bridge/policy_critic/contracts.py` | `PolicyCriticReview` dataclass | Typed contract |
| `v7/src/v7/alpha/policy_bridge/policy_critic/critic_engine.py` | Abstract `PolicyCritic` Protocol | Registration interface |
| `v7/src/v7/alpha/policy_bridge/policy_critic/rule_based_critic_v1.py` | V1 heuristic risk scorer (~200 LoC) | Shadow-only baseline |
| `v7/src/v7/alpha/policy_bridge/policy_critic/supervised_critic_v2.py` | V2 XGBoost expected-value estimator | Supervised critic |
| `v7/src/v7/alpha/policy_bridge/policy_critic/iql_critic_v3.py` | V3 IQL distributional Q-function | Offline RL critic |
| `v7/src/v7/alpha/policy_bridge/policy_critic/critic_calibration.py` | Conformal calibration retrofit | Uncertainty quantification |
| `v7/src/v7/alpha/policy_bridge/policy_critic/critic_ensemble.py` | IQL/CQL cross-check | Disagreement detection |
| `runtime/services/policy/__init__.py` | New policy services package | Directory initialization |
| `runtime/services/policy/policy_critic_registry_service.py` | Critic registration + selection | Mirrors AnalyzerEngineRegistryService |
| `runtime/services/policy/policy_critic_adapter.py` | Critic invocation in scan path | Runtime integration |

---

## 3. How the Policy Critic Connects Without Becoming Final Authority

### 3.1 Integration Architecture

```
AlphaForge Scorer (proposes action + alpha scores)
    │
    ▼
V7 Policy Gates (hard gates: confidence, expected-R, regime, degradation)
    │
    ▼
Policy Critic (ADVISORY: reviews, scores risk, adjusts confidence)
    │  emits PolicyCriticReview (ALLOW / DOWNWEIGHT / VETO_TO_NO_TRADE / REQUIRE_REVIEW)
    ▼
V7 Policy enacts critic verdict (NOT the critic itself):
    - ALLOW → policy_passed stays true
    - DOWNWEIGHT → multiply confidence, re-trip confidence gate
    - VETO_TO_NO_TRADE → policy sets recommended_action=NO_TRADE
    - REQUIRE_REVIEW → should_surface_to_review=true
    │
    ▼
Portfolio + Risk Gates
    │
    ▼
Runtime Execution Eligibility (operational hard gate)
    │
    ▼
ExecutionOrchestrator (only executes gate-cleared actions)
```

### 3.2 Why the Critic Cannot Become Final Authority

1. **Code path**: The critic is invoked BETWEEN gates, not as the final step. The operational hard gate in `execution_orchestrator.py` always runs after.
2. **Advisory verdict**: Critic emits a `PolicyCriticReview` with `is_advisory=true`. V7 policy ENACTS the verdict — the critic itself never changes `recommended_action`.
3. **No execution access**: The critic has no import path to `ExecutionOrchestrator`, broker APIs, or order placement.
4. **Config-gated**: `POLICY_CRITIC_ACTIVE` setting; bypass when unavailable. Safe degrade: policy proceeds unchanged.
5. **Rollback**: Critic can be disabled per-mode via readiness state transitions or kill-switch.

### 3.3 Files That Must NOT Be Touched (All Phases)

These files are outside the Policy Critic's authority boundary and must never be modified as part of critic implementation:

- `runtime/runtime/scan_runtime.py` — may call critic via adapter, but critic must not modify scan logic
- `runtime/runtime/execution_orchestrator.py` — operational hard gate must remain independent
- `simulation/engine/engine.py` — economic truth must remain single-source
- `simulation/engine/costs.py` — cost model must not be bypassed
- `contracts/registry.json` — only append, never modify existing entries
- `v7/docs/pipeline/policy.md` — policy gate specification remains authoritative
- `alphaforge/docs/ai_summary__v7_alphaforge_xgb.md` — AlphaForge remains alpha discovery authority
