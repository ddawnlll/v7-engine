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

## 3. Executive Summary

The Policy Critic is a proposed advisory component that inserts between V7 policy gates and the final operational gate. It consumes AlphaForge alpha evidence, emits a PolicyCriticReview verdict (ALLOW / DOWNWEIGHT_CONFIDENCE / VETO_TO_NO_TRADE / REQUIRE_REVIEW), and V7 policy enacts the verdict — not the critic itself. Implementation requires 12 PRs across 6 phases. Zero implementation exists today. This file maps every file that would be created, touched, or must not be touched.

---

## 4. Future PR Sequence

### PR Summary

| PR | Phase | Scope | Files Touched | Live Authority |
|----|-------|-------|--------------|----------------|
| PR-01 | 1 | Contract-only critic verdict schema | 3 created, 2 modified | None |
| PR-02 | 2 | Replay buffer schema + migration | 2 created, 1 modified | None |
| PR-03 | 2 | Replay writer (shadow-only) | 2 created | None |
| PR-04 | 3 | Offline dataset builder | 2 created | None |
| PR-05 | 3 | Leakage + temporal validation checks | 3 created | None |
| PR-06 | 3 | OPE/FQE evaluator | 2 created | None |
| PR-07 | 3 | IQL/CQL offline training sandbox | 3 created | None |
| PR-08 | 3 | Calibration + distributional uncertainty wrapper | 2 created | None |
| PR-09 | 4 | Shadow runtime runner | 4 created, 1 modified | Shadow only |
| PR-10 | 4 | Shadow reporting dashboard/API | 2 created | Shadow only |
| PR-11 | 5 | Guarded influence proposal | 3 created, 1 modified | Advisory (gated) |
| PR-12 | 6 | Business validation + go/no-go review | 3 created | Conditional |

### Detailed PR Specifications

#### PR-01: Contract-Only Critic Verdict Schema
- **Scope**: Define PolicyCriticReview contract. Zero runtime code.
- **Files created**: `contracts/schemas/policy_critic_review.schema.json`, `contracts/fixtures/policy_critic_review_minimal.json`, `contracts/mappings/policy_critic_to_decision_event.json`
- **Files modified**: `contracts/registry.json` (append), `contracts/compatibility.json` (append)
- **Allowed behavior**: Schema validation passes. Fixture roundtrip test passes.
- **Forbidden behavior**: Any Python code importing or using the schema.
- **Acceptance criteria**: `make check-contracts` passes. Schema validates against metaschema.
- **Evidence required**: Schema parity test output.
- **Rollback**: Remove appended entries, delete new files.
- **Merge blockers**: Schema validation failure. Registry inconsistency.

#### PR-02: Replay Buffer Schema + Migration
- **Scope**: Define ReplayBufferTuple table + migration. Zero data emission.
- **Files created**: `runtime/db/repos/replay_buffer_repo.py`, migration file
- **Files modified**: `runtime/db/models.py` (append model)
- **Allowed behavior**: Migration runs forward and backward cleanly.
- **Forbidden behavior**: Any tuple emission. Any critic invocation.
- **Acceptance criteria**: Migration applies and rolls back. Model validates.
- **Evidence required**: Migration test output.
- **Rollback**: Downgrade migration, remove model.

#### PR-03: Replay Writer (Shadow-Only)
- **Scope**: Tuple assembler that pairs canonical state with SimulationOutput. Persists tuples. Zero live influence.
- **Files created**: `runtime/services/policy/__init__.py`, `runtime/services/policy/replay_buffer_emitter.py`
- **Allowed behavior**: Tuples stored in replay_buffer_tuple table. Data split labeled correctly.
- **Forbidden behavior**: Any critic inference. Any execution influence. Any modification to scan loop.
- **Acceptance criteria**: ≥ 100 tuples stored. NO_TRADE records ≥ 20%. Temporal leakage test passes.
- **Evidence required**: Tuple count. NO_TRADE ratio. Leakage test.
- **Rollback**: Delete emitter service. Truncate replay buffer table.

#### PR-04: Offline Dataset Builder
- **Scope**: Build train/val/test splits from replay buffer with purge+embargo.
- **Files created**: `runtime/services/policy/offline_dataset_builder.py`, `runtime/services/policy/dataset_split_validator.py`
- **Allowed behavior**: Produces split datasets as file artifacts. Splits validated for temporal ordering.
- **Forbidden behavior**: Any training. Any inference.
- **Acceptance criteria**: 70/15/15 split. No overlap detected. Purge verified.
- **Evidence required**: Split statistics. Leakage detection report.
- **Rollback**: Delete dataset files.

#### PR-05: Leakage + Temporal Validation Checks
- **Scope**: Automated tests verifying no temporal leakage in replay buffer and dataset splits.
- **Files created**: `tests/runtime/policy_critic/test_replay_buffer_no_leakage.py`, `tests/runtime/policy_critic/test_temporal_splits.py`, `tests/runtime/policy_critic/test_no_lookahead.py`
- **Allowed behavior**: Tests pass. CI enforces.
- **Forbidden behavior**: Any production code changes.
- **Acceptance criteria**: All leakage tests pass. CI gate enforced.
- **Evidence required**: CI output.
- **Rollback**: Delete test files (no production impact).

#### PR-06: OPE/FQE Evaluator
- **Scope**: Implement Fitted Q-Evaluation + DSR/PBO computation.
- **Files created**: `runtime/services/policy/ope_evaluator.py`, `runtime/services/policy/dsr_pbo_calculator.py`
- **Allowed behavior**: Computes FQE 95% CI, DSR p-value, PBO estimate from offline dataset.
- **Forbidden behavior**: Any critic deployment. Any live influence.
- **Acceptance criteria**: FQE CI computed. DSR/PBO values produced. Reports generated.
- **Evidence required**: OPE report with CI, DSR, PBO values.
- **Rollback**: Delete evaluator files (no production impact).

#### PR-07: IQL/CQL Offline Training Sandbox
- **Scope**: Train IQL and CQL critics on offline dataset. Produce model artifacts.
- **Files created**: `alphaforge/training/critic_iql_v3.py`, `alphaforge/training/critic_cql_v3.py`, `alphaforge/training/critic_training_config.py`
- **Allowed behavior**: Training runs. Model artifacts saved. Training metrics logged.
- **Forbidden behavior**: Any model deployment. Any runtime inference.
- **Acceptance criteria**: IQL expectile loss converges. CQL conservative penalty applied. Bellman error not diverging.
- **Evidence required**: Training curves. Final model artifacts.
- **Rollback**: Delete training scripts and artifacts.

#### PR-08: Calibration + Distributional Uncertainty Wrapper
- **Scope**: Conformal calibration retrofit on IQL distributional Q-head. Uncertainty quantification.
- **Files created**: `alphaforge/training/critic_calibration.py`, `alphaforge/training/critic_uncertainty.py`
- **Allowed behavior**: Calibration report produced. Coverage measured.
- **Forbidden behavior**: Any runtime deployment.
- **Acceptance criteria**: Conformal coverage within tolerance. Quantile crossing resolved.
- **Evidence required**: Calibration report. Coverage-vs-nominal plot.
- **Rollback**: Delete calibration files.

#### PR-09: Shadow Runtime Runner
- **Scope**: Wire critic into scan runtime in shadow-only mode. Record PolicyCriticReview for every decision. Zero execution influence.
- **Files created**: `v7/src/v7/alpha/policy_bridge/policy_critic/__init__.py`, `v7/src/v7/alpha/policy_bridge/policy_critic/contracts.py`, `v7/src/v7/alpha/policy_bridge/policy_critic/critic_engine.py`, `runtime/services/policy/policy_critic_adapter.py`
- **Files modified**: `runtime/runtime/scan_runtime.py` (add critic invocation point — advisory only)
- **Allowed behavior**: Critic invoked for every scan decision. PolicyCriticReview persisted. Zero execution influence.
- **Forbidden behavior**: Any confidence adjustment applied to execution. Any gate override.
- **Acceptance criteria**: 100% scan coverage. Zero live influence confirmed. Safe degrade tested.
- **Evidence required**: Shadow audit log. Zero-influence verification.
- **Rollback**: Disable critic via config. Remove invocation from scan_runtime.

#### PR-10: Shadow Reporting Dashboard/API
- **Scope**: API endpoint and dashboard for shadow critic verdicts.
- **Files created**: `runtime/api/routes/policy_critic_shadow.py`, interface dashboard component
- **Allowed behavior**: Read-only API. Dashboard displays verdicts.
- **Forbidden behavior**: Any write/execute capability.
- **Acceptance criteria**: API returns verdicts. Dashboard renders.
- **Evidence required**: API response. Dashboard screenshot.
- **Rollback**: Remove route and dashboard component.

#### PR-11: Guarded Influence Proposal
- **Scope**: Enable critic DOWNWEIGHT_CONFIDENCE and VETO_TO_NO_TRADE in SWING mode only. V7 policy enacts verdicts. Human approval required.
- **Files created**: `runtime/services/policy/policy_critic_registry_service.py`, `v7/src/v7/alpha/policy_bridge/policy_critic/rule_based_critic_v1.py`, `v7/src/v7/alpha/policy_bridge/policy_critic/supervised_critic_v2.py`
- **Files modified**: `runtime/runtime/scan_runtime.py` (verdict enactment)
- **Allowed behavior**: DOWNWEIGHT adjusts confidence via recorded multiplier. VETO sets NO_TRADE via policy. All changes visible in runtime_interpretation.
- **Forbidden behavior**: Direct execution control. Gate bypass. SCALP/AGGRESSIVE influence.
- **Acceptance criteria**: Veto rate bounded. DSR maintained. Human approval documented.
- **Evidence required**: 30-day shadow evidence. DSR/PBO report. Human approval record.
- **Rollback**: Disable influence via config. Revert to shadow-only.

#### PR-12: Business Validation + Go/No-Go Review
- **Scope**: ≥ 90 day evidence package. V4 constrained optimizer (if applicable). Live consideration decision.
- **Files created**: `v7/src/v7/alpha/policy_bridge/policy_critic/iql_critic_v3.py`, `v7/src/v7/alpha/policy_bridge/policy_critic/constrained_optimizer_v4.py`, evidence package report
- **Allowed behavior**: Evidence compiled. Decision documented.
- **Forbidden behavior**: Automatic live promotion.
- **Acceptance criteria**: All metrics maintained ≥ 90 days. All stakeholders signed off.
- **Evidence required**: 90-day evidence package. Signed approvals.
- **Rollback**: Disable all critic influence. Archive evidence.

---

## 5. Implementation Readiness Checklist

### Schema & Contract (6 items)
- [ ] PolicyCriticReview schema versioned (v1.0.0)
- [ ] Schema validates against JSON Schema metaschema
- [ ] Fixture roundtrip test passes
- [ ] Registry entry consistent with existing entries
- [ ] Compatibility entry defines breaking-change rules
- [ ] Contract reviewed by at least one reviewer

### Data Infrastructure (8 items)
- [ ] Replay buffer table migration applied and rollback tested
- [ ] Tuple assembler routes through /simulation engine (NOT runtime historical engine)
- [ ] NO_TRADE records captured (≥ 20% of total)
- [ ] Temporal ordering enforced in all data splits
- [ ] Look-ahead leakage blocked (purge + embargo validated)
- [ ] Survivorship bias documented and mitigated (delisted assets included)
- [ ] Reward normalization statistics computed on training split only
- [ ] Replay buffer retention policy defined

### Training & Evaluation (10 items)
- [ ] FQE implementation matches literature (Fu et al. 2021)
- [ ] OPE report exists with 95% CI
- [ ] DSR p-value computed with correct N_trials
- [ ] PBO estimate via CSCV procedure
- [ ] Walk-forward validation with ≥ 4/5 folds and purge+embargo
- [ ] Conformal calibration report with coverage-vs-nominal
- [ ] Distributional uncertainty report (quantile spread analysis)
- [ ] Bellman error monitored (not diverging)
- [ ] IQL/CQL disagreement rate tracked and bounded
- [ ] Champion anti-regression test against previous critic version

### Runtime Safety (10 items)
- [ ] Shadow-only runner: zero execution influence
- [ ] Zero-influence verification test passes
- [ ] Safe degrade: critic unavailable → system unchanged
- [ ] Critic inference latency < 10ms p99
- [ ] Kill switch defined and tested (POLICY_CRITIC_ACTIVE=false)
- [ ] Rollback tested: disable critic → revert to gate-only
- [ ] Human approval gate exists (required for Phase 5+)
- [ ] Audit log complete: every verdict in runtime_interpretation
- [ ] No hidden veto: every suppression reason visible
- [ ] Model registry separation: critic artifacts separate from scorer artifacts

### Business Validation (8 items)
- [ ] Shadow comparison ≥ 90 days
- [ ] False veto cost measured (shadow: vetoed trades that would have won)
- [ ] False allow cost measured (shadow: allowed trades that lost)
- [ ] Per-regime breakdown shows no single-regime degradation
- [ ] Drawdown profile not worsened
- [ ] Transaction cost impact analyzed
- [ ] Business go/no-go checkpoint documented
- [ ] All stakeholders signed off for any live transition

### Authority Boundary (6 items)
- [ ] Critic never calls ExecutionOrchestrator directly
- [ ] Critic never imports broker/order APIs
- [ ] Critic verdict ALWAYS has is_advisory=true
- [ ] V7 policy enacts verdict (NOT critic)
- [ ] Operational hard gate always runs after critic
- [ ] Simulation truth hierarchy preserved (critic uses simulation realized_r_net only)

**Total: 48 checklist items**

---

## 6. Definition of Implementation-Ready

A Policy Critic version is **implementation-ready** when:

1. All schema and contract items pass (6/6)
2. All data infrastructure items pass (8/8)
3. Training metrics meet evidence gates (DSR p<0.05, PBO<0.10, FQE CI overlaps)
4. All runtime safety items pass (10/10)
5. Shadow evidence ≥ required period (30 days for V1→V2, 90 days for live consideration)
6. Human approval documented for any live influence

---

## 7. How the Policy Critic Connects Without Becoming Final Authority

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
