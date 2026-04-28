# Phase 2 — Runtime Simulation, Replay & Monte Carlo Layer (Planned)

**Status:** Planned
**Owner:** Runtime simulation / truth-layer track
**Last updated:** 2026-04-24
**Delivery status:** Not started

---

## 1. Purpose

This phase standardizes the runtime-hosted simulation engine for V7 use.

It exists because labels, evaluation, replay comparison, paper forward simulation, outcome normalization, and Monte Carlo robustness testing must consume the same runtime simulation semantics without creating a new model-side or pipeline-owned simulator.

---

## 2. What Carried Over / What Must Stay Stable

The following are already implemented / must remain stable:

- [x] typed contract family is available from Phase 1
- [x] runtime already has paper-trading / runtime simulation behavior
- [x] one simulated-truth language is already the documented direction
- [x] no-trade is already first-class in docs

This phase builds on top of those decisions. Do not regress them.

---

## 3. Background & Motivation

The old failure pattern would be:
- one cost model for labeling
- another for evaluation
- another for runtime replay reasoning
- a new V7-only pipeline simulator that drifts from runtime
- model-side simulation loops hidden inside training or inference

This phase prevents that by standardizing the **runtime simulation engine** and its side-effect-free adapters.

Runtime owns simulation execution. The model does not own simulation. The pipeline consumes simulation output.

---

## 4. Current Failure State / Known Blockers

The current state has the following known issues:

- existing runtime paper simulation behavior may not yet be documented as the shared engine surface
- `V6 simulation profile` and `V7 simulation profile` adapters may not yet be explicit
- training/replay and evaluation adapters may not yet be side-effect-free and versioned
- live execution side effects may not yet be clearly separated from replay/training simulation calls
- Monte Carlo robustness mode may not yet exist or may not yet be tied to runtime simulation lineage

---

## 5. Workstream A — Runtime Simulation Engine Standardization

**Status:** New

### Problem / Goal

Inspect existing runtime paper simulation behavior and standardize the runtime simulation engine interface for V6/V7 profile use.

### Implementation Tasks

- [ ] Identify the existing runtime simulation / paper-trading path
- [ ] Separate pure simulation execution from live exchange, broker, and mutable account-state side effects
- [ ] Define a deterministic runtime simulation input/output surface
- [ ] Support long / short / no-trade in one output family
- [ ] Preserve exit reason families
- [ ] Preserve raw no-trade comparative outputs:
  - `saved_loss_score`
  - `missed_opportunity_score`
  - `no_trade_counterfactual_quality`

### Acceptance Criteria

- [ ] runtime simulation engine can evaluate all three actions
- [ ] live execution side effects are not reachable from pure simulation calls
- [ ] long/short/no-trade use the same truth rules
- [ ] unresolved/invalid states are explicit
- [ ] raw no-trade comparative outputs exist for later label logic

---

## 6. Workstream B — Profiles, Costs, Exit, Horizon Semantics

**Status:** New

### Problem / Goal

Make runtime simulation profiles, costs, and exit semantics explicit and versioned.

### Implementation Tasks

- [ ] Add/confirm `V6 simulation profile`
- [ ] Add/confirm `V7 simulation profile`
- [ ] Support `model_scope` / `trade_mode` profiles for `SWING`, `SCALP`, and `AGGRESSIVE_SCALP`
- [ ] Implement or standardize fee model usage
- [ ] Implement or standardize slippage model usage
- [ ] Implement or standardize stop/target/time-exit behavior
- [ ] Implement or standardize horizon-end and invalidation rules

### Default invalidation rule

First implementation default:
- unresolved remains unresolved while the approved future window may still complete
- unresolved becomes invalidated after **2 × configured horizon length**
- immediate invalidation is allowed for explicitly irrecoverable/corrupted future data

### Configuration / Code Reference

```python
# expected config families
simulation_profile_version
runtime_simulation_adapter_version
cost_model_version
fee_model_version
slippage_model_version
horizon_family
invalidation_multiplier = 2.0
```

These are config-driven surfaces through the unified config system, not hardcoded parallel settings.

### Acceptance Criteria

- [ ] realized R includes cost semantics
- [ ] stop/target/time-exit are deterministic
- [ ] unresolved → invalidated behavior follows documented rules
- [ ] V6 and V7 profile/adapters are versioned

---

## 7. Workstream C — Side-Effect-Free Adapters And Replay Driver

**Status:** New

### Problem / Goal

Expose deterministic adapters for training, labels, and evaluation without calling live execution paths.

### Required adapter/driver families

- training/replay adapter
- evaluation replay adapter
- historical replay driver
- paper forward simulation driver

### Implementation Tasks

- [ ] Implement training/replay adapter over runtime simulation engine
- [ ] Implement evaluation replay adapter over runtime simulation engine
- [ ] Implement or standardize historical replay driver orchestration
- [ ] Confirm paper forward simulation uses the runtime simulation engine
- [ ] Preserve `simulation_run_id` / `replay_run_id` lineage

### Acceptance Criteria

- [ ] training adapter has no live execution side effects
- [ ] evaluation adapter has no live execution side effects
- [ ] paper driver and replay driver use the same runtime simulation engine semantics
- [ ] replay/training/evaluation runs preserve profile/version lineage

---

## 8. Workstream D — Path Metrics, Timing Annotation, And Monte Carlo Robustness

**Status:** New

### Problem / Goal

Expose path-aware quality and Monte Carlo robustness without letting timing metadata or randomized robustness runs rewrite execution truth.

#### 8.1 Core path metrics

```python
mfe_r
mae_r
time_to_mfe
time_to_mae
```

#### 8.2 Timing annotation rule

```python
entry_timing_annotation = "metadata_only"
```

Timing annotations may be preserved for audit but do not change entry price or exit rules in the same simulation family.

#### 8.3 Monte Carlo robustness mode

Monte Carlo robustness mode runs on top of the runtime simulation engine. It may produce:
- expected-R distribution
- downside risk
- target-before-stop probability
- stop-before-target probability
- tail risk
- confidence stability

Monte Carlo is diagnostic/distributional evidence. It is not live execution truth and does not replace paper forward simulation or historical replay.

### Acceptance Criteria

- [ ] path metrics exist in one normalized family
- [ ] metrics are deterministic for same non-Monte-Carlo input
- [ ] timing annotation is preserved as metadata only
- [ ] no silent entry-price mutation occurs due to timing annotation
- [ ] Monte Carlo mode produces distributional outputs with `monte_carlo_run_id` lineage

---

## 9. Workstream E — Test Coverage

**Status:** New
**Required before:** Phase 3 labels/outcomes

### 9.1 Runtime simulation invariant tests

- [ ] stop hit first scenario
- [ ] target hit first scenario
- [ ] time-exit scenario
- [ ] horizon-end unresolved scenario

### 9.2 Cost and path tests

- [ ] fee/slippage reduce realized R correctly
- [ ] MFE/MAE calculations are correct
- [ ] path quality score is deterministic

### 9.3 Adapter / driver tests

- [ ] training adapter has no live execution side effects
- [ ] evaluation adapter has no live execution side effects
- [ ] paper forward simulation and historical replay driver use the same runtime simulation engine semantics
- [ ] V6/V7 profile selection is versioned

### 9.4 Monte Carlo tests

- [ ] Monte Carlo mode produces distributional outputs
- [ ] Monte Carlo output preserves `monte_carlo_run_id`
- [ ] Monte Carlo evidence remains distinguishable from realized/live outcome truth

---

## 10. Workstream F — Pre-Run Audit Checklist

**Status:** New
**Must complete before:** label generation work

### 10.1 Simulation config audit

- [ ] verify cost/exit/horizon families exist in config
- [ ] verify no duplicate conflicting exit semantics are active
- [ ] verify V6/V7 simulation profiles are explicit

### 10.2 Ownership audit

- [ ] verify labels and evaluation consume runtime simulation outputs
- [ ] verify no model-side simulator is active
- [ ] verify no pipeline-owned simulator is considered authoritative
- [ ] verify no label-only or backtest-only simulator exists

### 10.3 Pending/invalid audit

- [ ] verify unresolved and invalidated are distinguishable
- [ ] verify partial future windows do not become fake final labels
- [ ] verify default invalidation timeout is implemented or explicitly overridden in config

---

## 11. Combined Implementation Order

1. Complete Workstream A — Runtime Simulation Engine Standardization
2. Implement Workstream B — Profiles, Costs, Exit, Horizon Semantics
3. Apply Workstream C — Side-Effect-Free Adapters And Replay Driver
4. Apply Workstream D — Path Metrics, Timing Annotation, And Monte Carlo Robustness
5. Run Workstream F — Pre-Run Audit
6. Implement Workstream E — Test Coverage
7. Execute runtime simulation scenario suite
8. Evaluate results against acceptance criteria

### Acceptance Criteria for First Combined Run

- [ ] long/short/no-trade outputs are produced by the runtime simulation engine
- [ ] realized R includes costs
- [ ] unresolved/invalid rules work as documented
- [ ] path metrics are present and correct
- [ ] training/evaluation adapters are side-effect-free
- [ ] Monte Carlo robustness output is distinguishable from realized outcome truth

---

## 12. Definition of Done

### 12.1 Runtime simulation layer

- [x] simulation semantics are documented
- [x] cost/path/horizon rules are specified
- [ ] runtime simulation engine interface is standardized
- [ ] runtime simulation profiles are version-aware

### 12.2 Adapter / driver layer

- [ ] training/replay adapter exists
- [ ] evaluation replay adapter exists
- [ ] historical replay driver exists or is standardized
- [ ] paper forward simulation uses the runtime simulation engine

### 12.3 Output layer

- [ ] comparative outputs exist
- [ ] path metrics exist
- [ ] resolution status exists
- [ ] raw no-trade comparative outputs exist
- [ ] Monte Carlo distributional outputs exist if included in Phase 2 scope

### 12.4 Candidate health

- [ ] no alternate truth layer silently competes with runtime simulation
- [ ] labels/evaluation/outcomes can consume runtime simulation outputs later
- [ ] timing metadata cannot silently rewrite canonical simulated truth
- [ ] simulated truth and execution truth remain distinguishable

### 12.5 Test layer

- [ ] scenario tests pass
- [ ] cost tests pass
- [ ] unresolved/invalid tests pass
- [ ] adapter side-effect tests pass
- [ ] Monte Carlo tests pass if included in Phase 2 scope

---

## 13. What Phase 3 Inherits

### 13.1 Capability expansion themes

- runtime-hosted simulated truth
- side-effect-free training/replay adapter outputs
- path-aware metrics
- cost-aware comparative action outputs
- raw no-trade comparative semantics
- Monte Carlo robustness evidence where configured

### 13.2 Phase Boundary

- Phase 3 is label and outcome semantics work.
- Phase 2 is the prerequisite.
- Do not start Phase 3 work until Phase 2 definition of done is fully satisfied.

---

## 14. Compact Mental Model

### 14.1 Phase Relationships

- Phase 1: contracts became real
- Phase 2: runtime simulation/adapters become real
- Phase 3: labels and outcomes become coherent
- Phase 4: training rows become valid

### 14.2 Key Takeaway

If Phase 2 creates a second simulator, V7 is already wrong.
The correct goal is one runtime simulation engine, side-effect-free adapters, clear replay/paper/Monte Carlo modes, and no model-owned simulation.
