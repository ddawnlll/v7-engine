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
- **profitability thesis** (see `profitability_thesis.md` — P0.6A design lock)
- contract family
- runtime integration
- runtime fallback/deployment policy
- full pipeline authority set

**P0.7A-C Lock Status (2026-06-18):**
- **P0.7A — Simulation MVP:** ✅ PASS. Simulation truth authority has minimal viable implementation (contracts, engine, exits, costs, golden tests, import boundary). 222 tests pass. `SimulationProfile` fixture exists.
- **P0.7B — CI Enforcement:** ✅ PASS (CI_FIRST_GREEN_RUN_HOLD). `.github/workflows/ci.yml` enforces contract checks, boundary checks, and full test suite on push/PR. First GitHub green run pending verification.
- **P0.7C — SWING Thresholds:** ✅ PASS. SWING promotion thresholds are **LOCKED_INITIAL_BASELINE** — owner-reviewed conservative baselines ready for implementation. SCALP and AGGRESSIVE_SCALP thresholds are **HOLD** pending empirical evidence.
- **P0.x — Policy Critic RL Research:** ✅ PASS. Full research + codebase mapping (V7 pipeline, AlphaForge, Simulation, Contracts/Runtime) + literature review (offline RL methods, critic/calibration, reward design, finance RL failure modes) + grounded RL architecture recommendation completed. **LOCK_CANDIDATE** — design documented in `v7/docs/policy_critic/`. Open HOLDs (replay buffer, regret_r, funding, per-direction expected_R, synthesized features, conformal exchangeability) must be resolved before lock.

**Design Lock Status:** The V7 pre-implementation design is now **LOCKABLE_WITH_HOLDS**. Implementation can proceed with SWING as secondary baseline/control mode (LOCKED_INITIAL_BASELINE thresholds). Remaining holds are explicitly scoped (funding DEFERRED, SCALP/AGGRESSIVE_SCALP HOLD, CI first green run hold).

That means the next work should be implementation-led, not more concept invention. **Implementation starts with SWING as the secondary baseline/control mode — the safest, most lockable starting point. Primary business/research priority is SCALP and AGGRESSIVE_SCALP (see Mode Priority Alignment below).**

---

## Mode Priority Alignment

### Primary vs Secondary Mode Classification

The mode implementation order (SWING first) must not be confused with business/research priority.

| Mode | Business Priority | Research Priority | Threshold Status | AlphaForge Report Type | Promotion Readiness |
|------|------------------|-------------------|-----------------|----------------------|---------------------|
| SCALP | **PRIMARY** | **PRIMARY** | HOLD (empirical evidence required) | Primary research report | Not ready until evidence |
| AGGRESSIVE_SCALP | **PRIMARY** | **PRIMARY** | HOLD (empirical evidence required) | Primary research report | Not ready until evidence |
| SWING | SECONDARY_BASELINE | SECONDARY_BASELINE | LOCKED_INITIAL_BASELINE | Secondary baseline report | Baseline ready; recalibration required after first evidence |

### Key Principles

1. **SCALP and AGGRESSIVE_SCALP are the PRIMARY business/research modes.** V7's main edge search targets shorter-term opportunities, anomaly capture, cost-aware fast reaction, and high-frequency signal validation. These modes carry the highest commercial upside.

2. **SWING is the SECONDARY_BASELINE / CONTROL mode.** SWING was locked first because it is safer, lower-noise, and easier to baseline — not because it is the primary product. It serves as a control anchor: if SWING fails, something is fundamentally wrong. If SWING works, it validates the architecture but does not validate SCALP or AGGRESSIVE_SCALP.

3. **HOLD on SCALP/AGGRESSIVE_SCALP means "empirical research required" — not "low priority."** Fee, slippage, latency, data quality, overfit, and funding risks make these modes harder to lock without evidence. Their HOLD status reflects research difficulty, not business importance.

4. **Promotion-readiness and research-priority are independent dimensions.** SWING is more promotion-ready (LOCKED_INITIAL_BASELINE). SCALP and AGGRESSIVE_SCALP have higher business/research priority but require empirical evidence before threshold lock.

5. **AlphaForge must support all three modes.** AlphaForge produces primary research reports for SCALP and AGGRESSIVE_SCALP, and a secondary baseline/control report for SWING. No mode is optional.

### AlphaForge Authority Lock (P0.8B+C)

**P0.8B — AlphaForge Discovery Authority Lock:** AlphaForge authority boundaries, docs, contracts, and report-level schemas are now LOCKED. See [../../alphaforge/docs/ai_summary.md](../../alphaforge/docs/ai_summary.md) for the thin hub.

**Key outcomes:**
- AlphaForge authority boundary is explicit: discovers alpha, does NOT decide trades
- 10 contract schemas, 5 minimal fixtures, 2 mapping docs created
- `contracts/registry.json` updated with AlphaForge contract entries
- `contracts/compatibility.json` updated with AlphaForge compatibility rules
- All three modes have ModeResearchReport contracts (SCALP/AGGRESSIVE_SCALP: primary_research_report, SWING: secondary_baseline_report)

**Verdict:** LOCKABLE_WITH_HOLDS. Ready for P0.9A implementation scaffold.

### Implementation Sequence

SWING is implemented first as the **control baseline** — it validates the entire architecture (contracts, simulation truth, labels, features, model training, calibration, policy, portfolio, risk, runtime integration) with the lowest risk. Once the architecture is proven via SWING, SCALP and AGGRESSIVE_SCALP research accelerates on a validated foundation.

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
- `SWING` is the secondary baseline/control mode — implemented first to validate the architecture with lowest risk. `SCALP` and `AGGRESSIVE_SCALP` are PRIMARY business/research modes added as separate artifacts under the same framework after SWING validates the architecture.
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
