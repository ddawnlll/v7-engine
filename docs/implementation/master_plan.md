
# V7 Master Implementation Plan

**Status:** Planned
**Owner:** V7 implementation track
**Last updated:** 2026-04-24
**Delivery status:** Not started

---

## 1. Purpose

This document defines the full implementation sequence for V7 from current repo state to first live-eligible release readiness.

It answers:

> In what exact order should V7 be built so that contracts, truth layer, learning pipeline, runtime integration, and deployment safety become correct without creating rework or hidden coupling?

This document is a sequencing authority, not a second architecture document.

---

## 2. What Must Stay Stable

The following are already documented and must remain stable:

- [x] V7 contract family semantics exist
- [x] V7 pipeline authority docs exist
- [x] Runtime integration, fallback, and deployment-safety direction exist
- [x] Atomic request/result/event/outcome boundaries are already defined
- [x] Runtime-hosted simulation engine / one simulated-truth layer is already the authoritative direction

This plan builds on top of those decisions.
Do not regress them during implementation.

Resolved model strategy: V7 uses one shared training framework with separate `model_scope` artifacts for `SWING`, `SCALP`, and `AGGRESSIVE_SCALP`; it must not train one universal model across those scopes. Each activated scope must satisfy its own data, model, calibration, evaluation, and release gates.

Resolved simulation strategy: runtime owns simulation execution. Phase 2 standardizes the runtime simulation engine, profiles, side-effect-free adapters, historical replay driver, and Monte Carlo robustness mode; it must not build a greenfield model-side or pipeline-owned simulator.

---

## 3. Background & Motivation

The repo now has enough design authority to stop expanding semantics and start implementing a coherent slice.

The old risk was:
- implementing runtime first
- training before truth-layer lock
- creating model artifacts before labels/evaluation semantics were stable

The correct approach is:
- bootstrap repo and typed surfaces first
- standardize the runtime-hosted simulation/truth layer before model family
- integrate runtime after policy/portfolio/risk semantics are concrete
- defer release complexity until evidence exists

---

## 4. Current Failure State / Known Blockers

The current state has the following known issues:

- `src/v7/*` = missing or partial — authoritative docs exist but implementation surfaces may not
- `contracts` = documented, not necessarily implemented as typed runtime objects
- `simulation truth` = documented, not yet guaranteed in code
- `runtime integration` = documented, not yet guaranteed in code
- `config surface` = required by all phases, not yet guaranteed as one implemented V7-resolved system
- `promotion / release authority` = referenced by later phases, not yet guaranteed as executable process

---

## 5. Phase Sequence

The full implementation sequence is:

1. **Phase 0 — Repo Alignment & Foundations**
2. **Phase 1 — Contracts & Validation**
3. **Phase 2 — Runtime Simulation, Replay & Monte Carlo Layer**
4. **Phase 3 — Labels & Outcome Semantics**
5. **Phase 4 — Features & Dataset**
6. **Phase 5 — Model Baseline**
7. **Phase 6 — Calibration & Policy**
8. **Phase 7 — Portfolio, Risk & Runtime Integration**
9. **Phase 8 — Evaluation & Monitoring**
10. **Phase 9 — Deployment Safety & Release Readiness**

---

## 6. Phase Dependency Rules

### Hard dependencies
- Phase 1 depends on Phase 0
- Phase 2 depends on Phase 1
- Phase 3 depends on Phase 2
- Phase 4 depends on Phases 2 and 3
- Phase 5 depends on Phase 4
- Phase 6 depends on Phase 5
- Phase 7 depends on Phase 6
- Phase 8 depends on Phases 5, 6, and 7
- Phase 9 depends on Phase 8

### Soft iteration loops
Allowed iteration loops:
- Phase 5 ↔ Phase 6
- Phase 6 ↔ Phase 8
- Phase 7 ↔ Phase 8

### Loop criteria
These loops are not “retry whenever it feels bad.”
They are triggered only when a defined acceptance gate fails.

#### Phase 5 ↔ Phase 6
Go back from calibration/policy to model baseline only when one of these is true:
- calibration error stays above the configured maximum on at least 2 consecutive folds
- no-trade distribution becomes structurally pathological after calibration/policy wrapping
- expected-R surface quality is too weak for policy to produce stable actionable decisions

#### Phase 6 ↔ Phase 8
Go back from evaluation to calibration/policy only when one of these is true:
- candidate fails promotion thresholds due primarily to calibration or policy behavior
- timing advisory outputs show no measurable usefulness across the required evaluation windows
- confidence vs expected-R conflict handling causes unacceptable no-trade or false-action behavior

#### Phase 7 ↔ Phase 8
Go back from evaluation to runtime integration only when one of these is true:
- actionability vs execution-eligibility gap is materially larger than configured tolerance
- fallback or degraded paths dominate beyond configured runtime-health thresholds
- lifecycle objects are correct in shape but wrong in sequencing or propagation

Not allowed:
- skipping Phase 2 and training first
- implementing live runtime authority before Phase 8 evidence
- expanding model/policy semantics before contract compatibility exists

---

## 7. Global Success Criteria

V7 implementation is not considered complete until all of the following are true:

- [ ] typed contract surfaces exist and validate correctly
- [ ] runtime simulation engine powers labels, evaluation, outcomes, replay, paper forward simulation, and Monte Carlo robustness mode through side-effect-free adapters
- [ ] feature and dataset surfaces are leakage-safe
- [ ] one shared training framework trains and loads separate activated `model_scope` artifacts correctly
- [ ] confidence surface is calibrated or explicitly downgraded
- [ ] policy emits compact normalized decisions
- [ ] portfolio and risk blocks are explicit
- [ ] runtime creates events and outcomes correctly
- [ ] evaluation compares candidate vs baseline credibly
- [ ] deployment safety gates, rollback, and kill switch are testable

### Evidence mapping
These success criteria are satisfied by phase definition-of-done gates:

- contracts → Phase 1 DoD
- runtime simulation truth/adapters → Phase 2 DoD
- labels/outcomes → Phase 3 DoD
- features/dataset → Phase 4 DoD
- baseline model → Phase 5 DoD
- calibration/policy → Phase 6 DoD
- runtime integration → Phase 7 DoD
- evaluation/monitoring → Phase 8 DoD
- release safety → Phase 9 DoD

A global success criterion is not considered satisfied until its owning phase definition of done is fully satisfied.

---

## 8. Document Index

Read the per-phase plans in this order:

- `phase_0_repo_alignment_and_foundations.md`
- `phase_1_contracts_and_validation.md`
- `phase_2_simulation_truth_layer.md`
- `phase_3_labels_and_outcome_semantics.md`
- `phase_4_features_and_dataset.md`
- `phase_5_model_baseline.md`
- `phase_6_calibration_and_policy.md`
- `phase_7_portfolio_risk_and_runtime_integration.md`
- `phase_8_evaluation_and_monitoring.md`
- `phase_9_deployment_safety_and_release.md`

---

## 9. Post-Phase 9 Direction

After Phase 9, V7 moves into controlled expansion work.

That includes:
- optimization of promoted families
- broader symbol-universe activation
- timing-gate promotion only if Phase 8 evidence supports it
- advanced portfolio/risk sophistication only after the first safe live-eligible slice exists
- optional deeper model-family experimentation

Post-Phase 9 does **not** create a new contract family automatically.
Phase 9 remains the prerequisite for expansion.

---

## 10. Compact Mental Model

### 10.1 Phase Relationships
- Phase 0: make the repo safe to build in
- Phase 1: make contracts real
- Phase 2: make runtime simulation, replay adapters, and Monte Carlo robustness real
- Phase 3: make labels/outcomes consistent
- Phase 4: make training rows valid
- Phase 5: make the first model real
- Phase 6: make decision surfaces operational
- Phase 7: make runtime consume them correctly
- Phase 8: prove quality and drift behavior
- Phase 9: prove release safety

### 10.2 Key Takeaway

V7 should be built from truth upward, not from runtime downward.
If runtime simulation adapters, labels, and evaluation are wrong, later runtime polish only hides broken semantics.
