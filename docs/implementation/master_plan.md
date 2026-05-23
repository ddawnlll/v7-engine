# V7 Hybrid Master Implementation Plan

**Status:** Planned  
**Owner:** V7 implementation track  
**Last updated:** 2026-05-23  
**Delivery status:** Not started

---

## 1. Purpose

This document defines the implementation sequence for V7 after the architecture decision to make the first learned system a **hybrid supervised trading model**.

It answers:

> In what order should V7 be built so that simulation truth, hybrid labels, hybrid model outputs, calibration, policy, runtime integration, and release safety stay aligned?

This is a sequencing authority. It does not replace the pipeline authority docs.

---

## 2. Stable Decisions

These decisions remain stable and must not be regressed:

- V7 is contract-first and uses the atomic lifecycle family: `AnalysisRequest`, `AnalysisResult`, `DecisionEvent`, `TradeOutcome`.
- V7 uses one simulation truth layer for labels, evaluation, replay, paper forward simulation, and outcome normalization.
- V7 is XGBoost-first for the first implementation phase.
- V7 remains centralized, multi-symbol aware, and runtime/engine separated.
- Runtime owns request assembly, validation, lifecycle persistence, execution eligibility, and operational safety.
- Engine owns market-state interpretation, model scoring, calibrated confidence, expected-R surfaces, recommended action, timing guidance, and visible degradation state.
- The first-phase action family remains compact: `LONG_NOW`, `SHORT_NOW`, `NO_TRADE`.

---

## 3. Resolved Hybrid Model Strategy

V7 first implementation uses an **XGBoost-first hybrid supervised decision model**.

The first baseline is not pure classification and not pure regression.

It consists of:

1. **Classification surface**
   - action probabilities for `LONG_NOW`, `SHORT_NOW`, `NO_TRADE`
   - primary owner of action selection probability

2. **Regression surface**
   - `expected_r_long`
   - `expected_r_short`
   - optional first-phase risk/economic regressors where supported:
     - `expected_adverse_r_long`
     - `expected_adverse_r_short`
     - `expected_cost_adjusted_r_long`
     - `expected_cost_adjusted_r_short`

3. **Policy surface**
   - calibrated probability + expected-R + risk gates
   - explicit no-trade selection
   - timing guidance remains advisory-first

### Scope rule

V7 uses one shared training framework with separate `model_scope` artifacts when multiple scopes are activated:

- `SWING`
- `SCALP`
- `AGGRESSIVE_SCALP`

Do not train one universal artifact across incompatible scopes. Each activated scope must satisfy its own dataset, model, calibration, evaluation, and release gates.

First implementation may stage `SWING` first.

---

## 4. Revised Phase Sequence

1. **Phase 0 — Repo Alignment & Hybrid Foundations**
2. **Phase 1 — Contracts & Hybrid Validation**
3. **Phase 2 — Runtime Simulation, Replay & Monte Carlo Layer**
4. **Phase 3 — Hybrid Labels & Outcome Semantics**
5. **Phase 4 — Features & Hybrid Dataset**
6. **Phase 5 — XGBoost Hybrid Model Baseline**
7. **Phase 6 — Calibration, Expected-R Reliability & Policy**
8. **Phase 7 — Portfolio, Risk & Runtime Integration**
9. **Phase 8 — Hybrid Evaluation & Monitoring**
10. **Phase 9 — Deployment Safety & Release Readiness**

The phase order stays close to the original plan, but Phase 1, 3, 4, 5, 6, 8, and 9 now explicitly understand the hybrid output surface.

---

## 5. Hard Dependencies

- Phase 1 depends on Phase 0.
- Phase 2 depends on Phase 1.
- Phase 3 depends on Phase 2.
- Phase 4 depends on Phases 2 and 3.
- Phase 5 depends on Phase 4.
- Phase 6 depends on Phase 5.
- Phase 7 depends on Phase 6.
- Phase 8 depends on Phases 5, 6, and 7.
- Phase 9 depends on Phase 8.

Do not train before simulation truth and hybrid labels exist.

---

## 6. Soft Iteration Loops

Allowed loops:

- Phase 5 ↔ Phase 6
- Phase 6 ↔ Phase 8
- Phase 7 ↔ Phase 8

### Phase 5 ↔ Phase 6 triggers

Return from policy/calibration to model only when:

- classification calibration error remains above threshold across repeated folds
- expected-R regression error or rank quality is too weak for policy gates
- probability and expected-R surfaces strongly conflict in a way policy cannot stabilize
- no-trade distribution becomes structurally pathological after calibration and policy wrapping

### Phase 6 ↔ Phase 8 triggers

Return from evaluation to calibration/policy when:

- promotion failure is primarily caused by threshold/policy behavior
- expected-R gate blocks too many profitable trades or allows too many negative expectancy trades
- confidence vs expected-R conflict handling causes unacceptable false-action or over-no-trade behavior
- timing advisory outputs show no measurable value across required windows

### Phase 7 ↔ Phase 8 triggers

Return from evaluation to runtime integration when:

- actionability vs execution-eligibility gap is above tolerance
- fallback/degraded paths dominate beyond runtime-health thresholds
- lifecycle objects carry hybrid outputs incorrectly
- portfolio/risk suppression hides or loses expected-R/probability context

---

## 7. Global Success Criteria

V7 implementation is complete only when:

- typed contracts validate hybrid outputs correctly
- runtime simulation powers labels, evaluation, outcomes, replay, paper forward simulation, and Monte Carlo robustness through side-effect-free adapters
- labels include both classification targets and regression targets
- datasets preserve target lineage and exclude unresolved/invalid rows by default
- feature and dataset surfaces are leakage-safe
- the hybrid XGBoost baseline trains and loads scope-compatible artifacts
- calibrated confidence is available or explicitly downgraded
- expected-R reliability is measured and visible
- policy emits compact normalized decisions using probability + expected-R + risk gates
- portfolio and risk blocks are explicit
- runtime persists hybrid score snapshots in decision lifecycle records
- evaluation compares candidate vs baseline economically and by hybrid-surface quality
- deployment safety gates, rollback bundles, and kill switch are testable

---

## 8. Document Index

Read the revised phase docs in this order:

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

## 9. Compact Mental Model

V7 should be built from truth upward:

```text
runtime simulation truth
      ↓
hybrid labels and regression targets
      ↓
leakage-safe features and dataset rows
      ↓
XGBoost action classifier + expected-R regressors
      ↓
calibration and expected-R reliability
      ↓
policy gates
      ↓
portfolio/risk/runtime lifecycle
      ↓
evaluation, monitoring, and release safety
```

If simulation, labels, or hybrid result contracts are wrong, later runtime polish only hides broken semantics.
