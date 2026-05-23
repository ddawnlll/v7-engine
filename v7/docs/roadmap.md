# V7 Roadmap

## Purpose

Defines the recommended implementation and rollout order for V7.

It answers:

> Now that the documentation set exists, what should be implemented first, what can wait, and what should not be mixed into the early phases?

This is a sequencing document, not a second architecture document.

---

## Core Position

V7 should be built in layers:

1. contract correctness
2. truth-layer correctness
3. dataset/model correctness
4. calibration/policy correctness
5. runtime integration correctness
6. safety and rollout hardening

Do not start with the hardest runtime or infra problems.

---

## Current State

Documentation authority is largely complete for:

- core direction
- **mode-centric architecture** (see `v7_mode_centric_architecture.md`)
- **regime-aware extensions** (see `v7_regime_aware_extensions.md`)
- contract family
- runtime integration
- runtime fallback/deployment policy
- full pipeline authority set

That means the next work should be implementation-led, not more concept invention.

---

## Recommended Delivery Order

### Phase 0 — Repo alignment
Goal:
- create module skeletons
- create config skeleton
- create contract types
- create test scaffolding

Exit condition:
- repository shape matches docs enough to begin implementation safely
- contract and config module skeleton tests pass

---

### Phase 1 — Contract surfaces
Goal:
- implement `AnalysisRequest`
- implement `AnalysisResult`
- implement `DecisionEvent`
- implement `TradeOutcome`
- contract validation tests

Exit condition:
- atomic lifecycle objects exist
- serialization / validation / round-trip tests pass

---

### Phase 2 — Runtime simulation, replay, and Monte Carlo layer
Goal:
- standardize the existing runtime-hosted simulation engine interface
- separate pure simulation paths from live execution side effects
- add/confirm `V6 simulation profile` and `V7 simulation profile` adapters
- add deterministic training/replay and evaluation adapters
- standardize paper forward simulation and historical replay driver behavior
- add or plan Monte Carlo robustness mode on top of the runtime simulation engine

Exit condition:
- runtime simulation scenario tests pass
- training/evaluation adapters are side-effect-free
- labels, evaluation, paper forward simulation, historical replay, outcomes, and Monte Carlo robustness mode consume the same runtime simulation engine semantics

---

### Phase 3 — Labels and features
Goal:
- implement label generation by `model_scope`
- implement canonical-state feature generation for scope defaults (`SWING` 4h/1d/1h, `SCALP` 15m/1h/5m, `AGGRESSIVE_SCALP` 1m-or-3m with 5m/15m context)
- implement schema/version tests

Exit condition:
- deterministic feature/label rows can be produced from canonical state and runtime simulation adapter outputs
- leakage and ambiguity tests pass

---

### Phase 4 — Dataset assembly
Goal:
- implement walk-forward dataset construction with separate dataset families by `model_scope` and no mixing of primary clocks or label horizons
- symbol weighting / balancing
- lineage-preserving row export

Exit condition:
- training-ready datasets exist without temporal leakage
- walk-forward dataset tests pass

---

### Phase 5 — Model and calibration
Goal:
- train first XGBoost model-suite baseline or staged scope baseline under one shared training framework without model-side simulation
- `SWING` may be implemented first, with `SCALP` and `AGGRESSIVE_SCALP` added as separate artifacts under the same framework
- produce calibration artifacts per scope
- validate confidence surface per scope
- validate no-trade behavior per scope

Exit condition:
- each activated `model_scope` candidate produces stable calibrated outputs
- model + calibration smoke/evaluation tests pass per activated scope

Note:
This phase produces **candidate** artifacts, not automatically promoted artifacts.

---

### Phase 6 — Policy / portfolio / risk
Goal:
- implement policy surface per `model_scope`
- implement portfolio suppression
- implement risk hard guards
- keep timing extension advisory-first

Exit condition:
- normalized result surface matches documented semantics
- policy / portfolio / risk integration tests pass

---

### Phase 7 — Runtime integration
Goal:
- request builder
- result validator
- event creation
- outcome lifecycle
- actionability vs execution-eligibility split

Primary authority:
- `runtime/runtime_integration.md`

Exit condition:
- runtime can consume V7 contracts safely in replay/paper contexts
- lifecycle integration tests pass

---

### Phase 8 — Evaluation and monitoring
Goal:
- candidate vs baseline comparison per `model_scope`
- walk-forward review per `model_scope`
- calibration review per `model_scope`
- no-trade review per `model_scope`
- monitoring by `model_scope`, including fallback/degraded rate, calibration drift, and harmful symbol-side cohorts
- promotion gate per `model_scope`

Exit condition:
- promotion is evidence-based rather than subjective
- baseline update rules are implemented per scope
- evaluation/monitoring distinguishes activated scopes and does not infer one scope's safety from another

---

### Phase 9 — Deployment safety
Goal:
- paper mode per `model_scope`
- shadow mode where required per `model_scope`
- deployment safety gates per `model_scope`
- rollback and kill switch hardening with compatible scope artifact bundles

Exit condition:
- rollout gates from `runtime/deployment_safety.md` are testable
- rollback and kill switch tests pass
- release gate distinguishes:
  - candidate
  - paper-eligible
  - live-eligible

### Shadow-mode rule
Shadow mode is optional for general experimentation.
For the **first live-eligible V7 release**, shadow should be treated as required unless release authority explicitly waives it.

---

## Iteration Rule

The roadmap is logically phased, but implementation is not perfectly linear.

Expected loop:
- train
- calibrate
- evaluate
- adjust
- re-train
- re-evaluate

Do not treat Phase 5 and Phase 9 as a contradiction.
Phase 5 creates candidates.
Phase 9 decides promotion discipline.

---

## Things That Should Wait

These are explicitly not first implementation priorities.

### Full runtime rewrite
Wait because V7 first needs:
- stable contracts
- stable simulation truth
- stable runtime integration boundaries

### Large deep-learning stack
Wait because first phase is about:
- shared baseline quality
- explainable economic surfaces
- calibration discipline

### Per-symbol model or calibration families
Wait until shared-family evidence clearly fails and a new family is justified.

### Heavy timing planner
Wait until advisory timing evidence proves operational value.

### Advanced portfolio optimizer
Wait until lightweight portfolio rules are proven insufficient.

---

## First Real Release Shape

The first credible V7 release should be able to do all of these:

- consume valid atomic request
- produce valid atomic result
- create decision event
- create/update trade outcome
- run the runtime-hosted simulation engine through paper/replay adapters
- generate labels/features/datasets
- train a scope-compatible baseline model suite or staged activated scope artifact
- calibrate each activated scope artifact
- apply compact policy
- paper or replay evaluate it safely through the runtime simulation engine
- monitor degradation and coverage

If it cannot do these, it is not yet a complete V7 slice.

---

## Success Criteria

The first implementation milestone should demonstrate:

- contract-family correctness
- no hidden degraded paths
- runtime-hosted simulation engine shared by labels, evaluation, replay, paper, outcomes, and Monte Carlo robustness mode through side-effect-free adapters
- no-trade quality is measurable
- confidence is calibrated or visibly uncalibrated
- event/outcome lifecycle is traceable
- runtime can distinguish actionability from execution eligibility

---

## Artifact Lifecycle Note

Artifact publishing, promotion, rollback, and retirement are separate concerns.

Minimal rule set:
- training creates candidate artifacts
- evaluation determines promotability
- deployment safety governs live eligibility
- rollback changes forward active authority, not historical records

Do not collapse these into one vague “publish” step.

---

## Final Position

The roadmap for V7 is not:
- write everything
- rewrite runtime
- hope it works

It is:
- lock semantics
- implement the smallest coherent slice
- prove the truth layer
- prove the contract layer
- prove the learning layer
- only then broaden runtime and deployment sophistication
