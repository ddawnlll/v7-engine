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

### Phase 2 — Simulation truth layer
Goal:
- implement comparative simulation (shared simulation core for engine and runtime)
- implement cost model
- implement path metrics
- implement unresolved / invalid logic
- explicitly support forward simulation (paper trading) and historical replay (via replay driver)

Exit condition:
- simulation scenario tests pass
- labels, evaluation, runtime paper trading, and replay can share one simulation truth layer

---

### Phase 3 — Labels and features
Goal:
- implement label generation
- implement canonical-state feature generation (including 4h primary, 1d context, and 1h refinement features)
- implement schema/version tests

Exit condition:
- deterministic feature/label rows can be produced from canonical state
- leakage and ambiguity tests pass

---

### Phase 4 — Dataset assembly
Goal:
- implement walk-forward dataset construction (fused multi-view rows, not separate interval universes)
- symbol weighting / balancing
- lineage-preserving row export

Exit condition:
- training-ready datasets exist without temporal leakage
- walk-forward dataset tests pass

---

### Phase 5 — Model and calibration
Goal:
- train first XGBoost baseline (one shared interval-aware, multi-view model family)
- produce calibration artifact
- validate confidence surface
- validate no-trade behavior

Exit condition:
- candidate model family produces stable calibrated outputs
- model + calibration smoke/evaluation tests pass

Note:
This phase produces **candidate** artifacts, not automatically promoted artifacts.

---

### Phase 6 — Policy / portfolio / risk
Goal:
- implement policy surface
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

### Phase 8 — Deployment safety
Goal:
- paper mode
- shadow mode where required
- deployment safety gates
- rollback and kill switch hardening

Exit condition:
- rollout gates from `runtime/deployment_safety.md` are testable
- rollback and kill switch tests pass

### Shadow-mode rule
Shadow mode is optional for general experimentation.
For the **first live-eligible V7 release**, shadow should be treated as required unless release authority explicitly waives it.

---

### Phase 9 — Evaluation and promotion discipline
Goal:
- candidate vs baseline comparison
- walk-forward review
- calibration review
- no-trade review
- promotion gate

Exit condition:
- promotion is evidence-based rather than subjective
- baseline update rules are implemented
- release gate distinguishes:
  - candidate
  - paper-eligible
  - live-eligible

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
- run one simulation truth layer
- generate labels/features/datasets
- train one shared baseline model
- calibrate it
- apply compact policy
- paper or replay evaluate it safely
- monitor degradation and coverage

If it cannot do these, it is not yet a complete V7 slice.

---

## Success Criteria

The first implementation milestone should demonstrate:

- contract-family correctness
- no hidden degraded paths
- one simulation truth layer shared by labels and evaluation
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
