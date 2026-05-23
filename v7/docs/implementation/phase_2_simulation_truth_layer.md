# Phase 2 — Runtime Simulation, Replay & Monte Carlo Layer (Planned)

**Status:** Planned  
**Owner:** Runtime simulation / truth-layer track  
**Last updated:** 2026-05-23  
**Delivery status:** Not started

---

## 1. Purpose

Standardize the runtime-hosted simulation engine used by V7 labels, evaluation, replay, paper forward simulation, outcome normalization, and Monte Carlo robustness.

This phase does not train models. It produces the economic truth that hybrid labels and regression targets will consume.

---

## 2. Stable Rules

- Runtime owns simulation execution.
- The model does not own simulation.
- The pipeline consumes simulation outputs through side-effect-free adapters.
- There must not be a label-only simulator or a backtest-only simulator.
- Long, short, and no-trade are evaluated under one simulation family.

---

## 3. Workstream A — Runtime Simulation Engine Standardization

The simulation engine must evaluate:

- `LONG_NOW`
- `SHORT_NOW`
- `NO_TRADE`

Minimum comparative outputs:

- `realized_r_long`
- `realized_r_short`
- `no_trade_outcome_quality`
- `saved_loss_score`
- `missed_opportunity_score`
- `best_action`
- `second_best_action`
- `action_gap_r`
- resolution status

These outputs feed both classification labels and regression targets.

### Acceptance Criteria

- [ ] all three actions are evaluated in one output family.
- [ ] long/short/no-trade use identical cost and horizon semantics.
- [ ] no-trade has raw comparative outputs.

---

## 4. Workstream B — Profiles, Costs, Exit, Horizon Semantics

Implement versioned config families for:

- `simulation_profile_version`
- `runtime_simulation_adapter_version`
- `cost_model_version`
- `fee_model_version`
- `slippage_model_version`
- `horizon_family`
- `stop_family`
- `target_family`
- `time_exit_family`
- `invalidation_multiplier`

Default invalidation behavior:

- unresolved remains unresolved while approved future window may still complete
- unresolved becomes invalidated after `2 × configured horizon length`
- immediate invalidation is allowed for irrecoverable/corrupted future data

### Acceptance Criteria

- [ ] realized R includes costs.
- [ ] stop/target/time-exit are deterministic.
- [ ] unresolved and invalidated states remain distinct.

---

## 5. Workstream C — Side-Effect-Free Adapters and Replay Driver

Required adapter/driver families:

- training/replay adapter
- evaluation replay adapter
- historical replay driver
- paper forward simulation driver

Adapter outputs must preserve:

- `simulation_run_id`
- `replay_run_id`
- `simulation_profile_version`
- `cost_model_version`
- `horizon_family`
- `model_scope`

### Acceptance Criteria

- [ ] training adapter has no live execution side effects.
- [ ] evaluation adapter has no live execution side effects.
- [ ] paper and replay use the same runtime simulation semantics.

---

## 6. Workstream D — Path Metrics and Monte Carlo Robustness

Core path metrics:

- `mfe_r`
- `mae_r`
- `time_to_mfe`
- `time_to_mae`
- `path_quality_score`

Monte Carlo robustness may produce:

- expected-R distribution
- downside risk
- target-before-stop probability
- stop-before-target probability
- tail risk
- confidence stability

Monte Carlo is diagnostic/distributional evidence. It does not replace realized simulation truth.

Timing annotations are metadata-only in first phase and must not silently alter entry price or exit rules.

### Acceptance Criteria

- [ ] path metrics are deterministic for non-Monte-Carlo input.
- [ ] Monte Carlo output carries `monte_carlo_run_id` lineage.
- [ ] timing annotations cannot mutate canonical simulation truth.

---

## 7. Workstream E — Test Coverage

Minimum tests:

- stop-hit first
- target-hit first
- time-exit
- horizon-end unresolved
- invalidated after missing data window
- fee/slippage reduce R
- MFE/MAE correctness
- no-trade saved-loss and missed-opportunity outputs
- adapter side-effect isolation
- V6/V7 profile selection versioning
- Monte Carlo output is distinguishable from realized truth

---

## 8. Pre-Run Audit

Before Phase 3:

- [ ] labels and evaluation consume runtime simulation outputs only
- [ ] no model-side simulator exists
- [ ] no label-only truth family exists
- [ ] unresolved/invalid states cannot become fake final labels

---

## 9. Definition of Done

- [ ] runtime simulation engine interface is standardized.
- [ ] comparative outputs exist for long/short/no-trade.
- [ ] cost/path/horizon rules are versioned.
- [ ] side-effect-free adapters exist.
- [ ] tests pass.

---

## 10. What Phase 3 Inherits

Phase 3 inherits cost-aware comparative truth that can produce both classification labels and regression targets.
p!